"""Milestone semantics and failure-path regression tests; no real RMC required."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('milestone', ROOT / 'scripts/rule22_pipeline.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
sys.path.insert(0, str(ROOT))
import run_rmc
import vacuity_checker
import verify_gate
from rmc_result_parser import parse_rmc_result_file


class MilestoneTests(unittest.TestCase):
    def setUp(self):
        self.source = (ROOT / 'examples/rule22a/source.txt').read_text().strip()
        self.data = m.extract_clause(self.source)
        self.inventory = m.extract(m.fixture(50, [6, 3, 3, 3, 3]))

    def test_extraction_schema_grounding_and_boundaries(self):
        spans = m.validate_extraction(self.data, self.source)
        self.assertEqual(len(spans), 7)
        self.assertEqual(self.data['extraction']['statements'][1]['operator'], '>=')
        self.assertEqual(self.data['extraction']['statements'][1]['value'], 50)
        self.assertEqual(self.data['extraction']['references'], ['Section 8 Annex I'])

    def test_changed_threshold_and_dangling_scope_rejected(self):
        for key, value in [('operator', '>'), ('value', 51), ('unit', 'feet'),
                           ('applies_when', ['nonexistent'])]:
            with self.subTest(key=key):
                data = copy.deepcopy(self.data)
                data['extraction']['statements'][1][key] = value
                with self.assertRaises(Exception):
                    m.validate_extraction(data, self.source)

    def test_no_silent_source_generalization(self):
        with self.assertRaises(ValueError):
            m.extract_clause(self.source.replace('50 metres', '51 metres'))

    def test_missing_or_wrong_type_mapping_blocks(self):
        for change in ('missing', 'wrong_type'):
            inventory = copy.deepcopy(self.inventory)
            variables = inventory['reactive_classes'][0]['state_variables']
            if change == 'missing':
                variables.pop()
            else:
                variables[-1]['type'] = 'boolean'
            result = m.bind(self.data, inventory)
            self.assertEqual(result['status'], 'blocked')
            with self.assertRaises(ValueError):
                m.render(result)

    def test_annex_gap_explicit(self):
        result = m.bind(self.data, self.inventory)
        self.assertEqual(result['status'], 'bound')
        self.assertFalse(result['full_regulatory_compliance'])
        self.assertEqual(result['unresolved'][0]['concept'], 'light_intensity')

    def test_synthesis_preserves_unrelated_sections(self):
        original = 'property {\n define { old = (s1.ship_length > 0); }\n Assertion { Old: old; }\n LTL { }\n}'
        defines, assertions = m.render(m.bind(self.data, self.inventory))
        generated = m.merge_property(original, defines, assertions)
        self.assertIn('old = (s1.ship_length > 0);', generated)
        self.assertIn('Old: old;', generated)
        self.assertIn('LTL { }', generated)
        self.assertIn('s1.ship_length >= 50', generated)
        self.assertIn('s1.allround_light_range >= 3', generated)
        self.assertEqual(generated.count('M1_Range_'), 5)
        with self.assertRaises(ValueError):
            m.merge_property(generated, defines, assertions)

    def test_applicability_is_antecedent_only(self):
        definitions, assertions = m.render(m.bind(self.data, self.inventory), witness_instance='s1')
        self.assertEqual(assertions, ['M1_WitnessAbsent_s1: !M1_s1_scope;'])
        self.assertEqual(len(definitions), 1)

    def test_new_property_has_rmc_section_order(self):
        generated = m.merge_property('property { }', *m.render(m.bind(self.data, self.inventory)))
        self.assertLess(generated.index('define'), generated.index('Assertion'))
        existing = 'property { Assertion { Keep: true; } }'
        generated = m.merge_property(existing, *m.render(m.bind(self.data, self.inventory)))
        self.assertLess(generated.index('define'), generated.index('Assertion'))

    def test_zero_and_nonzero_exit_are_not_verdicts(self):
        self.assertEqual(run_rmc._classify_model_outcome(0), 'unknown')
        self.assertEqual(run_rmc._classify_model_outcome(1), 'unknown')

    def test_legacy_vacuity_does_not_infer_antecedent(self):
        result = vacuity_checker.check_vacuity('missing', 'missing', 'missing', 'missing')
        self.assertIsNone(result['is_vacuous'])
        self.assertEqual(result['comparison_basis'], 'explicit_applicability_required')

    def test_gate_rejects_compilation_and_unknown_vacuity(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with patch.object(verify_gate, 'run_rmc_detailed', return_value={
                    'rmc_exit_code': 0, 'rmc_outcome': 'verified', 'verification_outcome': 'unknown'}):
                result = verify_gate.run_verification_gate('jar', 'model', 'property', 'Rule22', directory,
                                                           skip_vacuity=True, skip_mutation=True)
                self.assertFalse(result['passes_gate'])
            with patch.object(verify_gate, 'run_rmc_detailed', return_value={
                    'rmc_exit_code': 0, 'rmc_outcome': 'verified', 'verification_outcome': 'satisfied'}), \
                 patch.object(verify_gate, 'check_vacuity', return_value={'is_vacuous': None}):
                result = verify_gate.run_verification_gate('jar', 'model', 'property', 'Rule22', directory,
                                                           skip_mutation=True)
                self.assertFalse(result['passes_gate'])

    def test_strict_parser_requires_actual_xml_verdict(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / 'result.xml'
            for text in ['verified', '<anything><result>satisfied</result></anything>',
                         '<model-checking-report><result>satisfied</result></model-checking-report>',
                         '<model-checking-report><checked-property><result>not satisfied</result></checked-property></model-checking-report>']:
                path.write_text(text)
                self.assertEqual(parse_rmc_result_file(str(path), strict=True)['outcome'], 'unknown')
            path.write_text('<model-checking-report><checked-property><result>satisfied</result></checked-property></model-checking-report>')
            self.assertEqual(parse_rmc_result_file(str(path), strict=True)['outcome'], 'satisfied')
            path.write_text('<model-checking-report><checked-property><result>assertion failed</result></checked-property><counter-example-trace><state id="1"/></counter-example-trace></model-checking-report>')
            result = parse_rmc_result_file(str(path), strict=True)
            self.assertEqual(result['outcome'], 'cex')
            self.assertTrue(Path(result['counterexample_path']).exists())

    def test_timeout_discards_partial_satisfaction(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            exe = Path(directory) / 'model.out'
            exe.write_text('fixture')
            def timeout(*args, **kwargs):
                (Path(directory) / 'result.xml').write_text('<model-checking-report><checked-property><result>satisfied</result></checked-property></model-checking-report>')
                raise run_rmc.subprocess.TimeoutExpired('model.out', 1)
            with patch.object(run_rmc.subprocess, 'run', side_effect=timeout):
                record = run_rmc.run_model_out(exe, export_result='result.xml')
            self.assertFalse(record['executed'])
            self.assertEqual(record['outcome'], 'timeout')

    def test_model_execution_drops_stale_xml(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            exe = Path(directory) / 'model.out'
            exe.write_text('not an actual executable')
            result = Path(directory) / 'result.xml'
            result.write_text('<model-checking-report><checked-property><result>satisfied</result></checked-property></model-checking-report>')
            with patch.object(run_rmc.subprocess, 'run') as process:
                process.return_value.returncode = 0
                record = run_rmc.run_model_out(exe, export_result='result.xml')
            self.assertFalse(result.exists())
            self.assertEqual(record['outcome'], 'unknown')

    def test_compile_and_generation_error_not_satisfaction(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            for name in ('rmc.jar', 'model.rebeca', 'model.property'):
                (root / name).write_text('fixture')
            def process(command, **kwargs):
                if command[0] == 'java':
                    (Path(kwargs['cwd']) / 'generated.cpp').write_text('int main() {return 0;}')
                else:
                    (Path(kwargs['cwd']) / 'model.out').write_text('fixture')
                class Result:
                    returncode = 0
                return Result()
            with patch.object(run_rmc.subprocess, 'run', side_effect=process):
                result = run_rmc.run_rmc_detailed(str(root / 'rmc.jar'), str(root / 'model.rebeca'),
                    str(root / 'model.property'), str(root / 'out'))
            self.assertEqual(result['rmc_outcome'], 'compiled')
            self.assertEqual(result['verification_outcome'], 'unknown')
            with patch.object(run_rmc.subprocess, 'run') as process:
                process.return_value.returncode = 1
                result = run_rmc.run_rmc_detailed(str(root / 'rmc.jar'), str(root / 'model.rebeca'),
                    str(root / 'model.property'), str(root / 'error'))
            self.assertEqual(result['verification_outcome'], 'unknown')


if __name__ == '__main__':
    unittest.main(verbosity=2)
