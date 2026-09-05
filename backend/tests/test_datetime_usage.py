"""Regression guard for the datetime.utcnow() cleanup fix.

datetime.utcnow() is deprecated and naive-vs-aware footguns already caused a
real bug on this branch, fixed by routing everything through
backend.utils.time.utcnow(). This walks every .py file under backend/ (except
this test directory and utils/time.py, which legitimately mentions the
deprecated name in its own docstring) via ast, looking for actual
`datetime.utcnow()` call sites - not a plain text/substring search, so it
can't be tripped up by comments or docstrings that just mention the name.
"""
import ast
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
EXCLUDED = {BACKEND_DIR / "utils" / "time.py"}


def _find_deprecated_utcnow_calls(path: Path) -> list:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "utcnow"
    ]


def test_no_file_under_backend_calls_datetime_utcnow_directly():
    offenders = {}
    for path in BACKEND_DIR.rglob("*.py"):
        if path in EXCLUDED or "tests" in path.parts or "__pycache__" in path.parts:
            continue
        lines = _find_deprecated_utcnow_calls(path)
        if lines:
            offenders[str(path.relative_to(BACKEND_DIR))] = lines

    assert not offenders, (
        f"Found direct .utcnow() calls (should use backend.utils.time.utcnow() "
        f"instead): {offenders}"
    )
