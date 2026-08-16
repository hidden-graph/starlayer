"""Verify ``starsparql.lower_rdf11`` — the algebra-level SPARQL 1.2 ->
SPARQL 1.1 lowering transform (see the module's own docstring for the full
design rationale).

Two layers:

1. Unit-level: hand-built small algebra snippets through
   ``lower_algebra_to_rdf11``/the full ``query_to_rdf11`` ->
   ``rdf11_to_query`` pipeline, executed *directly as a Query object*
   (no SPARQL 1.1 text involved at all — see ``lower_rdf11.py``'s module
   docstring for why ``rdf11_to_query`` is preferred over
   ``rdf11_to_sparql11_text`` for execution) against a real
   ``StarLayerGraph``, for each branch documented in ``lower_rdf11.py``'s
   own module docstring (ground/non-ground pattern position, expression
   position, ``isTRIPLE``/accessor builtins, CONSTRUCT template, VALUES
   row). Small, hand-built data rather than reusing W3C fixtures here:
   these are meant to isolate one branch at a time, the way
   ``test_roundtrip.py``/``test_phase6_*`` already do for ``to_rdf.py``/
   ``from_rdf.py``.
2. End-to-end, reusing the *existing* W3C SPARQL 1.2 fixtures already
   wired up in ``tests/test_w3c_sparql12.py`` (not duplicating them) - for
   every ``QueryEvaluationTest`` (SELECT-shaped) entry, compares this new
   lowering path's result against the same official ``.srj`` ground truth
   ``test_w3c_sparql12.py::test_eval_select`` already checks the *existing*
   (``serialize12.translate_algebra_12`` + starlayergraph's text-based
   ``sparql12_to_11``) path against - directly testing this task's own
   acceptance criterion: same result as the already-proven-correct process,
   via a structurally different (tree-level, not text-level) route.

``test_rdf11_to_sparql11_text_still_works`` is the one dedicated test for
the text-producing path — everything else above exercises
``rdf11_to_query`` instead, so without it that path would silently lose
coverage.
"""

from __future__ import annotations

import pytest
from rdflib import Literal, URIRef, Variable
from rdflib.compare import to_isomorphic
from rdflib.plugins.sparql.update import evalUpdate
from starlayergraph.graph.starlayer_dataset import StarLayerDataset
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.triple import TripleTerm
from starsparql.lower_rdf11 import (
    query_to_rdf11,
    rdf11_to_query,
    rdf11_to_sparql11_text,
    rdf11_to_update,
    rdf11_update_to_sparql11_text,
    update_to_rdf11,
)
from starsparql.parse12 import prepare_query_12, prepare_update_12
from w3c_sparql12.harness import bindings_match, load_index, parse_srj, skolemize_graph

pytestmark = pytest.mark.w3c_sparql12

ALL_ENTRIES = load_index()
EVAL_SELECT = [
    e for e in ALL_ENTRIES if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".srj")
]
EVAL_CONSTRUCT = [
    e for e in ALL_ENTRIES if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".ttl")
]

_no_data = pytest.mark.skipif(not ALL_ENTRIES, reason="W3C SPARQL 1.2 test data not fetched - run download_w3c_sparql12_tests.py")

_DATA_FORMAT_BY_SUFFIX = {".ttl": "turtle12", ".trig": "trig12", ".nq": "nq12", ".nt": "nt12"}
_DATASET_FORMATS = {"trig12", "nq12"}


def _data_format(entry) -> str:
    for suffix, fmt in _DATA_FORMAT_BY_SUFFIX.items():
        if entry.data_file.endswith(suffix):
            return fmt
    raise ValueError(f"no known RDF-1.2 format for data file {entry.data_file!r}")


def _new_graph(entry):
    if entry.data_file and _data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset()
    return StarLayerGraph()


def _run_lowered(query_text: str, graph: StarLayerGraph | StarLayerDataset) -> list[dict]:
    prepared = prepare_query_12(query_text)
    rdf_graph, root = query_to_rdf11(prepared)
    query_object = rdf11_to_query(rdf_graph, root)
    return [{k: v for k, v in dict(row).items() if v is not None} for row in graph.query(query_object).bindings]


