"""Regression tests for the SRL bug hunt (parser, well-formedness, stratification, evaluation)."""

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError
from starlayer.graph import StarLayerGraph
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


def _hits(g, body):
    rs = srl.parse_ruleset(PRE + "RULE { ?s :hit 1 } WHERE { ?s :p ?o " + body + " }")
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
        PRE + "RULE { ?x :ok ?x } WHERE { ?x :q ?o NOT { ?x :bad ?x } }\nRULE { ?s :bad ?s } WHERE { ?s :ok ?s }\n",
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
    rs = srl.parse_ruleset(PRE + "RULE { :r :out ?z } WHERE { ?s :p ?y SET(?z := ?y) }")
    assert [str(t[2]) for t in rs.infer(g)] == ["<http://e/o>"]
    assert _hits(_g(("a", "p", _lit("true", XSD + "boolean"))), "FILTER(?o)") == 1


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
    rs = srl.parse_ruleset(PRE + "RULE { ?s :b ?x } WHERE { ?s :p ?o SET(?x := ?o) }")
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
    with pytest.raises(FormatError, match="nested too deeply"):
        srl.parse_ruleset(PRE + "RULE { :a :p :b } WHERE { :a :q ?y FILTER(" + expr + ") }")


@pytest.mark.parametrize("assign", ["?y : = ?z + 1", "?y :\n= ?z + 1", "?y :# comment\n= ?z + 1"])
def test_a_split_assignment_operator_is_rejected(assign):
    text = PRE + "RULE { ?x :r ?y } WHERE { ?x :q ?z SET(" + assign + ") }"
    with pytest.raises(FormatError):
        srl.parse_ruleset(text)


def test_the_assignment_operator_parses():
    srl.parse_ruleset(PRE + "RULE { ?x :r ?y } WHERE { ?x :q ?z SET(?y := ?z + 1) }")


@pytest.mark.parametrize("number", ["+5", "+5.0", "+5e0", "-5"])
def test_a_signed_number_after_a_predicate_is_the_object(number):
    rs = srl.parse_ruleset(PRE + "RULE { :a :p :b } WHERE { :a :q " + number + " }")
    assert rs.rules[0].body[0].object.value == number


def test_a_path_modifier_before_a_number_still_parses_in_sparql():
    from starlayer.sparql.check import check_query

    assert check_query(PRE + "SELECT * WHERE { ?s :q+ 5 }").ok
    assert check_query(PRE + "SELECT * WHERE { ?s :q +5 }").ok


# ---- custom functions ---------------------------------------------------------


@pytest.mark.parametrize("body", ["SET(?z := <http://e/f>(?y))", "FILTER(<http://e/f>(?y))"])
@pytest.mark.parametrize("validate", [True, False])
def test_a_function_called_by_iri_other_than_a_cast_is_rejected_at_parse_time(body, validate):
    with pytest.raises(FormatError, match="not one SRL supports"):
        srl.parse_ruleset(PRE + "RULE { :r :out ?z } WHERE { :s :q ?y " + body + " }")


def test_an_xsd_cast_is_not_a_custom_function():
    srl.parse_ruleset(PRE + f"RULE {{ :r :out ?z }} WHERE {{ :s :q ?y SET(?z := <{XSD}integer>(?y)) }}")


# ---- well-formedness of triple terms and DATA ----------------------------------


def test_a_triple_term_with_a_triple_term_subject_is_rejected():
    nested = "<<( <<( :a :b :c )>> :a ?y )>>"
    for text in ("RULE { ?x :q " + nested + " } WHERE { ?x :p ?y }", "DATA { :a :p <<( <<( :a :b :c )>> :p :b )>> }"):
        rs = srl.parse_ruleset(PRE + text)  # it loads; running it is refused
        with pytest.raises(FormatError):
            rs.infer(StarLayerGraph())


def test_a_nested_triple_term_in_object_position_is_fine():
    srl.parse_ruleset(PRE + "RULE { ?x :q <<( :a :a <<( :a :b ?y )>> )>> } WHERE { ?x :p ?y }")


def test_a_data_triple_with_a_literal_subject_is_an_srl_error():
    # the srl: shapes reject it at parse; with validate=False it is still caught when the rules run
    rs = srl.parse_ruleset(PRE + "DATA { \"a\" :p :b }")
    with pytest.raises(srl.SRLError):
        rs.infer(StarLayerGraph())


# ---- evaluation robustness ------------------------------------------------------


def test_a_literal_in_a_triple_term_subject_matches_nothing():
    g = _g(("z", "p", ox.Literal("lit")))
    rs = srl.parse_ruleset(PRE + "RULE { ?z :hit 1 } WHERE { ?z :p ?x . ?w :p <<( ?x :p :n )>> }")
    assert list(rs.infer(g)) == []


def test_a_literal_in_a_triple_term_subject_keeps_the_other_solutions():
    t = ox.Triple(ox.NamedNode("http://e/a"), ox.NamedNode("http://e/p"), ox.NamedNode("http://e/n"))
    g = _g(("z", "p", ox.Literal("lit")), ("z", "p", ox.NamedNode("http://e/a")), ("w", "p", t))
    rs = srl.parse_ruleset(PRE + "RULE { ?z :hit ?x } WHERE { ?z :p ?x . ?w :p <<( ?x :p :n )>> }")
    assert [str(x[2]) for x in rs.infer(g)] == ["<http://e/a>"]


def test_a_variable_named_like_the_internal_target_evaluates():
    g = _g(("a", "p", INT1))
    rs = srl.parse_ruleset(PRE + "RULE { ?s :r ?w } WHERE { ?s :p ?__srl_value SET(?w := ?__srl_value + 1) }")
    assert len(list(rs.infer(g))) == 1


def test_a_variable_name_above_the_bmp_is_refused_when_the_rules_run():
    rs = srl.parse_ruleset(PRE + "RULE { ?s :r ?\U00010000 } WHERE { ?s :p ?\U00010000 }")  # it loads
    with pytest.raises(FormatError, match="unsupported_variable_name"):
        rs.infer(StarLayerGraph())


# ---- rdflib graphs and direction-tagged literals ----------------------------------


# ---- decoding a damaged tree -----------------------------------------------------


def test_every_single_triple_deletion_decodes_or_raises_srl_decode_error():
    rs = srl.parse_ruleset(PRE + "RULE { :a :p <<( :a :b ?y )>> } WHERE { :a :q ?y FILTER(?y > 1) NOT { :a :z ?y } }")
    g, root = srl.ruleset_to_tree(rs)
    triples = list(g)
    for dropped in triples:
        g2 = StarLayerGraph()
        g2.extend([t for t in triples if t != dropped])
        try:
            srl.tree_to_ruleset(g2, root)
        except srl.SRLError:
            pass
