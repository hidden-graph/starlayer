"""pyparsing grammar for SRL/SPARQL-RL text syntax
(`WD-sparql12-rl-20260919 <https://www.w3.org/TR/sparql12-rl/>`_ §7.6),
entry point :func:`parse_ruleset`.

Reuses rdflib's own real, already-installed SPARQL 1.2 grammar productions
directly (``rdflib.plugins.sparql.parser``) for everything the spec's own
grammar text says is unchanged from SPARQL - confirmed live this session
that ``Var``, ``VarOrTerm``, ``VarOrIri``, ``GraphTerm``, ``iri``,
``Expression``, ``Constraint``, ``BaseDecl``, ``PrefixDecl`` are all
directly importable, already-built pyparsing productions, not something
that needs re-deriving. Only the genuinely new SRL-specific productions
(``RuleSet``/``Rule``/``Data``/``HeadTemplate``/``BodyPattern``/``Filter``/
``Negation``/``Assignment``, plus ``VERSION``/``IMPORTS`` prologue
extensions) are hand-written here, using the same ``Comp``/``Param``
CompValue-building convention rdflib's own grammar (and this project's
``grammar12.py``) already uses - **not** ``starsparql.srl_ast``'s
dataclasses directly, so that prefixed-name resolution can happen as a
single post-parse tree pass (:func:`_resolve_pnames`, using rdflib's own
``algebra.translatePName``/``traverse`` - confirmed live this session to
work unmodified against this grammar's own CompValue shapes), exactly
mirroring how rdflib's own ``parseQuery``/``translateQuery`` split parsing
from prefix resolution into two separate steps rather than resolving
inline during parsing. :func:`_build_ruleset` is the final step, walking
the resolved CompValue tree into real ``srl_ast`` dataclasses.

**Deliberate scope reduction for this first implementation pass** (each
noted at its own production below): only ``;``-chained same-subject
property lists are supported (needed by the §6.6 worked example's own R5:
``RULE { [] rdf:type :Notification ; :concerns ?x } WHERE ...``) - no
``,``-chained same-subject-and-predicate object lists (no example in the
spec's own text needs them); no property paths
beyond a bare IRI predicate (the spec's own path grammar, productions
83-88, is already far more restricted than full SPARQL 1.1/1.2 paths -
no alternative/inverse/repetition operators visible in it at all); no
reified-triple/triple-term syntax in pattern/template/data position yet
(``srl_ast.Term`` already types this in, ready for a follow-up grammar
widening - see that module's docstring). None of these are used by the
spec's own worked examples, so they don't block a correct, testable v1.
"""

from __future__ import annotations

from functools import partial

from pyparsing import CaselessKeyword as Keyword
from pyparsing import Literal, Optional, Suppress, ZeroOrMore
from rdflib import URIRef
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

# ---------------------------------------------------------------------------
# New prologue productions - [7]/[8]
# ---------------------------------------------------------------------------

# [7] VersionDecl ::= 'VERSION' VersionSpecifier   (VersionSpecifier a String)
VersionDecl = Comp("VersionDecl", Keyword("VERSION") + Param("version", String))

# [8] ImportsDecl ::= 'IMPORTS' iri
ImportsDecl = Comp("ImportsDecl", Keyword("IMPORTS") + Param("iri", iri))

_Prologue1Decl = BaseDecl | PrefixDecl | VersionDecl | ImportsDecl

_Period = Suppress(Literal("."))
_BoolFlag = lambda keyword: Optional(Keyword(keyword)).set_parse_action(lambda t: bool(t))  # noqa: E731


def _property_list(term=VarOrTerm, predicate=VarOrIri):
    """One same-subject line: ``subject predicate object (';' predicate
    object)* .`` - the minimal property-list chaining the spec's own §6.6
    worked example needs (``RULE { [] rdf:type :Notification ; :concerns
    ?x } WHERE ...``). Comma-separated object lists (``p o1, o2``) are
    still out of scope - see module docstring's scope note; no example in
    the spec's own text needs them.
    """
    pair = Comp("PredObj", Param("predicate", predicate) + Param("object", term))
    return Comp(
        "SameSubject",
        Param("subject", term)
        + Param("verbs", pair, isList=True)
        + ZeroOrMore(Suppress(";") + Param("verbs", pair, isList=True)),
    )


