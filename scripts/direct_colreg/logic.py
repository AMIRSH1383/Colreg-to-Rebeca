"""Typed single-entity state logic. Unsupported constructs fail closed."""
import math
import re


class Unsupported(ValueError):
    pass


COMPARISONS = {'>', '>=', '<', '<=', '==', '!='}
IDENT = re.compile(r'^[A-Za-z_]\w*$')


def atoms(expr):
    if expr['op'] == 'compare':
        return [expr]
    return [a for child in expr.get('args', []) for a in atoms(child)]


def validate(expr):
    op = expr.get('op')
    if op == 'compare':
        if expr.get('operator') not in COMPARISONS:
            raise Unsupported('Unsupported comparison')
        if not all(IDENT.fullmatch(expr.get(k, '')) for k in ('entity', 'concept')):
            raise Unsupported('Invalid concept/entity identifier')
        value = expr.get('value')
        if type(value) not in (int, float, bool) or (type(value) is float and not math.isfinite(value)):
            raise Unsupported('Only finite numeric and boolean comparison values are supported')
        return
    args = expr.get('args', [])
    if op in ('true', 'false') and not args:
        return
    if op in ('and', 'or') and len(args) >= 2 or op == 'not' and len(args) == 1 or op == 'implies' and len(args) == 2:
        for arg in args:
            validate(arg)
        return
    raise Unsupported('Unsupported logical operator or arity: ' + str(op))


def check_type(atom, variable_type):
    boolean = type(atom['value']) is bool
    if boolean:
        if variable_type != 'boolean' or atom['operator'] not in ('==', '!='):
            raise Unsupported('Boolean comparisons require boolean fields and ==/!=')
    elif variable_type not in ('int', 'byte', 'short', 'double', 'float'):
        raise Unsupported('Numeric comparison requires scalar numeric field')


def render(expr, bindings, instance, definitions):
    validate(expr)
    op = expr['op']
    if op in ('true', 'false'):
        return op
    if op == 'compare':
        key = (expr['entity'], expr['concept'])
        binding = bindings[key]
        check_type(expr, binding['type'])
        if expr['unit'] != binding['unit']:
            raise Unsupported('Unit mismatch; no implicit unit conversion')
        value = str(expr['value']).lower()
        name = 'G_ap_' + str(len(definitions))
        definitions.append(f'{name} = ({instance}.{binding["variable"]} {expr["operator"]} {value});')
        return name
    rendered = [render(a, bindings, instance, definitions) for a in expr['args']]
    if op == 'not':
        return '!(' + rendered[0] + ')'
    if op == 'implies':
        return '(!(' + rendered[0] + ') || (' + rendered[1] + '))'
    return '(' + (' && ' if op == 'and' else ' || ').join(rendered) + ')'


def effective_applicability(requirement):
    antecedent = requirement['applicability']
    if requirement['exceptions']:
        exceptions = requirement['exceptions']
        exemption = exceptions[0] if len(exceptions) == 1 else {'op': 'or', 'args': exceptions}
        return {'op': 'and', 'args': [antecedent, {'op': 'not', 'args': [exemption]}]}
    return antecedent


def property_text(requirement, bindings, instance, witness=False):
    if requirement['support'] != 'state' or requirement['temporal'] is not None:
        raise Unsupported('Temporal, operational or underspecified semantics are unsupported')
    condition = effective_applicability(requirement)
    all_atoms = atoms(condition) + atoms(requirement['obligation'])
    if len({a['entity'] for a in all_atoms}) != 1:
        raise Unsupported('Only one entity per requirement is supported; no relational/multi-actor semantics')
    definitions = []
    left = render(condition, bindings, instance, definitions)
    if witness:
        assertion = '!(' + left + ')'
    else:
        right = render(requirement['obligation'], bindings, instance, definitions)
        if requirement['kind'] == 'prohibition':
            right = '!(' + right + ')'
        assertion = '(!(' + left + ') || (' + right + '))'
    label = 'G_WitnessAbsent' if witness else 'G_Requirement'
    return definitions, [label + ': ' + assertion + ';']
