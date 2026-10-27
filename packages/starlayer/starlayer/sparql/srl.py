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
``from_rdf.py``) and ``_render_expr_text`` (``ssyn_to_text.py``) are reused
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

import warnings
from functools import partial

from pyparsing import CaselessKeyword as Keyword
from pyparsing import Group, Optional, Suppress, ZeroOrMore
from pyparsing import Literal as _PPLiteral
from rdflib import RDF, BNode, Graph, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import NamespaceManager
from rdflib.plugins.sparql import algebra
from rdflib.plugins.sparql.parser import (
    BaseDecl,
    Constraint,
    Expression,
    PrefixDecl,
    String,
    TriplesSameSubject,
    TriplesSameSubjectPath,
    Var,
    iri,
)
from rdflib.plugins.sparql.parserutils import Comp, CompValue, Param
from rdflib.plugins.sparql.pyparsing_compat import rest_of_line
from rdflib.plugins.sparql.sparql import Prologue

from . import _srl_ast as srl_ast
from ._srl_ast import (  # noqa: F401 - re-exported, see module docstring
    PlanEdge,
    PlanRule,
    PlanStratum,
    RulePlan,
    RuleSet,
    TriplePattern,
)
from .from_rdf import _decode
from .srl_semantic_checks import _check_ruleset
from .ssyn_to_text import _render_expr_text
from .to_rdf import _encode, _new_starlayer_graph
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


# ---------------------------------------------------------------------------
# Grammar - reuses rdflib's own real SPARQL 1.2 grammar
# productions directly for everything the spec's own grammar text says is
# unchanged from SPARQL; only the genuinely new SRL-specific productions are
# hand-written here.
#
# Triple groups use rdflib's own TriplesSameSubject (see ``_SameSubject`` below), so the
# whole SPARQL 1.2 triple syntax is available. Property paths in rule bodies are limited to
# `/` and `^`, as the spec says, and are expanded into triple patterns.
# ---------------------------------------------------------------------------

_VersionDecl = Comp("VersionDecl", Keyword("VERSION") + Param("version", String))
_ImportsDecl = Comp("ImportsDecl", Keyword("IMPORTS") + Param("iri", iri))
_Prologue1Decl = BaseDecl | PrefixDecl | _VersionDecl | _ImportsDecl

_Period = Suppress(_PPLiteral("."))
_BoolFlag = lambda keyword: Optional(Keyword(keyword)).set_parse_action(lambda t: bool(t))  # noqa: E731


# A group of triples sharing a subject, written exactly as in SPARQL 1.2: rdflib's own
# TriplesSameSubject production, extended in place by this project's SPARQL 1.2 grammar
# (``_grammar12.install()``), expands `,` object lists, `;` property lists, `[ ... ]`
# blank-node property lists, `( ... )` collections, RDF 1.2 triple terms `<<( s p o )>>`,
# reified triples `<< s p o >>`, reifiers `~ r` and annotations `{| ... |}` into a flat
# sequence of (subject, predicate, object) terms. The same production is used for DATA
# blocks (where `_check_ruleset` then rejects variables), head templates and body patterns.
_SameSubject = Comp("SameSubject", Param("terms", Group(TriplesSameSubject)))
_SameSubjectData = _SameSubject
# Rule bodies (and the bodies of NOT) may also use a property path as a predicate; the head
# and DATA blocks may not (§7.6: only `Verb` there). SRL allows only the `/` and `^`
# path operators; they are expanded into plain triple patterns when the rule is built.
_SameSubjectPattern = Comp("SameSubject", Param("terms", Group(TriplesSameSubjectPath)))


