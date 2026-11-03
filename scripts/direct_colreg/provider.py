"""Real, bounded Codex CLI inference using existing authentication.

No mock/replay extraction backend is provided. Each request runs in an empty
directory, with no examples, model files or evaluator data attached.
"""
import json
import subprocess
import time
from pathlib import Path


class ProviderError(RuntimeError):
    pass


class CodexProvider:
    def __init__(self, model, timeout=180, executable='codex', prices=None):
        self.model, self.timeout, self.executable = model, timeout, executable
        self.prices = prices
        self.calls = []

    def request(self, prompt, schema, directory, purpose):
        directory = Path(directory).resolve()
        directory.mkdir(parents=True, exist_ok=False)
        schema_path, output = directory / 'schema.json', directory / 'response.json'
        # Transport schema omits constraints unsupported by strict structured
        # outputs; the full original schema is still validated locally.
        def transport(value):
            if isinstance(value, dict):
                result = {k: transport(v) for k, v in value.items() if k not in ('uniqueItems', '$schema')}
                if 'const' in result:
                    constant = result.pop('const')
                    result['enum'] = [constant]
                    result['type'] = ('boolean' if type(constant) is bool else
                                      'integer' if type(constant) is int else
                                      'number' if type(constant) is float else 'string')
                return result
            if isinstance(value, list):
                return [transport(v) for v in value]
            return value
        schema_path.write_text(json.dumps(transport(schema)), encoding='utf-8')
        (directory / 'prompt.txt').write_text(prompt, encoding='utf-8')
        isolated = directory / 'empty-context'
        isolated.mkdir()
        command = [self.executable, 'exec', '--ephemeral', '--ignore-user-config',
                   '--skip-git-repo-check', '--sandbox', 'read-only', '--json',
                   '--model', self.model, '--cd', str(isolated),
                   '--output-schema', str(schema_path), '--output-last-message', str(output), '-']
        record = {'purpose': purpose, 'provider': 'codex_cli', 'model': self.model,
                  'status': 'attempted', 'input_tokens': None, 'output_tokens': None,
                  'cached_input_tokens': None, 'estimated_cost': None,
                  'billing_note': 'CLI subscription billing not exposed; no cost assumed',
                  'provider_requests': None, 'tool_items': [], 'command': command}
        self.calls.append(record)
        started = time.perf_counter()
        try:
            process = subprocess.run(command, input=prompt, text=True, encoding='utf-8',
                                     errors='replace', capture_output=True, timeout=self.timeout)
            (directory / 'events.jsonl').write_text(process.stdout, encoding='utf-8')
            (directory / 'stderr.txt').write_text(process.stderr, encoding='utf-8')
            record['exit_code'] = process.returncode
            for line in process.stdout.splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('type') == 'turn.completed':
                    usage = event.get('usage', {})
                    for key in ('input_tokens', 'output_tokens', 'cached_input_tokens'):
                        record[key] = usage.get(key)
                item = event.get('item', {})
                if item.get('type') in ('command_execution', 'mcp_tool_call', 'web_search', 'file_change'):
                    record['tool_items'].append(item['type'])
            if record['tool_items']:
                raise ProviderError('Source-only inference contract violated: tool use recorded')
            if process.returncode or not output.is_file():
                raise ProviderError('Provider failed; see request stderr and events')
            data = json.loads(output.read_text(encoding='utf-8'))
            import jsonschema
            jsonschema.Draft202012Validator(schema).validate(data)
            record['status'] = 'completed'
            if self.prices and all(record[k] is not None for k in ('input_tokens', 'output_tokens', 'cached_input_tokens')):
                p = self.prices
                record['estimated_cost'] = ((record['input_tokens'] - record['cached_input_tokens']) * p['input_per_million']
                    + record['cached_input_tokens'] * p['cached_input_per_million']
                    + record['output_tokens'] * p['output_per_million']) / 1_000_000
                record['pricing_provenance'] = p['provenance']
            return data
        except subprocess.TimeoutExpired as error:
            record['status'] = 'timeout'
            raise ProviderError('Provider timeout; no extraction substituted') from error
        except Exception as error:
            record['status'] = 'failed'
            record['error'] = str(error)
            raise
        finally:
            record['latency_seconds'] = time.perf_counter() - started
            (directory / 'usage.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
