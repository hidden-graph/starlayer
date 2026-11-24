"""Notice when the store rewrites a literal as it is loaded (StarLayer issue #190).

Oxigraph stores some literals in a canonical form, so ``"04"^^xsd:integer`` is read back as ``"4"`` and ``"1"^^xsd:boolean`` as
``"true"``. The parser still returns the literal as it was written, so a load can compare it with what the store will keep and
say which literals changed. ``watch`` wraps the terms being added; ``Rewrites.emit`` warns once for the whole load and counts what
changed on the store (``StoreVersion.rewritten``), which is what ``shacl.engine.fidelity`` reads at validation time.

Only a literal in the object position is checked. A write that does not pass through the wrapper (a SPARQL UPDATE, a raw
``pyoxigraph.Store``, a database opened from disk) is not seen.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from typing import Any

import pyoxigraph as ox

from starlayer._callsite import warn_at_caller

_XSD = "http://www.w3.org/2001/XMLSchema#"

#: The datatypes whose lexical form Oxigraph rewrites (integer family, decimal, float, double, boolean, date/time, g* and duration types;
#: xsd:dateTimeStamp is even stored as xsd:dateTime).
AFFECTED_DATATYPES: frozenset[str] = frozenset(
    _XSD + n
    for n in (
        "integer", "int", "long", "short", "byte", "nonNegativeInteger", "positiveInteger", "nonPositiveInteger",
        "negativeInteger", "unsignedLong", "unsignedInt", "unsignedShort", "unsignedByte", "decimal", "float", "double",
        "boolean", "dateTime", "dateTimeStamp", "date", "time", "gYear", "gYearMonth", "gMonth", "gMonthDay", "gDay",
        "duration", "dayTimeDuration", "yearMonthDuration",
    )
)

_INTEGER = _XSD + "integer"
_BOOLEAN = _XSD + "boolean"
_DECIMAL = _XSD + "decimal"
_CANONICAL_INTEGER = re.compile(r"0|-?[1-9][0-9]*")
_CANONICAL_DECIMAL = re.compile(r"(0|-?[1-9][0-9]*|-0(?=\.[0-9]*[1-9]))(\.[0-9]*[1-9])?")

MESSAGE = (
    "{count} literal{s} stored in a different form than written, because Oxigraph keeps some literals in a canonical form: "
    "{examples}. A constraint that reads a literal's lexical form or exact datatype (sh:pattern, sh:minLength, sh:maxLength, "
    "sh:in, sh:hasValue, sh:equals, sh:datatype of a numeric or boolean type) sees the stored form. See StarLayer issue #190."
)

_stored: dict[Any, ox.Literal] = {}  # the form the store keeps, by literal (a literal that is repeated is looked up once)
_SUBJECT, _PREDICATE = ox.NamedNode("urn:starlayer:lexical:s"), ox.NamedNode("urn:starlayer:lexical:p")


def stored_form(literal: ox.Literal) -> ox.Literal:
    """The literal as the store will keep it (``literal`` itself when the store keeps it as written)."""
    datatype = literal.datatype.value
    if datatype not in AFFECTED_DATATYPES:
        return literal
    if datatype == _INTEGER and _CANONICAL_INTEGER.fullmatch(literal.value):
        return literal
    if datatype == _BOOLEAN and literal.value in ("true", "false"):
        return literal
    if datatype == _DECIMAL and _CANONICAL_DECIMAL.fullmatch(literal.value):
        return literal
    kept = _stored.get(literal)
    if kept is None:
        scratch = ox.Store()
        scratch.add(ox.Quad(_SUBJECT, _PREDICATE, literal, ox.DefaultGraph()))
        kept = next(iter(scratch)).object
        if len(_stored) < 10_000:
            _stored[literal] = kept
    return kept


def _show(literal: ox.Literal) -> str:
    datatype = literal.datatype.value
    text = '"' + literal.value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f"{text}^^xsd:{datatype[len(_XSD):]}" if datatype.startswith(_XSD) else f"{text}^^<{datatype}>"


class Rewrites:
    """The literals one load found stored in a different form than written."""

    __slots__ = ("count", "examples")

    def __init__(self) -> None:
        self.count = 0
        self.examples: list[str] = []

    def see(self, literal: ox.Literal) -> None:
        kept = stored_form(literal)
        if kept != literal:
            self.count += 1
            if len(self.examples) < 3:
                self.examples.append(f"{_show(literal)} as " + (_show(kept) if kept.datatype != literal.datatype else f'"{kept.value}"'))

    def emit(self, store: ox.Store) -> None:
        """Warn once for the load and count the literals on ``store``."""
        if not self.count:
            return
        from starlayer.graph.execution import union
        from starlayer.shacl.engine.terms import StarLayerFidelityWarning

        union.version_of(store).rewritten += self.count
        more = self.count - len(self.examples)
        examples = "; ".join(self.examples) + (f"; and {more} more" if more else "")
        warn_at_caller(MESSAGE.format(count=self.count, s=" was" if self.count == 1 else "s were", examples=examples), StarLayerFidelityWarning)


def watch(quads: Iterable[Any], rewrites: Rewrites) -> Iterator[Any]:
    """``quads`` unchanged, noting each object literal the store will keep in another form."""
    for quad in quads:
        obj = quad.object
        if isinstance(obj, ox.Literal) and obj.datatype.value in AFFECTED_DATATYPES:
            rewrites.see(obj)
        yield quad


def rewritten_count(store: ox.Store) -> int:
    """How many literals loaded through the wrapper were stored in a different form (see the module doc for what is not seen)."""
    from starlayer.graph.execution import union

    return union.version_of(store).rewritten


def report(quads: Iterable[Any], store: ox.Store) -> None:
    """Read ``quads`` (a second read of what was loaded into ``store``) and warn about the literals the store kept in another form."""
    rewrites = Rewrites()
    for _ in watch(quads, rewrites):
        pass
    rewrites.emit(store)
