"""
Shared sample content for rebeca_tooling tests.
"""

RULE_ID = "Rule-22"

SAMPLE_MODEL = """\
reactiveclass Ship(5) {
    statevars {
        boolean hasLight;
        int lightRange;
        int speed;
    }
    msgsrv initial() {
        hasLight = false;
        lightRange = 0;
        speed = 10;
    }
    msgsrv updateLight(boolean on, int range) {
        if (on) {
            hasLight = true;
            lightRange = range;
        }
    }
    msgsrv updateSpeed(int v) {
        speed = v + 1;
    }
}
main {
    Ship ship(5, 5);
}
"""

SAMPLE_PROPERTY = """\
property {
    define {
        hasLightOn = (ship.hasLight == true);
        rangeOk    = (ship.lightRange >= 6);
    }
    Assertion {
        Rule22: !hasLightOn || rangeOk;
    }
}
"""

SAMPLE_PROPERTY_AND = """\
property {
    define {
        cond1 = (ship.speed > 5);
        cond2 = (ship.lightRange < 100);
    }
    Assertion {
        Rule22: cond1 && cond2;
    }
}
"""

SAMPLE_PROPERTY_VARS = """\
property {
    Assertion {
        Rule22: ship.speed > ship.lightRange;
    }
}
"""
