"""Regression tests for the starontology / build-script hunt findings (SKOS shapes, registry, Manchester, build scripts)."""

import pathlib

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