# Ground-only triples, for [12] Data - predicate is a bare `iri` (never a
# Var), matching the spec's own RDFTermData productions admitting no
# variables anywhere.
_SameSubjectData = _property_list(term=GraphTerm, predicate=iri)
# Ordinary pattern/template-position triples - Var allowed everywhere Term
# allows it (subject/object) and in predicate position (VarOrIri), plus the
# `a` shorthand for rdf:type (rdflib's own `A` production already resolves
# straight to the real rdf:type URIRef).
_SameSubjectPattern = _property_list(term=VarOrTerm, predicate=A | VarOrIri)


def _expand_same_subject(cv: CompValue) -> list[srl_ast.TriplePattern]:
    """One ``SameSubject`` match (see :func:`_property_list`) expands to
    one or more flat ``srl_ast.TriplePattern``\\ s sharing ``cv["subject"]``."""
    subject = cv["subject"]
    return [
        srl_ast.TriplePattern(subject=subject, predicate=pair["predicate"], object=pair["object"])
        for pair in _list_field(cv, "verbs")
    ]


# ---------------------------------------------------------------------------
# [12] Data ::= 'DATA' '{' DataTriplesBlock? '}'
# ---------------------------------------------------------------------------

_DataTriplesBlock = ZeroOrMore(Param("subjects", _SameSubjectData, isList=True) + Optional(_Period))
Data = Comp("Data", Keyword("DATA") + Suppress("{") + _DataTriplesBlock + Suppress("}"))

# ---------------------------------------------------------------------------
# [13] HeadTemplate ::= '{' HeadTemplateBlock? '}'
# ---------------------------------------------------------------------------

_HeadTemplateBlock = ZeroOrMore(Param("subjects", _SameSubjectPattern, isList=True) + Optional(_Period))
HeadTemplate = Comp("HeadTemplate", Suppress("{") + _HeadTemplateBlock + Suppress("}"))

# ---------------------------------------------------------------------------
# [16] Filter ::= 'FILTER' Constraint
# ---------------------------------------------------------------------------

Filter = Comp("Filter", Keyword("FILTER") + Param("expr", Constraint))

# ---------------------------------------------------------------------------
# [24] Assignment ::= 'SET' '(' Var ':=' Expression ')'
# ---------------------------------------------------------------------------

Assignment = Comp(
    "Assignment",
    Keyword("SET") + Suppress("(") + Param("var", Var) + Suppress(":=") + Param("expr", Expression) + Suppress(")"),
)

# ---------------------------------------------------------------------------
# [21]-[23] Negation ::= 'NOT' 'DATA'? '{' BodyBasic '}'
#   BodyBasic ::= BodyTriplesBlock? ( BodyBasicNotTriples '.'? BodyTriplesBlock? )*
#   BodyBasicNotTriples ::= Filter
# Negation bodies are grammatically restricted to triple patterns + filters
# only (no nested negation/assignment) - enforced here structurally, not
# just documented: this alternation has no Negation/Assignment branch.
# ---------------------------------------------------------------------------

_NegationBodyItem = (Param("inner", _SameSubjectPattern, isList=True) + Optional(_Period)) | (
    Param("inner", Filter, isList=True) + Optional(_Period)
)
Negation = Comp(
    "Negation",
    Keyword("NOT") + Param("data", _BoolFlag("DATA")) + Suppress("{") + ZeroOrMore(_NegationBodyItem) + Suppress("}"),
)

# ---------------------------------------------------------------------------
# [14]-[15] BodyPattern ::= '{' BodyTriplesBlock? ( BodyNotTriples '.'? BodyTriplesBlock? )* '}'
#   BodyNotTriples ::= Filter | Negation | Assignment
# ---------------------------------------------------------------------------

_BodyItem = (Param("body", _SameSubjectPattern, isList=True) + Optional(_Period)) | (
    Param("body", Filter | Negation | Assignment, isList=True) + Optional(_Period)
)
BodyPattern = Comp("BodyPattern", Suppress("{") + ZeroOrMore(_BodyItem) + Suppress("}"))

