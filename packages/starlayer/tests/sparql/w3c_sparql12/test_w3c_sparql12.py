"""W3C SPARQL 1.2 syntax tests, run against StarLayer's own SPARQL 1.2 parser (``parse_sparql`` / ``parse_sparql_update``).

``tests/w3c_sparql12/download_w3c_sparql12_tests.py`` populates ``data/``. Two test shapes:

1. ``PositiveSyntaxTest`` / ``NegativeSyntaxTest`` (and their ``*Update*`` counterparts): parse only. The parser accepts every
   construct the suite considers valid 1.2 syntax and rejects every construct it considers invalid.
2. ``QueryEvaluationTest`` and ``UpdateEvaluationTest`` fixtures are run elsewhere, on the original query text:
   ``tests/graph/w3c_sparql12/`` (the evaluation tests) and ``tests/sparql/sqe_coverage/`` (through ``sqe:``). The tests that
   once ran the *regenerated* text of an rdflib algebra round trip here tested the deleted salg encoder and were removed.
"""

from __future__ import annotations

import pytest
from starlayer.graph.oxgraph import StarLayerDataset, StarLayerGraph
from starlayer.graph.oxgraph.sparql_text import strip_version_directive
from starlayer.sparql.parse_sparql import parse_sparql as prepare_query_12
from starlayer.sparql.parse_sparql import parse_sparql_update as prepare_update_12
from tests.sparql.w3c_sparql12.harness import load_index

pytestmark = pytest.mark.w3c_sparql12

ALL_ENTRIES = load_index()

SYNTAX_POSITIVE = [
    e for e in ALL_ENTRIES if e.test_type in ("PositiveSyntaxTest", "PositiveUpdateSyntaxTest")
]
SYNTAX_NEGATIVE = [
    e for e in ALL_ENTRIES if e.test_type in ("NegativeSyntaxTest", "NegativeUpdateSyntaxTest")
]
_no_data = pytest.mark.skipif(not ALL_ENTRIES, reason="W3C SPARQL 1.2 test data not fetched - run download_w3c_sparql12_tests.py")


def _is_update(entry) -> bool:
    return "Update" in entry.test_type


# (Seven PositiveSyntaxTest fixtures put a triple term in subject position, which RDF 1.2 Concepts never permits
# (docs/sparql/w3c-sparql12-test-suite-issues.md Issue 1); the rdflib-based grammar rejected them and they were strict xfails.
# StarLayer's own parser follows the suite and accepts them, and rejects the two codepoint-escape fixtures
# rdflib's grammar let through, so no fixture is marked now. A triple term in subject position is still refused where it
# matters: by an SRL rule set's well-formedness check and by the SHACL engine's query check.)


@_no_data
@pytest.mark.parametrize("entry", SYNTAX_POSITIVE, ids=lambda e: e.test_iri)
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
@pytest.mark.parametrize("entry", SYNTAX_NEGATIVE, ids=lambda e: e.test_iri)
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


# Helpers the sqe coverage tests import (they run the evaluation fixtures).
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



def _stored_form(term):
    """The term as Oxigraph holds it. Owner decision O1: Oxigraph's canonical lexical forms are accepted, so a result file that
    spells a number the long way (op-2: ``"123.0"^^xsd:decimal``) is compared as the store returns it (``"123"``)."""
    from rdflib import Literal as RdfLiteral
    from rdflib import URIRef
    from starlayer.graph.model.triple import TripleTerm

    if isinstance(term, TripleTerm):
        return TripleTerm(_stored_form(term.subject), _stored_form(term.predicate), _stored_form(term.object))
    xsd = "http://www.w3.org/2001/XMLSchema#"
    if isinstance(term, RdfLiteral) and str(term.datatype) in (xsd + "decimal", xsd + "double"):
        # the Turtle numeric token of the same value, parsed the way the test data is
        token = str(term) if str(term.datatype) == xsd + "decimal" else f"{term}e0"
        graph = StarLayerGraph()
        graph.parse(data=f"<urn:s> <urn:p> {token} .", format="turtle")
        stored = next(iter(graph.triples((None, None, None))))[2]
        return RdfLiteral(stored.value, datatype=URIRef(str(term.datatype)), normalize=False)
    return term


