"""The only graph surface the engine touches. A narrow protocol: ``StarLayerGraph`` / ``StarLayerDataset`` and the engine's own views satisfy it, and
every view also provides ``sparql_query`` (``SparqlCapable``, below).

Terms are pyoxigraph terms (``shacl_engine.terms``). Equality is RDF term
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
    """The read-only graph surface the SHACL engine uses; ``None`` in any position is a wildcard."""

    def triples(self, pattern: tuple[Term | None, Term | None, Term | None]) -> Iterator[tuple[Term, Term, Term]]:
        """Yield the triples matching ``pattern``."""
        ...

    def objects(self, subject: Term | None = None, predicate: Term | None = None) -> Iterator[Term]:
        """The objects of the triples matching the given subject and predicate."""
        ...

    def subjects(self, predicate: Term | None = None, object: Term | None = None) -> Iterator[Term]:
        """The subjects of the triples matching the given predicate and object."""
        ...

    def predicate_objects(self, subject: Term | None = None) -> Iterator[tuple[Term, Term]]:
        """The (predicate, object) pairs of the triples matching the given subject."""
        ...

    def __contains__(self, triple: tuple[Term, Term, Term]) -> bool:
        """Whether any triple matches ``triple``; ``None`` in a position matches anything."""
        ...


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
    ``StarLayerGraph.query`` already exists with a different signature. ``custom_functions`` maps function IRIs to Python
    callables (pyoxigraph's ``custom_functions``): the shapes graph's SHACL functions.
    """

    def sparql_query(
        self, text: str, init_bindings: Mapping[str, Term] | None = None, custom_functions: Mapping[Term, Any] | None = None
    ) -> Solutions:
        """Run a SPARQL SELECT or ASK query with variables pre-bound; the contract is in the class docstring."""
        ...