def _expand_path(subject, predicate, obj) -> list[srl_ast.TriplePattern]:
    """Expand a property path into the triple patterns it stands for (§5: "Property
    path syntax only covers paths with / and ^. These can be expanded into triple
    patterns"). ``s p/q o`` becomes ``s p _:m . _:m q o``; ``s ^p o`` becomes ``o p s``.
    A blank node introduced here behaves as a variable in a rule body.

    Raises:
        SRLParseError: For any other path operator (``|``, ``*``, ``+``, ``?``, ``!``).
    """
    from rdflib.paths import InvPath, Path, SequencePath

    if isinstance(predicate, CompValue):  # the parse tree of a path, with prefixed names resolved
        predicate = algebra.traverse(predicate, visitPost=algebra.translatePath)
    if isinstance(predicate, SequencePath):
        nodes = [subject, *(BNode() for _ in predicate.args[:-1]), obj]
        return [t for i, arg in enumerate(predicate.args) for t in _expand_path(nodes[i], arg, nodes[i + 1])]
    if isinstance(predicate, InvPath):
        return _expand_path(obj, predicate.arg, subject)
    if isinstance(predicate, Path):
        raise SRLParseError(
            f"SRL: property path {predicate.n3()} is not allowed: SRL property paths use only the / and ^ operators "
            "(write a repeated or optional step with a recursive rule instead)"
        )
    return [srl_ast.TriplePattern(subject=subject, predicate=predicate, object=obj)]


def _expand_same_subject(cv: CompValue) -> list[srl_ast.TriplePattern]:
    terms = list(cv["terms"])
    return [t for i in range(0, len(terms), 3) for t in _expand_path(terms[i], terms[i + 1], terms[i + 2])]


_DataTriplesBlock = ZeroOrMore(Param("subjects", _SameSubjectData, isList=True) + Optional(_Period))
_SRLData = Comp("Data", Keyword("DATA") + Suppress("{") + _DataTriplesBlock + Suppress("}"))

_HeadTemplateBlock = ZeroOrMore(Param("subjects", _SameSubject, isList=True) + Optional(_Period))
_HeadTemplate = Comp("HeadTemplate", Suppress("{") + _HeadTemplateBlock + Suppress("}"))

_Filter = Comp("Filter", Keyword("FILTER") + Param("expr", Constraint))

_Assignment = Comp(
    "Assignment",
    Keyword("SET") + Suppress("(") + Param("var", Var) + Suppress(":=") + Param("expr", Expression) + Suppress(")"),
)

# Negation bodies are grammatically restricted to triple patterns + filters
# only (no nested negation/assignment) - enforced structurally: this
# alternation has no Negation/Assignment branch.
_NegationBodyItem = (Param("inner", _SameSubjectPattern, isList=True) + Optional(_Period)) | (
    Param("inner", _Filter, isList=True) + Optional(_Period)
)
_Negation = Comp(
    "Negation",
    Keyword("NOT") + Param("data", _BoolFlag("DATA")) + Suppress("{") + ZeroOrMore(_NegationBodyItem) + Suppress("}"),
)

_BodyItem = (Param("body", _SameSubjectPattern, isList=True) + Optional(_Period)) | (
    Param("body", _Filter | _Negation | _Assignment, isList=True) + Optional(_Period)
)
_BodyPattern = Comp("BodyPattern", Suppress("{") + ZeroOrMore(_BodyItem) + Suppress("}"))

_SRLRule = Comp(
    "Rule",
    Keyword("RULE")
    + Optional(Param("id", iri))
    + Param("head", _HeadTemplate)
    + Keyword("WHERE")
    + Param("data", _BoolFlag("DATA"))
    + Param("body", _BodyPattern),
)

# RuleSet ::= RuleOrDataBlock - simplified (documented, behaviourally
# equivalent for well-formed input): prologue declarations and Rule/Data
# items are matched in one flat ZeroOrMore regardless of interleaving, then
# bucketed by kind, since Prologue accumulation is order-independent the
# same way rdflib's own translatePrologue already is.
_RuleOrData = _SRLRule | _SRLData
_RuleSetGrammar = Comp(
    "RuleSet",
    ZeroOrMore(Param("prologue", _Prologue1Decl, isList=True) | Param("body", _RuleOrData, isList=True)),
)
_RuleSetGrammar.ignore("#" + rest_of_line)


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


