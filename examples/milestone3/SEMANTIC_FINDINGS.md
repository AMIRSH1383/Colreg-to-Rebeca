# Milestone 3: model semantics and limits

This audit uses the actual model source and its documentation comments. No
regulatory translation or historical property file supplies semantic evidence.
Annotations are analyst interpretations with exact source citations, not human
review. The complete field inventory is in `model-audit.md` and the v2 catalog.

## Navigation-model findings

Source: `work/Original Model.rebeca`, byte hash
`be31a8c28b08facfa9f322f2a29fd77572de1c55c3e928688742906133b09149`.

| Quantity | Actual source behavior | Suitability and uncertainty |
| --- | --- | --- |
| Ship.ship_length | Constructor copies s_length at145; main supplies12/10 at1553–1554; passed to map at345/412/660/676; unscaled in distance guard695 | A configured geometric quantity, not safely established as metres. MapServer divides the same arguments by SCALING_FACTOR at1067/1239. Unit/scale conflict blocks automatic threshold binding. |
| Ship.ship_width | Constructor copy146; scaled at513 and map geometry1068/1240; used in path clearances1269/1276 | Configured geometric dimension; physical unit must be reviewed with scaling. |
| Ship.ship_draught | Constructor copy147; no behavioral reads identified | Configured attribute with unestablished units; no draught physics demonstrated. |
| Ship.*light_range | Declared121–134; initialized158–170; no operational reads or subsequent writes identified | Configured attributes only. No nautical-mile declarations, attenuation model, sensing, emission, color encoding or intensity calculation. Values alone do not establish units or regulatory meaning. |
| Ship.*light / *_light_on | Constructor true values157–169; no operational reads or subsequent updates | Constant configuration flags. They do not establish visible emission, working equipment or changing light states. |
| Ship.signal_light_range versus allround_light_range | Distinct fields, initialized3 and2 respectively | No source evidence of synonymy. Do not substitute one for the other to satisfy a property. |
| Ship.engine_on | Initialized true155; no behavioral reads/transitions identified | Constant flag, not a readiness/capability model. Immediate manoeuvre cannot be inferred. |
| Ship.vessel_type_powerdriven | Copied from constructor154; both actors receive true | Type configuration only; no propulsion capability established by the flag. |
| Ship.ship_velocity | int(real_velocity*10) at149; copied into original_velocity150; halved/restored625/630 | Comment says knots but multiplication is not a conversion proof. This attribute does not drive movement scheduling; do not equate it with the actual motion variable. |
| Ship.velocity/default_velocity | default_velocity derives from real_velocity/MAP_RESOL182; velocity changes0/default in movement methods; used in messages and guards | Movement simulation quantity. Timing183–184 and cell geometry support a separate interpretation from ship_velocity. Rounding and source comments require review before physical conversion. |
| Ship.vis_range | Set to VISRANGEOK151, switches500/1200 in fog branch623/628 | Abstract visibility setting with no behavioral reads identified. Not an optical measurement or a navigation-light visibility range. |
| Ship.obstacles | Array initialized205, overwritten from scandata480, consumed as encoded coordinates522–525 | Simulated scan/message data, not a physical radar measurement. The comment at475 describes relative obstacle coordinates. |
| Ship.front_obstacle | Initialized206, derived with stepwise=true482, recomputed as distance/steplen693 | Derived step-distance quantity with casts and sentinel values, not a light-visibility range. |
| Ship.distance2target | Initialized INFINITY180, rounded geometric distance413, used in target/scan guards485/646 | Derived navigation distance; units require following the grid/distance helpers rather than matching the word distance. |
| Ship.restricted_visibility | Starts false152; updated by a strict rectangle-membership test621/624/629 | A derived simulation condition, refreshed on updateMovingStatus, not a full legal applicability condition or proof that vessels are not in sight. Rectangle boundaries are excluded by isInsideRect213. |
| MapServer.speed_safe_range | Initialized7 at820; no reads identified | No source-supported context-dependent safe-speed function. Never use7 as a regulatory threshold. |
| MapServer.ships_close_to_each_other | distance computed in grid coordinates1079; true if distance>=5 at1080–1081 | Name and comparison direction conflict. Units and intended meaning unresolved. |
| MapServer.ship_loc_dir_vel | Stores direction at offset3 and velocity at offset4,1073–1076 | scanObstacles reads offset3 into ship_velocity_hiep and offset4 into ship_dir,941–942; other sites use the opposite ordering. This is an indexing inconsistency, not reliable motion evidence. |
| MapServer.traffic-zone flags | Derived from rectangle intersection1132–1149 | Simulation geometry membership; no independent regulatory-zone definition established. |

MapServer local variables named ship_length/ship_width are not Ship state fields.
The audit keeps class ownership and flags possible local shadowing. Scalar and
array accesses are inventoried lexically, not through a complete language AST.

The navigation model still has the independently recorded double-to-int compiler
errors at293/846. It is not modified by this milestone. No physical-unit ambiguity
is repaired merely to obtain a passing verification result.

## Isolated fixture findings

Source: `examples/rule22a/range-model.rebeca`, byte hash
`80d2dfafb4d8e4dddc001c104644aa73394928d3e012b3a1a9388ad33174bea2`.

Its existing first-line documentation explicitly states that length uses metres
and visibility ranges use nautical miles. The class declaration, field names and
constructor jointly identify the configured attribute family/category. All six
measurement fields are constructor-only; the check message changes none of them.

This supports **configured-attribute comparisons in that fixture**, with unreviewed
analyst annotations and source citations. It does not establish installation,
photometry, colored-light semantics, real sensors, physical compliance or a
behavioral abstraction of the navigation model. The binder must retain these limits.

The catalog contains no regulatory thresholds, source-rule identifiers, expected
properties or concept-alias answer table. Constructor values occur only as actual
source evidence and must not be used to select a mapping. A renamed field can only
be matched if its documentary/use evidence still supports the meaning.
