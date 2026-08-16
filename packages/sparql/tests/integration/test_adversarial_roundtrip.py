"""
tests/test_adversarial_roundtrip.py

An adversarial battery trying to *disprove* the conclusion
test_w3c_sparql12_oxigraph_roundtrip.py's 40/40 pass rate suggests - that
this project's SPARQL 1.2 -> algebra -> SPARQL 1.2 round trip preserves
query semantics. The W3C suite's 40 QueryEvaluationTest fixtures are
curated to test triple-term/reification/dirLangString features mostly in
*isolation*; this file specifically targets *combinations* those fixtures
never exercise - triple terms/reification interacting with OPTIONAL, UNION,
MINUS, subqueries, aggregates, property paths, deep nesting, multiple
annotation predicates on one triple, and double round-trips (regenerate
twice, not just once) - on the theory that interaction bugs are exactly
what a curated, feature-isolated conformance suite is least likely to catch.

Same methodology as test_w3c_sparql12_oxigraph_roundtrip.py: load real data
into a live Oxigraph-backed StarLayerGraph/StarLayerDataset, run the
original query text, translate it through this project's own RDF algebra
and back to text, run the regenerated text against the *same* data, and
compare results directly - no W3C fixture, no starlayergraph in-memory backend
involved, so a failure here is unambiguously either a real translation bug
or a real Oxigraph-specific engine quirk (distinguishable by checking
whether the *same* query executed twice, unmodified, is stable).

Requires a running Oxigraph and/or Fuseki instance - see starlayergraph's
own tests/integration/test_oxigraph_backend.py / test_fuseki_backend.py
module docstrings for the docker run commands. Each backend's cases are
skipped independently/cleanly if that specific engine is unreachable - run
against whichever (or both) are available, to distinguish a genuine
translation bug (fails on every engine) from an engine-specific quirk.

A nested-subject triple term (a ground triple term used as *another* triple
term's own subject, e.g. `<<( <<( :a :b :c )>> :d :e )>>`) is deliberately
absent from this file's own adversarial cases - not an oversight. It looked
like exactly the kind of interaction bug this file exists to catch (Oxigraph
0.5.9 returns `HTTP 500` on it), but turned out to be invalid RDF 1.2 to
begin with: RDF 1.2's own grammar restricts a triple term's subject to
`iri | BlankNode` - never another triple term, unconditionally, not just in
expression position (see starsparql/triple_term.py's
`InvalidTripleTermError`, and the sibling starlayergraph repo's
docs/oxigraph-upstream-issues.md Issue 1 for the full, retracted
investigation). `starsparql.parse12.prepare_query_12` now rejects this
shape outright (`InvalidTripleTermError`) before any query ever reaches a
backend - see `test_nested_subject_triple_term_is_rejected` below. Deep
nesting *is* still exercised here, correctly, in object position instead.

A second, broader case in the same family (found 2026-08-15, directly
challenged and confirmed by a user question in conversation, not caught by
the investigation above): a *whole* triple term used as the subject of an
ordinary pattern - not nested inside another triple term at all, just
`<<( :a :b :c )>> :d :e .` on its own - is equally invalid RDF 1.2 Concepts
(https://www.w3.org/TR/rdf12-concepts/#section-triple-terms - a triple
term is legal only as an object, never a subject, in every triple-formation
rule that admits one). This was a real, previously-unfixed gap: the
narrower nested-subject check above did not catch it, and this project's
own construction paths accepted it silently until
`starsparql.triple_term._reject_triple_term_pattern_subjects` was added -
see `test_pattern_subject_triple_term_is_rejected` and its sibling tests
below. Confirmed *not* to affect the RDF 1.2 reifier-shorthand form
(`<<s p o>>`/`<<s p o ~ r>>`, no parens) in subject position, which
desugars to an ordinary blank-node reifier and remains fully legal - see
`test_reifier_shorthand_subject_still_works`. See
`docs/w3c-sparql12-test-suite-issues.md` for the corresponding W3C test
suite issue write-up (two `PositiveSyntaxTest` fixtures constructing this
exact invalid shape).
"""

from __future__ import annotations

import pytest
import requests
from rdflib import URIRef
from rdflib.compare import to_isomorphic
from rdflib.graph import DATASET_DEFAULT_GRAPH_ID
from rdflib.plugins.stores.sparqlstore import SPARQLUpdateStore

