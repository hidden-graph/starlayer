#!/usr/bin/env python3
"""scripts/spec_drift.py - what has moved upstream since we last looked?

The specs this project follows (RDF 1.2, SPARQL 1.2, SHACL 1.2) are Working Drafts that change every week, and nothing else
watches them. This script reports three kinds of drift, from our own records:

1. **Specs.** The publication date of each tracked W3C document now, against the date recorded in ``docs/working/spec-dates.json`` (the
   date of the draft at our last review), and against the date of the vendored copy of it (a snapshot, or a grammar table).
2. **Test-suite pins.** Each vendored W3C suite is pinned to a commit (``PINNED_SHA`` in its download script). The commits and the files
   in the vendored subtrees that changed upstream since the pin.
3. **Vendored vocabularies.** ``scripts/assets/vendor/w3c-*.ttl`` against the upstream file.

It changes nothing but ``--record``. After you have *read* what moved and dealt with it, ``--record`` writes the current dates to
``spec-dates.json``, so that the next run reports only what moved after that.

    python scripts/spec_drift.py                 # the report; exit 0 current, 1 something moved, 2 a check could not be made
    python scripts/spec_drift.py --offline       # only our own records: a vendored copy older than the last review
    python scripts/spec_drift.py --commits       # also list the upstream commits that touched the vendored subtrees
    python scripts/spec_drift.py --json          # the same, machine-readable
    python scripts/spec_drift.py --record        # after a review: record today's dates (or name specs: --record shacl12-ui)

GitHub's unauthenticated API allows 60 requests an hour; set ``GITHUB_TOKEN`` for more. A full run makes about 25 requests.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "packages" / "starlayer"
DATES_FILE = ROOT / "docs" / "working" / "spec-dates.json"
SNAPSHOTS = PACKAGE / "tests" / "graph" / "vendor" / "spec_snapshots"
VENDOR = ROOT / "scripts" / "assets" / "vendor"

#: slug of https://www.w3.org/TR/<slug>/ -> (title, the vendored copy of it, if any: ("snapshot", file) or ("json", file))
SPECS: dict[str, tuple[str, tuple[str, Path] | None]] = {
    "rdf12-concepts": ("RDF 1.2 Concepts", ("snapshot", SNAPSHOTS / "rdf12-concepts.txt")),
    "rdf12-schema": ("RDF 1.2 Schema", ("snapshot", SNAPSHOTS / "rdf12-schema.txt")),
    "rdf12-semantics": ("RDF 1.2 Semantics", None),
    "rdf12-turtle": ("RDF 1.2 Turtle", ("snapshot", SNAPSHOTS / "rdf12-turtle.txt")),
    "rdf12-n-triples": ("RDF 1.2 N-Triples", ("snapshot", SNAPSHOTS / "rdf12-n-triples.txt")),
    "rdf12-n-quads": ("RDF 1.2 N-Quads", ("snapshot", SNAPSHOTS / "rdf12-n-quads.txt")),
    "rdf12-trig": ("RDF 1.2 TriG", ("snapshot", SNAPSHOTS / "rdf12-trig.txt")),
    "rdf12-xml": ("RDF 1.2 XML Syntax", ("snapshot", SNAPSHOTS / "rdf12-xml.txt")),
    "sparql12-query": ("SPARQL 1.2 Query", ("snapshot", SNAPSHOTS / "sparql12-query.txt")),
    "sparql12-update": ("SPARQL 1.2 Update", ("snapshot", SNAPSHOTS / "sparql12-update.txt")),
    "sparql12-entailment": ("SPARQL 1.2 Entailment Regimes", None),
    "sparql12-rl": ("SPARQL 1.2 Rules (SRL)", ("json", PACKAGE / "tests" / "sparql" / "srl_conformance" / "vendor" / "sparql12-rl-productions.json")),
    "shacl12-core": ("SHACL 1.2 Core", None),
    "shacl12-sparql": ("SHACL 1.2 SPARQL Extensions", None),
    "shacl12-node-expr": ("SHACL 1.2 Node Expressions", None),
    "shacl12-inference-rules": ("SHACL 1.2 Inference Rules", None),
    "shacl12-ui": ("SHACL 1.2 UI", None),
    "shacl12-profiling": ("SHACL 1.2 Profiling", None),
}
#: the grammar table of SPARQL Query is vendored too (it is not a snapshot); its date is checked against the same live date
EXTRA_ARTIFACTS: dict[str, tuple[str, Path]] = {
    "sparql12-query": ("json", PACKAGE / "tests" / "sparql" / "parse_sparql_conformance" / "vendor" / "sparql12-query-productions.json"),
}

#: vendored suite -> (GitHub repo, branch, the scripts that carry its PINNED_SHA, the subtrees that are vendored)
PINS: dict[str, tuple[str, str, list[Path], list[str]]] = {
    "w3c/rdf-tests": (
        "w3c/rdf-tests",
        "main",
        [
            PACKAGE / "tests" / "graph" / "w3c_rdf12" / "download_w3c_rdf12_tests.py",
            PACKAGE / "tests" / "graph" / "w3c_turtle12" / "download_w3c_turtle_tests.py",
            PACKAGE / "tests" / "graph" / "w3c_sparql12" / "download_w3c_sparql12_tests.py",
            PACKAGE / "tests" / "sparql" / "w3c_sparql11" / "download_w3c_sparql11_tests.py",
            PACKAGE / "tests" / "sparql" / "w3c_sparql12" / "download_w3c_sparql12_tests.py",
        ],
        ["rdf/rdf12/", "sparql/sparql11/", "sparql/sparql12/"],
    ),
    "w3c/data-shapes": (
        "w3c/data-shapes",
        "gh-pages",
        [PACKAGE / "scripts" / "sync_w3c_shacl12_suite.py"],
        ["shacl12-test-suite/"],
    ),
}

#: vendored vocabulary -> the upstream path in w3c/data-shapes (branch gh-pages)
VOCABULARIES: dict[str, str] = {
    "w3c-shacl.ttl": "shacl12-vocabularies/shacl.ttl",
    "w3c-shacl-shacl.ttl": "shacl12-vocabularies/shacl-shacl.ttl",
    "w3c-shacl-ui.ttl": "shacl12-vocabularies/shacl-ui.ttl",
}

_MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
_DATE_IN_STATUS = re.compile(r"(\d{1,2}) ([A-Z][a-z]+) (\d{4})")


# ---------------------------------------------------------------------------------------------------------------------------------
# Pure parsing (unit-tested without a network)
# ---------------------------------------------------------------------------------------------------------------------------------


def date_in_status(text: str) -> str | None:
    """The ISO date in a status line such as ``W3C Working Draft 09 November 2026``, or ``None``."""
    m = _DATE_IN_STATUS.search(text)
    if m is None or m.group(2) not in _MONTHS:
        return None
    return datetime.date(int(m.group(3)), _MONTHS[m.group(2)], int(m.group(1))).isoformat()


def tr_date(html_head: str) -> tuple[str | None, str | None]:
    """``(ISO publication date, status)`` from the start of a W3C TR page (the ReSpec configuration carries both)."""
    subtitle = re.search(r'"generatedSubtitle":\s*"([^"]+)"', html_head)
    published = re.search(r'"publishISODate":\s*"([^"]+)"', html_head)
    status = subtitle.group(1) if subtitle else None
    if published:
        return published.group(1)[:10], status
    return (date_in_status(status) if status else None), status


def snapshot_date(text: str) -> str | None:
    """The publication date a snapshot file records (its ``Published:`` header line)."""
    m = re.search(r"^Published:\s*(\d{4}-\d{2}-\d{2})", text, re.M)
    return m.group(1) if m else None


def artifact_date(kind: str, path: Path) -> str | None:
    """The date of the draft a vendored copy was taken from, or ``None`` if the file does not say."""
    if not path.exists():
        return None
    if kind == "snapshot":
        return snapshot_date(path.read_text(encoding="utf8", errors="replace")[:2000])
    return date_in_status(json.loads(path.read_text(encoding="utf8")).get("document", ""))


def pinned_sha(path: Path) -> str | None:
    m = re.search(r'^PINNED_SHA\s*=\s*"([0-9a-f]{40})"', path.read_text(encoding="utf8"), re.M)
    return m.group(1) if m else None


def summarise_files(files: list[dict], subtrees: list[str]) -> dict[str, dict[str, int]]:
    """Per vendored subtree, how many files an upstream comparison added, modified, removed or renamed."""
    out: dict[str, dict[str, int]] = {}
    for f in files:
        names = [f.get("filename", "")] + ([f["previous_filename"]] if f.get("previous_filename") else [])
        for subtree in subtrees:
            if any(n.startswith(subtree) for n in names):
                kind = {"added": "added", "removed": "removed", "renamed": "renamed"}.get(f.get("status", ""), "modified")
                bucket = out.setdefault(subtree, {})
                bucket[kind] = bucket.get(kind, 0) + 1
    return out


# ---------------------------------------------------------------------------------------------------------------------------------
# The records
# ---------------------------------------------------------------------------------------------------------------------------------


def load_dates() -> dict:
    if DATES_FILE.exists():
        return json.loads(DATES_FILE.read_text(encoding="utf8"))
    return {"reviewed": None, "specs": {}}


def save_dates(data: dict) -> None:
    DATES_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATES_FILE.write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf8")


# ---------------------------------------------------------------------------------------------------------------------------------
# The network
# ---------------------------------------------------------------------------------------------------------------------------------


def _get(url: str, *, limit: int | None = None, accept: str | None = None) -> bytes:
    headers = {"User-Agent": "starlayer-spec-drift"}
    if accept:
        headers["Accept"] = accept
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=40) as response:  # noqa: S310 - fixed https URLs
        return response.read(limit) if limit else response.read()


def live_spec(slug: str) -> tuple[str | None, str | None]:
    head = _get(f"https://www.w3.org/TR/{slug}/", limit=120_000).decode("utf8", errors="replace")
    return tr_date(head)


def compare(repo: str, sha: str, branch: str) -> dict:
    return json.loads(_get(f"https://api.github.com/repos/{repo}/compare/{sha}...{branch}", accept="application/vnd.github+json"))


def commits_touching(repo: str, branch: str, subtree: str, since: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/commits?sha={branch}&path={subtree.rstrip('/')}&since={since}&per_page=30"
    return json.loads(_get(url, accept="application/vnd.github+json"))


# ---------------------------------------------------------------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------------------------------------------------------------


def check_specs(dates: dict, *, offline: bool) -> list[dict]:
    rows = []
    for slug, (title, artifact) in SPECS.items():
        recorded = dates.get("specs", {}).get(slug)
        artifacts = [a for a in (artifact, EXTRA_ARTIFACTS.get(slug)) if a]
        vendored = [d for d in (artifact_date(kind, path) for kind, path in artifacts) if d]
        row = {"spec": slug, "title": title, "recorded": recorded, "vendored": min(vendored) if vendored else None, "live": None, "status": "?"}
        problems = []
        if not offline:
            try:
                row["live"], row["subtitle"] = live_spec(slug)
            except Exception as exc:  # noqa: BLE001 - network, rate limit, a changed page
                row["error"] = str(exc)
        if row.get("error"):
            row["status"] = "could not check"
        else:
            if row["live"] and recorded and row["live"] > recorded:
                problems.append(f"moved since the last review ({recorded})")
            if not recorded:
                problems.append("no recorded date")
            reference = row["live"] or recorded
            if row["vendored"] and reference and row["vendored"] < reference:
                problems.append(f"vendored copy is from {row['vendored']}")
            row["status"] = "; ".join(problems) if problems else "current"
        rows.append(row)
    return rows


def check_pins(*, commits: bool) -> list[dict]:
    rows = []
    for name, (repo, branch, scripts, subtrees) in PINS.items():
        shas = {pinned_sha(p) for p in scripts}
        row: dict = {"suite": name, "pin": None, "ahead": None, "changed": {}, "status": "?"}
        if len(shas) != 1 or None in shas:
            row["status"] = f"the download scripts disagree about the pin: {sorted(str(s) for s in shas)}"
            rows.append(row)
            continue
        sha = next(iter(shas))
        row["pin"] = sha[:9]
        try:
            data = compare(repo, sha, branch)
            row["ahead"] = data.get("ahead_by")
            files = data.get("files", [])
            row["changed"] = summarise_files(files, subtrees)
            row["truncated"] = len(files) >= 300
            if commits and row["changed"]:
                since = data.get("base_commit", {}).get("commit", {}).get("committer", {}).get("date", "")
                row["commits"] = [
                    f"{c['sha'][:9]} {c['commit']['committer']['date'][:10]} {c['commit']['message'].splitlines()[0]}"
                    for subtree in subtrees
                    for c in commits_touching(repo, branch, subtree, since)
                ]
            row["status"] = "current" if not row["changed"] else f"{row['ahead']} commits ahead; the vendored subtrees changed"
            if not row["changed"] and row["ahead"]:
                row["status"] = f"current ({row['ahead']} upstream commits, none in the vendored subtrees)"
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
            row["status"] = "could not check"
        rows.append(row)
    return rows


def check_vocabularies() -> list[dict]:
    rows = []
    for name, upstream_path in VOCABULARIES.items():
        local = VENDOR / name
        row = {"file": name, "status": "?"}
        try:
            upstream = _get(f"https://raw.githubusercontent.com/w3c/data-shapes/gh-pages/{upstream_path}")
            same = local.exists() and hashlib.sha256(upstream).digest() == hashlib.sha256(local.read_bytes()).digest()
            row["status"] = "current" if same else "upstream differs from the vendored copy (see scripts/assets/vendor/VENDORED_FROM.md)"
        except Exception as exc:  # noqa: BLE001
            row["error"] = str(exc)
            row["status"] = "could not check"
        rows.append(row)
    return rows


def render(report: dict) -> str:
    lines = [f"Spec drift report (records last reviewed {report['reviewed'] or 'never'})", ""]
    lines.append("SPECS")
    for r in report["specs"]:
        lines.append(f"  {r['spec']:<25} recorded {r['recorded'] or '-':<10}  now {r['live'] or '-':<10}  vendored {r['vendored'] or '-':<10}  {r['status']}")
    if report["pins"]:
        lines += ["", "TEST SUITES"]
        for r in report["pins"]:
            lines.append(f"  {r['suite']:<18} pinned {r['pin'] or '-'}  {r['status']}")
            for subtree, counts in r["changed"].items():
                lines.append("      " + subtree.ljust(24) + ", ".join(f"{n} {k}" for k, n in sorted(counts.items())))
            if r.get("truncated"):
                lines.append("      (the comparison lists at most 300 files: there may be more)")
            for c in r.get("commits", []):
                lines.append("      " + c)
    if report["vocabularies"]:
        lines += ["", "VENDORED VOCABULARIES"]
        for r in report["vocabularies"]:
            lines.append(f"  {r['file']:<22} {r['status']}")
    errors = [r.get("error") for part in ("specs", "pins", "vocabularies") for r in report[part] if r.get("error")]
    if errors:
        lines += ["", f"{len(errors)} check(s) could not be made, for example: {errors[0]}"]
    lines += ["", "After reading what moved and dealing with it: python scripts/spec_drift.py --record"]
    return "\n".join(lines)


def drifted(report: dict) -> bool:
    return any(r["status"] not in ("current",) and not r["status"].startswith("current (") and r["status"] != "could not check"
               for part in ("specs", "pins", "vocabularies") for r in report[part])


def broken(report: dict) -> bool:
    return any(r["status"] == "could not check" for part in ("specs", "pins", "vocabularies") for r in report[part])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--offline", action="store_true", help="only our own records; no network")
    parser.add_argument("--commits", action="store_true", help="list the upstream commits that touched the vendored subtrees")
    parser.add_argument("--json", action="store_true", help="the report as JSON")
    parser.add_argument("--record", nargs="*", metavar="SPEC", help="record the current dates (all specs, or the named ones) as reviewed")
    args = parser.parse_args(argv)

    dates = load_dates()
    if args.record is not None:
        names = args.record or list(SPECS)
        unknown = [n for n in names if n not in SPECS]
        if unknown:
            print(f"unknown spec(s): {', '.join(unknown)}; the tracked ones are {', '.join(SPECS)}", file=sys.stderr)
            return 2
        for slug in names:
            try:
                live, _status = live_spec(slug)
            except Exception as exc:  # noqa: BLE001
                print(f"could not read {slug}: {exc}", file=sys.stderr)
                return 2
            if live:
                dates.setdefault("specs", {})[slug] = live
        dates["reviewed"] = datetime.date.today().isoformat()
        save_dates(dates)
        print(f"recorded {len(names)} spec date(s) in {DATES_FILE.relative_to(ROOT)}")
        return 0

    report = {
        "reviewed": dates.get("reviewed"),
        "specs": check_specs(dates, offline=args.offline),
        "pins": [] if args.offline else check_pins(commits=args.commits),
        "vocabularies": [] if args.offline else check_vocabularies(),
    }
    print(json.dumps(report, indent=1) if args.json else render(report))
    if drifted(report):
        return 1
    return 2 if broken(report) else 0


if __name__ == "__main__":
    sys.exit(main())
