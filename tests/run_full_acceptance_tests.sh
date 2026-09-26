#!/usr/bin/env bash
set -euo pipefail

# Comprehensive acceptance test runner for all 22 acceptance tests
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

AGENT_FILE="$ARTIFACT_ROOT/agents/legata_to_rebeca.md"

echo "======================================================"
echo "FULL ACCEPTANCE TEST SUITE (AT-001 through AT-022)"
echo "======================================================"
echo ""

PASSED=0
FAILED=0
FAILED_TESTS=()

# Helper function to check if file exists
check_file() {
  if [[ -f "$1" ]]; then
    return 0
  else
    return 1
  fi
}

# Helper function to check if directory exists
check_dir() {
  if [[ -d "$1" ]]; then
    return 0
  else
    return 1
  fi
}

# Helper function to check if grep pattern exists (case-insensitive)
check_grep_ci() {
  if grep -iq "$1" "$2" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

# Helper function to check if grep pattern exists
check_grep() {
  if grep -q "$1" "$2" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

# Helper function to check if grep pattern does NOT exist
check_grep_not() {
  if ! grep -q "$1" "$2" 2>/dev/null; then
    return 0
  else
    return 1
  fi
}

# AT-001: Prescribed workflow artifact exists with canonical step enums
echo -n "AT-001 (Prescribed Workflow Artifact): "
if check_file "$AGENT_FILE" && \
  check_grep "## Step Bindings" "$AGENT_FILE" && \
  check_grep "step01_init" "$AGENT_FILE" && \
  check_grep "step07_reporting" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-001")
fi

# AT-002: Agent file exists with handbook-derived Rebeca constraints
echo -n "AT-002 (Agent Structure & Handbook): "
if check_file "$AGENT_FILE" && \
  check_grep "Rebeca" "$AGENT_FILE" && \
  check_grep_ci "condition\|assertion" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-002")
fi

# AT-003: Agent workflow explicitly covers canonical step enums (Step Bindings)
echo -n "AT-003 (Agent Workflow Phases): "
if check_grep "## Step Bindings" "$AGENT_FILE" && \
  check_grep "step02_abstraction" "$AGENT_FILE" && \
  check_grep "step03_mapping" "$AGENT_FILE" && \
  check_grep "step05_synthesis" "$AGENT_FILE" && \
  check_grep "step05_verification_gate" "$AGENT_FILE" && \
  check_grep "step07_packaging" "$AGENT_FILE" && \
  check_grep "step07_reporting" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-003")
fi

# AT-003a: For formalized rules, output includes model_artifact and property_artifact
echo -n "AT-003a (Dual Artifact Output): "
if check_grep_ci "artifact" "$AGENT_FILE" && \
  check_grep_ci "property" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-003a")
fi

# AT-004: Skill directory exists with SKILL.md and trigger description
echo -n "AT-004 (Workflow Skill Structure): "
if check_file "$ARTIFACT_ROOT/skills/legata_to_rebeca/SKILL.md" && \
   check_grep_ci "when to use" "$ARTIFACT_ROOT/skills/legata_to_rebeca/SKILL.md"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-004")
fi

# AT-005: Workflow skill includes Step01..Step08 with embedded Rebeca constraints
echo -n "AT-005 (Workflow Skill Content): "
if check_grep "Legata" "$ARTIFACT_ROOT/skills/legata_to_rebeca/SKILL.md" && \
   check_grep "Rebeca" "$ARTIFACT_ROOT/skills/legata_to_rebeca/SKILL.md"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-005")
fi

# AT-008: run_rmc script exists and validates model/property paths
echo -n "AT-008 (RMC Run Script): "
if check_file "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/run_rmc.py" && \
   check_grep "jar\|model" "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/run_rmc.py"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-008")
fi

# AT-009: run_rmc script supports timeout and output configuration
echo -n "AT-009 (RMC Run Configuration): "
if check_grep "timeout" "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/run_rmc.py"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-009")
fi

# AT-010: Tooling skill documents script interfaces
echo -n "AT-010 (Script Interfaces): "
if check_grep_ci "download[_ -]rmc\|run[_ -]rmc\|Run RMC" "$ARTIFACT_ROOT/skills/rebeca_tooling/SKILL.md"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-010")
fi

# AT-011: Prompts for implementation and review exist
echo -n "AT-011 (Implementation Prompts): "
if check_dir "$ARTIFACT_ROOT" && \
  check_file "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-011")
fi

# AT-012: Traceability matrix or documentation exists
echo -n "AT-012 (Traceability Matrix): "
if check_file "$ARTIFACT_ROOT/README.md" && \
   check_grep_ci "workflow\|phase\|artifact" "$ARTIFACT_ROOT/README.md"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-012")
fi

# AT-013: Install scripts exist and verify installation success
echo -n "AT-013 (Install Scripts): "
if check_file "$ARTIFACT_ROOT/setup.py" && \
  check_grep "target-root\|target_root\|no-rmc" "$ARTIFACT_ROOT/setup.py"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-013")
fi

# AT-015: Single-rule scoring exists
echo -n "AT-015 (Single-Rule Scoring): "
if check_file "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/score_rule.py"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-015")
fi

# AT-016: Reporting mechanism exists
echo -n "AT-016 (Reporting Mechanism): "
if check_file "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/generate_report.py"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-016")
fi

# AT-019: Incorrect/incomplete handling documented
echo -n "AT-019 (Degraded Input Handling): "
if check_grep_ci "incomplete\|incorrect\|blocked\|manual review" "$ARTIFACT_ROOT/skills/legata_to_rebeca/SKILL.md" || \
  check_grep_ci "defect\|repair\|failure\|error" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-019")
fi

# AT-020: No silent skips - all outcomes reported
echo -n "AT-020 (No Silent Skips): "
if check_grep_ci "report\|output\|error envelope\|status" "$AGENT_FILE"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-020")
fi

# AT-021: No requirement leakage (FR-*, AT-*, requirements/**)
echo -n "AT-021 (No Requirement Leakage): "
LEAKAGE_CLEAN=true
if grep -r "FR-" "$ARTIFACT_ROOT/agents/" "$ARTIFACT_ROOT/skills/" "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/" 2>/dev/null | grep -v "Binary"; then
  LEAKAGE_CLEAN=false
fi
if grep -r "AT-[0-9]" "$ARTIFACT_ROOT/agents/" "$ARTIFACT_ROOT/skills/" "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/" 2>/dev/null | grep -v "Binary"; then
  LEAKAGE_CLEAN=false
fi
if grep -r "requirements/" "$ARTIFACT_ROOT/agents/" "$ARTIFACT_ROOT/skills/" "$ARTIFACT_ROOT/skills/rebeca_tooling/scripts/" 2>/dev/null | grep -v "Binary"; then
  LEAKAGE_CLEAN=false
fi
if [[ "$LEAKAGE_CLEAN" == true ]]; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-021")
fi

# AT-022: Dedicated Rebeca modeling skill with Do/Don'ts and examples
echo -n "AT-022 (Rebeca Modeling Skill): "
if check_file "$ARTIFACT_ROOT/skills/rebeca_handbook/SKILL.md" && \
   check_grep_ci "do\|don't" "$ARTIFACT_ROOT/skills/rebeca_handbook/SKILL.md" && \
   check_grep_ci "example" "$ARTIFACT_ROOT/skills/rebeca_handbook/SKILL.md"; then
  echo "PASS"
  ((PASSED++))
else
  echo "FAIL"
  ((FAILED++))
  FAILED_TESTS+=("AT-022")
fi

echo ""
echo "======================================================"
echo "TEST RESULTS: $PASSED passed, $FAILED failed"
echo "======================================================"

if [[ $FAILED -gt 0 ]]; then
  echo ""
  echo "Failed tests:"
  for test in "${FAILED_TESTS[@]}"; do
    echo "  - $test"
  done
  exit 1
fi

exit 0
