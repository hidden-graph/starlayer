"""starlayer.sparql.srl

SRL/SPARQL-RL (`WD-sparql12-rl-20260919 <https://www.w3.org/TR/sparql12-rl/>`_)
- a Datalog-style rules language built on SPARQL triple patterns and filter
expressions - text, its tree-RDF encoding (``srl:``), and SHACL validation
of that encoding. Consolidated (2026-10-03) from six previously-separate
sibling files (``srl_grammar.py``, ``srl_vocab.py``, ``srl_to_rdf.py``,
``srl_from_rdf.py``, ``srl_to_text.py``, and the shapes-loading half of
``srl_shapes.py``), mirroring ``starontology.manchester``'s consolidation of
the equivalent Manchester-syntax pieces - see that module's own docstring
for the general pattern this follows.

**Where this sits, and why it's not in ``starontology`` like ``manch:``
is**: SRL rule sets aren't documents describing a vocabulary (what
Manchester's tree edits) - they're inference rules built directly out of
SPARQL triple patterns/filter expressions, run *against* a graph. That's a
SPARQL-adjacent artifact, and it can't cleanly separate from
``starlayer.sparql``'s shared internals the way Manchester's AST module
could: ``_encode``/``_decode``/``_new_starlayer_graph`` (``to_rdf.py``/
``from_rdf.py``) and ``render_expr_text`` (``ssyn_to_text.py``) are reused
directly below, not reimplemented - moving this module out of
``starlayer.sparql`` would mean forking that machinery. Staying here means
every cross-reference below is an ordinary same-package import, not a
cross-package one - no circular-import discipline needed, unlike
``starontology.manchester``'s deferred ``starlayer.graph`` imports.

Six entry points, forming two independent round trips (text<->tree-RDF,
text<->RuleSet) plus a third already covered by the first two composed
(tree-RDF<->RuleSet):

- ``parse_to_tree(text, base=None) -> (Graph, root)`` - SRL text straight
  to its ``srl:``-encoded tree-RDF. Composes ``parse_ruleset`` +
  ``ruleset_to_tree``.
- ``tree_to_text(graph, root) -> str`` - the inverse. Composes
  ``tree_to_ruleset`` + ``ruleset_to_text``.
- ``parse_ruleset(text, base=None) -> RuleSet`` - SRL text straight to a
  real ``srl_ast.RuleSet`` object, skipping RDF entirely. Kept as its own
  entry point (not just an implementation detail of ``parse_to_tree``)
  because ``RuleSet`` is independently useful - ``srl_eval.srl_infer``/
  ``srl_query`` consume it directly, with no RDF involved at all. This is
  the one real asymmetry with Manchester: ``manch:``'s ``Document`` object
  never existed before its own AST-as-RDF module invented it purely as a
  decode artifact; SRL's ``RuleSet`` already existed independently.
- ``ruleset_to_text(ruleset, namespace_manager=None) -> str`` - the
  inverse of ``parse_ruleset``, working on the AST directly.
- ``tree_to_ruleset(graph, root) -> RuleSet`` - decode ``srl:``-encoded
  tree-RDF into a real ``RuleSet``, e.g. after programmatically editing the
  RDF via plain graph surgery.
- ``ruleset_to_tree(ruleset, graph=None) -> (Graph, root)`` - the inverse:
  encode a ``RuleSet`` (e.g. one built or edited programmatically - rules
  combined, a filter rewritten) back to ``srl:`` tree-RDF.

Plus ``validate(data_graph) -> (conforms, report_graph, report_text)`` -
structural SHACL validation of an ``srl:`` tree-RDF graph. Deliberately
**no** public ``ontology_graph()``/``shapes_graph()`` here (same decision
``starontology.manchester`` makes for ``manch:``) - callers who want the
raw ``srl:`` ontology/shapes graphs themselves can already get them from
the registry: ``starontology.get_ontology_graph("srl_owl")`` /
``get_ontology_graph("srl_shacl")`` for the graph directly, or
``starlayer.registry.get_ontology("srl_owl")`` /
``get_ontology("srl_shacl")`` then ``.graph()`` for the same graph plus
registry metadata (``.description``/``.namespace``/``.kind``) and a
bundled ``.validate()``.
Exposing a third path to the exact same two graphs here would just be
another way to do what these two already do. ``validate()`` still needs
its own private, combined copy
internally (an ``srl:expr``/``srl:assign`` expression tree is validated by
the *existing* ``salg:ExpressionShape``, not a separate ``srl:`` expression
vocabulary - so both the ``srl:`` and ``salg:`` ontology/shapes graphs are
needed together for RDFS reasoning to resolve that dispatch) - see
``_ontology_graph()``/``_shapes_graph()`` below.

Deliberately outside this module's scope, unchanged, living in their own
sibling files:

- ``srl_ast.py`` - the ``RuleSet``/``Rule``/``Data``/... dataclasses
  themselves. Stays separate (not folded in here) because it's already a
  clean, independently-useful module consumed by ``srl_eval.py``/
  ``srl_semantic_checks.py`` too, neither of which needs anything else
  this module provides.
- ``srl_eval.py`` (``srl_infer``/``srl_query``) - *running* a ``RuleSet``
  against a base graph is a separate concern from the tree pipeline above,
  not a missing or oddly-shaped seventh step: unlike Manchester's
  `tree_to_owl()` (a pure function of the tree alone, translating between
  two independently-meaningful RDF forms), SRL has only one RDF form
  (`srl:`) - decoding already produces the runnable `RuleSet`, and running
  it inherently needs a second input (the base graph) that has nothing to
  do with this module's own encode/decode/validate concerns.
- ``srl_semantic_checks.py`` - cross-referential well-formedness checks
  (an unbound head/filter/assignment variable, a ``SET(...)`` reusing an
  already-bound variable) - deliberately kept out of SHACL (see
  ``validate()``'s own docstring for why structural-only is the line), so
  this is a separate, plain-Python check, not part of this module.
"""

