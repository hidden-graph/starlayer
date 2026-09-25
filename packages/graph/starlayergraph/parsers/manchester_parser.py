"""
starlayergraph.parsers.manchester_parser

Hand-rolled parser for OWL 2 Manchester Syntax (the frame-based
"Class: X SubClassOf: Y" notation), following the OWL 2 Mapping to RDF
Graphs spec to turn each frame/axiom into plain triples - ordinary
rdflib.BNode()s for owl:Restriction/rdf:List cells, and (for an
Annotations:-prefixed clause-list item) owl:Axiom reification - the one
piece of reification machinery this parser does need, unlike
turtle_parser.py's <<( )>>/{| |} triple-term/RDF-1.2-reification syntax,
which Manchester syntax has no equivalent of. Same underlying principle
either way though: an annotation asserts something *about* a triple
without ever replacing the plain triple itself - see _maybe_reify().

Entry point: parse_manchester(text, base=None) -> list[tuple]

Grammar and RDF-mapping coverage is tracked against the real OWL API
parser (not just the W3C REC) in
packages/graph/docs/manchester_syntax_gap_analysis.md - re-derived by
decompiling org.semanticweb.owlapi.manchestersyntax.parser.
ManchesterOWLSyntax (OWL API 5.1.20's own keyword table) plus empirical
probes, rather than from memory of the spec text. That doc is the
authoritative "what's supported and why" reference; the summary:

  Frames: Prefix:, Ontology: (+ Import:), Class:, ObjectProperty:,
  DataProperty:, AnnotationProperty:, Individual:, Datatype:

  Class: clauses: SubClassOf:, SuperClassOf:, EquivalentTo:, DisjointWith:,
  DisjointUnionOf:, HasKey:, Annotations:
  Object/DataProperty clauses: Domain:, Range:, SubPropertyOf:,
  SuperPropertyOf:, EquivalentTo:, DisjointWith:, InverseOf: (object only),
  Characteristics:, SubPropertyChain: (object only), Annotations:
  AnnotationProperty clauses: Domain:, Range:, SubPropertyOf:, Annotations:
  Individual: clauses: Types:, Facts: (positive and negative), SameAs:,
  DifferentFrom:, Annotations:
  Datatype: clauses: EquivalentTo:, Annotations:
  Top-level Misc axioms: EquivalentClasses:, DisjointClasses:,
  EquivalentProperties:, DisjointProperties:, SameIndividual:,
  DifferentIndividuals:

  Class expressions: atomic name, `and`/`or`/`not`/`that` (a confirmed
  synonym for `and`), parenthesised grouping, `some`/`only`/`onlysome`/
  `value`/`Self`, `min n`/`max n`/`exactly n` (qualified and unqualified),
  `{ind1, ind2, ...}` enumeration, `inverse p`.
  Data ranges (DataProperty Range:, Datatype EquivalentTo:): atomic
  datatype, `and`/`or`/`not`, `{lit, lit, ...}` (DataOneOf), facet
  restrictions (`datatype[facet literal, ...]` - `>=`/`<=`/`>`/`<`/
  `length`/`minLength`/`maxLength`/`pattern`).

Two distinct kinds of Annotations: are both supported, mapped differently:

  - The "frame-level" clause - its own standalone section
    (`Class: A Annotations: rdfs:label "Foo"` -> a direct triple on A) -
    confirmed empirically to need no reification at all.
  - An inline per-item prefix inside another clause's comma-separated list
    (`SubClassOf: Annotations: rdfs:comment "why" B, C` - annotates just
    the B axiom, not C, confirmed empirically) - needs full owl:Axiom
    reification (owl:annotatedSource/Property/Target + the annotation
    triples themselves), alongside the plain axiom triple, never instead
    of it. See _parse_item_annotations()/_maybe_reify(). Supported on
    every clause where "one list item -> one axiom triple" holds; *not*
    supported on the six top-level Misc axioms (EquivalentClasses: and
    friends), whose pairwise-chain/AllDisjoint* encoding means a single
    list item doesn't correspond to a single axiom the way it does
    everywhere else - flagged in the gap-analysis doc rather than guessed
    at without an empirical grammar reference to check it against.

See the gap-analysis doc for the full list of what's deliberately not
implemented and why (SWRL Rule:, Misc-axiom inline annotations, a couple
of reserved-but-dead oracle keywords, and the declaration-order
strictness the OWL API's own parser enforces that this one deliberately
doesn't).

Also deliberately unsupported: any use of a name under the default `:`
prefix without an explicit `Prefix: :` declaration for it (no implicit
ontology-IRI-based default is guessed).
"""

from __future__ import annotations

from urllib.parse import urljoin

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from starlayergraph.parsers.errors import ManchesterSyntaxError
from starlayergraph.parsers.syntax import coerce_object

_DEFAULT_PREFIXES = {
    'owl': 'http://www.w3.org/2002/07/owl#',
    'rdf': 'http://www.w3.org/1999/02/22-rdf-syntax-ns#',
    'rdfs': 'http://www.w3.org/2000/01/rdf-schema#',
    'xsd': 'http://www.w3.org/2001/XMLSchema#',
}

_FRAME_KEYWORDS = {
    'Prefix:', 'Ontology:', 'Import:', 'Class:', 'ObjectProperty:',
    'DataProperty:', 'AnnotationProperty:', 'Individual:', 'Datatype:',
    'EquivalentClasses:', 'DisjointClasses:', 'EquivalentProperties:',
    'DisjointProperties:', 'SameIndividual:', 'DifferentIndividuals:',
}

