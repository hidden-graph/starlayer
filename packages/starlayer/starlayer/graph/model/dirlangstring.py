"""
starlayer.graph.model.dirlangstring

Core RDF 1.2 type: DirLangString — a language-tagged string literal carrying
an explicit base text direction ('ltr' or 'rtl'), per rdf:dirLangString
(RDF 1.2 Concepts sec 3.4). Lexical form: "text"@lang--dir.

Encoding follows the same "invisible to public APIs" approach as TripleTerm:
rdflib.Literal(text, lang="en--rtl") raises (rdflib has no notion of the
--dir suffix), so a DirLangString is stored as a plain Literal whose datatype
URI packs (language, direction) - see encode_dirlang_datatype below.
The Oxigraph-backed graphs hold the real ``ox.Literal(..., language=, direction=)``;
the datatype form is for rdflib (``encode_dirlangstring``, the bridge).
"""

from starlayer.graph.interop import DIRLANG_NS

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

    def __reduce__(self):  # pickle / copy would restore the slots with setattr, which is refused
        return (DirLangString, (self.value, self.language, self.direction))

    def _key(self):
        return (self.value, self.language, self.direction)

    def __eq__(self, other):
        if isinstance(other, DirLangString):
            return self._key() == other._key()
        return NotImplemented

    def __hash__(self):
        return hash(self._key())

    def n3(self, namespace_manager=None) -> str:
        """Returns the N3/Turtle-1.2 (``"text"@lang--dir``) text form."""
        return f'{_quoted(self.value)}@{self.language}--{self.direction}'

    def __str__(self):
        return self.value

    def __repr__(self):
        return f'DirLangString({self.value!r}, {self.language!r}, {self.direction!r})'


def _quoted(text: str) -> str:
    """``text`` as a double-quoted N-Triples string (pyoxigraph writes it; no rdflib needed)."""
    import pyoxigraph as ox

    return str(ox.Literal(text))


def encode_dirlang_datatype(language: str, direction: str) -> str:
    """The datatype IRI (as text) that packs a directional language string's (language, direction): ``DIRLANG_NS`` +
    ``"<language>--<direction>"``. rdflib's ``Literal(lang="en--rtl")`` raises, so the rdflib side carries the pair in a datatype."""
    return f'{DIRLANG_NS}{language}--{direction}'


def decode_dirlang_datatype(datatype) -> tuple[str, str] | None:
    """``(language, direction)`` if ``datatype`` (an IRI term or text) is a dirlang datatype IRI, else None."""
    s = str(getattr(datatype, 'value', datatype))
    if not s.startswith(DIRLANG_NS):
        return None
    language, sep, direction = s[len(DIRLANG_NS):].rpartition('--')
    if not sep or not language or direction not in _VALID_DIRECTIONS:
        return None
    return language, direction


def encode_dirlangstring(dls: DirLangString):
    """The rdflib ``Literal`` that carries a DirLangString as a datatype IRI; needs rdflib."""
    from rdflib import Literal, URIRef

    return Literal(dls.value, datatype=URIRef(encode_dirlang_datatype(dls.language, dls.direction)))


def decode_dirlangstring(literal) -> DirLangString | None:
    """Return a DirLangString if literal is a starlayer.graph dirlang-encoded Literal, else None."""
    datatype = getattr(literal, 'datatype', None)
    if datatype is None:
        return None
    decoded = decode_dirlang_datatype(datatype)
    if decoded is None:
        return None
    language, direction = decoded
    import pyoxigraph as ox

    # an ``ox.Literal`` prints as N-Triples, so its lexical form is ``.value``; an rdflib Literal prints as its lexical form
    text = literal.value if isinstance(literal, ox.Literal) else str(literal)
    return DirLangString(text, language, direction)
