"""The meta-shapes graph is the W3C Working Group's SHACL-for-SHACL plus additions (scripts/build_meta_shapes.py).

These tests keep the additions honest as the Working Group's file evolves. Each addition exists because the pinned file
rejects a shapes graph SHACL 1.2 allows, so each test shows that the pinned file *still* rejects it. When a test here
fails after the pinned copy is updated, upstream has fixed the problem: drop the matching addition from
build_meta_shapes.py and rebuild. Run ``python scripts/check_wg_shacl_shacl.py`` to see whether upstream has moved."""

import re

import pyshacl
import pytest
from build_meta_shapes import (
    RELAXED_PATHS,
    WG_VENDORED_FROM_PATH,
    _type_shape_values,
    build_meta_shapes_graph,
    load_wg_shapes,
    wg_file_sha256,
)
from rdflib import Graph, URIRef

SH = "http://www.w3.org/ns/shacl#"
_PREFIXES = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
)

# Valid SHACL 1.2 shapes graphs, one per predicate whose Working Group rule is still too strict ...
STILL_TOO_STRICT = {
    "nodeKind": "ex:S a sh:NodeShape ; sh:nodeKind ( sh:IRI sh:Literal ) .",
    "disjoint": "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:disjoint ( ex:a ex:b ) ] .",
    "equals": "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:equals ( ex:a ex:b ) ] .",
    "lessThan": "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:lessThan ( ex:a ex:b ) ] .",
    "lessThanOrEquals": "ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:lessThanOrEquals ( ex:a ex:b ) ] .",
}
# ... and ones the Working Group has already fixed, which its file must keep accepting.
FIXED_UPSTREAM = {
    "class": "ex:S a sh:NodeShape ; sh:class ( ex:A ex:B ) .",
    "datatype": "ex:S a sh:NodeShape ; sh:datatype ( xsd:string xsd:integer ) .",
    "closed ByTypes": "ex:S a sh:NodeShape ; sh:closed sh:ByTypes .",
}
EXPRESSION_ONLY_PROPERTY_SHAPE = "ex:S a sh:NodeShape ; sh:property [ sh:expression [ shnex:pathValues ex:p ] ] ."


def _conforms(shapes_ttl: str, meta: Graph) -> bool:
    shapes = Graph()
    shapes.parse(data=_PREFIXES + shapes_ttl, format="turtle")
    conforms, _, _ = pyshacl.validate(shapes, shacl_graph=meta, max_validation_depth=30)
    return conforms


@pytest.fixture(scope="module")
def wg_alone() -> Graph:
    return _type_shape_values(load_wg_shapes())


@pytest.fixture(scope="module")
def assembled() -> Graph:
    return build_meta_shapes_graph()


def test_the_pinned_file_matches_its_provenance_record() -> None:
    recorded = re.search(r"SHA-256 of the file: `([0-9a-f]{64})`", open(WG_VENDORED_FROM_PATH).read())
    assert recorded, "VENDORED_FROM.md must record the file's SHA-256"
    assert wg_file_sha256() == recorded.group(1), (
        "the pinned Working Group file changed but VENDORED_FROM.md was not updated (or the reverse)"
    )


def test_the_overrides_cover_every_relaxed_path() -> None:
    assert {str(p).removeprefix(SH) for p in RELAXED_PATHS} == set(STILL_TOO_STRICT)


@pytest.mark.parametrize("name", sorted(STILL_TOO_STRICT))
def test_the_working_group_file_still_rejects_it_and_the_assembled_graph_accepts_it(name, wg_alone, assembled) -> None:
    ttl = STILL_TOO_STRICT[name]
    assert not _conforms(ttl, wg_alone), (
        f"the pinned Working Group file now accepts a list-valued/path-valued sh:{name}: upstream fixed it, so "
        f"remove sh:{name} from RELAXED_PATHS in scripts/build_meta_shapes.py and rebuild"
    )
    assert _conforms(ttl, assembled)


@pytest.mark.parametrize("name", sorted(FIXED_UPSTREAM))
def test_what_the_working_group_has_fixed_it_still_accepts(name, wg_alone, assembled) -> None:
    assert _conforms(FIXED_UPSTREAM[name], wg_alone), f"the Working Group file stopped accepting {name}"
    assert _conforms(FIXED_UPSTREAM[name], assembled)


def test_the_working_group_file_still_rejects_an_expression_based_property_shape(wg_alone, assembled) -> None:
    assert not _conforms(EXPRESSION_ONLY_PROPERTY_SHAPE, wg_alone), (
        "the Working Group file now accepts a property shape with sh:expression and no sh:path: drop the "
        "PropertyShapeShape/NodeShapeShape additions in _add_overrides"
    )
    assert _conforms(EXPRESSION_ONLY_PROPERTY_SHAPE, assembled)


def test_every_predicate_the_working_group_file_constrains_is_constrained_by_the_assembled_graph(wg_alone, assembled) -> None:
    def constrained(graph: Graph) -> set[URIRef]:
        out = {p for ps in graph.subjects(URIRef(SH + "path"), None) for p in graph.objects(ps, URIRef(SH + "path"))}
        out |= set(graph.objects(None, URIRef(SH + "targetSubjectsOf")))
        return {p for p in out if isinstance(p, URIRef) and str(p).startswith(SH)}

    assert constrained(wg_alone) <= constrained(assembled)


def test_the_assembled_graph_still_rejects_what_it_should(assembled) -> None:
    assert not _conforms("ex:S a sh:NodeShape ; sh:property [ sh:minCount 1 ] .", assembled)  # no path, no expression
    assert not _conforms('ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; sh:minCount "x" ] .', assembled)
