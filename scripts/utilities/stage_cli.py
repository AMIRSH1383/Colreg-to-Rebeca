"""Opt-in --rule publication adapter for the existing stage CLIs.

The computational/semantic implementations remain in their original functions.
Only destinations, lifecycle metadata and hash-based freshness are managed here.
"""
from typing import Any, Callable
import contextlib
import io
import json
from pathlib import Path
import sys

from scripts.utilities.experiment_store import Experiment, ROOT


def managed_main(
    stage: str, argv: list[str] | None, legacy_main: Callable[[list[str]], int | None],
    *, expected_inputs: dict[str, str | None] | None = None,
    contract_inputs: tuple[Path, ...] = (),
    validate_outputs: Callable[[Path], None] | None = None,
) -> int | None:
    args = list(sys.argv[1:] if argv is None else argv)
    if '--help' in args or '-h' in args:
        print('Managed mode: --rule RULE [--experiments-dir PATH]. Outputs update one permanent rule directory; failed attempts preserve last success.')
        for flag in ('--rule', '--experiments-dir'):
            if flag in args:
                index = args.index(flag)
                del args[index:index + 2]
        return legacy_main(args)
    if '--rule' not in args:
        return legacy_main(args)

    def take(flag: str, default: str | None = None) -> str | None:
        if flag not in args:
            return default
        index = args.index(flag)
        if index + 1 >= len(args):
            raise ValueError(f'Missing argument for {flag}')
        value = args[index + 1]
        del args[index:index + 2]
        return value

    try:
        rule = take('--rule')
        base = take('--experiments-dir', str(ROOT / 'experiments'))
        assert rule is not None and base is not None
        experiment = Experiment(rule, base)
        folder = experiment.folder
        def supplied(flag: str, default: Path) -> Path:
            if flag not in args:
                args.extend([flag, str(default)])
            return Path(args[args.index(flag) + 1])
        if any(flag in args for flag in ['--output', '--output-dir', '--output-file', '--base-dir']):
            raise ValueError('--rule owns output destinations; use explicit output mode for scratch work')
        if stage == 'rebeca_extraction':
            inputs = [supplied('--input', ROOT / 'inputs/rebeca/original_model.rebeca')]
        elif stage == 'binding':
            inputs = [supplied('--colreg', folder / 'colreg_extraction.json'),
                      supplied('--rebeca', folder / 'rebeca_extraction.json')]
        elif stage == 'synthesis':
            inputs = [supplied('--colreg', folder / 'colreg_extraction.json'),
                      supplied('--binding', folder / 'semantic_binding.json'),
                      supplied('--rebeca', folder / 'rebeca_extraction.json'),
                      supplied('--model', ROOT / 'inputs/rebeca/original_model.rebeca')]
        elif stage == 'verification':
            inputs = [supplied('--model', folder / 'synthesis/model.rebeca'),
                      supplied('--property', folder / 'synthesis/model.property')]
            config = json.loads((ROOT / 'verification/rmc/configs/rmc_timing_fixed.json').read_text())
            inputs.append(supplied('--jar', ROOT / config['jar']))
            if '--rule-id' not in args:
                args += ['--rule-id', rule]
        else:
            raise ValueError('Unsupported CLI stage')
        inputs.extend(contract_inputs)
        transient: list[Path] = []
        if '--response' in args:
            response = Path(args[args.index('--response') + 1])
            inputs.append(response)
            if expected_inputs is not None:
                transient.append(response)
        with experiment.attempt(stage, inputs, provenance={'execution': 'existing_runner'}) as attempt:
            if expected_inputs is not None and any(
                attempt.inputs.get(key) != value for key, value in expected_inputs.items()
            ):
                raise ValueError('Stage inputs changed before the runner started')
            work = attempt.workspace
            if stage == 'rebeca_extraction':
                args += ['--output', str(work / 'rebeca_extraction.json')]
            elif stage == 'binding':
                args += ['--output', str(work / 'semantic_binding.json')]
            else:
                args += ['--output-dir', str(work / 'result')]
                if stage == 'verification':
                    args += ['--base-dir', str(work / 'pipeline'), '--output-file', str(work / 'result/result.json')]
            captured, diagnostics = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(diagnostics):
                    code = legacy_main(args)
            finally:
                (work / 'runner.stdout.log').write_text(captured.getvalue())
                (work / 'runner.stderr.log').write_text(diagnostics.getvalue())
                print(diagnostics.getvalue(), end='', file=sys.stderr)
            if code not in (None, 0):
                raise ValueError(f'{stage} runner failed with exit {code}')
            if stage == 'synthesis' and '--prepare-only' in args:
                target = attempt.prepared()
                print(json.dumps({'status': 'prepared', 'request': str(target / 'result/request.json')}))
                return 0
            if validate_outputs is not None:
                validate_outputs(work)
            if stage == 'rebeca_extraction':
                files = {'rebeca_extraction.json': work / 'rebeca_extraction.json'}
            elif stage == 'binding':
                files = {p.name: p for p in work.glob('semantic_binding*.json')}
            elif stage == 'synthesis':
                files = {'synthesis/' + p.name: p for p in (work / 'result').iterdir()
                         if p.suffix in {'.json', '.rebeca', '.property', '.diff'}}
            else:
                result = json.loads((work / 'result/result.json').read_text())
                if result['verification_status'] not in ('satisfied', 'violated'):
                    raise ValueError('Verification did not produce a completed semantic result: ' + result['verification_status'])
                files = {'verification/result.json': work / 'result/result.json'}
                xml = work / 'result/rmc/model_result.xml'
                if xml.is_file() and xml.stat().st_size <= 1024 * 1024:
                    files['verification/model_result.xml'] = xml
            # Move logs/build products to ignored scratch; never publish them as research finals.
            retained = attempt.retain('latest')
            if stage == 'verification':
                # Relocate only filesystem paths in the existing gate payload.
                # Semantic verdicts and schemas are untouched.
                def relocate(value: Any) -> Any:
                    if isinstance(value, dict):
                        return {key: relocate(item) for key, item in value.items()}
                    if isinstance(value, list):
                        return [relocate(item) for item in value]
                    if isinstance(value, str) and value.startswith(str(work) + '/'):
                        return str(retained) + value[len(str(work)):]
                    return value
                result_path = work / 'result/result.json'
                result_path.write_text(json.dumps(relocate(result), indent=2) + '\n')
                (retained / 'result/result.json').write_bytes(result_path.read_bytes())
                assessment = work / 'assessment.md'
                assessment.write_text('Existing verification gate status: ' + result['verification_status']
                                      + '\n\nOptional diagnostics: ' + json.dumps(result['optional_checks'])
                                      + '\n\nConsult result XML for the specific checked property/failure. '
                                      'This record does not establish non-vacuity or regulatory compliance.\n')
                files['verification/assessment.md'] = assessment
            attempt.publish(files, transient_inputs=transient)
        print(json.dumps({'status': 'completed', 'rule': rule, 'stage': stage, 'directory': str(folder)}))
        return 0
    except (Exception, SystemExit) as exc:
        print(f'Managed {stage} failed: {exc}', file=sys.stderr)
        return 1
