#!/usr/bin/env python3
"""Minimal SAST scanner for the demo.

Flags string-concatenated SQL (CWE-89) in Java sources and FAILS the job
(exit 1) when it finds any -- that failure is what triggers the incident agent.
It prints the CWE id and the offending `.java` file:line so the agent can both
ROUTE the incident (security -> fine-tuned vuln-fixer) and AUTO-DETECT what to
fix (no hard-coded file/CWE on the agent side).

In production swap this for CodeQL / Semgrep; the contract is the same -- emit
the CWE id and the file path in the job logs.

Usage:  python3 scripts/sast_scan.py [src_dir]
"""
from __future__ import annotations

import pathlib
import re
import sys

# A SQL keyword followed (on the same line) by a string that is concatenated
# with a variable: the classic CWE-89 shape, e.g.
#   "SELECT * FROM payments WHERE user_id = '" + userId + "'"
_SQLI = re.compile(r'(?i)(select|insert|update|delete|where).*?"\s*\+\s*\w')

_DESC = "SQL Injection: untrusted input is concatenated into a SQL query"


def scan(root: str) -> list[tuple[str, int]]:
    hits: list[tuple[str, int]] = []
    for path in sorted(pathlib.Path(root).rglob("*.java")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if _SQLI.search(line):
                hits.append((path.as_posix(), lineno))
    return hits


def main() -> int:
    root = sys.argv[1] if len(sys.argv) > 1 else "src"
    print(f"SAST scan: scanning {root!r} for CWE-89 (SQL injection) ...")
    hits = scan(root)

    for file, lineno in hits:
        # GitHub annotation + a plain line the agent's log parser reads.
        print(f"::error file={file},line={lineno}::CWE-89 {_DESC}")
        print(f"SAST: CWE-89 detected in {file}:{lineno}")

    if hits:
        print(f"\nsecurity scan FAILED: {len(hits)} vulnerability(ies) found")
        return 1
    print("security scan passed: no vulnerabilities found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
