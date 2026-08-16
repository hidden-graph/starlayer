"""
starlayergraph.serializers.turtle12

Serialize a StarLayerGraph (or a raw rdflib.Graph with the SL internal
encoding) to Turtle 1.2 text, writing triple terms as <<( s p o )>>.

Entry point: serialize_turtle12(graph) -> str

Approach: walk sg.triples() directly — which already returns TripleTerm objects
and filters encoding triples — rather than post-processing rdflib's Turtle output.
This avoids the inline-bnode problem (rdflib collapses bnodes with no outgoing
triples to `[ ]`, losing their ID).
"""

from collections import defaultdict

from rdflib import BNode, Literal, URIRef

from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.encoding import RR_NS, TT_NS
from starlayergraph.model.triple import TripleTerm

SL_NS = 'https://github.com/hidden-graph/starlayergraph/ns#'
_RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
_INTERNAL_NS = {SL_NS, TT_NS, RR_NS}


def _node_to_ttl(node, ns_mgr):
    """Format an rdflib node as a Turtle token using namespace prefixes."""
    if isinstance(node, DirLangString):
        return node.n3(ns_mgr)
    if isinstance(node, URIRef):
        # Anonymous reifier URIs are internal — serialize as blank nodes so
        # re-parsing re-assigns them via _skolemize_encoding for round-trip stability.
        s = str(node)
        if s.startswith(RR_NS):
            return '_:rr_' + s[len(RR_NS):]
        try:
            qn = ns_mgr.qname(s)
            # rdflib returns bare local names for the empty prefix ('' → 'a' not ':a')
            if ':' not in qn:
                qn = ':' + qn
            return qn
        except Exception:
            return f'<{node}>'
    if isinstance(node, BNode):
        return f'_:{node}'
    if isinstance(node, Literal):
        escaped = str(node).replace('\\', '\\\\').replace('"', '\\"')
        if node.language:
            return f'"{escaped}"@{node.language}'
        if node.datatype and str(node.datatype) != 'http://www.w3.org/2001/XMLSchema#string':
            try:
                dt = ns_mgr.qname(str(node.datatype))
            except Exception:
                dt = f'<{node.datatype}>'
            return f'"{escaped}"^^{dt}'
        return f'"{escaped}"'
    return str(node)


def _tt_to_str(tt, ns_mgr):
    """Recursively format a TripleTerm as <<( s p o )>> (object position)."""
    s = _node_to_ttl(tt.subject,  ns_mgr)
    p = _node_to_ttl(tt.predicate, ns_mgr)
    o = _tt_to_str(tt.object, ns_mgr) if isinstance(tt.object, TripleTerm) else _node_to_ttl(tt.object, ns_mgr)
    return f'<<( {s} {p} {o} )>>'


def _tt_to_reif_str(tt, ns_mgr):
    """Format a TripleTerm as << s p o >> (reification shorthand, subject position)."""
    s = _node_to_ttl(tt.subject,  ns_mgr)
    p = _node_to_ttl(tt.predicate, ns_mgr)
    o = _tt_to_str(tt.object, ns_mgr) if isinstance(tt.object, TripleTerm) else _node_to_ttl(tt.object, ns_mgr)
    return f'<< {s} {p} {o} >>'


def _fmt(node, ns_mgr):
    """Format any node (including TripleTerm) as a Turtle string."""
    if isinstance(node, TripleTerm):
        return _tt_to_str(node, ns_mgr)
    return _node_to_ttl(node, ns_mgr)


def _sort_key(node):
    if isinstance(node, URIRef):
        return (0, str(node))
    if isinstance(node, BNode):
        return (1, str(node))
    return (2, str(getattr(node, '_key', lambda: node)()))


_RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')


def _graph_has_dirlangstring(sg) -> bool:
    return any(isinstance(o, DirLangString) for _, _, o in sg.triples((None, None, None)))


def _graph_has_triple_term(sg) -> bool:
    """True if any triple in sg has a TripleTerm-valued object - used to
    decide whether the @version "1.2" directive is needed.

    Prefers the already-populated _tt_nodes registry when available (rdf-1.1
    backend - O(1), no store round-trip) over scanning every triple. Falls
    back to scanning only for a native backend, whose _tt_nodes is always
    empty (StarLayerGraph._build_registry_from_store() is a no-op there -
    no tt:HASH encoding, so no local registry to check at all) - confirmed
    a real bug: `getattr(sg, '_tt_nodes', None)` alone silently omitted the
    version directive for every native-backend graph containing real triple
    terms, since that check is always falsy for native regardless of actual
    content.
    """
    if getattr(sg, '_tt_nodes', None):
        return True
    if not getattr(sg, '_is_native', False):
        return False
    from starlayergraph.model.triple import TripleTerm
    return any(isinstance(o, TripleTerm) for _, _, o in sg.triples((None, None, None)))


