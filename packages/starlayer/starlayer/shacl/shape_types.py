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
2. **The rules** (``shacl_shacl_rules``): SHACL rules for what RDFS cannot say (a list walk, an absent ``sh:path``), and the node
   expressions under ``sh:values``/``sh:defaultValue``/``sh:expression`` (typed ``sh:NodeExpression``, at any nesting depth, with the cells
   of their argument lists typed ``rdf:List``) so that every node there has a shape that targets it (GitHub issue #22).

The result holds only new ``rdf:type`` triples, in the ``sh:`` namespace; it never contains what the shapes graph already
says, and the shapes graph is not changed.
"""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

from starlayer.graph.oxgraph.helpers.entailment import ENTAILMENT
from starlayer.shacl_engine.graphs import new_graph
from starlayer.shacl_engine.terms import RDF, RDFS, SH, engine_view

_SH_NS = str(SH)

# Left out of the vocabulary: their domain is sh:Shape, which would make a property group a shape.
_PREDICATES_WITHOUT_VOCABULARY_DOMAIN = (SH.name, SH.description, SH.order)

__all__ = ["infer_types"]


def _is_vocabulary_term(node: Any) -> bool:
    return isinstance(node, ox.NamedNode) and node.value.startswith(_SH_NS)


def _copy(graph: Any) -> Any:
    result = new_graph(graph)
    result.extend(list(graph.triples((None, None, None))))
    return result


def infer_types(shapes_graph: Any) -> Any:
    """The ``rdf:type`` triples ``shapes_graph``'s structure entails and it does not already state, as an ``OxGraph``.

    ``shapes_graph`` is read as data and left unchanged. Needs the optional ``owlrl`` dependency (for the RDFS step).
    """
    from starlayer import starontology
    from starlayer.shacl.validator import apply_rules

    data = _copy(engine_view(shapes_graph, "shapes graph"))

    # 1. RDFS entailment over the shapes graph and the SHACL vocabulary; keep the new sh: types of nodes in the shapes graph.
    vocabulary = _copy(starontology.get_ontology_graph("shacl_vocabulary"))
    for predicate in _PREDICATES_WITHOUT_VOCABULARY_DOMAIN:
        for axiom in (RDFS.domain, RDFS.range):
            for value in list(vocabulary.objects(predicate, axiom)):
                vocabulary.remove((predicate, axiom, value))
    combined = _copy(data)
    combined.extend(list(vocabulary.triples((None, None, None))))
    # Not the vocabulary's own terms: an object such as sh:NodeShape (from an earlier pass's output) is a class, not a shape.
    nodes = {n for n in set(data.subjects()) | set(data.objects()) if not _is_vocabulary_term(n)}
    entailed = new_graph()
    entailed.extend(
        [
            (s, p, o)
            for s, p, o in combined.infer(ENTAILMENT.RDFS, mode="delta").triples((None, None, None))
            if p == RDF.type and s in nodes and isinstance(o, ox.NamedNode) and o.value.startswith(_SH_NS)
        ]
    )

    # 2. The rules, over the shapes graph with those types added (a value of sh:property is already a sh:PropertyShape).
    working = _copy(data)
    working.extend(list(entailed.triples((None, None, None))))
    rules = _copy(starontology.get_ontology_graph("shacl_shacl_rules"))
    ruled = apply_rules(working, shacl_graph=rules).inferred_graph

    result = new_graph(data)
    for graph in (entailed, ruled):
        result.extend(
            [
                (s, p, o)
                for s, p, o in graph.triples((None, None, None))
                if p == RDF.type and not _is_vocabulary_term(s) and (s, p, o) not in data
            ]
        )
    return result
