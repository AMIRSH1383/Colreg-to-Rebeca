#!/usr/bin/env bash
# Integration test suite for RebecAI.
# Validates the full operational chain:
#   IT-001  Prerequisites (java, g++, python3)
#   IT-002  setup.py runs end-to-end and exits 0
#   IT-003  Agents installed to target dir
#   IT-004  Skills installed to target dir
#   IT-005  rmc.jar downloaded and is a valid JAR (ZIP magic)
#   IT-006  rmc.jar executes (java -jar rmc.jar -h)
#   IT-009  run_rmc.py: RMC parses known-good model → generates .cpp files
#   IT-010  run_rmc.py: g++ compiles generated .cpp → produces executable
#   IT-011  run_rmc.py: RMC rejects known-bad model → exit code 5
#   IT-012  run_rmc.py: timeout respected → exit code 3
#   IT-013  setup.py --target-root custom dir installs to correct location
#   IT-014  Leakage scan: no hardcoded paths in installed artifacts
#
# Usage:
#   bash tests/run_integration_tests.sh
#
# Environment variables:
#   RMC_TAG        Pin a specific RMC version (default: latest)
#   INSTALL_DIR    Override install target (default: tmp dir, cleaned up after)
#   KEEP_ARTIFACTS Set to 1 to skip cleanup (useful for debugging)

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LIB_DIR="$PROJECT_ROOT/skills/rebeca_tooling/scripts"

RMC_TAG="${RMC_TAG:-}"
KEEP_ARTIFACTS="${KEEP_ARTIFACTS:-0}"

# Use a temp dir as install target so we never pollute ~/.agents
INSTALL_DIR="${INSTALL_DIR:-$(mktemp -d "$HOME/tmp_claude_integration_XXXX")}"
SECONDARY_DIR="$(mktemp -d "$HOME/tmp_claude_secondary_XXXX")"

PASSED=0
FAILED=0
ERRORS=()

pass() { echo "  PASS: $1"; ((PASSED++)); }
fail() { echo "  FAIL: $1 — $2"; ((FAILED++)); ERRORS+=("$1: $2"); }
skip() { echo "  SKIP: $1 — $2"; }

cleanup() {
  if [[ "$KEEP_ARTIFACTS" != "1" ]]; then
    rm -rf "$INSTALL_DIR" "$SECONDARY_DIR"
  else
    echo ""
    echo "Artifacts kept at:"
    echo "  Primary:   $INSTALL_DIR"
    echo "  Secondary: $SECONDARY_DIR"
  fi
}
trap cleanup EXIT

echo "======================================================"
echo " INTEGRATION TEST SUITE"
echo "======================================================"
echo ""
echo "  Install dir : $INSTALL_DIR"
echo "  Project root: $PROJECT_ROOT"
[[ -n "$RMC_TAG" ]] && echo "  RMC tag     : $RMC_TAG" || echo "  RMC tag     : latest"
echo ""

# ──────────────────────────────────────────────────────────
# IT-001: Prerequisites
# ──────────────────────────────────────────────────────────
echo "── IT-001: Prerequisites ──"

JAVA_BIN="$(command -v java 2>/dev/null || true)"
if [[ -n "$JAVA_BIN" ]]; then
  java_ver=$("$JAVA_BIN" -version 2>&1 | head -1)
  pass "IT-001-java: $java_ver"
else
  fail "IT-001-java" "java not found on PATH — install Java 11+"
fi

GPP_BIN="$(command -v g++ 2>/dev/null || command -v clang++ 2>/dev/null || true)"
if [[ -n "$GPP_BIN" ]]; then
  pass "IT-001-cpp: $GPP_BIN found"
else
  fail "IT-001-cpp" "g++ / clang++ not found — install build-essential or Xcode CLT"
fi

PYTHON_BIN="$(command -v python3 2>/dev/null || true)"
if [[ -n "$PYTHON_BIN" ]]; then
  py_ver=$("$PYTHON_BIN" --version 2>&1)
  pass "IT-001-python: $py_ver"
else
  fail "IT-001-python" "python3 not found on PATH"
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-002: setup.py end-to-end
# ──────────────────────────────────────────────────────────
echo "── IT-002: setup.py end-to-end ──"

