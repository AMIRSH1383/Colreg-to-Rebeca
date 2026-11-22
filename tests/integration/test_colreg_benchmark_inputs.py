"""Check benchmark provenance, model references, and default input resolution."""

from hashlib import sha256
import json
import re

import pytest

from scripts.coordinator.pipeline import rule_inputs
from scripts.extraction.rebeca_extractor import parse_model
from scripts.utilities.experiment_store import ROOT


COLREG = ROOT / 'inputs/colreg'
MODEL = ROOT / 'inputs/rebeca/original_model.rebeca'
MANIFEST = json.loads((COLREG / 'source_manifest.json').read_text(encoding='utf-8'))
FILES = MANIFEST['files']


@pytest.mark.parametrize('filename', FILES)
def test_benchmark_default_input(filename):
    rule_id = FILES[filename]['rule_id']
    assert re.fullmatch(r'Rule[1-9][0-9]*[a-z]*', rule_id)
    assert filename == f'{rule_id}.txt'
    agent_id = rule_id.replace('Rule', 'Rule-', 1)
    expected = (rule_id, agent_id, COLREG / filename, MODEL)
    assert rule_inputs(rule_id, None, None) == expected
    assert rule_inputs(agent_id, None, None) == expected


def test_benchmark_text_matches_manifest_without_overlap():
    baselines = [path.read_text(encoding='utf-8') for path in COLREG.glob('*_baseline_colreg.txt')]
    seen_cells = set()
    seen_passages = set()
    for filename, entry in FILES.items():
        payload = (COLREG / filename).read_bytes()
        assert sha256(payload).hexdigest() == entry['text_sha256']
        passages = payload.decode(MANIFEST['text_encoding']).split(MANIFEST['cell_separator'])
        sources = entry['sources']
        assert len(passages) == len(sources)
        assert any(source['role'] == 'target' for source in sources)
        for source, passage in zip(sources, passages):
            assert source['cell'] not in seen_cells
            assert passage and passage not in seen_passages
            assert all(passage not in baseline for baseline in baselines)
            seen_cells.add(source['cell'])
            seen_passages.add(passage)


def test_benchmark_references_declared_model_state():
    extraction = parse_model(MODEL.read_text(encoding='utf-8'), str(MODEL))
    variables = {
        f"{reactor['name']}.{variable['name']}"
        for reactor in extraction['reactive_classes']
        for variable in reactor['state_variables']
    }
    for entry in FILES.values():
        assert set(entry['relevant_state_variables']) <= variables
