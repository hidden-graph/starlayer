"""``Result``: a small wrapper over a pyoxigraph query result that behaves like rdflib's for the common uses.

SELECT: iterate rows (``Row``, a tuple that is also readable by variable name), ``.vars`` (list of ``pyoxigraph.Variable``),
``.bindings`` (list of ``{name: term}`` dicts, unbound variables absent). ASK: ``.askAnswer`` and ``bool(result)``.
CONSTRUCT / DESCRIBE: iterate ``(s, p, o)`` tuples, ``.graph`` (an ``OxGraph`` over a fresh store).

``.raw`` is the underlying pyoxigraph object (``QuerySolutions`` / ``QueryBoolean`` / ``QueryTriples``). It is a one-shot
stream: the wrapper reads it on first use of ``rows`` / ``bindings`` / iteration / ``.graph``, so use ``.raw`` directly (for
``serialize`` to JSON, CSV, TSV, XML) *instead of*, not after, those.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

import pyoxigraph as ox


class Row(tuple):
    """One solution: a tuple of terms in ``vars`` order (``None`` for an unbound variable) that can also be read by name:
    ``row["x"]``, ``row[Variable("x")]``, ``row.x``, ``row.get("x")``, ``row.asdict()``."""

    _names: tuple[str, ...]

    def __new__(cls, values: Any, names: tuple[str, ...]) -> Row:
        obj = super().__new__(cls, values)
        obj._names = names
        return obj

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, ox.Variable):
            key = key.value
        if isinstance(key, str):
            try:
                return tuple.__getitem__(self, self._names.index(key.lstrip("?$")))
            except ValueError:
                raise KeyError(key) from None
        return tuple.__getitem__(self, key)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None

    def get(self, key: Any, default: Any = None) -> Any:
        try:
            v = self[key]
        except KeyError:
            return default
        return default if v is None else v

    def asdict(self) -> dict[str, Any]:
        return {n: v for n, v in zip(self._names, self, strict=True) if v is not None}


_KEYWORD = re.compile(r"\b(SELECT|ASK|CONSTRUCT|DESCRIBE)\b", re.I)


def _query_type(text: str, raw: Any) -> str:
    if isinstance(raw, ox.QueryBoolean):
        return "ASK"
    if isinstance(raw, ox.QuerySolutions):
        return "SELECT"
    stripped = re.sub(r"(?m)#[^\n]*$|<[^<>\s]*>|\"(?:[^\"\\\n]|\\.)*\"", " ", text)
    m = _KEYWORD.search(stripped)
    return m.group(1).upper() if m and m.group(1).upper() == "DESCRIBE" else "CONSTRUCT"


class Result:
    def __init__(self, raw: Any, text: str = "") -> None:
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
                raise TypeError(f"a {self.type} result has no rows")
            names = tuple(v.value for v in self.vars)
            self._rows = [Row((sol[v] for v in self.vars), names) for sol in self.raw]
        return self._rows

    @property
    def rows(self) -> list[Row]:
        return self._read_rows()

    @property
    def bindings(self) -> list[dict[str, Any]]:
        return [r.asdict() for r in self._read_rows()]

    # ---- CONSTRUCT / DESCRIBE -----------------------------------------------------------------------------------
    @property
    def triples(self) -> list[tuple[Any, Any, Any]]:
        if self._triples is None:
            if self.type not in ("CONSTRUCT", "DESCRIBE"):
                raise TypeError(f"a {self.type} result has no triples")
            self._triples = [(t.subject, t.predicate, t.object) for t in self.raw]
        return self._triples

    @property
    def graph(self) -> Any:
        if self._graph is None:
            from starlayer.graph.oxgraph.core import OxGraph

            g = OxGraph()
            g.extend(self.triples)
            self._graph = g
        return self._graph

    # ---- protocol -----------------------------------------------------------------------------------------------
    def __iter__(self) -> Iterator[Any]:
        if self.type == "SELECT":
            return iter(self._read_rows())
        if self.type == "ASK":
            return iter([self.askAnswer])
        return iter(self.triples)

    def __len__(self) -> int:
        if self.type == "SELECT":
            return len(self._read_rows())
        if self.type == "ASK":
            return 1
        return len(self.triples)

    def __bool__(self) -> bool:
        if self.type == "ASK":
            return bool(self.askAnswer)
        return len(self) > 0

    def __repr__(self) -> str:
        return f"<Result {self.type}>"
