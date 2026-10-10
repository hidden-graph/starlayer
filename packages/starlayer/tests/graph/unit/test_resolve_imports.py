"""
tests/unit/test_resolve_imports.py

Coverage for StarLayerGraph.owl_imports()/.resolve_imports() and the
standalone can_resolve_import() - generalizes validator.py's own
_resolve_shapes_graph_imports() (SHACL-specific, shacl_graph only) into a
plain graph capability any caller can use, with the same three-way mode=
contract infer() already established ("full"/"delta"/"in-place").

Retrieval policy is never this project's own decision - every test here
supplies its own explicit loader (a plain dict lookup), never a real
network call, matching the "no default loader" design: resolve_imports()
itself doesn't dictate how an IRI becomes a graph, only how to use the
result once a loader hands one back.
"""

from rdflib import RDF, RDFS, Literal
from rdflib.namespace import OWL

import pytest

from starlayer.graph import Namespace, StarLayerGraph, can_resolve_import

EX = Namespace("http://example.org/")


class TestOwlImports:
    def test_returns_direct_import_objects(self) -> None:
        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))
        assert g.owl_imports() == (EX.other,)

    def test_empty_when_no_imports_declared(self) -> None:
        g = StarLayerGraph()
        g.add((EX.alice, EX.knows, EX.bob))
        assert g.owl_imports() == ()

    def test_deduplicates_preserving_first_seen_order(self) -> None:
        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.a))
        g.add((EX.this, OWL.imports, EX.b))
        g.add((EX.other, OWL.imports, EX.a))  # same target, different subject
        assert g.owl_imports() == (EX.a, EX.b)

    def test_does_not_resolve_anything_itself(self) -> None:
        """owl_imports() is a pure read - it never calls a loader, never
        fetches, never merges. Confirmed by never supplying one at all."""
        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))
        # No TypeError about a missing loader= - owl_imports() takes none.
        assert g.owl_imports() == (EX.other,)


class TestCanResolveImport:
    def test_true_when_loader_returns_a_graph(self) -> None:
        other = StarLayerGraph()
        assert can_resolve_import(EX.other, loader=lambda iri: other if iri == EX.other else None) is True

    def test_false_when_loader_returns_none(self) -> None:
        assert can_resolve_import(EX.unknown, loader=lambda iri: None) is False

    def test_calls_the_loader_exactly_once(self) -> None:
        calls = []

        def loader(iri):
            calls.append(iri)
            return StarLayerGraph()

        can_resolve_import(EX.other, loader=loader)
        assert calls == [EX.other]


class TestResolveImportsFullMode:
    def _setup(self):
        imported = StarLayerGraph()
        imported.add((EX.Dog, RDFS.subClassOf, EX.Animal))

        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))
        g.add((EX.fido, RDF.type, EX.Dog))
        return g, imported

    def test_full_mode_contains_self_plus_imported(self) -> None:
        g, imported = self._setup()
        result = g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="full")

        assert (EX.fido, RDF.type, EX.Dog) in result
        assert (EX.Dog, RDFS.subClassOf, EX.Animal) in result

    def test_full_mode_never_mutates_self(self) -> None:
        g, imported = self._setup()
        before = set(g)
        g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="full")
        assert set(g) == before

    def test_full_mode_never_mutates_the_imported_graph(self) -> None:
        g, imported = self._setup()
        before = set(imported)
        g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="full")
        assert set(imported) == before

    def test_default_mode_is_full(self) -> None:
        g, imported = self._setup()
        default_result = g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None)
        explicit_result = g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="full")
        assert set(default_result) == set(explicit_result)

    def test_unresolvable_import_is_skipped_not_an_error(self) -> None:
        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.unreachable))
        g.add((EX.fido, RDF.type, EX.Dog))

        result = g.resolve_imports(loader=lambda iri: None, mode="full")

        assert set(result) == set(g)


