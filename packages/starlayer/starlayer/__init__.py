"""starlayer - the full StarLayer RDF 1.2 stack in one import.

**Deliberately minimal top-level surface.** This top level exists only to pick which subpackage you want:
`StarLayerGraph`/`StarLayerDataset` from `starlayer.graph` (Oxigraph-backed graphs and datasets over pyoxigraph terms),
`StarShaclSchema` from `starlayer.shacl`, `StarQuery` from `starlayer.sparql`. Every name here is the exact same object as its
source subpackage's own export; nothing is redefined, wrapped, or copied.

For anything not re-exported here, import from the owning subpackage directly (e.g. ``starlayer.graph.TripleTerm``,
``starlayer.sparql.srl.parse_ruleset`` (then ``RuleSet.infer()``/``.query()``), ``starlayer.shacl.apply_rules``).
"""

from .graph import StarLayerDataset, StarLayerGraph
from .shacl import StarShaclSchema
from .sparql import StarQuery

__all__ = [
    "StarLayerDataset",
    "StarLayerGraph",
    "StarQuery",
    "StarShaclSchema",
]
