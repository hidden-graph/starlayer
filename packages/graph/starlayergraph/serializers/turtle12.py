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

import re
from collections import defaultdict

from rdflib import BNode, Literal, URIRef

from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.encoding import RR_NS, TT_NS
from starlayergraph.model.triple import TripleTerm

SL_NS = 'https://github.com/hidden-graph/starlayergraph/ns#'
_RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'
_INTERNAL_NS = {SL_NS, TT_NS, RR_NS}

_RDF_TYPE    = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#type')
_XSD_BOOLEAN = 'http://www.w3.org/2001/XMLSchema#boolean'
_XSD_INTEGER = 'http://www.w3.org/2001/XMLSchema#integer'
_XSD_DECIMAL = 'http://www.w3.org/2001/XMLSchema#decimal'
_XSD_STRING  = 'http://www.w3.org/2001/XMLSchema#string'

# Turtle grammar's own bare-token productions (https://www.w3.org/TR/turtle/
# #grammar-production-INTEGER / -DECIMAL) - narrower than XSD's own lexical
# space for each datatype, so a value must match *this*, not just be
# "a valid xsd:integer/xsd:decimal", before it's safe to emit unquoted.
# BooleanLiteral is stricter still: exactly the two keyword tokens, not
# XSD boolean's other legal lexical forms ("1"/"0").
_TURTLE_INTEGER_RE = re.compile(r'^[+-]?[0-9]+$')
_TURTLE_DECIMAL_RE = re.compile(r'^[+-]?[0-9]*\.[0-9]+$')


def _node_to_ttl(node, ns_mgr, compact=True):
    """Format an rdflib node as a Turtle token using namespace prefixes.

    ``compact``: when True (turtle12's own default), literals typed
    xsd:boolean/xsd:integer/xsd:decimal are emitted using Turtle's bare
    BooleanLiteral/INTEGER/DECIMAL tokens where the lexical form allows it,
    and rdf:nil is emitted as '()' - matching rdflib's own always-compact
    Turtle serializer. When False (longturtle12's own choice - fully
    canonical, one-triple-per-line output for diffing), every literal
    keeps its explicit "value"^^xsd:type form and rdf:nil stays spelled
    out, regardless of what its lexical form would otherwise allow.
    """
    if isinstance(node, DirLangString):
        return node.n3(ns_mgr)
    if compact and node == _RDF_NIL:
        return '()'
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
        raw = str(node)
        has_newline = '\n' in raw or '\r' in raw
        if compact and has_newline:
            # Turtle's single-quoted STRING_LITERAL_QUOTE forbids a literal,
            # unescaped newline/CR - only the triple-quoted long form
            # allows one. Previously this branch was never taken at all:
            # _node_to_ttl always emitted the single-quote form regardless
            # of content, so any multi-line literal (e.g. an embedded
            # sh:select/sh:construct SPARQL query, formatted with real
            # newlines) produced syntactically invalid Turtle - confirmed
            # live via round-trip: the malformed output still "parsed"
            # under this project's own lenient parser without raising, but
            # silently diverged from the original graph (caught by
            # rdflib.compare.isomorphic() returning False on a document
            # with embedded multi-line SPARQL text, despite an identical
            # triple *count*). Escaping backslashes only (not the
            # newlines/CRs themselves, and not quotes - a lone `"""` run
            # colliding with the content is astronomically unlikely for
            # real-world text and not worth the extra complexity here) and
            # keeping literal newlines preserves the original multi-line
            # formatting exactly, which also reads far better for
            # something like an embedded SPARQL query than a `\n`-escaped
            # single line would.
            escaped = raw.replace('\\', '\\\\')
            quote = '"""'
        else:
            # longturtle12 (compact=False) deliberately never takes the
            # triple-quote branch above, even for multi-line content - its
            # whole point is one physical line per triple for diffing, so
            # a literal newline here must be escaped instead, not preserved.
            escaped = raw.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r')
            quote = '"'
        if node.language:
            return f'{quote}{escaped}{quote}@{node.language}'
        dt = str(node.datatype) if node.datatype else None
        # Bare-token shorthand only when the literal's own lexical form is
        # actually a valid Turtle BooleanLiteral/INTEGER/DECIMAL token - not
        # just "typed as xsd:boolean/integer/decimal". Both datatypes' own
        # lexical spaces are wider than what Turtle's bare grammar accepts
        # (XSD boolean also allows "1"/"0"; XSD decimal also allows forms
        # like "5." with nothing after the point), and a value can be
        # malformed relative to its declared datatype entirely (rdflib
        # allows constructing e.g. Literal("not-a-number", datatype=
        # XSD.integer) without validating it - confirmed live: serializing
        # that bare produced `ex:p not-a-number .`, not valid Turtle at
        # all, and failed to re-parse). Falling through to the quoted
        # `"value"^^xsd:type` form below is always syntactically valid
        # regardless of how malformed the lexical form is - that's the
        # correct fallback, not a special case.
        if compact and dt == _XSD_BOOLEAN and escaped in ('true', 'false'):
            return escaped
        if compact and dt == _XSD_INTEGER and _TURTLE_INTEGER_RE.match(escaped):
            return escaped
        if compact and dt == _XSD_DECIMAL and _TURTLE_DECIMAL_RE.match(escaped):
            return escaped
        if dt and dt != _XSD_STRING:
            try:
                dt_str = ns_mgr.qname(dt)
            except Exception:
                dt_str = f'<{dt}>'
            return f'{quote}{escaped}{quote}^^{dt_str}'
        return f'{quote}{escaped}{quote}'
    return str(node)


