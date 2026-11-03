"""The plan serialises to JSON and back without loss (``plan_json``), and the component/operator table is complete
(``component_table``)."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyoxigraph as ox
import pytest
from pyoxigraph import BlankNode as BNode
from pyoxigraph import Literal
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl_engine import validate
from starlayer.shacl_engine.component_table import component_table
from starlayer.shacl_engine.components.registry import REGISTRY
from starlayer.shacl_engine.expressions import OPERATORS
from starlayer.shacl_engine.plan import Plan
from starlayer.shacl_engine.plan_json import (
    FORMAT_VERSION,
    main,
    plan_from_json,
    plan_to_json,
    term_from_json,
    term_to_json,
)
from starlayer.shacl_engine.terms import XSD, integer
from tests.shacl.w3c_shacl12.comparison import find_report_node, result_multiset
from tests.shacl.w3c_shacl12.manifest import (
    clone_graph,
    iter_manifest_entries,
    load_document,
    uri_to_path,
)
from tests.shacl.w3c_shacl12.namespaces import MF, SHT
from tests.shacl.w3c_shacl12.test_w3c_validate import TOP_MANIFEST, VENDOR_ROOT

SUITE_TESTS = VENDOR_ROOT / "tests"
DOC = Path(__file__).resolve().parents[4] / "docs" / "working" / "shacl-engine-plan-format.md"


def _graph_files() -> list[Path]:
    if not SUITE_TESTS.exists():
        return []
    return [p for p in sorted(SUITE_TESTS.rglob("*.ttl")) if not p.name.startswith("manifest")]


_FILES = _graph_files()


def _plan_of(path: Path) -> Plan | None:
    try:
        return Plan(shapes_graph=load_document(path))
    except Exception:  # noqa: BLE001  (fixtures the Turtle parser cannot read are covered by the W3C parse-health test)
        return None


# --------------------------------------------------------------------------------------------------------------------
# Terms


@pytest.mark.parametrize(
    "term",
    [
        URIRef("http://example.org/a"),
        BNode("b1"),
        Literal("plain"),
        Literal("01", datatype=XSD.integer),  # lexical form kept
        Literal("abc", datatype=XSD.byte),  # ill-formed kept
        Literal("hello", language="en-GB"),
        Literal("txt", language="ar", direction=ox.BaseDirection.RTL),
        Literal("x", datatype=XSD.string),
        ox.Triple(URIRef("http://e/s"), URIRef("http://e/p"), Literal("o", language="de")),
        ox.Triple(BNode("s"), URIRef("http://e/p"), ox.Triple(URIRef("http://e/a"), URIRef("http://e/b"), integer(1))),
    ],
)
def test_term_round_trip(term):
    obj = json.loads(json.dumps(term_to_json(term)))
    back = term_from_json(obj)
    assert back == term
    assert type(back) is type(term)
    if isinstance(term, ox.Literal):
        assert back.value == term.value and back.datatype == term.datatype and back.language == term.language


def test_term_tags_are_explicit():
    assert term_to_json(URIRef("http://e/a")) == {"t": "iri", "v": "http://e/a"}
    assert term_to_json(Literal("a", language="en")) == {"t": "lit", "v": "a", "dt": None, "lang": "en", "dir": None}
    assert term_to_json(Literal("a", language="en", direction=ox.BaseDirection.LTR))["dir"] == "ltr"


# --------------------------------------------------------------------------------------------------------------------
# Round trip over every graph of the vendored W3C suites


@pytest.mark.skipif(not _FILES, reason="vendored W3C SHACL 1.2 suite not present")
@pytest.mark.parametrize("path", _FILES, ids=[str(p.relative_to(SUITE_TESTS)) for p in _FILES])
def test_round_trip_suite_graph(path):
    plan = _plan_of(path)
    if plan is None:
        pytest.skip("fixture does not parse")
    obj = json.loads(json.dumps(plan_to_json(plan)))  # through real JSON text
    assert obj["format_version"] == FORMAT_VERSION
    back = plan_from_json(obj)
    assert list(back.all_shape_nodes()) == list(plan.all_shape_nodes())
    for s in obj["shapes"]:
        node = term_from_json(s["node"])
        assert back.shape(node) == plan.shape(node)  # Shape dataclass equality
    # a second serialisation of the rebuilt plan is identical: the format is a fixed point
    again = json.loads(json.dumps(plan_to_json(back)))
    assert again["shapes"] == obj["shapes"]
    assert again["declared"] == obj["declared"]


@pytest.mark.skipif(not _FILES, reason="vendored W3C SHACL 1.2 suite not present")
def test_suite_round_trip_counts():
    plans = [p for p in (_plan_of(f) for f in _FILES) if p is not None]
    shapes = sum(len(plan_to_json(p)["shapes"]) for p in plans)
    assert len(plans) >= 300 and shapes >= 400


def _validate_entries():
    if not TOP_MANIFEST.exists():
        return []
    out = []
    for e in iter_manifest_entries(TOP_MANIFEST):
        path = str(e.source_path).replace("\\", "/")
        if e.entry_type == SHT.Validate and any(f"/tests/{d}/" in path for d in ("core", "sparql", "node-expr")):
            out.append(e)
    return out


_ENTRIES = _validate_entries()


def _g(entry, pred):
    action = next(entry.graph.objects(entry.iri, MF.action))
    return clone_graph(load_document(uri_to_path(next(entry.graph.objects(action, pred)))), OxGraph)


@pytest.mark.skipif(not _ENTRIES, reason="vendored W3C SHACL 1.2 suite not present")
def test_rebuilt_plan_validates_like_the_original():
    """Run every Validate entry with the plan rebuilt from JSON (shapes graph replaced by the term store) and compare the
    outcome with the original plan's: same conformance and result multiset, or both fail."""
    compared = mismatches = 0
    bad: list[str] = []
    for entry in _ENTRIES:
        data, shapes = _g(entry, SHT.dataGraph), _g(entry, SHT.shapesGraph)
        try:
            plan = Plan(shapes_graph=shapes)
            rebuilt = plan_from_json(json.loads(json.dumps(plan_to_json(plan))))
        except Exception:  # noqa: BLE001  (a malformed shapes graph: the original fails at validation too)
            continue
        try:
            want = validate(data, shapes)
        except Exception:  # noqa: BLE001
            want = None
        try:
            got = validate(data, shapes, plan=rebuilt)
        except Exception:  # noqa: BLE001
            got = None
        compared += 1
        if want is None or got is None:
            ok = want is None and got is None
        else:
            ok = want.conforms == got.conforms and result_multiset(
                got.report_graph, find_report_node(got.report_graph)
            ) == result_multiset(want.report_graph, find_report_node(want.report_graph))
        if not ok:
            mismatches += 1
            bad.append(str(entry.iri))
    assert compared >= 150
    assert mismatches == 0, bad[:10]


