"""starlayer.sparql.parse_sparql

A hand-written SPARQL 1.2 query parser, in the style of
``starlayer.graph.parsers.manchester_parser``: a position-carrying regex
tokenizer, then a recursive-descent parser with one method per grammar
production, building a small in-memory AST (:class:`Node`). No rdflib parser,
no pyparsing, and nothing from ``salg``.

Covers the whole SPARQL 1.2 Query grammar (section 19.7): the prologue
(``BASE``, ``PREFIX``, ``VERSION``), ``SELECT``/``ASK``/``CONSTRUCT``/
``DESCRIBE`` with ``FROM``/``FROM NAMED``, every ``WHERE`` element (triple
patterns with ``;`` ``,`` ``[ ]`` ``( )``, RDF 1.2 triple terms, reified
triples, reifiers, annotations, property paths with negated sets,
``OPTIONAL``, ``UNION``, ``MINUS``, ``GRAPH``, ``SERVICE [SILENT]``,
``FILTER``, ``BIND``, ``VALUES``, sub-selects), expressions with the full
built-in list and the aggregates, and the solution modifiers. The static
rules the grammar leaves to prose (section 19.7 notes and 18.3.1 scope) are
enforced by :class:`_Checker` and the parser itself (blank node labels per
basic graph pattern).

``parse_sparql_update`` covers the Update grammar ([3], [31]-[53]): ``LOAD``, ``CLEAR``, ``DROP``, ``CREATE``, ``ADD``,
``MOVE``, ``COPY``, ``INSERT DATA``, ``DELETE DATA``, ``DELETE WHERE`` and ``[WITH] DELETE/INSERT ... [USING [NAMED]]
WHERE``, a prologue in front of every operation, ``GRAPH`` blocks in quad data and templates, and the static rules: no
variables in ``INSERT DATA`` / ``DELETE DATA``; no blank nodes (labels, ``[]``, collections, annotations, reified triples
without a reifier, an empty ``~``) in ``DELETE DATA``, ``DELETE WHERE`` and ``DELETE`` templates; a blank node label
written in one ``INSERT DATA`` cannot be reused in another operation; WHERE patterns follow the query rules. SPARQL Update is parsed by :func:`parse_sparql_update` (see below).

The AST is one generic class, :class:`Node` (``kind`` plus an ordered ``f``
dict), because the ``sqe:``/``spexpr:`` vocabulary is itself generic: an
expression node of kind ``Builtin_STR`` with field ``arg`` is encoded as
``[] a spexpr:Builtin_STR ; spexpr:arg ...``. :func:`sparql_to_tree` encodes
the AST as ``sqe:`` RDF (the same shapes ``sqe.sqe_parse_to_tree`` produces),
so ``sqe_tree_to_text`` works on its output.

Entry points::

    parse_sparql(text, base=None) -> Node
    sparql_to_tree(text, base=None, graph=None, root=None) -> (Graph, root)
    parse_sparql_update(text, base=None) -> Node                # an UpdateRequest
    sparql_update_to_tree(text, base=None, graph=None, root=None) -> (Graph, root)

Errors are :class:`SparqlSyntaxError` with ``line``/``col``/``pos``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, NamedTuple

# Terms are pyoxigraph terms (``_oxterms`` makes the stand-ins for text an RDF term cannot be: a relative IRI, a bad label).
import pyoxigraph as ox

from starlayer.sparql import _oxterms as T
from starlayer.sparql._oxterms import RDF, XSD

if TYPE_CHECKING:
    from starlayer.graph.oxgraph.core import StarLayerGraph

Variable = ox.Variable


def _vn(v) -> str:
    """A variable as ``?name`` (for messages)."""
    return "?" + v.value


_URI_RE = re.compile(r"^(?:([A-Za-z][A-Za-z0-9+.\-]*):)?(?://([^/?#]*))?([^?#]*)(?:\?([^#]*))?(?:#(.*))?$", re.S)


def _remove_dot_segments(path: str) -> str:
    """RFC 3986 5.2.4."""
    out: list[str] = []
    segs = path.split("/")
    for i, seg in enumerate(segs):
        last = i == len(segs) - 1
        if seg == ".":
            if last:
                out.append("")
        elif seg == "..":
            if len(out) > 1 or (out and out[0] != ""):
                out.pop()
            if last:
                out.append("")
        else:
            out.append(seg)
    return "/".join(out)


def _join(base_uri, ref):
    """RFC 3986 5.2 reference resolution (not ``urllib.parse.urljoin``, which collapses empty path segments, keeps the
    base fragment for an empty reference and does not resolve against ``urn:``)."""
    rs, ra, rp, rq, rf = _URI_RE.match(ref).groups()
    bs, ba, bp, bq, _bf = _URI_RE.match(base_uri).groups()
    if rs is not None:
        scheme, auth, path, query = rs, ra, _remove_dot_segments(rp), rq
    elif ra is not None:
        scheme, auth, path, query = bs, ra, _remove_dot_segments(rp), rq
    else:
        scheme, auth = bs, ba
        if rp == "":
            path, query = bp, (rq if rq is not None else bq)
        else:
            if rp.startswith("/"):
                path = _remove_dot_segments(rp)
            else:
                merged = "/" + rp if ba is not None and bp == "" else bp[: bp.rfind("/") + 1] + rp
                path = _remove_dot_segments(merged)
            query = rq
    out = ""
    if scheme is not None:
        out += scheme + ":"
    if auth is not None:
        out += "//" + auth
    out += path
    if query is not None:
        out += "?" + query
    if rf is not None:
        out += "#" + rf
    return out


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SparqlSyntaxError(ValueError):
    """A syntax error, with the 0-based offset ``pos`` and 1-based ``line``/``col`` it was found at."""

    def __init__(self, why: str, text: str = "", pos: int = 0):
        self.why = why
        self.pos = pos
        self.line = text.count("\n", 0, pos) + 1
        self.col = pos - (text.rfind("\n", 0, pos) + 1) + 1
        super().__init__(f"SPARQL syntax error at line {self.line}, column {self.col}: {why}")


# ---------------------------------------------------------------------------
# Tokenizer (SPARQL 1.2 terminals [139]-[194])
# ---------------------------------------------------------------------------

_BASE = (
    "A-Za-zÀ-ÖØ-öø-˿Ͱ-ͽͿ-῿‌-‍"
    "⁰-↏Ⰰ-⿯、-퟿豈-﷏ﷰ-�\U00010000-\U000effff"
)
_U = _BASE + "_"
_CH = _U + "0-9·̀-ͯ‿-⁀-"
_PN_PREFIX = rf"[{_BASE}](?:[{_CH}.]*[{_CH}])?"
_PLX = r"(?:%[0-9A-Fa-f]{2}|\\[_~.\-!$&'()*+,;=/?#@%])"
_PN_LOCAL = rf"(?:[{_U}:0-9]|{_PLX})(?:(?:[{_CH}.:]|{_PLX})*(?:[{_CH}:]|{_PLX}))?"
_VARNAME = rf"[{_U}0-9][{_U}0-9·̀-ͯ‿-⁀]*"
_EXP = r"[eE][+-]?[0-9]+"

_TOKEN = re.compile(
    "|".join(
        [
            r"(?P<ws>[ \t\r\n]+|#[^\r\n]*)",
            r"(?P<P>\<\<\(|\)\>\>|\<\<|\>\>)",
            r"(?P<IRI>\<(?:[^<>\"{}|^`\\\x00-\x20]|\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8})*\>)",
            r'(?P<STR>"""(?:(?:"|"")?(?:[^"\\]|\\.))*"""|' + r"'''(?:(?:'|'')?(?:[^'\\]|\\.))*'''|"
            r'"(?:[^"\\\n\r]|\\.)*"|' + r"'(?:[^'\\\n\r]|\\.)*')",
            rf"(?P<VAR>[?$]{_VARNAME})",
            rf"(?P<BNODE>_:[{_U}0-9](?:[{_CH}.]*[{_CH}])?)",
            r"(?P<LANG>@[a-zA-Z]+(?:-[a-zA-Z0-9]+)*(?:--[a-zA-Z]+)?)",
            rf"(?P<DBL>(?:[0-9]+\.[0-9]*|\.[0-9]+|[0-9]+){_EXP})",
            r"(?P<DEC>[0-9]*\.[0-9]+)",
            r"(?P<INT>[0-9]+)",
            rf"(?P<PNAME>(?:{_PN_PREFIX})?:(?:{_PN_LOCAL})?)",
            r"(?P<W>[A-Za-z_][A-Za-z0-9_]*)",
            r"(?P<P2>\^\^|&&|\|\||!=|<=|>=|\{\||\|\})",
            r"(?P<P1>[{}()\[\];,.*/+\-?!=<>|^~@])",
        ]
    ),
    re.DOTALL,
)

_UCHAR = re.compile(r"\\u([0-9A-Fa-f]{4})|\\U([0-9A-Fa-f]{8})")
_ECHAR = {"t": "\t", "b": "\b", "n": "\n", "r": "\r", "f": "\f", "\\": "\\", '"': '"', "'": "'"}


class Tok(NamedTuple):
    kind: str  # IRI STR VAR BNODE LANG DBL DEC INT PNAME W P EOF
    text: str
    pos: int


def _decode_uchars(raw: str) -> str:
    """Decode ``\\uXXXX``/``\\UXXXXXXXX`` (SPARQL 1.2 allows them only in strings and IRIs). A surrogate is rejected."""

    def sub(m):
        code = int(m.group(1) or m.group(2), 16)
        if 0xD800 <= code <= 0xDFFF or code > 0x10FFFF:
            raise SparqlSyntaxError(f"{m.group(0)} is not a Unicode scalar value", raw, m.start())
        return chr(code)

    return _UCHAR.sub(sub, raw)


def _split_keywords(word: str) -> list[tuple[str, str]] | None:
    """Longest-match tokenization of a run of letters and digits that is no keyword itself, as (kind, text) pairs
    (``FILTERSTR`` -> FILTER, STR; ``LIMIT1`` -> LIMIT, INTEGER 1).

    The grammar has no terminal for such a run, so its terminals are matched longest first, one after the other
    (section 19.7: "the longest match is chosen"). Returns None unless every letter run splits into keywords.
    """
    if not word.isalnum() or not word.isascii() or not word[0].isalpha() or len(word) > 40:
        return None
    parts: list[tuple[str, str]] = []
    for run in re.findall(r"[0-9]+|[A-Za-z]+", word):
        if run[0].isdigit():
            parts.append(("INT", run))
            continue
        rest = run
        while rest:
            for k in range(len(rest), 1, -1):
                if rest[:k].upper() in _KEYWORDS or rest[:k] in _CASE_SENSITIVE_WORDS:
                    parts.append(("W", rest[:k]))
                    rest = rest[k:]
                    break
            else:
                return None
    return parts


def tokenize(text: str) -> list[Tok]:
    out: list[Tok] = []
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if m is None:
            raise SparqlSyntaxError(f"unexpected character {text[pos]!r}", text, pos)
        kind = m.lastgroup
        if kind == "W" and m.group().upper() not in _KEYWORDS and m.group() not in _CASE_SENSITIVE_WORDS:
            parts = _split_keywords(m.group())
            if parts:
                at = pos
                for part_kind, part in parts:
                    out.append(Tok(part_kind, part, at))
                    at += len(part)
                pos = m.end()
                continue
        if kind != "ws":
            out.append(Tok("P" if kind in ("P2", "P1") else kind, m.group(), pos))
        pos = m.end()
    out.append(Tok("EOF", "", n))
    return out


def _unquote(raw: str) -> str:
    body = raw[3:-3] if raw[:3] in ('"""', "'''") else raw[1:-1]
    if "\\" not in body:
        return body

    def sub(m):
        c = m.group(1)
        if c[0] in ("u", "U") and len(c) > 1:
            return _decode_uchars("\\" + c)
        if c not in _ECHAR:
            raise SparqlSyntaxError(f"invalid string escape \\{c}", raw, m.start())
        return _ECHAR[c]

    return re.sub(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)", sub, body, flags=re.DOTALL)