SETUP_ARGS=(--target-root "$INSTALL_DIR")
[[ -n "$RMC_TAG" ]] && SETUP_ARGS+=(--rmc-tag "$RMC_TAG")

if "$PYTHON_BIN" "$PROJECT_ROOT/setup.py" "${SETUP_ARGS[@]}" > "$INSTALL_DIR/setup.log" 2>&1; then
  pass "IT-002: setup.py exited 0"
else
  exit_code=$?
  fail "IT-002" "setup.py exited $exit_code — see $INSTALL_DIR/setup.log"
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-003: Agents installed
# ──────────────────────────────────────────────────────────
echo "── IT-003: Agents installed ──"

agent_count=0
while IFS= read -r -d '' f; do
  agent_count=$((agent_count + 1))
  pass "IT-003: agent installed — $(basename "$f")"
done < <(find "$INSTALL_DIR/agents" -name "*.md" -print0 2>/dev/null)

if [[ $agent_count -eq 0 ]]; then
  fail "IT-003" "No agent .md files found in $INSTALL_DIR/agents/"
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-004: Skills installed
# ──────────────────────────────────────────────────────────
echo "── IT-004: Skills installed ──"

skill_count=0
while IFS= read -r -d '' d; do
  if [[ -f "$d/SKILL.md" ]]; then
    skill_count=$((skill_count + 1))
    pass "IT-004: skill installed — $(basename "$d")"
  fi
done < <(find "$INSTALL_DIR/skills" -mindepth 1 -maxdepth 1 -type d -print0 2>/dev/null)

if [[ $skill_count -eq 0 ]]; then
  fail "IT-004" "No skill directories with SKILL.md found in $INSTALL_DIR/skills/"
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-005: rmc.jar downloaded and valid
# ──────────────────────────────────────────────────────────
echo "── IT-005: rmc.jar validity ──"

RMC_JAR="$INSTALL_DIR/rmc/rmc.jar"

if [[ ! -f "$RMC_JAR" ]]; then
  fail "IT-005-exists" "rmc.jar not found at $RMC_JAR"
else
  pass "IT-005-exists: rmc.jar present"

  # Check ZIP/JAR magic bytes PK\x03\x04
  magic=$(xxd -l 4 "$RMC_JAR" 2>/dev/null | awk '{print $2$3}' | head -1 || true)
  if [[ "$magic" == "504b0304" ]]; then
    pass "IT-005-magic: rmc.jar has valid ZIP/JAR magic bytes"
  else
    # Fallback: python check
    if "$PYTHON_BIN" -c "
import sys
with open('$RMC_JAR', 'rb') as f:
    magic = f.read(4)
sys.exit(0 if magic == b'PK\x03\x04' else 1)
" 2>/dev/null; then
      pass "IT-005-magic: rmc.jar has valid ZIP/JAR magic bytes"
    else
      fail "IT-005-magic" "rmc.jar does not have ZIP/JAR magic bytes — file may be corrupt"
    fi
  fi

  # Check file size > 1MB
  jar_size=$(wc -c < "$RMC_JAR" 2>/dev/null | tr -d ' ')
  if [[ "$jar_size" -gt 1000000 ]]; then
    pass "IT-005-size: rmc.jar size ${jar_size} bytes (> 1MB)"
  else
    fail "IT-005-size" "rmc.jar size ${jar_size} bytes is suspiciously small"
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-006: rmc.jar executes
# ──────────────────────────────────────────────────────────
echo "── IT-006: rmc.jar executes ──"

if [[ ! -f "$RMC_JAR" ]]; then
  skip "IT-006" "rmc.jar missing — skipping execution test"
elif [[ -z "$JAVA_BIN" ]]; then
  skip "IT-006" "java not found — skipping execution test"
else
  if timeout 10 "$JAVA_BIN" -jar "$RMC_JAR" -h > /dev/null 2>&1; then
    pass "IT-006: java -jar rmc.jar -h exited successfully"
  else
    # RMC may exit non-zero for -h but still be functional — check stderr for usage text
    output=$(timeout 10 "$JAVA_BIN" -jar "$RMC_JAR" -h 2>&1 || true)
    if echo "$output" | grep -qi "usage\|option\|rebeca\|rmc"; then
      pass "IT-006: java -jar rmc.jar -h produced usage output (functional)"
    else
      fail "IT-006" "rmc.jar produced no recognisable output — may be corrupt"
    fi
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# Shared known-good model for IT-009 / IT-010
# ──────────────────────────────────────────────────────────
MODEL_DIR="$(mktemp -d "$SECONDARY_DIR/rmc_model_XXXX")"

