"""starlayer.sparql.srl

SRL (SPARQL Rules; spec `WD-sparql12-rl-20260919 <https://www.w3.org/TR/sparql12-rl/>`_)
- a Datalog-style rules language built on SPARQL triple patterns and filter
expressions. This module provides SRL text, its tree-RDF encoding (``srl:``; the ordered children of a node, such as a rule's body
or a rule set's rules, are written with the shared ``tree:`` vocabulary: ``tree:ord`` on each child, ``tree:Item`` for a variable or
an IRI, no ``rdf:List``; the argument lists inside an expression are ordinals too, written by the shared ``spexpr:`` encoder),
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

An expression (``srl:expr``, the ``SET`` and ``FILTER`` operand) is written by the ``spexpr:`` encoder it shares with ``sqe:``
(``parse_sparql._Encoder``), so the argument and operand lists of an expression (``spexpr:args``, ``other``, ``op``) are ordinals too.

Four entry points on the ``RuleSet`` object, which with ``parse_ruleset`` make the round trips text<->RuleSet and
RuleSet<->tree-RDF (text<->tree-RDF is ``starlayer.sparql.sparql_to_tree`` / ``tree_to_sparql``, which compose them):

- ``parse_ruleset(text, base=None, *, imports_loader=None) -> RuleSet`` - SRL text
  straight to a real ``RuleSet`` object, skipping RDF entirely in the result
  (any text the grammar accepts gives a rule set; ``validate_sparql_tree`` reports its problems). Kept as its own
  entry point (``sparql_to_tree`` reads SRL text as a tree) because ``RuleSet`` is independently useful - ``RuleSet.infer()``/
  ``.query()`` run it directly, with no RDF involved at all. This is
  the one real asymmetry with Manchester: ``manch:``'s ``Document`` object
  never existed before its own syntax-tree-as-RDF module invented it purely
  as a decode artifact; SRL's ``RuleSet`` already existed independently.
- ``ruleset_to_text(ruleset, namespace_manager=None) -> str`` - the
  inverse of ``parse_ruleset``, working on the syntax tree directly.
- ``tree_to_ruleset(graph, root) -> RuleSet`` - decode ``srl:``-encoded
  tree-RDF into a real ``RuleSet``, e.g. after programmatically editing the
  RDF via plain graph surgery.
- ``ruleset_to_tree(ruleset, graph=None, *, root=None) -> (graph, root)`` - the inverse:
  encode a ``RuleSet`` (e.g. one built or edited programmatically - rules
  combined, a filter rewritten) back to ``srl:`` tree-RDF.

The functions that read SRL text as a tree, write a tree as text and validate it are the ones that cover SPARQL and Update too
(``starlayer.sparql``: ``sparql_to_tree``, ``tree_to_sparql``, ``validate_sparql_tree``); this module holds the SRL halves
(``validate_srl_tree`` is the structural SHACL validation of an ``srl:`` tree-RDF graph). Deliberately
**no** public ``ontology_graph()``/``shapes_graph()`` here (same decision
``starontology.manchester`` makes for ``manch:``) - callers who want the
raw ``srl:`` ontology/shapes graphs themselves can already get them from
``starontology`` directly instead: ``get_ontology_graph("srl_owl")`` /
``get_ontology_graph("srl_shacl")``. Exposing a second path to the exact
same two graphs here would just be another way to do what that one already
does. ``validate_srl_tree()`` still needs its own private, combined copy
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
  same "no two paths to the same graphs" reasoning ``validate_sparql_tree()``'s
  own docstring note above already applies to ``ontology_graph()``/
  ``shapes_graph()``. The rest (``_Rule``/``_Data``/``_FilterElement``/
  ``_AssignmentElement``/``_NegationElement``) are private: no public
  function or method requires any of them directly (``TriplePattern`` is
  still re-exported, but ``RuleSet.query()`` takes its goal as SPARQL text, so a caller does not need it) - the only way a caller would touch one is by walking
  ``RuleSet.rules``/``Rule.head``/``Rule.body``, an inspection/editing
  concern this API doesn't cover yet.
- ``srl_eval.py`` (``RuleSet.infer()``/``.query()``, implemented as thin
  delegates to this module's private ``_srl_infer``/``_srl_query``) -
  *running* a ``RuleSet`` against a base graph is a separate concern from
  the tree pipeline above, not a missing or oddly-shaped seventh step:
  unlike Manchester's `tree_to_owl()` (a pure function of the
  tree alone, translating between two independently-meaningful RDF forms),
  SRL has only one RDF form (`srl:`) - decoding already produces the
  runnable `RuleSet`, and running it inherently needs a second input (the
  base graph) that has nothing to do with this module's own encode/decode/
  validation concerns.
- ``srl_semantic_checks.py`` - the §4.2 well-formedness checks (an unbound head/filter/assignment variable, a ``SET(...)``
  reusing an already-bound variable) as a plain-Python function over the decoded rule set. Running a rule set calls it. The same
  conditions are SHACL shapes in ``srl_shapes.ttl``, and ``validate_sparql_tree()`` reports those (a result per offending element); the
  two are kept equal by a test, because a SPARQL constraint per element is too slow to run on every ``infer()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyoxigraph as ox

from starlayer.errors import ExecutionError, FormatError, only_kind
from starlayer.graph import ordinals

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
from .parse_sparql import _Encoder, _Sink
from .triple_term import TripleTermNode
from .vocab import PY_STR_DATATYPE, VARIABLE_DATATYPE

if TYPE_CHECKING:
    from starlayer.shacl.results import ValidationReport

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

# The spec reuses the name "evalground" for two components (rule.evalground and
# negation.evalground), and "data" for a third (ruleset.data) - each gets its own
# predicate URI to avoid a same-URI-different-shape collision within one shared
# graph. The flag is the spec's own: true = match the evaluation graph (plain
# WHERE / NOT), false = match the base graph only (WHERE GROUND / NOT GROUND).
_RULE_EVALGROUND_FLAG = SRL["ruleEvalground"]
_RULE_ID = SRL["id"]
_EXPR = SRL["expr"]
_VAR = SRL["var"]
_NEGATION_EVALGROUND_FLAG = SRL["negationEvalground"]
# a group element (§4.1: group.keys, group.pattern, group.aggregations) and its aggregation assignments (aggregation.variable is srl:var;
# aggfunc.name, aggfunc.argument and aggfunc.distinct are srl:function, srl:argument, srl:distinct; no srl:argument is ``*``)
_GROUP_KEYS = SRL["keys"]
_GROUP_PATTERN = SRL["pattern"]
_GROUP_AGGREGATIONS = SRL["aggregations"]
_AGG_FUNCTION = SRL["function"]
_AGG_ARGUMENT = SRL["argument"]
_AGG_DISTINCT = SRL["distinct"]


def parse_ruleset(text: str, base: str | None = None, *, imports_loader: Any | None = None) -> srl_ast.RuleSet:
    """Parse SRL rule-set text into a real ``RuleSet``, with no RDF
    involved at all.

    The text is read by StarLayer's own SPARQL 1.2 parser (``parse_srl``), with prefixed and relative names resolved
    against the text's own ``PREFIX`` / ``BASE`` declarations.

    Any text the grammar accepts gives a rule set, so a rule set with a problem can still be loaded and fixed. Nothing else
    is checked here: not the §4.2 well-formedness conditions (an unbound head, filter or assignment variable, a ``SET(...)``
    reusing a bound variable), not the ``srl:`` shapes, not that the rules can be ordered. :func:`validate_sparql_tree` reports all three
    for the rule set's tree (``ruleset_to_tree``); running (``infer()``, ``query()``, ``materialize()``) a rule set that breaks a §4.2 condition raises a ``FormatError`` (kind
    ``"srl"``), and one that cannot be ordered an ``ExecutionError`` (kind ``"rule"``), so it never evaluates to a wrong answer.

    With ``imports_loader`` (as for :func:`resolve_imports`) the ``IMPORTS`` are resolved while the
    text is parsed, and the result is the resolved rule set (``is_resolved`` is true). ``base`` is then also the IRI the
    text was read from, so a document that imports itself is not read again.

    Args:
        text: The SRL rule-set text to parse.
        base: Base IRI for resolving relative IRIs, if any.
        imports_loader: ``loader(iri) -> str | RuleSet``, as for :func:`resolve_imports`. Without
            one, a rule set with ``IMPORTS`` is returned with them unresolved.

    Returns:
        The parsed ``RuleSet``.

    Raises:
        FormatError: (kind "srl") For text outside the SRL grammar, an undeclared prefix or a property path SRL does not allow.
        ExecutionError: (kind ``"import"``) and FormatError (kind ``"srl"``): With ``imports_loader``, as for :func:`resolve_imports`.
    """
    from .parse_srl import parse_srl

    ruleset = parse_srl(text, base)
    if imports_loader is not None and ruleset.imports:
        return _resolve_imports(ruleset, imports_loader, location=base, check=False)
    return ruleset


def _check_stratification(ruleset: srl_ast.RuleSet) -> None:
    """Raise an ``ExecutionError`` (kind ``"rule"``) if the rules of ``ruleset`` cannot be ordered."""
    from .srl_eval import _stratify

    _stratify(ruleset)


# ---------------------------------------------------------------------------
# RuleSet -> srl: tree-RDF. Every term/expression leaf is written as the sqe: / spexpr: encoder writes it
# (``parse_sparql._Encoder``); this only has bespoke logic for the srl:-specific container shapes.
# ---------------------------------------------------------------------------


def ruleset_to_tree(ruleset: srl_ast.RuleSet, graph: Any = None, *, root: Any = None) -> tuple[Any, Any]:
    """Encode ``ruleset`` as ``srl:`` tree-RDF.

    Useful on its own (not just inside ``sparql_to_tree``) for a ``RuleSet`` built or edited programmatically - rules
    combined, a filter rewritten - that now needs to go back into RDF, e.g. for storage or SHACL validation, without
    round-tripping through text.

    Args:
        ruleset: The RuleSet to encode.
        graph: The ``StarLayerGraph`` to add the encoding to; a fresh one if not given.
        root: The node to use as the rule set's root (an IRI or blank node), a fresh blank node when not given.

    Returns:
        A ``(graph, root)`` tuple, ``root`` the ``srl:RuleSet``-typed node .
    """
    sink = _Sink()
    root = _Writer(sink).ruleset(ruleset, root)
    if graph is None:
        from starlayer.graph.core import StarLayerGraph

        graph = StarLayerGraph(prefixes={})
    graph.extend(list(sink))
    return graph, root


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

    def ruleset(self, ruleset: srl_ast.RuleSet, root=None):
        g = self.g
        root = ox.BlankNode() if root is None else root
        g.add((root, RDF.type, _RULE_SET))
        self.sequence(root, _RULES, [self.rule(r) for r in ruleset.rules])
        self.sequence(root, _DATA, [self.data(d) for d in ruleset.data])
        self.sequence(root, _IMPORTS, list(ruleset.imports))
        return root

    def sequence(self, parent, prop, members) -> None:
        """The ordered children of ``parent`` for ``prop``: each fresh blank node carries ``tree:ord`` itself, an IRI or a variable sits in a
        ``tree:Item``."""
        ordinals.write_ordered(self.g, parent, prop, members)

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
            self.sequence(node, _INNER, [self.body_element(e) for e in element.inner])
            g.add((node, _NEGATION_EVALGROUND_FLAG, self.node(element.evalground)))
        elif isinstance(element, srl_ast._GroupElement):
            g.add((node, RDF.type, _GROUP_ELEMENT))
            self.sequence(node, _GROUP_KEYS, [self.node(k) for k in element.keys])
            self.sequence(node, _GROUP_PATTERN, [self.body_element(e) for e in element.pattern])
            self.sequence(node, _GROUP_AGGREGATIONS, [self.aggregation(a) for a in element.aggregations])
        else:  # pragma: no cover
            raise ExecutionError(f"starlayer.sparql.srl: no encoding for body element {element!r}", kind="unsupported", context="srl: tree encoding")
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
        self.sequence(node, _HEAD, [self.triple(t) for t in rule.head])
        self.sequence(node, _BODY, [self.body_element(e) for e in rule.body])
        g.add((node, _RULE_EVALGROUND_FLAG, self.node(rule.evalground)))
        if rule.id is not None:
            g.add((node, _RULE_ID, rule.id))
        return node

    def data(self, data: srl_ast._Data):
        g, node = self.g, ox.BlankNode()
        g.add((node, RDF.type, _DATA_BLOCK))
        self.sequence(node, _TRIPLES, [self.triple(t) for t in data.triples])
        return node


# ---------------------------------------------------------------------------
# srl: tree-RDF -> RuleSet - the inverse, same "bespoke containers, delegate leaves" split.
# ---------------------------------------------------------------------------

def _tree_error(message: str) -> FormatError:
    """The error for an ``srl:`` tree that is not a usable rule set (a missing part, an unknown element, a loop)."""
    return FormatError(message, kind="srl", why=message, context="srl: tree")


def _children(graph, node, prop) -> list:
    """The ordered children of ``node`` for ``prop`` (``graph/ordinals.py``); none is an empty list. A tie, a missing or non-integer
    ordinal is a ``FormatError`` (kind ``"rdf"``) and is not turned into kind ``"srl"``: the tree has no order to decode."""
    return ordinals.ordered_items(graph, node, prop)


def _decode_expr(node, graph):
    """An expression leaf: a term as it is, an ``spexpr:`` node as the parser's tree of the text the node renders to."""
    from .parse_sparql import _Parser, _syntax_error
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
                raise _syntax_error("trailing text after the expression")
        except FormatError as exc:
            raise _tree_error(f"srl: cannot read the expression {text!r}: {exc}") from exc
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


