"""Real pySHACL ``ConstraintComponent`` registrations for SHACL 1.2 Core
predicates pySHACL doesn't implement.

Every pySHACL constraint - including its own ``sh:not``/``sh:and``/``sh:or``/
``sh:xone`` composition operators - is dispatched through one module-level
registry: ``pyshacl.constraints.CONSTRAINT_PARAMETERS_MAP``. Registering a
predicate here means pySHACL's own ``Shape.validate()`` picks it up and
evaluates it exactly like a core component, which is what makes composition
with logical operators, ``sh:deactivated``, and ``sh:severity`` correct by
construction, instead of needing to be reimplemented for every native pass
(see ``docs/shacl12-gap-matrix.md``'s "Note on Architecture Direction",
pattern 10, for the full rationale and the investigation that led here).

Predicates whose value is itself a referenced shape (e.g. ``sh:someValue``)
need one extra step: pySHACL's own shape-graph loader only auto-recognizes
shape nodes reachable via a fixed, hardcoded list of predicates
(``sh:property``, ``sh:node``, ``sh:not``, ``sh:qualifiedValueShape``, and
``sh:and``/``sh:or``/``sh:xone`` list members - confirmed by reading
``pyshacl/shapes_graph.py::ShapesGraph._build_node_shape_cache``, which
does not consult the constraint-parameter registry at all despite its own
docstring's third bullet). A value reached only via a newly-registered
predicate like ``sh:someValue`` is invisible to that loader unless it's
independently typed ``sh:NodeShape``/``sh:PropertyShape``. ``ensure_shape_typed``
below patches a copy of the shapes graph with that typing, the same
augment-a-copy pattern already used for SHACL 1.2's new target types
(``StarShaclValidator._augment_shapes_with_new_target_types``).
"""

from __future__ import annotations

import re as _re
import weakref as _weakref
from typing import Any

from rdflib import RDF, Literal, Namespace, URIRef

SH = Namespace("http://www.w3.org/ns/shacl#")

_LINE_BREAK_RE = _re.compile(r"[\f\r\n\v]")
RDF_DIR_LANG_STRING = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#dirLangString")

_registered = False


def ensure_shape_typed(shapes_graph: Any, shape_node: Any) -> tuple[Any, Any, Any] | None:
    """Return an ``(shape_node, rdf:type, sh:NodeShape|sh:PropertyShape)``
    triple to add to a shapes-graph copy so pySHACL's shape loader
    recognizes ``shape_node`` as a shape, or ``None`` if it already would
    (explicit ``sh:NodeShape``/``sh:PropertyShape`` typing already present).
    """
    existing_types = set(shapes_graph.objects(shape_node, RDF.type))
    if SH.NodeShape in existing_types or SH.PropertyShape in existing_types:
        return None
    is_property_shape = any(True for _ in shapes_graph.triples((shape_node, SH.path, None)))
    shape_type = SH.PropertyShape if is_property_shape else SH.NodeShape
    return (shape_node, RDF.type, shape_type)


def shape_reference_nodes(shapes_graph: Any, value: Any) -> list:
    """Resolve a SHAPE_EXPECTING_PREDICATES value to the actual shape
    node(s) it references. Most of these predicates (sh:someValue,
    sh:memberShape, sh:reifierShape) take a single shape reference
    directly, but sh:condition also accepts a SHACL list of shape
    references (SHACLRule.get_conditions()) - if ``value`` is itself a
    well-formed SHACL list (has rdf:first), its members are the real
    references and ``value`` itself is not a shape at all.
    """
    if any(True for _ in shapes_graph.triples((value, RDF.first, None))):
        return list(shapes_graph.items(value))
    return [value]


def register_native_components() -> None:
    """Register starShacl's SHACL 1.2 native constraint components into
    pySHACL's own dispatch map (idempotent - safe to call many times, only
    registers once per process).

    Mutates ``CONSTRAINT_PARAMETERS_MAP``/``ALL_CONSTRAINT_COMPONENTS``/
    ``ALL_CONSTRAINT_PARAMETERS`` *in place* rather than rebinding them:
    ``pyshacl/shape.py``'s ``Shape.validate()`` lazily caches a reference to
    these same list/dict objects the first time it runs in a process
    (``module.CONSTRAINT_PARAMS``); in-place mutation stays visible through
    that cache, reassignment would not.
    """
    global _registered
    if _registered:
        return

    from pyshacl.constraints import (
        ALL_CONSTRAINT_COMPONENTS,
        ALL_CONSTRAINT_PARAMETERS,
        CONSTRAINT_PARAMETERS_MAP,
    )
    from pyshacl.constraints.constraint_component import ConstraintComponent

    if not (isinstance(CONSTRAINT_PARAMETERS_MAP, dict) and isinstance(ALL_CONSTRAINT_PARAMETERS, list)):
        raise RuntimeError(
            "pyshacl's constraint-component registry has an unexpected shape; "
            "starshacl.native_components can't safely register into it. This "
            "usually means the installed pyshacl version changed its internal "
            "structure - see starshacl/native_components.py."
        )

    for predicate, component_cls in _NATIVE_COMPONENTS.items():
        if not (isinstance(component_cls, type) and issubclass(component_cls, ConstraintComponent)):
            raise RuntimeError(f"{component_cls!r} is not a pyshacl ConstraintComponent subclass.")
        CONSTRAINT_PARAMETERS_MAP[predicate] = component_cls
        if predicate not in ALL_CONSTRAINT_PARAMETERS:
            ALL_CONSTRAINT_PARAMETERS.append(predicate)
        if component_cls not in ALL_CONSTRAINT_COMPONENTS:
            ALL_CONSTRAINT_COMPONENTS.append(component_cls)

    _registered = True


def _build_some_value_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class SomeValueConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:someValue``: at least one value node must conform to the
        given shape. No single value node is to blame for a violation, so
        the result carries no ``sh:value`` (matches the SHACL 1.2 Core
        spec's own wording and starShacl's pre-migration behavior).
        """

        shacl_constraint_component = SH.SomeValueConstraintComponent
        shape_expecting = True
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.some_value_node = next(iter(shape.sg.objects(shape.node, SH.someValue)))

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.someValue]

        @classmethod
        def constraint_name(cls) -> str:
            return "SomeValueConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            found_shape = self.shape.get_other_shape(self.some_value_node)
            if found_shape is None:
                raise RuntimeError(
                    f"SHACL Shape not found: sh:someValue on '{self.shape.node}' references "
                    f"'{self.some_value_node}', which is not a recognized shape. This should "
                    "be unreachable - starshacl always types sh:someValue's value before "
                    "handing the shapes graph to pySHACL (see ensure_shape_typed)."
                )
            for focus_node, value_nodes in focus_value_nodes.items():
                conforms_somewhere = False
                for value in value_nodes:
                    is_conform, _reports = found_shape.validate(
                        executor, target_graph, focus=value, _evaluation_path=_evaluation_path[:]
                    )
                    if is_conform:
                        conforms_somewhere = True
                        break
                if not conforms_somewhere:
                    non_conformant = True
                    reports.append(self.make_v_result(target_graph, focus_node))
            return (not non_conformant), reports

    return SomeValueConstraintComponent


def _build_single_line_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class SingleLineConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:singleLine``: a literal value node whose lexical form
        contains a line-break character (``[\\f\\r\\n\\v]``) is a violation.
        Non-literal values aren't checked. ``sh:singleLine false`` is an
        explicit opt-out, not a constraint (matches the SHACL 1.2 Core
        spec's own example, where a shape can carry ``sh:singleLine false``
        to allow multi-line values on an otherwise-checked property).
        """

        shacl_constraint_component = SH.SingleLineConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from rdflib import XSD

            value = next(iter(shape.sg.objects(shape.node, SH.singleLine)))
            # Checking the literal's datatype (not just truthiness) matters:
            # a string literal like "false" is still truthy in Python
            # (bool() on any non-empty str is True), so sh:singleLine
            # "false" would otherwise silently enable the check instead of
            # disabling it - the same bug class found and fixed for
            # sh:closed.
            if not (isinstance(value, Literal) and value.datatype == XSD.boolean):
                raise ValueError(
                    f"sh:singleLine on '{shape.node}' must be a xsd:boolean literal, got {value!r}."
                )
            # Exact-term comparison against "true"^^xsd:boolean, not
            # bool(value.value) (XSD's value-space conversion, which also
            # accepts "1"^^xsd:boolean) - see UniqueLangConstraintComponent's
            # identical fix (confirmed via the W3C SHACL 1.2 test suite's
            # uniqueLang-002 fixture) for the reasoning; applied consistently
            # here since this is the same boolean-parameter grammar.
            self.enabled = str(value) == "true"

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.singleLine]

        @classmethod
        def constraint_name(cls) -> str:
            return "SingleLineConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            if not self.enabled:
                return True, reports
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if isinstance(value, Literal) and _LINE_BREAK_RE.search(str(value)):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return SingleLineConstraintComponent


def _build_subset_of_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.helper.path_helper import shacl_path_to_sparql_path

    class SubsetOfConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:subsetOf``: every value node reached via the shape's own
        ``sh:path`` must also be reachable from the focus node via the
        comparison path given as the ``sh:subsetOf`` value. The comparison
        path can be any SHACL property path (simple IRI, sequence,
        inverse, alternative, etc.) - converted once, in ``__init__``, to a
        SPARQL property path via pySHACL's own
        ``shacl_path_to_sparql_path`` (already used elsewhere in pySHACL
        for ordinary ``sh:path`` evaluation) rather than reimplementing
        SHACL path semantics here. A malformed path (caught via
        ``ReportableRuntimeError``, or any query-time failure) is treated
        as no constraint (conforms) - meta-shacl's job to flag separately.
        """

        shacl_constraint_component = SH.SubsetOfConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.other_path = next(iter(shape.sg.objects(shape.node, SH.subsetOf)))
            try:
                self.other_sparql_path: str | None = shacl_path_to_sparql_path(shape.sg, self.other_path)
            except Exception:
                self.other_sparql_path = None

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.subsetOf]

        @classmethod
        def constraint_name(cls) -> str:
            return "SubsetOfConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            if self.other_sparql_path is None:
                return True, reports
            for focus_node, value_nodes in focus_value_nodes.items():
                try:
                    other_nodes = set(
                        row[0]
                        for row in target_graph.query(
                            f"SELECT ?o WHERE {{ $this {self.other_sparql_path} ?o }}",
                            initBindings={"this": focus_node},
                        )
                    )
                except Exception:
                    continue
                for value in value_nodes:
                    if value not in other_nodes:
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return SubsetOfConstraintComponent


def _is_subclass_of_or_self(graph: Any, node: Any, target_class: Any) -> bool:
    from rdflib import RDFS

    if node == target_class:
        return True
    seen = {node}
    frontier = [node]
    while frontier:
        current = frontier.pop()
        for _, _, superclass in graph.triples((current, RDFS.subClassOf, None)):
            if superclass == target_class:
                return True
            if superclass not in seen:
                seen.add(superclass)
                frontier.append(superclass)
    return False


def _build_root_class_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from rdflib import URIRef

    class RootClassConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:rootClass``: each value node must be an IRI that is, or is a
        transitive ``rdfs:subClassOf`` subclass of, at least one of the
        given root classes. ``rdfs:subClassOf`` triples are read from
        ``target_graph`` alone - when the caller opted into also consulting
        the shapes graph (``rdfs_subclass_reasoning_includes_shapes_graph``),
        ``StarShaclValidator.validate()`` injects the shapes graph's
        ``rdfs:subClassOf`` triples into a copy of the data graph before
        pySHACL runs (``_inject_shapes_graph_subclass_triples``), so this
        component doesn't need a separate channel to the shapes graph.
        """

        shacl_constraint_component = SH.RootClassConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            classes: list[Any] = []
            for value in shape.sg.objects(shape.node, SH.rootClass):
                if isinstance(value, URIRef):
                    classes.append(value)
                elif _is_shacl_list(shape.sg.graph, value):
                    classes.extend(_shacl_list_members(shape.sg.graph, value))
            self.classes = classes

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.rootClass]

        @classmethod
        def constraint_name(cls) -> str:
            return "RootClassConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if not isinstance(value, URIRef) or not any(
                        _is_subclass_of_or_self(target_graph, value, root) for root in self.classes
                    ):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return RootClassConstraintComponent


