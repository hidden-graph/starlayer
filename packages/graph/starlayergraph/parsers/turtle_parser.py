"""
starlayergraph.parsers.turtle_parser

Parses Turtle 1.2 text into an rdflib.Graph, expanding RDF 1.2 quoted-triple
syntax (<<( )>>, << >>, {| |}, ~ reifier) into the starlayergraph internal encoding:

  Triple terms  → content-addressed URIRefs under tt: namespace
  Anon reifiers → plain BNodes (anonymous by nature)
  Named reifiers → unchanged (already named URIs)

Entry point: StarLayerTurtleParser().parse(data)
"""

import re
from urllib.parse import urljoin
from rdflib import Graph, URIRef, BNode, Literal
from rdflib.namespace import RDF, XSD
from starlayergraph.parsers import lexer as _lexer
from starlayergraph.parsers import syntax as _syntax
from starlayergraph.parsers.errors import TurtleSyntaxError
from starlayergraph.model.encoding import TT_NS, RR_NS, tt_hash, term_key, encode_dirlang_datatype

# Legacy sl: constants — kept for the intermediate build phase only;
# stripped from the final graph by _skolemize_encoding().
SL_NS          = 'https://github.com/hidden-graph/starlayergraph/ns#'
SL_TRIPLE_TERM = URIRef(SL_NS + 'TripleTerm')
SL_REIFICATION = URIRef(SL_NS + 'Reification')
RDF_REIFIES    = URIRef('http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies')


# ---------------------------------------------------------------------------
# Pure helpers — no per-parse state
# ---------------------------------------------------------------------------

def _is_qt_term(val):
    """True if val is <<( s p o )>> triple-term syntax."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if s.startswith('<<(') and s.endswith(')>>'):
        return True
    if s.startswith('<<') and s.endswith('>>'):
        inner = s[2:-2].strip()
        return inner.startswith('(') and inner.endswith(')')
    return False


def _is_qt_reif(val):
    """True if val is << s p o >> reification-shorthand syntax (no parens)."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if not (s.startswith('<<') and s.endswith('>>')):
        return False
    if s.startswith('<<('):
        return False
    inner = s[2:-2].strip()
    return not (inner.startswith('(') and inner.endswith(')'))


def _is_qt(val):
    return _is_qt_term(val) or _is_qt_reif(val)