from __future__ import annotations

import warnings
from functools import partial

from pyparsing import CaselessKeyword as Keyword
from pyparsing import Literal as _PPLiteral
from pyparsing import Optional, Suppress, ZeroOrMore
from rdflib import RDF, BNode, Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import NamespaceManager
from rdflib.plugins.sparql import algebra
from rdflib.plugins.sparql.parser import (
    A,
    BaseDecl,
    Constraint,
    Expression,
    GraphTerm,
    PrefixDecl,
    String,
    Var,
    VarOrIri,
    VarOrTerm,
    iri,
)
from rdflib.plugins.sparql.parserutils import Comp, CompValue, Param
from rdflib.plugins.sparql.pyparsing_compat import rest_of_line
from rdflib.plugins.sparql.sparql import Prologue

from . import srl_ast
from .from_rdf import _decode
from .ssyn_to_text import render_expr_text
from .to_rdf import _encode, _new_starlayer_graph

SRL = Namespace("https://github.com/hidden-graph/starsparql/ns/srl#")

# ---------------------------------------------------------------------------
# srl: vocabulary (was srl_vocab.py) - field names taken verbatim from the
# spec's own §4.1 "Component Notation" table, not invented.
# ---------------------------------------------------------------------------

RULE_SET = SRL.RuleSet
RULE = SRL.Rule
DATA_BLOCK = SRL.Data
TRIPLE_PATTERN = SRL.TriplePattern
FILTER_ELEMENT = SRL.FilterElement
NEGATION_ELEMENT = SRL.NegationElement
ASSIGNMENT_ELEMENT = SRL.AssignmentElement

TRIPLE_SUBJECT = SRL.subject
TRIPLE_PREDICATE = SRL.predicate
TRIPLE_OBJECT = SRL.object