def _decode_body_element(node, graph, path: tuple = ()) -> srl_ast.BodyElement:
    """``path`` is the elements being decoded above ``node``: an element that holds itself (a loop through the ordered children) cannot be decoded."""
    if node in path:
        raise _tree_error(f"srl: the rule body element {node!r} contains itself")
    path = (*path, node)
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
        inner = [_decode_body_element(n, graph, path) for n in _children(graph, node, _INNER)]
        return srl_ast._NegationElement(inner=inner, evalground=_is_true(graph.value(node, _NEGATION_EVALGROUND_FLAG)))
    if t == _GROUP_ELEMENT:
        return srl_ast._GroupElement(
            keys=[_decode_term(n, graph) for n in _children(graph, node, _GROUP_KEYS)],
            pattern=[_decode_body_element(n, graph, path) for n in _children(graph, node, _GROUP_PATTERN)],
            aggregations=[_decode_aggregation(n, graph) for n in _children(graph, node, _GROUP_AGGREGATIONS)],
        )
    raise _tree_error(f"unrecognized rule body element node {node!r} (rdf:type {t!r})")


def _decode_aggregation(node, graph) -> srl_ast._Aggregation:
    function = graph.value(node, _AGG_FUNCTION)
    if not isinstance(function, ox.Literal) or function.value not in ("COUNT", "MIN", "MAX", "SUM"):
        raise _tree_error(f"aggregation node {node!r} has no aggregation function COUNT, MIN, MAX or SUM")
    argument = graph.value(node, _AGG_ARGUMENT)
    return srl_ast._Aggregation(
        var=_decode_term(graph.value(node, _VAR), graph),
        function=function.value,
        argument=None if argument is None else _decode_term(argument, graph),
        distinct=_is_true(graph.value(node, _AGG_DISTINCT)),
    )


