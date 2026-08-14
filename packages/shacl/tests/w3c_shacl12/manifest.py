"""Generic DAWG-style test-manifest walker for the vendored W3C SHACL 1.2 suite.

Independent of test type (``sht:Validate``/``sht:EvalNodeExpr``/``sht:Infer``/
anything else) - see docs/w3c-shacl12-test-suite-plan.md for the format this
parses and why. Confirmed against the vendored suite's own manifest files
(not assumed from the general DAWG spec): ``mf:include`` is a set of ordinary
repeated triples (not an ``rdf:List``), while ``mf:entries`` is an
``rdf:List``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

from rdflib import URIRef
from rdflib.namespace import RDF
from starlayergraph.graph.starlayer_graph import StarLayerGraph

from .namespaces import MF

# Parsed-graph cache keyed by resolved absolute path - a leaf test file is
# reached exactly once per manifest walk in this suite, but sharing the
# cache across walks (e.g. Phase 1's sht:Validate walk and a later phase's
# sht:EvalNodeExpr walk both starting from tests/manifest.ttl) avoids
# reparsing shared ancestor manifests.
_DOCUMENT_CACHE: dict[Path, StarLayerGraph] = {}


def file_uri(path: Path) -> URIRef:
    return URIRef(path.resolve().as_uri())


def uri_to_path(iri: URIRef) -> Path:
    parsed = urlparse(str(iri))
    if parsed.scheme != "file":
        raise ValueError(f"expected a file:// IRI, got {iri!r}")
    return Path(unquote(parsed.path))


def load_document(path: Path) -> StarLayerGraph:
    """Parse ``path`` as Turtle 1.2, cached, with its own file:// IRI as base.

    Uses ``format="turtle12"`` (StarLayerGraph's own RDF-1.2-aware parser,
    ``starlayergraph.parsers.turtle_parser.StarLayerTurtleParser``), not plain
    ``"turtle"`` - confirmed empirically that several suite fixtures use
    genuine RDF 1.2 Turtle syntax plain rdflib's parser rejects outright:
    triple-term literals (``<<( s p o )>>``), inline reification annotations
    (``{| ... |}``), and direction-tagged language strings
    (``"txt"@en--ltr``).

    ``publicID`` resolves ``<>`` and every other relative IRI (including
    ``mf:include`` targets) against the file's own IRI - fixed upstream in
    ``starlayergraph`` 2026-07-30 (see
    docs/starlayergraph-upstream-change-log.md); previously this needed a local
    post-parse workaround here, now removed.
    """
    path = path.resolve()
    if path not in _DOCUMENT_CACHE:
        graph = StarLayerGraph()
        graph.parse(location=str(path), format="turtle12", publicID=str(file_uri(path)))
        _DOCUMENT_CACHE[path] = graph
    return _DOCUMENT_CACHE[path]


def clone_graph(source: StarLayerGraph) -> StarLayerGraph:
    """Return an independent copy of a StarLayerGraph.

    Round-trips through the public ``.triples()`` view (real, decoded
    TripleTerm values) and ``.add()`` (which re-encodes/re-registers them for
    the new graph's own store), rather than a plain rdflib-level union -
    needed because ``load_document`` caches and reuses graph objects for the
    lifetime of the test session, and a self-contained fixture commonly
    passes the *same* cached document as both data_graph and shacl_graph;
    without an independent copy per role, a mutation validate() makes to one
    role (e.g. target-type injection augmenting the shapes graph) could leak
    into the other role or into a later test that reuses the same cached
    document.
    """
    clone = StarLayerGraph()
    for prefix, namespace in source.namespaces():
        clone.bind(prefix, namespace)
    for triple in source.triples((None, None, None)):
        clone.add(triple)
    return clone


@dataclass(frozen=True)
class ManifestEntry:
    iri: URIRef
    entry_type: URIRef | None
    graph: StarLayerGraph | None
    source_path: Path
    # Set (with entry_type=None, graph=None) instead of raising when an
    # mf:include target fails to parse - see iter_manifest_entries. A test
    # runner that doesn't recognize a parse_error entry as its own type
    # naturally skips it (entry_type is None); a dedicated health-check
    # module surfaces it instead of letting it vanish from collection
    # unnoticed. Per CLAUDE.md's testing discipline, a load failure gets a
    # visible, reasoned disposition, never a silent drop.
    parse_error: str | None = None


def iter_manifest_entries(manifest_path: Path, *, _visited: set[Path] | None = None):
    """Recursively walk a manifest, yielding one ManifestEntry per mf:entries member.

    Follows mf:include at every level. A file with no mf:entries of its own
    (a pure router, e.g. the suite's top-level tests/manifest.ttl) yields
    nothing directly - only its included descendants contribute entries.

    An mf:include target that fails to parse yields one synthetic
    parse_error entry for that file (see ManifestEntry.parse_error) and does
    not recurse further into it, rather than raising and aborting the whole
    walk - a handful of the vendored suite's own fixtures use Turtle
    constructs the young StarLayerTurtleParser doesn't yet support (see
    docs/starlayergraph-upstream-change-log.md), and one bad fixture shouldn't
    hide every other entry from collection.
    """
    if _visited is None:
        _visited = set()

    manifest_path = manifest_path.resolve()
    if manifest_path in _visited:
        return
    _visited.add(manifest_path)

    try:
        graph = load_document(manifest_path)
    except Exception as exc:  # noqa: BLE001 - reported as a test entry, not swallowed
        yield ManifestEntry(
            iri=file_uri(manifest_path),
            entry_type=None,
            graph=None,
            source_path=manifest_path,
            parse_error=str(exc),
        )
        return

    manifest_node = file_uri(manifest_path)

    for _, _, entries_list in graph.triples((manifest_node, MF.entries, None)):
        for entry_iri in graph.items(entries_list):
            entry_types = list(graph.objects(entry_iri, RDF.type))
            yield ManifestEntry(
                iri=entry_iri,
                entry_type=entry_types[0] if entry_types else None,
                graph=graph,
                source_path=manifest_path,
            )

    for _, _, included in graph.triples((manifest_node, MF.include, None)):
        yield from iter_manifest_entries(uri_to_path(included), _visited=_visited)