RULES = SRL.rules
DATA = SRL.data
IMPORTS = SRL.imports
HEAD = SRL.head
BODY = SRL.body
INNER = SRL.inner
TRIPLES = SRL.triples

# The spec reuses the bare name "data" for three different components
# (rule.data/ruleset.data/negation.data) - each gets its own predicate URI
# to avoid a same-URI-different-shape collision within one shared graph.
RULE_DATA_FLAG = SRL.ruleData
RULE_ID = SRL.id
EXPR = SRL.expr
VAR = SRL.var
NEGATION_DATA_FLAG = SRL.negationData


# ---------------------------------------------------------------------------
# Grammar (was srl_grammar.py) - reuses rdflib's own real SPARQL 1.2 grammar
# productions directly for everything the spec's own grammar text says is
# unchanged from SPARQL; only the genuinely new SRL-specific productions are
# hand-written here. See the removed module's own docstring (preserved in
# git history) for the full production-by-production design notes - kept
# brief here since this is now one module among several, not the whole
# story for SRL.
#
# Deliberate scope reduction for this first implementation pass: only
# `;`-chained same-subject property lists are supported (no `,`-chained
# object lists); no property paths beyond a bare IRI predicate; no
# reified-triple/triple-term syntax in pattern/template/data position yet
# (srl_ast.Term already types this in for a follow-up grammar widening).
# ---------------------------------------------------------------------------

VersionDecl = Comp("VersionDecl", Keyword("VERSION") + Param("version", String))
ImportsDecl = Comp("ImportsDecl", Keyword("IMPORTS") + Param("iri", iri))
_Prologue1Decl = BaseDecl | PrefixDecl | VersionDecl | ImportsDecl

_Period = Suppress(_PPLiteral("."))
_BoolFlag = lambda keyword: Optional(Keyword(keyword)).set_parse_action(lambda t: bool(t))  # noqa: E731


def _property_list(term=VarOrTerm, predicate=VarOrIri):
    pair = Comp("PredObj", Param("predicate", predicate) + Param("object", term))
    return Comp(
        "SameSubject",
        Param("subject", term)
        + Param("verbs", pair, isList=True)
        + ZeroOrMore(Suppress(";") + Param("verbs", pair, isList=True)),
    )


# Ground-only triples (Data block) - predicate is a bare `iri`, never a Var.
_SameSubjectData = _property_list(term=GraphTerm, predicate=iri)
# Ordinary pattern/template-position triples.
_SameSubjectPattern = _property_list(term=VarOrTerm, predicate=A | VarOrIri)


def _expand_same_subject(cv: CompValue) -> list[srl_ast.TriplePattern]:
    subject = cv["subject"]
    return [
        srl_ast.TriplePattern(subject=subject, predicate=pair["predicate"], object=pair["object"])
        for pair in _list_field(cv, "verbs")
    ]


_DataTriplesBlock = ZeroOrMore(Param("subjects", _SameSubjectData, isList=True) + Optional(_Period))
_SRLData = Comp("Data", Keyword("DATA") + Suppress("{") + _DataTriplesBlock + Suppress("}"))

_HeadTemplateBlock = ZeroOrMore(Param("subjects", _SameSubjectPattern, isList=True) + Optional(_Period))
HeadTemplate = Comp("HeadTemplate", Suppress("{") + _HeadTemplateBlock + Suppress("}"))

Filter = Comp("Filter", Keyword("FILTER") + Param("expr", Constraint))

Assignment = Comp(
    "Assignment",
    Keyword("SET") + Suppress("(") + Param("var", Var) + Suppress(":=") + Param("expr", Expression) + Suppress(")"),
)

# Negation bodies are grammatically restricted to triple patterns + filters
# only (no nested negation/assignment) - enforced structurally: this
# alternation has no Negation/Assignment branch.
_NegationBodyItem = (Param("inner", _SameSubjectPattern, isList=True) + Optional(_Period)) | (
    Param("inner", Filter, isList=True) + Optional(_Period)
)
Negation = Comp(
    "Negation",
    Keyword("NOT") + Param("data", _BoolFlag("DATA")) + Suppress("{") + ZeroOrMore(_NegationBodyItem) + Suppress("}"),
)

