#!/usr/bin/env bash
set -euo pipefail

# Run acceptance tests AT-001 through AT-022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENT_FILE="$ARTIFACT_ROOT/agents/legata_to_rebeca.md"
SKILL_FILE="$ARTIFACT_ROOT/skills/rebeca_handbook/SKILL.md"

echo "Running Acceptance Tests..."
echo ""

PASSED=0
FAILED=0

# AT-001: Prescribed Workflow
echo -n "AT-001 (Prescribed Workflow): "
if [[ -f "$AGENT_FILE" ]] && \
   grep -q "## Step Bindings" "$AGENT_FILE" && \
   grep -q "step01_init" "$AGENT_FILE" && \
   grep -q "step07_reporting" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
fi

# AT-002: Agent Structure
echo -n "AT-002 (Agent Structure): "
if grep -q "Rebeca" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
fi

# AT-021: No Requirements Leakage
echo -n "AT-021 (No Leakage): "
if ! grep -q "FR-" "$AGENT_FILE" 2>/dev/null; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
fi

# AT-022: Rebeca Guidance Skill
echo -n "AT-022 (Rebeca Skill): "
if [[ -f "$SKILL_FILE" ]]; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
fi

echo ""
echo "Results: $PASSED passed, $FAILED failed"
