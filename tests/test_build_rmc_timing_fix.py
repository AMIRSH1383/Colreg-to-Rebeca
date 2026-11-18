"""Archive/provenance safeguards; actual Java builds are tested separately."""
import hashlib
from pathlib import Path
import zipfile

import pytest

from scripts import build_rmc_timing_fix as builder


def test_repack_changes_only_listener_and_adds_versioned_provenance(tmp_path):
    upstream = tmp_path / 'upstream.jar'
    with zipfile.ZipFile(upstream, 'w') as archive:
        archive.writestr(builder.LISTENER, b'original listener')
        archive.writestr('META-INF/MANIFEST.MF', b'Main-Class: unchanged.Main\n')
        archive.writestr('LICENSE', b'preserved attribution')
        archive.writestr('other.class', b'unchanged bytecode')
    original = upstream.read_bytes()
    metadata = {'version': builder.VERSION, 'upstream_sha256': hashlib.sha256(original).hexdigest()}
    first, second = tmp_path / 'first.jar', tmp_path / 'second.jar'
    builder.repack(upstream, first, b'patched listener', metadata)
    builder.repack(upstream, second, b'patched listener', metadata)
    assert first.read_bytes() == second.read_bytes()
    assert upstream.read_bytes() == original
    with zipfile.ZipFile(upstream) as before, zipfile.ZipFile(first) as after:
        assert [n for n in before.namelist() if before.read(n) != after.read(n)] == [builder.LISTENER]
        assert set(after.namelist()) - set(before.namelist()) == {builder.METADATA}
        assert after.testzip() is None


def test_unpinned_upstream_rejected_before_output_creation(tmp_path):
    upstream = tmp_path / 'unknown.jar'
    upstream.write_bytes(b'unreviewed input')
    output = tmp_path / 'build'
    with pytest.raises(ValueError, match='checksum'):
        builder.build(upstream, output)
    assert not output.exists()
    assert upstream.read_bytes() == b'unreviewed input'


def test_existing_build_is_never_overwritten(tmp_path, monkeypatch):
    upstream = tmp_path / 'upstream.jar'
    upstream.write_bytes(b'test fixture')
    monkeypatch.setattr(builder, 'UPSTREAM_SHA256', builder.sha256(upstream))
    monkeypatch.setattr(builder.subprocess, 'run', lambda *a, **kw: pytest.fail('Must not rebuild'))
    output = tmp_path / 'existing'
    output.mkdir()
    evidence = output / 'research'
    evidence.write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        builder.build(upstream, output)
    assert evidence.read_bytes() == b'keep'


def test_signed_archive_is_not_silently_invalidated(tmp_path):
    upstream = tmp_path / 'signed.jar'
    with zipfile.ZipFile(upstream, 'w') as archive:
        archive.writestr(builder.LISTENER, b'old')
        archive.writestr('META-INF/SIGNATURE.SF', b'signature')
    with pytest.raises(ValueError, match='signed'):
        builder.repack(upstream, tmp_path / 'out.jar', b'new', {})
