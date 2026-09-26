"""
Transformation pattern library derived from the Legata-to-Rebeca handbook.
Provides programmatic access to standard formalization patterns.
"""

def get_canonical_assertion(condition: str, exclude: str, assure: str) -> str:
    """
    Constructs an assertion based on the standard Legata mapping pattern:
    (!condition || !exclude || assure)
    """
    # Clean up logical negations to avoid double-negation
    c = f"!{condition}" if not condition.startswith("!") else condition[1:]
    e = f"!{exclude}" if not exclude.startswith("!") else exclude[1:]
    a = assure
    return f"{c} || {e} || {a}"

def format_rebeca_define(var_name: str, expression: str) -> str:
    """Formats a standard Rebeca define statement."""
    return f"{var_name} = ({expression});"