def _build_unique_values_for_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from rdflib import URIRef

    class UniqueValuesForConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:uniqueValuesFor``: a node-shape-level constraint (not a
        property-shape one). Among the focus nodes given to a single
        ``evaluate()`` call, if two or more share exactly the same values
        for every given property, all of them are violations. A focus node
        with no values for any of the given properties is excluded from
        comparison.

        Composition (``sh:not``/``sh:and``/``sh:or``/``sh:xone``) is
        correct, not just direct targeting: pySHACL's own logical-operator
        components normally invoke a nested shape once *per individual
        value node* (confirmed by reading
        ``pyshacl/constraints/core/logical_constraints.py`` - e.g.
        ``AndConstraintComponent._evaluate_and_constraint`` calls
        ``and_shape.validate(executor, target_graph, focus=v, ...)`` with a
        single scalar ``v``, never the whole batch), which would make a
        cross-node constraint like this one vacuously conform (or, through
        ``sh:not``, vacuously violate) every time, regardless of the real
        data - there's no second node in view to collide with. This is
        fixed at the composition layer, not here: ``_build_and_component``/
        ``_build_or_component``/``_build_xone_component``/
        ``_build_not_component`` below shadow pySHACL's own logical
        operators and detect (via ``_shape_needs_full_batch``) when a
        nested shape declares a cross-node predicate, invoking it once with
        the *full* batch of value nodes as focus instead of one at a time -
        so this component always sees the real comparison set, whether
        reached directly or through composition. See
        ``AndConstraintComponent``'s docstring for the full mechanism.
        """

        shacl_constraint_component = SH.UniqueValuesForConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            value = next(iter(shape.sg.objects(shape.node, SH.uniqueValuesFor)))
            if isinstance(value, URIRef):
                self.properties = [value]
            elif _is_shacl_list(shape.sg.graph, value):
                self.properties = _shacl_list_members(shape.sg.graph, value)
            else:
                self.properties = []

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.uniqueValuesFor]

        @classmethod
        def constraint_name(cls) -> str:
            return "UniqueValuesForConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            signatures: dict[Any, list[Any]] = {}
            for node in focus_value_nodes.keys():
                signature = tuple(
                    frozenset(o for _, _, o in target_graph.triples((node, prop, None))) for prop in self.properties
                )
                if all(len(values) == 0 for values in signature):
                    continue
                signatures.setdefault(signature, []).append(node)

            for nodes in signatures.values():
                if len(nodes) > 1:
                    non_conformant = True
                    for node in nodes:
                        reports.append(self.make_v_result(target_graph, node))
            return (not non_conformant), reports

    return UniqueValuesForConstraintComponent


def _build_member_shape_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class MemberShapeConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:memberShape``: each value node must be a well-formed SHACL
        list, or that alone is a violation; otherwise every member of the
        list must conform to the given shape. Matches the SHACL 1.2 Core
        spec's and starShacl's pre-migration reporting shape: one violation
        per non-conforming *member*, each blaming the whole list as the
        value node (not the individual member).
        """

        shacl_constraint_component = SH.MemberShapeConstraintComponent
        shape_expecting = True
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.member_shape_node = next(iter(shape.sg.objects(shape.node, SH.memberShape)))

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.memberShape]

        @classmethod
        def constraint_name(cls) -> str:
            return "MemberShapeConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            reports: list[Any] = []
            non_conformant = False
            found_shape = self.shape.get_other_shape(self.member_shape_node)
            if found_shape is None:
                raise RuntimeError(
                    f"SHACL Shape not found: sh:memberShape on '{self.shape.node}' references "
                    f"'{self.member_shape_node}', which is not a recognized shape. This should "
                    "be unreachable - starshacl always types sh:memberShape's value before "
                    "handing the shapes graph to pySHACL (see ensure_shape_typed)."
                )
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if not _is_shacl_list(target_graph, value):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                        continue
                    # One sh:result per non-conforming *list* (blaming the
                    # whole list as sh:value), not one per non-conforming
                    # member - matching standard SHACL sh:detail composite-
                    # constraint reporting (same pattern sh:and/sh:qualified
                    # ValueShape use). Each member's own nested violation
                    # report is preserved under sh:detail rather than
                    # discarded or promoted to its own independent top-level
                    # sh:result (which would double-count one list as
                    # multiple violations - confirmed via the W3C SHACL 1.2
                    # test suite's memberShape-001 fixture, whose ex:list5
                    # has two non-conforming members and expects exactly one
                    # sh:result with two sh:detail entries, not two results).
                    member_reports = []
                    for member in _shacl_list_members(target_graph, value):
                        is_conform, _reports = found_shape.validate(
                            executor, target_graph, focus=member, _evaluation_path=_evaluation_path[:]
                        )
                        if not is_conform:
                            member_reports.extend(_reports)
                    if member_reports:
                        non_conformant = True
                        desc, r_node, r_triples = self.make_v_result(target_graph, focus_node, value_node=value)
                        for _n_desc, n_bn, n_tr in member_reports:
                            r_triples.append((r_node, SH.detail, n_bn))
                            r_triples.extend(n_tr)
                        reports.append((desc, r_node, r_triples))
            return (not non_conformant), reports

    return MemberShapeConstraintComponent


def _build_min_list_length_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class MinListLengthConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:minListLength``: each value node must be a well-formed SHACL
        list with at least the given number of members."""

        shacl_constraint_component = SH.MinListLengthConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.min_length = int(next(iter(shape.sg.objects(shape.node, SH.minListLength))))

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.minListLength]

        @classmethod
        def constraint_name(cls) -> str:
            return "MinListLengthConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if not _is_shacl_list(target_graph, value):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                        continue
                    if len(_shacl_list_members(target_graph, value)) < self.min_length:
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return MinListLengthConstraintComponent


def _build_max_list_length_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class MaxListLengthConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:maxListLength``: each value node must be a well-formed SHACL
        list with at most the given number of members."""

        shacl_constraint_component = SH.MaxListLengthConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.max_length = int(next(iter(shape.sg.objects(shape.node, SH.maxListLength))))

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.maxListLength]

        @classmethod
        def constraint_name(cls) -> str:
            return "MaxListLengthConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if not _is_shacl_list(target_graph, value):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                        continue
                    if len(_shacl_list_members(target_graph, value)) > self.max_length:
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return MaxListLengthConstraintComponent


