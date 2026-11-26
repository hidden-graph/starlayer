"""Query-time entailment on ``StarLayerGraph`` / ``StarLayerDataset`` / ``StarQuery``, migrated from ``tests/graph/unit/test_entailment.py``,
``test_entailment_hunt2.py`` and ``test_entailment_direct.py`` (which ran on the old class and now run on ``StarLayerGraph``).

RDF and RDFS are a rewrite of the query (``starlayer.sparql.sqe.entailment``); the OWL regimes run the query on a temporary copy
of the store that ``infer()`` has closed. Differences from the originals:

- the OWL regimes copy the store on every query, but the graph keeps the entailed triples per regime and engine and ``recompute=``
  (``"onChange"`` / ``"never"`` / ``"always"``) says when they are computed again (``TestEachRegimeKeepsItsOwnEntailedTriples``); the
  union-with-delta design (``_UnionForQuery``) has no counterpart, and a bad ``recompute=`` value raises ``ValueError``;
- ``entailment='native'`` / the ``rdf-1.2`` backend tests do not apply (the wrapper is always Oxigraph);
- the OWL-Direct tests need ``owlready2`` + Java (HermiT) or ``rustdl`` and skip without them, as before.
"""

from __future__ import annotations

import shutil

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import StarLayerDataset, StarLayerGraph
from starlayer.graph.entailment.infer import ENTAILMENT
from starlayer.graph.execution import union
from starlayer.sparql.sqe.entailment import (
    rewrite_for_entailment,
)
from starlayer.sparql.star_query import StarQuery
from tests.support.errors import raises_kind

EX = "http://example.org/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RDFS_SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
N = ox.NamedNode

try:
    import owlready2  # noqa: F401
    _OWLREADY2 = True
except ImportError:
    _OWLREADY2 = False
try:
    import rustdl  # noqa: F401
    _RUSTDL = True
except ImportError:
    _RUSTDL = False

owl_dl_extra = pytest.mark.skipif(not _OWLREADY2, reason="owlready2 not importable (pip install starlayer-reasoning[hermit])")
java_required = pytest.mark.skipif(shutil.which("java") is None, reason="no Java runtime on PATH (HermiT needs a JVM)")
rustdl_extra = pytest.mark.skipif(not _RUSTDL, reason="rustdl not importable (pip install starlayer-reasoning[rustdl])")

_DATA = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Manager rdfs:subClassOf ex:Employee .
    ex:alice a ex:Manager .
