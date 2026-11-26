"""The end-state vocabulary of the ``manch:`` tree (docs/working/manchester-vocabulary-table-2026-11-25.md, decision of 2026-11-26): every
renamed family is written by the encoder, read back to the same text, accepted by the shapes, and no old name is left in the sources."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from starlayer.graph.manchester._ox_terms import RDF
from starlayer.starontology.manchester import MANCH, manchester_parse_to_tree, manchester_tree_to_text, manchester_validate

PACKAGE = Path(__file__).resolve().parents[3] / "starlayer"
FOLDER = PACKAGE / "starontology" / "manchester"
EX = "http://example.org/o#"

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

TEXT = f"""Prefix: : <{EX}>
Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>
Ontology: <http://example.org/o> <http://example.org/o/1>
Annotations: :note "an ontology"
Class: A
    Annotations: :note "x"
    SubClassOf: :p some :B, :p only :B, :p value :i, :p Self, :p min 1 :B, :p max 2 :B, :p exactly 3 :B,
        :p some {{:i, :j}}, inverse :p some :B, :d some xsd:integer, :d only xsd:integer, :d min 1 xsd:integer, :d max 2 xsd:integer, :d exactly 3 xsd:integer,
        :d value 5, :d min 2, :p exactly 1
    EquivalentTo: :B and :p some :B or not :B
    DisjointWith: :B
    DisjointUnionOf: :B, :C
    HasKey: :p
Class: B
Class: C
ObjectProperty: :p
    Domain: :A
    Range: :A
    SubPropertyOf: :q
    EquivalentTo: :q
    DisjointWith: :q
    InverseOf: :q
    Characteristics: Functional
    SubPropertyChain: :p o :q
    Annotations: :note "x"
ObjectProperty: :q
DataProperty: :d
    Domain: :A
    Range: xsd:integer[>= 1, < 10] and not xsd:integer[> 3] or {{1, 2}}
    SubPropertyOf: :e
    EquivalentTo: :e
    DisjointWith: :e
    Characteristics: Functional
    Annotations: :note "x"
DataProperty: :e
AnnotationProperty: :note
    Domain: :A
    Range: :A
    SubPropertyOf: :n2
    Annotations: :note "x"
AnnotationProperty: :n2
Individual: :i
    Types: :A
    Facts: :p :i, not :d 5
    SameAs: :j
    DifferentFrom: :k
    Annotations: :note "x"
Individual: :j
Individual: :k
Datatype: :dt
    EquivalentTo: xsd:integer[>= 1]
    Annotations: :note "x"
