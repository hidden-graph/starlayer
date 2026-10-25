"""
starlayer.graph.serializers.turtle12

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

from starlayer.graph.graph.prefixes import select_prefixes
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm

SL_NS = 'https://github.com/hidden-graph/starlayergraph/ns#'
_RDF_NS = 'http://www.w3.org/1999/02/22-rdf-syntax-ns#'

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


_PN_CHARS_BASE = (
    'A-Za-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F'
    '\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\U00010000-\U000EFFFF'
)
_PN_CHARS_U = _PN_CHARS_BASE + '_'
_PN_CHARS = _PN_CHARS_U + '\\-0-9\u00B7\u0300-\u036F\u203F-\u2040'
# Turtle PN_LOCAL, without the backslash escapes (a name that needs one is written as a full <IRI>)
_PN_LOCAL = re.compile(
    rf'(?:[{_PN_CHARS_U}:0-9]|%[0-9A-Fa-f]{{2}})'
    rf'(?:(?:[{_PN_CHARS}.:]|%[0-9A-Fa-f]{{2}})*(?:[{_PN_CHARS}:]|%[0-9A-Fa-f]{{2}}))?'
)


def _valid_qname(ns_mgr, iri):
    """The prefixed name for iri, or None when it would not be valid Turtle.

    rdflib's namespace manager will hand out a name whose local part ends in '.' or contains '#';
    written as is, the file does not re-parse to the same IRI (GitHub issue #73).
    """
    try:
        qn = ns_mgr.qname(iri)
    except Exception:
        return None
    local = qn.split(':', 1)[1] if ':' in qn else qn
    if local and not _PN_LOCAL.fullmatch(local):
        return None
    return qn


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
        s = str(node)
        qn = _valid_qname(ns_mgr, s)
        if qn is None:
            return f'<{node}>'
        # rdflib returns bare local names for the empty prefix ('' → 'a' not ':a')
        if ':' not in qn:
            qn = ':' + qn
        return qn
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
            # triple *count*). Escaping backslashes only (not quotes in
            # general - legal per STRING_LITERAL_LONG_QUOTE's own grammar,
            # which allows up to 2 consecutive unescaped quote chars
            # mid-string, and keeping them bare reads better for e.g. an
            # embedded SPARQL query) and keeping literal newlines preserves
            # the original multi-line formatting exactly.
            #
            # A run of 3+ literal quote chars is a different story - that
            # WAS dismissed here as "astronomically unlikely", but turned
            # out not to be: this project's own code-KG extractor feeds
            # this project's own source code back through this serializer,
            # and a docstring *describing* Turtle's own triple-quote syntax
            # (e.g. this very module's sibling syntax.py, whose
            # _split_on_delimiter() docstring literally quotes "```\"\"\"```"
            # inline) genuinely contains an unescaped '"""' run. Left bare,
            # that run is indistinguishable from - and was being misread by
            # this project's own parser as - the literal's real closing
            # delimiter, truncating the string there and leaking the rest
            # of the docstring as bogus top-level syntax. Escaping every
            # quote char in any such run (`\"\"\"` instead of `"""`) breaks
            # it into something no closing-delimiter scan can match, without
            # the grammar requiring this function to understand escape
            # sequences at all. A trailing run of 1-2 quote chars right at
            # the end of the content needs the same treatment for the same
            # reason: left bare, it would merge with the real closing
            # delimiter appended right after it into an unintended 3+ run.
            # One pass over each maximal run of quotes (never a second pass over what the first already escaped, which
            # turned a trailing \\"\\"\\" into an escaped backslash and a bare quote; GitHub issue #58): a run is escaped
            # when it is 3 or more long, or when it ends the content (a bare quote there would merge with the closing delimiter).
            escaped = raw.replace('\\', '\\\\')
            escaped = re.sub(
                r'"+', lambda m: '\\"' * len(m.group()) if len(m.group()) >= 3 or m.end() == len(escaped) else m.group(), escaped
            )
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
            dt_str = _valid_qname(ns_mgr, dt) or f'<{dt}>'
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


def _blank_nodes_in_triple_terms(sg) -> set:
    """Every blank node that is a component of some triple term in the graph, at any depth."""
    found: set = set()

    def walk(term) -> None:
        for part in (term.subject, term.predicate, term.object):
            if isinstance(part, TripleTerm):
                walk(part)
            elif isinstance(part, BNode):
                found.add(part)

    for s, _p, o in sg.triples((None, None, None)):
        for node in (s, o):
            if isinstance(node, TripleTerm):
                walk(node)
    return found


def _demote_unreachable_inline(by_subj, inline_bns, list_heads, list_items, list_cells) -> None:
    """Make sure every blank node written inline (``[ ... ]`` or ``( ... )``) is inside something that is written.

    A blank node referenced as an object exactly once is written inside its parent, and its own subject block is skipped.
    That is only safe if the parent is written. When the one reference comes from the node itself (a self-loop), from a cycle
    of such nodes, or from a node only they point at, nothing at the top level reaches them and their triples were silently
    lost (GitHub issue #55). Find what the named (top-level) subjects reach through inline nodes and lists, and for anything
    left over, give one node of it (in label order, so the output is stable) its own labelled subject block; repeat until
    everything is reached. The demoted node is then written ``_:label`` where it is referenced.

    Mutates ``inline_bns``, ``list_heads``, ``list_items`` and ``list_cells`` in place.
    """

    def chain_from(head) -> list:
        """The cells of the list that starts at ``head``, head first."""
        cells, node = [], head
        while isinstance(node, BNode) and node in list_cells and node not in cells:
            cells.append(node)
            node = by_subj.get(node, {}).get(_RDF_REST, [None])[0]
        return cells

    # every well-formed cell counts as a "head" of its own tail ( 2 ) in list_heads, but only a cell no other list contains is
    # written as a list of its own; an interior cell is written as part of the list it is in
    interior = {cell for head in list_heads for cell in chain_from(head)[1:]}

    def reached_from_top_level() -> set:
        reached: set = set()
        stack = [s for s in by_subj if not (s in inline_bns or s in list_heads or s in list_cells)]
        seen_subjects: set = set()
        while stack:
            subject = stack.pop()
            if subject in seen_subjects:
                continue
            seen_subjects.add(subject)
            for objs in by_subj.get(subject, {}).values():
                for o in objs:
                    if not isinstance(o, BNode):
                        continue
                    if o in list_heads:
                        if o not in reached:
                            reached.add(o)
                            for item in list_items[o]:
                                if isinstance(item, BNode):
                                    stack.append(item)  # an item is itself a node that may be inline
                                    if item in inline_bns or item in list_heads:
                                        reached.add(item)
                    elif o in inline_bns:
                        if o not in reached:
                            reached.add(o)
                            stack.append(o)
        return reached

    while True:
        reached = reached_from_top_level()
        unreached = (inline_bns | (list_heads - interior)) - reached
        if not unreached:
            return
        victim = min(unreached, key=str)
        if victim in inline_bns:
            inline_bns.discard(victim)
        else:  # a list head: stop folding this list; its cells become ordinary subjects with rdf:first / rdf:rest
            for cell in chain_from(victim):
                list_cells.discard(cell)
                list_heads.discard(cell)
                list_items.pop(cell, None)
                interior.discard(cell)


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
    from starlayer.graph.model.triple import TripleTerm
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

        is_named = isinstance(reifier, URIRef)
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


def iter_lines_outside_strings(text):
    """Yield (line, in_string) for every physical line of text (as produced
    by this module's own serialize_turtle12()/serialize_longturtle12()),
    in_string being whether an open (triple- or single-quoted) string
    literal is already active at that line's very first character.

    A caller post-processing already-serialized Turtle text line-by-line
    (e.g. to pull real top-level '@prefix'/'@version' lines out from the
    rest, the way serializers.trig12.serialize_trig12() and
    StarLayerDataset.serialize(format='trig12') both do) must check this
    before treating a line's own leading text as meaningful syntax -
    otherwise a line that merely *starts with* '@prefix'/'@version' while
    still inside an open multi-line string literal (e.g. a docstring
    about Turtle's own directive syntax, word-wrapped so one of its lines
    happens to start that way - confirmed live via this project's own
    code-KG extractor feeding this project's own trig12.py, whose module
    docstring does exactly this, back through itself) is misread as a
    real directive and torn out of the literal it's part of.

    Tracks string state exactly like syntax._split_statements_impl's own
    scan (including its triple-quote-awareness: a lone embedded quote
    char doesn't close a triple-quoted string, only a real matching run
    of three does).
    """
    in_string = False
    string_char = ''
    triple = False
    for line in text.splitlines():
        yield line, in_string
        i = 0
        n = len(line)
        while i < n:
            c = line[i]
            if in_string:
                if c == '\\' and i + 1 < n:
                    # Skip an escaped character as one atomic pair, before
                    # the string_char check below ever sees it - otherwise
                    # an escaped quote sitting directly against the real
                    # closing delimiter is misread as itself starting the
                    # close, one character early. Mirrors
                    # syntax._split_statements_impl's matching fix.
                    i += 2
                    continue
                if c == string_char:
                    if triple:
                        if line[i:i+3] == string_char * 3:
                            i += 3
                            in_string = False
                            continue
                    else:
                        in_string = False
                i += 1
                continue
            if c in ('"', "'"):
                in_string = True
                string_char = c
                if line[i:i+3] == c * 3:
                    triple = True
                    i += 3
                else:
                    triple = False
                    i += 1
                continue
            i += 1


def serialize_turtle12(graph) -> str:
    """Serialize a StarLayerGraph or rdflib.Graph (with SL encoding) to Turtle 1.2.

    Triple terms are emitted as <<( s p o )>>. Internal encoding triples
    (sl:TripleTerm, sl:Reification, rdf:subject/predicate/object) are omitted.
    Reifier bnodes whose annotated triple is asserted in the graph are folded
    into inline {| ann_pred ann_val |} syntax on the base triple.
    Only namespace prefixes actually used in the graph are emitted.

    Args:
        graph: The graph to serialize - a StarLayerGraph, or a plain
            rdflib.Graph wrapped via StarLayerGraph.from_rdflib().

    Returns:
        The Turtle 1.2 serialization of graph.
    """
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

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
        if isinstance(node, URIRef):
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
        for _p, objs in subj_preds.items():
            for o in objs:
                if isinstance(o, BNode):
                    obj_bn_count[o] += 1
    list_heads, list_items, list_cells = _compute_list_heads(by_subj, obj_bn_count)
    inline_bns: set = {
        bn for bn, cnt in obj_bn_count.items()
        if cnt == 1 and bn in by_subj and bn not in list_heads and bn not in list_cells
    }
    # A blank node that also sits inside a triple term keeps its label: <<( _:b ... )>> and [ ... ] would be read back as two
    # different nodes (GitHub issue #73).
    inline_bns -= _blank_nodes_in_triple_terms(sg)
    _demote_unreachable_inline(by_subj, inline_bns, list_heads, list_items, list_cells)

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
    for prefix, ns_uri in select_prefixes(sg.namespaces(), used_uris):
        prefix_lines.append(f'@prefix {prefix}: <{ns_uri}> .')

    # rdf: is declared when something in the output needs it and the graph has no binding for it; not when nothing uses it
    if _RDF_NS not in {str(ns) for _, ns in sg.namespaces()} and any(u.startswith(_RDF_NS) for u in used_uris):
        prefix_lines.append(f'@prefix rdf: <{_RDF_NS}> .')

    prefix_lines.append('')

    return '\n'.join(prefix_lines + triple_lines)


def serialize_longturtle12(graph) -> str:
    """Serialize a StarLayerGraph to longturtle 1.2 — one triple per line.

    Identical to turtle12 but with no subject/predicate grouping: every triple
    is emitted as ``s p o .`` on its own line.  Prefix declarations and the
    ``@version`` directive are emitted the same way as turtle12.

    Args:
        graph: The graph to serialize - a StarLayerGraph, or a plain
            rdflib.Graph wrapped via StarLayerGraph.from_rdflib().

    Returns:
        The longturtle 1.2 serialization of graph.
    """
    from starlayer.graph.graph.starlayer_graph import StarLayerGraph

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
        if isinstance(node, URIRef):
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
    for prefix, ns_uri in select_prefixes(sg.namespaces(), used_uris):
        prefix_lines.append(f'@prefix {prefix}: <{ns_uri}> .')

    # rdf: is declared when something in the output needs it and the graph has no binding for it; not when nothing uses it
    if _RDF_NS not in {str(ns) for _, ns in sg.namespaces()} and any(u.startswith(_RDF_NS) for u in used_uris):
        prefix_lines.append(f'@prefix rdf: <{_RDF_NS}> .')

    prefix_lines.append('')

    return '\n'.join(prefix_lines + triple_lines)
