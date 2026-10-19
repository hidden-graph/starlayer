"""scripts/check_notebook_links.py - compare the hand-made notebook links with the guide notebooks.

``codekg/curated/notebook-links.ttl`` links guide cells (by notebook and cell id) to the code they demonstrate, with a
hash of each cell from when a person last reviewed the link. This reports each link as unchanged, edited, moved or
broken (see ``starlayer.codekg.notebook_links``) and exits 1 unless every link is unchanged.

    python scripts/check_notebook_links.py                 # check; exit 1 and list what needs review
    python scripts/check_notebook_links.py --show NAME     # a review packet: the link, the cell's text, the symbols
    python scripts/check_notebook_links.py --restamp NAME  # record that NAME was reviewed (new hash, today's date)

Build-time only, like the other scripts here. It is run by ``python scripts/build.py`` (step ``notebooks``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _show(name: str) -> int:
    from starlayer.codekg import notebook_links as nl

    link = next((entry for entry in nl.load_links() if entry.name == name), None)
    if link is None:
        print(f"no notebook link {name!r}", file=sys.stderr)
        return 2
    finding = next(f for f in nl.check([link]))
    print(f"link:       {link.name}  [{finding.status}] {finding.detail}".rstrip())
    print(f"notebook:   {link.notebook}  (cell id {link.cell_id})")
    print(f"reviewed:   {link.reviewed_on}")
    print(f"why:        {link.why}")
    print("symbols:    " + "\n            ".join(link.identifiers))
    source = nl.cell_source(link)
    print("\ncell source now:" if source is not None else "\ncell not found")
    if source is not None:
        print("    " + source.replace("\n", "\n    "))
    print(f"\nwhat changed since the review: git log -p --since={link.reviewed_on} -- {link.notebook}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="accepted for build.py; this script only ever checks")
    parser.add_argument("--show", metavar="NAME", help="print a review packet for one link")
    parser.add_argument("--restamp", metavar="NAME", nargs="+", help="record that these links were reviewed")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "packages/starlayer"))
    from starlayer.codekg import notebook_links as nl

    if args.show:
        return _show(args.show)
    if args.restamp:
        try:
            done = nl.restamp(args.restamp)
        except (KeyError, ValueError) as error:
            print(error, file=sys.stderr)
            return 2
        print("restamped: " + ", ".join(done))
        return 0

    findings = nl.check()
    needs_review = [f for f in findings if f.status != nl.UNCHANGED]
    for f in needs_review:
        print(f"{f.status:9} {f.link.name}: {f.detail}")
    if needs_review:
        print(
            f"{len(needs_review)} of {len(findings)} notebook link(s) need review: "
            "`--show NAME`, then fix the link or `--restamp NAME`",
            file=sys.stderr,
        )
        return 1
    print(f"{len(findings)} notebook link(s) are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
