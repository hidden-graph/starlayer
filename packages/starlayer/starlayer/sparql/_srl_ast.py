"""Private module (renamed from ``srl_ast.py`` 2026-10-05 - not directly
importable from outside this package). Only ``RuleSet`` and
``TriplePattern`` are re-exported from ``srl.py`` (e.g. ``srl.RuleSet``),
so there's one real path to those two, not two paths - everything else
here (``_Rule``, ``_Data``, ``_FilterElement``, ``_AssignmentElement``,
``_NegationElement``) is private, made so 2026-10-06: no public function
or method requires any of them directly, and the only way a caller would
ever touch one is by walking ``RuleSet.rules``/``Rule.head``/``Rule.body``,
an inspection/editing concern this API doesn't cover yet.

Python dataclasses for the SRL/SPARQL-RL abstract syntax tree, mirroring
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

from rdflib import BNode, Graph, Literal, URIRef, Variable
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
class _FilterElement:
    """§4.1 "Filter element" - ``filter.expr``, a boolean-valued SPARQL 1.2
    expression. ``expr`` is a real rdflib ``Expr``/``CompValue`` tree,
    produced by ``srl.py`` reusing rdflib's own ``Constraint``/
    ``Expression`` productions unmodified (see that module's docstring) -
    not a bespoke SRL expression AST.

    Private: no public function or method takes or returns one - only
    reachable by walking ``Rule.body``, an inspection/editing concern this
    API doesn't cover yet (same reasoning as ``_AssignmentElement``/
    ``_NegationElement``/``_Data``/``_Rule`` below)."""

    expr: Expr


@dataclass(frozen=True)
class _AssignmentElement:
    """§4.1 "Assignment element" - ``SET (?var := expr)``. Per §4.2's
    well-formedness conditions, ``var`` must be a variable not already
    bound earlier in the same rule body - enforced by
    ``srl_semantic_checks.py``.

    Private - see ``_FilterElement`` above."""

    var: Variable
    expr: Expr


# §4.1's "Negation element" body (``negation.inner``) is grammatically
# restricted (production 23, BodyBasicNotTriples ::= Filter) to triple
# patterns and filters only - no nested negation or assignment, unlike an
# ordinary rule body. Modeled as its own narrower union rather than reusing
# BodyElement, so a _NegationElement literally cannot hold an illegal member
# by construction.
NegationBodyElement = TriplePattern | _FilterElement


@dataclass(frozen=True)
class _NegationElement:
    """§4.1 "Negation element" - ``NOT DATA? { ... }``. ``data=True`` means
    the negated pattern is matched against the rule set's own DATA graph
    (``GD``) rather than the evaluation graph, per §6.4's ``evalRuleElements``
    pseudocode (``if rElt with DATA: ... GD, GD else ... G, GD``).

    Private - see ``_FilterElement`` above."""

    inner: list[NegationBodyElement] = field(default_factory=list)
    data: bool = False


# §4.1's "Rule element" - the union every rule body member belongs to.
BodyElement = TriplePattern | _FilterElement | _NegationElement | _AssignmentElement


@dataclass(frozen=True)
class _Rule:
    """§4.1 "Rule" - ``head`` + ``body``, optional ``id`` (an IRI naming the
    rule), and ``data`` (match the body's own top-level triple patterns
    against the rule set's DATA graph rather than the base graph - the
    grammar's ``WHERE DATA? { ... }``).

    Private (was ``Rule``, public, until 2026-10-06): no public function or
    method takes or returns a ``Rule`` directly, and it has no public
    methods of its own (``_is_run_once`` below is private too) - the only
    way a caller would ever touch one is by walking ``RuleSet.rules``, an
    inspection/editing concern this API doesn't cover yet. Unlike
    ``TriplePattern`` (needed directly as ``RuleSet.query()``'s own
    ``goal_pattern`` parameter type), nothing requires this type publicly."""

    head: list[TripleTemplate] = field(default_factory=list)
    body: list[BodyElement] = field(default_factory=list)
    data: bool = False
    id: URIRef | None = None

    @property
    def _is_run_once(self) -> bool:
        """§4.1/§4.4: a rule is "run-once" (evaluated exactly once per
        stratum, vs. "general": evaluated to a fixpoint) iff it has an
        assignment element anywhere in its body, or a blank node anywhere
        in its head. (Assignment elements can never occur nested inside a
        negation element - the grammar forbids it, see ``_NegationElement``
        - so a top-level scan of ``body`` already covers every assignment
        element that could exist.) Deliberately not stored as a field -
        it is a pure function of ``head``/``body``, not independent state.

        Private: consulted only by ``srl_eval.py``'s own dependency-graph/
        stratification internals (``_build_dependency_graph``/
        ``_stratify``, both private themselves) - no external caller
        needs this classification directly, same evidentiary standard
        applied to every other SRL internal this session."""
        if any(isinstance(e, _AssignmentElement) for e in self.body):
            return True
        return any(isinstance(t.subject, BNode) or isinstance(t.object, BNode) for t in self.head)


@dataclass(frozen=True)
class _Data:
    """§4.1 "Data block" - ground triples only (the grammar's ``RDFTermData``
    productions admit no variables), giving the DATA graph GD any rule may
    match against instead of, or in addition to, the base graph.

    Private - see ``_FilterElement`` above."""

    triples: list[TriplePattern] = field(default_factory=list)


@dataclass
class RuleSet:
    """§4.1 "Rule set" - ``rules`` + ``data`` blocks + ``imports`` (IRIs of
    other rule sets to inline, §4.5 "Processing Imports"). A "resolved rule
    set" (§4.5) is one whose ``imports`` list is empty because every import
    has already been recursively inlined - not modeled as a separate type
    here, just a ``RuleSet`` with ``imports == []``.
    """

    rules: list[_Rule] = field(default_factory=list)
    data: list[_Data] = field(default_factory=list)
    imports: list[URIRef] = field(default_factory=list)

    def infer(self, base_graph: Graph) -> Graph:
        """Runs this rule set against ``base_graph`` to a fixpoint and
        returns the inferred-triples-only graph (§4.1's ``Infer``) - the
        one real way to run a rule set; ``srl_eval._srl_infer`` is private
        plumbing underneath this, not a second public path. Imported
        locally since ``srl_eval.py`` itself imports this module, so a
        top-level import here would be circular."""
        from . import srl_eval

        return srl_eval._srl_infer(base_graph, self)

    def query(self, base_graph: Graph, goal_pattern: TriplePattern) -> list[dict]:
        """Runs :meth:`infer` then returns every match of
        ``goal_pattern`` against ``base_graph`` union the inferred triples
        (§4.1's ``Query``)."""
        from . import srl_eval

        return srl_eval._srl_query(base_graph, self, goal_pattern)
