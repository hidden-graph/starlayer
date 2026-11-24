"""scripts/build_meta_shapes.py - builds the SHACL 1.2 meta-shapes graph that
``starlayer.shacl.meta_validate()`` checks shapes graphs against.

Build-time only: the library never imports this. It reads the stored result,
``starontology/shacl/shacl12-shacl.ttl``, which ``scripts/build_starontology.py``
regenerates from ``build_meta_shapes_graph()`` below.

The graph is the W3C Data Shapes Working Group's own SHACL-for-SHACL
(``_sources/vendor/w3c-shacl-shacl.ttl``, a pinned verbatim copy, see
``_sources/vendor/VENDORED_FROM.md``) **plus additions only - nothing in the
Working Group's file is deleted or edited**, so a newer upstream copy can be
dropped in and compared. The additions are:

1. ``_sources/shacl12-validation-shapes.ttl``: rules for the SHACL 1.2 predicates
   the Working Group's file has no rule for yet (``sh:someValue``,
   ``sh:uniqueValuesFor``, ``sh:subsetOf``, ``sh:rootClass``, ``sh:reifierShape``,
   ``sh:reificationRequired``, SPARQL, rules, ...), our ``stsh:`` shapes, and
   documentation of the terms.
2. ``sh:deactivated true`` on the Working Group rules that are still stricter
   than SHACL 1.2 allows (``RELAXED_PATHS``). SHACL constraints combine by AND,
   so a looser rule added beside a strict one would change nothing; the
   Working Group's own file says to customise it this way ("this graph should
   be supplemented with 'shsh:xoneSubjectsShape sh:deactivated true'"). The
   replacement rules are in (1).
3. The ``rdf:type`` the shape-valued predicates of the native components need
   (``sh:memberShape``), which starlayer otherwise adds at validation time.

``tests/shacl/integration/test_wg_overrides.py`` checks that each deactivation
is still needed, so when upstream fixes one the test fails and prompts a review.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterable
from typing import Any

import pyoxigraph as ox
from starlayer.graph import RDF, XSD, Namespace
from starlayer.graph import StarLayerGraph as Graph

URIRef = ox.NamedNode
TRUE = ox.Literal("true", datatype=XSD.boolean)

SH = Namespace("http://www.w3.org/ns/shacl#")
SHSH = Namespace("http://www.w3.org/ns/shacl-shacl#")

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "packages", "starlayer", "starlayer", "starontology", "_sources")
VALIDATION_SHAPES_PATH = os.path.join(_ASSETS_DIR, "shacl12-validation-shapes.ttl")
WG_SHAPES_PATH = os.path.join(_ASSETS_DIR, "vendor", "w3c-shacl-shacl.ttl")
WG_VENDORED_FROM_PATH = os.path.join(_ASSETS_DIR, "vendor", "VENDORED_FROM.md")
# The sources of the shipped vocabulary (starontology/shacl/shacl12-vocabulary.ttl is their union).
VOCABULARY_SOURCE_PATHS = (
    os.path.join(_ASSETS_DIR, "vendor", "w3c-shacl.ttl"),
    os.path.join(_ASSETS_DIR, "vendor", "w3c-shacl-ui.ttl"),
    os.path.join(_ASSETS_DIR, "shacl12-vocabulary-overlay.ttl"),
)
SH_NAMESPACE = "http://www.w3.org/ns/shacl#"

# The predicates whose Working Group rule on shsh:ShapeShape is still stricter than SHACL 1.2 allows (list-valued
# sh:nodeKind, path-valued sh:equals/sh:disjoint/sh:lessThan/sh:lessThanOrEquals). As of the pinned copy the Working
# Group has already fixed sh:class, sh:datatype and sh:closed; test_wg_overrides.py fails when one of these is fixed too.
RELAXED_PATHS: tuple[URIRef, ...] = (
    SH.nodeKind,
    SH.disjoint,
    SH.equals,
    SH.lessThan,
    SH.lessThanOrEquals,
    SH.targetNode,  # sh:nodeKind sh:IRIOrLiteral rejects a node expression (GitHub issue #66)
)


def wg_file_sha256() -> str:
    """The SHA-256 of the pinned Working Group file (compared with ``VENDORED_FROM.md`` by a test)."""
    with open(WG_SHAPES_PATH, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def load_wg_shapes() -> Graph:
    """A fresh copy of the pinned Working Group file, unchanged."""
    graph = Graph()
    graph.parse(WG_SHAPES_PATH, format="turtle")
    return graph


def _property_shapes_of(graph: Graph, shape: URIRef, path: URIRef) -> list[Any]:
    """The blank-node property shapes of ``shape`` whose ``sh:path`` is ``path``, found by structure - the blank
    node labels differ on every parse, so they cannot be hard-coded."""
    return [bn for bn in graph.objects(shape, SH.property) if (bn, SH.path, path) in graph]


def _add_overrides(graph: Graph) -> Graph:
    """Add (never remove) the deactivations described in the module docstring."""
    for path in RELAXED_PATHS:
        for property_shape in _property_shapes_of(graph, SHSH.ShapeShape, path):
            graph.add((property_shape, SH.deactivated, TRUE))
    return graph


# The predicates whose values are shapes the Working Group's file does not type (``sh:someValue``, ``sh:memberShape``,
# ``sh:reifierShape``, ``sh:condition``).
_SHAPE_EXPECTING_PREDICATES = (SH.someValue, SH.memberShape, SH.reifierShape, SH.condition)


def _type_shape_values(graph: Graph) -> Graph:
    """Add an ``rdf:type`` (``sh:PropertyShape`` for a node with ``sh:path``, else ``sh:NodeShape``) to every shape that a
    shape-expecting predicate refers to and that has no explicit shape type, so the stored meta-shapes file states them. A
    ``sh:condition`` value may be a SHACL list, whose members are the references. Only adds; the output is byte-for-byte what the
    earlier validator's loader needed."""
    result = Graph()
    for prefix, namespace in graph.namespaces():
        result.bind(prefix, namespace)
    for triple in graph:
        result.add(triple)
    for predicate in _SHAPE_EXPECTING_PREDICATES:
        for _s, _p, value in graph.triples((None, predicate, None)):
            references = list(graph.items(value)) if (value, RDF.first, None) in graph else [value]
            for node in references:
                if isinstance(node, ox.Literal):
                    continue  # a malformed value: left for the meta-shapes to report
                if {SH.NodeShape, SH.PropertyShape} & set(graph.objects(node, RDF.type)):
                    continue
                kind = SH.PropertyShape if (node, SH.path, None) in graph else SH.NodeShape
                result.add((node, RDF.type, kind))
    return result


