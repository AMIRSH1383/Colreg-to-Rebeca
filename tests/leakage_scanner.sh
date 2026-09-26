#!/usr/bin/env bash
set -euo pipefail

# Scan runtime artifacts for requirement leakage

echo "Scanning for requirement leakage..."

VIOLATIONS=0

# Scan agent files
for file in .agents/agents/*.agent.md; do
  if [[ -f "$file" ]]; then
    if grep -E "(FR-|AT-|requirements/)" "$file" > /dev/null 2>&1; then
      echo "✗ Leakage found in $file"
      ((VIOLATIONS++))
    fi
  fi
done

# Scan skill files
for file in .agents/skills/*/SKILL.md; do
  if [[ -f "$file" ]]; then
    if grep -E "(FR-|AT-|requirements/)" "$file" > /dev/null 2>&1; then
      echo "✗ Leakage found in $file"
      ((VIOLATIONS++))
    fi
  fi
done

if [[ $VIOLATIONS -eq 0 ]]; then
  echo "✓ No leakage detected"
  exit 0
else
  echo "✗ $VIOLATIONS violation(s) found"
  exit 1
fi
