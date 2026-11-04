"""The N-Triples / N-Quads ``VERSION`` directive (RDF 1.2 N-Triples sec. 2.2, grammar rules 1-5).

Oxigraph's N-Triples and N-Quads parsers reject ``VERSION "1.2"`` (its Turtle and TriG parsers accept it), so the wrapper
validates the directive itself and hands Oxigraph the text with each directive line emptied. Line numbers are kept, so a
``SyntaxError`` from Oxigraph still names the line of the original document.

The grammar: ``statement ::= directive | triple``, one statement per line, ``versionDirective ::= 'VERSION' versionSpecifier``
with ``'VERSION'`` case-sensitive and ``versionSpecifier ::= STRING_LITERAL_QUOTE`` (a double-quoted string; a number, an IRI,
a single-quoted string are not). Horizontal white space (space, tab) may surround the tokens and a ``#`` comment may follow. A
line whose first token is ``VERSION`` is a directive and is checked here (so ``VERSION 1.2`` fails for what it is). Anything else
is left to Oxigraph, which rejects ``version "1.2"`` (wrong case) and Turtle's ``@version "1.2" .`` as the statements they are not.
The version string is a hint (the spec requires no behaviour from it), so any string is accepted.
"""

from __future__ import annotations

import io
import os
import re
from typing import Any

import pyoxigraph as ox

_LINE_END = re.compile(rb"\r\n|\r|\n")
_CANDIDATE = re.compile(rb"[ \t]*VERSION")
_DIRECTIVE = re.compile(
    rb"""[ \t]*VERSION[ \t]*"(?:[^"\\\r\n]|\\[tbnrf\\"']|\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8})*"[ \t]*(?:\#[^\r\n]*)?"""
)
_CHUNK = 1 << 20


def _filter_lines(block: bytes, first_line: int) -> bytes:
    """``block`` (whole lines) with every valid directive line emptied; an invalid one raises ``SyntaxError``."""
    out, line_no = [], first_line
    pos = 0
    for m in _LINE_END.finditer(block):
        out.append(_filter_line(block[pos:m.start()], line_no))
        out.append(m.group())
        pos, line_no = m.end(), line_no + 1
    if pos < len(block):
        out.append(_filter_line(block[pos:], line_no))
    return b"".join(out)


def _filter_line(line: bytes, line_no: int) -> bytes:
    if not _CANDIDATE.match(line):
        return line
    if _DIRECTIVE.fullmatch(line):
        return b""
    col = len(line) - len(line.lstrip(b" \t")) + 1
    # the message and the (filename, line, column, text, end line, end column) position follow pyoxigraph's own SyntaxError
    raise SyntaxError(
        f"Parser error at line {line_no} column {col}: a VERSION directive is 'VERSION' followed by a double-quoted "
        f"string, like VERSION \"1.2\" (got {line.decode('utf-8', 'replace').strip()!r})",
        (None, line_no, col, None, line_no, len(line) + 1),
    )


class _DirectiveFilter(io.RawIOBase):
    """A readable byte stream over ``source`` (anything with ``read``, bytes or text) with the directive lines emptied.
    It works a chunk at a time, passing a chunk through untouched when ``VERSION`` does not occur in it."""

    def __init__(self, source: Any, close: bool = False) -> None:
        super().__init__()
        self._source, self._close_source = source, close
        self._pending = b""  # an unfinished last line
        self._ready = b""
        self._line = 1
        self._eof = False

    def readable(self) -> bool:
        return True

    def _fill(self) -> None:
        raw = self._source.read(_CHUNK)
        if isinstance(raw, str):
            raw = raw.encode("utf-8")
        if not raw:
            self._eof = True
            block, self._pending = self._pending, b""
        else:
            data = self._pending + raw
            cut = max(data.rfind(b"\n"), data.rfind(b"\r")) + 1  # a CR LF pair split here is read as two line ends: harmless
            if data.endswith(b"\r"):  # the LF may be next: keep the CR for the next round
                cut = data.rfind(b"\n") + 1 if data.rfind(b"\n") >= 0 else 0
            block, self._pending = data[:cut], data[cut:]
        if b"VERSION" in block:
            block = _filter_lines(block, self._line)
            self._line += len(_LINE_END.findall(block))
        else:
            self._line += len(_LINE_END.findall(block))
        self._ready += block

    def readall(self) -> bytes:
        parts = []
        while True:
            chunk = self.read(_CHUNK)
            if not chunk:
                return b"".join(parts)
            parts.append(chunk)

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        if size is None or size < 0:
            return self.readall()
        while len(self._ready) < size and not self._eof:
            self._fill()
        out, self._ready = self._ready[:size], self._ready[size:]
        return out

    def readinto(self, buffer: Any) -> int:
        data = self.read(len(buffer))
        buffer[:len(data)] = data
        return len(data)

    def close(self) -> None:
        if self._close_source and hasattr(self._source, "close"):
            self._source.close()
        super().close()


def accept_version_directive(kw: dict[str, Any], fmt: ox.RdfFormat) -> dict[str, Any]:
    """The ``ox.parse`` input keyword (``input=`` or ``path=``) for ``fmt``: unchanged for every format but N-Triples and
    N-Quads, else the same input read through the directive filter."""
    if fmt not in (ox.RdfFormat.N_TRIPLES, ox.RdfFormat.N_QUADS):
        return kw
    if "path" in kw:
        return {"input": _DirectiveFilter(open(os.fspath(kw["path"]), "rb"), close=True)}  # noqa: SIM115
    src = kw["input"]
    if isinstance(src, (bytes, bytearray, str)):
        data = src.encode("utf-8") if isinstance(src, str) else bytes(src)
        if b"VERSION" not in data:
            return kw
        return {"input": _filter_lines(data, 1)}
    return {"input": _DirectiveFilter(src)}
