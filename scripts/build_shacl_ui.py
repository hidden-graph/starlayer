"""scripts/build_shacl_ui.py - builds ``starontology/shacl12-shacl-ui.ttl`` (registry entry ``shacl_shacl_ui``), the UI companion of
``shacl_shacl``, and checks that it is complete.

Build-time only: the library never imports this. It reads the stored result, which ``scripts/build_starontology.py``
regenerates from ``build_shacl_ui_graph()`` below.

The registered file is two things:

1. the hand-edited source, ``assets/shacl12-shacl-ui-overlay.ttl``: the property groups, ``sh:group`` / ``sh:order`` on each
   SHACL predicate, the form flags (``stsh:nodeFormField``, ``stsh:propertyFormField``, ``stsh:formMaxCount``,
   ``stsh:nodePrimary``) and two small forms written by hand (a property group's, a shapes graph's);
2. the **form shapes** generated from it: ``stsh:NodeShapeForm`` and ``stsh:PropertyShapeForm``, each a node shape whose
   property shapes are the fields of that kind of shape. A field is one property shape per flagged predicate, named
   ``stsh:<Form>_<prefix>_<local>``, with the predicate's ``sh:group`` and ``sh:order``, a ``sh:maxCount`` where the form
   allows one value, and the ``sh:datatype``, ``sh:nodeKind`` and ``sh:in`` list the predicate has in ``shacl_shacl`` (so a
   number is stored as a number and an enumeration lists its values). A node shape form's field for a predicate flagged
   ``stsh:nodePrimary false`` gets ``stsh:secondary true`` (allowed, but not commonly expected there).

Why this is needed: ``shacl_shacl`` is many small shapes that mostly target the *subjects of one predicate*, which is right for
validation (a name is checked when there is one) and wrong for a form (a shape with no name yet needs a field for one). So no
single shape of ``shacl_shacl`` lists a shape's fields. The forms do, and a tool passes one to ``select_widgets`` as
``shape_node`` with ``shacl_shacl_ui_scores`` and the generic catalog as the scoring graph. A form shape has no
``sh:target*``: it is applied to nothing, so merging it into a shapes graph never changes what validates.

The completeness check, ``missing_fields()``: every predicate ``shacl_shacl`` validates must be a field of some form shape
(the generated ones or the hand-written ones) or be listed in ``EXCLUDED`` with the reason it belongs to another kind of node.
The build fails when one is missing, so the forms cannot fall behind the validation shapes.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGES_STARLAYER = Path(__file__).resolve().parents[1] / "packages" / "starlayer"
if str(_PACKAGES_STARLAYER) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_STARLAYER))

from rdflib import BNode, Graph, Literal, Namespace, URIRef  # noqa: E402
from rdflib.namespace import RDF, RDFS  # noqa: E402

OVERLAY_PATH = Path(__file__).resolve().parent / "assets" / "shacl12-shacl-ui-overlay.ttl"

SH = Namespace("http://www.w3.org/ns/shacl#")
SHUI = Namespace("http://www.w3.org/ns/shacl-ui#")
SHNEX = Namespace("http://www.w3.org/ns/shacl-node-expr#")
STSH = Namespace("https://github.com/hidden-graph/starlayer/ns/shacl#")

# (form name, the class of node it is the form for, the flag that puts a predicate in it)
FORMS = (
    ("NodeShapeForm", SH.NodeShape, STSH.nodeFormField),
    ("PropertyShapeForm", SH.PropertyShape, STSH.propertyFormField),
)

# Predicates shacl_shacl validates that are not a field of any shape's form, because they belong to another kind of node. A
# predicate that belongs in a form of a node kind we have no form for yet (a constraint component, a widget score, a validation
# report) is listed here with that kind, so adding such a form is a visible change.
EXCLUDED: dict[URIRef, str] = {
    **{p: "a field of a shui:WidgetScore, not of a shape" for p in (SHUI.score, SHUI.widget, SHUI.shapesGraphShape, SHUI.dataGraphShape)},
    **{p: "a field of a SPARQL constraint or a constraint component, not of a shape" for p in (SH.select, SH.ask, SH.validator, SH.nodeValidator, SH.propertyValidator, SH.parameter)},
    SH.condition: "a field of a rule, not of a shape",
    **{p: "a field of a prefix declaration or a SPARQL query, not of a shape" for p in (SH.prefixes, SH.declare, SH.prefix, SH.namespace)},
    **{p: "a field of a validation report, not of a shape" for p in (SH.usedDataGraph, SH.usedShapesGraph, SH.usedConfiguration)},
    **{p: "an operator of a property path (the value of sh:path), not a field of a shape" for p in (SH.alternativePath, SH.inversePath, SH.oneOrMorePath, SH.zeroOrMorePath, SH.zeroOrOnePath)},
    **{p: "a field of a node expression (the value of sh:values and the like), not of a shape" for p in (SH.nodes, SH.union, SH.intersection, SH.filterShape)},
    **{p: "a field of a rule (sh:TripleRule, sh:SPARQLRule), not of a shape" for p in (SH.subject, SH.predicate, SH.object, SH.construct)},
    **{p: "RDF list structure or a type, never a field of a form" for p in (RDF.first, RDF.rest, RDF.type)},
}
# Every term of the node expression vocabulary is a field of a node expression, not of a shape.
EXCLUDED_NAMESPACES: dict[str, str] = {str(SHNEX): "a field of a node expression, not of a shape"}


def is_excluded(predicate: URIRef) -> bool:
    return predicate in EXCLUDED or any(str(predicate).startswith(ns) for ns in EXCLUDED_NAMESPACES)


def _field_name(form: str, predicate: URIRef, prefixes: dict[str, str]) -> URIRef:
    for prefix, namespace in sorted(prefixes.items(), key=lambda item: -len(item[1])):
        if str(predicate).startswith(namespace):
            return STSH[f"{form}_{prefix}_{str(predicate)[len(namespace):]}"]
    return STSH[f"{form}_{abs(hash(str(predicate)))}"]


def _copy(graph: Graph, node, out: Graph) -> None:
    """Copy the triples of ``node`` and of the blank nodes under it (an ``sh:in`` list)."""
    pending, seen = [node], set()
    while pending:
        subject = pending.pop()
        if subject in seen:
            continue
        seen.add(subject)
        for predicate, value in graph.predicate_objects(subject):
            out.add((subject, predicate, value))
            if isinstance(value, BNode):
                pending.append(value)


def _constraints_in_shacl_shacl(shacl_shacl: Graph, predicate: URIRef):
    """The datatype, node kind and sh:in list of a predicate in shacl_shacl: those of its first property shape that has one."""
    owners = sorted(shacl_shacl.subjects(SH.path, predicate), key=str)
    for term in (SH.datatype, SH.nodeKind, SH["in"]):
        for owner in owners:
            values = list(shacl_shacl.objects(owner, term))
            if values:
                yield term, values
                break


def build_shacl_ui_graph(overlay: Graph | None = None, shacl_shacl: Graph | None = None) -> Graph:
    """The registered ``shacl_shacl_ui`` graph: the overlay source plus the generated form shapes."""
    from build_meta_shapes import build_meta_shapes_graph
    from starlayer import starontology

    if overlay is None:
        overlay = Graph().parse(str(OVERLAY_PATH), format="turtle")
    if shacl_shacl is None:
        shacl_shacl = build_meta_shapes_graph()
    prefixes = {p: str(ns) for p, ns in starontology._PREFIXES.items()}

    out = Graph()
    for triple in overlay:
        out.add(triple)
    for name, kind, flag in FORMS:
        form = STSH[name]
        out.add((form, RDF.type, SH.NodeShape))
        out.add((form, STSH.formFor, kind))
        out.add((form, RDFS.label, Literal(f"Form for a {str(kind).rsplit('#', 1)[-1]}", lang="en")))
        for predicate in sorted((s for s in set(overlay.subjects(flag, Literal(True))) if isinstance(s, URIRef)), key=str):
            field = _field_name(name, predicate, prefixes)
            out.add((form, SH.property, field))
            out.add((field, RDF.type, SH.PropertyShape))
            out.add((field, SH.path, predicate))
            for term in (SH.group, SH.order):
                for value in overlay.objects(predicate, term):
                    out.add((field, term, value))
            for value in overlay.objects(predicate, STSH.formMaxCount):
                out.add((field, SH.maxCount, value))
            if kind == SH.NodeShape and (predicate, STSH.nodePrimary, Literal(False)) in overlay:
                out.add((field, STSH.secondary, Literal(True)))  # allowed, but not commonly expected on a node shape
            for term, values in _constraints_in_shacl_shacl(shacl_shacl, predicate):
                for value in values:
                    out.add((field, term, value))
                    if isinstance(value, BNode):
                        _copy(shacl_shacl, value, out)
    return out


def validated_predicates(shacl_shacl: Graph) -> set[URIRef]:
    """The predicates shacl_shacl says something about: the path of a property shape, or a predicate whose subjects it targets."""
    found = {p for ps in shacl_shacl.subjects(SH.path, None) for p in shacl_shacl.objects(ps, SH.path) if isinstance(p, URIRef)}
    found |= {o for o in shacl_shacl.objects(None, SH.targetSubjectsOf) if isinstance(o, URIRef)}
    return found


def form_fields(ui: Graph) -> set[URIRef]:
    """The predicates that are a field of some form shape (a shape with ``stsh:formFor``) in the built graph."""
    fields: set = set()
    for form in ui.subjects(STSH.formFor, None):
        for prop in ui.objects(form, SH.property):
            fields.update(p for p in ui.objects(prop, SH.path) if isinstance(p, URIRef))
    return fields


def missing_fields(ui: Graph | None = None, shacl_shacl: Graph | None = None) -> set[URIRef]:
    """Predicates shacl_shacl validates that are neither a field of a form nor excluded with a reason."""
    from build_meta_shapes import build_meta_shapes_graph

    if shacl_shacl is None:
        shacl_shacl = build_meta_shapes_graph()
    if ui is None:
        ui = build_shacl_ui_graph(shacl_shacl=shacl_shacl)
    return {p for p in validated_predicates(shacl_shacl) - form_fields(ui) if not is_excluded(p)}