from starlayergraph.graph.starlayer_graph import StarLayerGraph

from starsparql import query_to_rdf, rdf_to_query
from starsparql.parse12 import prepare_query_12
from starsparql.serialize12 import translate_algebra_12
from w3c_sparql12.harness import bindings_match, skolemize_graph

pytestmark = pytest.mark.w3c_sparql12

OXIGRAPH_BASE = "http://localhost:7878"
OXIGRAPH_QUERY_URL = f"{OXIGRAPH_BASE}/query"
OXIGRAPH_UPDATE_URL = f"{OXIGRAPH_BASE}/update"

# Same dataset name/endpoint shape as starlayergraph's own
# tests/integration/test_fuseki_backend.py - create it first with:
#   curl -X POST http://localhost:3030/$/datasets -u admin:admin \
#     --data 'dbName=starlayergraph&dbType=mem'
FUSEKI_BASE = "http://localhost:3030/starlayergraph"
FUSEKI_QUERY_URL = f"{FUSEKI_BASE}/query"
FUSEKI_UPDATE_URL = f"{FUSEKI_BASE}/update"

GRAPH_URI = URIRef("http://example.org/adversarial")

_ENDPOINTS = {
    "oxigraph": (OXIGRAPH_BASE, OXIGRAPH_QUERY_URL, OXIGRAPH_UPDATE_URL),
    "fuseki": (FUSEKI_BASE, FUSEKI_QUERY_URL, FUSEKI_UPDATE_URL),
}


def _backend_available(name: str) -> bool:
    base = _ENDPOINTS[name][0]
    try:
        return requests.get(base if name == "oxigraph" else f"{base.rsplit('/', 1)[0]}/$/ping", timeout=2).status_code == 200
    except Exception:
        return False


@pytest.fixture(params=list(_ENDPOINTS))
def backend(request) -> str:
    name = request.param
    if not _backend_available(name):
        pytest.skip(f"{name} not running")
    return name


def _clear_store(backend: str) -> None:
    _, _, update_url = _ENDPOINTS[backend]
    requests.post(
        update_url,
        data="CLEAR ALL",
        headers={"Content-Type": "application/sparql-update"},
        timeout=10,
    ).raise_for_status()


def _fresh_graph(backend: str) -> StarLayerGraph:
    _clear_store(backend)
    _, query_url, update_url = _ENDPOINTS[backend]
    store = SPARQLUpdateStore(query_endpoint=query_url, update_endpoint=update_url)
    return StarLayerGraph(store=store, identifier=DATASET_DEFAULT_GRAPH_ID, backend="rdf-1.2")


def _regenerate(query_text: str) -> str:
    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    return translate_algebra_12(reconstructed)


def _select_equivalent(g, query_text: str, regenerated_text: str) -> tuple[bool, list, list]:
    original = [dict(row) for row in g.query(query_text).bindings]
    regenerated = [dict(row) for row in g.query(regenerated_text).bindings]
    return bindings_match(original, regenerated), original, regenerated


def _construct_equivalent(g, query_text: str, regenerated_text: str) -> bool:
    original_graph = g.query(query_text).graph
    regenerated_graph = g.query(regenerated_text).graph
    return to_isomorphic(skolemize_graph(original_graph)) == to_isomorphic(skolemize_graph(regenerated_graph))


# ---------------------------------------------------------------------------
# Data fixtures shared by several cases below.
# ---------------------------------------------------------------------------

_BASE_DATA = """
PREFIX : <http://example/>
:a :b :c .
:x :y :z .
:s1 :knows :s2 .
:s2 :knows :s3 .
:s3 :knows :s4 .
:reifier1 <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( :a :b :c )>> .
:reifier1 :confidence "0.9" .
"""


# ---------------------------------------------------------------------------
# SELECT-shaped adversarial cases: (name, query, data)
# ---------------------------------------------------------------------------

