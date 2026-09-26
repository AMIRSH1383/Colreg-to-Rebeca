import importlib
import sys
from pathlib import Path

# Add scripts directory to path to support dynamic import
sys.path.insert(0, str(Path(__file__).parent))

def _lazy_import(name, module_name):
    # Filenames are hyphenated, modules must be underscore for Python
    module = importlib.import_module(module_name.replace("-", "_"))
    return getattr(module, name)

run_rmc = _lazy_import("run_rmc", "run-rmc")
resolve_rmc_jar = _lazy_import("resolve_rmc_jar", "rmc_resolver")
require_rmc_jar = _lazy_import("require_rmc_jar", "rmc_resolver")
RuleStatusClassifier = _lazy_import("RuleStatusClassifier", "classify-rule-status")
from .utils import safe_path, safe_open, validate_https_url, resolve_executable
MutationEngine = _lazy_import("MutationEngine", "mutation-engine")
Mutation = _lazy_import("Mutation", "mutation-engine")
parse_rmc_result_file = _lazy_import("parse_rmc_result_file", "rmc_result_parser")
check_vacuity = _lazy_import("check_vacuity", "vacuity-checker")
extract_precondition = _lazy_import("extract_precondition", "vacuity-checker")
build_negated_property = _lazy_import("build_negated_property", "vacuity-checker")

__all__ = [
    "run_rmc",
    "resolve_rmc_jar", "require_rmc_jar", "RuleStatusClassifier",
    "safe_path", "safe_open", "validate_https_url", "resolve_executable",
    "MutationEngine", "Mutation", "parse_rmc_result_file", "check_vacuity", "extract_precondition",
]
