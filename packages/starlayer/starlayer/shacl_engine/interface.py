"""The only graph surface the engine touches. A narrow protocol: rdflib graphs and ``StarLayerGraph`` satisfy it as is;
an Oxigraph- or Rust-backed implementation would provide the same five methods, and optionally ``sparql_query``
(``SparqlCapable``, below).

Terms are ``rdflib`` nodes plus ``starlayer.graph.model`` ``TripleTerm`` / ``DirLangString``. Equality is RDF term
equality. ``preserves_lexical_forms`` says whether literals come back exactly as stored (parked issue: Oxigraph
normalizes them).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

Term = Any


@runtime_checkable
class GraphView(Protocol):
    def triples(self, pattern: tuple[Term | None, Term | None, Term | None]) -> Iterator[tuple[Term, Term, Term]]: ...
    def objects(self, subject: Term | None = None, predicate: Term | None = None) -> Iterator[Term]: ...
    def subjects(self, predicate: Term | None = None, object: Term | None = None) -> Iterator[Term]: ...
    def predicate_objects(self, subject: Term | None = None) -> Iterator[tuple[Term, Term]]: ...
    def __contains__(self, triple: tuple[Term, Term, Term]) -> bool: ...


@dataclass(frozen=True)
class Solutions:
    """The result of a SPARQL query, as plain data: ``variables`` are the projected variable names (no ``?``),
    ``rows`` the solutions (variable name -> term; unbound variables are absent), ``boolean`` the ASK answer (``None``
    for SELECT)."""

    variables: tuple[str, ...] = ()
    rows: tuple[dict[str, Term], ...] = ()
    boolean: bool | None = None


@runtime_checkable
class SparqlCapable(Protocol):
    """Optional capability of a data graph: run a SPARQL query on it (SPARQL-related features need it).

    ``sparql_query(text, init_bindings)`` runs the SPARQL SELECT or ASK ``text`` (SPARQL 1.2 syntax) against the graph
    with the variables in ``init_bindings`` (name without ``?``/``$`` -> term) pre-bound as SHACL 1.2 SPARQL appendix A
    defines it: the same as joining the one-row table of those bindings into every basic graph pattern, property path
    and GRAPH pattern of the query. The engine has already rejected queries it must not run (MINUS, VALUES, SERVICE,
    ``AS`` of a pre-bound variable), so implementations need not. The method name is not ``query`` because
    ``StarLayerGraph.query`` and rdflib's ``Graph.query`` already exist with a different signature.

    A graph that lacks this method is queried through ``starlayer.shacl_engine.sparql_support.starlayer_sparql_query``,
    which runs the text through StarLayer's own query layer (``starlayer.graph.query.sparql_api.prepareQuery`` and the
    graph's ``.query()``). A native backend (Oxigraph, later Rust) provides the method itself and sets the
    ``native_sparql`` capability flag.
    """

    def sparql_query(self, text: str, init_bindings: Mapping[str, Term] | None = None) -> Solutions: ...
