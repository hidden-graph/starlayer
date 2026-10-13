"""W3C SPARQL 1.2 Test Suite download script.

Downloads manifest.ttl and every file it references (queries, data, expected
results) for a fixed set of manifest categories from a single pinned-commit
tarball snapshot of the official test suite at
https://github.com/w3c/rdf-tests/tree/main/sparql/sparql12 - a real,
separate test suite from starlayer.graph's own tests/w3c_turtle12/
(Turtle-1.2-only, a different repo path). Mirrors
scripts/sync_w3c_shacl12_suite.py's own fetch shape (one tarball request,
pinned SHA, deliberate bump, a VENDORED_FROM.md provenance stamp) rather than
this script's own prior per-file ``requests.get()`` design, which risked
GitHub's 60-req/hour unauthenticated rate limit and left no record of what
was actually fetched.

The manifest itself is still parsed as real Turtle via rdflib, not regex -
the SPARQL 1.2 manifests nest mf:action as a blank node with qt:query/qt:data
(or ut:request for updates), which a line-oriented regex scan can't recover
reliably.

Categories fetched (see this suite's own index at
https://w3c.github.io/rdf-tests/sparql/sparql12/ for the full list of 10):
  - syntax-triple-terms-positive / -negative: PositiveSyntaxTest/
    NegativeSyntaxTest(/Update variants) - parse-only checks.
  - eval-triple-terms: QueryEvaluationTest/UpdateEvaluationTest - full
    execution checks (Update ones are fetched for completeness but this
    project can't run them yet - no Update serialization, see CLAUDE.md).
  - expression: QueryEvaluationTest for isTRIPLE/SUBJECT/PREDICATE/OBJECT.
  - lang-basedir/codepoint-escapes/grouping/rdf11/syntax/version - added
    2026-10-13 (previously the only unfetched six; see
    starlayer/graph/CLAUDE.md's dated entry for why lang-basedir in
    particular was worth adding - several real starlayer.sparql gaps were
    found and fixed through it). Several fixtures across these are
    believed, confirmed-against-plain-rdflib defects inherited from
    rdflib itself, not this project's own gap - see
    tests/sparql/w3c_sparql12/test_w3c_sparql12.py's own
    _KNOWN_SUITE_DEFECT_FRAGMENTS/_INHERITED_RDFLIB_GAP_FRAGMENTS for the
    full, individually-reasoned list.

Bumping PINNED_SHA is a deliberate, one-line, reviewable change - this
script never auto-follows ``main``'s tip. The companion Turtle 1.2 downloader
(tests/graph/w3c_turtle12/) and this script's own sibling copy
(tests/graph/w3c_sparql12/) pull from the same w3c/rdf-tests repo at their
own independently-pinned SHA; bump all affected scripts together when
investigating a specific upstream change, but there's no requirement they
share one SHA otherwise.

Always re-fetches and overwrites (the source is a pinned, immutable commit,
so there's nothing to gain from skipping files already on disk - unlike a
live, unpinned fetch, re-running this can never produce different output
until PINNED_SHA is bumped).

Usage: python download_w3c_sparql12_tests.py
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
# Bump deliberately - see this module's own docstring. Do not auto-follow
# main's tip.
PINNED_SHA = "d5d930b03ee6b63b388d0bb28fdb29ee78a59ec0"
SUBTREE_PREFIX = "sparql/sparql12/"
MANIFEST_PUBLIC_BASE = "https://w3c.github.io/rdf-tests/sparql/sparql12"

CATEGORIES = [
    "syntax-triple-terms-positive",
    "syntax-triple-terms-negative",
    "eval-triple-terms",
    "expression",
    # Added 2026-10-13 - previously left unfetched; a hand-fetched
    # investigation of lang-basedir specifically found and fixed several
    # real starlayer.sparql gaps (see starlayer/graph/CLAUDE.md's dated
    # entry), so these now get the same pinned-SHA, CI-tracked treatment
    # as the original four rather than staying a one-off manual exercise.
    "lang-basedir",
    "codepoint-escapes",
    "grouping",
    "rdf11",
    "syntax",
    "version",
]

TARBALL_URL = f"https://codeload.github.com/{REPO}/tar.gz/{PINNED_SHA}"

DEST_ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INDEX_FILE = os.path.join(DEST_ROOT, "index.tsv")
STAMP_FILE = os.path.join(DEST_ROOT, "VENDORED_FROM.md")


def _fetch_tarball_members() -> dict[str, dict[str, bytes]]:
    """{category: {relative_filename: bytes}} for each name in CATEGORIES."""
    with urllib.request.urlopen(TARBALL_URL) as resp:
        archive_bytes = resp.read()

    by_category: dict[str, dict[str, bytes]] = {name: {} for name in CATEGORIES}
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Archive root is "<repo>-<sha>/..." - strip that one path segment.
            relative = member.name.split("/", 1)[1] if "/" in member.name else member.name
            if not relative.startswith(SUBTREE_PREFIX):
                continue
            after_prefix = relative[len(SUBTREE_PREFIX) :]
            for category in CATEGORIES:
                cat_prefix = category + "/"
                if after_prefix.startswith(cat_prefix):
                    extracted = tar.extractfile(member)
                    if extracted is not None:
                        by_category[category][after_prefix[len(cat_prefix) :]] = extracted.read()
                    break
    return by_category


def _local_filename(iri: str) -> str:
    """The manifest references files by IRI relative to the category's own
    base URL - just the trailing path segment is the local filename."""
    return iri.rsplit("/", 1)[-1]


def fetch_category(category: str, files: dict[str, bytes]) -> list[dict]:
    """Write this category's manifest.ttl + every file it references from
    the already-fetched tarball contents, return a list of test-entry dicts
    for the combined index."""
    cat_dir = os.path.join(DEST_ROOT, category)
    os.makedirs(cat_dir, exist_ok=True)

    manifest_bytes = files.get("manifest.ttl")
    if manifest_bytes is None:
        raise RuntimeError(
            f"{SUBTREE_PREFIX}{category}/manifest.ttl not found in tarball at {PINNED_SHA}"
        )
    manifest_text = manifest_bytes.decode("utf-8")
    manifest_path = os.path.join(cat_dir, "manifest.ttl")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(manifest_text)

    g = Graph()
    g.parse(
        data=manifest_text,
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
            raise RuntimeError(
                f"no files found under {SUBTREE_PREFIX}{category}/ at {PINNED_SHA} - "
                "did the subtree move or the SHA get mistyped?"
            )

    all_entries = []
    for category in CATEGORIES:
        all_entries.extend(fetch_category(category, by_category[category]))

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

    stamp = (
        "# Vendored snapshot provenance\n\n"
        "Do not hand-edit files in this directory - regenerate with "
        "`python download_w3c_sparql12_tests.py` after bumping `PINNED_SHA` "
        "there.\n\n"
        f"- Source: https://github.com/{REPO}/tree/{PINNED_SHA}/{SUBTREE_PREFIX}\n"
        f"- Pinned commit SHA: `{PINNED_SHA}`\n"
        f"- Synced: {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}\n"
        f"- Categories: {', '.join(CATEGORIES)}\n"
        f"- Test entries: {len(all_entries)}\n"
    )
    with open(STAMP_FILE, "w", encoding="utf-8") as f:
        f.write(stamp)

    print(f"\nTotal: {len(all_entries)} test entries across {len(CATEGORIES)} categories.")
    print(f"Index written to {INDEX_FILE}")
    print(f"Pinned SHA: {PINNED_SHA}")


if __name__ == "__main__":
    main()
