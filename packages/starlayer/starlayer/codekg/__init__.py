"""starlayer.codekg - loader for the code knowledge graph extracted from
this project's own Python source.

Two files, two very different lifecycles:

- ``ontology.ttl`` is the hand-maintained vocabulary (``slkg:``/
  ``externaltype:``) this subpackage defines - never touched by the
  extractor, edited by hand like any other vocabulary in
  ``starlayer.starontology``.
- ``codekg.trig`` is the auto-generated dataset the extractor produces: one
  named graph per extracted module, wholesale-replaced on every extractor
  run (see ``starlayer.codekg.extractor``, built separately). It does not
  exist until the extractor has run at least once.

A third named graph, identified by ``CURATED_GRAPH_IRI``, is reserved for
a future hand-maintained curated graph (e.g. "this notebook demonstrates
this method") - not file-backed yet, created on demand by whatever later
code populates it. This loader never writes to it.

Mirrors ``starlayer.starontology``'s own loader pattern: parse once,
never hand back a shared mutable object, copy out a fresh graph/dataset
per call instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from rdflib import Namespace, URIRef

if TYPE_CHECKING:
    from starlayer.graph import StarLayerGraph
    from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

CODEKG_NS = Namespace("https://github.com/hidden-graph/starlayer/ns/codekg#")
EXTERNALTYPE_NS = Namespace("https://github.com/hidden-graph/starlayer/ns/codekg/externaltype#")

# ontology.ttl's own self-identity, used as its named-graph IRI when loaded
# into a dataset alongside codekg.trig's per-module graphs.
ONTOLOGY_GRAPH_IRI = URIRef("https://github.com/hidden-graph/starlayer/ns/codekg")

# Reserved for the future hand-curated graph (see module docstring) - not
# file-backed yet, never written to by this loader.
CURATED_GRAPH_IRI = URIRef("https://github.com/hidden-graph/starlayer/ns/codekg/curated")

# Per-module named-graph IRIs are BLOB_BASE + <repo-relative path from
# packages/starlayer/starlayer/>, matching starontology's own GitHub-blob-
# URL convention.
BLOB_BASE = "https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/"

# Same convention, for files under packages/starlayer/tests/ - see
# starlayer.codekg.extractor.symbol_index.resolve_root(), which is what
# decides which of these two bases a given target path gets.
TESTS_BLOB_BASE = "https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/tests/"

_HERE = Path(__file__).parent
_ONTOLOGY_TTL_PATH = _HERE / "ontology.ttl"

# The extractor's generated dataset file - does not exist until the
# extractor has run at least once. get_codekg_dataset() below handles that
# missing-file case gracefully rather than crashing, since this loader
# needs to work both before and after the extractor's first run.
CODEKG_TRIG_PATH = _HERE / "codekg.trig"


def get_ontology_graph() -> StarLayerGraph:
    """A fresh ``StarLayerGraph`` of ``ontology.ttl`` alone (plain Turtle,
    not a dataset), identified by ``ONTOLOGY_GRAPH_IRI``."""
    # Lazy, not top-level: a top-level `from starlayer.graph import
    # StarLayerGraph` pulls in the whole starlayer package before this
    # subpackage finishes its own import (Python always fully executes a
    # parent package's __init__.py before any of its submodules) - the
    # same circular-import discipline starlayer.starontology's own loaders
    # follow, kept here for consistency even though today's import order
    # doesn't strictly require it.
    from starlayer.graph import StarLayerGraph

    graph = StarLayerGraph(identifier=ONTOLOGY_GRAPH_IRI)
    graph.parse(str(_ONTOLOGY_TTL_PATH), format="turtle")
    return graph


def get_codekg_dataset() -> StarLayerDataset:
    """A fresh ``StarLayerDataset`` with ``codekg.trig`` parsed into it, or
    an empty dataset (no module graphs) if the extractor hasn't produced
    that file yet. Never cached/shared - the extractor mutates a dataset
    returned from a similar pattern, so a caller must never be handed back
    the same mutable object another caller could also be holding."""
    from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

    dataset = StarLayerDataset()
    if CODEKG_TRIG_PATH.exists():
        dataset.parse(str(CODEKG_TRIG_PATH), format="trig12")
    return dataset


def get_module_graph(module_path: str) -> StarLayerGraph | None:
    """The named graph for one extracted module, or ``None`` if it doesn't
    exist (or is empty) in the current ``codekg.trig``.

    ``module_path`` is a repo-relative path under
    ``packages/starlayer/starlayer/``, e.g. ``"graph/model/encoding.py"``.
    """
    iri = URIRef(BLOB_BASE + module_path)
    graph = get_codekg_dataset().get_context(iri)
    if len(graph) == 0:
        return None
    return graph