# ---------------------------------------------------------------------------
# AST
# ---------------------------------------------------------------------------


class Node:
    """An AST node: ``kind`` plus ordered fields. Terms (IRI, literal, variable) are pyoxigraph terms, not Nodes."""

    __slots__ = ("kind", "f", "pos")

    def __init__(self, kind: str, **f):
        self.kind = kind
        self.f = f
        self.pos = 0  # source offset, set by the parser on the nodes the static checks report on

    def __getitem__(self, key):
        return self.f.get(key)

    def __repr__(self):
        return f"{self.kind}({', '.join(f'{k}={v!r}' for k, v in self.f.items())})"


_RDF_REIFIES = RDF.reifies

_ZERO = ("NOW", "UUID", "STRUUID", "RAND")
_ONE = (
    "STR LANG DATATYPE IRI URI ABS CEIL FLOOR ROUND STRLEN UCASE LCASE ENCODE_FOR_URI YEAR MONTH DAY HOURS MINUTES "
    "SECONDS TIMEZONE TZ MD5 SHA1 SHA256 SHA384 SHA512 isIRI isURI isBLANK isLITERAL isNUMERIC isTRIPLE SUBJECT "
    "PREDICATE OBJECT LANGDIR hasLANG hasLANGDIR"
).split()
_TWO = "LANGMATCHES CONTAINS STRSTARTS STRENDS STRBEFORE STRAFTER STRLANG STRDT sameTerm".split()
_BUILTIN_BY_UPPER = {n.upper(): n for n in (*_ZERO, *_ONE, *_TWO, "BOUND", "BNODE", "IF", "CONCAT", "COALESCE")}
_AGGS = {"COUNT", "SUM", "MIN", "MAX", "AVG", "SAMPLE", "GROUP_CONCAT"}

_CASE_SENSITIVE_WORDS = {"a", "true", "false", "isIRI", "isURI", "isBLANK", "isLITERAL", "isNUMERIC", "isTRIPLE", "hasLANG",
                         "hasLANGDIR", "sameTerm"}  # fmt: skip
_KEYWORDS = (
    {w.upper() for w in _CASE_SENSITIVE_WORDS - {"a", "true", "false"}}
    | set(_BUILTIN_BY_UPPER)
    | _AGGS
    | set(
        "BASE PREFIX VERSION SELECT DISTINCT REDUCED CONSTRUCT DESCRIBE ASK FROM NAMED WHERE GROUP BY HAVING ORDER ASC DESC "
        "LIMIT OFFSET VALUES UNDEF OPTIONAL GRAPH SERVICE SILENT BIND AS MINUS UNION FILTER NOT IN EXISTS SEPARATOR REGEX "
        "SUBSTR REPLACE STRLANGDIR TRIPLE "
        "LOAD INTO CLEAR DROP CREATE ADD MOVE COPY TO DEFAULT ALL DATA INSERT DELETE WITH USING".split()
    )
)

