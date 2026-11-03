"""``evaluate``, ``validate_each``, ``Outcome.report_text`` and ``Outcome.diagnostics`` of the engine against the old
validator on the same inline Turtle."""

from __future__ import annotations

import pytest
from pyoxigraph import Literal
from pyoxigraph import NamedNode as URIRef
from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.oxgraph import OxGraph
from starlayer.shacl import StarShaclSchema
from starlayer.shacl import evaluate as old_evaluate
from starlayer.shacl import validate as old_validate
from starlayer.shacl_engine import evaluate as new_evaluate
from starlayer.shacl_engine import validate, validate_each

PFX = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . @prefix sparql: <http://www.w3.org/ns/sparql#> . "
    "@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
)
EX = "http://example.org/"
RDFS = ENTAILMENT.RDFS


def g(ttl: str) -> OxGraph:
    graph = OxGraph()
    graph.parse(data=PFX + ttl, format="turtle")
    return graph


def both(data: str, shapes: str | None, **kw):
    old = old_evaluate(g(data), g(shapes) if shapes is not None else None, **kw)
    new = new_evaluate(g(data), g(shapes) if shapes is not None else None, **kw)
    return old, new


FRIENDS = "ex:alice a ex:Person ; ex:friend ex:bob, ex:carol . ex:dave a ex:Person ; ex:friend ex:erin ."
LABELS = 'ex:a a ex:Person ; ex:first "Ann" ; ex:last "Lee" . ex:b a ex:Person ; ex:first "Bo" ; ex:last "Ng" .'
LABEL_SHAPES = """ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:property [ sh:path ex:label ; sh:values [ sparql:concat ( [ shnex:pathValues ex:first ] " " [ shnex:pathValues ex:last ] ) ] ] ;
  sh:property [ sh:path ex:first ] ."""

CASES = {
    "count": (
        FRIENDS,
        "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .",
        {},
    ),
    "multivalued": (
        FRIENDS,
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:echo ; sh:values [ shnex:pathValues ex:friend ] ] .",
        {},
    ),
    "standalone_property_shape": (
        FRIENDS,
        "ex:PS a sh:PropertyShape ; sh:targetNode ex:alice ; sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] .",
        {},
    ),
    "union_with_stored": (
        "ex:alice ex:friend ex:bob, ex:carol ; ex:friendCount 99 .",
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:friendCount ; sh:values [ shnex:count [ shnex:pathValues ex:friend ] ] ] .",
        {},
    ),
    "no_values_is_a_noop": (
        "ex:alice a ex:Person .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ] .",
        {},
    ),
    "complex_path_skipped": (
        "ex:alice ex:friend ex:bob .",
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ( ex:friend ex:friend ) ; sh:values [ shnex:pathValues ex:friend ] ] .",
        {},
    ),
    "shapes_default_to_data": ("ex:alice a ex:Person .", None, {}),
    "subgraph_scoping": (
        'ex:alice a ex:Person ; ex:name "Alice" ; ex:noise "n" . ex:other ex:unconnected "x" .',
        "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ] .",
        {},
    ),
    "default_value_fills": (
        "ex:carol a ex:Person .",
        'ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:nickname ; sh:values [ shnex:pathValues ex:preferredName ] ; sh:defaultValue "Anonymous" ] .',
        {},
    ),
    "default_value_skipped_by_computed": (
        'ex:carol a ex:Person ; ex:preferredName "Caz" .',
        'ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:nickname ; sh:values [ shnex:pathValues ex:preferredName ] ; sh:defaultValue "Anonymous" ] .',
        {},
    ),
    "default_value_skipped_by_stored": (
        'ex:carol a ex:Person ; ex:nickname "Cee" .',
        'ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:nickname ; sh:defaultValue "Anonymous" ] .',
        {},
    ),
    "default_value_expression": (
        'ex:carol a ex:Person ; ex:fallback "Fb" .',
        "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:nickname ; sh:defaultValue [ shnex:pathValues ex:fallback ] ] .",
        {},
    ),
    "deactivated_property_shape": (
        FRIENDS,
        "ex:S a sh:NodeShape ; sh:targetNode ex:alice ; sh:property [ sh:path ex:echo ; sh:deactivated true ; sh:values [ shnex:pathValues ex:friend ] ] .",
        {},
    ),
    "deactivated_host": (
        FRIENDS,
        "ex:S a sh:NodeShape ; sh:deactivated true ; sh:targetNode ex:alice ; sh:property [ sh:path ex:echo ; sh:values [ shnex:pathValues ex:friend ] ] .",
        {},
    ),
    "everything": (LABELS, LABEL_SHAPES, {}),
    "one_focus_node": (LABELS, LABEL_SHAPES, {"focus_nodes": [URIRef(EX + "b")]}),
    "untargeted_focus_node": (LABELS + ' ex:z ex:first "Z" .', LABEL_SHAPES, {"focus_nodes": [URIRef(EX + "z")]}),
    "one_property": (LABELS, LABEL_SHAPES, {"properties": [URIRef(EX + "label")]}),
    "one_property_of_one_node": (
        LABELS,
        LABEL_SHAPES,
        {"focus_nodes": [URIRef(EX + "a")], "properties": [URIRef(EX + "label")]},
    ),
    "rdfs_inference_class_target": (
        'ex:n a ex:Sub ; ex:name "Nina" . ex:Sub rdfs:subClassOf ex:Person .',
        "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ] .",
        {"inference": RDFS},
    ),
}