def _is_bnode_list(val):
    """True if val is `[ ... ]` anonymous blank-node property-list syntax."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    return s.startswith('[') and s.endswith(']')


def _has_reifier(val):
    """True if val is << s p o ~ r >> (inline reifier)."""
    if not isinstance(val, str):
        return False
    s = val.strip()
    if not (s.startswith('<<') and s.endswith('>>')):
        return False
    if s.startswith('<<('):
        return False
    inner = s[2:-2].strip()
    if inner.startswith('(') and inner.endswith(')'):
        return False
    if '~' not in inner:
        return False
    _, r1 = _lexer.next_token(inner)
    _, r2 = _lexer.next_token(r1)
    _, r3 = _lexer.next_token(r2)
    return r3.strip().startswith('~')


def _get_reifier_parts(val):
    """Extract (triple_term_str, reifier_str_or_None) from << s p o ~ r >>."""
    inner = val.strip()[2:-2].strip()
    ts, r1 = _lexer.next_token(inner)
    tp, r2 = _lexer.next_token(r1)
    to, r3 = _lexer.next_token(r2)
    after_tilde = r3.strip()[1:].strip()
    return f'<<( {ts} {tp} {to} )>>', (after_tilde if after_tilde else None)


def _norm_qt(val):
    """Normalise any quoted-triple form to <<( s p o )>> for use as a cache key."""
    s = val.strip()
    inner = s[2:-2].strip()
    if inner.startswith('(') and inner.endswith(')'):
        inner = inner[1:-1].strip()
    ts, r1 = _lexer.next_token(inner)
    tp, r2 = _lexer.next_token(r1)
    to, r3 = _lexer.next_token(r2)
    while r3.startswith('^^') or (r3.startswith('@') and len(r3) > 1 and r3[1].isalpha()):
        suffix, r3 = _lexer.next_token(r3)
        to += suffix
        r3 = r3.strip()
    if r3.strip():
        # RDF 1.2 grammar: reifiedTriple/tripleTerm hold exactly subject,
        # predicate, object - nothing more (e.g. "<< :g :s :p :o >>" is an
        # over-long reified triple, not a 4-term form of anything).
        raise TurtleSyntaxError(
            f'too many terms inside <<...>>/<<(...)>> - expected exactly subject, '
            f'predicate, object, found extra {r3.strip()!r}',
            val, pos=0,
        )
    return f'<<( {ts} {tp} {to} )>>'


def _unescape(s):
    """Expand Turtle string escape sequences including \\uXXXX and \\UXXXXXXXX."""
    result = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            if   c == 'n':  result.append('\n'); i += 2
            elif c == 't':  result.append('\t'); i += 2
            elif c == 'r':  result.append('\r'); i += 2
            elif c == 'b':  result.append('\b'); i += 2
            elif c == 'f':  result.append('\f'); i += 2
            elif c == '"':  result.append('"');  i += 2
            elif c == "'":  result.append("'");  i += 2
            elif c == '\\': result.append('\\'); i += 2
            elif c == 'u' and i + 5 <= len(s):
                hex4 = s[i+2:i+6]
                cp = int(hex4, 16)
                if 0xD800 <= cp <= 0xDFFF:
                    # Turtle's UCHAR directly encodes a Unicode codepoint;
                    # the UTF-16 surrogate range is excluded (surrogates
                    # are a UTF-16 encoding artifact, not a standalone
                    # codepoint) - not even a well-formed high+low
                    # surrogate *pair* combines into one, unlike JSON/JS
                    # \u escapes. Confirmed via the W3C RDF 1.2 Turtle
                    # syntax test suite (turtle12-surrogate*,
                    # turtle12-surrogates-bad-* - see tests/w3c_turtle12/).
                    raise TurtleSyntaxError(
                        f'\\u{hex4} is a UTF-16 surrogate codepoint (U+D800-U+DFFF), '
                        f'not valid as a standalone Unicode codepoint in a \\u escape (RDF 1.2)',
                        s, pos=i,
                    )
                result.append(chr(cp)); i += 6
            elif c == 'U' and i + 9 <= len(s):
                hex8 = s[i+2:i+10]
                cp = int(hex8, 16)
                if 0xD800 <= cp <= 0xDFFF:
                    raise TurtleSyntaxError(
                        f'\\U{hex8} is a UTF-16 surrogate codepoint (U+D800-U+DFFF), '
                        f'not valid as a standalone Unicode codepoint in a \\U escape (RDF 1.2)',
                        s, pos=i,
                    )
                result.append(chr(cp)); i += 10
            else:
                result.append('\\'); result.append(c); i += 2
        else:
            result.append(s[i]); i += 1
    return ''.join(result)


def _split_literal(val):
    """Split a Turtle literal token into (content_str, suffix_str, kind).

    kind is '^^' for typed literals, '@' for language-tagged, '' for plain.
    Correctly skips ^^ and @ sequences that appear inside the quoted string.

    val is normally already a lexer-validated, properly-closed literal token
    by the time this is called (next_token() raises on an unterminated quote
    before ever returning one) - the raise below is defense-in-depth for a
    malformed val reaching this function some other way, not the primary
    place this class of error is caught in the normal parsing pipeline.
    """
    q = val[:3] if val[:3] in ('"""', "'''") else val[0]
    i = len(q)
    while i < len(val):
        if val[i] == '\\':
            i += 2
            continue
        if val[i:i+len(q)] == q:
            content = val[len(q):i]
            rest = val[i+len(q):]
            if rest.startswith('^^'):
                return content, rest[2:].strip(), '^^'
            if rest.startswith('@'):
                return content, rest[1:], '@'
            return content, '', ''
        i += 1
    raise TurtleSyntaxError(f'unterminated {q!r} string', val, pos=len(val))