def _build_fold_map(sg):
    """Return (fold_map, folded_reifiers, tt_subj_map, tt_subj_reifiers).

    fold_map: (s, p, o) -> list of (reifier, anns, is_named)
        Asserted base triple. Anonymous reifiers → {| |}; named → ~ :r {| |}.
    folded_reifiers: reifier nodes suppressed as explicit subjects (asserted fold).
    tt_subj_map: TripleTerm -> {pred: [obj]}
        Unasserted base triple, anonymous reifier → <<( )>> used as subject.
    tt_subj_reifiers: reifier nodes suppressed as explicit subjects (unasserted fold).

    Not foldable (stay as explicit subjects):
    - Reifier annotates multiple triples (e.g. NYT reported X and Y).
    - Reifier appears as an object elsewhere.
    - Unasserted base triple with a named reifier (identity must be preserved).
    """
    fold_map: dict = defaultdict(list)
    folded_reifiers: set = set()
    tt_subj_map: dict = defaultdict(lambda: defaultdict(list))
    tt_subj_reifiers: set = set()

    objects_elsewhere = {o for _, _, o in sg.triples((None, None, None))}

    reifies_count: dict = defaultdict(int)
    for reifier, _, _ in sg.triples((None, _RDF_REIFIES, None)):
        reifies_count[reifier] += 1

    for reifier, _, tt in sg.triples((None, _RDF_REIFIES, None)):
        if not isinstance(tt, TripleTerm):
            continue
        if reifies_count[reifier] > 1:
            continue
        if reifier in objects_elsewhere:
            continue

        is_named = isinstance(reifier, URIRef) and not str(reifier).startswith(RR_NS)
        base = (tt.subject, tt.predicate, tt.object)
        base_asserted = sg.__contains__((base[0], base[1], base[2]))

        anns = sorted(
            [(p, o) for _, p, o in sg.triples((reifier, None, None))
             if p != _RDF_REIFIES],
            key=lambda x: str(x[0]),
        )

        if base_asserted:
            # Asserted: anonymous → {| |}  /  named → ~ :r {| |}
            fold_map[base].append((reifier, anns, is_named))
            folded_reifiers.add(reifier)
        elif not is_named:
            # Unasserted anonymous → <<( s p o )>> as subject.
            # Multiple anonymous reifiers on the same TT are merged: there is
            # no Turtle 1.2 syntax for multiple unasserted anonymous reifiers
            # in a single statement, and the parser resolves all <<( )>>
            # subject occurrences to the same TripleTerm node anyway.
            for ann_p, ann_o in anns:
                tt_subj_map[tt][ann_p].append(ann_o)
            tt_subj_reifiers.add(reifier)
        # Otherwise → stays as explicit subject

    return fold_map, folded_reifiers, tt_subj_map, tt_subj_reifiers