SELECT_CASES = [
    (
        "nested_depth_4",
        # Nesting depth 4, correctly in *object* position at every level
        # (`<<( :a :b <<( :c :d <<( :e :f <<( :g :h :i )>> )>> )>> )>>`) - see
        # this module's own docstring for why this isn't subject-nested, the
        # way an earlier version of this case was.
        """
        PREFIX : <http://example/>
        SELECT * WHERE {
          ?s ?p <<( :a :b <<( :c :d <<( :e :f <<( :g :h :i )>> )>> )>> )>> .
        }
        """,
        """
        PREFIX : <http://example/>
        :outer :says <<( :a :b <<( :c :d <<( :e :f <<( :g :h :i )>> )>> )>> )>> .
        """,
    ),
    (
        "triple_term_with_optional",
        """
        PREFIX : <http://example/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?stmt ?conf WHERE {
          ?stmt rdf:reifies <<( :a :b :c )>> .
          OPTIONAL { ?stmt :confidence ?conf }
        }
        """,
        _BASE_DATA,
    ),
    (
        "triple_term_with_union",
        """
        PREFIX : <http://example/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {
          { ?r rdf:reifies ?tt }
          UNION
          { BIND(TRIPLE(:x, :y, :z) AS ?tt) }
        }
        """,
        _BASE_DATA,
    ),
    (
        "triple_term_with_minus",
        """
        PREFIX : <http://example/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {
          ?r rdf:reifies ?tt .
          MINUS { BIND(TRIPLE(:a, :b, :c) AS ?tt) }
        }
        """,
        _BASE_DATA,
    ),
    (
        "triple_term_in_subquery",
        """
        PREFIX : <http://example/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?tt WHERE {
          { SELECT ?tt WHERE { ?r rdf:reifies ?tt } }
        }
        """,
        _BASE_DATA,
    ),
    (
        "triple_term_with_aggregate_group_by",
        """
        PREFIX : <http://example/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        SELECT ?p (COUNT(?tt) AS ?c) WHERE {
          ?r rdf:reifies ?tt .
          BIND(PREDICATE(?tt) AS ?p)
        }
        GROUP BY ?p
        """,
        _BASE_DATA,
    ),
    (
        "triple_term_with_property_path",
        """
        PREFIX : <http://example/>
        SELECT ?tt WHERE {
          ?s :knows+ ?friend .
          BIND(TRIPLE(?s, :knows, ?friend) AS ?tt)
        }
        """,
        _BASE_DATA,
    ),
    (
        "multiple_annotation_predicates_same_triple",
        """
        PREFIX : <http://example/>
        SELECT * WHERE {
          :a :b :c ~ :r1 {| :conf "0.9" |} ~ :r2 {| :source :bob |} .
        }
        """,
        """
        PREFIX : <http://example/>
        :a :b :c ~ :r1 {| :conf "0.9" |} ~ :r2 {| :source :bob |} .
        """,
    ),
    (
        "dirlangstring_and_triple_term_same_values_row",
        """
        PREFIX : <http://example/>
        SELECT ?a ?b WHERE {
          VALUES (?a ?b) {
            ("hi"@en--ltr <<( :x :y :z )>>)
            ("bye"@en--rtl <<( :a :b :c )>>)
          }
        }
        """,
        _BASE_DATA,
    ),
    (
        "explicit_bnode_reifier",
        """
        PREFIX : <http://example/>
        SELECT ?z WHERE {
          << :a :b :c ~ _:myreifier >> :q ?z .
        }
        """,
        """
        PREFIX : <http://example/>
        :a :b :c ~ _:myreifier {| :q "answer" |} .
        """,
    ),
    (
        "ground_triple_never_stored",
        """
        PREFIX : <http://example/>
        SELECT (TRIPLE(:a, :b, :c) AS ?t) (isTRIPLE(TRIPLE(:a, :b, :c)) AS ?isTT) WHERE {}
        """,
        "",
    ),
    (
        "two_reifiers_same_triple_pattern",
        """
        PREFIX : <http://example/>
        SELECT ?r WHERE {
          << :a :b :c >> :q ?r .
        }
        """,
        """
        PREFIX : <http://example/>
        :a :b :c ~ :r1 {| :q "one" |} ~ :r2 {| :q "two" |} .
        """,
    ),
    (
        "nested_reifier_shorthand",
        """
        PREFIX : <http://example/>
        SELECT * WHERE {
          << << :a :b :c >> :says :d >> :q ?z .
        }
        """,
        """
        PREFIX : <http://example/>
        << :a :b :c >> :says :d ~ :outer {| :q "nested" |} .
        """,
    ),
]

