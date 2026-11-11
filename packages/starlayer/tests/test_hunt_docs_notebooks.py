"""Regression tests for guide prose that no longer matched the code (docs-notebooks hunt).

Each test reads the guide notebooks as JSON and checks a claim against the behaviour it describes.
"""

from __future__ import annotations

import json
import re
import warnings
from pathlib import Path

import pytest

GUIDES = Path(__file__).resolve().parents[3] / "docs" / "guides"

pytestmark = pytest.mark.skipif(not GUIDES.is_dir(), reason="guides are not in this checkout")


def _cells(name: str, kinds=("markdown",)) -> list[str]:
    nb = json.loads((GUIDES / name).read_text(encoding="utf-8"))
    return ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] in kinds]


def _text(name: str, kinds=("markdown",)) -> str:
    return "\n".join(_cells(name, kinds))


def _all_guides() -> list[str]:
    return sorted(p.name for p in GUIDES.glob("*.ipynb"))


def test_no_guide_describes_a_rename_to_itself():
    bad = []
    for name in _all_guides():
        for cell in _cells(name, ("markdown", "code")):
            for pat in (r"working names?\b", r"\bbecomes? `?StarLayer", r"rdflib-based (class|classes|graph class|one)", r"previous rdflib"):
                if re.search(pat, cell):
                    bad.append((name, pat))
    assert not bad, bad


def test_guide_01_names_the_class_once():
    t = _text("01-getting-started.ipynb")
    assert "working name" not in t
    assert "The graph class is `StarLayerGraph`" in t


def test_guide_05a_names_an_existing_validation_function():
    import starlayer.sparql as sp
    from starlayer.sparql.sqe.shapes import sqe_validate  # noqa: F401

    t = _text("05a-manchester-syntax.ipynb")
    assert not hasattr(sp, "validate_query")
    assert "validate_query" not in t


def test_guides_have_no_empty_code_span_and_registry_functions_return_one_class():
    for name in _all_guides():
        for cell in _cells(name):
            assert not re.search(r"(?<!`)``(?!`)", cell), (name, "empty code span")
    import inspect

    from starlayer import starontology as so
    from starlayer.graph.oxgraph import StarLayerGraph

    assert list(inspect.signature(so.get_ontology_graph).parameters) == ["name"]
    assert isinstance(so.get_ontology_graph("skos_owl"), StarLayerGraph)
    assert "keyword to ask for" not in _text("04e-shacl-profiling.ipynb")


def test_guide_04_does_not_say_node_kind_delegates_to_pyshacl():
    assert "pySHACL" not in _text("04-shacl-shapes.ipynb")


def test_guides_02b_02c_do_not_say_query_entailment_raises():
    from starlayer import StarLayerGraph
    from starlayer.graph import ENTAILMENT

    g = StarLayerGraph()
    g.parse(
        data="@prefix ex: <http://e.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . ex:A rdfs:subClassOf ex:B . ex:x a ex:A .",
        format="turtle",
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rows = list(g.query("SELECT ?x WHERE { ?x a <http://e.org/B> }", entailment=ENTAILMENT.RDFS))
    assert len(rows) == 1
    for name in ("02b-graphs-inferencing.ipynb", "02c-owl-dl-reasoning.ipynb"):
        t = _text(name)
        assert "not yet available" not in t, name
        assert "until the query-time rewrite" not in t, name
        assert "raises `NotImplementedError`" not in t, name


def test_guide_04_names_the_rule_error_class_that_exists():
    import starlayer.shacl_engine.rules as rules

    assert not hasattr(rules, "RuleLoadError")
    assert hasattr(rules, "RuleError")
    assert "RuleLoadError" not in _text("04-shacl-shapes.ipynb")


def test_guide_06b_service_silent_row_claim_matches_behaviour():
    from starlayer import StarLayerGraph

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        rows = list(StarLayerGraph().query("SELECT ?p WHERE { SERVICE SILENT <http://localhost:1/query> { ?p a <http://e.org/P> } }"))
    assert len(rows) == 1 and rows[0][0] is None
    assert "returns no rows" not in _text("06b-backend-graph-databases.ipynb")


def test_guide_04f_section_references_point_at_the_right_sections():
    nb = _text("04f-shacl-subgraph-extraction.ipynb", ("markdown", "code"))
    heads = dict(re.findall(r"^## (\d+)\. (.*)$", nb, re.M))
    for m in re.finditer(r"[Ss]ection (\d+)(?:'s| below)? (staging pattern|commitment)|see section (\d+)\)", nb):
        n = m.group(1) or m.group(3)
        topic = m.group(2) or "hash"
        want = "pending addition" if topic == "staging pattern" else "hash"
        assert want in heads[n], (m.group(0), heads[n])


def test_guide_05b_scope_matches_what_the_encoder_accepts():
    from starlayer import StarLayerGraph
    from starlayer.sparql import sqe

    for q in ("DESCRIBE <urn:a>", "INSERT DATA { <urn:a> <urn:p> <urn:b> }", "CLEAR ALL"):
        tree, root = sqe.sqe_parse_to_tree(q, StarLayerGraph())
        assert sqe.sqe_tree_to_text(tree, root).startswith(q.split()[0])
    assert "does not cover `DESCRIBE`" not in _text("05b-sparql-query-as-rdf.ipynb")
