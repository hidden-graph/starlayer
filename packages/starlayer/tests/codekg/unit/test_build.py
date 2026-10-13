"""End-to-end test for starlayer.codekg.extractor.build.refresh() - the
wholesale-replace orchestration.

Writes tiny synthetic module files to a tmp dir structured to mimic
packages/starlayer/starlayer/<something>/, points refresh() at a tmp
trig_path override (never the real, checked-in codekg.trig), and
confirms: the result parses back with the expected triples, and running
refresh() a second time with a MODIFIED fixture file produces updated
triples rather than stale ones - the real behavior this design hinges on.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Literal, URIRef
from rdflib.namespace import RDF, RDFS

from starlayer.codekg import BLOB_BASE, CODEKG_NS
from starlayer.codekg.extractor.build import refresh
from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

SLKG = CODEKG_NS


def _make_repo_root(tmp_path: Path) -> Path:
    repo_root = tmp_path / "repo"
    pkg_dir = repo_root / "packages" / "starlayer" / "starlayer" / "widgets"
    pkg_dir.mkdir(parents=True)
    return repo_root


def test_refresh_produces_expected_triples(tmp_path):
    repo_root = _make_repo_root(tmp_path)
    mod_path = repo_root / "packages" / "starlayer" / "starlayer" / "widgets" / "thing.py"
    mod_path.write_text(
        "def greet(name: str) -> str:\n"
        '    """Greet someone."""\n'
        "    return name\n",
        encoding="utf-8",
    )
    trig_path = tmp_path / "codekg.trig"

    refresh([mod_path], repo_root, trig_path=trig_path)

    assert trig_path.exists()

    ds = StarLayerDataset()
    ds.parse(str(trig_path), format="trig12")

    module_iri = URIRef(BLOB_BASE + "widgets/thing.py")
    fn_iri = URIRef(f"{module_iri}#greet")

    module_graph = ds.get_context(module_iri)
    triples = list(module_graph.triples((None, None, None)))

    assert (module_iri, RDF.type, SLKG.Module) in triples
    assert (fn_iri, RDF.type, SLKG.Function) in triples
    assert (fn_iri, RDFS.label, Literal("greet")) in triples


def test_refresh_second_run_replaces_stale_triples_not_stacks_them(tmp_path):
    repo_root = _make_repo_root(tmp_path)
    mod_path = repo_root / "packages" / "starlayer" / "starlayer" / "widgets" / "thing.py"
    trig_path = tmp_path / "codekg.trig"
    module_iri = URIRef(BLOB_BASE + "widgets/thing.py")

    mod_path.write_text("def old_name():\n    pass\n", encoding="utf-8")
    refresh([mod_path], repo_root, trig_path=trig_path)

    ds1 = StarLayerDataset()
    ds1.parse(str(trig_path), format="trig12")
    old_fn_iri = URIRef(f"{module_iri}#old_name")
    assert (old_fn_iri, RDF.type, SLKG.Function) in list(ds1.get_context(module_iri).triples((None, None, None)))

    # Modify the fixture: rename the function and add a new one.
    mod_path.write_text(
        "def new_name():\n    pass\n\n\ndef another():\n    pass\n",
        encoding="utf-8",
    )
    refresh([mod_path], repo_root, trig_path=trig_path)

    ds2 = StarLayerDataset()
    ds2.parse(str(trig_path), format="trig12")
    module_triples = list(ds2.get_context(module_iri).triples((None, None, None)))

    new_fn_iri = URIRef(f"{module_iri}#new_name")
    another_fn_iri = URIRef(f"{module_iri}#another")

    assert (new_fn_iri, RDF.type, SLKG.Function) in module_triples
    assert (another_fn_iri, RDF.type, SLKG.Function) in module_triples
    # The old, renamed function must be gone - not left behind as a stale
    # leftover triple alongside the new content.
    assert not any(s == old_fn_iri for s, p, o in module_triples)


def test_refresh_removes_graph_for_module_no_longer_in_target_paths(tmp_path):
    repo_root = _make_repo_root(tmp_path)
    widgets_dir = repo_root / "packages" / "starlayer" / "starlayer" / "widgets"
    mod_a = widgets_dir / "a.py"
    mod_b = widgets_dir / "b.py"
    mod_a.write_text("def fn_a():\n    pass\n", encoding="utf-8")
    mod_b.write_text("def fn_b():\n    pass\n", encoding="utf-8")
    trig_path = tmp_path / "codekg.trig"

    refresh([mod_a, mod_b], repo_root, trig_path=trig_path)

    ds1 = StarLayerDataset()
    ds1.parse(str(trig_path), format="trig12")
    a_iri = URIRef(BLOB_BASE + "widgets/a.py")
    b_iri = URIRef(BLOB_BASE + "widgets/b.py")
    assert len(ds1.get_context(a_iri)) > 0
    assert len(ds1.get_context(b_iri)) > 0

    # Second run only targets mod_a - mod_b's graph must be dropped, not
    # left behind as a stale graph from before.
    refresh([mod_a], repo_root, trig_path=trig_path)

    ds2 = StarLayerDataset()
    ds2.parse(str(trig_path), format="trig12")
    assert len(ds2.get_context(a_iri)) > 0
    assert len(ds2.get_context(b_iri)) == 0


def test_refresh_preserves_ontology_and_curated_graphs(tmp_path):
    from starlayer.codekg import CURATED_GRAPH_IRI, ONTOLOGY_GRAPH_IRI

    repo_root = _make_repo_root(tmp_path)
    mod_path = repo_root / "packages" / "starlayer" / "starlayer" / "widgets" / "thing.py"
    mod_path.write_text("def f():\n    pass\n", encoding="utf-8")
    trig_path = tmp_path / "codekg.trig"

    # Seed the trig file with a pre-existing ontology graph and a curated
    # graph - refresh() must never touch either, even though they share
    # the module graphs' same dataset file.
    seed_ds = StarLayerDataset()
    seed_ds.graph(ONTOLOGY_GRAPH_IRI).add((ONTOLOGY_GRAPH_IRI, RDF.type, SLKG.Module))
    seed_ds.graph(CURATED_GRAPH_IRI).add((CURATED_GRAPH_IRI, RDF.type, SLKG.Module))
    seed_ds.serialize(destination=str(trig_path), format="trig12")

    refresh([mod_path], repo_root, trig_path=trig_path)

    ds = StarLayerDataset()
    ds.parse(str(trig_path), format="trig12")
    assert len(ds.get_context(ONTOLOGY_GRAPH_IRI)) > 0
    assert len(ds.get_context(CURATED_GRAPH_IRI)) > 0