_CLASS_CLAUSES = {
    'SubClassOf:', 'SuperClassOf:', 'EquivalentTo:', 'DisjointWith:',
    'DisjointUnionOf:', 'HasKey:', 'Annotations:',
}
_CLASS_DEFERRED = set()

_OBJPROP_CLAUSES = {
    'Domain:', 'Range:', 'SubPropertyOf:', 'SuperPropertyOf:', 'EquivalentTo:',
    'DisjointWith:', 'InverseOf:', 'Characteristics:', 'SubPropertyChain:',
    'Annotations:',
}
_OBJPROP_DEFERRED = set()

_DATAPROP_CLAUSES = {
    'Domain:', 'Range:', 'SubPropertyOf:', 'SuperPropertyOf:', 'EquivalentTo:',
    'DisjointWith:', 'Characteristics:', 'Annotations:',
}
_DATAPROP_DEFERRED = set()

_ANNPROP_CLAUSES = {'Domain:', 'Range:', 'SubPropertyOf:', 'Annotations:'}
_ANNPROP_DEFERRED = set()

_INDIVIDUAL_CLAUSES = {'Types:', 'Facts:', 'SameAs:', 'DifferentFrom:', 'Annotations:'}
_INDIVIDUAL_DEFERRED = set()

_DATATYPE_CLAUSES = {'EquivalentTo:', 'Annotations:'}
_DATATYPE_DEFERRED = set()

_DATA_FACETS = {
    '>=': XSD.minInclusive, '<=': XSD.maxInclusive,
    '>': XSD.minExclusive, '<': XSD.maxExclusive,
    'length': XSD.length, 'minLength': XSD.minLength, 'maxLength': XSD.maxLength,
    'pattern': XSD.pattern,
}

_CHARACTERISTICS = {
    'Functional': OWL.FunctionalProperty,
    'InverseFunctional': OWL.InverseFunctionalProperty,
    'Transitive': OWL.TransitiveProperty,
    'Symmetric': OWL.SymmetricProperty,
    'Asymmetric': OWL.AsymmetricProperty,
    'Reflexive': OWL.ReflexiveProperty,
    'Irreflexive': OWL.IrreflexiveProperty,
}

_RESTRICTION_KEYWORDS = {'some', 'only', 'onlysome', 'value', 'Self', 'min', 'max', 'exactly'}


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# A bare word (keyword, prefixed name, integer, ...) never legally contains
# any of these - each unambiguously starts a different token form.
_WORD_STOP_CHARS = ('<', '"', '(', ')', ',', '{', '}', '[', ']')


def _tokenize(text):
    """Return a flat list of token dicts: {kind, text, line, [lang, datatype]}.

    kind is one of 'IRI', 'LITERAL', 'WORD', 'PUNCT'. A LITERAL token folds
    in its optional @lang or ^^datatype suffix (only legal directly after
    the closing quote, no intervening whitespace, so it has to be handled
    at this level rather than as independent tokens).
    """
    tokens = []
    i, n, line = 0, len(text), 1

    def err(why, pos):
        raise ManchesterSyntaxError(why, text, pos=pos, line=line)

    while i < n:
        c = text[i]
        if c == '\n':
            line += 1
            i += 1
            continue
        if c.isspace():
            i += 1
            continue
        if c == '#':
            nl = text.find('\n', i)
            i = n if nl == -1 else nl
            continue
        if c == '<':
            # '<=' and bare '<' are also the minInclusive/minExclusive data
            # facet operators (used as `xsd:int[< "10"^^xsd:int]`), not just
            # IRIREF's opening bracket - disambiguated by content rather
            # than position: a real IRI never contains whitespace, so
            # only commit to the IRI reading when the text up to the next
            # '>' has none. '<=' is unambiguous on its own (no IRI starts
            # with '=') and is checked first.
            if text[i:i + 2] == '<=':
                tokens.append({'kind': 'WORD', 'text': '<=', 'line': line})
                i += 2
                continue
            end = text.find('>', i + 1)
            candidate = text[i + 1:end] if end != -1 else ''
            if end != -1 and not any(ch.isspace() for ch in candidate):
                tokens.append({'kind': 'IRI', 'text': candidate, 'line': line})
                i = end + 1
                continue
            tokens.append({'kind': 'WORD', 'text': '<', 'line': line})
            i += 1
            continue
        if c == '"':
            j = i + 1
            while j < n and text[j] != '"':
                if text[j] == '\\':
                    j += 1
                j += 1
            if j >= n:
                err('unterminated string literal', i)
            value = text[i + 1:j]
            tok = {'kind': 'LITERAL', 'text': value, 'line': line, 'lang': None, 'datatype': None}
            j += 1
            if j < n and text[j] == '@':
                k = j + 1
                while k < n and (text[k].isalnum() or text[k] == '-'):
                    k += 1
                tok['lang'] = text[j + 1:k]
                j = k
            elif text[j:j + 2] == '^^':
                j += 2
                if j < n and text[j] == '<':
                    end = text.find('>', j + 1)
                    if end == -1:
                        err("unterminated datatype IRI (missing '>')", j)
                    tok['datatype'] = ('IRI', text[j + 1:end])
                    j = end + 1
                else:
                    k = j
                    while k < n and not text[k].isspace() and text[k] not in _WORD_STOP_CHARS:
                        k += 1
                    if k == j:
                        err('expected datatype after ^^', j)
                    tok['datatype'] = ('WORD', text[j:k])
                    j = k
            tokens.append(tok)
            i = j
            continue
        if c in '(),{}[]':
            tokens.append({'kind': 'PUNCT', 'text': c, 'line': line})
            i += 1
            continue
        j = i
        while j < n and not text[j].isspace() and text[j] not in _WORD_STOP_CHARS:
            j += 1
        if j == i:
            err(f'unexpected {c!r}', i)
        tokens.append({'kind': 'WORD', 'text': text[i:j], 'line': line})
        i = j

    return tokens