def _build_unique_members_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class UniqueMembersConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:uniqueMembers``: each value node must be a well-formed SHACL
        list with no duplicate members. ``sh:uniqueMembers false`` is an
        explicit opt-out (matches ``sh:singleLine false``'s treatment) - not
        itself a constraint, not even a "must be a list" check.
        """

        shacl_constraint_component = SH.UniqueMembersConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from rdflib import XSD

            value = next(iter(shape.sg.objects(shape.node, SH.uniqueMembers)))
            # See SingleLineConstraintComponent's identical guard: a string
            # literal like "false" is truthy in Python, so without checking
            # the datatype, sh:uniqueMembers "false" would silently enable
            # the check instead of disabling it.
            if not (isinstance(value, Literal) and value.datatype == XSD.boolean):
                raise ValueError(
                    f"sh:uniqueMembers on '{shape.node}' must be a xsd:boolean literal, got {value!r}."
                )
            # Exact-term comparison against "true"^^xsd:boolean - see
            # UniqueLangConstraintComponent's identical fix for the reasoning.
            self.enabled = str(value) == "true"

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.uniqueMembers]

        @classmethod
        def constraint_name(cls) -> str:
            return "UniqueMembersConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            reports: list[Any] = []
            non_conformant = False
            if not self.enabled:
                return True, reports
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if not _is_shacl_list(target_graph, value):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                        continue
                    members = _shacl_list_members(target_graph, value)
                    if len(set(members)) != len(members):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return UniqueMembersConstraintComponent


_RDF_REIFIES = URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies")

# Predicates that need the *whole* batch of value nodes handed to their
# component in one evaluate() call, not one node at a time - because the
# constraint is inherently about comparing focus nodes to each other, not
# checking each one against fixed, node-independent criteria. Currently just
# sh:uniqueValuesFor; extend this tuple if a future cross-node predicate is
# added. See _build_and_component's docstring for the full rationale.
_CROSS_NODE_PREDICATES: tuple[Any, ...] = (SH.uniqueValuesFor,)

# Predicates whose pySHACL evaluation invokes a nested/referenced shape's
# validate() once per individual value node (confirmed by reading
# pyshacl/constraints/core/logical_constraints.py and
# pyshacl/constraints/core/shape_based_constraints.py) - i.e. every
# composition mechanism a cross-node predicate's bug can hide behind, not
# just the four logical operators. sh:property is deliberately not listed:
# its target must be a *property* shape, which sh:uniqueValuesFor can't sit
# on directly - the real path through sh:property is indirect, via that
# property shape's own sh:node, already covered below.
_COMPOSITION_PREDICATES: tuple[Any, ...] = (
    SH["not"],
    SH.node,
    SH.qualifiedValueShape,
    SH["and"],
    SH["or"],
    SH.xone,
)

_cross_node_reachability_cache: _weakref.WeakKeyDictionary[Any, frozenset] = _weakref.WeakKeyDictionary()


def _shapes_directly_composed_by(shapes_graph: Any, shape_node: Any) -> set[Any]:
    """Every shape node ``shape_node`` directly composes via one of
    ``_COMPOSITION_PREDICATES`` - list members for ``sh:and``/``sh:or``/
    ``sh:xone``, the single referenced node otherwise.
    """
    from starshacl.validator import _is_shacl_list, _shacl_list_members

    composed: set[Any] = set()
    for predicate in (SH["not"], SH.node, SH.qualifiedValueShape):
        for _, _, target in shapes_graph.triples((shape_node, predicate, None)):
            composed.add(target)
    for predicate in (SH["and"], SH["or"], SH.xone):
        for _, _, list_head in shapes_graph.triples((shape_node, predicate, None)):
            if _is_shacl_list(shapes_graph, list_head):
                composed.update(_shacl_list_members(shapes_graph, list_head))
    return composed


def _cross_node_reachable_shapes(shapes_graph: Any) -> frozenset:
    """Every shape node in ``shapes_graph`` whose composition tree - walked
    transitively through ``_COMPOSITION_PREDICATES`` - reaches a shape that
    directly declares one of ``_CROSS_NODE_PREDICATES``.

    Computed once per distinct shapes-graph object and cached in a
    ``WeakKeyDictionary`` (note: rdflib's ``Graph.__eq__``/``__hash__`` key
    off ``identifier``, not Python object identity - harmless in practice
    since ``encode_graph()`` never sets an explicit ``identifier``, so each
    call gets rdflib's own fresh-random-BNode default, but this is a
    same-*content* cache, not a same-*object* cache, so don't rely on the
    latter). The entry is dropped once the graph is garbage-collected - no
    explicit invalidation needed. This is what lets nested composition (e.g.
    ``sh:and`` containing an ``sh:and`` containing the shape that declares
    ``sh:uniqueValuesFor``) be detected correctly: a shallow, one-level
    check on the immediate child shape misses this, since the child itself
    doesn't declare the cross-node predicate - only something *it* composes
    does. Every registered component evaluating shapes from the same
    ``validate()`` call shares the identical (encoded) shapes graph object
    (confirmed empirically), so this table is naturally computed once per
    ``validate()`` call and then just looked up, not re-walked live on every
    branch decision.

    Computed via monotonic fixed-point propagation, not DFS-with-memo: a
    naive DFS that memoizes a node's answer using a cycle-guard's early
    ``False`` return is unsound whenever the composition graph has a real
    cycle (e.g. ``A`` composes ``B``, ``B`` composes ``A``, and ``A`` also
    composes a shape ``C`` that declares the cross-node predicate) - ``B``'s
    correct answer is True (via A -> C), but a DFS starting at A that visits
    B before C would hit the cycle guard while exploring B (B -> A, A
    already on the stack) and permanently memoize B as False before C is
    ever considered, silently reintroducing the exact vacuous-conformance
    bug this whole mechanism exists to prevent - confirmed empirically as
    genuinely order-dependent (varies by ``PYTHONHASHSEED`` since set
    iteration order for URIRef/str-keyed sets depends on it), not merely
    theoretical. A worklist that repeatedly marks a node reachable if
    anything it composes is already marked, until nothing changes, is
    correct regardless of iteration order or how the cycle is shaped.
    """
    cached = _cross_node_reachability_cache.get(shapes_graph)
    if cached is not None:
        return cached

    directly_declared: set[Any] = set()
    for predicate in _CROSS_NODE_PREDICATES:
        for s, _, _ in shapes_graph.triples((None, predicate, None)):
            directly_declared.add(s)

    all_nodes: set[Any] = set(directly_declared)
    for predicate in _COMPOSITION_PREDICATES:
        for s, _, _ in shapes_graph.triples((None, predicate, None)):
            all_nodes.add(s)

    composes: dict[Any, set[Any]] = {node: _shapes_directly_composed_by(shapes_graph, node) for node in all_nodes}

    reachable: set[Any] = set(directly_declared)
    changed = True
    while changed:
        changed = False
        for node in all_nodes:
            if node in reachable:
                continue
            if any(child in reachable for child in composes[node]):
                reachable.add(node)
                changed = True

    result = frozenset(reachable)
    _cross_node_reachability_cache[shapes_graph] = result
    return result


def _shape_needs_full_batch(shape: Any) -> bool:
    """Whether ``shape``'s own composition tree - walked transitively
    through ``_COMPOSITION_PREDICATES`` - reaches a shape declaring one of
    ``_CROSS_NODE_PREDICATES``. Backed by ``_cross_node_reachable_shapes``,
    a per-shapes-graph table computed once and memoized, so this is an O(1)
    lookup, not a live graph walk.
    """
    return shape.node in _cross_node_reachable_shapes(shape.sg.graph)


def _evaluate_shape_for_all_values(
    shape: Any, executor: Any, target_graph: Any, all_values: list, _evaluation_path: list
) -> tuple[dict, list]:
    """Invoke ``shape.validate()`` ONCE with ``all_values`` as ``focus``
    (the full batch, not one node at a time) - this is what lets a
    cross-node constraint like ``sh:uniqueValuesFor`` see every candidate
    together and compare them, the same way it would if ``shape`` were
    independently, directly targeted.

    A full-batch call only returns one aggregate ``is_conform`` for the
    whole batch, but the logical operators calling this need a per-value
    answer (composition semantics attribute violations to individual focus
    nodes, not the batch as a whole). Recovered from the returned reports'
    own ``sh:focusNode`` markers, which every native component here (and
    every pySHACL core component) sets via ``make_v_result`` - a value not
    named in any report's ``sh:focusNode`` conforms; one that is, doesn't.
    """
    is_conform, reports = shape.validate(
        executor, target_graph, focus=list(all_values), _evaluation_path=_evaluation_path[:]
    )
    violating: set = set()
    for _desc, _r_node, r_triples in reports:
        for _s, p, o in r_triples:
            if p == SH.focusNode:
                violating.add(o[1] if isinstance(o, tuple) else o)
    conforms_per_value = {v: (v not in violating) for v in all_values}
    return conforms_per_value, reports


def _get_tt_adapter(target_graph: Any) -> Any | None:
    """The ``TripleTermAdapter`` that encoded ``target_graph``, or ``None``
    if it wasn't produced by one (e.g. a direct, non-starShacl ``pyshacl.validate()``
    call). ``target_graph``, as handed to a ``ConstraintComponent``, is
    pySHACL's own ``RdfLibDataGraph`` wrapper, not the
    ``_SparqlAwareEncodedGraph`` ``encode_graph()`` actually produced - the
    adapter back-reference lives one level down, on ``.impl`` (confirmed
    empirically, not documented by pySHACL - see
    ``ReifierShapeConstraintComponent`` for the same pattern).
    """
    adapter = getattr(target_graph, "_tt_adapter", None)
    if adapter is None:
        adapter = getattr(getattr(target_graph, "impl", None), "_tt_adapter", None)
    return adapter


def _is_encoded_triple_term(target_graph: Any, value: Any) -> bool:
    """Whether ``value`` is the content-addressed URI a ``TripleTermAdapter``
    assigned to a real triple term, given ``target_graph`` (the encoded
    graph a registered component's ``evaluate()`` receives) - so node-kind
    matching can recognize ``sh:TripleTerm`` correctly even though the
    original triple-term object is no longer present in encoded form.
    """
    adapter = _get_tt_adapter(target_graph)
    if adapter is None:
        return False
    return value in adapter._reverse


def _annotation_value(shapes_graph: Any, subject: Any, predicate: Any, obj: Any, annotation_predicate: Any) -> Any:
    """The single value of ``annotation_predicate`` on the reifier of the
    constraint-value triple ``(subject, predicate, obj)`` in ``shapes_graph``,
    via RDF 1.2's inline reification-annotation shorthand
    (``sh:datatype xsd:integer {| sh:severity sh:Warning |}``) - or ``None``
    if that triple has no reifier, or the reifier has no (or more than one)
    value for ``annotation_predicate``.

    This is SHACL 1.2 Core's per-constraint ``sh:severity``/``sh:deactivated``
    override, distinct from - and finer-grained than - the shape-level
    ``sh:severity``/``sh:deactivated`` every native component already
    inherits generically from ``self.shape``. Mirrors
    ``ReifierShapeConstraintComponent``'s own triple-term re-encoding
    approach (see its docstring for why re-encoding through the *same*
    adapter/registry that produced the graph's own encoding reproduces the
    identical lookup key) - here applied to the *shapes* graph (where a
    constraint-value annotation lives) rather than the data graph.
    """
    adapter = _get_tt_adapter(shapes_graph)
    key = adapter.encode_term((subject, predicate, obj)) if adapter is not None else (subject, predicate, obj)
    values = set()
    for reifier, _, _ in shapes_graph.triples((None, _RDF_REIFIES, key)):
        values.update(shapes_graph.objects(reifier, annotation_predicate))
    if len(values) == 1:
        return next(iter(values))
    return None


def _ambient_shapes_graph_prefixes(shapes_graph: Any) -> dict[str, Any]:
    """Prefixes declared via any ``sh:ShapesGraph``-typed node's own
    ``sh:declare``, for ambient (implicit) resolution when a ``sh:sparql``
    constraint has no explicit ``sh:prefixes`` reference at all - see
    ``_build_sparql_constraint_component``'s own docstring for why pySHACL's
    ``SPARQLQueryHelper.collect_prefixes()`` never falls back to this on its
    own. Deliberately does *not* also consult ``owl:Ontology`` nodes the way
    pySHACL's own explicit-``sh:prefixes``-reference path does - confirmed
    via the W3C SHACL 1.2 test suite's ``prefixes-002`` fixture, whose
    ``owl:Ontology``-declared prefix is a deliberate distractor (the same
    prefix letter mapped to a different, wrong namespace) that must not be
    picked up here.
    """
    prefixes: dict[str, Any] = {}
    for sgraph_node in shapes_graph.subjects(RDF.type, SH.ShapesGraph):
        for dec in shapes_graph.objects(sgraph_node, SH.declare):
            prefix_vals = list(shapes_graph.objects(dec, SH.prefix))
            ns_vals = list(shapes_graph.objects(dec, SH.namespace))
            if len(prefix_vals) == 1 and len(ns_vals) == 1:
                prefixes[str(prefix_vals[0])] = URIRef(str(ns_vals[0]))
    return prefixes


def _build_sparql_constraint_component() -> Any:
    """Fixes a confirmed pySHACL gap: ``sh:sparql``'s own constraint node
    (the object of ``sh:sparql``, distinct from the shape it's attached to)
    can carry its own ``sh:severity`` override, per the SHACL Core spec's
    SPARQL-based Constraints section - the same way it already carries its
    own ``sh:message``/``sh:deactivated``. pySHACL's own
    ``SPARQLBasedConstraint.__init__`` reads ``sh:message``/``sh:deactivated``
    from that node but never ``sh:severity``, so every violation always
    reports the *shape's* own severity (``self.shape.severity``, read
    generically inside ``ConstraintComponent.make_v_result``) regardless of
    what the constraint node itself declares. Confirmed via the W3C SHACL
    1.2 test suite's sparql-001 fixture, and via a grep of pySHACL's own
    ``constraints/sparql/`` and ``helper/`` modules for "severity" (zero
    matches) - not something specific to advanced/rules mode or any starShacl
    wrapping.

    Subclasses pySHACL's own ``SPARQLBasedConstraint`` rather than
    reimplementing it (same "shadow an existing pySHACL component" pattern
    as ``sh:closed``/``sh:class``/``sh:nodeKind``/``sh:datatype``), only
    overriding the one method that builds each violation's report triples -
    everything else (query execution, message/deactivation handling,
    pre-binding) stays pySHACL's own, unmodified logic.
    """
    from pyshacl.constraints.sparql.sparql_based_constraints import (
        SPARQLBasedConstraint,
    )

    class SparqlConstraintComponentWithSeverity(SPARQLBasedConstraint):  # type: ignore[misc]
        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            # Ambient sh:declare prefix discovery (SHACL 1.2 Core): pySHACL's
            # own SPARQLQueryHelper.collect_prefixes() only ever looks past
            # the named graph/owl:Ontology declares as an *addition* to an
            # explicit sh:prefixes reference on the sh:sparql constraint -
            # if that reference is entirely absent, it returns immediately
            # without considering any sh:ShapesGraph-typed node's own
            # sh:declare at all. Confirmed via the W3C SHACL 1.2 test
            # suite's prefixes-002 fixture. Checked via the constraint
            # node's own sh:prefixes presence, not query_helper.prefixes'
            # truthiness - collect_prefixes() already unconditionally seeds
            # a handful of default bindings (rdf/rdfs/owl) regardless of
            # sh:prefixes, so that dict is never actually empty. An explicit
            # sh:prefixes reference (however narrow) always wins as-is,
            # unchanged from pySHACL's own behavior - ambient discovery only
            # fills in when there's no such reference to begin with.
            ambient = _ambient_shapes_graph_prefixes(shape.sg.graph)
            if ambient:
                for query_helper in self.sparql_constraints:
                    if not list(shape.sg.graph.objects(query_helper.node, SH.prefixes)):
                        query_helper.prefixes.update(ambient)

        def _evaluate_sparql_constraint(self, sparql_constraint: Any, target_graph: Any, f_v_dict: Any):
            non_conformant, reports = super()._evaluate_sparql_constraint(sparql_constraint, target_graph, f_v_dict)
            severity_vals = list(self.shape.sg.graph.objects(sparql_constraint.node, SH.severity))
            if len(severity_vals) != 1:
                return non_conformant, reports
            severity = severity_vals[0]
            fixed_reports = []
            for desc, r_node, r_triples in reports:
                fixed_triples = [
                    (s, p, severity) if (s == r_node and p == SH.resultSeverity) else (s, p, o)
                    for s, p, o in r_triples
                ]
                fixed_reports.append((desc, r_node, fixed_triples))
            return non_conformant, fixed_reports

    return SparqlConstraintComponentWithSeverity


def _build_node_by_expression_component() -> Any:
    """``sh:nodeByExpression``: like ``sh:node``, but the referenced shape is
    computed via a SHACL 1.2 node expression rather than given directly -
    the expression is evaluated once per *value* node (using that value
    node's own focus-shape context as ``$this``, via the shape's own
    ``eval_expr()``), and the value must conform to whatever shape(s) that
    evaluates to. The W3C SHACL 1.2 test suite's own fixtures for this
    (``nodeByExpression-001`` at both node- and property-shape level) note
    "Core doesn't define interesting node expressions" and only ever use a
    plain IRI constant as the expression - `eval_expr()` already evaluates a
    constant to itself via delegation to pySHACL's own
    ``nodes_from_node_expression``, so this works for the common case
    without needing shnex:-specific handling here.
    """
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class NodeByExpressionConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        shacl_constraint_component = SH.NodeByExpressionConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.expr = next(iter(shape.sg.objects(shape.node, SH.nodeByExpression)))

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.nodeByExpression]

        @classmethod
        def constraint_name(cls) -> str:
            return "NodeByExpressionConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            from starshacl.node_expressions import eval_expr

            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                shape_nodes = eval_expr(self.expr, focus_node, target_graph, self.shape.sg, scope={})
                for value in value_nodes:
                    for shape_node in shape_nodes:
                        found_shape = self.shape.get_other_shape(shape_node)
                        if found_shape is None:
                            continue
                        is_conform, _reports = found_shape.validate(
                            executor, target_graph, focus=value, _evaluation_path=_evaluation_path[:]
                        )
                        if not is_conform:
                            non_conformant = True
                            reports.append(
                                self.make_v_result(
                                    target_graph, focus_node, value_node=value, source_constraint=shape_node
                                )
                            )
            return (not non_conformant), reports

    return NodeByExpressionConstraintComponent


def _build_property_constraint_component() -> Any:
    """Shadows pySHACL's own ``PropertyConstraintComponent`` to honor a
    per-``sh:property``-value ``sh:deactivated`` override via RDF-1.2's
    inline reification-annotation shorthand
    (``sh:property ex:Shape {| sh:deactivated true |}``) - SHACL 1.2 Core,
    distinct from a shape's own ordinary ``sh:deactivated`` (which
    deactivates the *referenced* shape's own constraints generically,
    already handled by pySHACL). This annotation instead deactivates one
    specific *reference* to a property shape - a shape referenced via
    multiple ``sh:property`` values elsewhere would be unaffected. Confirmed
    via the W3C SHACL 1.2 test suite's deactivated-003 fixture. Filters
    ``self.property_shapes`` once in ``__init__``, before pySHACL's own
    ``evaluate()`` ever sees it - unlike the severity case (``sh:datatype``,
    see ``_build_datatype_component``), this fixture doesn't need a
    per-reference ``sh:severity`` override too, so that isn't implemented
    here.
    """
    from pyshacl.constraints.core.shape_based_constraints import (
        PropertyConstraintComponent,
    )

    class PropertyConstraintComponentWithAnnotations(PropertyConstraintComponent):  # type: ignore[misc]
        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self.property_shapes = [
                p_shape
                for p_shape in self.property_shapes
                if _annotation_value(shape.sg.graph, shape.node, SH.property, p_shape, SH.deactivated)
                != Literal(True)
            ]

    return PropertyConstraintComponentWithAnnotations


def _build_reifier_shape_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from rdflib import URIRef

    class ReifierShapeConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """``sh:reifierShape``/``sh:reificationRequired``: for each value
        node reached via the shape's own ``sh:path`` (must be a simple IRI
        per the spec's own syntax rule for this component), find its
        reifiers (nodes ``r`` such that ``r rdf:reifies <<( focus, path,
        value )>>``) and:

        - if ``sh:reificationRequired`` is true and no reifier exists,
          that's a violation with the triple term as ``sh:value``;
        - if ``sh:reifierShape`` is given, each reifier that fails to
          conform to it is a violation, also with the triple term as
          ``sh:value``.

        Both predicates are declared as this one class's constraint
        parameters (pySHACL's own ``done_constraints`` de-duplication in
        ``Shape.validate()`` then instantiates and evaluates it once even
        when a shape has both), matching how both were handled together as
        one bundled pass before this migration.

        The one real wrinkle migrating this predicate: ``rdf:reifies``
        matches against real RDF-1.2 triple-term identity, but ``evaluate()``
        runs on ``target_graph`` *after* ``TripleTermAdapter.encode_graph()``
        has flattened every triple term into a content-addressed URI. This
        works anyway because ``encode_graph()`` returns a
        ``_SparqlAwareEncodedGraph`` (``starshacl/adapters.py``) carrying a
        back-reference to the exact adapter instance that did the encoding
        (``target_graph._tt_adapter``, built earlier for SPARQL/rules
        wiring) - re-encoding ``(focus, path, value)`` through that same
        adapter/registry reproduces the identical URI ``encode_graph()``
        already assigned when it encountered this triple term as the object
        of a real ``rdf:reifies`` triple in the data, so the lookup matches
        correctly without reconstructing or guessing at adapter state.
        """

        shacl_constraint_component = SH.ReifierShapeConstraintComponent
        shape_expecting = True
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            path = shape.path()
            if not isinstance(path, URIRef):
                raise NotImplementedError(
                    "sh:reifierShape/sh:reificationRequired requires sh:path to be a simple IRI, "
                    "per the SHACL 1.2 spec's own syntax rule for this constraint component"
                )
            self.path = path
            self.reifier_shape_node = next(iter(shape.sg.objects(shape.node, SH.reifierShape)), None)

            from rdflib import XSD

            reification_required_val = next(iter(shape.sg.objects(shape.node, SH.reificationRequired)), None)
            if reification_required_val is None:
                self.reification_required = False
            elif isinstance(reification_required_val, Literal) and reification_required_val.datatype == XSD.boolean:
                # Exact-term comparison against "true"^^xsd:boolean - see
                # UniqueLangConstraintComponent's identical fix for the
                # reasoning (not bool(value.value), XSD's value-space
                # conversion, which also accepts "1"^^xsd:boolean).
                self.reification_required = str(reification_required_val) == "true"
            else:
                raise ValueError(
                    f"sh:reificationRequired on '{shape.node}' must be a xsd:boolean literal, "
                    f"got {reification_required_val!r}."
                )

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.reifierShape, SH.reificationRequired]

        @classmethod
        def constraint_name(cls) -> str:
            return "ReifierShapeConstraintComponent"

        def _encode_key(self, target_graph: Any, triple_term: tuple[Any, Any, Any]) -> Any:
            adapter = _get_tt_adapter(target_graph)
            return adapter.encode_term(triple_term) if adapter is not None else triple_term

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            found_shape = (
                self.shape.get_other_shape(self.reifier_shape_node) if self.reifier_shape_node is not None else None
            )
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    triple_term = (focus_node, self.path, value)
                    key = self._encode_key(target_graph, triple_term)
                    reifiers = tuple(s for s, _, _ in target_graph.triples((None, _RDF_REIFIES, key)))

                    if self.reification_required and not reifiers:
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))

                    if found_shape is not None:
                        for reifier in reifiers:
                            is_conform, _reports = found_shape.validate(
                                executor, target_graph, focus=reifier, _evaluation_path=_evaluation_path[:]
                            )
                            if not is_conform:
                                non_conformant = True
                                reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return ReifierShapeConstraintComponent


def _build_closed_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from rdflib import RDFS

    _ALWAYS_IGNORE = {(RDF.type, RDFS.Resource)}

    class ClosedConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``ClosedConstraintComponent`` (registered
        under the same predicates, ``sh:closed``/``sh:ignoredProperties``,
        which fully replaces pySHACL's dispatch entry for both - not an
        addition alongside it) to add the SHACL 1.2 Core ``sh:closed
        sh:ByTypes`` value pySHACL 0.40 crashes on outright
        (``AssertionError: sh:closed must take a xsd:boolean literal`` -
        it only ever expected a boolean literal). The plain-boolean case
        below reproduces pySHACL's own non-SPARQL-mode ``evaluate()`` logic
        exactly (same ``ALWAYS_IGNORE``/``ignored_props``/``working_paths``
        checks, same violation shape) for parity with existing behavior;
        only the ``sh:ByTypes`` branch is new.
        """

        shacl_constraint_component = SH.ClosedConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from rdflib import XSD

            from starshacl.validator import _shacl_list_members

            closed_vals = list(shape.sg.objects(shape.node, SH.closed))
            if len(closed_vals) != 1:
                raise ValueError(
                    "ClosedConstraintComponent must have exactly one sh:closed predicate, "
                    f"found {len(closed_vals)} on '{shape.node}'."
                )
            closed_val = closed_vals[0]

            self.by_types = closed_val == SH.ByTypes
            if not self.by_types:
                # Checking the literal's datatype (not just isinstance(..., Literal))
                # matters: an untyped/xsd:string literal like "false" is still a
                # Literal, but bool("false") is True in Python regardless of the
                # string's content - silently coercing sh:closed "false" to closed
                # = True, the opposite of what it reads as. Requiring xsd:boolean
                # specifically guarantees .value is already a real Python bool.
                if not (isinstance(closed_val, Literal) and closed_val.datatype == XSD.boolean):
                    raise ValueError(
                        f"sh:closed on '{shape.node}' must be either an xsd:boolean literal or sh:ByTypes, "
                        f"got {closed_val!r}."
                    )
                self.is_closed = bool(closed_val.value)

            self.ignored_props: set = set()
            for ignored_list in shape.sg.objects(shape.node, SH.ignoredProperties):
                self.ignored_props.update(_shacl_list_members(shape.sg.graph, ignored_list))

            working_paths: set = set()
            for prop_shape_node in shape.sg.objects(shape.node, SH.property):
                prop_shape = shape.get_other_shape(prop_shape_node)
                if prop_shape is not None and prop_shape.path():
                    working_paths.add(prop_shape.path())
            self.working_paths = working_paths

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.closed, SH.ignoredProperties]

        @classmethod
        def constraint_name(cls) -> str:
            return "ClosedConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            from starshacl.validator import _collect_by_types_properties

            reports: list[Any] = []
            non_conformant = False

            if self.by_types:
                for focus_node, value_nodes in focus_value_nodes.items():
                    for value in value_nodes:
                        allowed: set = {RDF.type} | self.ignored_props
                        for value_type in set(o for _, _, o in target_graph.triples((value, RDF.type, None))):
                            allowed |= _collect_by_types_properties(self.shape.sg.graph, value_type, set())
                        for _, predicate, obj in target_graph.triples((value, None, None)):
                            if predicate not in allowed:
                                non_conformant = True
                                reports.append(
                                    self.make_v_result(
                                        target_graph, focus_node, value_node=obj, result_path=predicate
                                    )
                                )
                return (not non_conformant), reports

            if not self.is_closed:
                return True, reports

            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    for predicate, obj in target_graph.predicate_objects(value):
                        if (predicate, obj) in _ALWAYS_IGNORE:
                            continue
                        if predicate in self.ignored_props or predicate in self.working_paths:
                            continue
                        non_conformant = True
                        reports.append(
                            self.make_v_result(target_graph, focus_node, value_node=obj, result_path=predicate)
                        )
            return (not non_conformant), reports

    return ClosedConstraintComponent


