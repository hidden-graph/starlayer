"""scripts/build_kg.py - the whole KG in one plain-TriG file, ``codekg/starlayer-kg.trig``.

The code graph (``codekg.trig``), the curated files (``codekg/curated/*.ttl``) and the vocabulary (``ontology.ttl``)
are separate sources. This joins them into one file that an agent can download, load into memory with any RDF
library and query, without a StarLayer checkout:

    from starlayer import StarLayerDataset
    kg = StarLayerDataset(default_union=True)
    kg.parse(path, format="trig12")

Named graphs in the file:

- one per extracted module (the code graph), plus the build stamp graph (``.../codekg/build``);
- the vocabulary (``.../ns/codekg``) and the curated layer (``.../codekg/curated``: capabilities, notebook links,
  upstream issues, the query library as sqe trees, and the derived ``slkg:demonstratedBy`` links);
- a derived graph (``.../codekg/derived``) holding ``slkg:queryText``, the SPARQL text of every named query, so the
  queries can be read from the graph itself and run with ``kg.query(text)``. The sqe trees stay the source.

Written and read with StarLayer's own TriG 1.2 support (``trig12``), the same writer that produces ``codekg.trig``;
plain rdflib's TriG output is not read back by StarLayer's parser, and the library is the tool to use.
Build-time only, like the other scripts here. Run: ``python scripts/build_kg.py [--check]``. ``--check`` rebuilds in memory and compares each named
graph (by isomorphism, since blank-node labels differ between runs) with the committed file.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages/starlayer"))

OUTPUT_REL = "packages/starlayer/starlayer/codekg/starlayer-kg.trig"

PREFIXES = {
    "slkg": "https://github.com/hidden-graph/starlayer/ns/codekg#",
    "dcterms": "http://purl.org/dc/terms/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "prov": "http://www.w3.org/ns/prov#",
    "sqe": "https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#",
    "spexpr": "https://github.com/hidden-graph/starlayer/ns/sparql/expr#",
    "ql": "https://github.com/hidden-graph/starlayer/ns/codekg/curated/query-library#",
    "cur": "https://github.com/hidden-graph/starlayer/ns/codekg/curated/functionality#",
    "nl": "https://github.com/hidden-graph/starlayer/ns/codekg/curated/notebook-links#",
    "ui": "https://github.com/hidden-graph/starlayer/ns/codekg/curated/upstream-issues#",
}


def build_dataset():
    """The combined dataset: the code graph, curated layer and build stamp, plus the vocabulary and derived query text."""
    from starlayer import StarLayerDataset
    from starlayer.codekg import (
        CODEKG_NS,
        CURATED_GRAPH_IRI,
        DERIVED_GRAPH_IRI,
        ONTOLOGY_GRAPH_IRI,
        get_codekg_dataset,
        get_ontology_graph,
        queries,
    )
    from starlayer.graph import RDF, Literal

    out: StarLayerDataset = get_codekg_dataset(include_curated=True)
    for prefix, namespace in PREFIXES.items():
        out.bind(prefix, namespace)

    ontology = out.graph(ONTOLOGY_GRAPH_IRI)
    for triple in get_ontology_graph():
        ontology.add(triple)

    derived = out.graph(DERIVED_GRAPH_IRI)
    curated = out.graph(CURATED_GRAPH_IRI)
    for node in sorted(curated.subjects(RDF.type, CODEKG_NS.NamedQuery)):
        derived.add((node, CODEKG_NS.queryText, Literal(queries.query_text(str(node).rsplit("#", 1)[-1]))))
    return out


def same_dataset(left, right) -> list[str]:
    """Names of the graphs that differ between two datasets (empty when they hold the same triples)."""
    from starlayer.graph import BNode
    from starlayer.graph.compare import isomorphic

    problems = []
    left_graphs = {str(g.identifier): g for g in left.contexts() if len(g)}
    right_graphs = {str(g.identifier): g for g in right.contexts() if len(g)}
    problems += [f"only in the committed file: {i}" for i in sorted(set(right_graphs) - set(left_graphs))]
    problems += [f"missing from the committed file: {i}" for i in sorted(set(left_graphs) - set(right_graphs))]
    for name, graph in left_graphs.items():
        other = right_graphs.get(name)
        if other is None:
            continue
        has_bnodes = any(isinstance(term, BNode) for triple in graph for term in triple)
        same = isomorphic(graph, other) if has_bnodes else set(graph) == set(other)
        if not same:
            problems.append(f"differs: {name}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if the committed file is out of date")
    args = parser.parse_args()

    from starlayer import StarLayerDataset

    output = ROOT / OUTPUT_REL
    built = build_dataset()

    if args.check:
        if not output.exists():
            print(f"stale: {OUTPUT_REL} does not exist - run `python scripts/build_kg.py`", file=sys.stderr)
            return 1
        committed = StarLayerDataset()
        committed.parse(str(output), format="trig12")
        problems = same_dataset(built, committed)
        if problems:
            print(f"stale: {OUTPUT_REL} - run `python scripts/build_kg.py`\n  " + "\n  ".join(problems[:10]), file=sys.stderr)
            return 1
        print("starlayer-kg.trig is current")
        return 0

    built.serialize(destination=str(output), format="trig12")
    graphs = [g for g in built.contexts() if len(g)]
    print(f"wrote {OUTPUT_REL} ({sum(len(g) for g in graphs):,} triples in {len(graphs)} named graphs, {output.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
