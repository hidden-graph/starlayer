"""The pyoxigraph terms StarLayer's own SPARQL parser (``parse_sparql``) and the ``sqe:`` tree are built from.

A query may hold what an RDF graph cannot: a relative IRI (``<s>`` with no ``BASE``), a blank node label or language tag
pyoxigraph rejects. ``sqe:`` trees keep such text as the opaque, reversible stand-ins the SHACL engine uses under
``term_policy("lenient")`` (``urn:starlayer:invalid-iri:<percent-encoded text>`` and so on, see
``shacl_engine.terms.TermError``), so the tree is a valid ``StarLayerGraph`` and the text comes back unchanged. The
functions here make the stand-in and take it apart again; nothing else in the sparql package needs to know the format.
"""

from __future__ import annotations

from urllib.parse import quote, unquote

import pyoxigraph as ox

from starlayer.shacl_engine.terms import (
    _INVALID_BNODE_PREFIX,
    _INVALID_IRI_PREFIX,
    _INVALID_LANG_PREFIX,
    NS,
    RDF,
    XSD,
)

__all__ = [
    "NS",
    "RDF",
    "XSD",
    "bnode",
    "bnode_label",
    "boolean",
    "directional",
    "iri",
    "iri_text",
    "language_of",
    "language_literal",
    "plain_literal",
    "typed_literal",
]

_DIRECTION = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}


def iri(text: str) -> ox.NamedNode:
    """The IRI ``text``; a text that is not an absolute IRI (a relative one, one with a space) becomes its stand-in."""
    try:
        return ox.NamedNode(text)
    except ValueError:
        return ox.NamedNode(_INVALID_IRI_PREFIX + quote(text, safe=""))


def iri_text(node: ox.NamedNode) -> str:
    """The text an IRI term was written with (the stand-in taken apart)."""
    value = node.value
    if value.startswith(_INVALID_IRI_PREFIX):
        return unquote(value[len(_INVALID_IRI_PREFIX):])
    return value


def bnode(label: str | None = None) -> ox.BlankNode:
    """A blank node with the given label (a fresh one for ``None``); a label pyoxigraph rejects becomes its stand-in."""
    if label is None:
        return ox.BlankNode()
    try:
        return ox.BlankNode(label)
    except ValueError:
        return ox.BlankNode(_INVALID_BNODE_PREFIX + label.encode("utf-8", "surrogatepass").hex())


def bnode_label(node: ox.BlankNode) -> str:
    value = node.value
    if value.startswith(_INVALID_BNODE_PREFIX):
        return bytes.fromhex(value[len(_INVALID_BNODE_PREFIX):]).decode("utf-8", "surrogatepass")
    return value


def plain_literal(lexical: str) -> ox.Literal:
    return ox.Literal(lexical)


def typed_literal(lexical: str, datatype: ox.NamedNode) -> ox.Literal:
    return ox.Literal(lexical, datatype=datatype)


def language_literal(lexical: str, tag: str) -> ox.Literal:
    """``"lexical"@tag``; a tag that is not BCP47 becomes a literal whose datatype is the language stand-in."""
    try:
        return ox.Literal(lexical, language=tag)
    except ValueError:
        return ox.Literal(lexical, datatype=ox.NamedNode(_INVALID_LANG_PREFIX + quote(tag, safe="")))


def directional(lexical: str, tag: str, direction: str) -> ox.Literal:
    """``"lexical"@tag--direction`` (``direction`` is ``ltr`` or ``rtl``)."""
    try:
        return ox.Literal(lexical, language=tag, direction=_DIRECTION[direction])
    except ValueError:
        return ox.Literal(lexical, datatype=ox.NamedNode(_INVALID_LANG_PREFIX + quote(f"{tag}--{direction}", safe="")))


def language_of(literal: ox.Literal) -> str | None:
    """The language tag a literal was written with (``tag`` or ``tag--dir``), the stand-in for a bad tag taken apart."""
    if literal.language is not None:
        return literal.language + (("--ltr" if literal.direction == ox.BaseDirection.LTR else "--rtl") if literal.direction is not None else "")
    datatype = literal.datatype.value
    if datatype.startswith(_INVALID_LANG_PREFIX):
        return unquote(datatype[len(_INVALID_LANG_PREFIX):])
    return None


def boolean(value: bool = True) -> ox.Literal:
    return ox.Literal("true" if value else "false", datatype=XSD.boolean)
