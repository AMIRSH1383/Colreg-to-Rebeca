"""Synthetic language-independent logic tests, never extraction replay inputs."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from direct_colreg.logic import validate, render, property_text, effective_applicability, Unsupported
from direct_colreg.binding import bind
from direct_colreg.property_io import merge
from direct_colreg.pipeline import synthesize
from direct_colreg.semantics import validate_extraction
from direct_colreg.provider import CodexProvider


def compare(value=7, operator='>=', concept='measurement', entity='Unit', unit='metres'):
    return {'op': 'compare', 'entity': entity, 'concept': concept, 'operator': operator,
            'value': value, 'unit': unit, 'args': []}


class GenericTests(unittest.TestCase):
    def setUp(self):
        self.binding = {('Unit', 'measurement'): {'variable': 'measurement', 'type': 'int',
                        'unit': 'metres', 'class': 'Unit', 'instances': ['u']}}
        self.req = {'id': 'r', 'statement_ids': ['s'], 'support': 'state', 'reason': None,
                    'kind': 'obligation', 'temporal': None, 'applicability': compare(2),
                    'obligation': compare(), 'exceptions': []}

    def test_all_comparisons_render(self):
        for op in ('>', '>=', '<', '<=', '==', '!='):
            with self.subTest(op=op):
                definitions = []
                render(compare(operator=op), self.binding, 'u', definitions)
                self.assertIn(' ' + op + ' ', definitions[0])

    def test_logic_operators(self):
        for op, args in [('and', [compare(), compare()]), ('or', [compare(), compare()]),
                         ('not', [compare()]), ('implies', [compare(), compare()])]:
            expr = {'op': op, 'args': args}
            validate(expr)
            self.assertTrue(render(expr, self.binding, 'u', []))

    def test_exceptions_and_prohibitions(self):
        self.req['exceptions'] = [compare(9, '>')]
        self.req['kind'] = 'prohibition'
        condition = effective_applicability(self.req)
        self.assertEqual(condition['op'], 'and')
        self.assertEqual(condition['args'][1]['op'], 'not')
        _, assertions = property_text(self.req, self.binding, 'u')
        self.assertIn('!(', assertions[0])

    def test_temporal_and_multiple_actors_rejected(self):
        self.req['temporal'] = 'eventually'
        with self.assertRaises(Unsupported):
            property_text(self.req, self.binding, 'u')
        self.req['temporal'] = None
        self.req['applicability']['entity'] = 'Other'
        with self.assertRaises(Unsupported):
            property_text(self.req, self.binding, 'u')

    def test_type_and_unit_mismatch_rejected(self):
        for field, value in [('type', 'boolean'), ('unit', 'seconds')]:
            bindings = copy.deepcopy(self.binding)
            bindings[('Unit', 'measurement')][field] = value
            with self.assertRaises(Unsupported):
                render(compare(), bindings, 'u', [])

    def test_boolean_ordering_rejected(self):
        expr = compare(True, '>')
        with self.assertRaises(Unsupported):
            render(expr, self.binding, 'u', [])

    def test_unknown_operator_and_nan_rejected(self):
        for expr in [{'op': 'eventually'}, compare(float('nan'))]:
            with self.assertRaises(Unsupported):
                validate(expr)

    def test_existing_properties_preserved(self):
        original = 'property { define { old = (u.measurement > 0); } Assertion { Old: old; } }'
        text = merge(original, ['G_new = (u.measurement < 8);'], ['G_New: G_new;'])
        self.assertIn('Old: old;', text)
        self.assertIn('old = (u.measurement > 0);', text)
        with self.assertRaises(ValueError):
            merge(text, [], [])

    def test_exact_mapping_requires_actor_type_and_known_units(self):
        inventory = {'reactive_classes': [{'name': 'Unit', 'state_variables': [
            {'name': 'measurement', 'type': 'int'}]}], 'instances': [{'class': 'Unit', 'name': 'u'}]}
        data = {'formalization': [self.req], 'extraction': {'entities': [
            {'id': 'Unit', 'name': 'Unit'}], 'statements': []}}
        catalog = {'version': 1, 'models': [{'sha256': 'hash', 'fields': [
            {'class': 'Unit', 'variable': 'measurement', 'unit': 'metres', 'provenance': 'synthetic test units'}]}]}
        selected, records = bind(data, inventory, catalog, 'hash', None, None)
        self.assertEqual(records[0]['method'], 'automatically_discovered')
        self.assertIn(('Unit', 'measurement'), selected)
        selected, records = bind(data, inventory, catalog, 'wrong-hash', None, None)
        self.assertFalse(selected)
        self.assertEqual(records[0]['method'], 'abstained')

    def test_missing_concept_is_not_invented(self):
        parts = synthesize({'formalization': [self.req]}, {})
        self.assertFalse(parts[1])
        self.assertEqual(parts[3][0]['status'], 'UNSUPPORTED_SEMANTICS')

    def test_unique_names_and_shared_antecedent(self):
        other = copy.deepcopy(self.req)
        other['id'] = 'other'
        parts = synthesize({'formalization': [self.req, other]}, self.binding)
        self.assertEqual(len(parts[1]), 2)
        names = [d.split('=')[0].strip() for d in parts[0]]
        self.assertEqual(len(set(names)), len(names))
        self.assertEqual(len(parts[2]), 1)

    def synthetic_semantics(self):
        # Unit-test data only: never passed to the production provider adapter.
        source = 'Unit: measurement >= 2 metres; measurement shall be >= 7 metres.'
        statements = []
        for sid, role, quote, value in [('stmt01', 'scope', 'measurement >= 2 metres', 2),
                                       ('stmt02', 'obligation', 'measurement shall be >= 7 metres', 7)]:
            statements.append({'id': sid, 'role': role, 'source_text': quote, 'subjects': ['unit'],
                'concept': 'measurement', 'predicate': quote, 'operator': '>=', 'value': value,
                'unit': 'metres', 'applies_when': ['stmt01'] if role == 'obligation' else []})
        requirement = copy.deepcopy(self.req)
        requirement['statement_ids'] = ['stmt02']
        requirement['applicability']['entity'] = 'unit'
        requirement['obligation']['entity'] = 'unit'
        return source, {'schema_version': 2, 'status': 'ok', 'rule_id': 'Synthetic',
            'extraction': {'entities': [{'id': 'unit', 'name': 'Unit', 'type': 'participant', 'source_text': 'Unit'}],
                           'statements': statements, 'references': []},
            'open_assumptions': [], 'formalization': [requirement]}

    def test_general_schema_and_traceability(self):
        source, data = self.synthetic_semantics()
        self.assertEqual(len(validate_extraction(data, source, 'Synthetic')), 3)

    def test_ungrounded_and_dangling_data_rejected(self):
        source, data = self.synthetic_semantics()
        data['extraction']['statements'][0]['source_text'] = 'invented source'
        with self.assertRaises(ValueError):
            validate_extraction(data, source, 'Synthetic')
        source, data = self.synthetic_semantics()
        data['formalization'][0]['statement_ids'] = ['missing']
        with self.assertRaises(ValueError):
            validate_extraction(data, source, 'Synthetic')

    def test_formalization_cannot_invent_numeric_statement(self):
        source, data = self.synthetic_semantics()
        data['formalization'][0]['obligation']['value'] = 8
        with self.assertRaises(ValueError):
            validate_extraction(data, source, 'Synthetic')

    def test_provider_transport_schema_and_usage_unit_test_only(self):
        # Mock transport only to test protocol conversion. Not an evaluation
        # extraction and never available as a production provider backend.
        schema = {'type': 'object', 'additionalProperties': False, 'required': ['version'],
                  'properties': {'version': {'const': 2}}}
        def process(command, **kwargs):
            wire = json.loads(Path(command[command.index('--output-schema') + 1]).read_text())
            self.assertEqual(wire['properties']['version'], {'enum': [2], 'type': 'integer'})
            Path(command[command.index('--output-last-message') + 1]).write_text('{"version":2}')
            class Result:
                returncode = 0
                stdout = '{"type":"turn.completed","usage":{"input_tokens":10,"cached_input_tokens":0,"output_tokens":4}}'
                stderr = ''
            return Result()
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            provider = CodexProvider('synthetic-test-model')
            with patch('direct_colreg.provider.subprocess.run', side_effect=process):
                self.assertEqual(provider.request('unit test', schema, Path(directory) / 'request', 'unit_test'), {'version': 2})
            self.assertEqual(provider.calls[0]['input_tokens'], 10)
            self.assertIsNone(provider.calls[0]['estimated_cost'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
