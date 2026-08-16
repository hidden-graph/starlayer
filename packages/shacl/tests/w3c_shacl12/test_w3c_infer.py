"""Phase 3 of docs/w3c-shacl12-test-suite-plan.md: run every sht:Infer entry
from the vendored W3C SHACL 1.2 suite (tests/sparql/rules/) against
StarShaclValidator.apply_rules().

Format (per docs/w3c-shacl12-test-suite-plan.md's "Test-format notes", derived
from the vendored tests/sparql/rules/*.ttl fixtures themselves): mf:action
carries sht:dataGraph/sht:shapesGraph (both typically the fixture's own
document, resolved the same way Phase 1's sht:Validate does). mf:result is
usually an rdf:List whose members are themselves 3-element rdf:Lists ``(
subject predicate object )`` - the set of triples inference is expected to
*add* to the data graph (empty list for a deliberately-inert case, e.g. a
sh:deactivated rule). Compared as a set, not order-sensitive - nothing in the
format or the plan doc's own description implies inferred-triple ordering is
meaningful, unlike sht:EvalNodeExpr's node lists.

A second, less common mf:result form (found 2026-08-15, ``sparql/rules/
layers-example.ttl``) points at a *separate results-graph file* instead of an
inline rdf:List (``mf:result <layers-example-results.ttl>``) - the expected
content there is every triple of that referenced graph, not a delta-list.
This still works as an "added" comparison rather than a full-graph one: this
particular fixture's own data graph starts with no ``:x*`` triples at all (its
``sht:dataGraph <>`` self-reference only contains the rule *definitions* - the
`:x*` data is entirely rule-CONSTRUCTed, from a `sh:runOnce` rule with an
empty WHERE clause), so every triple in the referenced results file is
genuinely rule-added, not pre-existing - the same "added == expected" set
comparison already used for the inline-list form applies unchanged once the
right set is loaded. ``_expected_triples`` below detects which form a given
fixture uses (an rdf:List vs. a plain IRI/file reference) and loads
accordingly.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlayergraph.graph.starlayer_graph import StarLayerGraph

pyshacl = pytest.importorskip("pyshacl")

from starshacl import StarShaclValidator

from .ids import portable_id
from .known_failures import KNOWN_FAILURES
from .manifest import (
    ManifestEntry,
    clone_graph,
    iter_manifest_entries,
    load_document,
    uri_to_path,
)
from .namespaces import MF, SHT

VENDOR_ROOT = Path(__file__).resolve().parents[1] / "vendor" / "shacl12-test-suite"
TOP_MANIFEST = VENDOR_ROOT / "tests" / "manifest.ttl"


def _load_infer_entries() -> list[ManifestEntry]:
    if not TOP_MANIFEST.exists():
        return []
    return [entry for entry in iter_manifest_entries(TOP_MANIFEST) if entry.entry_type == SHT.Infer]


_ENTRIES = _load_infer_entries()


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


def _expected_triples(entry: ManifestEntry) -> set[tuple]:
    from rdflib.namespace import RDF

    result_list = next(entry.graph.objects(entry.iri, MF.result))

    is_rdf_list = result_list == RDF.nil or next(entry.graph.objects(result_list, RDF.first), None) is not None
    if not is_rdf_list:
        # A plain IRI pointing at a separate results-graph file - see this
        # module's own docstring for why "every triple of that file" is the
        # right expected set here, not a different comparison strategy.
        results_graph = load_document(uri_to_path(result_list))
        return set(results_graph.triples((None, None, None)))

    triples = set()
    for triple_list in entry.graph.items(result_list):
        s, p, o = entry.graph.items(triple_list)
        triples.add((s, p, o))
    return triples


def test_w3c_infer(entry: ManifestEntry) -> None:
    entry_key = portable_id(entry, VENDOR_ROOT)
    if entry_key in KNOWN_FAILURES:
        pytest.xfail(KNOWN_FAILURES[entry_key])

    data_graph = _resolve_action_graph(entry, SHT.dataGraph)
    shapes_graph = _resolve_action_graph(entry, SHT.shapesGraph)
    expected = _expected_triples(entry)

    before = set(data_graph.triples((None, None, None)))

    validator = StarShaclValidator()
    result = validator.apply_rules(data_graph=data_graph, shacl_graph=shapes_graph, meta_shacl=False)

    after = set(result.data_graph.triples((None, None, None)))
    added = after - before

    assert added == expected, (
        f"inferred-triple set mismatch\nexpected added: {expected}\nactual added: {added}"
    )
