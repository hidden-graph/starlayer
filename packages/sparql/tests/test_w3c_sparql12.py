"""W3C SPARQL 1.2 test suite, run against this project's own translation
pipeline — see CLAUDE.md's Phase 6 status entry and
``tests/w3c_sparql12/download_w3c_sparql12_tests.py`` for how ``data/`` is
populated (a real, separate test suite from starlayergraph's own ``tests/w3c/``,
which is Turtle-1.2-only).

Four manifest categories are in scope, matching what this project's
`parse12.py`/`serialize12.py` actually support today (see CLAUDE.md's "Not
started" section for what's deliberately excluded and why):
`syntax-triple-terms-positive`/`-negative`, `eval-triple-terms`,
`expression`.

Three test shapes:
1. Syntax tests (`PositiveSyntaxTest`/`NegativeSyntaxTest`, and their
   `*Update*` counterparts) - parse-only, via this project's own
   `parse_query_12`/`parse_update_12` (not starlayergraph's parser, not plain
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

import pytest
from rdflib.compare import to_isomorphic
from starlayergraph.graph.starlayergraph_dataset import StarLayerDataset
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

from starsparql import query_to_rdf, rdf_to_query
from starsparql.parse12 import prepare_query_12, prepare_update_12
from w3c_sparql12.harness import bindings_match, canon_bindings, load_index, parse_srj, skolemize_graph

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
# (data-4.trig, using `GRAPH :g { ... }`) raises a real TurtleSyntaxError
# when parsed as 'turtle12' ('unexpected trailing content' at the first
# GRAPH block) and parses cleanly as 'trig12'. Previously this harness
# always passed 'turtle12' regardless of the data file's actual extension -
# misdiagnosed as "starlayergraph's own Turtle parser rejecting nested
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
# Same convention already used by starlayergraph's own
# tests/w3c_sparql12/test_w3c_sparql12_eval.py::_new_graph - this harness
# previously always constructed a plain StarLayerGraph() regardless of the
# data file's actual format, confirmed a real, reproducible false failure
# for every eval-triple-terms fixture backed by data-4.trig (graphs-1,
# graphs-2, expr-1): querying a GRAPH clause against data that was silently
# merged into one ungraphed StarLayerGraph instead of a real multi-graph
# Dataset gave wrong (usually empty) results, misattributed at the time to
# a starlayergraph in-memory-backend or algebra-round-trip bug - neither was at
# fault, this harness was simply loading the data into the wrong container.
_DATASET_FORMATS = {"trig12", "nq12"}


def _new_graph(entry) -> StarLayerGraph | StarLayerDataset:
    if entry.data_file and _data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset()
    return StarLayerGraph()


@_no_data
@pytest.mark.parametrize("entry", SYNTAX_POSITIVE, ids=lambda e: e.test_iri)
def test_syntax_positive(entry):
    text = entry.read(entry.query_file or entry.update_file)
    if _is_update(entry):
        prepare_update_12(text)
    else:
        prepare_query_12(text)


@_no_data
@pytest.mark.parametrize("entry", SYNTAX_NEGATIVE, ids=lambda e: e.test_iri)
def test_syntax_negative(entry):
    text = entry.read(entry.query_file or entry.update_file)
    with pytest.raises(Exception):
        if _is_update(entry):
            prepare_update_12(text)
        else:
            prepare_query_12(text)


@_no_data
@pytest.mark.parametrize("entry", EVAL_SELECT, ids=lambda e: e.test_iri)
def test_eval_select(entry):
    query_text = entry.read(entry.query_file)
    expected = parse_srj(entry.read(entry.result_file))

    starlayergraph_graph = _new_graph(entry)
    if entry.data_file:
        starlayergraph_graph.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    from starsparql.serialize12 import translate_algebra_12

    regenerated_text = translate_algebra_12(reconstructed)

    # {k: v for ... if v is not None}, not a bare dict(row): an unbound
    # variable (including one explicitly bound to UNDEF via a VALUES row -
    # SPARQL's own result-set semantics make the two indistinguishable, per
    # the SPARQL Query Results JSON format simply omitting the key either
    # way) comes back from starlayergraph as key -> None, not an absent key -
    # confirmed a real, reproducible false mismatch via the W3C
    # triple-on-undefs fixture before this filtering existed: `expected`
    # (built by parse_srj from the official .srj file) naturally has no
    # key at all for an unbound variable, so an unfiltered `actual` never
    # compared equal even when the *bound* variables agreed perfectly.
    # Same filtering starlayergraph's own
    # tests/w3c_sparql12/test_w3c_sparql12_eval.py::test_eval_select_original_query
    # already applies, for the identical reason.
    actual = [{k: v for k, v in dict(row).items() if v is not None} for row in starlayergraph_graph.query(regenerated_text).bindings]
    # bindings_match, not exact canon_bindings equality: a BNode's (or
    # starlayergraph's rr:N-skolemized anonymous reifier's) *label* is never
    # semantically meaningful, only a consistent relabeling is - see
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

    starlayergraph_graph = _new_graph(entry)
    if entry.data_file:
        starlayergraph_graph.parse(data=entry.read(entry.data_file), format=_data_format(entry))

    prepared = prepare_query_12(query_text)
    graph, root = query_to_rdf(prepared)
    reconstructed = rdf_to_query(graph, root)
    from starsparql.serialize12 import translate_algebra_12

    regenerated_text = translate_algebra_12(reconstructed)

    actual_graph = starlayergraph_graph.query(regenerated_text).graph
    assert to_isomorphic(skolemize_graph(actual_graph)) == to_isomorphic(skolemize_graph(expected_graph))


@_no_data
@pytest.mark.parametrize("entry", EVAL_UPDATE, ids=lambda e: e.test_iri)
def test_eval_update_not_yet_supported(entry):
    pytest.skip(
        "Update serialization back to SPARQL text is not implemented by this "
        "project for 1.1 or 1.2 - see test_phase2_update.py's docstring and "
        "CLAUDE.md's Not-started section."
    )
