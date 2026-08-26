"""starShacl's own meta-shacl preflight, replacing reliance on pySHACL's
``meta_shacl`` kwarg.

pySHACL's own ``meta_shacl=True`` mechanism has no extension point: it
always validates a shapes graph against its own hardcoded,
process-cached ``shacl-shacl.pickle`` (confirmed by reading
``pyshacl/entrypoints.py::meta_validate``/``with_metashacl_shacl_graph_cache``
- there is no parameter to supply additional or replacement meta-shapes).
Since that bundled meta-shapes graph predates SHACL 1.2, it produces two
confirmed problems under starShacl's default ``meta_shacl=True``:

1. The 11 brand-new SHACL 1.2 predicates (``sh:someValue``,
   ``sh:uniqueValuesFor``, etc.) have no rule at all, so malformed uses
   silently pass.
2. 8 shadowed predicates whose value space SHACL 1.2 *widened* -
   list-valued ``sh:class``/``sh:datatype``/``sh:nodeKind``, path-valued
   ``sh:equals``/``sh:disjoint``/``sh:lessThan``/``sh:lessThanOrEquals``,
   and ``sh:closed sh:ByTypes`` - are *actively rejected*, since pySHACL's
   bundled meta-shapes still enforce the old SHACL 1.0/1.1 single-value
   shape (confirmed empirically: ``sh:class ( ex:A ex:B )`` raises
   ``ReportableRuntimeError`` under default settings even though
   ``starshacl/native_components.py`` fully supports it).

``build_meta_shapes_graph`` assembles a corrected, extensible replacement:
pySHACL's own base graph with exactly those 8 now-too-strict triples
removed (SHACL constraints combine via AND, so a relaxed rule added
*alongside* an unremoved strict one would not help), plus starShacl's own
supplementary rules (``starshacl/assets/shacl12-validation-shapes.ttl``,
``shacl12-presentation-shapes.ttl``), plus any caller-supplied extra
graphs - e.g. a downstream SHACL editor's own domain-specific rules,
merged in the same way. ``meta_validate`` runs this assembled graph
directly through ``pyshacl.validate()`` (not through the ``meta_shacl``
kwarg), so starShacl's preflight fully replaces pySHACL's own rather than
running both (which would still reject the 8 widened forms via pySHACL's
unmodified check).
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from typing import Any

from rdflib import RDF, BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL

SH = Namespace("http://www.w3.org/ns/shacl#")

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_VALIDATION_SHAPES_PATH = os.path.join(_ASSETS_DIR, "shacl12-validation-shapes.ttl")
_PRESENTATION_SHAPES_PATH = os.path.join(_ASSETS_DIR, "shacl12-presentation-shapes.ttl")

_SHSH_SHAPE_SHAPE = URIRef("http://www.w3.org/ns/shacl-shacl#ShapeShape")
_SHSH_PROPERTY_SHAPE_SHAPE = URIRef("http://www.w3.org/ns/shacl-shacl#PropertyShapeShape")

# The 8 SHACL 1.0/1.1-era rules in pySHACL's own bundled shacl-shacl.ttl
# that are now too strict for SHACL 1.2's widened value spaces - each
# located dynamically via (shsh:ShapeShape, sh:property, ?bn) + (?bn,
# sh:path, <predicate>), never by hardcoding a blank node identifier
# (confirmed empirically: rdflib assigns fresh blank node IDs on every
# separate parse of the same source file, so a hardcoded ID would never
# match a freshly loaded copy).
_TOO_STRICT_PATHS: tuple[Any, ...] = (
    SH["class"],
    SH.datatype,
    SH.nodeKind,
    SH.disjoint,
    SH.equals,
    SH.lessThan,
    SH.lessThanOrEquals,
    SH.closed,
)


def _remove_blank_node_subtree(graph: Graph, node: Any, _seen: set[Any] | None = None) -> None:
    """Remove ``node``'s own triples, and (recursively) the triples of any
    blank node it points to - so excising a property-shape blank node also
    removes structure hanging off it (e.g. ``sh:in``'s list), not just the
    blank node's own top-level triples, leaving no orphaned garbage behind.
    """
    if _seen is None:
        _seen = set()
    if node in _seen or not isinstance(node, BNode):
        return
    _seen.add(node)
    for p, o in list(graph.predicate_objects(node)):
        graph.remove((node, p, o))
        _remove_blank_node_subtree(graph, o, _seen)


def _load_pyshacl_base_meta_shapes() -> Graph:
    """A fresh, independent copy of pySHACL's own bundled SHACL-of-SHACL
    meta-shapes graph, loaded directly from its ``shacl-shacl.ttl`` asset
    (not the pickle pySHACL's own ``meta_shacl`` mechanism uses, avoiding
    any dependence on pickle-format compatibility across pySHACL versions;
    not pySHACL's own process-wide cached graph object either, so nothing
    here ever mutates what a caller using plain ``pyshacl.validate(...,
    meta_shacl=True)`` directly would see).
    """
    import pyshacl

    pyshacl_dir = os.path.dirname(pyshacl.__file__)
    shacl_shacl_ttl = os.path.join(pyshacl_dir, "assets", "shacl-shacl.ttl")
    graph = Graph()
    graph.parse(shacl_shacl_ttl, format="turtle")
    return graph


def _strip_too_strict_base_rules(graph: Graph) -> Graph:
    """Remove the 8 SHACL 1.0/1.1-era rules documented on
    ``_TOO_STRICT_PATHS`` from ``graph`` (mutated in place), so
    starShacl's own replacement rules (``shacl12-validation-shapes.ttl``'s
    ``stsh:ShapeShapeOverrides``) are the only ones left governing those
    paths - if the old triple weren't removed, SHACL's AND-combination of
    multiple ``sh:property`` constraints on the same path would mean a
    valid SHACL 1.2 shape still had to *also* satisfy the old, narrower
    rule to conform, defeating the relaxation entirely.

    Also makes two SHACL 1.2 adjustments for ``sh:expression`` as a
    property-shape path alternative:

    * Strips ``sh:xone (shsh:NodeShapeShape shsh:PropertyShapeShape)``
      from ``shsh:ShapeShape``.  An expression-based property shape has no
      ``sh:path``, so it passes ``shsh:NodeShapeShape``'s ``sh:path
      maxCount 0`` *and* the new ``shsh:PropertyShapeShape`` (which now
      accepts ``sh:expression``), meaning both xone branches are satisfied
      and the xone fires.  Replaced by ``sh:or`` in
      ``shacl12-validation-shapes.ttl``.

    * Strips ``shsh:PropertyShapeShape``'s ``sh:path minCount 1`` rule so
      expression-based property shapes are not unconditionally rejected.
      Replaced by ``sh:or (sh:path | sh:expression)`` in
      ``shacl12-validation-shapes.ttl``, keeping the shape non-trivial.
    """
    for path in _TOO_STRICT_PATHS:
        for prop_bn in list(graph.objects(_SHSH_SHAPE_SHAPE, SH.property)):
            if (prop_bn, SH.path, path) in graph:
                graph.remove((_SHSH_SHAPE_SHAPE, SH.property, prop_bn))
                _remove_blank_node_subtree(graph, prop_bn)
    # Strip sh:xone from shsh:ShapeShape.  SHACL 1.2 expression-based property
    # shapes (sh:expression instead of sh:path) legitimately satisfy BOTH
    # shsh:NodeShapeShape (no sh:path → maxCount 0 passes) and the new
    # shsh:PropertyShapeShape (sh:expression branch), so sh:xone would fire.
    # Replaced by sh:or in shacl12-validation-shapes.ttl.
    for xone_bn in list(graph.objects(_SHSH_SHAPE_SHAPE, SH.xone)):
        graph.remove((_SHSH_SHAPE_SHAPE, SH.xone, xone_bn))
        _remove_blank_node_subtree(graph, xone_bn)
    # Strip the original sh:path minCount 1 from shsh:PropertyShapeShape so it
    # is no longer trivially violated by expression-based property shapes.
    # The replacement sh:or constraint (path OR expression) is in
    # shacl12-validation-shapes.ttl and keeps the shape non-trivial.
    for prop_bn in list(graph.objects(_SHSH_PROPERTY_SHAPE_SHAPE, SH.property)):
        if (prop_bn, SH.path, SH.path) in graph:
            graph.remove((_SHSH_PROPERTY_SHAPE_SHAPE, SH.property, prop_bn))
            _remove_blank_node_subtree(graph, prop_bn)
    return graph


def build_meta_shapes_graph(extra_graphs: Iterable[Any] = ()) -> Graph:
    """Assemble the complete meta-shapes graph used for starShacl's own
    meta-shacl preflight: pySHACL's own base graph (with the 8 too-strict
    triples removed) plus starShacl's own SHACL 1.2 validation and
    presentation rules plus every graph in ``extra_graphs`` - all unioned
    into one graph via plain triple addition ("they would be merged into
    one shapes graph"), so a caller (e.g. a downstream SHACL editor) can
    freely add its own validation and/or presentation rule sets without
    this function needing to know or care what they're for.
    """
    graph = _strip_too_strict_base_rules(_load_pyshacl_base_meta_shapes())
    graph.parse(_VALIDATION_SHAPES_PATH, format="turtle")
    graph.parse(_PRESENTATION_SHAPES_PATH, format="turtle")
    for extra in extra_graphs:
        for triple in extra:
            graph.add(triple)
    return graph


def meta_validate(shapes_graph: Any, *, extra_graphs: Iterable[Any] = (), **kwargs: Any) -> tuple[bool, Any, str]:
    """Validate ``shapes_graph`` against the assembled meta-shapes graph
    (see ``build_meta_shapes_graph``), replacing starShacl's previous
    reliance on pySHACL's own ``meta_shacl`` kwarg. Raises
    ``pyshacl.errors.ReportableRuntimeError`` with the same message prefix
    pySHACL's own mechanism used, for compatibility with existing callers
    that check for that text.
    """
    import pyshacl
    from pyshacl.errors import ReportableRuntimeError

    # pySHACL's default max_validation_depth (15, pyshacl/pytypes.py) is sized
    # for ordinary data validation. Meta-validation nests shapes-about-shapes
    # much more deeply (e.g. stsh:RuleShape -> stsh:NodeExpressionShape ->
    # shsh:PathNodeShape's own recursive path grammar) and trips pySHACL's
    # "Validation path too deep!" guard (pyshacl/shape.py) well before any
    # real recursion/cycle exists. Confirmed live that even a compound
    # sh:path (sequence + inverse + zeroOrMore) needs depth ~20; 30 leaves
    # headroom for future meta-shape nesting without raising it near
    # pySHACL's own internal precedent of 999 (rule_expand_runner.py).
    kwargs.setdefault("max_validation_depth", 30)

    meta_shapes = build_meta_shapes_graph(extra_graphs)
    conforms, report_graph, report_text = pyshacl.validate(shapes_graph, shacl_graph=meta_shapes, **kwargs)
    if not conforms:
        msg = f"SHACL File does not validate against the SHACL Shapes SHACL (MetaSHACL) file.\n{report_text}"
        raise ReportableRuntimeError(msg)
    return conforms, report_graph, report_text


def _collect_query_prefixes(shapes_graph: Any, query_node: Any) -> dict[str, Any]:
    """Resolve the prefix map a ``sh:select``/``sh:ask``/``sh:construct``
    query at ``query_node`` would actually see at real execution time -
    same algorithm as pySHACL's own
    ``SPARQLQueryHelper.collect_prefixes()``, reimplemented directly
    against a plain shapes graph rather than through a full ``Shape``/
    ``ShapesGraph`` wrapper (unnecessary overhead for a read-only prefix
    lookup - ``shape.sg.graph`` is just the same graph passed in here).

    Falls back to starShacl's own ambient ``sh:ShapesGraph`` discovery
    (``_ambient_shapes_graph_prefixes``) when ``query_node`` has no
    explicit ``sh:prefixes`` reference at all - pySHACL's own mechanism
    never does this on its own (see that function's docstring for why).
    """
    from starshacl.native_components import _ambient_shapes_graph_prefixes

    prefixes: dict[str, Any] = {
        "rdf": URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#"),
        "rdfs": URIRef("http://www.w3.org/2000/01/rdf-schema#"),
        "owl": URIRef("http://www.w3.org/2002/07/owl#"),
    }

    prefixes_vals = set(shapes_graph.objects(query_node, SH.prefixes))
    if not prefixes_vals:
        prefixes.update(_ambient_shapes_graph_prefixes(shapes_graph))
        return prefixes

    g_name = shapes_graph.identifier
    ng_declares = set(shapes_graph.objects(g_name, SH.declare)) if g_name else set()
    onts = set(shapes_graph.subjects(RDF.type, OWL.Ontology))
    ont_declares: set = set()
    for o in onts:
        ont_declares.update(shapes_graph.objects(o, SH.declare))
    global_declares = ng_declares | ont_declares

    for pv in prefixes_vals:
        pfx_declares = set(shapes_graph.objects(pv, SH.declare))
        all_declares = (pfx_declares | ng_declares) if (pfx_declares and pv in onts) else (global_declares | pfx_declares)
        for dec in all_declares:
            prefix_vals = list(shapes_graph.objects(dec, SH.prefix))
            ns_vals = list(shapes_graph.objects(dec, SH.namespace))
            if len(prefix_vals) == 1 and len(ns_vals) == 1:
                prefixes[str(prefix_vals[0])] = URIRef(str(ns_vals[0]))
    return prefixes


def check_sparql_query_text(shapes_graph: Any) -> None:
    """Preflight: every ``sh:select``/``sh:ask``/``sh:construct`` literal
    anywhere in ``shapes_graph`` must be syntactically valid SPARQL text.

    The meta-shapes graph already checks these structurally (cardinality,
    ``xsd:string`` datatype), but never actually parses the string -
    confirmed live that ``sh:ask "this is not valid SPARQL at all !!!"``
    conforms cleanly under the structural check alone. This is a
    Python-level check, not another SHACL shape, because "is this string
    valid SPARQL" isn't RDF-structural - no shape can express it.

    Scans the whole graph for these three predicates directly rather than
    walking ``sh:sparql``/``sh:validator``/``sh:selectValidator``-style
    parent structures individually - ``sh:select``/``sh:ask``/
    ``sh:construct`` are the same predicates regardless of which kind of
    parent node carries them (an ordinary ``sh:sparql`` constraint, or a
    custom ``sh:ConstraintComponent``'s validator node), so one direct
    scan covers every case uniformly.

    ``$this``/``$value``/``$PATH``-style pre-bound variables need no
    special handling here - they parse as ordinary ``Var`` tokens
    regardless of whether they're bound, which only matters at execution
    time. Prefixes do matter at parse time (an unresolved ``PrefixedName``
    is a real parse error), so each query's prefix map is resolved the
    same way real execution would (see ``_collect_query_prefixes``).

    Raises ``pyshacl.errors.ConstraintLoadError`` (the same exception type
    pySHACL itself raises for other malformed ``sh:sparql`` declarations)
    naming the offending predicate and the underlying parse error.
    """
    from pyshacl.errors import ConstraintLoadError

    import starsparql

    for predicate in (SH.select, SH.ask, SH.construct):
        for query_node, text_literal in shapes_graph.subject_objects(predicate):
            if not isinstance(text_literal, Literal) or not isinstance(text_literal.value, str):
                continue  # not xsd:string - already caught by the meta-shapes structural check
            prefixes = _collect_query_prefixes(shapes_graph, query_node)
            try:
                starsparql.prepare_query_12(str(text_literal), initNs=prefixes)
            except Exception as exc:
                raise ConstraintLoadError(
                    f"{predicate.n3(shapes_graph.namespace_manager)} value is not valid SPARQL: {exc}",
                    "https://www.w3.org/TR/shacl12-sparql/",
                ) from exc
