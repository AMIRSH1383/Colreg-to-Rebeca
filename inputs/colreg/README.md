# COLREG benchmark inputs

The additional inputs come from `COLREG_Formalizability_Benchmark_v2.xlsx`. Its
`Benchmark` sheet has 253 entries covering Rules 1–41, keyed by `Source Key` in
column A. The source text is in `Exact Rule Text` in column G. `Legend` defines
the workbook's ratings and `Summary` aggregates them. The Rule 19 and Rule 22
baseline files predate this selection.

## Selected cases in benchmark order

| Coordinator ID and input | Selected subsection | `Benchmark` cells | Expected difficulty | Relevant state in `Ship` unless noted | Selection rationale and limitations |
| --- | --- | --- | --- | --- | --- |
| 1. `Rule3b` ([text](Rule3b.txt)) | 3(b), power-driven vessel definition | G10 (C) | Easy | `vessel_type_powerdriven` | Direct Boolean classification initialized from `is_powerdriven`. Both ships start true. This is an extraction and binding control with no standalone obligation. |
| 2. `Rule6ai` ([text](Rule6ai.txt)) | 6(a)(i), visibility as a factor in determining safe speed | G30 (B) | Easy | `restricted_visibility`, `vis_range`, `ship_velocity`, `original_velocity` | The fog check in `updateMovingStatus` sets visibility state and reduces the stored `ship_velocity`. This tests whether the pipeline can connect a decision factor to an existing assignment. Actual transit timing uses constructor-derived `default_time_cross` and `default_time_cross_diag`. Safe speed, an appropriate reduction, and physical speed units remain unresolved. The target covers one factor for all vessels. The existing Rule 19 input concerns conduct in restricted visibility. |
| 3. `Rule23a` ([text](Rule23a.txt)) | 23(a)(i)–(iv), lights for a power-driven vessel underway, with 23(d)(i)–(iii) alternatives and fitting exceptions | G133–G136 target (A). G22, G118–G120, G122, G139–G141 context. | Moderate | `vessel_type_powerdriven`, `ship_length`, `original_velocity`, `restricted_visibility`, `masthead_light`, `side_light`, `side_light_on`, `stern_light`, `allround_light`, `allround_light_on` | Light-display obligations, a 50 m exception, and conditional alternatives below 12 m and 7 m. The flags offer partial evidence about equipment. The model lacks underway status, day/night, light counts, color, placement, and complete exhibit state. Geometry divides raw `ship_length` by `SCALING_FACTOR`. The constructor derives `original_velocity` from `int(real_velocity * 10)`. The 7-knot maximum-speed test and physical length thresholds need validated mappings. Annex I specifications are outside the workbook. The input covers ordinary power-driven-vessel light configuration and associated exceptions. |
| 4. `Rule13b` ([text](Rule13b.txt)) | 13(b), initial overtaking classification | G85 target (A). G24 and G79 context. | Moderate | `ship_x`, `ship_y`, `ship_dir`, `side_light`, `stern_light`, `MapServer.ship_loc_dir_vel` | The strict 22.5° threshold tests a derived relative bearing referenced to the vessel being overtaken. The model stores grid positions and eight 45° heading codes. No state directly records an overtaking encounter, closing evidence over time, or mutual visual observation of the sternlight and sidelights. The give-way obligation, doubt handling, and persistence until past and clear in 13(a), (c), and (d) are outside the selection. |

Difficulty describes the expected work of extraction and binding the supported
portion. None of these ratings or mappings has been validated through Synthesis
or Verification. The four inputs cover vessel classification, a factor in speed
selection, light configuration with exceptions, and encounter geometry. The
model gaps below limit the selection to four.

The `Rule23a` benchmark targets the four light-display clauses in Rule 23(a).
Rule 3(i) defines *underway*. Rule 20(a)–(c) supplies the weather, time-of-day,
and visibility scope, and Rule 20(e) supplies the Annex I reference. Rule
23(d)(i) and (ii) give conditional alternatives to the standard light display,
and Rule 23(d)(iii) permits an offset light only under its stated fitting
conditions. The manifest marks these passages as context for interpreting the
Rule 23(a) target.