# ---------------------------------------------------------------------------
# Cursor - token stream + parser state
# ---------------------------------------------------------------------------

class _Cursor:
    def __init__(self, tokens, base):
        self.tokens = tokens
        self.pos = 0
        self.prefixes = dict(_DEFAULT_PREFIXES)
        self.base = base
        self.triples = []

    def mint_bnode(self):
        return BNode()

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def peek_word(self):
        tok = self.peek()
        return tok['text'] if tok is not None and tok['kind'] == 'WORD' else None

    def advance(self):
        tok = self.peek()
        if tok is None:
            self.error('unexpected end of input', pos=None)
        self.pos += 1
        return tok

    def expect_punct(self, ch):
        tok = self.peek()
        if tok is None or tok['kind'] != 'PUNCT' or tok['text'] != ch:
            got = tok['text'] if tok else '<end of input>'
            self.error(f'expected {ch!r}, got {got!r}')
        return self.advance()

    def error(self, why, pos=0):
        tok = self.peek()
        line = tok['line'] if tok else None
        text = tok['text'] if tok else ''
        raise ManchesterSyntaxError(why, text, pos=pos or 0, line=line)

    # -- name resolution ---------------------------------------------------

    def resolve_prefixed(self, prefix, local):
        if prefix not in self.prefixes:
            self.error(
                f'unknown prefix {prefix!r} - no matching Prefix: directive '
                f'(the default ":" prefix must be declared explicitly too; '
                f"it isn't guessed from the ontology IRI)"
            )
        return URIRef(self.prefixes[prefix] + local)

    def resolve_iri(self, raw):
        return URIRef(urljoin(self.base, raw) if self.base else raw)

    def read_name(self):
        """Consume one IRI/WORD token naming a class/property/individual/datatype."""
        tok = self.advance()
        if tok['kind'] == 'IRI':
            return self.resolve_iri(tok['text'])
        if tok['kind'] != 'WORD':
            self.error(f'expected a name, got {tok["text"]!r}')
        text = tok['text']
        if ':' in text:
            prefix, local = text.split(':', 1)
        else:
            prefix, local = '', text
        return self.resolve_prefixed(prefix, local)

    def read_literal_or_name(self):
        """Read a `value`-restriction/Facts: filler: a data Literal if the
        next token is a quoted literal, otherwise an individual name."""
        tok = self.peek()
        if tok is not None and tok['kind'] == 'LITERAL':
            self.advance()
            if tok['datatype'] is not None:
                kind, dt_text = tok['datatype']
                dt = self.resolve_iri(dt_text) if kind == 'IRI' else self._resolve_word(dt_text)
                return Literal(tok['text'], datatype=dt)
            if tok['lang']:
                return Literal(tok['text'], lang=tok['lang'])
            return Literal(tok['text'])
        word = self.peek_word()
        if word is not None and (word.replace('.', '', 1).replace('-', '', 1).isdigit() or word in ('true', 'false')):
            self.advance()
            val = coerce_object(word)
            return Literal(val) if isinstance(val, bool) else val
        return self.read_name()

    def _resolve_word(self, text):
        if ':' in text:
            prefix, local = text.split(':', 1)
        else:
            prefix, local = '', text
        return self.resolve_prefixed(prefix, local)


# ---------------------------------------------------------------------------
# Class-expression AST + parsing
# ---------------------------------------------------------------------------
# Tagged tuples: ('And', [expr,...]) | ('Or', [expr,...]) | ('Not', expr)
# | ('OneOf', [uri,...]) | ('Some'|'Only', propExpr, expr)
# | ('Value', propExpr, uriOrLiteral) | ('SelfR', propExpr)
# | ('Min'|'Max'|'Exact', n, propExpr, expr_or_None)
# | ('Inverse', uri) | a plain URIRef for an atomic class/property.

def _parse_description(cur):
    left = _parse_conjunction(cur)
    items = [left]
    while cur.peek_word() == 'or':
        cur.advance()
        items.append(_parse_conjunction(cur))
    return items[0] if len(items) == 1 else ('Or', items)


def _parse_conjunction(cur):
    # 'that' is a confirmed straight synonym for 'and' at this position
    # (checked empirically against the OWL API oracle: `Leg that (hasNumber
    # value 4)` produces the identical owl:intersectionOf shape as
    # `Leg and (hasNumber value 4)`) - used for English-readable restriction
    # refinement, e.g. "hasPart some (Leg that hasNumber value 4)".
    left = _parse_primary(cur)
    items = [left]
    while cur.peek_word() in ('and', 'that'):
        cur.advance()
        items.append(_parse_primary(cur))
    return items[0] if len(items) == 1 else ('And', items)