RULES_SHAPES = """ex:Shapes a sh:ShapesGraph ; sh:entailment sh:RulesEntailment .
ex:Needs a sh:NodeShape ; sh:targetClass ex:Special ; sh:property [ sh:path ex:name ] .
ex:Mark a sh:TripleRule ; sh:subject ex:n ; sh:predicate rdf:type ; sh:object ex:Special ."""


@pytest.mark.parametrize("name", CASES)
def test_evaluate_matches_the_old_function(name: str) -> None:
    data, shapes, kw = CASES[name]
    old, new = both(data, shapes, **kw)
    assert set(new) == set(old)


def test_computed_values_are_what_the_old_tests_expect() -> None:
    new = new_evaluate(g(FRIENDS), g(CASES["count"][1]))
    assert sorted(int(v.value) for v in new.objects(URIRef(EX + "alice"), URIRef(EX + "friendCount"))) == [2]
    assert [int(v.value) for v in new.objects(URIRef(EX + "dave"), URIRef(EX + "friendCount"))] == [1]
    union = new_evaluate(g(CASES["union_with_stored"][0]), g(CASES["union_with_stored"][1]))
    assert sorted(int(v.value) for v in union.objects(URIRef(EX + "alice"), URIRef(EX + "friendCount"))) == [2, 99]
    restricted = new_evaluate(g(LABELS), g(LABEL_SHAPES), focus_nodes=[URIRef(EX + "a")], properties=[URIRef(EX + "label")])
    assert set(restricted) == {(URIRef(EX + "a"), URIRef(EX + "label"), Literal("Ann Lee"))}


def test_evaluate_leaves_both_graphs_alone() -> None:
    data, shapes = g(FRIENDS), g(CASES["count"][1])
    before_d, before_s = set(data), set(shapes)
    result = new_evaluate(data, shapes)
    assert set(data) == before_d and set(shapes) == before_s
    assert result is not data and type(result) is type(data)


def test_evaluate_rules_entailment_matches_the_old_function() -> None:
    data = 'ex:n ex:name "Nina" .'
    for flag in (False, True):
        old = old_evaluate(g(data), g(RULES_SHAPES), rules_entailment=flag)
        new = new_evaluate(g(data), g(RULES_SHAPES), rules_entailment=flag)
        assert set(new) == set(old)
    assert set(new_evaluate(g(data), g(RULES_SHAPES), rules_entailment=True))
    assert not set(new_evaluate(g(data), g(RULES_SHAPES)))


def test_evaluate_ont_graph_is_visible_to_entailment_only() -> None:
    data, shapes = 'ex:n a ex:Sub ; ex:name "Nina" .', "ex:S a sh:NodeShape ; sh:targetClass ex:Person ; sh:property [ sh:path ex:name ] ."
    ont = "ex:Sub rdfs:subClassOf ex:Person ."
    old = old_evaluate(g(data), g(shapes), g(ont), inference=RDFS)
    new = new_evaluate(g(data), g(shapes), g(ont), inference=RDFS)
    assert set(new) == set(old) == {(URIRef(EX + "n"), URIRef(EX + "name"), Literal("Nina"))}


# --- validate_each ----------------------------------------------------------------------------------------------------
SHAPES = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minCount 1 ; sh:message 'need p' ] ."
GRAPHS = ["ex:a a ex:T ; ex:p 1 .", "ex:a a ex:T . ex:b a ex:T .", "ex:z a ex:U ."]


def test_validate_each_matches_the_old_function() -> None:
    from starlayer.shacl import validate_each as old_each

    old = old_each([g(x) for x in GRAPHS], g(SHAPES), meta_shacl=False, ignore_imports=True)
    new = validate_each([g(x) for x in GRAPHS], g(SHAPES))
    assert list(new) == list(old) == [0, 1, 2]
    for i in old:
        assert new[i].conforms == old[i].conforms
        assert len(new[i].results) == len(list(old[i].report_graph.objects(None, URIRef("http://www.w3.org/ns/shacl#result"))))
    assert [new[i].conforms for i in new] == [True, False, True]


def test_validate_each_equals_validate_per_graph() -> None:
    each = validate_each([g(x) for x in GRAPHS], g(SHAPES), shapes_graph_iri=EX + "s")
    for i, x in enumerate(GRAPHS):
        single = validate(g(x), g(SHAPES), shapes_graph_iri=EX + "s")
        assert each[i].conforms == single.conforms
        assert each[i].report_text == single.report_text


