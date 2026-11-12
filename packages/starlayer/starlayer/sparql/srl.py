"""starlayer.sparql.srl

SRL (SPARQL Rules; spec `WD-sparql12-rl-20260919 <https://www.w3.org/TR/sparql12-rl/>`_)
- a Datalog-style rules language built on SPARQL triple patterns and filter
expressions. This module provides SRL text, its tree-RDF encoding (``srl:``),
and SHACL validation of that encoding: parsing SRL text to a ``RuleSet``
syntax tree and back, encoding/decoding that syntax tree to/from RDF, and
validating an ``srl:``-encoded ruleset against SHACL shapes.

**Where this sits, and why it's not in ``starontology`` like ``manch:``
is**: SRL rule sets aren't documents describing a vocabulary (what
Manchester's tree edits) - they're inference rules built directly out of
SPARQL triple patterns/filter expressions, run *against* a graph. That's a
SPARQL-adjacent artifact, and it can't cleanly separate from
``starlayer.sparql``'s shared internals the way Manchester's syntax-tree
module could: the term and expression encoder of ``parse_sparql`` is reused
directly below, not reimplemented - moving this module out of
``starlayer.sparql`` would mean forking that machinery.

Six entry points, forming two independent round trips (text<->tree-RDF,
text<->RuleSet) plus a third already covered by the first two composed
(tree-RDF<->RuleSet):

- ``srl_parse_to_tree(text, base=None) -> (graph, root)`` - SRL text straight
  to its ``srl:``-encoded tree-RDF. Composes ``parse_ruleset`` +
  ``ruleset_to_tree``.
- ``srl_tree_to_text(graph, root) -> str`` - the inverse. Composes
  ``tree_to_ruleset`` + ``ruleset_to_text``.
- ``parse_ruleset(text, base=None, *, validate=True) -> RuleSet`` - SRL text
  straight to a real ``RuleSet`` object, skipping RDF entirely in the result
  (with ``validate=True`` the rule set is also checked against the ``srl:``
  SHACL shapes, which encodes it as RDF internally; see below). Kept as its own
  entry point (not just an implementation detail of ``srl_parse_to_tree``)
  because ``RuleSet`` is independently useful - ``RuleSet.infer()``/
  ``.query()`` run it directly, with no RDF involved at all. This is
  the one real asymmetry with Manchester: ``manch:``'s ``Document`` object
  never existed before its own syntax-tree-as-RDF module invented it purely
  as a decode artifact; SRL's ``RuleSet`` already existed independently.
- ``ruleset_to_text(ruleset, namespace_manager=None) -> str`` - the
  inverse of ``parse_ruleset``, working on the syntax tree directly.
- ``tree_to_ruleset(graph, root) -> RuleSet`` - decode ``srl:``-encoded
  tree-RDF into a real ``RuleSet``, e.g. after programmatically editing the
  RDF via plain graph surgery.
- ``ruleset_to_tree(ruleset, graph=None) -> (graph, root)`` - the inverse:
  encode a ``RuleSet`` (e.g. one built or edited programmatically - rules
  combined, a filter rewritten) back to ``srl:`` tree-RDF.

Plus ``srl_validate(data_graph) -> (conforms, report_graph, report_text)`` -
structural SHACL validation of an ``srl:`` tree-RDF graph. Deliberately
**no** public ``ontology_graph()``/``shapes_graph()`` here (same decision
``starontology.manchester`` makes for ``manch:``) - callers who want the
raw ``srl:`` ontology/shapes graphs themselves can already get them from
``starontology`` directly instead: ``get_ontology_graph("srl_owl")`` /
``get_ontology_graph("srl_shacl")``. Exposing a second path to the exact
same two graphs here would just be another way to do what that one already
does. ``srl_validate()`` still needs its own private, combined copy
internally (an ``srl:expr``/``srl:assign`` expression tree is validated by the shared ``spexpr:`` expression shapes, so the ``srl:``, ``spexpr:`` and ``sqe:`` ontology/shapes graphs are
needed together for the RDFS closure to resolve that dispatch) - see
``_ontology_graph()``/``_shapes_graph()`` below.

Deliberately outside this module's scope, unchanged, living in their own
sibling files:

- ``_srl_ast.py`` (private) - the
  ``RuleSet``/``_Rule``/``_Data``/``TriplePattern``/``_FilterElement``/
  ``_AssignmentElement``/``_NegationElement`` dataclasses themselves. Stays
  a separate *file* (not folded in here) because it's already a clean,
  independently-useful module consumed by ``srl_eval.py``/
  ``srl_semantic_checks.py`` too, neither of which needs anything else
  this module provides - but it's no longer directly importable from
  outside the package. Only ``RuleSet``/``TriplePattern`` are re-exported
  from here (``srl.RuleSet``, etc.) - one real path to those two, not two -
  same "no two paths to the same graphs" reasoning ``srl_validate()``'s
  own docstring note above already applies to ``ontology_graph()``/
  ``shapes_graph()``. The rest (``_Rule``/``_Data``/``_FilterElement``/
  ``_AssignmentElement``/``_NegationElement``) are private: no public
  function or method requires any of them directly (unlike
  ``TriplePattern``, needed as ``RuleSet.query()``'s own ``goal_pattern``
  parameter type) - the only way a caller would touch one is by walking
  ``RuleSet.rules``/``Rule.head``/``Rule.body``, an inspection/editing
  concern this API doesn't cover yet.
- ``srl_eval.py`` (``RuleSet.infer()``/``.query()``, implemented as thin
  delegates to this module's private ``_srl_infer``/``_srl_query``) -
  *running* a ``RuleSet`` against a base graph is a separate concern from
  the tree pipeline above, not a missing or oddly-shaped seventh step:
  unlike Manchester's `manchester_tree_to_owl()` (a pure function of the
  tree alone, translating between two independently-meaningful RDF forms),
  SRL has only one RDF form (`srl:`) - decoding already produces the
  runnable `RuleSet`, and running it inherently needs a second input (the
  base graph) that has nothing to do with this module's own encode/decode/
  validation concerns.
- ``srl_semantic_checks.py`` - cross-referential well-formedness checks
  (an unbound head/filter/assignment variable, a ``SET(...)`` reusing an
  already-bound variable) - deliberately kept out of SHACL (see
  ``srl_validate()``'s own docstring for why structural-only is the line), so
  this is a separate, plain-Python check, not part of this module as a
  *file* - but ``parse_ruleset()`` above calls into it directly (its own
  ``_check_ruleset``) as the well-formedness half
  of this module's one real parse-time gate, the grammar being the other
  half.
"""