def _parse_primary(cur):
    word = cur.peek_word()
    if word == 'not':
        cur.advance()
        return ('Not', _parse_primary(cur))
    if word == 'inverse':
        cur.advance()
        prop = ('Inverse', cur.read_name())
        if cur.peek_word() in _RESTRICTION_KEYWORDS:
            return _parse_restriction_tail(cur, prop)
        return prop

    tok = cur.peek()
    if tok is not None and tok['kind'] == 'PUNCT' and tok['text'] == '(':
        cur.advance()
        expr = _parse_description(cur)
        cur.expect_punct(')')
        return expr
    if tok is not None and tok['kind'] == 'PUNCT' and tok['text'] == '{':
        cur.advance()
        individuals = [cur.read_name()]
        while cur.peek() is not None and cur.peek()['kind'] == 'PUNCT' and cur.peek()['text'] == ',':
            cur.advance()
            individuals.append(cur.read_name())
        cur.expect_punct('}')
        return ('OneOf', individuals)

    name = cur.read_name()
    if cur.peek_word() in _RESTRICTION_KEYWORDS:
        return _parse_restriction_tail(cur, name)
    return name


def _parse_property_expr(cur):
    """objectPropertyExpr ::= objectProperty | 'inverse' objectProperty -
    deliberately not routed through _parse_description/_parse_primary:
    property positions (SubPropertyOf:, EquivalentTo:, DisjointWith:,
    InverseOf:) never accept the full and/or/not/restriction grammar,
    only a bare name or a single 'inverse'."""
    if cur.peek_word() == 'inverse':
        cur.advance()
        return ('Inverse', cur.read_name())
    return cur.read_name()


def _starts_a_primary(tok):
    """True if tok could begin a class-expression primary - used to decide
    whether an unqualified `min n`/`max n`/`exactly n` is followed by a
    qualifying filler or not. Every Manchester keyword (frame or clause)
    ends with ':', and 'and'/'or' are the only other bare words that can't
    start a primary - so this is a simple, general check rather than one
    tied to a fixed terminator set."""
    if tok is None:
        return False
    if tok['kind'] == 'IRI':
        return True
    if tok['kind'] == 'PUNCT':
        return tok['text'] in ('(', '{')
    if tok['kind'] == 'WORD':
        return tok['text'] not in ('and', 'or', 'that') and not tok['text'].endswith(':')
    return False


def _parse_restriction_tail(cur, prop_expr):
    kw = cur.advance()['text']
    if kw == 'some':
        return ('Some', prop_expr, _parse_primary(cur))
    if kw == 'only':
        return ('Only', prop_expr, _parse_primary(cur))
    if kw == 'onlysome':
        # `p onlysome C` - OWL-API GCI-writing convenience, confirmed
        # empirically to expand to `(p some C) and (p only C)` exactly
        # (same owl:intersectionOf-of-two-restrictions shape the oracle
        # emits) - reuses the existing And/Some/Only RDF mapping rather
        # than needing a dedicated tag.
        filler = _parse_primary(cur)
        return ('And', [('Some', prop_expr, filler), ('Only', prop_expr, filler)])
    if kw == 'value':
        return ('Value', prop_expr, cur.read_literal_or_name())
    if kw == 'Self':
        return ('SelfR', prop_expr)
    # min / max / exactly
    n_tok = cur.advance()
    if n_tok['kind'] != 'WORD' or not n_tok['text'].isdigit():
        cur.error(f'expected a non-negative integer after {kw!r}, got {n_tok["text"]!r}')
    n = int(n_tok['text'])
    tag = {'min': 'Min', 'max': 'Max', 'exactly': 'Exact'}[kw]
    filler = _parse_primary(cur) if _starts_a_primary(cur.peek()) else None
    return (tag, n, prop_expr, filler)


# ---------------------------------------------------------------------------
# AST -> RDF
# ---------------------------------------------------------------------------

def _prop_node(cur, prop_expr):
    if isinstance(prop_expr, URIRef):
        return prop_expr
    # ('Inverse', uri)
    node = cur.mint_bnode()
    cur.triples.append((node, OWL.inverseOf, prop_expr[1]))
    return node


def _expr_node(cur, expr):
    if isinstance(expr, URIRef):
        return expr
    tag = expr[0]
    t = cur.triples

    if tag in ('And', 'Or'):
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Class))
        items = [_expr_node(cur, e) for e in expr[1]]
        pred = OWL.intersectionOf if tag == 'And' else OWL.unionOf
        t.append((node, pred, _build_list(cur, items)))
        return node
    if tag == 'Not':
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Class))
        t.append((node, OWL.complementOf, _expr_node(cur, expr[1])))
        return node
    if tag == 'OneOf':
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Class))
        t.append((node, OWL.oneOf, _build_list(cur, expr[1])))
        return node
    if tag in ('Some', 'Only'):
        _, prop_expr, filler = expr
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Restriction))
        t.append((node, OWL.onProperty, _prop_node(cur, prop_expr)))
        pred = OWL.someValuesFrom if tag == 'Some' else OWL.allValuesFrom
        t.append((node, pred, _expr_node(cur, filler)))
        return node
    if tag == 'Value':
        _, prop_expr, value = expr
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Restriction))
        t.append((node, OWL.onProperty, _prop_node(cur, prop_expr)))
        t.append((node, OWL.hasValue, value))
        return node
    if tag == 'SelfR':
        _, prop_expr = expr
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Restriction))
        t.append((node, OWL.onProperty, _prop_node(cur, prop_expr)))
        t.append((node, OWL.hasSelf, Literal(True)))
        return node
    if tag in ('Min', 'Max', 'Exact'):
        _, n, prop_expr, filler = expr
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Restriction))
        t.append((node, OWL.onProperty, _prop_node(cur, prop_expr)))
        card = Literal(n, datatype=XSD.nonNegativeInteger)
        if filler is None:
            pred = {'Min': OWL.minCardinality, 'Max': OWL.maxCardinality, 'Exact': OWL.cardinality}[tag]
            t.append((node, pred, card))
        else:
            pred = {
                'Min': OWL.minQualifiedCardinality,
                'Max': OWL.maxQualifiedCardinality,
                'Exact': OWL.qualifiedCardinality,
            }[tag]
            t.append((node, pred, card))
            t.append((node, OWL.onClass, _expr_node(cur, filler)))
        return node
    if tag == 'Inverse':
        return _prop_node(cur, expr)
    raise AssertionError(f'unhandled class-expression tag {tag!r}')


