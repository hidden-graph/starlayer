"""sh:targetWhere narrows its candidate nodes with one SPARQL query built from necessary conditions of the where-shape.

The exact conformance check still decides, so the targets must equal those of the full scan of every node. The baseline here is
that full scan (the candidate function switched off)."""

import pytest
from starlayer.graph import ENTAILMENT, NamedNode
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import target_nodes
from starlayer.shacl.engine import executor, targets

P = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
DATA = """
ex:a a ex:Person ; ex:age 30 ; ex:name "A" .
ex:b a ex:Person ; ex:name "B" .
ex:c a ex:Student ; ex:age 12 .
ex:d ex:age 40 .
ex:e a ex:Robot ; ex:age 99 .
ex:Student rdfs:subClassOf ex:Person .
ex:f ex:friend ex:a .
ex:g a ex:Person ; ex:tag ex:vip .
"""
NODE = NamedNode("http://ex/S")


def _g(ttl: str) -> Graph:
    return Graph().parse(data=P + ttl, format="turtle")


def _both(where: str, monkeypatch, data: str = DATA, extra: str = "", **kw):
    shapes = _g(f"ex:S a sh:NodeShape ; sh:targetWhere ex:W {extra}. ex:W {where} ex:X a sh:NodeShape ; sh:class ex:Person .")
    fast = set(target_nodes(data_graph=_g(data), shacl_graph=shapes, shape_node=NODE, **kw))
    with monkeypatch.context() as m:
        m.setattr(targets, "_target_where_candidates", lambda *a, **k: None)
        slow = set(target_nodes(data_graph=_g(data), shacl_graph=shapes, shape_node=NODE, **kw))
    assert fast == slow
    return fast


def _names(nodes) -> set:
    return {n.value.rsplit("/", 1)[-1] if hasattr(n, "value") else str(n) for n in nodes}


def test_class_only(monkeypatch):
    assert _names(_both("a sh:NodeShape ; sh:class ex:Person .", monkeypatch)) == {"a", "b", "c", "g"}


def test_property_mincount_only(monkeypatch):
    got = _both("a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:minCount 1 ] .", monkeypatch)
    assert _names(got) == {"a", "c", "d", "e"}


def test_property_hasvalue_only(monkeypatch):
    got = _both("a sh:NodeShape ; sh:property [ sh:path ex:tag ; sh:hasValue ex:vip ] .", monkeypatch)
    assert _names(got) == {"g"}


def test_class_and_property(monkeypatch):
    w = "a sh:NodeShape ; sh:class ex:Person ; sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:minInclusive 18 ] ."
    assert _names(_both(w, monkeypatch)) == {"a"}


def test_and_and_node_nesting(monkeypatch):
    w = "a sh:NodeShape ; sh:and ( [ sh:class ex:Person ] [ sh:node ex:Aged ] ) ."
    got = _both(w + " ex:Aged sh:property [ sh:path ex:age ; sh:minCount 1 ] .", monkeypatch)
    assert _names(got) == {"a", "c"}


def test_recursive_node_reference_terminates(monkeypatch):
    got = _both("a sh:NodeShape ; sh:node ex:W ; sh:class ex:Person .", monkeypatch)
    assert _names(got) == {"a", "b", "c", "g"}


def test_or_is_not_narrowed(monkeypatch):
    w = "a sh:NodeShape ; sh:or ( [ sh:class ex:Robot ] [ sh:property [ sh:path ex:tag ; sh:minCount 1 ] ] ) ."
    assert _names(_both(w, monkeypatch)) == {"e", "g"}


def test_list_valued_class_is_a_choice(monkeypatch):
    got = _both("a sh:NodeShape ; sh:class ( ex:Robot ex:Student ) .", monkeypatch)
    assert _names(got) == {"c", "e"}


def test_only_value_constraints_fall_back(monkeypatch):
    got = _both("a sh:NodeShape ; sh:in ( ex:a ex:b ) .", monkeypatch)
    assert _names(got) == {"a", "b"}


def test_deactivated_shape_makes_every_node_conform(monkeypatch):
    got = _both("a sh:NodeShape ; sh:deactivated true ; sh:class ex:Person .", monkeypatch)
    assert ("a" in _names(got)) and ("d" in _names(got))


def test_deactivated_member_is_not_a_condition(monkeypatch):
    w = "a sh:NodeShape ; sh:node ex:Off ; sh:property [ sh:path ex:age ; sh:minCount 1 ] . ex:Off sh:deactivated true ; sh:class ex:Robot ."
    assert _names(_both(w, monkeypatch)) == {"a", "c", "d", "e"}