CONSTRUCT_CASES = [
    (
        "construct_mixed_shorthand_and_explicit",
        """
        PREFIX : <http://example/>
        CONSTRUCT {
          << ?s ?p ?o >> :derived true .
          ?s :seen true .
        } WHERE {
          ?s ?p ?o .
        }
        """,
        _BASE_DATA,
    ),
    (
        "construct_where_with_annotation",
        """
        PREFIX : <http://example/>
        CONSTRUCT WHERE {
          ?s ?p ?o {| :meta true |} .
        }
        """,
        _BASE_DATA,
    ),
    (
        "construct_with_optional_and_triple_term",
        """
        PREFIX : <http://example/>
        PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
        CONSTRUCT {
          ?r rdf:reifies ?tt .
          ?r :hasConf ?conf .
        } WHERE {
          ?r rdf:reifies ?tt .
          OPTIONAL { ?r :confidence ?conf }
        }
        """,
        _BASE_DATA,
    ),
]


@pytest.mark.parametrize("name,query,data", SELECT_CASES, ids=[c[0] for c in SELECT_CASES])
def test_select_adversarial_semantic_equivalence(backend, name, query, data):
    g = _fresh_graph(backend)
    if data.strip():
        g.parse(data=data, format="turtle12")
    regenerated_text = _regenerate(query)
    ok, original, regenerated = _select_equivalent(g, query, regenerated_text)
    assert ok, (
        f"[{name}] original and regenerated disagree.\n"
        f"original Q:\n{query}\nregenerated Q':\n{regenerated_text}\n"
        f"original results: {original}\nregenerated results: {regenerated}"
    )


@pytest.mark.parametrize("name,query,data", CONSTRUCT_CASES, ids=[c[0] for c in CONSTRUCT_CASES])
def test_construct_adversarial_semantic_equivalence(backend, name, query, data):
    g = _fresh_graph(backend)
    if data.strip():
        g.parse(data=data, format="turtle12")
    regenerated_text = _regenerate(query)
    assert _construct_equivalent(g, query, regenerated_text), (
        f"[{name}] original and regenerated disagree.\n"
        f"original Q:\n{query}\nregenerated Q':\n{regenerated_text}"
    )


@pytest.mark.parametrize("name,query,data", SELECT_CASES, ids=[c[0] for c in SELECT_CASES])
def test_select_double_roundtrip_idempotent(backend, name, query, data):
    """Regenerate *twice* (Q -> Q' -> Q''), not just once - if translation
    silently drifts on a second pass (e.g. a canonicalization that isn't
    actually a fixed point), a single round trip could hide it while a
    second one wouldn't."""
    g = _fresh_graph(backend)
    if data.strip():
        g.parse(data=data, format="turtle12")
    once = _regenerate(query)
    twice = _regenerate(once)
    ok, original, regenerated = _select_equivalent(g, query, twice)
    assert ok, (
        f"[{name}] double round-trip disagrees with original.\n"
        f"original Q:\n{query}\nQ':\n{once}\nQ'':\n{twice}\n"
        f"original results: {original}\ntwice-regenerated results: {regenerated}"
    )


def test_nested_subject_triple_term_is_rejected():
    """A ground triple term used as *another* triple term's own subject is
    invalid RDF 1.2 (see starsparql.triple_term.InvalidTripleTermError's
    own docstring for the grammar citation and the full investigation this
    module's own docstring references) - confirm it's rejected outright at
    parse time, before any query ever reaches a backend. No live server
    needed - this is pure parsing, unlike every other test in this file."""
    from starsparql.triple_term import InvalidTripleTermError

    query = """
    PREFIX : <http://example/>
    SELECT * WHERE { ?s ?p <<( <<( :a :b :c )>> :d :e )>> . }
    """
    with pytest.raises(InvalidTripleTermError):
        prepare_query_12(query)


def test_pattern_subject_triple_term_is_rejected():
    """The broader case (see module docstring): a triple term used as the
    subject of an *ordinary* pattern - not nested inside another triple
    term at all. `<<(:x ?R :z )>> :p <<(:a :b ?C )>> .` is the exact shape
    the W3C `compound-tripleterm-subject` fixture's own first line uses
    (`docs/w3c-sparql12-test-suite-issues.md` Issue 1) - confirmed to have
    parsed and constructed without error before
    `starsparql.triple_term._reject_triple_term_pattern_subjects` existed.
    No live server needed - pure parsing."""
    from starsparql.triple_term import InvalidTripleTermError

    query = """
    PREFIX : <http://example/>
    SELECT * { <<(:x ?R :z )>> :p <<(:a :b ?C )>> . }
    """
    with pytest.raises(InvalidTripleTermError):
        prepare_query_12(query)