"""

CLASSES = {
    "OntologyDocument", "PrefixDeclaration", "Exactly", "Self", "DataSome", "DataOnly", "DataMin", "DataMax", "DataExactly", "DataAnd",
    "DataOr", "DataNot", "DataOneOf", "DatatypeRestriction", "Fact", "Annotation", "FacetRestriction", "OntologyHeader", "Inverse",
    "ObjectPropertyDomainClause", "ObjectPropertyRangeClause", "ObjectPropertySubPropertyOfClause", "ObjectPropertyEquivalentToClause",
    "ObjectPropertyDisjointWithClause", "ObjectPropertyInverseOfClause", "ObjectPropertyCharacteristicsClause",
    "ObjectPropertySubPropertyChainClause", "ObjectPropertyAnnotationsClause", "DataPropertyDomainClause", "DataPropertyRangeClause",
    "DataPropertySubPropertyOfClause", "DataPropertyEquivalentToClause", "DataPropertyDisjointWithClause",
    "DataPropertyCharacteristicsClause", "DataPropertyAnnotationsClause", "AnnotationPropertyDomainClause",
    "AnnotationPropertyRangeClause", "AnnotationPropertySubPropertyOfClause", "AnnotationPropertyAnnotationsClause",
}
PROPERTIES = {"prefixName", "namespace", "ontologyIRI", "versionIRI", "datatype", "facet", "restrictionValue", "annotationTarget"}
STAYS = {"Value", "Min", "Max", "Some", "Only", "And", "Or", "Not", "OneOf", "ClauseItem", "ClassExpression", "PropertyExpression", "DataRange",
         "MiscAxiom", "annotationProperty", "onProperty", "filler", "cardinality", "operand", "operands", "individuals", "literals", "reversed"}


@pytest.fixture(scope="module")
def tree():
    return manchester_parse_to_tree(TEXT)


def _types(tree):
    return {o.value.rsplit("#", 1)[1] for _s, _p, o in tree.triples((None, RDF.type, None))}


def _predicates(tree):
    return {p.value.rsplit("#", 1)[1] for _s, p, _o in tree.triples((None, None, None)) if "manchester-ast#" in p.value}


def test_every_renamed_class_is_written_by_the_encoder(tree):
    assert CLASSES <= _types(tree)


def test_every_renamed_property_is_written_by_the_encoder(tree):
    assert PROPERTIES <= _predicates(tree)


def test_the_unrenamed_terms_are_still_written(tree):
    assert {"Value", "Min", "Max", "Some", "Only", "And", "Or", "Not", "ClauseItem", "OneOf"} <= _types(tree)
    assert {"annotationProperty", "onProperty", "filler", "cardinality", "operand", "operands", "individuals", "literals"} <= _predicates(tree)


def test_the_tree_validates_and_renders_back_to_text_that_parses_to_the_same_tree(tree):
    assert manchester_validate(tree).conforms
    again = manchester_parse_to_tree(manchester_tree_to_text(tree))
    assert manchester_validate(again).conforms
    assert _types(again) == _types(tree) and _predicates(again) == _predicates(tree)


@pytest.mark.parametrize(
    "keyword,cls",
    [("exactly", "Exactly"), ("Self", "Self")],
)
def test_the_restriction_keyword_is_the_class(keyword, cls):
    body = ":p Self" if keyword == "Self" else ":p exactly 2 :B"
    g = manchester_parse_to_tree(f"Prefix: : <{EX}>\nClass: A\n    SubClassOf: {body}\nClass: B\nObjectProperty: :p\n")
    assert cls in _types(g)
    assert keyword in manchester_tree_to_text(g)


@pytest.mark.parametrize("n,old", [(1, "DSome"), (2, "DExact")])
def test_a_data_restriction_has_no_d_prefixed_class(tree, n, old):
    assert old not in _types(tree)


def test_a_clause_class_is_the_frame_class_plus_the_keyword_plus_clause():
    ontology = (FOLDER / "manchester-ast-ontology.ttl").read_text()
    clauses = set(re.findall(r"^manch:(\w+Clause) ", ontology, re.M))
    from starlayer.starontology.manchester import _CLAUSE_CLASS

    assert clauses == {str(c.value).rsplit('#', 1)[1] for c in _CLAUSE_CLASS.values()}
    assert all(re.fullmatch(r"(Class|ObjectProperty|DataProperty|AnnotationProperty|Individual|Datatype)[A-Z]\w+Clause", c) for c in clauses)


def test_the_ontology_declares_the_new_terms():
    ontology = (FOLDER / "manchester-ast-ontology.ttl").read_text()
    declared = set(re.findall(r"^manch:(\w+) ", ontology, re.M))
    assert (CLASSES | PROPERTIES | STAYS) - declared == set()


def test_no_old_name_is_left_in_the_sources():
    old = re.compile(
        r"\b(ObjProp\w*|AnnProp\w*|DataProp(Annotations|Characteristic|Disjoint|Domain|Equivalent|Range|SubProperty)\w*"
        r"|DSome|DOnly|DMin|DMax|DExact|DAnd|DOr|DNot|DOneOf|DRestriction|SelfR|FactItem\w*|AnnotationAssertion\w*|PrefixDecl(?!aration)\w*"
        r"|DocumentShape|prefixLabel|prefixIri|ontologyIri|versionIri|facetPredicate|facetValue|annotationValue|onDatatype"
        r"|(?<!\w)manch:(Document|Exact))\b|\bExact(Shape)?\b"
    )
    found = []
    for f in FOLDER.glob("*.ttl"):
        found += [f"{f.name}:{n}: {line.strip()[:80]}" for n, line in enumerate(f.read_text().splitlines(), 1) if old.search(line)]
    source = (FOLDER / "__init__.py").read_text()
    qualified = re.compile(r"(MANCH\.|manch:)(Document|Exact|SelfR|D(Some|Only|Min|Max|Exact|And|Or|Not|OneOf)|DRestriction|FactItem|AnnotationAssertion|PrefixDecl(?!aration)|ObjProp\w+|AnnProp\w+|DataProp[A-Z]\w+Clause|prefixLabel|prefixIri|ontologyIri|versionIri|facetPredicate|facetValue|annotationValue|onDatatype)\b")
    found += [f"__init__.py:{n}: {line.strip()[:80]}" for n, line in enumerate(source.splitlines(), 1) if qualified.search(line)]
    assert not found, "\n".join(found)


def test_the_snapshots_match_the_live_files():
    snapshots = Path(__file__).resolve().parents[1] / "manchester_conformance" / "snapshots"
    for name in ("manchester-ast-ontology.ttl", "manchester_shapes.ttl"):
        assert (snapshots / name).read_text() == (FOLDER / name).read_text()
