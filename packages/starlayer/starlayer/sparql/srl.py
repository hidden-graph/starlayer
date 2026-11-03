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
module could: ``_encode``/``_decode``/``_new_starlayer_graph`` (``to_rdf.py``/
``from_rdf.py``) are reused
directly below, not reimplemented - moving this module out of
``starlayer.sparql`` would mean forking that machinery. Staying here means
every cross-reference below is an ordinary same-package import, not a
cross-package one - no circular-import discipline needed, unlike
``starontology.manchester``'s deferred ``starlayer.graph`` imports.

Six entry points, forming two independent round trips (text<->tree-RDF,
text<->RuleSet) plus a third already covered by the first two composed
(tree-RDF<->RuleSet):

- ``srl_parse_to_tree(text, base=None) -> (Graph, root)`` - SRL text straight
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
- ``ruleset_to_tree(ruleset, graph=None) -> (Graph, root)`` - the inverse:
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
internally (an ``srl:expr``/``srl:assign`` expression tree is validated by
the *existing* ``salg:ExpressionShape``, not a separate ``srl:`` expression
vocabulary - so both the ``srl:`` and ``salg:`` ontology/shapes graphs are
needed together for RDFS reasoning to resolve that dispatch) - see
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

from rdflib import RDF, BNode, Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import NamespaceManager
from rdflib.plugins.sparql import algebra
from rdflib.plugins.sparql.parserutils import CompValue

from starlayer._ox_out import ox_out

from . import _srl_ast as srl_ast
from ._srl_ast import (  # noqa: F401 - re-exported, see module docstring
    PlanEdge,
    PlanRule,
    PlanStratum,
    RulePlan,
    RuleSet,
    TriplePattern,
)
from .spexpr_codec import _NS_OVERRIDES, _decode, _encode, _new_starlayer_graph
from .sqe.expr_text import expr_text as _sqe_expr_text
from .sqe.to_rdf import _encode_expr
from .sqe.vocab import SQE as _SQE
from .srl_semantic_checks import _check_ruleset
from .triple_term import TripleTermNode

SRL = Namespace("https://github.com/hidden-graph/starlayer/ns/sparql/srl#")

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

_TRIPLE_SUBJECT = SRL.subject
_TRIPLE_PREDICATE = SRL.predicate
_TRIPLE_OBJECT = SRL.object

_RULES = SRL.rules
_DATA = SRL.data
_IMPORTS = SRL.imports
_HEAD = SRL.head
_BODY = SRL.body
_INNER = SRL.inner
_TRIPLES = SRL.triples

# The spec reuses the name "evaldata" for two components (rule.evaldata and
# negation.evaldata), and "data" for a third (ruleset.data) - each gets its own
# predicate URI to avoid a same-URI-different-shape collision within one shared
# graph. The flag is the spec's own: true = match the evaluation graph (plain
# WHERE / NOT), false = match the base graph only (WHERE DATA / NOT DATA).
_RULE_EVALDATA_FLAG = SRL.ruleEvaldata
_RULE_ID = SRL.id
_EXPR = SRL.expr
_VAR = SRL.var
_NEGATION_EVALDATA_FLAG = SRL.negationEvaldata


def _merge_into(dst, src):
    """``dst += src`` for graphs of either kind (the ontology loaders return whatever class ``StarLayerGraph`` is)."""
    from starlayer.graph.oxgraph._rdflib_bridge import merge_into

    merge_into(dst, src)


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

    Two-pass, matching rdflib's own ``parseQuery``/``translateQuery`` split:
    parse raw (leaving prefixed names unresolved), build a real ``Prologue``
    from the parsed ``BASE``/``PREFIX`` decls and resolve every prefixed/
    relative name against it in one tree pass, then convert the resolved
    tree into real ``srl_ast`` dataclasses.

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
# RuleSet -> srl: tree-RDF. Every term/expression leaf
# delegates straight to to_rdf._encode - this only has bespoke logic for
# the srl:-specific container shapes.
# ---------------------------------------------------------------------------