_BodyItem = (Param("body", _SameSubjectPattern, isList=True) + Optional(_Period)) | (
    Param("body", Filter | Negation | Assignment, isList=True) + Optional(_Period)
)
BodyPattern = Comp("BodyPattern", Suppress("{") + ZeroOrMore(_BodyItem) + Suppress("}"))

_SRLRule = Comp(
    "Rule",
    Keyword("RULE")
    + Optional(Param("id", iri))
    + Param("head", HeadTemplate)
    + Keyword("WHERE")
    + Param("data", _BoolFlag("DATA"))
    + Param("body", BodyPattern),
)

# RuleSet ::= RuleOrDataBlock - simplified (documented, behaviourally
# equivalent for well-formed input): prologue declarations and Rule/Data
# items are matched in one flat ZeroOrMore regardless of interleaving, then
# bucketed by kind, since Prologue accumulation is order-independent the
# same way rdflib's own translatePrologue already is.
_RuleOrData = _SRLRule | _SRLData
RuleSetGrammar = Comp(
    "RuleSet",
    ZeroOrMore(Param("prologue", _Prologue1Decl, isList=True) | Param("body", _RuleOrData, isList=True)),
)
RuleSetGrammar.ignore("#" + rest_of_line)


class SRLParseError(ValueError):
    """Raised by :func:`parse_ruleset` for malformed SRL text."""


def _list_field(cv: CompValue, key: str) -> list:
    """``CompValue.get(key, default)``'s second positional parameter is
    *not* a default value - it's ``variables`` - so ``cv.get(key, [])``
    silently does something else entirely; worse, an absent key falls back
    to returning ``key`` itself (rdflib's own ``OrderedDict.get`` "hack"),
    not ``None``/``[]``. A ``Param(..., isList=True)`` field is only ever
    set at all if at least one occurrence matched, so an absent key
    genuinely means "zero occurrences" - this is the correct way to read
    that as ``[]``."""
    return list(cv[key]) if key in cv else []


def _opt_field(cv: CompValue, key: str):
    """See :func:`_list_field` for why ``cv.get(key)`` is unsafe here too."""
    return cv[key] if key in cv else None


def _resolve_pnames(tree, prologue: Prologue):
    return algebra.traverse(tree, visitPost=partial(algebra.translatePName, prologue=prologue))


def _build_prologue(decls: list[CompValue]) -> Prologue:
    from rdflib.plugins.sparql.algebra import translatePrologue

    return translatePrologue(decls, base=None)


def _build_negation_inner(items: list) -> list[srl_ast.NegationBodyElement]:
    out: list[srl_ast.NegationBodyElement] = []
    for item in items:
        if item.name == "SameSubject":
            out.extend(_expand_same_subject(item))
        elif item.name == "Filter":
            out.append(srl_ast.FilterElement(expr=item["expr"]))
        else:  # pragma: no cover - grammar structurally forbids anything else
            raise SRLParseError(f"illegal negation body element: {item!r}")
    return out


def _build_body_elements(items: list) -> list[srl_ast.BodyElement]:
    out: list[srl_ast.BodyElement] = []
    for cv in items:
        if cv.name == "SameSubject":
            out.extend(_expand_same_subject(cv))
        elif cv.name == "Filter":
            out.append(srl_ast.FilterElement(expr=cv["expr"]))
        elif cv.name == "Assignment":
            out.append(srl_ast.AssignmentElement(var=cv["var"], expr=cv["expr"]))
        elif cv.name == "Negation":
            out.append(srl_ast.NegationElement(inner=_build_negation_inner(_list_field(cv, "inner")), data=bool(cv["data"])))
        else:
            raise SRLParseError(f"unknown rule body element: {cv!r}")  # pragma: no cover
    return out


