"""Regression tests for the SRL bug hunt (parser, well-formedness, stratification, evaluation)."""

import pyoxigraph as ox
import pytest
from starlayer.graph.oxgraph import StarLayerGraph
from starlayer.sparql import srl

PRE = "PREFIX : <http://e/>\n"
XSD = "http://www.w3.org/2001/XMLSchema#"


def _data(update: str) -> StarLayerGraph:
    g = StarLayerGraph()
    g.update(PRE + "INSERT DATA { " + update + " }")
    return g


def _lit(value, datatype):
    return ox.Literal(value, datatype=ox.NamedNode(datatype))


def _g(*triples):
    g = StarLayerGraph(prefixes={})
    for s, p, o in triples:
        g.add((ox.NamedNode("http://e/" + s), ox.NamedNode("http://e/" + p), o))
    return g


def _hits(g, body, validate=True):
    rs = srl.parse_ruleset(PRE + "RULE { ?s :hit 1 } WHERE { ?s :p ?o " + body + " }", validate=validate)
    return len(list(rs.infer(g)))


INT1 = _lit("1", XSD + "integer")


# ---- stratification --------------------------------------------------------


def test_stratifier_unifies_repeated_variables():
    # the head `:x :ok :y` can never match the body pattern `?s :ok ?s`
    rs = srl.parse_ruleset(
        PRE + "RULE { :x :ok :y } WHERE { ?s :q ?o NOT { ?s :bad ?s } }\nRULE { ?s :bad ?s } WHERE { ?s :ok ?s }\n"
    )
    list(rs.infer(_data(":a :q :b")))


def test_stratifier_keeps_a_real_dependency_with_repeated_variables():
    rs = srl.parse_ruleset(
        PRE + "RULE { ?x :ok ?x } WHERE { ?x :q ?o NOT { ?x :bad ?x } }\nRULE { ?s :bad ?s } WHERE { ?s :ok ?s }\n"
    )
    with pytest.raises(srl.SRLError):
        list(rs.infer(_data(":a :q :b")))


# ---- expression evaluation -------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "expected"),
    [("?o = 1.0", 1), ("?o IN (1.0)", 1), ("?o != 1.0", 0), ("?o NOT IN (1.0)", 0), ("?o = 1e0", 1)],
)
def test_filter_equality_is_value_equality_across_numeric_datatypes(expr, expected):
    assert _hits(_g(("a", "p", INT1)), f"FILTER({expr})") == expected


def test_filter_between_two_bound_variables_uses_value_equality():
    g = _g(("a", "p", _lit("2", XSD + "integer")), ("a", "q", _lit("2", XSD + "double")))
    rs = srl.parse_ruleset(PRE + "RULE { ?s :same true } WHERE { ?s :p ?a . ?s :q ?b FILTER(?a = ?b) }")
    assert len(list(rs.infer(g))) == 1
    rs = srl.parse_ruleset(PRE + "RULE { ?s :same true } WHERE { ?s :p ?a . ?s :q ?b FILTER(?a != ?b) }")
    assert len(list(rs.infer(g))) == 0


@pytest.mark.parametrize("expr", ["?o != 1", "?o NOT IN (1)"])
def test_filter_comparison_with_an_unknown_datatype_is_an_error(expr):
    g = _g(("a", "p", _lit("x", "http://e/dt")))
    assert _hits(g, f"FILTER({expr})") == 0


def test_bare_variable_expressions_evaluate():
    g = _g(("s", "p", ox.NamedNode("http://e/o")))
    rs = srl.parse_ruleset(PRE + "RULE { :r :out ?z } WHERE { ?s :p ?y SET(?z := ?y) }", validate=False)
    assert [str(t[2]) for t in rs.infer(g)] == ["<http://e/o>"]
    assert _hits(_g(("a", "p", _lit("true", XSD + "boolean"))), "FILTER(?o)", validate=False) == 1


def test_if_with_a_variable_branch_evaluates():
    g = _g(("a", "p", _lit("true", XSD + "boolean")))
    assert _hits(g, "FILTER(IF(true, ?o, false))") == 1
    rs = srl.parse_ruleset(PRE + "RULE { ?s :hit ?w } WHERE { ?s :p ?o SET(?w := IF(true, ?o, false)) }")
    assert len(list(rs.infer(g))) == 1


def test_bnode_gives_a_fresh_blank_node_per_solution():
    g = _g(("a", "p", INT1), ("b", "p", INT1))
    rs = srl.parse_ruleset(PRE + 'RULE { ?s :b ?x } WHERE { ?s :p ?o SET(?x := BNODE("k")) }')
    nodes = {t[2] for t in rs.infer(g)}
    assert len(nodes) == 2
    assert ox.BlankNode("k") not in nodes


def test_a_blank_node_value_passes_through_an_expression():
    g = _g(("a", "p", ox.BlankNode("n")))
    rs = srl.parse_ruleset(PRE + "RULE { ?s :b ?x } WHERE { ?s :p ?o SET(?x := ?o) }", validate=False)
    assert {t[2] for t in rs.infer(g)} == {ox.BlankNode("n")}
    assert _hits(g, "FILTER(isBlank(?o))") == 1


# ---- bare-term expressions -----------------------------------------------------


@pytest.mark.parametrize("body", ["SET(?z := ?y)", "SET(?z := 7)", "SET(?z := :iri)", "FILTER(true)", "FILTER(?y)"])
def test_a_bare_term_is_a_valid_expression(body):
    srl.parse_ruleset(PRE + "RULE { :r :out ?y } WHERE { :s :q ?y " + body + " }")


# ---- a pyoxigraph Store with named graphs ---------------------------------------


def test_infer_on_a_store_uses_the_union_of_its_graphs():
    st = ox.Store()
    e = lambda n: ox.NamedNode("http://e/" + n)  # noqa: E731
    st.add(ox.Quad(e("a"), e("q"), e("b"), e("g1")))
    st.add(ox.Quad(e("a"), e("q"), e("b"), e("g2")))
    rs = srl.parse_ruleset(PRE + "RULE { ?x :p ?y } WHERE { ?x :q ?y }")
    assert [tuple(map(str, t)) for t in rs.infer(st)] == [("<http://e/a>", "<http://e/p>", "<http://e/b>")]


# ---- parser ---------------------------------------------------------------------


@pytest.mark.parametrize("filler", ["(", "STR("])
def test_deep_nesting_is_a_parse_error(filler):
    close = {"(": ")", "STR(": ")"}[filler]
    expr = filler * 300 + "?y" + close * 300
    with pytest.raises(srl.SRLParseError, match="nested too deeply"):
        srl.parse_ruleset(PRE + "RULE { :a :p :b } WHERE { :a :q ?y FILTER(" + expr + ") }")