def _build_class_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.value_constraints import (
        ClassConstraintComponent as _OriginalClassComponent,
    )
    from rdflib import BNode

    class ClassConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``ClassConstraintComponent`` to add SHACL
        1.2's list-valued ``sh:class`` (union of choices - a value matches
        if it's a SHACL instance of *any* class in the list). Multiple
        separate ``sh:class`` triples on one shape remain AND'd together
        (pySHACL's own, pre-existing semantics) - each triple's value can
        now independently be a plain IRI (one required class) or a list
        (any-of-these), combined with AND across triples.

        If none of the shape's ``sh:class`` values are list-valued, this
        delegates entirely to a real instance of pySHACL's own component
        for byte-for-byte parity (its transitive-subclass walk and
        Literal/debug-logging behavior are non-trivial to reproduce
        faithfully by hand) - native evaluation only kicks in once a list
        value is actually present, the genuinely new SHACL 1.2 case with no
        prior pySHACL behavior to preserve.
        """

        shacl_constraint_component = SH["ClassConstraintComponent"]
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            class_values = list(shape.sg.objects(shape.node, SH["class"]))
            self.class_groups: list[frozenset] = []
            has_list = False
            for value in class_values:
                if _is_shacl_list(shape.sg.graph, value):
                    has_list = True
                    self.class_groups.append(frozenset(_shacl_list_members(shape.sg.graph, value)))
                else:
                    self.class_groups.append(frozenset({value}))
            self.delegate = None if has_list else _OriginalClassComponent(shape)

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH["class"]]

        @classmethod
        def constraint_name(cls) -> str:
            return "ClassConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            if self.delegate is not None:
                return self.delegate.evaluate(executor, target_graph, focus_value_nodes, _evaluation_path)

            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    if not isinstance(value, (URIRef, BNode)):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                        continue
                    types = set(o for _, _, o in target_graph.triples((value, RDF.type, None)))
                    satisfies_all_groups = all(
                        any(
                            _is_subclass_of_or_self(target_graph, value_type, cls)
                            for value_type in types
                            for cls in group
                        )
                        for group in self.class_groups
                    )
                    if not satisfies_all_groups:
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return ClassConstraintComponent


def _build_node_kind_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.value_constraints import (
        NodeKindConstraintComponent as _OriginalNodeKindComponent,
    )

    class NodeKindConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``NodeKindConstraintComponent`` to add
        SHACL 1.2's list-valued ``sh:nodeKind`` (only the four "pure" kinds
        - ``sh:IRI``/``sh:BlankNode``/``sh:Literal``/``sh:TripleTerm`` - are
        valid list members per spec, not the combined forms like
        ``sh:BlankNodeOrIRI`` which stay single-value-only). Delegates to a
        real instance of pySHACL's own component for the plain single-value
        case (byte-for-byte parity), except scalar ``sh:TripleTerm`` which is
        handled natively the same way as list-valued forms because pySHACL has
        no built-in concept of triple terms. Native evaluation
        (``_matches_node_kind``, reused from the pre-migration native pass)
        uses ``_is_encoded_triple_term`` to recognize a ``sh:TripleTerm``-kind
        value correctly, since a real triple term is already flattened into a
        plain content-addressed URI by the time this component's ``evaluate()``
        sees it.
        """

        shacl_constraint_component = SH.NodeKindConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            values = list(shape.sg.objects(shape.node, SH.nodeKind))
            if len(values) != 1:
                raise ValueError(
                    f"NodeKindConstraintComponent must have exactly one sh:nodeKind predicate, "
                    f"found {len(values)} on '{shape.node}'."
                )
            value = values[0]
            self.is_list_valued = _is_shacl_list(shape.sg.graph, value)
            if self.is_list_valued:
                self.node_kinds = _shacl_list_members(shape.sg.graph, value)
                self.delegate = None
            elif value == SH.TripleTerm:
                self.node_kinds = [value]
                self.delegate = None
            else:
                self.delegate = _OriginalNodeKindComponent(shape)

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.nodeKind]

        @classmethod
        def constraint_name(cls) -> str:
            return "NodeKindConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            if self.delegate is not None:
                return self.delegate.evaluate(executor, target_graph, focus_value_nodes, _evaluation_path)

            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    is_tt = _is_encoded_triple_term(target_graph, value)
                    if not any(_matches_node_kind_encoded(value, kind, is_tt) for kind in self.node_kinds):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return NodeKindConstraintComponent


