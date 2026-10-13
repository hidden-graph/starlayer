"""W3C SPARQL 1.2 test suite, run against this project's own translation
pipeline — see CLAUDE.md's Phase 6 status entry and
``tests/w3c_sparql12/download_w3c_sparql12_tests.py`` for how ``data/`` is
populated (a real, separate test suite from starlayer.graph's own ``tests/w3c_turtle12/``,
which is Turtle-1.2-only).

Ten manifest categories are fetched as of 2026-10-13 (see
`download_w3c_sparql12_tests.py`'s own `CATEGORIES` list and module
docstring) - every one the W3C suite publishes. Several fixtures across
`codepoint-escapes`/`syntax` are confirmed inherited rdflib grammar gaps,
not starlayer bugs or W3C suite defects - see `_INHERITED_RDFLIB_GAP_FRAGMENTS`
below and starlayer/graph/CLAUDE.md's 2026-10-13 dated entry for the full,
individually-reasoned account of each.

Three test shapes:
1. Syntax tests (`PositiveSyntaxTest`/`NegativeSyntaxTest`, and their
   `*Update*` counterparts) - parse-only, via this project's own
   `parse_query_12`/`parse_update_12` (not starlayer.graph's parser, not plain
   rdflib's) - confirms our grammar extension (`grammar12.py`) accepts
   every construct the suite considers valid 1.2 syntax, and rejects every
   construct it considers invalid.
2. `QueryEvaluationTest` (SELECT-shaped, `.srj` expected results) - the
   real semantic check: parse via `parse12.py` -> encode -> decode ->
   regenerate text via `serialize12.py` -> execute the *regenerated* text
   against a real `StarLayerGraph` loaded with the test's data -> compare
   against the suite's own official expected results (not just
   self-consistency against the original query, which the existing
   `tests/test_phase6_serialize12.py` already covers with hand-written
   cases - this harness checks against an independent, external ground
   truth). `.srx`-only tests (no `.srj`) are skipped - this harness's JSON
   results parser (`tests/w3c_sparql12/harness.py`) doesn't have an XML
   counterpart yet, not needed for the tests actually hit.
3. `QueryEvaluationTest` (CONSTRUCT-shaped, `.ttl` expected results) -
   same loop, compared by graph isomorphism instead of binding rows.

`UpdateEvaluationTest` is collected (see the downloader) but not run here -
this project has never attempted Update serialization back to text at all,
for 1.1 or 1.2 (see `test_phase2_update.py`'s docstring) - skipped with a
clear reason, not silently ignored.
"""

from __future__ import annotations

import json

import pytest
from rdflib.compare import to_isomorphic
from starlayer.graph.graph.starlayer_dataset import StarLayerDataset
from starlayer.graph.graph.starlayer_graph import StarLayerGraph
from starlayer.graph.query.version_directive import strip_version_directive
from starlayer.sparql import query_to_rdf, rdf_to_query
from starlayer.sparql.parse12 import prepare_query_12, prepare_update_12
from tests.sparql.w3c_sparql12.harness import (
    bindings_match,
    load_index,
    parse_srj,
    skolemize_graph,
)

pytestmark = pytest.mark.w3c_sparql12

ALL_ENTRIES = load_index()

SYNTAX_POSITIVE = [
    e for e in ALL_ENTRIES if e.test_type in ("PositiveSyntaxTest", "PositiveUpdateSyntaxTest")
]
SYNTAX_NEGATIVE = [
    e for e in ALL_ENTRIES if e.test_type in ("NegativeSyntaxTest", "NegativeUpdateSyntaxTest")
]
EVAL_SELECT = [
    e
    for e in ALL_ENTRIES
    if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".srj")
]
EVAL_CONSTRUCT = [
    e
    for e in ALL_ENTRIES
    if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".ttl")
]
EVAL_UPDATE = [e for e in ALL_ENTRIES if e.test_type == "UpdateEvaluationTest"]

_no_data = pytest.mark.skipif(not ALL_ENTRIES, reason="W3C SPARQL 1.2 test data not fetched - run download_w3c_sparql12_tests.py")


def _is_update(entry) -> bool:
    return "Update" in entry.test_type


