"""The term classes StarLayer's own SPARQL parser (``parse_sparql``) builds its syntax tree from.

rdflib is an optional extra, but the parser sits on the core path: SHACL's ``sh:sparql`` checks and the query rewrites read the
parse tree. So the parser asks this module for ``URIRef``, ``BNode``, ``Literal``, ``Variable`` and the ``RDF`` / ``XSD``
namespaces. With rdflib installed they are rdflib's own classes (what the tree encoder, ``sqe`` and the tests expect). Without it
they are the small stand-ins below, which provide only what the parser uses: construction (``Literal`` with ``lang``,
``datatype`` and ``normalize``), ``str``, equality, hashing, ``n3()``, ``.language`` and ``.datatype``. The encoder that writes
the tree into an rdflib graph raises the clear ``ImportError`` instead of using them.

When the parser moves to pyoxigraph terms, delete this module.
"""

from __future__ import annotations

import itertools
from typing import Any

try:
    from rdflib import BNode, Literal, URIRef, Variable
    from rdflib.namespace import RDF, XSD

    HAVE_RDFLIB = True
except ImportError:  # rdflib is not installed: the stand-ins
    HAVE_RDFLIB = False

    def _escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")

    class URIRef(str):  # type: ignore[no-redef]
        __slots__ = ()

        def __repr__(self) -> str:
            return f"URIRef({str.__repr__(self)})"

        def __eq__(self, other: object) -> bool:
            return isinstance(other, URIRef) and str.__eq__(self, other)

        def __ne__(self, other: object) -> bool:
            return not self == other

        def __hash__(self) -> int:
            return hash(("URIRef", str(self)))

        def n3(self, namespace_manager: Any = None) -> str:
            return f"<{self}>"

    class Variable(str):  # type: ignore[no-redef]
        __slots__ = ()

        def __repr__(self) -> str:
            return f"Variable({str.__repr__(self)})"

        def __eq__(self, other: object) -> bool:
            return isinstance(other, Variable) and str.__eq__(self, other)

        def __ne__(self, other: object) -> bool:
            return not self == other

        def __hash__(self) -> int:
            return hash(("Variable", str(self)))

        def n3(self, namespace_manager: Any = None) -> str:
            return f"?{self}"

    _bnode_ids = itertools.count(1)

    class BNode(str):  # type: ignore[no-redef]
        __slots__ = ()

        def __new__(cls, value: str | None = None) -> BNode:
            return str.__new__(cls, value if value is not None else f"N{next(_bnode_ids):x}")

        def __repr__(self) -> str:
            return f"BNode({str.__repr__(self)})"

        def __eq__(self, other: object) -> bool:
            return isinstance(other, BNode) and str.__eq__(self, other)

        def __ne__(self, other: object) -> bool:
            return not self == other

        def __hash__(self) -> int:
            return hash(("BNode", str(self)))

        def n3(self, namespace_manager: Any = None) -> str:
            return f"_:{self}"

    class Literal(str):  # type: ignore[no-redef]
        """A lexical form with an optional language tag or datatype; ``normalize`` is accepted and ignored (the lexical form is kept)."""

        __slots__ = ("language", "datatype")

        def __new__(cls, lexical: Any, lang: str | None = None, datatype: Any = None, normalize: bool | None = None) -> Literal:
            if lang is not None and datatype is not None:
                raise TypeError("a literal has a language or a datatype, not both")
            if isinstance(lexical, bool):
                lexical = "true" if lexical else "false"
                datatype = datatype or XSD.boolean
            obj = str.__new__(cls, str(lexical))
            obj.language = lang.lower() if lang else None
            obj.datatype = URIRef(datatype) if datatype is not None else None
            return obj

        def __repr__(self) -> str:
            extra = f", lang={self.language!r}" if self.language else (f", datatype={self.datatype!r}" if self.datatype else "")
            return f"Literal({str.__repr__(self)}{extra})"

        def __eq__(self, other: object) -> bool:
            return (
                isinstance(other, Literal)
                and str.__eq__(self, other)
                and self.language == other.language
                and self.datatype == other.datatype
            )

        def __ne__(self, other: object) -> bool:
            return not self == other

        def __hash__(self) -> int:
            return hash(("Literal", str(self), self.language, self.datatype))

        def n3(self, namespace_manager: Any = None) -> str:
            text = f'"{_escape(str(self))}"'
            if self.language:
                return f"{text}@{self.language}"
            if self.datatype is not None:
                return f"{text}^^<{self.datatype}>"
            return text

    class _Namespace(str):
        __slots__ = ()

        def __getattr__(self, name: str) -> URIRef:
            if name.startswith("__"):
                raise AttributeError(name)
            return URIRef(str(self) + name)

        def __getitem__(self, name: str) -> URIRef:  # type: ignore[override]
            return URIRef(str(self) + name)

    RDF = _Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")  # type: ignore[assignment]
    XSD = _Namespace("http://www.w3.org/2001/XMLSchema#")  # type: ignore[assignment]

# The datatype IRI that carries a base-direction string (``"x"@en--ltr``) inside a ``Literal``; the same IRIs as
# ``starlayer.sparql.vocab.encode_dirlang_datatype`` (a test checks they agree).
_DIRLANG_NS = "https://github.com/hidden-graph/starlayer/ns/sparql/expr#dirlang/"


def encode_dirlang_datatype(language: str, direction: str) -> URIRef:
    return URIRef(f"{_DIRLANG_NS}{language}--{direction}")


__all__ = ["BNode", "HAVE_RDFLIB", "Literal", "RDF", "URIRef", "Variable", "XSD", "encode_dirlang_datatype"]
