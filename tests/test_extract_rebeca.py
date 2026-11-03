from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / 'skills' / 'rebeca_tooling' / 'scripts'))

from extract_rebeca import extract


def test_inventory_ignores_comment_and_string_braces():
    result = extract('''// reactiveclass Fake(1) { }
env int LIMIT = 50;
reactiveclass Ship(10) {
 knownrebecs { Map map; }
 statevars { int length, speed; int[4/*size*/] ranges; }
 Ship(int n) { length = n; assertion(true, "}"); if (true) { speed = 2; } }
 msgsrv tick() { if (true) { speed = 3; } }
}
main { @priority(3) Ship s1(map):(60); }
''')
    actor = result['reactive_classes'][0]
    assert actor['state_variables'] == [
        {'name': 'length', 'type': 'int'}, {'name': 'speed', 'type': 'int'},
        {'name': 'ranges', 'type': 'int[4]'}]
    assert actor['constructors'][0]['assignments'] == [
        {'variable': 'length', 'expression': 'n'}, {'variable': 'speed', 'expression': '2'}]
    assert actor['message_servers'][0]['name'] == 'tick'
    assert result['instances'][0]['constructor_arguments'] == '60'
    assert result['environment'][0]['expression'] == '50'


def test_rejects_incomplete_or_unsupported_input():
    for source in ['reactiveclass S(1) {', '}', '',
                   'reactiveclass S(1) {} main { unsupported; }']:
        with unittest.TestCase().assertRaises(ValueError):
            extract(source)


def test_repository_model():
    source = (Path(__file__).parents[1] / 'work' / 'Original Model.rebeca').read_text(encoding='utf-8')
    result = extract(source)
    assert [c['name'] for c in result['reactive_classes']] == ['Ship', 'MapServer']
    ship = result['reactive_classes'][0]
    assert {'name': 'masthead_light_range', 'type': 'int'} in ship['state_variables']
    assert [i['name'] for i in result['instances']] == ['s1', 's2', 'theMap']
    assert result == extract(source)


def test_context_preserves_source_and_line_numbers():
    source = '''reactiveclass A(2) {
 statevars { int x; }
 A() { x = 3; }
 msgsrv tick(int x) { if (x > 2) { self.tick(x - 1); } }
}
main { A a():(); }
'''
    contexts = extract(source)['reactive_classes'][0]['source_context']
    method = next(c for c in contexts if c['member'].startswith('msgsrv'))
    assert 'self.tick(x - 1)' in method['source']
    assert method['source'] in source
    assert method['line_start'] == source.count('\n', 0, source.index(method['source'])) + 1
    assert 'shadow' in method['interpretation']


def test_rejects_ambiguous_or_missing_actor_identity():
    for source in ['reactiveclass A(1) {} reactiveclass A(2) {}',
                   'reactiveclass A(1) {} main { A a():(); A a():(); }',
                   'reactiveclass A(1) {} main { B b():(); }']:
        with unittest.TestCase().assertRaises(ValueError):
            extract(source)


if __name__ == '__main__':
    suite = unittest.TestSuite(unittest.FunctionTestCase(test) for test in (
        test_inventory_ignores_comment_and_string_braces,
        test_rejects_incomplete_or_unsupported_input, test_repository_model))
    outcome = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if outcome.wasSuccessful() else 1)
