"""The correlated FILTER [NOT] EXISTS -> join rewrite (``starlayer.sparql.sqe.rewrite``): same rows as the original, on Oxigraph."""

import random
from collections import Counter

import pyoxigraph as ox
import pytest
import starlayer.sparql  # noqa: F401  (import order)
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from starlayer.sparql.sqe.rewrite import rewrite_exists_text

E = "http://e/"
XI = ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")
P = "PREFIX : <http://e/>\n"


def _store(seed=1, n=14):
    rnd = random.Random(seed)
    s = ox.Store()

    def nn(x):
        return ox.NamedNode(E + x)

    for i in range(n):
        p = nn(f"p{i}")
        s.add(ox.Quad(p, nn("type"), nn("Person")))
        if rnd.random() < 0.85:
            s.add(ox.Quad(p, nn("age"), ox.Literal(str(rnd.randint(1, 6)), datatype=XI)))
        if rnd.random() < 0.3:
            s.add(ox.Quad(p, nn("age"), ox.Literal(str(rnd.randint(1, 6)), datatype=XI)))
        for _ in range(rnd.randint(0, 3)):
            s.add(ox.Quad(p, nn("knows"), nn(f"p{rnd.randrange(n)}")))
        if rnd.random() < 0.4:
            s.add(ox.Quad(p, nn("tag"), ox.Literal(rnd.choice("abc"))))
    return s


def _rows(store, text):
    res = store.query(text)
    if isinstance(res, ox.QueryBoolean):
        return bool(res)
    names = [v.value for v in res.variables]
    return Counter(tuple(str(sol[n]) if sol[n] is not None else None for n in names) for sol in res)


REWRITTEN = [
    # EXISTS, NOT EXISTS, several, nested EXISTS inside the inner FILTER, a path in the inner block, other outer FILTERs
    "SELECT ?p WHERE { ?p :type :Person ; :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { ?p :type :Person ; :age ?a . FILTER NOT EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p ?a WHERE { ?p :age ?a . FILTER(?a > 2) FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b = ?a) } }",
    "SELECT * WHERE { ?p :age ?a . FILTER EXISTS { ?x :knows ?y . ?y :age ?b . FILTER(?b < ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER NOT EXISTS { ?x :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . FILTER NOT EXISTS { ?q :age ?b . FILTER(?b > ?a) } } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . FILTER EXISTS { ?q :age ?b . FILTER(?b > ?a) } } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows+ ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } FILTER NOT EXISTS { ?p :tag ?t . FILTER(?a > 3) } }",
    "SELECT ?p WHERE { ?p :age ?a . ?p :knows ?r . FILTER EXISTS { ?r :age ?b . FILTER(?b >= ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?a } FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT DISTINCT ?a WHERE { ?p :age ?a . FILTER NOT EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } ORDER BY ?a",
    "ASK { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT (COUNT(*) AS ?n) WHERE { ?p :age ?a . FILTER NOT EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } UNION { ?p :tag ?a } }",
    "SELECT ?p WHERE { ?p :type :Person . MINUS { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } }",
    "SELECT ?p WHERE { ?p :type :Person . { SELECT ?p WHERE { ?p :age ?a . FILTER NOT EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows [ :age ?b ] . FILTER(?b > ?a) } }",
]