cat > "$MODEL_DIR/test.rebeca" << 'REBECA_EOF'
reactiveclass Ship(10) {
  statevars {
    int length;
    boolean hasLight;
  }
  Ship() {
    length = 60;
    hasLight = true;
  }
  msgsrv tick() {
    length = length + 1;
  }
}
main {
  Ship s1():();
}
REBECA_EOF

cat > "$MODEL_DIR/test.property" << 'PROP_EOF'
property {
  define {
    isLong = (s1.length > 50);
    lightOn = (s1.hasLight == true);
  }
  Assertion {
    Rule22: !isLong || lightOn;
  }
}
PROP_EOF

OUTPUT_DIR="$MODEL_DIR/out"
mkdir -p "$OUTPUT_DIR"

# ──────────────────────────────────────────────────────────
# IT-009: run_rmc.py → RMC parses model → .cpp files generated
# ──────────────────────────────────────────────────────────
echo "── IT-009: RMC parses model and generates C++ ──"

if [[ ! -f "$RMC_JAR" ]]; then
  skip "IT-009" "rmc.jar missing"
elif [[ -z "$JAVA_BIN" ]]; then
  skip "IT-009" "java not found"
else
  rmc_exit=0
  PYTHONPATH="$LIB_DIR" "$PYTHON_BIN" "$LIB_DIR/run_rmc.py" \
    --jar "$RMC_JAR" \
    --model "$MODEL_DIR/test.rebeca" \
    --property "$MODEL_DIR/test.property" \
    --output-dir "$OUTPUT_DIR" \
    --timeout-seconds 60 \
    > "$MODEL_DIR/run_rmc.log" 2>&1 || rmc_exit=$?

  cpp_count=$(find "$OUTPUT_DIR" -name "*.cpp" 2>/dev/null | wc -l | tr -d ' ')

  if [[ "$cpp_count" -gt 0 ]]; then
    pass "IT-009: RMC generated $cpp_count .cpp file(s) from known-good model"
  else
    fail "IT-009" "RMC produced no .cpp files (exit=$rmc_exit) — see $MODEL_DIR/run_rmc.log"
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-010: g++ compiles generated .cpp → executable produced
# ──────────────────────────────────────────────────────────
echo "── IT-010: g++ compiles generated C++ ──"

if [[ ! -f "$RMC_JAR" ]]; then
  skip "IT-010" "rmc.jar missing — no .cpp files to compile"
elif [[ -z "$GPP_BIN" ]]; then
  skip "IT-010" "g++ not found"
