from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from rdflib import BNode, Literal, Namespace
from rdflib.namespace import RDF

from starshacl.engine.contracts import ComponentRequest
from starshacl.engine.normalization import normalize_to_starlayer_graph
from starshacl.types import is_triple_term_like

SH = Namespace("http://www.w3.org/ns/shacl#")
STSH = Namespace("https://github.com/hidden-graph/starshacl/ns#")


@dataclass(frozen=True)
class ComponentEvaluationResult:
    conforms: bool
    violations: tuple[Any, ...] = ()


def target_nodes(*, data_graph: Any, shacl_graph: Any, shape_node: Any) -> tuple[Any, ...]:
    data = normalize_to_starlayer_graph(data_graph, name="data_graph")
    graph = normalize_to_starlayer_graph(shacl_graph, name="shacl_graph")
    targets: list[Any] = []

    # Explicit target nodes from shape definitions.
    for _, _, obj in graph.triples((shape_node, SH.targetNode, None)):
        if obj not in targets:
            targets.append(obj)

    # Targets by rdf:type class membership.
    for _, _, cls in graph.triples((shape_node, SH.targetClass, None)):
        for subject, _, _ in data.triples((None, RDF.type, cls)):
            if subject not in targets:
                targets.append(subject)

    # Targets by predicate in subject position.
    for _, _, predicate in graph.triples((shape_node, SH.targetSubjectsOf, None)):
        for subject, _, _ in data.triples((None, predicate, None)):
            if subject not in targets:
                targets.append(subject)

    # Targets by predicate in object position.
    for _, _, predicate in graph.triples((shape_node, SH.targetObjectsOf, None)):
        for _, _, obj in data.triples((None, predicate, None)):
            if obj not in targets:
                targets.append(obj)

    return tuple(targets)


def evaluate_component(request: ComponentRequest) -> ComponentEvaluationResult:
    name = _component_name(request.component)

    if name == str(STSH.TripleTermNodeKind):
        violations = tuple(v for v in request.value_nodes if not _is_triple_term_value(v))
        return ComponentEvaluationResult(conforms=len(violations) == 0, violations=violations)

    if name == "hasValue":
        expected = _component_option(request.component, "value")
        conforms = any(_structural_equal(v, expected) for v in request.value_nodes)
        return ComponentEvaluationResult(conforms=conforms, violations=() if conforms else request.value_nodes)

    if name == "in":
        allowed = tuple(_component_option(request.component, "allowed", ()))
        violations = tuple(v for v in request.value_nodes if not any(_structural_equal(v, a) for a in allowed))
        return ComponentEvaluationResult(conforms=len(violations) == 0, violations=violations)

    if name == "equals":
        other_values = tuple(_component_option(request.component, "other_values", ()))
        missing_in_other = tuple(v for v in request.value_nodes if not any(_structural_equal(v, o) for o in other_values))
        missing_in_self = tuple(o for o in other_values if not any(_structural_equal(o, v) for v in request.value_nodes))
        violations = missing_in_other + missing_in_self
        return ComponentEvaluationResult(conforms=len(violations) == 0, violations=violations)

    if name == "disjoint":
        other_values = tuple(_component_option(request.component, "other_values", ()))
        overlaps = tuple(v for v in request.value_nodes if any(_structural_equal(v, o) for o in other_values))
        return ComponentEvaluationResult(conforms=len(overlaps) == 0, violations=overlaps)

    if name in {"pattern", "datatype", "languageIn", "minLength", "maxLength"}:
        violations = tuple(v for v in request.value_nodes if not isinstance(v, Literal))
        return ComponentEvaluationResult(conforms=len(violations) == 0, violations=violations)

    return ComponentEvaluationResult(conforms=True, violations=())


def build_report(*, events: tuple[dict[str, Any], ...], graph_context: Any, options: dict[str, Any] | None = None) -> Any:
    options = options or {}
    value_decoder = options.get("value_decoder", lambda x: x)

    report = normalize_to_starlayer_graph(graph_context, name="graph_context")
    report.remove((None, None, None))

    report_node = BNode()
    report.add((report_node, SH.type, SH.ValidationReport))
    report.add((report_node, SH.conforms, Literal(len(events) == 0)))

    for event in events:
        result_node = BNode()
        report.add((report_node, SH.result, result_node))
        report.add((result_node, SH.type, SH.ValidationResult))

        focus = event.get("focus_node")
        if focus is not None:
            report.add((result_node, SH.focusNode, value_decoder(focus)))

        path = event.get("result_path")
        if path is not None:
            report.add((result_node, SH.resultPath, value_decoder(path)))

        value = event.get("value")
        if value is not None:
            report.add((result_node, SH.value, value_decoder(value)))

        source_component = event.get("source_constraint_component")
        if source_component is not None:
            report.add((result_node, SH.sourceConstraintComponent, source_component))

        message = event.get("message")
        if message:
            report.add((result_node, SH.resultMessage, Literal(message)))

    return report


def _component_name(component: Any) -> str:
    if isinstance(component, dict):
        raw = component.get("name")
    else:
        raw = component
    return str(raw)


def _component_option(component: Any, key: str, default: Any = None) -> Any:
    if isinstance(component, dict):
        return component.get(key, default)
    return default


def _to_structural_key(value: Any) -> Any:
    if is_triple_term_like(value):
        return (
            _to_structural_key(value.subject),
            _to_structural_key(value.predicate),
            _to_structural_key(value.object),
        )

    if isinstance(value, tuple) and len(value) == 3:
        return (
            _to_structural_key(value[0]),
            _to_structural_key(value[1]),
            _to_structural_key(value[2]),
        )

    return value


def _is_triple_term_value(value: Any) -> bool:
    if isinstance(value, tuple) and len(value) == 3:
        return True
    return is_triple_term_like(value)


def _structural_equal(left: Any, right: Any) -> bool:
    return _to_structural_key(left) == _to_structural_key(right)
