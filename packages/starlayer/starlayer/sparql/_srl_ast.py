"""Private module: not directly importable from outside this package.
Only ``RuleSet`` and ``TriplePattern`` are re-exported from ``srl.py``
(e.g. ``srl.RuleSet``), so there's one real path to those two, not two
paths - everything else here (``_Rule``, ``_Data``, ``_FilterElement``,
``_AssignmentElement``, ``_NegationElement``) is private.

Python dataclasses for the SRL abstract syntax tree, mirroring
`WD-sparql12-rl-20260919 <https://www.w3.org/TR/sparql12-rl/>`_ §4.1
"Elements of the Abstract Syntax" (+ its own "Component Notation" table)
field-for-field - field names here are the spec's own attribute names
(``rule.head``, ``ruleset.data``, ``negation.inner``, ...), not invented.

Terms are pyoxigraph terms (``NamedNode``, ``BlankNode``, ``Literal``, ``Variable``). A triple pattern/template's
subject/object may additionally be a ``starlayer.sparql.triple_term.TripleTermNode`` (RDF 1.2 triple term). Expressions
(filters, assignments) are the parser's own ``Node`` trees (``parse_sparql.Node``), or a bare term. A reified triple or
annotation is expanded at parse time into a reifier plus ``rdf:reifies <<( s p o )>>``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pyoxigraph as ox

from .parse_sparql import Node
from .triple_term import TripleTermNode

Variable = ox.Variable

# VarOrRDFTerm (template/pattern position)
Term = ox.Variable | ox.NamedNode | ox.BlankNode | ox.Literal | TripleTermNode

# VarOrIri (predicate position)
PredicateTerm = ox.Variable | ox.NamedNode

Expr = Node | Term


def _is_ox_term(value: Any) -> bool:
    return isinstance(value, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple, ox.Variable))


def _ox_to_srl_term(value: Any) -> Any:
    """A pyoxigraph term as a term of the SRL tree: a ``pyoxigraph.Triple`` becomes a ``TripleTermNode``."""
    if isinstance(value, ox.Triple):
        return TripleTermNode(
            "TripleTerm",
            subject=_ox_to_srl_term(value.subject),
            predicate=_ox_to_srl_term(value.predicate),
            object=_ox_to_srl_term(value.object),
        )
    return value


def _coerce_term(value: Any) -> Any:
    """``value`` as a term of the SRL tree: a pyoxigraph term (a triple becomes a ``TripleTermNode``); anything else comes back unchanged."""
    if isinstance(value, TripleTermNode):
        parts = {k: _coerce_term(v) for k, v in value.f.items()}
        if all(parts[k] is value.f[k] for k in parts):
            return value
        return TripleTermNode("TripleTerm", **parts)
    if _is_ox_term(value):
        return _ox_to_srl_term(value)
    return value


def goal_from_text(text: str, prefixes: dict[str, str]) -> TriplePattern:
    """The triple pattern written in ``text`` (SPARQL syntax, without the ``.``), with ``prefixes`` (prefix to namespace) declared.

    Raises:
        FormatError: (kind "srl") If the text is not exactly one triple pattern, or uses an undeclared prefix.
    """
    from starlayer.errors import FormatError

    from .parse_srl import parse_srl

    header = "".join(f"PREFIX {prefix}: <{namespace}>\n" for prefix, namespace in prefixes.items())
    # the text is parsed as the body of a rule, so it gets the parser, the prefixes and the term syntax of a rule body
    body = parse_srl(f"{header}RULE {{ {text} }} WHERE {{ {text} }}").rules[0].body
    if len(body) != 1 or not isinstance(body[0], TriplePattern):
        message = f"a goal is one triple pattern, such as '?who ex:ancestorOf ex:carol'; got {text!r}"
        raise FormatError(message, kind="srl", why=message, context="goal")
    return body[0]


def check_goal_pattern(goal_pattern: Any) -> TriplePattern:
    """``goal_pattern`` as a ``TriplePattern`` of pyoxigraph terms, raising instead of letting a wrong-typed term match nothing.

    Accepted in each position: pyoxigraph terms (``NamedNode``, ``BlankNode``, ``Literal``, ``Triple``, ``Variable``). The predicate must be an IRI or a variable.

    Raises:
        TypeError: If ``goal_pattern`` is not a ``TriplePattern``, or a position holds something that is not an RDF term or
            variable (a plain ``str``, ``None``, a number), or the predicate is not an IRI or variable.
    """
    if not isinstance(goal_pattern, TriplePattern):
        raise TypeError(f"the goal pattern must be a TriplePattern, not {type(goal_pattern).__name__}")
    parts = []
    for name in ("subject", "predicate", "object"):
        value = _coerce_term(getattr(goal_pattern, name))
        if not isinstance(value, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Variable, TripleTermNode)):
            raise TypeError(f"goal pattern {name} must be an RDF term or variable, not {value!r} ({type(value).__name__})")
        parts.append(value)
    if not isinstance(parts[1], (ox.Variable, ox.NamedNode)):
        raise TypeError(f"goal pattern predicate must be an IRI or a variable, not {parts[1]!r}")
    return TriplePattern(*parts)


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

    def __post_init__(self) -> None:
        """Converts each position to its pyoxigraph (or ``TripleTermNode``) form."""
        # a pyoxigraph triple is stored as a TripleTermNode
        for name in ("subject", "predicate", "object"):
            value = getattr(self, name)
            converted = _coerce_term(value)
            if converted is not value:
                object.__setattr__(self, name, converted)


# §4.1 calls a rule's own head elements "triple templates" - same shape as
# TriplePattern (see its docstring), reused rather than duplicated.
TripleTemplate = TriplePattern


@dataclass(frozen=True)
class _FilterElement:
    """§4.1 "Filter element" - ``filter.expr``, a boolean-valued SPARQL 1.2
    expression. ``expr`` is the parser's ``Node`` tree (or a bare term), produced by
    ``parse_srl`` on SPARQL's own ``Constraint`` / ``Expression`` productions.

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

    var: ox.Variable
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
    """§4.1 "Negation element" - ``NOT GROUND? { ... }``. ``evalground`` is the
    spec's own flag (``negation.evalground``): true (a plain ``NOT { }``) matches
    the negated pattern against the evaluation graph, false (``NOT GROUND { }``)
    against the base graph only, per §6.4's ``evalRuleElements`` pseudocode
    (``if N.evalground: ... G, GD else ... GD, GD``).

    Private - see ``_FilterElement`` above.

    Attributes:
        inner: The negated body elements (triple patterns and filters only
            - see ``NegationBodyElement``).
        evalground: True to match ``inner`` against the evaluation graph (a
            plain ``NOT``); False to match only the base graph (``NOT GROUND``).
    """

    inner: list[NegationBodyElement] = field(default_factory=list)
    evalground: bool = True