def ruleset_to_tree(ruleset: srl_ast.RuleSet, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode ``ruleset`` as ``srl:`` tree-RDF.

    Useful on its own (not just inside ``srl_parse_to_tree``) for a ``RuleSet``
    built or edited programmatically - rules combined, a filter rewritten -
    that now needs to go back into RDF, e.g. for storage or SHACL
    validation, without round-tripping through text.

    Args:
        ruleset: The RuleSet to encode.
        graph: Graph to add the encoding to; a fresh graph is created if
            not given.

    Returns:
        A ``(graph, root)`` tuple, ``root`` the ``srl:RuleSet``-typed node.
    """
    if graph is not None:
        from starlayer.graph.oxgraph import _rdflib_bridge as _ox

        if _ox.is_oxigraph_input(graph):  # an OxGraph target: encode on rdflib terms, then add them to it
            return _ox.write_boundary(graph, lambda g: ruleset_to_tree(ruleset, g))
    if graph is None:
        graph = _new_starlayer_graph()
    root = BNode()
    graph.add((root, RDF.type, _RULE_SET))
    graph.add((root, _RULES, _rdf_list(graph, [_rule_to_rdf(r, graph) for r in ruleset.rules])))
    graph.add((root, _DATA, _rdf_list(graph, [_data_to_rdf(d, graph) for d in ruleset.data])))
    graph.add((root, _IMPORTS, _rdf_list(graph, list(ruleset.imports))))
    return graph, root


def _rdf_list(graph: Graph, items: list) -> BNode | URIRef:
    if not items:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, items)
    return list_node


def _encode_node(value, graph: Graph):
    """Encode one leaf of the tree: an expression, a triple term, or a plain term/flag.

    Expressions and triple terms are encoded exactly as ``sqe:`` encodes them (``sqe.to_rdf._encode_expr``):
    after ``simplifyFilters`` collapses rdflib's precedence chains to their minimal form, with triple terms
    typed ``sqe:TripleTerm`` and aggregates ``spexpr:``, so the tree contains no ``salg:`` term and validates
    against the ``spexpr:``/``sqe:`` shapes alone. Anything else (an IRI, variable, literal, blank node, a
    boolean flag) goes through the shared term encoder, with triple terms inside it typed the same way.
    """
    if isinstance(value, CompValue):
        return _encode_expr(algebra.simplifyFilters(value), graph)
    token = _NS_OVERRIDES.set({"TripleTerm": _SQE})
    try:
        return _encode(value, graph)
    finally:
        _NS_OVERRIDES.reset(token)


def _triple_to_rdf(triple: srl_ast.TriplePattern, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, _TRIPLE_PATTERN))
    graph.add((node, _TRIPLE_SUBJECT, _encode_node(triple.subject, graph)))
    graph.add((node, _TRIPLE_PREDICATE, _encode_node(triple.predicate, graph)))
    graph.add((node, _TRIPLE_OBJECT, _encode_node(triple.object, graph)))
    return node


def _body_element_to_rdf(element: srl_ast.BodyElement, graph: Graph) -> BNode:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_to_rdf(element, graph)
    if isinstance(element, srl_ast._FilterElement):
        node = BNode()
        graph.add((node, RDF.type, _FILTER_ELEMENT))
        graph.add((node, _EXPR, _encode_node(element.expr, graph)))
        return node
    if isinstance(element, srl_ast._AssignmentElement):
        node = BNode()
        graph.add((node, RDF.type, _ASSIGNMENT_ELEMENT))
        graph.add((node, _VAR, _encode_node(element.var, graph)))
        graph.add((node, _EXPR, _encode_node(element.expr, graph)))
        return node
    if isinstance(element, srl_ast._NegationElement):
        node = BNode()
        graph.add((node, RDF.type, _NEGATION_ELEMENT))
        inner_nodes = [_body_element_to_rdf(e, graph) for e in element.inner]
        graph.add((node, _INNER, _rdf_list(graph, inner_nodes)))
        graph.add((node, _NEGATION_EVALDATA_FLAG, _encode_node(element.evaldata, graph)))
        return node
    raise NotImplementedError(f"starlayer.sparql.srl: no encoding for body element {element!r}")  # pragma: no cover


def _rule_to_rdf(rule: srl_ast._Rule, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, _RULE))
    head_nodes = [_triple_to_rdf(t, graph) for t in rule.head]
    graph.add((node, _HEAD, _rdf_list(graph, head_nodes)))
    body_nodes = [_body_element_to_rdf(e, graph) for e in rule.body]
    graph.add((node, _BODY, _rdf_list(graph, body_nodes)))
    graph.add((node, _RULE_EVALDATA_FLAG, _encode_node(rule.evaldata, graph)))
    if rule.id is not None:
        graph.add((node, _RULE_ID, rule.id))
    return node


def _data_to_rdf(data: srl_ast._Data, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, _DATA_BLOCK))
    triple_nodes = [_triple_to_rdf(t, graph) for t in data.triples]
    graph.add((node, _TRIPLES, _rdf_list(graph, triple_nodes)))
    return node


# ---------------------------------------------------------------------------
# srl: tree-RDF -> RuleSet - the inverse, same
# "bespoke containers, delegate leaves" split.
# ---------------------------------------------------------------------------

class SRLDecodeError(SRLError):
    """Raised for an ``srl:`` graph shape ``tree_to_ruleset`` doesn't recognize."""


def _read_rdf_list(node, graph: Graph) -> list:
    if node == RDF.nil:
        return []
    return list(Collection(graph, node))


def _decode_triple(node, graph: Graph) -> srl_ast.TriplePattern:
    return srl_ast.TriplePattern(
        subject=_decode(graph.value(node, _TRIPLE_SUBJECT), graph),
        predicate=_decode(graph.value(node, _TRIPLE_PREDICATE), graph),
        object=_decode(graph.value(node, _TRIPLE_OBJECT), graph),
    )


def _node_type(node, graph: Graph):
    return graph.value(node, RDF.type)


def _decode_body_element(node, graph: Graph) -> srl_ast.BodyElement:
    t = _node_type(node, graph)
    if t == _TRIPLE_PATTERN:
        return _decode_triple(node, graph)
    if t == _FILTER_ELEMENT:
        return srl_ast._FilterElement(expr=_decode(graph.value(node, _EXPR), graph))
    if t == _ASSIGNMENT_ELEMENT:
        return srl_ast._AssignmentElement(
            var=_decode(graph.value(node, _VAR), graph),
            expr=_decode(graph.value(node, _EXPR), graph),
        )
    if t == _NEGATION_ELEMENT:
        inner = [_decode_body_element(n, graph) for n in _read_rdf_list(graph.value(node, _INNER), graph)]
        evaldata = bool(_decode(graph.value(node, _NEGATION_EVALDATA_FLAG), graph))
        return srl_ast._NegationElement(inner=inner, evaldata=evaldata)
    raise SRLDecodeError(f"unrecognized rule body element node {node!r} (rdf:type {t!r})")


def _decode_rule(node, graph: Graph) -> srl_ast._Rule:
    head = [_decode_triple(n, graph) for n in _read_rdf_list(graph.value(node, _HEAD), graph)]
    body = [_decode_body_element(n, graph) for n in _read_rdf_list(graph.value(node, _BODY), graph)]
    evaldata = bool(_decode(graph.value(node, _RULE_EVALDATA_FLAG), graph))
    rule_id = graph.value(node, _RULE_ID)
    return srl_ast._Rule(head=head, body=body, evaldata=evaldata, id=rule_id)


def _decode_data(node, graph: Graph) -> srl_ast._Data:
    triples = [_decode_triple(n, graph) for n in _read_rdf_list(graph.value(node, _TRIPLES), graph)]
    return srl_ast._Data(triples=triples)


def tree_to_ruleset(graph: Graph, root) -> srl_ast.RuleSet:
    """Decode the ``srl:RuleSet`` node ``root`` in ``graph`` (as returned by
    ``srl_parse_to_tree``/``ruleset_to_tree``, or an LLM-authored ``srl:`` graph
    not yet decoded) back into a real ``srl_ast.RuleSet``."""
    from starlayer.graph.oxgraph import _rdflib_bridge as _ox

    graph, root = _ox.read_boundary(graph, root)  # an OxGraph is read as a snapshot of rdflib terms
    rules = [_decode_rule(n, graph) for n in _read_rdf_list(graph.value(root, _RULES), graph)]
    data = [_decode_data(n, graph) for n in _read_rdf_list(graph.value(root, _DATA), graph)]
    imports = list(_read_rdf_list(graph.value(root, _IMPORTS), graph))
    return srl_ast.RuleSet(rules=rules, data=data, imports=imports)


# ---------------------------------------------------------------------------
# RuleSet -> SRL text - the inverse of parse_ruleset,
# working directly on the dataclass tree, no RDF involved.
# ---------------------------------------------------------------------------

def ruleset_to_text(ruleset: srl_ast.RuleSet, namespace_manager: NamespaceManager | None = None) -> str:
    """Render ``ruleset`` back into SRL text - ``IMPORTS``/``DATA`` blocks
    first, then each ``RULE``, in the order they appear on the dataclass
    tree.

    **No original ``PREFIX``/``BASE`` declarations are preserved** - like
    rdflib's own ``translateAlgebra``, the parsed syntax tree only ever
    holds fully-resolved absolute IRIs; prefix declarations are consumed
    during parsing and never stored.

    Args:
        ruleset: The RuleSet to render.
        namespace_manager: If given (an rdflib ``NamespaceManager``, a prefix -> namespace ``dict`` or an ``OxGraph``), render
            prefixed names instead of full
            ``<...>`` IRIs wherever a match exists - purely cosmetic, the
            resulting text still parses identically either way.

    Returns:
        The rendered SRL text.
    """
    namespace_manager = _namespace_manager_of(namespace_manager)
    lines = [f"IMPORTS {_term_text(iri_, namespace_manager)}" for iri_ in ruleset.imports]
    lines += [_data_text(block, namespace_manager) for block in ruleset.data]
    lines += [_rule_text(rule, namespace_manager) for rule in ruleset.rules]
    return "\n".join(lines)


def _namespace_manager_of(source):
    """``source`` as an rdflib ``NamespaceManager`` (or ``None``): a prefix -> namespace mapping, or an ``OxGraph`` (its
    ``prefixes``), is turned into one; a ``NamespaceManager`` passes through."""
    if source is None:
        return None
    from starlayer.graph.oxgraph._rdflib_bridge import is_oxigraph_input

    prefixes = getattr(source, "prefixes", None) if is_oxigraph_input(source) else source if isinstance(source, dict) else None
    if prefixes is None:
        return source
    from rdflib import Graph as _Graph

    graph = _Graph(bind_namespaces="none")
    for prefix, namespace in prefixes.items():
        graph.bind(prefix, str(namespace))
    return graph.namespace_manager


def _term_text(term, namespace_manager: NamespaceManager | None) -> str:
    from rdflib import BNode as _BNode
    from rdflib import Literal as _Literal
    from rdflib import URIRef as _URIRef
    from rdflib import Variable as _Variable

    if isinstance(term, _Variable):
        return "?" + str(term)
    if isinstance(term, (_URIRef, _BNode, _Literal)):
        return term.n3(namespace_manager) if namespace_manager is not None else term.n3()
    if isinstance(term, TripleTermNode):
        s, p, o = (_term_text(term.get(part), namespace_manager) for part in ("subject", "predicate", "object"))
        return f"<<( {s} {p} {o} )>>"
    raise NotImplementedError(f"starlayer.sparql.srl: no text rendering for term {term!r}")


def _triple_text(triple: srl_ast.TriplePattern, namespace_manager: NamespaceManager | None) -> str:
    subject = _term_text(triple.subject, namespace_manager)
    predicate = _term_text(triple.predicate, namespace_manager)
    obj = _term_text(triple.object, namespace_manager)
    return f"{subject} {predicate} {obj} ."


def _block_text(triples: list[srl_ast.TriplePattern], namespace_manager: NamespaceManager | None) -> str:
    return " ".join(_triple_text(t, namespace_manager) for t in triples)


def _expr_text(expr, namespace_manager: NamespaceManager | None) -> str:
    """An expression as SPARQL text, rendered by ``sqe:``'s renderer from the same tree the encoder builds.

    (The older route, rdflib's ``translateAlgebra`` placeholder renderer, printed ``{Function}``,
    ``{UnaryMinus}`` and ``{TripleTerm}`` for calls, unary operators and triple terms, and dropped the
    parentheses that make ``(?y + 1) * 2`` mean what it says.)
    """
    graph = Graph()
    node = _encode_expr(algebra.simplifyFilters(expr), graph)
    prefixes = {prefix: str(namespace) for prefix, namespace in namespace_manager.namespaces()} if namespace_manager is not None else {}
    return _sqe_expr_text(node, graph, prefixes)


def _body_element_text(element: srl_ast.BodyElement, namespace_manager: NamespaceManager | None) -> str:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_text(element, namespace_manager)
    if isinstance(element, srl_ast._FilterElement):
        return f"FILTER({_expr_text(element.expr, namespace_manager)})"
    if isinstance(element, srl_ast._AssignmentElement):
        var = _term_text(element.var, namespace_manager)
        return f"SET ({var} := {_expr_text(element.expr, namespace_manager)})"
    if isinstance(element, srl_ast._NegationElement):
        inner = " ".join(_body_element_text(e, namespace_manager) for e in element.inner)
        data = "" if element.evaldata else "DATA "
        return f"NOT {data}{{ {inner} }}"
    raise NotImplementedError(f"starlayer.sparql.srl: no text rendering yet for body element {element!r}")


def _data_text(data: srl_ast._Data, namespace_manager: NamespaceManager | None) -> str:
    return f"DATA {{ {_block_text(data.triples, namespace_manager)} }}"


def _rule_text(rule: srl_ast._Rule, namespace_manager: NamespaceManager | None) -> str:
    rule_id = f"{_term_text(rule.id, namespace_manager)} " if rule.id is not None else ""
    head = _block_text(rule.head, namespace_manager)
    body = " ".join(_body_element_text(e, namespace_manager) for e in rule.body)
    data = "" if rule.evaldata else "DATA "
    return f"RULE {rule_id}{{ {head} }} WHERE {data}{{ {body} }}"


# ---------------------------------------------------------------------------
# Composed text <-> tree-RDF convenience, matching starontology.manchester's
# srl_parse_to_tree()/srl_tree_to_text() naming.
# ---------------------------------------------------------------------------

def srl_parse_to_tree(text: str, base: str | None = None, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """SRL text straight to its ``srl:``-encoded tree-RDF. Composes
    ``parse_ruleset`` + ``ruleset_to_tree``. Returns ``(graph, root)``; ``graph`` (an ``OxGraph``, which gives pyoxigraph terms,
    or an rdflib graph) is where the tree is written, a fresh ``StarLayerGraph`` when omitted."""
    return ruleset_to_tree(parse_ruleset(text, base), graph)


def srl_tree_to_text(graph: Graph, root) -> str:
    """The inverse of ``srl_parse_to_tree``. Composes ``tree_to_ruleset`` +
    ``ruleset_to_text``."""
    return ruleset_to_text(tree_to_ruleset(graph, root))


# ---------------------------------------------------------------------------
# IMPORTS (§3.7, §4.5, Appendix B)
# ---------------------------------------------------------------------------


def _rename_blank_nodes(term, mapping: dict):
    if isinstance(term, BNode):
        return mapping.setdefault(term, BNode())
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
            if str(import_iri) in visited:
                continue
            visited.add(str(import_iri))
            try:
                loaded = loader(str(import_iri))
            except Exception as exc:
                reason = "not found" if isinstance(exc, KeyError) else f"{type(exc).__name__}: {exc}"
                raise SRLImportError(f"SRL: cannot read the import <{import_iri}>: {reason}") from exc
            if isinstance(loaded, str):
                try:
                    loaded = parse_ruleset(loaded, base=str(import_iri))
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

def _ontology_graph() -> Graph:
    """The ``srl:`` RDFS ontology, combined with the shared ``spexpr:`` expression ontology and ``sqe:``'s
    (which supplies ``sqe:TripleTerm``) - private: see module docstring for why this isn't exposed publicly.

    All three must be loaded together: this module's own SHACL shapes use ``sh:class spexpr:Expression`` and
    ``spexpr:Variable``, and the RDFS subclass entailment those checks depend on only resolves correctly when
    the ontologies are in the same graph. Nothing here comes from ``salg:``: SRL is published with ``spexpr:``
    and ``sqe:``, not with the algebra-tree encoding.

    Returns:
        A fresh combined ontology graph.
    """
    from starlayer import starontology

    from .expr_validation import ontology_graph as spexpr_ontology_graph

    g = spexpr_ontology_graph()
    _merge_into(g, starontology.get_ontology_graph("srl_owl"))
    _merge_into(g, starontology.get_ontology_graph("sqe_owl"))
    return g


def _shapes_graph() -> Graph:
    """A fresh graph of the ``srl:`` shapes, combined with the shared ``spexpr:`` expression shapes and
    ``sqe:``'s (the triple-term shapes) - private, same reasoning as ``_ontology_graph()`` above. No ``salg:``."""
    from starlayer import starontology

    from .expr_validation import shapes_graph as spexpr_shapes_graph

    g = spexpr_shapes_graph()
    _merge_into(g, starontology.get_ontology_graph("srl_shacl"))
    _merge_into(g, starontology.get_ontology_graph("sqe_shacl"))
    return g


_validation_graphs_cache: tuple[Graph, Graph] | None = None


def _validation_graphs() -> tuple[Graph, Graph]:
    """The ``(shapes, ontology)`` graphs ``srl_validate`` uses, built once and
    reused: validation does not modify them, and building them costs about 20 ms
    per call."""
    global _validation_graphs_cache
    if _validation_graphs_cache is None:
        _validation_graphs_cache = (_shapes_graph(), _ontology_graph())
    return _validation_graphs_cache


def _check_against_shapes(ruleset: srl_ast.RuleSet) -> None:
    """Raise ``SRLParseError`` if ``ruleset``'s RDF encoding does not conform to
    the ``srl:`` shapes."""
    graph, _root = ruleset_to_tree(ruleset)
    conforms, report_graph, report_text = srl_validate(graph)
    if conforms:
        return
    shacl_message = Namespace("http://www.w3.org/ns/shacl#").resultMessage
    messages = sorted({str(m) for m in report_graph.objects(None, shacl_message)})
    detail = "; ".join(messages) if messages else report_text.strip().splitlines()[0]
    raise SRLParseError(f"SRL: rule set does not conform to the srl: shapes: {detail}")


@ox_out("data_graph")
def srl_validate(data_graph: Graph) -> tuple[bool, Graph, str]:
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
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT

    result = starlayer.shacl.validate(
        data_graph,
        shacl_graph=_validation_graphs()[0],
        ont_graph=_validation_graphs()[1],
        inference=ENTAILMENT.RDFS,
        invalid_terms="lenient",  # query / ontology trees hold relative IRIs: opaque terms to the shapes
        advanced=True,
        max_validation_depth=100,
    )
    return result.conforms, result.report_graph, result.report_text
