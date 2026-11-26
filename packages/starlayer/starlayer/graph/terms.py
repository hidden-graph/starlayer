"""Terms: coercion for the wrapper, and the helpers for making a term from a Python value (``literal``), reading a literal's Python value
(``to_python``) and reading a term from Turtle text (``parse_term``). Terms are pyoxigraph terms; an rdflib or StarLayer term is converted
(rdflib is imported lazily, only when such a term actually arrives)."""

from __future__ import annotations

import datetime as _dt
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

import pyoxigraph as ox

from starlayer.errors import FormatError

NamedNode, BlankNode, Literal, Triple, Variable = ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple, ox.Variable
DefaultGraph = ox.DefaultGraph

RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDF_TYPE = NamedNode(RDF + "type")
RDF_VALUE = NamedNode(RDF + "value")
RDF_FIRST = NamedNode(RDF + "first")
RDF_REST = NamedNode(RDF + "rest")
RDF_NIL = NamedNode(RDF + "nil")
RDF_REIFIES = NamedNode(RDF + "reifies")

_OX_TERMS = (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)


def term(x: Any) -> Any:
    """``x`` as a pyoxigraph term (``None`` stays ``None``; a 3-tuple becomes a ``Triple``)."""
    if x is None or isinstance(x, _OX_TERMS):
        return x
    if isinstance(x, tuple) and len(x) == 3:
        return Triple(term(x[0]), term(x[1]), term(x[2]))
    from starlayer.shacl.engine.terms import (
        to_engine,  # rdflib / StarLayer terms; imports rdflib lazily
    )

    return to_engine(x)


def to_iri(text: str, context: str | None = None) -> ox.NamedNode:
    """The ``NamedNode`` of IRI ``text``. Text that is not an absolute IRI is a ``FormatError`` of kind ``"rdf"`` (a term) (Oxigraph's
    ``ValueError`` for it is converted here, so a caller that takes IRI text from a person or a document catches one class)."""
    try:
        return NamedNode(text)
    except ValueError as error:
        raise FormatError(f"{text!r} is not a valid IRI: {error}", kind="rdf", why=str(error), context=context) from error


def graph_name(x: Any) -> Any:
    """A graph identifier as ``NamedNode`` / ``BlankNode`` / ``DefaultGraph``. A plain ``str`` is an IRI; one that is not a valid
    IRI is a ``FormatError`` (kind ``"rdf"``, context says it is a term)."""
    if x is None or isinstance(x, ox.DefaultGraph):
        return ox.DefaultGraph()
    if isinstance(x, str):
        return to_iri(x, "graph name")
    ident = getattr(x, "identifier", None)  # an StarLayerGraph
    if ident is not None:
        return ident
    return term(x)


def in_pattern(s: Any, p: Any, o: Any) -> tuple[Any, Any, Any] | None:
    """Pattern terms coerced; ``None`` when no RDF statement can match (a literal subject or a non-IRI predicate), because
    Oxigraph raises there while an RDF graph simply has no such statement."""
    try:
        s, p, o = term(s), term(p), term(o)
    except TypeError:
        if any(isinstance(x, tuple) and len(x) == 3 for x in (s, p, o)):  # a triple term that cannot exist (a literal subject ...): no statement holds it
            return None
        raise
    if isinstance(s, (ox.Literal, ox.Triple)) or (p is not None and not isinstance(p, ox.NamedNode)):
        return None
    return s, p, o


XSD = "http://www.w3.org/2001/XMLSchema#"
_INTEGER_TYPES = frozenset(
    XSD + n for n in ("integer", "int", "long", "short", "byte", "nonNegativeInteger", "positiveInteger", "nonPositiveInteger",
                      "negativeInteger", "unsignedInt", "unsignedLong", "unsignedShort", "unsignedByte")
)


_LANGUAGE_DATATYPES = frozenset({XSD + "string", "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString", "http://www.w3.org/1999/02/22-rdf-syntax-ns#dirLangString"})


def literal(value: Any, datatype: Any = None, *, lang: str | None = None, direction: str | None = None) -> ox.Literal:
    """A literal from a Python value, or from text with a ``datatype`` (a ``NamedNode`` or IRI text), a language ``lang`` and a base
    ``direction`` (``"ltr"`` or ``"rtl"``, with ``lang``).

    A ``bool`` is ``xsd:boolean``, an ``int`` ``xsd:integer``, a ``float`` ``xsd:double``, a ``Decimal`` ``xsd:decimal``, a ``datetime`` /
    ``date`` / ``time`` ``xsd:dateTime`` / ``xsd:date`` / ``xsd:time``, a ``str`` a plain string. A language-tagged literal has the datatype
    ``rdf:langString`` (``rdf:dirLangString`` with a ``direction``), so a ``datatype`` given with ``lang`` must be ``xsd:string`` or one of those;
    any other raises ``ValueError``, as the datatype cannot be kept (so does a ``direction`` other than ``"ltr"`` / ``"rtl"`` or one given
    without ``lang``: a wrong combination or choice of arguments). Text that is not a valid language tag or datatype IRI is a ``FormatError``
    (kind ``"rdf"``, context says it is a term). A Python value with a ``datatype`` is written as its own lexical form (``literal(5, XSD.long)``)."""
    if lang is not None:
        if datatype is not None and str(getattr(datatype, "value", datatype)) not in _LANGUAGE_DATATYPES:
            raise ValueError(f"a literal has a language tag or a datatype, not both: lang={lang!r} with datatype {datatype}")
        if direction is not None and direction not in ("ltr", "rtl"):
            raise ValueError(f"direction must be 'ltr' or 'rtl', not {direction!r}")
        try:
            return Literal(str(value), language=lang, **({"direction": ox.BaseDirection.LTR if direction == "ltr" else ox.BaseDirection.RTL} if direction else {}))
        except ValueError as error:
            raise FormatError(f"{lang!r} is not a valid language tag: {error}", kind="rdf", why=str(error), context="language tag") from error
    if direction is not None:
        raise ValueError("a base direction needs a language tag")
    iri = None if datatype is None else (datatype if isinstance(datatype, NamedNode) else to_iri(str(datatype), "datatype"))
    if isinstance(value, bool):
        text, default = ("true" if value else "false"), "boolean"
    elif isinstance(value, int):
        text, default = str(value), "integer"
    elif isinstance(value, float):
        text, default = repr(value) if value == value and abs(value) != float("inf") else ("NaN" if value != value else ("INF" if value > 0 else "-INF")), "double"
    elif isinstance(value, Decimal):
        text, default = format(value, "f"), "decimal"
    elif isinstance(value, _dt.datetime):
        text, default = value.isoformat(), "dateTime"
    elif isinstance(value, _dt.date):
        text, default = value.isoformat(), "date"
    elif isinstance(value, _dt.time):
        text, default = value.isoformat(), "time"
    else:
        text, default = str(value), None
    if iri is None and default is not None:
        iri = NamedNode(XSD + default)
    return Literal(text, datatype=iri) if iri is not None else Literal(text)


