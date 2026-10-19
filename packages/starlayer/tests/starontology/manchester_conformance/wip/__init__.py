"""Working copy of the Manchester tree layer (``starlayer.starontology.manchester`` plus its two
vocabulary files), edited here so fixes cannot conflict with other work on ``starontology/``.

Merge base for the eventual three-way comparison: ``../snapshots/`` (the files as they were at the
start). Live files: ``starlayer/starontology/``. This copy: this directory. When the work is done, diff
all three and fold the changes back; see ``../WIP.md``.

``get_ontology_graph`` mirrors ``starlayer.starontology.get_ontology_graph`` for the only two names the
tree module asks for, reading this directory's copies instead of the live files.
"""

from __future__ import annotations

from pathlib import Path

_HERE = Path(__file__).parent
_FILES = {
    "manchester_owl": _HERE / "manchester-ast-ontology.ttl",
    "manchester_shacl": _HERE / "manchester_shapes.ttl",
}
_IDENTIFIERS = {
    "manchester_owl": "https://github.com/hidden-graph/starlayer/ns/graph/manchester-ast",
    "manchester_shacl": "https://github.com/hidden-graph/starlayer/ns/graph/manchester-shapes",
}


def get_ontology_graph(name: str):
    """A fresh ``StarLayerGraph`` of the named working-copy file."""
    from rdflib import URIRef
    from starlayer.graph import StarLayerGraph

    try:
        path = _FILES[name]
    except KeyError:
        raise KeyError(f"{name!r} is not a working-copy ontology - choices are {sorted(_FILES)}") from None
    g = StarLayerGraph(identifier=URIRef(_IDENTIFIERS[name]))
    g.parse(path, format="turtle")
    return g