# --------------------------------------------------------------------------------------------------------------------
# Content, rules, prefixes, CLI

SHAPES_TTL = """
@prefix sh: <http://www.w3.org/ns/shacl#> .
@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
ex:PrefixDecl sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
ex:Person a sh:NodeShape ; sh:targetClass ex:Person ; sh:closed true ;
  sh:property ex:nameShape ; sh:property [ sh:path [ sh:inversePath ex:knows ] ; sh:minCount 1 ] ;
  sh:or ( ex:A ex:B ) ;
  sh:sparql [ sh:prefixes ex:PrefixDecl ; sh:select "SELECT $this WHERE { $this ex:bad ?x }" ; sh:message "bad {?x}"@en ] .
ex:nameShape sh:path ex:name ; sh:datatype xsd:string ; sh:minLength "01"^^xsd:integer ; sh:node ex:Child ;
  sh:severity sh:Warning ; sh:message "name"@en--ltr .
ex:A a sh:NodeShape ; sh:not ex:Child .
ex:B a sh:NodeShape ; sh:deactivated true .
ex:Child a sh:NodeShape ; sh:nodeKind sh:IRI .
ex:Rule a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ; sh:object ex:o ; sh:order 2 ; sh:condition ex:A .
"""


def _plan_from_text(text: str) -> Plan:
    g = OxGraph()
    g.parse(data=text, format="turtle")
    return Plan(shapes_graph=g)


