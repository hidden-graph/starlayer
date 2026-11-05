"""starlayer.sparql.parse_srl

SRL (SPARQL Rules) text -> the ``_srl_ast`` tree, on the same tokenizer and productions as
:mod:`starlayer.sparql.parse_sparql`. SRL reuses SPARQL's triple syntax (``TriplesSameSubject`` with every RDF 1.2
addition), ``Constraint`` and ``Expression``, so :class:`_SrlParser` subclasses the query parser and adds only what is
new in the SRL grammar (``RULE``, ``DATA``, ``WHERE [DATA]``, ``NOT [DATA]``, ``SET(?v := expr)``, ``IMPORTS``).

``parse_srl(text, base)`` returns a ``RuleSet`` of pyoxigraph terms whose expressions are the parser's own ``Node`` trees,
the form the SRL evaluator and the ``srl:`` tree encoder consume.

Static checks that belong to the rule set (a variable bound, ``SET`` not reusing a variable) stay in
``srl_semantic_checks``; ``srl.parse_ruleset`` calls them and the ``srl:`` shapes after this.
"""

from __future__ import annotations

import pyoxigraph as ox

from . import _srl_ast as srl_ast
from .parse_sparql import Node, _Parser
from .triple_term import ExprNode, TripleTermNode

__all__ = ["parse_srl"]

# SPARQL built-ins that SRL's BuiltInCall (spec [118]) does not list. RAND is non-deterministic, which a fixpoint
# evaluation cannot allow, and EXISTS has no defined meaning in a rule; the rest are outside the draft's function set.
_NOT_IN_SRL = {
    "Builtin_BOUND": "BOUND",
    "Builtin_COALESCE": "COALESCE",
    "Builtin_RAND": "RAND",
    "Builtin_MD5": "MD5",
    "Builtin_SHA1": "SHA1",
    "Builtin_SHA256": "SHA256",
    "Builtin_SHA384": "SHA384",
    "Builtin_SHA512": "SHA512",
    "Builtin_EXISTS": "EXISTS",
    "Builtin_NOTEXISTS": "NOT EXISTS",
}


def _srl_error(message: str, cause: Exception | None = None) -> Exception:
    from .srl import SRLParseError  # srl imports this module: resolved at call time

    err = SRLParseError(message)
    err.__cause__ = cause
    return err


def _convert(value):
    """A parser ``Node`` (or a list of them, or a term) as the value the SRL tree holds: the same tree, with a triple term as a
    ``TripleTermNode``, after the check that every built-in is one SRL's BuiltInCall lists."""
    if isinstance(value, Node):
        if value.kind in _NOT_IN_SRL:
            raise _srl_error(f"SRL: {_NOT_IN_SRL[value.kind]} is not part of SRL's built-in function set (spec BuiltInCall)")
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
        SRLParseError: For any other path operator (``|``, ``*``, ``+``, ``?``, ``!``).
    """
    if isinstance(predicate, Node):
        if predicate.kind == "SequencePath":
            args = predicate.f["args"]
            nodes = [subject, *(ox.BlankNode() for _ in args[:-1]), obj]
            return [t for i, arg in enumerate(args) for t in _expand_path(nodes[i], arg, nodes[i + 1])]
        if predicate.kind == "InvPath":
            return _expand_path(obj, predicate.f["arg"], subject)
        raise _srl_error(
            f"SRL: property path {_path_text(predicate)} is not allowed: SRL property paths use only the / and ^ operators "
            "(write a repeated or optional step with a recursive rule instead)"
        )
    return [srl_ast.TriplePattern(subject=_term(subject), predicate=predicate, object=_term(obj))]


def _path_text(path) -> str:
    if isinstance(path, Node):
        if path.kind == "MulPath":
            return f"{_path_text(path.f['path'])}{path.f['mod']}"
        if path.kind == "InvPath":
            return f"^{_path_text(path.f['arg'])}"
        sep = {"SequencePath": "/", "AlternativePath": "|"}.get(path.kind)
        if sep:
            return "(" + sep.join(_path_text(a) for a in path.f["args"]) + ")"
        if path.kind == "NegatedPath":
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

    def _negation(self) -> srl_ast._NegationElement:
        self.expect_kw("NOT")
        data = self.accept_kw("DATA")
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
        return srl_ast._NegationElement(inner=inner, evaldata=not data)

    def _assignment(self) -> srl_ast._AssignmentElement:
        self.expect_kw("SET")
        self.expect_p("(")
        var = self.var()
        t = self.peek()
        if not (t.kind == "PNAME" and t.text == ":" and self.at_p("=", k=1)):
            self.err("expected ':='")
        self.i += 2
        expr = self.expression()
        self.expect_p(")")
        return srl_ast._AssignmentElement(var=var, expr=_convert(expr))

    def _body(self) -> list:
        self.expect_p("{")
        out: list = []
        pending: list[Node] = []
        while not self.at_p("}"):
            if self.peek().kind == "EOF":
                self.err("unterminated rule body, expected '}'")
            if self.at_kw("FILTER", "NOT", "SET"):
                out.extend(_triples(pending))
                pending = []
                if self.at_kw("FILTER"):
                    out.append(self._filter())
                elif self.at_kw("NOT"):
                    out.append(self._negation())
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
        data = self.accept_kw("DATA")
        body = self._body()
        return srl_ast._Rule(head=head, body=body, evaldata=not data, id=rule_id)

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
        SRLParseError: For a syntax error, an undeclared prefix, or a property path SRL does not allow.
    """
    from .parse_sparql import SparqlSyntaxError as _Err

    try:
        return _SrlParser(text, base).parse_ruleset()
    except _Err as exc:
        raise _srl_error(str(exc), exc) from exc