def _to_node(val, prefix_map, base_uri):
    """Convert a string token or coerced Python value to an rdflib term."""
    if isinstance(val, bool):
        return Literal(val, datatype=XSD.boolean)
    if isinstance(val, Literal):
        # A bare (unquoted) numeric literal - syntax.coerce_object() already
        # classified it into a correctly-typed, lexical-form-preserving
        # Literal (INTEGER/DECIMAL/DOUBLE can't be told apart, nor can the
        # exact source spelling be preserved, once collapsed through a
        # Python int/float - see coerce_object's own docstring). Passed
        # through as-is rather than falling into the generic string
        # handling below, which would re-parse its lexical form as if it
        # were raw Turtle token text.
        return val
    if not isinstance(val, str):
        return Literal(str(val))

    val = val.strip()

    if val.startswith('_:'):
        return BNode(val[2:])

    if val.startswith('<') and val.endswith('>'):
        inner = val[1:-1]
        if base_uri and not re.match(r'^[a-zA-Z][a-zA-Z0-9+\-.]*:', inner):
            return URIRef(urljoin(base_uri, inner))
        return URIRef(inner)

    if val.startswith(('"""', "'''", '"', "'")):
        content, suffix, kind = _split_literal(val)
        text = _unescape(content)
        if kind == '^^':
            # normalize=False preserves the exact lexical form the source
            # document wrote (e.g. "04"^^xsd:integer stays "04", not
            # silently rewritten to the canonical "4") - rdflib's default
            # normalizes numeric/boolean-typed literals to their value's
            # canonical lexical form on construction, which silently
            # violates RDF 1.2's own literal term-equality definition
            # (https://www.w3.org/TR/rdf12-concepts/#dfn-literal-term-equality:
            # two literals are term-equal only if their lexical forms match,
            # not just their value) - a Turtle *parser* must preserve
            # whatever the document actually wrote. Confirmed via the W3C
            # SHACL 1.2 Node Expressions test suite (distinct-termEquality,
            # remove-list-from-list), which construct exactly this
            # value-equal/lexically-different case deliberately.
            return Literal(text, datatype=_to_node(suffix, prefix_map, base_uri), normalize=False)
        if kind == '@':
            if '--' in suffix:
                # RDF 1.2 "text"@lang--dir (rdf:dirLangString). rdflib's Literal
                # has no notion of the --dir suffix and raises on lang=suffix
                # directly, so encode via the internal dirlang: datatype URI
                # instead - decoded back to DirLangString at the StarLayerGraph
                # boundary (see starlayergraph.model.dirlangstring).
                language, _, direction = suffix.rpartition('--')
                # RDF 1.2 Concepts sec 3.4: base direction MUST be exactly
                # "ltr" or "rtl" - lowercase only, no case-insensitive
                # matching (unlike the language tag itself, which RDF 1.2
                # Concepts sec 3.4.1 does case-fold). Confirmed via the W3C
                # RDF 1.2 Turtle syntax test suite (nt-ttl12-langdir-bad-2,
                # "Hello"@en--LTR - see tests/w3c_turtle12/): must be rejected, not
                # silently lowercased and accepted.
                if direction not in ('ltr', 'rtl'):
                    raise ValueError(
                        f'RDF 1.2: base direction must be "ltr" or "rtl", got {direction!r} in @{suffix}'
                    )
                return Literal(text, datatype=encode_dirlang_datatype(language.lower(), direction))
            return Literal(text, lang=suffix)
        return Literal(text)

    if val == 'a':
        return RDF.type

    if ':' in val:
        pref, local = val.split(':', 1)
        if pref in prefix_map:
            return URIRef(prefix_map[pref] + local)
        if val.startswith('http'):
            return URIRef(val)
        return URIRef(val)

    if base_uri:
        # Best-effort relative-reference resolution only - full IRI-reference
        # grammar validation is out of scope here (see module docstring's
        # sibling functions and TurtleSyntaxError's own docstring); a bare
        # token that isn't a valid relative reference either will still
        # produce a URIRef, just possibly a syntactically invalid one.
        return URIRef(urljoin(base_uri, val))

    # No recognized term shape matched (not an IRI, prefixed name, blank
    # node, quoted literal, or "a") and there's no base_uri to attempt a
    # relative-reference resolution against - this is not valid Turtle 1.2,
    # e.g. a stray unquoted token like "totally!bogus$$token". Previously
    # silently became Literal(val) here, which is worse than raising: it
    # makes a malformed document parse "successfully" with wrong data
    # instead of failing where the problem actually is.
    raise TurtleSyntaxError(
        f'unrecognized term {val!r} (not an IRI, prefixed name, blank node, literal, or "a")',
        val, pos=0,
    )


# ---------------------------------------------------------------------------
# Per-parse stateful expander
# ---------------------------------------------------------------------------

