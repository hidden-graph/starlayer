"""A graph carries its own ``owl:imports`` settings (maintainer decision 2026-11-26): ``imports_loader`` and ``ignore_imports`` (constructor
keywords and properties) and the one accessor ``resolved_imports()`` that every consumer asks. The rule itself is tested in
``test_import_resolution.py``; the consumers (SHACL, ``infer``, ``query``) in their own files."""

from __future__ import annotations

import copy
import pickle

import pyoxigraph as ox
import pytest
from starlayer.errors import ExecutionError
from starlayer.graph import StarLayerDataset, StarLayerGraph

EX = "http://example.org/"
OWL = "http://www.w3.org/2002/07/owl#"
RDF_TYPE = ox.NamedNode("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
IMPORTS = ox.NamedNode(OWL + "imports")
ONTOLOGY = ox.NamedNode(OWL + "Ontology")


def n(local: str) -> ox.NamedNode:
    return ox.NamedNode(EX + local)


def ontology(iri: ox.NamedNode, *more: tuple) -> StarLayerGraph:
    g = StarLayerGraph()
    g.add((iri, RDF_TYPE, ONTOLOGY))
    for t in more:
        g.add(t)
    return g


class Loader:
    def __init__(self, graphs: dict) -> None:
        self.graphs = graphs
        self.calls: list = []

    def __call__(self, iri):
        self.calls.append(iri)
        return self.graphs.get(iri)


def importing(*iris: ox.NamedNode, **kw) -> StarLayerGraph:
    g = StarLayerGraph(**kw)
    g.add((n("root"), RDF_TYPE, ONTOLOGY))
    for iri in iris:
        g.add((n("root"), IMPORTS, iri))
    return g


FACT = (n("a"), n("p"), n("b"))


def lib() -> Loader:
    return Loader({n("lib"): ontology(n("lib"), FACT)})


def test_defaults_no_loader_not_ignored():
    g = StarLayerGraph()
    assert g.imports_loader is None and g.ignore_imports is False
    assert g.resolved_imports() == frozenset()


def test_constructor_setting_and_property():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    assert g.imports_loader is loader
    assert FACT in g.resolved_imports()
    h = importing(n("lib"))
    h.imports_loader = loader
    assert FACT in h.resolved_imports()
    h.ignore_imports = True
    assert h.resolved_imports() == frozenset()


def test_dataset_constructor_and_property():
    ds = StarLayerDataset(imports_loader=lib(), ignore_imports=False)
    ds.add((n("root"), IMPORTS, n("lib")))
    assert FACT in ds.resolved_imports()
    ds.imports_loader = None
    with pytest.raises(ExecutionError) as e:
        ds.resolved_imports()
    assert e.value.kind == "import" and e.value.unresolved == (n("lib"),)


def test_loader_must_be_callable():
    with pytest.raises(TypeError):
        StarLayerGraph(imports_loader="not callable")


def test_per_call_override_of_loader_and_flag():
    own, other = lib(), Loader({n("lib"): ontology(n("lib"), (n("c"), n("p"), n("d")))})
    g = importing(n("lib"), imports_loader=own)
    assert (n("c"), n("p"), n("d")) in g.resolved_imports(imports_loader=other)
    assert not own.calls[1:] and len(other.calls) == 1
    g.ignore_imports = True
    assert g.resolved_imports() == frozenset()
    assert FACT in g.resolved_imports(ignore_imports=False)  # a call can switch the graph's flag off
    h = importing(n("lib"), imports_loader=own)
    assert h.resolved_imports(ignore_imports=True) == frozenset()  # and on


def test_lazy_nothing_loaded_until_consumed():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    g.add((n("x"), n("p"), n("y")))
    g.copy()
    len(g)
    assert loader.calls == []
    g.resolved_imports()
    assert loader.calls == [n("lib")]


def test_cached_and_invalidated_by_writes():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    first = g.resolved_imports()
    assert g.resolved_imports() is first and len(loader.calls) == 1
    g.add((n("x"), n("p"), n("y")))  # any write to the store
    g.resolved_imports()
    assert len(loader.calls) == 2
    g.resolved_imports()
    assert len(loader.calls) == 2
    g.remove((n("x"), n("p"), n("y")))
    g.resolved_imports()
    assert len(loader.calls) == 3


def test_parse_that_adds_an_import_invalidates():
    loader = Loader({n("lib"): ontology(n("lib"), FACT), n("lib2"): ontology(n("lib2"), (n("e"), n("p"), n("f")))})
    g = importing(n("lib"), imports_loader=loader)
    assert (n("e"), n("p"), n("f")) not in g.resolved_imports()
    g.parse(data=f"<{EX}root> <{OWL}imports> <{EX}lib2> .", format="turtle")
    assert (n("e"), n("p"), n("f")) in g.resolved_imports()


def test_clear_invalidates_and_drops_the_imports():
    g = importing(n("lib"), imports_loader=lib())
    assert g.resolved_imports()
    g.clear()
    assert g.resolved_imports() == frozenset()


def test_loader_set_after_the_fact_applies_at_next_consumption():
    g = importing(n("lib"))
    with pytest.raises(ExecutionError):
        g.resolved_imports()
    g.imports_loader = lib()
    assert FACT in g.resolved_imports()
    g.imports_loader = None  # the cache is keyed by the loader: no stale answer
    with pytest.raises(ExecutionError):
        g.resolved_imports()


def test_a_failure_is_not_cached_and_a_later_loader_works():
    loader = Loader({})
    g = importing(n("lib"), imports_loader=loader)
    for _ in range(2):
        with pytest.raises(ExecutionError):
            g.resolved_imports()
    assert len(loader.calls) == 2
    loader.graphs[n("lib")] = ontology(n("lib"), FACT)
    assert FACT in g.resolved_imports()


def test_clear_imports_cache_loads_again():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    g.resolved_imports()
    assert g.clear_imports_cache() is g
    g.resolved_imports()
    assert len(loader.calls) == 2


def test_unresolved_error_names_the_iris():
    g = importing(n("lib"), n("missing"), imports_loader=lib())
    with pytest.raises(ExecutionError) as e:
        g.resolved_imports()
    assert e.value.kind == "import" and e.value.unresolved == (n("missing"),)
    assert "imports_loader" in str(e.value)


def test_loader_that_raises_is_wrapped():
    def boom(iri):
        raise OSError("down")

    g = importing(n("lib"), imports_loader=boom)
    with pytest.raises(ExecutionError) as e:
        g.resolved_imports()
    assert e.value.kind == "import" and isinstance(e.value.__cause__, OSError)


def test_cycle_ends():
    a, b = n("a-ont"), n("b-ont")
    loader = Loader({a: ontology(a, (a, IMPORTS, b)), b: ontology(b, (b, IMPORTS, a))})
    g = importing(a, imports_loader=loader)
    got = g.resolved_imports()
    assert (b, IMPORTS, a) in got and sorted(loader.calls, key=str) == [a, b]


def test_ignore_flag_skips_the_check_too():
    g = importing(n("missing"), ignore_imports=True)
    assert g.resolved_imports() == frozenset()


def test_builtin_import_needs_no_loader():
    g = importing(ox.NamedNode("http://www.w3.org/ns/shacl#"))
    assert g.resolved_imports() == frozenset()


def test_copies_and_set_operations_keep_the_setting():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader, ignore_imports=False)
    for c in (g.copy(), copy.copy(g), copy.deepcopy(g), g + StarLayerGraph(), g - StarLayerGraph(), g.empty_like()):
        assert c.imports_loader is loader
    ig = importing(n("lib"), ignore_imports=True)
    assert ig.copy().ignore_imports and (ig + StarLayerGraph()).ignore_imports
    assert (StarLayerGraph() + g).imports_loader is None  # the left operand's setting


