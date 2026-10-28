"""The curated layer (``curated/*.ttl``) and how it is loaded next to the generated code graph."""

from __future__ import annotations

import pytest
import starlayer.codekg as codekg
from rdflib import RDF, Literal, URIRef
from rdflib.namespace import DCTERMS
from starlayer.codekg import (
    CODEKG_NS,
    CURATED_DIR,
    CURATED_GRAPH_IRI,
    get_codekg_dataset,
)


def test_the_curated_graph_is_left_out_unless_asked_for(monkeypatch, tmp_path):
    """The extractor reads and rewrites the dataset it gets, so the default must never carry curated triples."""
    monkeypatch.setattr(codekg, "TESTSKG_TRIG_PATH", tmp_path / "absent-tests.trig")
    monkeypatch.setattr(codekg, "CODEKG_TRIG_PATH", tmp_path / "absent.trig")  # skip the 15 s parse of the real file
    assert len(get_codekg_dataset().get_context(CURATED_GRAPH_IRI)) == 0
    assert len(get_codekg_dataset(include_curated=True).get_context(CURATED_GRAPH_IRI)) > 0


def test_the_curated_graph_holds_every_curated_file(monkeypatch, tmp_path):
    monkeypatch.setattr(codekg, "TESTSKG_TRIG_PATH", tmp_path / "absent-tests.trig")
    monkeypatch.setattr(codekg, "CODEKG_TRIG_PATH", tmp_path / "absent.trig")  # the curated files do not need the 15 s parse
    curated = get_codekg_dataset(include_curated=True).get_context(CURATED_GRAPH_IRI)
    assert next(curated.subjects(RDF.type, CODEKG_NS.Capability), None) is not None
    assert next(curated.subjects(RDF.type, CODEKG_NS.NamedQuery), None) is not None
    assert sorted(p.name for p in CURATED_DIR.glob("*.ttl")) == ["functionality.ttl", "notebook-links.ttl", "query-library.ttl", "upstream-issues.ttl"]


@pytest.mark.deferred
def test_every_implementing_symbol_of_a_capability_exists_in_the_code_graph(codekg_dataset):
    dataset = codekg_dataset
    """``slkg:implementedByIdentifier`` names a dotted path; each must be a ``dcterms:identifier`` in ``codekg.trig``."""
    curated = dataset.get_context(CURATED_GRAPH_IRI)
    cited = {str(o) for o in curated.objects(None, CODEKG_NS.implementedByIdentifier)}
    known = {str(o) for ctx in dataset.contexts() if ctx.identifier != CURATED_GRAPH_IRI for o in ctx.objects(None, DCTERMS.identifier)}
    assert len(cited) > 30
    assert not sorted(cited - known), f"capabilities cite symbols the code KG does not have (rebuild it, or fix the name): {sorted(cited - known)}"


FUNCTIONALITY_TTL = CURATED_DIR / "functionality.ttl"
SHAPES_TTL = CURATED_DIR.parent / "functionality-shapes.ttl"


def _conforms(graph) -> bool:
    import starlayer.shacl
    from rdflib import Graph

    return starlayer.shacl.validate(graph, shacl_graph=Graph().parse(SHAPES_TTL, format="turtle")).conforms


def test_the_capability_list_conforms_to_its_shapes():
    from rdflib import Graph

    assert _conforms(Graph().parse(FUNCTIONALITY_TTL, format="turtle"))


@pytest.mark.parametrize(
    "corrupt",
    [
        lambda g, c: g.remove((c, CODEKG_NS.appRole, None)),
        lambda g, c: g.set((c, CODEKG_NS.appRole, Literal("make-coffee"))),
        lambda g, c: g.set((c, CODEKG_NS.hasStatus, Literal("done"))),
        lambda g, c: g.remove((c, CODEKG_NS.inCapabilityArea, None)),
        lambda g, c: g.add((c, CODEKG_NS.implementsSpecification, URIRef("http://example.org/not-a-w3c-spec"))),
    ],
    ids=["no-role", "unknown-role", "unknown-status", "no-area", "spec-not-w3c"],
)
def test_the_capability_shapes_notice_a_damaged_capability(corrupt):
    from rdflib import Graph

    graph = Graph().parse(FUNCTIONALITY_TTL, format="turtle")
    capability = next(graph.subjects(RDF.type, CODEKG_NS.Capability))
    assert _conforms(graph)
    corrupt(graph, capability)
    assert not _conforms(graph)


def test_every_app_role_is_used():
    from rdflib import Graph

    used = {str(o) for o in Graph().parse(FUNCTIONALITY_TTL, format="turtle").objects(None, CODEKG_NS.appRole)}
    assert used == {"storage", "interchange", "query", "validate", "infer", "ui-generate", "reference"}


@pytest.mark.deferred
def test_every_notebook_link_names_symbols_the_code_graph_has_and_demonstratedby_is_derived(codekg_dataset):
    dataset = codekg_dataset
    curated = dataset.get_context(CURATED_GRAPH_IRI)
    cited = {str(o) for o in curated.objects(None, CODEKG_NS.demonstratesIdentifier)}
    known = {str(o) for ctx in dataset.contexts() if ctx.identifier != CURATED_GRAPH_IRI for o in ctx.objects(None, DCTERMS.identifier)}
    assert len(cited) >= 20
    assert not sorted(cited - known), f"notebook links cite symbols the code KG does not have: {sorted(cited - known)}"
    derived = list(curated.subject_objects(CODEKG_NS.demonstratedBy))
    assert len(derived) >= len(cited)
    assert all((example, RDF.type, CODEKG_NS.NotebookExample) in curated for _entity, example in derived)


def test_capabilities_name_the_specifications_they_implement():
    from rdflib import Graph

    graph = Graph().parse(FUNCTIONALITY_TTL, format="turtle")
    specs = {str(o) for o in graph.objects(None, CODEKG_NS.implementsSpecification)}
    assert len(specs) >= 12
    assert "https://www.w3.org/TR/shacl12-core" in specs and "https://www.w3.org/TR/sparql12-update" in specs
    assert all(s.startswith("https://www.w3.org/TR/") for s in specs)
