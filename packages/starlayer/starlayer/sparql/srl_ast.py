"""Python dataclasses for the SRL/SPARQL-RL abstract syntax tree, mirroring
`WD-sparql12-rl-20260919 <https://www.w3.org/TR/sparql12-rl/>`_ §4.1
"Elements of the Abstract Syntax" (+ its own "Component Notation" table)
field-for-field - field names here are the spec's own attribute names
(``rule.head``, ``ruleset.data``, ``negation.inner``, ...), not invented.

Deliberately plain dataclasses, not ``rdflib.plugins.sparql.parserutils
.CompValue``: unlike ``starlayer.sparql``'s existing SPARQL 1.2 work
(``triple_term.TripleTermNode``, ``grammar12.py``), SRL text never feeds
rdflib's own algebra/``translateQuery``/``translateUpdate`` machinery, so
there is no ``CompValue``-specific requirement (hashability for
``reorderTriples``, etc.) to satisfy here - a real dataclass tree is
simpler and gets real type checking.

Terms reuse plain rdflib types directly - no new term representation is
minted. A triple pattern/template's subject/object may additionally be a
``starlayer.sparql.triple_term.TripleTermNode`` (RDF 1.2 triple term) per the
spec's own grammar (productions 25-46 "Data", 47-60 "Template", 61-82
"Pattern" all admit reified-triple/triple-term syntax structurally
identical to Turtle 1.2's own) - **not yet parsed by ``srl.py``**
(see that module's own docstring for the explicit scope note); the field
type already allows it so decoding (``srl.py``) and the AST-as-RDF
round trip need no follow-up widening once grammar support for it lands.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdflib import BNode, Literal, URIRef, Variable
from rdflib.plugins.sparql.parserutils import Expr

from .triple_term import TripleTermNode

# VarOrRDFTerm (template/pattern position) - a Variable, an ordinary ground
# RDF term, or (per the spec's grammar, not yet emitted by srl.py -
# see module docstring) a triple term.
Term = Variable | URIRef | BNode | Literal | TripleTermNode

# VarOrIri (predicate position) - narrower than Term: never a Literal,
# BNode, or triple term, per the spec's own predicate-position grammar
# (Verb/VerbPath/VerbTemplate all reduce to "Var | iri").
PredicateTerm = Variable | URIRef


@dataclass(frozen=True)
class TriplePattern:
    """§4.1's "Triple template" and "Triple pattern" - the spec defines
    both as the same 3-tuple shape (``subject``/``predicate``/``object``,
    predicate always ``VarOrIri``), so one dataclass covers both a rule's
    head (where the spec calls it a "triple template") and its body/DATA
    block (where it calls it a "triple pattern") - see ``TripleTemplate``
    alias below for call sites that want the spec's own head-position name.
    """

    subject: Term
    predicate: PredicateTerm
    object: Term


# §4.1 calls a rule's own head elements "triple templates" - same shape as
# TriplePattern (see its docstring), reused rather than duplicated.
TripleTemplate = TriplePattern


@dataclass(frozen=True)
class FilterElement:
    """§4.1 "Filter element" - ``filter.expr``, a boolean-valued SPARQL 1.2
    expression. ``expr`` is a real rdflib ``Expr``/``CompValue`` tree,
    produced by ``srl.py`` reusing rdflib's own ``Constraint``/
    ``Expression`` productions unmodified (see that module's docstring) -
    not a bespoke SRL expression AST.
    """

    expr: Expr


@dataclass(frozen=True)
class AssignmentElement:
    """§4.1 "Assignment element" - ``SET (?var := expr)``. Per §4.2's
    well-formedness conditions, ``var`` must be a variable not already
    bound earlier in the same rule body - enforced by
    ``srl_semantic_checks.py`` (Phase 3, not yet implemented), not here.
    """

    var: Variable
    expr: Expr


# §4.1's "Negation element" body (``negation.inner``) is grammatically
# restricted (production 23, BodyBasicNotTriples ::= Filter) to triple
# patterns and filters only - no nested negation or assignment, unlike an
# ordinary rule body. Modeled as its own narrower union rather than reusing
# BodyElement, so a NegationElement literally cannot hold an illegal member
# by construction.
NegationBodyElement = TriplePattern | FilterElement


@dataclass(frozen=True)
class NegationElement:
    """§4.1 "Negation element" - ``NOT DATA? { ... }``. ``data=True`` means
    the negated pattern is matched against the rule set's own DATA graph
    (``GD``) rather than the evaluation graph, per §6.4's ``evalRuleElements``
    pseudocode (``if rElt with DATA: ... GD, GD else ... G, GD``).
    """

    inner: list[NegationBodyElement] = field(default_factory=list)
    data: bool = False


# §4.1's "Rule element" - the union every rule body member belongs to.
BodyElement = TriplePattern | FilterElement | NegationElement | AssignmentElement


@dataclass(frozen=True)
class Rule:
    """§4.1 "Rule" - ``head`` + ``body``, optional ``id`` (an IRI naming the
    rule), and ``data`` (match the body's own top-level triple patterns
    against the rule set's DATA graph rather than the base graph - the
    grammar's ``WHERE DATA? { ... }``).

    A rule is "run-once" (§4.1: evaluated exactly once per stratum, vs.
    "general": evaluated to a fixpoint) iff it has an assignment element
    anywhere in its body, or a blank node anywhere in its head - see
    ``srl_eval.py`` (Phase 4, not yet implemented) for where this is
    actually consulted; deliberately not stored as a field here since it is
    a pure function of ``head``/``body``, not independent state.
    """

    head: list[TripleTemplate] = field(default_factory=list)
    body: list[BodyElement] = field(default_factory=list)
    data: bool = False
    id: URIRef | None = None


@dataclass(frozen=True)
class Data:
    """§4.1 "Data block" - ground triples only (the grammar's ``RDFTermData``
    productions admit no variables), giving the DATA graph GD any rule may
    match against instead of, or in addition to, the base graph.
    """

    triples: list[TriplePattern] = field(default_factory=list)


@dataclass
class RuleSet:
    """§4.1 "Rule set" - ``rules`` + ``data`` blocks + ``imports`` (IRIs of
    other rule sets to inline, §4.5 "Processing Imports"). A "resolved rule
    set" (§4.5) is one whose ``imports`` list is empty because every import
    has already been recursively inlined - not modeled as a separate type
    here, just a ``RuleSet`` with ``imports == []``.
    """

    rules: list[Rule] = field(default_factory=list)
    data: list[Data] = field(default_factory=list)
    imports: list[URIRef] = field(default_factory=list)
