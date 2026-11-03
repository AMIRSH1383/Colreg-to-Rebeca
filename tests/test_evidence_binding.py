"""Independent synthetic evidence tests; no regulatory answer fixtures."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from direct_colreg.model_evidence import audit, apply_annotations, citation, validate_field
from direct_colreg.evidence_binding import bind_with_evidence, evidence_id


def fixture(directory, renamed=False, ambiguous=False):
    q = 'renamed_span' if renamed else 'q'
    second = 'Configured hull length in metres' if ambiguous else 'Configured beam width in metres'
    source = ('reactiveclass Vessel(10) {\n statevars {\n'
        f' int {q}; // Configured hull length in metres\n'
        f' int r; // {second}\n'
        ' }\n Vessel() { '+q+'=9; r=5; self.tick(); }\n msgsrv tick() {self.tick();}\n}\nmain {Vessel v():();}\n')
    path = Path(directory) / 'model.rebeca'
    path.write_text(source)
    result = audit(path)
    annotations = []
    for field, line in zip(result['fields'], [3, 4]):
        description = 'Configured hull length' if field['variable'] == q or ambiguous else 'Configured beam width'
        annotations.append({'model_sha256': result['model_sha256'], 'class': 'Vessel',
            'variable': field['variable'], 'description': description, 'unit': 'metres',
            'unit_status': 'explicit_documentation', 'meaning_status': 'source_supported_scoped',
            'suitability': 'configured_attribute_check', 'contradictions': [],
            'evidence': [citation(path, source, line)], 'provenance': 'Synthetic source documentation; no human review'})
    return apply_annotations(result, annotations)


def semantic_input(concept='hull_length', unit='metres'):
    atom = {'op': 'compare', 'entity': 'vessel', 'concept': concept, 'operator': '>=',
            'value': 1, 'unit': unit, 'args': []}
    return {'formalization': [{'support': 'state', 'temporal': None,
        'applicability': {'op': 'true'}, 'obligation': atom, 'exceptions': []}],
        'extraction': {'entities': [{'id': 'vessel', 'name': 'vessel'}],
                       'statements': [{'concept': concept, 'source_text': 'Synthetic concept under test'}]}}


def inventory(model):
    return {'reactive_classes': [{'name': 'Vessel', 'state_variables': [
        {'name': f['variable'], 'type': f['type']} for f in model['fields']]}],
        'instances': [{'class': 'Vessel', 'name': 'v'}]}


class Selection:
    """Unit-test response only. Real-inference tests are separate."""
    def __init__(self, field=None, confidence=0.95, bad_citations=False):
        self.field, self.confidence, self.bad_citations = field, confidence, bad_citations

    def request(self, prompt, schema, directory, purpose):
        requests = json.loads(prompt.split('\n', 1)[1])
        choices = []
        for request in requests:
            selected = next((c for c in request['candidates'] if c['variable'] == self.field), None)
            citations = list(set(selected['declaration_ids'] + selected['documentary_ids'])) if selected else []
            if self.bad_citations:
                citations = ['invented']
            choices.append({'key': request['key'], 'selected': selected['id'] if selected else None,
                            'evidence': 'Synthetic documented attribute evidence', 'confidence': self.confidence,
                            'citations': citations})
        return {'selections': choices}


class EvidenceTests(unittest.TestCase):
    def run_binding(self, model, provider, data=None):
        return bind_with_evidence(data or semantic_input(), inventory(model),
            {'version': 2, 'models': [model]}, model['model_sha256'], provider, None)

    def test_positive_documented_meaning_with_nonsemantic_name(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            model = fixture(directory)
            selected, records = self.run_binding(model, Selection('q'))
            self.assertEqual(selected[('vessel', 'hull_length')]['variable'], 'q')
            self.assertTrue(records[0]['citations'])
            self.assertEqual(records[0]['review_status'], 'not_human_reviewed')

    def test_renamed_variable_uses_source_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            model = fixture(directory, renamed=True)
            selected, _ = self.run_binding(model, Selection('renamed_span'))
            self.assertEqual(selected[('vessel', 'hull_length')]['variable'], 'renamed_span')

    def test_ambiguous_duplicate_descriptions_abstain_even_if_provider_selects(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            model = fixture(directory, ambiguous=True)
            selected, records = self.run_binding(model, Selection('q'))
            self.assertFalse(selected)
            self.assertIn('indistinguishable', records[0]['evidence'])

    def test_negative_wrong_unit_and_missing_meaning(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            model = fixture(directory)
            selected, _ = self.run_binding(model, Selection('q'), semantic_input(unit='nautical_miles'))
            self.assertFalse(selected)
            for f in model['fields']:
                f['meaning_status'] = 'unestablished'
            selected, _ = self.run_binding(model, Selection('q'))
            self.assertFalse(selected)

    def test_low_confidence_not_weakened(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            selected, records = self.run_binding(fixture(directory), Selection('q', confidence=0.89))
            self.assertFalse(selected)
            self.assertIn('0.9', records[0]['evidence'])

    def test_fabricated_citations_rejected(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            selected, records = self.run_binding(fixture(directory), Selection('q', bad_citations=True))
            self.assertFalse(selected)

    def test_source_tampering_invalidates_evidence(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            model = fixture(directory)
            Path(model['source']).write_text('changed source')
            with self.assertRaises(ValueError):
                self.run_binding(model, Selection('q'))

    def test_audit_classifies_initialization_and_reads(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            model = fixture(directory)
            field = model['fields'][0]
            self.assertEqual(field['kind'], 'constructor_configured_attribute')
            self.assertEqual(len(field['writes']), 1)
            self.assertFalse(field['reads'])
            self.assertFalse(field['transitions'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
