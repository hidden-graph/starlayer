"""W3C SPARQL 1.2 test suite - execution correctness, run against StarLayerGraph / StarLayerDataset directly.

The *original* W3C query text is executed exactly as published, so a failure here is a defect of the engine behind
``StarLayerGraph.query()`` and nothing that starlayer.sparql's own SPARQL-1.2-to-algebra-to-text pipeline adds.

Two test shapes:
1. QueryEvaluationTest, SELECT / ASK (``.srj`` expected results): bindings are compared as a set, up to renaming of blank
   nodes. ``.srx``-only tests (no ``.srj``) are not collected: the harness's results parser has no XML counterpart.
2. QueryEvaluationTest, CONSTRUCT (``.ttl`` expected results): the two graphs are compared up to blank-node isomorphism
   (``starlayer.graph.isomorphic``; triple terms are handled natively).

Literals are compared in the form Oxigraph stores them (canonical lexical form, owner decision O1): the expected
``"123.0"^^xsd:decimal`` of op-2 is ``"123"`` (see the harness).

UpdateEvaluationTest is collected (via the shared index) but not exercised here.
"""

from __future__ import annotations

import json

import pytest
from starlayer.graph import isomorphic
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph

from .harness import bindings_match, data_format, load_index, parse_srj

_DATASET_FORMATS = {"trig12", "nq12"}


def _new_graph(entry) -> StarLayerGraph | StarLayerDataset:
    """A fixture whose data defines named graphs (TriG / N-Quads) needs a dataset; the rest an ``StarLayerGraph``."""
    if entry.data_file and data_format(entry) in _DATASET_FORMATS:
        return StarLayerDataset()
    return StarLayerGraph()


ALL_ENTRIES = load_index()

EVAL_SELECT = [e for e in ALL_ENTRIES if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".srj")]
EVAL_CONSTRUCT = [e for e in ALL_ENTRIES if e.test_type == "QueryEvaluationTest" and e.result_file.endswith(".ttl")]

_no_data = pytest.mark.skipif(
    not ALL_ENTRIES,
    reason="W3C SPARQL 1.2 test data not fetched - run download_w3c_sparql12_tests.py",
)


@_no_data
@pytest.mark.parametrize("entry", EVAL_SELECT, ids=lambda e: e.test_iri)
def test_eval_select_original_query(entry):
    query_text = entry.read(entry.query_file)
    result_text = entry.read(entry.result_file)
    # "QueryEvaluationTest" + ".srj" covers both SELECT and ASK
    is_ask = "boolean" in json.loads(result_text)

    g = _new_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    if is_ask:
        assert g.query(query_text).askAnswer == json.loads(result_text)["boolean"]
        return

    expected = parse_srj(result_text)
    actual = [{k: v for k, v in dict(row).items() if v is not None} for row in g.query(query_text).bindings]
    assert bindings_match(actual, expected)


@_no_data
@pytest.mark.parametrize("entry", EVAL_CONSTRUCT, ids=lambda e: e.test_iri)
def test_eval_construct_original_query(entry):
    query_text = entry.read(entry.query_file)
    expected_graph = StarLayerGraph()
    expected_graph.parse(data=entry.read(entry.result_file), format="turtle12")

    g = _new_graph(entry)
    if entry.data_file:
        g.parse(data=entry.read(entry.data_file), format=data_format(entry))

    assert isomorphic(g.query(query_text).graph, expected_graph)
