"""Name the nodes of a shapes graph in an error message, so it says which shape it is about.

An IRI is named by its prefixed name when the caller has prefixes (the ``sh:`` terms always) and by its text otherwise; a blank node
by the node that holds it ("the property shape of ex:S for ex:name", "the sh:values of ...") since its own label means nothing to a
reader. ``locate`` rewrites the ``<BlankNode value=...>`` / ``<NamedNode value=...>`` an error message got from ``repr()`` that way.
"""

from __future__ import annotations

import re
from typing import Any

import pyoxigraph as ox

from starlayer.shacl.engine.terms import RDF, SH, text

_SH_NAMESPACE = SH.Violation.value[: -len("Violation")]
_REPR = re.compile(r"<(BlankNode|NamedNode) value=([^>]*)>")
_MAX_DEPTH = 8


def short(term: Any, prefixes: dict[str, str] | None = None) -> str:
    """An IRI by its prefixed name (the ``sh:`` namespace always, then ``prefixes``) or its text; a path of one property by that property."""
    kind = getattr(term, "kind", None)
    if kind == "pred":
        term = term.iri
    elif kind is not None:
        return "a complex path"
    if isinstance(term, ox.NamedNode):
        namespaces = sorted({**(prefixes or {}), "sh": _SH_NAMESPACE}.items(), key=lambda item: -len(item[1]))  # str-ok: prefix namespaces are plain strings
        for prefix, namespace in namespaces:
            if term.value.startswith(namespace) and term.value != namespace:
                return f"{prefix}:{term.value[len(namespace):]}"  # str-ok: prefix and namespace are plain strings
    return text(term)


def _path_name(path: Any, prefixes: dict[str, str] | None) -> str:
    """A property path as a reader names it: a single property by its name, any other path (a blank node) as a complex path."""
    return "a complex path" if isinstance(path, ox.BlankNode) else short(path, prefixes)


def describe(graph: Any, node: Any, prefixes: dict[str, str] | None = None, _depth: int = 0) -> str:
    """``node`` as a reader of the shapes graph would name it: an IRI by its name, a blank node by what holds it."""
    if not isinstance(node, ox.BlankNode):
        return short(node, prefixes)
    path = next(iter(graph.objects(node, SH.path)), None)
    links = sorted(((s, p) for s, p, _o in graph.triples((None, None, node))), key=lambda sp: (text(sp[0]), text(sp[1])))
    if _depth < _MAX_DEPTH and links:
        holder, predicate = links[0]
        if predicate == SH.property:
            return f"the property shape of {describe(graph, holder, prefixes, _depth + 1)}" + (f" for {_path_name(path, prefixes)}" if path is not None else "")
        if predicate in (RDF.first, RDF.rest):  # a list cell: named by what holds the list
            return describe(graph, holder, prefixes, _depth + 1)
        return f"the {short(predicate, prefixes)} of {describe(graph, holder, prefixes, _depth + 1)}"
    return f"a shape with path {_path_name(path, prefixes)}" if path is not None else "a blank node shape"


def locate(graph: Any, message: str, prefixes: dict[str, str] | None = None) -> str:
    """``message`` with each ``<BlankNode value=...>`` / ``<NamedNode value=...>`` (a term's ``repr``) named by ``describe``."""

    def name(match: re.Match) -> str:
        term = ox.BlankNode(match.group(2)) if match.group(1) == "BlankNode" else ox.NamedNode(match.group(2))
        return describe(graph, term, prefixes)

    return _REPR.sub(name, message)


def names_a_node(message: str, node: Any) -> bool:
    """Whether ``message`` already says where it is about (a node's repr or, for an IRI, its text)."""
    return _REPR.search(message) is not None or (isinstance(node, ox.NamedNode) and node.value in message)


def add_where(error: Exception, graph: Any, node: Any) -> Exception:
    """``error`` with its message named by ``describe`` and, if it does not say it, prefixed by the node it is about. Returned for ``raise``."""
    message = str(error)
    if getattr(error, "located", False):
        return error
    prefix = "" if names_a_node(message, node) else describe(graph, node) + ": "
    error.args = (prefix + locate(graph, message),)
    error.located = True  # type: ignore[attr-defined]
    return error