def _build_rule(cv: CompValue) -> srl_ast.Rule:
    head = [t for grp in _list_field(cv["head"], "subjects") for t in _expand_same_subject(grp)]
    body = _build_body_elements(_list_field(cv["body"], "body"))
    rule_id = _opt_field(cv, "id")
    return srl_ast.Rule(
        head=head,
        body=body,
        data=bool(cv["data"]),
        id=URIRef(rule_id) if rule_id is not None else None,
    )


def _build_data(cv: CompValue) -> srl_ast.Data:
    return srl_ast.Data(triples=[t for grp in _list_field(cv, "subjects") for t in _expand_same_subject(grp)])


def _build_ruleset(cv: CompValue) -> srl_ast.RuleSet:
    imports: list[URIRef] = []
    for decl in _list_field(cv, "prologue"):
        if decl.name == "ImportsDecl":
            imports.append(URIRef(decl["iri"]))
        # BaseDecl/PrefixDecl were already consumed to build the Prologue
        # used for name resolution before this function ran; VersionDecl
        # is informative only.

    rules: list[srl_ast.Rule] = []
    data_blocks: list[srl_ast.Data] = []
    for item in _list_field(cv, "body"):
        if item.name == "Rule":
            rules.append(_build_rule(item))
        elif item.name == "Data":
            data_blocks.append(_build_data(item))
        else:  # pragma: no cover
            raise SRLParseError(f"unknown top-level rule set item: {item!r}")

    return srl_ast.RuleSet(rules=rules, data=data_blocks, imports=imports)


def parse_ruleset(text: str, base: str | None = None) -> srl_ast.RuleSet:
    """Parse SRL rule-set text into a real ``srl_ast.RuleSet``, with no RDF
    involved at all.

    Two-pass, matching rdflib's own ``parseQuery``/``translateQuery`` split:
    parse raw (leaving prefixed names unresolved), build a real ``Prologue``
    from the parsed ``BASE``/``PREFIX`` decls and resolve every prefixed/
    relative name against it in one tree pass, then convert the resolved
    tree into real ``srl_ast`` dataclasses.
    """
    try:
        parsed = RuleSetGrammar.parse_string(text, parse_all=True)
    except Exception as exc:  # pyparsing.ParseException et al.
        raise SRLParseError(str(exc)) from exc

    root: CompValue = parsed[0]
    prologue = _build_prologue(_list_field(root, "prologue"))
    if base:
        prologue.base = base
    resolved = _resolve_pnames(root, prologue)
    return _build_ruleset(resolved)


# ---------------------------------------------------------------------------
# RuleSet -> srl: tree-RDF (was srl_to_rdf.py). Every term/expression leaf
# delegates straight to to_rdf._encode - this only has bespoke logic for
# the srl:-specific container shapes.
# ---------------------------------------------------------------------------

def ruleset_to_tree(ruleset: srl_ast.RuleSet, graph: Graph | None = None) -> tuple[Graph, BNode]:
    """Encode a ``RuleSet`` as ``srl:`` tree-RDF. Returns ``(graph, root)``,
    ``root`` the ``srl:RuleSet``-typed node.

    Useful on its own (not just inside ``parse_to_tree``) for a ``RuleSet``
    built or edited programmatically - rules combined, a filter rewritten -
    that now needs to go back into RDF, e.g. for storage or SHACL
    validation, without round-tripping through text.
    """
    if graph is None:
        graph = _new_starlayer_graph()
    root = BNode()
    graph.add((root, RDF.type, RULE_SET))
    graph.add((root, RULES, _rdf_list(graph, [_rule_to_rdf(r, graph) for r in ruleset.rules])))
    graph.add((root, DATA, _rdf_list(graph, [_data_to_rdf(d, graph) for d in ruleset.data])))
    graph.add((root, IMPORTS, _rdf_list(graph, list(ruleset.imports))))
    return graph, root


