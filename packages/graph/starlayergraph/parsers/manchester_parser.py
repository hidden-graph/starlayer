"""
starlayergraph.parsers.manchester_parser

Hand-rolled parser for OWL 2 Manchester Syntax (the frame-based
"Class: X SubClassOf: Y" notation), following the OWL 2 Mapping to RDF
Graphs spec to turn each frame/axiom into plain triples - ordinary
rdflib.BNode()s for owl:Restriction and rdf:List cells, no triple-term or
reification machinery, unlike turtle_parser.py (Manchester syntax has no
equivalent concept).

Entry point: parse_manchester(text, base=None) -> list[tuple]

Supported subset (v1):

  Frames: Prefix:, Ontology:, Class:, ObjectProperty:, DataProperty:,
  AnnotationProperty:, Individual:

  Class: clauses:            SubClassOf:, EquivalentTo:, DisjointWith:
  Object/DataProperty clauses: Domain:, Range:, SubPropertyOf:, EquivalentTo:,
                              DisjointWith:, InverseOf: (object only),
                              Characteristics:
  AnnotationProperty clauses: Domain:, Range:, SubPropertyOf:
  Individual: clauses:       Types:, Facts:, SameAs:, DifferentFrom:
  Top-level Misc axioms:     EquivalentClasses:, DisjointClasses:,
                              SameIndividual:, DifferentIndividuals:

  Class expressions: atomic name, `and`/`or`/`not`, parenthesised grouping,
  `some`/`only`/`value`/`Self`, `min n`/`max n`/`exactly n` (qualified and
  unqualified), `{ind1, ind2, ...}` enumeration, `inverse p`.

Deliberately unsupported, raising ManchesterSyntaxError rather than
silently dropping or mis-parsing: Datatype: frames (and datatype facet
restrictions generally), DisjointUnionOf:, HasKey:, SubPropertyChain:,
axiom/frame Annotations: (owl:Axiom reification), negative Facts:
(`not prop value`), and any use of a name under the default `:` prefix
without an explicit `Prefix: :` declaration for it (no implicit
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
    'EquivalentClasses:', 'DisjointClasses:', 'SameIndividual:',
    'DifferentIndividuals:',
}

_CLASS_CLAUSES = {'SubClassOf:', 'EquivalentTo:', 'DisjointWith:'}
_CLASS_DEFERRED = {'DisjointUnionOf:', 'HasKey:', 'Annotations:'}

_OBJPROP_CLAUSES = {
    'Domain:', 'Range:', 'SubPropertyOf:', 'EquivalentTo:', 'DisjointWith:',
    'InverseOf:', 'Characteristics:',
}
_OBJPROP_DEFERRED = {'SubPropertyChain:', 'Annotations:'}

_DATAPROP_CLAUSES = {
    'Domain:', 'Range:', 'SubPropertyOf:', 'EquivalentTo:', 'DisjointWith:',
    'Characteristics:',
}
_DATAPROP_DEFERRED = {'Annotations:'}

_ANNPROP_CLAUSES = {'Domain:', 'Range:', 'SubPropertyOf:'}
_ANNPROP_DEFERRED = {'Annotations:'}

_INDIVIDUAL_CLAUSES = {'Types:', 'Facts:', 'SameAs:', 'DifferentFrom:'}
_INDIVIDUAL_DEFERRED = {'Annotations:'}

_CHARACTERISTICS = {
    'Functional': OWL.FunctionalProperty,
    'InverseFunctional': OWL.InverseFunctionalProperty,
    'Transitive': OWL.TransitiveProperty,
    'Symmetric': OWL.SymmetricProperty,
    'Asymmetric': OWL.AsymmetricProperty,
    'Reflexive': OWL.ReflexiveProperty,
    'Irreflexive': OWL.IrreflexiveProperty,
}

_RESTRICTION_KEYWORDS = {'some', 'only', 'value', 'Self', 'min', 'max', 'exactly'}


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# A bare word (keyword, prefixed name, integer, ...) never legally contains
# any of these - each unambiguously starts a different token form.
_WORD_STOP_CHARS = ('<', '"', '(', ')', ',', '{', '}')


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
            end = text.find('>', i + 1)
            if end == -1:
                err("unterminated IRI (missing '>')", i)
            tokens.append({'kind': 'IRI', 'text': text[i + 1:end], 'line': line})
            i = end + 1
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
        if c in '(),{}':
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
    left = _parse_primary(cur)
    items = [left]
    while cur.peek_word() == 'and':
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
        return tok['text'] not in ('and', 'or') and not tok['text'].endswith(':')
    return False


def _parse_restriction_tail(cur, prop_expr):
    kw = cur.advance()['text']
    if kw == 'some':
        return ('Some', prop_expr, _parse_primary(cur))
    if kw == 'only':
        return ('Only', prop_expr, _parse_primary(cur))
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
        items = _parse_comma_list(cur, _parse_description)
        pred = {
            'SubClassOf:': RDFS.subClassOf,
            'EquivalentTo:': OWL.equivalentClass,
            'DisjointWith:': OWL.disjointWith,
        }[clause]
        for expr in items:
            cur.triples.append((subject, pred, _expr_node(cur, expr)))

    _frame_body(cur, _CLASS_CLAUSES, _CLASS_DEFERRED, handle)


def _parse_property_frame(cur, rdf_type, clauses, deferred, range_is_class_expr):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, rdf_type))

    def handle(clause):
        if clause == 'Characteristics:':
            names = _parse_comma_list(cur, lambda c: c.advance()['text'])
            for name in names:
                if name not in _CHARACTERISTICS:
                    cur.error(f'unknown property characteristic {name!r}')
                cur.triples.append((subject, RDF.type, _CHARACTERISTICS[name]))
            return
        if clause == 'Range:' and not range_is_class_expr:
            items = _parse_comma_list(cur, lambda c: c.read_name())
            for datatype in items:
                cur.triples.append((subject, RDFS.range, datatype))
            return
        if clause in ('SubPropertyOf:', 'EquivalentTo:', 'DisjointWith:', 'InverseOf:'):
            items = _parse_comma_list(cur, _parse_property_expr)
            pred = {
                'SubPropertyOf:': RDFS.subPropertyOf,
                'EquivalentTo:': OWL.equivalentProperty,
                'DisjointWith:': OWL.propertyDisjointWith,
                'InverseOf:': OWL.inverseOf,
            }[clause]
            for expr in items:
                cur.triples.append((subject, pred, _prop_node(cur, expr)))
            return
        # Domain: (both frame kinds), Range: (object-property case) - full
        # class-expression grammar.
        items = _parse_comma_list(cur, _parse_description)
        pred = {'Domain:': RDFS.domain, 'Range:': RDFS.range}[clause]
        for expr in items:
            cur.triples.append((subject, pred, _expr_node(cur, expr)))

    _frame_body(cur, clauses, deferred, handle)


def _parse_annotation_property_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, OWL.AnnotationProperty))

    def handle(clause):
        items = _parse_comma_list(cur, lambda c: c.read_name())
        pred = {'Domain:': RDFS.domain, 'Range:': RDFS.range, 'SubPropertyOf:': RDFS.subPropertyOf}[clause]
        for name in items:
            cur.triples.append((subject, pred, name))

    _frame_body(cur, _ANNPROP_CLAUSES, _ANNPROP_DEFERRED, handle)


def _parse_fact(cur):
    if cur.peek_word() == 'not':
        cur.error("negative Facts: assertions ('not prop value') are not supported yet")
    prop = cur.read_name()
    value = cur.read_literal_or_name()
    return prop, value


def _parse_individual_frame(cur):
    subject = cur.read_name()
    cur.triples.append((subject, RDF.type, OWL.NamedIndividual))

    def handle(clause):
        if clause == 'Types:':
            for expr in _parse_comma_list(cur, _parse_description):
                cur.triples.append((subject, RDF.type, _expr_node(cur, expr)))
        elif clause == 'Facts:':
            for prop, value in _parse_comma_list(cur, _parse_fact):
                cur.triples.append((subject, prop, value))
        else:
            pred = OWL.sameAs if clause == 'SameAs:' else OWL.differentFrom
            for name in _parse_comma_list(cur, lambda c: c.read_name()):
                cur.triples.append((subject, pred, name))

    _frame_body(cur, _INDIVIDUAL_CLAUSES, _INDIVIDUAL_DEFERRED, handle)


def _parse_misc(cur, keyword):
    if keyword in ('EquivalentClasses:', 'DisjointClasses:'):
        nodes = [_expr_node(cur, e) for e in _parse_comma_list(cur, _parse_description)]
        if keyword == 'EquivalentClasses:':
            _pairwise_chain(cur, nodes, OWL.equivalentClass)
        else:
            _nary_disjoint_or_different(cur, nodes, OWL.disjointWith, OWL.AllDisjointClasses)
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
            if tok is not None and tok['kind'] == 'IRI':
                cur.advance()
                ontology_iri = cur.resolve_iri(tok['text'])
                cur.base = str(ontology_iri)
                cur.triples.append((ontology_iri, RDF.type, OWL.Ontology))
            if cur.peek_word() in ('Import:', 'Annotations:'):
                cur.error(f'{cur.peek_word()} in the Ontology: header is not supported yet')
        elif word == 'Datatype:':
            cur.error('Datatype: frames are not supported yet')
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
        elif word in ('EquivalentClasses:', 'DisjointClasses:', 'SameIndividual:', 'DifferentIndividuals:'):
            cur.advance()
            _parse_misc(cur, word)
        else:
            cur.error(f'expected a Prefix:/Ontology:/frame/Misc-axiom keyword, got {word!r}')

    return cur.triples
