"""Generic bounded RMC adapter; decisions depend on fresh structured XML."""
import json
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'skills/rebeca_tooling/scripts'))
from rmc_result_parser import parse_rmc_result_file


def host_path(path, wsl):
    value = str(Path(path).resolve())
    if wsl and re.match(r'^[A-Za-z]:', value):
        return '/mnt/' + value[0].lower() + value[2:].replace('\\', '/')
    return value


def verify(model, prop, output, config):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    started = time.perf_counter()
    wsl = config.get('wsl')
    command = [sys.executable, host_path(ROOT / 'skills/rebeca_tooling/scripts/run_rmc.py', wsl),
        '--jar', host_path(config['jar'], wsl), '--model', host_path(model, wsl),
        '--property', host_path(prop, wsl), '--output-dir', host_path(output, wsl),
        '--timeout-seconds', str(config['timeout']), '--run-model-outcome',
        '--model-out-timeout-seconds', str(config['timeout']),
        '--output-file', host_path(output / 'details.json', wsl)]
    if wsl:
        command[0] = 'python3'
        command = ['wsl', '-d', wsl, '--exec'] + command
    record = {'status': 'UNKNOWN', 'command': command, 'counterexample_path': None,
              'result_path': str(output / 'result.xml'), 'details_path': str(output / 'details.json')}
    try:
        process = subprocess.run(command, capture_output=True, timeout=config['timeout']*3+15)
        (output / 'stdout.log').write_bytes(process.stdout)
        (output / 'stderr.log').write_bytes(process.stderr)
        details = json.loads((output / 'details.json').read_text()) if (output / 'details.json').is_file() else {}
        record['execution_exit_code'] = process.returncode
        record['phase'] = details.get('rmc_outcome')
        if details.get('verification_outcome') == 'timeout':
            record['status'] = 'TIMEOUT'
        elif details.get('rmc_outcome') in ('parse_failed', 'generation_failed', 'cpp_compile_failed'):
            record['status'] = 'COMPILATION_ERROR'
        elif details.get('cpp_compile_ok') and details.get('model_out', {}).get('executed'):
            parsed = parse_rmc_result_file(str(output / 'result.xml'), strict=True)
            record['raw_verdicts'] = parsed.get('raw_verdicts', [])
            record['status'] = {'satisfied': 'VERIFIED', 'cex': 'VIOLATED'}.get(parsed['outcome'], 'UNKNOWN')
            record['counterexample_path'] = parsed.get('counterexample_path')
    except subprocess.TimeoutExpired:
        record['status'] = 'TIMEOUT'
    except (OSError, ValueError) as error:
        record['error'] = str(error)
    record['elapsed_seconds'] = time.perf_counter() - started
    (output / 'execution.json').write_text(json.dumps(record, indent=2))
    return record