def _list_field(cv: CompValue, key: str) -> list:
    """``CompValue.get(key, default)``'s second positional parameter is
    *not* a default value - it's ``variables`` - so ``cv.get(key, [])``
    silently does something else entirely; worse, an absent key falls back
    to returning ``key`` itself (rdflib's own ``OrderedDict.get`` "hack"),
    not ``None``/``[]``. A ``Param(..., isList=True)`` field is only ever
    set at all if at least one occurrence matched, so an absent key
    genuinely means "zero occurrences" - this is the correct way to read
    that as ``[]``.

    Args:
        cv: The CompValue to read the field from.
        key: The list-valued field name.

    Returns:
        The field's values as a list, or ``[]`` if the key is absent.
    """
    return list(cv[key]) if key in cv else []


def _opt_field(cv: CompValue, key: str):
    """See :func:`_list_field` for why ``cv.get(key)`` is unsafe here too."""
    return cv[key] if key in cv else None


def _resolve_pnames(tree, prologue: Prologue):
    return algebra.traverse(tree, visitPost=partial(algebra.translatePName, prologue=prologue))


_PASS_THROUGH_EXPRESSIONS = frozenset(
    {
        "ConditionalOrExpression",
        "ConditionalAndExpression",
        "RelationalExpression",
        "AdditiveExpression",
        "MultiplicativeExpression",
        "UnaryPlus",
    }
)


def _unwrap_pass_through(value):
    """``TRIPLE(?s, :p, ?o)`` parses its three arguments as full expressions, so a plain term arrives wrapped in a
    chain of single-operand expression nodes. Strip that chain so the triple term has the same shape as ``<<( ?s :p ?o )>>``."""
    while isinstance(value, CompValue) and value.name in _PASS_THROUGH_EXPRESSIONS and "expr" in value:
        if any(value.get(key) is not None and key != value.get(key) for key in ("other", "op")):
            break
        value = value["expr"]
    return value


def _simplify_triple_term_expressions(tree):
    def visit(node):
        if isinstance(node, TripleTermNode):
            for key in ("subject", "predicate", "object"):
                if key in node:
                    node[key] = _unwrap_pass_through(node[key])
        return None

    return algebra.traverse(tree, visitPost=visit)


def _build_prologue(decls: list[CompValue], base: str | None = None) -> Prologue:
    from rdflib.plugins.sparql.algebra import translatePrologue

    # ``base`` is only the initial base; a BASE declaration in the document replaces it (SPARQL 1.1 section 4.1.1)
    return translatePrologue(decls, base=base)


def _build_negation_inner(items: list) -> list[srl_ast.NegationBodyElement]:
    out: list[srl_ast.NegationBodyElement] = []
    for item in items:
        if item.name == "SameSubject":
            out.extend(_expand_same_subject(item))
        elif item.name == "Filter":
            out.append(srl_ast._FilterElement(expr=item["expr"]))
        else:  # pragma: no cover - grammar structurally forbids anything else
            raise SRLParseError(f"illegal negation body element: {item!r}")
    return out


def _build_body_elements(items: list) -> list[srl_ast.BodyElement]:
    out: list[srl_ast.BodyElement] = []
    for cv in items:
        if cv.name == "SameSubject":
            out.extend(_expand_same_subject(cv))
        elif cv.name == "Filter":
            out.append(srl_ast._FilterElement(expr=cv["expr"]))
        elif cv.name == "Assignment":
            out.append(srl_ast._AssignmentElement(var=cv["var"], expr=cv["expr"]))
        elif cv.name == "Negation":
            out.append(srl_ast._NegationElement(inner=_build_negation_inner(_list_field(cv, "inner")), evaldata=not bool(cv["data"])))
        else:
            raise SRLParseError(f"unknown rule body element: {cv!r}")  # pragma: no cover
    return out