# --- Unit-level: one branch at a time -------------------------------------


def test_ground_pattern_position_binds_hash():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:stmt :verifiedBy <<( :s :p :o )>> .\n", format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT * WHERE { ?stmt :verifiedBy <<( :s :p :o )>> . }", g
    )
    assert actual == [{Variable("stmt"): URIRef("http://example/stmt")}]


def test_non_ground_pattern_position_match_decomposes():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:who :verified <<( :s :p :o )>> .\n", format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT * WHERE { :who :verified <<( ?s ?p ?o )>> . }", g
    )
    assert actual == [
        {
            Variable("s"): URIRef("http://example/s"),
            Variable("p"): URIRef("http://example/p"),
            Variable("o"): URIRef("http://example/o"),
        }
    ]


def test_expression_position_inlines_hash_call():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:who :verified <<( :s :p :o )>> .\n", format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT * WHERE { :who :verified ?t . "
        "FILTER(?t = <<( :s :p :o )>>) }",
        g,
    )
    assert len(actual) == 1


def test_filter_exists_with_multi_triple_block_executes():
    """Regression test for a real bug: decoding a `FILTER EXISTS { ... }`
    whose block has more than one triple pattern used to crash at execution
    time with "What do I do with this CompValue?" - `rdflib.plugins.sparql.
    operators.Builtin_EXISTS` reads its own `.graph` via *attribute* syntax
    specifically so a real instance attribute (set by rdflib's own
    `algebra.translateExists`) bypasses `CompValue`'s ctx-based value
    resolution, which cannot handle a raw graph-pattern fragment. A plain
    `CompValue.update()`/dict-style reconstruction (what `from_rdf.py`'s
    generic decoder did before the fix) only stores the value as a dict
    key, not a real attribute, so the rebuilt node lost the one property
    its own evaluator depends on. Nothing in this project's test suite
    executed (as opposed to just structurally SHACL-validating) a
    multi-triple EXISTS/NOT EXISTS block before this - a single-triple
    block doesn't reach the crashing code path via this project's own
    pipeline, only a compound one does.
    """
    g = StarLayerGraph()
    g.parse(
        data="@prefix : <http://example/> .\n:alice :knows :bob .\n:bob :knows :carol .\n",
        format="turtle",
    )
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT ?s WHERE { "
        "?s :knows ?o . FILTER EXISTS { ?s :knows ?o . ?o :knows ?f } }",
        g,
    )
    assert actual == [{Variable("s"): URIRef("http://example/alice")}]


def test_filter_not_exists_with_multi_triple_block_executes():
    g = StarLayerGraph()
    g.parse(
        data="@prefix : <http://example/> .\n:alice :knows :bob .\n:bob :knows :carol .\n",
        format="turtle",
    )
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT ?s WHERE { "
        "?s :knows ?o . FILTER NOT EXISTS { ?s :knows ?o . ?o :knows ?nonexistent } }",
        g,
    )
    assert actual == [{Variable("s"): URIRef("http://example/bob")}]


def test_graph_pattern_executes_against_named_graph():
    """Regression test for a real gap found 2026-08-15 (shapes.py audit):
    `GRAPH ?g { ... }`/`GRAPH <iri> { ... }` produces a real, distinct
    `Graph` CompValue at the algebra layer, but no shape in shapes.py ever
    targeted `salg:Graph` - a pure structural-validation gap, since nothing
    special-cases `Graph` in the generic encoder/decoder/lowerer, so
    execution itself was never actually broken. This test proves that: it
    would have passed even before the shapes.py fix (the fix is a
    validation-coverage improvement, not a bugfix to execution), but per
    this project's own testing-discipline policy (CLAUDE.md), a
    newly-validated *operator* still needs its own execution-comparison
    test, not just the shape fix's own structural mutation tests.
    """
    ds = StarLayerDataset()
    g1 = ds.graph(URIRef("http://example/g1"))
    g1.parse(data="@prefix : <http://example/> .\n:s :p :o .\n", format="turtle")

    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT ?s WHERE { GRAPH <http://example/g1> { ?s :p :o } }",
        ds,
    )
    assert actual == [{Variable("s"): URIRef("http://example/s")}]


