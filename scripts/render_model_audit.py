"""Render all field evidence and uncertainties from a v2 semantic catalog."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text())
    lines = ['# Rebeca source semantic audit', '',
        'Method: bounded lexical def/use analysis plus explicitly attributed analyst annotations.',
        'No regulation, expected property, or historical mapping is an audit input.',
        'All entries remain not human reviewed. Read/write sites are not proofs of reachability.', '']
    def ref(e):
        path = Path(e['path']).resolve()
        return f"[{path.name}:{e['line_start']}](<{path}:{e['line_start']}>)"
    for model in catalog['models']:
        lines += ['## ' + model['source'], '', 'SHA-256: `' + model['model_sha256'] + '`', '']
        for field in model['fields']:
            lines += ['### ' + field['class'] + '.' + field['variable'], '',
                '- Declared type: `' + field['type'] + '`',
                '- Ownership: ' + ', '.join(i['name'] + '(' + i['constructor_arguments'] + ')' for i in field['instances']),
                '- State category: ' + field['kind'],
                '- Meaning: ' + (field['description'] or 'Unestablished beyond structural use.'),
                '- Meaning support: ' + field['meaning_status'],
                '- Unit: ' + str(field['unit']) + '; status: ' + field['unit_status'],
                '- Formalization suitability: ' + field['suitability'],
                '- Review status: ' + field['review_status'],
                '- Declaration evidence: ' + ', '.join(ref(e) for e in field['declarations'])]
            for label, key in [('Writes/initialization', 'writes'), ('Reads', 'reads'), ('Transitions', 'transitions')]:
                lines += ['', label + ':', '']
                entries = field[key]
                lines += ['- ' + e['member'] + ': ' + ref(e['evidence']) + ' — `' + e['evidence']['quote'].strip().replace('`', "'") + '`' for e in entries] if entries else ['- None identified.']
            lines += ['', 'Semantic documentation evidence:', '']
            lines += ['- ' + ref(e) + ' — `' + e['quote'].strip().replace('`', "'") + '`' for e in field['semantic_evidence']] or ['- None; no semantic equivalence asserted.']
            lines += ['', 'Uncertainty/contradictions:', '']
            lines += ['- ' + item for item in field['contradictions'] + field['limitations']]
            if field['shadowed_occurrences']:
                lines += ['- Possible local shadowing sites are retained in the machine-readable catalog and excluded from attributed state operations.']
            lines += ['']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text('\n'.join(lines), encoding='utf-8')


if __name__ == '__main__':
    main()