class _Expander:
    """Holds mutable state for quoted-triple expansion within a single parse() call."""

    def __init__(self, blank_counter):
        self.blank_counter = blank_counter
        self.qt_cache = {}

    def _alloc(self):
        n = f'_:si_{self.blank_counter[0]}'
        self.blank_counter[0] += 1
        return n

    def _require_plain_blank_node(self, val, role):
        """A `[ ... ]` triple-term/reified-triple component must be an
        *empty* anonymous blank node (RDF 1.2 grammar: ttSubject/rtSubject/
        ttObject/rtObject all admit `BlankNode`, which is BLANK_NODE_LABEL
        or ANON - i.e. a bare `_:label` or empty `[]` - never a
        blankNodePropertyList carrying its own properties, e.g.
        `[ :p :o ]`). Raises if non-empty; otherwise mints and returns a
        fresh, plain blank node label for the empty-`[]` case.
        """
        inner = val.strip()[1:-1].strip()
        if inner:
            raise TurtleSyntaxError(
                f'a blank node with properties is not valid as a triple-term/reified-triple '
                f'{role} (RDF 1.2) - only a plain blank node (_:label or []) is allowed here',
                val, pos=0,
            )
        return self._alloc()

    def _resolve_qt_slot(self, val, *, allow_ground_term, role):
        """Resolve a subject/object slot that might itself be quoted-triple
        syntax, used by both an ordinary triple's own subject/object
        (``expand_qt_in_triple``) and a triple term's/reified-triple's own
        ``s``/``o`` slots (``qt_to_json``) - the same three shapes are legal
        (or not) in both places, so both now share this one implementation
        instead of the two near-duplicate, subtly-inconsistent copies this
        replaced.

        Three shapes, each resolving differently - **the key distinction**:
        a reifier-shorthand term (``<<s p o>>``/``<<s p o ~ r>>``) is legal
        in *any* term slot regardless of ``allow_ground_term``, because it
        does not denote a nested triple term at all - it denotes the
        (fresh or given) *reifier* of the triple ``s p o``, an ordinary
        node exactly like any other IRI or blank node. "A triple term is
        only permitted in object position" (the real RDF 1.2 restriction,
        enforced below for the *ground* ``<<( )>>``/``TRIPLE()`` form) is
        not the right rule for this - previously conflated, which incorrectly
        rejected e.g. ``<< <<:s :p :o>> :p2 :o2 >>`` (a reifier-shorthand
        term whose own subject is *another* reifier-shorthand term - legal)
        the same way as ``<<( <<( :s :p :o )>> :p2 :o2 )>>`` (a ground
        triple term nested in a ground triple term's subject slot -
        actually illegal):

          - ``<<s p o ~ r>>`` (explicit reifier) or ``<<s p o>>`` (bare,
            reifier minted fresh) - always legal. Resolves to the reifier
            node plus the triple term's own encoding triples and the
            ``rdf:reifies`` link.
          - ``<<( s p o )>>``/``TRIPLE(s, p, o)`` (ground triple term) -
            legal only when ``allow_ground_term`` (i.e. in object position);
            raised here with a message pointing at the reifier-shorthand
            alternative when it isn't, since confusing the two is an easy
            mistake to make and the fix is usually "did you mean the
            shorthand form".
          - anything else - returned unchanged; not this function's concern
            (blank-node-property-list / literal rejection stay in the two
            callers, which have slightly different rules for those).

        Returns ``(resolved_val, extra_triples)``.
        """
        if _has_reifier(val):
            tt_str, reif = _get_reifier_parts(val)
            tb, e = self.qt_to_json(tt_str)
            node = reif if reif else self._alloc()
            e = e + [{'subject': node, 'predicate': 'rdf:reifies', 'object': tb}]
            return node, e
        if _is_qt_reif(val):
            return self.qt_reif_to_json(val)
        if _is_qt_term(val):
            if not allow_ground_term:
                raise TurtleSyntaxError(
                    f'RDF 1.2: a ground triple term <<(...)>>/TRIPLE(...) is not '
                    f'valid as a triple-term/reified-triple {role} - nesting a '
                    f'triple term is only legal in object position. A '
                    f'reifier-shorthand <<s p o>>/<<s p o ~ r>> is different and '
                    f'IS legal here: it resolves to an ordinary reifier node, not '
                    f'a nested triple term - use that if this is what you meant.',
                    val, pos=0,
                )
            return self.qt_to_json(_norm_qt(val))
        return val, []

    def qt_to_json(self, qt_str):
        """Return (term_bnode_str, [extra_triples]) for a <<( s p o )>> term.
        Identical triple terms reuse the same bnode via qt_cache."""
        val = _norm_qt(qt_str.strip())
        if val in self.qt_cache:
            return self.qt_cache[val], []

        inner = val[3:-3].strip()
        subj_str, rest  = _lexer.next_token(inner)
        pred_str, rest2 = _lexer.next_token(rest)
        obj_str,  rest3 = _lexer.next_token(rest2)
        while rest3.startswith('^^') or (rest3.startswith('@') and len(rest3) > 1 and rest3[1].isalpha()):
            suffix, rest3 = _lexer.next_token(rest3)
            obj_str += suffix
            rest3 = rest3.strip()

        if pred_str == 'a':
            pred_str = 'rdf:type'

        # RDF 1.2 grammar: the middle "verb" slot of a tripleTerm/
        # reifiedTriple is always an iri (via PrefixedName/IRIREF/'a') -
        # never a literal, blank node, or nested <<...>>/<<(...)>>.
        if _is_qt(pred_str) or pred_str.strip().startswith(('"', "'", '_:', '[')):
            raise TurtleSyntaxError(
                'only an IRI is valid as a triple-term/reified-triple predicate (RDF 1.2)',
                pred_str, pos=0,
            )

        extras = []
        if _is_qt(subj_str):
            subj_str, e = self._resolve_qt_slot(subj_str, allow_ground_term=False, role='subject')
            extras.extend(e)
        elif _is_bnode_list(subj_str):
            subj_str = self._require_plain_blank_node(subj_str, 'subject')
        elif subj_str.strip().startswith(('"', "'")):
            raise TurtleSyntaxError(
                'a literal is not valid as a triple-term/reified-triple subject (RDF 1.2) '
                '- must be an IRI or blank node',
                subj_str, pos=0,
            )

        if _is_qt(obj_str):
            obj_str, e = self._resolve_qt_slot(obj_str, allow_ground_term=True, role='object')
            extras.extend(e)
        elif _is_bnode_list(obj_str):
            obj_str = self._require_plain_blank_node(obj_str, 'object')
        else:
            obj_str = _syntax.coerce_object(obj_str) if obj_str else ''

        bnode = self._alloc()
        self.qt_cache[val] = bnode
        extras.extend([
            {'subject': bnode, 'predicate': 'rdf:subject',   'object': subj_str or ''},
            {'subject': bnode, 'predicate': 'rdf:predicate', 'object': pred_str or ''},
            {'subject': bnode, 'predicate': 'rdf:object',    'object': obj_str  or ''},
            {'subject': bnode, 'predicate': 'rdf:type',      'object': 'sl:TripleTerm'},
        ])
        return bnode, extras

    def qt_reif_to_json(self, qt_str):
        """<< s p o >> → a new Reification bnode that rdf:reifies the TripleTerm."""
        term_bnode, term_extras = self.qt_to_json(_norm_qt(qt_str))
        reif_bnode = self._alloc()
        return reif_bnode, term_extras + [
            {'subject': reif_bnode, 'predicate': 'rdf:reifies', 'object': term_bnode},
        ]

    def expand_qt_in_triple(self, s, p, o):
        """Expand quoted-triple syntax in subject and object positions.
        Returns (s, p, o, extra_triples)."""
        extras = []

        if _is_qt(p):
            raise TurtleSyntaxError(
                'a triple term <<(...)>> or reified-triple shorthand <<...>> is not '
                'valid in predicate position (RDF 1.2 - verb is always an IRI)',
                p, pos=0,
            )

        if _is_qt(s):
            s, e = self._resolve_qt_slot(s, allow_ground_term=False, role='subject')
            extras.extend(e)

        if p == 'rdf:reifies' and _is_qt(o):
            # `X rdf:reifies <<(...)>>` (whether user-written or generated
            # internally by expand_annotation/the ~reifier forms below) -
            # the object here is always meant as a reference to the
            # underlying ground triple term itself, not to "the reifier of
            # o" (that would be circular: reifying a reifier). Deliberately
            # NOT routed through _resolve_qt_slot, which would instead
            # resolve a reifier-shorthand `o` to *its own* reifier node.
            bnode, e = self.qt_to_json(_norm_qt(o))
            extras.extend(e)
            o = bnode
        elif _is_qt(o):
            o, e = self._resolve_qt_slot(o, allow_ground_term=True, role='object')
            extras.extend(e)

        return s, p, o, extras

    def expand_annotation(self, subj_str, pred_str, obj_str, annotations):
        """Return extra triples for {| ... |} annotation specs on (subj, pred, obj)."""
        extras = []
        term_bnode, term_extras = self.qt_to_json(f'<<( {subj_str} {pred_str} {obj_str} )>>')
        extras.extend(term_extras)
        for reifier, ann_body in annotations:
            reif_bnode = reifier if reifier else self._alloc()
            extras.append({'subject': reif_bnode, 'predicate': 'rdf:reifies', 'object': term_bnode})
            if ann_body:
                ann_fields = _syntax.extract_fields(
                    f'{reif_bnode} {ann_body} .', 'triple', self.blank_counter
                )
                if ann_fields and 'triple_set' in ann_fields:
                    for t in _syntax.expand_triple_set(ann_fields['triple_set'], self.blank_counter):
                        es, ep, eo, ee = self.expand_qt_in_triple(
                            t['subject'], t['predicate'], t['object']
                        )
                        ao_str = eo if isinstance(eo, str) else t.get('object_str', str(t['object']))
                        if t.get('annotations'):
                            extras.extend(self.expand_annotation(es, ep, ao_str, t['annotations']))
                        extras.append({'subject': es, 'predicate': ep, 'object': eo})
                        extras.extend(ee)
        return extras


