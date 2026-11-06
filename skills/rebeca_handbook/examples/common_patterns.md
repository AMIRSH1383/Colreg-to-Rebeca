# Illustrative Rebeca patterns

Initialize actors in `main`, use constructors for state initialization, and avoid
local parameters that shadow state variables. See `syntax_examples.rebeca` and
its paired `property_examples.property` for a finite example.

Assertion implication: `!precondition || postcondition`.
Conjunction: `condition_a && condition_b`.
LTL may use temporal operators and implication, but belongs in an LTL section,
not in an Assertion. Check syntax with RMC; the heuristic checker is not a parser.
No pattern here supplies missing COLREG thresholds or maritime assumptions.
