"""Oxigraph differential for the hand-written parser ``parse_sparql`` (needs ``pyoxigraph``).

Oxigraph (``spargebra``) is an independent SPARQL parser, so every disagreement is either a bug in ours or a place
where Oxigraph is laxer or older than the SPARQL 1.2 draft. Nothing is skipped: each disagreement is registered below
with the verdict (who is right and why), and a registry entry that stops being a disagreement fails the test, so the
list can only shrink as Oxigraph improves.

1. Every positive W3C query (1.1 syntax + evaluation queries, 1.2 syntax + evaluation queries): the text rendered by
   ``sqe_tree_to_text`` from our tree must be accepted by Oxigraph.
2. Every negative W3C query: our parser rejects the original text; Oxigraph's verdict is compared.
3. The semantic-rule table (``parse_sparql_rules.py``) and the production corpus: verdicts compared.
"""

from __future__ import annotations

import pytest
from starlayer.sparql.parse_sparql import (
    SparqlSyntaxError,
    parse_sparql,
    sparql_to_tree,
)
from starlayer.sparql.sqe import sqe_tree_to_text

from .parse_sparql_conformance.corpus import CASES
from .parse_sparql_rules import RULES
from .parse_sparql_support import entry_key, w3c11_entries, w3c_entries

ox = pytest.importorskip("pyoxigraph")

BASE = "http://example/base/"  # the W3C queries use relative IRIs and rely on a base; Oxigraph wants one


def ox_accepts(text: str) -> bool:
    """True when Oxigraph's parser accepts the query (a custom function is a planning error, not a syntax error)."""
    try:
        ox.Store().query(text, base_iri=BASE)
    except SyntaxError as e:
        return "custom function" in str(e)
    except Exception:  # noqa: BLE001 - evaluation errors on the empty store are fine
        return True
    return True


def _positive():
    out = [(e.key, e.read()) for e in w3c11_entries("PositiveSyntaxTest", "QueryEvaluationTest", ext=".rq")]
    out += [
        ("12/" + entry_key(e), e.read(e.query_file))
        for e in w3c_entries("PositiveSyntaxTest", "QueryEvaluationTest")
        if e.query_file.endswith(".rq")
    ]
    return out


def _negative():
    out = [(e.key, e.read()) for e in w3c11_entries("NegativeSyntaxTest", ext=".rq")]
    out += [
        ("12/" + entry_key(e), e.read(e.query_file))
        for e in w3c_entries("NegativeSyntaxTest")
        if e.query_file.endswith(".rq")
    ]
    return out


POSITIVE, NEGATIVE = _positive(), _negative()

# Positive W3C queries Oxigraph itself rejects (the rendered text is rejected too). Ours is right in both.
OX_REJECTS_VALID = {
    "11/bindings/values-construct-group-by":
        "CONSTRUCT ... GROUP BY: ConstructQuery ::= ... SolutionModifier allows GROUP BY; Oxigraph reads it as SELECT *.",
    "12/grouping/select-variable-reuse":
        "(?count + 1 AS ?x) after (COUNT(?v) AS ?count): a later SELECT expression may use an earlier alias "
        "(18.3.4); Oxigraph reports the variable unbound.",
}

# Negative W3C queries Oxigraph accepts. We reject them, as the suite requires.
OX_ACCEPTS_INVALID = {
    "12/syntax-triple-terms-negative/tripleterm-subject-03":
        "ExprTripleTermSubject ::= iri | Var: a nested triple term cannot be the subject in an expression.",
    "12/syntax-triple-terms-negative/tripleterm-subject-06":
        "ExprTripleTermSubject ::= iri | Var: a nested triple term cannot be the subject in an expression.",
    "12/syntax/nested-aggregate-functions":
        "19.7 note: the expression argument of an aggregate cannot contain an aggregate.",
}