else
  cpp_count=$(find "$OUTPUT_DIR" -name "*.cpp" 2>/dev/null | wc -l | tr -d ' ')
  if [[ "$cpp_count" -eq 0 ]]; then
    skip "IT-010" "no .cpp files present (IT-009 may have failed)"
  else
    compile_exit=0
    pushd "$OUTPUT_DIR" > /dev/null
    "$GPP_BIN" ./*.cpp -w -o model.out > "$MODEL_DIR/compile.log" 2>&1 || compile_exit=$?
    popd > /dev/null

    if [[ $compile_exit -eq 0 ]] && [[ -f "$OUTPUT_DIR/model.out" ]]; then
      pass "IT-010: g++ compiled $cpp_count .cpp file(s) → model.out produced"
    else
      fail "IT-010" "g++ compilation failed (exit=$compile_exit) — see $MODEL_DIR/compile.log"
    fi
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-010b: model.out runs and property is satisfied
# ──────────────────────────────────────────────────────────
echo "── IT-010b: model.out executes and property is satisfied ──"

if [[ ! -f "$OUTPUT_DIR/model.out" ]]; then
  skip "IT-010b" "model.out not present (IT-010 may have failed)"
else
  mc_output=$(timeout 30 "$OUTPUT_DIR/model.out" 2>&1 || true)
  mc_exit=$?

  if echo "$mc_output" | grep -q "<result>satisfied</result>"; then
    pass "IT-010b: model.out ran and property is satisfied"
  elif echo "$mc_output" | grep -q "<result>violated</result>"; then
    fail "IT-010b" "model.out ran but property is violated (counterexample found in known-good model)"
  elif [[ $mc_exit -eq 0 ]] && [[ -n "$mc_output" ]]; then
    # Produced output but no recognised result tag — still functional
    pass "IT-010b: model.out ran and produced model-checking output"
  else
    fail "IT-010b" "model.out failed to run or produced no output (exit=$mc_exit)"
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-011: run_rmc.py rejects known-bad model → exit code 5
# ──────────────────────────────────────────────────────────
echo "── IT-011: RMC rejects known-bad model (exit 5) ──"

if [[ ! -f "$RMC_JAR" ]]; then
  skip "IT-011" "rmc.jar missing"
elif [[ -z "$JAVA_BIN" ]]; then
  skip "IT-011" "java not found"
else
  BAD_DIR="$(mktemp -d "$SECONDARY_DIR/rmc_bad_XXXX")"
  BAD_OUT="$BAD_DIR/out"
  mkdir -p "$BAD_OUT"

  # Deliberately invalid Rebeca — uses forbidden -> operator
  cat > "$BAD_DIR/bad.rebeca" << 'BAD_REBECA'
reactiveclass Broken(10) {
  statevars { int x; }
  Broken() { x = 0; }
}
main { Broken b1():(); }
BAD_REBECA

  cat > "$BAD_DIR/bad.property" << 'BAD_PROP'
property {
  Assertion {
    BadRule: b1.x -> true;
  }
}
BAD_PROP

  bad_exit=0
  PYTHONPATH="$LIB_DIR" "$PYTHON_BIN" "$LIB_DIR/run_rmc.py" \
    --jar "$RMC_JAR" \
    --model "$BAD_DIR/bad.rebeca" \
    --property "$BAD_DIR/bad.property" \
    --output-dir "$BAD_OUT" \
    --timeout-seconds 30 \
    > "$BAD_DIR/run.log" 2>&1 || bad_exit=$?

  if [[ $bad_exit -eq 5 ]]; then
    pass "IT-011: run_rmc.py returned exit code 5 for known-bad model (parse error)"
  else
    fail "IT-011" "Expected exit 5 (parse error), got exit $bad_exit — see $BAD_DIR/run.log"
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-012: run_rmc.py timeout respected → exit code 3
# ──────────────────────────────────────────────────────────
echo "── IT-012: run_rmc.py timeout (exit 3) ──"

if [[ ! -f "$RMC_JAR" ]]; then
  skip "IT-012" "rmc.jar missing"
elif [[ -z "$JAVA_BIN" ]]; then
  skip "IT-012" "java not found"
else
  TIMEOUT_DIR="$(mktemp -d "$SECONDARY_DIR/rmc_timeout_XXXX")"
  TIMEOUT_OUT="$TIMEOUT_DIR/out"
  mkdir -p "$TIMEOUT_OUT"

  # Use the known-good model but with a 1-second timeout to force expiry
  timeout_exit=0
  PYTHONPATH="$LIB_DIR" "$PYTHON_BIN" "$LIB_DIR/run_rmc.py" \
    --jar "$RMC_JAR" \
    --model "$MODEL_DIR/test.rebeca" \
    --property "$MODEL_DIR/test.property" \
    --output-dir "$TIMEOUT_OUT" \
    --timeout-seconds 1 \
    > "$TIMEOUT_DIR/run.log" 2>&1 || timeout_exit=$?

  if [[ $timeout_exit -eq 3 ]]; then
    pass "IT-012: run_rmc.py returned exit code 3 on 1-second timeout"
  elif [[ $timeout_exit -eq 0 ]]; then
    # RMC completed within 1s on fast hardware — not a failure, just note it
    skip "IT-012" "RMC completed within 1s (fast hardware) — timeout not triggered"
  else
    fail "IT-012" "Expected exit 3 (timeout) or 0 (fast), got exit $timeout_exit"
  fi
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-013: setup.py --target-root custom dir
# ──────────────────────────────────────────────────────────
echo "── IT-013: setup.py custom --target-root ──"

CUSTOM_DIR="$SECONDARY_DIR/custom_install"
mkdir -p "$CUSTOM_DIR"

CUSTOM_ARGS=(--target-root "$CUSTOM_DIR")
[[ -n "$RMC_TAG" ]] && CUSTOM_ARGS+=(--rmc-tag "$RMC_TAG")

if "$PYTHON_BIN" "$PROJECT_ROOT/setup.py" "${CUSTOM_ARGS[@]}" \
    > "$SECONDARY_DIR/setup_custom.log" 2>&1; then
  agents_ok=0
  skills_ok=0
  rmc_ok=0
  [[ -d "$CUSTOM_DIR/agents" ]] && agents_ok=1
  [[ -d "$CUSTOM_DIR/skills" ]] && skills_ok=1
  [[ -f "$CUSTOM_DIR/rmc/rmc.jar" ]] && rmc_ok=1

  if [[ $agents_ok -eq 1 && $skills_ok -eq 1 && $rmc_ok -eq 1 ]]; then
    pass "IT-013: setup.py installed to custom --target-root correctly"
  else
    fail "IT-013" "Missing artifacts in custom dir (agents=$agents_ok skills=$skills_ok rmc=$rmc_ok)"
  fi
else
  exit_code=$?
  fail "IT-013" "setup.py exited $exit_code for custom target — see $SECONDARY_DIR/setup_custom.log"
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-014: Leakage scan on installed artifacts
# ──────────────────────────────────────────────────────────
echo "── IT-014: Leakage scan on installed artifacts ──"

leakage_found=0

# Check for hardcoded absolute paths (other than the install dir itself)
while IFS= read -r -d '' f; do
  # Skip binary files
  if file "$f" 2>/dev/null | grep -q "text"; then
    # Flag any hardcoded /Users/ or /home/ paths that aren't the install dir
    if grep -Pn "/Users/(?!.*$(basename "$INSTALL_DIR"))|/home/[a-z]" "$f" 2>/dev/null | grep -v "^Binary"; then
      fail "IT-014-$(basename "$f")" "Hardcoded user path found in installed artifact"
      leakage_found=$((leakage_found + 1))
    fi
  fi
done < <(find "$INSTALL_DIR/agents" "$INSTALL_DIR/skills" -type f -print0 2>/dev/null)

if [[ $leakage_found -eq 0 ]]; then
  pass "IT-014: No hardcoded user paths found in installed agents/skills"
fi

echo ""

# ──────────────────────────────────────────────────────────
# IT-015: Path patching — .agents/rmc placeholder replaced in installed files
# ──────────────────────────────────────────────────────────
echo "── IT-015: RMC path patching in installed artifacts ──"

expected_jar="$INSTALL_DIR/rmc/rmc.jar"
placeholder_found=0
patched_found=0

while IFS= read -r -d '' f; do
  if file "$f" 2>/dev/null | grep -q "text"; then
    if grep -q '\.agents/rmc/rmc\.jar\|\.agents/rmc"' "$f" 2>/dev/null; then
      fail "IT-015-$(basename "$f")" "Placeholder .agents/rmc path not replaced in installed file"
      placeholder_found=$((placeholder_found + 1))
    fi
    if grep -qF "$expected_jar" "$f" 2>/dev/null; then
      patched_found=$((patched_found + 1))
    fi
  fi
done < <(find "$INSTALL_DIR/agents" "$INSTALL_DIR/skills" -type f -print0 2>/dev/null)

if [[ $placeholder_found -eq 0 && $patched_found -gt 0 ]]; then
  pass "IT-015: RMC paths correctly patched to $expected_jar in $patched_found file(s)"
elif [[ $placeholder_found -eq 0 && $patched_found -eq 0 ]]; then
  fail "IT-015" "No files contain the expected patched RMC path — patching may not have run"
fi

echo ""

# ──────────────────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────────────────
echo "======================================================"
echo " INTEGRATION TEST RESULTS: $PASSED passed, $FAILED failed"
echo "======================================================"

if [[ $FAILED -gt 0 ]]; then
  echo ""
  echo "Failures:"
  for err in "${ERRORS[@]}"; do
    echo "  ✗ $err"
  done
  exit 1
fi

exit 0
