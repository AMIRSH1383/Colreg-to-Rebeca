"""Exact, source-anchored byte patches; no filesystem writes or fuzzy matching."""
from hashlib import sha256


def digest(data):
    return sha256(data).hexdigest()


def apply_patches(source, source_sha256, sections, patches):
    if digest(source) != source_sha256:
        raise ValueError('Stale source hash')
    anchors = {s['id']: s for s in sections}
    if len(anchors) != len(sections):
        raise ValueError('Duplicate section ID')
    edits = []
    for patch in patches:
        if patch['section_id'] not in anchors:
            raise ValueError('Unauthorized section')
        section = anchors[patch['section_id']]
        start, end = section['start'], section['end']
        if not 0 <= start < end <= len(source):
            raise ValueError('Invalid source range')
        fragment = source[start:end]
        if digest(fragment) != section['sha256'] or patch['section_sha256'] != section['sha256']:
            raise ValueError('Stale section hash')
        old = patch['old'].encode('utf-8')
        if not old or fragment.count(old) != 1:
            raise ValueError('Missing or ambiguous exact anchor')
        offset = start + fragment.index(old)
        edits.append((offset, offset + len(old), patch['new'].encode('utf-8')))
    edits.sort()
    if any(a[1] > b[0] for a, b in zip(edits, edits[1:])):
        raise ValueError('Overlapping patches')
    result = source
    for start, end, replacement in reversed(edits):
        result = result[:start] + replacement + result[end:]
    return result