def _pred_to_ttl(node, ns_mgr):
    """Format a predicate node; uses the Turtle 'a' keyword for rdf:type."""
    if node == _RDF_TYPE:
        return 'a'
    return _node_to_ttl(node, ns_mgr)


def _tt_to_str(tt, ns_mgr, compact=True):
    """Recursively format a TripleTerm as <<( s p o )>> (object position)."""
    s = _node_to_ttl(tt.subject,  ns_mgr, compact)
    p = _node_to_ttl(tt.predicate, ns_mgr, compact)
    o = _tt_to_str(tt.object, ns_mgr, compact) if isinstance(tt.object, TripleTerm) else _node_to_ttl(tt.object, ns_mgr, compact)
    return f'<<( {s} {p} {o} )>>'


def _tt_to_reif_str(tt, ns_mgr, compact=True):
    """Format a TripleTerm as << s p o >> (reification shorthand, subject position)."""
    s = _node_to_ttl(tt.subject,  ns_mgr, compact)
    p = _node_to_ttl(tt.predicate, ns_mgr, compact)
    o = _tt_to_str(tt.object, ns_mgr, compact) if isinstance(tt.object, TripleTerm) else _node_to_ttl(tt.object, ns_mgr, compact)
    return f'<< {s} {p} {o} >>'


def _fmt(node, ns_mgr, compact=True):
    """Format any node (including TripleTerm) as a Turtle string."""
    if isinstance(node, TripleTerm):
        return _tt_to_str(node, ns_mgr, compact)
    return _node_to_ttl(node, ns_mgr, compact)


def _sort_key(node):
    if isinstance(node, URIRef):
        return (0, str(node))
    if isinstance(node, BNode):
        return (1, str(node))
    return (2, str(getattr(node, '_key', lambda: node)()))


_RDF_REIFIES = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')
_RDF_FIRST = URIRef(_RDF_NS + 'first')
_RDF_REST = URIRef(_RDF_NS + 'rest')
_RDF_NIL = URIRef(_RDF_NS + 'nil')