def _build_rule(cv: CompValue) -> srl_ast._Rule:
    head = [t for grp in _list_field(cv["head"], "subjects") for t in _expand_same_subject(grp)]
    body = _build_body_elements(_list_field(cv["body"], "body"))
    rule_id = _opt_field(cv, "id")
    return srl_ast._Rule(
        head=head,
        body=body,
        evaldata=not bool(cv["data"]),  # the grammar's DATA keyword means evaldata is false
        id=URIRef(rule_id) if rule_id is not None else None,
    )


def _build_data(cv: CompValue) -> srl_ast._Data:
    return srl_ast._Data(triples=[t for grp in _list_field(cv, "subjects") for t in _expand_same_subject(grp)])


def _build_ruleset(cv: CompValue) -> srl_ast.RuleSet:
    imports: list[URIRef] = []
    for decl in _list_field(cv, "prologue"):
        if decl.name == "ImportsDecl":
            imports.append(URIRef(decl["iri"]))
        # BaseDecl/PrefixDecl were already consumed to build the Prologue
        # used for name resolution before this function ran; VersionDecl
        # is informative only.

    rules: list[srl_ast._Rule] = []
    data_blocks: list[srl_ast._Data] = []
    for item in _list_field(cv, "body"):
        if item.name == "Rule":
            rules.append(_build_rule(item))
        elif item.name == "Data":
            data_blocks.append(_build_data(item))
        else:  # pragma: no cover
            raise SRLParseError(f"unknown top-level rule set item: {item!r}")

    return srl_ast.RuleSet(rules=rules, data=data_blocks, imports=imports)


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
    try:
        from starlayer.sparql.parse12 import parse_serialized

        parsed = parse_serialized(lambda: _RuleSetGrammar.parse_string(text, parse_all=True))
    except Exception as exc:  # pyparsing.ParseException et al.
        raise SRLParseError(str(exc)) from exc

    root: CompValue = parsed[0]
    prologue = _build_prologue(_list_field(root, "prologue"), base)
    try:
        resolved = _resolve_pnames(root, prologue)
    except SRLError:
        raise
    except Exception as exc:  # rdflib raises a bare Exception for an undeclared prefix
        raise SRLParseError(f"SRL: {exc}") from exc
    ruleset = _build_ruleset(_simplify_triple_term_expressions(resolved))

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


def _triple_to_rdf(triple: srl_ast.TriplePattern, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, _TRIPLE_PATTERN))
    graph.add((node, _TRIPLE_SUBJECT, _encode(triple.subject, graph)))
    graph.add((node, _TRIPLE_PREDICATE, _encode(triple.predicate, graph)))
    graph.add((node, _TRIPLE_OBJECT, _encode(triple.object, graph)))
    return node


def _body_element_to_rdf(element: srl_ast.BodyElement, graph: Graph) -> BNode:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_to_rdf(element, graph)
    if isinstance(element, srl_ast._FilterElement):
        node = BNode()
        graph.add((node, RDF.type, _FILTER_ELEMENT))
        graph.add((node, _EXPR, _encode(element.expr, graph)))
        return node
    if isinstance(element, srl_ast._AssignmentElement):
        node = BNode()
        graph.add((node, RDF.type, _ASSIGNMENT_ELEMENT))
        graph.add((node, _VAR, _encode(element.var, graph)))
        graph.add((node, _EXPR, _encode(element.expr, graph)))
        return node
    if isinstance(element, srl_ast._NegationElement):
        node = BNode()
        graph.add((node, RDF.type, _NEGATION_ELEMENT))
        inner_nodes = [_body_element_to_rdf(e, graph) for e in element.inner]
        graph.add((node, _INNER, _rdf_list(graph, inner_nodes)))
        graph.add((node, _NEGATION_EVALDATA_FLAG, _encode(element.evaldata, graph)))
        return node
    raise NotImplementedError(f"starlayer.sparql.srl: no encoding for body element {element!r}")  # pragma: no cover