def test_substr_binds_correctly():
    """Regression test for a real bug: `BIND(SUBSTR(...) AS ?z)` silently
    never bound `?z` after decoding - no exception, `?z` just always came
    back unbound. `from_rdf.py`'s `_PLAIN_VALUE_KEYS` converts `start`/
    `length` to plain Python ints for `Slice.start`/`.length` (needed by
    `itertools.islice`), but matched by bare key name - `Builtin_SUBSTR`'s
    own `start`/`length` parameters share those key names by coincidence
    (SPARQL's `SUBSTR(str, start[, length])`) and need to stay real
    `Literal`s, since `operators.numeric()` raises `SPARQLTypeError` for
    anything else - which `evalExtend` then silently swallows into "leave
    the BIND target unbound" rather than raising. Found via a differential
    audit comparing every `EXPRESSION_FAMILY_QUERIES` entry (see
    test_shacl_shapes.py) against plain rdflib execution - the only one, of
    ~20, that actually diverged.
    """
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:who :name \"apple\" .\n", format="turtle")
    actual = _run_lowered(
        'PREFIX : <http://example/> SELECT ?z WHERE { :who :name ?y . BIND(SUBSTR(?y, 1, 3) AS ?z) }',
        g,
    )
    assert actual == [{Variable("z"): Literal("app")}]


def test_is_triple_and_accessors():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:who :verified <<( :s :p :o )>> .\n", format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT ?s2 WHERE { :who :verified ?t . "
        "FILTER(isTRIPLE(?t)) BIND(SUBJECT(?t) AS ?s2) }",
        g,
    )
    assert actual == [{Variable("s2"): URIRef("http://example/s")}]


def test_langdir_hasLangdir():
    g = StarLayerGraph()
    g.parse(data='@prefix : <http://example/> .\n:s :saysDir "hi"@en--rtl .\n', format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT (LANGDIR(?o) AS ?d) (hasLANGDIR(?o) AS ?h) "
        "WHERE { :s :saysDir ?o . }",
        g,
    )
    assert actual == [{Variable("d"): Literal("rtl"), Variable("h"): Literal(True)}]


def test_langdir_hasLangdir_false_for_plain_literal():
    g = StarLayerGraph()
    g.parse(data='@prefix : <http://example/> .\n:s :plain "hi"@en .\n', format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT (LANGDIR(?o) AS ?d) (hasLANGDIR(?o) AS ?h) "
        "WHERE { :s :plain ?o . }",
        g,
    )
    assert actual == [{Variable("d"): Literal(""), Variable("h"): Literal(False)}]


def test_lang_on_dirlangstring_extracts_language_subtag():
    g = StarLayerGraph()
    g.parse(data='@prefix : <http://example/> .\n:s :saysDir "hi"@en--rtl .\n', format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT (LANG(?o) AS ?l) WHERE { :s :saysDir ?o . }", g
    )
    assert actual == [{Variable("l"): Literal("en")}]


def test_lang_on_plain_langtagged_literal_still_works():
    g = StarLayerGraph()
    g.parse(data='@prefix : <http://example/> .\n:s :plain "hi"@en .\n', format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT (LANG(?o) AS ?l) WHERE { :s :plain ?o . }", g
    )
    assert actual == [{Variable("l"): Literal("en")}]


def test_haslang_true_for_dirlangstring_and_plain_langtagged():
    g = StarLayerGraph()
    g.parse(
        data='@prefix : <http://example/> .\n:s :saysDir "hi"@en--rtl .\n:s :plain "hi"@en .\n',
        format="turtle12",
    )
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT ?p (hasLANG(?o) AS ?h) "
        "WHERE { :s ?p ?o . FILTER(?p IN (:saysDir, :plain)) }",
        g,
    )
    assert {row[Variable("h")] for row in actual} == {Literal(True)}


