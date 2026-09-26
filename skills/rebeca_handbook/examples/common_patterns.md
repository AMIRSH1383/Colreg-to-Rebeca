# Common Rebeca Modeling Patterns

## Actor Initialization Pattern
```rebeca
reactiveclass Ship(10) {
  knownrebecs { MapServer map; }
  statevars { int id; }
  
  Ship(int vessel_id, MapServer m) {
    id = vessel_id;
    map = m;
  }
}
```

## Message Handler Pattern
```rebeca
msgsrv updateState(int new_value) {
  state_variable = new_value;
  other_actor.notify(id);
}
```

## Conditional State Update Pattern
```rebeca
msgsrv processMessage(int value) {
  if (value > threshold) {
    state_variable = true;
  } else {
    state_variable = false;
  }
}
```

## Property Define Pattern
```
define {
  condition1 = (actor.var1 > 0);
  condition2 = (actor.var2 == expected);
  combined = (condition1 && condition2);
}
```

## Assertion Pattern
```
Assertion {
  Safety: !precondition || postcondition;
  Safety2: !precondition || (postcondition1 && postcondition2);
}
```

## Temporal Logic Pattern
```
LTL {
  Liveness: G(need -> F(satisfied));
  Safety: G(!(bad1 && bad2));
  Fairness: GF(eventually_true);
}
```
