"""Render a ``starlayer.sparql.srl_ast.RuleSet`` back into SRL text - the
inverse of ``srl_grammar.parse_ruleset``, working directly on the parsed
dataclass tree (no RDF involved at all - unlike ``ssyn_to_text.py``, which
starts from an *RDF-encoded* graph, this starts from the AST already sitting
in memory after ``parse_ruleset`` runs).

The only piece genuinely worth reusing rather than hand-writing again:
``filter.expr``/``assign.expr`` are real rdflib ``Expr`` trees (see
``srl_grammar.py``'s docstring - SRL's expression grammar is SPARQL's own,
reused unmodified), so rendering *those* back to text reuses the exact
same trick ``ssyn_to_text.py`` already established and tests: wrap the
expression in a throwaway ``SELECT * WHERE { FILTER(<expr>) }`` query and
let rdflib's own ``algebra.translateAlgebra`` do the real work, then slice
out the ``FILTER(...)`` contents. Not duplicated here as a second copy —
imported directly from ``ssyn_to_text``.

**No original ``PREFIX``/``BASE`` declarations are preserved** - like
``translateAlgebra`` itself (see ``packages/sparql/CLAUDE.md``'s own
finding on this), the parsed AST only ever holds fully-resolved absolute
IRIs; prefix declarations are consumed during parsing and never stored.
Pass a ``namespace_manager`` (e.g. ``some_graph.namespace_manager``, from
any graph with the bindings you want) to render prefixed names instead of
full ``<...>`` IRIs wherever a match exists - purely cosmetic, the
resulting text still parses identically either way via ``parse_ruleset``
(which resolves prefixed names against whatever ``PREFIX`` lines are
present in the *input* text, not against this parameter).
"""

from __future__ import annotations

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.namespace import NamespaceManager

from . import srl_ast
from .ssyn_to_text import render_expr_text


def ruleset_to_text(ruleset: srl_ast.RuleSet, namespace_manager: NamespaceManager | None = None) -> str:
    """Render ``ruleset`` back into SRL text - ``IMPORTS``/``DATA``
    blocks first, then each ``RULE``, in the order they appear on the
    dataclass tree."""
    lines = [f"IMPORTS {_term_text(iri, namespace_manager)}" for iri in ruleset.imports]
    lines += [_data_text(block, namespace_manager) for block in ruleset.data]
    lines += [_rule_text(rule, namespace_manager) for rule in ruleset.rules]
    return "\n".join(lines)


def _term_text(term, namespace_manager: NamespaceManager | None) -> str:
    if isinstance(term, Variable):
        return "?" + str(term)
    if isinstance(term, (URIRef, BNode, Literal)):
        return term.n3(namespace_manager) if namespace_manager is not None else term.n3()
    raise NotImplementedError(
        f"starlayer.sparql.srl_to_text: no text rendering yet for term {term!r} - triple terms "
        "in pattern/template/data position aren't produced by srl_grammar.py yet either, "
        "see that module's own documented scope reduction"
    )


def _triple_text(triple: srl_ast.TriplePattern, namespace_manager: NamespaceManager | None) -> str:
    subject = _term_text(triple.subject, namespace_manager)
    predicate = _term_text(triple.predicate, namespace_manager)
    obj = _term_text(triple.object, namespace_manager)
    return f"{subject} {predicate} {obj} ."


def _block_text(triples: list[srl_ast.TriplePattern], namespace_manager: NamespaceManager | None) -> str:
    return " ".join(_triple_text(t, namespace_manager) for t in triples)


def _body_element_text(element: srl_ast.BodyElement, namespace_manager: NamespaceManager | None) -> str:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_text(element, namespace_manager)
    if isinstance(element, srl_ast.FilterElement):
        return f"FILTER({render_expr_text(element.expr)})"
    if isinstance(element, srl_ast.AssignmentElement):
        var = _term_text(element.var, namespace_manager)
        return f"SET ({var} := {render_expr_text(element.expr)})"
    if isinstance(element, srl_ast.NegationElement):
        inner = " ".join(_body_element_text(e, namespace_manager) for e in element.inner)
        data = "DATA " if element.data else ""
        return f"NOT {data}{{ {inner} }}"
    raise NotImplementedError(f"starlayer.sparql.srl_to_text: no text rendering yet for body element {element!r}")


def _data_text(data: srl_ast.Data, namespace_manager: NamespaceManager | None) -> str:
    return f"DATA {{ {_block_text(data.triples, namespace_manager)} }}"


def _rule_text(rule: srl_ast.Rule, namespace_manager: NamespaceManager | None) -> str:
    rule_id = f"{_term_text(rule.id, namespace_manager)} " if rule.id is not None else ""
    head = _block_text(rule.head, namespace_manager)
    body = " ".join(_body_element_text(e, namespace_manager) for e in rule.body)
    data = "DATA " if rule.data else ""
    return f"RULE {rule_id}{{ {head} }} WHERE {data}{{ {body} }}"
