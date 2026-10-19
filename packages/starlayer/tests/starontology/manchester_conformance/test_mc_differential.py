"""Differential test: our parser against the OWL API 5.1.20 oracle goldens (P in the plan's P/T/R/O/V/N).

For each corpus case with a golden: if the oracle accepted it, ``parse_manchester`` must accept it and
produce an OWL-equivalent graph (unordered lists compared as sets); if the oracle rejected it, the
disposition is recorded in ``known_failures.ORACLE_REJECTS`` - the W3C Note may allow what OWL API does
not, so a rejection is a *finding to classify*, never a silent skip.
"""

from __future__ import annotations

import pytest
from starlayer.graph.parsers.errors import ManchesterSyntaxError

from .corpus import CASES
from .helpers import load_golden, owlapi_graph_from_golden, parse_to_graph, same_owl
from .known_failures import DIFFERENTIAL_FAILURES, ORACLE_DEVIATIONS, ORACLE_REJECTS

GOLDEN_CASES = [c for c in CASES if c.oracle]


@pytest.mark.manchester_conformance
@pytest.mark.parametrize("case", GOLDEN_CASES, ids=lambda c: c.id)
def test_matches_owlapi(case, request):
    golden = load_golden(case.id)
    assert golden is not None, f"no golden for {case.id}; run tools/regen_owlapi_goldens.py"

    if not golden["accepted"]:
        # Oracle rejects: our parser may legitimately accept (Note allows it) - must be classified.
        reason = ORACLE_REJECTS.get(case.id)
        assert reason is not None, (
            f"{case.id}: OWL API rejected this input ({golden.get('error_detail', '')[:120]}) and the "
            "case is not classified in known_failures.ORACLE_REJECTS"
        )
        return

    if case.id in ORACLE_DEVIATIONS:
        # The oracle's output differs from the W3C mapping here; the spec-derived expectation is checked
        # in test_mc_note_only.py instead of diffing against the oracle.
        from .test_mc_note_only import CHECKS

        assert case.id in CHECKS, f"{case.id} deviates from the oracle but has no spec-derived check"
        return

    if case.id in DIFFERENTIAL_FAILURES:
        request.applymarker(pytest.mark.xfail(reason=DIFFERENTIAL_FAILURES[case.id], strict=True, raises=(AssertionError, ManchesterSyntaxError)))

    ours = parse_to_graph(case.text)
    theirs = owlapi_graph_from_golden(golden)
    assert same_owl(ours, theirs), f"{case.id}: parse differs from OWL API"


@pytest.mark.manchester_conformance
def test_oracle_reject_registry_has_no_stale_entries():
    for case_id in ORACLE_REJECTS:
        golden = load_golden(case_id)
        assert golden is not None and not golden["accepted"], (
            f"{case_id} is in ORACLE_REJECTS but the oracle now accepts it (or the case is gone)"
        )