def _rdf_list(graph: Graph, items: list) -> BNode | URIRef:
    if not items:
        return RDF.nil
    list_node = BNode()
    Collection(graph, list_node, items)
    return list_node


def _triple_to_rdf(triple: srl_ast.TriplePattern, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, TRIPLE_PATTERN))
    graph.add((node, TRIPLE_SUBJECT, _encode(triple.subject, graph)))
    graph.add((node, TRIPLE_PREDICATE, _encode(triple.predicate, graph)))
    graph.add((node, TRIPLE_OBJECT, _encode(triple.object, graph)))
    return node


def _body_element_to_rdf(element: srl_ast.BodyElement, graph: Graph) -> BNode:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_to_rdf(element, graph)
    if isinstance(element, srl_ast.FilterElement):
        node = BNode()
        graph.add((node, RDF.type, FILTER_ELEMENT))
        graph.add((node, EXPR, _encode(element.expr, graph)))
        return node
    if isinstance(element, srl_ast.AssignmentElement):
        node = BNode()
        graph.add((node, RDF.type, ASSIGNMENT_ELEMENT))
        graph.add((node, VAR, _encode(element.var, graph)))
        graph.add((node, EXPR, _encode(element.expr, graph)))
        return node
    if isinstance(element, srl_ast.NegationElement):
        node = BNode()
        graph.add((node, RDF.type, NEGATION_ELEMENT))
        inner_nodes = [_body_element_to_rdf(e, graph) for e in element.inner]
        graph.add((node, INNER, _rdf_list(graph, inner_nodes)))
        graph.add((node, NEGATION_DATA_FLAG, _encode(element.data, graph)))
        return node
    raise NotImplementedError(f"starlayer.sparql.srl: no encoding for body element {element!r}")  # pragma: no cover


def _rule_to_rdf(rule: srl_ast.Rule, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, RULE))
    head_nodes = [_triple_to_rdf(t, graph) for t in rule.head]
    graph.add((node, HEAD, _rdf_list(graph, head_nodes)))
    body_nodes = [_body_element_to_rdf(e, graph) for e in rule.body]
    graph.add((node, BODY, _rdf_list(graph, body_nodes)))
    graph.add((node, RULE_DATA_FLAG, _encode(rule.data, graph)))
    if rule.id is not None:
        graph.add((node, RULE_ID, rule.id))
    return node


def _data_to_rdf(data: srl_ast.Data, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, DATA_BLOCK))
    triple_nodes = [_triple_to_rdf(t, graph) for t in data.triples]
    graph.add((node, TRIPLES, _rdf_list(graph, triple_nodes)))
    return node


# ---------------------------------------------------------------------------
# srl: tree-RDF -> RuleSet (was srl_from_rdf.py) - the inverse, same
# "bespoke containers, delegate leaves" split.
# ---------------------------------------------------------------------------

class SRLDecodeError(ValueError):
    """Raised for an ``srl:`` graph shape ``tree_to_ruleset`` doesn't recognize."""


def _read_rdf_list(node, graph: Graph) -> list:
    if node == RDF.nil:
        return []
    return list(Collection(graph, node))


def _decode_triple(node, graph: Graph) -> srl_ast.TriplePattern:
    return srl_ast.TriplePattern(
        subject=_decode(graph.value(node, TRIPLE_SUBJECT), graph),
        predicate=_decode(graph.value(node, TRIPLE_PREDICATE), graph),
        object=_decode(graph.value(node, TRIPLE_OBJECT), graph),
    )


def _node_type(node, graph: Graph):
    return graph.value(node, RDF.type)


