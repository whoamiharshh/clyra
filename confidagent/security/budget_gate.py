"""DEPRECATED: use kernel.ledger instead.

This module is kept only as a thin compatibility wrapper so existing imports
of `security.budget_gate.BudgetGate` don't break. All budget logic lives in
kernel.ledger (check_budget / run_total / downgrade_tier).
"""

import os
from dotenv import load_dotenv

load_dotenv()

from kernel import ledger as _ledger

COST_LOW_DECISION = 0.001
COST_HIGH_DECISION = 0.0001
COST_TAVILY_CALL = 0.0005


class BudgetGate:
    """Deprecated shim over kernel.ledger. Prefer kernel.ledger directly."""

    def __init__(self, state_manager):
        self.state = state_manager

    def estimate_task_cost(self, num_low: int, num_high: int) -> float:
        return (num_low * COST_LOW_DECISION) + (num_high * COST_HIGH_DECISION) + (num_low * COST_TAVILY_CALL)

    def check_budget(self, estimated_cost: float, run_id: str = None, limit_usd: float = None) -> tuple:
        if run_id is None:
            run_id = _ledger.get_current_run()
        if limit_usd is None:
            limit_usd = self.state.state.get('budget_limit', 2.00)
        return _ledger.check_budget(run_id, estimated_cost, limit_usd)

    def check_per_call(self, estimated_call_cost: float, run_id: str = None, limit_usd: float = None) -> bool:
        ok, _reason = self.check_budget(estimated_call_cost, run_id=run_id, limit_usd=limit_usd)
        return ok
