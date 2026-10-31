"""W3C SPARQL 1.1 syntax and query test download script.

Sibling of ``../w3c_sparql12/download_w3c_sparql12_tests.py`` and fetched the same way: one tarball request for a
pinned commit of https://github.com/w3c/rdf-tests (``sparql/sparql11/``), every manifest parsed as real Turtle,
a ``VENDORED_FROM.md`` provenance stamp, and an ``index.tsv`` with the same columns as the 1.2 index.

What is kept: the manifest of each category plus only the *query / update request* file of every test of these
types (the parser is a text-to-tree component; data and result files are not needed and are not vendored):

  PositiveSyntaxTest11 / NegativeSyntaxTest11 / PositiveUpdateSyntaxTest11 / NegativeUpdateSyntaxTest11
  QueryEvaluationTest / UpdateEvaluationTest   (their queries are extra positive-syntax material)

The ``11`` suffix is dropped in ``index.tsv`` so the types read like the 1.2 index (PositiveSyntaxTest, ...).
Categories without syntax-relevant tests (protocol, graph-store-protocol, http-rdf-update, json-res,
service-description, entailment) are not fetched.

Usage: python download_w3c_sparql11_tests.py   (bump PINNED_SHA deliberately; it never follows ``main``)
"""

from __future__ import annotations

import datetime
import io
import os
import tarfile
import urllib.request

from rdflib import Graph
from rdflib.namespace import RDF, Namespace

MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
QT = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-query#")
UT = Namespace("http://www.w3.org/2009/sparql/tests/test-update#")

REPO = "w3c/rdf-tests"
# The same commit as the SPARQL 1.2 suite, so both vendored suites describe one snapshot of the repository.
PINNED_SHA = "d5d930b03ee6b63b388d0bb28fdb29ee78a59ec0"
SUBTREE_PREFIX = "sparql/sparql11/"
MANIFEST_PUBLIC_BASE = "http://www.w3.org/2009/sparql/docs/tests/data-sparql11"

CATEGORIES = [
    "syntax-query",
    "syntax-update-1",
    "syntax-update-2",
    "syntax-fed",
    "aggregates",
    "bind",
    "bindings",
    "cast",
    "construct",
    "exists",
    "functions",
    "grouping",
    "negation",
    "project-expression",
    "property-path",
    "service",
    "subquery",
    "add",
    "basic-update",
    "clear",
    "copy",
    "delete",
    "delete-data",
    "delete-insert",
    "delete-where",
    "drop",
    "move",
    "update-silent",
]

TEST_TYPES = [
    "PositiveSyntaxTest11",
    "NegativeSyntaxTest11",
    "PositiveUpdateSyntaxTest11",
    "NegativeUpdateSyntaxTest11",
    "QueryEvaluationTest",
    "UpdateEvaluationTest",
]

TARBALL_URL = f"https://codeload.github.com/{REPO}/tar.gz/{PINNED_SHA}"

DEST_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INDEX_FILE = os.path.join(DEST_ROOT, "index.tsv")
STAMP_FILE = os.path.join(DEST_ROOT, "VENDORED_FROM.md")


def _fetch_tarball_members() -> dict[str, dict[str, bytes]]:
    with urllib.request.urlopen(TARBALL_URL) as resp:
        archive_bytes = resp.read()
    by_category: dict[str, dict[str, bytes]] = {name: {} for name in CATEGORIES}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            relative = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if not relative.startswith(SUBTREE_PREFIX):
                continue
            after_prefix = relative[len(SUBTREE_PREFIX) :]
            category, _, rest = after_prefix.partition("/")
            if category in by_category and rest and "/" not in rest:
                extracted = tar.extractfile(member)
                if extracted is not None:
                    by_category[category][rest] = extracted.read()
    return by_category


def _local_filename(iri: str) -> str:
    return iri.rsplit("/", 1)[-1]


def fetch_category(category: str, files: dict[str, bytes]) -> list[dict]:
    cat_dir = os.path.join(DEST_ROOT, category)
    os.makedirs(cat_dir, exist_ok=True)
    manifest_bytes = files.get("manifest.ttl")
    if manifest_bytes is None:
        raise RuntimeError(f"{SUBTREE_PREFIX}{category}/manifest.ttl not found in tarball at {PINNED_SHA}")
    manifest_text = manifest_bytes.decode("utf-8")
    with open(os.path.join(cat_dir, "manifest.ttl"), "w", encoding="utf-8") as f:
        f.write(manifest_text)

    g = Graph()
    g.parse(data=manifest_text, format="turtle", publicID=f"{MANIFEST_PUBLIC_BASE}/{category}/manifest#")

    entries = []
    for type_name in TEST_TYPES:
        for test_iri in sorted(g.subjects(RDF.type, MF[type_name])):
            name = str(g.value(test_iri, MF.name) or "")
            action = g.value(test_iri, MF.action)
            query_iri = update_iri = None
            if action is not None:
                query_iri = g.value(action, QT.query)
                update_iri = g.value(action, UT.request)
                if query_iri is None and update_iri is None:
                    query_iri = action  # bare-IRI syntax-test form
            is_update = "Update" in type_name
            if is_update and update_iri is None:
                update_iri, query_iri = query_iri, None
            entry = {
                "category": category,
                "test_type": type_name.removesuffix("11"),
                "name": name,
                "query_file": _local_filename(str(query_iri)) if query_iri else "",
                "update_file": _local_filename(str(update_iri)) if update_iri else "",
                "data_file": "",
                "result_file": "",
                "test_iri": str(test_iri),
            }
            entries.append(entry)
            for iri in (query_iri, update_iri):
                if iri is None:
                    continue
                fname = _local_filename(str(iri))
                content = files.get(fname)
                if content is None:
                    print(f"  MISSING in tarball: {category}/{fname} (test {name})")
                    continue
                with open(os.path.join(cat_dir, fname), "wb") as f:
                    f.write(content)
    print(f"  {len(entries)} test entries in {category}")
    return entries


def main() -> None:
    os.makedirs(DEST_ROOT, exist_ok=True)
    by_category = _fetch_tarball_members()
    for category, files in by_category.items():
        if not files:
            raise RuntimeError(f"no files found under {SUBTREE_PREFIX}{category}/ at {PINNED_SHA}")
    all_entries: list[dict] = []
    for category in CATEGORIES:
        all_entries.extend(fetch_category(category, by_category[category]))

    fields = ["category", "test_type", "name", "query_file", "update_file", "data_file", "result_file", "test_iri"]
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write("\t".join(fields) + "\n")
        for entry in all_entries:
            f.write("\t".join(entry[k] for k in fields) + "\n")

    stamp = (
        "# Vendored snapshot provenance\n\n"
        "Do not hand-edit files in this directory - regenerate with "
        "`python download_w3c_sparql11_tests.py` after bumping `PINNED_SHA` there.\n\n"
        f"- Source: https://github.com/{REPO}/tree/{PINNED_SHA}/{SUBTREE_PREFIX}\n"
        f"- Pinned commit SHA: `{PINNED_SHA}` (the same commit as the SPARQL 1.2 suite)\n"
        f"- Synced: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"- Categories: {', '.join(CATEGORIES)}\n"
        "- Kept per test: the query or update request file only (no data or result files)\n"
        f"- Test entries: {len(all_entries)}\n"
    )
    with open(STAMP_FILE, "w", encoding="utf-8") as f:
        f.write(stamp)
    print(f"\nTotal: {len(all_entries)} test entries across {len(CATEGORIES)} categories. Pinned SHA: {PINNED_SHA}")


if __name__ == "__main__":
    main()
