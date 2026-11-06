#!/usr/bin/env bash
# Check canonical runtime instructions for accidental local paths/requirements text.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
files=(agents/*.md skills/*/SKILL.md)
count=0
for file in "${files[@]}"; do
  [[ -f "$file" ]] || continue
  count=$((count + 1))
  if grep -nE '(/Users/[^ /]+|/home/[^ /]+|[A-Z]:\\|FR-[0-9]+|AT-[0-9]+)' "$file"; then
    echo "Unexpected local path or requirements text: $file" >&2
    exit 1
  fi
done
[[ "$count" -gt 0 ]] || { echo 'No instructions scanned' >&2; exit 1; }
echo "Checked $count instruction files"
