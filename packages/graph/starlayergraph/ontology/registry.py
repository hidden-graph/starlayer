"""
starlayergraph.ontology.registry

A registry of every ontology/SHACL-shapes pair ("SHACL library") this
stack ships, so a caller can discover and load any of them by name without
needing to know which package or file each one actually lives in. Origin:
`packages/graph/docs/future_enhancements.md`'s own SUGGESTION item - "a
method to return a list of SHACL libraries and return a specific SHACL
library ... SPARQL AST, SKOS, Manchester AST, SHACL, generic RDF, OWL RDF."

**Lives in `starlayergraph`, not `starshacl` or `starsparql`** - it's the
only package that already depends on both siblings (`packages/graph/pyproject.toml`
depends on both `sparql` and `shacl`, an intentional pair of circular
dependencies, confirmed working - see `shape_derivation.py`'s own module
docstring for the `graph`<->`shacl` one). `starshacl` has no dependency on
`starsparql`, so it couldn't reach `salg:` without adding a new cycle;
`starsparql` has no dependency on `starshacl` either.

Every loader below is resolved **lazily** - the real `import starsparql`/
`import starshacl` only happens inside the function actually called, not at
module import time. `list_shacl_libraries()`/`get_shacl_library()` never
require every optional dependency (`pyshacl`, etc.) to be installed just to
enumerate what exists; calling a library's own `.shapes_graph()`/`.validate()`
still needs whatever that library's own module needs (same friendly,
actionable `ImportError` each `xxx_shapes.py` module already raises on its
own).

**Deliberately not yet registered** - the user's own "any others?" is
answered here, not silently dropped: "generic RDF" (a SHACL shape to drive
a generic RDF editor, likely built via `StarLayerGraph.derive()`) doesn't
exist yet - see `future_enhancements.md`'s own still-open SUGGESTION item;
"OWL RDF" names no concrete artifact anywhere in this codebase to point at.
Both are left out entirely rather than registered as a stub/placeholder
entry - add them here once they're real, rather than shipping a
`ShaclLibrary` whose loaders would immediately raise `NotImplementedError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rdflib import Graph


@dataclass(frozen=True)
class ShaclLibrary:
    """One registered ontology/shapes pair.

    ``ontology_graph``/``shapes_graph``/``validate`` are lazy zero-argument
    (``validate`` takes the data graph) loader callables - ``None`` for a
    library that genuinely has no artifact of that kind (e.g. ``"shacl"``
    itself has no separate OWL ontology in this stack, only meta-shapes),
    never a dummy no-op standing in for a missing one.
    """

    name: str
    description: str
    namespace: str | None
    ontology_graph: Callable[[], Graph] | None = None
    shapes_graph: Callable[[], Graph] | None = None
    validate: Callable[..., tuple[bool, Any, str]] | None = None


def _manchester_ontology_graph() -> Graph:
    from starlayergraph.ontology import ontology_graph
    return ontology_graph()


def _manchester_shapes_graph() -> Graph:
    from starlayergraph.ontology.manchester_shapes import shapes_graph
    return shapes_graph()


def _manchester_validate(data_graph: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    from starlayergraph.ontology.manchester_shapes import validate
    return validate(data_graph, **kwargs)


def _skos_ontology_graph() -> Graph:
    from starlayergraph.ontology import skos_ontology_graph
    return skos_ontology_graph()


def _skos_shapes_graph() -> Graph:
    from starlayergraph.ontology.skos_shapes import shapes_graph
    return shapes_graph()


def _skos_validate(data_graph: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    from starlayergraph.ontology.skos_shapes import validate
    return validate(data_graph, **kwargs)


def _sparql_ontology_graph() -> Graph:
    import starsparql
    return starsparql.ontology_graph()


def _sparql_shapes_graph() -> Graph:
    import starsparql
    return starsparql.shapes_graph()


def _sparql_validate(data_graph: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    import starsparql
    return starsparql.validate(data_graph, **kwargs)


def _shacl_meta_shapes_graph() -> Graph:
    from starshacl.meta_shapes import build_meta_shapes_graph
    return build_meta_shapes_graph()


def _shacl_meta_validate(shapes_graph_to_check: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    # Note the different shape from every other library's own validate():
    # this checks a *shapes* graph's own well-formedness against SHACL's
    # meta-shapes, not a data graph against this library's shapes - the
    # correct meaning of "validate" for the "shacl" library itself.
    from starshacl.meta_shapes import meta_validate
    return meta_validate(shapes_graph_to_check, **kwargs)


_LIBRARIES: dict[str, ShaclLibrary] = {
    lib.name: lib
    for lib in (
        ShaclLibrary(
            name='manchester',
            description=(
                "OWL 2 Manchester Syntax's own internal AST as RDF (manch:) - "
                "frames/clauses/class- and property-expressions/data-ranges, "
                "one level upstream of the compiled OWL RDF mapping."
            ),
            namespace='https://github.com/hidden-graph/starlayergraph/ns/manchester-ast#',
            ontology_graph=_manchester_ontology_graph,
            shapes_graph=_manchester_shapes_graph,
            validate=_manchester_validate,
        ),
        ShaclLibrary(
            name='skos',
            description=(
                "The W3C SKOS Reference's own formal axioms and numbered "
                "Documented Consistency and Integrity Conditions, over the "
                "real skos: namespace."
            ),
            namespace='http://www.w3.org/2004/02/skos/core#',
            ontology_graph=_skos_ontology_graph,
            shapes_graph=_skos_shapes_graph,
            validate=_skos_validate,
        ),
        ShaclLibrary(
            name='sparql',
            description=(
                "A SPARQL 1.2 query/update's own algebra as RDF (salg:), "
                "from the sibling starsparql package - encode/edit/decode/"
                "re-execute a query as data."
            ),
            namespace='https://github.com/hidden-graph/starsparql/ns/algebra#',
            ontology_graph=_sparql_ontology_graph,
            shapes_graph=_sparql_shapes_graph,
            validate=_sparql_validate,
        ),
        ShaclLibrary(
            name='shacl',
            description=(
                "The SHACL 1.2 meta-shapes themselves (starshacl's own "
                "shapes-about-shapes, validating a shapes graph's own "
                "well-formedness) - no separate OWL ontology exists for "
                "SHACL's own vocabulary anywhere in this stack, so "
                "ontology_graph is None for this one entry, not a stub."
            ),
            namespace='http://www.w3.org/ns/shacl#',
            shapes_graph=_shacl_meta_shapes_graph,
            validate=_shacl_meta_validate,
        ),
    )
}


def list_shacl_libraries() -> tuple[str, ...]:
    """Names of every registered ontology/shapes library, sorted."""
    return tuple(sorted(_LIBRARIES))


def get_shacl_library(name: str) -> ShaclLibrary:
    """Look up one registered library by name.

    Raises ``KeyError`` (naming every valid choice) for an unknown name,
    rather than returning ``None`` - a typo'd name should fail loudly at
    the call site, not surface as a confusing ``AttributeError`` two lines
    later on a ``None``.
    """
    try:
        return _LIBRARIES[name]
    except KeyError:
        raise KeyError(
            f'{name!r} is not a registered SHACL library - choices are {list_shacl_libraries()}'
        ) from None