def test_validate_each_without_shapes_uses_each_graph_as_its_own() -> None:
    graphs = [g(SHAPES + " ex:a a ex:T ."), g(SHAPES + " ex:a a ex:T ; ex:p 1 .")]
    assert {i: r.conforms for i, r in validate_each(graphs).items()} == {0: False, 1: True}


def test_validate_each_empty() -> None:
    assert validate_each([], g(SHAPES)) == {}


# --- report text and diagnostics --------------------------------------------------------------------------------------
TEXT_CASES = {
    "conforms": ("ex:a a ex:T ; ex:p 1 .", SHAPES),
    "min_count": ("ex:a a ex:T .", SHAPES),
    "datatype_literal": (
        'ex:a a ex:T ; ex:p "x" .',
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:datatype xsd:integer ] .",
    ),
    "lang_literal_and_warning": (
        'ex:a a ex:T ; ex:p "x"@en .',
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:severity sh:Warning ; sh:property [ sh:path ex:p ; sh:datatype xsd:string ] .",
    ),
    "node_shape_class": (
        "ex:a a ex:T .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:class ex:Other .",
    ),
    "sequence_path": (
        "ex:a a ex:T ; ex:q ex:b . ex:b ex:r 1 .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ( ex:q ex:r ) ; sh:maxInclusive 0 ] .",
    ),
    "blank_value_node": (
        "ex:a a ex:T ; ex:p [ ex:x 1 ] .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:nodeKind sh:IRI ] .",
    ),
    "pattern_and_length": (
        'ex:a a ex:T ; ex:p "x" .',
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:pattern '^[0-9]+$' ; sh:minLength 3 ; sh:maxLength 0 ] .",
    ),
    "in_and_not": (
        "ex:a a ex:T ; ex:p ex:x .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:in ( ex:y ) ; sh:not [ a sh:NodeShape ; sh:class rdfs:Resource ] ] .",
    ),
    "closed": (
        "ex:a a ex:T ; ex:q 1 .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:closed true ; sh:ignoredProperties ( rdf:type ) .",
    ),
    "range_and_pair": (
        "ex:a a ex:T ; ex:p 5 ; ex:q 1 .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:minExclusive 5 ; sh:lessThan ex:q ] .",
    ),
    "and_or_xone": (
        "ex:a a ex:T ; ex:p 5 .",
        "ex:A a sh:NodeShape ; sh:class ex:Z . ex:B a sh:NodeShape ; sh:class ex:Y . "
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:and ( ex:A ex:B ) ; sh:or ( ex:A ex:B ) ; sh:xone ( ex:A ex:B ) ] .",
    ),
    "max_count": (
        "ex:a a ex:T ; ex:p 1, 2 .",
        "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:maxCount 1 ] .",
    ),
    "two_results_sorted": (
        "ex:a a ex:T . ex:b a ex:T .",
        SHAPES,
    ),
}


@pytest.mark.parametrize("name", TEXT_CASES)
def test_report_text_matches_the_old_validator(name: str) -> None:
    data, shapes = TEXT_CASES[name]
    old = old_validate(g(data), g(shapes), meta_shacl=False, ignore_imports=True)
    new = validate(g(data), g(shapes))
    assert new.report_text == old.report_text


def test_report_text_with_provenance_matches_the_old_validator() -> None:
    kw = {"data_graph_iri": EX + "d", "shapes_graph_iri": EX + "s"}
    old = old_validate(g("ex:a a ex:T ."), g(SHAPES), meta_shacl=False, ignore_imports=True, **kw)
    new = validate(g("ex:a a ex:T ."), g(SHAPES), **kw)
    assert new.report_text == old.report_text
    assert "Provenance:" in new.report_text


def test_report_text_of_a_debug_only_report_says_conforms_true() -> None:
    shapes = "ex:S a sh:NodeShape ; sh:targetClass ex:T ; sh:property [ sh:path ex:p ; sh:severity sh:Debug ; sh:minCount 1 ] ."
    new = validate(g("ex:a a ex:T ."), g(shapes))
    assert new.conforms and "Conforms: True" in new.report_text and "Results (1)" in new.report_text


def test_diagnostics() -> None:
    out = validate(g("ex:a a ex:T ."), g(SHAPES))
    d = out.diagnostics
    assert d.report_triples == len(out.report_graph) > 0
    assert d.encode_graph_calls == d.decode_graph_calls == d.encoded_triple_terms == d.decoded_triple_terms == 0
    assert d.recursion_revisits == 0 and d.inplace_data_triples == 0
    old = old_validate(g("ex:a a ex:T ."), g(SHAPES), meta_shacl=False, ignore_imports=True).diagnostics
    assert type(d) is type(old)


def test_schema_evaluate_is_the_module_function() -> None:
    data, shapes = g(FRIENDS), g(CASES["count"][1])
    assert set(StarShaclSchema(shacl_graph=shapes).evaluate(data_graph=data)) == set(new_evaluate(data, shapes))