def _matches_node_kind_encoded(value: Any, node_kind: Any, is_triple_term: bool) -> bool:
    from rdflib import BNode

    if is_triple_term:
        return node_kind == SH.TripleTerm
    if isinstance(value, Literal):
        return node_kind == SH.Literal
    if isinstance(value, BNode):
        return node_kind == SH.BlankNode
    if isinstance(value, URIRef):
        return node_kind == SH.IRI
    return False


def _matches_any_datatype_encoded(value: Any, datatypes: list[Any]) -> bool:
    """Datatype matching for a value from the *encoded* graph. A real
    ``DirLangString`` object never reaches here (``TripleTermAdapter``
    flattens it into a plain ``Literal`` carrying starlayergraph's own internal
    packing datatype URI before pySHACL ever sees it - see
    ``adapters.py::_encode_node``), so the usual ``is_dirlangstring_like``
    check would always be ``False`` even for a genuine RDF 1.2
    direction-tagged string. ``_try_decode_dirlangstring`` recognizes the
    encoded form directly (a pure function keyed off the fixed packing
    datatype URI, not adapter-instance state, so no back-reference needed
    here unlike triple terms).
    """
    from rdflib import RDF, XSD

    from starshacl.adapters import _try_decode_dirlangstring

    if not isinstance(value, Literal):
        return False
    if _try_decode_dirlangstring(value) is not None:
        return RDF_DIR_LANG_STRING in datatypes
    effective = value.datatype if value.datatype is not None else (RDF.langString if value.language else XSD.string)
    return effective in datatypes


def _build_datatype_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.value_constraints import (
        DatatypeConstraintComponent as _OriginalDatatypeComponent,
    )

    class DatatypeConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``DatatypeConstraintComponent`` to add two
        SHACL 1.2 cases pySHACL 0.40 gets wrong:

        - list-valued ``sh:datatype`` (union of choices) - pySHACL only
          ever accepts a single IRI value.
        - ``sh:datatype rdf:dirLangString`` - a ``DirLangString`` is encoded
          internally (``starlayergraph``) as a ``Literal`` whose datatype
          is starlayergraph's own packing URI, never the real ``rdf:dirLangString``,
          so pySHACL's own datatype-equality check always reports a
          spurious violation for genuinely well-formed values.

        Delegates to a real instance of pySHACL's own component for every
        other single-IRI value (byte-for-byte parity, including its
        SPARQL-1.1 ill-typed-literal detection via ``_assert_actual_datatype``
        - not something to risk reimplementing by hand for a predicate this
        widely used).
        """

        shacl_constraint_component = SH.DatatypeConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from starshacl.validator import _is_shacl_list, _shacl_list_members

            values = list(shape.sg.objects(shape.node, SH.datatype))
            if len(values) != 1:
                raise ValueError(
                    f"DatatypeConstraintComponent must have exactly one sh:datatype predicate, "
                    f"found {len(values)} on '{shape.node}'."
                )
            value = values[0]
            # Per-constraint sh:severity/sh:deactivated via RDF-1.2 inline
            # reification annotation (SHACL 1.2 Core) - distinct from, and
            # finer-grained than, this shape's own sh:severity/sh:deactivated
            # (already handled generically by pySHACL itself for every
            # constraint). See _annotation_value's own docstring. Confirmed
            # via the W3C SHACL 1.2 test suite's severity-003/deactivated-003
            # fixtures.
            self.annotation_deactivated = (
                _annotation_value(shape.sg.graph, shape.node, SH.datatype, value, SH.deactivated) == Literal(True)
            )
            self.annotation_severity = _annotation_value(shape.sg.graph, shape.node, SH.datatype, value, SH.severity)
            self.is_list_valued = _is_shacl_list(shape.sg.graph, value)
            self.delegate = None
            if self.is_list_valued:
                self.datatypes = _shacl_list_members(shape.sg.graph, value)
            elif value == RDF_DIR_LANG_STRING:
                self.datatypes = [value]
            else:
                self.delegate = _OriginalDatatypeComponent(shape)

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.datatype]

        @classmethod
        def constraint_name(cls) -> str:
            return "DatatypeConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            if self.annotation_deactivated:
                return True, []

            if self.delegate is not None:
                non_conformant_result, reports = self.delegate.evaluate(
                    executor, target_graph, focus_value_nodes, _evaluation_path
                )
            else:
                reports = []
                non_conformant = False
                for focus_node, value_nodes in focus_value_nodes.items():
                    for value in value_nodes:
                        if not _matches_any_datatype_encoded(value, self.datatypes):
                            non_conformant = True
                            reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                non_conformant_result = not non_conformant

            if self.annotation_severity is not None:
                reports = [
                    (
                        desc,
                        r_node,
                        [
                            (s, p, self.annotation_severity) if (s == r_node and p == SH.resultSeverity) else (s, p, o)
                            for s, p, o in r_triples
                        ],
                    )
                    for desc, r_node, r_triples in reports
                ]
            return non_conformant_result, reports

    return DatatypeConstraintComponent


def _effective_language_encoded(value: Any) -> str | None:
    from starshacl.adapters import _try_decode_dirlangstring

    decoded = _try_decode_dirlangstring(value)
    if decoded is not None:
        return decoded.language
    if isinstance(value, Literal) and value.language:
        return value.language
    return None


def _effective_language_direction_key_encoded(value: Any) -> tuple[str, Any] | None:
    from starshacl.adapters import _try_decode_dirlangstring

    decoded = _try_decode_dirlangstring(value)
    if decoded is not None:
        return (decoded.language, decoded.direction)
    if isinstance(value, Literal) and value.language:
        return (value.language, None)
    return None


def _lang_matches_range(tag: str, range_: str) -> bool:
    tag = tag.lower()
    range_ = range_.lower()
    if range_ == "*":
        return bool(tag)
    return tag == range_ or tag.startswith(range_ + "-")


def _build_language_in_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class LanguageInConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Fully replaces (not shadows-for-one-case-only) pySHACL's own
        ``LanguageInConstraintComponent``: pySHACL's own check keys off
        ``Literal.language``, which is never set for an encoded
        ``DirLangString`` value (stored via a special ``datatype=``, not
        ``lang=``), so any RDF 1.2 direction-tagged string value always
        spuriously fails, regardless of its real language tag. Matching
        otherwise reproduces pySHACL's own basic language-range filtering
        (SPARQL ``langMatches``) exactly for the plain-language-tag case.
        Base direction plays no part in the match - per spec,
        ``sh:languageIn`` is about the language tag component only.
        """

        shacl_constraint_component = SH.LanguageInConstraintComponent
        shape_expecting = False
        list_taking = True

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from starshacl.validator import _shacl_list_members

            values = list(shape.sg.objects(shape.node, SH.languageIn))
            if len(values) != 1:
                raise ValueError(
                    f"LanguageInConstraintComponent must have exactly one sh:languageIn predicate, "
                    f"found {len(values)} on '{shape.node}'."
                )
            self.ranges = [str(r) for r in _shacl_list_members(shape.sg.graph, values[0])]

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.languageIn]

        @classmethod
        def constraint_name(cls) -> str:
            return "LanguageInConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            for focus_node, value_nodes in focus_value_nodes.items():
                for value in value_nodes:
                    language = _effective_language_encoded(value)
                    if language is None or not any(_lang_matches_range(language, r) for r in self.ranges):
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return LanguageInConstraintComponent


