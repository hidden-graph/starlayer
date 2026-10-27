"""``ruleset_to_text`` keeps what the expressions mean (GitHub issue #80): parentheses, REGEX/REPLACE flags,
unary minus, function calls by IRI, IF, BNODE and the RDF 1.2 builtins."""

import pytest
from rdflib import Graph, Literal, URIRef
from starlayer.sparql.expr_text import render_expression
from starlayer.sparql.srl import parse_ruleset, ruleset_to_text

E = "http://e/"
PREFIXES = f"PREFIX : <{E}> PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> "


def _data():
    g = Graph()
    g.add((URIRef(E + "a"), URIRef(E + "p"), Literal(5)))
    g.add((URIRef(E + "a"), URIRef(E + "p"), Literal("ABC")))
    return g


def _inferred(ruleset):
    return sorted(str(o) for _s, _p, o in ruleset.infer(_data()))


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        ("(?y - 1) * 2", ["8"]),
        ("?y - (1 - 2)", ["6"]),
        ("2 * (?y + 1)", ["12"]),
        ("(?y + 1) * (?y - 1)", ["24"]),
        ("-?y", ["-5"]),
        ("?y - -1", ["6"]),
        ("xsd:integer(?y)", ["5"]),
        ("IF(?y > 3, 1, 2)", ["1"]),
        ("COALESCE(?y, 1)", ["5"]),
        ("!(?y > 1)", ["false"]),
        ("?y > 1 && ?y < 9 || false", ["true"]),
        ('REPLACE(STR(?y), "b", "x", "i")', ["5"]),  # the engine ignores REPLACE flags (rdflib item 10): only the text is compared
        ('REPLACE(STR(?y), "b", "x")', ["5", "ABC"]),
    ],
)
def test_assignment_expression_means_the_same_after_a_text_round_trip(expr, expected):
    ruleset = parse_ruleset(f"{PREFIXES}RULE {{ ?x :q ?z }} WHERE {{ ?x :p ?y SET(?z := {expr}) }}")
    again = parse_ruleset(ruleset_to_text(ruleset))
    assert _inferred(ruleset) == _inferred(again)
    assert set(expected) <= set(_inferred(again))


def test_arithmetic_keeps_its_parentheses():
    ruleset = parse_ruleset(f"{PREFIXES}RULE {{ ?x :q ?z }} WHERE {{ ?x :p ?y SET(?z := (?y - 1) * 2) }}")
    again = parse_ruleset(ruleset_to_text(ruleset))
    assert [str(o) for _s, _p, o in again.infer(_data()) if str(o).isdigit()] == ["8"]


def test_regex_flags_are_kept():
    text = f'{PREFIXES}RULE {{ ?x :s ?y }} WHERE {{ ?x :p ?y FILTER(REGEX(STR(?y), "abc", "i")) }}'
    ruleset = parse_ruleset(text)
    rendered = ruleset_to_text(ruleset)
    assert '"i"' in rendered
    assert sorted(map(str, parse_ruleset(rendered).infer(_data()))) == sorted(map(str, ruleset.infer(_data())))
    assert len(parse_ruleset(rendered).infer(_data())) == 1  # "ABC" matches only with the flag


@pytest.mark.parametrize("expr", ["-?y < 0", "BOUND(?y)", 'STRLEN(STR(?y)) > 1', "isTRIPLE(?y)", "BNODE() = BNODE()"])
def test_filter_text_has_no_placeholders_and_re_parses(expr):
    ruleset = parse_ruleset(f"{PREFIXES}RULE {{ ?x :s ?y }} WHERE {{ ?x :p ?y FILTER({expr}) }}")
    text = ruleset_to_text(ruleset)
    assert "{" not in text.split("FILTER", 1)[1].split("}", 1)[0]
    parse_ruleset(text)


def test_render_expression_refuses_what_it_cannot_render():
    from rdflib.plugins.sparql.parserutils import CompValue

    with pytest.raises(NotImplementedError):
        render_expression(CompValue("Builtin_EXISTS"))


def test_replace_flags_are_kept_in_the_text():
    ruleset = parse_ruleset(f'{PREFIXES}RULE {{ ?x :q ?z }} WHERE {{ ?x :p ?y SET(?z := REPLACE(STR(?y), "b", "x", "i")) }}')
    assert 'REPLACE(STR(?y), "b", "x", "i")' in ruleset_to_text(ruleset)
