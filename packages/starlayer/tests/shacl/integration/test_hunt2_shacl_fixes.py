"""SHACL fixes from the second adversarial hunt (GitHub issue #82)."""

import warnings

import pytest
import starlayer.shacl as shacl
from rdflib import Graph, URIRef
from starlayer.graph import StarLayerGraph, TripleTerm
from starlayer.shacl import StarShaclSchema
from starlayer.shacl.paths import path_values

warnings.simplefilter("ignore")
PREFIXES = (
    "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
)
EX = lambda name: URIRef("http://ex/" + name)  # noqa: E731


def _graph(ttl):
    g = StarLayerGraph()
    g.parse(data=PREFIXES + ttl, format="turtle12")
    return g


def _infer(shapes, data):
    result = shacl.apply_rules(_graph(data), _graph(shapes), meta_shacl=False)
    return set(result.inferred_graph)


def test_close_shape_works_on_a_shape_without_a_class():
    shapes = _graph("ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .")
    closed = StarShaclSchema(shacl_graph=shapes).close_shape(EX("S"))
    assert (EX("S"), URIRef("http://www.w3.org/ns/shacl#closed"), None) in closed


def test_triple_rule_without_sh_subject_uses_the_focus_node():
    inferred = _infer(
        "ex:P a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:R . "
        "ex:R a sh:TripleRule ; sh:predicate ex:childCount ; sh:object [ shnex:count [ shnex:pathValues ex:child ] ] .",
        "ex:Dad a ex:Person ; ex:child ex:D, ex:S .",
    )
    assert [(s, p) for s, p, _o in inferred] == [(EX("Dad"), EX("childCount"))]
    assert [str(o) for _s, _p, o in inferred] == ["2"]


def test_triple_rule_example_without_subject_and_with_a_constant_object():
    inferred = _infer(
        "ex:P a sh:NodeShape ; sh:targetClass ex:Person ; sh:rule ex:R . "
        "ex:R a sh:TripleRule ; sh:predicate rdf:type ; sh:object ex:Square .",
        "ex:Dad a ex:Person .",
    )
    assert inferred == {(EX("Dad"), URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), EX("Square"))}


@pytest.mark.parametrize(
    "head",
    ['sh:subject sh:this ; sh:predicate "p" ; sh:object 1', "sh:subject 5 ; sh:predicate ex:p ; sh:object 1"],
)
def test_triple_rule_skips_ill_formed_triples(head):
    inferred = _infer(f"ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule [ a sh:TripleRule ; {head} ] .", "ex:a ex:q 1 .")
    assert inferred == set()


def test_triple_rule_still_infers_a_well_formed_triple():
    inferred = _infer(
        "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ; sh:object 1 ] .",
        "ex:a ex:q 1 .",
    )
    assert len(inferred) == 1


def test_rule_set_accepts_an_iterable_of_rule_sets():
    shapes = (
        "ex:S a sh:NodeShape ; sh:targetNode ex:a . "
        "ex:RS1 a sh:RuleSet ; sh:hasRule ex:R1 . ex:RS2 a sh:RuleSet ; sh:hasRule ex:R2 . "
        "ex:R1 a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:q1 ; sh:object 1 . "
        "ex:R2 a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:q2 ; sh:object 2 . "
        "ex:S sh:rule ex:R1, ex:R2 ."
    )
    shapes_graph = _graph(shapes)
    for rule_set, predicates in [
        (EX("RS1"), {EX("q1")}),
        ([EX("RS1"), EX("RS2")], {EX("q1"), EX("q2")}),
        ((EX("RS2"),), {EX("q2")}),
    ]:
        result = shacl.apply_rules(_graph("ex:a ex:z 0 ."), shapes_graph, rule_set=rule_set, meta_shacl=False)
        assert {p for _s, p, _o in result.inferred_graph} == predicates


