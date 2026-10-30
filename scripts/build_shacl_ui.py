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
   allows one value, the ``sh:nodeKind`` the overlay states for the predicate (see below), and the ``sh:datatype``, ``sh:nodeKind``, ``sh:class``, ``sh:in`` list, ``sh:minCount`` and ``sh:maxCount`` the predicate has in
   ``shacl_shacl`` (so a
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

# Predicates shacl_shacl validates that are not a field of any form shape, because they belong to a kind of node that has no form. A
# predicate that belongs in a form of a node kind we have no form for yet (a validation report, a node expression) is listed here
# with that kind, so adding such a form is a visible change. (The SPARQL constraint, rule, constraint component, parameter, validator,
# function, SPARQL target, prefix declaration and widget score forms of GitHub issue #105 took their predicates off this list.)
EXCLUDED: dict[URIRef, str] = {
    **{p: "a field of a validation report, not of a shape" for p in (SH.usedDataGraph, SH.usedShapesGraph, SH.usedConfiguration)},
    **{p: "an operator of a property path (the value of sh:path), not a field of a shape" for p in (SH.alternativePath, SH.inversePath, SH.oneOrMorePath, SH.zeroOrMorePath, SH.zeroOrOnePath)},
    **{p: "a field of a node expression (the value of sh:values and the like), not of a shape; no form for node expressions yet (GitHub issue #67)" for p in (SH.nodes, SH.union, SH.intersection, SH.filterShape)},
    **{p: "RDF list structure, never a field of a form" for p in (RDF.first, RDF.rest)},
    SH.sourceRule: "a field of the reifier of an inferred triple (Inference Rules 9), not of a shape or a rule",
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


SHSH = Namespace("http://www.w3.org/ns/shacl-shacl#")
# The Working Group's rules that apply to one kind of shape only: what a node shape must not have, what a property shape must have.
_KIND_SPECIFIC = {SH.NodeShape: SHSH.NodeShapeShape, SH.PropertyShape: SHSH.PropertyShapeShape}


def _roots(graph: Graph, node) -> set[URIRef]:
    """The named shapes a (possibly nested) property shape belongs to: walk up through blank nodes to the IRIs that hold it."""
    roots, seen, pending = set(), set(), [node]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        for subject, _predicate in graph.subject_predicates(current):
            if isinstance(subject, URIRef):
                roots.add(subject)
            else:
                pending.append(subject)
    return roots


def _owners(shacl_shacl: Graph, predicate: URIRef, kind) -> list:
    """The property shapes of shacl_shacl for a predicate that apply to a kind of shape, in a stable order (blank node labels
    change between builds, so the order is by the named shape that holds them and by their own content)."""
    other = _KIND_SPECIFIC.get(SH.PropertyShape if kind == SH.NodeShape else SH.NodeShape) if kind in _KIND_SPECIFIC else None
    found = []
    for owner in shacl_shacl.subjects(SH.path, predicate):
        roots = _roots(shacl_shacl, owner)
        if other is not None and roots == {other}:
            continue  # a rule for the other kind of shape (NodeShapeShape forbids sh:path; PropertyShapeShape requires it)
        content = tuple(sorted((str(p), "_" if isinstance(v, BNode) else str(v)) for p, v in shacl_shacl.predicate_objects(owner)))
        found.append((sorted(map(str, roots)), content, owner))
    return [owner for _roots_, _content, owner in sorted(found, key=lambda item: (item[0], item[1]))]


def _constraints_in_shacl_shacl(shacl_shacl: Graph, predicate: URIRef, kind):
    """The datatype, node kind, class, sh:in list and cardinality of a predicate in shacl_shacl for a kind of shape: the first
    property shape that applies to it and has the term (a ``sh:maxCount 0`` is a ban, not a limit, and is skipped)."""
    owners = _owners(shacl_shacl, predicate, kind)
    # A form of another kind of element (a SPARQL constraint, a prefix declaration) lists what it requires itself (stsh:formRequired): the
    # same predicate is required in one kind and optional in another, so a minimum count of shacl_shacl is not copied there.
    terms = (SH.datatype, SH.nodeKind, SH["class"], SH["in"], SH.minCount, SH.maxCount) if kind in _KIND_SPECIFIC else (SH.datatype, SH.nodeKind, SH["class"], SH["in"], SH.maxCount)
    for term in terms:
        for owner in owners:
            values = [v for v in shacl_shacl.objects(owner, term) if not (term == SH.maxCount and v == Literal(0))]
            if values:
                yield term, values
                break


def _max_count_in_shacl_shacl(shacl_shacl: Graph, predicate: URIRef, kind) -> bool:
    return any(term == SH.maxCount for term, _values in _constraints_in_shacl_shacl(shacl_shacl, predicate, kind))


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

    def add_field(form, form_name, predicate, kind, required=False):
        field = _field_name(form_name, predicate, prefixes)
        out.add((form, SH.property, field))
        out.add((field, RDF.type, SH.PropertyShape))
        out.add((field, SH.path, predicate))
        for term in (SH.group, SH.order):
            for value in overlay.objects(predicate, term):
                out.add((field, term, value))
        if not _max_count_in_shacl_shacl(shacl_shacl, predicate, kind):
            for value in overlay.objects(predicate, STSH.formMaxCount):  # the form's own limit where shacl_shacl has none
                out.add((field, SH.maxCount, value))
        if required:
            out.add((field, SH.minCount, Literal(1)))
        for holder in overlay.objects(predicate, STSH.formHeldBy):
            out.add((field, STSH.formHeldBy, holder))  # (the field is for a node held by a node of this class)
        for kind_of in overlay.objects(predicate, STSH.formOnlyFor):
            out.add((field, STSH.formOnlyFor, kind_of))  # (the field is for a node of this class)
        if kind == SH.NodeShape and (predicate, STSH.nodePrimary, Literal(False)) in overlay:
            out.add((field, STSH.secondary, Literal(True)))  # allowed, but not commonly expected on a node shape
        found = dict(_constraints_in_shacl_shacl(shacl_shacl, predicate, kind))
        for term in (SH.datatype, SH.nodeKind, SH["class"]):
            if list(overlay.objects(predicate, term)):
                found[term] = list(overlay.objects(predicate, term))  # a constraint the overlay gives: where shacl_shacl has none, or a stricter one (a form may be stricter than validation)
        for term, values in found.items():
            for value in values:
                out.add((field, term, value))
                if isinstance(value, BNode):
                    _copy(shacl_shacl, value, out)

    for name, kind, flag in FORMS:
        form = STSH[name]
        out.add((form, RDF.type, SH.NodeShape))
        out.add((form, STSH.formFor, kind))
        out.add((form, RDFS.label, Literal(f"Form for a {str(kind).rsplit('#', 1)[-1]}", lang="en")))
        for predicate in sorted((s for s in set(overlay.subjects(flag, Literal(True))) if isinstance(s, URIRef)), key=str):
            add_field(form, name, predicate, kind)
    # The forms of the other kinds of element: a form lists its fields (stsh:formFields) and what it requires (stsh:formRequired).
    for form in sorted(overlay.subjects(STSH.formFields, None), key=str):
        kind = overlay.value(form, STSH.formFor)
        name = str(form).rsplit("#", 1)[-1]
        out.add((form, RDF.type, SH.NodeShape))
        if not list(overlay.objects(form, RDFS.label)):
            out.add((form, RDFS.label, Literal(f"Form for a {str(kind).rsplit('#', 1)[-1].rsplit('/', 1)[-1]}", lang="en")))
        required = {p for lst in overlay.objects(form, STSH.formRequired) for p in overlay.items(lst)}
        listed = [predicate for lst in overlay.objects(form, STSH.formFields) for predicate in overlay.items(lst)]
        inherited: list = []
        for base in overlay.objects(form, STSH.formFieldsOf):  # the fields of another kind's form (a parameter is a property shape), less the ones left out
            flag = next(flag for _name, base_kind, flag in FORMS if base_kind == base)
            left_out = {p for lst in overlay.objects(form, STSH.formFieldsExcept) for p in overlay.items(lst)}
            inherited += [(p, base) for p in sorted((s for s in set(overlay.subjects(flag, Literal(True))) if isinstance(s, URIRef)), key=str) if p not in left_out]
        for predicate, base in inherited:
            add_field(form, name, predicate, base, required=predicate in required)
        for predicate in listed:
            if predicate not in {p for p, _base in inherited}:
                add_field(form, name, predicate, kind, required=predicate in required)
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


def vocabulary_shape_predicates(vocabulary: Graph) -> set[URIRef]:
    """The properties the SHACL vocabulary gives a shape: those with ``rdfs:domain`` sh:Shape, sh:NodeShape or sh:PropertyShape
    (GitHub issue #91). shacl_shacl says nothing about some of them (sh:target, sh:targetWhere, sh:unit), but a form needs a field."""
    return {p for kind in (SH.Shape, SH.NodeShape, SH.PropertyShape) for p in vocabulary.subjects(RDFS.domain, kind) if isinstance(p, URIRef)}


def missing_vocabulary_fields(ui: Graph | None = None, vocabulary: Graph | None = None) -> set[URIRef]:
    """Properties of the vocabulary with a shape as their domain that are not a field of a form and not excluded with a reason."""
    from starlayer import starontology

    if vocabulary is None:
        vocabulary = starontology.get_ontology_graph("shacl_vocabulary")
    if ui is None:
        ui = build_shacl_ui_graph()
    return {p for p in vocabulary_shape_predicates(vocabulary) - form_fields(ui) if not is_excluded(p)}


def missing_fields(ui: Graph | None = None, shacl_shacl: Graph | None = None) -> set[URIRef]:
    """Predicates shacl_shacl validates that are neither a field of a form nor excluded with a reason."""
    from build_meta_shapes import build_meta_shapes_graph

    if shacl_shacl is None:
        shacl_shacl = build_meta_shapes_graph()
    if ui is None:
        ui = build_shacl_ui_graph(shacl_shacl=shacl_shacl)
    return {p for p in validated_predicates(shacl_shacl) - form_fields(ui) if not is_excluded(p)}
