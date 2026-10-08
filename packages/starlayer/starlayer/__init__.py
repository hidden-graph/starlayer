"""starlayer - the full StarLayer RDF 1.2 stack in one import.

**Deliberately minimal top-level surface (slimmed 2026-10-04).** `starlayer.graph`
is the rdflib replacement; `starlayer.shacl` is the pyshacl replacement. This
top level exists only to pick which one you want - `StarLayerGraph`/
`StarLayerDataset` from `starlayer.graph`, `StarShaclSchema` from
`starlayer.shacl` - not to carry up everything each of those subpackages
re-exports for its own rdflib-mirroring convenience (`BNode`/`Literal`/
`URIRef`/`Variable`/`Namespace`/`RDF`/`RDFS`/`XSD`/plain `Graph`/`Dataset`
all still live at `starlayer.graph`, same as before - just not duplicated
up here too) or RDF-1.2-specific value types scoped to the graph layer
(`TripleTerm`/`DirLangString` - also still at `starlayer.graph`). Every
name here is the exact same object as its source subpackage's own export;
nothing is redefined, wrapped, or copied.

For anything not re-exported here, import from the owning subpackage
directly (e.g. ``starlayer.graph.Namespace``, ``starlayer.sparql.prepare_query_12``,
``starlayer.sparql.srl.parse_ruleset`` (then ``RuleSet.infer()``/``.query()``),
``starlayer.shacl.shacl_inference.apply_rules``).
"""

from .graph import StarLayerDataset, StarLayerGraph
from .shacl import StarShaclSchema

__all__ = [
    "StarLayerDataset",
    "StarLayerGraph",
    "StarShaclSchema",
]
