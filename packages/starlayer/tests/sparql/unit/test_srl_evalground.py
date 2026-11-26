"""The spec's flag is ``evalground`` (SRL draft 2026-11-19): the Python field and the RDF properties carry that name, with no alias for the old one."""

from __future__ import annotations

import re
import warnings
from pathlib import Path

from starlayer.sparql.srl import (
    parse_ruleset,
    ruleset_to_tree,
    srl_validate,
    tree_to_ruleset,
)
from starlayer.sparql.vocab import SQE  # noqa: F401 - the package is importable

PACKAGE = Path(__file__).resolve().parents[3] / "starlayer"
SRL_NS = "https://github.com/hidden-graph/starlayer/ns/sparql/srl#"
TEXT = "PREFIX : <http://e/> RULE { ?x :q ?y } WHERE GROUND { ?x :p ?y NOT GROUND { ?y :r ?x } }"


def _tree():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return ruleset_to_tree(parse_ruleset(TEXT))


def test_the_tree_writes_the_flags_as_ruleEvalground_and_negationEvalground():
    graph, _root = _tree()
    predicates = {p.value for _s, p, _o in graph.triples((None, None, None))}
    assert {SRL_NS + "ruleEvalground", SRL_NS + "negationEvalground"} <= predicates
    assert not any(p.endswith("Evaldata") for p in predicates)
    assert srl_validate(graph).conforms


def test_the_flag_round_trips_through_the_tree_and_the_python_field_is_evalground():
    graph, root = _tree()
    rule = tree_to_ruleset(graph, root).rules[0]
    assert rule.evalground is False and rule.body[1].evalground is False
    assert not hasattr(rule, "evaldata")


def test_a_tree_with_the_old_property_is_rejected_by_the_shapes():
    graph, _root = _tree()
    import pyoxigraph as ox

    for s, _p, o in list(graph.triples((None, ox.NamedNode(SRL_NS + "ruleEvalground"), None))):
        graph.remove((s, ox.NamedNode(SRL_NS + "ruleEvalground"), o))
        graph.add((s, ox.NamedNode(SRL_NS + "ruleEvaldata"), o))
    assert not srl_validate(graph).conforms


def test_no_evaldata_is_left_in_the_code_and_the_vocabulary_files():
    found = [str(p.relative_to(PACKAGE)) for p in sorted(PACKAGE.rglob("*")) if p.suffix in (".py", ".ttl") and re.search(r"(?i)evaldata", p.read_text())]
    assert not found, found
