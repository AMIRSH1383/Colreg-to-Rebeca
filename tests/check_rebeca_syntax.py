#!/usr/bin/env python3
"""
Cross-platform syntax checker for .rebeca and .property files.
Checks for forbidden patterns per the Rebeca language handbook.

Forbidden patterns (outside comments):
  - Implication operators: -> or =>
  - Chained assignments:   x = (y = ...)

Returns:
  exit 0  — no violations found
  exit 1  — violations found (details printed to stdout)
  exit 2  — usage error
"""
import re
import sys
from pathlib import Path

# Patterns to detect in code (not comments)
FORBIDDEN_IMPLICATION = re.compile(r'(?<![=!<>])->|==>')
FORBIDDEN_CHAINED_ASSIGN = re.compile(r'\w+\s*=\s*\(\s*\w+\s*=')

def strip_comments(text: str) -> str:
    """Remove // line comments and /* ... */ block comments."""
    # Remove block comments /* ... */
    text = re.sub(r'/\*.*?\*/', lambda m: '\n' * m.group().count('\n'), text, flags=re.DOTALL)
    # Remove line comments //
    text = re.sub(r'//[^\n]*', '', text)
    return text

def check_file(path: str) -> list:
    violations = []
    try:
        raw = Path(path).read_text()
    except Exception as e:
        return [f"Cannot read file: {e}"]

    # Build a comment-stripped version for pattern matching
    stripped = strip_comments(raw)

    # Check line by line (using original for display, stripped for detection)
    raw_lines = raw.splitlines()
    stripped_lines = stripped.splitlines()

    for i, (raw_line, stripped_line) in enumerate(zip(raw_lines, stripped_lines), 1):
        if FORBIDDEN_IMPLICATION.search(stripped_line):
            violations.append(
                f"Line {i}: forbidden implication operator (-> or ==>): {raw_line.strip()}"
            )
        if FORBIDDEN_CHAINED_ASSIGN.search(stripped_line):
            violations.append(
                f"Line {i}: forbidden chained assignment (x = (y = ...)): {raw_line.strip()}"
            )
    return violations

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: check_rebeca_syntax.py <file> [file ...]")
        sys.exit(2)

    total_violations = 0
    for filepath in sys.argv[1:]:
        violations = check_file(filepath)
        if violations:
            print(f"VIOLATIONS in {filepath}:")
            for v in violations:
                print(f"  {v}")
            total_violations += len(violations)
        else:
            print(f"OK: {filepath}")

    sys.exit(1 if total_violations > 0 else 0)