def test_haslang_false_for_untagged_literal():
    g = StarLayerGraph()
    g.parse(data='@prefix : <http://example/> .\n:s :untagged "hi" .\n', format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT (hasLANG(?o) AS ?h) WHERE { :s :untagged ?o . }", g
    )
    assert actual == [{Variable("h"): Literal(False)}]


def test_strlangdir_constructs_dirlangstring():
    g = StarLayerGraph()
    actual = _run_lowered(
        'SELECT (STRLANGDIR("hi", "en", "ltr") AS ?r) WHERE {}', g
    )
    assert actual == [{Variable("r"): DirLangString("hi", "en", "ltr")}]


_CONSTRUCT_TEMPLATE_QUERY = (
    "PREFIX : <http://example/> CONSTRUCT { <<( ?s :p ?o )>> :verifiedBy :me . } WHERE { ?s :p ?o . }"
)


def test_construct_template_mints_triple_term():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:s :p :o .\n", format="turtle12")
    prepared = prepare_query_12(_CONSTRUCT_TEMPLATE_QUERY)
    rdf_graph, root = query_to_rdf11(prepared)
    query_object = rdf11_to_query(rdf_graph, root)
    result_graph = g.query(query_object).graph
    triples = list(result_graph)
    assert triples == [
        (
            TripleTerm(URIRef("http://example/s"), URIRef("http://example/p"), URIRef("http://example/o")),
            URIRef("http://example/verifiedBy"),
            URIRef("http://example/me"),
        )
    ]


def test_rdf11_to_sparql11_text_still_works():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:s :p :o .\n", format="turtle12")
    prepared = prepare_query_12(_CONSTRUCT_TEMPLATE_QUERY)
    rdf_graph, root = query_to_rdf11(prepared)
    text = rdf11_to_sparql11_text(rdf_graph, root)
    assert isinstance(text, str)
    result_graph = g.query(text).graph
    triples = list(result_graph)
    assert triples == [
        (
            TripleTerm(URIRef("http://example/s"), URIRef("http://example/p"), URIRef("http://example/o")),
            URIRef("http://example/verifiedBy"),
            URIRef("http://example/me"),
        )
    ]


def test_values_row_eager_hash():
    g = StarLayerGraph()
    g.parse(data="@prefix : <http://example/> .\n:who :verified <<( :s :p :o )>> .\n", format="turtle12")
    actual = _run_lowered(
        "PREFIX : <http://example/> SELECT * WHERE { :who :verified ?t . VALUES ?t { <<( :s :p :o )>> } }",
        g,
    )
    assert actual == [
        {
            Variable("t"): TripleTerm(
                URIRef("http://example/s"), URIRef("http://example/p"), URIRef("http://example/o")
            )
        }
    ]


# --- Update lowering: DeleteWhere/Modify with a triple-term pattern -------
#
# See CLAUDE.md finding #28 for the full non-ground-triple-term-pattern
# investigation (SELECT side) and the "closing the DeleteWhere gap" session
# for these Update-specific fixes: DeleteWhere with a non-ground triple
# term is rewritten into an equivalent Modify (`_lower_delete_where`), and
# closing that gap surfaced two further, genuinely separate bugs outside
# this project entirely - a confirmed rdflib `evalModify` bug (writing
# through the wrong graph wrapper against a Dataset) and a real gap in the
# sibling `starlayergraph` repo's own `StarLayerDataset` (no
# TripleTerm-aware `add`/`remove`/`addN` override at all, unlike
# `triples()`/`quads()`) - both fixed there, not here, but exercised by
# every test below that goes through `StarLayerDataset`.


def _run_update(update_text: str, graph) -> None:
    prepared = prepare_update_12(update_text)
    rdf_graph, root = update_to_rdf11(prepared)
    update_object = rdf11_to_update(rdf_graph, root)
    evalUpdate(graph, update_object)


