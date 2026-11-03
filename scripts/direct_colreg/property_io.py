"""Insert generated state properties while retaining existing source sections."""
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'skills/rebeca_tooling/scripts'))
from extract_rebeca import mask, blocks


def merge(original, definitions, assertions):
    clean = mask(original)
    if re.search(r'\bG_\w+', clean):
        raise ValueError('Generated G_ namespace already exists')
    outer = list(blocks(clean))
    if len(outer) != 1 or clean[:outer[0][1]].strip() != 'property':
        raise ValueError('Expected one property block')
    _, left, right = outer[0]
    body = clean[left+1:right]
    edits, locations, seen = [], {}, set()
    for start, opening, closing in blocks(body):
        name = body[start:opening].strip()
        locations[name] = left+1+start
        if name in ('define', 'Assertion'):
            if name in seen:
                raise ValueError('Duplicate property section')
            seen.add(name)
            values = definitions if name == 'define' else assertions
            edits.append((left+1+closing, '\n    ' + '\n    '.join(values) + '\n'))
    for name, values in (('define', definitions), ('Assertion', assertions)):
        if name not in seen:
            offset = min(locations.values(), default=right) if name == 'define' else min(
                (v for k, v in locations.items() if k in ('TCTL', 'LTL')), default=right)
            edits.append((offset, '\n  ' + name + ' {\n    ' + '\n    '.join(values) + '\n  }\n'))
    grouped = {}
    for offset, value in edits:
        grouped[offset] = grouped.get(offset, '') + value
    for offset, value in sorted(grouped.items(), reverse=True):
        original = original[:offset] + value + original[offset:]
    return original
