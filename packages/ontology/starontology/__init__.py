"""starontology - the raw ontology/SHACL-shapes ``.ttl`` files this stack
ships, kept in one place, independent of any package that consumes them.

**Why this package exists.** Before it did, these six files lived scattered
across the packages that happened to consume them first: ``manch:``/``skos:``
inside ``packages/graph/starlayergraph/ontology/``, ``salg:`` inside
``packages/sparql/starsparql/ontology/``. That made "where do I edit the
``manch:`` vocabulary" and "where do I edit the ``salg:`` vocabulary"
different answers depending on which package happened to need it first - a
real editing/discoverability cost, not just an aesthetic one. Consolidating
them here means one place to look, one place to edit, regardless of which
package(s) end up consuming a given file.

**Why this is its own package, not just a shared directory.** Each `.ttl`
file here is pure data with no logic of its own - no ``pyshacl``, no
``starlayergraph``/``starsparql``/``starshacl`` import anywhere in this
package. That means `starontology` can sit *underneath* every package that
needs ontology data (`graph`, `sparql`) as a one-directional dependency,
rather than files needing to live inside whichever consumer happens to
already have a dependency edge to the others. It deliberately does **not**
do any SHACL validation itself, or wrap `pyshacl`/`starshacl` - loading a
shapes graph here and actually validating with it is each consuming
package's own job (`starlayergraph.ontology.manchester_shapes.validate()`,
`starlayergraph.ontology.skos_shapes.validate()`,
`starsparql.ontology.sparql_shapes.validate()`), since *how* to validate
(which reasoning settings, which severity flags) is genuinely different per
vocabulary - see each of those modules' own docstrings for why.

**What's here**: eight files, two per vocabulary (an OWL/RDFS ontology and
a SHACL shapes graph) for four vocabularies:

- ``manch:`` (``manchester-ast-ontology.ttl`` / ``manchester_shapes.ttl``) -
  OWL 2 Manchester Syntax's own internal AST as RDF.
- ``skos:`` (``skos-ontology.ttl`` / ``skos_shapes.ttl``) - the W3C SKOS
  Reference's own formal axioms and integrity conditions, over the real
  ``skos:`` namespace.
- ``salg:`` (``salg-ontology.ttl`` / ``sparql_shapes.ttl``) - a SPARQL 1.2
  query/update's own algebra as RDF.
- ``srl:`` (``srl-ontology.ttl`` / ``srl_shapes.ttl``) - SRL/SPARQL-RL's
  own rule-set abstract syntax as RDF (see `starsparql/srl_vocab.py`).

The SHACL 1.2 meta-shapes themselves (``starshacl``'s shapes-about-shapes)
are deliberately **not** here - they're generated Python
(``starshacl.meta_shapes.build_meta_shapes_graph()``), not a static file,
and stay inside ``starshacl`` where that generation code lives.

Every loader below returns a **fresh, plain ``rdflib.Graph``** - never a
``StarLayerGraph`` - since none of these six files carry RDF 1.2 content
(triple terms, direction-tagged literals) to represent; they're ordinary
RDF 1.1 vocabulary/shape definitions, so a plain ``rdflib.Graph`` is the
right and complete return type (the same reasoning ``starsparql``'s own
pre-existing ``ontology_graph()`` already documented before this package
existed).
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Graph

_HERE = Path(__file__).parent

MANCHESTER_ONTOLOGY_TTL_PATH = _HERE / "manchester-ast-ontology.ttl"
MANCHESTER_SHAPES_TTL_PATH = _HERE / "manchester_shapes.ttl"
SKOS_ONTOLOGY_TTL_PATH = _HERE / "skos-ontology.ttl"
SKOS_SHAPES_TTL_PATH = _HERE / "skos_shapes.ttl"
SPARQL_ONTOLOGY_TTL_PATH = _HERE / "salg-ontology.ttl"
SPARQL_SHAPES_TTL_PATH = _HERE / "sparql_shapes.ttl"
SRL_ONTOLOGY_TTL_PATH = _HERE / "srl-ontology.ttl"
SRL_SHAPES_TTL_PATH = _HERE / "srl_shapes.ttl"


def _load(path: Path) -> Graph:
    g = Graph()
    g.parse(source=str(path), format="turtle")
    return g


def manchester_ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``manch:`` RDFS ontology."""
    return _load(MANCHESTER_ONTOLOGY_TTL_PATH)


def manchester_shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``manch:`` SHACL shapes."""
    return _load(MANCHESTER_SHAPES_TTL_PATH)


def skos_ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``skos:`` OWL/RDFS ontology."""
    return _load(SKOS_ONTOLOGY_TTL_PATH)


def skos_shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``skos:`` SHACL shapes."""
    return _load(SKOS_SHAPES_TTL_PATH)


def sparql_ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``salg:`` RDFS ontology."""
    return _load(SPARQL_ONTOLOGY_TTL_PATH)


def sparql_shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``salg:`` SHACL shapes."""
    return _load(SPARQL_SHAPES_TTL_PATH)


def srl_ontology_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``srl:`` RDFS ontology."""
    return _load(SRL_ONTOLOGY_TTL_PATH)


def srl_shapes_graph() -> Graph:
    """A fresh ``rdflib.Graph`` of the ``srl:`` SHACL shapes."""
    return _load(SRL_SHAPES_TTL_PATH)
