"""The only graph surface the engine touches. A narrow protocol: rdflib graphs and ``StarLayerGraph`` satisfy it as is;
an Oxigraph- or Rust-backed implementation would provide the same five methods.

Terms are ``rdflib`` nodes plus ``starlayer.graph.model`` ``TripleTerm`` / ``DirLangString``. Equality is RDF term
equality. ``preserves_lexical_forms`` says whether literals come back exactly as stored (parked issue: Oxigraph
normalizes them).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Protocol, runtime_checkable

Term = Any


@runtime_checkable
class GraphView(Protocol):
    def triples(self, pattern: tuple[Term | None, Term | None, Term | None]) -> Iterator[tuple[Term, Term, Term]]: ...
    def objects(self, subject: Term | None = None, predicate: Term | None = None) -> Iterator[Term]: ...
    def subjects(self, predicate: Term | None = None, object: Term | None = None) -> Iterator[Term]: ...
    def predicate_objects(self, subject: Term | None = None) -> Iterator[tuple[Term, Term]]: ...
    def __contains__(self, triple: tuple[Term, Term, Term]) -> bool: ...
