"""
starlayer.graph.parsers.manchester_parser

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

import re
from urllib.parse import urljoin

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS, XSD

from starlayer.graph.parsers.errors import ManchesterSyntaxError

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
    'langRange': URIRef(str(RDF) + 'langRange'),
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

_SHORT_DATATYPES = {
    'integer': XSD.integer,
    'decimal': XSD.decimal,
    'float': XSD.float,
    'string': XSD.string,
}

# Datatypes that need no declaration: the xsd namespace plus the OWL 2 / RDF built-ins that are not in it.
_BUILTIN_DATATYPES = frozenset({
    URIRef(str(RDF) + 'PlainLiteral'), URIRef(str(RDF) + 'XMLLiteral'), URIRef(str(RDF) + 'langString'),
    RDFS.Literal, OWL.real, OWL.rational,
})


def _is_builtin_datatype(uri):
    return uri in _BUILTIN_DATATYPES or str(uri).startswith(str(XSD))


_RESTRICTION_KEYWORDS = {'some', 'only', 'onlysome', 'value', 'Self', 'min', 'max', 'exactly'}


# ---------------------------------------------------------------------------
# Numeric literals (the note's integerLiteral / decimalLiteral / floatingPointLiteral)
# ---------------------------------------------------------------------------

_INTEGER_RE = re.compile(r'^[+-]?[0-9]+$')
_DECIMAL_RE = re.compile(r'^[+-]?[0-9]+\.[0-9]+$')
_FLOAT_RE = re.compile(r'^([+-]?(?:[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?))[fF]$')


def _numeric_literal(word):
    """The Literal for a bare numeric token, or None if ``word`` is not one.

    integer -> xsd:integer, decimal -> xsd:decimal, and a number ending in ``f``/``F`` (the only way the
    note's grammar spells a floating-point literal, with an optional exponent) -> xsd:float. A leading
    ``+`` is accepted and not kept in the lexical form, matching the OWL API.
    """
    if _INTEGER_RE.match(word):
        return Literal(str(int(word)), datatype=XSD.integer, normalize=False)
    if _DECIMAL_RE.match(word):
        return Literal(word.lstrip('+'), datatype=XSD.decimal, normalize=False)
    m = _FLOAT_RE.match(word)
    if m:
        return Literal(repr(float(m.group(1))), datatype=XSD.float, normalize=False)
    return None


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# A bare word (keyword, prefixed name, integer, ...) never legally contains
# any of these - each unambiguously starts a different token form.
_WORD_STOP_CHARS = ('<', '"', '(', ')', ',', '{', '}', '[', ']')


def _unescape_quoted(raw):
    """Decode the two escapes the note's ``quotedString`` production defines, ``\\"`` and ``\\\\``.

    Any other backslash is left alone (the note defines no other escape; the OWL API does the same), so a
    lone backslash in a string such as a regular expression survives unchanged.
    """
    if '\\' not in raw:
        return raw
    out = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == '\\' and i + 1 < n and raw[i + 1] in '"\\':
            out.append(raw[i + 1])
            i += 2
        else:
            out.append(c)
            i += 1
    return ''.join(out)


def _tokenize(text):
    """Tokenize Manchester Syntax text into a flat list of token dicts.

    A LITERAL token folds in its optional @lang or ^^datatype suffix (only
    legal directly after the closing quote, no intervening whitespace, so
    it has to be handled at this level rather than as independent tokens).

    Args:
        text: The Manchester Syntax document text to tokenize.

    Returns:
        A list of token dicts, each {kind, text, line, [lang, datatype]} -
        kind is one of 'IRI', 'LITERAL', 'WORD', 'PUNCT'; a LITERAL token
        also carries 'lang' and 'datatype' (datatype as a (kind, text)
        pair, kind 'IRI' or 'WORD'), both None when absent.
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
            value = _unescape_quoted(text[i + 1:j])
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
        if c == '>':
            # '>=' / '>' are facet operators; the note puts no whitespace requirement between one and
            # its value ('[>=1,<10]'), so they are tokens of their own, like '<=' and '<' above.
            op = '>=' if text[i:i + 2] == '>=' else '>'
            tokens.append({'kind': 'WORD', 'text': op, 'line': line})
            i += len(op)
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
        self._declared = None
        self._blank_nodes = {}

    def mint_bnode(self):
        return BNode()

    # -- syntax-tree-capture hooks ---------------------------------------------------
    # No-ops by default, so ordinary OWL-semantic parsing (parse_manchester())
    # is completely unaffected. starontology.manchester overrides
    # these on a _Cursor subclass to record the surface grammar (frames,
    # clauses, their already-parsed-but-not-yet-compiled item lists) as RDF,
    # alongside - not instead of - the OWL semantic triples every clause
    # handler already appends to cur.triples. Called with the exact items
    # each clause already computes for its own compile loop, so recording
    # never changes what gets compiled or in what order.

    def record_frame(self, kind, subject):
        """Called when a frame's own header line was just parsed
        (`Class: Foo`, etc.) - a no-op hook by default (see the
        syntax-tree-capture hooks comment above).

        Args:
            kind: A plain string naming the frame kind - 'Class',
                'ObjectProperty', 'DataProperty', 'AnnotationProperty',
                'Individual', or 'Datatype'.
            subject: The frame's subject name.
        """

    def record_frame_end(self):
        """Called once per frame, right after _frame_body() returns - the
        current frame's last clause has just been parsed (its whole body
        is now complete). A no-op hook by default."""

    def record_clause(self, frame_kind, clause_kind, items):
        """Called when one clause body was just parsed for the current
        frame. A no-op hook by default.

        Args:
            frame_kind: The enclosing frame's kind, as passed to
                record_frame().
            clause_kind: The clause's own keyword, e.g. 'SubClassOf:'.
            items: Whatever that clause's own comma-list already
                produced - a list of (annotations, expr-or-name) pairs for
                a per-item-annotatable clause, or a list of bare
                names/tags for one that isn't - always *before*
                compilation to OWL triples, never a compiled node.
        """

    def record_misc(self, keyword, items, annotations=None):
        """Called when a top-level Misc axiom (EquivalentClasses:, etc.,
        no subject frame) was just parsed. A no-op hook by default.

        Args:
            keyword: The Misc axiom's own keyword, e.g.
                'EquivalentClasses:'.
            items: The axiom's own comma-list, before compilation.
            annotations: The axiom's leading `Annotations:` as a list of
                annotations, or None.
        """

    def record_ontology_header(self, iri, imports, version_iri=None, annotations=None):
        """Called when the Ontology: header line was just parsed. A no-op
        hook by default.

        Args:
            iri: The ontology's own IRI, or None for a bare `Ontology:`
                with no IRI.
            imports: The list of Import: names, in order.
            version_iri: The version IRI following the ontology IRI, or
                None.
            annotations: The header's `Annotations:` as a list of
                (property, value) pairs, or None if none were written.
        """

    def record_prefix(self, prefix, iri):
        """Called when a Prefix: declaration was just parsed. A no-op hook
        by default.

        Args:
            prefix: The bare prefix label (no trailing ':'; '' for the
                default prefix).
            iri: The raw IRI text.
        """

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

    def blank_node(self, label):
        """The blank node for a ``_:label`` nodeID. The label is the node's identity within the
        document, so every ``_:b1`` is the same node and a rendered label can be read back."""
        node = self._blank_nodes.get(label)
        if node is None:
            node = self._blank_nodes[label] = BNode(label)
        return node

    def read_individual(self):
        """Consume an individual: a name, or a nodeID (``_:label``, the note's ``individual ::=
        individualIRI | nodeID``)."""
        tok = self.peek()
        if tok is not None and tok['kind'] == 'WORD' and tok['text'].startswith('_:') and len(tok['text']) > 2:
            self.advance()
            return self.blank_node(tok['text'][2:])
        return self.read_name()

    def read_name(self):
        """Consume one IRI/WORD token naming a class/property/individual/datatype.

        Returns:
            The resolved URIRef.
        """
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
        """Read a `value`-restriction/Facts: filler.

        Returns:
            A Literal if the next token is a quoted literal or a bare
            numeric/boolean word, otherwise the resolved URIRef for an
            individual name.
        """
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
        if word is not None:
            number = _numeric_literal(word)
            if number is not None:
                self.advance()
                return number
            if word in ('true', 'false'):
                self.advance()
                return Literal(word == 'true')
        return self.read_individual()

    def try_name(self, tok):
        """The resolved URIRef a name token denotes, or None if ``tok`` is not a usable name here (a
        keyword, a literal, an unknown prefix). Never consumes anything and never raises."""
        if tok is None:
            return None
        if tok['kind'] == 'IRI':
            return self.resolve_iri(tok['text'])
        if tok['kind'] != 'WORD' or tok['text'].endswith(':'):
            return None
        text = tok['text']
        prefix, local = text.split(':', 1) if ':' in text else ('', text)
        if prefix not in self.prefixes:
            return None
        return URIRef(self.prefixes[prefix] + local)

    def declared_kinds(self):
        """``(property_kinds, datatypes)`` read from the document's own frames, wherever they occur.

        Manchester syntax does not mark a restriction as data or object syntactically (``p some X``
        reads the same either way); the property's declaration does. ``property_kinds`` maps a property
        IRI to 'data' or 'object'; ``datatypes`` is the set of IRIs declared with ``Datatype:``.
        Computed once, on first use, from the token stream (by then every Prefix: is known)."""
        if self._declared is None:
            kinds, datatypes = {}, set()
            for i, tok in enumerate(self.tokens[:-1]):
                if tok['kind'] != 'WORD':
                    continue
                keyword = tok['text']
                if keyword not in ('DataProperty:', 'ObjectProperty:', 'Datatype:'):
                    continue
                uri = self.try_name(self.tokens[i + 1])
                if uri is None:
                    continue
                if keyword == 'Datatype:':
                    datatypes.add(uri)
                else:
                    kinds[uri] = 'data' if keyword == 'DataProperty:' else 'object'
            self._declared = (kinds, datatypes)
        return self._declared

    def read_datatype_name(self):
        """Consume a datatype name: the note's ``Datatype ::= datatypeIRI | 'integer' | 'decimal' |
        'float' | 'string'``, so the four short words mean the xsd datatypes, not names in the default
        namespace."""
        word = self.peek_word()
        if word in _SHORT_DATATYPES:
            self.advance()
            return _SHORT_DATATYPES[word]
        return self.read_name()

    def _resolve_word(self, text):
        if text in _SHORT_DATATYPES:
            return _SHORT_DATATYPES[text]
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
        individuals = [cur.read_individual()]
        while cur.peek() is not None and cur.peek()['kind'] == 'PUNCT' and cur.peek()['text'] == ',':
            cur.advance()
            individuals.append(cur.read_individual())
        cur.expect_punct('}')
        return ('OneOf', individuals)

    name = cur.read_name()
    if cur.peek_word() in _RESTRICTION_KEYWORDS:
        return _parse_restriction_tail(cur, name)
    return name


def _parse_property_expr(cur):
    """Parse an objectPropertyExpr ::= objectProperty | 'inverse'
    objectProperty.

    Deliberately not routed through _parse_description/_parse_primary:
    property positions (SubPropertyOf:, EquivalentTo:, DisjointWith:,
    InverseOf:) never accept the full and/or/not/restriction grammar,
    only a bare name or a single 'inverse'.

    Args:
        cur: The parser cursor to read tokens from.

    Returns:
        A plain URIRef for a bare name, or an ('Inverse', uri) tuple for
        'inverse' objectProperty.
    """
    if cur.peek_word() == 'inverse':
        cur.advance()
        return ('Inverse', cur.read_name())
    return cur.read_name()


def _starts_a_primary(tok):
    """Check whether tok could begin a class-expression primary.

    Used to decide whether an unqualified `min n`/`max n`/`exactly n` is
    followed by a qualifying filler or not. Every Manchester keyword (frame
    or clause) ends with ':', and 'and'/'or' are the only other bare words
    that can't start a primary - so this is a simple, general check rather
    than one tied to a fixed terminator set.

    Args:
        tok: The next token to check, or None at end of input.

    Returns:
        True if tok could begin a class-expression primary, False
        otherwise.
    """
    if tok is None:
        return False
    if tok['kind'] == 'IRI':
        return True
    if tok['kind'] == 'PUNCT':
        return tok['text'] in ('(', '{')
    if tok['kind'] == 'WORD':
        return tok['text'] not in ('and', 'or', 'that') and not tok['text'].endswith(':')
    return False


def _filler_is_data(cur):
    """Does the filler about to be read look like a data range? Looks ahead without consuming.

    Used only when the property's own declaration does not settle data-vs-object: a literal enumeration
    (``{1, 2}``), a datatype name (xsd:, the short ``integer``/``string``/..., OWL/RDF built-ins, or a
    ``Datatype:`` declared in the document), or a name followed by ``[`` (a facet restriction). Leading
    ``(`` and ``not`` are looked through, so ``not xsd:string`` and ``(xsd:integer or ...)`` count."""
    tokens, i = cur.tokens, cur.pos
    while i < len(tokens) and (
        (tokens[i]['kind'] == 'PUNCT' and tokens[i]['text'] == '(')
        or (tokens[i]['kind'] == 'WORD' and tokens[i]['text'] == 'not')
    ):
        i += 1
    if i >= len(tokens):
        return False
    tok = tokens[i]
    nxt = tokens[i + 1] if i + 1 < len(tokens) else None
    if tok['kind'] == 'PUNCT' and tok['text'] == '{':
        return nxt is not None and (
            nxt['kind'] == 'LITERAL'
            or (nxt['kind'] == 'WORD' and (_numeric_literal(nxt['text']) is not None or nxt['text'] in ('true', 'false')))
        )
    if tok['kind'] == 'WORD' and tok['text'] in _SHORT_DATATYPES:
        return True
    uri = cur.try_name(tok)
    if uri is None:
        return False
    if _is_builtin_datatype(uri) or uri in cur.declared_kinds()[1]:
        return True
    return nxt is not None and nxt['kind'] == 'PUNCT' and nxt['text'] == '['


def _restriction_is_data(cur, prop_expr):
    """Is a ``p some/only/min/max/exactly`` restriction on a data property? The property's declaration
    (a ``DataProperty:``/``ObjectProperty:`` frame anywhere in the document) decides when there is one;
    otherwise the filler's shape does (see ``_filler_is_data``). ``inverse p`` is always an object property."""
    if isinstance(prop_expr, URIRef):
        kind = cur.declared_kinds()[0].get(prop_expr)
        if kind is not None:
            return kind == 'data'
    elif isinstance(prop_expr, tuple):
        return False
    return _filler_is_data(cur)


def _parse_restriction_tail(cur, prop_expr):
    kw = cur.advance()['text']
    if kw in ('some', 'only', 'onlysome'):
        # `p onlysome C` is an OWL-API convenience, confirmed against the oracle to expand to
        # `(p some C) and (p only C)` exactly, so it reuses the Some/Only mapping and needs no tag.
        data = _restriction_is_data(cur, prop_expr)
        filler = _parse_data_primary(cur) if data else _parse_primary(cur)
        some, only = ('DSome', 'DOnly') if data else ('Some', 'Only')
        if kw == 'some':
            return (some, prop_expr, filler)
        if kw == 'only':
            return (only, prop_expr, filler)
        return ('And', [(some, prop_expr, filler), (only, prop_expr, filler)])
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
    if not _starts_a_primary(cur.peek()):
        return (tag, n, prop_expr, None)
    if _restriction_is_data(cur, prop_expr):
        return ('D' + tag, n, prop_expr, _parse_data_primary(cur))
    return (tag, n, prop_expr, _parse_primary(cur))


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
    if tag in ('DSome', 'DOnly'):
        _, prop_expr, filler = expr
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Restriction))
        t.append((node, OWL.onProperty, _prop_node(cur, prop_expr)))
        pred = OWL.someValuesFrom if tag == 'DSome' else OWL.allValuesFrom
        t.append((node, pred, _data_range_node(cur, filler)))
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
    if tag in ('DMin', 'DMax', 'DExact'):
        _, n, prop_expr, filler = expr
        node = cur.mint_bnode()
        t.append((node, RDF.type, OWL.Restriction))
        t.append((node, OWL.onProperty, _prop_node(cur, prop_expr)))
        pred = {
            'DMin': OWL.minQualifiedCardinality,
            'DMax': OWL.maxQualifiedCardinality,
            'DExact': OWL.qualifiedCardinality,
        }[tag]
        t.append((node, pred, Literal(n, datatype=XSD.nonNegativeInteger)))
        t.append((node, OWL.onDataRange, _data_range_node(cur, filler)))
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

    datatype = cur.read_datatype_name()
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