def _build_unique_lang_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class UniqueLangConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Fully replaces pySHACL's own ``UniqueLangConstraintComponent``:
        the SHACL 1.2 Core spec extends the uniqueness condition to include
        base direction for ``rdf:dirLangString`` values (``"1"@ar--rtl`` and
        ``"1"@ar--ltr`` are different, as is the pair ``"1"@ar--rtl`` and
        ``"1"@ar``) - pySHACL has no notion of this, and since an encoded
        ``DirLangString`` value never has ``Literal.language`` set, pySHACL
        doesn't even group it with same-language values at all, silently
        missing genuine duplicates. One violation per over-used (language,
        direction) pair, no ``sh:value`` - matching pySHACL's own
        (already-correct) behavior for the plain-langString case.
        """

        shacl_constraint_component = SH.UniqueLangConstraintComponent
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            from rdflib import XSD

            values = list(shape.sg.objects(shape.node, SH.uniqueLang))
            if len(values) != 1:
                raise ValueError(
                    f"UniqueLangConstraintComponent must have exactly one sh:uniqueLang predicate, "
                    f"found {len(values)} on '{shape.node}'."
                )
            value = values[0]
            # See SingleLineConstraintComponent's identical guard: a string
            # literal like "false" is truthy in Python, so without checking
            # the datatype, sh:uniqueLang "false" would silently enable the
            # check instead of disabling it.
            if not (isinstance(value, Literal) and value.datatype == XSD.boolean):
                raise ValueError(
                    f"sh:uniqueLang on '{shape.node}' must be a xsd:boolean literal, got {value!r}."
                )
            # Exact-term comparison against "true"^^xsd:boolean specifically,
            # not bool(value.value) - the latter uses XSD's *value*-space
            # conversion, which also accepts "1"^^xsd:boolean as true. The
            # spec only mentions "true" for this predicate, so "1" (a
            # distinct term, even though value-equal) must leave the
            # constraint inactive, not silently enable it. Confirmed via the
            # W3C SHACL 1.2 test suite's uniqueLang-002 fixture.
            self.enabled = str(value) == "true"

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.uniqueLang]

        @classmethod
        def constraint_name(cls) -> str:
            return "UniqueLangConstraintComponent"

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            if not self.enabled:
                return True, reports
            for focus_node, value_nodes in focus_value_nodes.items():
                counts: dict[tuple[str, Any], int] = {}
                for value in value_nodes:
                    key = _effective_language_direction_key_encoded(value)
                    if key is None:
                        continue
                    counts[key] = counts.get(key, 0) + 1
                for count in counts.values():
                    if count >= 2:
                        non_conformant = True
                        reports.append(self.make_v_result(target_graph, focus_node))
            return (not non_conformant), reports

    return UniqueLangConstraintComponent


class _PathEvalGraphAdapter:
    """Minimal duck-typed stand-in for pySHACL's internal ``ShapesGraph``
    wrapper, whose only use inside ``value_nodes_from_path`` is
    ``sg.graph.objects(...)`` for walking SHACL property path structures -
    a plain rdflib-compatible graph is all it actually needs.
    """

    def __init__(self, graph: Any) -> None:
        self.graph = graph


def _compares_favorably(value: Any, other: Any, predicate: Any) -> bool:
    """Whether ``value`` satisfies ``sh:lessThan``/``sh:lessThanOrEquals``
    against ``other``, per SPARQL's ``<``/``<=`` operators. Incomparable
    values (per spec, "the two values cannot be compared") count as failing.
    """
    try:
        if predicate == SH.lessThan:
            return bool(value < other)
        return bool(value < other or value == other)
    except TypeError:
        return False


def _build_property_pair_component(predicate: Any, delegate_cls: Any, mode: str) -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent

    class PropertyPairConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own property-pair component (``sh:equals``/
        ``sh:disjoint``/``sh:lessThan``/``sh:lessThanOrEquals``) to add
        SHACL 1.2's generalization of the comparison value to a full
        property path, not just a simple predicate IRI. pySHACL only
        supports a simple-IRI value for these four predicates; given a
        complex path value it silently treats it as resolving to an empty
        node set rather than evaluating the path, which makes ``sh:equals``
        spuriously fail (nothing can be "in" an empty set) and
        ``sh:disjoint``/``sh:lessThan``/``sh:lessThanOrEquals`` spuriously
        pass (nothing can overlap with, or compare unfavorably against, an
        empty set) - not merely unimplemented, but actively wrong.

        Delegates to a real instance of pySHACL's own component when every
        value is a simple IRI (byte-for-byte parity); native evaluation
        (reusing pySHACL's own ``value_nodes_from_path`` path evaluator
        rather than reimplementing SHACL property path resolution) only
        once a complex path value is actually present - and then covers
        *all* the shape's values for this predicate together, plain and
        complex alike, since pySHACL's own multi-value-AND semantics (each
        ``sh:equals`` triple, of possibly several, contributes independently)
        aren't easily split between a delegate and native evaluation.
        """

        shacl_constraint_component = SH[delegate_cls.__name__]
        shape_expecting = False
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            values = list(shape.sg.objects(shape.node, predicate))
            if len(values) < 1:
                raise ValueError(
                    f"{delegate_cls.__name__} must have at least one {predicate} predicate, "
                    f"found none on '{shape.node}'."
                )
            has_complex = any(not isinstance(v, URIRef) for v in values)
            self.path_values = values
            self.delegate = None if has_complex else delegate_cls(shape)

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [predicate]

        @classmethod
        def constraint_name(cls) -> str:
            return delegate_cls.constraint_name()

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            if self.delegate is not None:
                return self.delegate.evaluate(executor, target_graph, focus_value_nodes, _evaluation_path)

            from pyshacl.helper.expression_helper import value_nodes_from_path

            reports: list[Any] = []
            non_conformant = False
            path_graph_context = _PathEvalGraphAdapter(self.shape.sg.graph)

            for path_value in self.path_values:
                for focus_node, value_nodes in focus_value_nodes.items():
                    other_nodes = value_nodes_from_path(path_graph_context, focus_node, path_value, target_graph)

                    if mode == "equals":
                        for value in value_nodes:
                            if value not in other_nodes:
                                non_conformant = True
                                reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                        for other in other_nodes:
                            if other not in value_nodes:
                                non_conformant = True
                                reports.append(self.make_v_result(target_graph, focus_node, value_node=other))
                    elif mode == "disjoint":
                        for value in value_nodes:
                            if value in other_nodes:
                                non_conformant = True
                                reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
                    else:
                        # Spec: "for each pair of a value node and a member
                        # of $otherNodes" that fails the comparison, one
                        # result - a value can legitimately produce more
                        # than one violation, one per failing partner.
                        for value in value_nodes:
                            for other in other_nodes:
                                if not _compares_favorably(value, other, predicate):
                                    non_conformant = True
                                    reports.append(self.make_v_result(target_graph, focus_node, value_node=value))
            return (not non_conformant), reports

    return PropertyPairConstraintComponent


def _build_and_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.logical_constraints import (
        AndConstraintComponent as _Original,
    )
    from pyshacl.errors import ReportableRuntimeError, ValidationFailure

    class AndConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``AndConstraintComponent``. For every
        ``sh:and`` list that contains no shape needing full-batch treatment
        (see ``_shape_needs_full_batch`` - currently, one using
        ``sh:uniqueValuesFor``), this delegates the *entire* evaluation to a
        real instance of pySHACL's own unmodified component (literally the
        same code object, same ``self.shape``) - zero behavior change for
        the overwhelming majority of shapes, which never touch a cross-node
        predicate.

        Only once a list actually contains such a shape does this run its
        own mixed evaluation: full-batch shapes are invoked once with
        ``focus`` set to every value node this operator resolved across all
        its own focus nodes (not one at a time), so they can correctly
        compare candidates against each other; ordinary shapes in the same
        list are still evaluated per-node exactly as pySHACL would. This is
        what fixes the composition bug documented on
        ``UniqueValuesForConstraintComponent``: before this, nesting
        ``sh:uniqueValuesFor`` inside ``sh:and`` silently missed real
        duplicates, because pySHACL's own recursion only ever shows a
        composed shape one node at a time.
        """

        shacl_constraint_component = SH.AndConstraintComponent
        shape_expecting = True
        list_taking = True

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self._original = _Original(shape)
            self.and_list = self._original.and_list

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH["and"]]

        @classmethod
        def constraint_name(cls) -> str:
            return "AndConstraintComponent"

        def make_generic_messages(self, datagraph: Any, focus_node: Any, value_node: Any) -> list[Any]:
            return self._original.make_generic_messages(datagraph, focus_node, value_node)

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            for and_c in self.and_list:
                if self._needs_full_batch(and_c):
                    _nc, _r = self._evaluate_and_constraint_mixed(
                        executor, and_c, target_graph, focus_value_nodes, _evaluation_path
                    )
                else:
                    _nc, _r = self._original._evaluate_and_constraint(
                        executor, and_c, target_graph, focus_value_nodes, _evaluation_path
                    )
                non_conformant = non_conformant or _nc
                reports.extend(_r)
            return (not non_conformant), reports

        def _needs_full_batch(self, and_c: Any) -> bool:
            sg = self.shape.sg.graph
            for a in set(sg.items(and_c)):
                if self.shape.sg.is_filtered_out_shape(a):
                    continue
                and_shape = self.shape.get_other_shape(a)
                if and_shape and _shape_needs_full_batch(and_shape):
                    return True
            return False

        def _evaluate_and_constraint_mixed(
            self, executor: Any, and_c: Any, target_graph: Any, focus_value_nodes: dict, _evaluation_path: list
        ) -> tuple[bool, list[Any]]:
            _reports: list[Any] = []
            _non_conformant = False
            sg = self.shape.sg.graph
            and_list = set(sg.items(and_c))
            if len(and_list) < 1:
                raise ReportableRuntimeError("The list associated with sh:and is not a valid RDF list.")
            and_shapes = set()
            for a in and_list:
                if self.shape.sg.is_filtered_out_shape(a):
                    continue
                and_shape = self.shape.get_other_shape(a)
                if not and_shape:
                    raise ReportableRuntimeError(
                        "Shape pointed to by sh:and does not exist or is not a well-formed SHACL Shape."
                    )
                and_shapes.add(and_shape)
            if not and_shapes:
                return _non_conformant, _reports

            all_values = list({v for value_nodes in focus_value_nodes.values() for v in value_nodes})

            full_batch_conforms: dict[Any, dict] = {}
            per_node_shapes = []
            for and_shape in and_shapes:
                if _shape_needs_full_batch(and_shape) and all_values:
                    conforms_per_value, _ = _evaluate_shape_for_all_values(
                        and_shape, executor, target_graph, all_values, _evaluation_path
                    )
                    full_batch_conforms[and_shape] = conforms_per_value
                else:
                    per_node_shapes.append(and_shape)

            for f, value_nodes in focus_value_nodes.items():
                for v in value_nodes:
                    passed_all = True
                    for conforms_map in full_batch_conforms.values():
                        if not conforms_map.get(v, True):
                            passed_all = False
                    for and_shape in per_node_shapes:
                        try:
                            _is_conform, _r = and_shape.validate(
                                executor, target_graph, focus=v, _evaluation_path=_evaluation_path[:]
                            )
                        except ValidationFailure as e:
                            raise e
                        passed_all = passed_all and _is_conform
                    if not passed_all:
                        _non_conformant = True
                        _reports.append(self.make_v_result(target_graph, f, value_node=v))
            return _non_conformant, _reports

    return AndConstraintComponent


def _build_or_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.logical_constraints import (
        OrConstraintComponent as _Original,
    )
    from pyshacl.errors import ReportableRuntimeError, ValidationFailure

    class OrConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``OrConstraintComponent`` - see
        ``AndConstraintComponent``'s docstring for the full rationale, the
        same delegate-unless-needed structure applies here with "at least
        one member conforms" combination logic instead of "all members".
        """

        shacl_constraint_component = SH.OrConstraintComponent
        shape_expecting = True
        list_taking = True

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self._original = _Original(shape)
            self.or_list = self._original.or_list

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH["or"]]

        @classmethod
        def constraint_name(cls) -> str:
            return "OrConstraintComponent"

        def make_generic_messages(self, datagraph: Any, focus_node: Any, value_node: Any) -> list[Any]:
            return self._original.make_generic_messages(datagraph, focus_node, value_node)

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            for or_c in self.or_list:
                if self._needs_full_batch(or_c):
                    _nc, _r = self._evaluate_or_constraint_mixed(
                        executor, or_c, target_graph, focus_value_nodes, _evaluation_path
                    )
                else:
                    _nc, _r = self._original._evaluate_or_constraint(
                        executor, or_c, target_graph, focus_value_nodes, _evaluation_path
                    )
                non_conformant = non_conformant or _nc
                reports.extend(_r)
            return (not non_conformant), reports

        def _needs_full_batch(self, or_c: Any) -> bool:
            sg = self.shape.sg.graph
            for o in set(sg.items(or_c)):
                if self.shape.sg.is_filtered_out_shape(o):
                    continue
                or_shape = self.shape.get_other_shape(o)
                if or_shape and _shape_needs_full_batch(or_shape):
                    return True
            return False

        def _evaluate_or_constraint_mixed(
            self, executor: Any, or_c: Any, target_graph: Any, focus_value_nodes: dict, _evaluation_path: list
        ) -> tuple[bool, list[Any]]:
            _reports: list[Any] = []
            _non_conformant = False
            sg = self.shape.sg.graph
            or_list = set(sg.items(or_c))
            if len(or_list) < 1:
                raise ReportableRuntimeError("The list associated with sh:or is not a valid RDF list.")
            or_shapes = set()
            for o in or_list:
                if self.shape.sg.is_filtered_out_shape(o):
                    continue
                or_shape = self.shape.get_other_shape(o)
                if not or_shape:
                    raise ReportableRuntimeError(
                        "Shape pointed to by sh:or does not exist or is not a well-formed SHACL Shape."
                    )
                or_shapes.add(or_shape)
            if not or_shapes:
                return _non_conformant, _reports

            all_values = list({v for value_nodes in focus_value_nodes.values() for v in value_nodes})

            full_batch_conforms: dict[Any, dict] = {}
            per_node_shapes = []
            for or_shape in or_shapes:
                if _shape_needs_full_batch(or_shape) and all_values:
                    conforms_per_value, _ = _evaluate_shape_for_all_values(
                        or_shape, executor, target_graph, all_values, _evaluation_path
                    )
                    full_batch_conforms[or_shape] = conforms_per_value
                else:
                    per_node_shapes.append(or_shape)

            for f, value_nodes in focus_value_nodes.items():
                for v in value_nodes:
                    passed_any = False
                    for conforms_map in full_batch_conforms.values():
                        if conforms_map.get(v, False):
                            passed_any = True
                    for or_shape in per_node_shapes:
                        try:
                            _is_conform, _r = or_shape.validate(
                                executor, target_graph, focus=v, _evaluation_path=_evaluation_path[:]
                            )
                        except ValidationFailure as e:
                            raise e
                        passed_any = passed_any or _is_conform
                    if not passed_any:
                        _non_conformant = True
                        _reports.append(self.make_v_result(target_graph, f, value_node=v))
            return _non_conformant, _reports

    return OrConstraintComponent


