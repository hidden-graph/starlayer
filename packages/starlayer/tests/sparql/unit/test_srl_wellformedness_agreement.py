"""The §4.2 well-formedness conditions are stated twice: as SHACL shapes (``srl_shapes.ttl``, what ``validate_sparql_tree`` reports) and as
Python (``srl_semantic_checks``, what refuses to run a rule set; a SPARQL constraint costs too much to run on every ``infer()``).
These tests keep them the same: over the §4.2 negative cases of the conformance suite, over the rule sets the other SRL tests use
to break one condition, and over seeded random rule sets (negations, groups, ``SET``, filters in any order), the two give the same
``(condition, variable)`` findings."""

from __future__ import annotations

import random

import pytest
from starlayer.errors import FormatError
from starlayer.sparql.srl import parse_ruleset, ruleset_to_tree
from starlayer.sparql.srl_semantic_checks import _check_ruleset
from tests.sparql.srl_conformance.corpus import PRELUDE
from tests.sparql.srl_conformance.test_sr_negative import WELL_FORMEDNESS
from tests.support.srl_wellformedness import findings

PREFIX = "PREFIX : <http://example.org/>\nPREFIX ex: <http://example.org/>\n"


def _python(ruleset) -> set[tuple[str, str | None]]:
    return {(issue.kind, None if issue.variable is None else issue.variable.value) for issue in _check_ruleset(ruleset)}


def _shapes(ruleset) -> set[tuple[str, str | None]]:
    _report, rows = findings(ruleset_to_tree(ruleset)[0])
    return {(kind, variable) for kind, variable, _focus in rows}


def _assert_agree(text: str) -> set:
    try:
        ruleset = parse_ruleset(text)
    except FormatError:
        return set()  # not in the grammar: neither check sees it
    python, shapes = _python(ruleset), _shapes(ruleset)
    assert shapes == python, f"shapes {sorted(map(str, shapes ^ python))} differ from Python for:\n{text}"
    return python


@pytest.mark.parametrize(("case_id", "text"), WELL_FORMEDNESS, ids=[c[0] for c in WELL_FORMEDNESS])
def test_the_conformance_suite_negative_cases_get_the_same_findings(case_id, text):
    found = _assert_agree(PRELUDE + text)
    if case_id not in ("not-inside-not", "set-inside-not", "head-variable-in-data"):  # refused by the grammar, or not a §4.2 finding
        assert found, f"{case_id}: neither check found anything"


@pytest.mark.parametrize(
    "text",
    [
        "RULE { ?x ex:r ?y } WHERE { <<( ?a ex:p ?b )>> ex:q ?y . ?x ex:s ?a }",
        "RULE { <<( ?a ex:p ?b )>> ex:q ?y } WHERE { ?a ex:p ?b . ?x ex:s ?y }",
        "DATA { <<( ex:a ex:p ex:b )>> ex:q ex:c . }",
        "DATA { ?x ex:p ex:o . }",
        "RULE { ?s :r ?\U00010000 } WHERE { ?s :p ?\U00010000 }",
        "RULE { ?x :n ?n } WHERE { ?x :p ?y . SET(?n := COUNT(?y)) }",
        "RULE { ?x :p ?z } WHERE { ?x :q ?y . SET (?z := ?w + 1) ?x :r ?w }",
        "RULE { :a :n ?n } WHERE { GROUP { ?x :r ?o } [ ?n := COUNT(*) , ?n := SUM(?o) ] }",
        "RULE { :a :n ?n } WHERE { GROUP { ?x :r ?o } [ ?n := SUM(?z) ] }",
        "RULE { ?x :n ?y } WHERE { ?x :q ?y . GROUP BY ?x { ?x :r ?o } [ ?y := COUNT(*) ] }",
        "RULE { ?x :n ?n } WHERE { ?x :q ?y . GROUP BY ?k { ?x :r ?o } [ ?n := COUNT(*) ] }",
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . GROUP BY ?x { ?x :r ?o } [ ?n := COUNT(*) ] ?o :s ?x }",
        "RULE { ?x :p ?y } WHERE { ?x :q ?y . NOT { ?x :r ?w } NOT { ?w :s ?x } }",
        "RULE { ?x :p ?w } WHERE { ?x :q ?y . NOT { ?x :r ?w } SET (?w := 1) }",
        "RULE { ?x :p ?n } WHERE { GROUP BY ?x { ?x :r ?o } [ ?c := COUNT(*) ] SET (?x := 1) SET (?n := ?c) }",
        "RULE { ?x :p ?n } WHERE { ?x :q ?y . GROUP BY ?x { ?x :r ?o SET (?o := 2) } [ ?n := COUNT(*) ] }",
        "RULE { ?x :p ?n } WHERE { ?x :q ?y . GROUP BY ?x { ?x :r ?o ?y :r ?o } [ ?n := COUNT(*) ] }",
    ],
)
def test_the_rule_sets_that_break_one_condition_get_the_same_findings(text):
    _assert_agree(PREFIX + text)


_VARIABLES = ["?a", "?b", "?c", "?d", "?e", "?f"]


def _random_rule_set(rnd: random.Random) -> str:
    """One rule over a small variable pool, mostly reusing names already used so that well-formed and ill-formed bodies both turn up."""
    seen: list[str] = []

    def pick() -> str:
        if seen and rnd.random() < 0.75:
            return rnd.choice(seen)
        seen.append(rnd.choice(_VARIABLES))
        return seen[-1]

    def triple() -> str:
        return f"{pick()} :p{rnd.randint(0, 1)} {pick()} ."

    def filter_() -> str:
        return f"FILTER({pick()} > {pick()})"

    def set_() -> str:
        return f"SET({pick()} := {pick()} + 1)"

    def aggregate_filter() -> str:
        return f"FILTER(COUNT({pick()}) > 1)"

    def negation() -> str:
        return "NOT { " + " ".join(rnd.choice([triple, triple, filter_])() for _ in range(rnd.randint(1, 3))) + " }"

    def group() -> str:
        keys = " ".join(pick() for _ in range(rnd.randint(0, 2)))
        pattern = " ".join(rnd.choice([triple, triple, filter_, set_])() for _ in range(rnd.randint(1, 3)))
        aggregations = []
        for _ in range(rnd.randint(1, 3)):
            function = rnd.choice(["COUNT", "MIN", "SUM"])
            argument = ("*" if rnd.random() < 0.2 else pick()) if function == "COUNT" else pick()
            aggregations.append(f"{pick()} := {function}({argument})")
        return f"GROUP BY {keys} {{ {pattern} }} [ {', '.join(aggregations)} ]"

    def triple_term() -> str:
        return f"{pick()} :p << {pick()} :q {pick()} >> ."

    elements = [triple, triple, triple, filter_, set_, negation, group, aggregate_filter, triple_term]
    body = " ".join(rnd.choice(elements)() for _ in range(rnd.randint(1, 5)))
    head = " ".join(f"{pick()} :h {pick()} ." for _ in range(rnd.randint(1, 2)))
    return f"RULE {{ {head} }} WHERE {{ {body} }}"


@pytest.mark.parametrize("seed", range(4))
def test_random_rule_sets_get_the_same_findings(seed):
    rnd = random.Random(seed)
    found: set[str] = set()
    for _ in range(60):
        found |= {kind for kind, _variable in _assert_agree(PREFIX + _random_rule_set(rnd))}
    assert len(found) >= 6  # the generator reaches a spread of conditions, not just one