_RESERVED_AFTER_TRIPLES = {
    "OPTIONAL", "MINUS", "GRAPH", "FILTER", "BIND", "VALUES", "SERVICE", "UNION", "SELECT",
}  # fmt: skip


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class _Parser:
    def __init__(self, text: str, base: str | None):
        self.text = text
        self.toks = tokenize(self.text)
        self.i = 0
        self.base = base
        self.prefixes: dict[str, str] = {}
        self.prologue: list[tuple] = []
        # Blank node labels may not be shared by two basic graph patterns (grammar note, section 19.6): every
        # group opens a fresh BGP id and every element other than FILTER (OPTIONAL, UNION, BIND, ...) ends the BGP.
        self._bgp_next = 0
        self._bgp = 0
        self._label_bgp: dict[tuple[bool, str], int] = {}
        # Update: a blank node label written in the data of one INSERT DATA may not be reused in another operation
        # (W3C syntax-update-54); labels of templates and patterns are per operation, and so is each solution's node.
        self._op = 0  # index of the operation being parsed
        self._data_op: int | None = None  # set while the QuadData of an INSERT DATA is parsed
        self._data_labels: dict[str, int] = {}
        self._in_template = False  # a CONSTRUCT template is not a basic graph pattern: its labels are a separate space

    def _fresh_bgp(self) -> int:
        self._bgp_next += 1
        return self._bgp_next

    # -- token helpers ------------------------------------------------------

    @staticmethod
    def _at(node: Node, pos: int) -> Node:
        node.pos = pos
        return node

    def peek(self, k: int = 0) -> Tok:
        return self.toks[min(self.i + k, len(self.toks) - 1)]

    def next(self) -> Tok:
        t = self.peek()
        self.i += 1
        return t

    def err(self, why: str, tok: Tok | None = None):
        tok = tok or self.peek()
        got = "end of input" if tok.kind == "EOF" else repr(tok.text)
        raise SparqlSyntaxError(f"{why} (found {got})", self.text, tok.pos)

    def at_kw(self, *names: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "W" and t.text.upper() in names

    def at_p(self, *ps: str, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "P" and t.text in ps

    def at_a(self, k: int = 0) -> bool:
        t = self.peek(k)
        return t.kind == "W" and t.text == "a"

    def accept_a(self) -> bool:
        if self.at_a():
            self.i += 1
            return True
        return False

    def accept_kw(self, name: str) -> bool:
        if self.at_kw(name):
            self.i += 1
            return True
        return False

    def accept_p(self, p: str) -> bool:
        if self.at_p(p):
            self.i += 1
            return True
        return False

    def expect_kw(self, name: str):
        if not self.accept_kw(name):
            self.err(f"expected {name}")

    def expect_p(self, p: str):
        if not self.accept_p(p):
            self.err(f"expected {p!r}")

    # -- terms --------------------------------------------------------------

    def _iri_string(self, raw: str) -> str:
        inner = _decode_uchars(raw[1:-1])
        if self.base and not re.match(r"[A-Za-z][A-Za-z0-9+.\-]*:", inner):
            inner = _join(self.base, inner)
        return inner

    def _iri_text(self, raw: str) -> ox.NamedNode:
        return T.iri(self._iri_string(raw))

    def _pname(self, tok: Tok) -> ox.NamedNode:
        prefix, _, local = tok.text.partition(":")
        if prefix not in self.prefixes:
            self.err(f"undeclared prefix {prefix!r}", tok)
        return T.iri(self.prefixes[prefix] + re.sub(r"\\(.)", r"\1", local))

    def iri(self) -> ox.NamedNode:
        t = self.peek()
        if t.kind == "IRI":
            self.i += 1
            return self._iri_text(t.text)
        if t.kind == "PNAME":
            self.i += 1
            return self._pname(t)
        self.err("expected an IRI")

    def at_iri(self, k: int = 0) -> bool:
        return self.peek(k).kind in ("IRI", "PNAME")

    def var(self) -> ox.Variable:
        t = self.peek()
        if t.kind != "VAR":
            self.err("expected a variable")
        self.i += 1
        return ox.Variable(t.text[1:])

    def bnode(self) -> ox.BlankNode:
        t = self.peek()
        if t.kind == "BNODE":
            self.i += 1
            label = t.text[2:]
            if self._data_op is not None and self._data_labels.setdefault(label, self._data_op) != self._data_op:
                self.err(f"blank node label {t.text} is already used in an INSERT DATA of another operation", t)
            if self._label_bgp.setdefault((self._in_template, label), self._bgp) != self._bgp:
                self.err(f"blank node label {t.text} is used in two different basic graph patterns", t)
            return T.bnode(label)
        if self.at_p("[") and self.at_p("]", k=1):
            self.i += 2
            return ox.BlankNode()
        self.err("expected a blank node")

    def at_bnode(self) -> bool:
        return self.peek().kind == "BNODE" or (self.at_p("[") and self.at_p("]", k=1))

    def string(self) -> ox.Literal:
        t = self.peek()
        if t.kind != "STR":
            self.err("expected a string")
        self.i += 1
        return T.plain_literal(_unquote(t.text))

    def at_literal(self) -> bool:
        t = self.peek()
        return t.kind in ("STR", "INT", "DEC", "DBL") or (t.kind == "W" and t.text in ("true", "false"))

    def literal(self, signed: bool = True) -> ox.Literal:
        """RDFLiteral | NumericLiteral | BooleanLiteral."""
        t = self.peek()
        if t.kind == "STR":
            s = _unquote(self.next().text)
            nx = self.peek()
            if nx.kind == "LANG":
                self.i += 1
                tag = nx.text[1:]
                if "--" in tag:
                    lang, direction = tag.split("--")
                    if direction not in ("ltr", "rtl"):
                        self.err("base direction must be ltr or rtl", nx)
                    return T.directional(s, lang, direction)
                return T.language_literal(s, tag)
            if nx.kind == "P" and nx.text == "^^":
                self.i += 1
                return T.typed_literal(s, self.iri())
            return T.plain_literal(s)
        sign = ""
        if signed and self.at_p("+", "-") and self.signed_number_ahead():
            sign = self.next().text
            t = self.peek()
        if t.kind in ("INT", "DEC", "DBL"):
            self.i += 1
            dt = {"INT": XSD.integer, "DEC": XSD.decimal, "DBL": XSD.double}[t.kind]
            return T.typed_literal(sign + t.text, dt)
        if t.kind == "W" and t.text in ("true", "false"):
            self.i += 1
            return T.typed_literal(t.text, XSD.boolean)
        self.err("expected a literal")

    def signed_number_ahead(self) -> bool:
        """A sign immediately followed by a number token: INTEGER_POSITIVE... (no white space between, grammar note)."""
        nx = self.peek(1)
        return nx.kind in ("INT", "DEC", "DBL") and nx.pos == self.peek().pos + 1

    def verb_simple(self):
        """Verb ::= VarOrIri | 'a'"""
        if self.peek().kind == "VAR":
            return self.var()
        if self.peek().kind == "W" and self.peek().text == "a":
            self.i += 1
            return RDF.type
        return self.iri()

    # -- prologue -----------------------------------------------------------

    def parse_prologue(self):
        while True:
            if self.accept_kw("BASE"):
                t = self.peek()
                if t.kind != "IRI":
                    self.err("expected an IRI after BASE")
                self.i += 1
                self.base = self._iri_string(t.text)
                self.prologue.append(("base", t.text[1:-1], self.base))
            elif self.accept_kw("PREFIX"):
                t = self.peek()
                if t.kind != "PNAME" or t.text.count(":") != 1 or not t.text.endswith(":"):
                    self.err("expected a prefix label ending in ':'")
                self.i += 1
                iri = self.peek()
                if iri.kind != "IRI":
                    self.err("expected an IRI after the prefix label")
                self.i += 1
                namespace = self._iri_string(iri.text)
                self.prefixes[t.text[:-1]] = namespace
                self.prologue.append(("prefix", t.text[:-1], namespace))
            elif self.accept_kw("VERSION"):
                t = self.peek()
                if t.kind != "STR" or t.text[:3] in ('"""', "'''"):
                    self.err("VERSION takes a short string literal")
                self.i += 1
                self.prologue.append(("version", _unquote(t.text)))
            else:
                return

    # -- query --------------------------------------------------------------

    def parse_query(self) -> Node:
        self.parse_prologue()
        if self.at_kw("SELECT"):
            q = self.select_query()
            q.kind = "SelectQuery"
        elif self.at_kw("ASK"):
            self.i += 1
            ds = self.dataset_clauses()
            where = self.where_clause()
            q = Node("AskQuery", datasets=ds, where=where)
            self.solution_modifier(q)
            self.values_clause(q)
        elif self.at_kw("CONSTRUCT"):
            q = self.construct_query()
        elif self.at_kw("DESCRIBE"):
            q = self.describe_query()
        else:
            self.err("expected SELECT, ASK, CONSTRUCT or DESCRIBE")
        if self.peek().kind != "EOF":
            self.err("unexpected text after the query")
        q.f["prologue"] = self.prologue
        _check_query(q, self.text)
        return q

    # -- update -------------------------------------------------------------

    def parse_update(self) -> Node:
        """Update ::= Prologue ( Update1 ( ';' Update )? )?   (UpdateUnit ::= Update)"""
        ops: list[Node] = []
        trailing: list = []
        while True:
            self.prologue = []  # the declarations written in front of this operation (prefixes and BASE stay in force)
            self.parse_prologue()
            if self.peek().kind == "EOF":
                trailing = self.prologue
                break
            decls = self.prologue
            # labels are scoped to one operation: the same label in two operations is two blank nodes (W3C
            # syntax-update-54, basic-update/insert-data-same-bnode), and basic graph patterns do not span operations
            self._label_bgp = {}
            self._op = len(ops)
            op = self.update1()
            op.f["prologue"] = decls
            ops.append(op)
            if self.peek().kind == "EOF":
                break
            if not self.accept_p(";"):
                self.err("expected ';' or the end of the update request")
        return Node("UpdateRequest", operations=ops, prologue=trailing)

    def update1(self) -> Node:
        t = self.peek()
        if t.kind != "W":
            self.err("expected an update operation")
        kw = t.text.upper()
        if kw == "LOAD":
            self.i += 1
            silent = self.accept_kw("SILENT")
            source = self.iri()
            into = self.graph_ref() if self.accept_kw("INTO") else None
            return self._at(Node("Load", silent=silent, source=source, into=into), t.pos)
        if kw in ("CLEAR", "DROP"):
            self.i += 1
            silent = self.accept_kw("SILENT")
            return self._at(Node(kw.capitalize(), silent=silent, target=self.graph_ref_all()), t.pos)
        if kw == "CREATE":
            self.i += 1
            silent = self.accept_kw("SILENT")
            return self._at(Node("Create", silent=silent, graph=self.graph_ref()), t.pos)
        if kw in ("ADD", "MOVE", "COPY"):
            self.i += 1
            silent = self.accept_kw("SILENT")
            src = self.graph_or_default()
            self.expect_kw("TO")
            return self._at(Node(kw.capitalize(), silent=silent, source=src, dest=self.graph_or_default()), t.pos)
        if kw == "INSERT" and self.at_kw("DATA", k=1):
            self.i += 2
            return self._at(Node("InsertData", quads=self.quad_block("INSERT DATA", variables=False, data=True)), t.pos)
        if kw == "DELETE" and self.at_kw("DATA", k=1):
            self.i += 2
            return self._at(
                Node("DeleteData", quads=self.quad_block("DELETE DATA", variables=False, bnodes=False)), t.pos
            )
        if kw == "DELETE" and self.at_kw("WHERE", k=1):
            self.i += 2
            return self._at(Node("DeleteWhere", quads=self.quad_block("DELETE WHERE", bnodes=False)), t.pos)
        if kw in ("WITH", "DELETE", "INSERT"):
            return self.modify()
        self.err("expected an update operation")

    def modify(self) -> Node:
        """Modify ::= ( 'WITH' iri )? ( DeleteClause InsertClause? | InsertClause ) UsingClause* 'WHERE' GroupGraphPattern"""
        at = self.peek().pos
        with_ = self.iri() if self.accept_kw("WITH") else None
        delete = insert = None
        if self.accept_kw("DELETE"):
            delete = self.quad_block("a DELETE template", bnodes=False)
            if self.accept_kw("INSERT"):
                insert = self.quad_block("an INSERT template")
        elif self.accept_kw("INSERT"):
            insert = self.quad_block("an INSERT template")
        else:
            self.err("expected DELETE or INSERT")
        using = []
        while self.accept_kw("USING"):
            named = self.accept_kw("NAMED")
            using.append((named, self.iri()))
        self.expect_kw("WHERE")
        where = self.group_graph_pattern()
        _Checker(self.text).group(where)
        return self._at(Node("Modify", with_=with_, delete=delete, insert=insert, using=using, where=where), at)

    def graph_ref(self) -> Node:
        """GraphRef ::= 'GRAPH' iri"""
        self.expect_kw("GRAPH")
        return Node("GraphRef", iri=self.iri())

    def graph_ref_all(self) -> Node:
        """GraphRefAll ::= GraphRef | 'DEFAULT' | 'NAMED' | 'ALL'"""
        for kw, kind in (("DEFAULT", "DefaultGraph"), ("NAMED", "NamedGraphs"), ("ALL", "AllGraphs")):
            if self.accept_kw(kw):
                return Node(kind)
        if self.at_kw("GRAPH"):
            return self.graph_ref()
        self.err("expected GRAPH, DEFAULT, NAMED or ALL")

    def graph_or_default(self) -> Node:
        """GraphOrDefault ::= 'DEFAULT' | 'GRAPH'? iri"""
        if self.accept_kw("DEFAULT"):
            return Node("DefaultGraph")
        self.accept_kw("GRAPH")
        return Node("GraphRef", iri=self.iri())

    def quad_block(self, what: str, variables: bool = True, bnodes: bool = True, data: bool = False) -> list:
        """QuadPattern / QuadData ::= '{' Quads '}' with Quads ::= TriplesTemplate? ( QuadsNotTriples '.'? TriplesTemplate? )*

        The result is the written order of ``TriplePattern`` (default graph) and ``QuadGraph`` nodes. ``variables`` /
        ``bnodes`` say whether this clause may contain them (the static rules of the Update grammar: no variables in
        INSERT DATA and DELETE DATA, no blank nodes in DELETE DATA, DELETE WHERE and DELETE templates).
        """
        start = self.peek()
        self.expect_p("{")
        outer = self._bgp, self._in_template
        self._bgp, self._in_template = self._fresh_bgp(), True  # a template's labels are their own space
        self._data_op = self._op if data else None
        items: list = []
        try:
            while True:
                if self.starts_triples():
                    self._quad_triples(items)
                elif self.at_kw("GRAPH"):
                    items.append(self.quads_not_triples())
                    self.accept_p(".")
                else:
                    break
            self.expect_p("}")
        finally:
            self._bgp, self._in_template = outer
            self._data_op = None
        for term in _quad_terms(items):
            if not variables and isinstance(term, ox.Variable):
                self.err(f"variables are not allowed in {what}", start)
            if not bnodes and isinstance(term, ox.BlankNode):
                self.err(
                    f"blank nodes (labels, [], collections, annotations and reified triples without an explicit "
                    f"reifier) are not allowed in {what}",
                    start,
                )
        return items

    def quads_not_triples(self) -> Node:
        """QuadsNotTriples ::= 'GRAPH' VarOrIri '{' TriplesTemplate? '}'"""
        at = self.next().pos
        term = self.var() if self.peek().kind == "VAR" else self.iri()
        self.expect_p("{")
        triples: list = []
        self._quad_triples(triples)
        self.expect_p("}")
        return self._at(Node("QuadGraph", term=term, triples=triples), at)

    def _quad_triples(self, out: list):
        """TriplesTemplate, with the '.' between triples required."""
        while self.starts_triples():
            self.triples_same_subject(out, path=False)
            if not self.accept_p("."):
                if self.starts_triples():
                    self.err("expected '.' between triples")
                return

    def select_clause(self, q: Node):
        self.expect_kw("SELECT")
        q.f["modifier"] = "DISTINCT" if self.accept_kw("DISTINCT") else "REDUCED" if self.accept_kw("REDUCED") else None
        proj: list = []
        if self.accept_p("*"):
            q.f["projection"] = None
            return
        while True:
            if self.peek().kind == "VAR":
                at = self.peek().pos
                proj.append(self._at(Node("ProjectVar", var=self.var()), at))
            elif self.at_p("("):
                at = self.next().pos
                e = self.expression()
                self.expect_kw("AS")
                v = self.var()
                self.expect_p(")")
                proj.append(self._at(Node("ProjectExpr", expr=e, var=v), at))
            else:
                break
        if not proj:
            self.err("expected '*' or a projection")
        q.f["projection"] = proj

    def select_query(self, sub: bool = False) -> Node:
        """SelectQuery, or (``sub``) SubSelect: the same without DatasetClause."""
        q = Node("SelectQuery")
        self.select_clause(q)
        q.f["datasets"] = [] if sub else self.dataset_clauses()
        q.f["where"] = self.where_clause()
        self.solution_modifier(q)
        self.values_clause(q)
        return q

    def describe_query(self) -> Node:
        """DescribeQuery ::= 'DESCRIBE' ( VarOrIri+ | '*' ) DatasetClause* WhereClause? SolutionModifier"""
        self.expect_kw("DESCRIBE")
        q = Node("DescribeQuery")
        if self.accept_p("*"):
            q.f["targets"] = None
        else:
            targets = []
            while self.peek().kind == "VAR" or self.at_iri():
                targets.append(self.var() if self.peek().kind == "VAR" else self.iri())
            if not targets:
                self.err("expected '*' or a variable or IRI after DESCRIBE")
            q.f["targets"] = targets
        q.f["datasets"] = self.dataset_clauses()
        q.f["where"] = self.where_clause() if self.at_kw("WHERE") or self.at_p("{") else None
        self.solution_modifier(q)
        self.values_clause(q)
        return q

    def dataset_clauses(self) -> list:
        out = []
        while self.accept_kw("FROM"):
            named = self.accept_kw("NAMED")
            out.append((named, self.iri()))
        return out

    def where_clause(self) -> list:
        self.accept_kw("WHERE")
        return self.group_graph_pattern()

    def construct_query(self) -> Node:
        self.expect_kw("CONSTRUCT")
        q = Node("ConstructQuery")
        if self.at_p("{"):
            self.i += 1
            template: list = []
            self.triples_template(template)
            self.expect_p("}")
            q.f["template"] = template
            q.f["datasets"] = self.dataset_clauses()
            q.f["where"] = self.where_clause()
        else:
            q.f["datasets"] = self.dataset_clauses()
            self.expect_kw("WHERE")
            self.expect_p("{")
            triples: list = []
            self.triples_template(triples)
            self.expect_p("}")
            q.f["template"] = None
            q.f["where"] = triples
        self.solution_modifier(q)
        self.values_clause(q)
        return q

    def triples_template(self, out: list):
        """TriplesTemplate: no property paths."""
        outer, self._in_template = self._in_template, True
        try:
            while self.starts_triples():
                self.triples_same_subject(out, path=False)
                if not self.accept_p("."):
                    break
        finally:
            self._in_template = outer

    # -- solution modifiers ---------------------------------------------------

    def solution_modifier(self, q: Node, allowed: bool = True):
        q.f.update(group_by=None, having=None, order_by=None, limit=None, offset=None)
        if not allowed:
            return
        if self.accept_kw("GROUP"):
            self.expect_kw("BY")
            conds = []
            while True:
                if self.peek().kind == "VAR":
                    conds.append(self.var())
                elif self.at_p("("):
                    at = self.next().pos
                    e = self.expression()
                    if self.accept_kw("AS"):
                        conds.append(self._at(Node("GroupAs", expr=e, var=self.var()), at))
                    else:
                        conds.append(e)
                    self.expect_p(")")
                elif self.starts_constraint():
                    conds.append(self.constraint())
                else:
                    break
            if not conds:
                self.err("expected a GROUP BY condition")
            q.f["group_by"] = conds
        if self.accept_kw("HAVING"):
            conds = []
            while self.starts_constraint() or self.at_p("("):
                conds.append(self.constraint())
            if not conds:
                self.err("expected a HAVING condition")
            q.f["having"] = conds
        if self.accept_kw("ORDER"):
            self.expect_kw("BY")
            conds = []
            while True:
                if self.at_kw("ASC", "DESC"):
                    desc = self.next().text.upper() == "DESC"
                    self.expect_p("(")
                    e = self.expression()
                    self.expect_p(")")
                    conds.append(Node("OrderCondition", expr=e, desc=desc))
                elif self.peek().kind == "VAR":
                    conds.append(Node("OrderCondition", expr=self.var(), desc=False))
                elif self.starts_constraint() or self.at_p("("):
                    conds.append(Node("OrderCondition", expr=self.constraint(), desc=False))
                else:
                    break
            if not conds:
                self.err("expected an ORDER BY condition")
            q.f["order_by"] = conds
        for _ in range(2):
            if self.at_kw("LIMIT") and q.f["limit"] is None:
                self.i += 1
                q.f["limit"] = self._integer()
            elif self.at_kw("OFFSET") and q.f["offset"] is None:
                self.i += 1
                q.f["offset"] = self._integer()

    def _integer(self) -> ox.Literal:
        t = self.peek()
        if t.kind != "INT":
            self.err("expected an integer")
        self.i += 1
        return T.typed_literal(t.text, XSD.integer)

    def values_clause(self, q: Node):
        q.f["values"] = self.inline_data() if self.at_kw("VALUES") else None

    # -- graph patterns -----------------------------------------------------

    def starts_triples(self) -> bool:
        t = self.peek()
        if t.kind in ("VAR", "IRI", "PNAME", "BNODE", "STR", "INT", "DEC", "DBL"):
            return True
        if t.kind == "W":
            return t.text in ("true", "false")
        return t.kind == "P" and (
            t.text in ("[", "(", "<<", "<<(") or (t.text in ("+", "-") and self.peek(1).kind in ("INT", "DEC", "DBL"))
        )

    def group_graph_pattern(self) -> list:
        self.expect_p("{")
        outer, self._bgp = self._bgp, self._fresh_bgp()
        try:
            return self._group_body()
        finally:
            self._bgp = outer

    def _group_body(self) -> list:
        if self.at_kw("SELECT"):
            sub = self.select_query(sub=True)
            sub.kind = "SubSelect"
            self.expect_p("}")
            return [sub]
        parts: list = []
        while not self.at_p("}"):
            if self.peek().kind == "EOF":
                self.err("unterminated group graph pattern, expected '}'")
            if self.starts_triples():
                self.triples_same_subject(parts, path=True)
                if not self.accept_p("."):
                    if self.starts_triples():
                        self.err("expected '.' between triple patterns")
                continue
            el = self.graph_pattern_not_triples()
            parts.append(el)
            if el.kind != "Filter":
                self._bgp = self._fresh_bgp()
            self.accept_p(".")
        self.expect_p("}")
        return parts

    def graph_pattern_not_triples(self) -> Node:
        if self.accept_kw("OPTIONAL"):
            return Node("Optional", where=self.group_graph_pattern())
        if self.accept_kw("MINUS"):
            return Node("Minus", where=self.group_graph_pattern())
        if self.accept_kw("GRAPH"):
            term = self.var() if self.peek().kind == "VAR" else self.iri()
            return Node("Graph", term=term, where=self.group_graph_pattern())
        if self.accept_kw("SERVICE"):
            silent = self.accept_kw("SILENT")
            term = self.var() if self.peek().kind == "VAR" else self.iri()
            return Node("Service", silent=silent, term=term, where=self.group_graph_pattern())
        if self.accept_kw("FILTER"):
            return Node("Filter", expr=self.constraint())
        if self.at_kw("BIND"):
            at = self.next().pos
            self.expect_p("(")
            e = self.expression()
            self.expect_kw("AS")
            v = self.var()
            self.expect_p(")")
            return self._at(Node("Bind", expr=e, var=v), at)
        if self.at_kw("VALUES"):
            return self.inline_data()
        if self.at_p("{"):
            alts = [self.group_graph_pattern()]
            while self.accept_kw("UNION"):
                alts.append(self.group_graph_pattern())
            return Node("Union", alts=alts)
        self.err("expected a graph pattern")

    def inline_data(self) -> Node:
        self.expect_kw("VALUES")
        if self.peek().kind == "VAR":
            vars_ = [self.var()]
            self.expect_p("{")
            rows = []
            while not self.at_p("}"):
                rows.append([self.data_value()])
            self.expect_p("}")
        else:
            self.expect_p("(")
            vars_ = []
            while self.peek().kind == "VAR":
                vars_.append(self.var())
            self.expect_p(")")
            self.expect_p("{")
            rows = []
            while not self.at_p("}"):
                self.expect_p("(")
                row = []
                while not self.at_p(")"):
                    row.append(self.data_value())
                self.expect_p(")")
                if len(row) != len(vars_):
                    self.err(f"VALUES row has {len(row)} values for {len(vars_)} variables")
                rows.append(row)
            self.expect_p("}")
        if len(set(vars_)) != len(vars_):
            self.err("a variable is repeated in VALUES")
        return Node("Values", vars=vars_, rows=rows)

    def data_value(self):
        if self.accept_kw("UNDEF"):
            return "UNDEF"
        if self.at_p("<<("):
            return self.triple_term(data=True)
        if self.at_iri():
            return self.iri()
        if self.at_literal() or self.at_p("+", "-"):
            return self.literal()
        self.err("expected a value in VALUES")

    # -- triples ------------------------------------------------------------

    def triples_same_subject(self, out: list, path: bool):
        if self.at_p("<<"):
            s = self.reified_triple(out)
            self.property_list(s, out, path, required=False)
        elif self.at_p("[", "(") and not self.at_bnode() and not (self.at_p("(") and self.at_p(")", k=1)):
            s = self.triples_node(out, path)
            self.property_list(s, out, path, required=False)
        else:
            s = self.var_or_term(out)
            self.property_list(s, out, path, required=True)

    def var_or_term(self, out: list):
        """GraphNode-position term: Var | iri | literal | BlankNode | NIL | TripleTerm."""
        t = self.peek()
        if t.kind == "VAR":
            return self.var()
        if t.kind in ("IRI", "PNAME"):
            return self.iri()
        if self.at_bnode():
            return self.bnode()
        if self.at_p("("):
            if self.at_p(")", k=1):
                self.i += 2
                return RDF.nil
            return self.triples_node(out, True)
        if self.at_p("<<("):
            return self.triple_term()
        if self.at_literal() or self.at_p("+", "-"):
            return self.literal()
        self.err("expected an RDF term or variable")

    def graph_node(self, out: list, path: bool):
        if self.at_p("[") and not self.at_bnode():
            return self.triples_node(out, path)
        if self.at_p("("):
            return self.triples_node(out, path)
        if self.at_p("<<"):
            return self.reified_triple(out)
        return self.var_or_term(out)

    def triples_node(self, out: list, path: bool):
        if self.accept_p("["):
            b = ox.BlankNode()
            self.property_list(b, out, path, required=True)
            self.expect_p("]")
            return b
        self.expect_p("(")
        items = []
        while not self.at_p(")"):
            if self.peek().kind == "EOF":
                self.err("unterminated collection")
            items.append(self.graph_node(out, path))
        self.expect_p(")")
        if not items:
            return RDF.nil
        head = ox.BlankNode()
        cur = head
        for k, item in enumerate(items):
            out.append(Node("TriplePattern", s=cur, p=RDF.first, o=item))
            nxt = RDF.nil if k == len(items) - 1 else ox.BlankNode()
            out.append(Node("TriplePattern", s=cur, p=RDF.rest, o=nxt))
            cur = nxt
        return head

    def verb_path(self, path: bool):
        if self.peek().kind == "VAR":
            return self.var()
        if not path:
            return self.verb_simple()
        return self.path_alternative()

    def property_list(self, s, out: list, path: bool, required: bool):
        if not (self.peek().kind in ("VAR", "IRI", "PNAME") or self.at_a() or (path and self.at_p("^", "!", "("))):
            if required:
                self.err("expected a predicate")
            return
        while True:
            p = self.verb_path(path)
            while True:
                o = self.graph_node(out, path)
                out.append(Node("TriplePattern", s=s, p=p, o=o))
                self.annotations(s, p, o, out, path)
                if not self.accept_p(","):
                    break
            if not self.accept_p(";"):
                return
            while self.accept_p(";"):
                pass
            if not (self.peek().kind in ("VAR", "IRI", "PNAME") or self.at_a() or (path and self.at_p("^", "!", "("))):
                return

    def annotations(self, s, p, o, out: list, path: bool):
        """AnnotationPath ::= ( Reifier | AnnotationBlockPath )*"""
        tt = None
        reifier = None
        while self.at_p("~", "{|"):
            if isinstance(p, Node):
                self.err("a reifier or annotation needs a single IRI or variable as its predicate, not a property path")
            if tt is None:
                tt = self._triple_term_node(s, p, o)
            if self.accept_p("~"):
                reifier = self.reifier_id()
                out.append(Node("TriplePattern", s=reifier, p=_RDF_REIFIES, o=tt))
            else:
                self.i += 1
                if reifier is None:
                    reifier = ox.BlankNode()
                    out.append(Node("TriplePattern", s=reifier, p=_RDF_REIFIES, o=tt))
                self.property_list(reifier, out, path, required=True)
                self.expect_p("|}")
                reifier = None
                continue
            if not self.at_p("{|"):
                reifier = None

    def reifier_id(self):
        if self.peek().kind == "VAR":
            return self.var()
        if self.at_iri():
            return self.iri()
        if self.at_bnode():
            return self.bnode()
        return ox.BlankNode()

    def reified_triple(self, out: list):
        """ReifiedTriple ::= '<<' ReifiedTripleSubject Verb ReifiedTripleObject Reifier? '>>'"""
        self.expect_p("<<")
        if self.at_p("<<"):
            s = self.reified_triple(out)
        elif self.at_p("<<("):
            s = self.triple_term()
        elif self.peek().kind == "VAR":
            s = self.var()
        elif self.at_iri():
            s = self.iri()
        elif self.at_bnode():
            s = self.bnode()
        elif self.at_literal() or self.at_p("+", "-"):
            s = self.literal()  # the grammar allows any term; a literal subject matches nothing
        else:
            self.err("expected a subject in a reified triple")
        p = self.verb_simple()
        if self.at_p("<<"):
            o = self.reified_triple(out)
        elif self.at_p("<<("):
            o = self.triple_term()
        elif self.peek().kind == "VAR":
            o = self.var()
        elif self.at_iri():
            o = self.iri()
        elif self.at_bnode():
            o = self.bnode()
        elif self.at_literal() or self.at_p("+", "-"):
            o = self.literal()
        else:
            self.err("expected an object in a reified triple")
        r = ox.BlankNode()
        if self.accept_p("~"):
            r = self.reifier_id()
        self.expect_p(">>")
        out.append(Node("TriplePattern", s=r, p=_RDF_REIFIES, o=self._triple_term_node(s, p, o)))
        return r

    @staticmethod
    def _triple_term_node(s, p, o) -> Node:
        return Node("TripleTerm", subject=s, predicate=p, object=o)

    def triple_term(self, data: bool = False) -> Node:
        """TripleTerm ::= '<<(' TripleTermSubject Verb TripleTermObject ')>>'  (data=True: TripleTermData)"""
        self.expect_p("<<(")
        if self.at_iri():
            s = self.iri()
        elif not data and self.peek().kind == "VAR":
            s = self.var()
        elif not data and self.at_bnode():
            s = self.bnode()
        elif not data and self.at_p("<<("):
            s = self.triple_term()  # allowed in patterns (W3C positive tests); not in VALUES or expressions
        elif not data and (self.at_literal() or self.at_p("+", "-")):
            s = self.literal()  # TripleTermSubject allows any term; a literal subject matches nothing
        else:
            self.err("expected a subject in a triple term")
        p = self.verb_simple() if not data else (RDF.type if self.accept_a() else self.iri())
        if isinstance(p, ox.Variable) and data:
            self.err("a variable cannot appear in a VALUES triple term")
        if self.at_p("<<("):
            o = self.triple_term(data)
        elif not data and self.peek().kind == "VAR":
            o = self.var()
        elif self.at_iri():
            o = self.iri()
        elif not data and self.at_bnode():
            o = self.bnode()
        elif self.at_literal() or self.at_p("+", "-"):
            o = self.literal()
        else:
            self.err("expected an object in a triple term")
        self.expect_p(")>>")
        return self._triple_term_node(s, p, o)

    # -- property paths -------------------------------------------------------

    def path_alternative(self):
        parts = [self.path_sequence()]
        while self.accept_p("|"):
            parts.append(self.path_sequence())
        return _flatten("AlternativePath", parts)

    def path_sequence(self):
        parts = [self.path_elt_or_inverse()]
        while self.accept_p("/"):
            parts.append(self.path_elt_or_inverse())
        return _flatten("SequencePath", parts)

    def path_elt_or_inverse(self):
        if self.accept_p("^"):
            return Node("InvPath", arg=self.path_elt())
        return self.path_elt()

    def path_elt(self):
        prim = self.path_primary()
        # a '+' touching a number is the signed number (INTEGER_POSITIVE is one token), not a path modifier: `:q +5`
        if self.at_p("?", "*", "+") and not (self.at_p("+") and self.signed_number_ahead()):
            return Node("MulPath", path=prim, mod=self.next().text)
        return prim

    def path_primary(self):
        if self.at_iri():
            return self.iri()
        if self.peek().kind == "W" and self.peek().text == "a":
            self.i += 1
            return RDF.type
        if self.accept_p("!"):
            if self.accept_p("("):
                parts = []
                if not self.at_p(")"):
                    parts.append(self.path_one_in_set())
                    while self.accept_p("|"):
                        parts.append(self.path_one_in_set())
                self.expect_p(")")
                return Node("NegatedPath", args=parts)
            return Node("NegatedPath", args=[self.path_one_in_set()])
        if self.accept_p("("):
            p = self.path_alternative()
            self.expect_p(")")
            return p
        self.err("expected a property path")

    def path_one_in_set(self):
        if self.accept_p("^"):
            return Node("InvPath", arg=RDF.type if self.accept_a() else self.iri())
        if self.accept_a():
            return RDF.type
        return self.iri()

    # -- expressions --------------------------------------------------------

    def starts_constraint(self) -> bool:
        t = self.peek()
        return t.kind in ("IRI", "PNAME") or (t.kind == "W" and self._is_builtin(t.text)) or self.at_p("(")

    def _is_builtin(self, word: str) -> bool:
        u = word.upper()
        return (
            u in _BUILTIN_BY_UPPER
            or u in _AGGS
            or u in ("REGEX", "SUBSTR", "REPLACE", "EXISTS", "NOT", "STRLANGDIR", "TRIPLE")
        )

    def constraint(self):
        """Constraint ::= BrackettedExpression | BuiltInCall | FunctionCall"""
        if self.at_p("("):
            return self.bracketted()
        if self.at_iri():
            return self.function_call()
        return self.builtin()

    def bracketted(self):
        self.expect_p("(")
        e = self.expression()
        self.expect_p(")")
        return e

    def expression(self):
        left = self.cond_and()
        others = []
        while self.accept_p("||"):
            others.append(self.cond_and())
        return Node("ConditionalOrExpression", expr=left, other=others) if others else left

    def cond_and(self):
        left = self.relational()
        others = []
        while self.accept_p("&&"):
            others.append(self.relational())
        return Node("ConditionalAndExpression", expr=left, other=others) if others else left

    def relational(self):
        left = self.additive()
        if self.at_p("=", "!=", "<", ">", "<=", ">="):
            op = self.next().text
            return Node("RelationalExpression", expr=left, op=op, other=self.additive())
        if self.at_kw("IN") or (self.at_kw("NOT") and self.at_kw("IN", k=1)):
            op = "NOT IN" if self.accept_kw("NOT") else "IN"
            self.expect_kw("IN")
            return Node("RelationalExpression", expr=left, op=op, other=self.expression_list())
        return left

    def expression_list(self) -> list:
        self.expect_p("(")
        items = []
        if not self.at_p(")"):
            items.append(self.expression())
            while self.accept_p(","):
                items.append(self.expression())
        self.expect_p(")")
        return items

    def additive(self):
        left = self.multiplicative()
        ops, others = [], []
        while self.at_p("+", "-"):
            ops.append(self.next().text)
            others.append(self.multiplicative())
        return Node("AdditiveExpression", expr=left, op=ops, other=others) if ops else left

    def multiplicative(self):
        left = self.unary()
        ops, others = [], []
        while self.at_p("*", "/"):
            ops.append(self.next().text)
            others.append(self.unary())
        return Node("MultiplicativeExpression", expr=left, op=ops, other=others) if ops else left

    def unary(self):
        if self.at_p("!"):
            self.i += 1
            return Node("UnaryNot", expr=self.unary())
        if self.at_p("+", "-"):
            kind = "UnaryPlus" if self.next().text == "+" else "UnaryMinus"
            # UnaryExpression ::= '+' PrimaryExpression | '-' PrimaryExpression (so not '--x', and not '-!x')
            if self.at_p("+", "-") and self.signed_number_ahead():
                return Node(kind, expr=self.literal())
            return Node(kind, expr=self.primary())
        return self.primary()

    def primary(self):
        t = self.peek()
        if self.at_p("("):
            return self.bracketted()
        if t.kind == "VAR":
            return self.var()
        if self.at_p("<<("):
            return self.expr_triple_term()
        if t.kind in ("STR", "INT", "DEC", "DBL"):
            return self.literal(signed=False)
        if t.kind == "W" and t.text in ("true", "false"):
            return self.literal()
        if t.kind in ("IRI", "PNAME"):
            if self.at_p("(", k=1):
                return self.function_call()
            return self.iri()
        if t.kind == "W":
            return self.builtin()
        self.err("expected an expression")

    def expr_triple_term(self) -> Node:
        """ExprTripleTerm: subject Var|iri|BlankNode label; object may be any expression term."""
        self.expect_p("<<(")
        if self.peek().kind == "VAR":
            s = self.var()
        elif self.at_iri():
            s = self.iri()
        else:
            self.err("expected a subject in a triple term")
        p = self.verb_simple()
        if self.at_p("<<("):
            o = self.expr_triple_term()
        elif self.peek().kind == "VAR":
            o = self.var()
        elif self.at_iri():
            o = self.iri()
        elif self.at_literal() or self.at_p("+", "-"):
            o = self.literal()
        else:
            self.err("expected an object in a triple term")
        self.expect_p(")>>")
        return self._triple_term_node(s, p, o)

    def function_call(self) -> Node:
        iri = self.iri()
        self.expect_p("(")
        distinct = self.accept_kw("DISTINCT")
        args = []
        if distinct or not self.at_p(")"):  # ArgList: NIL | '(' 'DISTINCT'? Expression ( ',' Expression )* ')'
            args.append(self.expression())
            while self.accept_p(","):
                args.append(self.expression())
        self.expect_p(")")
        return Node("Function", iri=iri, distinct="DISTINCT" if distinct else [], expr=args)

    def builtin(self) -> Node:
        t = self.peek()
        if t.kind != "W":
            self.err("expected a built-in call")
        up = t.text.upper()
        if up in _AGGS:
            return self.aggregate()
        if up == "NOT":
            self.i += 1
            self.expect_kw("EXISTS")
            return Node("Builtin_NOTEXISTS", graph=self.group_graph_pattern())
        if up == "EXISTS":
            self.i += 1
            return Node("Builtin_EXISTS", graph=self.group_graph_pattern())
        self.i += 1
        if up == "REGEX":
            self.expect_p("(")
            f = {"text": self.expression()}
            self.expect_p(",")
            f["pattern"] = self.expression()
            if self.accept_p(","):
                f["flags"] = self.expression()
            self.expect_p(")")
            return Node("Builtin_REGEX", **f)
        if up == "SUBSTR":
            self.expect_p("(")
            f = {"arg": self.expression()}
            self.expect_p(",")
            f["start"] = self.expression()
            if self.accept_p(","):
                f["length"] = self.expression()
            self.expect_p(")")
            return Node("Builtin_SUBSTR", **f)
        if up == "REPLACE":
            self.expect_p("(")
            f = {"arg": self.expression()}
            self.expect_p(",")
            f["pattern"] = self.expression()
            self.expect_p(",")
            f["replacement"] = self.expression()
            if self.accept_p(","):
                f["flags"] = self.expression()
            self.expect_p(")")
            return Node("Builtin_REPLACE", **f)
        if up == "STRLANGDIR":
            self.expect_p("(")
            f = {"lex": self.expression()}
            self.expect_p(",")
            f["lang"] = self.expression()
            self.expect_p(",")
            f["direction"] = self.expression()
            self.expect_p(")")
            return Node("Builtin_STRLANGDIR", **f)
        if up == "TRIPLE":
            self.expect_p("(")
            f = {"subject": self.expression()}
            self.expect_p(",")
            f["predicate"] = self.expression()
            self.expect_p(",")
            f["object"] = self.expression()
            self.expect_p(")")
            return Node("TripleTerm", **f)
        name = _BUILTIN_BY_UPPER.get(up)
        if name is None:
            self.err(f"unknown function {t.text!r}", t)
        if name in _ZERO:
            self.expect_p("(")
            self.expect_p(")")
            return Node(f"Builtin_{name}")
        if name == "BNODE":
            self.expect_p("(")
            if self.accept_p(")"):
                return Node("Builtin_BNODE")
            e = self.expression()
            self.expect_p(")")
            return Node("Builtin_BNODE", arg=e)
        if name == "BOUND":
            self.expect_p("(")
            v = self.var()
            self.expect_p(")")
            return Node("Builtin_BOUND", arg=v)
        if name in ("CONCAT", "COALESCE"):
            return Node(f"Builtin_{name}", arg=self.expression_list())
        if name == "IF":
            self.expect_p("(")
            a = self.expression()
            self.expect_p(",")
            b = self.expression()
            self.expect_p(",")
            c = self.expression()
            self.expect_p(")")
            return Node("Builtin_IF", arg1=a, arg2=b, arg3=c)
        self.expect_p("(")
        a = self.expression()
        if name in _TWO:
            self.expect_p(",")
            b = self.expression()
            self.expect_p(")")
            return Node(f"Builtin_{name}", arg1=a, arg2=b)
        self.expect_p(")")
        return Node(f"Builtin_{name}", arg=a)

    def aggregate(self) -> Node:
        at = self.peek().pos
        name = self.next().text.upper()
        kind = "Aggregate_" + {"GROUP_CONCAT": "GroupConcat"}.get(name, name.capitalize())
        self.expect_p("(")
        distinct = "DISTINCT" if self.accept_kw("DISTINCT") else []
        if name == "COUNT" and self.accept_p("*"):
            vars_ = "*"
        else:
            vars_ = self.expression()
        f = {"distinct": distinct, "vars": vars_}
        if name == "GROUP_CONCAT" and self.accept_p(";"):
            self.expect_kw("SEPARATOR")
            self.expect_p("=")
            f["separator"] = self.string()
        self.expect_p(")")
        return self._at(Node(kind, **f), at)


def _quad_terms(items: list):
    """Every term of a quad list (graph names, subjects, predicates, objects), looking inside triple terms."""

    def walk(t):
        if isinstance(t, Node) and t.kind == "TripleTerm":
            for k in ("subject", "predicate", "object"):
                yield from walk(t.f[k])
        else:
            yield t

    for item in items:
        if item.kind == "QuadGraph":
            yield item.f["term"]
            yield from _quad_terms(item.f["triples"])
        else:
            for k in ("s", "p", "o"):
                yield from walk(item.f[k])


def _flatten(kind: str, parts: list):
    if len(parts) == 1:
        return parts[0]
    flat: list = []
    for p in parts:
        flat.extend(p.f["args"] if isinstance(p, Node) and p.kind == kind else [p])
    return Node(kind, args=flat)


# ---------------------------------------------------------------------------
# Static semantic rules the grammar leaves to prose (section 19.7 notes, 18.3.1 scope, 11 aggregates)
# ---------------------------------------------------------------------------


def _term_vars(t, vs: set) -> None:
    if isinstance(t, ox.Variable):
        vs.add(t)
    elif isinstance(t, Node) and t.kind == "TripleTerm":
        for k in ("subject", "predicate", "object"):
            _term_vars(t.f[k], vs)


def _pattern_vars(where: list | None) -> set:
    """The variables in scope after a group graph pattern (section 18.3.1): FILTER, MINUS and EXISTS add none."""
    vs: set = set()
    for el in where or []:
        k = el.kind
        if k == "TriplePattern":
            _term_vars(el.f["s"], vs)
            _term_vars(el.f["o"], vs)
            if isinstance(el.f["p"], ox.Variable):
                vs.add(el.f["p"])
        elif k == "Optional":
            vs |= _pattern_vars(el.f["where"])
        elif k == "Service":
            _term_vars(el.f["term"], vs)
            vs |= _pattern_vars(el.f["where"])
        elif k == "Graph":
            _term_vars(el.f["term"], vs)
            vs |= _pattern_vars(el.f["where"])
        elif k == "Union":
            for alt in el.f["alts"]:
                vs |= _pattern_vars(alt)
        elif k == "Bind":
            vs.add(el.f["var"])
        elif k == "Values":
            vs |= set(el.f["vars"])
        elif k == "SubSelect":
            vs |= _projected(el)
    return vs


def _values_vars(q: Node) -> set:
    values = q.f.get("values")
    return set(values.f["vars"]) if values is not None else set()


def _projected(q: Node) -> set:
    """The variables a sub-select exposes: its projection (all in-scope variables for ``*``) plus its trailing VALUES."""
    if q.f["projection"] is None:
        return _pattern_vars(q.f["where"]) | _values_vars(q)
    return {p.f["var"] for p in q.f["projection"]} | _values_vars(q)


def _has_aggregate(e) -> bool:
    if isinstance(e, Node):
        if e.kind.startswith("Aggregate_"):
            return True
        if e.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            return False
        return any(_has_aggregate(v) for v in e.f.values())
    if isinstance(e, list):
        return any(_has_aggregate(v) for v in e)
    return False


def _expr_vars(e, out: set) -> None:
    """Variables an expression reads outside aggregates and EXISTS patterns."""
    if isinstance(e, ox.Variable):
        out.add(e)
    elif isinstance(e, Node):
        if e.kind.startswith("Aggregate_") or e.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            return
        for v in e.f.values():
            _expr_vars(v, out)
    elif isinstance(e, list):
        for v in e:
            _expr_vars(v, out)


class _Checker:
    """Walks a parsed query and raises :class:`SparqlSyntaxError` (at the offending node) for what the grammar cannot say."""

    def __init__(self, text: str):
        self.text = text

    def fail(self, msg: str, node=None):
        raise SparqlSyntaxError(msg, self.text, getattr(node, "pos", 0) or 0)

    # expressions: aggregate placement and nesting, plus the groups inside EXISTS ----------------
    def expr(self, e, aggregates_ok: bool, inside_aggregate: bool = False):
        if isinstance(e, Node):
            if e.kind.startswith("Aggregate_"):
                if not aggregates_ok:
                    self.fail("aggregate functions may only be used in SELECT, HAVING and ORDER BY", e)
                if inside_aggregate:
                    self.fail("aggregate functions cannot be nested", e)
                inside_aggregate = True
            elif e.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
                self.group(e.f["graph"])
                return
            for v in e.f.values():
                self.expr(v, aggregates_ok, inside_aggregate)
        elif isinstance(e, list):
            for v in e:
                self.expr(v, aggregates_ok, inside_aggregate)

    # group graph patterns ---------------------------------------------------------------------
    def group(self, where: list | None):
        seen: set = set()
        for el in where or []:
            k = el.kind
            if k == "Bind":
                if el.f["var"] in seen:
                    self.fail(f"BIND target {_vn(el.f['var'])} is already in scope in the group", el)
                self.expr(el.f["expr"], False)
            elif k == "Filter":
                self.expr(el.f["expr"], False)
            elif k in ("Optional", "Minus", "Graph", "Service"):
                self.group(el.f["where"])
            elif k == "Union":
                for alt in el.f["alts"]:
                    self.group(alt)
            elif k == "SubSelect":
                self.query(el)
            seen |= _pattern_vars([el])

    # whole queries and sub-selects ---------------------------------------------------------
    def query(self, q: Node):
        where = q.f.get("where")
        self.group(where)
        proj = q.f.get("projection")  # None for SELECT * and for the other query forms
        is_select = q.kind in ("SelectQuery", "SubSelect")
        group_by = q.f.get("group_by") or []
        having = q.f.get("having") or []
        order_by = [c.f["expr"] for c in q.f.get("order_by") or []]
        proj_exprs = [p.f["expr"] for p in proj or [] if p.kind == "ProjectExpr"]
        for c in group_by:
            self.expr(c.f["expr"] if isinstance(c, Node) and c.kind == "GroupAs" else c, False)
        for e in (*proj_exprs, *having, *order_by):
            self.expr(e, True)
        aggregated = bool(group_by) or any(_has_aggregate(e) for e in (*proj_exprs, *having, *order_by))
        if is_select and proj is None and (group_by or any(_has_aggregate(e) for e in (*having, *order_by))):
            self.fail("SELECT * cannot be used with GROUP BY or aggregates")
        # What `(expr AS ?v)` may not reuse. After grouping (explicit, or implicit when the projection aggregates) only the
        # group variables are in scope (section 18.3.1: "GROUP BY ... v"), so `SELECT (COUNT(*) AS ?o) { ?s ?p ?o }` is valid.
        clash_scope = set() if aggregated else _pattern_vars(where)
        group_vars: set = set()
        if group_by:
            for c in group_by:
                if isinstance(c, ox.Variable):
                    group_vars.add(c)
                elif isinstance(c, Node) and c.kind == "GroupAs":
                    v = c.f["var"]
                    if v in _pattern_vars(where) or v in group_vars:
                        self.fail(f"{_vn(v)} is already in scope at GROUP BY (... AS {_vn(v)})", c)
                    group_vars.add(v)
            clash_scope = set(group_vars)
        # the trailing VALUES is joined in before the SELECT expressions run: its variables are in scope and "grouped"
        clash_scope |= _values_vars(q)
        in_scope = (group_vars | _values_vars(q)) if aggregated else clash_scope
        if proj is not None:
            projected: set = set()
            for p in proj:
                v = p.f["var"]
                if p.kind == "ProjectExpr" and (v in clash_scope or v in projected):
                    self.fail(f"{_vn(v)} is already in scope at SELECT (... AS {_vn(v)})", p)
                if v in projected:
                    self.fail(f"{_vn(v)} is projected twice", p)
                projected.add(v)
        if aggregated and proj is not None:
            earlier: set = set()
            for p in proj:
                if p.kind == "ProjectVar" and p.f["var"] not in in_scope:
                    self.fail(f"{_vn(p.f['var'])} is projected but not grouped", p)
                if p.kind == "ProjectExpr":
                    used: set = set()
                    _expr_vars(p.f["expr"], used)
                    if used - in_scope - earlier:
                        self.fail("a projected expression uses a variable that is not grouped", p)
                    earlier.add(p.f["var"])


def _check_query(q: Node, text: str = "") -> None:
    _Checker(text).query(q)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def parse_sparql(text: str, base: str | None = None, prefixes: dict[str, str] | None = None) -> Node:
    """Parse SPARQL 1.2 query text to an AST. ``prefixes`` (prefix -> namespace) are in force as if declared before the text
    (they are not recorded as the query's own ``PREFIX`` lines).

    Raises:
        SparqlSyntaxError: For anything outside the grammar (with line and column).
    """
    try:
        parser = _Parser(text, base)
        parser.prefixes.update(prefixes or {})
        return parser.parse_query()
    except RecursionError:  # the grammar nests without limit, Python's stack does not (as in manchester_parser.run_guarded)
        raise SparqlSyntaxError("expression or pattern nested too deeply to parse", text, 0) from None


def parse_sparql_update(text: str, base: str | None = None) -> Node:
    """Parse a SPARQL 1.2 Update request (``UpdateUnit``) to an AST: a ``UpdateRequest`` node whose ``operations`` are
    ``Load``, ``Clear``, ``Drop``, ``Create``, ``Add``, ``Move``, ``Copy``, ``InsertData``, ``DeleteData``,
    ``DeleteWhere`` and ``Modify`` nodes. Each carries the prologue written in front of it; the prefixes and ``BASE``
    of earlier operations stay in force for later ones.

    Raises:
        SparqlSyntaxError: For anything outside the grammar or the static rules (variables in INSERT/DELETE DATA,
            blank nodes in DELETE DATA / DELETE WHERE / DELETE templates, a blank node label shared by two basic graph patterns or by the INSERT DATA of two operations).
    """
    try:
        return _Parser(text, base).parse_update()
    except RecursionError:
        raise SparqlSyntaxError("expression or pattern nested too deeply to parse", text, 0) from None


# ---------------------------------------------------------------------------
# AST -> sqe: RDF
# ---------------------------------------------------------------------------


class _Sink(list):
    """The triples an encoder produces, in order; ``add`` is the graph method the encoder code was written against."""

    def add(self, triple) -> None:
        self.append(triple)


def _list(graph: _Sink, nodes: list):
    """The RDF list of ``nodes`` (its triples go to ``graph``); ``rdf:nil`` for no nodes."""
    if not nodes:
        return RDF.nil
    head = cur = ox.BlankNode()
    for i, item in enumerate(nodes):
        graph.add((cur, RDF.first, item))
        nxt = RDF.nil if i == len(nodes) - 1 else ox.BlankNode()
        graph.add((cur, RDF.rest, nxt))
        cur = nxt
    return head


class _Encoder:
    def __init__(self, graph: _Sink, triple_order=None):
        from .sqe import vocab as v
        from .vocab import PY_STR_DATATYPE, SPEXPR, VARIABLE_DATATYPE

        self.g = graph
        self.v = v
        self.SPEXPR = SPEXPR
        self.PY = PY_STR_DATATYPE
        self.VAR = VARIABLE_DATATYPE
        self.triple_order = triple_order

    # terms and expressions ----------------------------------------------------
    def term(self, t):
        if isinstance(t, ox.Variable):
            return ox.Literal(t.value, datatype=self.VAR)
        if isinstance(t, Node):
            return self.node(t)
        if type(t) is str:
            return ox.Literal(t, datatype=self.PY)
        return t

    def node(self, n: Node):
        v, g = self.v, self.g
        if n.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            b = ox.BlankNode()
            g.add((b, RDF.type, v.EXISTS))
            if n.kind == "Builtin_NOTEXISTS":
                g.add((b, v.NEGATED, T.boolean()))
            g.add((b, v.WHERE, self.where(n.f["graph"])))
            return b
        if n.kind in ("InvPath", "SequencePath", "AlternativePath", "MulPath", "NegatedPath"):
            return self.path(n)
        ns = v.SQE if n.kind == "TripleTerm" else self.SPEXPR
        b = ox.BlankNode()
        g.add((b, RDF.type, ns[n.kind]))
        for k, val in n.f.items():
            if isinstance(val, list):
                g.add((b, ns[k], _list(g, [self.term(x) for x in val])))
            else:
                g.add((b, ns[k], self.term(val)))
        return b

    def path(self, n: Node):
        g, S = self.g, self.SPEXPR
        b = ox.BlankNode()
        g.add((b, RDF.type, S[n.kind]))
        if n.kind == "InvPath":
            g.add((b, S.arg, self.term(n.f["arg"])))
        elif n.kind == "MulPath":
            g.add((b, S.path, self.term(n.f["path"])))
            g.add((b, S.mod, T.plain_literal(n.f["mod"])))
        else:
            g.add((b, S.args, _list(g, [self.term(x) for x in n.f["args"]])))
        return b

    # patterns -------------------------------------------------------------------
    def triple(self, el: Node):
        b, v, g = ox.BlankNode(), self.v, self.g
        g.add((b, RDF.type, v.TRIPLE_PATTERN))
        g.add((b, v.TRIPLE_PATTERN_SUBJECT, self.term(el.f["s"])))
        g.add((b, v.TRIPLE_PATTERN_PREDICATE, self.term(el.f["p"])))
        g.add((b, v.TRIPLE_PATTERN_OBJECT, self.term(el.f["o"])))
        return b

    def where(self, parts: list):
        if len(parts) == 1 and parts[0].kind == "SubSelect":
            return _list(self.g, [self.sub_select(parts[0])])
        if self.triple_order is not None:
            parts = self.triple_order(parts)
        return _list(self.g, [self.element(p) for p in parts])

    def element(self, el: Node):
        v, g = self.v, self.g
        k = el.kind
        if k == "TriplePattern":
            return self.triple(el)
        b = ox.BlankNode()
        if k in ("Optional", "Minus"):
            g.add((b, RDF.type, v.OPTIONAL if k == "Optional" else v.MINUS))
            g.add((b, v.WHERE, self.where(el.f["where"])))
        elif k == "Service":
            g.add((b, RDF.type, v.SERVICE))
            g.add((b, v.SERVICE_TERM, self.term(el.f["term"])))
            if el.f["silent"]:
                g.add((b, v.SERVICE_SILENT, T.boolean()))
            g.add((b, v.WHERE, self.where(el.f["where"])))
        elif k == "Filter":
            g.add((b, RDF.type, v.FILTER))
            g.add((b, v.EXPR, self.term(el.f["expr"])))
        elif k == "Bind":
            g.add((b, RDF.type, v.BIND))
            g.add((b, v.EXPR, self.term(el.f["expr"])))
            g.add((b, v.BIND_VAR, self.term(el.f["var"])))
        elif k == "Graph":
            g.add((b, RDF.type, v.GRAPH_PATTERN))
            g.add((b, v.GRAPH_TERM, self.term(el.f["term"])))
            g.add((b, v.WHERE, self.where(el.f["where"])))
        elif k == "Values":
            return self.values(el)
        elif k == "Union":
            alts = el.f["alts"]
            if len(alts) == 1 and len(alts[0]) == 1 and alts[0][0].kind == "SubSelect":
                return self.sub_select(alts[0][0])
            g.add((b, RDF.type, v.UNION))
            g.add((b, v.UNION_ALTERNATIVES, _list(g, [self.where(a) for a in alts])))
        elif k == "SubSelect":
            return self.sub_select(el)
        else:
            raise NotImplementedError(f"starlayer.sparql.sqe: WHERE-clause element {k!r} not modeled yet")
        return b

    def values(self, el: Node):
        v, g = self.v, self.g
        b = ox.BlankNode()
        g.add((b, RDF.type, v.VALUES))
        g.add((b, v.VALUES_VARS, _list(g, [self.term(x) for x in el.f["vars"]])))
        rows = []
        for row in el.f["rows"]:
            rows.append(_list(g, [v.VALUES_UNDEF if c == "UNDEF" else self.term(c) for c in row]))
        g.add((b, v.VALUES_ROWS, _list(g, rows)))
        return b

    def sub_select(self, q: Node):
        b = ox.BlankNode()
        self.g.add((b, RDF.type, self.v.SUB_SELECT))
        self.g.add((b, RDF.type, self.v.SELECT_QUERY))
        self.body(q, b, "SelectQuery")
        return b

    def alias(self, expr, var):
        b, v = ox.BlankNode(), self.v
        self.g.add((b, RDF.type, v.ALIAS))
        self.g.add((b, v.EXPR, self.term(expr)))
        self.g.add((b, v.BIND_VAR, self.term(var)))
        return b

    def body(self, q: Node, root, kind: str):
        v, g = self.v, self.g
        if kind == "SelectQuery":
            if q.f["projection"] is not None:
                items = [
                    self.alias(p.f["expr"], p.f["var"]) if p.kind == "ProjectExpr" else self.term(p.f["var"])
                    for p in q.f["projection"]
                ]
                g.add((root, v.PROJECTION, _list(g, items)))
            else:
                g.add((root, v.SELECT_ALL, T.boolean()))
            if q.f["modifier"] == "DISTINCT":
                g.add((root, v.DISTINCT, T.boolean()))
            elif q.f["modifier"] == "REDUCED":
                g.add((root, v.REDUCED, T.boolean()))
        elif kind == "ConstructQuery":
            template = q.f["template"] if q.f["template"] is not None else q.f["where"]
            if self.triple_order is not None:
                template = self.triple_order(template)
            g.add((root, v.TEMPLATE, _list(g, [self.triple(t) for t in template])))
        elif kind == "DescribeQuery":
            if q.f["targets"] is None:
                g.add((root, v.DESCRIBE_ALL, T.boolean()))
            else:
                g.add((root, v.DESCRIBE, _list(g, [self.term(t) for t in q.f["targets"]])))
        if q.f.get("datasets"):
            clauses = []
            for named, iri in q.f["datasets"]:
                c = ox.BlankNode()
                g.add((c, RDF.type, v.DATASET_CLAUSE))
                g.add((c, v.DATASET_SOURCE, iri))
                if named:
                    g.add((c, v.DATASET_NAMED, T.boolean()))
                clauses.append(c)
            g.add((root, v.DATASET, _list(g, clauses)))
        if q.f["where"] is not None:
            g.add((root, v.WHERE, self.where(q.f["where"])))
        if q.f["group_by"]:
            items = [
                self.alias(c.f["expr"], c.f["var"]) if isinstance(c, Node) and c.kind == "GroupAs" else self.term(c)
                for c in q.f["group_by"]
            ]
            g.add((root, v.GROUP_BY, _list(g, items)))
        if q.f["having"]:
            g.add((root, v.HAVING, _list(g, [self.term(c) for c in q.f["having"]])))
        if q.f["order_by"]:
            conds = []
            for c in q.f["order_by"]:
                b = ox.BlankNode()
                g.add((b, RDF.type, v.ORDER_CONDITION))
                g.add((b, v.EXPR, self.term(c.f["expr"])))
                if c.f["desc"]:
                    g.add((b, v.ORDER_DESCENDING, T.boolean()))
                conds.append(b)
            g.add((root, v.ORDER_BY, _list(g, conds)))
        if q.f["limit"] is not None:
            g.add((root, v.LIMIT, q.f["limit"]))
        if q.f["offset"] is not None:
            g.add((root, v.OFFSET, q.f["offset"]))
        if q.f["values"] is not None:
            g.add((root, v.QUERY_VALUES, self.values(q.f["values"])))

    def query(self, q: Node, root):
        v, g = self.v, self.g
        root_type = {
            "SelectQuery": v.SELECT_QUERY,
            "AskQuery": v.ASK_QUERY,
            "ConstructQuery": v.CONSTRUCT_QUERY,
            "DescribeQuery": v.DESCRIBE_QUERY,
        }[q.kind]
        g.add((root, RDF.type, root_type))
        g.add((root, RDF.type, v.QUERY))
        self.body(q, root, q.kind)
        self.prologue(root, q.f["prologue"])

    def prologue(self, root, decls: list):
        v, g = self.v, self.g
        bases = [d for d in decls if d[0] == "base"]
        if bases:
            # sqe:base is one IRI. Every IRI in the tree is already resolved, so with several BASE declarations the
            # last (the base in force at the end of the prologue) stands for them, as the IRI it resolved to.
            g.add((root, v.PROLOGUE_BASE, T.iri(bases[0][1] if len(bases) == 1 else bases[-1][2])))
        for decl in decls:
            if decl[0] == "base":
                continue
            elif decl[0] == "prefix":
                b = ox.BlankNode()
                g.add((b, RDF.type, v.PREFIX_BINDING))
                g.add((b, v.PREFIX_LABEL, ox.Literal(decl[1], datatype=self.PY)))
                g.add((b, v.PREFIX_NAMESPACE, T.iri(decl[2])))
                g.add((root, v.PROLOGUE_PREFIX, b))
            elif decl[0] == "version":
                g.add((root, v.VERSION, T.plain_literal(decl[1])))

    # SPARQL Update -------------------------------------------------------------
    def update(self, u: Node, root):
        v, g = self.v, self.g
        g.add((root, RDF.type, v.UPDATE_REQUEST))
        g.add((root, v.OPERATIONS, _list(g, [self.operation(o) for o in u.f["operations"]])))
        self.prologue(root, u.f["prologue"])

    def graph_ref(self, n: Node):
        v, g = self.v, self.g
        b = ox.BlankNode()
        if n.kind == "GraphRef":
            g.add((b, RDF.type, v.GRAPH_REF))
            g.add((b, v.GRAPH_REF_IRI, n.f["iri"]))
        else:
            g.add((b, RDF.type, {"DefaultGraph": v.DEFAULT_GRAPH, "NamedGraphs": v.NAMED_GRAPHS, "AllGraphs": v.ALL_GRAPHS}[n.kind]))
        return b

    def quads(self, items: list):
        v, g = self.v, self.g
        out = []
        for item in items:
            if item.kind == "QuadGraph":
                b = ox.BlankNode()
                g.add((b, RDF.type, v.QUAD_GRAPH))
                g.add((b, v.QUAD_GRAPH_NAME, self.term(item.f["term"])))
                g.add((b, v.QUAD_TRIPLES, _list(g, [self.triple(t) for t in item.f["triples"]])))
                out.append(b)
            else:
                out.append(self.triple(item))
        return _list(g, out)

    def operation(self, o: Node):
        v, g = self.v, self.g
        b = ox.BlankNode()
        k = o.kind
        g.add((b, RDF.type, {
            "InsertData": v.INSERT_DATA, "DeleteData": v.DELETE_DATA, "DeleteWhere": v.DELETE_WHERE, "Modify": v.MODIFY,
            "Load": v.LOAD, "Clear": v.CLEAR, "Drop": v.DROP, "Create": v.CREATE, "Add": v.ADD, "Move": v.MOVE,
            "Copy": v.COPY,
        }[k]))  # fmt: skip
        if o.f.get("silent"):
            g.add((b, v.SERVICE_SILENT, T.boolean()))
        if k in ("InsertData", "DeleteData", "DeleteWhere"):
            g.add((b, v.QUADS, self.quads(o.f["quads"])))
        elif k == "Modify":
            if o.f["with_"] is not None:
                g.add((b, v.MODIFY_WITH, o.f["with_"]))
            if o.f["delete"] is not None:
                g.add((b, v.MODIFY_DELETE, self.quads(o.f["delete"])))
            if o.f["insert"] is not None:
                g.add((b, v.MODIFY_INSERT, self.quads(o.f["insert"])))
            if o.f["using"]:
                clauses = []
                for named, iri in o.f["using"]:
                    c = ox.BlankNode()
                    g.add((c, RDF.type, v.DATASET_CLAUSE))
                    g.add((c, v.DATASET_SOURCE, iri))
                    if named:
                        g.add((c, v.DATASET_NAMED, T.boolean()))
                    clauses.append(c)
                g.add((b, v.MODIFY_USING, _list(g, clauses)))
            g.add((b, v.WHERE, self.where(o.f["where"])))
        elif k == "Load":
            g.add((b, v.LOAD_FROM, o.f["source"]))
            if o.f["into"] is not None:
                g.add((b, v.LOAD_INTO, self.graph_ref(o.f["into"])))
        elif k in ("Clear", "Drop"):
            g.add((b, v.GRAPH_TARGET, self.graph_ref(o.f["target"])))
        elif k == "Create":
            g.add((b, v.GRAPH_TARGET, self.graph_ref(o.f["graph"])))
        else:  # Add, Move, Copy
            g.add((b, v.UPDATE_FROM, self.graph_ref(o.f["source"])))
            g.add((b, v.UPDATE_TO, self.graph_ref(o.f["dest"])))
        self.prologue(b, o.f["prologue"])
        return b


_DEPTH_RETRY_FACTOR = 8  # the encoder and the renderer need more frames per nesting level than the parser does


def run_with_deeper_stack(fn, *args, **kwargs):
    """Call ``fn``; on a RecursionError retry once with a larger recursion limit (main thread only, where the C stack
    is large enough). Raises RecursionError if that does not suffice or the retry is not safe.

    The grammar nests without limit, Python's stack does not: text the parser accepted may still be deeper than the
    encoder or the text renderer can follow within the default limit.
    """
    import sys
    import threading

    try:
        return fn(*args, **kwargs)
    except RecursionError:
        if threading.current_thread() is not threading.main_thread():
            raise
    limit = sys.getrecursionlimit()
    sys.setrecursionlimit(limit * _DEPTH_RETRY_FACTOR)
    try:
        return fn(*args, **kwargs)
    finally:
        sys.setrecursionlimit(limit)


def ast_to_triples(q: Node, root=None, *, triple_order=None) -> tuple[list, object]:
    """The ``sqe:`` tree of a parsed query or update as a list of ``(s, p, o)`` triples of pyoxigraph terms, and its root
    (a fresh blank node unless ``root`` is given). Literals keep the lexical form written (no store has touched them).

    Raises:
        SparqlSyntaxError: The query is nested too deeply to encode within the Python stack.
    """
    root = root if root is not None else ox.BlankNode()
    try:
        return run_with_deeper_stack(_encode_ast, q, root, triple_order), root
    except RecursionError:
        raise SparqlSyntaxError("expression or pattern nested too deeply to encode") from None


def _encode_ast(q: Node, root, triple_order) -> list:
    sink = _Sink()
    enc = _Encoder(sink, triple_order)
    if q.kind == "UpdateRequest":
        enc.update(q, root)
    else:
        enc.query(q, root)
    return list(sink)


def ast_to_tree(q: Node, graph: StarLayerGraph | None = None, root=None, *, triple_order=None) -> tuple[StarLayerGraph, object]:
    """Encode a parsed query or update as ``sqe:`` RDF in ``graph`` (a fresh ``StarLayerGraph`` when none is given) and return
    ``(graph, root)``. ``triple_order``: an optional callback that reorders a run of patterns (the differential tests use it).

    The graph is an Oxigraph store, which rewrites some literal lexical forms (``"007"^^xsd:integer`` is stored as ``"7"``);
    ``ast_to_triples`` keeps them.

    Raises:
        SparqlSyntaxError: The query is nested too deeply to encode within the Python stack.
    """
    from starlayer.graph.oxgraph.core import StarLayerGraph

    triples, root = ast_to_triples(q, root, triple_order=triple_order)
    if graph is None:
        graph = StarLayerGraph(prefixes={})
    graph.extend(triples)
    return graph, root


def sparql_to_tree(
    text: str, base: str | None = None, graph: StarLayerGraph | None = None, root=None, *, validate: bool = False
) -> tuple[StarLayerGraph, object]:
    """SPARQL 1.2 query text straight to ``sqe:`` tree-RDF, with the new parser.

    With ``validate=True`` the tree is also checked against the ``sqe:`` SHACL shapes (about 100 ms).
    """
    g, r = ast_to_tree(parse_sparql(text, base), graph, root)
    if validate:
        from .sqe.shapes import sqe_validate
        from .sqe.to_rdf import SQEValidationError

        ok, report_graph, report_text = sqe_validate(g)
        if not ok:
            raise SQEValidationError(report_text, report_graph)
    return g, r


def sparql_update_to_tree(
    text: str, base: str | None = None, graph: StarLayerGraph | None = None, root=None, *, validate: bool = False
) -> tuple[StarLayerGraph, object]:
    """SPARQL 1.2 Update text to ``sqe:`` tree-RDF (root typed ``sqe:UpdateRequest``); ``validate=True`` checks the SHACL shapes."""
    g, r = ast_to_tree(parse_sparql_update(text, base), graph, root)
    if validate:
        from .sqe.shapes import sqe_validate
        from .sqe.to_rdf import SQEValidationError

        ok, report_graph, report_text = sqe_validate(g)
        if not ok:
            raise SQEValidationError(report_text, report_graph)
    return g, r