def _build_list(cur, items):
    if not items:
        return RDF.nil
    head, prev = None, None
    for item in items:
        node = cur.mint_bnode()
        if prev is not None:
            cur.triples.append((prev, RDF.rest, node))
        else:
            head = node
        cur.triples.append((node, RDF.first, item))
        prev = node
    cur.triples.append((prev, RDF.rest, RDF.nil))
    return head


# ---------------------------------------------------------------------------
# Data ranges - a separate grammar from class expressions (used by
# DataProperty: Range: and Datatype: EquivalentTo:), since a data range's
# atoms are datatypes/literals rather than classes/individuals. Tagged
# tuples: ('DAnd'|'DOr', [dr,...]) | ('DNot', dr) | ('DOneOf', [literal,...])
# | ('DRestriction', datatype_uri, [(facet_uri, literal), ...])
# | a plain URIRef for an atomic datatype.
# ---------------------------------------------------------------------------

def _parse_data_range(cur):
    left = _parse_data_conjunction(cur)
    items = [left]
    while cur.peek_word() == 'or':
        cur.advance()
        items.append(_parse_data_conjunction(cur))
    return items[0] if len(items) == 1 else ('DOr', items)


def _parse_data_conjunction(cur):
    left = _parse_data_primary(cur)
    items = [left]
    while cur.peek_word() == 'and':
        cur.advance()
        items.append(_parse_data_primary(cur))
    return items[0] if len(items) == 1 else ('DAnd', items)


def _parse_data_primary(cur):
    if cur.peek_word() == 'not':
        cur.advance()
        return ('DNot', _parse_data_atomic(cur))
    return _parse_data_atomic(cur)


def _read_data_literal(cur):
    val = cur.read_literal_or_name()
    if not isinstance(val, Literal):
        cur.error('expected a literal here')
    return val


def _parse_facet_restriction(cur):
    tok = cur.advance()
    if tok['text'] not in _DATA_FACETS:
        cur.error(f'unknown facet {tok["text"]!r}')
    return _DATA_FACETS[tok['text']], _read_data_literal(cur)


def _parse_data_atomic(cur):
    tok = cur.peek()
    if tok is not None and tok['kind'] == 'PUNCT' and tok['text'] == '(':
        cur.advance()
        dr = _parse_data_range(cur)
        cur.expect_punct(')')
        return dr
    if tok is not None and tok['kind'] == 'PUNCT' and tok['text'] == '{':
        cur.advance()
        literals = [_read_data_literal(cur)]
        while cur.peek() is not None and cur.peek()['kind'] == 'PUNCT' and cur.peek()['text'] == ',':
            cur.advance()
            literals.append(_read_data_literal(cur))
        cur.expect_punct('}')
        return ('DOneOf', literals)

    datatype = cur.read_name()
    if cur.peek() is not None and cur.peek()['kind'] == 'PUNCT' and cur.peek()['text'] == '[':
        cur.advance()
        facets = [_parse_facet_restriction(cur)]
        while cur.peek() is not None and cur.peek()['kind'] == 'PUNCT' and cur.peek()['text'] == ',':
            cur.advance()
            facets.append(_parse_facet_restriction(cur))
        cur.expect_punct(']')
        return ('DRestriction', datatype, facets)
    return datatype


def _data_range_node(cur, dr):
    if isinstance(dr, URIRef):
        return dr
    tag = dr[0]
    t = cur.triples
    if tag in ('DAnd', 'DOr'):
        node = cur.mint_bnode()
        t.append((node, RDF.type, RDFS.Datatype))
        items = [_data_range_node(cur, e) for e in dr[1]]
        pred = OWL.intersectionOf if tag == 'DAnd' else OWL.unionOf
        t.append((node, pred, _build_list(cur, items)))
        return node
    if tag == 'DNot':
        node = cur.mint_bnode()
        t.append((node, RDF.type, RDFS.Datatype))
        t.append((node, OWL.datatypeComplementOf, _data_range_node(cur, dr[1])))
        return node
    if tag == 'DOneOf':
        node = cur.mint_bnode()
        t.append((node, RDF.type, RDFS.Datatype))
        t.append((node, OWL.oneOf, _build_list(cur, dr[1])))
        return node
    if tag == 'DRestriction':
        _, datatype, facets = dr
        node = cur.mint_bnode()
        t.append((node, RDF.type, RDFS.Datatype))
        t.append((node, OWL.onDatatype, datatype))
        facet_nodes = []
        for facet_uri, lit in facets:
            fn = cur.mint_bnode()
            t.append((fn, facet_uri, lit))
            facet_nodes.append(fn)
        t.append((node, OWL.withRestrictions, _build_list(cur, facet_nodes)))
        return node
    raise AssertionError(f'unhandled data-range tag {tag!r}')