# ---------------------------------------------------------------------------
# Public parser class
# ---------------------------------------------------------------------------

def _skolemize_encoding(g: Graph, rr_counter: list[int] | None = None) -> Graph:
    """Replace intermediate bnodes with stable URIRefs and strip sl: type triples.

    The parser builds a graph with anonymous bnodes and sl:TripleTerm /
    sl:Reification type markers as a convenient intermediate.  This function
    post-processes that graph into the final encoding:

      * Each TT bnode → URIRef(TT_NS + content_hash)   (deduplicated by content)
      * Each anon reifier bnode → URIRef(RR_NS + N)     (sequential, distinct)
      * sl:TripleTerm and sl:Reification type triples → removed
      * sl: namespace binding → removed; tt: and rr: added

    rr_counter, if given, is a shared, mutable ``[next_index]`` box: reifier
    numbering starts from ``rr_counter[0]`` instead of scanning `g` itself,
    and is advanced in place so a second call sharing the same box continues
    numbering where the first left off. Needed by trig12.py's per-GRAPH-block
    parsing (parse_trig12()/parse_trig12_named()): each block is parsed via
    its own, independent call to this function on a fresh Graph, so scanning
    each block's *own* `g` for already-used indices (the rr_counter=None
    default, used for a single whole-document parse) can't see reifiers
    minted for an *earlier* block in the same document - confirmed via the
    W3C SPARQL 1.2 eval-triple-terms/expr-1 fixture's data-4.trig, whose
    ``:g`` and ``:g2`` blocks each independently mint their own unrelated
    "rr:0", which then collide once a query result puts content from both
    graphs in one place (e.g. this fixture's own CONSTRUCT template).
    """
    # --- find TT bnodes (tagged sl:TripleTerm in intermediate graph) ---
    tt_bnodes = frozenset(
        s for s, p, o in g.triples((None, RDF.type, SL_TRIPLE_TERM))
        if isinstance(s, BNode)
    )

    # --- topological sort: inner TTs before outer TTs ---
    sorted_tt: list = []
    visited: set = set()

    def _visit(bn):
        if bn in visited:
            return
        s_n = next(g.objects(bn, RDF.subject),   None)
        o_n = next(g.objects(bn, RDF.object),    None)
        if s_n in tt_bnodes:
            _visit(s_n)
        if o_n in tt_bnodes:
            _visit(o_n)
        visited.add(bn)
        sorted_tt.append(bn)

    for bn in tt_bnodes:
        _visit(bn)

    # --- compute content-addressed URIs ---
    bn_to_uri: dict = {}
    for bn in sorted_tt:
        s_n = next(g.objects(bn, RDF.subject),   None)
        p_n = next(g.objects(bn, RDF.predicate), None)
        o_n = next(g.objects(bn, RDF.object),    None)
        s_key = term_key(bn_to_uri.get(s_n, s_n))
        p_key = term_key(p_n)
        o_key = term_key(bn_to_uri.get(o_n, o_n))
        bn_to_uri[bn] = URIRef(TT_NS + tt_hash(s_key, p_key, o_key))

    # --- map anonymous reifier bnodes to rr:N URIRefs ---
    # Numbering must not collide with any rr:N URIRef *already* present in g
    # - g isn't always a fresh parse (StarLayerGraph.from_rdflib() also
    # routes a SPARQL CONSTRUCT result through this same function, and that
    # result can legitimately contain both a pre-existing rr:N value passed
    # through unchanged from a variable binding *and* a fresh anonymous
    # reifier minted by <<s p o>> shorthand in the template). Numbering
    # fresh reifiers from 0 regardless of what's already in the graph would
    # silently collide the two into one URI, merging two unrelated nodes -
    # confirmed via a real StarLayerGraph.query() CONSTRUCT result mixing a
    # passed-through rr:0 with a freshly-minted one (see the W3C SPARQL 1.2
    # eval-triple-terms/construct-3 and expr-1 fixtures, which both do
    # exactly this). Scanning for the highest already-used index first and
    # continuing after it keeps every rr:N in the final graph distinct.
    if rr_counter is not None:
        _next_rr = rr_counter[0]
    else:
        _existing_rr_indices = [
            int(str(term)[len(RR_NS):])
            for s, p, o in g.triples((None, None, None))
            for term in (s, p, o)
            if isinstance(term, URIRef) and str(term).startswith(RR_NS)
            and str(term)[len(RR_NS):].isdigit()
        ]
        _next_rr = max(_existing_rr_indices, default=-1) + 1

    reif_bnodes = sorted(
        {s for s, p, o in g.triples((None, RDF_REIFIES, None)) if isinstance(s, BNode)},
        key=str,
    )
    for offset, bn in enumerate(reif_bnodes):
        bn_to_uri[bn] = URIRef(RR_NS + str(_next_rr + offset))

    if rr_counter is not None:
        rr_counter[0] = _next_rr + len(reif_bnodes)

    # --- rebuild graph with substitutions, dropping sl: type triples ---
    new_g = Graph()
    for prefix, ns in g.namespaces():
        if str(ns) != SL_NS:
            new_g.bind(prefix, ns)
    new_g.bind('tt', TT_NS)
    if reif_bnodes:
        new_g.bind('rr', RR_NS)

    # g.triples((None, None, None)) rather than bare iteration: Graph.__iter__
    # is just this same call under the hood, but a Dataset/ConjunctiveGraph
    # overrides triples() to respect its own default_union setting, while
    # bare iteration yields 4-tuples (s, p, o, context) that don't unpack
    # into 3 - so this also makes _skolemize_encoding accept a Dataset input
    # (e.g. via StarLayerGraph.from_rdflib()) without crashing, correctly
    # scoped to the default graph only unless the caller set
    # default_union=True, matching Dataset's own declared semantics rather
    # than forcing a union regardless of that setting.
    for s, p, o in g.triples((None, None, None)):
        if p == RDF.type and o in (SL_TRIPLE_TERM, SL_REIFICATION):
            continue
        s2 = bn_to_uri.get(s, s) if isinstance(s, BNode) else s
        o2 = bn_to_uri.get(o, o) if isinstance(o, BNode) else o
        new_g.add((s2, p, o2))

    return new_g