def _compute_list_heads(by_subj, obj_bn_count):
    """Find every BNode that's the head of a well-formed, safely-foldable
    RDF list, so serialize_turtle12 can emit Turtle's ``( a b c )``
    collection syntax instead of the expanded ``rdf:first``/``rdf:rest``/
    ``rdf:nil`` chain. Same well-formedness rule rdflib's own Turtle
    serializer uses (``isValidList``/``p_squared`` in
    ``rdflib/plugins/serializers/turtle.py``), reimplemented here against
    this module's own ``by_subj``/reference-count structures rather than a
    live store lookup:

    - The head (and every interior cell after it) must be referenced as an
      object exactly once - a shared/multiply-referenced node can't be
      folded away without losing the fact that something else points at
      it too.
    - Every cell in the chain must have *exactly* ``rdf:first``/``rdf:rest``
      as its only predicates - nothing else attached - so folding the cell
      away (it never gets its own subject block or ``[ ]``) loses no
      information. A cell carrying some other triple must stay expanded.
    - The chain must terminate in ``rdf:nil``, not run off into an
      undefined/non-BNode ``rdf:rest`` value or a missing cell.

    Returns ``(list_heads, list_items, list_cells)``: ``list_heads`` is the
    set of foldable head BNodes; ``list_items`` maps each head to its
    ordered Python list of member nodes; ``list_cells`` is every interior
    cell BNode consumed by some head's chain (must never be rendered as
    its own subject or inline ``[ ]`` block - it exists only to be
    swallowed into whichever head's ``( )`` owns it).
    """
    list_items: dict = {}
    list_cells: set = set()

    for bn, preds in by_subj.items():
        if not isinstance(bn, BNode):
            continue
        if _RDF_FIRST not in preds:
            continue
        if obj_bn_count.get(bn, 0) != 1:
            continue

        items = []
        chain_cells = []
        node = bn
        valid = True
        while True:
            node_preds = by_subj.get(node)
            if node_preds is None or set(node_preds.keys()) != {_RDF_FIRST, _RDF_REST}:
                valid = False
                break
            first_vals = node_preds[_RDF_FIRST]
            rest_vals = node_preds[_RDF_REST]
            if len(first_vals) != 1 or len(rest_vals) != 1:
                valid = False
                break
            items.append(first_vals[0])
            chain_cells.append(node)
            rest = rest_vals[0]
            if rest == _RDF_NIL:
                break
            if not isinstance(rest, BNode) or obj_bn_count.get(rest, 0) != 1:
                valid = False
                break
            node = rest

        if valid:
            list_items[bn] = items
            list_cells.update(chain_cells)

    return set(list_items.keys()), list_items, list_cells


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

    # Compute inline BNodes: BNodes that appear as object exactly once and are
    # subjects in by_subj.  These are rendered as [ ... ] rather than as top-level
    # subject blocks.  Suppressed reifier nodes are never candidates.
    obj_bn_count: dict = defaultdict(int)
    for subj_preds in by_subj.values():
        for p, objs in subj_preds.items():
            for o in objs:
                if isinstance(o, BNode):
                    obj_bn_count[o] += 1
    list_heads, list_items, list_cells = _compute_list_heads(by_subj, obj_bn_count)
    inline_bns: set = {
        bn for bn, cnt in obj_bn_count.items()
        if cnt == 1 and bn in by_subj and bn not in list_heads and bn not in list_cells
    }

    def _fmt_list(head, cur_indent, visiting=frozenset()):
        """Format a foldable RDF list head as Turtle '( a b c )' syntax."""
        inner_visiting = visiting | {head}
        parts = [
            _fmt_with_inline(item, cur_indent, inner_visiting)
            for item in list_items[head]
        ]
        if not parts:
            return '()'
        return '( ' + ' '.join(parts) + ' )'

    def _fmt_inline_bn(bn, cur_indent, visiting=frozenset()):
        """Recursively format a BNode as a Turtle [ ... ] inline block."""
        if bn in visiting:
            return f'_:{bn}'  # cycle guard: fall back to label
        inner_visiting = visiting | {bn}
        inner_indent = cur_indent + "    "
        pred_items = sorted(by_subj[bn].items(), key=lambda x: str(x[0]))
        n_preds = len(pred_items)
        parts = []
        for i, (pred, objs) in enumerate(pred_items):
            if pred != _RDF_TYPE:
                used_uris.add(str(pred))
            p_str = _pred_to_ttl(pred, ns_mgr)
            is_last = (i == n_preds - 1)
            o_parts = []
            for o in objs:
                o_str = _fmt_with_inline(o, inner_indent, inner_visiting)
                ann = _ann_block((bn, pred, o))
                o_parts.append(o_str + ann)
            o_combined = ', '.join(o_parts)
            term = '' if is_last else ' ;'
            parts.append(f'{inner_indent}{p_str} {o_combined}{term}')
        if not parts:
            return '[]'
        return '[\n' + '\n'.join(parts) + f'\n{cur_indent}]'

    def _fmt_with_inline(node, cur_indent, visiting=frozenset()):
        """Format any node; foldable RDF lists become '( )', other
        inlineable BNodes become '[ ... ]' blocks."""
        if isinstance(node, BNode) and node in list_heads:
            return _fmt_list(node, cur_indent, visiting)
        if isinstance(node, BNode) and node in inline_bns:
            return _fmt_inline_bn(node, cur_indent, visiting)
        return _fmt_collect(node, ns_mgr)

    triple_lines = []
    for subj in sorted(by_subj.keys(), key=_sort_key):
        if subj in inline_bns or subj in list_heads or subj in list_cells:
            continue  # rendered inline (as '[ ... ]' or '( ... )') in its parent's block
        if isinstance(subj, TripleTerm):
            _collect_tt(subj)
            s_str = _tt_to_reif_str(subj, ns_mgr)
        else:
            s_str = _fmt_collect(subj, ns_mgr)
        pred_items = sorted(by_subj[subj].items(), key=lambda x: str(x[0]))
        n_preds = len(pred_items)

        for i, (pred, objs) in enumerate(pred_items):
            if pred != _RDF_TYPE:
                used_uris.add(str(pred))
            p_str = _pred_to_ttl(pred, ns_mgr)
            is_last_pred = (i == n_preds - 1)
            o_parts = []
            for o in objs:
                o_str = _fmt_with_inline(o, "    ")
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
        # compact=False throughout: longturtle12 is the fully-canonical
        # format (every literal keeps its explicit "value"^^xsd:type form,
        # rdf:nil stays spelled out) - the deliberate counterpart to
        # turtle12's always-compact output, not just "one triple per line".
        if isinstance(node, TripleTerm):
            _collect_tt(node)
            return _tt_to_str(node, ns_mgr, compact=False)
        if isinstance(node, URIRef) and not str(node).startswith(RR_NS):
            used_uris.add(str(node))
        elif isinstance(node, Literal) and node.datatype:
            used_uris.add(str(node.datatype))
        return _node_to_ttl(node, ns_mgr, compact=False)

    triple_lines = []
    for s, p, o in sorted(sg.triples((None, None, None)), key=lambda t: (_sort_key(t[0]), str(t[1]), _sort_key(t[2]))):
        used_uris.add(str(p))
        triple_lines.append(f'{_fmt_collect(s)} {_fmt(p, ns_mgr, compact=False)} {_fmt_collect(o)} .')

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