def _run_update_via_text(update_text: str, graph) -> None:
    """Same as ``_run_update``, but round-tripped through
    ``rdf11_update_to_sparql11_text`` and reparsed with plain rdflib first -
    exercises the text-serialization path ``native_update`` needs for a
    remote HTTP store that hard-requires a string (SPARQLUpdateStore), not
    just the direct-object execution path."""
    from rdflib.plugins.sparql.algebra import translateUpdate
    from rdflib.plugins.sparql.parser import parseUpdate

    prepared = prepare_update_12(update_text)
    rdf_graph, root = update_to_rdf11(prepared)
    text = rdf11_update_to_sparql11_text(rdf_graph, root)
    reparsed = translateUpdate(parseUpdate(text))
    evalUpdate(graph, reparsed)


_TT_DATA = """
@prefix : <http://example/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
:r1 rdf:reifies <<( :a :b :c )>> .
:r2 rdf:reifies <<( :x :b :c )>> .
:r3 rdf:reifies <<( :a :other :thing )>> .
"""


def test_delete_where_ground_triple_term():
    """The ordinary (unchanged) DeleteWhere path - a ground triple term
    needs no Filter/Extend wrapping, so this stays on the simple
    _lower_flat_triples_op path, not the Modify rewrite."""
    g = StarLayerDataset()
    g.parse(data=_TT_DATA, format="turtle12")
    _run_update(
        "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
        "DELETE WHERE { ?r rdf:reifies <<( :a :b :c )>> . }",
        g,
    )
    remaining = {s for s, p, o in g.triples((None, None, None))}
    assert remaining == {URIRef("http://example/r2"), URIRef("http://example/r3")}


def test_delete_where_nonground_triple_term_rewrites_to_modify():
    """The gap this session closed: a non-ground triple term in DELETE
    WHERE previously raised NotImplementedError (evalDeleteWhere has no
    Filter/Extend-wrapping capability for its own flat triples list) -
    _lower_delete_where now rewrites this into an equivalent
    DELETE {...} WHERE {...} Modify instead. Matches both :r1 and :r2
    (predicate :b, object :c) and leaves :r3 alone (predicate :other) -
    also exercises the "same variable" already_bound machinery
    (_add_single_constraint) correctly classifying ?s as Extend, not
    Filter, since it's introduced solely by the triple term."""
    g = StarLayerDataset()
    g.parse(data=_TT_DATA, format="turtle12")
    _run_update(
        "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
        "DELETE WHERE { ?r rdf:reifies <<( ?s :b :c )>> . }",
        g,
    )
    remaining = {s for s, p, o in g.triples((None, None, None))}
    assert remaining == {URIRef("http://example/r3")}


def test_modify_delete_nonground_triple_term_pattern():
    """An ordinary Modify (not DeleteWhere) with a non-ground triple-term
    pattern in its own WHERE clause - the case that was already working
    before the DeleteWhere-specific gap, kept here as a regression test
    since no Update-lowering test existed for it at all before this
    session."""
    g = StarLayerDataset()
    g.parse(data=_TT_DATA, format="turtle12")
    _run_update(
        "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
        "DELETE { ?r :flagged true } INSERT { ?r :matchedSubject ?s } "
        "WHERE { ?r rdf:reifies <<( ?s :b :c )>> . }",
        g,
    )
    matched = {
        (s, o) for s, p, o in g.triples((None, URIRef("http://example/matchedSubject"), None))
    }
    assert matched == {
        (URIRef("http://example/r1"), URIRef("http://example/a")),
        (URIRef("http://example/r2"), URIRef("http://example/x")),
    }


