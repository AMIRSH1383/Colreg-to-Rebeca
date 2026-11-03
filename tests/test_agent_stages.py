"""Independent checks of actor-scope safety and persisted agent boundaries."""
import copy
import sys
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from direct_colreg.synthesis import synthesize
from direct_colreg.agent_stages import handoff, validate_handoff, write_synthesis
from extract_rebeca import extract


def atom(entity, concept):
    return {'op': 'compare', 'entity': entity, 'concept': concept, 'operator': '>=',
            'value': 4, 'unit': 'metres', 'args': []}


class StageTests(unittest.TestCase):
    def setUp(self):
        self.data = {'rule_id': 'synthetic', 'formalization': [{'id': 'r', 'statement_ids': ['s'],
            'support': 'state', 'temporal': None, 'reason': None, 'kind': 'obligation',
            'applicability': atom('vessel', 'size'), 'obligation': atom('vessel', 'clearance'),
            'exceptions': []}]}
        self.fields = {('vessel', k): {'class': 'Unit', 'variable': v, 'type': 'int',
                       'unit': 'metres', 'instances': ['u']} for k, v in [('size', 'x'), ('clearance', 'y')]}

    def test_cross_entity_same_class_is_rejected(self):
        self.data['formalization'][0]['obligation']['entity'] = 'other'
        self.fields[('other', 'clearance')] = self.fields.pop(('vessel', 'clearance'))
        definitions, assertions, witnesses, records = synthesize(self.data, self.fields)
        self.assertFalse(assertions)
        self.assertEqual(records[0]['status'], 'UNSUPPORTED_SEMANTICS')

    def test_different_instance_scopes_are_rejected(self):
        self.fields[('vessel', 'clearance')]['instances'] = ['v']
        self.assertFalse(synthesize(self.data, self.fields)[1])

    def test_handoff_and_preserved_artifacts(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            folder = Path(directory)
            model = folder / 'input.rebeca'
            model.write_text('reactiveclass Unit(2) { statevars { int x; int y; } Unit() {x=4;y=4;} } main { Unit u():(); }')
            extraction = folder / 'extraction.json'
            extraction.write_text('{}')
            artifact = handoff(self.data, self.fields, [], model, extraction)
            inventory = extract(model.read_text(), str(model))
            selected = validate_handoff(artifact, inventory, model, extraction)
            prop = folder / 'input.property'
            prop.write_text('property { define { old = (u.x > 0); } Assertion { oldCheck: old; } }')
            output = folder / 'output'
            output.mkdir()
            result = write_synthesis(self.data, selected, model, output, prop)
            self.assertEqual(model.read_bytes(), (output / 'model.rebeca').read_bytes())
            self.assertIn('oldCheck: old;', (output / 'model.property').read_text())
            self.assertEqual(result['verification'], 'NOT_RUN')
            saved = (output / 'model.property').read_bytes()
            with self.assertRaises(ValueError):
                write_synthesis(self.data, selected, model, output, prop)
            self.assertEqual(saved, (output / 'model.property').read_bytes())
            changed = copy.deepcopy(artifact)
            changed['bindings'][0]['field']['variable'] = 'invented'
            with self.assertRaises(ValueError):
                validate_handoff(changed, inventory, model, extraction)
            extraction.write_text('{"changed":true}')
            with self.assertRaises(ValueError):
                validate_handoff(artifact, inventory, model, extraction)


if __name__ == '__main__':
    unittest.main()