from __future__ import annotations

import warnings
from typing import Any

import pyoxigraph as ox

from starlayer._ox_out import ox_out

from . import _oxterms as _T
from . import _srl_ast as srl_ast
from ._oxterms import NS, RDF
from ._srl_ast import (  # noqa: F401 - re-exported, see module docstring
    PlanEdge,
    PlanRule,
    PlanStratum,
    RulePlan,
    RuleSet,
    TriplePattern,
)
from .parse_sparql import _Encoder, _list, _Sink
from .srl_semantic_checks import _check_ruleset
from .triple_term import TripleTermNode
from .vocab import PY_STR_DATATYPE, VARIABLE_DATATYPE

SRL = NS("https://github.com/hidden-graph/starlayer/ns/sparql/srl#")

# ---------------------------------------------------------------------------
# srl: vocabulary - field names taken verbatim from the
# spec's own §4.1 "Component Notation" table, not invented.
# ---------------------------------------------------------------------------

_RULE_SET = SRL.RuleSet
_RULE = SRL.Rule
_DATA_BLOCK = SRL.Data
_TRIPLE_PATTERN = SRL.TriplePattern
_FILTER_ELEMENT = SRL.FilterElement
_NEGATION_ELEMENT = SRL.NegationElement
_ASSIGNMENT_ELEMENT = SRL.AssignmentElement
_GROUP_ELEMENT = SRL.GroupElement
_AGGREGATION = SRL.Aggregation

_TRIPLE_SUBJECT = SRL["subject"]
_TRIPLE_PREDICATE = SRL["predicate"]
_TRIPLE_OBJECT = SRL["object"]

_RULES = SRL["rules"]
_DATA = SRL["data"]
_IMPORTS = SRL["imports"]
_HEAD = SRL["head"]
_BODY = SRL["body"]
_INNER = SRL["inner"]
_TRIPLES = SRL["triples"]

# The spec reuses the name "evaldata" for two components (rule.evaldata and
# negation.evaldata), and "data" for a third (ruleset.data) - each gets its own
# predicate URI to avoid a same-URI-different-shape collision within one shared
# graph. The flag is the spec's own: true = match the evaluation graph (plain
# WHERE / NOT), false = match the base graph only (WHERE DATA / NOT DATA).
_RULE_EVALDATA_FLAG = SRL["ruleEvaldata"]
_RULE_ID = SRL["id"]
_EXPR = SRL["expr"]
_VAR = SRL["var"]
_NEGATION_EVALDATA_FLAG = SRL["negationEvaldata"]
# a group element (§4.1: group.keys, group.pattern, group.aggregations) and its aggregation assignments (aggregation.variable is srl:var;
# aggfunc.name, aggfunc.argument and aggfunc.distinct are srl:function, srl:argument, srl:distinct; no srl:argument is ``*``)
_GROUP_KEYS = SRL["keys"]
_GROUP_PATTERN = SRL["pattern"]
_GROUP_AGGREGATIONS = SRL["aggregations"]
_AGG_FUNCTION = SRL["function"]
_AGG_ARGUMENT = SRL["argument"]
_AGG_DISTINCT = SRL["distinct"]


class SRLError(ValueError):
    """Base class for every SRL-specific exception
    (``SRLParseError``/``SRLDecodeError`` here, ``SRLEvalError`` and its
    own subclasses in ``srl_eval.py``) - gives a caller two real catch
    granularities, "this specific failure" (``SRLParseError``/
    ``SRLDecodeError``) vs. "any SRL failure" (``SRLError`` itself), the
    same two-tier shape rdflib (``rdflib.exceptions.Error``) and pyshacl
    (``pyshacl.errors.ReportableRuntimeError``) each give their own
    callers. Contrast ``starlayer.graph.parsers.errors``'s
    ``Turtle12SyntaxError``/``ManchesterSyntaxError``, which deliberately
    don't share a base - see that module's own docstring for why that
    case is different."""