def test_modify_insert_only_nonground_triple_term_pattern():
    """A Modify with only an INSERT clause (no DELETE at all) - `.delete` is
    legitimately absent from the algebra CompValue in this case. Regression
    test for a real bug in `_lower_modify`: it used `node.get("delete")`,
    but `CompValue.get(key)` isn't a normal dict `.get()` - its signature
    (`get(self, a, variables=False, errors=False)`) has no default
    parameter and falls back to returning the key string itself, not None,
    for a missing key (`OrderedDict.get(self, a, a)`). That silently handed
    `_lower_modify_clause` the string "delete" instead of None, crashing on
    `clause.name`. Fixed by switching to attribute access (`node.delete`),
    which correctly returns None via CompValue.__getattr__."""
    g = StarLayerDataset()
    g.parse(data=_TT_DATA, format="turtle12")
    _run_update(
        "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
        "INSERT { ?r :matchedSubject ?s } "
        "WHERE { ?r rdf:reifies <<( ?s :b :c )>> . }",
        g,
    )
    matched = {
        (s, o) for s, p, o in g.triples((None, URIRef("http://example/matchedSubject"), None))
    }
    assert matched == {
        (URIRef("http://example/r1"), URIRef("http://example/a")),
        (URIRef("http://example/r2"), URIRef("http://example/x")),
    }


def test_prepare_query_12_initns():
    """`initNs` seeds the query's Prologue - a bare `ex:` prefixed name
    resolves without the query text declaring `PREFIX ex:` itself, matching
    plain rdflib's own `prepareQuery(text, initNs=...)`."""
    q = prepare_query_12(
        "SELECT ?s WHERE { ?s ex:knows ex:bob }", initNs={"ex": "http://example.org/"}
    )
    triples = q.algebra.p.p.triples
    assert triples == [
        (Variable("s"), URIRef("http://example.org/knows"), URIRef("http://example.org/bob"))
    ]


def test_prepare_query_12_initns_overridden_by_query_own_prefix():
    """A `PREFIX` actually written in the query text overrides the same
    prefix supplied via `initNs` - same precedence as plain rdflib's
    `translatePrologue` (initNs binds first, the query's own declarations
    are applied afterward)."""
    q = prepare_query_12(
        "PREFIX ex: <http://override.org/> SELECT ?s WHERE { ?s ex:knows ex:bob }",
        initNs={"ex": "http://example.org/"},
    )
    triples = q.algebra.p.p.triples
    assert triples == [
        (Variable("s"), URIRef("http://override.org/knows"), URIRef("http://override.org/bob"))
    ]


def test_prepare_query_12_base():
    """`base` resolves a relative IRI in the query text, same as plain
    rdflib's `prepareQuery(text, base=...)`."""
    q = prepare_query_12("SELECT ?s WHERE { ?s <knows> <bob> }", base="http://example.org/")
    triples = q.algebra.p.p.triples
    assert triples == [
        (Variable("s"), URIRef("http://example.org/knows"), URIRef("http://example.org/bob"))
    ]


def test_prepare_update_12_initns():
    """`prepare_update_12`'s own `initNs` passthrough, mirroring the query
    side above - exercised through a real INSERT DATA against a Dataset."""
    g = StarLayerDataset()
    update = prepare_update_12(
        "INSERT DATA { ex:alice ex:knows ex:bob }", initNs={"ex": "http://example.org/"}
    )
    evalUpdate(g, update)
    matches = list(g.triples((
        URIRef("http://example.org/alice"),
        URIRef("http://example.org/knows"),
        URIRef("http://example.org/bob"),
    )))
    assert len(matches) == 1


