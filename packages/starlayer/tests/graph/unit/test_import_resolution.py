"""The one import rule (maintainer decision 2026-11-26), through every path that resolves imports.

A graph that declares ``owl:imports`` must resolve them or raise ``ExecutionError`` kind ``"import"``. An import is satisfied when its
IRI is a subject of the resulting graph (already present, a built-in ontology of the registry, or loaded), or the ``owl:versionIRI`` of
a present ontology. A loader that returns ``None`` or a graph without the IRI is the error; a loader that raises is wrapped (``__cause__``);
``ignore_imports=True`` loads and checks nothing; the application reads ``unresolved_imports()`` and may call again.
"""

from __future__ import annotations

import pickle

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError, FormatError, ShapeCompileError
from starlayer.graph import StarLayerGraph, unresolved_imports
from starlayer.graph.imports import is_builtin_import, resolve_or_raise

EX = "http://example.org/"
OWL = "http://www.w3.org/2002/07/owl#"
RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
IMPORTS = ox.NamedNode(OWL + "imports")
VERSION_IRI = ox.NamedNode(OWL + "versionIRI")
ONTOLOGY = ox.NamedNode(OWL + "Ontology")


def n(local: str) -> ox.NamedNode:
    return ox.NamedNode(EX + local)


def ontology(iri: ox.NamedNode, *more: tuple) -> StarLayerGraph:
    g = StarLayerGraph()
    g.add((iri, RDF_TYPE, ONTOLOGY))
    for t in more:
        g.add(t)
    return g


def importing(*iris: ox.NamedNode) -> StarLayerGraph:
    g = StarLayerGraph()
    g.add((n("root"), RDF_TYPE, ONTOLOGY))
    for iri in iris:
        g.add((n("root"), IMPORTS, iri))
    return g


class Loader:
    def __init__(self, graphs: dict) -> None:
        self.graphs = graphs
        self.calls: list = []

    def __call__(self, iri):
        self.calls.append(iri)
        return self.graphs.get(iri)


# ---- satisfied --------------------------------------------------------------------------------------------------------


def test_an_import_that_is_a_subject_of_the_graph_is_satisfied_and_the_loader_is_not_asked():
    g = importing(n("a"))
    g.add((n("a"), RDF_TYPE, ONTOLOGY))
    loader = Loader({})
    assert set(g.resolve_imports(loader=loader)) == set(g)
    assert loader.calls == []
    assert g.resolve_imports() is not None  # no loader needed either
    assert unresolved_imports(g) == ()


def test_a_built_in_registry_import_is_satisfied_without_a_loader_and_adds_nothing():
    for iri in ("http://www.w3.org/ns/shacl#", "http://www.w3.org/ns/shacl-ui/", "http://www.w3.org/2004/02/skos/core"):
        g = importing(ox.NamedNode(iri))
        assert is_builtin_import(ox.NamedNode(iri))
        loader = Loader({})
        assert set(g.resolve_imports(loader=loader)) == set(g)
        assert loader.calls == []
        assert unresolved_imports(g) == ()


def test_an_import_satisfied_by_a_loader():
    g = importing(n("a"))
    loader = Loader({n("a"): ontology(n("a"), (n("x"), n("p"), n("y")))})
    result = g.resolve_imports(loader=loader)
    assert (n("x"), n("p"), n("y")) in result
    assert loader.calls == [n("a")]


def test_a_version_iri_of_a_present_ontology_satisfies_the_import_of_that_version():
    g = importing(n("v2"))
    loader = Loader({n("v2"): ontology(n("base"), (n("base"), VERSION_IRI, n("v2")))})
    assert g.resolve_imports(loader=loader) is not None
    resolved = g.resolve_imports(loader=loader)
    assert unresolved_imports(resolved) == ()  # the merged graph holds the version declaration


# ---- unresolved -------------------------------------------------------------------------------------------------------


def test_no_loader_is_an_error_naming_the_iri():
    g = importing(n("a"))
    with pytest.raises(ExecutionError, match="owl:imports <http://example.org/a>") as caught:
        g.resolve_imports()
    error = caught.value
    assert error.kind == "import"
    assert error.context == "owl:imports <http://example.org/a>"
    assert error.unresolved == (n("a"),)


def test_a_loader_that_returns_none_is_the_error_not_a_skip():
    g = importing(n("a"))
    with pytest.raises(ExecutionError) as caught:
        g.resolve_imports(loader=lambda iri: None)
    assert caught.value.kind == "import" and caught.value.unresolved == (n("a"),)


def test_a_loader_that_returns_a_graph_without_the_iri_as_a_subject_is_the_error():
    g = importing(n("a"))
    other = StarLayerGraph()
    other.add((n("x"), n("p"), n("y")))
    with pytest.raises(ExecutionError) as caught:
        g.resolve_imports(loader=lambda iri: other)
    assert caught.value.unresolved == (n("a"),)
    assert unresolved_imports(g) == (n("a"),)  # the helper says the same without loading anything