def shacl_vocabulary_terms() -> list[str]:
    """The IRIs in the SHACL namespace that the shipped vocabulary defines (as a subject), sorted."""
    vocabulary = Graph()
    for path in VOCABULARY_SOURCE_PATHS:
        vocabulary.parse(path, format="turtle")
    return sorted({str(s.value) for s, _p, _o in vocabulary if isinstance(s, ox.NamedNode) and s.value.startswith(SH_NAMESPACE)})


def unknown_term_shape_turtle(terms: Iterable[str]) -> str:
    """The shape that warns about an IRI in the SHACL namespace outside ``terms``, as a predicate or an object. It is written here
    and not in the asset because its list of terms comes from the vocabulary, so it cannot drift from it. The target selects only the
    nodes that use an unknown term, so a conforming graph runs the constraint on none (the variable cannot be ``?this``, which a
    node-expression target pre-binds to the shape); the constraint then names the terms."""
    known = ", ".join(f"<{t}>" for t in terms)
    return f"""
@prefix sh: <{SH_NAMESPACE}> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix stsh: <https://github.com/hidden-graph/starlayer/ns/shacl#> .

stsh:UnknownShaclTermShape
	a sh:NodeShape ;
	rdfs:label "No unknown term in the SHACL namespace"@en ;
	rdfs:comment "An IRI in the SHACL namespace that the shipped vocabulary does not define, used as a predicate or as an object (a misspelt sh:minCountt or sh:Shape2). Generated by scripts/build_meta_shapes.py from the vocabulary; IRIs in other namespaces are never reported."@en ;
	sh:severity sh:Warning ;
	sh:targetNode [ sh:select \"\"\"
		SELECT DISTINCT ?user WHERE {{
			{{ ?user ?term ?o }} UNION {{ ?user ?p ?term . FILTER (isIRI(?term)) }}
			FILTER (STRSTARTS(STR(?term), "{SH_NAMESPACE}") && ?term NOT IN ({known}))
		}}
	\"\"\" ] ;
	sh:sparql [
		sh:select \"\"\"
			SELECT DISTINCT $this ?value ?message WHERE {{
				{{ $this ?value ?o }} UNION {{ $this ?p ?value . FILTER (isIRI(?value)) }}
				FILTER (STRSTARTS(STR(?value), "{SH_NAMESPACE}") && ?value NOT IN ({known}))
				BIND (CONCAT("sh:", STRAFTER(STR(?value), "{SH_NAMESPACE}"), " is not a term of the SHACL vocabulary") AS ?message)
			}}
		\"\"\" ;
	] .
"""


def build_meta_shapes_graph(extra_graphs: Iterable[Any] = (), *, wg_graph: Graph | None = None) -> Graph:
    """Assemble the complete meta-shapes graph: the Working Group's file, ``shacl12-validation-shapes.ttl``, the
    overrides above, and every graph in ``extra_graphs`` (plain triple addition, so a caller such as a SHACL editor
    can add its own rules without this function knowing what they are for). ``wg_graph`` is for tests: a
    Working Group graph already loaded, copied with its blank nodes unchanged so the result can be compared with it."""
    if wg_graph is None:
        graph = load_wg_shapes()
    else:
        graph = Graph()
        for triple in wg_graph:
            graph.add(triple)
    graph.parse(VALIDATION_SHAPES_PATH, format="turtle")
    graph.parse(data=unknown_term_shape_turtle(shacl_vocabulary_terms()), format="turtle")
    _add_overrides(graph)
    graph = _type_shape_values(graph)
    for extra in extra_graphs:
        for triple in extra:
            graph.add(triple)
    return graph