def _pairwise_chain(cur, nodes, pred, annotations=None):
    # nodes/nodes[1:] are deliberately always length-1 apart (the sliding-
    # window pairwise idiom) - strict=True would always raise here, not
    # catch a real mismatch.
    # Annotations on the axiom annotate every pairwise triple it expands to (OWL 2 RDF mapping).
    for a, b in zip(nodes, nodes[1:]):  # noqa: B905
        cur.triples.append((a, pred, b))
        _maybe_reify(cur, a, pred, b, annotations)


def _nary_disjoint_or_different(cur, nodes, binary_pred, collection_class, annotations=None):
    if len(nodes) == 2:
        cur.triples.append((nodes[0], binary_pred, nodes[1]))
        _maybe_reify(cur, nodes[0], binary_pred, nodes[1], annotations)
        return
    node = cur.mint_bnode()
    cur.triples.append((node, RDF.type, collection_class))
    cur.triples.append((node, OWL.members, _build_list(cur, nodes)))
    # The n-ary form is one node, so the axiom's annotations hang directly off it.
    _annotation_triples(cur, node, annotations or ())


class _Annotation(tuple):
    """One annotation: ``(property, value)``, plus ``nested`` - the annotations on this annotation (the
    note's ``annotationAnnotatedList ::= [annotations] annotation ...``), or None.

    A 2-tuple subclass on purpose: every place that unpacks ``(prop, value)`` keeps working, and only the
    code that cares about annotations-of-annotations reads ``.nested``.
    """

    def __new__(cls, prop, value, nested=None):
        self = super().__new__(cls, (prop, value))
        self.nested = nested
        return self