def test_deactivated_property_shape_is_not_a_condition(monkeypatch):
    w = "a sh:NodeShape ; sh:property [ sh:path ex:tag ; sh:minCount 1 ; sh:deactivated true ] ."
    assert len(_both(w, monkeypatch)) > 3


def test_deactivated_constraint_annotation_is_not_a_condition(monkeypatch):
    w = "a sh:NodeShape ; sh:class ex:Robot {| sh:deactivated true |} ."
    assert len(_both(w, monkeypatch)) > 3


def test_literals_can_conform_to_a_datatype_shape(monkeypatch):
    got = _both("a sh:NodeShape ; sh:datatype xsd:integer .", monkeypatch)
    assert {n.value for n in got} == {"30", "12", "40", "99"}


def test_literal_cannot_satisfy_a_class_condition_but_class_still_exact(monkeypatch):
    got = _both("a sh:NodeShape ; sh:class ex:Person ; sh:nodeKind sh:IRI .", monkeypatch)
    assert _names(got) == {"a", "b", "c", "g"}


def test_subclass_of_in_shapes_graph(monkeypatch):
    data = "ex:x a ex:Kid . ex:y a ex:Person ."
    shapes = "ex:Kid rdfs:subClassOf ex:Person ."
    s = _g(f"ex:S a sh:NodeShape ; sh:targetWhere ex:W . ex:W sh:class ex:Person . {shapes}")
    d = _g(data)
    on = set(target_nodes(data_graph=d, shacl_graph=s, shape_node=NODE, subclass_of_in_shapes_graph=True))
    off = set(target_nodes(data_graph=d, shacl_graph=s, shape_node=NODE))
    with monkeypatch.context() as m:
        m.setattr(targets, "_target_where_candidates", lambda *a, **k: None)
        assert on == set(target_nodes(data_graph=d, shacl_graph=s, shape_node=NODE, subclass_of_in_shapes_graph=True))
        assert off == set(target_nodes(data_graph=d, shacl_graph=s, shape_node=NODE))
    assert _names(on) == {"x", "y"}
    assert _names(off) == {"y"}


def test_entailment_makes_a_node_an_instance(monkeypatch):
    data = "ex:Kid rdfs:subClassOf ex:Person . ex:x a ex:Kid . ex:p ex:q ex:x . ex:q rdfs:domain ex:Person ."
    got = _both("a sh:NodeShape ; sh:class ex:Person .", monkeypatch, data=data, inference=ENTAILMENT.RDFS)
    assert {"x", "p"} <= _names(got)


def test_combined_with_other_targets(monkeypatch):
    got = _both("a sh:NodeShape ; sh:class ex:Robot .", monkeypatch, extra="; sh:targetNode ex:d ; sh:targetSubjectsOf ex:friend ")
    assert _names(got) == {"e", "d", "f"}


def test_conformance_checks_drop_to_the_candidates(monkeypatch):
    calls = []
    original = executor.Context.conforms

    def counting(self, shape_node, node, **kw):
        if shape_node == NamedNode("http://ex/W"):
            calls.append(node)
        return original(self, shape_node, node, **kw)

    monkeypatch.setattr(executor.Context, "conforms", counting)
    shapes = _g("ex:S sh:targetWhere ex:W . ex:W a sh:NodeShape ; sh:class ex:Person ; sh:property [ sh:path ex:age ; sh:minCount 1 ] .")
    got = target_nodes(data_graph=_g(DATA), shacl_graph=shapes, shape_node=NODE)
    assert _names(got) == {"a", "c"}
    assert _names(calls) == {"a", "c"}  # persons with an age; the scan checked every subject and object (literals too)
    calls.clear()
    monkeypatch.setattr(targets, "_target_where_candidates", lambda *a, **k: None)
    target_nodes(data_graph=_g(DATA), shacl_graph=shapes, shape_node=NODE)
    assert len(calls) > 15


@pytest.mark.parametrize("value", ["true", "false"])
def test_deactivated_literal_forms(monkeypatch, value):
    got = _both(f"a sh:NodeShape ; sh:deactivated {value} ; sh:class ex:Robot .", monkeypatch)
    assert (len(got) > 3) == (value == "true")


# --- FILTERs for value constraints (range, datatype) ------------------------------------------------------------------

