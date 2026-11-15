import os
from dotenv import load_dotenv

load_dotenv()

class ConfidAgent:

    def __init__(self, repo_path: str, task: str, budget_override: float = None, force_confidential: bool = False, dry_run: bool = False, feature_flags=None):
        self.repo_path = repo_path
        self.force_confidential = force_confidential
        self.dry_run = dry_run
        if feature_flags is None:
            from kernel.settings import settings as _s
            self.feature_flags = _s.feature_flags
        else:
            self.feature_flags = feature_flags
        if force_confidential:
            os.environ["CONFIDENTIAL"] = "true"

        from security.privacy_checker import sanitize_untrusted_text
        self.task = sanitize_untrusted_text(task, context="task")

        from output.terminal_display import TerminalDisplay
        from agent.state import StateManager
        from agent.scorer import ConfidenceScorer
        from agent.file_reader import FileReader
        from agent.planner import TaskAnalyzer
        from integrations.bifrost_client import BifrostClient
        from integrations.tavily_client import TavilyClient
        from integrations.ollama_client import OllamaClient
        from security.privacy_checker import PrivacyChecker
        from security.budget_gate import BudgetGate
        from security.approval_gate import ApprovalGate

        budget = budget_override or float(os.getenv('CONFIDAGENT_BUDGET_USD', '2.00'))

        from agent.triage import classify_task
        from kernel.gateway import Gateway
        self.gateway = Gateway()
        self.task_class = 'generation'
        try:
            self.task_class = classify_task(self.task, '')
        except Exception:
            pass  # triage failure must not break init

        from kernel import ledger as ledger_mod
        self.ledger = ledger_mod
        self.run_id = ledger_mod.start_run('agent')

        self.display = TerminalDisplay()
        self.state = StateManager(budget)
        self.state.state['budget_limit'] = budget
        self.state.set_run_id(self.run_id)
        self.scorer = ConfidenceScorer()
        self.file_reader = FileReader()
        self.bifrost = BifrostClient(self.state)
        self.tavily = TavilyClient()
        self.ollama = OllamaClient()
        self.privacy = PrivacyChecker(repo_path, force_confidential)
        self.budget_gate = BudgetGate(self.state)
        self.approval = ApprovalGate(self.display, dry_run=dry_run)
    
    def run(self) -> bool:
        try:
            self.display.show_banner()

            # Resume detection: if an in-progress state exists, continue from it.
            resuming = False
            if os.path.exists(self.state.STATE_FILE) and self.state.state.get('status') == 'in_progress' and self.state.state.get('decisions'):
                resuming = True
                n_done = len(self.state.state.get('completed_decisions', []))
                n_total = len(self.state.state.get('decisions', []))
                prior_run = self.state.state.get('run_id', 'unknown')
                print(f"[reliability] resuming run {prior_run} ({n_done}/{n_total} decisions done)")
                self.task = self.state.state.get('task') or self.task
                self.repo_path = self.state.state.get('repo_path') or self.repo_path

            is_confidential = self.privacy.is_confidential() or bool(self.state.state.get('is_confidential'))
            self.display.show_privacy_status(is_confidential)

            self.display.show_task_start(self.task, self.repo_path)
