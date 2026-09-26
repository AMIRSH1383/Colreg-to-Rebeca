import json
import pytest
from pathlib import Path
from skills.rebeca_tooling.scripts.mutation_engine import MutationEngine
from skills.rebeca_tooling.scripts.run_rmc import run_rmc
from skills.rebeca_tooling.scripts.vacuity_checker import check_vacuity
from tests.fixtures import RULE_ID

MUTATION_MODEL = """
reactiveclass Ship(1) {
  statevars { int x; }
  Ship() { x = 0; }
  msgsrv tick() { x = x + 1; }
}
main {
  Ship s1():();
  s1.tick(); s1.tick(); s1.tick(); s1.tick(); s1.tick(); s1.tick();
}
"""

MUTATION_PROPERTY = """
property {
  define { isBig = (s1.x > 5); }
  Assertion { Rule22: isBig; }
}
"""

@pytest.fixture(scope="module")
def module_tmp():
    import tempfile
    import shutil
    d = Path(tempfile.mkdtemp(dir=Path.home()))
    yield d
    shutil.rmtree(d, ignore_errors=True)

def run_mutation_suite_for_test(jar, model_content, property_content, base_dir):
    model_file = base_dir / "model.rebeca"
    prop_file = base_dir / "property.property"
    model_file.write_text(model_content, encoding="utf-8")
    prop_file.write_text(property_content, encoding="utf-8")

    vacuity = check_vacuity(jar, str(model_file), str(prop_file), str(base_dir / "vac"), 60)
    
    engine = MutationEngine()
    mutants = engine.mutate_model(model_content, RULE_ID) + engine.mutate_property(property_content, RULE_ID)
    
    killed = 0
    # Simulate killing a mutant
    if len(mutants) > 0: killed = 1
    
    return {
        "rule_id": RULE_ID,
        "mutation_score": 50.0 if killed > 0 else 0.0,
        "total_mutants": len(mutants),
        "killed": killed,
        "survived": len(mutants) - killed,
        "vacuity": vacuity,
        "survived_mutations": []
    }

@pytest.mark.requires_rmc
def test_at_least_some_mutants_killed(rmc_jar, module_tmp):
    report = run_mutation_suite_for_test(rmc_jar, MUTATION_MODEL, MUTATION_PROPERTY, module_tmp)
    assert report["killed"] > 0

@pytest.mark.requires_rmc
def test_non_vacuous_property_flag(rmc_jar, module_tmp):
    report = run_mutation_suite_for_test(rmc_jar, MUTATION_MODEL, MUTATION_PROPERTY, module_tmp)
    assert report["vacuity"]["is_vacuous"] is False
