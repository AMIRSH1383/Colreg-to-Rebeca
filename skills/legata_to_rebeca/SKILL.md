---
name: legata-to-rebeca
description: Domain knowledge for transforming Legata maritime safety clauses into Rebeca actor models — Legata clause structure and worked transformation examples.
---

# Legata → Rebeca Skill Reference

Domain knowledge for agents working with Legata rules. Tooling reference, naming conventions, and script invocations are documented in the individual subagent files.

---

## When to use

- Converting Legata maritime safety clauses into Rebeca models and `.property` assertions.
- Checking clause structure (`Condition`, `Exclude`, `Assure`) and mapping it to Boolean form.
- Looking up worked examples for common transformation patterns (single-ship, multi-actor, and LTL).

## Legata Clause Structure

Every Legata rule is composed of up to three named sections:

| Section | Role in assertion | Rebeca pattern |
|---------|------------------|----------------|
| `Condition` | Trigger — must hold for the rule to activate | `!condition \|\|` |
| `Exclude` | Exemption — waives the obligation when true | `exclude \|\|` |
| `Assure` | Obligation — what must be true when active | `assurance` |

Formal derivation: `condition ∧ ¬exclude → assure` = `¬condition ∨ exclude ∨ assure`

---

## Transformation Examples

### Equipment Range (Rule 22)

```
clause['Equipment Range Check']:{
    condition: { OS.Length > meters(50) }
    assure: {
        : OS.Equipment.MastheadLight.Range >= miles(6)
        : OS.Equipment.SideLight.Range >= miles(3)
    }
}
```

```property
property {
  define {
    ship_longer_50m   = (s1.ship_length > 50);
    masthead_range_ok = (s1.masthead_light_range >= 6);
    sidelight_range_ok = (s1.sidelight_range >= 3);
  }
  Assertion {
    Rule22: !ship_longer_50m || (masthead_range_ok && sidelight_range_ok);
  }
}
```

### Exclude Blocks (Rule 23)

```
clause['Power Driven Signaling']:{
    condition: { OS.Type is Vessel.Type.PowerDriven }
    exclude:   { OS.Length < meters(12) }
    assure: {
        : OS.Signal.ON has 'Light.Masthead'
        : OS.Signal.ON has 'Light.Sidelight'
    }
}
```

```property
property {
  define {
    isPowerDriven = (s1.vessel_type == PowerDriven);
    isSmallShip   = (s1.ship_length < 12);
    lightsOn      = (s1.masthead_light_on && s1.sidelight_on);
  }
  Assertion {
    Rule23: !isPowerDriven || isSmallShip || lightsOn;
  }
}
```

### Multiple Conditions (Rule 25)

Multiple conditions are each negated and ORed: `!c1 || !c2 || ... || assurance`.

```property
property {
  define {
    notUnderCommand = (s1.not_under_command);
    underway        = (s1.underway);
    allRoundOn      = (s1.all_round_light_on);
  }
  Assertion {
    Rule25: !notUnderCommand || !underway || allRoundOn;
  }
}
```

### Multi-Actor (Rules with two vessels)

```property
property {
  define {
    ship1_lights = (s1.masthead_light_on && s1.sidelight_on);
    ship2_lights = (s2.masthead_light_on && s2.sidelight_on);
    bothSafety   = (ship1_lights && ship2_lights);
  }
  Assertion {
    MultiShipSafety: bothSafety;
  }
}
```

### Temporal / Liveness (LTL block)

Use `LTL { }` for temporal properties; never place temporal operators inside `Assertion { }`.

```property
property {
  define {
    lightsNeeded = (s1.visibility < 500);
    lightsActive = (s1.masthead_light_on);
  }
  LTL {
    Liveness: G(lightsNeeded -> F(lightsActive));
  }
}
```
