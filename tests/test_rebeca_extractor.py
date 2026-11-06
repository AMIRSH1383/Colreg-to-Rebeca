"""Regression tests for scripts/rebeca_extractor.py.

Schema validation uses the existing jsonschema development dependency; the
extractor itself has no external runtime dependencies.

Run from repository root:
    python -m unittest discover -s tests -p test_rebeca_extractor.py -v
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
# Supported after placing test in tests/ and extractor in scripts/.
MODULE_PATH = HERE.parent.parent / "scripts" / "rebeca_extractor.py"
if not MODULE_PATH.is_file():
    MODULE_PATH = HERE.with_name("rebeca_extractor.py")
spec = importlib.util.spec_from_file_location("rebeca_extractor", MODULE_PATH)
extractor = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(extractor)

SAMPLE = r'''
// The next fake class should not be parsed: reactiveclass Fake(1) { }
/* env int COMMENTED = 1; */
env int LENGTH = 55;
reactiveclass Vessel(10) {
  knownrebecs { MapServer theMap; }
  statevars {
    int length, speed;
    boolean engine_on;
    int[3/*comment*/] readings;
  }
  Vessel(int len){
    length = len;
    engine_on = true;
    readings[0] = 0;
  }
  @priority(2)
  msgsrv step(int amount){
    speed = amount;
    readings[1] = amount;
    assertion(speed >= 0,"not negative");
  }
}
reactiveclass MapServer(5) {
  knownrebecs { Vessel s1; Vessel s2; }
  statevars { int count; }
  MapServer(){count = 2;}
  msgsrv tick(){count++;}
}
main {
  @priority(1) Vessel s1(theMap):(12);
  @priority(3) Vessel s2(theMap):(70);
  MapServer theMap(s1,s2):();
}
'''


class TestParser(unittest.TestCase):
    def setUp(self):
        self.result = extractor.parse_model(SAMPLE, "sample.rebeca")

    def test_main_counts(self):
        self.assertEqual(self.result["summary"]["reactive_classes"], 2)
        self.assertEqual(self.result["summary"]["instances"], 3)
        self.assertEqual(self.result["summary"]["message_servers"], 2)

    def test_no_fake_or_commented_constants(self):
        self.assertEqual([x["name"] for x in self.result["reactive_classes"]], ["Vessel", "MapServer"])
        self.assertEqual([x["name"] for x in self.result["environment_constants"]], ["LENGTH"])

    def test_multiple_variables_and_array_dimension(self):
        v = self.result["reactive_classes"][0]
        state = {x["name"]: x for x in v["state_variables"]}
        self.assertEqual(sorted(state), ["engine_on", "length", "readings", "speed"])
        self.assertEqual(state["readings"]["array_dimensions"], ["3"])
        self.assertNotIn("constructor_initialization", state["readings"])

    def test_per_instance_initial_values(self):
        v = self.result["reactive_classes"][0]
        state = {x["name"]: x for x in v["state_variables"]}
        self.assertEqual(state["length"]["constructor_initialization"]["per_instance"], {
            "s1": {"resolved": True, "value": 12}, "s2": {"resolved": True, "value": 70}
        })
        self.assertEqual(state["engine_on"]["constructor_initialization"]["per_instance"]["s2"], {"resolved": True, "value": True})

    def test_main_links(self):
        instances = {i["name"]: i for i in self.result["instances"]}
        self.assertEqual(instances["s1"]["known_rebec_bindings"], {"theMap": "theMap"})
        self.assertEqual(instances["theMap"]["known_rebec_bindings"], {"s1": "s1", "s2": "s2"})
        self.assertEqual(instances["s2"]["priority"], 3)

    def test_server_writes_and_assertions(self):
        server = self.result["reactive_classes"][0]["message_servers"][0]
        self.assertEqual(server["name"], "step")
        self.assertEqual(server["priority"], 2)
        self.assertEqual({x["variable"] for x in server["state_writes"]}, {"speed", "readings"})
        self.assertEqual(server["inline_assertions"][0]["condition"], "speed >= 0")

    def test_only_direct_initializers_resolve(self):
        v = self.result["reactive_classes"][0]
        state = {x["name"]: x for x in v["state_variables"]}
        self.assertNotIn("constructor_initialization", state["speed"])
        self.assertNotIn("constructor_initialization", state["readings"])

    def test_malformed_input_is_rejected(self):
        with self.assertRaises(extractor.ExtractionError):
            extractor.parse_model("reactiveclass A(1) {", "bad.rebeca")

    def test_cli_does_not_modify_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "model.rebeca"
            output = Path(tmp) / "output" / "model.json"
            source.write_text(SAMPLE, encoding="utf-8")
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            run = subprocess.run([sys.executable, str(MODULE_PATH), "--input", str(source), "--output", str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertTrue(output.is_file())
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["summary"]["instances"], 3)

    def test_real_reference_model_when_available(self):
        source = HERE.parent.parent / "inputs" / "rebeca" / "original_model.rebeca"
        if not source.is_file():
            self.skipTest("Repo reference model not present; synthetic tests still run")
        model = extractor.parse_model(source.read_text(encoding="utf-8-sig"), source.as_posix())
        self.assertEqual(model["summary"]["reactive_classes"], 2)
        self.assertEqual(model["summary"]["instances"], 3)
        self.assertEqual(model["summary"]["message_servers"], 6)
        self.assertEqual({c["name"] for c in model["reactive_classes"]}, {"Ship", "MapServer"})
        ship = next(c for c in model["reactive_classes"] if c["name"] == "Ship")
        variables = {v["name"]: v for v in ship["state_variables"]}
        self.assertEqual(variables["ship_length"]["constructor_initialization"]["per_instance"]["s1"]["value"], 12)
        self.assertEqual(variables["ship_length"]["constructor_initialization"]["per_instance"]["s2"]["value"], 10)
        self.assertEqual(variables["allround_light_range"]["constructor_initialization"]["per_instance"]["s1"]["value"], 2)

    def test_cli_rejects_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "model.rebeca"
            source.write_text(SAMPLE, encoding="utf-8")
            run = subprocess.run([sys.executable, str(MODULE_PATH), "--input", str(source), "--output", str(source)], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertIn("overwrite", run.stderr)


class TestParserRegressions(unittest.TestCase):
    def parse_constructor(self, body, states='int x;'):
        return extractor.parse_model(
            'reactiveclass A(5) { statevars {' + states + '} A(boolean flag) {' + body +
            '} } main { A a():(true); }', 'regression.rebeca')['reactive_classes'][0]

    def test_equality_is_not_an_initializer(self):
        cl = self.parse_constructor('x == 3;')
        self.assertNotIn('constructor_initialization', cl['state_variables'][0])

    def test_later_conditional_write_invalidates_earlier_value(self):
        cl = self.parse_constructor('x = 1; if(flag) { x = 2; }')
        self.assertNotIn('constructor_initialization', cl['state_variables'][0])

    def test_unconditional_assignment_after_branch_is_retained(self):
        cl = self.parse_constructor('if(flag) { x = 2; } x = 3;')
        self.assertEqual(cl['state_variables'][0]['constructor_initialization']['per_instance']['a']['value'], 3)

    def test_multiple_locals_do_not_become_state_writes(self):
        cl = self.parse_constructor('int local, x; x = 3;')
        self.assertEqual(cl['constructor']['state_writes'], [])
        self.assertNotIn('constructor_initialization', cl['state_variables'][0])

    def test_env_text_in_string_is_not_a_constant(self):
        cl = extractor.parse_model(
            'reactiveclass A(5) { A() { assertion(true,"env int FAKE = 1;"); } } main { A a():(); }',
            'regression.rebeca')
        self.assertEqual(cl['environment_constants'], [])

    def test_unterminated_declaration_is_rejected(self):
        with self.assertRaises(extractor.ExtractionError):
            self.parse_constructor('', 'int x; int missing')

    def test_string_initializer_containing_semicolon(self):
        declarations = extractor.parse_declarations('String s = "hello;world";')
        self.assertEqual(declarations[0]['declaration_initializer'], '"hello;world"')


class TestIntegrationSafety(unittest.TestCase):
    def test_output_hardlink_cannot_overwrite_input(self):
        import os
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'model.rebeca'
            target = Path(tmp) / 'alias.rebeca'
            source.write_text(SAMPLE)
            os.link(source, target)
            before = source.read_bytes()
            self.assertEqual(extractor.main(['--input', str(source), '--output', str(target)]), 1)
            self.assertEqual(source.read_bytes(), before)

    def test_repeated_cli_output_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'model.rebeca'
            target = Path(tmp) / 'out.json'
            source.write_text(SAMPLE)
            args = ['--input', str(source), '--output', str(target)]
            self.assertEqual(extractor.main(args), 0)
            before = target.read_bytes()
            self.assertEqual(extractor.main(args), 0)
            self.assertEqual(target.read_bytes(), before)

    def test_original_model_output_matches_schema(self):
        from jsonschema import Draft202012Validator
        root = HERE.parent.parent
        schema = json.loads((root / 'schemas/rebeca_extraction.schema.json').read_text())
        Draft202012Validator.check_schema(schema)
        source = root / 'inputs/rebeca/original_model.rebeca'
        output = extractor.parse_model(source.read_text(encoding='utf-8-sig'), source.as_posix())
        Draft202012Validator(schema).validate(output)


if __name__ == '__main__':
    unittest.main()
