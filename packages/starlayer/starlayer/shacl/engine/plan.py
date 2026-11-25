"""The plan: shapes read once from a shapes graph into plain data, built lazily per shape node.

``Shape`` and ``Path`` are plain frozen data (dataclasses of terms and tuples) so a plan can be serialized for a Rust
executor later. ``Plan.shape(node)`` builds a shape on first use, so shapes referenced from ``sh:node``, ``sh:not``,
``sh:and`` etc. need no pre-pass.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from starlayer.shacl.engine.naming import add_where
from starlayer.shacl.engine.terms import RDF, SH, NamedNode, engine_view, text

URIRef = NamedNode  # type alias kept for the annotations below
Term = Any


class ShapeError(ValueError):
    """The base of the shapes-graph errors: the shapes graph, its rules or its setup is wrong or asks for something unsupported (the
    W3C suite's ``sht:Failure`` cases), found by anyone. Raised as ``ShapeCompileError`` (the engine cannot read or compile it) or
    ``MetaShaclError`` (the meta check found it); catch ``ShapeError`` for either."""


class ShapeCompileError(ShapeError):
    """The engine itself cannot read or compile the shapes graph, its rules or its setup: a malformed shape, path, constraint
    parameter, query or rule, an unsupported construct, or an ``owl:imports`` it cannot resolve. Not a ``MetaShaclError``, which the
    meta check (shacl_shacl) raises."""


class ExecutionError(Exception):
    """The shapes graph is fine and running it failed. A plain ``Exception``, not a ``ValueError``: the engine's narrow
    ``except ValueError`` clauses (and a caller's) must not swallow it.

    One class; ``kind`` says what failed (a plain string, one of ``KINDS``):

    * ``"rule"``: a rule failed while running, ``max_iterations`` or ``max_triples`` was exceeded, or the rule set failed as a whole.
    * ``"expression"``: a node expression cannot be evaluated (SHACL 1.2 Node Expressions 3.2), an error and not an empty result.
    * ``"nesting"``: the validation path or node expressions nest deeper than the limit (a cyclic expression, a recursive function).
    * ``"recursion"``: a shape reaches itself on a focus node through ``sh:not`` (a cycle in the data).
    * ``"constraint-query"``: a ``sh:sparql`` constraint query reported ``?failure true``.
    * ``"ambiguous"``: a lookup that must give exactly one result gave several.
    * ``"internal"``: the engine failed an assertion about its own result, a bug in StarLayer to be reported.

    ``str(error)`` is the message. Catch ``ExecutionError`` and test ``error.kind``; inside the engine, ``only_kind`` does the test."""

    KINDS = ("rule", "expression", "nesting", "recursion", "constraint-query", "ambiguous", "internal")

    def __init__(self, message: str, *, kind: str) -> None:
        if kind not in self.KINDS:
            raise ValueError(f"unknown ExecutionError kind {kind!r}; one of {', '.join(self.KINDS)}")
        super().__init__(message)
        self.kind = kind

    def __reduce__(self) -> Any:  # a keyword-only ``kind`` must survive pickle and copy
        return (_rebuild_execution_error, (self.args[0] if self.args else "", self.kind))


def _rebuild_execution_error(message: str, kind: str) -> ExecutionError:
    return ExecutionError(message, kind=kind)


def only_kind(error: ExecutionError, *kinds: str) -> None:
    """For an ``except ExecutionError as error`` clause that handles only some kinds: returns when ``error.kind`` is one of ``kinds``
    and raises ``error`` again otherwise, so a clause that means "no value" cannot swallow a rule, nesting or recursion failure."""
    if error.kind not in kinds:
        raise error


def reject_removed_constructs(graph: Any) -> None:
    """SHACL 1.2 SPARQL-Related Features, Appendix F: "SPARQL-based targets (``sh:target`` with ``sh:SPARQLTarget`` and
    ``sh:SPARQLTargetType``) are no longer defined", and ``sh:SPARQLFunction`` (SHACL Advanced Features) is replaced by functions
    declared on node expressions. The W3C vocabulary file still lists the terms, so the vocabulary cannot tell them from live
    ones; a shapes graph that uses them would otherwise validate with those parts silently doing nothing, so it is refused."""
    found = [(f"sh:target on {text(s)}") for s, _p, _o in graph.triples((None, SH.target, None))]
    for cls, name in ((SH.SPARQLTarget, "sh:SPARQLTarget"), (SH.SPARQLTargetType, "sh:SPARQLTargetType"), (SH.SPARQLFunction, "sh:SPARQLFunction")):
        found += [f"{text(s)} is a {name}" for s in graph.subjects(RDF.type, cls)]
    if found:
        shown = "; ".join(found[:5]) + (f"; and {len(found) - 5} more" if len(found) > 5 else "")
        raise ShapeCompileError(
            "the shapes graph uses SHACL Advanced Features constructs that SHACL 1.2 no longer defines (SHACL SPARQL-Related Features, "
            f"Appendix F): {shown}. Use sh:targetNode with a node expression, for example sh:targetNode [ sh:select \"...\" ] (section 6.1), "
            "and sh:ListParameterExpressionFunction for a function (section 7)"
        )


_SEVERITY_RANK = {SH.Violation: 2, SH.Warning: 1, SH.Info: 0}


def most_severe(severities: Any) -> Term:
    """The most severe of the given severities (``None`` entries ignored; ``None`` if there are none). Violation, Warning,
    Info; any other severity IRI ranks below Info. A tie keeps the first."""
    best = None
    for s in severities:
        if s is not None and (best is None or _SEVERITY_RANK.get(s, -1) > _SEVERITY_RANK.get(best, -1)):
            best = s
    return best


@dataclass(frozen=True)
class Path:
    """A SHACL property path. ``kind`` is one of: pred, inverse, seq, alt, zero_or_more, one_or_more, zero_or_one.
    ``pred`` carries ``iri``; the others carry ``args`` (one sub-path, or several for seq/alt). ``node`` is the path's
    term in the shapes graph (reported as ``sh:resultPath``)."""

    kind: str
    iri: Term = None
    args: tuple[Path, ...] = ()
    node: Term = None


@dataclass(frozen=True)
class Shape:
    """One SHACL shape read from the shapes graph into a frozen record of terms and tuples."""

    node: Term
    is_property: bool
    path: Path | None
    targets: tuple[tuple[URIRef, Term], ...]  # (target predicate, target value)
    params: dict[URIRef, tuple[Term, ...]]  # every sh: parameter predicate present -> its values, in graph order
    property_shapes: tuple[Term, ...]
    severity: Term
    deactivated: bool
    messages: tuple[Term, ...]
    values: tuple[Term, ...] = ()  # sh:values node expressions (extra value nodes of a property shape)
    default_values: tuple[Term, ...] = ()  # sh:defaultValue node expressions (used only if there are no other value nodes)
    # (parameter predicate, value) -> {'deactivated': bool, 'severity': Term|None, 'messages': tuple, 'exprs': tuple}, read from RDF 1.2 reifiers of the
    # shape's own triples (`sh:datatype xsd:boolean {| sh:deactivated true |}`); sh:property uses the same key shape.
    annotations: dict[tuple[Term, Term], dict[str, Any]] = field(default_factory=dict)
    deactivated_exprs: tuple[Term, ...] = ()  # sh:deactivated values that are node expressions, evaluated per focus node


@dataclass
class Plan:
    """A shapes graph plus its lazily built ``Shape`` objects and constraint components."""

    shapes_graph: Any
    _cache: dict[Term, Shape] = field(default_factory=dict)
    _components: list | None = None
    sparql_cache: dict = field(default_factory=dict)  # prefix declarations and checked queries, keyed by their inputs

    def __post_init__(self) -> None:
        """Normalise the shapes graph to an engine-term view and refuse one using unsupported constructs.

        The refused constructs are sh:target, sh:SPARQLTarget, sh:SPARQLTargetType and sh:SPARQLFunction."""
        self.shapes_graph = engine_view(self.shapes_graph, "shapes graph")  # the seam: rdflib / StarLayer graphs get an engine-term view
        reject_removed_constructs(self.shapes_graph)

    def components(self) -> list:
        """Built-in components plus the SPARQL-based constraint components declared in the shapes graph (built once)."""
        if self._components is None:
            from starlayer.shacl.engine.components.registry import static_specs
            from starlayer.shacl.engine.components.sparql_components import (
                declared_components,
            )

            self._components = static_specs() + declared_components(self)
        return self._components

    def shape(self, node: Term) -> Shape:
        """The ``Shape`` for a node, built on first request and cached."""
        if node not in self._cache:
            from starlayer.shacl.engine.builder import build_shape

            extra = {p for spec in self.components() for p in spec.predicates}
            try:
                self._cache[node] = build_shape(self.shapes_graph, node, extra)
            except ShapeError as error:
                raise add_where(error, self.shapes_graph, node) from None
        return self._cache[node]

    def compile(self) -> Plan:
        """Read every shape the shapes graph declares, and every shape they refer to, and check each constraint's parameters, so
        a malformed shapes graph raises ``ShapeError`` here rather than when a focus node first reaches the constraint.

        Builds what ``run()`` builds (all declared shapes) plus the shapes reached through ``sh:property`` and through the
        parameters of the components that name shapes (``ComponentSpec.check`` returns them). A shape deactivated by the literal
        ``true``, and a constraint or ``sh:property`` link deactivated that way, are not checked or followed, as validation
        never reaches them. What stays evaluation-time: node expressions, SPARQL text, target expressions, and parameter
        errors of components that have no ``check`` (SPARQL-based components' validators). Returns ``self``."""
        from starlayer.shacl.engine.executor import constraints_of

        queue = list(self.all_shape_nodes())
        seen: set = set()
        while queue:
            node = queue.pop()
            if node in seen:
                continue
            seen.add(node)
            shape = self.shape(node)
            if shape.deactivated:
                continue
            for ps in shape.property_shapes:
                link = shape.annotations.get((SH.property, ps))
                if not (link and link["deactivated"]):
                    queue.append(ps)
            for spec, present, _sev, _msgs, _exprs in constraints_of(self, shape):
                if spec.check is not None:
                    try:
                        queue.extend(spec.check(self.shapes_graph, shape, present) or ())
                    except ShapeError as error:
                        raise add_where(error, self.shapes_graph, node) from None
        return self

    def all_shape_nodes(self) -> list[Term]:
        """The shape nodes the shapes graph declares, by shape type or by having a target, without duplicates."""
        from starlayer.shacl.engine.builder import declared_shape_nodes

        return declared_shape_nodes(self.shapes_graph)


def is_shape_type(graph: Any, node: Term) -> bool:
    """Whether the node is explicitly typed sh:NodeShape, sh:PropertyShape or sh:Shape (subclasses not followed)."""
    return any(t in (SH.NodeShape, SH.PropertyShape, SH.Shape) for t in graph.objects(node, RDF.type))
