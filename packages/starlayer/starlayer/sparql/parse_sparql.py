"""starlayer.sparql.parse_sparql

PROTOTYPE: a hand-written SPARQL 1.2 query parser, in the style of
``starlayer.graph.parsers.manchester_parser``: a position-carrying regex
tokenizer, then a recursive-descent parser with one method per grammar
production, building a small in-memory AST (:class:`Node`). No rdflib parser,
no pyparsing, and nothing from ``salg``.

Scope of this first cut: the query prologue (``BASE``, ``PREFIX``,
``VERSION``), ``SELECT``/``ASK``/``CONSTRUCT``, every ``WHERE`` element
(triple patterns with ``;`` ``,`` ``[ ]`` ``( )``, RDF 1.2 triple terms,
reified triples, reifiers, annotations, property paths, ``OPTIONAL``,
``UNION``, ``MINUS``, ``GRAPH``, ``FILTER``, ``BIND``, ``VALUES``,
sub-selects, ``SERVICE``), expressions with the full built-in list and the
aggregates, and the solution modifiers. ``DESCRIBE`` and SPARQL Update are
not parsed (``sqe`` does not model them either).

The AST is one generic class, :class:`Node` (``kind`` plus an ordered ``f``
dict), because the ``sqe:``/``spexpr:`` vocabulary is itself generic: an
expression node of kind ``Builtin_STR`` with field ``arg`` is encoded as
``[] a spexpr:Builtin_STR ; spexpr:arg ...``. :func:`sparql_to_tree` encodes
the AST as ``sqe:`` RDF (the same shapes ``sqe.sqe_parse_to_tree`` produces),
so ``sqe_tree_to_text`` and ``sqe_tree_to_query`` work on its output.

Entry points::

    parse_sparql(text, base=None) -> Node
    sparql_to_tree(text, base=None, graph=None, root=None) -> (Graph, root)

Errors are :class:`SparqlSyntaxError` with ``line``/``col``/``pos``.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from rdflib import BNode, Graph, Literal, URIRef, Variable
from rdflib.collection import Collection
from rdflib.namespace import RDF, XSD

from starlayer.graph.parsers.turtle_parser import _join
from starlayer.sparql.vocab import encode_dirlang_datatype

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


def tokenize(text: str) -> list[Tok]:
    out: list[Tok] = []
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if m is None:
            raise SparqlSyntaxError(f"unexpected character {text[pos]!r}", text, pos)
        kind = m.lastgroup
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
    """An AST node: ``kind`` plus ordered fields. Terms (IRI, literal, variable) are rdflib terms, not Nodes."""

    __slots__ = ("kind", "f")

    def __init__(self, kind: str, **f):
        self.kind = kind
        self.f = f

    def __getitem__(self, key):
        return self.f.get(key)

    def __repr__(self):
        return f"{self.kind}({', '.join(f'{k}={v!r}' for k, v in self.f.items())})"


_RDF_REIFIES = URIRef(str(RDF) + "reifies")

_ZERO = ("NOW", "UUID", "STRUUID", "RAND")
_ONE = (
    "STR LANG DATATYPE IRI URI ABS CEIL FLOOR ROUND STRLEN UCASE LCASE ENCODE_FOR_URI YEAR MONTH DAY HOURS MINUTES "
    "SECONDS TIMEZONE TZ MD5 SHA1 SHA256 SHA384 SHA512 isIRI isURI isBLANK isLITERAL isNUMERIC isTRIPLE SUBJECT "
    "PREDICATE OBJECT LANGDIR hasLANG hasLANGDIR"
).split()
_TWO = "LANGMATCHES CONTAINS STRSTARTS STRENDS STRBEFORE STRAFTER STRLANG STRDT sameTerm".split()
_BUILTIN_BY_UPPER = {n.upper(): n for n in (*_ZERO, *_ONE, *_TWO, "BOUND", "BNODE", "IF", "CONCAT", "COALESCE")}
_AGGS = {"COUNT", "SUM", "MIN", "MAX", "AVG", "SAMPLE", "GROUP_CONCAT"}

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

    # -- token helpers ------------------------------------------------------

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

    def _iri_text(self, raw: str) -> URIRef:
        inner = _decode_uchars(raw[1:-1])
        if self.base and not re.match(r"[A-Za-z][A-Za-z0-9+.\-]*:", inner):
            inner = _join(self.base, inner)
        return URIRef(inner)

    def _pname(self, tok: Tok) -> URIRef:
        prefix, _, local = tok.text.partition(":")
        if prefix not in self.prefixes:
            self.err(f"undeclared prefix {prefix!r}", tok)
        return URIRef(self.prefixes[prefix] + re.sub(r"\\(.)", r"\1", local))

    def iri(self) -> URIRef:
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

    def var(self) -> Variable:
        t = self.peek()
        if t.kind != "VAR":
            self.err("expected a variable")
        self.i += 1
        return Variable(t.text[1:])

    def bnode(self) -> BNode:
        t = self.peek()
        if t.kind == "BNODE":
            self.i += 1
            return BNode(t.text[2:])
        if self.at_p("[") and self.at_p("]", k=1):
            self.i += 2
            return BNode()
        self.err("expected a blank node")

    def at_bnode(self) -> bool:
        return self.peek().kind == "BNODE" or (self.at_p("[") and self.at_p("]", k=1))

    def string(self) -> Literal:
        t = self.peek()
        if t.kind != "STR":
            self.err("expected a string")
        self.i += 1
        return Literal(_unquote(t.text))

    def at_literal(self) -> bool:
        t = self.peek()
        return t.kind in ("STR", "INT", "DEC", "DBL") or (t.kind == "W" and t.text in ("true", "false"))

    def literal(self, signed: bool = True) -> Literal:
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
                    return Literal(s, datatype=encode_dirlang_datatype(lang.lower(), direction))
                return Literal(s, lang=tag)
            if nx.kind == "P" and nx.text == "^^":
                self.i += 1
                # normalize=False: rdflib's Literal rewrites some lexical forms by default ("...Z"^^xsd:dateTime becomes
                # "...+00:00"); a query's literal is kept exactly as written, as the current path does.
                return Literal(s, datatype=self.iri(), normalize=False)
            return Literal(s)
        sign = ""
        if signed and self.at_p("+", "-") and self.peek(1).kind in ("INT", "DEC", "DBL"):
            sign = self.next().text
            sign = "-" if sign == "-" else ""
            t = self.peek()
        if t.kind in ("INT", "DEC", "DBL"):
            self.i += 1
            dt = {"INT": XSD.integer, "DEC": XSD.decimal, "DBL": XSD.double}[t.kind]
            return Literal(sign + t.text, datatype=dt)
        if t.kind == "W" and t.text in ("true", "false"):
            self.i += 1
            return Literal(t.text == "true")
        self.err("expected a literal")

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
                self.base = str(self._iri_text(t.text))
                self.prologue.append(("base", t.text[1:-1]))
            elif self.accept_kw("PREFIX"):
                t = self.peek()
                if t.kind != "PNAME" or not t.text.endswith(":"):
                    self.err("expected a prefix label ending in ':'")
                self.i += 1
                iri = self.peek()
                if iri.kind != "IRI":
                    self.err("expected an IRI after the prefix label")
                self.i += 1
                self.prefixes[t.text[:-1]] = str(self._iri_text(iri.text))
                self.prologue.append(("prefix", t.text[:-1], str(self._iri_text(iri.text))))
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
            self.solution_modifier(q, allowed=False)
            self.values_clause(q)
        elif self.at_kw("CONSTRUCT"):
            q = self.construct_query()
        elif self.at_kw("DESCRIBE"):
            self.err("DESCRIBE is not implemented in this prototype")
        else:
            self.err("expected SELECT, ASK, CONSTRUCT or DESCRIBE")
        if self.peek().kind != "EOF":
            self.err("unexpected text after the query")
        q.f["prologue"] = self.prologue
        _check_query(q)
        return q

    def select_clause(self, q: Node):
        self.expect_kw("SELECT")
        q.f["modifier"] = "DISTINCT" if self.accept_kw("DISTINCT") else "REDUCED" if self.accept_kw("REDUCED") else None
        proj: list = []
        if self.accept_p("*"):
            q.f["projection"] = None
            return
        while True:
            if self.peek().kind == "VAR":
                proj.append(Node("ProjectVar", var=self.var()))
            elif self.at_p("("):
                self.i += 1
                e = self.expression()
                self.expect_kw("AS")
                v = self.var()
                self.expect_p(")")
                proj.append(Node("ProjectExpr", expr=e, var=v))
            else:
                break
        if not proj:
            self.err("expected '*' or a projection")
        q.f["projection"] = proj

    def select_query(self) -> Node:
        q = Node("SelectQuery")
        self.select_clause(q)
        q.f["datasets"] = self.dataset_clauses()
        q.f["where"] = self.where_clause()
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
        while self.starts_triples():
            self.triples_same_subject(out, path=False)
            if not self.accept_p("."):
                break

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
                    self.i += 1
                    e = self.expression()
                    if self.accept_kw("AS"):
                        conds.append(Node("GroupAs", expr=e, var=self.var()))
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

    def _integer(self) -> Literal:
        t = self.peek()
        if t.kind != "INT":
            self.err("expected an integer")
        self.i += 1
        return Literal(t.text, datatype=XSD.integer)

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
        if self.at_kw("SELECT"):
            sub = self.select_query()
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
            parts.append(self.graph_pattern_not_triples())
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
        if self.accept_kw("BIND"):
            self.expect_p("(")
            e = self.expression()
            self.expect_kw("AS")
            v = self.var()
            self.expect_p(")")
            return Node("Bind", expr=e, var=v)
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
        elif self.at_p("[", "(") and not self.at_bnode():
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
            b = BNode()
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
        head = BNode()
        cur = head
        for k, item in enumerate(items):
            out.append(Node("TriplePattern", s=cur, p=RDF.first, o=item))
            nxt = RDF.nil if k == len(items) - 1 else BNode()
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
                    reifier = BNode()
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
        return BNode()

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
        r = BNode()
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
        else:
            self.err("expected a subject in a triple term")
        p = self.verb_simple() if not data else (RDF.type if self.accept_a() else self.iri())
        if isinstance(p, Variable) and data:
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
        if self.at_p("?", "*", "+"):
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
        if self.at_p("+"):
            self.i += 1
            return Node("UnaryPlus", expr=self.unary())
        if self.at_p("-"):
            self.i += 1
            return Node("UnaryMinus", expr=self.unary())
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
        elif self.peek().kind == "BNODE":
            s = self.bnode()
        else:
            self.err("expected a subject in a triple term")
        p = self.verb_simple()
        if self.at_p("<<("):
            o = self.expr_triple_term()
        elif self.peek().kind == "VAR":
            o = self.var()
        elif self.at_iri():
            o = self.iri()
        elif self.peek().kind == "BNODE":
            o = self.bnode()
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
        if not self.at_p(")"):
            args.append(self.expression())
            while self.accept_p(","):
                args.append(self.expression())
        self.expect_p(")")
        f = {"iri": iri}
        if args:
            f["distinct"] = "DISTINCT" if distinct else []
            f["expr"] = args
        return Node("Function", **f)

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
        return Node(kind, **f)


def _flatten(kind: str, parts: list):
    if len(parts) == 1:
        return parts[0]
    flat: list = []
    for p in parts:
        flat.extend(p.f["args"] if isinstance(p, Node) and p.kind == kind else [p])
    return Node(kind, args=flat)


# ---------------------------------------------------------------------------
# Static checks the grammar leaves to prose (a subset: scope and aggregates)
# ---------------------------------------------------------------------------


def _pattern_vars(where: list) -> set:
    vs: set = set()

    def term(t):
        if isinstance(t, Variable):
            vs.add(t)
        elif isinstance(t, Node) and t.kind == "TripleTerm":
            for k in ("subject", "predicate", "object"):
                term(t.f[k])

    for el in where:
        k = el.kind
        if k == "TriplePattern":
            term(el.f["s"])
            term(el.f["o"])
            if isinstance(el.f["p"], Variable):
                vs.add(el.f["p"])
        elif k in ("Optional", "Service"):
            vs |= _pattern_vars(el.f["where"])
        elif k == "Graph":
            term(el.f["term"])
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


def _projected(q: Node) -> set:
    if q.f["projection"] is None:
        return _pattern_vars(q.f["where"])
    return {p.f["var"] for p in q.f["projection"]}


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


def _nested_aggregate(e, inside=False) -> bool:
    if isinstance(e, Node):
        agg = e.kind.startswith("Aggregate_")
        if agg and inside:
            return True
        return any(_nested_aggregate(v, inside or agg) for v in e.f.values())
    if isinstance(e, list):
        return any(_nested_aggregate(v, inside) for v in e)
    return False


def _expr_vars(e, out: set, skip_aggregates: bool = True):
    if isinstance(e, Variable):
        out.add(e)
    elif isinstance(e, Node):
        if skip_aggregates and e.kind.startswith("Aggregate_"):
            return
        if e.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            return
        for v in e.f.values():
            _expr_vars(v, out, skip_aggregates)
    elif isinstance(e, list):
        for v in e:
            _expr_vars(v, out, skip_aggregates)


def _check_query(q: Node, top: bool = True) -> None:
    def fail(msg):
        raise SparqlSyntaxError(msg, "", 0)

    where = q.f["where"] or []
    for el in where:
        if el.kind == "SubSelect":
            _check_query(el, top=False)
    seen_scope: set = set()
    for el in where:  # BIND may not rebind a variable already in scope
        if el.kind == "Bind" and el.f["var"] in seen_scope:
            fail(f"BIND target {el.f['var'].n3()} is already in scope")
        seen_scope |= _pattern_vars([el])
    proj = q.f.get("projection")
    exprs = [p.f["expr"] for p in proj or [] if p.kind == "ProjectExpr"]
    exprs += list(q.f.get("having") or []) + [c.f["expr"] for c in q.f.get("order_by") or []]
    if any(_nested_aggregate(e) for e in exprs):
        fail("aggregate functions cannot be nested")
    aggregated = bool(q.f.get("group_by")) or any(_has_aggregate(e) for e in exprs)
    if q.f.get("group_by") and proj is None:
        fail("SELECT * cannot be used with GROUP BY")
    if proj is not None:
        names = [p.f["var"] for p in proj]
        if len(set(names)) != len(names):
            fail("a variable is projected twice")
        in_scope = _pattern_vars(where)
        if q.f.get("group_by"):
            in_scope = {c for c in q.f["group_by"] if isinstance(c, Variable)} | {
                c.f["var"] for c in q.f["group_by"] if isinstance(c, Node) and c.kind == "GroupAs"
            }
        for p in proj:
            if p.kind == "ProjectExpr" and p.f["var"] in in_scope:
                fail(f"{p.f['var'].n3()} is already in scope in the WHERE clause")
    if aggregated:
        grouped: set = set()
        for c in q.f.get("group_by") or []:
            if isinstance(c, Variable):
                grouped.add(c)
            elif isinstance(c, Node) and c.kind == "GroupAs":
                grouped.add(c.f["var"])
        if proj is not None:
            for k, p in enumerate(proj):
                if p.kind == "ProjectVar" and p.f["var"] not in grouped:
                    fail(f"{p.f['var'].n3()} is projected but not grouped")
                if p.kind == "ProjectExpr":
                    used: set = set()
                    _expr_vars(p.f["expr"], used)
                    earlier = {x.f["var"] for x in proj[:k] if x.kind == "ProjectExpr"}
                    if used - grouped - earlier:
                        fail("a projected expression uses an ungrouped variable")
        for c in q.f.get("group_by") or []:
            if isinstance(c, Node) and c.kind == "GroupAs" and c.f["var"] in _pattern_vars(where):
                fail(f"{c.f['var'].n3()} is already in scope in the WHERE clause")


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def parse_sparql(text: str, base: str | None = None) -> Node:
    """Parse SPARQL 1.2 query text to an AST.

    Raises:
        SparqlSyntaxError: For anything outside the grammar (with line and column).
    """
    try:
        return _Parser(text, base).parse_query()
    except RecursionError:  # the grammar nests without limit, Python's stack does not (as in manchester_parser.run_guarded)
        raise SparqlSyntaxError("expression or pattern nested too deeply to parse", text, 0) from None


# ---------------------------------------------------------------------------
# AST -> sqe: RDF
# ---------------------------------------------------------------------------


def _list(graph: Graph, nodes: list):
    if not nodes:
        return RDF.nil
    head = BNode()
    Collection(graph, head, nodes)
    return head


class _Encoder:
    def __init__(self, graph: Graph, triple_order=None):
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
        if isinstance(t, Variable):
            return Literal(str(t), datatype=self.VAR)
        if isinstance(t, Node):
            return self.node(t)
        if type(t) is str:
            return Literal(t, datatype=self.PY)
        return t

    def node(self, n: Node):
        v, g = self.v, self.g
        if n.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
            b = BNode()
            g.add((b, RDF.type, v.EXISTS))
            if n.kind == "Builtin_NOTEXISTS":
                g.add((b, v.NEGATED, Literal(True)))
            g.add((b, v.WHERE, self.where(n.f["graph"])))
            return b
        if n.kind in ("InvPath", "SequencePath", "AlternativePath", "MulPath", "NegatedPath"):
            return self.path(n)
        ns = v.SQE if n.kind == "TripleTerm" else self.SPEXPR
        b = BNode()
        g.add((b, RDF.type, ns[n.kind]))
        for k, val in n.f.items():
            if isinstance(val, list):
                g.add((b, ns[k], _list(g, [self.term(x) for x in val])))
            else:
                g.add((b, ns[k], self.term(val)))
        return b

    def path(self, n: Node):
        g, S = self.g, self.SPEXPR
        b = BNode()
        g.add((b, RDF.type, S[n.kind]))
        if n.kind == "InvPath":
            g.add((b, S.arg, self.term(n.f["arg"])))
        elif n.kind == "MulPath":
            g.add((b, S.path, self.term(n.f["path"])))
            g.add((b, S.mod, Literal(n.f["mod"])))
        else:
            g.add((b, S.args, _list(g, [self.term(x) for x in n.f["args"]])))
        return b

    # patterns -------------------------------------------------------------------
    def triple(self, el: Node):
        b, v, g = BNode(), self.v, self.g
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
        b = BNode()
        if k in ("Optional", "Minus"):
            g.add((b, RDF.type, v.OPTIONAL if k == "Optional" else v.MINUS))
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
        b = BNode()
        g.add((b, RDF.type, v.VALUES))
        g.add((b, v.VALUES_VARS, _list(g, [self.term(x) for x in el.f["vars"]])))
        rows = []
        for row in el.f["rows"]:
            rows.append(_list(g, [v.VALUES_UNDEF if c == "UNDEF" else self.term(c) for c in row]))
        g.add((b, v.VALUES_ROWS, _list(g, rows)))
        return b

    def sub_select(self, q: Node):
        b = BNode()
        self.g.add((b, RDF.type, self.v.SUB_SELECT))
        self.g.add((b, RDF.type, self.v.SELECT_QUERY))
        self.body(q, b, "SelectQuery")
        return b

    def alias(self, expr, var):
        b, v = BNode(), self.v
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
                g.add((root, v.SELECT_ALL, Literal(True)))
            if q.f["modifier"] == "DISTINCT":
                g.add((root, v.DISTINCT, Literal(True)))
            elif q.f["modifier"] == "REDUCED":
                g.add((root, v.REDUCED, Literal(True)))
        elif kind == "ConstructQuery":
            template = q.f["template"] if q.f["template"] is not None else q.f["where"]
            if self.triple_order is not None:
                template = self.triple_order(template)
            g.add((root, v.TEMPLATE, _list(g, [self.triple(t) for t in template])))
        g.add((root, v.WHERE, self.where(q.f["where"])))
        if kind == "AskQuery":
            return
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
                b = BNode()
                g.add((b, RDF.type, v.ORDER_CONDITION))
                g.add((b, v.EXPR, self.term(c.f["expr"])))
                if c.f["desc"]:
                    g.add((b, v.ORDER_DESCENDING, Literal(True)))
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
        if q.f["datasets"]:
            raise NotImplementedError("starlayer.sparql.sqe: FROM / FROM NAMED are not modeled; refusing to drop them")
        root_type = {"SelectQuery": v.SELECT_QUERY, "AskQuery": v.ASK_QUERY, "ConstructQuery": v.CONSTRUCT_QUERY}[q.kind]
        g.add((root, RDF.type, root_type))
        g.add((root, RDF.type, v.QUERY))
        self.body(q, root, q.kind)
        for decl in q.f["prologue"]:
            if decl[0] == "base":
                g.add((root, v.PROLOGUE_BASE, URIRef(decl[1])))
            elif decl[0] == "prefix":
                b = BNode()
                g.add((b, RDF.type, v.PREFIX_BINDING))
                g.add((b, v.PREFIX_LABEL, Literal(decl[1], datatype=self.PY)))
                g.add((b, v.PREFIX_NAMESPACE, URIRef(decl[2])))
                g.add((root, v.PROLOGUE_PREFIX, b))
            # VERSION has no sqe: term: a vocabulary gap, the label is dropped.


def ast_to_tree(q: Node, graph: Graph | None = None, root=None, *, triple_order=None) -> tuple[Graph, object]:
    """Encode a parsed query as ``sqe:`` RDF (``triple_order``: an optional callback that reorders a run of
    patterns, used by the differential tests to mimic rdflib's ``reorderTriples``)."""
    from .to_rdf import _new_starlayer_graph

    graph = graph if graph is not None else _new_starlayer_graph()
    root = root if root is not None else BNode()
    _Encoder(graph, triple_order).query(q, root)
    return graph, root


def sparql_to_tree(
    text: str, base: str | None = None, graph: Graph | None = None, root=None, *, validate: bool = False
) -> tuple[Graph, object]:
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
