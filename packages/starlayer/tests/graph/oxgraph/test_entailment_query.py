"""Query-time entailment on ``OxGraph`` / ``OxDataset`` / ``StarQuery``, migrated from ``tests/graph/unit/test_entailment.py``,
``test_entailment_hunt2.py`` and ``test_entailment_direct.py`` (which run on ``StarLayerGraph``).

RDF and RDFS are a rewrite of the query (``starlayer.sparql.sqe.entailment``); the OWL regimes run the query on a temporary copy
of the store that ``infer()`` has closed. Differences from the originals:

- the OWL regimes keep no cache (a copy is made per query), so the tests of ``infer="changed" / "cached" / "always"`` reuse
  (``_owl_rl_cache``, ``_owl_dl_cache``) and of the union-with-delta design (``_UnionForQuery``) have no counterpart; ``infer=`` is
  still checked and a bad value raises ``ValueError``;
- ``entailment='native'`` / the ``rdf-1.2`` backend tests do not apply (the wrapper is always Oxigraph);
- the OWL-Direct tests need ``owlready2`` + Java (HermiT) or ``rustdl`` and skip without them, as before.
"""

from __future__ import annotations

import shutil

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import OxDataset, OxGraph
from starlayer.graph.oxgraph.helpers.entailment import ENTAILMENT
from starlayer.sparql.sqe.entailment import (
    EntailmentRewriteError,
    rewrite_for_entailment,
)
from starlayer.sparql.star_query import StarQuery

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

owl_dl_extra = pytest.mark.skipif(not _OWLREADY2, reason="owlready2 not importable (pip install starlayer[hermit])")
java_required = pytest.mark.skipif(shutil.which("java") is None, reason="no Java runtime on PATH (HermiT needs a JVM)")
rustdl_extra = pytest.mark.skipif(not _RUSTDL, reason="rustdl not importable (pip install starlayer[rustdl])")

_DATA = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:Manager rdfs:subClassOf ex:Employee .
    ex:alice a ex:Manager .
"""
_QUERY = "PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Employee }"
_PREFIXES = "PREFIX ex: <http://example.org/> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "


def _graph(data: str = _DATA) -> OxGraph:
    g = OxGraph()
    g.parse(data=data, format="turtle")
    return g


def _col(result, name: str = "x") -> list[str]:
    return sorted(getattr(r[name], "value", str(r[name])) for r in result)


def _alice() -> list[str]:
    return [EX + "alice"]


# ---- per-query, not per-graph -----------------------------------------------------------------------------------------
class TestEntailmentIsPerQueryNotPerGraph:
    def test_unsupported_entailment_raises(self):
        with pytest.raises(NotImplementedError, match="entailment must be one of"):
            _graph().query(_QUERY, entailment="owl")

    def test_d_entailment_raises(self):
        with pytest.raises(NotImplementedError):
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
        from starlayer.graph.graph.entailment_regimes import ENTAILMENT as OLD

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
        with pytest.raises(EntailmentRewriteError):
            self._g().query(_PREFIXES + "SELECT * WHERE { ex:a a ex:D }", entailment=ENTAILMENT.RDFS)

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
        with pytest.raises(Exception):  # noqa: B017  (a syntax error or EntailmentRewriteError)
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
        ds = OxDataset(default_union=union)
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
            _graph().query(_QUERY, entailment=ENTAILMENT["OWL-RDF-Based"], infer="bogus")

    def test_infer_kwarg_is_ignored_without_an_owl_regime(self):
        assert list(_graph().query(_QUERY, infer="bogus")) == []

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

    def test_tiny_timeout_raises_reasoning_timeout_error(self):
        from starlayer.graph.graph._timeout import ReasoningTimeoutError

        with pytest.raises(ReasoningTimeoutError):
            list(_graph(_DISJUNCTIVE).query(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"], timeout=0.001))

    def test_inconsistent_ontology_propagates(self):
        from starlayer.graph.graph.owl_dl import InconsistentOntologyError

        g = _graph("@prefix ex: <http://example.org/> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ex:Man owl:disjointWith ex:Woman . ex:bob a ex:Man, ex:Woman .")
        with pytest.raises(InconsistentOntologyError):
            list(g.query("PREFIX ex: <http://example.org/> SELECT ?x WHERE { ?x a ex:Man }", entailment=ENTAILMENT["OWL-Direct"]))


@rustdl_extra
class TestEntailmentDirectRustdl:
    def test_engine_rustdl_selectable_via_query(self):
        assert _col(_graph(_DISJUNCTIVE).query(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"], engine="rustdl")) == _alice()


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
        ds = OxDataset()
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
        from starlayer.graph.graph._timeout import ReasoningTimeoutError

        with pytest.raises(ReasoningTimeoutError):
            StarQuery(_Q_WOMAN, entailment=ENTAILMENT["OWL-Direct"], timeout=0.001).run(_graph(_DISJUNCTIVE))
