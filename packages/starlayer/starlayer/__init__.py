"""starlayer - the full StarLayer RDF 1.2 stack in one import.

**Deliberately minimal top-level surface.** This top level exists only to pick which subpackage you want:
`StarLayerGraph`/`StarLayerDataset` from `starlayer.graph` (Oxigraph-backed graphs and datasets over pyoxigraph terms),
`StarShaclProcessor` from `starlayer.shacl`, `StarQuery` from `starlayer.sparql`. Every name here is the exact same object as its
source subpackage's own export; nothing is redefined, wrapped, or copied.

For anything not re-exported here, import from the owning subpackage directly (e.g. ``starlayer.graph.TripleTerm``,
``starlayer.sparql.srl.parse_ruleset`` (then ``RuleSet.infer()``/``.query()``), ``starlayer.shacl.apply_rules``).
"""

from .graph import StarLayerDataset, StarLayerGraph
from .shacl import StarShaclProcessor
from .sparql import StarQuery


def __getattr__(name: str):
    """``StarShaclSchema``, the old name of ``StarShaclProcessor``: the same class, with a DeprecationWarning."""
    if name == "StarShaclSchema":
        import warnings

        warnings.warn(
            "StarShaclSchema is renamed StarShaclProcessor; the old name will be removed",
            DeprecationWarning,
            stacklevel=2,
        )
        return StarShaclProcessor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "StarLayerDataset",
    "StarLayerGraph",
    "StarQuery",
    "StarShaclProcessor",
]