class TestUpdateToSparql11Text:
    """``rdf11_update_to_sparql11_text`` - needed for a remote HTTP store
    that hard-requires a plain string (SPARQLUpdateStore.update() asserts
    isinstance(query, str)), unlike the direct-Update-object execution path
    every other Update test in this file uses. Each case here runs the
    *same* update through both ``_run_update`` (object) and
    ``_run_update_via_text`` (text round-trip) against separately-seeded,
    identical starting graphs, and asserts they reach the same final
    state - the real parity claim, not just "the text reparses.\""""

    def test_insert_data_with_graph_clause(self):
        g1 = StarLayerDataset()
        g2 = StarLayerDataset()
        q = "PREFIX : <http://ex/> INSERT DATA { GRAPH <http://ex/g1> { :a :b :c . } }"
        _run_update(q, g1)
        _run_update_via_text(q, g2)
        assert set(g1.get_context("http://ex/g1").triples((None, None, None))) == set(
            g2.get_context("http://ex/g1").triples((None, None, None))
        )
        assert (URIRef("http://ex/a"), URIRef("http://ex/b"), URIRef("http://ex/c")) in g2.get_context(
            "http://ex/g1"
        )

    def test_delete_data_ground_triple_term(self):
        """Exercises the tt:HASH-lowered ground-triple-term case through
        text, not just plain triples. The registry entry for the triple
        term itself deliberately survives a DELETE (same as the legacy
        pipeline's own documented behavior - only the one referencing
        triple goes away, not the tt:HASH encoding infrastructure), so the
        real check is that the specific (who, verifiedBy, tt) triple is
        gone, not has_triple_term()."""
        seed = "@prefix : <http://example/> .\n:who :verifiedBy <<( :s :p :o )>> .\n"
        g = StarLayerGraph()
        g.parse(data=seed, format="turtle12")
        q = "PREFIX : <http://example/> DELETE DATA { :who :verifiedBy <<( :s :p :o )>> . }"
        _run_update_via_text(q, g)
        remaining = list(g.triples((URIRef("http://example/who"), URIRef("http://example/verifiedBy"), None)))
        assert remaining == []

    def test_modify_where_insert_with_triple_term(self):
        """Modify (WHERE + INSERT, non-ground triple-term pattern) through
        text - the branch that needs _sparql11_text_for_where's throwaway-
        SelectQuery reuse of _AlgebraTranslator11's pattern rendering."""
        g = StarLayerGraph()
        g.parse(data=_TT_DATA, format="turtle12")
        q = (
            "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "INSERT { ?r :matchedSubject ?s } WHERE { ?r rdf:reifies <<( ?s :b :c )>> . }"
        )
        _run_update_via_text(q, g)
        matched = {
            (s, o) for s, p, o in g.triples((None, URIRef("http://example/matchedSubject"), None))
        }
        assert matched == {
            (URIRef("http://example/r1"), URIRef("http://example/a")),
            (URIRef("http://example/r2"), URIRef("http://example/x")),
        }

    def test_clear_graph(self):
        g = StarLayerDataset()
        _run_update(
            "PREFIX : <http://ex/> INSERT DATA { GRAPH <http://ex/g1> { :a :b :c . } }", g
        )
        _run_update_via_text("CLEAR GRAPH <http://ex/g1>", g)
        assert list(g.get_context("http://ex/g1").triples((None, None, None))) == []