@dataclass(frozen=True)
class _Aggregation:
    """§4.1 "Aggregation assignment" - ``?n := COUNT(*)``: ``var`` is the aggregation variable, ``function`` the name of the
    aggregation function (``COUNT``, ``MIN``, ``MAX`` or ``SUM``), ``argument`` the aggregation argument (a variable, or ``None``
    for ``*``, which only ``COUNT`` takes) and ``distinct`` the distinct flag (only ``COUNT`` takes it).

    Private - see ``_FilterElement`` above."""

    var: ox.Variable
    function: str
    argument: ox.Variable | None = None
    distinct: bool = False


# §4.1's group pattern (production [23], GroupPattern ::= triple patterns with Filter | Assignment): like a rule body, without
# negation or a nested group.
GroupBodyElement = TriplePattern | _FilterElement | _AssignmentElement


@dataclass(frozen=True)
class _GroupElement:
    """§4.1 "Group element" - ``GROUP BY ?x { pattern } [ ?n := COUNT(*) ]``. ``keys`` are the group keys (``group.keys``, a set in
    the spec, kept in the order written and without repeats), ``pattern`` the group pattern (``group.pattern``) and
    ``aggregations`` the aggregation assignments (``group.aggregations``, possibly none: ``[]``).

    A rule with a group element is a run-once rule. Private - see ``_FilterElement`` above."""

    keys: list[ox.Variable] = field(default_factory=list)
    pattern: list[GroupBodyElement] = field(default_factory=list)
    aggregations: list[_Aggregation] = field(default_factory=list)