def _rule_to_rdf(rule: srl_ast._Rule, graph: Graph) -> BNode:
    node = BNode()
    graph.add((node, RDF.type, _RULE))
    head_nodes = [_triple_to_rdf(t, graph) for t in rule.head]
    graph.add((node, _HEAD, _rdf_list(graph, head_nodes)))
    body_nodes = [_body_element_to_rdf(e, graph) for e in rule.body]
    graph.add((node, _BODY, _rdf_list(graph, body_nodes)))
    graph.add((node, _RULE_EVALDATA_FLAG, _encode(rule.evaldata, graph)))
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
        namespace_manager: If given, render prefixed names instead of full
            ``<...>`` IRIs wherever a match exists - purely cosmetic, the
            resulting text still parses identically either way.

    Returns:
        The rendered SRL text.
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


def _body_element_text(element: srl_ast.BodyElement, namespace_manager: NamespaceManager | None) -> str:
    if isinstance(element, srl_ast.TriplePattern):
        return _triple_text(element, namespace_manager)
    if isinstance(element, srl_ast._FilterElement):
        return f"FILTER({_render_expr_text(element.expr)})"
    if isinstance(element, srl_ast._AssignmentElement):
        var = _term_text(element.var, namespace_manager)
        return f"SET ({var} := {_render_expr_text(element.expr)})"
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

def srl_parse_to_tree(text: str, base: str | None = None) -> tuple[Graph, BNode]:
    """SRL text straight to its ``srl:``-encoded tree-RDF. Composes
    ``parse_ruleset`` + ``ruleset_to_tree``. Returns ``(graph, root)``."""
    return ruleset_to_tree(parse_ruleset(text, base))


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
    return srl_ast.RuleSet(rules=rules, data=data, imports=[])


# ---------------------------------------------------------------------------
# SHACL validation of an srl: tree-RDF graph - ontology_graph()/
# shapes_graph() deliberately not exposed publicly here, see module
# docstring for why.
# ---------------------------------------------------------------------------

def _ontology_graph() -> Graph:
    """The ``srl:`` RDFS ontology, combined with ``salg:``'s and
    ``spexpr:``'s - private: see module docstring for why this isn't
    exposed publicly.

    All three must be loaded together: this module's own SHACL shapes use
    ``sh:class spexpr:Expression``/``spexpr:Variable``, and the RDFS
    subclass entailment those checks depend on only resolves correctly
    when ``srl_owl``, ``sparql_owl``, and ``spexpr_owl`` are all present in
    the same graph.

    Returns:
        A fresh combined ontology graph.
    """
    from starlayer import starontology

    g = starontology.get_ontology_graph("srl_owl")
    g += starontology.get_ontology_graph("sparql_owl")
    g += starontology.get_ontology_graph("spexpr_owl")
    return g


def _shapes_graph() -> Graph:
    """A fresh graph of the ``srl:`` shapes, combined with ``salg:``'s and
    ``spexpr:``'s - private, same reasoning as ``_ontology_graph()``
    above."""
    from starlayer import starontology

    g = starontology.get_ontology_graph("srl_shacl")
    g += starontology.get_ontology_graph("sparql_shacl")
    g += starontology.get_ontology_graph("spexpr_shacl")
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
    from pyshacl.errors import ShapeRecursionWarning

    import starlayer.shacl  # lazy: avoids a circular-import deadlock at module load time
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=ShapeRecursionWarning)
        result = starlayer.shacl.validate(
            data_graph,
            shacl_graph=_validation_graphs()[0],
            ont_graph=_validation_graphs()[1],
            inference=ENTAILMENT.RDFS,
            advanced=True,
            max_validation_depth=100,
        )
    return result.conforms, result.report_graph, result.report_text