def _parse_annotation_assertion(cur):
    nested = _parse_item_annotations(cur)
    prop = cur.read_name()
    return _Annotation(prop, cur.read_literal_or_name(), nested)


def _annotation_triples(cur, node, annotations):
    """Hang ``annotations`` on ``node``. An annotation that is itself annotated is reified as an
    ``owl:Annotation`` (OWL 2 RDF mapping, annotations of annotations), recursively."""
    for ann in annotations:
        prop, value = ann
        cur.triples.append((node, prop, value))
        nested = getattr(ann, 'nested', None)
        if nested:
            inner = cur.mint_bnode()
            cur.triples.append((inner, RDF.type, OWL.Annotation))
            cur.triples.append((inner, OWL.annotatedSource, node))
            cur.triples.append((inner, OWL.annotatedProperty, prop))
            cur.triples.append((inner, OWL.annotatedTarget, value))
            _annotation_triples(cur, inner, nested)


def _handle_frame_annotations(cur, frame_kind, subject):
    """Parse the standalone `Annotations:` frame section (its own clause,
    listing annotationProperty/value pairs about the frame's own subject) -
    confirmed empirically to map straight to direct triples on that
    subject, no owl:Axiom reification involved. Distinct from - and much
    simpler than - annotating one specific item inside e.g. a SubClassOf:
    list (see _parse_item_annotations/_maybe_reify below), which *does*
    need reification.

    Args:
        cur: The parser cursor to read tokens from and append triples to.
        frame_kind: The enclosing frame's kind, passed through to
            cur.record_clause().
        subject: The frame's own subject, which each annotation triple is
            asserted directly on.
    """
    items = _parse_comma_list(cur, _parse_annotation_assertion)
    for ann in items:
        prop, value = ann
        cur.triples.append((subject, prop, value))
        # An annotation assertion is itself an axiom, so annotating it reifies it as owl:Axiom.
        _maybe_reify(cur, subject, prop, value, getattr(ann, 'nested', None))
    cur.record_clause(frame_kind, 'Annotations:', items)