# §4.1's "Rule element" - the union every rule body member belongs to.
BodyElement = TriplePattern | _FilterElement | _NegationElement | _AssignmentElement | _GroupElement


def _triple_term_has_variable(term: Any) -> bool:
    """True if ``term`` is a triple term (at any depth) that contains a variable or a blank node.

    A blank node inside a head triple term is a fresh node per solution, exactly like one in a head triple, so a rule
    holding one is run-once too; without it the rule produced a new triple every pass and ``infer()`` never ended
    (GitHub issue #96).
    """
    if not isinstance(term, TripleTermNode):
        return False
    return any(
        isinstance(part, (ox.Variable, ox.BlankNode)) or _triple_term_has_variable(part)
        for part in (term.get("subject"), term.get("predicate"), term.get("object"))
    )


@dataclass(frozen=True)
class _Rule:
    """§4.1 "Rule" - ``head`` + ``body``, optional ``id`` (an IRI naming the
    rule), and ``evalground`` (the spec's own ``rule.evalground``: true matches the
    body's triple patterns against the evaluation graph; false matches the base
    graph only - the grammar's ``WHERE GROUND { ... }``).

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
    evalground: bool = True
    id: ox.NamedNode | None = None

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
        if any(isinstance(e, (_AssignmentElement, _GroupElement)) for e in self.body):
            return True
        return any(
            isinstance(t.subject, ox.BlankNode)
            or isinstance(t.object, ox.BlankNode)
            or _triple_term_has_variable(t.subject)
            or _triple_term_has_variable(t.object)
            for t in self.head
        )


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
    id: ox.NamedNode | None
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
    imports: list[ox.NamedNode] = field(default_factory=list)
    prefixes: dict[str, str] = field(default_factory=dict, compare=False, repr=False)
    """The ``PREFIX`` declarations of the text this rule set was parsed from (prefix -> namespace), empty for one built by hand.
    Informative only: names in the rules are already absolute IRIs, and it takes no part in equality. ``infer()`` on an
    Oxigraph graph gives these prefixes to the result."""

    @property
    def is_resolved(self) -> bool:
        """True when no ``IMPORTS`` are left to resolve (``imports`` is empty). A rule set with imports is incomplete: the checks made when
        it was parsed covered only the rules in its own text, until :func:`~starlayer.sparql.srl.resolve_imports` resolves it."""
        return not self.imports

    def _with_imports_resolved(self, imports_loader) -> RuleSet:
        """This rule set with its ``IMPORTS`` resolved by ``imports_loader``, or ``self``
        when no loader is given (then ``infer()`` rejects any imports, as §4.5 requires
        of a processor that does not support them)."""
        if imports_loader is None or not self.imports:
            return self
        from . import srl

        return srl.resolve_imports(self, imports_loader)

    def plan(self, *, imports_loader: Any | None = None) -> RulePlan:
        """Shows how this rule set would be evaluated, without running it:
        the strata in evaluation order and the rule dependency graph they
        were computed from (§4.3.2 and §4.4.2 of the spec). Rules are
        identified by their position in ``self.rules``.

        Useful for seeing why a rule fires in a later stratum than another,
        which matters with negation, and for checking that a rule set
        stratifies before running it. ``IMPORTS`` are not resolved here;
        ``infer()`` rejects them.

        Args:
            imports_loader: Resolves ``IMPORTS`` first, as for :meth:`infer`; the plan
                then covers the imported rules too. Without one, imports are ignored.

        Returns:
            The :class:`RulePlan`.

        Raises:
            StratificationError: If a recursive dependency involves a
                negation, so no valid evaluation order exists (§4.4.1).
        """
        from . import srl, srl_eval

        self = self._with_imports_resolved(imports_loader)

        edges = srl_eval._build_dependency_graph(self)
        layers = srl_eval._stratify(self)
        index = {id(rule): i for i, rule in enumerate(self.rules)}

        def plan_rule(rule: _Rule) -> PlanRule:
            return PlanRule(index[id(rule)], rule.id, srl._rule_text(rule, {}))

        return RulePlan(
            strata=[
                PlanStratum(number, [plan_rule(r) for r in once], [plan_rule(r) for r in general])
                for number, (once, general) in enumerate(layers)
            ],
            edges=[PlanEdge(index[id(e.source)], index[id(e.target)], e.label) for e in edges],
        )

    def infer(
        self,
        base_graph: Any,
        *,
        inference: Any | None = None,
        schema: Any | None = None,
        imports_loader: Any | None = None,
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
        ``docs/design/sparql_srl_object_model_design.md`` for
        the full design discussion.

        Args:
            base_graph: The graph to run the rule set against.
            inference: An entailment regime IRI (or iterable of them, the
                same ``ENTAILMENT.*`` vocabulary ``StarShaclProcessor``/
                ``StarLayerGraph`` already use), applied to ``base_graph``
                (via ``base_graph.infer(entailment=inference, mode="full")``)
                before the rule set runs against it - the same "entailment
                feeds inference" relationship SHACL's own
                ``sh:entailment``-before-rules already has. ``None``
                (default) runs against ``base_graph`` unchanged.
            imports_loader: ``loader(iri) -> str | RuleSet``, used to read the
                documents named by this rule set's ``IMPORTS`` (see
                :func:`starlayer.sparql.srl.resolve_imports`). There is no default
                loader, because reading a document has security implications; without
                one, a rule set that has imports is rejected with
                ``SRLImportsNotSupportedError``.
            schema: A ``starlayer.shacl.StarShaclProcessor`` instance, or a
                bare SHACL shapes graph, to validate the inferred result
                against. A bare shapes graph is wrapped in a throwaway
                ``StarShaclProcessor(shacl_graph=schema)`` first; an already-
                constructed ``StarShaclProcessor`` is used as-is, so its own
                bound ``ont_graph``/``inference`` are honored too.
                ``None`` (default) skips validation entirely.

        Returns:
            The inferred-triples-only graph (a plain graph object), when
            ``schema`` is omitted - the unchanged, pre-existing return
            shape. When ``schema`` is given, a
            a ``starlayer.shacl.results.CheckedInferenceResult`` instead: a
            ``RulesResult`` (``inferred_graph``) that also has ``validation``,
            the report of the base data together with the inferred triples
            against ``schema`` (``apply_rules()`` itself validates nothing).
        """
        from . import srl_eval

        original_graph = base_graph
        base_graph = srl_eval.flatten_dataset(base_graph)
        if inference is not None:
            base_graph = base_graph.infer(entailment=inference, mode="full")

        inferred = srl_eval._srl_infer(base_graph, self._with_imports_resolved(imports_loader))

        if schema is None:
            return self._with_own_prefixes(self._with_prefixes_of(inferred, original_graph))

        from starlayer.shacl import StarShaclProcessor
        from starlayer.shacl.results import CheckedInferenceResult

        resolved_schema = schema if isinstance(schema, StarShaclProcessor) else StarShaclProcessor(shacl_graph=schema)
        # the evaluation graph (base plus inferred): validating the inferred
        # triples alone reported violations for constraints the base graph satisfies (GitHub issue #96)
        # (an StarLayerGraph with no prefixes of its own, so the report does not carry an old graph's 29 default prefixes)
        from starlayer.shacl.engine.graphs import new_graph

        evaluation = new_graph()
        evaluation.extend(srl_eval._default_quads(base_graph))
        evaluation.extend(srl_eval._default_quads(inferred))
        validation = resolved_schema.validate(data_graph=evaluation)
        result = CheckedInferenceResult(inferred_graph=self._with_prefixes_of(inferred, original_graph), validation=validation)
        self._with_own_prefixes(result.inferred_graph)
        return result

    @staticmethod
    def _with_prefixes_of(inferred: Any, original: Any) -> Any:
        """Bind the prefixes of the Oxigraph graph the rules ran on to the inferred graph (a prefix it already has stays)."""
        for prefix, namespace in dict(getattr(original, "prefixes", {})).items():
            inferred.bind(prefix, namespace, override=False)
        return inferred

    def _with_own_prefixes(self, graph: Any) -> Any:
        """Bind this rule set's own ``PREFIX`` declarations on an ``StarLayerGraph`` result (the input graph's prefixes are already
        there); a prefix the input graph binds differently is left as the input has it."""
        for prefix, namespace in self.prefixes.items():
            graph.bind(prefix, str(namespace), override=False)
        return graph

    def _goal_pattern(self, goal: Any, graph: Any) -> TriplePattern:
        """``goal`` (SPARQL text, or a ``TriplePattern``) as a checked ``TriplePattern``; a prefix in text is the graph's, else this
        rule set's."""
        if isinstance(goal, str):
            prefixes = {**self.prefixes, **{str(k): str(v) for k, v in dict(getattr(graph, "prefixes", {})).items()}}
            goal = goal_from_text(goal, prefixes)
        return check_goal_pattern(goal)

    def materialize(self, base_graph: Any, *, inference: Any | None = None, imports_loader: Any | None = None):
        """Runs this rule set on ``base_graph`` once and keeps what it derives, as a :class:`~starlayer.sparql.srl.Materialization`.

        Where ``query()`` runs the rules each time, a materialization answers any number of goals from the kept triples
        (``materialization.query(goal)``), and ``materialization.inferred`` is the derived graph, the same as ``infer()``. It does
        not follow changes to ``base_graph``: ``stale`` tells you it has gone out of date and ``refresh()`` runs the rules again.

        Args:
            base_graph: The graph to run the rule set against.
            inference: As for :meth:`infer`.
            imports_loader: As for :meth:`infer`.
        """
        from . import srl_eval

        return srl_eval.Materialization(self, base_graph, inference=inference, imports_loader=imports_loader)

    def query(
        self,
        base_graph: Any,
        goal_pattern: str,
        *,
        inference: Any | None = None,
        imports_loader: Any | None = None,
    ) -> list[dict]:
        """Runs :meth:`infer` then returns every match of
        ``goal_pattern`` against ``base_graph`` union the inferred triples
        (§4.1's ``Query``).

        Args:
            base_graph: The graph to run the rule set against.
            goal_pattern: One triple pattern in SPARQL syntax, such as ``"?who ex:ancestorOf ex:carol"``, to match against the union
                of ``base_graph`` and the inferred triples. A prefix is the graph's own, else this rule set's. (A ``TriplePattern``
                is accepted too.)
            inference: Same meaning as :meth:`infer`'s own ``inference=`` -
                applied to ``base_graph`` before the rule set runs. There
                is no ``schema=`` here - this method returns rows, not a
                graph, so there is nothing to validate.
            imports_loader: Same meaning as :meth:`infer`'s own ``imports_loader=``.

        Returns:
            One ``dict[Variable, term]`` solution per match: the keys are ``pyoxigraph.Variable``, as in the wrapper's own query
            results (``result.vars``), and the values pyoxigraph terms.

        Raises:
            FormatError: (kind "srl") If ``goal_pattern`` text is not exactly one triple pattern, or uses an undeclared prefix.
            TypeError: If a position of a ``TriplePattern`` goal is not an RDF term or variable (nothing is silently matched).
        """
        from . import srl_eval

        goal_pattern = self._goal_pattern(goal_pattern, base_graph)
        base_graph = srl_eval.flatten_dataset(base_graph)
        if inference is not None:
            base_graph = base_graph.infer(entailment=inference, mode="full")

        rows = srl_eval._srl_query(base_graph, self._with_imports_resolved(imports_loader), goal_pattern)
        import pyoxigraph as ox

        return [{ox.Variable(var.value): value for var, value in row.items()} for row in rows]