# ---------------------------------------------------------------------------
# Comma-separated clause lists
# ---------------------------------------------------------------------------

def _parse_comma_list(cur, parse_item):
    items = [parse_item(cur)]
    while True:
        tok = cur.peek()
        if tok is not None and tok['kind'] == 'PUNCT' and tok['text'] == ',':
            cur.advance()
            items.append(parse_item(cur))
        else:
            return items


def _pairwise_chain(cur, nodes, pred):
    for a, b in zip(nodes, nodes[1:]):
        cur.triples.append((a, pred, b))


def _nary_disjoint_or_different(cur, nodes, binary_pred, collection_class):
    if len(nodes) == 2:
        cur.triples.append((nodes[0], binary_pred, nodes[1]))
        return
    node = cur.mint_bnode()
    cur.triples.append((node, RDF.type, collection_class))
    cur.triples.append((node, OWL.members, _build_list(cur, nodes)))


def _parse_annotation_assertion(cur):
    return cur.read_name(), cur.read_literal_or_name()


def _handle_frame_annotations(cur, subject):
    """The standalone `Annotations:` frame section (its own clause, listing
    annotationProperty/value pairs about the frame's own subject) -
    confirmed empirically to map straight to direct triples on that
    subject, no owl:Axiom reification involved. Distinct from - and much
    simpler than - annotating one specific item inside e.g. a SubClassOf:
    list (see _parse_item_annotations/_maybe_reify below), which *does*
    need reification."""
    for prop, value in _parse_comma_list(cur, _parse_annotation_assertion):
        cur.triples.append((subject, prop, value))


def _parse_item_annotations(cur):
    """Optional `Annotations: prop val, prop val, ...` immediately before
    one axiom-list item (or before a whole single-axiom clause's body,
    e.g. HasKey:/DisjointUnionOf:/SubPropertyChain:) - confirmed
    empirically against the OWL API oracle to apply to exactly that one
    item/clause, never carrying over to a later comma-separated item
    (`SubClassOf: Annotations: rdfs:comment "why" A, B` only reifies the
    A axiom, not B). Returns None when absent - the grammar has no
    "annotated with nothing" form, so None unambiguously means "no
    Annotations: prefix was written here"."""
    if cur.peek_word() != 'Annotations:':
        return None
    cur.advance()
    return _parse_comma_list(cur, _parse_annotation_assertion)


def _annotated(parse_item):
    """Wrap an item-parser so _parse_comma_list collects (annotations,
    item) pairs instead of bare items - used at every clause-list call
    site whose items each become their own axiom."""
    return lambda c: (_parse_item_annotations(c), parse_item(c))


def _maybe_reify(cur, subject, pred, obj, annotations):
    """If `annotations` came from a real Annotations: prefix (not None),
    add the owl:Axiom reification block the OWL 2 RDF mapping's
    "Annotations of Axioms" section uses - alongside the plain
    (subject, pred, obj) triple the caller already asserted, never
    instead of it, the same principle RDF 1.2's own `{| |}` annotation
    block follows (see turtle_parser.py) even though the concrete
    mechanism differs (real reification here, not a triple-term)."""
    if annotations is None:
        return
    node = cur.mint_bnode()
    cur.triples.append((node, RDF.type, OWL.Axiom))
    cur.triples.append((node, OWL.annotatedSource, subject))
    cur.triples.append((node, OWL.annotatedProperty, pred))
    cur.triples.append((node, OWL.annotatedTarget, obj))
    for prop, value in annotations:
        cur.triples.append((node, prop, value))


# ---------------------------------------------------------------------------
# Frame bodies
# ---------------------------------------------------------------------------

def _frame_body(cur, clauses, deferred, handle_clause):
    while True:
        word = cur.peek_word()
        if word is None:
            return
        if word in clauses:
            cur.advance()
            handle_clause(word)
        elif word in deferred:
            cur.error(f'{word} is not supported yet')
        elif word in _FRAME_KEYWORDS:
            return
        else:
            cur.error(f'expected a clause keyword or new frame, got {word!r}')


def _parse_class_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, OWL.Class))

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, subject)
            return
        if clause == 'SuperClassOf:':
            for anns, expr in _parse_comma_list(cur, _annotated(_parse_description)):
                node = _expr_node(cur, expr)
                cur.triples.append((node, RDFS.subClassOf, subject))
                _maybe_reify(cur, node, RDFS.subClassOf, subject, anns)
            return
        if clause == 'DisjointUnionOf:':
            anns = _parse_item_annotations(cur)
            nodes = [_expr_node(cur, e) for e in _parse_comma_list(cur, _parse_description)]
            obj = _build_list(cur, nodes)
            cur.triples.append((subject, OWL.disjointUnionOf, obj))
            _maybe_reify(cur, subject, OWL.disjointUnionOf, obj, anns)
            return
        if clause == 'HasKey:':
            anns = _parse_item_annotations(cur)
            nodes = [_prop_node(cur, e) for e in _parse_comma_list(cur, _parse_property_expr)]
            obj = _build_list(cur, nodes)
            cur.triples.append((subject, OWL.hasKey, obj))
            _maybe_reify(cur, subject, OWL.hasKey, obj, anns)
            return
        pred = {
            'SubClassOf:': RDFS.subClassOf,
            'EquivalentTo:': OWL.equivalentClass,
            'DisjointWith:': OWL.disjointWith,
        }[clause]
        for anns, expr in _parse_comma_list(cur, _annotated(_parse_description)):
            node = _expr_node(cur, expr)
            cur.triples.append((subject, pred, node))
            _maybe_reify(cur, subject, pred, node, anns)

    _frame_body(cur, _CLASS_CLAUSES, _CLASS_DEFERRED, handle)