"""
_QUERY = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }"
_PREFIXES = "PREFIX ex: <http://example.org/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "


def _graph(data: str = _DATA) -> StarLayerGraph:
    g = StarLayerGraph()
    g.parse(data=data, format="turtle")
    return g


def _col(result, name: str = "x") -> list[str]:
    return sorted(getattr(r[name], "value", str(r[name])) for r in result)


def _alice() -> list[str]:
    return [EX + "alice"]


# ---- per-query, not per-graph -----------------------------------------------------------------------------------------
class TestEntailmentIsPerQueryNotPerGraph:
    def test_unsupported_entailment_raises(self):
        with pytest.raises(ValueError, match="entailment must be one of"):
            _graph().query(_QUERY, entailment="owl")

    def test_d_entailment_raises(self):
        with pytest.raises(ValueError):
            _graph().query(_QUERY, entailment=ENTAILMENT.D)

    def test_one_graph_answers_different_entailment_per_call(self):
        g = _graph()
        assert list(g.query(_QUERY)) == []
        assert _col(g.query(_QUERY, entailment=ENTAILMENT.RDFS)) == _alice()
        assert _col(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"])) == _alice()
        assert list(g.query(_QUERY)) == []  # not sticky

    def test_regime_may_be_given_as_string_or_rdflib_uriref(self):
        from rdflib import URIRef

        g = _graph()
        assert _col(g.query(_QUERY, entailment=str(ENTAILMENT.RDFS.value))) == _alice()
        assert _col(g.query(_QUERY, entailment=URIRef(ENTAILMENT.RDFS.value))) == _alice()

    def test_the_old_rdflib_regime_constant_works(self):
        from starlayer.graph.entailment import ENTAILMENT as OLD

        assert _col(_graph().query(_QUERY, entailment=OLD.RDFS)) == _alice()

    def test_no_data_is_copied_or_added(self):
        g = _graph()
        before = set(g.store)
        for regime in (ENTAILMENT.RDF, ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]):
            list(g.query(_QUERY, entailment=regime))
        assert set(g.store) == before and len(g) == 2


# ---- RDFS -------------------------------------------------------------------------------------------------------------
class TestQueryTimeRdfsRewrite:
    def test_plain_query_misses_the_subclass_fact(self):
        assert list(_graph().query(_QUERY)) == []

    def test_matches_infer_oracle_for_a_richer_hierarchy(self):
        g = _graph()
        g.add((N(EX + "Employee"), N(RDFS_SUBCLASS), N(EX + "Person")))
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Person }"
        rewritten = _col(g.query(q, entailment=ENTAILMENT.RDFS))
        closure = g.infer(entailment=ENTAILMENT.RDFS)
        materialized = sorted(s.value for s, p, o in closure.triples() if p.value == RDF_TYPE and o.value == EX + "Person")
        assert rewritten == materialized == _alice()

    @pytest.mark.parametrize(
        ("data", "query", "col", "expected"),
        [
            ("ex:worksAt rdfs:domain ex:Person . ex:alice ex:worksAt ex:Acme .", "SELECT ?x WHERE { ?x a ex:Person }", "x", EX + "alice"),
            ("ex:worksAt rdfs:range ex:Organization . ex:alice ex:worksAt ex:Acme .", "SELECT ?x WHERE { ?x a ex:Organization }", "x", EX + "Acme"),
            ("ex:hasParent rdfs:subPropertyOf ex:hasRelative . ex:alice ex:hasParent ex:bob .", "SELECT ?x WHERE { ex:alice ex:hasRelative ?x }", "x", EX + "bob"),
        ],
    )
    def test_rewrite_agrees_with_the_materialized_closure(self, data, query, col, expected):
        g = _graph("@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . " + data)
        rewritten = _col(g.query(_PREFIXES + query, entailment=ENTAILMENT.RDFS), col)
        closure = g.infer(entailment=ENTAILMENT.RDFS)
        assert rewritten == _col(closure.query(_PREFIXES + query), col) == [expected]

    def test_repeated_call_stays_correct(self):
        g = _graph()
        assert _col(g.query(_QUERY, entailment=ENTAILMENT.RDFS)) == _col(g.query(_QUERY, entailment=ENTAILMENT.RDFS)) == _alice()

    def test_a_change_to_the_data_is_seen_by_the_next_query(self):
        g = _graph()
        list(g.query(_QUERY, entailment=ENTAILMENT.RDFS))
        g.add((N(EX + "bob"), N(RDF_TYPE), N(EX + "Manager")))
        assert _col(g.query(_QUERY, entailment=ENTAILMENT.RDFS)) == [EX + "alice", EX + "bob"]


class TestQueryTimeRdfEntailment:
    _Q = "PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> SELECT ?p WHERE { ?p a rdf:Property }"

    def test_plain_query_misses_the_fact(self):
        assert list(_graph().query(self._Q)) == []

    def test_entailment_rdf_finds_predicates_used_in_the_graph(self):
        assert set(_col(_graph().query(self._Q, entailment=ENTAILMENT.RDF), "p")) == {RDFS_SUBCLASS, RDF_TYPE}

    def test_variable_class_query_is_not_rewritten(self):
        g = _graph()
        q = "SELECT ?x ?c WHERE { ?x a ?c }"
        plain = {(r["x"].value, r["c"].value) for r in g.query(q)}
        rewritten = {(r["x"].value, r["c"].value) for r in g.query(q, entailment=ENTAILMENT.RDF)}
        assert plain == rewritten == {(EX + "alice", EX + "Manager")}


# ---- the third hunt (issue #97): domain / range / typing through sub-properties --------------------------------------
HUNT = """@prefix : <http://e/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
:hasMother rdfs:subPropertyOf :hasParent . :hasParent rdfs:domain :Child ; rdfs:range :Parent .
:Child rdfs:subClassOf :Person . :typedBy rdfs:subPropertyOf rdf:type .
:a :hasMother :b . :c :typedBy :Child . :d a :Child ."""


def _members(rows):
    return sorted({getattr(r[0], "value", str(r[0])).rsplit("/", 1)[-1] for r in rows})


class TestHunt3:
    @pytest.mark.parametrize(("cls", "expected"), [("Child", ["a", "c", "d"]), ("Person", ["a", "c", "d"]), ("Parent", ["b"])])
    def test_type_query_sees_domain_range_and_typing_through_subproperties(self, cls, expected):
        rows = _graph(HUNT).query(f"PREFIX : <http://e/> SELECT ?x {{ ?x a :{cls} }}", entailment=ENTAILMENT.RDFS)
        assert _members(rows) == expected

    @pytest.mark.parametrize("cls", ["Child", "Person", "Parent"])
    def test_rewrite_agrees_with_the_materialized_closure(self, cls):
        g = _graph(HUNT)
        closure = g.infer(entailment=ENTAILMENT.RDFS, mode="full")
        materialized = sorted({s.value.rsplit("/", 1)[-1] for s, p, o in closure.triples() if p.value == RDF_TYPE and o.value == f"http://e/{cls}"})
        rows = g.query(f"PREFIX : <http://e/> SELECT ?x {{ ?x a :{cls} }}", entailment=ENTAILMENT.RDFS)
        assert _members(rows) == materialized

    def test_a_subproperty_query_still_works(self):
        assert _members(_graph(HUNT).query("PREFIX : <http://e/> SELECT ?x { ?x :hasParent ?y }", entailment=ENTAILMENT.RDFS)) == ["a"]

    @pytest.mark.parametrize(("pattern", "expected"), [("?x a :Child", ["a", "c", "d"]), ("?x :hasParent ?z", ["a"])])
    def test_filter_exists_sees_the_entailed_triples(self, pattern, expected):
        g = _graph(HUNT)
        base = "PREFIX : <http://e/> SELECT ?x { VALUES ?x { :a :b :c :d } FILTER %s { " + pattern + " } }"
        assert _members(g.query(base % "EXISTS", entailment=ENTAILMENT.RDFS)) == expected
        absent = _members(g.query(base % "NOT EXISTS", entailment=ENTAILMENT.RDFS))
        assert sorted(set(expected) | set(absent)) == ["a", "b", "c", "d"] and not set(expected) & set(absent)

    def test_filter_exists_sees_the_rdf_regime_too(self):
        g = _graph("@prefix : <http://e/> . :a :p :b .")
        rows = g.query(
            "PREFIX : <http://e/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "SELECT ?x { VALUES ?x { :p :q } FILTER EXISTS { ?x a rdf:Property } }",
            entailment=ENTAILMENT.RDF,
        )
        assert _members(rows) == ["p"]


# ---- query shapes the rewrite must carry through ------------------------------------------------------------------------
class TestQueryShapes:
    def _g(self):
        return _graph(
            "@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . "
            "ex:C rdfs:subClassOf ex:D . ex:D rdfs:subClassOf ex:C . ex:a a ex:C ; ex:name 'A' . ex:b a ex:D ."
        )

    def test_select_star_projects_only_the_variables_of_the_query(self):
        res = self._g().query(_PREFIXES + "SELECT * WHERE { ?x a ex:D }", entailment=ENTAILMENT.RDFS)
        assert [v.value for v in res.vars] == ["x"]
        assert {r["x"].value for r in res} == {EX + "a", EX + "b"}

    def test_select_star_keeps_the_order_of_appearance(self):
        res = self._g().query(_PREFIXES + "SELECT * WHERE { ?s ex:name ?n . ?s a ?c }", entailment=ENTAILMENT.RDFS)
        assert [v.value for v in res.vars] == ["s", "n", "c"]

    def test_select_star_without_variables_raises(self):
        with pytest.raises(ExecutionError) as caught:
            self._g().query(_PREFIXES + "SELECT * WHERE { ex:a a ex:D }", entailment=ENTAILMENT.RDFS)
        assert caught.value.kind == "unsupported"

    def test_ask(self):
        g = self._g()
        assert g.query(_PREFIXES + "ASK { ex:a a ex:D }", entailment=ENTAILMENT.RDFS).askAnswer is True
        assert g.query(_PREFIXES + "ASK { ex:a a ex:D }").askAnswer is False

    def test_construct_and_construct_where(self):
        g = self._g()
        out = g.query(_PREFIXES + "CONSTRUCT { ?x a ex:K } WHERE { ?x a ex:D }", entailment=ENTAILMENT.RDFS)
        assert {t[0].value for t in out} == {EX + "a", EX + "b"}
        where = g.query(_PREFIXES + "CONSTRUCT WHERE { ?x a ex:D }", entailment=ENTAILMENT.RDFS)
        assert {(t[0].value, t[2].value) for t in where} == {(EX + "a", EX + "D"), (EX + "b", EX + "D")}

    def test_blank_node_in_the_pattern_is_a_variable(self):
        g = self._g()
        rows = g.query(_PREFIXES + "SELECT ?x WHERE { ?x a [ rdfs:subClassOf ex:C ] }", entailment=ENTAILMENT.RDFS)
        assert {r["x"].value for r in rows} == {EX + "a", EX + "b"}

    def test_optional_minus_union_subselect_aggregate(self):
        g = self._g()
        rdfs = ENTAILMENT.RDFS
        assert _col(g.query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:D . OPTIONAL { ?x ex:name ?n } FILTER(!BOUND(?n)) }", entailment=rdfs)) == [EX + "b"]
        assert _col(g.query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:D MINUS { ?x ex:name ?n } }", entailment=rdfs)) == [EX + "b"]
        assert len(list(g.query(_PREFIXES + "SELECT ?x WHERE { { ?x a ex:C } UNION { ?x a ex:K } }", entailment=rdfs))) >= 2
        assert _col(g.query(_PREFIXES + "SELECT DISTINCT ?x WHERE { { SELECT ?x WHERE { ?x a ex:D } } }", entailment=rdfs)) == [EX + "a", EX + "b"]
        n = next(iter(g.query(_PREFIXES + "SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE { ?x a ex:D }", entailment=rdfs)))["n"]
        assert n.value == "2"

    def test_a_cycle_does_not_duplicate_rows_of_a_path(self):
        # ex:C and ex:D are subclasses of each other: the zero-length and the one-or-more match of ex:C must count once
        g = self._g()
        rows = list(g.query(_PREFIXES + "SELECT ?c WHERE { ex:C rdfs:subClassOf ?c }", entailment=ENTAILMENT.RDFS))
        assert sorted(r["c"].value for r in rows) == [EX + "C", EX + "D"]

    def test_initbindings_and_initns(self):
        g = self._g()
        rows = g.query("SELECT ?x WHERE { ?x a ex:D }", initNs={"ex": EX}, initBindings={"x": N(EX + "b")}, entailment=ENTAILMENT.RDFS)
        assert _col(rows) == [EX + "b"]

    def test_a_pattern_not_widened_is_sent_as_written(self):
        text = "SELECT ?s WHERE { ?s <http://example.org/p>+ ?o }"
        assert rewrite_for_entailment(text, ENTAILMENT.RDFS) == text  # a property path is not widened (as before)
        assert rewrite_for_entailment("SELECT ?s WHERE { ?s <p> ?o }", ENTAILMENT.RDF) == "SELECT ?s WHERE { ?s <p> ?o }"

    def test_a_query_that_is_already_rewritten_is_left_alone(self):
        once = rewrite_for_entailment(_QUERY, ENTAILMENT.RDFS)
        assert rewrite_for_entailment(once, ENTAILMENT.RDFS) == once

    def test_an_update_is_not_a_query(self):
        with pytest.raises(Exception):  # noqa: B017  (a FormatError of kind sparql)
            rewrite_for_entailment("INSERT DATA { <a> <b> <c> }", ENTAILMENT.RDFS)

    def test_zero_length_path_on_a_constant_absent_from_the_data(self):
        # Oxigraph's ``p*`` does not match a constant that is not a node of the data; the rewrite must not depend on that
        g = _graph("@prefix ex: <http://example.org/> . ex:a ex:p ex:b .")
        assert _col(g.query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:NotInTheData }", entailment=ENTAILMENT.RDFS)) == []
        assert g.query(_PREFIXES + "ASK { ex:a ex:p ex:b }", entailment=ENTAILMENT.RDFS).askAnswer is True
        g.add((N(EX + "z"), N(RDF_TYPE), N(EX + "NotInTheData")))
        assert _col(g.query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:NotInTheData }", entailment=ENTAILMENT.RDFS)) == [EX + "z"]


class TestDataset:
    def _ds(self, union=True):
        ds = StarLayerDataset(default_union=union)
        ds.graph(N(EX + "g1")).parse(data="@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . ex:M rdfs:subClassOf ex:E . ex:alice a ex:M .", format="turtle")
        ds.graph(N(EX + "g2")).parse(data="@prefix ex: <http://example.org/> . ex:bob a ex:M .", format="turtle")
        return ds

    def test_union_default_graph_sees_the_schema_of_another_graph(self):
        assert _col(self._ds().query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:E }", entailment=ENTAILMENT.RDFS)) == [EX + "alice", EX + "bob"]

    def test_graph_pattern_reads_the_schema_of_that_graph_only(self):
        rows = self._ds().query(_PREFIXES + "SELECT ?g ?x WHERE { GRAPH ?g { ?x a ex:E } }", entailment=ENTAILMENT.RDFS)
        assert {(r["g"].value, r["x"].value) for r in rows} == {(EX + "g1", EX + "alice")}

    def test_graph_view_query(self):
        g1 = self._ds().graph(N(EX + "g1"))
        assert _col(g1.query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:E }", entailment=ENTAILMENT.RDFS)) == [EX + "alice"]

    def test_owl_regime_copy_leaves_the_dataset_alone(self):
        ds = self._ds()
        before = set(ds.store)
        rows = ds.query(_PREFIXES + "SELECT ?x WHERE { ?x a ex:E }", entailment=ENTAILMENT["OWL-RDF-Based"])
        assert _col(rows) == [EX + "alice", EX + "bob"]
        assert set(ds.store) == before and len(ds.store) == 3


# ---- OWL regimes: a temporary closed copy ---------------------------------------------------------------------------------
class TestEntailmentOwlRl:
    def test_original_graph_is_never_modified(self):
        g = _graph()
        before = set(g.store)
        list(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"]))
        assert set(g.store) == before and len(g) == 2

    def test_matches_rdfs_rewrite_for_the_subclass_case(self):
        g = _graph()
        assert _col(g.query(_QUERY, entailment=ENTAILMENT.RDFS)) == _col(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"])) == _alice()

    def test_covers_owl_constructs_rdfs_rewrite_cannot(self):
        g = _graph("@prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ex:Manager owl:equivalentClass ex:TeamLead . ex:alice a ex:Manager .")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:TeamLead }"
        assert list(g.query(q, entailment=ENTAILMENT.RDFS)) == []
        assert _col(g.query(q, entailment=ENTAILMENT["OWL-RDF-Based"])) == _alice()

    def test_a_mutation_in_between_is_seen(self):
        g = _graph()
        assert _col(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"])) == _alice()
        g.add((N(EX + "bob"), N(RDF_TYPE), N(EX + "Manager")))
        assert _col(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"])) == [EX + "alice", EX + "bob"]

    def test_matches_owlrl_semantics_directly(self):
        owlrl = pytest.importorskip("owlrl")
        import rdflib

        g = _graph("""@prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:partOf a owl:TransitiveProperty . ex:SalesTeam ex:partOf ex:SalesDept . ex:SalesDept ex:partOf ex:AcmeCorp .""")
        q = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ex:SalesTeam ex:partOf ?x }"
        via_query = set(_col(g.query(q, entailment=ENTAILMENT["OWL-RDF-Based"])))
        oracle = rdflib.Graph()
        oracle.parse(data=g.serialize(format="turtle"), format="turtle")
        owlrl.DeductiveClosure(owlrl.OWLRL_Semantics).expand(oracle)
        expected = {str(o) for o in oracle.objects(rdflib.URIRef(EX + "SalesTeam"), rdflib.URIRef(EX + "partOf"))}
        assert via_query == expected == {EX + "SalesDept", EX + "AcmeCorp"}

    def test_property_path_query_has_no_duplicate_rows(self):
        g = _graph("@prefix ex: <http://example.org/> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . ex:A rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:C .")
        q = "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> SELECT ?x ?y WHERE { ?x rdfs:subClassOf+ ?y }"
        via = sorted((r["x"].value, r["y"].value) for r in g.query(q, entailment=ENTAILMENT["OWL-RDF-Based"]))
        closure = g.infer(entailment=ENTAILMENT["OWL-RDF-Based"])
        flat = sorted((r["x"].value, r["y"].value) for r in closure.query(q))
        assert via == flat and len(via) == len(set(via))

    def test_graph_with_triple_terms(self):
        g = _graph()
        g.add((N(EX + "claim"), N("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies"), ox.Triple(N(EX + "bob"), N(EX + "knows"), N(EX + "carol"))))
        assert _col(g.query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"])) == _alice()
        assert len(g) == 3

    def test_unsupported_infer_mode_raises(self):
        with pytest.raises(ValueError, match="bogus"):
            _graph().query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], recompute="bogus")

    def test_infer_kwarg_is_ignored_without_an_owl_regime(self):
        assert list(_graph().query(_QUERY, recompute="bogus")) == []

    def test_engine_and_timeout_rejected_for_other_regimes(self):
        for regime in (None, ENTAILMENT.RDFS, ENTAILMENT["OWL-RDF-Based"]):
            with pytest.raises(ValueError, match="only meaningful for entailment="):
                _graph().query(_QUERY, entailment=regime, engine="rustdl")
            with pytest.raises(ValueError, match="only meaningful for entailment="):
                _graph().query(_QUERY, entailment=regime, timeout=5)

    def test_owl_direct_unknown_engine_raises(self):
        with pytest.raises(ValueError, match="Unsupported engine"):
            _graph().query(_QUERY, entailment=ENTAILMENT["OWL-Direct"], engine="bogus")


_Q_WOMAN = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Woman }"
_DISJUNCTIVE = """
    @prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Man owl:disjointWith ex:Woman .
    ex:Person rdfs:subClassOf [ owl:unionOf ( ex:Man ex:Woman ) ] .
    ex:alice a ex:Person, [ owl:complementOf ex:Man ] .