XSD_NS = "http://www.w3.org/2001/XMLSchema#"
VALUE_KINDS = [  # every value kind the engine's range and datatype components meet
    '"18"^^xsd:integer', '"17"^^xsd:integer', '"19"^^xsd:integer', '"18.0"^^xsd:decimal', '"17.5"^^xsd:decimal', '"18.5"^^xsd:decimal',
    '"1.8e1"^^xsd:double', '"1.7e1"^^xsd:double', '"1.9e1"^^xsd:float', '"+18"^^xsd:integer', '"018"^^xsd:integer', '"-5"^^xsd:integer',
    '"0"^^xsd:integer', '"NaN"^^xsd:double', '"INF"^^xsd:double', '"-INF"^^xsd:float', '"abc"^^xsd:integer', '"1.5"^^xsd:integer',
    '"99999999999999999999"^^xsd:integer', '"-99999999999999999999"^^xsd:integer', '"9223372036854775807"^^xsd:long',
    '"9223372036854775808"^^xsd:integer', '"18"^^xsd:int', '"18"^^xsd:byte', '"300"^^xsd:byte', '"-3"^^xsd:unsignedInt',
    '"  18 "^^xsd:integer', '"\\n19\\t"^^xsd:decimal', '" 1.8e1 "^^xsd:double', '"18.0000000000000000001"^^xsd:decimal',
    '"18"', '"abc"', '"18"@en', '"18"^^xsd:string', '"true"^^xsd:boolean', '"2020-01-01"^^xsd:date', '"18"^^<http://ex/dt>', "ex:iri", "[]",
]
RANGES = [("sh:minInclusive", "18"), ("sh:minExclusive", "18"), ("sh:maxInclusive", "18"), ("sh:maxExclusive", "18"),
          ("sh:minInclusive", "17.5"), ("sh:maxExclusive", "1.8e1"), ("sh:minExclusive", "-5"), ("sh:maxInclusive", '"18.0"^^xsd:decimal'),
          ("sh:minInclusive", '"1.8e1"^^xsd:float'), ("sh:maxInclusive", "9223372036854775807")]
VALUE_DATA = "\n".join(f"ex:n{i} a ex:Person ; ex:age {v} ." for i, v in enumerate(VALUE_KINDS)) + """
ex:m1 a ex:Person ; ex:age 10, 30 .
ex:m2 a ex:Person ; ex:age 10, 11 .
ex:m3 a ex:Person ; ex:age 30, "x" .
ex:none a ex:Person .
ex:robot a ex:Robot ; ex:age 50 .
"""


def _queries(monkeypatch) -> list[str]:
    queries: list[str] = []
    original = targets._target_where_candidates

    def recording(data, *args, **kw):
        class Spy:
            def __getattr__(self, name):
                return getattr(data, name)

            def sparql_query(self, q, *a, **k):
                queries.append(q)
                return data.sparql_query(q, *a, **k)

        return original(Spy(), *args, **kw)

    monkeypatch.setattr(targets, "_target_where_candidates", recording)
    return queries


def _w(constraints: str, count: str = "sh:minCount 1 ;", cls: str = "sh:class ex:Person ;") -> str:
    return f"a sh:NodeShape ; {cls} sh:property [ sh:path ex:age ; {count} {constraints} ] ."


@pytest.mark.parametrize("pred,bound", RANGES)
@pytest.mark.parametrize("count", ["sh:minCount 1 ;", ""])
def test_range_filter_never_drops_a_conforming_node(monkeypatch, pred, bound, count):
    queries = _queries(monkeypatch)
    got = _both(_w(f"{pred} {bound}", count), monkeypatch, data=VALUE_DATA)
    assert ("FILTER" in queries[0]) == bool(count)
    assert ("none" in _names(got)) == (not count)  # no minCount: a node without values conforms, and nothing narrows it


@pytest.mark.parametrize("count", ["sh:minCount 1 ;", ""])
def test_several_range_constraints_are_one_filter(monkeypatch, count):
    queries = _queries(monkeypatch)
    got = _both(_w("sh:minInclusive 18 ; sh:maxExclusive 19", count), monkeypatch, data=VALUE_DATA)
    if count:
        assert queries[0].count("FILTER") == 1 and ">= \"18\"^^" in queries[0] and "< \"19\"^^" in queries[0]
        assert "n0" in _names(got) and "n1" not in _names(got)
    else:
        assert "FILTER" not in queries[0]


