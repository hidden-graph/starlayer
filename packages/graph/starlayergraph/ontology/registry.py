"""
starlayergraph.ontology.registry

A registry of every ontology/SHACL-shapes file this stack ships, so a
caller can discover and load any of them by name without needing to know
which package or file each one actually lives in. Origin:
`packages/graph/docs/future_enhancements.md`'s own SUGGESTION item - "a
method to return a list of SHACL libraries and return a specific SHACL
library ... SPARQL AST, SKOS, Manchester AST, SHACL, generic RDF, OWL RDF."

**"Ontology registry", not "SHACL library registry"** - an OWL/RDFS
ontology and a SHACL shapes graph are both just ontology files, registered
as equals rather than one ("shapes") privileged over the other ("ontology")
by being bundled as its secondary attribute. Each is its own independent
entry (`manchester_owl`/`manchester_shacl`, not one `manchester` entry
carrying both) - renamed from an earlier design that paired them, per
direct user feedback: "the libraries should be described like skos_owl, or
skos_shacl. don't treat them like pairs."

**Lives in `starlayergraph`, not `starontology`/`starshacl`/`starsparql`**
- it's the one package with visibility into all of them (`starlayergraph`
depends on `starontology`, `starsparql`, and `starshacl`; none of those
three depend on each other's ontology data except through `starlayergraph`
itself). Exposed as `starlayergraph.ontology.list_ontologies()`/
`get_ontology()` directly, without a caller needing a separate `import
starlayergraph.ontology` - see `starlayergraph/__init__.py`.

**The raw `.ttl` files themselves live in the sibling `starontology`
package** (`packages/ontology`), not here - one place to edit them,
independent of which consuming package happens to validate against them.
This module only wires up discovery/validation over files `starontology`
already loads.

Every loader below is resolved **lazily** - the real `import starsparql`/
`import starshacl` only happens inside the function actually called, not at
module import time (avoiding a circular-import deadlock, since
`starlayergraph` depends on both). `list_ontologies()`/`get_ontology()`
never require every optional dependency (`pyshacl`, etc.) to be installed
just to enumerate what exists; calling an entry's own `.graph()`/
`.validate()` still needs whatever that entry's own module needs (same
friendly, actionable `ImportError` each `xxx_shapes.py` module already
raises on its own).

**Deliberately not yet registered** - the user's own "any others?" is
answered here, not silently dropped: "generic RDF" (a SHACL shape to drive
a generic RDF editor, likely built via `StarLayerGraph.derive()`) doesn't
exist yet - see `future_enhancements.md`'s own still-open SUGGESTION item;
"OWL RDF" names no concrete artifact anywhere in this codebase to point at.
Both are left out entirely rather than registered as a stub/placeholder
entry - add them here once they're real, rather than shipping an `Ontology`
whose loader would immediately raise `NotImplementedError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from rdflib import Graph


@dataclass(frozen=True)
class Ontology:
    """One registered ontology/shapes file - always exactly one kind of
    artifact (an OWL/RDFS ontology, or a SHACL shapes graph), never a pair.

    ``graph`` is a lazy, zero-argument loader returning a fresh
    ``rdflib.Graph``. ``validate`` is only set on shapes-graph entries (an
    OWL-ontology entry has nothing meaningful to validate a data graph
    against on its own) - ``None`` otherwise, never a dummy no-op.
    """

    name: str
    description: str
    namespace: str | None
    kind: str  # "owl" or "shacl"
    graph: Callable[[], Graph]
    validate: Callable[..., tuple[bool, Any, str]] | None = None


def _manchester_owl_graph() -> Graph:
    from starlayergraph.ontology import ontology_graph
    return ontology_graph()


def _manchester_shacl_graph() -> Graph:
    from starlayergraph.ontology.manchester_shapes import shapes_graph
    return shapes_graph()


def _manchester_shacl_validate(data_graph: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    from starlayergraph.ontology.manchester_shapes import validate
    return validate(data_graph, **kwargs)


def _skos_owl_graph() -> Graph:
    from starlayergraph.ontology import skos_ontology_graph
    return skos_ontology_graph()


def _skos_shacl_graph() -> Graph:
    from starlayergraph.ontology.skos_shapes import shapes_graph
    return shapes_graph()


def _skos_shacl_validate(data_graph: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    from starlayergraph.ontology.skos_shapes import validate
    return validate(data_graph, **kwargs)


def _sparql_owl_graph() -> Graph:
    import starsparql
    return starsparql.ontology_graph()


def _sparql_shacl_graph() -> Graph:
    import starsparql
    return starsparql.shapes_graph()


def _sparql_shacl_validate(data_graph: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    import starsparql
    return starsparql.validate(data_graph, **kwargs)


def _shacl_meta_graph() -> Graph:
    from starshacl.meta_shapes import build_meta_shapes_graph
    return build_meta_shapes_graph()


def _shacl_meta_validate(shapes_graph_to_check: Any, **kwargs: Any) -> tuple[bool, Any, str]:
    # Note the different shape from every other entry's own validate(): this
    # checks a *shapes* graph's own well-formedness against SHACL's own
    # meta-shapes, not a data graph against this entry's own shapes - the
    # correct meaning of "validate" for the "shacl_meta" entry specifically.
    from starshacl.meta_shapes import meta_validate
    return meta_validate(shapes_graph_to_check, **kwargs)


_ONTOLOGIES: dict[str, Ontology] = {
    ont.name: ont
    for ont in (
        Ontology(
            name='manchester_owl',
            description=(
                "OWL 2 Manchester Syntax's own internal AST as RDF (manch:) - "
                "frames/clauses/class- and property-expressions/data-ranges, "
                "one level upstream of the compiled OWL RDF mapping."
            ),
            namespace='https://github.com/hidden-graph/starlayergraph/ns/manchester-ast#',
            kind='owl',
            graph=_manchester_owl_graph,
        ),
        Ontology(
            name='manchester_shacl',
            description="SHACL shapes validating a manch: AST graph's own structural well-formedness.",
            namespace='https://github.com/hidden-graph/starlayergraph/ns/manchester-ast#',
            kind='shacl',
            graph=_manchester_shacl_graph,
            validate=_manchester_shacl_validate,
        ),
        Ontology(
            name='skos_owl',
            description=(
                "The W3C SKOS Reference's own formal axioms and numbered "
                "Documented Consistency and Integrity Conditions, over the "
                "real skos: namespace."
            ),
            namespace='http://www.w3.org/2004/02/skos/core#',
            kind='owl',
            graph=_skos_owl_graph,
        ),
        Ontology(
            name='skos_shacl',
            description="SHACL shapes checking SKOS's own numbered integrity conditions against a data graph.",
            namespace='http://www.w3.org/2004/02/skos/core#',
            kind='shacl',
            graph=_skos_shacl_graph,
            validate=_skos_shacl_validate,
        ),
        Ontology(
            name='sparql_owl',
            description=(
                "A SPARQL 1.2 query/update's own algebra as RDF (salg:), "
                "from the sibling starsparql package - encode/edit/decode/"
                "re-execute a query as data."
            ),
            namespace='https://github.com/hidden-graph/starsparql/ns/algebra#',
            kind='owl',
            graph=_sparql_owl_graph,
        ),
        Ontology(
            name='sparql_shacl',
            description="SHACL shapes validating a salg: algebra graph's own structural well-formedness.",
            namespace='https://github.com/hidden-graph/starsparql/ns/algebra#',
            kind='shacl',
            graph=_sparql_shacl_graph,
            validate=_sparql_shacl_validate,
        ),
        Ontology(
            name='shacl_meta',
            description=(
                "The SHACL 1.2 meta-shapes themselves (starshacl's own "
                "shapes-about-shapes, validating a shapes graph's own "
                "well-formedness) - no separate OWL ontology exists for "
                "SHACL's own vocabulary anywhere in this stack, so there's "
                "no shacl_owl counterpart to this entry."
            ),
            namespace='http://www.w3.org/ns/shacl#',
            kind='shacl',
            graph=_shacl_meta_graph,
            validate=_shacl_meta_validate,
        ),
    )
}


def list_ontologies() -> tuple[str, ...]:
    """Names of every registered ontology/shapes file, sorted."""
    return tuple(sorted(_ONTOLOGIES))


def get_ontology(name: str) -> Ontology:
    """Look up one registered ontology/shapes file by name.

    Raises ``KeyError`` (naming every valid choice) for an unknown name,
    rather than returning ``None`` - a typo'd name should fail loudly at
    the call site, not surface as a confusing ``AttributeError`` two lines
    later on a ``None``.
    """
    try:
        return _ONTOLOGIES[name]
    except KeyError:
        raise KeyError(
            f'{name!r} is not a registered ontology - choices are {list_ontologies()}'
        ) from None
