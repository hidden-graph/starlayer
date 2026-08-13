"""
starlayergraph.model.dirlangstring

Core RDF 1.2 type: DirLangString — a language-tagged string literal carrying
an explicit base text direction ('ltr' or 'rtl'), per rdf:dirLangString
(RDF 1.2 Concepts sec 3.4). Lexical form: "text"@lang--dir.

Encoding follows the same "invisible to public APIs" approach as TripleTerm:
rdflib.Literal(text, lang="en--rtl") raises (rdflib has no notion of the
--dir suffix), so a DirLangString is stored as a plain Literal whose datatype
URI packs (language, direction) - see encode_dirlang_datatype in
starlayergraph.model.encoding. StarLayerGraph encodes/decodes at its read/write
boundary so callers only ever see DirLangString or plain rdflib terms.
"""

from rdflib import Literal

from starlayergraph.model.encoding import encode_dirlang_datatype, decode_dirlang_datatype

_VALID_DIRECTIONS = frozenset({'ltr', 'rtl'})


class DirLangString:
    """An RDF 1.2 directional language-tagged string literal.

    Value-typed: two instances with the same (value, language, direction) are
    equal and have the same hash. Per RDF 1.2 Concepts sec 3.4.1, a language
    tag's case does not participate in the abstract syntax - it is folded to
    lowercase here, mirroring rdflib.Literal's existing behaviour for lang=.
    """
    __slots__ = ('value', 'language', 'direction')

    def __init__(self, value: str, language: str, direction: str):
        if direction not in _VALID_DIRECTIONS:
            raise ValueError(f"direction must be 'ltr' or 'rtl', got {direction!r}")
        if not language:
            raise ValueError("DirLangString requires a non-empty language tag")
        object.__setattr__(self, 'value', str(value))
        object.__setattr__(self, 'language', language.lower())
        object.__setattr__(self, 'direction', direction)

    def __setattr__(self, name, value):
        raise AttributeError("DirLangString is immutable")

    def _key(self):
        return (self.value, self.language, self.direction)

    def __eq__(self, other):
        if isinstance(other, DirLangString):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self):
        return hash(self._key())

    def n3(self, namespace_manager=None) -> str:
        return f'{Literal(self.value).n3(namespace_manager)}@{self.language}--{self.direction}'

    def __str__(self):
        return self.value

    def __repr__(self):
        return f'DirLangString({self.value!r}, {self.language!r}, {self.direction!r})'


def encode_dirlangstring(dls: DirLangString) -> Literal:
    """Return the internal Literal encoding of a DirLangString."""
    return Literal(dls.value, datatype=encode_dirlang_datatype(dls.language, dls.direction))


def decode_dirlangstring(literal) -> DirLangString | None:
    """Return a DirLangString if literal is a starlayergraph dirlang-encoded Literal, else None."""
    datatype = getattr(literal, 'datatype', None)
    if datatype is None:
        return None
    decoded = decode_dirlang_datatype(datatype)
    if decoded is None:
        return None
    language, direction = decoded
    return DirLangString(str(literal), language, direction)