def _parse_item_annotations(cur):
    """Parse an optional `Annotations: prop val, prop val, ...` immediately
    before one axiom-list item (or before a whole single-axiom clause's
    body, e.g. HasKey:/DisjointUnionOf:/SubPropertyChain:) - confirmed
    empirically against the OWL API oracle to apply to exactly that one
    item/clause, never carrying over to a later comma-separated item
    (`SubClassOf: Annotations: rdfs:comment "why" A, B` only reifies the
    A axiom, not B).

    Args:
        cur: The parser cursor to read tokens from.

    Returns:
        A list of (prop, value) pairs, or None if no Annotations: prefix
        was written here - the grammar has no "annotated with nothing"
        form, so None unambiguously means absence.
    """
    if cur.peek_word() != 'Annotations:':
        return None
    cur.advance()
    return _parse_comma_list(cur, _parse_annotation_assertion)


def _annotated(parse_item):
    """Wrap an item-parser so _parse_comma_list collects (annotations,
    item) pairs instead of bare items - used at every clause-list call
    site whose items each become their own axiom.

    Args:
        parse_item: The item-parser function to wrap, e.g.
            _parse_description or _parse_property_expr.

    Returns:
        A function of cur that returns (annotations, item) - annotations
        from _parse_item_annotations(cur), item from parse_item(cur).
    """
    return lambda c: (_parse_item_annotations(c), parse_item(c))


