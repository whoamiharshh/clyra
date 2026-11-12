"""Kernel Context - AST-based code context builder. Pure functions, no internal caching.

Replaces full-file reads for LLM context:
  repo_map()     -> compact map of every top-level symbol in the repo
  file_outline() -> same format for a single file
  symbol_body()  -> exact source lines of one function/class/method
  expand()       -> concatenated bodies for lazy loading
  tokens()       -> tiktoken cl100k_base counting (fallback: len//4)
"""

import ast
import os
import sys
from typing import List, Optional

from security.privacy_checker import sanitize_untrusted_text

SKIP_DIRS = {
    "__pycache__", ".venv", ".git", "node_modules", "venv", "env",
    "dist", "build", ".idea", ".vscode", ".pytest_cache", ".confidagent",
    "demo_repo_backup", "demo_repo_original",
}
SKIP_TEST_DIRS_DEFAULT = True

_cl100k_encoder = None
_tiktoken_failed = False


def _walk_py_files(repo_path: str, include_tests: bool = False) -> List[str]:
    """Return sorted list of .py file paths under repo_path."""
    out = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if not include_tests and os.path.basename(root) in ("tests", "test"):
            dirs[:] = []
            continue
        for f in files:
            if f.endswith(".py"):
                out.append(os.path.join(root, f))
    return sorted(out)


def _unparse_args(node: ast.AST) -> str:
    """Render an arguments node as a signature fragment."""
    try:
        parts = []
        pos = list(getattr(node, "posonlyargs", []) or [])
        args = list(node.args or [])
        all_args = pos + args
        # Defaults are omitted from the outline to save tokens; use symbol_body() for exact source.
        for a in all_args:
            s = a.arg
            if a.annotation is not None:
                try:
                    s += ":" + ast.unparse(a.annotation)
                except Exception:
                    pass
            parts.append(s)
        if getattr(node, "vararg", None):
            parts.append("*" + node.vararg.arg)
        elif node.kwonlyargs:
            parts.append("*")
        for a in getattr(node, "kwonlyargs", []) or []:
            s = a.arg
            if a.annotation is not None:
                try:
                    s += ":" + ast.unparse(a.annotation)
                except Exception:
                    pass
            parts.append(s)
        if getattr(node, "kwarg", None):
            parts.append("**" + node.kwarg.arg)
        return ", ".join(parts)
    except Exception:
        return "..."


def _sig_line(node: ast.AST, indent: str = "  ") -> str:
    """One signature line for a FunctionDef / ClassDef node."""
    start = getattr(node, "lineno", 0)
    end = getattr(node, "end_lineno", start)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        prefix = "async def " if isinstance(node, ast.AsyncFunctionDef) else "def "
        args = _unparse_args(node.args)
        ret = ""
        if getattr(node, "returns", None) is not None:
            try:
                ret = "->" + ast.unparse(node.returns)
            except Exception:
                ret = ""
        return f"{indent}{prefix}{node.name}({args}){ret} # L{start}-{end}"
    if isinstance(node, ast.ClassDef):
        bases = []
        for b in node.bases:
            try:
                bases.append(ast.unparse(b))
            except Exception:
                bases.append("?")
        base_str = f"({', '.join(bases)})" if bases else ""
        return f"{indent}class {node.name}{base_str} # L{start}-{end}"
    return ""


def _collect_methods(class_node: ast.ClassDef) -> List[str]:
    """Signature lines for methods defined directly on a class."""
    lines = []
    for child in class_node.body:
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(_sig_line(child, indent="    "))
    return lines


def _module_first_docstring_line(tree: ast.Module) -> str:
    doc = ast.get_docstring(tree)
    if doc:
        first = doc.strip().splitlines()[0]
        return f"  \"\"\"{first}\"\"\""
    return ""