def test_reachable_shapes_and_sections():
    obj = json.loads(json.dumps(plan_to_json(_plan_from_text(SHAPES_TTL))))
    nodes = {s["node"]["v"] for s in obj["shapes"] if s["node"]["t"] == "iri"}
    assert {"http://example.org/" + n for n in ("Person", "nameShape", "A", "B", "Child")} <= nodes
    # the anonymous property shape is reachable through sh:property
    assert any(s["node"]["t"] == "bnode" and s["is_property"] for s in obj["shapes"])
    assert obj["rules"] and obj["rules"][0]["order"] == 2.0 and obj["rules"][0]["conditions"]
    assert obj["prefixes"]["holders"][0]["declarations"] == {"ex": "http://example.org/"}
    name = next(s for s in obj["shapes"] if s["node"]["v"] == "http://example.org/nameShape")
    assert name["messages"][0]["dir"] == "ltr" and name["severity"]["v"].endswith("#Warning")
    assert name["params"]["http://www.w3.org/ns/shacl#minLength"][0]["v"] == "1"  # the store writes "01"^^xsd:integer as "1"
    assert obj["graph"]  # the term store holds the sh:sparql node and the sh:or list


def test_from_json_with_given_graph_and_version_check():
    plan = _plan_from_text(SHAPES_TTL)
    obj = plan_to_json(plan)
    back = plan_from_json(obj, shapes_graph=plan.shapes_graph)
    assert back.shapes_graph is plan.shapes_graph
    with pytest.raises(ValueError):
        plan_from_json({**obj, "format_version": 999})


def test_malformed_shape_is_a_recorded_plan_error():
    plan = _plan_from_text(
        "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://e/> . ex:S a sh:NodeShape ; sh:path ex:a, ex:b ."
    )
    obj = plan_to_json(plan)
    assert [e["node"]["v"] for e in obj["errors"]] == ["http://e/S"]
    from starlayer.shacl_engine.plan import ShapeError

    with pytest.raises(ShapeError):
        plan_from_json(json.loads(json.dumps(obj))).shape(URIRef("http://e/S"))


def test_cli(tmp_path, capsys):
    f = tmp_path / "shapes.ttl"
    f.write_text(SHAPES_TTL)
    assert main([str(f)]) == 0
    obj = json.loads(capsys.readouterr().out)
    assert obj["format_version"] == FORMAT_VERSION and obj["shapes"]


# --------------------------------------------------------------------------------------------------------------------
# The component / operator table


def test_every_registered_component_is_in_the_table_and_annotated():
    rows = {r["component"]: r for r in component_table()["components"]}
    assert set(rows) == {k.value for k in REGISTRY}
    unannotated = [k for k, r in rows.items() if not r["annotated"]]
    assert not unannotated, f"add them to _COMPONENT_META in component_table.py: {unannotated}"
    for iri, spec in REGISTRY.items():
        row = rows[iri.value]
        assert set(row["parameters"]) == {p.value for p in spec.predicates}
        assert set(row["required"]) | set(row["optional"]) <= set(row["parameters"])
        assert row["scope"] in ("value_node", "focus_node")
        assert row["needs"]["graph"] is True


def test_every_registered_operator_is_in_the_table_and_annotated():
    rows = {r["operator"]: r for r in component_table()["operators"]}
    assert set(rows) == {k.value for k in OPERATORS}
    unannotated = [k for k, r in rows.items() if not r["annotated"]]
    assert not unannotated, f"add them to _OPERATOR_META / _SPARQL_FN_ARITY in component_table.py: {unannotated}"


def test_table_flags():
    rows = {r["component"].rsplit("#", 1)[-1]: r for r in component_table()["components"]}
    assert rows["UniqueValuesForConstraintComponent"]["needs"]["cross_focus"] is True
    assert rows["SPARQLConstraintComponent"]["needs"]["sparql"] is True
    assert rows["NotConstraintComponent"]["needs"]["conforms"] is True
    assert rows["MinCountConstraintComponent"]["needs"] == {
        "graph": True, "shapes_graph": False, "sparql": False, "conforms": False, "cross_focus": False,
    }  # fmt: skip
    assert sum(r["needs"]["cross_focus"] for r in rows.values()) == 1


# --------------------------------------------------------------------------------------------------------------------
# The doc's JSON Schema block stays in step with the serialiser


def test_doc_schema_lists_the_serialiser_keys():
    if not DOC.exists():
        pytest.skip("doc not present")
    m = re.search(r"```json schema\n(.*?)```", DOC.read_text(), re.S)
    assert m, "the doc must contain a ```json schema block"
    schema = json.loads(m.group(1))
    obj = plan_to_json(_plan_from_text(SHAPES_TTL))
    assert set(schema["properties"]) == set(obj)
    assert set(schema["required"]) == set(obj)
    shape_keys = set(obj["shapes"][0])
    assert set(schema["$defs"]["shape"]["properties"]) == shape_keys
