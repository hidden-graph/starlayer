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


def test_refresh_handles_docstring_resembling_a_prefix_directive(tmp_path):
    """Regression test for a real bug found while running this extractor
    over this project's own trig12.py: a docstring whose word-wrapping
    happens to put the literal text '@prefix' at the very start of one of
    its own physical lines (e.g. describing Turtle's own @prefix syntax)
    was misread by several line-based post-processing steps (TriG block
    splitting/prefix extraction in graph.parsers.trig12, and the
    prefix/body line split in graph.graph.starlayer_dataset.serialize())
    as a real directive, tearing it out of the docstring literal it's
    part of and corrupting the whole document - it no longer parsed back
    at all. Also covers a line starting with 'GRAPH <' and a line
    starting with '@version', the same category of false positive for
    the other two directive-like keywords this pipeline recognizes."""
    repo_root = _make_repo_root(tmp_path)
    mod_path = repo_root / "packages" / "starlayer" / "starlayer" / "widgets" / "thing.py"
    mod_path.write_text(
        'def f():\n'
        '    """Uses a directive like\n'
        '@prefix ex: <http://example.org/> . at the very start of this\n'
        'line, same as a literal\n'
        'GRAPH <http://example.org/g> { ... } block, and also an\n'
        '@version "1.2" directive, all as plain prose, not real syntax."""\n'
        '    pass\n',
        encoding="utf-8",
    )
    trig_path = tmp_path / "codekg.trig"

    refresh([mod_path], repo_root, trig_path=trig_path)

    assert trig_path.exists()

    ds = StarLayerDataset()
    ds.parse(str(trig_path), format="trig12")  # must not raise

    module_iri = URIRef(BLOB_BASE + "widgets/thing.py")
    fn_iri = URIRef(f"{module_iri}#f")
    triples = list(ds.get_context(module_iri).triples((None, None, None)))
    assert (fn_iri, RDF.type, SLKG.Function) in triples
    comment = next(o for s, p, o in triples if s == fn_iri and p == RDFS.comment)
    assert '@prefix ex: <http://example.org/> .' in str(comment)
    assert 'GRAPH <http://example.org/g> { ... }' in str(comment)
    assert '@version "1.2" directive' in str(comment)


def test_refresh_writes_the_file_from_scratch_and_does_not_read_the_old_one(tmp_path):
    from starlayer.codekg import ONTOLOGY_GRAPH_IRI

    repo_root = _make_repo_root(tmp_path)
    mod_path = repo_root / "packages" / "starlayer" / "starlayer" / "widgets" / "thing.py"
    mod_path.write_text("def f():\n    pass\n", encoding="utf-8")
    trig_path = tmp_path / "codekg.trig"
    # anything already in the file is replaced: the file holds only what the extractor produces
    seed_ds = StarLayerDataset()
    seed_ds.graph(ONTOLOGY_GRAPH_IRI).add((ONTOLOGY_GRAPH_IRI, RDF.type, SLKG.Module))
    seed_ds.serialize(destination=str(trig_path), format="trig12")

    written, _ = refresh([mod_path], repo_root, trig_path=trig_path)

    ds = StarLayerDataset()
    ds.parse(str(trig_path), format="trig12")
    assert len(ds.get_context(ONTOLOGY_GRAPH_IRI)) == 0
    assert len(ds) == len(written)


def test_refresh_writes_test_modules_to_their_own_file(tmp_path):
    from starlayer.codekg import TESTS_BLOB_BASE

    repo_root = _make_repo_root(tmp_path)
    src = repo_root / "packages" / "starlayer" / "starlayer" / "widgets" / "thing.py"
    src.write_text("def f():\n    pass\n", encoding="utf-8")
    tests_dir = repo_root / "packages" / "starlayer" / "tests" / "widgets"
    tests_dir.mkdir(parents=True)
    test_file = tests_dir / "test_thing.py"
    test_file.write_text("from starlayer.widgets.thing import f\n\n\ndef test_f():\n    f()\n", encoding="utf-8")
    trig_path = tmp_path / "codekg.trig"

    refresh([src, test_file], repo_root, trig_path=trig_path)

    source_ds, tests_ds = StarLayerDataset(), StarLayerDataset()
    source_ds.parse(str(trig_path), format="trig12")
    tests_ds.parse(str(tmp_path / "testskg.trig"), format="trig12")
    source_graphs = {str(c.identifier) for c in source_ds.contexts()}
    tests_graphs = {str(c.identifier) for c in tests_ds.contexts()}
    assert tests_graphs and all(g.startswith(TESTS_BLOB_BASE) for g in tests_graphs)
    assert not any(g.startswith(TESTS_BLOB_BASE) for g in source_graphs)
