"""Per-rule artifact publication and freshness; payload contracts are untouched.

Build outside experiments, publish only validated small artifacts, and keep the
last successful payload when an attempt fails. run.json is the authority for
freshness, including hashes of both inputs and outputs. Consumers must inspect
it rather than interpreting mere file existence as success.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterable, Iterator
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[2]
STAGES = ('colreg_extraction', 'rebeca_extraction', 'binding', 'synthesis', 'verification')
DEPENDENCIES = {'colreg_extraction': (), 'rebeca_extraction': (),
                'binding': ('colreg_extraction', 'rebeca_extraction'),
                'synthesis': ('colreg_extraction', 'rebeca_extraction', 'binding'),
                'verification': ('synthesis',)}
REQUIRED = {'colreg_extraction': {'colreg_extraction.json'},
            'rebeca_extraction': {'rebeca_extraction.json'}, 'binding': {'semantic_binding.json'},
            'synthesis': {'synthesis/model.rebeca', 'synthesis/report.json'},
            'verification': {'verification/result.json'}}


def digest(path: str | Path) -> str | None:
    path = Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def path_key(path: str | Path) -> str:
    path = Path(path).resolve()
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def snapshot(paths: Iterable[str | Path]) -> dict[str, str | None]:
    return {path_key(p): digest(p) for p in paths}


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.publish-', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


class Experiment:
    def __init__(self, rule: str, base: str | Path | None = None, work_root: str | Path | None = None) -> None:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', rule):
            raise ValueError('Invalid rule directory identifier')
        self.rule = rule
        self.folder = (Path(base) if base is not None else ROOT / 'experiments') / rule
        self.work_root = (Path(work_root) if work_root is not None else self.folder.parent.parent / 'output/work') / rule
        self.manifest = self.folder / 'run.json'

    def inspect(self) -> dict[str, Any]:
        data: dict[str, Any] = json.loads(self.manifest.read_text()) if self.manifest.exists() else {
            'schema_version': '1.0', 'rule': self.rule, 'stages': {}}
        for stage in STAGES:
            record = data['stages'].setdefault(stage, {})
            success = record.get('last_success')
            record['status'] = 'missing'
            if not success:
                continue
            current = all(digest(ROOT / p) == sha and sha is not None
                          for p, sha in success['inputs'].items())
            current &= all(digest(self.folder / p) == sha for p, sha in success['artifacts'].items())
            current &= all(data['stages'].get(dep, {}).get('status') == 'current'
                           for dep in DEPENDENCIES[stage])
            record['status'] = 'current' if current else 'stale'
        return data

    @contextmanager
    def attempt(self, stage: str, inputs: Iterable[str | Path], *, provenance: dict[str, Any] | None = None) -> Iterator[Attempt]:
        if stage not in STAGES:
            raise ValueError('Unknown stage')
        self.folder.mkdir(parents=True, exist_ok=True)
        self.work_root.mkdir(parents=True, exist_ok=True)
        lock = self.folder / '.publish.lock'
        # A rule-wide exclusive lock prevents concurrent stages losing metadata.
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with tempfile.TemporaryDirectory(prefix='stage-', dir=self.work_root) as temp:
                attempt = Attempt(self, stage, list(map(Path, inputs)), Path(temp), provenance or {})
                data = self.inspect()
                data['stages'][stage]['last_attempt'] = {'status': 'running', 'inputs': attempt.inputs,
                                                       'started_at': datetime.now(timezone.utc).isoformat()}
                atomic_json(self.manifest, data)
                try:
                    if any(sha is None for sha in attempt.inputs.values()):
                        raise ValueError('Required stage input is missing')
                    for dep in DEPENDENCIES[stage]:
                        if data['stages'][dep]['status'] != 'current':
                            raise ValueError(f'Required upstream stage is not current: {dep}')
                    yield attempt
                    if not attempt.finished:
                        raise ValueError('Attempt did not publish a result')
                except BaseException as exc:
                    data = self.inspect()
                    data['stages'][stage]['last_attempt'].update(status='failed', error=str(exc))
                    atomic_json(self.manifest, data)
                    try:
                        attempt.retain('failed')
                    except Exception as diagnostic_error:
                        data['stages'][stage]['last_attempt']['diagnostics_error'] = str(diagnostic_error)
                        atomic_json(self.manifest, data)
                    raise
        finally:
            lock.unlink(missing_ok=True)


class Attempt:
    def __init__(self, experiment: Experiment, stage: str, paths: list[Path], workspace: Path, provenance: dict[str, Any]) -> None:
        self.experiment, self.stage, self.paths = experiment, stage, paths
        self.workspace, self.provenance = workspace, provenance
        self.inputs, self.finished = snapshot(paths), False

    def retain(self, name: str) -> Path:
        target = self.experiment.work_root / self.stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(self.workspace, target)
        return target

    def prepared(self) -> Path:
        target = self.retain('prepared')
        data = self.experiment.inspect()
        data['stages'][self.stage]['last_attempt'].update(status='prepared', scratch=str(target))
        atomic_json(self.experiment.manifest, data)
        self.finished = True
        return target

    def publish(self, files: dict[str, Path]) -> None:
        """files maps final relative paths to already validated source files."""
        if snapshot(self.paths) != self.inputs:
            raise ValueError('Inputs changed during stage execution')
        if not REQUIRED[self.stage] <= set(files):
            raise ValueError('Incomplete stage artifact set')
        folder = self.experiment.folder
        data = self.experiment.inspect()
        old = data['stages'][self.stage].get('last_success', {}).get('artifacts', {})
        for name, source in files.items():
            path = Path(name)
            allowed = name in REQUIRED[self.stage]
            allowed |= name.startswith({'colreg_extraction': 'extraction/', 'binding': 'semantic_binding.', 'synthesis': 'synthesis/',
                                       'verification': 'verification/'}.get(self.stage, '\0'))
            if (not allowed or not (folder / path).resolve().is_relative_to(folder.resolve())
                    or path.is_absolute() or path.suffix in {'.cpp', '.h', '.jar', '.out', '.pyc', '.exe', '.class', '.o', '.so', '.dll'}
                    or 'statespace' in path.name.lower() or not Path(source).is_file()):
                raise ValueError(f'Unauthorized experiment artifact: {name}')
        # Save small previous payloads for rollback. run.json remains marked
        # running until all files and hashes are published; interrupted updates
        # are detected as stale on the next inspect, never presented as valid.
        affected = set(old) | set(files)
        previous = {name: (folder / name).read_bytes() if (folder / name).is_file() else None
                    for name in affected}
        before_manifest = self.experiment.manifest.read_bytes()
        try:
            for name in affected:
                target = folder / name
                if name in files:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    fd, temporary = tempfile.mkstemp(dir=target.parent, prefix='.publish-')
                    os.close(fd)
                    try:
                        shutil.copyfile(files[name], temporary)
                        os.replace(temporary, target)
                    finally:
                        Path(temporary).unlink(missing_ok=True)
                else:
                    target.unlink(missing_ok=True)
            data['stages'][self.stage]['last_success'] = {
                'inputs': self.inputs, 'artifacts': {name: digest(folder / name) for name in files},
                'provenance': self.provenance}
            data['stages'][self.stage]['last_attempt'].update(status='completed')
            atomic_json(self.experiment.manifest, data)
            atomic_json(self.experiment.manifest, self.experiment.inspect())
        except BaseException:
            for name, content in previous.items():
                target = folder / name
                if content is None:
                    target.unlink(missing_ok=True)
                else:
                    target.write_bytes(content)
            self.experiment.manifest.write_bytes(before_manifest)
            raise
        self.finished = True