class SRLParseError(SRLError):
    """Raised by :func:`parse_ruleset` for malformed SRL text, or for text
    that parses fine but fails a §4.2 well-formedness check (see
    `srl_semantic_checks.py`) - one error type for "this SRL text doesn't
    produce a usable `RuleSet`", matching how a caller already has to
    handle this exception from this function regardless of which case
    occurred."""


class SRLImportError(SRLError):
    """Raised by :func:`resolve_imports` when an ``IMPORTS`` document cannot be
    read, or is not a valid rule set (§4.5: a processor MUST signal an error in
    either case)."""


def parse_ruleset(text: str, base: str | None = None, *, validate: bool = True) -> srl_ast.RuleSet:
    """Parse SRL rule-set text into a real ``RuleSet``, with no RDF
    involved at all.

    The text is read by StarLayer's own SPARQL 1.2 parser (``parse_srl``), with prefixed and relative names resolved
    against the text's own ``PREFIX`` / ``BASE`` declarations.

    A successfully-returned ``RuleSet`` is also guaranteed §4.2 well-formed
    (every filter/assignment/head variable properly bound, no ``SET(...)``
    reusing an already-bound variable) - this function is the one real gate,
    the same contract plain SPARQL's own ``prepareQuery()`` has. ``SRLParseError``
    is raised for a §4.2 well-formedness violation too, not just a
    grammar/syntax error: this is what prevents a violating ruleset from
    silently parsing *and* evaluating to a wrong answer with no error at all.

    By default the rule set is then also encoded as RDF and checked against
    the ``srl:`` SHACL shapes (the same check as :func:`srl_validate`), and
    ``SRLParseError`` is raised if it does not conform. That costs on the
    order of 150 ms, against a few ms for parsing alone, so a caller parsing
    many rule sets that it already trusts can pass ``validate=False``.

    Args:
        text: The SRL rule-set text to parse.
        base: Base IRI for resolving relative IRIs, if any.
        validate: Also validate the rule set against the ``srl:`` shapes.
            Defaults to ``True``.

    Returns:
        The parsed, well-formed ``RuleSet``.

    Raises:
        SRLParseError: For malformed SRL text, text that parses but fails a
            §4.2 well-formedness check, or (with ``validate=True``) a rule set
            that does not conform to the ``srl:`` shapes.
    """
    from .parse_srl import parse_srl

    ruleset = parse_srl(text, base)

    issues = _check_ruleset(ruleset)
    if issues:
        summary = "; ".join(
            f"{i.kind} ({i.variable} in {i.context})" if i.variable is not None else f"{i.kind} (in {i.context})"
            for i in issues
        )
        raise SRLParseError(f"SRL: rule set is not well-formed per §4.2: {summary}")
    if validate:
        _check_against_shapes(ruleset)
    return ruleset


# ---------------------------------------------------------------------------
# RuleSet -> srl: tree-RDF. Every term/expression leaf is written as the sqe: / spexpr: encoder writes it
# (``parse_sparql._Encoder``); this only has bespoke logic for the srl:-specific container shapes.
# ---------------------------------------------------------------------------


def ruleset_to_tree(ruleset: srl_ast.RuleSet, graph: Any = None) -> tuple[Any, Any]:
    """Encode ``ruleset`` as ``srl:`` tree-RDF.

    Useful on its own (not just inside ``srl_parse_to_tree``) for a ``RuleSet`` built or edited programmatically - rules
    combined, a filter rewritten - that now needs to go back into RDF, e.g. for storage or SHACL validation, without
    round-tripping through text.

    Args:
        ruleset: The RuleSet to encode.
        graph: Graph to add the encoding to (an ``StarLayerGraph``, which gets pyoxigraph terms, or an rdflib graph, which
            gets rdflib terms and needs rdflib); a fresh ``StarLayerGraph`` if not given.

    Returns:
        A ``(graph, root)`` tuple, ``root`` the ``srl:RuleSet``-typed node (a pyoxigraph term for a ``StarLayerGraph``).
    """
    sink = _Sink()
    root = _Writer(sink).ruleset(ruleset)
    if graph is None:
        from starlayer.graph.oxgraph.core import StarLayerGraph

        graph = StarLayerGraph(prefixes={})
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox

    if _ox.is_oxigraph_input(graph):
        graph.extend(list(sink))
        return graph, root
    from starlayer.graph.model.dirlangstring import DirLangString, encode_dirlangstring

    for row in _ox.to_rdflib_triples(sink):
        # a plain rdflib graph holds a direction-tagged literal in its datatype-IRI form
        graph.add(tuple(encode_dirlangstring(t) if isinstance(t, DirLangString) else t for t in row))
    return graph, _ox.to_rdflib_term(root)


