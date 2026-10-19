"""Architecture rule: SRL may rely on ``sqe:`` but must not rely on ``salg:`` (the query-algebra vocabulary).

Four measurable ways SRL could depend on ``salg:``, each its own test; three are strict xfails while the dependency
exists (the failure message is the inventory). When a dependency is removed the test XPASSes and must have its
marker deleted, so the list can only shrink.

Measured 2026-10-19: the srl: *trees* use only four salg: terms (all for triple terms); the graphs SRL validates
against are dominated by salg: (every salg: shape and class is loaded); a few source lines name it. The
expression vocabulary ``spexpr:`` is already free of salg: IRIs (a passing guard below).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from rdflib import URIRef

from .corpus import CASES
from .helpers import srl_parse_to_tree

SALG = "https://github.com/hidden-graph/starlayer/ns/sparql/algebra#"
STARLAYER = Path(__file__).resolve().parents[3] / "starlayer"

# Representative cases: triple terms, expressions of every family, functions, negation, data, paths.
TREE_CASES = [c for c in CASES if c.id in {
    "rdf12-triple-term", "rdf12-triple-term-nested", "rdf12-reified-triple", "head-triple-term", "data-triple-term",
    "body-filter-brackets", "body-filter-builtin", "body-set", "body-not", "expr-in", "expr-builtin-nesting",
    "expr-unary-not", "pat-path-sequence", "data-simple", "rule-where-data",
}]


def _salg_terms(graph) -> set[str]:
    return {str(t) for triple in graph for t in triple if isinstance(t, URIRef) and str(t).startswith(SALG)}


def _local(iri: str) -> str:
    return iri[len(SALG):]


@pytest.mark.srl_conformance
@pytest.mark.xfail(strict=True, reason=(
    "srl: trees encode triple terms with salg:TripleTerm / salg:subject / salg:predicate / salg:object "
    "(ast_vocab.py re-exports salg's vocabulary). Everything else in the tree is srl: or spexpr:."))
def test_trees_contain_no_salg_terms():
    found: set[str] = set()
    for case in TREE_CASES:
        graph, _ = srl_parse_to_tree(case.text)
        found |= _salg_terms(graph)
    assert not found, f"salg: terms in srl: trees: {sorted(map(_local, found))}"


@pytest.mark.srl_conformance
@pytest.mark.xfail(strict=True, reason=(
    "srl_validate() builds its ontology and shapes by adding the WHOLE salg: ontology and shapes graphs "
    "(sparql_owl / sparql_shacl) to srl:'s own, because the expression shapes it reuses are defined there."))
def test_validation_graphs_do_not_load_salg():
    from starlayer.sparql.srl import _ontology_graph, _shapes_graph

    ontology, shapes = _salg_terms(_ontology_graph()), _salg_terms(_shapes_graph())
    assert not ontology and not shapes, f"salg: terms: {len(ontology)} in the ontology, {len(shapes)} in the shapes"


@pytest.mark.srl_conformance
def test_expression_vocabulary_does_not_reference_salg():
    """Already true: spexpr: (the expression vocabulary SRL uses) contains no salg: IRIs. Text mentions of "salg"
    in its files are comments and prefix declarations only. Kept as a guard so it stays true."""
    from starlayer import starontology

    terms = _salg_terms(starontology.get_ontology_graph("spexpr_owl")) | _salg_terms(starontology.get_ontology_graph("spexpr_shacl"))
    assert not terms, f"{len(terms)} salg: terms in spexpr: {sorted(map(_local, terms))[:12]}"


@pytest.mark.srl_conformance
@pytest.mark.xfail(strict=True, reason=(
    "srl.py loads the salg ontology and shapes by name (sparql_owl / sparql_shacl), and ast_vocab.py, "
    "srl_shapes.ttl and srl-ontology.ttl name salg: in code or data."))
def test_srl_source_does_not_mention_salg():
    files = ["sparql/srl.py", "sparql/srl_eval.py", "sparql/srl_semantic_checks.py", "sparql/_srl_ast.py",
             "sparql/ast_vocab.py", "starontology/srl_shapes.ttl", "starontology/srl-ontology.ttl"]
    mentions = {}
    for name in files:
        count = len(re.findall(r"salg", (STARLAYER / name).read_text(encoding="utf-8"), flags=re.IGNORECASE))
        if count:
            mentions[name] = count
    assert not mentions, f"salg mentions: {mentions}"