"""


@owl_dl_extra
@java_required
class TestEntailmentDirect:
    def test_direct_entailment_answers_disjunctive_query(self):
        g = _graph(_DISJUNCTIVE)
        before = set(g.store)
        assert _col(g.query(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"])) == _alice()
        assert set(g.store) == before

    def test_tiny_timeout_raises_a_timeout_error(self):
        with raises_kind("timeout"):
            list(_graph(_DISJUNCTIVE).query(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"], timeout=0.001))

    def test_inconsistent_ontology_propagates(self):
        g = _graph("@prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ex:Man owl:disjointWith ex:Woman . ex:bob a ex:Man, ex:Woman .")
        with raises_kind("inconsistent"):
            list(g.query("PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Man }", entailment=ENTAILMENT["OWL-Direct"]))


@rustdl_extra
class TestEntailmentDirectRustdl:
    def test_engine_rustdl_selectable_via_query(self):
        assert _col(_graph(_DISJUNCTIVE).query(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"], engine="rustdl")) == _alice()


# ---- each regime keeps its own entailed triples -------------------------------------------------------------------------
#
# ``recompute="never"`` uses whatever the graph kept for a regime and computes only when it kept nothing. A write after a regime was
# queried makes its kept triples out of date, so a regime that answers from fresh data has not used them.


def _add_bob() -> tuple:
    return (N(EX + "bob"), N(RDF_TYPE), N(EX + "Manager"))


_ALICE_AND_BOB = [EX + "alice", EX + "bob"]


class TestEachRegimeKeepsItsOwnEntailedTriples:
    def test_the_owl_rl_copy_is_not_used_by_the_rdfs_rewrite(self):
        g = _graph()
        rl = ENTAILMENT["OWL-RDF-Based"]
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()  # computed and kept
        g.add(_add_bob())
        assert _col(g.query(_QUERY, entailment=rl, recompute="never")) == _alice()  # the kept copy, out of date
        assert _col(g.query(_QUERY, entailment=ENTAILMENT.RDFS)) == _ALICE_AND_BOB  # the rewrite reads the data as it is

    @owl_dl_extra
    @java_required
    def test_owl_direct_does_not_use_the_owl_rl_copy_and_leaves_it_as_it_was(self):
        g = _graph()
        rl, direct = ENTAILMENT["OWL-RDF-Based"], ENTAILMENT["OWL-Direct"]
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()
        g.add(_add_bob())
        # OWL-Direct has kept nothing, so "never" computes it from the data as it is now
        assert _col(g.query(_QUERY, entailment=direct, recompute="never")) == _ALICE_AND_BOB
        # computing it did not replace the OWL-RL copy
        assert _col(g.query(_QUERY, entailment=rl, recompute="never")) == _alice()
        # and the OWL-Direct copy is now kept too: a later write does not reach it
        g.add((N(EX + "cy"), N(RDF_TYPE), N(EX + "Manager")))
        assert _col(g.query(_QUERY, entailment=direct, recompute="never")) == _ALICE_AND_BOB

    @owl_dl_extra
    @java_required
    @rustdl_extra
    def test_each_owl_direct_engine_keeps_its_own_copy(self):
        g = _graph()
        direct = ENTAILMENT["OWL-Direct"]
        assert _col(g.query(_QUERY, entailment=direct, engine="hermit")) == _alice()
        g.add(_add_bob())
        # nothing is kept for rustdl yet, so it is computed from the data as it is now
        assert _col(g.query(_QUERY, entailment=direct, engine="rustdl", recompute="never")) == _ALICE_AND_BOB
        # the HermiT copy is still the one from before the write
        assert _col(g.query(_QUERY, entailment=direct, engine="hermit", recompute="never")) == _alice()

    def test_always_computes_the_entailed_triples_and_keeps_none(self):
        g = _graph()
        rl = ENTAILMENT["OWL-RDF-Based"]
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()  # computed and kept
        g.add(_add_bob())
        assert _col(g.query(_QUERY, entailment=rl, recompute="always")) == _ALICE_AND_BOB  # computed again; what was kept is dropped
        g.add((N(EX + "cy"), N(RDF_TYPE), N(EX + "Manager")))
        # nothing is kept, so "never" computes them from the data as it is now. A kept copy would have stopped at bob.
        assert _col(g.query(_QUERY, entailment=rl, recompute="never")) == [*_ALICE_AND_BOB, EX + "cy"]

    def test_the_copy_is_made_once_and_again_after_a_write(self):
        g = _graph()
        rl = ENTAILMENT["OWL-RDF-Based"]

        def kept():
            (entry,) = union.version_of(g.store).entailed.entries.values()
            return entry.copy

        list(g.query(_QUERY, entailment=rl))
        first = kept()
        list(g.query(_QUERY, entailment=rl))
        assert kept() is first  # the same copy answered the second query: the store was not copied again
        g.add(_add_bob())
        list(g.query(_QUERY, entailment=rl))
        assert kept() is not first  # a write: the copy was made again
        g.clear_entailment_cache()
        assert not union.version_of(g.store).entailed.entries

    def test_the_prefixes_bound_after_the_copy_was_made_reach_it(self):
        g = _graph()
        rl = ENTAILMENT["OWL-RDF-Based"]
        list(g.query(_QUERY, entailment=rl))
        g.prefixes["e"] = EX
        assert _col(g.query("SELECT ?x WHERE { ?x a e:Employee }", entailment=rl, recompute="never")) == _alice()

    def test_the_default_recomputes_each_regime_after_a_write(self):
        g = _graph()
        rl = ENTAILMENT["OWL-RDF-Based"]
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()
        g.add(_add_bob())
        assert _col(g.query(_QUERY, entailment=rl)) == _ALICE_AND_BOB  # recompute="onChange": a write since the copy was made


class TestEntailedCopyFollowsItsOwnStore:
    """``recompute="onChange"`` compares the write count of the store of the graph: a write to another store does not make the copy
    again, a write to the same store does (through any wrapper of it), and so does a write on a raw store reference (``touch()``)."""

    @staticmethod
    def _count_builds(monkeypatch) -> list:
        from starlayer.graph.entailment import cache

        builds: list = []
        real = cache.build_entailed_copy

        def counting(*a, **kw):
            builds.append(1)
            return real(*a, **kw)

        monkeypatch.setattr(cache, "build_entailed_copy", counting)
        return builds

    def _kept(self, monkeypatch):
        g = _graph()
        builds = self._count_builds(monkeypatch)
        rl = ENTAILMENT["OWL-RDF-Based"]
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()
        assert len(builds) == 1  # kept
        return g, rl, builds

    def test_a_write_to_another_store_does_not_make_it_again(self, monkeypatch):
        g, rl, builds = self._kept(monkeypatch)
        _graph().add(_add_bob())
        StarLayerDataset().add((N(EX + "s"), N(EX + "p"), N(EX + "o"), N(EX + "g")))
        assert _col(g.query(_QUERY, entailment=rl)) == _alice()
        assert len(builds) == 1

    def test_a_write_through_another_wrapper_of_the_same_store_makes_it_again(self, monkeypatch):
        dataset = StarLayerDataset()
        dataset.parse(data=_DATA, format="turtle")
        graph = StarLayerGraph(dataset.as_store())
        builds = self._count_builds(monkeypatch)
        rl = ENTAILMENT["OWL-RDF-Based"]
        assert _col(graph.query(_QUERY, entailment=rl)) == _alice()
        graph.query(_QUERY, entailment=rl)
        assert len(builds) == 1
        dataset.add(_add_bob() + (ox.DefaultGraph(),))
        assert _col(graph.query(_QUERY, entailment=rl)) == _ALICE_AND_BOB
        assert len(builds) == 2

    def test_a_write_that_names_no_store_makes_it_again(self, monkeypatch):
        from starlayer.graph.execution import union

        g, rl, builds = self._kept(monkeypatch)
        g.store.add(ox.Quad(*_add_bob(), ox.DefaultGraph()))  # a raw store reference
        union.touch()
        assert _col(g.query(_QUERY, entailment=rl)) == _ALICE_AND_BOB
        assert len(builds) == 2


# ---- StarQuery -----------------------------------------------------------------------------------------------------------
class TestStarQueryOnOxGraph:
    def test_bound_entailment_is_used_and_can_be_overridden(self):
        g = _graph()
        q = StarQuery(_QUERY, entailment=ENTAILMENT.RDFS)
        assert _col(q.run(g)) == _alice()
        assert list(q.run(g, entailment=None)) == []
        assert _col(q.run(g, entailment=ENTAILMENT["OWL-RDF-Based"])) == _alice()
        assert _col(q.run(g)) == _alice()  # repeated, still bound

    def test_rdf_regime(self):
        q = StarQuery("SELECT ?p WHERE { ?p a <http://www.w3.org/1999/02/22-rdf-syntax-ns#Property> }", entailment=ENTAILMENT.RDF)
        assert set(_col(q.run(_graph()), "p")) == {RDF_TYPE, RDFS_SUBCLASS}

    def test_works_on_a_dataset(self):
        ds = StarLayerDataset()
        ds.parse(data=_DATA, format="turtle")
        assert _col(StarQuery(_QUERY, entailment=ENTAILMENT.RDFS).run(ds)) == _alice()

    def test_timeout_is_only_meaningful_for_owl_direct_as_before(self):
        g = _graph()
        with pytest.raises(ValueError, match="only meaningful"):
            StarQuery(_QUERY, timeout=5).run(g)
        with pytest.raises(ValueError, match="only meaningful"):
            StarQuery(_QUERY, entailment=ENTAILMENT.RDFS, timeout=5).run(g)

    @owl_dl_extra
    @java_required
    def test_timeout_reaches_owl_direct(self):
        with raises_kind("timeout"):
            StarQuery(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"], timeout=0.001).run(_graph(_DISJUNCTIVE))
