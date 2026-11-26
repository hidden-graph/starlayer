"""starlayer.sparql.parse_srl

SRL (SPARQL Rules) text -> the ``_srl_ast`` tree, on the same tokenizer and productions as
:mod:`starlayer.sparql.parse_sparql`. SRL reuses SPARQL's triple syntax (``TriplesSameSubject`` with every RDF 1.2
addition), ``Constraint`` and ``Expression``, so :class:`_SrlParser` subclasses the query parser and adds only what is
new in the SRL grammar (``RULE``, ``DATA``, ``WHERE [GROUND]``, ``NOT [GROUND]``, ``SET(?v := expr)``, ``GROUP [BY] { } [ ... ]``, ``IMPORTS``).

``parse_srl(text, base)`` returns a ``RuleSet`` of pyoxigraph terms whose expressions are the parser's own ``Node`` trees,
the form the SRL evaluator and the ``srl:`` tree encoder consume.

Static checks that belong to the rule set (a variable bound, ``SET`` not reusing a variable) stay in
``srl_semantic_checks``, which running a rule set calls; ``srl_validate`` reports the same conditions from the shapes in ``srl_shapes.ttl``.
"""

from __future__ import annotations

import pyoxigraph as ox

from starlayer.errors import FormatError

from . import _srl_ast as srl_ast
from .parse_sparql import Node, _Parser
from .triple_term import ExprNode, TripleTermNode

__all__ = ["parse_srl"]

# SPARQL built-ins that SRL's BuiltInCall (spec [126]) does not list. RAND is non-deterministic, which a fixpoint
# evaluation cannot allow, and EXISTS has no defined meaning in a rule; the rest are outside the draft's function set.
_NOT_IN_SRL = {
    "BOUND": "BOUND",
    "COALESCE": "COALESCE",
    "RAND": "RAND",
    "MD5": "MD5",
    "SHA1": "SHA1",
    "SHA256": "SHA256",
    "SHA384": "SHA384",
    "SHA512": "SHA512",
    "Exists": "EXISTS",
    "NotExists": "NOT EXISTS",
}

# The functions SPARQL calls by IRI: its XSD casts (SPARQL's own, and the one the SRL draft's examples call). The draft's
# expressions are "compatible with SPARQL expressions" but it lists no other function by IRI and no way to supply one, and one could
# read the graph or differ between calls, outside what the evaluation order is computed from.
_XSD = "http://www.w3.org/2001/XMLSchema#"
_CASTS = {_XSD + name for name in ("boolean", "double", "float", "decimal", "integer", "dateTime", "string")}


def _srl_error(message: str, cause: Exception | None = None) -> Exception:
    err = FormatError(message, kind="srl", why=message)
    err.__cause__ = cause
    return err


def _convert(value):
    """A parser ``Node`` (or a list of them, or a term) as the value the SRL tree holds: the same tree, with a triple term as a
    ``TripleTermNode``, after the check that every built-in is one SRL's BuiltInCall lists."""
    if isinstance(value, Node):
        if value.kind in _NOT_IN_SRL:
            raise _srl_error(f"SRL: {_NOT_IN_SRL[value.kind]} is not part of SRL's built-in function set (spec BuiltInCall)")
        if value.kind == "FunctionCall" and getattr(value.f["iri"], "value", None) not in _CASTS:
            raise _srl_error(
                f"SRL: the function {value.f['iri']} is not one SRL supports; a rule can call only the built-in functions "
                "and the XSD casts, and the specification has no way to supply any other function"
            )
        fields = {k: _convert(v) for k, v in value.f.items()}
        node = TripleTermNode("TripleTerm", **fields) if value.kind == "TripleTerm" else ExprNode(value.kind, **fields)
        node.pos = value.pos
        return node
    if isinstance(value, list):
        return [_convert(v) for v in value]
    return value


def _term(value):
    """A term of a triple: a triple term node becomes a ``TripleTermNode``, everything else is already a term."""
    if isinstance(value, Node) and value.kind == "TripleTerm":
        return _convert(value)
    return value


def _expand_path(subject, predicate, obj) -> list[srl_ast.TriplePattern]:
    """Expand a property path into the triple patterns it stands for (§5: "Property
    path syntax only covers paths with / and ^. These can be expanded into triple
    patterns"). ``s p/q o`` becomes ``s p _:m . _:m q o``; ``s ^p o`` becomes ``o p s``.
    A blank node introduced here behaves as a variable in a rule body.

    Raises:
        FormatError: (kind "srl") For any other path operator (``|``, ``*``, ``+``, ``?``, ``!``).
    """
    if isinstance(predicate, Node):
        if predicate.kind == "PathSequence":
            args = predicate.f["args"]
            nodes = [subject, *(ox.BlankNode() for _ in args[:-1]), obj]
            return [t for i, arg in enumerate(args) for t in _expand_path(nodes[i], arg, nodes[i + 1])]
        if predicate.kind == "PathInverse":
            return _expand_path(obj, predicate.f["arg"], subject)
        raise _srl_error(
            f"SRL: property path {_path_text(predicate)} is not allowed: SRL property paths use only the / and ^ operators "
            "(write a repeated or optional step with a recursive rule instead)"
        )
    return [srl_ast.TriplePattern(subject=_term(subject), predicate=predicate, object=_term(obj))]


