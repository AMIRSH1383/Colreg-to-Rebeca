"""Downstream and mutation checks; run directly without third-party dependencies."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('evaluation', ROOT / 'scripts/evaluate-extractor.py')
evaluation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluation)


class ExtractorEvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / 'work/Original Model.rebeca').read_text(encoding='utf-8')
        cls.mapping = json.loads((ROOT / 'tests/evaluation/rule22_binding.json').read_text())
        cls.reference = json.loads((ROOT / 'tests/evaluation/original_model_reference.json').read_text())

    def test_reference_and_all_static_scenarios(self):
        with tempfile.TemporaryDirectory() as directory:
            report = evaluation.run(Path(directory))
            self.assertTrue(report['local_passed'])
            self.assertEqual(report['scenario_count'], 18)
            self.assertFalse(report['rmc_passed'])
            self.assertEqual(sum(c['applicable'] for c in report['scenarios']), 12)
            self.assertEqual(sum(not c['expected_satisfied'] for c in report['scenarios']), 10)

    def test_renaming_requires_binding_update(self):
        source = self.source.replace('masthead_light_range', 'mast_range')
        inventory = evaluation.extract(source)
        with self.assertRaisesRegex(ValueError, 'masthead_light_range'):
            evaluation.properties(inventory, self.mapping)
        mapping = copy.deepcopy(self.mapping)
        mapping['requirements'][0]['variable'] = 'mast_range'
        generated = evaluation.properties(inventory, mapping)
        self.assertIn('s1.mast_range >= 6', generated)
        self.assertNotIn('masthead_light_range', generated)

    def test_new_instance_gets_properties(self):
        source = self.source.replace('@priority(1) MapServer theMap',
            'Ship s3(theMap):(3,5,13,47,13,2,1.1,1500,false,50,20,3,false,true);\n'
            '@priority(1) MapServer theMap')
        inventory = evaluation.extract(source)
        generated = evaluation.properties(inventory, self.mapping)
        self.assertEqual(generated.count('Rule22_s3_'), 5)
        self.assertEqual(len(evaluation.bind(inventory, self.mapping)), 3)

    def test_constructor_argument_change_is_extracted(self):
        inventory = evaluation.extract(self.source.replace('false,12,20,3,false,true',
                                                           'false,50,20,3,false,true'))
        self.assertIn('false,50,20,3,false,true', inventory['instances'][0]['constructor_arguments'])
        self.assertFalse(evaluation.compare(inventory, self.reference)['passed'])

    def test_comments_do_not_change_facts(self):
        modified = '// fake { reactiveclass Ghost(1) {} }\n' + self.source
        modified = modified.replace('statevars{', 'statevars{ /* } fake variable; { */')
        self.assertEqual(evaluation.facts(evaluation.extract(modified)),
                         evaluation.facts(evaluation.extract(self.source)))

    def test_reference_detects_missing_extra_and_wrong_type(self):
        baseline = evaluation.extract(self.source)
        for mutation in ('missing', 'extra', 'wrong_type'):
            with self.subTest(mutation=mutation):
                inventory = copy.deepcopy(baseline)
                variables = inventory['reactive_classes'][0]['state_variables']
                if mutation == 'missing':
                    variables.pop()
                elif mutation == 'extra':
                    variables.append({'name': 'invented', 'type': 'int'})
                else:
                    variables[0]['type'] = 'boolean'
                self.assertFalse(evaluation.compare(inventory, self.reference)['passed'])

    def test_selected_assignment_error_is_detected(self):
        inventory = evaluation.extract(self.source.replace('masthead_light_range = 6;',
                                                           'masthead_light_range = 5;'))
        result = evaluation.compare(inventory, self.reference)
        self.assertFalse(result['passed'])
        self.assertTrue(any(not item['passed'] for item in result['selected_assignments']))

    def test_annotated_message_is_not_lost(self):
        inventory = evaluation.extract(self.source)
        methods = inventory['reactive_classes'][1]['message_servers']
        self.assertIn('scanObstacles', [m['name'] for m in methods])

    def test_property_oracle_detects_wrong_threshold(self):
        generated = evaluation.properties(evaluation.extract(self.source), self.mapping)
        state = {f'{instance}.{field}': value for instance in ('s1', 's2')
                 for field, value in [('ship_length', 50), ('masthead_light_range', 5),
                     ('side_light_range', 3), ('stern_light_range', 3),
                     ('towing_light_range', 3), ('allround_light_range', 3)]}
        self.assertFalse(evaluation.evaluate_property(generated, state))
        corrupted = generated.replace('masthead_light_range >= 6', 'masthead_light_range >= 5')
        self.assertTrue(evaluation.evaluate_property(corrupted, state))


if __name__ == '__main__':
    unittest.main(verbosity=2)