def decode_tt_encoded_triples(g: Graph):
    """Reverse ``_skolemize_encoding``'s tt:HASH encoding, yielding real
    ``(s, p, o)`` triples with any tt:HASH-encoded triple-term value
    restored to a proper ``TripleTerm`` object (nested triple terms
    restored recursively).

    ``_skolemize_encoding``'s output is written directly into the store
    for the rdf-1.1 backend (its content-addressed tt:HASH URIs *are* that
    backend's own on-disk encoding, so no further translation is needed -
    ``super().add()`` is correct there and untouched by this function).
    But that same flat, pre-encoded shape is wrong for the native rdf-1.2
    backend, which needs real ``TripleTerm`` objects handed to
    ``StarLayerGraph.add()`` so its own ``_native_add()`` can write them
    using the backend's real ``<<( )>>`` syntax - this function is the
    bridge that makes that possible, used only on the native-backend path
    (see ``StarLayerGraph.parse()``).

    Reifier skolemization (``rr:N`` URIs standing in for anonymous ``~``
    reifiers) is left untouched - those are ordinary stable node
    identifiers, not triple-term encodings, and need no decoding.
    """
    from starlayergraph.model.triple import TripleTerm

    tt_nodes: dict = {}

    def reconstruct(uri):
        if uri in tt_nodes:
            return tt_nodes[uri]
        s_n = next((o for _, _, o in g.triples((uri, RDF.subject, None))), None)
        p_n = next((o for _, _, o in g.triples((uri, RDF.predicate, None))), None)
        o_n = next((o for _, _, o in g.triples((uri, RDF.object, None))), None)
        s = reconstruct(s_n) if isinstance(s_n, URIRef) and str(s_n).startswith(TT_NS) else s_n
        o = reconstruct(o_n) if isinstance(o_n, URIRef) and str(o_n).startswith(TT_NS) else o_n
        tt = TripleTerm(s, p_n, o)
        tt_nodes[uri] = tt
        return tt

    tt_uris = frozenset(
        s for s, _, _ in g.triples((None, RDF.subject, None))
        if isinstance(s, URIRef) and str(s).startswith(TT_NS)
    )

    for s, p, o in g:
        if s in tt_uris and p in (RDF.subject, RDF.predicate, RDF.object):
            continue  # the encoding fragment itself, not a real triple
        s_out = reconstruct(s) if s in tt_uris else s
        o_out = reconstruct(o) if o in tt_uris else o
        yield (s_out, p, o_out)


