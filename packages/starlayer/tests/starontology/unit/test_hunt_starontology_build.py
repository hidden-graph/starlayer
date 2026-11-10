"""Regression tests for the starontology / build-script hunt findings (SKOS shapes, registry, Manchester, build scripts)."""

import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest
from starlayer.graph.oxgraph.core import StarLayerGraph
from starlayer.starontology.skos import skos_validate

_ROOT = pathlib.Path(__file__).resolve().parents[5]
_SCRIPTS = _ROOT / "scripts"

P = "@prefix skos: <http://www.w3.org/2004/02/skos/core#> . @prefix ex: <http://e/> .\n"
C = "ex:a a skos:Concept . ex:b a skos:Concept . "


def _conforms(body, fmt="turtle"):
    g = StarLayerGraph()
    g.parse(data=body, format=fmt)
    return skos_validate(g)[0]


@pytest.mark.parametrize("body", [
    "ex:a skos:related ex:b ; skos:broader ex:b .",
    "ex:a skos:related ex:b ; skos:broadMatch ex:b .",
    "ex:a skos:related ex:b ; skos:narrowMatch ex:b .",
    "ex:a skos:relatedMatch ex:b ; skos:broader ex:b .",
    "ex:a skos:relatedMatch ex:b ; skos:narrower ex:b .",
    "ex:a skos:relatedMatch ex:b ; skos:broadMatch ex:b .",
])
def test_s27_covers_mapping_subproperties(body):
    assert not _conforms(P + C + body)


@pytest.mark.parametrize("prop", ["broader", "narrower", "related", "broaderTransitive", "narrowerTransitive", "semanticRelation",
                                  "broadMatch", "narrowMatch", "relatedMatch", "closeMatch", "exactMatch", "mappingRelation"])
def test_collection_as_subject_of_semantic_relation_is_rejected(prop):
    assert not _conforms(P + f"ex:c a skos:Collection . ex:c skos:{prop} ex:d . ex:d a skos:Concept .")


def test_two_untagged_preflabels_rejected():
    assert not _conforms(P + "ex:a a skos:Concept; skos:prefLabel 'x', 'y' .")


def test_one_untagged_and_one_tagged_preflabel_conform():
    assert _conforms(P + "ex:a a skos:Concept; skos:prefLabel 'x', 'y'@en .")


def test_dirlang_preflabel_conforms():
    h = "@prefix skos: <http://www.w3.org/2004/02/skos/core#> . @prefix : <http://e/> .\nVERSION '1.2'\n"
    assert _conforms(h + ":a a skos:Concept ; skos:prefLabel 'x'@ar--rtl .", "turtle12")


def test_ui_baseline_treats_dirlangstring_like_langstring():
    import pyoxigraph as ox
    from starlayer import starontology as so
    from starlayer.shacl.ui_widget_selection import select_widgets

    t = ("@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "
         "@prefix : <http://e/> .\n")
    sg = StarLayerGraph()
    sg.parse(data=t + ":S a sh:NodeShape ; sh:property [ sh:path :a ; sh:datatype rdf:langString ], "
             "[ sh:path :b ; sh:datatype rdf:dirLangString ] .", format="turtle")
    sh_path = ox.NamedNode("http://www.w3.org/ns/shacl#path")
    for role, expected in (("viewer", "LangStringViewer"), ("editor", "TextFieldWithLangEditor")):
        r = select_widgets(shape_node=ox.NamedNode("http://e/S"), shapes_graph=sg,
                           scoring_graph=so.get_ontology_graph("shacl_ui_baseline"), role=role)
        out = {next(sg.objects(k, sh_path)).value[-1]: str(v).rstrip(">").rsplit("#", 1)[-1] for k, v in r.items()}
        assert out == {"a": expected, "b": expected}


def test_manchester_second_document_into_one_graph_is_rejected():
    from starlayer.starontology import manchester as M

    pre = "Prefix: : <http://ex/>\n"
    g = M.manchester_parse_to_tree(pre + "Class: :A\n")
    with pytest.raises(ValueError, match="manch:Document"):
        M.manchester_parse_to_tree(pre + "Class: :B\n", graph=g)
    text = M.manchester_tree_to_text(g)
    assert "ex/A" in text and "ex/B" not in text


def _script(name):
    spec = importlib.util.spec_from_file_location(name, _SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_SCRIPTS))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_SCRIPTS))
    return module


def test_field_name_fallback_is_stable_across_processes():
    code = (
        f"import sys; sys.path.insert(0, {str(_SCRIPTS)!r}); sys.path.insert(0, {str(_ROOT / 'packages' / 'starlayer')!r})\n"
        "import build_shacl_ui as b\n"
        "from rdflib import URIRef\n"
        "print(b._field_name('NodeShapeForm', URIRef('http://example.org/ns#unknownPredicate'), {'sh': 'http://www.w3.org/ns/shacl#'}))\n"
    )
    outs = set()
    for seed in ("1", "2", "3"):
        r = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONHASHSEED=seed), capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        outs.add(r.stdout.strip())
    assert len(outs) == 1, outs


def test_build_reports_missing_registered_file(capsys):
    from starlayer import starontology as so

    b = _script("build_starontology")
    so._FILENAME_BY_NAME["ghost"] = "ghost-missing.ttl"
    try:
        assert b.build(check=True) == 1
    finally:
        del so._FILENAME_BY_NAME["ghost"]
    assert "registered files missing" in capsys.readouterr().err


def test_anchor_keeps_underscores_in_identifiers(tmp_path):
    cd = _script("check_docs")
    (tmp_path / "a.md").write_text("# Title\n\n## my_function\n\n## _emphasis_ here\n\nSee [x](#my_function).\n")
    anchors = cd._anchors(tmp_path / "a.md")
    assert "my_function" in anchors and "myfunction" not in anchors
    assert "emphasis-here" in anchors