## Other candidates screened

Workbook grades are **A** for directly formalizable, **B** for formalizable with
abstraction, and **C** for currently unsuitable for direct property formalization.
They describe the regulation independently of this model. The screening below
compares the exact source cells to the current model's state and behavior.

| Candidate | `Benchmark` cell and grade | Formalization and current model fit | Pipeline decision |
| --- | --- | --- | --- |
| 3(l) | G25, C | A definition with an open list of visibility causes. The model has a fog zone and flag. | Excluded to limit repeated fog coverage. Other causes remain unmodeled. |
| 8(d) | G50, B | Distances are computable from positions. Safe passing distance and the point at which the other vessel is past and clear require additional criteria. `MapServer.ships_close_to_each_other` is set true for computed distances of at least 5. | Excluded. The flag cannot establish safe passage or the required monitoring interval. |
| 8(e) | G51, B | `velocity`, `isWaiting`, and the obstacle-stop branch expose stopping. The model lacks a regulatory necessity predicate or propulsion reversal state. The cell reads “allow more to assess the situation”. | Excluded. The source wording leaves that trigger incomplete, and the observed stopping behavior covers only part of the clause. |
| 10(c) | G67, B | The right-angle target is clear. `ship_dir` and traffic-zone flags are available, with the latter representing rectangle intersection. | Excluded. No adopted traffic separation scheme, directed lane, crossing obligation, or angular tolerance is represented. |
| 14(a) | G88, B | The starboard maneuver is concrete and code stores heading and vessel type. Reciprocal-encounter risk and sight conditions are absent. | Excluded. Rule 11 scope and 14(b)–(c) visual and doubt criteria would require additional state and interpretation. |
| 15 | G91, B | A starboard-side give-way rule can use relative pose as a starting point. The model lacks crossing-risk recognition and a give-way role. | Excluded. “Keep out of the way” and the exception for crossing ahead need encounter and behavioral criteria. |
| 17(a)(i) | G93, B | Course and speed can be observed. The stand-on role and the conditions for departing from course and speed in 17(a)(ii) and 17(b) are absent. | Excluded. A course-and-speed invariant alone would discard the qualifying roles and exceptions. |
| 21(e) | G127, C | The 360° definition is explicit. `allround_light` and `allround_light_on` are flags with no optical coverage state. | Excluded. The angles cannot be evaluated from these flags, and light categories are already covered in Rule 23. |
| 30(e) | G206, B | The under-7 m threshold and location exceptions could be represented with an anchorage-aware model. `ship_length` is available with unresolved physical units. | Excluded. Anchor status, channels, fairways, and usual navigation areas are absent. Paragraphs 30(a) and (b) specify the lights and shapes being waived. |
| 33(a) | G212, A | Clear 12 m, 20 m, and 100 m thresholds. There are no whistle, bell, gong, equivalent equipment, or manual-sounding fields. | Excluded. Only a potential length mapping exists. Annex III specifications are outside the workbook. |
| 35(a) | G223, A | Objective two-minute interval with a prolonged blast. The model has fog and power-driven flags and timed messages. | Excluded. Making way through the water and acoustic blast events are absent. RMC message timing alone cannot represent sound signals. |

## Source verification

The [source manifest](source_manifest.json) identifies the workbook by SHA-256
and maps each file to ordered cell addresses, source keys, target or context
roles, and a SHA-256 of the file bytes. Each file consists of the original cell
values encoded as UTF-8 and joined with two LF characters. No heading, footer,
or final newline is added. The four Rule 23(a) cells each repeat the introductory
clause in the workbook, so each occurrence is preserved.

The Coordinator recognizes the IDs in the table and hyphenated equivalents such
as `Rule-6ai`. The deterministic dataset tests check discovery, recorded text
hashes, duplicate source passages, and declared Rebeca state references.