def _build_xone_component() -> Any:
    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.logical_constraints import (
        XoneConstraintComponent as _Original,
    )
    from pyshacl.errors import ReportableRuntimeError, ValidationFailure

    class XoneConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``XoneConstraintComponent`` - see
        ``AndConstraintComponent``'s docstring for the full rationale, the
        same delegate-unless-needed structure applies here with "exactly
        one member conforms" combination logic.
        """

        shacl_constraint_component = SH.XoneConstraintComponent
        shape_expecting = True
        list_taking = True

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self._original = _Original(shape)
            self.xone_nodes = self._original.xone_nodes

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.xone]

        @classmethod
        def constraint_name(cls) -> str:
            return "XoneConstraintComponent"

        def make_generic_messages(self, datagraph: Any, focus_node: Any, value_node: Any) -> list[Any]:
            return self._original.make_generic_messages(datagraph, focus_node, value_node)

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            for xone_c in self.xone_nodes:
                if self._needs_full_batch(xone_c):
                    _nc, _r = self._evaluate_xone_constraint_mixed(
                        executor, xone_c, target_graph, focus_value_nodes, _evaluation_path
                    )
                else:
                    _nc, _r = self._original._evaluate_xone_constraint(
                        executor, xone_c, target_graph, focus_value_nodes, _evaluation_path
                    )
                non_conformant = non_conformant or _nc
                reports.extend(_r)
            return (not non_conformant), reports

        def _needs_full_batch(self, xone_c: Any) -> bool:
            sg = self.shape.sg.graph
            for x in list(sg.items(xone_c)):
                if self.shape.sg.is_filtered_out_shape(x):
                    continue
                xone_shape = self.shape.get_other_shape(x)
                if xone_shape and _shape_needs_full_batch(xone_shape):
                    return True
            return False

        def _evaluate_xone_constraint_mixed(
            self, executor: Any, xone_c: Any, target_graph: Any, focus_value_nodes: dict, _evaluation_path: list
        ) -> tuple[bool, list[Any]]:
            _reports: list[Any] = []
            _non_conformant = False
            sg = self.shape.sg.graph
            xone_list = list(sg.items(xone_c))
            if len(xone_list) < 1:
                raise ReportableRuntimeError("The list associated with sh:xone is not a valid RDF list.")
            xone_shapes = []
            for x in xone_list:
                if self.shape.sg.is_filtered_out_shape(x):
                    continue
                xone_shape = self.shape.get_other_shape(x)
                if not xone_shape:
                    raise ReportableRuntimeError(
                        "Shape pointed to by sh:xone does not exist or is not a well-formed SHACL Shape."
                    )
                xone_shapes.append(xone_shape)
            if not xone_shapes:
                return _non_conformant, _reports

            all_values = list({v for value_nodes in focus_value_nodes.values() for v in value_nodes})

            full_batch_conforms: dict[Any, dict] = {}
            per_node_shapes = []
            for xone_shape in xone_shapes:
                if xone_shape in full_batch_conforms or xone_shape in per_node_shapes:
                    continue
                if _shape_needs_full_batch(xone_shape) and all_values:
                    conforms_per_value, _ = _evaluate_shape_for_all_values(
                        xone_shape, executor, target_graph, all_values, _evaluation_path
                    )
                    full_batch_conforms[xone_shape] = conforms_per_value
                else:
                    per_node_shapes.append(xone_shape)

            for f, value_nodes in focus_value_nodes.items():
                for v in value_nodes:
                    passed_count = 0
                    for xone_shape in xone_shapes:
                        if xone_shape in full_batch_conforms:
                            if full_batch_conforms[xone_shape].get(v, False):
                                passed_count += 1
                            continue
                        try:
                            _is_conform, _r = xone_shape.validate(
                                executor, target_graph, focus=v, _evaluation_path=_evaluation_path[:]
                            )
                        except ValidationFailure as e:
                            raise e
                        if _is_conform:
                            passed_count += 1
                    if passed_count != 1:
                        _non_conformant = True
                        _reports.append(self.make_v_result(target_graph, f, value_node=v))
            return _non_conformant, _reports

    return XoneConstraintComponent


def _build_not_component() -> Any:
    from warnings import warn

    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.logical_constraints import (
        NotConstraintComponent as _Original,
    )
    from pyshacl.errors import ShapeRecursionWarning, ValidationFailure

    class NotConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``NotConstraintComponent`` - see
        ``AndConstraintComponent``'s docstring for the full rationale. For
        ``sh:not``, "full-batch" means: evaluate the negated shape once
        with every value node this operator resolved as ``focus``, so a
        cross-node predicate like ``sh:uniqueValuesFor`` sees the real
        comparison set instead of one isolated node - then negate each
        value's own per-value result (from the returned reports'
        ``sh:focusNode`` markers), not one shared aggregate answer.
        """

        shacl_constraint_component = SH.NotConstraintComponent
        shape_expecting = True
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self._original = _Original(shape)
            self.not_list = self._original.not_list

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH["not"]]

        @classmethod
        def constraint_name(cls) -> str:
            return "NotConstraintComponent"

        def make_generic_messages(self, datagraph: Any, focus_node: Any, value_node: Any) -> list[Any]:
            return self._original.make_generic_messages(datagraph, focus_node, value_node)

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False
            potentially_recursive = self.recursion_triggers(_evaluation_path)
            for not_c in self.not_list:
                if self.shape.sg.is_filtered_out_shape(not_c):
                    continue
                found_not_shape = self.shape.get_other_shape(not_c)
                if found_not_shape is not None and _shape_needs_full_batch(found_not_shape):
                    _nc, _r = self._evaluate_not_constraint_mixed(
                        executor,
                        found_not_shape,
                        target_graph,
                        focus_value_nodes,
                        potentially_recursive,
                        _evaluation_path,
                    )
                else:
                    _nc, _r = self._original._evaluate_not_constraint(
                        executor, not_c, target_graph, focus_value_nodes, potentially_recursive, _evaluation_path
                    )
                non_conformant = non_conformant or _nc
                reports.extend(_r)
            return (not non_conformant), reports

        def _evaluate_not_constraint_mixed(
            self,
            executor: Any,
            found_not_shape: Any,
            target_graph: Any,
            focus_value_nodes: dict,
            potentially_recursive: Any,
            _evaluation_path: list,
        ) -> tuple[bool, list[Any]]:
            _reports: list[Any] = []
            _non_conformant = False
            if potentially_recursive and found_not_shape in potentially_recursive:
                warn(ShapeRecursionWarning(_evaluation_path), stacklevel=2)
                return _non_conformant, _reports

            all_values = list({v for value_nodes in focus_value_nodes.values() for v in value_nodes})
            if not all_values:
                return _non_conformant, _reports

            try:
                conforms_per_value, _ = _evaluate_shape_for_all_values(
                    found_not_shape, executor, target_graph, all_values, _evaluation_path
                )
            except ValidationFailure as e:
                raise e

            for f, value_nodes in focus_value_nodes.items():
                for v in value_nodes:
                    if conforms_per_value.get(v, True):
                        # in this case, we _dont_ want to conform!
                        _non_conformant = True
                        _reports.append(self.make_v_result(target_graph, f, value_node=v))
            return _non_conformant, _reports

    return NotConstraintComponent