# StarLayerGraph.parse's `format=` is not resolved via rdflib's plugin
# registry for the RDF-1.2-aware formats (confirmed: 'turtle12'/'trig12'/
# etc. aren't registered `Parser` plugins at all) - it's a bespoke dispatch
# inside StarLayerGraph.parse itself, keyed on the literal format string,
# with genuinely different parsers per RDF *syntax* (TriG's `GRAPH { }`
# blocks are not valid Turtle). A fixture's actual syntax has to match the
# format passed in - confirmed empirically that a real .trig fixture
# (data-4.trig, using `GRAPH :g { ... }`) raises a real Turtle12SyntaxError
# when parsed as 'turtle12' ('unexpected trailing content' at the first
# GRAPH block) and parses cleanly as 'trig12'. Previously this harness
# always passed 'turtle12' regardless of the data file's actual extension -
# misdiagnosed as "starlayer.graph's own Turtle parser rejecting nested
# <<...>> syntax" when investigating failures, when the real cause was
# simply parsing TriG/N-Quads content with the Turtle-only parser.
_DATA_FORMAT_BY_SUFFIX = {
    ".ttl": "turtle12",
    ".trig": "trig12",
    ".nq": "nq12",
    ".nt": "nt12",
}


def _data_format(entry) -> str:
    for suffix, fmt in _DATA_FORMAT_BY_SUFFIX.items():
        if entry.data_file.endswith(suffix):
            return fmt
    raise ValueError(f"no known RDF-1.2 format for data file {entry.data_file!r}")


# A fixture's data may define named graphs (TriG/N-Quads) - those need a
# real multi-graph StarLayerDataset, not a single StarLayerGraph (which
# raises "You performed a query operation requiring a dataset" the moment a
# query uses GRAPH against data that was never loaded into any graph at all
# - a lone StarLayerGraph has no notion of a graph name other than its own).
# Same convention already used by starlayer.graph's own
# tests/w3c_sparql12/test_w3c_sparql12_eval.py::_new_graph - this harness
# previously always constructed a plain StarLayerGraph() regardless of the
# data file's actual format, confirmed a real, reproducible false failure
# for every eval-triple-terms fixture backed by data-4.trig (graphs-1,
# graphs-2, expr-1): querying a GRAPH clause against data that was silently
# merged into one ungraphed StarLayerGraph instead of a real multi-graph
# Dataset gave wrong (usually empty) results, misattributed at the time to
# a starlayer.graph in-memory-backend or algebra-round-trip bug - neither was at
# fault, this harness was simply loading the data into the wrong container.
_DATASET_FORMATS = {"trig12", "nq12"}


def _new_graph(entry) -> StarLayerGraph | StarLayerDataset:
    if entry.data_file and _data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset()
    return StarLayerGraph()


# Confirmed, documented W3C test-suite defect, not an implementation bug -
# see docs/sparql/w3c-sparql12-test-suite-issues.md Issue 1. Each of these
# seven PositiveSyntaxTest fixtures constructs an explicit triple term
# directly as a pattern's *subject*, which RDF 1.2 Concepts' own
# triple-formation rule never permits (a triple term is only ever legal as
# the object) - confirmed against the spec text itself and independently
# against a live SPARQL engine rejecting the same shape. xfail(strict=True)
# rather than a plain skip: if a future suite fix (filed upstream but not
# yet accepted as of this writing) changes these fixtures, an unexpected
# pass here is itself the signal to revisit this list, not something to
# stay silently green.
_KNOWN_SUITE_DEFECT_FRAGMENTS = {
    "basic-tripleterm-01",
    "basic-tripleterm-03",
    "bnode-tripleterm-01",
    "bnode-tripleterm-02",
    "bnode-tripleterm-03",
    "compound-tripleterm-subject",
    "nested-tripleterm-02",
}


def _syntax_positive_param(entry):
    fragment = entry.test_iri.rsplit("#", 1)[-1]
    if fragment in _KNOWN_SUITE_DEFECT_FRAGMENTS:
        return pytest.param(
            entry,
            marks=pytest.mark.xfail(
                reason=(
                    "W3C test-suite defect, not an implementation bug - "
                    "docs/sparql/w3c-sparql12-test-suite-issues.md Issue 1"
                ),
                strict=True,
            ),
            id=entry.test_iri,
        )
    return pytest.param(entry, id=entry.test_iri)