def _maybe_reify(cur, subject, pred, obj, annotations):
    """If `annotations` came from a real Annotations: prefix (not None),
    add the owl:Axiom reification block the OWL 2 RDF mapping's
    "Annotations of Axioms" section uses - alongside the plain
    (subject, pred, obj) triple the caller already asserted, never
    instead of it, the same principle RDF 1.2's own `{| |}` annotation
    block follows (see turtle_parser.py) even though the concrete
    mechanism differs (real reification here, not a triple-term).

    Args:
        cur: The parser cursor to append triples to.
        subject: The annotated axiom's subject.
        pred: The annotated axiom's predicate.
        obj: The annotated axiom's object.
        annotations: A list of (prop, value) pairs from
            _parse_item_annotations(), or None to do nothing.
    """
    if annotations is None:
        return
    node = cur.mint_bnode()
    cur.triples.append((node, RDF.type, OWL.Axiom))
    cur.triples.append((node, OWL.annotatedSource, subject))
    cur.triples.append((node, OWL.annotatedProperty, pred))
    cur.triples.append((node, OWL.annotatedTarget, obj))
    _annotation_triples(cur, node, annotations)


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
    cur.record_frame('Class', subject)

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, 'Class', subject)
            return
        if clause == 'SuperClassOf:':
            items = _parse_comma_list(cur, _annotated(_parse_description))
            for anns, expr in items:
                node = _expr_node(cur, expr)
                cur.triples.append((node, RDFS.subClassOf, subject))
                _maybe_reify(cur, node, RDFS.subClassOf, subject, anns)
            cur.record_clause('Class', clause, items)
            return
        if clause == 'DisjointUnionOf:':
            anns = _parse_item_annotations(cur)
            exprs = _parse_comma_list(cur, _parse_description)
            nodes = [_expr_node(cur, e) for e in exprs]
            obj = _build_list(cur, nodes)
            cur.triples.append((subject, OWL.disjointUnionOf, obj))
            _maybe_reify(cur, subject, OWL.disjointUnionOf, obj, anns)
            cur.record_clause('Class', clause, [(anns, exprs)])
            return
        if clause == 'HasKey:':
            anns = _parse_item_annotations(cur)
            prop_exprs = _parse_comma_list(cur, _parse_property_expr)
            nodes = [_prop_node(cur, e) for e in prop_exprs]
            obj = _build_list(cur, nodes)
            cur.triples.append((subject, OWL.hasKey, obj))
            _maybe_reify(cur, subject, OWL.hasKey, obj, anns)
            cur.record_clause('Class', clause, [(anns, prop_exprs)])
            return
        pred = {
            'SubClassOf:': RDFS.subClassOf,
            'EquivalentTo:': OWL.equivalentClass,
            'DisjointWith:': OWL.disjointWith,
        }[clause]
        items = _parse_comma_list(cur, _annotated(_parse_description))
        for anns, expr in items:
            node = _expr_node(cur, expr)
            cur.triples.append((subject, pred, node))
            _maybe_reify(cur, subject, pred, node, anns)
        cur.record_clause('Class', clause, items)

    _frame_body(cur, _CLASS_CLAUSES, _CLASS_DEFERRED, handle)
    cur.record_frame_end()