def _build_node_component() -> Any:
    from warnings import warn

    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.shape_based_constraints import (
        NodeConstraintComponent as _Original,
    )
    from pyshacl.errors import ReportableRuntimeError, ShapeRecursionWarning

    class NodeConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``NodeConstraintComponent`` - see
        ``AndConstraintComponent``'s docstring for the full rationale.
        ``sh:node`` has the identical per-value-node recursion pattern as
        the four logical operators (confirmed by reading
        ``pyshacl/constraints/core/shape_based_constraints.py::
        NodeConstraintComponent._evaluate_node_shape``), so it needs the
        same fix. This is also the mechanism behind the ``sh:property``
        case: ``sh:property``'s own per-value recursion (unpatched, and
        left that way - its target must be a *property* shape, which
        ``sh:uniqueValuesFor`` can't sit on directly) hands each path
        value one at a time to the property shape's own ``sh:node``, which
        is what actually truncates the batch - patching ``sh:node`` here
        covers that path too, at whatever depth it's reached from.
        """

        shacl_constraint_component = SH.NodeConstraintComponent
        shape_expecting = True
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self._original = _Original(shape)
            self.node_shapes = self._original.node_shapes

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.node]

        @classmethod
        def constraint_name(cls) -> str:
            return "NodeConstraintComponent"

        def make_generic_messages(self, datagraph: Any, focus_node: Any, value_node: Any) -> list[Any]:
            return self._original.make_generic_messages(datagraph, focus_node, value_node)

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False

            value_node_count = sum(len(v) for v in focus_value_nodes.values())
            if value_node_count < 1:
                return True, reports

            potentially_recursive = self.recursion_triggers(_evaluation_path)

            for n_shape in self.node_shapes:
                if self.shape.sg.is_filtered_out_shape(n_shape):
                    continue
                found_node_shape = self.shape.get_other_shape(n_shape)
                if found_node_shape is not None and _shape_needs_full_batch(found_node_shape):
                    _nc, _r = self._evaluate_node_shape_mixed(
                        executor,
                        found_node_shape,
                        target_graph,
                        focus_value_nodes,
                        potentially_recursive,
                        _evaluation_path,
                    )
                else:
                    _nc, _r = self._original._evaluate_node_shape(
                        executor, n_shape, target_graph, focus_value_nodes, potentially_recursive, _evaluation_path
                    )
                non_conformant = non_conformant or _nc
                reports.extend(_r)
            return (not non_conformant), reports

        def _evaluate_node_shape_mixed(
            self,
            executor: Any,
            found_node_shape: Any,
            target_graph: Any,
            focus_value_nodes: dict,
            potentially_recursive: Any,
            _evaluation_path: list,
        ) -> tuple[bool, list[Any]]:
            _reports: list[Any] = []
            _non_conformant = False
            if potentially_recursive and found_node_shape in potentially_recursive:
                warn(ShapeRecursionWarning(_evaluation_path), stacklevel=2)
                return _non_conformant, _reports
            if found_node_shape.is_property_shape:
                raise ReportableRuntimeError("Shape pointed to by sh:node is not a well-formed SHACL NodeShape.")

            all_values = list({v for value_nodes in focus_value_nodes.values() for v in value_nodes})
            if not all_values:
                return _non_conformant, _reports

            conforms_per_value, _ = _evaluate_shape_for_all_values(
                found_node_shape, executor, target_graph, all_values, _evaluation_path
            )

            for f, value_nodes in focus_value_nodes.items():
                for v in value_nodes:
                    if not conforms_per_value.get(v, True):
                        _non_conformant = True
                        _reports.append(self.make_v_result(target_graph, f, value_node=v))
            return _non_conformant, _reports

    return NodeConstraintComponent


def _build_qualified_value_shape_component() -> Any:
    from warnings import warn

    from pyshacl.constraints.constraint_component import ConstraintComponent
    from pyshacl.constraints.core.shape_based_constraints import (
        QualifiedValueShapeConstraintComponent as _Original,
    )
    from pyshacl.errors import (
        ReportableRuntimeError,
        ShapeRecursionWarning,
        ValidationFailure,
    )

    class QualifiedValueShapeConstraintComponent(ConstraintComponent):  # type: ignore[misc]
        """Shadows pySHACL's own ``QualifiedValueShapeConstraintComponent``
        - see ``AndConstraintComponent``'s docstring for the full
        rationale. ``sh:qualifiedValueShape`` has the identical per-value-
        node recursion pattern as the four logical operators (confirmed by
        reading ``pyshacl/constraints/core/shape_based_constraints.py::
        QualifiedValueShapeConstraintComponent._evaluate_value_shape``), for
        both the value shape itself and, when ``sh:qualifiedValueShapesDisjoint``
        is set, each sibling shape - both get the same full-batch treatment
        when they need it, independently.
        """

        shacl_constraint_component = NotImplemented
        shape_expecting = True
        list_taking = False

        def __init__(self, shape: Any) -> None:
            super().__init__(shape)
            self._original = _Original(shape)
            self.value_shapes = self._original.value_shapes
            self.min_count = self._original.min_count
            self.max_count = self._original.max_count
            self.is_disjoint = self._original.is_disjoint

        @classmethod
        def constraint_parameters(cls) -> list[Any]:
            return [SH.qualifiedValueShape, SH.qualifiedMinCount, SH.qualifiedValueShapesDisjoint, SH.qualifiedMaxCount]

        @classmethod
        def constraint_name(cls) -> str:
            return "QualifiedValueShapeConstraintComponent"

        def make_generic_messages(self, datagraph: Any, focus_node: Any, value_node: Any) -> list[Any]:
            return self._original.make_generic_messages(datagraph, focus_node, value_node)

        def evaluate(
            self,
            executor: Any,
            target_graph: Any,
            focus_value_nodes: dict[Any, Any],
            _evaluation_path: list[Any],
        ) -> tuple[bool, list[Any]]:
            reports: list[Any] = []
            non_conformant = False

            value_node_count = sum(len(v) for v in focus_value_nodes.values())
            if not self.is_disjoint and value_node_count < 1 and (self.min_count is None or self.min_count < 1):
                return True, reports

            potentially_recursive = self.recursion_triggers(_evaluation_path)

            for v_shape in self.value_shapes:
                if self.shape.sg.is_filtered_out_shape(v_shape):
                    continue
                other_shape = self.shape.get_other_shape(v_shape)
                if other_shape is not None and self._needs_full_batch_for(v_shape, other_shape):
                    _nc, _r = self._evaluate_value_shape_mixed(
                        executor, v_shape, target_graph, focus_value_nodes, potentially_recursive, _evaluation_path
                    )
                else:
                    _nc, _r = self._original._evaluate_value_shape(
                        executor, v_shape, target_graph, focus_value_nodes, potentially_recursive, _evaluation_path
                    )
                non_conformant = non_conformant or _nc
                reports.extend(_r)
            return (not non_conformant), reports

        def _resolve_sibling_shapes(self, _v_shape: Any) -> set:
            """Every disjoint-sibling shape of ``_v_shape`` (per the spec's
            "sibling shapes" definition: other sh:qualifiedValueShape values
            among sibling property shapes of a shared parent), or an empty
            set if ``sh:qualifiedValueShapesDisjoint`` isn't set. A sibling
            can independently need full-batch treatment even when the
            primary value shape doesn't - the disjoint check invokes
            *sibling* shapes per-value too (``pyshacl``'s own
            ``_evaluate_value_shape``), so this has to be checked wherever
            that per-value invocation is decided, not just for the primary
            value shape.
            """
            if not self.is_disjoint:
                return set()
            sibling_shapes = set()
            parent_shapes = set(self.shape.sg.subjects(SH.property, self.shape.node))
            for p in iter(parent_shapes):
                parent_property_shapes = set(self.shape.sg.objects(p, SH.property))
                for s in iter(parent_property_shapes):
                    parent_property_qualifiedvalueshapes = set(self.shape.sg.objects(s, SH.qualifiedValueShape))
                    for sibling in parent_property_qualifiedvalueshapes:
                        if sibling == _v_shape:
                            continue
                        sibling_shapes.add(sibling)
            sibling_shapes = set(self.shape.get_other_shape(s) for s in sibling_shapes)
            return {s for s in sibling_shapes if s is not None}

        def _needs_full_batch_for(self, _v_shape: Any, other_shape: Any) -> bool:
            if _shape_needs_full_batch(other_shape):
                return True
            return any(_shape_needs_full_batch(sibling) for sibling in self._resolve_sibling_shapes(_v_shape))

        def _evaluate_value_shape_mixed(
            self,
            executor: Any,
            _v_shape: Any,
            target_graph: Any,
            focus_value_nodes: dict,
            potentially_recursive: Any,
            _evaluation_path: list,
        ) -> tuple[bool, list[Any]]:
            _reports: list[Any] = []
            _non_conformant = False
            other_shape = self.shape.get_other_shape(_v_shape)
            if potentially_recursive and other_shape in potentially_recursive:
                warn(ShapeRecursionWarning(_evaluation_path), stacklevel=2)
                return _non_conformant, _reports
            if not other_shape:
                raise ReportableRuntimeError(
                    "Shape pointed to by sh:qualifiedValueShape does not exist or is not a well-formed SHACL Shape."
                )

            sibling_shapes = self._resolve_sibling_shapes(_v_shape)

            all_values = list({v for value_nodes in focus_value_nodes.values() for v in value_nodes})

            other_conforms_per_value: dict = {}
            if all_values and _shape_needs_full_batch(other_shape):
                other_conforms_per_value, _ = _evaluate_shape_for_all_values(
                    other_shape, executor, target_graph, all_values, _evaluation_path
                )

            sibling_conforms_per_value: dict[Any, dict] = {}
            for sibling_shape in sibling_shapes:
                if all_values and _shape_needs_full_batch(sibling_shape):
                    conforms_map, _ = _evaluate_shape_for_all_values(
                        sibling_shape, executor, target_graph, all_values, _evaluation_path
                    )
                    sibling_conforms_per_value[sibling_shape] = conforms_map

            for f, value_nodes in focus_value_nodes.items():
                number_conforms = 0
                for v in value_nodes:
                    try:
                        if v in other_conforms_per_value:
                            _is_conform = other_conforms_per_value[v]
                        else:
                            _is_conform, _r = other_shape.validate(
                                executor, target_graph, focus=v, _evaluation_path=_evaluation_path[:]
                            )
                        if _is_conform:
                            _conforms_to_sibling = False
                            for sibling_shape in sibling_shapes:
                                if sibling_shape in sibling_conforms_per_value:
                                    _c2 = sibling_conforms_per_value[sibling_shape].get(v, True)
                                else:
                                    _c2, _r = sibling_shape.validate(
                                        executor, target_graph, focus=v, _evaluation_path=_evaluation_path[:]
                                    )
                                _conforms_to_sibling = _conforms_to_sibling or _c2
                            if not _conforms_to_sibling:
                                number_conforms += 1
                    except ValidationFailure as e:
                        raise e
                if self.max_count is not None and number_conforms > self.max_count:
                    _non_conformant = True
                    _r = self.make_v_result(target_graph, f, constraint_component=SH.QualifiedMaxCountConstraintComponent)
                    _reports.append(_r)
                if self.min_count is not None and number_conforms < self.min_count:
                    _non_conformant = True
                    _r = self.make_v_result(target_graph, f, constraint_component=SH.QualifiedMinCountConstraintComponent)
                    _reports.append(_r)
            return _non_conformant, _reports

    return QualifiedValueShapeConstraintComponent


_SparqlConstraintComponent = _build_sparql_constraint_component()
_PropertyConstraintComponent = _build_property_constraint_component()
_NodeByExpressionConstraintComponent = _build_node_by_expression_component()
_ReifierShapeConstraintComponent = _build_reifier_shape_component()
_ClosedConstraintComponent = _build_closed_component()
_ClassConstraintComponent = _build_class_component()
_NodeKindConstraintComponent = _build_node_kind_component()
_DatatypeConstraintComponent = _build_datatype_component()
_LanguageInConstraintComponent = _build_language_in_component()
_UniqueLangConstraintComponent = _build_unique_lang_component()
_QualifiedValueShapeConstraintComponent = _build_qualified_value_shape_component()


def _build_all_property_pair_components() -> dict[Any, Any]:
    from pyshacl.constraints.core.property_pair_constraints import (
        DisjointConstraintComponent,
        EqualsConstraintComponent,
        LessThanConstraintComponent,
        LessThanOrEqualsConstraintComponent,
    )

    return {
        SH.equals: _build_property_pair_component(SH.equals, EqualsConstraintComponent, "equals"),
        SH.disjoint: _build_property_pair_component(SH.disjoint, DisjointConstraintComponent, "disjoint"),
        SH.lessThan: _build_property_pair_component(SH.lessThan, LessThanConstraintComponent, "less_than"),
        SH.lessThanOrEquals: _build_property_pair_component(
            SH.lessThanOrEquals, LessThanOrEqualsConstraintComponent, "less_than_or_equals"
        ),
    }


_PROPERTY_PAIR_COMPONENTS = _build_all_property_pair_components()

_NATIVE_COMPONENTS: dict[Any, Any] = {
    SH.someValue: _build_some_value_component(),
    SH.singleLine: _build_single_line_component(),
    SH.subsetOf: _build_subset_of_component(),
    SH.rootClass: _build_root_class_component(),
    SH.uniqueValuesFor: _build_unique_values_for_component(),
    SH.memberShape: _build_member_shape_component(),
    SH.minListLength: _build_min_list_length_component(),
    SH.maxListLength: _build_max_list_length_component(),
    SH.uniqueMembers: _build_unique_members_component(),
    SH.sparql: _SparqlConstraintComponent,
    SH.property: _PropertyConstraintComponent,
    SH.nodeByExpression: _NodeByExpressionConstraintComponent,
    SH.reifierShape: _ReifierShapeConstraintComponent,
    SH.reificationRequired: _ReifierShapeConstraintComponent,
    SH.closed: _ClosedConstraintComponent,
    SH.ignoredProperties: _ClosedConstraintComponent,
    SH["class"]: _ClassConstraintComponent,
    SH.nodeKind: _NodeKindConstraintComponent,
    SH.datatype: _DatatypeConstraintComponent,
    SH.languageIn: _LanguageInConstraintComponent,
    SH.uniqueLang: _UniqueLangConstraintComponent,
    **_PROPERTY_PAIR_COMPONENTS,
    SH["and"]: _build_and_component(),
    SH["or"]: _build_or_component(),
    SH.xone: _build_xone_component(),
    SH["not"]: _build_not_component(),
    SH.node: _build_node_component(),
    SH.qualifiedValueShape: _QualifiedValueShapeConstraintComponent,
    SH.qualifiedMinCount: _QualifiedValueShapeConstraintComponent,
    SH.qualifiedMaxCount: _QualifiedValueShapeConstraintComponent,
    SH.qualifiedValueShapesDisjoint: _QualifiedValueShapeConstraintComponent,
}

# Shape-expecting native predicates whose value must be typed (via
# ensure_shape_typed) before pySHACL's shape-graph loader will recognize it.
# sh:condition isn't a starShacl-native component (it's pySHACL's own SHACL
# 1.2 Rules mechanism), but has the identical problem - it's not on
# pySHACL's own hardcoded shape-discovery predicate list either - so it's
# included here too for one consistent fix strategy rather than two.
SHAPE_EXPECTING_PREDICATES: tuple[Any, ...] = (SH.someValue, SH.memberShape, SH.reifierShape, SH.condition)
