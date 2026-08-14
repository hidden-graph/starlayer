"""Phase 6 (continued): SPARQL 1.2 algebra -> text, verified by *executing*
the original and round-tripped query against a real `StarLayerGraph` and
comparing results — the execution-based verification
test_phase6_rdf12_native.py explicitly deferred (see that file's docstring).

The loop under test: SPARQL 1.2 text -> our own grammar (parse12.py) ->
algebra tree (with TripleTermNode nodes) -> encode to RDF (query_to_rdf) ->
decode (rdf_to_query) -> regenerate SPARQL 1.2 text (serialize12.py) ->
execute via StarLayerGraph.query(text). Both the *original* text and the
*regenerated* text are executed the same way, via StarLayerGraph's own
`query(str)` entry point — never by executing our own algebra tree directly
(rdflib's evaluator doesn't know how to match a TripleTermNode-shaped
pattern against real stored data; StarLayerGraph internally represents a
ground triple term as a content-addressed hash URI, not as something our
tree's raw Python objects would coincidentally match — confirmed empirically
while building this). StarLayerGraph's own internal 1.2-to-1.1 lowering is
treated as a black box throughout, per design: this project's job stops at
producing correct SPARQL 1.2 text.

serialize12.translate_algebra_12 supports SELECT and CONSTRUCT. ASK/DESCRIBE
are not supported - confirmed empirically that this is a pre-existing
rdflib gap unrelated to this project's own work (plain, unmodified rdflib's
algebra.translateAlgebra already returns an empty string for a CONSTRUCT
query with zero triple terms involved, since self._alg_translation is only
ever seeded by the SelectQuery branch - the same gap applies to ASK/
DESCRIBE, not investigated further since nothing in scope needs them).
CONSTRUCT support itself is a genuinely new capability this project adds
(see serialize12.py's own docstring for the two non-obvious things that had
to be gotten right, both found only by testing against real StarLayerGraph
execution, not by reading rdflib's source alone).

Also covers expression-position triple-term usage (isTRIPLE(expr)/
SUBJECT(expr)/PREDICATE(expr)/OBJECT(expr), and a triple term used directly
as a value in BIND/SELECT-AS) — grammar12.py's second extension point
(PrimaryExpression/BuiltInCall, not just the triple-pattern-term grammar).
Building the serializer side of this surfaced a real, subtle bug, not
anticipated in advance: rdflib's own _traverse() (algebra.py) stops
recursing into a node's *children* the moment its visitPre callback returns
non-None. The Builtin_isTRIPLE/SUBJECT/PREDICATE/OBJECT branch originally
returned `node` (mirroring the TripleTerm/BGP/TriplesBlock branches, which
correctly self-contain all the text they need) — but a builtin's own
argument can itself be a TripleTermNode (e.g. PREDICATE(TRIPLE(:a,:b,:c))),
whose own "{TripleTerm}" placeholder then never got a chance to be resolved
independently, leaving literal unresolved placeholder text in the output.
Fixed by NOT returning early there, matching every ordinary base-class
builtin branch's own convention, so rdflib's normal per-child recursion
reaches the argument on its own.
"""

from __future__ import annotations

from starlayergraph.graph.starlayer_graph import StarLayerGraph

from starsparql import query_to_rdf, rdf_to_query
from starsparql.parse12 import prepare_query_12
from starsparql.serialize12 import translate_algebra_12

PREFIXES = "PREFIX : <http://example.org/>\n"

FIXTURE_TTL12 = """
@prefix : <http://example.org/> .
:alice :reifies <<( :bob :knows :carol )>> ; :source :Wikipedia .
:dave :claims <<( :bob :knows <<( :carol :trusts :eve )>> )>> .
:frank :says <<( :bob :knows :carol )>> .
"""