def _parse_property_frame(cur, frame_kind, rdf_type, clauses, deferred, range_is_class_expr):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, rdf_type))
    cur.record_frame(frame_kind, subject)

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, frame_kind, subject)
            return
        if clause == 'Characteristics:':
            items = _parse_comma_list(cur, _annotated(lambda c: c.advance()['text']))
            resolved = []
            for anns, name in items:
                if name not in _CHARACTERISTICS:
                    cur.error(f'unknown property characteristic {name!r}')
                obj = _CHARACTERISTICS[name]
                cur.triples.append((subject, RDF.type, obj))
                _maybe_reify(cur, subject, RDF.type, obj, anns)
                resolved.append((anns, obj))
            cur.record_clause(frame_kind, clause, resolved)
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
            cur.record_clause(frame_kind, clause, [(anns, chain)])
            return
        if clause == 'SuperPropertyOf:':
            items = _parse_comma_list(cur, _annotated(_parse_property_expr))
            for anns, expr in items:
                node = _prop_node(cur, expr)
                cur.triples.append((node, RDFS.subPropertyOf, subject))
                _maybe_reify(cur, node, RDFS.subPropertyOf, subject, anns)
            cur.record_clause(frame_kind, clause, items)
            return
        if clause == 'Range:' and not range_is_class_expr:
            items = _parse_comma_list(cur, _annotated(_parse_data_range))
            for anns, dr in items:
                obj = _data_range_node(cur, dr)
                cur.triples.append((subject, RDFS.range, obj))
                _maybe_reify(cur, subject, RDFS.range, obj, anns)
            cur.record_clause(frame_kind, clause, items)
            return
        if clause in ('SubPropertyOf:', 'EquivalentTo:', 'DisjointWith:', 'InverseOf:'):
            pred = {
                'SubPropertyOf:': RDFS.subPropertyOf,
                'EquivalentTo:': OWL.equivalentProperty,
                'DisjointWith:': OWL.propertyDisjointWith,
                'InverseOf:': OWL.inverseOf,
            }[clause]
            items = _parse_comma_list(cur, _annotated(_parse_property_expr))
            for anns, expr in items:
                node = _prop_node(cur, expr)
                cur.triples.append((subject, pred, node))
                _maybe_reify(cur, subject, pred, node, anns)
            cur.record_clause(frame_kind, clause, items)
            return
        # Domain: (both frame kinds), Range: (object-property case) - full
        # class-expression grammar.
        pred = {'Domain:': RDFS.domain, 'Range:': RDFS.range}[clause]
        items = _parse_comma_list(cur, _annotated(_parse_description))
        for anns, expr in items:
            node = _expr_node(cur, expr)
            cur.triples.append((subject, pred, node))
            _maybe_reify(cur, subject, pred, node, anns)
        cur.record_clause(frame_kind, clause, items)

    _frame_body(cur, clauses, deferred, handle)
    cur.record_frame_end()


