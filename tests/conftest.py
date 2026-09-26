"""
Shared pytest fixtures and path setup for the RebecAI test suite.
"""
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_SCRIPTS = _ROOT / "skills" / "rebeca_tooling" / "scripts"
_TESTS = Path(__file__).parent

sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_SCRIPTS))
sys.path.insert(0, str(_TESTS))

import pytest


# ---------------------------------------------------------------------------
# Real rmc.jar — used by tests that invoke run_rmc for real
# ---------------------------------------------------------------------------

RMC_JAR = Path.home() / ".rebeca" / "rmc.jar"


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "requires_rmc: mark test as requiring a real rmc.jar"
    )


def pytest_collection_modifyitems(config, items):
    if not RMC_JAR.exists():
        skip = pytest.mark.skip(reason=f"rmc.jar not found at {RMC_JAR}")
        for item in items:
            if item.get_closest_marker("requires_rmc"):
                item.add_marker(skip)


@pytest.fixture(scope="session")
def rmc_jar() -> str:
    """Path to the real rmc.jar. Session-scoped — resolved once per run."""
    if not RMC_JAR.exists():
        pytest.skip(f"rmc.jar not found at {RMC_JAR}")
    return str(RMC_JAR)


# ---------------------------------------------------------------------------
# Known-good model + property (same as run_integration_tests.sh IT-009)
# ---------------------------------------------------------------------------

GOOD_MODEL = """\
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
"""

GOOD_PROPERTY = """\
property {
  define {
    isLong = (s1.length > 50);
    lightOn = (s1.hasLight == true);
  }
  Assertion {
    Rule22: !isLong || lightOn;
  }
}
"""


@pytest.fixture(scope="session")
def model_dir(tmp_path_factory):
    """Session-scoped dir with a known-good .rebeca + .property pair under ~."""
    d = Path(tempfile.mkdtemp(dir=Path.home()))
    (d / "model.rebeca").write_text(GOOD_MODEL, encoding="utf-8")
    (d / "model.property").write_text(GOOD_PROPERTY, encoding="utf-8")
    yield d
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(scope="session")
def model_file(model_dir) -> str:
    return str(model_dir / "model.rebeca")


@pytest.fixture(scope="session")
def property_file(model_dir) -> str:
    return str(model_dir / "model.property")


# ---------------------------------------------------------------------------
# Function-scoped home temp dir (for tests that write their own files)
# ---------------------------------------------------------------------------

@pytest.fixture
def home_tmp():
    """Temp directory inside Path.home() so safe_path() allows it."""
    import shutil
    d = tempfile.mkdtemp(dir=Path.home())
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------------------
# MutationEngine instance
# ---------------------------------------------------------------------------

@pytest.fixture
def engine():
    from mutation_engine import MutationEngine
    return MutationEngine()