class TestInsertDataGroundTripleTermPersistsEncoding:
    """Regression test for a real gap found while `starlayergraph` was
    scoping the full removal of its old text-based rewriter: a ground
    triple term used as an ordinary *value* in InsertData (not a Modify
    template) was hashed correctly, but its own encoding triples
    (rdf:subject/predicate/object on the tt:HASH URI) were never persisted
    to the graph - only registered in the ephemeral, process-global
    `remember_tt_hash` cache `_eager_lower_value` alone populates. A
    same-process `.triples()` read appeared to work (it consults that
    cache), masking the gap; `has_triple_term()`/`triple_terms()` (which
    both rebuild their registry from the store's own *persisted* encoding
    triples) never saw the triple term at all. Fixed by giving InsertData
    its own lowering (`_lower_flat_triples_for_insert`/
    `_lower_flat_triples_term_for_insert`) instead of reusing the shared
    pattern-position one (correct for DeleteData/DeleteWhere/VALUES rows/
    ordinary WHERE matching, all of which only ever *match* an existing
    value, never introduce a new one)."""

    def test_encoding_triples_written_for_ground_triple_term_value(self):
        g = StarLayerGraph()
        _run_update(
            "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "INSERT DATA { :stmt3 rdf:reifies <<( :carol :knows :dave )>> . }",
            g,
        )
        # evalUpdate() alone (what _run_update calls) doesn't rebuild
        # StarLayerGraph's own registry the way its real .update() method
        # does afterward - force it here so has_triple_term()/
        # triple_terms() reflect what's actually *persisted* in the store,
        # not the ephemeral process-global remember_tt_hash cache (which
        # would mask this exact gap - see this class's own docstring).
        g._build_registry_from_store()
        assert g.has_triple_term(
            URIRef("http://example/carol"), URIRef("http://example/knows"), URIRef("http://example/dave")
        )
        tt = next(g.triple_terms(
            URIRef("http://example/carol"), URIRef("http://example/knows"), URIRef("http://example/dave")
        ), None)
        assert tt is not None

    def test_encoding_triples_written_via_text_round_trip_too(self):
        """Same case through rdf11_update_to_sparql11_text - confirms the
        fix holds for the remote-HTTP-store text-serialization path too,
        not just direct-object execution."""
        g = StarLayerGraph()
        _run_update_via_text(
            "PREFIX : <http://example/> PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> "
            "INSERT DATA { :stmt3 rdf:reifies <<( :carol :knows :dave )>> . }",
            g,
        )
        g._build_registry_from_store()
        assert g.has_triple_term(
            URIRef("http://example/carol"), URIRef("http://example/knows"), URIRef("http://example/dave")
        )

    def test_nested_ground_triple_term_both_levels_persist_encoding(self):
        """A triple term nested in *object* position (the only legal
        nesting) - both the outer and inner triple term's own encoding
        triples must be persisted."""
        g = StarLayerGraph()
        _run_update(
            "PREFIX : <http://example/> "
            "INSERT DATA { :stmt3 :about <<( :p :q <<( :carol :knows :dave )>> )>> . }",
            g,
        )
        g._build_registry_from_store()
        assert g.has_triple_term(
            URIRef("http://example/carol"), URIRef("http://example/knows"), URIRef("http://example/dave")
        )
        inner = TripleTerm(
            URIRef("http://example/carol"), URIRef("http://example/knows"), URIRef("http://example/dave")
        )
        assert g.has_triple_term(URIRef("http://example/p"), URIRef("http://example/q"), inner)


# InsertData with a plain (no triple term involved) ground value, against a
# StarLayerDataset specifically, is deliberately not covered here:
# `evalInsertData`'s own `g += u.triples` hits a separate, pre-existing,
# already-documented incompatibility (`ConjunctiveGraph.__iadd__` expects
# quads, not plain triples - the same root cause
# `patch_evalmodify_default_graph_selection` fixes for `evalModify`, but
# `evalInsertData` isn't patched) - confirmed unrelated to this session's
# DeleteWhere fix (reproduces against plain, unmodified rdflib +
# StarLayerDataset with no triple terms involved at all), and out of scope
# here. Not a concern for the tests just above, which use StarLayerGraph
# (not Dataset) or a GRAPH-wrapped quad (a different, unaffected write
# path) - see test_clear_graph above.


# --- End-to-end: existing W3C fixtures, official ground truth -------------


@_no_data
@pytest.mark.parametrize("entry", EVAL_SELECT, ids=lambda e: e.test_iri)
def test_eval_select_via_lowering(entry):
    query_text = entry.read(entry.query_file)
    expected = parse_srj(entry.read(entry.result_file))

    graph = _new_graph(entry)
    if entry.data_file:
        graph.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    actual = _run_lowered(query_text, graph)
    assert bindings_match(actual, expected)


@_no_data
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT, ids=lambda e: e.test_iri)
def test_eval_construct_via_lowering(entry):
    query_text = entry.read(entry.query_file)
    expected_graph = StarLayerGraph()
    expected_graph.parse(data=entry.read(entry.result_file), format="turtle12")

    graph = _new_graph(entry)
    if entry.data_file:
        graph.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    prepared = prepare_query_12(query_text)
    rdf_graph, root = query_to_rdf11(prepared)
    query_object = rdf11_to_query(rdf_graph, root)
    actual_graph = graph.query(query_object).graph
    assert to_isomorphic(skolemize_graph(actual_graph)) == to_isomorphic(skolemize_graph(expected_graph))
