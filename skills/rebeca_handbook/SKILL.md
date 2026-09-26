---
name: rebeca-handbook
description: Canonical self-contained reference for writing correct Rebeca models and properties. Covers actor model patterns, forbidden operators, Do's/Don'ts, property examples, Legata-to-assertion mapping, and RMC pitfall table.
---

# Rebeca Modeling Guidelines Skill

## Actor Model Basics

Rebeca uses the actor model — actors communicate only via asynchronous messages:

```rebeca
reactiveclass Ship(int id) {
    statevars {
        int ship_length;
        boolean masthead_light_on;
        int masthead_light_range;
    }

    Ship() {
        ship_length = 0;
        masthead_light_on = false;
        masthead_light_range = 0;
    }

    msgsrv updateLight(boolean on, int range) {
        masthead_light_on = on;
        masthead_light_range = range;
    }
}

main {
    Ship s1(1):();
    Ship s2(2):();
}
```

Key rules:
- State is **local** to each actor — no shared memory
- Actors communicate only via `msgsrv` message handlers
- Property access uses `actorName.stateVariable` syntax

## Rebeca Do's

- ✓ DO define all variables before using them
- ✓ DO use parentheses for clarity in complex expressions
- ✓ DO keep assertion logic simple and verifiable
- ✓ DO test with concrete actor instances first
- ✓ DO use meaningful variable names matching domain (vessel_type, light_on)
- ✓ DO validate property files syntax independently
- ✓ DO archive counterexamples for regression testing

## Rebeca Don'ts

- ✗ DON'T use implication operators (→, =>)
- ✗ DON'T chain variable assignments
- ✗ DON'T reference undefined variables
- ✗ DON'T mix temporal operators in assertion section
- ✗ DON'T assume operator precedence - use explicit parentheses
- ✗ DON'T create properties without testing model first
- ✗ DON'T ignore RMC error messages - they indicate real issues

## Syntax Examples

### Good: Simple Assertion
```
property {
  define {
    hasLight = s1.masthead_light_on;
    lightRange = s1.masthead_light_range;
  }
  Assertion {
    Rule22: !hasLight || (lightRange >= 6);
  }
}
```

### Bad: Uses Implication
```
property {
  define {
    hasLight = s1.masthead_light_on;
  }
  Assertion {
    Rule22: hasLight -> s1.masthead_light_range >= 6;  // FORBIDDEN
  }
}
```

### Good: Multi-Actor Coverage
```
property {
  define {
    ship1_rules = (s1.length > 50) || (s1.type != PowerDriven);
    ship2_rules = (s2.length > 50) || (s2.type != PowerDriven);
  }
  Assertion {
    BothShips: ship1_rules && ship2_rules;
  }
}
```

## Property-Writing Examples

### Good: Well-Structured Property
```
property {
  define {
    smallVessel = (s1.vessel_length < 12);
    powerDriven = (s1.vessel_type == PowerDriven);
    lightsActive = (s1.masthead_light_on && s1.sidelight_on);
  }
  Assertion {
    Rule23: !powerDriven || smallVessel || lightsActive;
  }
  LTL {
    Liveness: G(powerDriven -> F(lightsActive));
  }
}
```

### Bad: Undefined Variable
```
property {
  define {
    smallVessel = (s1.vessel_length < 12);
  }
  Assertion {
    Rule23: !powerDriven || smallVessel || lightsActive;  // undefined: powerDriven, lightsActive
  }
}
```

## RMC Toolchain Usage

RMC is provisioned by `setup.py` at install time. To run verification:

```bash
python3 <scripts>/run_rmc.py \
  --jar <jar> \
  --model ./models/SimulationModelCode.rebeca \
  --property ./properties/rule_22.property \
  --output-dir ./verification_output \
  --timeout-seconds 120
```

For the full tooling API and additional CLI commands, consult the `rebeca_tooling` skill at `<skills>/rebeca_tooling/SKILL.md`.

## Common Pitfalls and Recovery

| Issue | Symptom | Fix |
|-------|---------|-----|
| Chained assignment | Compile error: unexpected `=` | Separate into define sections |
| Undefined variable | RMC error: unknown variable | Add to define section |
| Missing parentheses | Unexpected operator precedence | Add `()` around complex expressions |
| Temporal in assertion | Property parse error | Move to LTL section |
| Non-determinism explosion | RMC timeout | Reduce non-det choices, pin values |
