"""Phase 1 of docs/w3c-shacl12-test-suite-plan.md: run every sht:Validate
entry from the vendored W3C SHACL 1.2 suite (tests/core/ and tests/sparql/)
against StarShaclValidator.validate().
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlayergraph.graph.starlayer_graph import StarLayerGraph

pyshacl = pytest.importorskip("pyshacl")

from starshacl import StarShaclValidator

from .closure import node_closure
from .comparison import conforms_of, find_report_node, result_multiset
from .ids import portable_id
from .known_failures import KNOWN_FAILURES
from .manifest import (
    ManifestEntry,
    clone_graph,
    iter_manifest_entries,
    load_document,
    uri_to_path,
)
from .namespaces import MF, SH, SHT

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "shacl12-test-suite"
TOP_MANIFEST = VENDOR_ROOT / "tests" / "manifest.ttl"


def _load_validate_entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    # parse_error entries (entry_type is None) are deliberately excluded here
    # - they're surfaced by test_w3c_parse_health.py instead, since we can't
    # know what type an unparseable file's entry would have been.
    return [entry for entry in iter_manifest_entries(TOP_MANIFEST) if entry.entry_type == SHT.Validate]


_ENTRIES = _load_validate_entries()


def pytest_generate_tests(metafunc):
    if "entry" not in metafunc.fixturenames:
        return
    if _ENTRIES:
        metafunc.parametrize("entry", _ENTRIES, ids=[portable_id(e, VENDOR_ROOT) for e in _ENTRIES])
    else:
        metafunc.parametrize(
            "entry",
            [pytest.param(None, marks=pytest.mark.skip(reason="vendored W3C suite not found - run scripts/sync_w3c_shacl12_suite.py"))],
            ids=["no-vendored-suite"],
        )


def _resolve_action_graph(entry: ManifestEntry, predicate) -> StarLayerGraph:
    action = next(entry.graph.objects(entry.iri, MF.action))
    target_iri = next(entry.graph.objects(action, predicate))
    # Fresh copies, not the cached document objects directly - see
    # clone_graph()'s docstring for why (shared self-contained fixtures,
    # cache reused across the whole test session).
    return clone_graph(load_document(uri_to_path(target_iri)))


def _conformance_disallows_kwargs(expected_graph: StarLayerGraph, expected_report_node) -> dict:
    """Translate mf:result's sh:conformanceDisallows into validate() kwargs.

    sh:conformanceDisallows X means "only a result at severity X blocks
    sh:conforms" - i.e. every *other* severity should be allowed. pySHACL's
    own validate() only exposes two coarse flags for this
    (allow_warnings=True allows both sh:Warning and sh:Info; allow_infos=True
    allows only sh:Info), so the mapping is necessarily approximate for any
    conformanceDisallows value other than sh:Violation/sh:Warning - not
    encountered in the vendored suite as of this writing (only
    conformance-disallows-001 uses sh:conformanceDisallows sh:Violation),
    so a finer-grained mechanism hasn't been needed.
    """
    disallows = next(expected_graph.objects(expected_report_node, SH.conformanceDisallows), None)
    if disallows == SH.Violation:
        return {"allow_warnings": True}
    if disallows == SH.Warning:
        return {"allow_infos": True}
    return {}


def test_w3c_validate(entry: ManifestEntry) -> None:
    entry_key = portable_id(entry, VENDOR_ROOT)
    if entry_key in KNOWN_FAILURES:
        pytest.xfail(KNOWN_FAILURES[entry_key])

    data_graph = _resolve_action_graph(entry, SHT.dataGraph)
    shapes_graph = _resolve_action_graph(entry, SHT.shapesGraph)
    expected = next(entry.graph.objects(entry.iri, MF.result))

    validator = StarShaclValidator()

    # advanced=True enables pySHACL's SHACL-AF ("advanced features") mode -
    # sh:expression/sh:rule and friends are otherwise silently never invoked
    # at all (conforms vacuously, regardless of the expression's actual
    # content) under the default "validation" profile's advanced=False.
    # Confirmed live this was mis-diagnosing at least one real Phase 1
    # finding as "sh:expression not implemented" when the feature actually
    # works correctly once configured the way real usage
    # (tests/integration/test_shnex_node_expressions.py) already does.
    if expected == SHT.Failure:
        with pytest.raises(Exception):
            validator.validate(data_graph=data_graph, shacl_graph=shapes_graph, meta_shacl=False, advanced=True)
        return

    expected_graph = node_closure(entry.graph, expected)
    expected_report_node = find_report_node(expected_graph)
    extra_kwargs = _conformance_disallows_kwargs(expected_graph, expected_report_node)

    result = validator.validate(
        data_graph=data_graph, shacl_graph=shapes_graph, meta_shacl=False, advanced=True, **extra_kwargs
    )

    actual_report_node = find_report_node(result.report_graph)

    assert result.conforms == conforms_of(expected_graph, expected_report_node), (
        f"conforms mismatch: actual={result.conforms}, expected report:\n{expected_graph.serialize(format='turtle')}\n"
        f"actual report:\n{result.report_graph.serialize(format='turtle')}"
    )
    assert result_multiset(result.report_graph, actual_report_node) == result_multiset(
        expected_graph, expected_report_node
    ), (
        f"result set mismatch\nexpected report:\n{expected_graph.serialize(format='turtle')}\n"
        f"actual report:\n{result.report_graph.serialize(format='turtle')}"
    )