class _Writer:
    """The ``srl:`` tree of a rule set, as triples of pyoxigraph terms."""

    def __init__(self, sink: _Sink) -> None:
        self.g = sink
        self.enc = _Encoder(sink)

    def node(self, value):
        """One leaf of the tree: a term, a triple term, an expression, or a flag."""
        if isinstance(value, bool):
            return _T.boolean(value)
        return self.enc.term(value)

    def ruleset(self, ruleset: srl_ast.RuleSet):
        g = self.g
        root = ox.BlankNode()
        g.add((root, RDF.type, _RULE_SET))
        g.add((root, _RULES, _list(g, [self.rule(r) for r in ruleset.rules])))
        g.add((root, _DATA, _list(g, [self.data(d) for d in ruleset.data])))
        g.add((root, _IMPORTS, _list(g, list(ruleset.imports))))
        return root

    def triple(self, triple: srl_ast.TriplePattern):
        g, node = self.g, ox.BlankNode()
        g.add((node, RDF.type, _TRIPLE_PATTERN))
        g.add((node, _TRIPLE_SUBJECT, self.node(triple.subject)))
        g.add((node, _TRIPLE_PREDICATE, self.node(triple.predicate)))
        g.add((node, _TRIPLE_OBJECT, self.node(triple.object)))
        return node

    def body_element(self, element: srl_ast.BodyElement):
        g = self.g
        if isinstance(element, srl_ast.TriplePattern):
            return self.triple(element)
        node = ox.BlankNode()
        if isinstance(element, srl_ast._FilterElement):
            g.add((node, RDF.type, _FILTER_ELEMENT))
            g.add((node, _EXPR, self.node(element.expr)))
        elif isinstance(element, srl_ast._AssignmentElement):
            g.add((node, RDF.type, _ASSIGNMENT_ELEMENT))
            g.add((node, _VAR, self.node(element.var)))
            g.add((node, _EXPR, self.node(element.expr)))
        elif isinstance(element, srl_ast._NegationElement):
            g.add((node, RDF.type, _NEGATION_ELEMENT))
            g.add((node, _INNER, _list(g, [self.body_element(e) for e in element.inner])))
            g.add((node, _NEGATION_EVALDATA_FLAG, self.node(element.evaldata)))
        elif isinstance(element, srl_ast._GroupElement):
            g.add((node, RDF.type, _GROUP_ELEMENT))
            g.add((node, _GROUP_KEYS, _list(g, [self.node(k) for k in element.keys])))
            g.add((node, _GROUP_PATTERN, _list(g, [self.body_element(e) for e in element.pattern])))
            g.add((node, _GROUP_AGGREGATIONS, _list(g, [self.aggregation(a) for a in element.aggregations])))
        else:  # pragma: no cover
            raise NotImplementedError(f"starlayer.sparql.srl: no encoding for body element {element!r}")
        return node

    def aggregation(self, agg: srl_ast._Aggregation):
        g, node = self.g, ox.BlankNode()
        g.add((node, RDF.type, _AGGREGATION))
        g.add((node, _VAR, self.node(agg.var)))
        g.add((node, _AGG_FUNCTION, ox.Literal(agg.function)))
        if agg.argument is not None:
            g.add((node, _AGG_ARGUMENT, self.node(agg.argument)))
        g.add((node, _AGG_DISTINCT, self.node(agg.distinct)))
        return node

    def rule(self, rule: srl_ast._Rule):
        g, node = self.g, ox.BlankNode()
        g.add((node, RDF.type, _RULE))
        g.add((node, _HEAD, _list(g, [self.triple(t) for t in rule.head])))
        g.add((node, _BODY, _list(g, [self.body_element(e) for e in rule.body])))
        g.add((node, _RULE_EVALDATA_FLAG, self.node(rule.evaldata)))
        if rule.id is not None:
            g.add((node, _RULE_ID, rule.id))
        return node

    def data(self, data: srl_ast._Data):
        g, node = self.g, ox.BlankNode()
        g.add((node, RDF.type, _DATA_BLOCK))
        g.add((node, _TRIPLES, _list(g, [self.triple(t) for t in data.triples])))
        return node


# ---------------------------------------------------------------------------
# srl: tree-RDF -> RuleSet - the inverse, same "bespoke containers, delegate leaves" split.
# ---------------------------------------------------------------------------

class SRLDecodeError(SRLError):
    """Raised for an ``srl:`` graph shape ``tree_to_ruleset`` doesn't recognize."""


def _read_list(node, graph) -> list:
    if node is None or node == RDF.nil:
        return []
    return list(graph.items(node))


def _decode_expr(node, graph):
    """An expression leaf: a term as it is, an ``spexpr:`` node as the parser's tree of the text the node renders to."""
    from .parse_sparql import SparqlSyntaxError, _Parser
    from .parse_srl import _convert
    from .sqe.expr_text import expr_text

    if node is None:
        return None
    if isinstance(node, ox.BlankNode) and (node, RDF.type, None) in graph:
        text = expr_text(node, graph, {})
        try:
            parser = _Parser(text, None)
            expr = parser.expression()
            if parser.peek().kind != "EOF":
                raise SparqlSyntaxError("trailing text after the expression")
        except SparqlSyntaxError as exc:
            raise SRLDecodeError(f"srl: cannot read the expression {text!r}: {exc}") from exc
        return _convert(expr)
    return _decode_term(node, graph)