def _decode_rule(node, graph) -> srl_ast._Rule:
    head = [_decode_triple(n, graph) for n in _children(graph, node, _HEAD)]
    body = [_decode_body_element(n, graph) for n in _children(graph, node, _BODY)]
    evalground = _is_true(graph.value(node, _RULE_EVALGROUND_FLAG))
    return srl_ast._Rule(head=head, body=body, evalground=evalground, id=graph.value(node, _RULE_ID))


def _decode_data(node, graph) -> srl_ast._Data:
    return srl_ast._Data(triples=[_decode_triple(n, graph) for n in _children(graph, node, _TRIPLES)])


def tree_to_ruleset(graph: Any, root) -> srl_ast.RuleSet:
    """Decode the ``srl:RuleSet`` node ``root`` in ``graph`` (as returned by
    ``sparql_to_tree``/``ruleset_to_tree``, or an LLM-authored ``srl:`` graph
    not yet decoded) back into a real ``srl_ast.RuleSet``.

    Raises:
        FormatError: (kind ``"srl"``) A part of the tree is missing or is not what the rule set needs (a damaged or hand-edited tree).
        FormatError: (kind ``"rdf"``) The order of some children is not defined: two children of one parent and property with the same
            ``tree:ord``, or a child with a missing, repeated, negative or non-integer ordinal.
    """
    from .sqe._memtree import as_engine_graph

    graph, root = as_engine_graph(graph, root)
    try:
        rules = [_decode_rule(n, graph) for n in _children(graph, root, _RULES)]
        data = [_decode_data(n, graph) for n in _children(graph, root, _DATA)]
        imports = _children(graph, root, _IMPORTS)
    except FormatError as exc:
        if exc.kind == "term":  # a triple term the tree holds in a position it cannot have: a damaged tree
            raise _tree_error(f"srl: the tree cannot be read as a rule set: {exc}") from exc
        raise
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        # a damaged tree (a missing part, a triple term that is not one) is the one error
        # a caller reading hand-edited trees catches
        raise _tree_error(f"srl: the tree cannot be read as a rule set: {exc}") from exc
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
        namespace_manager: If given (a prefix -> namespace ``dict`` or a ``StarLayerGraph`` (its ``prefixes``)), render prefixed names instead of full
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
    raise ExecutionError(f"starlayer.sparql.srl: no text rendering for term {term!r}", kind="unsupported", context="srl: text rendering")


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
        ground = "" if element.evalground else "GROUND "
        return f"NOT {ground}{{ {inner} }}"
    if isinstance(element, srl_ast._GroupElement):
        keys = "BY " + " ".join(_term_text(k, prefixes) for k in element.keys) + " " if element.keys else ""
        inner = " ".join(_body_element_text(e, prefixes) for e in element.pattern)
        aggregations = ", ".join(_aggregation_text(a, prefixes) for a in element.aggregations)
        return f"GROUP {keys}{{ {inner} }} [ {aggregations} ]" if aggregations else f"GROUP {keys}{{ {inner} }} []"
    raise ExecutionError(f"starlayer.sparql.srl: no text rendering yet for body element {element!r}", kind="unsupported", context="srl: text rendering")


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
    ground = "" if rule.evalground else "GROUND "
    return f"RULE {rule_id}{{ {head} }} WHERE {ground}{{ {body} }}"


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
        ExecutionError: (kind ``"import"``) If the loader fails for an import.
        FormatError: (kind ``"srl"``) If the loader returns text that is not a valid rule set.
        ExecutionError: (kind ``"rule"``) If the rules of the combined rule set cannot be ordered.
    """
    return _resolve_imports(ruleset, loader, location=location, check=True)


def _resolve_imports(ruleset: srl_ast.RuleSet, loader, *, location: str | None, check: bool) -> srl_ast.RuleSet:
    """``resolve_imports``; ``check=False`` leaves the stratification of the combined rule set unchecked (``parse_ruleset`` does not check it)."""
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
                message = f"SRL: cannot read the import <{import_iri}>: {reason}"
                raise ExecutionError(message, kind="import", context=f"IMPORTS <{import_iri}>") from exc
            if isinstance(loaded, str):
                try:
                    loaded = parse_ruleset(loaded, base=_T.iri_text(import_iri))
                except FormatError as exc:
                    message = f"SRL: the import <{import_iri}> is not a valid rule set: {exc}"
                    raise FormatError(message, kind="srl", why=message, context=f"IMPORTS <{import_iri}>") from exc
            sub_rules, sub_data = _merge(loaded, renamed=True)
            rules += sub_rules
            data += sub_data
        return rules, data

    rules, data = _merge(ruleset, renamed=False)
    resolved = srl_ast.RuleSet(rules=rules, data=data, imports=[], prefixes=dict(ruleset.prefixes))
    if check:
        _check_stratification(resolved)  # now the whole rule set: an import can add a dependency the text alone does not have
    return resolved


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
    _merge_into(g, starontology.get_ontology_graph("tree_owl"))
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
    _merge_into(g, starontology.get_ontology_graph("tree_shacl"))
    _merge_into(g, starontology.get_ontology_graph("srl_shacl"))
    _merge_into(g, starontology.get_ontology_graph("sqe_shacl"))
    return g


_validation_graphs_cache: tuple[Any, Any, Any] | None = None
_validation_plans: dict = {}  # the parsed Plan of the cached shapes graph, kept across calls (see ``shacl._adapter.shared_plans``)


def _validation_graphs() -> tuple[Any, Any, Any]:
    """The ``(shapes, ontology, closed schema maps)`` ``validate_sparql_tree`` uses, built once and
    reused: validation does not modify them, and building them costs about 20 ms
    per call."""
    global _validation_graphs_cache
    if _validation_graphs_cache is None:
        from .expr_validation import rdfs_schema

        ontology = _ontology_graph()
        _validation_graphs_cache = (_shapes_graph(), ontology, rdfs_schema(ontology))
    return _validation_graphs_cache


# The shapes of ``srl_shapes.ttl`` that state the spec's §4.2 well-formedness conditions, one per condition. A result of one of
# these is a rule-set problem (the tree decodes and means what it says, but the rule set is not well-formed); a result of any
# other shape means the tree itself is malformed.
_WELL_FORMEDNESS_SHAPES = frozenset(
    SRL[name].value
    for name in (
        "TripleTermSubjectShape",
        "TripleTermPredicateShape",
        "VariableInDataShape",
        "AggregateInExpressionShape",
        "UnboundHeadVariableShape",
        "UnboundFilterVariableShape",
        "UnboundAssignmentExpressionVariableShape",
        "ReusedAssignmentVariableShape",
        "VariableInUseShape",
        "GroupKeyUnboundShape",
        "AggregationVariableInScopeShape",
        "DuplicateAggregationVariableShape",
        "UnboundAggregationArgumentShape",
        "UnsupportedVariableNameShape",
    )
)


def _validate_against_shapes(tree_graph: Any) -> ValidationReport:
    """The report of checking ``tree_graph`` against the ``srl:`` shapes (with ``spexpr:`` and ``sqe:``), the one place both
    ``validate_sparql_tree`` and a run (``_require_well_formed``) get the §4.2 results from. A ``sh:Warning`` result does not make it
    non-conforming."""
    from starlayer.shacl._adapter import (  # lazy: avoids a circular-import deadlock at module load time
        shared_plans,
        validate_bounded,
    )

    from .expr_validation import rdfs_entailed_copy
    from .sqe._memtree import as_engine_graph

    shapes, _ontology, schema = _validation_graphs()
    tree_graph, _ = as_engine_graph(tree_graph)
    with shared_plans(_validation_plans):
        return validate_bounded(
            rdfs_entailed_copy(tree_graph, schema),  # the RDFS closure the shapes rely on, done natively
            shapes,
            max_validation_depth=100,
            allow_warnings=True,
        )


def _results_of(report: ValidationReport) -> list[tuple[str | None, Any, str]]:
    """``(source shape IRI, focus node, message)`` of each ``sh:Violation`` result in ``report``."""
    from starlayer.shacl.engine.terms import SH

    graph = report.report_graph
    out = []
    for result in graph.subjects(SH.resultSeverity, SH.Violation):
        shape = next(iter(graph.objects(result, SH.sourceShape)), None)
        focus = next(iter(graph.objects(result, SH.focusNode)), None)
        message = next(iter(graph.objects(result, SH.resultMessage)), None)
        out.append((getattr(shape, "value", None), focus, getattr(message, "value", "")))
    return out


def validate_srl_tree(tree_graph: Any) -> ValidationReport:
    """Validate ``tree_graph`` (e.g. straight out of ``sparql_to_tree()``,
    or an LLM-authored ``srl:`` graph not yet decoded) against the ``srl:``
    shapes.

    Goes through ``starlayer.shacl.validate()``, never bare ``pyshacl`` -
    same rule every other shapes module in this stack follows, since a
    caller-supplied graph may carry genuine RDF 1.2 content (a triple term
    as a ``srl:subject``/``srl:object``) that only ``starlayer.shacl``
    understands correctly.

    The shapes cover the tree's structure and the spec's §4.2 well-formedness conditions (``srl_shapes.ttl``: a
    triple term as a subject or predicate, a variable in ``DATA``, an aggregate or ``EXISTS`` in an expression, a head, filter or
    assignment variable that is not bound, a ``SET`` or aggregation variable that is already bound or in use, a variable that
    is in use, a group key or aggregation argument that is not bound, a repeated aggregation variable, a variable name
    above U+FFFF). Each is an ``sh:Violation`` whose focus node is the offending element (a triple pattern, FILTER, SET, group
    or aggregation), so an editor can point at it. Running a rule set checks the same conditions in Python
    (``srl_semantic_checks``, a ``FormatError``): a SPARQL constraint per element costs too much to run on every ``infer()``
    (a 40-rule set takes about half a second), and ``test_srl_wellformedness_agreement.py`` keeps the two the same.

    Two things shapes cannot say are added when the structure conforms: that the rules can be ordered (§4.4, an
    ``ExecutionError`` of kind ``"rule"`` when running) is an ``sh:Violation`` with the ``srl:RuleSet`` node as its focus node; and an
    ``IMPORTS`` entry that is not resolved is an ``sh:Warning`` (``srl:UnresolvedImportsShape``, one result per import IRI, focus
    node the ``srl:RuleSet``), which does not make the report non-conforming: the ordering check covers only the rules in the
    document, and an imported rule can add a dependency that makes them unorderable. A tree that cannot be decoded is left to the
    shapes.

    Args:
        tree_graph: The ``srl:`` tree-RDF graph to validate.

    Returns:
        The ``ValidationReport`` ``starlayer.shacl.validate()`` gives, with the ordering findings added; it is not iterable, so
        read ``conforms``, ``report_text`` and the rest by name.
    """
    from .sqe._memtree import as_engine_graph

    engine_graph, _ = as_engine_graph(tree_graph)
    result = _validate_against_shapes(engine_graph)
    if any(shape not in _WELL_FORMEDNESS_SHAPES for shape, _focus, _message in _results_of(result)):
        return result  # the tree itself is malformed: it may not decode, so there is nothing to order
    problems = _ordering_problems(engine_graph)
    if not problems:
        return result
    from .sqe.shapes import _with_violations

    return _with_violations(result, problems)


def _ordering_problems(tree_graph: Any) -> list[tuple[Any, str]]:
    """``(srl:RuleSet node, message)`` for each rule set of a structurally sound tree whose rules cannot be ordered (§4.4)."""
    from .srl_eval import _stratify

    problems: list[tuple[Any, str]] = []
    for root in sorted(tree_graph.subjects(RDF.type, SRL.RuleSet), key=str):
        try:
            ruleset = tree_to_ruleset(tree_graph, root)
        except FormatError:
            continue
        try:
            _stratify(ruleset)
        except ExecutionError as error:
            only_kind(error, "rule")
            problems.append((root, str(error)))
    return problems


def __getattr__(name: str) -> Any:
    """``srl.Materialization``, the result of ``RuleSet.materialize()``; ``srl_eval`` imports this module, so it is reached lazily."""
    if name == "Materialization":
        from .srl_eval import Materialization

        return Materialization
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