def _outline_for_source(source: str) -> str:
    """Render the outline text for one module's source (shared by repo_map / file_outline)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"  # <syntax error: {exc}>"

    lines: List[str] = []
    doc_line = _module_first_docstring_line(tree)
    if doc_line:
        lines.append(doc_line)

    count = 0
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lines.append(_sig_line(node))
            count += 1
        elif isinstance(node, ast.ClassDef):
            lines.append(_sig_line(node))
            count += 1
            lines.extend(_collect_methods(node))
    return "\n".join(lines)


def _map_cap(lines: List[str], max_symbols: int) -> str:
    """Cap a rendered outline at max_symbols lines with a truncation trailer."""
    if len(lines) <= max_symbols:
        return "\n".join(lines)
    shown = lines[:max_symbols]
    hidden = len(lines) - max_symbols
    shown.append(f"... {hidden} more symbols")
    return "\n".join(shown)


def repo_map(repo_path: str, max_symbols: int = 400, include_tests: bool = False) -> str:
    """Compact map of every .py file in the repo: paths + top-level symbol signatures."""
    blocks: List[str] = []
    all_lines: List[str] = []
    for fpath in _walk_py_files(repo_path, include_tests=include_tests):
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                source = fh.read()
        except OSError:
            continue
        rel = os.path.relpath(fpath, repo_path)
        outline = _outline_for_source(source)
        if not outline:
            continue
        block = f"{rel}:\n{outline}"
        blocks.append(block)
        all_lines.extend(block.splitlines())

    result = _map_cap(all_lines, max_symbols)
    return sanitize_untrusted_text(result, context="repo_map")


def file_outline(repo_path: str, rel_path: str) -> str:
    """Outline of a single file. Warns if the file exceeds 300 lines (never full bodies)."""
    full = os.path.join(repo_path, rel_path)
    try:
        with open(full, "r", encoding="utf-8", errors="ignore") as fh:
            source = fh.read()
    except OSError as exc:
        return f"# <cannot read {rel_path}: {exc}>"

    n_lines = len(source.splitlines())
    if n_lines > 300:
        header = f"# WARNING: {rel_path} is {n_lines} lines; outline only, use expand()/symbol_body() for details"
    else:
        header = f"# {rel_path}"
    result = header + "\n" + _outline_for_source(source)
    return sanitize_untrusted_text(result, context=f"file_outline:{rel_path}")


def symbol_body(repo_path: str, rel_path: str, symbol: str) -> str:
    """Exact source lines of a named function/class, resolving dotted forms like 'Class.method'."""
    full = os.path.join(repo_path, rel_path)
    try:
        with open(full, "r", encoding="utf-8", errors="ignore") as fh:
            source = fh.read()
    except OSError as exc:
        return f"# <cannot read {rel_path}: {exc}>"

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        return f"# <syntax error in {rel_path}: {exc}>"

    parts = symbol.split(".")
    target_top = parts[0]

    candidates: List[ast.AST] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == target_top:
            candidates.append(node)

    if not candidates:
        return f"# <symbol '{symbol}' not found in {rel_path}>"

    node = candidates[0]
    if len(parts) > 1 and isinstance(node, ast.ClassDef):
        method_name = parts[1]
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) and child.name == method_name:
                node = child
                break
        else:
            return f"# <symbol '{symbol}' not found in {rel_path}>"

    src_lines = source.splitlines()
    start = getattr(node, "lineno", 1)
    end = getattr(node, "end_lineno", start)
    # Include leading decorators.
    deco_start = start
    decorators = getattr(node, "decorator_list", []) or []
    if decorators:
        deco_start = min(d.lineno for d in decorators)
    result = "\n".join(src_lines[deco_start - 1:end])
    return sanitize_untrusted_text(result, context=f"symbol_body:{rel_path}:{symbol}")


def expand(repo_path: str, rel_path: str, symbols: List[str]) -> str:
    """Concatenated symbol bodies with headers, for lazy loading after seeing repo_map."""
    chunks = []
    for sym in symbols:
        body = symbol_body(repo_path, rel_path, sym)
        chunks.append(f"# --- {rel_path} :: {sym} ---\n{body}")
    result = "\n\n".join(chunks)
    return sanitize_untrusted_text(result, context=f"expand:{rel_path}")


def tokens(text: str) -> int:
    """Token count via tiktoken cl100k_base; falls back to len//4 if unavailable."""
    global _cl100k_encoder, _tiktoken_failed
    if _tiktoken_failed:
        return len(text) // 4
    if _cl100k_encoder is None:
        try:
            import tiktoken
            _cl100k_encoder = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _tiktoken_failed = True
            return len(text) // 4
    try:
        return len(_cl100k_encoder.encode(text))
    except Exception:
        return len(text) // 4


def find_symbol_line_range(repo_path: str, rel_path: str, symbol: str) -> Optional[tuple]:
    """(start_line, end_line) for a symbol, for callers that need to map to decision ranges."""
    body = symbol_body(repo_path, rel_path, symbol)
    if body.startswith("# <"):
        return None
    return None


if __name__ == "__main__":
    repo = sys.argv[1] if len(sys.argv) > 1 else "demo_repo"
    the_map = repo_map(repo)

    # all files concatenated (spec check), plus .py-only for reference
    all_concat = ""
    py_concat = ""
    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = os.path.join(root, fn)
            if not os.path.isfile(p):
                continue
            try:
                txt = open(p, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            all_concat += txt
            if fn.endswith(".py"):
                py_concat += txt

    n_lines = len(the_map.splitlines())
    t_map = tokens(the_map)
    t_all = tokens(all_concat)
    t_py = tokens(py_concat)
    ratio = (t_map / t_all * 100) if t_all else 0.0
    ratio_py = (t_map / t_py * 100) if t_py else 0.0
    print(f"repo_map lines:      {n_lines} (cap 400)")
    print(f"tokens(repo_map):    {t_map}")
    print(f"tokens(all files):   {t_all}")
    print(f"tokens(.py only):    {t_py}")
    print(f"ratio vs all files:  {ratio:.1f}% (must be < 25%)")
    print(f"ratio vs .py only:   {ratio_py:.1f}%")
    ok = ratio < 25.0 and n_lines < 500
    print("ACCEPTANCE:", "PASS" if ok else "FAIL")
    print()
    print(the_map[:2000])
    sys.exit(0 if ok else 1)