# (query_text, expect_nonempty) - expect_nonempty is False only for the
# subject-position case, where asserting matching fixture data would need
# hand-writing StarLayerGraph's internal content-addressed hash URI (not
# practical in a Turtle fixture) - still a real, meaningful check: both
# sides must still agree (here, agree on zero rows) and both must execute
# without error.
QUERIES = [
    (
        PREFIXES
        + "SELECT ?source WHERE { ?stmt :reifies <<( :bob :knows :carol )>> . ?stmt :source ?source . }",
        True,
    ),
    (
        PREFIXES
        + "SELECT ?stmt ?p WHERE { ?stmt :reifies <<( :bob ?p :carol )>> . }",
        True,
    ),
    (
        PREFIXES
        + "SELECT ?d WHERE { ?d :claims <<( :bob :knows <<( :carol :trusts :eve )>> )>> . }",
        True,
    ),
    (
        PREFIXES + "SELECT ?stmt WHERE { ?stmt :reifies TRIPLE(:bob, :knows, :carol) . }",
        True,
    ),
    (
        PREFIXES
        + "SELECT ?team WHERE { <<( :bob :knows :carol )>> :verifiedBy ?team . }",
        False,
    ),
    # expression-position: SUBJECT()/PREDICATE()/OBJECT() applied to a bound
    # variable holding a triple term
    (
        PREFIXES + "SELECT ?s WHERE { ?x :says ?tt . BIND(SUBJECT(?tt) AS ?s) }",
        True,
    ),
    (
        PREFIXES + "SELECT ?p WHERE { ?x :says ?tt . BIND(PREDICATE(?tt) AS ?p) }",
        True,
    ),
    (
        PREFIXES + "SELECT ?o WHERE { ?x :says ?tt . BIND(OBJECT(?tt) AS ?o) }",
        True,
    ),
    # expression-position: isTRIPLE() as a FILTER condition
    (
        PREFIXES + "SELECT ?o WHERE { ?s ?p ?o . FILTER(isTRIPLE(?o)) }",
        True,
    ),
    # a triple term used directly as an expression value (not via a builtin)
    (
        PREFIXES + "SELECT ?x WHERE { BIND(<<( :bob :knows :carol )>> AS ?x) }",
        True,
    ),
    # two sibling accessor calls on freshly-constructed (not variable-bound)
    # triple terms in the same projection list - the specific shape that
    # exposed the _traverse()-stops-recursing bug described in the module
    # docstring
    (
        PREFIXES
        + "SELECT (PREDICATE(TRIPLE(:bob, :knows, :carol)) AS ?p) "
        "(OBJECT(TRIPLE(:bob, :knows, :carol)) AS ?o) WHERE {}",
        True,
    ),
]

CONSTRUCT_QUERIES = [
    # plain CONSTRUCT, no triple term at all - the base case that surfaced
    # the Project/PV-vs-node.p.p bug (see serialize12.py's docstring)
    PREFIXES + "CONSTRUCT { :dave :repeats ?tt } WHERE { :alice :reifies ?tt . }",
    # a triple term in the CONSTRUCT template, matched from a ground pattern
    # in WHERE - the case that surfaced the WHERE-keyword-required-by-
    # starlayergraph's-rewriter finding
    PREFIXES
    + "CONSTRUCT { :eve :claims <<( :bob :knows :carol )>> } "
    "WHERE { :alice :reifies <<( :bob :knows :carol )>> . }",
]


def _run(graph, query_text):
    return sorted(str(row) for row in graph.query(query_text))


def test_serializer_output_reparses():
    """Every regenerated text is itself valid SPARQL 1.2 - parses cleanly
    through our own grammar again, no partial/garbled placeholder text left
    over (see serialize12.py's docstring on the base class's placeholder
    mechanism)."""
    for query_text, _ in QUERIES:
        prepared = prepare_query_12(query_text)
        graph, root = query_to_rdf(prepared)
        reconstructed = rdf_to_query(graph, root)
        regenerated_text = translate_algebra_12(reconstructed)

        reparsed = prepare_query_12(regenerated_text)
        assert reparsed.algebra["_vars"] == prepared.algebra["_vars"], query_text


def test_execution_roundtrip_via_starlayergraph():
    starlayer_graph = StarLayerGraph()
    starlayer_graph.parse(data=FIXTURE_TTL12, format="turtle12")

    for query_text, expect_nonempty in QUERIES:
        original_rows = _run(starlayer_graph, query_text)

        prepared = prepare_query_12(query_text)
        graph, root = query_to_rdf(prepared)
        reconstructed = rdf_to_query(graph, root)
        regenerated_text = translate_algebra_12(reconstructed)

        roundtripped_rows = _run(starlayer_graph, regenerated_text)

        assert original_rows == roundtripped_rows, query_text
        if expect_nonempty:
            assert len(original_rows) > 0, query_text


def test_construct_serializer_output_reparses():
    for query_text in CONSTRUCT_QUERIES:
        prepared = prepare_query_12(query_text)
        graph, root = query_to_rdf(prepared)
        reconstructed = rdf_to_query(graph, root)
        regenerated_text = translate_algebra_12(reconstructed)

        reparsed = prepare_query_12(regenerated_text)
        assert reparsed.algebra["template"] == prepared.algebra["template"], query_text


def test_construct_execution_roundtrip_via_starlayergraph():
    starlayer_graph = StarLayerGraph()
    starlayer_graph.parse(data=FIXTURE_TTL12, format="turtle12")

    for query_text in CONSTRUCT_QUERIES:
        original_graph = sorted(starlayer_graph.query(query_text).graph)

        prepared = prepare_query_12(query_text)
        graph, root = query_to_rdf(prepared)
        reconstructed = rdf_to_query(graph, root)
        regenerated_text = translate_algebra_12(reconstructed)

        roundtripped_graph = sorted(starlayer_graph.query(regenerated_text).graph)

        assert original_graph == roundtripped_graph, query_text
        assert len(original_graph) > 0, query_text
