"""``Result``: a small wrapper over a pyoxigraph query result that behaves like rdflib's for the common uses.

SELECT: iterate rows (``Row``, a tuple that is also readable by variable name), ``.vars`` (list of ``pyoxigraph.Variable``),
``.bindings`` (list of ``{name: term}`` dicts, unbound variables absent). ASK: ``.askAnswer`` and ``bool(result)``.
CONSTRUCT / DESCRIBE: iterate ``(s, p, o)`` tuples, ``.graph`` (an ``StarLayerGraph`` over a fresh store).

``serialize(destination=None, format=None)`` writes the result as SPARQL Results JSON, XML, CSV or TSV (SELECT, ASK) or as an RDF
syntax (CONSTRUCT, DESCRIBE), after or before the rows are read.

``.raw`` is the underlying pyoxigraph object (``QuerySolutions`` / ``QueryBoolean`` / ``QueryTriples``). It is a one-shot
stream: the wrapper reads it on first use of ``rows`` / ``bindings`` / iteration / ``.graph`` / ``serialize``, so use ``.raw``
directly *instead of*, not after, those (for a very large SELECT written straight to a file, ``raw.serialize`` streams where
``Result.serialize`` holds the rows first).
"""

from __future__ import annotations

import io
import json
import os
import re
from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox


class Row(tuple):
    """One solution: a tuple of terms in ``vars`` order (``None`` for an unbound variable) that can also be read by name:
    ``row["x"]``, ``row[Variable("x")]``, ``row.x``, ``row.get("x")``, ``row.asdict()``."""

    _names: tuple[str, ...]

    def __new__(cls, values: Any, names: tuple[str, ...]) -> Row:
        """Build a row from values in ``names`` order."""
        obj = super().__new__(cls, values)
        obj._names = names
        return obj

    def __getitem__(self, key: Any) -> Any:
        """Index by position, or by variable name (a ``Variable``, or a string with or without its leading ``?`` / ``$``)."""
        if isinstance(key, ox.Variable):
            key = key.value
        if isinstance(key, str):
            try:
                return tuple.__getitem__(self, self._names.index(key.lstrip("?$")))
            except ValueError:
                raise KeyError(key) from None
        return tuple.__getitem__(self, key)

    def __getattr__(self, name: str) -> Any:
        """Read a variable as an attribute.

        Names starting with ``_`` are never looked up as variables, so internals and protocol probes fail normally.
        """
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def get(self, key: Any, default: Any = None) -> Any:
        """Value of a variable, or ``default`` when the name is unknown or the variable is unbound."""
        try:
            v = self[key]
        except KeyError:
            return default
        return default if v is None else v

    def asdict(self) -> dict[str, Any]:
        """Map variable name to term, leaving unbound variables out."""
        return {n: v for n, v in zip(self._names, self, strict=True) if v is not None}


class HiddenColumns:
    """A one-shot SELECT result with some columns left out (variables that were added to the projection only so that a
    pre-binding could be applied; see ``run._query_widening``)."""

    def __init__(self, raw: Any, hide: set[str]) -> None:
        """Wrap ``raw`` so that ``variables`` omits the names in ``hide`` while iteration still yields the full solutions."""
        self._raw = raw
        self.variables = [v for v in raw.variables if v.value not in hide]

    def __iter__(self) -> Iterator[Any]:
        """Iterate the underlying solutions unchanged, hidden columns included."""
        return iter(self._raw)


_XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"


def _json_term(term: Any) -> dict[str, Any]:
    """A term as an entry of SPARQL 1.1 / 1.2 Query Results JSON (``uri``, ``bnode``, ``literal`` with ``xml:lang`` and
    ``its:dir``, ``triple``), the form ``pyoxigraph.parse_query_results`` reads."""
    if isinstance(term, ox.NamedNode):
        return {"type": "uri", "value": term.value}
    if isinstance(term, ox.BlankNode):
        return {"type": "bnode", "value": term.value}
    if isinstance(term, ox.Triple):
        return {"type": "triple", "value": {"subject": _json_term(term.subject), "predicate": _json_term(term.predicate), "object": _json_term(term.object)}}
    entry: dict[str, Any] = {"type": "literal", "value": term.value}
    if term.language:
        entry["xml:lang"] = term.language
        if term.direction is not None:
            entry["its:dir"] = "rtl" if term.direction == ox.BaseDirection.RTL else "ltr"
    elif term.datatype.value != _XSD_STRING:
        entry["datatype"] = term.datatype.value
    return entry


