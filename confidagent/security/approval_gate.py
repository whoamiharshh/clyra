import os

BLOCKED_PHRASES = [
    'ignore approval', 'skip approval', 'auto approve',
    'bypass approval', 'no approval needed', 'approve automatically'
]

READS = {"read_symbol", "read_outline", "search_repo", "verify_claim"}
WRITES = {"write_file", "shell", "git", "run_shell", "git_op"}

# Registry includes stub tool names for gate testability.
TOOL_REGISTRY = {
    "read_symbol": "read",
    "read_outline": "read",
    "search_repo": "read",
    "verify_claim": "read",
    "write_file": "write",
    "shell": "write",
    "git": "write",
    "run_shell": "write",
    "git_op": "write",
}


def classify_operation(operation: str) -> str:
    op = (operation or "").strip().lower()
    if op in READS or op in TOOL_REGISTRY and TOOL_REGISTRY[op] == "read":
        return "read"
    if op in WRITES or op in TOOL_REGISTRY and TOOL_REGISTRY[op] == "write":
        return "write"
    # Backward-compatible heuristics.
    read_hints = ["read", "scan", "list", "search", "find", "analyze", "outline", "verify"]
    write_hints = ["write", "patch", "edit", "delete", "shell", "git", "run", "commit"]
    if any(h in op for h in write_hints):
        return "write"
    if any(h in op for h in read_hints):
        return "read"
    return "write"


class ApprovalGate:

    def __init__(self, display=None, dry_run: bool = False):
        self.display = display
        self.auto_approve_reads = True
        self.dry_run = bool(dry_run)

    def check_injection(self, prompt: str) -> bool:
        prompt_lower = (prompt or "").lower()
        return any(phrase in prompt_lower for phrase in BLOCKED_PHRASES)

    def _print_prompt_details(self, tool_name: str, target: str, preview: str = None) -> None:
        print(f"[approval] tool={tool_name}")
        print(f"[approval] target={target}")
        if preview:
            print("[approval] preview:")
            print(preview)

    def request_approval(self, operation: str, target: str, diff: str = None) -> bool:
        tool_name = operation
        kind = classify_operation(operation)

        # READS auto-approve.
        if kind == "read":
            return True

        # WRITES in dry-run auto-deny.
        if self.dry_run:
            print(f"[dry-run] would write {target}")
            return False

        # Interactive explicit y/n required for writes.
        self._print_prompt_details(tool_name, target, diff)
        if self.display and hasattr(self.display, "show_approval_request"):
            try:
                return bool(self.display.show_approval_request(tool_name, target, diff))
            except Exception:
                pass

        while True:
            try:
                resp = input("Approve write? (y/n): ").strip().lower()
            except EOFError:
                return False
            if resp in ("y", "yes"):
                return True
            if resp in ("n", "no"):
                return False
            print("Please answer y or n.")