def _decode_body_element(node, graph: Graph) -> srl_ast.BodyElement:
    t = _node_type(node, graph)
    if t == TRIPLE_PATTERN:
        return _decode_triple(node, graph)
    if t == FILTER_ELEMENT:
        return srl_ast.FilterElement(expr=_decode(graph.value(node, EXPR), graph))
    if t == ASSIGNMENT_ELEMENT:
        return srl_ast.AssignmentElement(
            var=_decode(graph.value(node, VAR), graph),
            expr=_decode(graph.value(node, EXPR), graph),
        )
    if t == NEGATION_ELEMENT:
        inner = [_decode_body_element(n, graph) for n in _read_rdf_list(graph.value(node, INNER), graph)]
        data_flag = bool(_decode(graph.value(node, NEGATION_DATA_FLAG), graph))
        return srl_ast.NegationElement(inner=inner, data=data_flag)
    raise SRLDecodeError(f"unrecognized rule body element node {node!r} (rdf:type {t!r})")


def _decode_rule(node, graph: Graph) -> srl_ast.Rule:
    head = [_decode_triple(n, graph) for n in _read_rdf_list(graph.value(node, HEAD), graph)]
    body = [_decode_body_element(n, graph) for n in _read_rdf_list(graph.value(node, BODY), graph)]
    data_flag = bool(_decode(graph.value(node, RULE_DATA_FLAG), graph))
    rule_id = graph.value(node, RULE_ID)
    return srl_ast.Rule(head=head, body=body, data=data_flag, id=rule_id)


def _decode_data(node, graph: Graph) -> srl_ast.Data:
    triples = [_decode_triple(n, graph) for n in _read_rdf_list(graph.value(node, TRIPLES), graph)]
    return srl_ast.Data(triples=triples)


def tree_to_ruleset(graph: Graph, root) -> srl_ast.RuleSet:
    """Decode the ``srl:RuleSet`` node ``root`` in ``graph`` (as returned by
    ``parse_to_tree``/``ruleset_to_tree``, or an LLM-authored ``srl:`` graph
    not yet decoded) back into a real ``srl_ast.RuleSet``."""
    rules = [_decode_rule(n, graph) for n in _read_rdf_list(graph.value(root, RULES), graph)]
    data = [_decode_data(n, graph) for n in _read_rdf_list(graph.value(root, DATA), graph)]
    imports = list(_read_rdf_list(graph.value(root, IMPORTS), graph))
    return srl_ast.RuleSet(rules=rules, data=data, imports=imports)


# ---------------------------------------------------------------------------
# RuleSet -> SRL text (was srl_to_text.py) - the inverse of parse_ruleset,
# working directly on the dataclass tree, no RDF involved.
# ---------------------------------------------------------------------------

def ruleset_to_text(ruleset: srl_ast.RuleSet, namespace_manager: NamespaceManager | None = None) -> str:
    """Render ``ruleset`` back into SRL text - ``IMPORTS``/``DATA`` blocks
    first, then each ``RULE``, in the order they appear on the dataclass
    tree.

    **No original ``PREFIX``/``BASE`` declarations are preserved** - like
    rdflib's own ``translateAlgebra``, the parsed AST only ever holds
    fully-resolved absolute IRIs; prefix declarations are consumed during
    parsing and never stored. Pass a ``namespace_manager`` (e.g. some
    graph's own) to render prefixed names instead of full ``<...>`` IRIs
    wherever a match exists - purely cosmetic, the resulting text still
    parses identically either way.
    """
    lines = [f"IMPORTS {_term_text(iri_, namespace_manager)}" for iri_ in ruleset.imports]
    lines += [_data_text(block, namespace_manager) for block in ruleset.data]
    lines += [_rule_text(rule, namespace_manager) for rule in ruleset.rules]
    return "\n".join(lines)