# Semantic-rule and corpus disagreements: text -> (who is right, why). ``ours`` is the verdict we give.
_BGP = "19.6 / 10.1: the same blank node label cannot be used in two basic graph patterns; BIND and VALUES end the BGP."
RULE_DIFFERENCES: dict[str, str] = {
    "SELECT * { _:a :p ?x . BIND(1 AS ?z) _:a :q ?y }": "ours right. " + _BGP,
    "SELECT * { _:a :p ?x . VALUES ?v { 1 } _:a :q ?y }": "ours right. " + _BGP,
    "SELECT * { SERVICE ?g { ?s ?p ?o } BIND(1 AS ?g) }":
        "ours right. 18.3.1: in SERVICE X { P } the variable X is in scope (Oxigraph rejects the same for GRAPH).",
    "SELECT (1 AS ?c) { ?s ?p ?o } GROUP BY (?s AS ?c)":
        "ours right. GROUP BY (expr AS ?c) puts ?c in scope; Oxigraph ignores GROUP BY aliases (see the next entries).",
    "SELECT (COUNT(?v) AS ?count) (?count + 1 AS ?next) { VALUES ?v { 1 2 } }":
        "ours right. A later SELECT expression may use an earlier alias (W3C 1.2 grouping/select-variable-reuse).",
    "SELECT ?s { ?s ?p ?o } GROUP BY ?s (?o AS ?s)":
        "ours right. The alias ?s is already a group variable and in the pattern; Oxigraph does not check.",
    "CONSTRUCT { ?s :n ?s } WHERE { ?s ?p ?o } GROUP BY ?s":
        "ours right. ConstructQuery ::= ... SolutionModifier (GroupClause allowed); Oxigraph reads it as SELECT *.",
    "ASK { ?s ?p ?o } GROUP BY ?s HAVING (COUNT(*) > 1)":
        "ours right. AskQuery ::= ... SolutionModifier in the 1.2 draft; Oxigraph reads it as SELECT *.",
    "SELECT (SUM(COUNT(*)) AS ?x) { ?s ?p ?o }": "ours right. 19.7 note: aggregates cannot be nested.",
    "SELECT (COUNT(*) AS ?x) { ?s ?p ?o FILTER(COUNT(*) > 1) }":
        "ours right. 19.7 note: aggregates may only be used in SELECT, HAVING and ORDER BY.",
    "SELECT ?s { ?s ?p ?o FILTER EXISTS { ?s ?q ?z FILTER(MAX(?z) > 1) } } GROUP BY ?s":
        "ours right. 19.7 note: aggregates may only be used in SELECT, HAVING and ORDER BY.",
    "SELECT (MAX(MIN(?o)) AS ?m) { ?s ?p ?o }": "ours right. 19.7 note: aggregates cannot be nested.",
    "SELECT (COUNT(1 + COUNT(*)) AS ?c) { ?s ?p ?o }": "ours right. 19.7 note: aggregates cannot be nested.",
    "SELECT ?s { ?s ?p ?o } GROUP BY ?s HAVING (SUM(COUNT(*)) > 1)": "ours right. 19.7 note: aggregates cannot be nested.",
    "SELECT * { ?s ^:a ?o ~ :r }":
        "ours right. 19.7 note: a reifier needs a simple path (IRI, 'a' or a variable); ^:a is an inverse path.",
    "SELECT * { ?x (:a|:b)/^:c*/:d+ ?y . ?x :e? ?y . ?x !:f ?y . ?x !(:g|^:h|a) ?y . ?x !() ?y . ?x a ?y }":
        "ours right. PathNegatedPropertySet allows the empty set '!()'; Oxigraph rejects it.",
    "SELECT * { ?x :p ?y FILTER (?y > 1) FILTER STR(?y) FILTER :f(?y) FILTER :g() FILTER :h(DISTINCT ?y, 2) }":
        "ours right. ArgList ::= NIL | '(' 'DISTINCT'? Expression ... ')' (custom aggregates); Oxigraph has none.",
    "SELECT * { VALUES ?x { + 1 } }":
        "ours right. 19.7 note: no white space is allowed between the sign and the number; Oxigraph allows it in VALUES.",
}


def _strip_prefix(text: str) -> str:
    return text.split("\n", 1)[1] if text.startswith("PREFIX : <http://e/>\n") else text


_RULE_TEXT = {_strip_prefix(r.text): r for r in RULES}
_CASE_TEXT = {_strip_prefix(c.text): c for c in CASES}
_ALL = {**{_strip_prefix(r.text): r.ok for r in RULES}, **{_strip_prefix(c.text): c.ok for c in CASES}}


@pytest.mark.parametrize("key,text", POSITIVE, ids=[k for k, _ in POSITIVE])
def test_rendered_text_of_positive_query_is_accepted_by_oxigraph(key, text):
    tree = sparql_to_tree(text)
    rendered = sqe_tree_to_text(*tree)
    if key in OX_REJECTS_VALID:
        assert not ox_accepts(text), f"Oxigraph now accepts {key}: remove it from OX_REJECTS_VALID"
        return
    assert ox_accepts(text), f"Oxigraph rejects the original of a positive W3C query: {key}"
    assert ox_accepts(rendered), f"Oxigraph rejects our rendering of {key}:\n{rendered}"


@pytest.mark.parametrize("key,text", NEGATIVE, ids=[k for k, _ in NEGATIVE])
def test_negative_query_is_rejected_by_us_and_oxigraph_verdict_is_registered(key, text):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql(text)
    if key in OX_ACCEPTS_INVALID:
        assert ox_accepts(text), f"Oxigraph now rejects {key}: remove it from OX_ACCEPTS_INVALID"
    else:
        assert not ox_accepts(text), f"Oxigraph accepts the negative query {key}"


@pytest.mark.parametrize("text,ours", sorted(_ALL.items()), ids=[t[:80] for t in sorted(_ALL)])
def test_semantic_rule_and_corpus_verdicts_agree_with_oxigraph_or_are_registered(text, ours):
    full = text if text.startswith(("PREFIX", "VERSION", "BASE")) else "PREFIX : <http://e/>\n" + text
    theirs = ox_accepts(full)
    if text in RULE_DIFFERENCES:
        assert theirs != ours, f"Oxigraph now agrees: remove the registry entry for {text!r}"
    else:
        assert theirs == ours, f"unregistered disagreement (ours={ours}, oxigraph={theirs}): {text!r}"


def test_registry_entries_name_real_cases():
    unknown = [t for t in RULE_DIFFERENCES if t not in _ALL]
    assert not unknown, unknown