def _path_text(path) -> str:
    if isinstance(path, Node):
        if path.kind == "PathElt":
            return f"{_path_text(path.f['path'])}{path.f['mod']}"
        if path.kind == "PathInverse":
            return f"^{_path_text(path.f['arg'])}"
        sep = {"PathSequence": "/", "PathAlternative": "|"}.get(path.kind)
        if sep:
            return "(" + sep.join(_path_text(a) for a in path.f["args"]) + ")"
        if path.kind == "PathNegatedPropertySet":
            return "!(" + "|".join(_path_text(a) for a in path.f["args"]) + ")"
    return str(path)


def _triples(items: list[Node]) -> list[srl_ast.TriplePattern]:
    return [t for it in items for t in _expand_path(it.f["s"], it.f["p"], it.f["o"])]


class _SrlParser(_Parser):
    """The SRL productions that SPARQL does not have, over SPARQL's own tokenizer and triple/expression productions."""

    def _block(self, path: bool) -> list[Node]:
        """``{ TriplesTemplate }`` / ``{ TriplesBlock }`` of triple groups, as ``TriplePattern`` nodes."""
        self.expect_p("{")
        out: list[Node] = []
        while not self.at_p("}"):
            if self.peek().kind == "EOF":
                self.err("unterminated block, expected '}'")
            self._group(out, path)
        self.expect_p("}")
        return out

    def _group(self, out: list, path: bool) -> None:
        if not self.starts_triples():
            self.err("expected a triple pattern")
        self.triples_same_subject(out, path=path)
        if not self.accept_p(".") and self.starts_triples():
            self.err("expected '.' between triple patterns")

    def _filter(self):
        self.expect_kw("FILTER")
        return srl_ast._FilterElement(expr=_convert(self.constraint()))

    def _ground(self) -> bool:
        """``GROUND`` after ``WHERE`` or ``NOT``: match the base graph only. The draft called it ``DATA`` until 2026-11-19."""
        if self.at_kw("DATA"):
            self.err("'DATA' after WHERE or NOT is now 'GROUND' (SPARQL-RL draft of 2026-11-19); a 'DATA { }' block is unchanged")
        return self.accept_kw("GROUND")

    def _negation(self) -> srl_ast._NegationElement:
        self.expect_kw("NOT")
        ground = self._ground()
        self.expect_p("{")
        inner: list = []
        pending: list[Node] = []
        while not self.at_p("}"):
            if self.peek().kind == "EOF":
                self.err("unterminated NOT block, expected '}'")
            if self.at_kw("FILTER"):
                inner.extend(_triples(pending))
                pending = []
                inner.append(self._filter())
                self.accept_p(".")
            else:
                self._group(pending, True)
        inner.extend(_triples(pending))
        self.expect_p("}")
        return srl_ast._NegationElement(inner=inner, evaldata=not ground)

    def _assign_op(self) -> None:
        """``:=``, one token in the grammar: nothing (whitespace, a comment) between the ':' and the '='."""
        t = self.peek()
        if not (t.kind == "PNAME" and t.text == ":" and self.at_p("=", k=1) and self.peek(1).pos == t.pos + 1):
            self.err("expected ':='")
        self.i += 2

    def _assignment(self) -> srl_ast._AssignmentElement:
        self.expect_kw("SET")
        self.expect_p("(")
        var = self.var()
        self._assign_op()
        expr = self.expression()
        self.expect_p(")")
        return srl_ast._AssignmentElement(var=var, expr=_convert(expr))

    def _group_pattern(self) -> list:
        """``{ GroupPattern }``: triple patterns with FILTER and SET (production [23])."""
        self.expect_p("{")
        inner: list = []
        pending: list[Node] = []
        while not self.at_p("}"):
            if self.peek().kind == "EOF":
                self.err("unterminated GROUP block, expected '}'")
            if self.at_kw("FILTER", "SET"):
                inner.extend(_triples(pending))
                pending = []
                inner.append(self._filter() if self.at_kw("FILTER") else self._assignment())
                self.accept_p(".")
            else:
                self._group(pending, True)
        inner.extend(_triples(pending))
        self.expect_p("}")
        return inner

    def _aggregation(self) -> srl_ast._Aggregation:
        """``?n := COUNT([DISTINCT] ?v | *)``, ``MIN(?v)``, ``MAX(?v)`` or ``SUM(?v)`` (productions [27] to [29]): the argument
        is a variable (or ``*`` for COUNT), never an expression, and DISTINCT is only for COUNT."""
        var = self.var()
        self._assign_op()
        if not self.at_kw("COUNT", "MIN", "MAX", "SUM"):
            self.err("expected an aggregation function: COUNT, MIN, MAX or SUM")
        name = self.peek().text.upper()
        self.i += 1
        self.expect_p("(")
        distinct = name == "COUNT" and self.accept_kw("DISTINCT")
        if name == "COUNT" and self.accept_p("*"):
            argument = None
        else:
            argument = self.var()
        self.expect_p(")")
        return srl_ast._Aggregation(var=var, function=name, argument=argument, distinct=distinct)

    def _group_aggregate(self) -> srl_ast._GroupElement:
        """``GROUP [BY ?k ...] { GroupPattern } ( [] | [ ?n := AGG(...) , ... ] )`` (production [22])."""
        self.expect_kw("GROUP")
        keys: list = []
        if self.accept_kw("BY"):
            if self.peek().kind != "VAR":
                self.err("expected a variable after GROUP BY")
            while self.peek().kind == "VAR":
                key = self.var()
                if key not in keys:
                    keys.append(key)
        pattern = self._group_pattern()
        self.expect_p("[")
        aggregations: list = []
        if not self.at_p("]"):
            aggregations.append(self._aggregation())
            while self.accept_p(","):
                aggregations.append(self._aggregation())
        self.expect_p("]")
        return srl_ast._GroupElement(keys=keys, pattern=pattern, aggregations=aggregations)

    def _body(self) -> list:
        self.expect_p("{")
        out: list = []
        pending: list[Node] = []
        while not self.at_p("}"):
            if self.peek().kind == "EOF":
                self.err("unterminated rule body, expected '}'")
            if self.at_kw("FILTER", "NOT", "SET", "GROUP"):
                out.extend(_triples(pending))
                pending = []
                if self.at_kw("FILTER"):
                    out.append(self._filter())
                elif self.at_kw("NOT"):
                    out.append(self._negation())
                elif self.at_kw("GROUP"):
                    out.append(self._group_aggregate())
                else:
                    out.append(self._assignment())
                self.accept_p(".")
            else:
                self._group(pending, True)
        out.extend(_triples(pending))
        self.expect_p("}")
        return out

    def _rule(self) -> srl_ast._Rule:
        self.expect_kw("RULE")
        rule_id = self.iri() if self.at_iri() else None
        head = _triples(self._block(False))
        self.expect_kw("WHERE")
        ground = self._ground()
        body = self._body()
        return srl_ast._Rule(head=head, body=body, evaldata=not ground, id=rule_id)

    def parse_ruleset(self) -> srl_ast.RuleSet:
        imports: list[ox.NamedNode] = []
        rules: list[srl_ast._Rule] = []
        data_blocks: list[srl_ast._Data] = []
        while self.peek().kind != "EOF":
            if self.at_kw("BASE", "PREFIX", "VERSION"):
                self.parse_prologue()
            elif self.accept_kw("IMPORTS"):
                imports.append(self.iri())
            elif self.at_kw("RULE"):
                rules.append(self._rule())
            elif self.at_kw("DATA"):
                self.i += 1
                data_blocks.append(srl_ast._Data(triples=_triples(self._block(False))))
            else:
                self.err("expected a rule, a DATA block, or a prologue declaration")
        ruleset = srl_ast.RuleSet(rules=rules, data=data_blocks, imports=imports)
        ruleset.prefixes.update(self.prefixes)
        return ruleset


def parse_srl(text: str, base: str | None = None) -> srl_ast.RuleSet:
    """SRL rule-set text as a ``RuleSet`` (no well-formedness or shape check: see ``srl.parse_ruleset``).

    Raises:
        FormatError: (kind "srl") For a syntax error, an undeclared prefix, or a property path SRL does not allow.
    """
    from .parse_sparql import _syntax_error

    try:
        return _SrlParser(text, base).parse_ruleset()
    except FormatError as exc:
        if exc.kind == "srl":
            raise
        raise FormatError(str(exc), kind="srl", why=exc.why, context=exc.context, line=exc.line, col=exc.col, pos=exc.pos) from exc
    except RecursionError:  # the grammar nests without limit, Python's stack does not (as in parse_sparql)
        exc = _syntax_error("expression or pattern nested too deeply to parse", text, 0)
        raise FormatError(str(exc), kind="srl", why=exc.why, line=exc.line, col=exc.col, pos=exc.pos) from None
