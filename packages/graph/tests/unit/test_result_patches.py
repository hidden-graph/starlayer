"""Confirms starlayergraph/__init__.py's import-time patch for the confirmed
plain-rdflib Result.__iter__ bug actually takes effect against real
Graph().query() calls - see starlayergraph/query/result_patches.py and
docs/rdflib-upstream-issues.md issue 6 for the root-cause writeup.
"""

import starlayergraph  # noqa: F401  (import-time patch application under test)
from rdflib import Graph

EX_A = "<http://example/a>"
EX_B = "<http://example/b>"
EX_C = "<http://example/c>"
EX_NOPE = "<http://example/nope>"


def _graph_with_one_fact() -> Graph:
    g = Graph()
    g.parse(data=f"{EX_A} {EX_B} {EX_C} .", format="nt")
    return g


class TestSelectStarOverGroundPatternIteration:
    def test_matching_fact_yields_one_row_on_iteration(self) -> None:
        g = _graph_with_one_fact()
        r = g.query(f"SELECT * WHERE {{ {EX_A} {EX_B} {EX_C} . }}")
        rows = list(r)
        assert len(rows) == 1
        assert tuple(rows[0]) == ()

    def test_matching_fact_bindings_and_len_agree_with_iteration(self) -> None:
        g = _graph_with_one_fact()
        r = g.query(f"SELECT * WHERE {{ {EX_A} {EX_B} {EX_C} . }}")
        assert r.bindings == [{}]
        assert len(r) == 1
        assert len(list(r)) == 1

    def test_matching_fact_agrees_with_ask(self) -> None:
        g = _graph_with_one_fact()
        ask = g.query(f"ASK {{ {EX_A} {EX_B} {EX_C} . }}")
        assert ask.askAnswer is True

    def test_nonmatching_fact_yields_zero_rows(self) -> None:
        g = _graph_with_one_fact()
        r = g.query(f"SELECT * WHERE {{ {EX_A} {EX_B} {EX_NOPE} . }}")
        assert list(r) == []
        assert r.bindings == []
        assert len(r) == 0

    def test_matching_and_nonmatching_are_distinguishable_via_iteration(self) -> None:
        # The bug this patch fixes made both of these collapse to the same
        # (wrong) `[]` when iterated - the whole point of the fix is that
        # they no longer do.
        g = _graph_with_one_fact()
        matching = list(g.query(f"SELECT * WHERE {{ {EX_A} {EX_B} {EX_C} . }}"))
        nonmatching = list(g.query(f"SELECT * WHERE {{ {EX_A} {EX_B} {EX_NOPE} . }}"))
        assert matching != nonmatching
        assert len(matching) == 1
        assert len(nonmatching) == 0


class TestOrdinaryQueriesUnaffected:
    def test_query_with_real_variables_still_returns_rows_normally(self) -> None:
        g = _graph_with_one_fact()
        r = g.query(f"SELECT ?s ?p WHERE {{ ?s ?p {EX_C} . }}")
        rows = list(r)
        assert len(rows) == 1
        assert str(rows[0].s) == "http://example/a"
        assert str(rows[0].p) == "http://example/b"

    def test_ask_query_still_works(self) -> None:
        g = _graph_with_one_fact()
        assert list(g.query(f"ASK {{ {EX_A} {EX_B} {EX_C} . }}")) == [True]

    def test_construct_query_still_works(self) -> None:
        g = _graph_with_one_fact()
        r = g.query(f"CONSTRUCT {{ {EX_A} {EX_B} {EX_C} . }} WHERE {{ {EX_A} {EX_B} {EX_C} . }}")
        triples = list(r)
        assert len(triples) == 1
