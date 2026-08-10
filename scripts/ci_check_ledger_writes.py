"""Fail CI if INSERT INTO ledger tables appears outside the LedgerService allowlist."""

from __future__ import annotations

import re
import sys
from pathlib import Path

INSERT_PATTERN = re.compile(
    r"INSERT\s+INTO\s+ledger_(transactions|postings)\b",
    re.IGNORECASE,
)

ALLOWED_PREFIXES = ("packages/common/src/finance_common/ledger/",)

ALLOWED_FILES = frozenset(
    {
        "packages/common/src/finance_common/db/migrations.py",
        "packages/common/src/finance_common/db/schema.sql",
    }
)

SKIP_DIR_NAMES = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".worktrees",
        "worktrees",
        ".superpowers",
    }
)

SCAN_SUFFIXES = frozenset({".py", ".sql"})
TESTS_PREFIX = "tests/"


def _is_allowed(rel_path: str) -> bool:
    if rel_path.startswith(TESTS_PREFIX):
        return True
    if rel_path in ALLOWED_FILES:
        return True
    return any(rel_path.startswith(prefix) for prefix in ALLOWED_PREFIXES)


def _scan_repo(root: Path) -> list[tuple[str, int, str]]:
    violations: list[tuple[str, int, str]] = []

    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
            continue
        if SKIP_DIR_NAMES.intersection(path.parts):
            continue

        rel = path.relative_to(root).as_posix()
        if _is_allowed(rel):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        for lineno, line in enumerate(text.splitlines(), start=1):
            if INSERT_PATTERN.search(line):
                violations.append((rel, lineno, line.strip()))

    return violations


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    violations = _scan_repo(root)
    if not violations:
        return 0

    print("Ledger INSERT outside allowlist:", file=sys.stderr)
    for rel, lineno, line in sorted(violations):
        print(f"  {rel}:{lineno}: {line}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