def _decode_term(node, graph):
    from .sqe.vocab import (
        TRIPLE_PATTERN_OBJECT,
        TRIPLE_PATTERN_PREDICATE,
        TRIPLE_PATTERN_SUBJECT,
        TRIPLE_TERM,
    )

    if node is None:
        return None
    if isinstance(node, ox.Literal):
        if node.datatype == VARIABLE_DATATYPE:
            return ox.Variable(node.value)
        if node.datatype == PY_STR_DATATYPE:
            return node.value
        return node
    if isinstance(node, ox.BlankNode) and (node, RDF.type, TRIPLE_TERM) in graph:
        parts = {
            name: _decode_term(graph.value(node, predicate), graph)
            for name, predicate in (
                ("subject", TRIPLE_PATTERN_SUBJECT),
                ("predicate", TRIPLE_PATTERN_PREDICATE),
                ("object", TRIPLE_PATTERN_OBJECT),
            )
        }
        return TripleTermNode("TripleTerm", **parts).validate()
    return node


def _decode_triple(node, graph) -> srl_ast.TriplePattern:
    return srl_ast.TriplePattern(
        subject=_decode_term(graph.value(node, _TRIPLE_SUBJECT), graph),
        predicate=_decode_term(graph.value(node, _TRIPLE_PREDICATE), graph),
        object=_decode_term(graph.value(node, _TRIPLE_OBJECT), graph),
    )


def _is_true(node) -> bool:
    return isinstance(node, ox.Literal) and node.value in ("true", "1")


def _decode_body_element(node, graph) -> srl_ast.BodyElement:
    t = graph.value(node, RDF.type)
    if t == _TRIPLE_PATTERN:
        return _decode_triple(node, graph)
    if t == _FILTER_ELEMENT:
        return srl_ast._FilterElement(expr=_decode_expr(graph.value(node, _EXPR), graph))
    if t == _ASSIGNMENT_ELEMENT:
        return srl_ast._AssignmentElement(
            var=_decode_term(graph.value(node, _VAR), graph),
            expr=_decode_expr(graph.value(node, _EXPR), graph),
        )
    if t == _NEGATION_ELEMENT:
        inner = [_decode_body_element(n, graph) for n in _read_list(graph.value(node, _INNER), graph)]
        return srl_ast._NegationElement(inner=inner, evaldata=_is_true(graph.value(node, _NEGATION_EVALDATA_FLAG)))
    if t == _GROUP_ELEMENT:
        return srl_ast._GroupElement(
            keys=[_decode_term(n, graph) for n in _read_list(graph.value(node, _GROUP_KEYS), graph)],
            pattern=[_decode_body_element(n, graph) for n in _read_list(graph.value(node, _GROUP_PATTERN), graph)],
            aggregations=[_decode_aggregation(n, graph) for n in _read_list(graph.value(node, _GROUP_AGGREGATIONS), graph)],
        )
    raise SRLDecodeError(f"unrecognized rule body element node {node!r} (rdf:type {t!r})")


def _decode_aggregation(node, graph) -> srl_ast._Aggregation:
    function = graph.value(node, _AGG_FUNCTION)
    if not isinstance(function, ox.Literal) or function.value not in ("COUNT", "MIN", "MAX", "SUM"):
        raise SRLDecodeError(f"aggregation node {node!r} has no aggregation function COUNT, MIN, MAX or SUM")
    argument = graph.value(node, _AGG_ARGUMENT)
    return srl_ast._Aggregation(
        var=_decode_term(graph.value(node, _VAR), graph),
        function=function.value,
        argument=None if argument is None else _decode_term(argument, graph),
        distinct=_is_true(graph.value(node, _AGG_DISTINCT)),
    )


def _decode_rule(node, graph) -> srl_ast._Rule:
    head = [_decode_triple(n, graph) for n in _read_list(graph.value(node, _HEAD), graph)]
    body = [_decode_body_element(n, graph) for n in _read_list(graph.value(node, _BODY), graph)]
    evaldata = _is_true(graph.value(node, _RULE_EVALDATA_FLAG))
    return srl_ast._Rule(head=head, body=body, evaldata=evaldata, id=graph.value(node, _RULE_ID))


def _decode_data(node, graph) -> srl_ast._Data:
    return srl_ast._Data(triples=[_decode_triple(n, graph) for n in _read_list(graph.value(node, _TRIPLES), graph)])


def tree_to_ruleset(graph: Any, root) -> srl_ast.RuleSet:
    """Decode the ``srl:RuleSet`` node ``root`` in ``graph`` (as returned by
    ``srl_parse_to_tree``/``ruleset_to_tree``, or an LLM-authored ``srl:`` graph
    not yet decoded) back into a real ``srl_ast.RuleSet``."""
    from .sqe._memtree import as_engine_graph

    graph, root = as_engine_graph(graph, root)
    try:
        rules = [_decode_rule(n, graph) for n in _read_list(graph.value(root, _RULES), graph)]
        data = [_decode_data(n, graph) for n in _read_list(graph.value(root, _DATA), graph)]
        imports = _read_list(graph.value(root, _IMPORTS), graph)
    except SRLError:
        raise
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        # a damaged tree (a list cell without rdf:rest, a missing part, a triple term that is not one) is the one error
        # a caller reading hand-edited trees catches
        raise SRLDecodeError(f"srl: the tree cannot be read as a rule set: {exc}") from exc
    return srl_ast.RuleSet(rules=rules, data=data, imports=imports)


