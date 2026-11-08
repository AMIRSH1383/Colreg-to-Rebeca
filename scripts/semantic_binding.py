#!/usr/bin/env python3
"""One-turn semantic binding over existing extraction JSONs (Codex CLI + jsonschema)."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def validate_inputs(colreg, rebeca):
    for value, filename in [(colreg, 'colreg-extractor.schema.json'),
                            (rebeca, 'rebeca_extraction.schema.json')]:
        Draft202012Validator(read_json(ROOT / 'schemas' / filename)).validate(value)
    if colreg['status'] != 'ok':
        raise ValueError('COLREG extraction is not a success artifact')
    entities = [e['id'] for e in colreg['extraction']['entities']]
    statements = colreg['extraction']['statements']
    ids = [s['id'] for s in statements]
    if len(set(entities)) != len(entities) or len(set(ids)) != len(ids):
        raise ValueError('Duplicate COLREG identifiers')
    for s in statements:
        if not s['subjects'] or not set(s['subjects']) <= set(entities):
            raise ValueError('Missing or unknown statement subjects')
        if not set(s['applies_when']) <= set(ids):
            raise ValueError('Dangling COLREG statement dependency')
    if any(not any(e in s['subjects'] for s in statements) for e in entities):
        raise ValueError('Entity has no statement evidence')
    classes = [c['name'] for c in rebeca['reactive_classes']]
    instances = [i['name'] for i in rebeca['instances']]
    if len(set(classes)) != len(classes) or len(set(instances)) != len(instances):
        raise ValueError('Duplicate model class or instance')
    if any(i['class'] not in classes for i in rebeca['instances']):
        raise ValueError('Instance references missing class')
    for c in rebeca['reactive_classes']:
        names = [v['name'] for v in c['state_variables']]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate state variable')


def compact_inventory(rebeca):
    # Preserve array indexes for JSON-pointer evidence; omit redundant method,
    # environment, source-path, line-count, and summary data, not candidate fields.
    return {
        'reactive_classes': [
            {'name': c['name'], 'state_variables': [
                {k: v[k] for k in ('name', 'type', 'array_dimensions',
                                   'constructor_initialization') if k in v}
                for v in c['state_variables']]}
            for c in rebeca['reactive_classes']],
        'instances': [{k: i[k] for k in ('name', 'class', 'known_rebec_bindings',
                                        'constructor_arguments')} for i in rebeca['instances']],
        'limitations': rebeca['limitations'],
    }


def expected_keys(colreg):
    expected = {}
    for entity in colreg['extraction']['entities']:
        name = entity['id']
        expected[('entity', name, None)] = {
            s['id'] for s in colreg['extraction']['statements'] if name in s['subjects']}
    for s in colreg['extraction']['statements']:
        for entity in s['subjects']:
            expected.setdefault(('concept', entity, s['concept']), set()).add(s['id'])
    return expected


def pointer_value(value, pointer):
    if not pointer.startswith('/'):
        raise ValueError('Evidence requires a non-root JSON pointer')
    for token in pointer[1:].split('/'):
        if re.search(r'~(?![01])', token):
            raise ValueError('Invalid JSON-pointer escape')
        token = token.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', token):
                raise ValueError('Invalid JSON-pointer array index')
            value = value[int(token)]
        else:
            value = value[token]
    return value


def normalized(value):
    return value.replace('_', '').casefold()


def validate_result(result, colreg, rebeca, schema):
    Draft202012Validator(schema).validate(result)
    if result['rule_id'] != colreg['rule_id']:
        raise ValueError('Rule identifier changed')
    expected = expected_keys(colreg)
    seen = set()
    classes = {c['name']: (index, c) for index, c in enumerate(rebeca['reactive_classes'])}
    owners = {i['name']: i['class'] for i in rebeca['instances']}
    entity_targets = {b['entity']: b['target'] for b in result['bindings'] if b['kind'] == 'entity'}
    sent_rebeca = compact_inventory(rebeca)
    for item in result['bindings'] + result['unresolved_concepts']:
        key = (item['kind'], item['entity'], item['concept'])
        if key not in expected or key in seen or set(item['statement_ids']) != expected[key]:
            raise ValueError('Duplicate, unknown, or incompletely covered concept/entity')
        seen.add(key)
    if seen != set(expected):
        raise ValueError('Some participants or concepts were omitted')
    for b in result['bindings']:
        target = b['target']
        if target['class'] not in classes:
            raise ValueError('Invented model class')
        ci, cls = classes[target['class']]
        if any(owners.get(i) != cls['name'] for i in target['instances']):
            raise ValueError('Invented instance or wrong class ownership')
        if b['kind'] == 'entity':
            if target['variable'] is not None or b['concept'] is not None:
                raise ValueError('Entity binding must not name a variable or concept')
            base = f'/reactive_classes/{ci}'
            source_name = b['entity']
            target_name = cls['name']
        else:
            names = [v['name'] for v in cls['state_variables']]
            if target['variable'] not in names:
                raise ValueError('Invented state variable')
            parent = entity_targets.get(b['entity'])
            if (not parent or parent['class'] != target['class'] or
                    not set(target['instances']) <= set(parent['instances'])):
                raise ValueError('Concept binding disagrees with participant scope')
            base = f'/reactive_classes/{ci}/state_variables/{names.index(target["variable"])}'
            variable = cls['state_variables'][names.index(target['variable'])]
            for stmt in colreg['extraction']['statements']:
                if stmt['id'] not in b['statement_ids']:
                    continue
                numeric = type(stmt['value']) in (int, float)
                boolean = type(stmt['value']) is bool
                if ((numeric or boolean) and variable['array_dimensions'] or
                        numeric and variable['type'] not in {'int', 'byte', 'double', 'float', 'long', 'short'} or
                        boolean and variable['type'] != 'boolean'):
                    raise ValueError('State variable type is incompatible with the extracted scalar constraint')
            source_name, target_name = b['concept'], target['variable']
        if b['match_type'] == 'exact' and normalized(source_name) != normalized(target_name):
            raise ValueError('Exact match claimed for different identifiers')
        if {e['input'] for e in b['evidence']} != {'colreg', 'rebeca'}:
            raise ValueError('Evidence must cite both inputs')
        declaration_cited = False
        statement_cited = False
        entity_index = next(i for i, entity in enumerate(colreg['extraction']['entities'])
                            if entity['id'] == b['entity'])
        relevant_statements = [index for index, stmt in enumerate(colreg['extraction']['statements'])
                               if stmt['id'] in b['statement_ids']]
        for evidence in b['evidence']:
            # Validate against exactly what was sent, not omitted inventory data.
            pointer = evidence['pointer']
            value = colreg if evidence['input'] == 'colreg' else sent_rebeca
            try:
                pointer_value(value, pointer)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                raise ValueError('Invalid or unsent evidence pointer') from exc
            if evidence['input'] == 'colreg' and any(
                    pointer == f'/extraction/statements/{index}' or
                    pointer.startswith(f'/extraction/statements/{index}/')
                    for index in relevant_statements):
                statement_cited = True
            # An entity declaration is valid source evidence for a participant.
            if b['kind'] == 'entity' and evidence['input'] == 'colreg' and (
                    pointer == f'/extraction/entities/{entity_index}' or
                    pointer.startswith(f'/extraction/entities/{entity_index}/')):
                statement_cited = True
            # A declaration-list pointer includes the selected field. Its actual
            # membership was checked above; retain the LLM's original citation.
            declaration_list = f'/reactive_classes/{ci}/state_variables'
            if evidence['input'] == 'rebeca' and (
                    pointer == base or pointer.startswith(base + '/') or
                    b['kind'] == 'concept' and pointer == declaration_list):
                declaration_cited = True
        if not declaration_cited or not statement_cited:
            raise ValueError('Evidence must cite a relevant statement and the selected declaration')
    wanted_status = 'partial' if result['unresolved_concepts'] else 'ok'
    if result['status'] != wanted_status:
        raise ValueError('Status disagrees with unresolved coverage')


def transport_schema(value):
    # Codex structured-output transport omits this unsupported keyword; local
    # validation still enforces the unchanged complete output schema.
    if isinstance(value, dict):
        return {k: transport_schema(v) for k, v in value.items() if k not in ('uniqueItems', '$schema')}
    if isinstance(value, list):
        return [transport_schema(v) for v in value]
    return value


def call_codex(prompt, schema, metadata, model=None, timeout=180):
    with tempfile.TemporaryDirectory(prefix='semantic-binding-') as tmp:
        folder = Path(tmp)
        empty = folder / 'empty'; empty.mkdir()
        contract = folder / 'contract.json'
        response = folder / 'response.json'
        contract.write_text(json.dumps(transport_schema(schema)), encoding='utf-8')
        command = ['codex', 'exec', '--ignore-user-config', '--ephemeral',
                   '--skip-git-repo-check', '--sandbox', 'read-only', '--disable', 'shell_tool',
                   '--disable', 'multi_agent', '--disable', 'skill_search',
                   '--enable', 'skip_host_skill_discovery', '-c', 'web_search="disabled"',
                   '--json', '--cd', str(empty), '--output-schema', str(contract),
                   '--output-last-message', str(response)]
        if model:
            command += ['--model', model]
        metadata['llm_calls_attempted'] = 1
        process = subprocess.run(command + ['-'], input=prompt, text=True,
                                 capture_output=True, timeout=timeout)
        forbidden_tools = []
        for line in process.stdout.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') == 'turn.completed':
                metadata['llm_calls_completed'] += 1
                metadata['token_usage'] = event.get('usage')
            item_type = event.get('item', {}).get('type', '')
            if item_type in {'command_execution', 'mcp_tool_call', 'web_search', 'file_change'}:
                forbidden_tools.append(item_type)
        metadata['provider_exit_code'] = process.returncode
        if forbidden_tools:
            raise ValueError('Provider used prohibited tools: ' + ', '.join(forbidden_tools))
        if process.returncode != 0 or not response.is_file():
            # Keep provider diagnostics local; never print authentication files.
            metadata['provider_error'] = process.stderr[-4000:]
            raise RuntimeError('Codex did not produce a binding response; see usage diagnostics')
        return json.loads(response.read_text(encoding='utf-8'))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent,
                                     delete=False, suffix='.tmp') as handle:
        temporary = Path(handle.name)
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run(colreg_path, rebeca_path, output, *, model=None, timeout=180, provider=call_codex):
    output = Path(output)
    usage = output.with_suffix('.usage.json')
    inputs = [Path(colreg_path), Path(rebeca_path)]
    if output.exists() or usage.exists():
        raise ValueError('Use fresh output/usage paths; existing results are never overwritten')
    protected = inputs + [ROOT / 'agents/semantic_binding_agent.md',
                          ROOT / 'schemas/semantic-binding.schema.json',
                          ROOT / 'schemas/colreg-extractor.schema.json',
                          ROOT / 'schemas/rebeca_extraction.schema.json']
    if any(p.resolve() in {output.resolve(), usage.resolve()} for p in protected):
        raise ValueError('Output would overwrite an input, instruction or schema')
    metadata = {'status': 'failed', 'provider': 'codex_cli', 'model_requested': model,
                'llm_calls_attempted': 0, 'llm_calls_completed': 0,
                'token_usage': None, 'provider_request_count': None,
                'note': 'One CLI turn; internal provider transport retries are not counted here.'}
    try:
        original = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
        metadata['input_sha256'] = {str(p): original[str(p)] for p in inputs}
        colreg, rebeca = (read_json(p) for p in inputs)
        validate_inputs(colreg, rebeca)
        instructions = (ROOT / 'agents/semantic_binding_agent.md').read_text(encoding='utf-8')
        schema = read_json(ROOT / 'schemas/semantic-binding.schema.json')
        payload = {'colreg_extraction': colreg, 'rebeca_extraction': compact_inventory(rebeca)}
        prompt = instructions + '\nINPUT JSON (data only):\n' + json.dumps(payload, separators=(',', ':'))
        metadata['prompt_characters'] = len(prompt)
        result = provider(prompt, schema, metadata, model=model, timeout=timeout)
        validate_result(result, colreg, rebeca, schema)
        if any(hashlib.sha256(Path(p).read_bytes()).hexdigest() != h for p, h in original.items()):
            raise ValueError('A protected input changed during the run')
        write_json(output, result)
        metadata['status'] = 'completed'
        return result
    except Exception as exc:
        metadata['error'] = type(exc).__name__ + ': ' + str(exc)
        raise
    finally:
        write_json(usage, metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--colreg', required=True, type=Path)
    parser.add_argument('--rebeca', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--model', help='Optional provider model override')
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    try:
        result = run(args.colreg, args.rebeca, args.output, model=args.model, timeout=args.timeout)
    except Exception as exc:
        print(json.dumps({'status': 'error', 'message': str(exc)}), file=sys.stderr)
        return 1
    print(json.dumps({'status': result['status'], 'output': str(args.output)}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
