"""Gaps found by the B1 classification (``docs/working/b1-classification.md``, branch ``mig-b1-gaps``): pickle and deepcopy,
``from_rdflib`` / ``to_rdflib``, the ``VERSION`` line on write, the basic encoding on a plain ``turtle`` parse, exception types
and the SHACL report. Each is a property of ``OxGraph`` / ``OxDataset`` alone."""

from __future__ import annotations

import pyoxigraph as ox
from starlayer.graph.oxgraph import OxDataset, OxGraph

EX = "http://example.org/"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

DOC12 = f"""@prefix : <{EX}> .
:a :p :b .
:a :q <<( :x :y :z )>> .
:a :r "x"@en--ltr .
_:n :p "plain" .
"""

TRIG12 = f"""@prefix : <{EX}> .
:a :p :b .
GRAPH :g1 {{ :a :q <<( :x :y :z )>> . _:n :p "x"@ar--rtl }}
GRAPH :g2 {{ :c :p :d }}
"""


def _graph() -> OxGraph:
    g = OxGraph()
    g.parse(data=DOC12, format="turtle")
    g.bind("ex", EX)
    return g


def _dataset(union: bool = True) -> OxDataset:
    d = OxDataset(default_union=union)
    d.parse(data=TRIG12, format="trig")
    d.store.add_graph(ox.NamedNode(EX + "empty"))
    d.bind("ex", EX)
    return d


def _quads(x) -> set:
    return set(x.store) if isinstance(x, OxDataset) else set(x.quads())


# ---- O2: pickle, copy.copy, copy.deepcopy -----------------------------------------------------------------------------------












# ---- B2 / O6: from_rdflib, to_rdflib ----------------------------------------------------------------------------------------


class TestFromRdflib:


    def test_starlayer_graph_with_a_triple_term(self):
        from starlayer.graph import StarLayerGraph

        old = StarLayerGraph()
        old.parse(data=DOC12, format="turtle")
        g = OxGraph.from_rdflib(old)
        assert any(isinstance(o, ox.Triple) for _, _, o in g.triples())
        assert (ox.NamedNode(EX + "a"), ox.NamedNode(EX + "r"),
                ox.Literal("x", language="en", direction=ox.BaseDirection.LTR)) in g








# ---- O3: the VERSION line on write; no RDF12ConformanceWarning ----------------------------------------------------------------

_FORMATS = {"turtle": '@version "1.2" .', "trig": '@version "1.2" .', "nt": 'VERSION "1.2"', "nq": 'VERSION "1.2"'}














# ---- O4: a plain turtle parse does not adopt the basic encoding --------------------------------------------------------------

BASIC = f"""@prefix : <{EX}> .
@prefix rdf: <{RDF}> .
:a :q _:b .
_:b a rdf:PropositionForm ; rdf:propositionFormSubject :x ; rdf:propositionFormPredicate :y ; rdf:propositionFormObject :z .
"""






# ---- O5: exception types; no used-graph line in a SHACL report -----------------------------------------------------------------




_SHAPES = f"""@prefix ex: <{EX}> . @prefix sh: <http://www.w3.org/ns/shacl#> .
ex:S a sh:NodeShape ; sh:targetClass ex:P ; sh:property [ sh:path ex:n ; sh:minCount 1 ] ."""




# ---- the equivalents named in oxgraph-wrapper.md for old-class API that is not ported -----------------------------------------