def _parse_property_frame(cur, rdf_type, clauses, deferred, range_is_class_expr):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, rdf_type))

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, subject)
            return
        if clause == 'Characteristics:':
            for anns, name in _parse_comma_list(cur, _annotated(lambda c: c.advance()['text'])):
                if name not in _CHARACTERISTICS:
                    cur.error(f'unknown property characteristic {name!r}')
                obj = _CHARACTERISTICS[name]
                cur.triples.append((subject, RDF.type, obj))
                _maybe_reify(cur, subject, RDF.type, obj, anns)
            return
        if clause == 'SubPropertyChain:':
            anns = _parse_item_annotations(cur)
            chain = [_parse_property_expr(cur)]
            while cur.peek_word() == 'o':
                cur.advance()
                chain.append(_parse_property_expr(cur))
            nodes = [_prop_node(cur, e) for e in chain]
            obj = _build_list(cur, nodes)
            cur.triples.append((subject, OWL.propertyChainAxiom, obj))
            _maybe_reify(cur, subject, OWL.propertyChainAxiom, obj, anns)
            return
        if clause == 'SuperPropertyOf:':
            for anns, expr in _parse_comma_list(cur, _annotated(_parse_property_expr)):
                node = _prop_node(cur, expr)
                cur.triples.append((node, RDFS.subPropertyOf, subject))
                _maybe_reify(cur, node, RDFS.subPropertyOf, subject, anns)
            return
        if clause == 'Range:' and not range_is_class_expr:
            for anns, dr in _parse_comma_list(cur, _annotated(_parse_data_range)):
                obj = _data_range_node(cur, dr)
                cur.triples.append((subject, RDFS.range, obj))
                _maybe_reify(cur, subject, RDFS.range, obj, anns)
            return
        if clause in ('SubPropertyOf:', 'EquivalentTo:', 'DisjointWith:', 'InverseOf:'):
            pred = {
                'SubPropertyOf:': RDFS.subPropertyOf,
                'EquivalentTo:': OWL.equivalentProperty,
                'DisjointWith:': OWL.propertyDisjointWith,
                'InverseOf:': OWL.inverseOf,
            }[clause]
            for anns, expr in _parse_comma_list(cur, _annotated(_parse_property_expr)):
                node = _prop_node(cur, expr)
                cur.triples.append((subject, pred, node))
                _maybe_reify(cur, subject, pred, node, anns)
            return
        # Domain: (both frame kinds), Range: (object-property case) - full
        # class-expression grammar.
        pred = {'Domain:': RDFS.domain, 'Range:': RDFS.range}[clause]
        for anns, expr in _parse_comma_list(cur, _annotated(_parse_description)):
            node = _expr_node(cur, expr)
            cur.triples.append((subject, pred, node))
            _maybe_reify(cur, subject, pred, node, anns)

    _frame_body(cur, clauses, deferred, handle)


def _parse_annotation_property_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, OWL.AnnotationProperty))

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, subject)
            return
        pred = {'Domain:': RDFS.domain, 'Range:': RDFS.range, 'SubPropertyOf:': RDFS.subPropertyOf}[clause]
        for anns, name in _parse_comma_list(cur, _annotated(lambda c: c.read_name())):
            cur.triples.append((subject, pred, name))
            _maybe_reify(cur, subject, pred, name, anns)

    _frame_body(cur, _ANNPROP_CLAUSES, _ANNPROP_DEFERRED, handle)


def _parse_fact(cur):
    negative = False
    if cur.peek_word() == 'not':
        cur.advance()
        negative = True
    prop = cur.read_name()
    value = cur.read_literal_or_name()
    return negative, prop, value


def _parse_individual_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, OWL.NamedIndividual))

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, subject)
        elif clause == 'Types:':
            for anns, expr in _parse_comma_list(cur, _annotated(_parse_description)):
                node = _expr_node(cur, expr)
                cur.triples.append((subject, RDF.type, node))
                _maybe_reify(cur, subject, RDF.type, node, anns)
        elif clause == 'Facts:':
            for anns, (negative, prop, value) in _parse_comma_list(cur, _annotated(_parse_fact)):
                if not negative:
                    cur.triples.append((subject, prop, value))
                    _maybe_reify(cur, subject, prop, value, anns)
                    continue
                # A negative fact has no base (s, p, o) triple to point an
                # owl:Axiom wrapper at - the NegativePropertyAssertion bnode
                # is itself already the reification-like structure the OWL 2
                # RDF mapping uses, so any annotations attach directly to it
                # rather than through a second _maybe_reify() wrapper node.
                node = cur.mint_bnode()
                cur.triples.append((node, RDF.type, OWL.NegativePropertyAssertion))
                cur.triples.append((node, OWL.sourceIndividual, subject))
                cur.triples.append((node, OWL.assertionProperty, prop))
                target_pred = OWL.targetValue if isinstance(value, Literal) else OWL.targetIndividual
                cur.triples.append((node, target_pred, value))
                if anns is not None:
                    for ann_prop, ann_value in anns:
                        cur.triples.append((node, ann_prop, ann_value))
        else:
            pred = OWL.sameAs if clause == 'SameAs:' else OWL.differentFrom
            for anns, name in _parse_comma_list(cur, _annotated(lambda c: c.read_name())):
                cur.triples.append((subject, pred, name))
                _maybe_reify(cur, subject, pred, name, anns)

    _frame_body(cur, _INDIVIDUAL_CLAUSES, _INDIVIDUAL_DEFERRED, handle)