# ---------------------------------------------------------------------------
# RuleSet -> SRL text - the inverse of parse_ruleset, working directly on the dataclass tree, no RDF involved.
# ---------------------------------------------------------------------------

def ruleset_to_text(ruleset: srl_ast.RuleSet, namespace_manager: Any = None) -> str:
    """Render ``ruleset`` back into SRL text - ``IMPORTS``/``DATA`` blocks
    first, then each ``RULE``, in the order they appear on the dataclass
    tree.

    **No original ``PREFIX``/``BASE`` declarations are preserved**: the parsed syntax tree only ever
    holds fully-resolved absolute IRIs; prefix declarations are consumed
    during parsing and never stored.

    Args:
        ruleset: The RuleSet to render.
        namespace_manager: If given (a prefix -> namespace ``dict``, a ``StarLayerGraph`` (its ``prefixes``) or an rdflib
            ``NamespaceManager``), render prefixed names instead of full
            ``<...>`` IRIs wherever a match exists - purely cosmetic, the
            resulting text still parses identically either way.

    Returns:
        The rendered SRL text.
    """
    prefixes = _prefixes_of(namespace_manager)
    lines = [f"IMPORTS {_term_text(iri_, prefixes)}" for iri_ in ruleset.imports]
    lines += [_data_text(block, prefixes) for block in ruleset.data]
    lines += [_rule_text(rule, prefixes) for rule in ruleset.rules]
    return "\n".join(lines)


def _prefixes_of(source) -> dict[str, str]:
    """``source`` as a prefix -> namespace dict: a dict, a ``StarLayerGraph`` (its ``prefixes``) or anything with
    ``namespaces()`` (an rdflib ``NamespaceManager``); ``None`` is no prefixes."""
    if source is None:
        return {}
    prefixes = source if isinstance(source, dict) else getattr(source, "prefixes", None)
    if prefixes is None and hasattr(source, "namespaces"):
        prefixes = dict(source.namespaces())
    return {str(k): str(v) for k, v in (prefixes or {}).items()}


def _term_text(term, prefixes: dict) -> str:
    from .sqe.expr_text import expr_text

    if isinstance(term, ox.Variable):
        return "?" + term.value
    if isinstance(term, (ox.NamedNode, ox.Literal)):
        return expr_text(term, None, prefixes)
    if isinstance(term, ox.BlankNode):
        return "_:" + _T.bnode_label(term)
    if isinstance(term, TripleTermNode):
        s, p, o = (_term_text(term.get(part), prefixes) for part in ("subject", "predicate", "object"))
        return f"<<( {s} {p} {o} )>>"
    raise NotImplementedError(f"starlayer.sparql.srl: no text rendering for term {term!r}")


def _triple_text(triple: srl_ast.TriplePattern, prefixes: dict) -> str:
    return f"{_term_text(triple.subject, prefixes)} {_term_text(triple.predicate, prefixes)} {_term_text(triple.object, prefixes)} ."


def _block_text(triples: list[srl_ast.TriplePattern], prefixes: dict) -> str:
    return " ".join(_triple_text(t, prefixes) for t in triples)


def _expr_text(expr, prefixes: dict) -> str:
    """An expression as SPARQL text, rendered by ``sqe:``'s renderer from the same tree the encoder builds."""
    from .expr_text import render_expression

    return render_expression(expr, prefixes)


def _body_element_text(element: srl_ast.BodyElement, prefixes: dict) -> str:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_text(element, prefixes)
    if isinstance(element, srl_ast._FilterElement):
        return f"FILTER({_expr_text(element.expr, prefixes)})"
    if isinstance(element, srl_ast._AssignmentElement):
        return f"SET ({_term_text(element.var, prefixes)} := {_expr_text(element.expr, prefixes)})"
    if isinstance(element, srl_ast._NegationElement):
        inner = " ".join(_body_element_text(e, prefixes) for e in element.inner)
        data = "" if element.evaldata else "DATA "
        return f"NOT {data}{{ {inner} }}"
    if isinstance(element, srl_ast._GroupElement):
        keys = "BY " + " ".join(_term_text(k, prefixes) for k in element.keys) + " " if element.keys else ""
        inner = " ".join(_body_element_text(e, prefixes) for e in element.pattern)
        aggregations = ", ".join(_aggregation_text(a, prefixes) for a in element.aggregations)
        return f"GROUP {keys}{{ {inner} }} [ {aggregations} ]" if aggregations else f"GROUP {keys}{{ {inner} }} []"
    raise NotImplementedError(f"starlayer.sparql.srl: no text rendering yet for body element {element!r}")


