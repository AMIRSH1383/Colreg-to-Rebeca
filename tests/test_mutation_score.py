import pytest
from pathlib import Path
from skills.rebeca_tooling.scripts.mutation_engine import MutationEngine, run_mutants
from skills.rebeca_tooling.scripts.vacuity_checker import check_vacuity
from fixtures import RULE_ID

MUTATION_MODEL = """
reactiveclass Ship(10) {
  statevars { int x; }
  Ship() { x = 0; self.tick(); }
  msgsrv tick() { x = 1; self.tick() after(1); }
}
main {
  Ship s1():();
}
"""

MUTATION_PROPERTY = """
property {
  define { isBig = (s1.x > 5); }
  Assertion { Rule22: !isBig; }
}
"""

@pytest.fixture(scope="module")
def module_tmp():
    import tempfile
    import shutil
    d = Path(tempfile.mkdtemp(dir=tempfile.gettempdir()))
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
    
    stats = run_mutants(mutants, jar, model_file, prop_file, max_mutants=4,
                        timeout_seconds=30, total_timeout=120)
    return {**stats, "vacuity": vacuity}

@pytest.fixture(scope="module")
def mutation_report(rmc_jar, module_tmp):
    return run_mutation_suite_for_test(rmc_jar, MUTATION_MODEL, MUTATION_PROPERTY, module_tmp)


@pytest.mark.requires_rmc
def test_at_least_some_mutants_killed(mutation_report):
    assert mutation_report["baseline_outcome"] == "satisfied"
    assert mutation_report["killed"] > 0


@pytest.mark.requires_rmc
def test_non_vacuous_property_flag(mutation_report):
    assert mutation_report["vacuity"]["is_vacuous"] is False
