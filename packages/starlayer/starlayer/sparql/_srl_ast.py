"""Private module: not directly importable from outside this package.
Only ``RuleSet`` and ``TriplePattern`` are re-exported from ``srl.py``
(e.g. ``srl.RuleSet``), so there's one real path to those two, not two
paths - everything else here (``_Rule``, ``_Data``, ``_FilterElement``,
``_AssignmentElement``, ``_NegationElement``) is private: no public
function or method requires any of them directly, and the only way a
caller would ever touch one is by walking ``RuleSet.rules``/
``Rule.head``/``Rule.body``, an inspection/editing concern this API
doesn't cover yet.

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
from typing import Any

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

    Attributes:
        subject: The triple's subject term.
        predicate: The triple's predicate term (never a Literal, BNode,
            or triple term - see ``PredicateTerm``).
        object: The triple's object term.
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
    reachable by walking ``Rule.body``, the same test applied to
    ``_AssignmentElement``/``_NegationElement``/``_Data``/``_Rule`` below."""

    expr: Expr


@dataclass(frozen=True)
class _AssignmentElement:
    """§4.1 "Assignment element" - ``SET (?var := expr)``. Per §4.2's
    well-formedness conditions, ``var`` must be a variable not already
    bound earlier in the same rule body - enforced by
    ``srl_semantic_checks.py``.

    Private - see ``_FilterElement`` above.

    Attributes:
        var: The variable being bound.
        expr: The expression assigned to ``var``.
    """

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

    Private - see ``_FilterElement`` above.

    Attributes:
        inner: The negated body elements (triple patterns and filters only
            - see ``NegationBodyElement``).
        data: Whether ``inner`` matches against the DATA graph rather than
            the evaluation graph.
    """

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

    Private: the test applied project-wide to every SRL AST type is
    whether any public function or method signature requires this type
    directly. No public function or method takes or returns a ``Rule``,
    and it has no public methods of its own (``_is_run_once`` below is
    private too) - the only way a caller would ever touch one is by
    walking ``RuleSet.rules``, an inspection/editing concern this API
    doesn't cover yet. ``TriplePattern`` is the one type that passes this
    test (it's ``RuleSet.query()``'s own ``goal_pattern`` parameter type,
    so a caller must be able to construct one) - nothing requires
    ``_Rule`` publicly."""

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
        needs this classification directly.

        Returns:
            True if this rule is run-once; False if it is general.
        """
        if any(isinstance(e, _AssignmentElement) for e in self.body):
            return True
        return any(isinstance(t.subject, BNode) or isinstance(t.object, BNode) for t in self.head)


@dataclass(frozen=True)
class _Data:
    """§4.1 "Data block" - ground triples only (the grammar's ``RDFTermData``
    productions admit no variables), giving the DATA graph GD any rule may
    match against instead of, or in addition to, the base graph.

    Private - see ``_FilterElement`` above.

    Attributes:
        triples: The block's ground triples.
    """

    triples: list[TriplePattern] = field(default_factory=list)


@dataclass(frozen=True)
class PlanRule:
    """One rule as it appears in a :class:`RulePlan`.

    Attributes:
        index: The rule's position in ``RuleSet.rules`` (0-based).
        id: The rule's IRI, or ``None`` if it has none.
        text: The rule rendered as SRL text (full IRIs, no prefixes).
    """

    index: int
    id: URIRef | None
    text: str


@dataclass(frozen=True)
class PlanStratum:
    """One stratum of a :class:`RulePlan`: the rules evaluated together.

    Attributes:
        number: The stratum's position in evaluation order (0-based).
        run_once: Rules evaluated exactly once in this stratum.
        general: Rules evaluated to a fixpoint in this stratum.
    """

    number: int
    run_once: list[PlanRule]
    general: list[PlanRule]


@dataclass(frozen=True)
class PlanEdge:
    """A dependency between two rules: ``source``'s body reads what
    ``target``'s head can produce, so ``target`` must be evaluated first (or
    in the same stratum).

    Attributes:
        source: ``PlanRule.index`` of the rule that depends on ``target``.
        target: ``PlanRule.index`` of the rule it depends on.
        label: ``"open"`` (a positive dependency) or ``"closed"`` (a
            negation, or any dependency of a run-once rule), which forces
            ``source`` into a later stratum than ``target``.
    """

    source: int
    target: int
    label: str


@dataclass(frozen=True)
class RulePlan:
    """How a rule set will be evaluated, from :meth:`RuleSet.plan` -
    nothing is run to produce it.

    Attributes:
        strata: The strata in evaluation order.
        edges: The rule dependency graph the strata were computed from.
    """

    strata: list[PlanStratum]
    edges: list[PlanEdge]


@dataclass
class RuleSet:
    """§4.1 "Rule set" - ``rules`` + ``data`` blocks + ``imports`` (IRIs of
    other rule sets to inline, §4.5 "Processing Imports"). A "resolved rule
    set" (§4.5) is one whose ``imports`` list is empty because every import
    has already been recursively inlined - not modeled as a separate type
    here, just a ``RuleSet`` with ``imports == []``.

    Attributes:
        rules: The rule set's rules.
        data: The rule set's DATA blocks.
        imports: IRIs of other rule sets to inline.
    """

    rules: list[_Rule] = field(default_factory=list)
    data: list[_Data] = field(default_factory=list)
    imports: list[URIRef] = field(default_factory=list)

    def plan(self) -> RulePlan:
        """Shows how this rule set would be evaluated, without running it:
        the strata in evaluation order and the rule dependency graph they
        were computed from (§4.3.2 and §4.4.2 of the spec). Rules are
        identified by their position in ``self.rules``.

        Useful for seeing why a rule fires in a later stratum than another,
        which matters with negation, and for checking that a rule set
        stratifies before running it. ``IMPORTS`` are not resolved here;
        ``infer()`` rejects them.

        Returns:
            The :class:`RulePlan`.

        Raises:
            StratificationError: If a recursive dependency involves a
                negation, so no valid evaluation order exists (§4.4.1).
        """
        from . import srl, srl_eval

        edges = srl_eval._build_dependency_graph(self)
        layers = srl_eval._stratify(self)
        index = {id(rule): i for i, rule in enumerate(self.rules)}

        def plan_rule(rule: _Rule) -> PlanRule:
            return PlanRule(index[id(rule)], rule.id, srl._rule_text(rule, None))

        return RulePlan(
            strata=[
                PlanStratum(number, [plan_rule(r) for r in once], [plan_rule(r) for r in general])
                for number, (once, general) in enumerate(layers)
            ],
            edges=[PlanEdge(index[id(e.source)], index[id(e.target)], e.label) for e in edges],
        )

    def infer(
        self,
        base_graph: Graph,
        *,
        inference: Any | None = None,
        schema: Any | None = None,
    ):
        """Runs this rule set against ``base_graph`` to a fixpoint and
        returns the inferred-triples-only graph (§4.1's ``Infer``) - the
        one real way to run a rule set; ``srl_eval._srl_infer`` is private
        plumbing underneath this, not a second public path. Imported
        locally since ``srl_eval.py`` itself imports this module, so a
        top-level import here would be circular.

        ``inference``/``schema`` are per-call, not bound on this dataclass
        itself - ``RuleSet`` is also the value ``ruleset_to_tree()``/
        ``tree_to_ruleset()`` round-trip to/from RDF (``srl.py``), and a
        stored "bound schema"/"bound entailment regime" field would either
        leak into that encoding or need excluding from it for no benefit
        over a plain per-call argument. See
        ``packages/starlayer/docs/sparql_srl_object_model_design.md`` for
        the full design discussion.

        Args:
            base_graph: The graph to run the rule set against.
            inference: An entailment regime IRI (or iterable of them, the
                same ``ENTAILMENT.*`` vocabulary ``StarShaclSchema``/
                ``StarLayerGraph`` already use), applied to ``base_graph``
                (via ``base_graph.infer(entailment=inference, mode="full")``)
                before the rule set runs against it - the same "entailment
                feeds inference" relationship SHACL's own
                ``sh:entailment``-before-rules already has. ``None``
                (default) runs against ``base_graph`` unchanged.
            schema: A ``starlayer.shacl.StarShaclSchema`` instance, or a
                bare SHACL shapes graph, to validate the inferred result
                against. A bare shapes graph is wrapped in a throwaway
                ``StarShaclSchema(shacl_graph=schema)`` first; an already-
                constructed ``StarShaclSchema`` is used as-is, so its own
                bound ``ont_graph``/``inference`` are honored too.
                ``None`` (default) skips validation entirely.

        Returns:
            The inferred-triples-only graph (a plain graph object), when
            ``schema`` is omitted - the unchanged, pre-existing return
            shape. When ``schema`` is given, a
            ``starlayer.shacl.RulesResult(inferred_graph=..., validation=...)``
            instead - the same result shape ``StarShaclSchema.apply_rules()``
            already returns for the identical underlying concept (inferred
            triples plus a validation of them), reused rather than
            duplicated.
        """
        from . import srl_eval

        if inference is not None:
            base_graph = base_graph.infer(entailment=inference, mode="full")

        inferred = srl_eval._srl_infer(base_graph, self)

        if schema is None:
            return inferred

        from starlayer.shacl import RulesResult, StarShaclSchema

        resolved_schema = schema if isinstance(schema, StarShaclSchema) else StarShaclSchema(shacl_graph=schema)
        validation = resolved_schema.validate(data_graph=inferred)
        return RulesResult(inferred_graph=inferred, validation=validation)

    def query(
        self,
        base_graph: Graph,
        goal_pattern: TriplePattern,
        *,
        inference: Any | None = None,
    ) -> list[dict]:
        """Runs :meth:`infer` then returns every match of
        ``goal_pattern`` against ``base_graph`` union the inferred triples
        (§4.1's ``Query``).

        Args:
            base_graph: The graph to run the rule set against.
            goal_pattern: The triple pattern to match against the union of
                ``base_graph`` and the inferred triples.
            inference: Same meaning as :meth:`infer`'s own ``inference=`` -
                applied to ``base_graph`` before the rule set runs. There
                is no ``schema=`` here - this method returns rows, not a
                graph, so there is nothing to validate.

        Returns:
            One ``dict[Variable, term]`` solution per match.
        """
        from . import srl_eval

        if inference is not None:
            base_graph = base_graph.infer(entailment=inference, mode="full")

        return srl_eval._srl_query(base_graph, self, goal_pattern)