class TestResolveImportsDeltaMode:
    def test_delta_contains_only_the_newly_imported_triples(self) -> None:
        imported = StarLayerGraph()
        imported.add((EX.Dog, RDFS.subClassOf, EX.Animal))

        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))
        g.add((EX.fido, RDF.type, EX.Dog))

        delta = g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="delta")

        assert set(delta) == {(EX.Dog, RDFS.subClassOf, EX.Animal)}

    def test_delta_excludes_anything_self_already_had(self) -> None:
        """A true set difference against self, matching infer()'s own
        delta semantics - if the imported graph happens to also assert
        something self already has, that's not "new"."""
        imported = StarLayerGraph()
        imported.add((EX.fido, RDF.type, EX.Dog))  # already in g too
        imported.add((EX.Dog, RDFS.subClassOf, EX.Animal))  # genuinely new

        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))
        g.add((EX.fido, RDF.type, EX.Dog))

        delta = g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="delta")

        assert set(delta) == {(EX.Dog, RDFS.subClassOf, EX.Animal)}


class TestResolveImportsInPlaceMode:
    def test_in_place_mutates_and_returns_self(self) -> None:
        imported = StarLayerGraph()
        imported.add((EX.Dog, RDFS.subClassOf, EX.Animal))

        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))

        result = g.resolve_imports(loader=lambda iri: imported if iri == EX.other else None, mode="in-place")

        assert result is g
        assert (EX.Dog, RDFS.subClassOf, EX.Animal) in g

    def test_in_place_rejects_target_graph(self) -> None:
        g = StarLayerGraph()
        with pytest.raises(ValueError, match="target_graph"):
            g.resolve_imports(loader=lambda iri: None, mode="in-place", target_graph=StarLayerGraph())


class TestResolveImportsValidation:
    def test_unknown_mode_raises(self) -> None:
        g = StarLayerGraph()
        with pytest.raises(ValueError, match="mode must be one of"):
            g.resolve_imports(loader=lambda iri: None, mode="bogus")


class TestResolveImportsTransitiveClosure:
    def test_follows_a_multi_hop_chain(self) -> None:
        """A -> B -> C: resolving A's own imports must also pick up
        whatever B itself imports, not just B's own direct content."""
        c = StarLayerGraph()
        c.add((EX.cFact, RDF.type, EX.CThing))

        b = StarLayerGraph()
        b.add((EX.b, OWL.imports, EX.c))
        b.add((EX.bFact, RDF.type, EX.BThing))

        registry = {EX.b: b, EX.c: c}

        a = StarLayerGraph()
        a.add((EX.a, OWL.imports, EX.b))

        result = a.resolve_imports(loader=lambda iri: registry.get(iri), mode="full")

        assert (EX.bFact, RDF.type, EX.BThing) in result
        assert (EX.cFact, RDF.type, EX.CThing) in result

    def test_import_cycle_does_not_hang_or_duplicate(self) -> None:
        """A -> B -> A: must terminate, and B's own content must still
        appear exactly once."""
        a = StarLayerGraph()
        a.add((EX.a, OWL.imports, EX.b))

        b = StarLayerGraph()
        b.add((EX.b, OWL.imports, EX.a))
        b.add((EX.bFact, RDF.type, EX.BThing))

        registry = {EX.a: a, EX.b: b}

        result = a.resolve_imports(loader=lambda iri: registry.get(iri), mode="full")

        assert (EX.bFact, RDF.type, EX.BThing) in result

    def test_versioned_import_reconverges_with_unversioned_import(self) -> None:
        """Mirrors _resolve_shapes_graph_imports()'s own
        ^owl:versionIRI?/owl:imports handling: a graph fetched under its
        own versionIRI is deduplicated against the same graph fetched
        under its base IRI, so importing both doesn't double-merge or
        double-chain further imports from it."""
        versioned_content = StarLayerGraph()
        versioned_content.add((EX.baseOntology, OWL.versionIRI, EX.versionedOntology))
        versioned_content.add((EX.baseOntology, OWL.imports, EX.furtherThing))
        versioned_content.add((EX.versionedFact, RDF.type, EX.Thing))

        further = StarLayerGraph()
        further.add((EX.furtherFact, RDF.type, EX.FurtherThing))

        registry = {EX.versionedOntology: versioned_content, EX.furtherThing: further}

        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.versionedOntology))

        result = g.resolve_imports(loader=lambda iri: registry.get(iri), mode="full")

        assert (EX.versionedFact, RDF.type, EX.Thing) in result
        # The chained import from the *base* IRI (not the version IRI)
        # must still be followed - this only works if canonical_id
        # resolution is correct.
        assert (EX.furtherFact, RDF.type, EX.FurtherThing) in result


