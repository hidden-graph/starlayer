"""starShacl's own meta-shacl preflight, replacing reliance on pySHACL's
``meta_shacl`` kwarg.

pySHACL's own ``meta_shacl=True`` mechanism has no extension point: it
always validates a shapes graph against its own hardcoded,
process-cached ``shacl-shacl.pickle`` (see
``pyshacl/entrypoints.py``'s ``meta_validate``/``with_metashacl_shacl_graph_cache``
- there is no parameter to supply additional or replacement meta-shapes).
Since that bundled meta-shapes graph predates SHACL 1.2, it has two
problems under starShacl's default ``meta_shacl=True``:

1. The 11 brand-new SHACL 1.2 predicates (``sh:someValue``,
   ``sh:uniqueValuesFor``, etc.) have no rule at all, so malformed uses
   silently pass.
2. 8 shadowed predicates whose value space SHACL 1.2 *widened* -
   list-valued ``sh:class``/``sh:datatype``/``sh:nodeKind``, path-valued
   ``sh:equals``/``sh:disjoint``/``sh:lessThan``/``sh:lessThanOrEquals``,
   and ``sh:closed sh:ByTypes`` - are *actively rejected*, since pySHACL's
   bundled meta-shapes still enforce the old SHACL 1.0/1.1 single-value
   shape (e.g. ``sh:class ( ex:A ex:B )`` raises ``ReportableRuntimeError``
   under default settings, even though
   ``starlayer.shacl/native_components.py`` fully supports it).

``build_meta_shapes_graph`` assembles a corrected, extensible replacement:
pySHACL's own base graph with exactly those 8 now-too-strict triples
removed (SHACL constraints combine via AND, so a relaxed rule added
*alongside* an unremoved strict one would not help), plus starShacl's own
supplementary rules (``starlayer.shacl/assets/shacl12-validation-shapes.ttl``,
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
from collections import OrderedDict
from collections.abc import Iterable
from typing import Any

from rdflib import RDF, BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import OWL

SH = Namespace("http://www.w3.org/ns/shacl#")

# meta_validate()'s own result cache, keyed by content (not object
# identity - see _meta_validate_cache_key's own docstring for why that
# distinction matters here specifically). Bounded LRU, same pattern as
# starlayer.graph.model.encoding's _TT_HASH_MEMO.
_META_VALIDATE_CACHE_MAXSIZE = 256
_META_VALIDATE_CACHE: OrderedDict[tuple, tuple] = OrderedDict()

# check_sparql_query_text()'s own SALG structural-validation result cache -
# salg.validate_query() is a real pySHACL validation pass (shapes/ontology
# graphs rebuilt from Turtle each call, RDFS inference enabled), not cheap,
# and otherwise uncached. Keyed directly on the exact inputs that determine
# its result (predicate, the literal query text, and its resolved prefix
# map) - no graph-identity/blank-node concern here the way
# _meta_validate_cache_key has, so no rdfc10_hash needed; these values are
# already directly, stably hashable. Same bounded-LRU shape as
# _META_VALIDATE_CACHE, kept as a separate cache since it's keyed on
# different things (one query's text+prefixes, not a whole shapes graph's
# content).
_SPARQL_STRUCTURE_CACHE_MAXSIZE = 256
_SPARQL_STRUCTURE_CACHE: OrderedDict[tuple, tuple] = OrderedDict()


def _meta_validate_cache_key(shapes_graph_for_meta: Any, kwargs: dict) -> tuple | None:
    """Content-based cache key for one ``meta_validate()`` outcome.

    ``meta_validate()`` is a pure function of (the shapes graph's own
    *content*, the assembled meta-shapes graph's content, the kwargs
    forwarded to ``pyshacl.validate()``) - never of any object's
    identity. That distinction is load-bearing, not academic: a typical
    caller (e.g. ``starontology``'s own ``shapes_graph()``) reparses
    fresh Turtle text into a brand-new ``Graph`` object on every single
    call, so an identity-keyed cache would never hit at all, even for
    byte-for-byte identical content.

    Uses ``starlayer.graph.rdfc.rdfc10_hash`` - the project's existing
    canonical-hashing tool for exactly this "same content, different
    object, possibly different blank node labels" problem - rather than
    hashing a raw serialization, which would spuriously miss whenever
    rdflib mints fresh, arbitrary blank node labels on a re-parse of the
    same source text: two independent reparses of identical shapes
    Turtle produce different N-Triples text but the identical
    ``rdfc10_hash``.

    The assembled meta-shapes graph itself is deliberately *not* hashed
    here - when ``extra_graphs`` is empty (this cache's only scope, see
    ``meta_validate()``'s own gating), ``build_meta_shapes_graph(())``'s
    output is itself always identical within one process, so it
    contributes nothing distinguishing to the key and hashing it too
    would just be another ~20ms paid for free on every call.

    Args:
        shapes_graph_for_meta: The shapes graph being meta-validated.
        kwargs: The keyword arguments that will be forwarded to
            ``pyshacl.validate()``.

    Returns:
        A ``(content_hash, kwarg_items)`` tuple to use as the cache
        key, or ``None`` if ``rdfc10_hash`` itself raises - not
        cacheable; the caller must compute fresh, exactly as if this
        cache didn't exist. ``rdfc10_hash`` has a known pre-existing
        edge case in its canonicalization algorithm (an
        ``AssertionError`` - "blank node ... was never assigned a
        canonical identifier") that a real shapes graph can hit,
        unrelated to this cache. A caching *optimization* must never
        be able to turn a graph that validates correctly into one that
        raises - correctness always wins over the cache hit.
    """
    from starlayer.graph.rdfc import rdfc10_hash

    def _hashable(v: Any) -> Any:
        if isinstance(v, (list, set, frozenset, tuple)):
            return tuple(sorted(str(x) for x in v))
        return v

    kwarg_items = tuple(sorted((k, _hashable(v)) for k, v in kwargs.items()))
    try:
        content_hash = rdfc10_hash(shapes_graph_for_meta)
    except Exception:
        return None
    return (content_hash, kwarg_items)

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_VALIDATION_SHAPES_PATH = os.path.join(_ASSETS_DIR, "shacl12-validation-shapes.ttl")
_PRESENTATION_SHAPES_PATH = os.path.join(_ASSETS_DIR, "shacl12-presentation-shapes.ttl")

_SHSH_SHAPE_SHAPE = URIRef("http://www.w3.org/ns/shacl-shacl#ShapeShape")
_SHSH_PROPERTY_SHAPE_SHAPE = URIRef("http://www.w3.org/ns/shacl-shacl#PropertyShapeShape")

# The 8 SHACL 1.0/1.1-era rules in pySHACL's own bundled shacl-shacl.ttl
# that are now too strict for SHACL 1.2's widened value spaces - each
# located dynamically via (shsh:ShapeShape, sh:property, ?bn) + (?bn,
# sh:path, <predicate>), never by hardcoding a blank node identifier -
# rdflib assigns fresh blank node IDs on every separate parse of the
# same source file, so a hardcoded ID would never match a freshly
# loaded copy.
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
    # real recursion/cycle exists. A compound sh:path (sequence + inverse +
    # zeroOrMore) needs depth ~20; 30 leaves headroom for future
    # meta-shape nesting without raising it near pySHACL's own internal
    # precedent of 999 (rule_expand_runner.py).
    kwargs.setdefault("max_validation_depth", 30)

    # Meta-shacl checks shapes_graph's own structural well-formedness
    # against the bundled meta-shapes - it never touches a data_graph, and
    # has no legitimate reason to need live remote-store behavior at all.
    # Snapshotting into a plain in-memory copy first sidesteps an entire
    # category of pySHACL-internal incompatibilities with a
    # SPARQLUpdateStore-backed graph (rdflib's SPARQLStore refuses to
    # serialize a bound blank node into query text at all - which breaks
    # at least three separate pySHACL-internal code paths this way: a
    # class-membership check, report-stringification for a blank-node
    # focus node, and a query(initBindings=...) call in its own
    # sh:sparql-based constraint evaluator - rather than one fixable root
    # cause). A snapshot is correct here specifically because meta-shacl is
    # a one-time structural preflight on shapes_graph as it stood at this
    # call, not a live, ongoing session against it.
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph as _StarLayerGraph

    if isinstance(shapes_graph, _StarLayerGraph) and getattr(shapes_graph, "_needs_bnode_skolemization", False):
        # use_baseline_representation=True: the whole point of this
        # snapshot is to escape SPARQLUpdateStore's own bound-BNode
        # limitations (see above) - a process-global
        # set_default_representation() must never silently hand back a
        # native-backed graph here instead, which could reintroduce the
        # very incompatibilities this snapshot exists to sidestep.
        snapshot = _StarLayerGraph(use_baseline_representation=True)
        for prefix, ns in shapes_graph.namespaces():
            snapshot.bind(prefix, ns)
        for triple in shapes_graph:
            snapshot.add(triple)
        shapes_graph_for_meta = snapshot
    else:
        shapes_graph_for_meta = shapes_graph

    # Cache keyed on content, scoped to the common extra_graphs=() case
    # (see _meta_validate_cache_key's own docstring for why identity
    # can't be the key, and why meta_shapes itself doesn't need hashing
    # here). Without this cache, every call pays an uncached ~30ms graph
    # (re)build, immediately followed by a full, uncached
    # pyshacl.validate() pass against a deliberately deep
    # (max_validation_depth=30) meta-shapes structure. A real repeated
    # caller (e.g. starontology's own validate_query(), called once per
    # test case against the identical bundled shapes/ontology content
    # every time) pays that full cost on every single call with no
    # caching anywhere.
    cache_key = _meta_validate_cache_key(shapes_graph_for_meta, kwargs) if not extra_graphs else None
    cached = _META_VALIDATE_CACHE.get(cache_key) if cache_key is not None else None
    if cached is not None:
        _META_VALIDATE_CACHE.move_to_end(cache_key)
        conforms, cached_report_graph, report_text = cached
        # A fresh copy, not the cached object itself - a cache hit must
        # never hand out a graph a caller could go on to mutate (e.g. by
        # merging derived triples into it) and have that mutation leak
        # into every future cache hit for the same key.
        report_graph = Graph()
        report_graph += cached_report_graph
    else:
        meta_shapes = build_meta_shapes_graph(extra_graphs)
        conforms, report_graph, report_text = pyshacl.validate(shapes_graph_for_meta, shacl_graph=meta_shapes, **kwargs)
        if cache_key is not None:
            _META_VALIDATE_CACHE[cache_key] = (conforms, report_graph, report_text)
            _META_VALIDATE_CACHE.move_to_end(cache_key)
            if len(_META_VALIDATE_CACHE) > _META_VALIDATE_CACHE_MAXSIZE:
                _META_VALIDATE_CACHE.popitem(last=False)
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
    ``pyshacl.ShapesGraph`` wrapper (unnecessary overhead for a read-only prefix
    lookup - ``shape.sg.graph`` is just the same graph passed in here).

    Falls back to starShacl's own ambient ``sh:ShapesGraph`` discovery
    (``_ambient_shapes_graph_prefixes``) when ``query_node`` has no
    explicit ``sh:prefixes`` reference at all - pySHACL's own mechanism
    never does this on its own (see that function's docstring for why).
    """
    from starlayer.shacl.native_components import _ambient_shapes_graph_prefixes

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


def _sparql_structure_cache_key(predicate: Any, text_literal: Literal, prefixes: dict, is_target: bool) -> tuple:
    """Cache key for one query's structural-validation outcome - the exact
    inputs the *effective* (exemption-applied) result depends on for this
    one embedded query: which predicate carried it (part of the error
    message, not the semantics, but cheap to include and keeps the key
    unambiguous), the literal text itself, its resolved prefix map (two
    otherwise-identical query strings can mean different things under
    different prefix bindings), and ``is_target`` - whether ``$this`` is
    genuinely required to be bound by this query's own pattern (a
    ``sh:target``-declared SPARQL target) or externally pre-bound (every
    other case) changes whether a given unbound-``$this`` violation is a
    real defect, even for byte-identical query text (see
    ``_is_prebound_variable_only_report``'s own docstring).
    """
    return (
        predicate,
        str(text_literal),
        tuple(sorted(((str(k), str(v)) for k, v in prefixes.items()))),
        is_target,
    )


# SHACL-SPARQL's own pre-bound pseudo-variables are supplied externally by
# pySHACL's own execution machinery before a sh:select/sh:ask/sh:construct
# query ever runs - never by anything in the query's own WHERE pattern -
# for a CONSTRAINT or RULE query. salg:noUnboundProjectedVariables (a
# plain, SHACL-unaware generic SPARQL check) has no way to know this, so
# without this exemption it would flag every single `$this`-only validator
# (an extremely common, perfectly valid pattern - e.g.
# `SELECT $this WHERE { FILTER(...) }`, with nothing in the pattern ever
# referencing $this directly) as a false positive - confirmed live via a
# real such query. Matches this function's own pre-existing docstring note
# on these three names (the parse check already didn't need to
# special-case them; the structural check does).
#
# This does NOT hold for a SPARQL-based TARGET (`sh:target [ a
# sh:SPARQLTarget ; sh:select ... ]`) - there, $this is not pre-bound at
# all; it's the query's own job to *compute* which nodes are $this, so an
# unbound $this in a target query is a real defect (the target would never
# select any candidate), not a false positive. Confirmed live: without
# excluding target queries from this exemption, a target query that never
# binds $this silently passed this check. check_sparql_query_text() below
# detects this via `is_target` (whether query_node is itself the object of
# a sh:target triple) and only applies this exemption when it's False.
_SHACL_PREBOUND_VARIABLE_NAMES = frozenset({"this", "value", "PATH"})


def _is_prebound_variable_only_report(report_graph: Graph) -> bool:
    """True iff every violation in a ``salg.validate_query()`` report is a
    ``salg:noUnboundProjectedVariables`` hit naming only a SHACL pre-bound
    pseudo-variable (``$this``/``$value``/``$PATH``) - a false positive
    this check should suppress, not a real defect. ``False`` (never
    suppressed) for an empty result set too - that would mean ``conforms``
    was already ``True`` and there was nothing to call this for in the
    first place.
    """
    from starlayer.sparql import SALG

    results = list(report_graph.subjects(RDF.type, SH.ValidationResult))
    if not results:
        return False
    for result in results:
        component = report_graph.value(result, SH.sourceConstraintComponent)
        if component != SALG.NoUnboundProjectedVariablesConstraintComponent:
            return False
        value = report_graph.value(result, SH.value)
        if value is None or str(value) not in _SHACL_PREBOUND_VARIABLE_NAMES:
            return False
    return True


def check_sparql_query_text(shapes_graph: Any) -> None:
    """Preflight: every ``sh:select``/``sh:ask``/``sh:construct`` literal
    anywhere in ``shapes_graph`` must be syntactically valid SPARQL text,
    and must not have a defect a bare parse can't catch - most notably an
    unbound projected variable (a query that compiles and runs, just
    silently never binds one of its own ``SELECT`` variables).

    The meta-shapes graph already checks these structurally (cardinality,
    ``xsd:string`` datatype), but never actually parses the string -
    confirmed live that ``sh:ask "this is not valid SPARQL at all !!!"``
    conforms cleanly under the structural check alone. This is a
    Python-level check, not another SHACL shape, because "is this string
    valid SPARQL" isn't RDF-structural - no shape can express it.

    A literal that parses is additionally encoded as a ``salg:`` (SPARQL-
    algebra-as-RDF) graph and validated against
    ``starlayer.sparql.salg``'s own general-purpose SPARQL-structure
    shapes - which already has a real check for the unbound-projected-
    variable case (``salg:noUnboundProjectedVariables``), just never
    pointed at a SHACL shape's own embedded query text before this. This
    is real extra validation work (pySHACL with RDFS inference, not just a
    parse), so results are cached per distinct (predicate, text, prefixes)
    - repeated calls against the same shapes graph only pay this once per
    distinct embedded query, the same reason ``meta_validate()`` itself
    caches its own, larger structural pass.

    Scans the whole graph for these three predicates directly rather than
    walking ``sh:sparql``/``sh:validator``/``sh:selectValidator``-style
    parent structures individually - ``sh:select``/``sh:ask``/
    ``sh:construct`` are the same predicates regardless of which kind of
    parent node carries them (an ordinary ``sh:sparql`` constraint, or a
    custom ``sh:ConstraintComponent``'s validator node), so one direct
    scan covers every case uniformly.

    ``$this``/``$value``/``$PATH``-style pre-bound variables need no
    special handling for the parse step - they parse as ordinary ``Var``
    tokens regardless of whether they're bound, which only matters at
    execution time. They *do* need special handling for the structural
    step above: ``salg:noUnboundProjectedVariables`` has no SHACL
    awareness, so a perfectly valid ``$this``-only validator (e.g.
    ``SELECT $this WHERE { FILTER(...) }``, never referencing ``$this``
    directly in its own pattern - these variables are bound externally by
    pySHACL itself, not by anything in the query text) would otherwise be
    a false positive - confirmed live. See
    ``_is_prebound_variable_only_report``'s own docstring for exactly
    which violations this suppresses (only ones naming exactly one of
    these three pre-bound names; anything else still raises). Prefixes do
    matter at parse time (an unresolved ``PrefixedName`` is a real parse
    error), so each query's prefix map is resolved the same way real
    execution would (see ``_collect_query_prefixes``).

    Args:
        shapes_graph: The shapes graph to scan.

    Raises ``pyshacl.errors.ConstraintLoadError`` (the same exception type
    pySHACL itself raises for other malformed ``sh:sparql`` declarations)
    naming the offending predicate and the underlying parse error, or the
    SALG structural-validation report.
    """
    from pyshacl.errors import ConstraintLoadError

    import starlayer.sparql
    from starlayer.sparql import salg

    for predicate in (SH.select, SH.ask, SH.construct):
        for query_node, text_literal in shapes_graph.subject_objects(predicate):
            if not isinstance(text_literal, Literal) or not isinstance(text_literal.value, str):
                continue  # not xsd:string - already caught by the meta-shapes structural check
            prefixes = _collect_query_prefixes(shapes_graph, query_node)
            try:
                query = starlayer.sparql.prepare_query_12(str(text_literal), initNs=prefixes)
            except Exception as exc:
                raise ConstraintLoadError(
                    f"{predicate.n3(shapes_graph.namespace_manager)} value is not valid SPARQL: {exc}",
                    "https://www.w3.org/TR/shacl12-sparql/",
                ) from exc

            # A sh:target-declared SPARQL target's own $this is NOT
            # pre-bound - it's the query's own job to compute it - so the
            # pre-bound-variable exemption below must not apply to it. See
            # _SHACL_PREBOUND_VARIABLE_NAMES's own comment.
            is_target = any(True for _ in shapes_graph.subjects(SH.target, query_node))
            cache_key = _sparql_structure_cache_key(predicate, text_literal, prefixes, is_target)
            cached = _SPARQL_STRUCTURE_CACHE.get(cache_key)
            if cached is not None:
                conforms, report_text = cached
            else:
                encoded_graph, _root = starlayer.sparql.query_to_rdf(query)
                conforms, report_graph, report_text = salg.validate_query(encoded_graph)
                if not conforms and not is_target and _is_prebound_variable_only_report(report_graph):
                    conforms = True
                _SPARQL_STRUCTURE_CACHE[cache_key] = (conforms, report_text)
                _SPARQL_STRUCTURE_CACHE.move_to_end(cache_key)
                if len(_SPARQL_STRUCTURE_CACHE) > _SPARQL_STRUCTURE_CACHE_MAXSIZE:
                    _SPARQL_STRUCTURE_CACHE.popitem(last=False)
            if not conforms:
                raise ConstraintLoadError(
                    f"{predicate.n3(shapes_graph.namespace_manager)} value fails SPARQL structural "
                    f"validation:\n{report_text}",
                    "https://www.w3.org/TR/shacl12-sparql/",
                )