# ---------------------------------------------------------------------------
# [11] Rule ::= 'RULE' iri? HeadTemplate 'WHERE' 'DATA'? BodyPattern
# ---------------------------------------------------------------------------

Rule = Comp(
    "Rule",
    Keyword("RULE")
    + Optional(Param("id", iri))
    + Param("head", HeadTemplate)
    + Keyword("WHERE")
    + Param("data", _BoolFlag("DATA"))
    + Param("body", BodyPattern),
)

# ---------------------------------------------------------------------------
# [1]-[3] RuleSet ::= RuleOrDataBlock
#   RuleOrDataBlock ::= Prologue ( RuleOrData+ ( Prologue1 RuleOrData? )* )?
#   RuleOrData ::= Rule | Data
#
# Simplified (documented, behaviourally equivalent for well-formed input):
# prologue declarations and Rule/Data items are matched in one flat
# ZeroOrMore regardless of interleaving, then bucketed by kind - Prologue
# accumulation (BASE/PREFIX -> a single rdflib Prologue) is order-
# independent in the same way rdflib's own translatePrologue already is,
# so collapsing the spec's own more permissive interleaving grouping down
# to "collect all prologue items, collect all rule/data items" changes
# nothing observable.
# ---------------------------------------------------------------------------

_RuleOrData = Rule | Data
RuleSetGrammar = Comp(
    "RuleSet",
    ZeroOrMore(Param("prologue", _Prologue1Decl, isList=True) | Param("body", _RuleOrData, isList=True)),
)
# Matches rdflib's own QueryUnit/UpdateUnit.ignore("#" + rest_of_line) - a
# SPARQL/SRL "#" comment runs to end of line, skipped like whitespace.
RuleSetGrammar.ignore("#" + rest_of_line)


class SRLParseError(ValueError):
    """Raised by :func:`parse_ruleset` for malformed SRL text."""


def _list_field(cv: CompValue, key: str) -> list:
    """``CompValue.get(key, default)``'s second positional parameter is
    *not* a default value - it's ``variables`` (see ``CompValue._value``) -
    so ``cv.get(key, [])`` silently does something else entirely (passes
    ``[]`` as ``variables``, a no-op here) rather than defaulting; worse,
    when ``key`` truly is absent, ``CompValue.get`` falls back to
    returning ``key`` itself (the OrderedDict.get(self, a, a) "hack" in
    rdflib's own source), not ``None``/``[]``. A ``Param(..., isList=True)``
    field is only ever set on a ``CompValue`` at all if at least one
    occurrence matched (``Comp.postParse``), so an absent key genuinely
    means "zero occurrences", not a bug - this helper is the correct way
    to read that as ``[]``.
    """
    return list(cv[key]) if key in cv else []


def _opt_field(cv: CompValue, key: str):
    """See :func:`_list_field` for why ``cv.get(key)`` is unsafe here too -
    same fix, for a scalar optional field."""
    return cv[key] if key in cv else None


def _resolve_pnames(tree, prologue: Prologue):
    """Single post-parse pass resolving every prefixed name (``pname``
    CompValue) and relative IRI in ``tree`` against ``prologue`` - see
    module docstring for why this mirrors rdflib's own two-step parse/
    translate split rather than resolving inline during parsing.
    """
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
        # is informative only (VERSION conformance is already handled at
        # the RDF/Turtle layer per docs/functionality-overview.md's
        # "VERSION-directive conformance warnings" entry, not re-litigated
        # here for SRL text specifically).

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
    """Parse SRL rule-set text into a :class:`starsparql.srl_ast.RuleSet`.

    Two-pass, matching rdflib's own ``parseQuery``/``translateQuery`` split
    (see module docstring): parse raw (leaving prefixed names unresolved),
    build a real ``Prologue`` from the parsed ``BASE``/``PREFIX`` decls and
    resolve every prefixed/relative name against it in one tree pass, then
    convert the resolved CompValue tree into real ``srl_ast`` dataclasses.
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
