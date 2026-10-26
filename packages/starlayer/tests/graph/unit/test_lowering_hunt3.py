"""SPARQL over triple terms (the lowering) from the third bug hunt (GitHub issue #134). Each class is a repro from the
issue; the expected rows are what SPARQL 1.1/1.2 Query define and what Oxigraph (the in-process native backend) returns.
"""

from __future__ import annotations

import pytest
from rdflib import Literal, URIRef
from starlayer import StarLayerDataset, StarLayerGraph
from starlayer.graph import TripleTerm
from starlayer.graph.model.encoding import TT_NS

PRE = "PREFIX : <http://e/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
DATA = """@prefix : <http://e/> .
:a :p :b . :b :p :c . :c :p :a .
:a :r <<( :a :p :b )>> . :b :r <<( :b :p :c )>> .
<< :a :p :b ~ :e1 >> :src :x . << :b :p :c ~ :e2 >> :src :x .
"""


def E(name: str) -> URIRef:
    return URIRef("http://e/" + name)


def make(backend: str, data: str = DATA) -> StarLayerGraph:
    if backend == "native":
        pytest.importorskip("oxrdflib")
        import oxrdflib

        g = StarLayerGraph(store=oxrdflib.OxigraphStore(), backend="rdf-1.2")
    else:
        g = StarLayerGraph()
    g.parse(data=data, format="turtle12")
    return g


def rows(g, query: str) -> list[dict]:
    res = g.query(PRE + query)
    return [{str(v): row[i] for i, v in enumerate(res.vars)} for row in res]


def pairs(g, query: str, *names: str) -> set[tuple]:
    return {tuple(r[n] for n in names) for r in rows(g, query)}


@pytest.fixture(params=["default", "native"])
def graph(request):
    return make(request.param)


class TestMinusOverTripleTerms:
    """MINUS whose shared variables occur only inside a triple term removed nothing on the default store."""

    @pytest.mark.parametrize(
        "right",
        [
            "<< ?x :p ?y >> :src ?v",
            "?x :r <<( ?x :p ?y )>>",
            "?z :r <<( ?x :p ?y )>>",
            "<< ?x :p ?y >> :src :x",
        ],
    )
    def test_minus_removes_the_matching_solutions(self, graph, right) -> None:
        got = pairs(graph, "SELECT ?x ?y WHERE { ?x :p ?y MINUS { " + right + " } }", "x", "y")
        assert got == {(E("c"), E("a"))}


class TestAggregatesOverTripleTerms:
    def test_min_max_return_triple_terms(self) -> None:
        g = make("default")
        (row,) = rows(g, "SELECT (MIN(?t) AS ?n) (MAX(?t) AS ?m) WHERE { ?s :r ?t }")
        tts = {TripleTerm(E("a"), E("p"), E("b")), TripleTerm(E("b"), E("p"), E("c"))}
        assert {row["n"], row["m"]} == tts
        assert row["n"] != row["m"]
        for value in row.values():
            assert not str(value).startswith(TT_NS)

    def test_min_max_of_iris_are_iris(self) -> None:
        g = make("default")
        (row,) = rows(g, "SELECT (MIN(?o) AS ?n) (MAX(?o) AS ?m) WHERE { :a :p ?o }")
        assert row == {"n": E("b"), "m": E("b")}

    def test_triple_term_sorts_after_iris_in_max(self) -> None:
        g = make("default", "@prefix : <http://e/> . :s :v :z . :s :v <<( :a :p :b )>> .")
        (row,) = rows(g, "SELECT (MAX(?o) AS ?m) (MIN(?o) AS ?n) WHERE { :s :v ?o }")
        assert row == {"m": TripleTerm(E("a"), E("p"), E("b")), "n": E("z")}

    @pytest.mark.parametrize("backend", ["default", "native"])
    @pytest.mark.parametrize(
        "agg",
        ["GROUP_CONCAT(STR(?o))", "GROUP_CONCAT(?o)", "MAX(STR(?o))", "MIN(STR(?o))"],
    )
    def test_error_in_an_aggregate_argument_leaves_it_unbound(self, backend, agg) -> None:
        g = make(backend, "@prefix : <http://e/> . :a :p :b . :a :p <<( :c :q 1 )>> .")
        (row,) = rows(g, "SELECT (" + agg + " AS ?g) WHERE { :a :p ?o }")
        assert row["g"] is None

    def test_group_concat_without_errors_is_unchanged(self) -> None:
        g = make("default", '@prefix : <http://e/> . :a :p "x", "y" .')
        (row,) = rows(g, "SELECT (GROUP_CONCAT(?o; separator=',') AS ?g) WHERE { :a :p ?o }")
        assert sorted(str(row["g"]).split(",")) == ["x", "y"]