def test_range_filter_with_class_and_nesting(monkeypatch):
    queries = _queries(monkeypatch)
    w = "a sh:NodeShape ; sh:and ( [ sh:class ex:Person ] [ sh:node ex:Aged ] ) . ex:Aged sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:minInclusive 18 ] ."
    got = _both(w, monkeypatch, data=VALUE_DATA)
    assert ">= \"18\"^^" in queries[0] and "VALUES" in queries[0]
    assert "n1" not in _names(got) and "robot" not in _names(got) and "n0" in _names(got)


def test_a_node_with_one_passing_value_stays_a_candidate(monkeypatch):
    got = _both(_w("sh:minInclusive 18"), monkeypatch, data=VALUE_DATA)
    assert "m1" not in _names(got)  # the exact check rejects it (10 fails), the query kept it as a candidate
    got = _both(_w("sh:minInclusive 0"), monkeypatch, data=VALUE_DATA)
    assert "m2" in _names(got)


def test_deactivated_property_shape_gets_no_filter(monkeypatch):
    queries = _queries(monkeypatch)
    _both(_w("sh:minInclusive 18 ; sh:deactivated true"), monkeypatch, data=VALUE_DATA)
    assert all("FILTER" not in q for q in queries)


@pytest.mark.parametrize("bound", ['"18"', '"2020-01-01"^^xsd:date', '"2020-01-01T00:00:00"^^xsd:dateTime', '"a"@en', '"abc"^^xsd:integer', '"NaN"^^xsd:double',
                                   '"INF"^^xsd:double', '"99999999999999999999"^^xsd:integer', '"  18 "^^xsd:integer', '"1.0000000000000000001"^^xsd:decimal', "true"])
def test_non_numeric_or_unsafe_bound_gets_no_filter(monkeypatch, bound):
    queries = _queries(monkeypatch)
    _both(_w(f"sh:minInclusive {bound}"), monkeypatch, data=VALUE_DATA)
    assert queries and all("FILTER" not in q for q in queries)


def test_two_values_of_one_range_constraint_get_no_filter(monkeypatch):
    queries = _queries(monkeypatch)
    _both(_w("sh:minInclusive 18, 20"), monkeypatch, data=VALUE_DATA)
    assert all("FILTER" not in q for q in queries)


@pytest.mark.parametrize("datatype", ["xsd:integer", "xsd:string", "rdf:langString", "xsd:decimal", "xsd:int", "xsd:double", "xsd:boolean", "xsd:date", "<http://ex/dt>"])
def test_datatype_filter_never_drops_a_conforming_node(monkeypatch, datatype):
    queries = _queries(monkeypatch)
    data = VALUE_DATA + "\n".join(f'ex:l{i} a ex:Person ; ex:age "x"@{t} .' for i, t in enumerate(["en", "en-US", "EN"]))
    got = _both(_w(f"sh:datatype {datatype}"), monkeypatch, data=data)
    assert "FILTER(datatype(?o" in queries[0]
    assert got is not None


def test_datatype_and_range_together(monkeypatch):
    got = _both(_w("sh:datatype xsd:integer ; sh:minInclusive 18"), monkeypatch, data=VALUE_DATA)
    assert {"n0", "n2"} <= _names(got) and "n1" not in _names(got)


def test_datatype_list_gets_no_filter(monkeypatch):
    queries = _queries(monkeypatch)
    _both(_w("sh:datatype ( xsd:integer xsd:decimal )"), monkeypatch, data=VALUE_DATA)
    assert all("FILTER" not in q for q in queries)


def test_conformance_checks_drop_to_the_adults(monkeypatch):
    calls = []
    original = executor.Context.conforms

    def counting(self, shape_node, node, **kw):
        if shape_node == NamedNode("http://ex/W"):
            calls.append(node)
        return original(self, shape_node, node, **kw)

    monkeypatch.setattr(executor.Context, "conforms", counting)
    data = "\n".join(f"ex:p{i} a ex:Person ; ex:age {age} ." for i, age in enumerate([5, 10, 12, 17, 18, 21, 30, 44, 60, 9]))
    shapes = _g("ex:S sh:targetWhere ex:W . ex:W a sh:NodeShape ; sh:class ex:Person ; sh:property [ sh:path ex:age ; sh:minCount 1 ; sh:minInclusive 18 ] .")
    got = target_nodes(data_graph=_g(data), shacl_graph=shapes, shape_node=NODE)
    assert _names(got) == {"p4", "p5", "p6", "p7", "p8"} and _names(calls) == _names(got)
    calls.clear()
    monkeypatch.setattr(targets, "_target_where_candidates", lambda *a, **k: None)
    target_nodes(data_graph=_g(data), shacl_graph=shapes, shape_node=NODE)
    assert len(calls) > 15