# Confirmed inherited rdflib gaps, not starlayer-specific bugs and not W3C
# suite defects either - each one checked directly against *plain,
# unmodified* rdflib (no starlayer.sparql involved at all) before being
# added here, confirmed to produce the identical wrong result there too.
# Found 2026-10-13 while wiring the `codepoint-escapes`/`syntax` categories
# into this suite for the first time - see starlayer/graph/CLAUDE.md's
# dated entry for the full account of each:
#   - nested-aggregate-functions / duplicated-values-variable: rdflib's own
#     grammar never rejects a nested aggregate (COUNT(COUNT(*))) or a
#     repeated variable within one VALUES row (VALUES (?a ?a) {...}),
#     despite both being syntax errors per the SPARQL 1.1/1.2 grammar.
#   - group-by-scope-bad-1/2/3: rdflib never rejects reusing a GROUP BY
#     key's own variable name as a fresh SELECT-expression target (the
#     SPARQL grammar's own variable-scoping rule).
#   - codepoint-esc-01-bad/03-bad: rdflib accepts a whole query spelled via
#     \\uXXXX codepoint escapes outside any string/IRI token, and a
#     codepoint escape inside a PN_LOCAL prefixed name - both of which the
#     SPARQL 1.2 grammar's own codepoint-escape production restricts to
#     specific token contexts.
#   - surrogate-esc-01 through -05-bad: rdflib's \\uXXXX handling never
#     validates that a lone or reversed-order UTF-16 surrogate pair is a
#     valid Unicode scalar value - it accepts each one unconditionally.
# xfail(strict=True), same reasoning as _KNOWN_SUITE_DEFECT_FRAGMENTS above:
# an unexpected pass means rdflib's own grammar changed, which is the
# signal to revisit this list, not something to stay silently green on.
_INHERITED_RDFLIB_GAP_FRAGMENTS = {
    "nested-aggregate-functions",
    "duplicated-values-variable",
    "group-by-scope-bad-1",
    "group-by-scope-bad-2",
    "group-by-scope-bad-3",
    "codepoint-esc-01-bad",
    "codepoint-esc-03-bad",
    "surrogate-esc-01-bad",
    "surrogate-esc-02-bad",
    "surrogate-esc-03-bad",
    "surrogate-esc-04-bad",
    "surrogate-esc-05-bad",
}


def _syntax_negative_param(entry):
    fragment = entry.test_iri.rsplit("#", 1)[-1]
    if fragment in _INHERITED_RDFLIB_GAP_FRAGMENTS:
        return pytest.param(
            entry,
            marks=pytest.mark.xfail(
                reason=(
                    "Confirmed inherited rdflib grammar gap, not a starlayer bug - "
                    "see starlayer/graph/CLAUDE.md's 2026-10-13 dated entry"
                ),
                strict=True,
            ),
            id=entry.test_iri,
        )
    return pytest.param(entry, id=entry.test_iri)


# Confirmed inherited rdflib *term-equality* gaps (not grammar this time) -
# both checked directly against plain, unmodified rdflib before being added
# here. Found 2026-10-13, same investigation as above:
#   - strlang: stock Builtin_STRLANG never rejects an empty language-tag
#     argument (STRLANG("abc", "")), though RDF 1.2 Query sec 17.4.2.16
#     requires it to error.
#   - plain-string-same (rdf11 category): stock sameTerm()/Literal.__eq__
#     treats a simple literal and its ^^xsd:string equivalent as different
#     terms (confirmed: Literal("foo") != Literal("foo", datatype=XSD.string)),
#     contradicting RDF 1.1/1.2 Concepts' own "a simple literal is shorthand
#     for the identical xsd:string literal" definition.
_INHERITED_RDFLIB_GAP_EVAL_FRAGMENTS = {"strlang", "plain-string-same"}


def _eval_select_param(entry):
    fragment = entry.test_iri.rsplit("#", 1)[-1]
    if fragment in _INHERITED_RDFLIB_GAP_EVAL_FRAGMENTS:
        return pytest.param(
            entry,
            marks=pytest.mark.xfail(
                reason=(
                    "Confirmed inherited rdflib term-equality gap, not a starlayer bug - "
                    "see starlayer/graph/CLAUDE.md's 2026-10-13 dated entry"
                ),
                strict=True,
            ),
            id=entry.test_iri,
        )
    return pytest.param(entry, id=entry.test_iri)


@_no_data
@pytest.mark.parametrize("entry", [_syntax_positive_param(e) for e in SYNTAX_POSITIVE])
def test_syntax_positive(entry):
    text = entry.read(entry.query_file or entry.update_file)
    # VERSION "label" (SPARQL 1.2 Query sec 4.3) isn't real grammar
    # prepare_query_12/prepare_update_12 understand on their own - it must
    # be stripped by the caller first (see version_directive.py's own
    # module docstring). Needed for the first time here by the `version`
    # category's own PositiveSyntaxTest fixtures, added 2026-10-13.
    text, _ = strip_version_directive(text)
    if _is_update(entry):
        prepare_update_12(text)
    else:
        prepare_query_12(text)


@_no_data
@pytest.mark.parametrize("entry", [_syntax_negative_param(e) for e in SYNTAX_NEGATIVE])
def test_syntax_negative(entry):
    text = entry.read(entry.query_file or entry.update_file)
    text, _ = strip_version_directive(text)
    # Deliberately broad: parametrized over every SYNTAX_NEGATIVE W3C fixture,
    # which fail via different exception types depending on what's malformed.
    with pytest.raises(Exception):  # noqa: B017
        if _is_update(entry):
            prepare_update_12(text)
        else:
            prepare_query_12(text)