def _term_text(term, namespace_manager: NamespaceManager | None) -> str:
    from rdflib import BNode as _BNode
    from rdflib import Literal as _Literal
    from rdflib import URIRef as _URIRef
    from rdflib import Variable as _Variable

    if isinstance(term, _Variable):
        return "?" + str(term)
    if isinstance(term, (_URIRef, _BNode, _Literal)):
        return term.n3(namespace_manager) if namespace_manager is not None else term.n3()
    raise NotImplementedError(
        f"starlayer.sparql.srl: no text rendering yet for term {term!r} - triple terms "
        "in pattern/template/data position aren't produced by the parser yet either, "
        "see this module's own documented scope reduction"
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
    raise NotImplementedError(f"starlayer.sparql.srl: no text rendering yet for body element {element!r}")


def _data_text(data: srl_ast.Data, namespace_manager: NamespaceManager | None) -> str:
    return f"DATA {{ {_block_text(data.triples, namespace_manager)} }}"


def _rule_text(rule: srl_ast.Rule, namespace_manager: NamespaceManager | None) -> str:
    rule_id = f"{_term_text(rule.id, namespace_manager)} " if rule.id is not None else ""
    head = _block_text(rule.head, namespace_manager)
    body = " ".join(_body_element_text(e, namespace_manager) for e in rule.body)
    data = "DATA " if rule.data else ""
    return f"RULE {rule_id}{{ {head} }} WHERE {data}{{ {body} }}"


# ---------------------------------------------------------------------------
# Composed text <-> tree-RDF convenience, matching starontology.manchester's
# parse_to_tree()/tree_to_text() naming.
# ---------------------------------------------------------------------------

def parse_to_tree(text: str, base: str | None = None) -> tuple[Graph, BNode]:
    """SRL text straight to its ``srl:``-encoded tree-RDF. Composes
    ``parse_ruleset`` + ``ruleset_to_tree``. Returns ``(graph, root)``."""
    return ruleset_to_tree(parse_ruleset(text, base))


def tree_to_text(graph: Graph, root) -> str:
    """The inverse of ``parse_to_tree``. Composes ``tree_to_ruleset`` +
    ``ruleset_to_text``."""
    return ruleset_to_text(tree_to_ruleset(graph, root))


# ---------------------------------------------------------------------------
# SHACL validation of an srl: tree-RDF graph (was the validate half of
# srl_shapes.py - ontology_graph()/shapes_graph() deliberately not exposed
# publicly here, see module docstring for why).
# ---------------------------------------------------------------------------

def _ontology_graph() -> Graph:
    """The ``srl:`` RDFS ontology, combined with ``salg:``'s (needed for
    the ``sh:class salg:Expression``/``salg:Variable`` checks below) -
    private: see module docstring for why this isn't exposed publicly."""
    import starontology

    g = starontology.get_ontology_graph("srl_owl")
    g += starontology.get_ontology_graph("sparql_owl")
    return g


def _shapes_graph() -> Graph:
    """A fresh graph of the ``srl:`` shapes, combined with ``salg:``'s -
    private, same reasoning as ``_ontology_graph()`` above."""
    import starontology

    g = starontology.get_ontology_graph("srl_shacl")
    g += starontology.get_ontology_graph("sparql_shacl")
    return g


def validate(data_graph: Graph) -> tuple[bool, Graph, str]:
    """Validate ``data_graph`` (e.g. straight out of ``parse_to_tree()``,
    or an LLM-authored ``srl:`` graph not yet decoded) against the ``srl:``
    shapes.

    Goes through ``starlayer.shacl.validate()``, never bare ``pyshacl`` -
    same rule every other shapes module in this stack follows, since a
    caller-supplied graph may carry genuine RDF 1.2 content (a triple term
    as a ``srl:subject``/``srl:object``) that only ``starlayer.shacl``
    understands correctly.

    Returns ``(conforms, results_graph, results_text)``, unpacked from
    ``starlayer.shacl``'s own ``ValidationResult``.
    """
    from pyshacl.errors import ShapeRecursionWarning

    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        result = starlayer.shacl.validate(
            data_graph,
            shacl_graph=_shapes_graph(),
            ont_graph=_ontology_graph(),
            inference="rdfs",
            advanced=True,
            max_validation_depth=100,
        )
    return result.conforms, result.report_graph, result.report_text