# Read-only analysis mode
            if self.task_class == 'analysis' and not resuming:
                self.display.show_step("Reading files for explanation...")

                import re

                repo_info = self.file_reader.scan_repo_structure(self.repo_path)
                requested = re.findall(r'[\w.-]+\.py', self.task, re.I)

                if requested:
                    files = [
                        f for f in repo_info['python_files']
                        if os.path.basename(f).lower() in
                        [name.lower() for name in requested]
                    ]
                else:
                    keywords = [
                        w.lower() for w in re.findall(r'[a-zA-Z_]+', self.task)
                        if len(w) > 3
                    ]
                    files = self.file_reader.find_relevant_files(
                        self.repo_path, keywords
                    )

                if not files:
                    self.display.show_error("No matching Python files found.")
                    return False

                context = ""
                for filepath in files[:3]:
                    context += f"\n\nFILE: {filepath}\n"
                    context += self.file_reader.read_file(filepath)[:10000]

                messages = [
                    {
                        "role": "system",
                        "content": "You are a Python code tutor. Explain code clearly in simple language. Do not modify files."
                    },
                    {
                        "role": "user",
                        "content": f"Task: {self.task}\n\nCode:\n{context}"
                    }
                ]

                result = self.gateway.complete(
                    messages, tier='local', max_tokens=2000
                )

                print("\n--- CODE EXPLANATION ---\n")
                print(result.text)

                self.state.set_task(self.task, self.repo_path, is_confidential)
                self.state.set_run_id(self.run_id)
                self.state.mark_complete()
                return True
            if resuming:
                decisions = self.state.state.get('decisions', [])
                baseline = self.state.state.get('tokens_baseline', 6200)
                analysis = {'relevant_files': []}
            else:
                self.display.show_step("Analyzing repository and task...")
                analysis = self.task_analyzer_analyze(is_confidential)
                decisions = analysis.get('decisions', [])

            if not decisions:
                self.display.show_error("Could not analyze task. Try being more specific.")
                return False

            if not resuming:
                decisions = self.scorer.score_all(decisions)
                self.display.show_confidence_scores(decisions)
                self.state.set_decisions(decisions)
                baseline = analysis.get('baseline_tokens', 6200)
                self.state.set_baseline_tokens(baseline)
            else:
                self.display.show_confidence_scores(decisions)
            
            low_count = sum(1 for d in decisions if d.get('action', {}).get('confidence') in ['LOW', 'MED'])
            high_count = len(decisions) - low_count
            estimated = self.budget_gate.estimate_task_cost(low_count, high_count)
            
            ok, message = self.budget_gate.check_budget(estimated)
            self.display.show_budget_status(self.state.state['budget_remaining'], estimated)
            
            if not ok:
                self.display.show_error(message)
                return False
            
            claims_to_verify = []
            for d in decisions:
                if d.get('action', {}).get('tavily_verify'):
                    claims = self.tavily.extract_library_claims(d.get('description', ''))
                    claims_to_verify.extend(claims)

            # Add pinned versions from requirements.txt and imports
            version_pins = self.file_reader.extract_version_pins(self.repo_path)
            for pin in version_pins:
                claims_to_verify.append(pin['claim'])

            # Dedupe
            seen = set()
            deduped = []
            for c in claims_to_verify:
                if c not in seen:
                    seen.add(c)
                    deduped.append(c)
            claims_to_verify = deduped
            print(f"[claims] {len(claims_to_verify)} -> {claims_to_verify[:10]}")
            tavily_results = []
            
            if claims_to_verify:
                self.display.show_tavily_section()
                self.display.show_step(f"Verifying {len(claims_to_verify)} claims via Tavily...")
                tavily_results = self.tavily.verify_all_parallel(claims_to_verify)
                
                stale_count = 0
                for result in tavily_results:
                    self.display.show_tavily_result(
                        result['claim'],
                        result['status'],
                        result.get('correction')
                    )
                    if result['status'] == 'STALE':
                        stale_count += 1
                
                if stale_count > 0:
                    self.state.add_stale_caught(stale_count)
                    self.state.set_tavily_results(tavily_results)
            
            self.state.set_task(self.task, self.repo_path, is_confidential)
            self.state.set_run_id(self.run_id)
            
            corrections = {
                r['claim']: r.get('correction', '')
                for r in tavily_results
                if r.get('status') == 'STALE' and r.get('correction')
            }
            
            batched_results = self._execute_decisions_batched(
                decisions, is_confidential, corrections, analysis.get('relevant_files', [])
            )
            for decision, result in zip(decisions, batched_results):
                dname = decision['name']
                if self.state.is_decision_completed(dname):
                    continue
                status = result.get('status', 'complete')
                self.state.update_decision(dname, status, result.get('tokens', 0), result.get('cost', 0.0))
            
            final_state = self.state.state
            self.display.show_completion(
                final_state['tokens_used'],
                final_state.get('tokens_baseline', final_state['tokens_used'] * 5),
                final_state['cost_usd'],
                final_state['stale_caught'],
                final_state['provider_switches']
            )
            
            self.state.mark_complete()
            return True
            
        except KeyboardInterrupt:
            try:
                self.state.save()
            except Exception:
                pass
            print("[reliability] session saved; rerun to resume")
            return False
        except Exception as e:
            self.display.show_error(f"Batched execution failed: {e}")
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': (
                        'complete'
                        if self.state.is_decision_completed(d.get('name', ''))
                        else 'failed'
                    )
                }
                for d in decisions
            ]
            self.display.show_error(f"Batched execution failed: {e}")
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': (
                        'complete'
                        if self.state.is_decision_completed(d.get('name', ''))
                        else 'failed'
                    )
                }
                for d in decisions
            ]
            self.display.show_error(f"Batched execution failed: {e}")
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': (
                        'complete'
                        if self.state.is_decision_completed(d.get('name', ''))
                        else 'failed'
                    ),
                }
                for d in decisions
            ]
            self.display.show_error(f"Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _validate_draft(self, content: str) -> bool:
        """Validate Python code with or without Markdown fences."""
        import ast
        import re

        content = (content or "").strip()

        match = re.search(
            r"```(?:python)?\s*\n(.*?)```",
            content,
            re.DOTALL | re.IGNORECASE
        )

        if match:
            content = match.group(1).strip()

        if not content:
            return False

        try:
            ast.parse(content)
            return True
        except SyntaxError:
            return False

    def _route_log(self, decision_name: str, outcome: str) -> None:
        print(f"[route] {decision_name}: local->{outcome}")
    def _budget_ok(self, tier: str) -> bool:
        """Check whether the requested model tier fits the remaining budget."""
        try:
            return self.budget_gate.check_budget(
                self.budget_gate.estimate_task_cost(0, 1)
            )[0]
        except Exception as e:
            print(f"[budget] check failed: {e}")
            return False    

    def _try_local_draft(self, messages: list, decision_name: str):
        """Attempt a local-model draft."""

        from kernel.settings import settings

        if not getattr(settings, 'local_triage_enabled', True):
            return None, 0, 0.0

        try:
            result = self.gateway.complete(
                messages, tier='local', max_tokens=2000
            )

            content = (result.text or "").strip()

            if content.startswith("===FILE:") and "```" not in content:
                header, _, code = content.partition("\n")
                content = f"{header}\n```python\n{code.strip()}\n```"

            print("[DEBUG] MODEL RESPONSE:")
            print(repr(content[:2000]))

            tokens_n = result.total_tokens
            cost = result.cost_usd

        except Exception as e:
            print(f"[route] {decision_name}: local-unavailable ({str(e)[:60]})")
            return None, 0, 0.0

        if self._validate_draft(content):
            self._route_log(decision_name, 'accepted')
            return content, tokens_n, cost

        self._route_log(decision_name, 'escalated:invalid draft')
        return None, 0, 0.0
    def task_analyzer_analyze(self, is_confidential: bool) -> dict:
        from agent.planner import TaskAnalyzer
        analyzer = TaskAnalyzer(self.file_reader, self.bifrost)
        return analyzer.analyze(self.task, self.repo_path)
    
    def _apply_file_patch(self, filepath: str, new_content: str) -> bool:
        full_path = os.path.join(self.repo_path, filepath)
        if not os.path.exists(full_path):
            self.display.show_error(f"File not found: {filepath}")
            return False
        backup_path = full_path + '.bak'
        with open(full_path, 'r', encoding='utf-8') as f:
            original = f.read()
        with open(backup_path, 'w', encoding='utf-8') as f:
            f.write(original)
        try:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            self.display.show_success(f"Patched {filepath}")
            return True
        except Exception as e:
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(original)
            self.display.show_error(f"Patch failed: {e}")
            return False
    
    def _execute_decision(self, decision: dict, is_confidential: bool, corrections: dict, relevant_files: list) -> dict:
        relevant_file = decision.get('relevant_file')
        code_context = ''
        
        if relevant_file:
            full_path = os.path.join(self.repo_path, relevant_file)
            if os.path.exists(full_path):
                # File memory: reuse cached outline/content knowledge when unchanged.
                if self.feature_flags.file_memory:
                    try:
                        from kernel.memory import outline_or_build
                        _outline, was_cached = outline_or_build(self.repo_path, relevant_file)
                        if was_cached:
                            _n = max(1, len(_outline.splitlines()))
                            print(f"\033[2m[memory] hit {relevant_file} (saved ~{_n} lines / ~{_n} tokens)\033[0m")
                    except Exception:
                        pass  # memory must never break the run
                full_content = self.file_reader.read_file(full_path)
                if self.feature_flags.ast_context and len(full_content.split('\n')) > 150:
                    keywords = decision.get('name', '').split()
                    code_context = self.file_reader.read_relevant_functions(full_path, keywords)
                else:
                    code_context = full_content
                # Compression: code excerpt only — instructions stay untouched.
                if self.feature_flags.ast_context:
                    try:
                        from kernel.compress import compress_code, maybe_log
                        code_context, cmeta = compress_code(code_context)
                        if 'orig_tokens' in cmeta:
                            maybe_log(cmeta, label=f'code_context:{relevant_file}')
                    except Exception:
                        pass  # compression must never break the run
                self.state.add_file_read(relevant_file)
        
        corrections_text = ''
        if corrections:
            corrections_text = '\n'.join([
                f"- Use '{v}' instead of '{k}'"
                for k, v in corrections.items()
                if v
            ])
        
        prompt = f"""You are fixing ONE specific bug. Return the COMPLETE updated file.

FILE: {relevant_file or 'N/A'}
ISSUE: {decision['name']} — {decision['description']}

CURRENT FILE CONTENT:
{code_context if code_context else 'File not loaded'}

{f'APPLY THESE VERIFIED CORRECTIONS:{chr(10)}{corrections_text}' if corrections_text else ''}

RULES:
1. Return the ENTIRE updated file, not just the changed lines
2. Keep all unrelated code exactly as-is
3. The result must be valid Python
4. Respond with ONLY the new file content in a single ```python code block
5. No explanation before or after the code block"""
        
        messages = [{"role": "user", "content": prompt}]
        
        try:
            from kernel.gateway import GatewayError
            use_powerful = decision.get('action', {}).get('model') == 'powerful'
            decision_name = decision.get('name', '?')

            if is_confidential:
                if self.feature_flags.cost_model and not self._budget_ok('local'):
                    return {'tokens': 0, 'cost': 0.0, 'content': '', 'status': 'skipped'}
                content, tokens, cost = self.ollama.call(messages)
            else:
                # Cascade: cheap/local draft -> deterministic gate -> escalate once.
                if self.feature_flags.cost_model and not self._budget_ok('cheap'):
                    return {'tokens': 0, 'cost': 0.0, 'content': '', 'status': 'skipped'}

                known = self._known_names_for(relevant_file)

                def _builder(tier, max_tokens):
                    return self.gateway.complete(messages, tier=tier, max_tokens=max_tokens)

                if self.feature_flags.routing:
                    from kernel.cascade import run as cascade_run
                    cres = cascade_run(
                        _builder,
                        expected_file=relevant_file,
                        known_names=known,
                        max_escalations=1,
                        decision_name=decision_name,
                        gateway=self.gateway,
                        allow_local=True,
                    )
                    content = cres.text
                    tokens, cost = cres.total_tokens, cres.total_cost_usd
                else:
                    # No routing: always powerful tier, single call.
                    result = self.gateway.complete(messages, tier='powerful', max_tokens=2000)
                    content = result.text
                    tokens, cost = result.total_tokens, result.cost_usd

            import re as _re
            code_match = _re.search(r'```(?:python)?\s*\n(.*?)```', content, _re.DOTALL)
            if code_match and relevant_file:
                new_content = code_match.group(1).strip() + '\n'
                preview = "Rewriting " + str(len(code_context.split('\n'))) + " lines -> " + str(len(new_content.split('\n'))) + " lines\n\nFirst 20 lines:\n" + '\n'.join(new_content.split('\n')[:20])
                approved = self.approval.request_approval('write_file', relevant_file, preview)
                if approved:
                    if self._apply_file_patch(relevant_file, new_content):
                        self.state.add_file_modified(relevant_file)
                else:
                    self.display.show_step(f"Skipped {relevant_file}")

            return {'tokens': tokens, 'cost': cost, 'content': content, 'status': 'complete'}

        except GatewayError as e:
            print(f"[reliability] decision failed after provider retries: {decision.get('name','?')} ({e})")
            return {'tokens': 0, 'cost': 0.0, 'content': '', 'status': 'failed'}
        except Exception as e:
            print(f"[reliability] decision error: {decision.get('name','?')} ({e})")
            return {'tokens': 0, 'cost': 0.0, 'content': '', 'status': 'failed'}

    def _execute_decisions_batched(
        self,
        decisions: list,
        is_confidential: bool,
        corrections: dict,
        relevant_files: list,
    ) -> list:
        pending_decisions = [
            d for d in decisions
            if not self.state.is_decision_completed(d.get('name', ''))
        ]

        if not pending_decisions:
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': 'complete',
                }
                for _ in decisions
            ]

        prompt = (
            f"Task: {self.task}\n\n"
            f"Fix the following decisions in batch.\n"
f"For EVERY file, output ===FILE: filename=== on its own line.\n"
f"Put the complete file content inside a Python code block. No explanations.\n"
            
            f"Decisions:\n"
            + "\n".join(
                f"- {d.get('name', '?')}: {d.get('description', '')}"
                for d in pending_decisions
            )
            + (f"\n\nRelevant files:\n{chr(10).join(relevant_files)}" if relevant_files else "")
            + (f"\n\nVerified corrections:\n{chr(10).join(f'- {k} -> {v}' for k, v in corrections.items() if v)}" if corrections else "")
        )

        messages = [{
            'role': 'user',
            'content': prompt,
        }]

        content = ''
        tokens = 0
        cost = 0.0

        try:
            if is_confidential:
                if self.feature_flags.cost_model and not self._budget_ok('local'):
                    return [
                        {
                            'tokens': 0,
                            'cost': 0.0,
                            'content': '',
                            'status': (
                                'complete'
                                if self.state.is_decision_completed(d.get('name', ''))
                                else 'skipped'
                            )
                        }
                        for d in decisions
                    ]

                content, tokens, cost = self.ollama.call(messages)
            else:
                has_cheap = any(
                    d.get('action', {}).get('model') != 'powerful'
                    for d in pending_decisions
                )

                batch_name = f"batch({len(pending_decisions)} decisions)"
                local_done = False

                if self.feature_flags.routing and (
                    has_cheap or self.task_class == 'analysis'
                ):
                    local_content, local_tokens, local_cost = self._try_local_draft(
                        messages, batch_name
                    )

                    if local_content is not None:
                        content, tokens, cost = (
                            local_content,
                            local_tokens,
                            local_cost,
                        )
                        local_done = True

                if not local_done:
                    if self.feature_flags.cost_model and not self._budget_ok('powerful'):
                        return [
                            {
                                'tokens': 0,
                                'cost': 0.0,
                                'content': '',
                                'status': (
                                    'complete'
                                    if self.state.is_decision_completed(d.get('name', ''))
                                    else 'skipped'
                                )
                            }
                            for d in decisions
                        ]

                    content, tokens, cost = self.bifrost.call_powerful(messages)

            import re as _re
            pattern = r'===FILE:\s*([^\s=]+)\s*===.*?```(?:python)?\s*\n(.*?)```'
            matches = _re.findall(pattern, content, _re.DOTALL)

            if not matches:
                code_match = _re.search(
                    r'```(?:python)?\s*\n(.*?)```',
                    content,
                    _re.DOTALL | _re.IGNORECASE,
                )
                if code_match:
                    code = code_match.group(1)
                    filename_match = _re.search(
                        r'(?m)^\s*#\s*([\w.-]+\.py)\s*$',
                        code,
                    )
                    if filename_match:
                        fname = filename_match.group(1)
                        code = code[filename_match.end():].strip()
                        matches = [(fname, code)]

            results = []
            patched_files = []

            for fname, new_content in matches:
                fname = fname.strip()
                new_content = new_content.strip() + '\n'

                full_path = os.path.abspath(
                    os.path.join(self.repo_path, fname)
                )
                repo_root = os.path.abspath(self.repo_path)

                if os.path.commonpath([repo_root, full_path]) != repo_root:
                    continue

                preview = (
                    f"Writing {fname} "
                    f"({len(new_content.splitlines())} lines)"
                )

                if self.approval.request_approval(
                    'write_file', fname, preview
                ):
                    if os.path.exists(full_path):
                        success = self._apply_file_patch(
                            fname, new_content
                        )
                    else:
                        os.makedirs(
                            os.path.dirname(full_path),
                            exist_ok=True,
                        )

                        with open(
                            full_path, 'w', encoding='utf-8'
                        ) as f:
                            f.write(new_content)

                        success = True

                    if success:
                        self.state.add_file_modified(fname)
                        patched_files.append(fname)

            per_decision_cost = cost / max(len(pending_decisions), 1)
            per_decision_tokens = tokens // max(len(pending_decisions), 1)

            for d in decisions:
                if self.state.is_decision_completed(d.get('name', '')):
                    results.append({
                        'tokens': 0,
                        'cost': 0.0,
                        'content': '',
                        'status': 'complete'
                    })
                else:
                    results.append({
                        'tokens': per_decision_tokens,
                        'cost': per_decision_cost,
                        'content': content,
                        'status': 'complete',
                    })
            return results

        except GatewayError as e:
            self.display.show_error(
                f"Batched execution failed after provider retries: {e}"
            )
            print(
                "[reliability] provider exhausted; Bifrost will attempt "
                "the next provider on the next call"
            )
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': (
                        'complete'
                        if self.state.is_decision_completed(d.get('name', ''))
                        else 'failed'
                    )
                }
                for d in decisions
            ]

        except Exception as e:
            self.display.show_error(f"Batched execution failed: {e}")
            import traceback
            traceback.print_exc()
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': (
                        'complete'
                        if self.state.is_decision_completed(d.get('name', ''))
                        else 'failed'
                    )
                }
                for d in decisions
            ]
            traceback.print_exc()
            return [
                {
                    'tokens': 0,
                    'cost': 0.0,
                    'content': '',
                    'status': (
                        'complete'
                        if self.state.is_decision_completed(d.get('name', ''))
                        else 'failed'
                    )
                }
                for d in decisions
            ]