def _conforms(shapes, data=None, setup=None):
    d = _graph(data or "")
    if setup:
        setup(d)
    return shacl.validate(d, _graph(shapes), meta_shacl=False).conforms


def _with_triple_term(d):
    d.add((EX("a"), EX("p"), TripleTerm(EX("x"), EX("y"), EX("z"))))


@pytest.mark.parametrize(
    ("kind", "accepts"),
    [
        ("sh:IRI", False),
        ("sh:BlankNodeOrIRI", False),
        ("sh:IRIOrLiteral", False),
        ("sh:Literal", False),
        ("sh:BlankNode", False),
        ("sh:BlankNodeOrLiteral", False),
        ("sh:TripleTerm", True),
        ("(sh:IRI)", False),
        ("(sh:IRI sh:TripleTerm)", True),
    ],
)
def test_node_kind_of_a_triple_term(kind, accepts):
    shapes = f"ex:S sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:nodeKind {kind} ] ."
    assert _conforms(shapes, "ex:a a ex:C .", _with_triple_term) is accepts


@pytest.mark.parametrize(
    ("kind", "ttl", "accepts"),
    [
        ("sh:IRI", "ex:a ex:p ex:o", True),
        ("sh:IRI", "ex:a ex:p 1", False),
        ("sh:IRI", "ex:a ex:p [ ex:q 1 ]", False),
        ("sh:BlankNodeOrIRI", "ex:a ex:p [ ex:q 1 ]", True),
        ("sh:BlankNodeOrIRI", "ex:a ex:p 1", False),
        ("sh:IRIOrLiteral", "ex:a ex:p 1", True),
        ("sh:IRIOrLiteral", "ex:a ex:p [ ex:q 1 ]", False),
        ("sh:BlankNodeOrLiteral", "ex:a ex:p ex:o", False),
    ],
)
def test_single_node_kind_still_works_on_ordinary_values(kind, ttl, accepts):
    shapes = f"ex:S sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:nodeKind {kind} ] ."
    assert _conforms(shapes, ttl + " .") is accepts


DATA = ":a :p :b . :b :q :c . :c :p :d . :d :p :a . :x :p :b ."


@pytest.mark.parametrize(
    ("sparql_path", "shacl_path"),
    [
        ("^(:p/:q)", "[ sh:inversePath ( :p :q ) ]"),
        ("^(^:p)", "[ sh:inversePath [ sh:inversePath :p ] ]"),
        ("^(:p*)", "[ sh:inversePath [ sh:zeroOrMorePath :p ] ]"),
        ("^(:p+)", "[ sh:inversePath [ sh:oneOrMorePath :p ] ]"),
        ("^(:p?)", "[ sh:inversePath [ sh:zeroOrOnePath :p ] ]"),
        ("^(:p|:q)", "[ sh:inversePath [ sh:alternativePath ( :p :q ) ] ]"),
        ("^(^:p/:q)", "[ sh:inversePath ( [ sh:inversePath :p ] :q ) ]"),
    ],
)
@pytest.mark.parametrize("focus", ["a", "b", "c", "d"])
def test_inverse_of_a_composite_path_matches_sparql(sparql_path, shacl_path, focus):
    data = StarLayerGraph()
    data.parse(data="@prefix : <http://e/> . " + DATA, format="turtle12")
    oracle = Graph().parse(data="@prefix : <http://e/> . " + DATA, format="turtle")
    shapes = StarLayerGraph()
    shapes.parse(
        data="@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix : <http://e/> . :S sh:path " + shacl_path + " .",
        format="turtle12",
    )
    root = next(shapes.objects(URIRef("http://e/S"), URIRef("http://www.w3.org/ns/shacl#path")))
    got = {str(v) for v in path_values(data, URIRef("http://e/" + focus), root, shapes)}
    expected = {str(r[0]) for r in oracle.query(f"PREFIX : <http://e/> SELECT ?v {{ :{focus} {sparql_path} ?v }}")}
    assert got == expected