class TestZeroLengthPaths:
    """The nodes of a graph are the subjects and objects of its triples, not the encoding of triple terms."""

    LEAKS = {URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#PropositionForm"), E("p")}

    @pytest.mark.parametrize("path", ["?x :p? ?y", "?x :zz* ?y", "?x (:p|^:p)* ?y", "?x :zz? ?x"])
    def test_no_encoding_nodes(self, path) -> None:
        g = make("default")
        seen = {v for r in rows(g, "SELECT * WHERE { " + path + " }") for v in r.values()}
        assert not seen & self.LEAKS
        assert not any(isinstance(v, URIRef) and str(v).startswith(TT_NS) for v in seen)

    @pytest.mark.parametrize("path", ["?x :p? ?y", "?x :zz* ?y", "?x (:p|^:p)* ?y"])
    def test_same_rows_as_native(self, path) -> None:
        q = "SELECT ?x ?y WHERE { " + path + " }"
        default = rows(make("default"), q)
        native = rows(make("native"), q)
        assert len(default) == len(native)
        assert {(r["x"], r["y"]) for r in default} == {(r["x"], r["y"]) for r in native}

    def test_triple_term_components_are_not_nodes(self) -> None:
        g = make("default", "@prefix : <http://x/> . :c :p <<( :a :b 2 )>> .\n")
        got = {r["x"] for r in rows(g, "SELECT ?x WHERE { ?x <http://x/zz>? ?x }")}
        assert got == {URIRef("http://x/c"), TripleTerm(URIRef("http://x/a"), URIRef("http://x/b"), Literal(2))}

    def test_reifier_data_does_not_add_predicate_or_class_nodes(self) -> None:
        g = make("default", "@prefix : <http://x/> . :c :p 1 ~ :r .\n")
        got = {r["x"] for r in rows(g, "SELECT ?x WHERE { ?x <http://x/zz>? ?x }")}
        assert URIRef("http://x/p") not in got
        assert len(got) == 4  # 1, :c, :r and the triple term


class TestSubqueryLimitKeepsDuplicates:
    DATA = "@prefix ex: <http://e/> . ex:s ex:says ex:b . ex:s2 ex:says ex:b ."
    Q = "SELECT ?x ?t WHERE { ?x ex:says ?t { SELECT ?t WHERE { ?q ex:says ?t } LIMIT 5 } }"

    def test_graph(self) -> None:
        g = StarLayerGraph()
        g.parse(data=self.DATA, format="turtle12")
        assert len(list(g.query("PREFIX ex: <http://e/> " + self.Q))) == 4

    def test_dataset(self) -> None:
        ds = StarLayerDataset()
        ds.default_graph.parse(data=self.DATA, format="turtle12")
        assert len(list(ds.query("PREFIX ex: <http://e/> " + self.Q))) == 4

    def test_count_over_a_limited_subquery(self) -> None:
        g = StarLayerGraph()
        g.parse(data=self.DATA, format="turtle12")
        q = "PREFIX ex: <http://e/> SELECT (COUNT(*) AS ?n) WHERE { { SELECT ?t WHERE { ?q ex:says ?t } LIMIT 5 } { SELECT ?t WHERE { ?q ex:says ?t } OFFSET 0 } }"
        (row,) = list(g.query(q))
        assert row[0].toPython() == 4


class TestTripleFunctionComposition:
    DATA = "@prefix : <http://e/> . :s :says <<( :a :p :b )>> ."

    @pytest.mark.parametrize(
        "expr",
        [
            "TRIPLE(SUBJECT(?t), PREDICATE(?t), OBJECT(?t))",
            "TRIPLE(SUBJECT(?t), :p, :b)",
            "TRIPLE(:a, PREDICATE(?t), :b)",
            "TRIPLE(:a, :p, OBJECT(?t))",
        ],
    )
    def test_rebuilds_the_triple_term(self, expr) -> None:
        g = make("default", self.DATA)
        (row,) = rows(g, "SELECT ?u WHERE { ?x :says ?t . BIND(" + expr + " AS ?u) }")
        assert row["u"] == TripleTerm(E("a"), E("p"), E("b"))

    def test_rebuilt_term_equals_the_original(self) -> None:
        g = make("default", self.DATA)
        out = rows(
            g,
            "SELECT ?t WHERE { ?x :says ?t . BIND(TRIPLE(SUBJECT(?t), PREDICATE(?t), OBJECT(?t)) AS ?u) FILTER(?u = ?t) }",
        )
        assert len(out) == 1


class TestSharedVariablesOutsideTheTripleTerm:
    DATA = "@prefix : <http://e/> . :b :q :c . :s :says <<( :b :q :c )>> ."

    @pytest.mark.parametrize("backend", ["default", "native"])
    def test_group_by_variable_bound_only_inside_a_triple_term(self, backend) -> None:
        g = make(backend, self.DATA)
        assert pairs(g, "SELECT ?x WHERE { ?s :says <<( ?x :q ?y )>> } GROUP BY ?x", "x") == {(E("b"),)}
        out = rows(g, "SELECT ?x (COUNT(*) AS ?n) WHERE { ?s :says <<( ?x :q ?y )>> } GROUP BY ?x")
        assert [(r["x"], r["n"].toPython()) for r in out] == [(E("b"), 1)]
        out = rows(g, "SELECT ?x (MAX(?y) AS ?m) WHERE { ?s :says <<( ?x :q ?y )>> } GROUP BY ?x")
        assert [(r["x"], r["m"]) for r in out] == [(E("b"), E("c"))]

    @pytest.mark.parametrize("backend", ["default", "native"])
    def test_group_by_through_a_reifier_and_in_a_subquery(self, backend) -> None:
        g = make(backend, "@prefix : <http://e/> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . :b :q :c . :r rdf:reifies <<( :b :q :c )>> .")
        assert pairs(g, "SELECT ?x WHERE { ?r rdf:reifies <<( ?x :q ?y )>> } GROUP BY ?x", "x") == {(E("b"),)}
        assert pairs(g, "SELECT ?x WHERE { { SELECT ?x WHERE { ?r rdf:reifies <<( ?x :q ?y )>> } GROUP BY ?x } }", "x") == {
            (E("b"),)
        }

    @pytest.mark.parametrize("backend", ["default", "native"])
    @pytest.mark.parametrize(
        ("values", "expected"),
        [
            ("VALUES ?x { :a UNDEF }", [{"s": E("s"), "x": E("b"), "y": E("c")}]),
            ("VALUES (?x ?y) { (:a :c) (:b UNDEF) }", [{"s": E("s"), "x": E("b"), "y": E("c")}]),
            ("VALUES ?x { :b UNDEF }", [{"s": E("s"), "x": E("b"), "y": E("c")}] * 2),
            ("VALUES ?x { :a }", []),
        ],
    )
    def test_values_with_undef_joined_with_a_triple_term(self, backend, values, expected) -> None:
        g = make(backend, self.DATA)
        got = rows(g, "SELECT * WHERE { " + values + " ?s :says <<( ?x :q ?y )>> }")
        key = lambda r: sorted(r.items())  # noqa: E731
        assert sorted(got, key=key) == sorted(expected, key=key)

    @pytest.mark.parametrize("backend", ["default", "native"])
    def test_values_with_undef_through_a_reifier(self, backend) -> None:
        g = make(backend, "@prefix : <http://e/> . :b :q :c . :r :says <<( :b :q :c )>> . :r2 :says <<( :a :q :c )>> .")
        got = rows(g, "SELECT ?r ?x WHERE { VALUES ?x { :a :b UNDEF } ?r :says <<( ?x :q :c )>> }")
        assert len(got) == 4  # :a -> r2, :b -> r, UNDEF -> r and r2
