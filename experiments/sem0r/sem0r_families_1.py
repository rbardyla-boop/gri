from __future__ import annotations

from sem0r_gen_core import nonce

def scalar_pair(i: int, invariant: bool):
    n = nonce("KEL", i)
    pair = f"SCALAR-{i:02d}"
    if invariant:
        a = [f"Some of the four {n} trials passed.", "The report gives no exact count of passing trials."]
        b = [f"Of the four {n} trials, some passed.", "The report gives no exact count of passing trials."]
        focus = f"Not all four {n} trials passed."
        common = [
            (focus, "IMPLICATED", ["S1"]),
            (f"At least one {n} trial passed.", "ENTAILED", ["S1"]),
            (f"Exactly two {n} trials passed.", "UNKNOWN", []),
            (f"No {n} trial passed.", "CONTRADICTED", ["S1"]),
            (f"All four {n} trials passed.", "UNKNOWN", []),
            (f"The report states an exact number of passing {n} trials.", "CONTRADICTED", ["S2"]),
            (f"Some of the four {n} trials passed.", "ASSERTED", ["S1"]),
            (f"At least three {n} trials passed.", "UNKNOWN", []),
        ]
        return (pair, "INVARIANCE", (a, common, 0, "some_initial"), (b, common, 0, "some_fronted"))

    a = [f"Some of the four {n} trials passed."]
    b = [f"Some of the four {n} trials passed.", f"In fact, all four {n} trials passed."]
    props_a = [
        (f"Not all four {n} trials passed.", "IMPLICATED", ["S1"]),
        (f"At least one {n} trial passed.", "ENTAILED", ["S1"]),
        (f"Exactly two {n} trials passed.", "UNKNOWN", []),
        (f"No {n} trial passed.", "CONTRADICTED", ["S1"]),
        (f"Some of the four {n} trials passed.", "ASSERTED", ["S1"]),
        (f"All four {n} trials passed.", "UNKNOWN", []),
        (f"Exactly one {n} trial passed.", "UNKNOWN", []),
        (f"At least two {n} trials passed.", "UNKNOWN", []),
    ]
    props_b = [
        (f"Not all four {n} trials passed.", "CONTRADICTED", ["S2"]),
        (f"At least one {n} trial passed.", "ENTAILED", ["S2"]),
        (f"Exactly two {n} trials passed.", "CONTRADICTED", ["S2"]),
        (f"No {n} trial passed.", "CONTRADICTED", ["S2"]),
        (f"All four {n} trials passed.", "ASSERTED", ["S2"]),
        (f"Some of the four {n} trials passed.", "ASSERTED", ["S1"]),
        (f"Exactly four {n} trials passed.", "ENTAILED", ["S2"]),
        (f"At least three {n} trials passed.", "ENTAILED", ["S2"]),
    ]
    return (pair, "REVISION", (a, props_a, 0, "some_plain"), (b, props_b, 0, "some_cancelled"))

def presupp_pair(i: int, invariant: bool):
    beacon = nonce("BEA", i)
    person = nonce("MIRA", i)
    pair = f"PRESUP-{i:02d}"
    focus = f"{beacon} failed."
    if invariant:
        a = [f"{person} realized that {beacon} failed."]
        b = [f"{person} did not realize that {beacon} failed."]
        props_a = [
            (focus, "PRESUPPOSED", ["S1"]),
            (f"{person} realized that {beacon} failed.", "ASSERTED", ["S1"]),
            (f"{person} caused {beacon} to fail.", "UNKNOWN", []),
            (f"{beacon} succeeded.", "CONTRADICTED", ["S1"]),
            (f"Someone knew that {beacon} failed.", "UNKNOWN", []),
            (f"{beacon} failed permanently.", "UNKNOWN", []),
            (f"{person} had evidence about {beacon}.", "UNKNOWN", []),
        ]
        props_b = [
            (focus, "PRESUPPOSED", ["S1"]),
            (f"{person} realized that {beacon} failed.", "CONTRADICTED", ["S1"]),
            (f"{person} caused {beacon} to fail.", "UNKNOWN", []),
            (f"{beacon} succeeded.", "CONTRADICTED", ["S1"]),
            (f"{person} did not realize that {beacon} failed.", "ASSERTED", ["S1"]),
            (f"{beacon} failed permanently.", "UNKNOWN", []),
            (f"{person} was surprised by the failure.", "UNKNOWN", []),
        ]
        return (pair, "INVARIANCE", (a, props_a, 0, "factive_affirmative"), (b, props_b, 0, "factive_negated"))
    a = [f"{person} realized that {beacon} failed."]
    b = [f"{person} believed that {beacon} failed."]
    props_a = [
        (focus, "PRESUPPOSED", ["S1"]),
        (f"{person} had a belief about {beacon}.", "ENTAILED", ["S1"]),
        (f"{beacon} succeeded.", "CONTRADICTED", ["S1"]),
        (f"{person} caused the failure.", "UNKNOWN", []),
        (f"{person} realized that {beacon} failed.", "ASSERTED", ["S1"]),
        (f"The failure happened yesterday.", "UNKNOWN", []),
        (f"{beacon} was operational before failing.", "UNKNOWN", []),
    ]
    props_b = [
        (focus, "UNKNOWN", []),
        (f"{person} had a belief about {beacon}.", "ENTAILED", ["S1"]),
        (f"{beacon} succeeded.", "UNKNOWN", []),
        (f"{person} caused the failure.", "UNKNOWN", []),
        (f"{person} believed that {beacon} failed.", "ASSERTED", ["S1"]),
        (f"The belief was correct.", "UNKNOWN", []),
        (f"The belief was false.", "UNKNOWN", []),
        (f"{beacon} definitely failed.", "UNKNOWN", []),
    ]
    return (pair, "REVISION", (a, props_a, 0, "factive_realize"), (b, props_b, 0, "nonfactive_believe"))