def _date_time(text: str) -> Any:
    return text[:-1] + "+00:00" if text.endswith("Z") else text


def to_python(term: Any) -> Any:
    """The Python value of a literal: ``bool`` for ``xsd:boolean``, ``int`` for the integer types, ``Decimal`` for ``xsd:decimal``,
    ``float`` for ``xsd:double`` and ``xsd:float``, ``datetime`` / ``date`` / ``time`` for ``xsd:dateTime`` / ``xsd:date`` /
    ``xsd:time``, and the lexical form for any other datatype, a plain string and a language string.

    ``TypeError`` for a term that is not a literal; a ``FormatError`` (kind ``"rdf"``, context says it is a term) for a lexical form that is not valid for its
    datatype (``"abc"^^xsd:integer``)."""
    if not isinstance(term, Literal):
        raise TypeError(f"only a literal has a Python value, not {type(term).__name__}")
    text, datatype = term.value, term.datatype.value
    if not datatype.startswith(XSD):
        return text
    kind = datatype[len(XSD):]
    try:
        if kind == "boolean":
            return {"true": True, "1": True, "false": False, "0": False}[text.strip()]
        if kind in {n[len(XSD):] for n in _INTEGER_TYPES}:
            return int(text)
        if kind == "decimal":
            return Decimal(text)
        if kind in ("double", "float"):
            return float(text)
        if kind == "dateTime":
            return _dt.datetime.fromisoformat(_date_time(text))
        if kind == "date":
            return _dt.date.fromisoformat(text[:10])
        if kind == "time":
            return _dt.time.fromisoformat(_date_time(text))
    except (KeyError, ValueError, InvalidOperation, ArithmeticError) as error:
        raise FormatError(f"{text!r} is not a valid {kind}", kind="rdf", context=f"xsd:{kind} literal") from error
    return text


_PREFIX_NAME = re.compile(r"[A-Za-z][\w.-]*|")


def term_kind(term: Any) -> str:
    """``"iri"``, ``"blank"``, ``"literal"`` or ``"triple"``: the kind of an RDF term. ``TypeError`` for anything else."""
    if isinstance(term, NamedNode):
        return "iri"
    if isinstance(term, BlankNode):
        return "blank"
    if isinstance(term, Literal):
        return "literal"
    if isinstance(term, Triple):
        return "triple"
    raise TypeError(f"not an RDF term: {term!r}")


def parse_term(text: str, prefixes: Mapping[str, str] | None = None) -> Any:
    """The term Turtle 1.2 text denotes: ``<http://e/x>``, ``"text"``, ``"text"@en``, ``"text"@ar--rtl``, ``"1"^^<...#integer>``, ``5``,
    ``true``, ``_:b0`` or a triple term ``<<( s p o )>>``. A prefixed name (``ex:alice``, ``xsd:integer`` inside a typed literal) is
    resolved with ``prefixes`` (prefix to namespace IRI) and is an error without one.

    A ``FormatError`` (kind ``"rdf"``, context says it is a term) for text that is not exactly one term; ``TypeError`` for a ``text`` that is not a ``str``."""
    if not isinstance(text, str):
        raise TypeError(f"parse_term() needs a str, not {type(text).__name__}")
    if not text.strip():
        raise FormatError(f"not a term: {text!r}", kind="rdf", why="empty text", context="term text")
    head = "".join(f"@prefix {p}: <{n}> .\n" for p, n in (prefixes or {}).items() if _PREFIX_NAME.fullmatch(p))
    document = f"{head}<urn:x-starlayer:s> <urn:x-starlayer:p> {text.strip()} ."
    try:
        quads = list(ox.parse(document, format=ox.RdfFormat.TURTLE, rename_blank_nodes=False))
    except (SyntaxError, ValueError) as error:
        raise FormatError(f"not a term: {text.strip()!r}", kind="rdf", why=str(error), context="term text") from error
    if len(quads) != 1:
        raise FormatError(f"not exactly one term: {text.strip()!r}", kind="rdf", context="term text")
    return quads[0].object
