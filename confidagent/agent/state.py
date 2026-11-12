import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

class StateManager:

    STATE_FILE = '.confidagent_state.json'

    def __init__(self, budget_usd: float = None):
        if budget_usd is None:
            budget_usd = float(os.getenv('CONFIDAGENT_BUDGET_USD', '2.00'))

        self.budget_usd = budget_usd
        self.state = self._load_or_create(budget_usd)

    def _load_or_create(self, budget_usd: float) -> dict:
        if os.path.exists(self.STATE_FILE):
            try:
                with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
                if existing.get('status') == 'in_progress':
                    existing.setdefault('run_id', 'unknown')
                    existing.setdefault('completed_decisions', [])
                    # normalize decisions done count
                    existing.setdefault('decisions_done', 0)
                    existing.setdefault('decisions_total', len(existing.get('decisions', []) or []))
                    return existing
            except Exception:
                pass

        return {
            'task': '',
            'repo_path': '',
            'is_confidential': False,
            'run_id': 'unknown',
            'decisions_total': 0,
            'decisions_done': 0,
            'decisions': [],
            'completed_decisions': [],
            'files_read': [],
            'files_modified': [],
            'tokens_used': 0,
            'tokens_baseline': 0,
            'cost_usd': 0.0,
            'budget_remaining': budget_usd,
            'provider_switches': 0,
            'current_provider': 'groq',
            'stale_caught': 0,
            'tavily_results': [],
            'status': 'in_progress',
            'created_at': datetime.now().isoformat()
        }

    def save(self):
        try:
            self.state['decisions_done'] = len(self.state.get('completed_decisions', [])) or self.state.get('decisions_done', 0)
        except Exception:
            pass
        with open(self.STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, indent=2)

    def set_task(self, task: str, repo_path: str, is_confidential: bool):
        self.state['task'] = task
        self.state['repo_path'] = repo_path
        self.state['is_confidential'] = is_confidential
        self.save()

    def set_run_id(self, run_id: str):
        self.state['run_id'] = run_id
        self.save()

    def mark_decision_complete(self, decision_name: str, status: str, tokens: int, cost: float):
        self.state['tokens_used'] += tokens
        self.state['cost_usd'] += cost
        self.state['budget_remaining'] -= cost
        completed = self.state.setdefault('completed_decisions', [])
        if decision_name not in completed:
            completed.append(decision_name)
        self.state['decisions_done'] = len(completed)
        for d in self.state.get('decisions', []):
            if d.get('name') == decision_name:
                d['status'] = status
                d['tokens'] = tokens
                break
        self.save()

    def update_decision(self, decision_name: str, status: str, tokens: int, cost: float):
        # Backward-compatible: treat as completion.
        self.mark_decision_complete(decision_name, status, tokens, cost)

    def is_decision_completed(self, decision_name: str) -> bool:
        return decision_name in (self.state.get('completed_decisions') or [])

    def add_file_read(self, filepath: str):
        if filepath not in self.state['files_read']:
            self.state['files_read'].append(filepath)
            self.save()

    def add_file_modified(self, filepath: str):
        if filepath not in self.state['files_modified']:
            self.state['files_modified'].append(filepath)
            self.save()

    def record_provider_switch(self, to_provider: str):
        self.state['provider_switches'] += 1
        self.state['current_provider'] = to_provider
        self.save()

    def add_stale_caught(self, count: int = 1):
        self.state['stale_caught'] += count
        self.save()

    def set_tavily_results(self, results: list):
        """Store full Tavily verification results for audit/dashboard."""
        self.state['tavily_results'] = results
        self.save()

    def set_decisions(self, decisions: list):
        # Preserve completion info when resuming same task/decisions if possible.
        existing_names = {d.get('name') for d in (self.state.get('decisions') or [])}
        incoming_names = {d.get('name') for d in (decisions or [])}
        if existing_names != incoming_names:
            self.state['completed_decisions'] = []
        self.state['decisions'] = decisions
        self.state['decisions_total'] = len(decisions)
        self.state['decisions_done'] = len(self.state.get('completed_decisions', []))
        self.save()

    def set_baseline_tokens(self, baseline: int):
        self.state['tokens_baseline'] = baseline
        self.save()

    def mark_complete(self):
        self.state['status'] = 'complete'
        self.save()

    def clear(self):
        if os.path.exists(self.STATE_FILE):
            os.remove(self.STATE_FILE)
        self.state = self._load_or_create(self.budget_usd)