def test_reifier_shorthand_subject_still_works():
    """Companion positive test to the one above - confirms the broader
    subject-position check doesn't overcorrect. The RDF 1.2 reifier
    shorthand (`<<s p o>>`/`<<s p o ~ r>>`, no parens) desugars to an
    ordinary blank-node reifier substituted into the pattern, with the
    real triple term only ever appearing as the *object* of a separate
    rdf:reifies triple - this must remain legal in subject position."""
    query = """
    PREFIX : <http://example/>
    SELECT * { <<:x ?R :z >> :p <<:a :b ?C ~ _:bnode >> . }
    """
    prepared = prepare_query_12(query)
    triples = prepared.algebra["p"]["p"]["triples"]
    assert len(triples) == 3
    # Every triple term in the decoded pattern is an OBJECT, never a subject.
    from starsparql.triple_term import TripleTermNode

    for s, p, o in triples:
        assert not isinstance(s, TripleTermNode), f"triple term as subject: {(s, p, o)!r}"


def test_pattern_subject_triple_term_rejected_in_update_insert_data():
    """Same broader rule, Update side: INSERT DATA's own quad template is
    a different code path from a query's WHERE clause, and needs its own
    independent coverage rather than assuming the query-side test above
    implies it. No live server needed - pure parsing."""
    from starsparql.parse12 import prepare_update_12
    from starsparql.triple_term import InvalidTripleTermError

    update = """
    PREFIX : <http://example/>
    INSERT DATA { <<(:x :p :z )>> :q :r . }
    """
    with pytest.raises(InvalidTripleTermError):
        prepare_update_12(update)


def test_pattern_subject_triple_term_rejected_in_modify_where():
    """Same broader rule, Update side: a Modify's WHERE clause is a nested
    pattern tree reached only via generic recursion (not a top-level BGP a
    naive, non-recursive check might special-case and stop at) - confirm
    the walk actually reaches it. No live server needed - pure parsing."""
    from starsparql.parse12 import prepare_update_12
    from starsparql.triple_term import InvalidTripleTermError

    update = """
    PREFIX : <http://example/>
    DELETE { ?s :q ?r } WHERE { <<(:x :p :z )>> :q ?r . }
    """
    with pytest.raises(InvalidTripleTermError):
        prepare_update_12(update)


def test_pattern_subject_triple_term_rejected_via_rdf_decode():
    """The 'hard backstop regardless of construction path' guarantee
    InvalidTripleTermError's own docstring claims - confirm the from_rdf.py
    decode path independently rejects this shape, not just parse12.py's
    text-parsing path. Builds the illegal algebra tree directly in Python
    (bypassing grammar12.py/parse12.py entirely - the encoder itself has no
    opinion on validity), encodes it, then confirms decoding rejects it -
    simulating a hand-crafted or otherwise-malformed RDF-encoded query
    graph that never went through this project's own SPARQL text parser at
    all. No live server needed - pure encode/decode."""
    from rdflib import URIRef, Variable
    from rdflib.plugins.sparql.parserutils import CompValue

    from starsparql.from_rdf import rdf_to_query
    from starsparql.triple_term import InvalidTripleTermError, TripleTermNode

    EX = "http://example.com/ns#"
    tt_subject = TripleTermNode(
        "TripleTerm", subject=URIRef(EX + "x"), predicate=Variable("R"), object=URIRef(EX + "z")
    )
    tt_object = TripleTermNode(
        "TripleTerm", subject=URIRef(EX + "a"), predicate=URIRef(EX + "b"), object=Variable("C")
    )
    bgp = CompValue("BGP", triples=[(tt_subject, URIRef(EX + "p"), tt_object)], _vars=set())
    project = CompValue("Project", p=bgp, PV=[Variable("R"), Variable("C")], _vars=set())
    select = CompValue(
        "SelectQuery", p=project, datasetClause=None, PV=[Variable("R"), Variable("C")]
    )

    class _FakeQuery:
        def __init__(self, algebra):
            self.algebra = algebra
            self.prologue = None

    graph, root = query_to_rdf(_FakeQuery(select))
    with pytest.raises(InvalidTripleTermError):
        rdf_to_query(graph, root)
