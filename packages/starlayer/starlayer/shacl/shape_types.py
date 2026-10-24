"""``infer_types()`` - the types a shapes graph's structure entails (GitHub issues #24, #27, #28).

SHACL 1.2 Core leaves much of a shape's typing to the engine: a shape need not say ``rdf:type sh:NodeShape`` (3.2) or
``sh:PropertyShape`` (3.3), and 3.1 makes a node a shape through its targets, its constraint parameters, being the value of
a shape-valued parameter, or being on the list that is the value of ``sh:and``/``sh:or``/``sh:xone``. A tool that lists the
entities of a shapes file by type needs those triples.

Two sources, both from the registry:

1. **The SHACL vocabulary** (``shacl_vocabulary``): RDFS entailment over the shapes graph plus the vocabulary's
   ``rdfs:domain``/``rdfs:range`` types things that are not shapes (the value of ``sh:group`` is a ``sh:PropertyGroup``, the
   subject of ``sh:validator`` a ``sh:ConstraintComponent``). The vocabulary's domain for ``sh:name`` and ``sh:description``
   is ``sh:Shape``, but a property group has them too, so those two are left out of the entailment.
2. **The rules** (``shacl_shacl_rules``): SHACL rules for what RDFS cannot say (a list walk, an absent ``sh:path``).

The result holds only new ``rdf:type`` triples, in the ``sh:`` namespace; it never contains what the shapes graph already
says, and the shapes graph is not changed.
"""

from __future__ import annotations

from typing import Any

from rdflib import RDF, RDFS, Namespace

from starlayer.graph.graph.entailment_regimes import ENTAILMENT
from starlayer.graph.graph.starlayer_graph import StarLayerGraph

SH = Namespace("http://www.w3.org/ns/shacl#")

# Left out of the vocabulary: their domain is sh:Shape, which would make a property group a shape.
_PREDICATES_WITHOUT_VOCABULARY_DOMAIN = (SH.name, SH.description, SH.order)

__all__ = ["infer_types"]


def _copy(graph: Any) -> StarLayerGraph:
    result = StarLayerGraph()
    for prefix, namespace in graph.namespaces():
        result.bind(prefix, namespace)
    for triple in graph:
        result.add(triple)
    return result


def infer_types(shapes_graph: Any) -> StarLayerGraph:
    """The ``rdf:type`` triples ``shapes_graph``'s structure entails and it does not already state.

    ``shapes_graph`` is read as data and left unchanged. Needs the optional ``owlrl`` dependency (for the RDFS step).
    """
    from starlayer import starontology
    from starlayer.shacl.validator import apply_rules

    data = _copy(shapes_graph)

    # 1. RDFS entailment over the shapes graph and the SHACL vocabulary; keep the new sh: types of nodes in the shapes graph.
    vocabulary = _copy(starontology.get_ontology_graph("shacl_vocabulary"))
    for predicate in _PREDICATES_WITHOUT_VOCABULARY_DOMAIN:
        for axiom in (RDFS.domain, RDFS.range):
            for value in list(vocabulary.objects(predicate, axiom)):
                vocabulary.remove((predicate, axiom, value))
    combined = _copy(data)
    for triple in vocabulary:
        combined.add(triple)
    nodes = set(data.subjects()) | set(data.objects())
    entailed = StarLayerGraph()
    for s, p, o in combined.infer(ENTAILMENT.RDFS, mode="delta"):
        if p == RDF.type and s in nodes and str(o).startswith(str(SH)):
            entailed.add((s, p, o))

    # 2. The rules, over the shapes graph with those types added (a value of sh:property is already a sh:PropertyShape).
    working = _copy(data)
    for triple in entailed:
        working.add(triple)
    rules = _copy(starontology.get_ontology_graph("shacl_shacl_rules"))
    ruled = apply_rules(working, shacl_graph=rules).inferred_graph

    result = StarLayerGraph()
    for prefix, namespace in data.namespaces():
        result.bind(prefix, namespace)
    for graph in (entailed, ruled):
        for s, p, o in graph:
            if p == RDF.type and (s, p, o) not in data:
                result.add((s, p, o))
    return result