def _aggregation_text(agg: srl_ast._Aggregation, prefixes: dict) -> str:
    argument = "*" if agg.argument is None else _term_text(agg.argument, prefixes)
    distinct = "DISTINCT " if agg.distinct else ""
    return f"{_term_text(agg.var, prefixes)} := {agg.function}({distinct}{argument})"


def _data_text(data: srl_ast._Data, prefixes: dict) -> str:
    return f"DATA {{ {_block_text(data.triples, prefixes)} }}"


def _rule_text(rule: srl_ast._Rule, prefixes: dict) -> str:
    rule_id = f"{_term_text(rule.id, prefixes)} " if rule.id is not None else ""
    head = _block_text(rule.head, prefixes)
    body = " ".join(_body_element_text(e, prefixes) for e in rule.body)
    data = "" if rule.evaldata else "DATA "
    return f"RULE {rule_id}{{ {head} }} WHERE {data}{{ {body} }}"


# ---------------------------------------------------------------------------
# Composed text <-> tree-RDF convenience, matching starontology.manchester's
# srl_parse_to_tree()/srl_tree_to_text() naming.
# ---------------------------------------------------------------------------

def srl_parse_to_tree(text: str, base: str | None = None, graph: Any = None) -> tuple[Any, Any]:
    """SRL text straight to its ``srl:``-encoded tree-RDF. Composes
    ``parse_ruleset`` + ``ruleset_to_tree``. Returns ``(graph, root)``; ``graph`` (an ``StarLayerGraph``, which gives pyoxigraph terms,
    or an rdflib graph) is where the tree is written, a fresh ``StarLayerGraph`` when omitted."""
    return ruleset_to_tree(parse_ruleset(text, base), graph)


def srl_tree_to_text(graph: Any, root) -> str:
    """The inverse of ``srl_parse_to_tree``. Composes ``tree_to_ruleset`` +
    ``ruleset_to_text``."""
    return ruleset_to_text(tree_to_ruleset(graph, root))


# ---------------------------------------------------------------------------
# IMPORTS (§3.7, §4.5, Appendix B)
# ---------------------------------------------------------------------------


def _rename_blank_nodes(term, mapping: dict):
    if isinstance(term, ox.BlankNode):
        return mapping.setdefault(term, ox.BlankNode())
    if isinstance(term, TripleTermNode):
        parts = {k: _rename_blank_nodes(term.get(k), mapping) for k in ("subject", "predicate", "object")}
        return TripleTermNode("TripleTerm", **parts)
    return term


def resolve_imports(ruleset: srl_ast.RuleSet, loader, *, location: str | None = None) -> srl_ast.RuleSet:
    """Return the *resolved* rule set (§4.5): ``ruleset`` with every ``IMPORTS``
    document read, recursively, and its rules and ``DATA`` merged in. The result
    has no imports left. ``ruleset`` itself is not changed.

    Reading a document from the web has security implications, so nothing is read
    unless the caller supplies ``loader`` - there is no default. The loader decides
    where documents come from: a directory, a verified copy, a dictionary.

    Each document is imported only once (§3.7), so a diamond or a cycle among the
    imports does not repeat or loop. The merge follows Appendix B: the importing rule
    set's rules come first, then each import's, in order; ``DATA`` blocks are
    combined as an RDF merge, so a blank node in an imported document stays distinct
    from a same-labelled blank node in another document.

    Args:
        ruleset: The rule set whose imports are resolved.
        loader: ``loader(iri) -> str | RuleSet``: given an import IRI (a string),
            returns the document's SRL text (parsed with ``base=iri``) or an already
            parsed ``RuleSet``. It may raise to say the document cannot be read.
        location: The IRI ``ruleset`` was read from, if any. It counts as already
            imported, so a document that imports itself is not read again.

    Returns:
        A new ``RuleSet`` with ``imports == []``.

    Raises:
        SRLImportError: If the loader fails for an import, or returns text that is
            not a valid rule set.
    """
    visited: set[str] = {str(location)} if location else set()

    def _merge(rs: srl_ast.RuleSet, renamed: bool) -> tuple[list, list]:
        rules = list(rs.rules)
        if renamed:
            mapping: dict = {}
            data = [
                srl_ast._Data(
                    triples=[
                        srl_ast.TriplePattern(
                            _rename_blank_nodes(t.subject, mapping),
                            t.predicate,
                            _rename_blank_nodes(t.object, mapping),
                        )
                        for t in block.triples
                    ]
                )
                for block in rs.data
            ]
        else:
            data = list(rs.data)
        for import_iri in rs.imports:
            if _T.iri_text(import_iri) in visited:
                continue
            visited.add(_T.iri_text(import_iri))
            try:
                loaded = loader(_T.iri_text(import_iri))
            except Exception as exc:
                reason = "not found" if isinstance(exc, KeyError) else f"{type(exc).__name__}: {exc}"
                raise SRLImportError(f"SRL: cannot read the import <{import_iri}>: {reason}") from exc
            if isinstance(loaded, str):
                try:
                    loaded = parse_ruleset(loaded, base=_T.iri_text(import_iri))
                except SRLParseError as exc:
                    raise SRLImportError(f"SRL: the import <{import_iri}> is not a valid rule set: {exc}") from exc
            sub_rules, sub_data = _merge(loaded, renamed=True)
            rules += sub_rules
            data += sub_data
        return rules, data

    rules, data = _merge(ruleset, renamed=False)
    return srl_ast.RuleSet(rules=rules, data=data, imports=[], prefixes=dict(ruleset.prefixes))


