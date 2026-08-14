"""W3C SPARQL 1.2 Test Suite download script.

Downloads manifest.ttl and every file it references (queries, data, expected
results) for a fixed set of manifest categories from the official test suite
at https://github.com/w3c/rdf-tests/tree/main/sparql/sparql12 — a real,
separate test suite from starlayergraph's own tests/w3c_turtle12/ (Turtle-1.2-only, a
different repo path). Mirrors that script's overall shape (fetch-then-cache,
skip files already on disk, write a local manifest for the test harness to
read) but parses manifest.ttl as real Turtle via rdflib, not regex — the
SPARQL 1.2 manifests nest mf:action as a blank node with qt:query/qt:data
(or ut:request for updates), which a line-oriented regex scan can't recover
reliably.

Categories fetched (see this suite's own index at
https://w3c.github.io/rdf-tests/sparql/sparql12/ for the full list of 10 -
these four are the ones starsparql currently has translation support
for; the rest are deliberately not fetched yet, see CLAUDE.md's "Not
started" section):
  - syntax-triple-terms-positive / -negative: PositiveSyntaxTest/
    NegativeSyntaxTest(/Update variants) - parse-only checks.
  - eval-triple-terms: QueryEvaluationTest/UpdateEvaluationTest - full
    execution checks (Update ones are fetched for completeness but this
    project can't run them yet - no Update serialization, see CLAUDE.md).
  - expression: QueryEvaluationTest for isTRIPLE/SUBJECT/PREDICATE/OBJECT.

Safe to re-run any time - skips files already present on disk.
"""

from __future__ import annotations

import os

import requests
from rdflib import Graph
from rdflib.namespace import RDF, Namespace

MF = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#")
QT = Namespace("http://www.w3.org/2001/sw/DataAccess/tests/test-query#")
UT = Namespace("http://www.w3.org/2009/sparql/tests/test-update#")

BASE_URL = "https://raw.githubusercontent.com/w3c/rdf-tests/main/sparql/sparql12"
MANIFEST_PUBLIC_BASE = "https://w3c.github.io/rdf-tests/sparql/sparql12"

CATEGORIES = [
    "syntax-triple-terms-positive",
    "syntax-triple-terms-negative",
    "eval-triple-terms",
    "expression",
]

DEST_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INDEX_FILE = os.path.join(DEST_ROOT, "index.tsv")


def _download(url: str, dest: str) -> None:
    if os.path.exists(dest):
        return
    r = requests.get(url, timeout=30)
    if r.status_code == 200:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(r.content)
        print(f"  downloaded {url}")
    else:
        print(f"  FAILED ({r.status_code}) {url}")


def _local_filename(iri: str) -> str:
    """The manifest references files by IRI relative to the category's own
    base URL - just the trailing path segment is the local filename."""
    return iri.rsplit("/", 1)[-1]


def fetch_category(category: str) -> list[dict]:
    """Download this category's manifest.ttl + every file it references,
    return a list of test-entry dicts for the combined index."""
    cat_dir = os.path.join(DEST_ROOT, category)
    os.makedirs(cat_dir, exist_ok=True)

    manifest_url = f"{BASE_URL}/{category}/manifest.ttl"
    print(f"Fetching manifest: {manifest_url}")
    r = requests.get(manifest_url, timeout=30)
    r.raise_for_status()
    manifest_path = os.path.join(cat_dir, "manifest.ttl")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(r.text)

    g = Graph()
    g.parse(
        data=r.text,
        format="turtle",
        publicID=f"{MANIFEST_PUBLIC_BASE}/{category}/manifest#",
    )

    entries = []
    seen_types = {
        MF.QueryEvaluationTest,
        MF.UpdateEvaluationTest,
        MF.PositiveSyntaxTest,
        MF.NegativeSyntaxTest,
        MF.PositiveUpdateSyntaxTest,
        MF.NegativeUpdateSyntaxTest,
    }
    for test_type in seen_types:
        for test_iri in g.subjects(RDF.type, test_type):
            name = str(g.value(test_iri, MF.name) or "")
            action = g.value(test_iri, MF.action)
            query_iri = update_iri = data_iri = result_iri = None
            if action is not None:
                # mf:action is either a bare IRI (syntax tests: the query/
                # update file directly) or a blank node with qt:query/
                # qt:data or ut:request (eval tests).
                query_iri = g.value(action, QT.query)
                data_iri = g.value(action, QT.data)
                update_iri = g.value(action, UT.request)
                if query_iri is None and update_iri is None:
                    query_iri = action  # bare-IRI syntax-test form
            result_iri = g.value(test_iri, MF.result)
            if result_iri is not None and not str(result_iri).startswith("http"):
                # UpdateEvaluationTest's mf:result is a blank node (the
                # expected post-update dataset state), not a plain file
                # IRI - ut:data points at the actual TriG/etc. file.
                # Confirmed empirically: a bare mf:result file IRI (as
                # QueryEvaluationTest uses) always starts with "http" here,
                # since this suite publishes absolute IRIs throughout.
                result_iri = g.value(result_iri, UT.data)

            entry = {
                "category": category,
                "test_iri": str(test_iri),
                "test_type": str(test_type).rsplit("#", 1)[-1],
                "name": name,
                "query_file": _local_filename(str(query_iri)) if query_iri else "",
                "update_file": _local_filename(str(update_iri)) if update_iri else "",
                "data_file": _local_filename(str(data_iri)) if data_iri else "",
                "result_file": _local_filename(str(result_iri)) if result_iri else "",
            }
            entries.append(entry)

            for iri in (query_iri, update_iri, data_iri, result_iri):
                if iri is not None:
                    fname = _local_filename(str(iri))
                    _download(f"{BASE_URL}/{category}/{fname}", os.path.join(cat_dir, fname))

    print(f"  {len(entries)} test entries in {category}")
    return entries


def main() -> None:
    os.makedirs(DEST_ROOT, exist_ok=True)
    all_entries = []
    for category in CATEGORIES:
        all_entries.extend(fetch_category(category))

    fields = [
        "category",
        "test_type",
        "name",
        "query_file",
        "update_file",
        "data_file",
        "result_file",
        "test_iri",
    ]
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write("\t".join(fields) + "\n")
        for entry in all_entries:
            f.write("\t".join(entry[k] for k in fields) + "\n")

    print(f"\nTotal: {len(all_entries)} test entries across {len(CATEGORIES)} categories.")
    print(f"Index written to {INDEX_FILE}")


if __name__ == "__main__":
    main()
