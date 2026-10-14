"""scripts/publish_starontology_files.py - regenerates the real, standalone
per-entry Turtle files under packages/starlayer/starlayer/starontology/,
derived from the one real source of truth, starontology.trig.

Why this exists: starontology.get_resource_iri(name)/get_raw_url(name)
mint a GitHub blob/raw URL for each registered ontology/shapes entry at
exactly the path this script writes to. Those URLs are only real,
fetchable links if a real file actually exists there in the repo -
starontology.trig alone (one dataset, many named graphs) doesn't make
that true by itself. This script is the bridge: run it, commit the
output, and every get_raw_url(name) becomes a genuinely fetchable
raw.githubusercontent.com URL.

This is a periodic, manual publish step (like scripts/build_codekg.py),
not something that runs on every commit - re-run it whenever
starontology.trig itself changes, and commit the regenerated files in the
same change. Nothing about how the library reads ontology/shapes data at
runtime changes - get_ontology_graph()/_load() still read starontology.trig
directly; these files exist purely for external fetchability.

Run:
    python scripts/publish_starontology_files.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGES_STARLAYER = Path(__file__).resolve().parents[1] / "packages" / "starlayer"
if str(_PACKAGES_STARLAYER) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_STARLAYER))

from rdflib.compare import to_isomorphic  # noqa: E402

from starlayer import starontology  # noqa: E402
from starlayer.graph import StarLayerGraph  # noqa: E402

_STARONTOLOGY_DIR = _PACKAGES_STARLAYER / "starlayer" / "starontology"


def _entries() -> list[tuple[str, str]]:
    """(name, filename) for every entry this script publishes - the 13
    registered ontology/shapes files (via get_ontology_list(), not the
    private registry dict directly - the public surface is enough) plus
    the one further profiles-mapping document, which isn't part of that
    list at all (get_conformance_profiles() is its own accessor)."""
    names = [info.name for info in starontology.get_ontology_list()]
    entries = [(name, starontology.get_resource_iri(name).split("/")[-1]) for name in names]
    entries.append(("ontology_shapes_profiles", "ontology-shapes-profiles.ttl"))
    return entries


def _graph_for(name: str):
    if name == "ontology_shapes_profiles":
        return starontology.get_conformance_profiles()
    return starontology.get_ontology_graph(name)


def publish() -> None:
    entries = _entries()
    failures = []
    for name, filename in entries:
        source_graph = _graph_for(name)
        path = _STARONTOLOGY_DIR / filename
        path.write_text(source_graph.serialize(format="turtle12"), encoding="utf-8")

        check = StarLayerGraph()
        check.parse(str(path), format="turtle12")
        if to_isomorphic(check) != to_isomorphic(source_graph):
            failures.append(name)
            print(f"FAIL  {name:28} -> {filename} (not isomorphic to the source named graph)")
        else:
            print(f"OK    {name:28} -> {filename} ({len(source_graph)} triples)")

    print()
    if failures:
        print(f"{len(failures)}/{len(entries)} entries failed isomorphism verification: {failures}")
        sys.exit(1)
    print(f"All {len(entries)} entries published and verified isomorphic.")


if __name__ == "__main__":
    publish()