_RESULT_FORMATS = {"json": ox.QueryResultsFormat.JSON, "xml": ox.QueryResultsFormat.XML, "csv": ox.QueryResultsFormat.CSV, "tsv": ox.QueryResultsFormat.TSV}


def results_format(format: Any = None) -> ox.QueryResultsFormat:  # noqa: A002
    """A ``pyoxigraph.QueryResultsFormat`` from itself, a name (``"json"``, ``"xml"``, ``"csv"``, ``"tsv"``), a media type
    (``"application/sparql-results+json"``) or a file extension; JSON when ``format`` is ``None``."""
    if format is None:
        return ox.QueryResultsFormat.JSON
    if isinstance(format, ox.QueryResultsFormat):
        return format
    text = str(format).strip().lower().lstrip(".")
    if text in _RESULT_FORMATS:
        return _RESULT_FORMATS[text]
    for lookup in (ox.QueryResultsFormat.from_media_type, ox.QueryResultsFormat.from_extension):
        found = lookup(text)
        if found is not None:
            return found
    raise ValueError(f"unknown query results format {format!r}; use one of {sorted(_RESULT_FORMATS)} or a media type")


_KEYWORD = re.compile(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", re.I)
# One prologue declaration, after IRIs and strings were blanked to ``<>`` / ``""`` (a prefix may be *named* ``describe``)
_PROLOGUE = re.compile(r"\s*(?:BASE\s*<>|PREFIX\s+[^\s:<>]*:\s*<>|VERSION\s*\"\")", re.I)


def _query_type(text: str, raw: Any) -> str:
    if isinstance(raw, ox.QueryBoolean):
        return "ASK"
    if isinstance(raw, (ox.QuerySolutions, HiddenColumns)):
        return "SELECT"
    # blank comments, then IRIs and strings (so a keyword inside one does not count), then skip the prologue: the query form is
    # the first keyword after it
    # one left-to-right pass, so a ``#`` inside an IRI or string is not a comment and a quote inside a comment is not a string
    def blank(m: re.Match[str]) -> str:
        return "<>" if m.group(1) else '""' if m.group(2) else " "

    stripped = re.sub(r"(<[^<>\s]*>)|(\"(?:[^\"\\\n]|\\.)*\"|'(?:[^'\\\n]|\\.)*')|(#[^\n]*)", blank, text)
    pos = 0
    while (m := _PROLOGUE.match(stripped, pos)) is not None:
        pos = m.end()
    m = _KEYWORD.search(stripped, pos)
    return "DESCRIBE" if m and m.group(1).upper() == "DESCRIBE" else "CONSTRUCT"


class Result:
    """A pyoxigraph query result read like an rdflib one: rows, bindings, triples or a boolean, by query form."""
    def __init__(self, raw: Any, text: str = "") -> None:
        """Wrap ``raw`` and classify the query form.

        Args:
            text: the query text; needed only to tell CONSTRUCT from DESCRIBE, which the raw triple stream does not say.
        """
        self.raw = raw
        self.type = _query_type(text, raw)
        self._rows: list[Row] | None = None
        self._triples: list[tuple[Any, Any, Any]] | None = None
        self._graph: Any = None
        self.askAnswer: bool | None = bool(raw) if self.type == "ASK" else None
        self.vars: list[ox.Variable] | None = list(raw.variables) if self.type == "SELECT" else None

    # ---- SELECT -------------------------------------------------------------------------------------------------
    def _read_rows(self) -> list[Row]:
        if self._rows is None:
            if self.type != "SELECT":
                raise ValueError(f"a {self.type} result has no rows")
            names = tuple(v.value for v in self.vars)
            self._rows = [Row((sol[v] for v in self.vars), names) for sol in self.raw]
        return self._rows

    @property
    def rows(self) -> list[Row]:
        """The SELECT solutions, read from the one-shot stream once; other query forms raise ``ValueError`` (the result is not in a state the read can use)."""
        return self._read_rows()

    @property
    def bindings(self) -> list[dict[str, Any]]:
        """The SELECT solutions as ``{name: term}`` dicts, with unbound variables absent."""
        return [r.asdict() for r in self._read_rows()]

    # ---- CONSTRUCT / DESCRIBE -----------------------------------------------------------------------------------
    @property
    def triples(self) -> list[tuple[Any, Any, Any]]:
        """The CONSTRUCT or DESCRIBE triples, read from the one-shot stream once; other forms raise ``ValueError`` (the result is not in a state the read can use)."""
        if self._triples is None:
            if self.type not in ("CONSTRUCT", "DESCRIBE"):
                raise ValueError(f"a {self.type} result has no triples")
            self._triples = [(t.subject, t.predicate, t.object) for t in self.raw]
        return self._triples

    @property
    def graph(self) -> Any:
        """The CONSTRUCT or DESCRIBE triples as a new in-memory ``StarLayerGraph``, built once."""
        if self._graph is None:
            from starlayer.graph.core import StarLayerGraph

            g = StarLayerGraph()
            g.extend(self.triples)
            self._graph = g
        return self._graph

    # ---- writing ------------------------------------------------------------------------------------------------
    def serialize(self, destination: Any = None, format: Any = None, **options: Any) -> str | None:  # noqa: A002
        """Write the result in ``format``.

        SELECT and ASK: SPARQL Query Results ``"json"`` (default), ``"xml"``, ``"csv"`` or ``"tsv"`` (a name, a media type such as
        ``"text/csv"``, a file extension or a ``pyoxigraph.QueryResultsFormat``); Oxigraph writes them. CONSTRUCT and DESCRIBE:
        any RDF format of ``StarLayerGraph.serialize`` (Turtle by default), and ``options`` are its options (``prefixes=``, ...).

        ``destination`` is a file path, a file object, or ``None``, which returns the text. A SELECT is read from the one-shot
        stream first (the same rows as ``rows``), so this works before or after reading them."""
        if self.type in ("CONSTRUCT", "DESCRIBE"):
            return self.graph.serialize(destination, format=format or "turtle", **options)
        if options:
            raise TypeError(f"a {self.type} result takes no serialize options besides format, got {sorted(options)}")
        fmt = results_format(format)
        if self.type == "ASK":
            document = {"head": {}, "boolean": bool(self.askAnswer)}
        else:
            names = [v.value for v in self.vars]
            document = {
                "head": {"vars": names},
                "results": {"bindings": [{n: _json_term(v) for n, v in zip(names, row, strict=True) if v is not None} for row in self._read_rows()]},
            }
        data = json.dumps(document, ensure_ascii=False).encode("utf-8")
        if fmt != ox.QueryResultsFormat.JSON:
            data = ox.parse_query_results(data, format=ox.QueryResultsFormat.JSON).serialize(format=fmt)
        if destination is None:
            return data.decode("utf-8")
        if isinstance(destination, (str, os.PathLike)):
            with open(destination, "wb") as handle:
                handle.write(data)
        elif isinstance(destination, io.TextIOBase):
            destination.write(data.decode("utf-8"))
        else:
            destination.write(data)
        return None

    # ---- protocol -----------------------------------------------------------------------------------------------
    def __iter__(self) -> Iterator[Any]:
        """Iterate rows for SELECT, the single answer for ASK, or ``(s, p, o)`` tuples."""
        if self.type == "SELECT":
            return iter(self._read_rows())
        if self.type == "ASK":
            return iter([self.askAnswer])
        return iter(self.triples)

    def __len__(self) -> int:
        """Number of items ``iter`` yields (1 for ASK); this reads the stream."""
        if self.type == "SELECT":
            return len(self._read_rows())
        if self.type == "ASK":
            return 1
        return len(self.triples)

    def __bool__(self) -> bool:
        """The answer for ASK; otherwise whether there is at least one row or triple."""
        if self.type == "ASK":
            return bool(self.askAnswer)
        return len(self) > 0

    def __repr__(self) -> str:
        """Show only the query form, so printing never consumes the stream."""
        return f"<Result {self.type}>"