def serialize_turtle12(graph) -> str:
    """Serialize a StarLayerGraph or rdflib.Graph (with SL encoding) to Turtle 1.2.

    Triple terms are emitted as <<( s p o )>>. Internal encoding triples
    (sl:TripleTerm, sl:Reification, rdf:subject/predicate/object) are omitted.
    Reifier bnodes whose annotated triple is asserted in the graph are folded
    into inline {| ann_pred ann_val |} syntax on the base triple.
    Only namespace prefixes actually used in the graph are emitted.
    """
    from starlayergraph.graph.starlayer_graph import StarLayerGraph

    sg = graph if isinstance(graph, StarLayerGraph) else StarLayerGraph.from_rdflib(graph)
    ns_mgr = sg.namespace_manager

    fold_map, folded_reifiers, tt_subj_map, tt_subj_reifiers = _build_fold_map(sg)

    # --- Pass 1: generate triple lines, collecting used URIRef strings ---
    by_subj: dict = defaultdict(lambda: defaultdict(list))
    used_uris: set = set()

    def _fmt_collect(node, ns_mgr):
        """Format node and record any URIRef string for prefix filtering."""
        if isinstance(node, TripleTerm):
            _collect_tt(node)
            return _tt_to_str(node, ns_mgr)
        if isinstance(node, URIRef) and not str(node).startswith(RR_NS):
            used_uris.add(str(node))
        elif isinstance(node, Literal) and node.datatype:
            used_uris.add(str(node.datatype))
        return _node_to_ttl(node, ns_mgr)

    def _collect_tt(tt):
        for part in (tt.subject, tt.predicate, tt.object):
            if isinstance(part, TripleTerm):
                _collect_tt(part)
            elif isinstance(part, URIRef):
                used_uris.add(str(part))

    suppressed = folded_reifiers | tt_subj_reifiers
    for s, p, o in sg.triples((None, None, None)):
        if s not in suppressed:
            by_subj[s][p].append(o)

    # Unasserted anonymous reifiers: TripleTerm becomes the subject directly.
    for tt, pred_map in tt_subj_map.items():
        for p, objs in pred_map.items():
            for o in objs:
                by_subj[tt][p].append(o)

    def _ann_block(base_triple):
        """Return inline annotation suffix for a foldable asserted base triple.

        Anonymous reifiers → ' {| ann val ; ... |}'
        Named reifiers     → ' ~ :r {| ann val |}' or ' ~ :r' if no annotations
        Multiple reifiers  → blocks concatenated with a space between them
        """
        entries = fold_map.get(base_triple)
        if not entries:
            return ''
        blocks = []
        for reifier, anns, is_named in entries:
            ann_parts = []
            for ann_p, ann_o in anns:
                used_uris.add(str(ann_p))
                ann_parts.append(f'{_fmt_collect(ann_p, ns_mgr)} {_fmt_collect(ann_o, ns_mgr)}')
            ann_str = ' ; '.join(ann_parts)
            if is_named:
                r_str = _fmt_collect(reifier, ns_mgr)
                blocks.append(f'~ {r_str} {{| {ann_str} |}}' if ann_str else f'~ {r_str}')
            else:
                blocks.append(f'{{| {ann_str} |}}' if ann_str else '{|  |}')
        return ' ' + ' '.join(blocks)

    triple_lines = []
    for subj in sorted(by_subj.keys(), key=_sort_key):
        if isinstance(subj, TripleTerm):
            _collect_tt(subj)
            s_str = _tt_to_reif_str(subj, ns_mgr)
        else:
            s_str = _fmt_collect(subj, ns_mgr)
        pred_items = sorted(by_subj[subj].items(), key=lambda x: str(x[0]))
        n_preds = len(pred_items)

        for i, (pred, objs) in enumerate(pred_items):
            used_uris.add(str(pred))
            p_str = _fmt(pred, ns_mgr)
            is_last_pred = (i == n_preds - 1)
            o_parts = []
            for o in objs:
                o_str = _fmt_collect(o, ns_mgr)
                ann = _ann_block((subj, pred, o))
                o_parts.append(o_str + ann)
            o_combined = ', '.join(o_parts)
            end = ' .' if is_last_pred else ' ;'

            if i == 0:
                triple_lines.append(f'{s_str} {p_str} {o_combined}{end}')
            else:
                triple_lines.append(f'    {p_str} {o_combined}{end}')

        triple_lines.append('')

    # --- Pass 2: emit version declaration and used prefix declarations ---
    prefix_lines = []
    if _graph_has_triple_term(sg) or _graph_has_dirlangstring(sg):
        prefix_lines.append('@version "1.2" .')
    for prefix, ns_uri in sorted(sg.namespaces(), key=lambda x: x[0]):
        ns = str(ns_uri)
        if ns in _INTERNAL_NS:
            continue
        if any(u.startswith(ns) for u in used_uris):
            prefix_lines.append(f'@prefix {prefix}: <{ns_uri}> .')

    if _RDF_NS not in {str(ns) for _, ns in sg.namespaces()}:
        prefix_lines.append(f'@prefix rdf: <{_RDF_NS}> .')

    prefix_lines.append('')

    return '\n'.join(prefix_lines + triple_lines)


def serialize_longturtle12(graph) -> str:
    """Serialize a StarLayerGraph to longturtle 1.2 — one triple per line.

    Identical to turtle12 but with no subject/predicate grouping: every triple
    is emitted as ``s p o .`` on its own line.  Prefix declarations and the
    ``@version`` directive are emitted the same way as turtle12.
    """
    from starlayergraph.graph.starlayer_graph import StarLayerGraph

    sg = graph if isinstance(graph, StarLayerGraph) else StarLayerGraph.from_rdflib(graph)
    ns_mgr = sg.namespace_manager

    used_uris: set = set()

    def _collect_tt(tt):
        for part in (tt.subject, tt.predicate, tt.object):
            if isinstance(part, TripleTerm):
                _collect_tt(part)
            elif isinstance(part, URIRef):
                used_uris.add(str(part))

    def _fmt_collect(node):
        if isinstance(node, TripleTerm):
            _collect_tt(node)
            return _tt_to_str(node, ns_mgr)
        if isinstance(node, URIRef) and not str(node).startswith(RR_NS):
            used_uris.add(str(node))
        elif isinstance(node, Literal) and node.datatype:
            used_uris.add(str(node.datatype))
        return _node_to_ttl(node, ns_mgr)

    triple_lines = []
    for s, p, o in sorted(sg.triples((None, None, None)), key=lambda t: (_sort_key(t[0]), str(t[1]), _sort_key(t[2]))):
        used_uris.add(str(p))
        triple_lines.append(f'{_fmt_collect(s)} {_fmt(p, ns_mgr)} {_fmt_collect(o)} .')

    triple_lines.append('')

    prefix_lines = []
    if _graph_has_triple_term(sg) or _graph_has_dirlangstring(sg):
        prefix_lines.append('@version "1.2" .')
    for prefix, ns_uri in sorted(sg.namespaces(), key=lambda x: x[0]):
        ns = str(ns_uri)
        if ns in _INTERNAL_NS:
            continue
        if any(u.startswith(ns) for u in used_uris):
            prefix_lines.append(f'@prefix {prefix}: <{ns_uri}> .')

    if _RDF_NS not in {str(ns) for _, ns in sg.namespaces()}:
        prefix_lines.append(f'@prefix rdf: <{_RDF_NS}> .')

    prefix_lines.append('')

    return '\n'.join(prefix_lines + triple_lines)
