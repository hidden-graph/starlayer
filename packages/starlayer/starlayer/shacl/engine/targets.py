"""Shape discovery and targets (SHACL 1.2 Core).

``shape_targets`` reads the target declarations of one shape (including the implicit class target of a node that is both
a shape and a class, and the data-graph ``sh:shape`` link as the pseudo target ``(sh:shape, shape)``). ``focus_nodes`` resolves them against the data graph: ``rdfs:subClassOf*`` expansion for class
targets uses the data graph only. ``sh:targetWhere`` takes a shape; its focus nodes are the data graph nodes that
conform to it, decided by the ``conforms(shape_node, node)`` callable the executor passes.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from starlayer.shacl.engine import xsd_values as xv
from starlayer.shacl.engine.plan import SH, ShapeError, Term
from starlayer.shacl.engine.terms import OWL, RDF, RDFS, XSD, BlankNode, Literal, text
from starlayer.shacl.engine.terms import NamedNode as URIRef

_TARGET_PREDICATES = (SH.targetNode, SH.targetClass, SH.targetSubjectsOf, SH.targetObjectsOf, SH.targetWhere)
_SHAPE_TYPES = (SH.NodeShape, SH.PropertyShape, SH.Shape, SH.ShapeClass)
_CLASS_TYPES = (RDFS.Class, OWL.Class, SH.ShapeClass)


def _types(graph: Any, node: Term) -> set:
    """The SHACL types of ``node`` in ``graph``: ``rdf:type`` followed by ``rdfs:subClassOf*`` (Core 3.1.3.3, "SHACL instance")."""
    seen = set(graph.objects(node, RDF.type))
    queue = list(seen)
    while queue:
        for parent in graph.objects(queue.pop(), RDFS.subClassOf):
            if parent not in seen:
                seen.add(parent)
                queue.append(parent)
    return seen


def _is_implicit_class_target(graph: Any, node: Term) -> bool:
    types = _types(graph, node)
    return any(t in types for t in _SHAPE_TYPES) and any(t in types for t in _CLASS_TYPES)


def shape_targets(graph: Any, node: Term) -> list[tuple[URIRef, Term]]:
    """The (target predicate, value) declarations of one shape, ready for ``focus_nodes``.

    The result always ends with the pseudo target ``(sh:shape, node)``, and a shape that is also a class gets an
    implicit ``sh:targetClass`` entry for itself. Raises ``ShapeError`` when a ``sh:targetWhere`` value is a literal.
    """
    out: list[tuple[URIRef, Term]] = []
    for pred in _TARGET_PREDICATES:
        for v in graph.objects(node, pred):
            if pred == SH.targetWhere and isinstance(v, Literal):
                raise ShapeError(f"{text(node)}: the value of sh:targetWhere must be a shape, not a literal")
            out.append((pred, v))
    if _is_implicit_class_target(graph, node) and (SH.targetClass, node) not in out:
        out.append((SH.targetClass, node))
    # SHACL 1.2: a data graph node can name its shapes with ``sh:shape``; resolved against the data graph.
    out.append((SH.shape, node))
    return out


def declared_shape_nodes(graph: Any) -> list[Term]:
    """Every node of a shapes graph that is typed as a shape or carries a target declaration, each once."""
    nodes: dict = {}
    for typ in _SHAPE_TYPES:
        for sub in _class_closure(graph, typ):  # a SHACL instance of a shape type includes instances of its subclasses
            for s in graph.subjects(RDF.type, sub):
                nodes.setdefault(s, None)
    for pred in _TARGET_PREDICATES:
        for s in graph.subjects(pred, None):
            nodes.setdefault(s, None)
    return list(nodes)


def _is_expression(shapes: Any, node: Term) -> bool:
    from starlayer.shacl.engine.expressions import is_expression

    return is_expression(shapes, node)


def _class_closure(data: Any, cls: Term, subclasses_of: Callable[[Term], Iterable[Term]] | None = None) -> list[Term]:
    """``cls`` and all its rdfs:subClassOf descendants in the data graph (cycle-safe). ``subclasses_of`` replaces the lookup of
    the direct subclasses (``Context.subclasses_of``: the data graph, and the shapes graph with ``subClassOf`` in the shapes graph)."""
    if subclasses_of is None:
        def subclasses_of(c: Term) -> Iterable[Term]:
            return data.subjects(RDFS.subClassOf, c)
    seen: dict = {cls: None}
    queue = [cls]
    while queue:
        c = queue.pop()
        for sub in subclasses_of(c):
            if sub not in seen:
                seen[sub] = None
                queue.append(sub)
    return list(seen)


def _all_nodes(data: Any) -> list[Term]:
    nodes: dict = {}
    for s, _p, o in data.triples((None, None, None)):
        nodes.setdefault(s, None)
        nodes.setdefault(o, None)
    return list(nodes)


_MAX_CONDITION_DEPTH = 8


def _is_off(shape: Any) -> bool:
    """True when the shape, or any of its constraints, could be switched off (``sh:deactivated``, as a literal, an expression or
    on a constraint's reifier): then no condition is taken from it."""
    return bool(shape.deactivated or shape.deactivated_exprs or any(a.get("deactivated") or a.get("exprs") for a in shape.annotations.values()))


def _sparql_text(term: Term) -> str:
    """An IRI or literal as SPARQL writes it (pyoxigraph's ``str`` is the ``<iri>`` / N-Triples form)."""
    return str(term)  # str-ok: the SPARQL form of an IRI or literal


def _int_param(shape: Any, pred: Term) -> int | None:
    values = shape.params.get(pred, ())
    if len(values) == 1 and isinstance(values[0], Literal):
        try:
            return int(str(values[0].value)) if values[0].datatype == XSD.integer else None
        except ValueError:
            return None
    return None


_RANGE_OPERATORS = ((SH.minInclusive, ">="), (SH.minExclusive, ">"), (SH.maxInclusive, "<="), (SH.maxExclusive, "<"))
_INT64 = 2**63


def _numeric_bound(shape: Any, pred: Term) -> str | None:
    """The SPARQL text of the one numeric parameter of a range constraint, or ``None`` when there is not exactly one, it is not a
    finite well-formed number, or the database may not read it as the engine does (padded lexical form, an integer outside 64 bits,
    a decimal of more than 18 digits on either side of the point)."""
    values = shape.params.get(pred, ())
    if len(values) != 1 or not isinstance(values[0], Literal) or values[0].language is not None:
        return None
    bound = values[0]
    number = xv.numeric(bound)
    if number is None or number != number or number in (float("inf"), float("-inf")) or bound.value != bound.value.strip():
        return None
    if bound.datatype == XSD.decimal or isinstance(number, int):
        digits = bound.value.lstrip("+-").split(".")
        if isinstance(number, int) and abs(number) >= _INT64:
            return None
        if bound.datatype == XSD.decimal and (len(digits[0]) > 18 or (len(digits) > 1 and len(digits[1]) > 18)):
            return None
    return _sparql_text(bound)


def _value_filters(ps: Any, var: str) -> list[str]:
    """FILTER clauses on ``var``, the values of a property shape that needs at least one: a necessary condition for each clause.

    * Range (``sh:minInclusive`` ...) with one numeric parameter: the engine passes a value only when it is a well-formed number and
      ``xsd_values.compare`` (the SPARQL 17.3 order, with the numeric promotion SPARQL uses) holds; the database evaluates the same
      comparison, so a passing value passes the FILTER. The database does not read some literals the engine accepts (a lexical form
      padded with whitespace, an integer outside 64 bits, a decimal of more than 18 fractional digits): such a literal has a
      numeric datatype and is not numeric for the database, and the FILTER lets it through (``!isNumeric`` and a numeric
      datatype) and the exact check decides. Strings, language strings, IRIs and non-numeric datatypes fail in the engine and in
      the FILTER alike (a type error). NaN fails both. Several range constraints are one conjunction.
    * ``sh:datatype`` with one IRI: the engine passes a literal only when its datatype term is that IRI (and it is well formed);
      ``datatype(?v)`` is that same term for every literal, a language string included, so the FILTER is looser than the engine.
    """
    out: list[str] = []
    tests = []
    for pred, op in _RANGE_OPERATORS:
        bound = _numeric_bound(ps, pred)
        if bound is not None:
            tests.append(" ".join((var, op, bound)))
    if tests:
        numeric_types = ", ".join(_sparql_text(URIRef(dt)) for dt in sorted(xv._NUMERIC_DATATYPES))  # noqa: SLF001
        unread = "(isLiteral(" + var + ") && !isNumeric(" + var + ") && datatype(" + var + ") IN (" + numeric_types + "))"
        out.append("FILTER((" + " && ".join(tests) + ") || " + unread + ")")
    datatypes = ps.params.get(SH.datatype, ())
    if len(datatypes) == 1 and isinstance(datatypes[0], URIRef):
        out.append("FILTER(datatype(" + var + ") = " + _sparql_text(datatypes[0]) + ")")
    return out


def _property_patterns(shape_of: Callable[[Term], Any], shape: Any, patterns: list[str]) -> None:
    for prop in shape.property_shapes:
        ps = shape_of(prop)
        if ps.path is None or ps.path.kind != "pred" or not isinstance(ps.path.iri, URIRef) or ps.values or ps.default_values or _is_off(ps):
            continue
        var = f"?o{len(patterns)}"
        path_text = _sparql_text(ps.path.iri)
        if (_int_param(ps, SH.minCount) or 0) >= 1:
            patterns.append(f"?n {path_text} {var} .")
            patterns.extend(_value_filters(ps, var))
        for want in ps.params.get(SH.hasValue, ()):
            if isinstance(want, (URIRef, Literal)):
                want_text = _sparql_text(want)
                patterns.append(f"?n {path_text} {want_text} .")


def _node_patterns(
    data: Any,
    shapes: Any,
    shape_of: Callable[[Term], Any],
    subclasses_of: Callable[[Term], Iterable[Term]] | None,
    node: Term,
    patterns: list[str],
    seen: set,
    depth: int,
) -> None:
    """Triple patterns on ``?n`` that every node conforming to the node shape ``node`` must match (conjunction only)."""
    if node in seen or depth > _MAX_CONDITION_DEPTH or isinstance(node, Literal):
        return
    from starlayer.shacl.engine.components.core_value import rdf_list

    seen.add(node)
    shape = shape_of(node)
    if shape.path is not None or _is_off(shape):
        return
    type_text = _sparql_text(RDF.type)
    for cls in shape.params.get(SH["class"], ()):
        if isinstance(cls, URIRef):  # a blank node is a list (a choice) or unusual: no condition
            closure_text = " ".join(_sparql_text(c) for c in _class_closure(data, cls, subclasses_of) if isinstance(c, URIRef))
            var = f"?c{len(patterns)}"
            patterns.append(f"VALUES {var} {{ {closure_text} }} ?n {type_text} {var} .")
    _property_patterns(shape_of, shape, patterns)
    for member in shape.params.get(SH.node, ()):
        _node_patterns(data, shapes, shape_of, subclasses_of, member, patterns, seen, depth + 1)
    for head in shape.params.get(SH["and"], ()):
        for member in (rdf_list(shapes, head) if isinstance(head, BlankNode) or head == RDF.nil else None) or ():
            _node_patterns(data, shapes, shape_of, subclasses_of, member, patterns, seen, depth + 1)


def _target_where_candidates(
    data: Any,
    shapes: Any,
    shape_of: Callable[[Term], Any] | None,
    subclasses_of: Callable[[Term], Iterable[Term]] | None,
    where_shape: Term,
) -> list[Term] | None:
    """A superset of the nodes that can conform to ``where_shape``, from one SPARQL SELECT on the data graph; ``None`` when no
    condition is known (the caller then scans every node).

    Invariant: necessary conditions only; the exact check (``conforms``) still decides. A condition is taken only from a
    conjunction of the shape itself, its ``sh:and`` members and ``sh:node`` values: ``sh:class`` with an IRI (the class and its
    subclasses as the engine reads them, so ``subclass_of_in_shapes_graph`` and entailment hold), and a ``sh:property`` whose path
    is one property IRI with ``sh:minCount`` of at least 1 or a ``sh:hasValue``. A property shape with ``sh:minCount`` of at least 1
    also gives FILTERs on its value variable (``_value_filters``): its numeric range constraints and its ``sh:datatype``. They are
    necessary because a conforming node has a value and every value passes; a node with only some passing values stays a candidate.
    Without ``sh:minCount`` there is no FILTER (a node with no value conforms). Nothing comes from ``sh:or``, ``sh:xone``,
    ``sh:not``, qualified shapes, other paths, SPARQL constraints, or any deactivated shape or constraint."""
    query = getattr(data, "sparql_query", None)
    if shape_of is None or query is None:
        return None
    patterns: list[str] = []
    _node_patterns(data, shapes, shape_of, subclasses_of, where_shape, patterns, set(), 0)
    if not patterns:
        return None
    solutions = query("SELECT DISTINCT ?n WHERE { " + " ".join(patterns) + " }")
    return [row["n"] for row in solutions.rows]


def focus_nodes(
    data: Any,
    shapes: Any,
    targets: tuple[tuple[URIRef, Term], ...],
    conforms: Callable[[Term, Term], bool] | None = None,
    expression: Callable[[Term], list[Term]] | None = None,
    subclasses_of: Callable[[Term], Iterable[Term]] | None = None,
    shape_of: Callable[[Term], Any] | None = None,
) -> list[Term]:
    """Focus nodes of the given targets, each once, in target order. ``conforms`` is only needed for
    ``sh:targetWhere`` (without it, targetWhere contributes nothing). ``expression`` evaluates a node-expression target
    (a ``sh:targetNode`` whose value is a blank-node node expression)."""
    out: dict = {}
    for pred, value in targets:
        if pred == SH.targetNode:
            if expression is not None and _is_expression(shapes, value):
                for n in expression(value):
                    out.setdefault(n, None)
            else:
                out.setdefault(value, None)
        elif pred == SH.targetClass:
            for cls in _class_closure(data, value, subclasses_of):
                for inst in data.subjects(RDF.type, cls):
                    out.setdefault(inst, None)
        elif pred == SH.shape:
            for s in data.subjects(SH.shape, value):
                out.setdefault(s, None)
        elif pred == SH.targetSubjectsOf:
            for s in data.subjects(value, None):
                out.setdefault(s, None)
        elif pred == SH.targetObjectsOf:
            for o in data.objects(None, value):
                out.setdefault(o, None)
        elif pred == SH.targetWhere and conforms is not None:
            candidates = _target_where_candidates(data, shapes, shape_of, subclasses_of, value)
            for n in _all_nodes(data) if candidates is None else candidates:
                if n not in out and conforms(value, n):
                    out[n] = None
    return list(out)
