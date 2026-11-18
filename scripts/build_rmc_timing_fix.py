#!/usr/bin/env python3
"""Build a pinned RMC 2.14 derivative without replacing the upstream JAR.

Requires Python 3.10+ and JDK 11+ source-file launching. Uses only the Javassist
already bundled in the pinned upstream JAR; no downloads or external packages.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = '2.14-colreg-timing.1'
UPSTREAM_SHA256 = 'a39112046d99e0895cf47f890242ace21db896e609f7eef86751a0d416d477f5'
LISTENER = 'org/rebecalang/compiler/modelcompiler/timedrebeca/compiler/TimedRebecaListener.class'
METADATA = 'META-INF/colreg-rmc-build.json'
PATCH_SOURCE = ROOT / 'tools/rmc-timing-fix/BuildTimingListener.java'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def repack(upstream, output, listener_bytes, metadata):
    """Preserve entry order/metadata and all payloads except the listener.

    Store entries uncompressed so the archive bytes do not depend on the host
    zlib version. Fixed metadata avoids timestamps or absolute paths in the JAR.
    """
    with zipfile.ZipFile(upstream) as source, zipfile.ZipFile(output, 'x') as target:
        if LISTENER not in source.namelist() or METADATA in source.namelist():
            raise ValueError('Unexpected upstream archive layout')
        for info in source.infolist():
            if info.filename.startswith('META-INF/') and info.filename.endswith(('.SF', '.RSA', '.DSA', '.EC')):
                raise ValueError('Refusing to invalidate a signed archive')
            data = listener_bytes if info.filename == LISTENER else source.read(info)
            info.compress_type = zipfile.ZIP_STORED
            target.writestr(info, data)
        info = zipfile.ZipInfo(METADATA, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        target.writestr(info, json.dumps(metadata, sort_keys=True, indent=2).encode() + b'\n')


def build(upstream, output_dir):
    upstream = Path(upstream).resolve()
    output_dir = Path(output_dir).resolve()
    if sha256(upstream) != UPSTREAM_SHA256:
        raise ValueError('Upstream JAR checksum mismatch; refusing unreviewed input')
    output_dir.mkdir(parents=True, exist_ok=False)
    metadata = {'version': VERSION, 'upstream_sha256': UPSTREAM_SHA256,
                'patch_source_sha256': sha256(PATCH_SOURCE),
                'patch': 'Add exitAfter/exitDeadline callbacks: ctx.e = ctx.expression().e'}
    with tempfile.TemporaryDirectory(prefix='rmc-listener-') as temp:
        command = ['java', '--class-path', str(upstream), str(PATCH_SOURCE), str(upstream), temp]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (output_dir / 'build.stdout.log').write_text(result.stdout)
        (output_dir / 'build.stderr.log').write_text(result.stderr)
        result.check_returncode()
        listener_bytes = (Path(temp) / LISTENER).read_bytes()
        metadata['listener_sha256'] = hashlib.sha256(listener_bytes).hexdigest()
        jar = output_dir / f'rmc-{VERSION}.jar'
        repack(upstream, jar, listener_bytes, metadata)
    assert sha256(upstream) == UPSTREAM_SHA256, 'Upstream JAR changed'
    manifest = {**metadata, 'jar': jar.name, 'jar_sha256': sha256(jar),
                'java_version': subprocess.run(['java', '-version'], capture_output=True, text=True, check=True).stderr.strip(),
                'build_method': 'JDK source launcher + bundled Javassist; deterministic ZIP_STORED repack'}
    (output_dir / 'build.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (output_dir / 'SHA256SUMS').write_text(f"{manifest['jar_sha256']}  {jar.name}\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-jar', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build(args.input_jar, args.output_dir), indent=2))


if __name__ == '__main__':
    main()