def _parse_annotation_property_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, OWL.AnnotationProperty))
    cur.record_frame('AnnotationProperty', subject)

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, 'AnnotationProperty', subject)
            return
        pred = {'Domain:': RDFS.domain, 'Range:': RDFS.range, 'SubPropertyOf:': RDFS.subPropertyOf}[clause]
        items = _parse_comma_list(cur, _annotated(lambda c: c.read_name()))
        for anns, name in items:
            cur.triples.append((subject, pred, name))
            _maybe_reify(cur, subject, pred, name, anns)
        cur.record_clause('AnnotationProperty', clause, items)

    _frame_body(cur, _ANNPROP_CLAUSES, _ANNPROP_DEFERRED, handle)
    cur.record_frame_end()


def _parse_fact(cur):
    negative = False
    if cur.peek_word() == 'not':
        cur.advance()
        negative = True
    prop = cur.read_name()
    value = cur.read_literal_or_name()
    return negative, prop, value


def _parse_individual_frame(cur):
    subject = cur.read_individual()
    if isinstance(subject, URIRef):
        # A nodeID names an anonymous individual: it is not declared owl:NamedIndividual.
        cur.triples.append((subject, RDF.type, OWL.NamedIndividual))
    cur.record_frame('Individual', subject)

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, 'Individual', subject)
        elif clause == 'Types:':
            items = _parse_comma_list(cur, _annotated(_parse_description))
            for anns, expr in items:
                node = _expr_node(cur, expr)
                cur.triples.append((subject, RDF.type, node))
                _maybe_reify(cur, subject, RDF.type, node, anns)
            cur.record_clause('Individual', clause, items)
        elif clause == 'Facts:':
            items = _parse_comma_list(cur, _annotated(_parse_fact))
            for anns, (negative, prop, value) in items:
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
            cur.record_clause('Individual', clause, items)
        else:
            pred = OWL.sameAs if clause == 'SameAs:' else OWL.differentFrom
            items = _parse_comma_list(cur, _annotated(lambda c: c.read_individual()))
            for anns, name in items:
                cur.triples.append((subject, pred, name))
                _maybe_reify(cur, subject, pred, name, anns)
            cur.record_clause('Individual', clause, items)

    _frame_body(cur, _INDIVIDUAL_CLAUSES, _INDIVIDUAL_DEFERRED, handle)
    cur.record_frame_end()


def _parse_datatype_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, RDFS.Datatype))
    cur.record_frame('Datatype', subject)

    def handle(clause):
        if clause == 'Annotations:':
            _handle_frame_annotations(cur, 'Datatype', subject)
            return
        # EquivalentTo: - a DatatypeDefinition axiom maps to owl:equivalentClass
        # per the OWL 2 RDF mapping, confirmed against the oracle the same
        # way as every other construct here.
        items = _parse_comma_list(cur, _annotated(_parse_data_range))
        for anns, dr in items:
            node = _data_range_node(cur, dr)
            cur.triples.append((subject, OWL.equivalentClass, node))
            _maybe_reify(cur, subject, OWL.equivalentClass, node, anns)
        cur.record_clause('Datatype', clause, items)

    _frame_body(cur, _DATATYPE_CLAUSES, _DATATYPE_DEFERRED, handle)
    cur.record_frame_end()