def test_two_imports_one_missing_names_only_the_missing_one():
    g = importing(n("a"), n("b"))
    loader = Loader({n("a"): ontology(n("a"))})
    with pytest.raises(ExecutionError) as caught:
        g.resolve_imports(loader=loader)
    assert caught.value.unresolved == (n("b"),)
    assert "http://example.org/b" in str(caught.value) and "http://example.org/a>" not in str(caught.value)


def test_several_missing_imports_are_all_listed_in_the_message_and_on_the_error():
    g = importing(n("a"), n("b"))
    with pytest.raises(ExecutionError) as caught:
        g.resolve_imports()
    assert caught.value.unresolved == (n("a"), n("b"))
    assert "<http://example.org/a>" in str(caught.value) and "<http://example.org/b>" in str(caught.value)


def test_an_import_found_by_an_imported_graph_that_is_itself_missing_is_reported():
    g = importing(n("a"))
    loader = Loader({n("a"): ontology(n("a"), (n("a"), IMPORTS, n("deeper")))})
    with pytest.raises(ExecutionError) as caught:
        g.resolve_imports(loader=loader)
    assert caught.value.unresolved == (n("deeper"),)


def test_the_error_is_picklable_with_its_unresolved_iris():
    with pytest.raises(ExecutionError) as caught:
        importing(n("a")).resolve_imports()
    again = pickle.loads(pickle.dumps(caught.value))
    assert (again.kind, again.context, again.unresolved) == ("import", caught.value.context, (n("a"),))
    assert str(again) == str(caught.value)


def test_unresolved_is_empty_on_every_other_error():
    assert ExecutionError("x", kind="limit").unresolved == ()


# ---- the loader raises ------------------------------------------------------------------------------------------------


def test_a_loader_that_raises_is_wrapped_with_the_original_as_cause():
    def broken(iri):
        raise OSError("no such file")

    with pytest.raises(ExecutionError, match="no such file") as caught:
        importing(n("a")).resolve_imports(loader=broken)
    assert caught.value.kind == "import"
    assert caught.value.context == "owl:imports <http://example.org/a>"
    assert isinstance(caught.value.__cause__, OSError)
    assert caught.value.unresolved == (n("a"),)


# ---- ignore_imports ---------------------------------------------------------------------------------------------------


def test_ignore_imports_loads_nothing_and_checks_nothing():
    g = importing(n("a"))
    loader = Loader({})
    result = g.resolve_imports(loader=loader, ignore_imports=True)
    assert set(result) == set(g) and loader.calls == []
    assert g.resolve_imports(ignore_imports=True) is not None
    assert set(g.resolve_imports(mode="delta", ignore_imports=True)) == set()


# ---- the application calls again --------------------------------------------------------------------------------------


def test_the_application_reads_unresolved_imports_and_calls_again_with_a_loader_that_knows_more():
    g = importing(n("a"), n("b"))
    first = Loader({n("a"): ontology(n("a"))})
    with pytest.raises(ExecutionError) as caught:
        g.resolve_imports(loader=first)
    assert caught.value.unresolved == (n("b"),)
    assert unresolved_imports(g) == (n("a"), n("b"))  # nothing was loaded into g itself
    second = Loader({n("a"): ontology(n("a")), n("b"): ontology(n("b"), (n("b"), n("p"), n("q")))})
    result = g.resolve_imports(loader=second)
    assert (n("b"), n("p"), n("q")) in result
    assert unresolved_imports(result) == ()


def test_a_graph_is_fetched_once_in_one_resolution():
    root = importing(n("a"), n("b"))
    a = ontology(n("a"), (n("a"), IMPORTS, n("b")))
    b = ontology(n("b"), (n("b"), IMPORTS, n("a")))
    loader = Loader({n("a"): a, n("b"): b})
    root.resolve_imports(loader=loader)
    assert sorted(loader.calls, key=str) == [n("a"), n("b")]


def test_a_cycle_terminates():
    root = importing(n("a"))
    a = ontology(n("a"), (n("a"), IMPORTS, n("b")))
    b = ontology(n("b"), (n("b"), IMPORTS, n("a")))
    result = root.resolve_imports(loader=Loader({n("a"): a, n("b"): b}))
    assert (n("b"), RDF_TYPE, ONTOLOGY) in result


def test_a_self_import_terminates_and_needs_no_loader():
    g = ontology(n("a"), (n("a"), IMPORTS, n("a")))
    assert set(g.resolve_imports()) == set(g)


# ---- malformed declaration --------------------------------------------------------------------------------------------


def test_an_import_object_that_is_not_an_iri_is_a_format_error_of_kind_owl_for_a_graph():
    g = StarLayerGraph()
    g.add((n("root"), IMPORTS, ox.Literal("not an iri")))
    with pytest.raises(FormatError) as caught:
        g.resolve_imports()
    assert caught.value.kind == "owl"
    with pytest.raises(FormatError):
        unresolved_imports(g)
    assert g.resolve_imports(ignore_imports=True) is not None


def test_resolve_or_raise_takes_the_error_for_a_malformed_declaration_from_the_caller():
    g = StarLayerGraph()
    g.add((n("root"), IMPORTS, ox.Literal("x")))
    with pytest.raises(ShapeCompileError):
        resolve_or_raise(g, None, False, malformed=lambda term: ShapeCompileError("bad"))
