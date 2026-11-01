"""Oxigraph differential for SPARQL Update in ``parse_sparql_update`` (needs ``pyoxigraph``).

Oxigraph (``spargebra``) is an independent parser, so a disagreement is either a bug in ours or a place where Oxigraph is
laxer or narrower than the grammar. As in ``test_parse_sparql_oxigraph.py`` nothing is skipped: each disagreement is
registered with its verdict, and a registry entry that stops being a disagreement fails the test.

Syntax errors and run-time errors are told apart: ``Store.update`` raises ``SyntaxError`` for a request it cannot parse,
and other errors (``OSError`` for a LOAD of a remote IRI, ``RuntimeError`` for MOVE/COPY/DROP of a graph the empty store
does not have) mean the request parsed and failed to run. Only the first kind counts as a rejection.

1. Every positive W3C update request: the original and the text rendered by ``sqe_tree_to_text`` from our tree both parse.
2. Every negative W3C update request: we reject it; Oxigraph's verdict is compared.
3. The rule table (``test_parse_sparql_update.py``) and the production corpus: verdicts compared.
"""

from __future__ import annotations

import pytest
from starlayer.sparql.parse_sparql import (
    SparqlSyntaxError,
    parse_sparql_update,
    sparql_update_to_tree,
)
from starlayer.sparql.sqe import sqe_tree_to_text

from .parse_sparql_conformance.corpus import CASES
from .test_parse_sparql_update import INVALID, NEGATIVE, POSITIVE, VALID

ox = pytest.importorskip("pyoxigraph")

BASE = "http://example/base/"


def ox_parses(text: str) -> bool:
    """True unless Oxigraph reports a syntax error (run-time errors on the empty store mean the request parsed)."""
    try:
        ox.Store().update(text, base_iri=BASE)
    except SyntaxError:
        return False
    except Exception:  # noqa: BLE001 - OSError (LOAD), RuntimeError (missing graph) are not syntax errors
        return True
    return True


# Positive W3C requests Oxigraph rejects at parse time, original or rendering: none.
OX_REJECTS_VALID: dict[str, str] = {}
# Negative W3C requests Oxigraph accepts: none (it rejects all of them, bnode reuse across INSERT DATA included).
OX_ACCEPTS_INVALID: dict[str, str] = {}

_PROLOGUE = (
    "ours right. Update ::= Prologue ( Update1 ( ';' Update )? )?: every operation may be preceded by its own PREFIX / BASE "
    "declarations, and an empty last Update may hold one. Oxigraph only takes a prologue before the first operation."
)
_PFX = "PREFIX : <http://e/>\n"
# Rule-table and corpus disagreements: text -> verdict.
DIFFERENCES: dict[str, str] = {
    "PREFIX a: <http://a/> INSERT DATA { a:s a:p a:o } ; PREFIX a: <http://a2/> INSERT DATA { a:s a:p a:o }": _PROLOGUE,
    "INSERT DATA { } ; PREFIX x: <http://x/>": _PROLOGUE,
    _PFX + "INSERT DATA { :a :p :o } ; PREFIX q: <http://q/> DELETE DATA { q:a :p :o } ;": _PROLOGUE,
    ";": "ours right. A lone ';' is no Update: Update1 is required before ';' (Oxigraph accepts it).",
    "INSERT DATA { <s> <p> <o> <s2> <p> <o> }":
        "ours right. TriplesTemplate ::= TriplesSameSubject ( '.' TriplesTemplate? )?: triples are separated by '.' "
        "(Oxigraph accepts the missing dot).",
}

_ALL: dict[str, bool] = {**{t: True for t in VALID}, **{t: False for t, _ in INVALID}}
_ALL.update({c.text: c.ok for c in CASES if c.update})


@pytest.mark.parametrize("key,text", POSITIVE, ids=[k for k, _ in POSITIVE])
def test_rendered_text_of_positive_update_parses_in_oxigraph(key, text):
    rendered = sqe_tree_to_text(*sparql_update_to_tree(text))
    if key in OX_REJECTS_VALID:
        assert not ox_parses(text), f"Oxigraph now parses {key}: remove it from OX_REJECTS_VALID"
        return
    assert ox_parses(text), f"Oxigraph rejects the original of a positive W3C update: {key}"
    assert ox_parses(rendered), f"Oxigraph rejects our rendering of {key}:\n{rendered}"


@pytest.mark.parametrize("key,text", NEGATIVE, ids=[k for k, _ in NEGATIVE])
def test_negative_update_is_rejected_by_us_and_oxigraph_verdict_is_registered(key, text):
    with pytest.raises(SparqlSyntaxError):
        parse_sparql_update(text)
    if key in OX_ACCEPTS_INVALID:
        assert ox_parses(text), f"Oxigraph now rejects {key}: remove it from OX_ACCEPTS_INVALID"
    else:
        assert not ox_parses(text), f"Oxigraph accepts the negative update {key}"


@pytest.mark.parametrize("text,ours", sorted(_ALL.items()), ids=[t[:80] for t in sorted(_ALL)])
def test_rule_and_corpus_verdicts_agree_with_oxigraph_or_are_registered(text, ours):
    theirs = ox_parses(text)
    if text in DIFFERENCES:
        assert theirs != ours, f"Oxigraph now agrees: remove the registry entry for {text!r}"
    else:
        assert theirs == ours, f"unregistered disagreement (ours={ours}, oxigraph={theirs}): {text!r}"


def test_registry_entries_name_real_cases():
    assert [t for t in DIFFERENCES if t not in _ALL] == []


def test_the_rendering_of_a_request_does_the_same_in_oxigraph():
    """Beyond parsing: INSERT DATA / DELETE DATA / CLEAR / Modify give the same store from the original and the text."""
    text = (
        "PREFIX : <http://e/> INSERT DATA { :a :p 1 . GRAPH :g { :a :p 2 } :b :q :c {| :r 3 |} } ;\n"
        "DELETE { ?s :p ?o } INSERT { ?s :p2 ?o } WHERE { ?s :p ?o } ; DROP SILENT GRAPH :zz ; COPY :g TO :h ;\n"
        "DELETE DATA { :b :q :c ~ :n }"
    )
    rendered = sqe_tree_to_text(*sparql_update_to_tree(text))

    def final(t):
        s = ox.Store()
        s.update(t, base_iri=BASE)
        return {(str(q.subject), str(q.predicate), str(q.object), str(q.graph_name)) for q in s if "reifies" not in str(q.predicate)
                and not isinstance(q.subject, ox.BlankNode) and not isinstance(q.object, ox.BlankNode)}

    assert final(text) == final(rendered)