@_no_data
@pytest.mark.parametrize("entry", [_eval_select_param(e) for e in EVAL_SELECT])
def test_eval_select(entry):
    query_text = entry.read(entry.query_file)
    result_text = entry.read(entry.result_file)
    # "QueryEvaluationTest" with a ".srj" result file covers both SELECT
    # (a "bindings" array) and ASK (a bare "boolean") per the SPARQL Query
    # Results JSON Format - EVAL_SELECT's own filter (test_type ==
    # "QueryEvaluationTest" and result_file.endswith(".srj")) doesn't
    # distinguish them, and this function's own name predates ever having
    # an ASK-shaped fixture flow through it (confirmed: lang-basedir's
    # contains.rq and rdf11's plain-string-same.rq, added 2026-10-13, are
    # the first two in this whole suite). Checked directly off the raw
    # JSON rather than the query text (e.g. "starts with ASK") - more
    # robust, and symmetric with how the result file itself is produced.
    is_ask = "boolean" in json.loads(result_text)

    starlayer_graph = _new_graph(entry)
    if entry.data_file:
        starlayer_graph.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    from starlayer.sparql.serialize12 import _translate_algebra_12

    regenerated_text = _translate_algebra_12(reconstructed)

    if is_ask:
        # No "bindings" to compare at all - parse_srj()/bindings_match()
        # are both bindings-shaped and would silently treat a missing
        # "results" key as zero bindings regardless of the real boolean
        # answer, so this is a genuinely separate comparison, not a
        # variant of the one below.
        assert starlayer_graph.query(regenerated_text).askAnswer == json.loads(result_text)["boolean"]
        return

    expected = parse_srj(result_text)

    # {k: v for ... if v is not None}, not a bare dict(row): an unbound
    # variable (including one explicitly bound to UNDEF via a VALUES row -
    # SPARQL's own result-set semantics make the two indistinguishable, per
    # the SPARQL Query Results JSON format simply omitting the key either
    # way) comes back from starlayer.graph as key -> None, not an absent key -
    # confirmed a real, reproducible false mismatch via the W3C
    # triple-on-undefs fixture before this filtering existed: `expected`
    # (built by parse_srj from the official .srj file) naturally has no
    # key at all for an unbound variable, so an unfiltered `actual` never
    # compared equal even when the *bound* variables agreed perfectly.
    # Same filtering starlayer.graph's own
    # tests/w3c_sparql12/test_w3c_sparql12_eval.py::test_eval_select_original_query
    # already applies, for the identical reason.
    actual = [{k: v for k, v in dict(row).items() if v is not None} for row in starlayer_graph.query(regenerated_text).bindings]
    # bindings_match, not exact canon_bindings equality: a BNode's (including
    # starlayer.graph's own anonymous reifiers, which are ordinary BNodes)
    # *label* is never semantically meaningful, only a consistent relabeling
    # is - see
    # harness.bindings_match's own docstring. canon_bindings alone
    # false-mismatches on any W3C fixture using one (e.g.
    # results-reifiedtriples-1j).
    assert bindings_match(actual, expected)


@_no_data
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT, ids=lambda e: e.test_iri)
def test_eval_construct(entry):
    query_text = entry.read(entry.query_file)
    # A plain rdflib.Graph().parse(format="turtle") can't handle RDF 1.2
    # syntax (confirmed: "turtle12" isn't a registered rdflib plugin at
    # all - StarLayerGraph.parse's format= dispatch is bespoke, per
    # _data_format's own docstring) - and a CONSTRUCT test's *expected*
    # result file can genuinely contain RDF 1.2 annotation syntax (e.g.
    # construct-1.ttl: "<< :a :b :c >> :q :z ."), not just the CONSTRUCTed
    # graph's own plain-Turtle-shaped output. Confirmed a real bug via
    # direct reproduction: plain "turtle" raised a BadSyntax error on
    # exactly that file, unrelated to anything this project's own
    # translation produces.
    expected_graph = StarLayerGraph()
    expected_graph.parse(data=entry.read(entry.result_file), format="turtle12")

    starlayer_graph = _new_graph(entry)
    if entry.data_file:
        starlayer_graph.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    from starlayer.sparql.serialize12 import _translate_algebra_12

    regenerated_text = _translate_algebra_12(reconstructed)

    actual_graph = starlayer_graph.query(regenerated_text).graph
    assert to_isomorphic(skolemize_graph(actual_graph)) == to_isomorphic(skolemize_graph(expected_graph))


@_no_data
@pytest.mark.parametrize("entry", EVAL_UPDATE, ids=lambda e: e.test_iri)
def test_eval_update_not_yet_supported(entry):
    pytest.skip(
        "Update serialization back to SPARQL text is not implemented by this "
        "project for 1.1 or 1.2 - see test_phase2_update.py's docstring and "
        "CLAUDE.md's Not-started section."
    )