def _parse_datatype_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, RDFS.Datatype))

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, subject)
            return
        # EquivalentTo: - a DatatypeDefinition axiom maps to owl:equivalentClass
        # per the OWL 2 RDF mapping, confirmed against the oracle the same
        # way as every other construct here.
        for anns, dr in _parse_comma_list(cur, _annotated(_parse_data_range)):
            node = _data_range_node(cur, dr)
            cur.triples.append((subject, OWL.equivalentClass, node))
            _maybe_reify(cur, subject, OWL.equivalentClass, node, anns)

    _frame_body(cur, _DATATYPE_CLAUSES, _DATATYPE_DEFERRED, handle)


def _parse_misc(cur, keyword):
    if keyword in ('EquivalentClasses:', 'DisjointClasses:'):
        nodes = [_expr_node(cur, e) for e in _parse_comma_list(cur, _parse_description)]
        if keyword == 'EquivalentClasses:':
            _pairwise_chain(cur, nodes, OWL.equivalentClass)
        else:
            _nary_disjoint_or_different(cur, nodes, OWL.disjointWith, OWL.AllDisjointClasses)
    elif keyword in ('EquivalentProperties:', 'DisjointProperties:'):
        nodes = [_prop_node(cur, e) for e in _parse_comma_list(cur, _parse_property_expr)]
        if keyword == 'EquivalentProperties:':
            _pairwise_chain(cur, nodes, OWL.equivalentProperty)
        else:
            _nary_disjoint_or_different(cur, nodes, OWL.propertyDisjointWith, OWL.AllDisjointProperties)
    else:
        names = _parse_comma_list(cur, lambda c: c.read_name())
        if keyword == 'SameIndividual:':
            _pairwise_chain(cur, names, OWL.sameAs)
        else:
            _nary_disjoint_or_different(cur, names, OWL.differentFrom, OWL.AllDifferent)


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def parse_manchester(text: str, base: str = None) -> list:
    """Parse Manchester OWL Syntax text and return a list of (s, p, o)
    triples (plain rdflib terms - URIRef/BNode/Literal).

    base seeds resolution of the `Ontology: <iri>` header and any other
    relative IRIs, the same role every other starlayergraph parser's base
    argument plays.
    """
    cur = _Cursor(_tokenize(text), base)

    while True:
        word = cur.peek_word()
        if word is None:
            break
        if word == 'Prefix:':
            cur.advance()
            name_tok = cur.advance()
            if name_tok['kind'] != 'WORD' or not name_tok['text'].endswith(':'):
                cur.error("expected a prefix name ending in ':'")
            prefix = name_tok['text'][:-1]
            iri_tok = cur.advance()
            if iri_tok['kind'] != 'IRI':
                cur.error('expected an <IRI> for the Prefix: declaration')
            cur.prefixes[prefix] = iri_tok['text']
        elif word == 'Ontology:':
            cur.advance()
            tok = cur.peek()
            ontology_iri = None
            if tok is not None and tok['kind'] == 'IRI':
                cur.advance()
                ontology_iri = cur.resolve_iri(tok['text'])
                cur.base = str(ontology_iri)
                cur.triples.append((ontology_iri, RDF.type, OWL.Ontology))
            while cur.peek_word() == 'Import:':
                cur.advance()
                imported = cur.read_name()
                if ontology_iri is not None:
                    cur.triples.append((ontology_iri, OWL.imports, imported))
            if cur.peek_word() == 'Annotations:':
                cur.error('Annotations: in the Ontology: header is not supported yet')
        elif word == 'Datatype:':
            cur.advance()
            _parse_datatype_frame(cur)
        elif word == 'Class:':
            cur.advance()
            _parse_class_frame(cur)
        elif word == 'ObjectProperty:':
            cur.advance()
            _parse_property_frame(cur, OWL.ObjectProperty, _OBJPROP_CLAUSES, _OBJPROP_DEFERRED, range_is_class_expr=True)
        elif word == 'DataProperty:':
            cur.advance()
            _parse_property_frame(cur, OWL.DatatypeProperty, _DATAPROP_CLAUSES, _DATAPROP_DEFERRED, range_is_class_expr=False)
        elif word == 'AnnotationProperty:':
            cur.advance()
            _parse_annotation_property_frame(cur)
        elif word == 'Individual:':
            cur.advance()
            _parse_individual_frame(cur)
        elif word in ('EquivalentClasses:', 'DisjointClasses:', 'EquivalentProperties:',
                      'DisjointProperties:', 'SameIndividual:', 'DifferentIndividuals:'):
            cur.advance()
            _parse_misc(cur, word)
        else:
            cur.error(f'expected a Prefix:/Ontology:/frame/Misc-axiom keyword, got {word!r}')

    return cur.triples