# ---------------------------------------------------------------------------
# SHACL validation of an srl: tree-RDF graph - ontology_graph()/
# shapes_graph() deliberately not exposed publicly here, see module
# docstring for why.
# ---------------------------------------------------------------------------

def _ontology_graph() -> Any:
    """The ``srl:`` RDFS ontology, combined with the shared ``spexpr:`` expression ontology and ``sqe:``'s
    (which supplies ``sqe:TripleTerm``) - private: see module docstring for why this isn't exposed publicly.

    All three must be loaded together: this module's own SHACL shapes use ``sh:class spexpr:Expression`` and
    ``spexpr:Variable``, and the RDFS subclass entailment those checks depend on only resolves correctly when
    the ontologies are in the same graph. SRL is published with ``spexpr:`` and ``sqe:``.

    Returns:
        A fresh combined ontology graph.
    """
    from starlayer import starontology

    from .expr_validation import _merge_into
    from .expr_validation import ontology_graph as spexpr_ontology_graph

    g = spexpr_ontology_graph()
    _merge_into(g, starontology.get_ontology_graph("srl_owl"))
    _merge_into(g, starontology.get_ontology_graph("sqe_owl"))
    return g


def _shapes_graph() -> Any:
    """A fresh graph of the ``srl:`` shapes, combined with the shared ``spexpr:`` expression shapes and
    ``sqe:``'s (the triple-term shapes) - private, same reasoning as ``_ontology_graph()`` above."""
    from starlayer import starontology

    from .expr_validation import _merge_into
    from .expr_validation import shapes_graph as spexpr_shapes_graph

    g = spexpr_shapes_graph()
    _merge_into(g, starontology.get_ontology_graph("srl_shacl"))
    _merge_into(g, starontology.get_ontology_graph("sqe_shacl"))
    return g


_validation_graphs_cache: tuple[Any, Any, Any] | None = None


def _validation_graphs() -> tuple[Any, Any, Any]:
    """The ``(shapes, ontology, closed schema maps)`` ``srl_validate`` uses, built once and
    reused: validation does not modify them, and building them costs about 20 ms
    per call."""
    global _validation_graphs_cache
    if _validation_graphs_cache is None:
        from .expr_validation import rdfs_schema

        ontology = _ontology_graph()
        _validation_graphs_cache = (_shapes_graph(), ontology, rdfs_schema(ontology))
    return _validation_graphs_cache


def _check_against_shapes(ruleset: srl_ast.RuleSet) -> None:
    """Raise ``SRLParseError`` if ``ruleset``'s RDF encoding does not conform to
    the ``srl:`` shapes."""
    from starlayer.shacl_engine.terms import StarLayerFidelityWarning

    graph, _root = ruleset_to_tree(ruleset)
    with warnings.catch_warnings():
        # the library's own tree and shapes are checked here, not the caller's data: a lexical-form warning is not theirs to act on
        warnings.simplefilter("ignore", StarLayerFidelityWarning)
        conforms, report_graph, report_text = srl_validate(graph)
    if conforms:
        return
    shacl_message = ox.NamedNode("http://www.w3.org/ns/shacl#resultMessage")
    messages = sorted({m.value for m in report_graph.objects(None, shacl_message)})
    detail = "; ".join(messages) if messages else report_text.strip().splitlines()[0]
    raise SRLParseError(f"SRL: rule set does not conform to the srl: shapes: {detail}")


@ox_out("data_graph")
def srl_validate(data_graph: Any) -> tuple[bool, Any, str]:
    """Validate ``data_graph`` (e.g. straight out of ``srl_parse_to_tree()``,
    or an LLM-authored ``srl:`` graph not yet decoded) against the ``srl:``
    shapes.

    Goes through ``starlayer.shacl.validate()``, never bare ``pyshacl`` -
    same rule every other shapes module in this stack follows, since a
    caller-supplied graph may carry genuine RDF 1.2 content (a triple term
    as a ``srl:subject``/``srl:object``) that only ``starlayer.shacl``
    understands correctly.

    Args:
        data_graph: The ``srl:`` tree-RDF graph to validate.

    Returns:
        A ``(conforms, report_graph, report_text)`` tuple, unpacked from
        ``starlayer.shacl``'s own ``ValidationResult``.
    """

    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time

    from .expr_validation import rdfs_entailed_copy
    from .sqe._memtree import as_engine_graph

    shapes, _ontology, schema = _validation_graphs()
    data_graph, _ = as_engine_graph(data_graph)
    result = starlayer.shacl.validate(
        rdfs_entailed_copy(data_graph, schema),  # the RDFS closure the shapes rely on, done natively
        shacl_graph=shapes,
        invalid_terms="lenient",  # query / ontology trees hold relative IRIs: opaque terms to the shapes
        advanced=True,
        max_validation_depth=100,
    )
    return result.conforms, result.report_graph, result.report_text
