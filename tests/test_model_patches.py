import pytest
from scripts.apply_model_patches import apply_patches, digest


def setup(source=b'alpha\r\nbeta\r\n'):
    section = {'id': 's', 'start': 7, 'end': 11, 'sha256': digest(source[7:11])}
    patch = {'section_id': 's', 'section_sha256': section['sha256'], 'old': 'beta', 'new': 'B'}
    return source, section, patch


def test_empty_is_byte_identical():
    source, section, _ = setup()
    assert apply_patches(source, digest(source), [section], []) is source


def test_preserves_bytes_outside_patch():
    source, section, patch = setup()
    assert apply_patches(source, digest(source), [section], [patch]) == b'alpha\r\nB\r\n'


@pytest.mark.parametrize('fault', ['source', 'section', 'unauthorized', 'missing', 'overlap', 'empty', 'range'])
def test_rejects_bad_patch(fault):
    source, section, patch = setup()
    sha = digest(source)
    patches = [patch]
    if fault == 'source':
        sha = 'stale'
    elif fault == 'section':
        patch['section_sha256'] = 'stale'
    elif fault == 'unauthorized':
        patch['section_id'] = 'other'
    elif fault == 'missing':
        patch['old'] = 'elsewhere'
    elif fault == 'overlap':
        patches.append(dict(patch))
    elif fault == 'empty':
        patch['old'] = ''
    elif fault == 'range':
        section['end'] = len(source) + 1
    with pytest.raises(ValueError):
        apply_patches(source, sha, [section], patches)


def test_ambiguous_anchor():
    source = b'xx'
    section = {'id': 's', 'start': 0, 'end': 2, 'sha256': digest(source)}
    patch = {'section_id': 's', 'section_sha256': digest(source), 'old': 'x', 'new': 'y'}
    with pytest.raises(ValueError, match='ambiguous'):
        apply_patches(source, digest(source), [section], [patch])