class StarLayerTurtleParser:

    def parse(self, data: str, debug: bool = False, base: str = None) -> Graph:
        """Parse Turtle 1.2 text and return an rdflib.Graph.

        The graph uses the starlayergraph internal blank-node encoding for RDF 1.2
        triple terms and reification. Pass debug=True to print intermediate
        representations to stdout.

        base seeds relative-IRI resolution (including a bare "<>") before any
        parsing happens, the same role rdflib's own parsers give their
        publicID/base argument - an in-document @base/BASE directive, if
        present, still overrides it from that point on (current_base is
        reassigned, not merged). Previously there was no way to seed this at
        all from the caller; a document with no @base of its own had no
        working relative-IRI resolution regardless of what publicID the
        caller (e.g. StarLayerGraph.parse(location=..., publicID=...))
        passed in - confirmed via the W3C SHACL 1.2 test suite, whose
        manifest files rely pervasively on "<>" self-reference.
        """
        # line_map[k] is the 1-based line number *in the original data* of the
        # k-th surviving line in data_clean, so a line number computed against
        # the blank/comment-stripped data_clean (by split_statements_with_lines
        # below) can be translated back to where the user would actually look.
        line_map = []
        lines = []
        for orig_lineno, l in enumerate(data.splitlines(), 1):
            if l.strip() and not l.strip().startswith('#'):
                lines.append(l)
                line_map.append(orig_lineno)
        data_clean = '\n'.join(lines)

        def _orig_line(cleaned_line: int) -> int:
            if not line_map:
                return cleaned_line
            idx = min(max(cleaned_line, 1), len(line_map)) - 1
            return line_map[idx]

        blank_counter = [0]
        canonical = {'prefixes': [], 'bases': [], 'triples': []}
        current_base = base
        declared_version = None

        for stmt, cleaned_line in _syntax.split_statements_with_lines(data_clean):
            try:
                typ = _syntax.classify_statement(stmt)
                fields = _syntax.extract_fields(stmt, typ, blank_counter)
            except TurtleSyntaxError as e:
                e.line = _orig_line(cleaned_line)
                raise
            if typ == 'version':
                if 'version' in fields:
                    declared_version = fields['version']
            elif typ == 'prefix' and 'prefix' in fields and 'iri' in fields:
                canonical['prefixes'].append({'prefix': fields['prefix'], 'iri': fields['iri']})
            elif typ == 'base' and 'iri' in fields:
                raw = fields['iri']
                current_base = urljoin(current_base, raw) if current_base else raw
                canonical['bases'].append({'iri': current_base})
            elif typ == 'triple' and 'triple_set' in fields:
                try:
                    triples = _syntax.expand_triple_set(fields['triple_set'], blank_counter)
                except TurtleSyntaxError as e:
                    e.line = _orig_line(cleaned_line)
                    raise
                for t in triples:
                    t['_base_uri'] = current_base
                    t['_line'] = _orig_line(cleaned_line)
                canonical['triples'].extend(triples)

        if debug:
            import json
            print('CANONICAL:', json.dumps(canonical, indent=2, default=str))

        expander = _Expander(blank_counter)
        expanded = []
        for triple in canonical['triples']:
            s, p, o = triple['subject'], triple['predicate'], triple['object']
            t_base = triple.get('_base_uri')
            t_line = triple.get('_line')
            try:
                s, p, o, extras = expander.expand_qt_in_triple(s, p, o)
            except TurtleSyntaxError as e:
                e.line = t_line
                raise
            expanded.append({'subject': s, 'predicate': p, 'object': o, '_base_uri': t_base, '_line': t_line})
            for e in extras:
                e['_base_uri'] = t_base
                e['_line'] = t_line
            expanded.extend(extras)
            if triple.get('annotations'):
                ann_obj = o if isinstance(o, str) else triple.get('object_str', str(triple['object']))
                try:
                    ann_extras = expander.expand_annotation(s, p, ann_obj, triple['annotations'])
                except TurtleSyntaxError as e:
                    e.line = t_line
                    raise
                for e in ann_extras:
                    e['_base_uri'] = t_base
                    e['_line'] = t_line
                expanded.extend(ann_extras)

        if debug:
            import json
            print('EXPANDED:', json.dumps(expanded, indent=2, default=str))

        prefix_map = {p['prefix']: p['iri'] for p in canonical['prefixes']}
        prefix_map.setdefault('rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#')
        prefix_map.setdefault('sl',  SL_NS)   # needed for intermediate sl:TripleTerm triples

        # Add sl:Reification markers so _skolemize_encoding can find reifier bnodes.
        # Carry _base_uri/_line from the rdf:reifies triple so relative subjects
        # resolve correctly and any later error on this marker is still located.
        reif_subjects = {
            (t['subject'], t.get('_base_uri'), t.get('_line'))
            for t in expanded if t['predicate'] == 'rdf:reifies'
        }
        for subj, base, line in reif_subjects:
            expanded.append({'subject': subj, 'predicate': 'rdf:type', 'object': 'sl:Reification',
                              '_base_uri': base, '_line': line})

        g = Graph()
        for prefix, iri in prefix_map.items():
            g.bind(prefix, iri)
        if current_base:
            g.base = current_base

        for triple in expanded:
            t_base = triple.get('_base_uri')
            t_line = triple.get('_line')
            try:
                s_node = _to_node(triple['subject'], prefix_map, t_base)
                p_raw = triple['predicate']
                p_node = RDF.type if p_raw == 'a' else _to_node(p_raw, prefix_map, t_base)
                o_node = _to_node(triple['object'], prefix_map, t_base)
            except TurtleSyntaxError as e:
                e.line = t_line
                raise
            g.add((s_node, p_node, o_node))

        # Stapled on as an attribute rather than changing this method's
        # return type, to avoid touching any of the several existing call
        # sites that unpack the return value directly as a plain Graph (see
        # starlayer_graph.py, trig12.py, tests/unit/test_turtle12_serializer.py).
        # Consumed by StarLayerGraph.parse() for the RDF12ConformanceWarning
        # check (starlayergraph.model.conformance) - a Turtle document may
        # declare VERSION "1.2-basic" but still use a triple term/
        # dirLangString, which that label excludes (RDF 1.2 Concepts sec 2.1).
        g._declared_version = declared_version
        return g