LEFT_ALONE = [
    # no inner FILTER over an outer variable: already fast, no change
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER NOT EXISTS { ?p :knows ?q . FILTER(?q != :p1) } }",
    # OPTIONAL in the outer group, in the inner block, as the right side of OPTIONAL
    "SELECT ?p WHERE { ?p :age ?a . OPTIONAL { ?p :tag ?t } FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . OPTIONAL { ?q :tag ?t } FILTER(?q != ?p || ?a > 2) } }",
    "SELECT ?p ?t WHERE { ?p :type :Person . OPTIONAL { ?p :tag ?t . ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } }",
    "SELECT ?p ?t WHERE { ?p :type :Person . OPTIONAL { ?p :age ?a FILTER NOT EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?t) } } }",
    # MINUS / BIND / GRAPH in the group or the block
    "SELECT ?p WHERE { ?p :age ?a . MINUS { ?p :tag ?t } FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . BIND(?a + 1 AS ?c) FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?c) } }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . BIND(1 AS ?z) FILTER(?z < ?a) } }",
    "SELECT ?p WHERE { GRAPH ?g { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } } }",
    # the EXISTS is not the whole FILTER expression
    "SELECT ?p WHERE { ?p :age ?a . FILTER (?a > 1 && EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) }) }",
    "SELECT ?p WHERE { ?p :age ?a . FILTER (!EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) }) }",
    "SELECT ?p WHERE { ?p :age ?a . BIND(EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } AS ?e) }",
    # a nondeterministic call in the block
    "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . FILTER(RAND() < ?a) } }",
    # a path or a blank node in the outer group
    "SELECT ?p WHERE { ?p :age ?a . ?p :knows+ ?r . FILTER EXISTS { ?r :age ?b . FILTER(?b > ?a) } }",
    "SELECT ?p WHERE { ?p :age ?a . [] :knows ?p . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }",
]


@pytest.mark.parametrize("q", REWRITTEN)
def test_rewritten_and_same_rows(q):
    text = P + q
    out = rewrite_exists_text(text)
    assert out != text, "expected a rewrite"
    for seed in range(4):
        s = _store(seed)
        assert _rows(s, out) == _rows(s, text)


@pytest.mark.parametrize("q", LEFT_ALONE)
def test_left_alone_and_same_rows(q):
    text = P + q
    assert rewrite_exists_text(text) == text


def test_no_change_without_exists_or_when_switched_off(monkeypatch):
    plain = P + "SELECT ?p WHERE { ?p :age ?a }"
    assert rewrite_exists_text(plain) == plain
    monkeypatch.setenv("STARLAYER_EXISTS_REWRITE", "0")
    assert rewrite_exists_text(P + REWRITTEN[0]) == P + REWRITTEN[0]


def test_prefixes_given_separately_and_unparsable_text():
    q = "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :knows ?q . ?q :age ?b . FILTER(?b > ?a) } }"
    assert rewrite_exists_text(q, prefixes={"": E}) != q
    broken = "SELECT ?p WHERE { ?p :age ?a . FILTER EXISTS { ?p :k"
    assert rewrite_exists_text(broken) == broken


# ---- property-based: random group shapes, rewritten or not, never change rows ----------------------------------------------

_OUTER = ["?p :age ?a", "?p :age ?a . ?p :tag ?t", "?p :age ?a . ?p :knows ?r", "?p :type :Person . ?p :age ?a"]
_INNER_T = ["?p :knows ?q . ?q :age ?b", "?x :age ?b", "?r :age ?b", "?p :knows ?q . ?q :knows ?x . ?x :age ?b"]
_COND = ["?b > ?a", "?b = ?a", "?b < ?a", "?b != ?a", "?b > ?a && ?a > 2", "?a > 3"]
_EXTRA = ["", "FILTER(?a > 1)", "OPTIONAL { ?p :tag ?z }", "MINUS { ?p :tag ?z }", "BIND(?a AS ?c)"]


@settings(max_examples=120, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.sampled_from(_OUTER), st.sampled_from(_INNER_T), st.sampled_from(_COND), st.sampled_from(_EXTRA),
    st.sampled_from(["EXISTS", "NOT EXISTS"]), st.booleans(), st.integers(0, 5),
)
def test_property_same_rows(outer, inner, cond, extra, kw, nested, seed):
    body = f"{inner} . FILTER({cond})"
    if nested:
        body = f"{inner.split('.')[0]} . FILTER NOT EXISTS {{ {inner} . FILTER({cond}) }}"
    text = P + f"SELECT * WHERE {{ {outer} . {extra} FILTER {kw} {{ {body} }} }}"
    out = rewrite_exists_text(text)
    s = _store(seed)
    assert _rows(s, out) == _rows(s, text)
