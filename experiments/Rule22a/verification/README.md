# Rule 22(a) full-rerun verification

The saved 2026-11-23 Coordinator run executed every stage in full-rerun mode.
Three native specialist passes produced fresh extraction, binding and synthesis
responses. Synthesis emitted ten guarded symbolic assertions and zero model
patches. The generated model is byte-identical to the original Rebeca input.
The timing-corrected RMC build compiled and checked this run's model and
Property. The [run manifest](../run.json) records the input and output hashes,
including the exact files passed to RMC.

| Phase | Recorded result |
| --- | --- |
| RMC build | `2.14-colreg-timing.1`, Timed Rebeca and FTTS |
| C++ generation and `g++` compilation | Both succeeded, compiler stderr empty |
| Checker execution | Completed, exit code 0 |
| XML verdict | `satisfied` |
| Reached states / transitions | 5,470 / 6,512 |
| RMC-reported checking time | 24 seconds |
| Counterexample trace | Empty |
| Optional vacuity and mutation checks | Disabled |

The XML names the reachability check “Deadlock-Freedom and No Deadline Missed.”
Inspection of the retained generated C++ confirmed that the timed checker also
calls all ten named assertion functions. The [execution record](execution.json)
summarizes that inspection and the saved command. The [gate JSON](result.json)
and [RMC XML](model_result.xml) are the original outputs from this execution.

## Vacuous satisfaction

All ten assertions have the antecedent `ship_length >= 50` for their respective
ship. The model initializes `s1.ship_length` to `12` and `s2.ship_length` to
`10`. Neither actor field is written after construction, so both antecedents
remain false and the range comparisons are vacuously satisfied. This conclusion
comes from static inspection of the original model and the
[Rebeca inventory](../rebeca_extraction.json).

The [Property](../synthesis/model.property) uses untranslated source numbers.
Model units, which lights are legally prescribed, Annex I intensity, physical
visibility, and the all-round light colors remain unresolved. The verdict
establishes execution of the encoded checks. Rule 22(a) compliance remains
unestablished. See the [synthesis report](../synthesis/report.json) for the
recorded binding and interpretation limits.

## Provenance

The [Coordinator report](../coordinator_report.json) records the fresh
handoffs and outcome. [Synthesis provenance](../synthesis/execution_provenance.json)
and [verification execution metadata](execution.json) were assembled for
publication from the saved run records and retained work products. Local
scratch paths in runner outputs describe the host that performed the run.
The JAR, generated C++, checker binary, state-space export, and build logs stay
in ignored local output. The [timing-fix build documentation](../../../verification/rmc/timing_fix/README.md)
identifies the pinned build.
