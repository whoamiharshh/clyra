import os
import json
import re
from dotenv import load_dotenv

from kernel.context import repo_map, tokens
from security.privacy_checker import sanitize_untrusted_text

load_dotenv()

STOP_WORDS = {
    'the', 'a', 'an', 'is', 'to', 'for', 'with', 'and', 'or',
    'in', 'on', 'at', 'by', 'this', 'that', 'it', 'be', 'as',
    'are', 'was', 'will', 'can', 'should', 'would', 'could'
}

HALF_CONTEXT_DIVISOR = 2


def _truncate_at_symbol_boundary(text: str, max_tokens: int) -> str:
    """Trim outline text to <= max_tokens, cutting back to the start of a symbol line."""
    if tokens(text) <= max_tokens:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if tokens(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid - 1
    cut = text[:lo]
    last_nl = cut.rfind('\n')
    cut = cut[:last_nl] if last_nl != -1 else cut
    symbol_start = re.search(r'^(?:class |def |async def |[A-Za-z_][\w.]*:)', cut[max(0, last_nl - 200):], re.M)
    # Walk back to the most recent line starting a file block or symbol definition.
    lines = cut.splitlines()
    while lines and not re.match(r'^\s*(def |class |async def |[A-Za-z_][\w./]*\.py:)', lines[-1]):
        lines.pop()
    if not lines:
        return cut
    return '\n'.join(lines) + '\n... truncated at symbol boundary'


class TaskAnalyzer:

    def __init__(self, file_reader, bifrost_client):
        self.file_reader = file_reader
        self.bifrost = bifrost_client

    def extract_keywords(self, task: str) -> list:
        words = re.findall(r'\b[a-zA-Z]+\b', task.lower())
        return [w for w in words if w not in STOP_WORDS and len(w) > 2]

    def _build_planning_prompt(self, task: str, repo_path: str) -> tuple:
        """Build the planning prompt from repo_map(), capped at max_context_tokens // 2."""
        from kernel.settings import settings

        the_map = repo_map(repo_path)
        cap = settings.max_context_tokens // HALF_CONTEXT_DIVISOR
        overhead = 350  # instructions + JSON schema + task text
        budget = max(200, cap - overhead)
        trimmed = _truncate_at_symbol_boundary(the_map, budget)
        used = tokens(trimmed)

        # Second-stage reduction for oversized maps: compress the code-derived
        # map text only. Instructions and the JSON schema are never compressed.
        if used > budget:
            try:
                from kernel.compress import compress_code, maybe_log
                trimmed, cmeta = compress_code(trimmed)
                used = tokens(trimmed)
                if 'orig_tokens' in cmeta:
                    maybe_log(cmeta, label='repo_map')
            except Exception:
                pass  # compression must never break planning

        task = sanitize_untrusted_text(task, context="task")
        prompt = f"""You are analyzing a coding task to break it into atomic decisions.

REPOSITORY MAP (paths and top-level symbols with line ranges):
{trimmed}

TASK: {task}

Break this task into 3-6 atomic decisions. Each decision is one specific choice.
Reference files by the paths shown in the map above.

Return ONLY valid JSON, no other text:
{{
  "decisions": [
    {{
      "id": 1,
      "name": "short name under 5 words",
      "description": "what needs to be decided, include library names and API names if relevant",
      "relevant_file": "filename.py or null",
      "relevant_lines": "line range like 10-25 or null"
    }}
  ],
  "summary": "one line of what will change"
}}"""
        return prompt, used

    def _fallback_plan(self, task, relevant_files, baseline_tokens, actual_tokens, repo_info):
        return {
            'decisions': [
                {
                    'id': 1,
                    'name': 'analyze and fix',
                    'description': f'Complete the following task: {task}',
                    'relevant_file': relevant_files[0] if relevant_files else None,
                    'relevant_lines': None
                }
            ],
            'summary': task,
            'baseline_tokens': baseline_tokens,
            'actual_tokens': actual_tokens,
            'relevant_files': relevant_files,
            'python_file_count': repo_info
        }

    def analyze(self, task: str, repo_path: str) -> dict:
        keywords = self.extract_keywords(task)

        repo_info = self.file_reader.scan_repo_structure(repo_path)
        relevant_files = self.file_reader.find_relevant_files(repo_path, keywords)

        # True naive baseline: every .py file read in full
        total_repo_chars = 0
        py_count = 0
        for fpath in repo_info['python_files']:
            try:
                with open(fpath, 'r', encoding='utf-8', errors='ignore') as fh:
                    total_repo_chars += len(fh.read())
                    py_count += 1
            except Exception:
                pass
        print(f"[baseline] python_files={len(repo_info['python_files'])} readable={py_count} chars={total_repo_chars}")

        naive_prompt_overhead = 400
        estimated_response = total_repo_chars
        baseline_tokens = (total_repo_chars + naive_prompt_overhead + estimated_response) // 4

        # Decision-plan cache: skip the LLM entirely when nothing changed.
        try:
            from kernel.settings import settings as _s
            if not _s.feature_flags.cache:
                raise Exception("cache disabled")
            from kernel.cache import get_decision, put_decision
            cached = get_decision(task, repo_path)
            if cached is not None:
                saved = 900 + len(json.dumps(cached)) // 4  # typical planning prompt + response
                print(f"[cache] decision-plan hit (saved ~{saved} tokens)")
                return {
                    'decisions': cached,
                    'summary': '',
                    'baseline_tokens': baseline_tokens,
                    'actual_tokens': 0,
                    'relevant_files': relevant_files,
                    'python_file_count': len(repo_info['python_files']),
                    'from_cache': True,
                }
        except Exception:
            pass  # cache must never break planning

        prompt, actual_tokens = self._build_planning_prompt(task, repo_path)

        messages = [{"role": "user", "content": prompt}]

        try:
            response, resp_tokens, cost = self.bifrost.call_cheap(messages)

            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                parsed = json.loads(json_match.group())
                parsed['baseline_tokens'] = baseline_tokens
                parsed['actual_tokens'] = actual_tokens
                parsed['relevant_files'] = relevant_files
                parsed['python_file_count'] = len(repo_info['python_files'])
                try:
                    from kernel.cache import put_decision
                    put_decision(task, repo_path, parsed.get('decisions', []))
                except Exception:
                    pass
                return parsed
        except Exception:
            pass

        return self._fallback_plan(task, relevant_files, baseline_tokens, actual_tokens, len(repo_info['python_files']))


if __name__ == "__main__":
    import sys
    repo = sys.argv[1] if len(sys.argv) > 1 else "demo_repo"
    task_text = "fix security vulnerabilities"
    prompt, n = TaskAnalyzer(None, None)._build_planning_prompt(task_text, repo)
    print(f"planning prompt tokens: {n} (cap {tokens(prompt)} total)")
    print(prompt[:1500])