class TestHasImportLocally:
    def test_true_when_the_iri_has_triples_in_this_graph(self) -> None:
        g = StarLayerGraph()
        g.add((EX.ModuleB, RDF.type, EX.ShapesGraph))
        assert g.has_import_locally(EX.ModuleB) is True

    def test_false_when_the_iri_has_no_triples_at_all(self) -> None:
        g = StarLayerGraph()
        g.add((EX.this, OWL.imports, EX.other))  # other appears only as an object
        assert g.has_import_locally(EX.other) is False


class TestResolveImportsSameGraphCoLocation:
    """The real gap this exists to close, found via direct user
    observation: owl:imports isn't only used for genuinely external
    references (ontology-style, needing a loader) - two shapes-graph
    "modules" that import each other are often just loaded together
    into one single graph, with nothing external to fetch at all.
    owl_imports() scans the whole graph regardless of subject, so
    without has_import_locally(), resolve_imports() would try to call a
    loader for an IRI that's already fully present right there."""

    def _co_located_graph(self) -> StarLayerGraph:
        g = StarLayerGraph()
        g.add((EX.ModuleA, OWL.imports, EX.ModuleB))
        g.add((EX.ModuleB, RDF.type, EX.ShapesGraph))
        g.add((EX.BFact, RDF.type, EX.BThing))
        return g

    def test_resolve_imports_never_calls_the_loader_for_a_locally_satisfied_import(self) -> None:
        g = self._co_located_graph()
        calls = []

        def loader(iri):
            calls.append(iri)
            return None

        result = g.resolve_imports(loader=loader, mode="full")

        assert calls == []
        assert set(result) == set(g)

    def test_resolve_imports_works_with_no_loader_at_all_when_everything_is_local(self) -> None:
        g = self._co_located_graph()
        result = g.resolve_imports(mode="full")  # loader omitted entirely
        assert set(result) == set(g)

    def test_a_locally_satisfied_modules_own_further_import_is_not_chased_either(self) -> None:
        """A -> B -> C, all three already co-located in one graph - B's
        own owl:imports C must not trigger a loader call either, since
        owl_imports()'s whole-graph scan already found C directly from
        self, and C is just as locally satisfied as B."""
        g = StarLayerGraph()
        g.add((EX.ModuleA, OWL.imports, EX.ModuleB))
        g.add((EX.ModuleB, OWL.imports, EX.ModuleC))
        g.add((EX.ModuleB, RDF.type, EX.ShapesGraph))
        g.add((EX.ModuleC, RDF.type, EX.ShapesGraph))
        g.add((EX.CFact, RDF.type, EX.CThing))

        calls = []

        def loader(iri):
            calls.append(iri)
            return None

        result = g.resolve_imports(loader=loader, mode="full")

        assert calls == []
        assert set(result) == set(g)

    def test_mixed_local_and_genuinely_external_imports(self) -> None:
        """One import is already co-located, the other is genuinely
        external and needs the loader - only the external one should
        ever reach it."""
        g = StarLayerGraph()
        g.add((EX.ModuleA, OWL.imports, EX.ModuleB))  # local
        g.add((EX.ModuleA, OWL.imports, EX.ExternalModule))  # genuinely external
        g.add((EX.ModuleB, RDF.type, EX.ShapesGraph))

        external = StarLayerGraph()
        external.add((EX.ExternalFact, RDF.type, EX.ExternalThing))

        calls = []

        def loader(iri):
            calls.append(iri)
            return external if iri == EX.ExternalModule else None

        result = g.resolve_imports(loader=loader, mode="full")

        assert calls == [EX.ExternalModule]
        assert (EX.ExternalFact, RDF.type, EX.ExternalThing) in result
