"""codekg.notebook_links - hand-made links from guide notebook cells to the code they demonstrate.

``curated/notebook-links.ttl`` holds one ``slkg:NotebookExample`` per link: the notebook, the cell's ``id``, the
dotted identifiers of the symbols it demonstrates, a sentence on why, and a hash of the cell's source taken when a
person last reviewed the link. The cell id is the reference (it survives moving the cell); the hash says whether the
cell has changed since the review. This module reads the links and compares them with the notebooks.

A link is one of:

- ``unchanged``: the cell is where the link says and its hash matches.
- ``edited``: the cell is there but its hash differs. Whether it still demonstrates the symbol is a judgement
  (``.claude/skills/review-notebook-links``); ``restamp`` records a review.
- ``moved``: the cell id is gone from the notebook but a cell with the same hash is elsewhere: fix the path.
- ``broken``: the cell is gone, or no longer mentions a symbol the link names.

Repo tooling like the rest of ``codekg``: not part of the installed wheel.
Run ``python scripts/check_notebook_links.py --help``.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from rdflib import RDF, RDFS, Graph, Namespace

from . import CODEKG_NS, CURATED_DIR

LINKS_TTL = CURATED_DIR / "notebook-links.ttl"
REPO_ROOT = Path(__file__).resolve().parents[3]
GUIDES = REPO_ROOT / "docs" / "guides"

NL_NS = Namespace("https://github.com/hidden-graph/starlayer/ns/codekg/curated/notebook-links#")

UNCHANGED, EDITED, MOVED, BROKEN = "unchanged", "edited", "moved", "broken"


@dataclass(frozen=True)
class Link:
    """One reviewed link from a notebook cell to the symbols it demonstrates."""

    name: str
    notebook: str  # path relative to the repository root
    cell_id: str
    cell_hash: str
    reviewed_on: str
    why: str
    identifiers: tuple[str, ...]


@dataclass(frozen=True)
class Finding:
    """What checking one link found."""

    link: Link
    status: str
    detail: str = ""


def normalize(source: str) -> str:
    """A cell's source with trailing whitespace and surrounding blank lines removed, so a re-save does not count as an edit."""
    return "\n".join(line.rstrip() for line in source.strip().splitlines())


def cell_hash(source: str) -> str:
    """The first 16 hex digits of the SHA-256 of the normalized source."""
    return hashlib.sha256(normalize(source).encode("utf-8")).hexdigest()[:16]


def load_links(path: Path = LINKS_TTL) -> list[Link]:
    graph = Graph().parse(path, format="turtle")
    links = []
    for node in graph.subjects(RDF.type, CODEKG_NS.NotebookExample):
        links.append(
            Link(
                name=str(node).rsplit("#", 1)[-1],
                notebook=str(graph.value(node, CODEKG_NS.notebookPath)),
                cell_id=str(graph.value(node, CODEKG_NS.cellId)),
                cell_hash=str(graph.value(node, CODEKG_NS.cellHash)),
                reviewed_on=str(graph.value(node, CODEKG_NS.reviewedOn)),
                why=str(graph.value(node, RDFS.comment)),
                identifiers=tuple(sorted(str(o) for o in graph.objects(node, CODEKG_NS.demonstratesIdentifier))),
            )
        )
    return sorted(links, key=lambda link: link.name)


def _read_cells(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")).get("cells", [])


def cell_source(link: Link, root: Path = REPO_ROOT) -> str | None:
    """The current source of the linked cell, or ``None`` if the notebook or the cell is gone."""
    path = root / link.notebook
    if not path.exists():
        return None
    for cell in _read_cells(path):
        if cell.get("id") == link.cell_id:
            return "".join(cell["source"])
    return None


def _short_name(identifier: str) -> str:
    """The last component of a dotted identifier; for a package (``x.y.__init__``) the package's own name."""
    parts = identifier.split(".")
    return parts[-2] if parts[-1] == "__init__" and len(parts) > 1 else parts[-1]


def missing_mentions(link: Link, source: str) -> list[str]:
    """Identifiers whose short name no longer appears (as a whole word) in the cell: the cell cannot demonstrate them."""
    return [i for i in link.identifiers if not re.search(rf"\b{re.escape(_short_name(i))}\b", source)]


def _find_by_hash(wanted: str, root: Path) -> str | None:
    for path in sorted((root / "docs" / "guides").glob("*.ipynb")):
        for cell in _read_cells(path):
            if cell_hash("".join(cell["source"])) == wanted:
                return f"{path.relative_to(root)}#{cell['id']}"
    return None


def check(links: list[Link] | None = None, root: Path = REPO_ROOT) -> list[Finding]:
    """Compare every link with the notebooks; see the module docstring for the four outcomes."""
    findings = []
    for link in load_links() if links is None else links:
        source = cell_source(link, root)
        if source is None:
            elsewhere = _find_by_hash(link.cell_hash, root)
            if elsewhere:
                findings.append(Finding(link, MOVED, f"the cell is now at {elsewhere}; update notebookPath and cellId"))
            else:
                findings.append(Finding(link, BROKEN, f"cell {link.cell_id} is not in {link.notebook}"))
            continue
        gone = missing_mentions(link, source)
        if gone:
            findings.append(Finding(link, BROKEN, f"the cell no longer mentions {', '.join(gone)}"))
        elif cell_hash(source) != link.cell_hash:
            findings.append(Finding(link, EDITED, f"cell {link.cell_id} changed since {link.reviewed_on}"))
        else:
            findings.append(Finding(link, UNCHANGED))
    return findings


def restamp(names: list[str], today: date | None = None, root: Path = REPO_ROOT, path: Path = LINKS_TTL) -> list[str]:
    """Record that a person reviewed these links: set each one's hash to the cell's current hash and its date to today.

    Edits only those two values in the Turtle file, so the rest of the hand-edited file is untouched. Returns the
    names restamped. Raises ``KeyError`` for an unknown link and ``ValueError`` for one whose cell cannot be found.
    """
    stamp = (today or date.today()).isoformat()
    links = {link.name: link for link in load_links(path)}
    text = path.read_text(encoding="utf-8")
    for name in names:
        if name not in links:
            raise KeyError(f"no notebook link {name!r}")
        source = cell_source(links[name], root)
        if source is None:
            raise ValueError(f"{name}: the cell is not in {links[name].notebook}; fix the link before restamping")
        block = re.search(rf"^nl:{re.escape(name)} a .*?(?:\n\n|\Z)", text, re.S | re.M)
        if block is None:
            raise ValueError(f"{name}: could not find the link's block in {path.name}")
        new = re.sub(r'(slkg:cellHash )"[0-9a-f]+"', rf'\1"{cell_hash(source)}"', block.group(0))
        new = re.sub(r'(slkg:reviewedOn )"[0-9-]+"\^\^xsd:date', rf'\1"{stamp}"^^xsd:date', new)
        text = text.replace(block.group(0), new, 1)
    path.write_text(text, encoding="utf-8")
    return list(names)