def _parse_misc(cur, keyword):
    # misc ::= 'EquivalentClasses:' annotations description2List | ... - one optional Annotations:
    # prefix for the whole axiom.
    annotations = _parse_item_annotations(cur)
    if keyword in ('EquivalentClasses:', 'DisjointClasses:'):
        exprs = _parse_comma_list(cur, _parse_description)
        nodes = [_expr_node(cur, e) for e in exprs]
        if keyword == 'EquivalentClasses:':
            _pairwise_chain(cur, nodes, OWL.equivalentClass, annotations)
        else:
            _nary_disjoint_or_different(cur, nodes, OWL.disjointWith, OWL.AllDisjointClasses, annotations)
        cur.record_misc(keyword, exprs, annotations)
    elif keyword in ('EquivalentProperties:', 'DisjointProperties:'):
        prop_exprs = _parse_comma_list(cur, _parse_property_expr)
        nodes = [_prop_node(cur, e) for e in prop_exprs]
        if keyword == 'EquivalentProperties:':
            _pairwise_chain(cur, nodes, OWL.equivalentProperty, annotations)
        else:
            _nary_disjoint_or_different(
                cur, nodes, OWL.propertyDisjointWith, OWL.AllDisjointProperties, annotations
            )
        cur.record_misc(keyword, prop_exprs, annotations)
    else:
        names = _parse_comma_list(cur, lambda c: c.read_individual())
        if keyword == 'SameIndividual:':
            _pairwise_chain(cur, names, OWL.sameAs, annotations)
        else:
            _nary_disjoint_or_different(cur, names, OWL.differentFrom, OWL.AllDifferent, annotations)
        cur.record_misc(keyword, names, annotations)


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def _run_top_level(cur):
    """Drive ``cur`` through a whole document: Prefix:/Ontology: headers, frames and Misc axioms.

    Shared by ``parse_manchester`` and the syntax-tree parser in ``starlayer.starontology.manchester``
    (which drives it with a recording cursor), so a parsing fix is made once and cannot drift between
    the two entry points.
    """
    while True:
        tok = cur.peek()
        if tok is None:
            break
        word = cur.peek_word()
        if word is None:
            # A token that is not a keyword (stray IRI, string, number, punctuation) is not the end of
            # the document: ending here would silently discard everything after it.
            cur.error(f'expected a Prefix:/Ontology:/frame/Misc-axiom keyword, got {tok["text"]!r}')
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
            cur.record_prefix(prefix, iri_tok['text'])
        elif word == 'Ontology:':
            cur.advance()
            tok = cur.peek()
            ontology_iri = None
            version_iri = None
            if tok is not None and tok['kind'] == 'IRI':
                cur.advance()
                ontology_iri = cur.resolve_iri(tok['text'])
                cur.base = str(ontology_iri)
                # ontology ::= 'Ontology:' [ ontologyIRI [ versionIRI ] ] ...
                version_tok = cur.peek()
                if version_tok is not None and version_tok['kind'] == 'IRI':
                    cur.advance()
                    version_iri = cur.resolve_iri(version_tok['text'])
            # OWL 2 RDF mapping: the ontology is always a node typed owl:Ontology - a fresh blank node
            # when it has no IRI - and its imports and annotations hang off that node.
            ontology_node = ontology_iri if ontology_iri is not None else cur.mint_bnode()
            cur.triples.append((ontology_node, RDF.type, OWL.Ontology))
            if version_iri is not None:
                cur.triples.append((ontology_node, OWL.versionIRI, version_iri))
            imports = []
            while cur.peek_word() == 'Import:':
                cur.advance()
                imported = cur.read_name()
                imports.append(imported)
                cur.triples.append((ontology_node, OWL.imports, imported))
            # ... { import } { annotations } - the annotations belong to the ontology itself.
            annotations = None
            while cur.peek_word() == 'Annotations:':
                cur.advance()
                annotations = (annotations or []) + _parse_comma_list(cur, _parse_annotation_assertion)
            _annotation_triples(cur, ontology_node, annotations or ())
            cur.record_ontology_header(ontology_iri, imports, version_iri, annotations)
        elif word == 'Datatype:':
            cur.advance()
            _parse_datatype_frame(cur)
        elif word == 'Class:':
            cur.advance()
            _parse_class_frame(cur)
        elif word == 'ObjectProperty:':
            cur.advance()
            _parse_property_frame(cur, 'ObjectProperty', OWL.ObjectProperty, _OBJPROP_CLAUSES, _OBJPROP_DEFERRED, range_is_class_expr=True)
        elif word == 'DataProperty:':
            cur.advance()
            _parse_property_frame(cur, 'DataProperty', OWL.DatatypeProperty, _DATAPROP_CLAUSES, _DATAPROP_DEFERRED, range_is_class_expr=False)
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


def parse_manchester(text: str, base: str = None) -> list:
    """Parse Manchester OWL Syntax text and return a list of (s, p, o)
    triples.

    Args:
        text: The Manchester OWL Syntax document text to parse.
        base: Seeds resolution of the `Ontology: <iri>` header and any
            other relative IRIs, the same role every other
            starlayer.graph parser's base argument plays.

    Returns:
        A list of (s, p, o) triples (plain rdflib terms -
        URIRef/BNode/Literal).
    """
    cur = _Cursor(_tokenize(text), base)
    _run_top_level(cur)
    return cur.triples