def test_pickle_keeps_the_flag_not_the_loader():
    g = importing(n("lib"), imports_loader=lib(), ignore_imports=True)
    h = pickle.loads(pickle.dumps(g))
    assert h.ignore_imports is True and h.imports_loader is None
    ds = StarLayerDataset(imports_loader=lib(), ignore_imports=True)
    d2 = pickle.loads(pickle.dumps(ds))
    assert d2.ignore_imports is True and d2.imports_loader is None


def test_dataset_views_and_copies_carry_the_setting():
    loader = lib()
    ds = StarLayerDataset(imports_loader=loader)
    assert ds.copy().imports_loader is loader
    assert ds.graph("urn:g:1").imports_loader is loader
    assert ds.default_graph.imports_loader is loader
    assert all(g.imports_loader is loader for g in ds.graphs())
    assert ds.to_graph().imports_loader is loader


def test_dataset_union_reads_all_graphs_and_default_only_otherwise():
    for union, expect_load in ((True, True), (False, False)):
        loader = lib()
        ds = StarLayerDataset(default_union=union, imports_loader=loader)
        ds.graph("urn:g:1").add((n("root"), IMPORTS, n("lib")))
        if expect_load:
            assert FACT in ds.resolved_imports()
        else:
            assert ds.resolved_imports() == frozenset()
        # the named graph's own view always resolves its own imports
        assert FACT in ds.graph("urn:g:1").resolved_imports()


def test_a_named_graph_is_resolved_per_graph():
    loader = lib()
    ds = StarLayerDataset(imports_loader=loader)
    ds.graph("urn:g:1").add((n("root"), IMPORTS, n("lib")))
    ds.graph("urn:g:2").add((n("other"), n("p"), n("q")))
    assert ds.graph("urn:g:2").resolved_imports() == frozenset()
    assert FACT in ds.graph("urn:g:1").resolved_imports()


def test_resolve_imports_uses_the_graph_setting_and_the_call_overrides():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    assert FACT in set(g.resolve_imports().triples((None, None, None)))
    assert g.resolve_imports(ignore_imports=True) is not None
    other = Loader({n("lib"): ontology(n("lib"), (n("c"), n("p"), n("d")))})
    assert (n("c"), n("p"), n("d")) in set(g.resolve_imports(imports_loader=other).triples((None, None, None)))
    full = g.resolve_imports()
    assert full.imports_loader is loader


def test_two_wrappers_of_one_store_share_the_cache_per_loader():
    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    h = StarLayerGraph(g.store, imports_loader=loader)
    g.resolved_imports()
    h.resolved_imports()
    assert len(loader.calls) == 1
    h2 = StarLayerGraph(g.store, imports_loader=lib())  # another loader is another answer
    h2.resolved_imports()
    assert len(loader.calls) == 1


def test_threads_asking_together_load_once():
    from concurrent.futures import ThreadPoolExecutor

    loader = lib()
    g = importing(n("lib"), imports_loader=loader)
    with ThreadPoolExecutor(8) as pool:
        results = list(pool.map(lambda _: g.resolved_imports(), range(16)))
    assert all(r == results[0] for r in results) and len(loader.calls) == 1
