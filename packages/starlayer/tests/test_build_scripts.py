"""The build-time scripts in scripts/ (GitHub issues #102 and #84): build.py --check, build_starontology.py, generate_api_docs.py."""

from __future__ import annotations

from rdflib import RDF, RDFS, Dataset, Graph, Literal, URIRef


def test_build_starontology_declares_a_namespace_the_registry_does_not_know(tmp_path, monkeypatch) -> None:
    import build_starontology as build

    (tmp_path / "x.ttl").write_text(
        '@prefix foaf: <http://xmlns.com/foaf/0.1/> .\n<http://example.org/a> foaf:name "x" .\n', encoding="utf-8"
    )
    monkeypatch.setattr(build, "_DIR", tmp_path)
    monkeypatch.setattr(build, "_filenames", lambda: ["x.ttl"])
    text = build._assemble_trig()  # used to produce a TriG with an undeclared ns1: prefix
    graphs = build._trig_graphs(text)  # parses only if every prefix is declared
    assert (URIRef("http://example.org/a"), URIRef("http://xmlns.com/foaf/0.1/name"), Literal("x")) in next(iter(graphs.values()))


def test_build_starontology_ttl_output_declares_unregistered_prefixes(tmp_path) -> None:
    import build_starontology as build

    graph = Graph()
    graph.add((URIRef("http://example.org/a"), URIRef("http://xmlns.com/foaf/0.1/name"), Literal("x")))
    out = tmp_path / "out.ttl"
    assert build._write_ttl(out, "# notice\n", graph, check=False)
    assert len(Graph().parse(str(out), format="turtle")) == 1


def test_api_docs_match_all_names_by_module_not_by_bare_name(tmp_path, monkeypatch) -> None:
    import generate_api_docs as api

    # tmp_path stands in for the starlayer package: __init__ re-exports `evaluate` from impl, which also has a
    # same-named method on a class that lives inside a private factory function.
    (tmp_path / "__init__.py").write_text('from .impl import evaluate\n__all__ = ["evaluate"]\n')
    (tmp_path / "impl.py").write_text("def evaluate():\n    pass\n\ndef _factory():\n    class Comp:\n        def evaluate(self):\n            pass\n")
    monkeypatch.setattr(api, "PKG_ROOT", tmp_path)
    monkeypatch.setattr(api, "_ALL_FILES", [("__init__.py", "starlayer")])
    ds = Dataset()
    g = ds.graph(URIRef("http://example.org/g"))
    for ident, rdf_type in (("starlayer.impl.evaluate", api.SLKG.Function), ("starlayer.impl._factory.Comp.evaluate", api.SLKG.Method)):
        node = URIRef("http://example.org/" + ident)
        g.add((node, RDF.type, rdf_type))
        g.add((node, RDFS.label, Literal("evaluate")))
        g.add((node, api.DCTERMS.identifier, Literal(ident)))
    assert api.collect_public_entities(ds) == [("starlayer.impl.evaluate", "starlayer")]


def test_api_docs_resolve_a_reexported_name_to_its_defining_module() -> None:
    import generate_api_docs as api

    assert api.resolve_export("starlayer.shacl", "evaluate") == "starlayer.shacl.validator.evaluate"
    assert api.resolve_export("starlayer.shacl", "no_such_name") is None


def _fake_build(tmp_path, monkeypatch):
    """scripts/build.py pointed at a scratch tree whose one step rewrites its output and a side-effect file."""
    import build

    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "fake.py").write_text(
        "import pathlib\n"
        "root = pathlib.Path(__file__).resolve().parents[1]\n"
        "(root / 'out.txt').write_text('rebuilt')\n"
        "(root / 'CHANGELOG.md').write_text('touched')\n"
    )
    (tmp_path / "out.txt").write_text("committed")
    (tmp_path / "CHANGELOG.md").write_text("original")
    monkeypatch.setattr(build, "_ROOT", tmp_path)
    monkeypatch.setattr(build, "_SCRIPTS", tmp_path / "scripts")
    monkeypatch.setattr(build, "_STEPS", {"fake": build.Step("fake.py", outputs=["out.txt"], side_effects=["CHANGELOG.md"])})
    return build


def test_check_restores_the_files_a_step_writes_besides_its_outputs(tmp_path, monkeypatch) -> None:
    build = _fake_build(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.argv", ["build.py", "--check"])
    assert build.main() == 1  # out.txt is stale
    assert (tmp_path / "out.txt").read_text() == "committed"
    assert (tmp_path / "CHANGELOG.md").read_text() == "original"  # the codekg step's changelog entry used to stay


def test_check_ignores_the_build_stamp_when_comparing_trig_files() -> None:
    import build

    def trig(built_at: str, value: str) -> bytes:
        from starlayer.graph import StarLayerDataset

        ds = StarLayerDataset()
        ds.graph(URIRef("https://github.com/hidden-graph/starlayer/ns/codekg/build")).add(
            (URIRef("http://example.org/b"), URIRef("http://example.org/builtAt"), Literal(built_at))
        )
        ds.graph(URIRef("http://example.org/module")).add((URIRef("http://example.org/s"), URIRef("http://example.org/p"), Literal(value)))
        return ds.serialize(format="trig12").encode()

    assert build._trig_isomorphic(trig("2026-01-01", "same"), trig("2026-10-26", "same"))
    assert not build._trig_isomorphic(trig("2026-01-01", "same"), trig("2026-01-01", "different"))
