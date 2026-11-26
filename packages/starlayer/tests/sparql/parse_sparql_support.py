"""Helpers shared by the parse_sparql tests: corpus collection."""

from __future__ import annotations

from tests.sparql.w3c_sparql12.harness import load_index


def w3c_entries(*types: str):
    return [e for e in load_index() if e.test_type in types]


def entry_key(entry) -> str:
    return entry.category + "/" + entry.test_iri.rsplit("#", 1)[-1]


# ---------------------------------------------------------------------------
# The vendored W3C SPARQL 1.1 suite (tests/sparql/w3c_sparql11/data)
# ---------------------------------------------------------------------------

import csv  # noqa: E402
import os  # noqa: E402
from dataclasses import dataclass  # noqa: E402

DATA_DIR_11 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "w3c_sparql11", "data")


@dataclass
class Entry11:
    category: str
    test_type: str
    name: str
    query_file: str
    update_file: str
    data_file: str
    result_file: str
    test_iri: str

    @property
    def file(self) -> str:
        return self.query_file or self.update_file

    def read(self, filename: str | None = None) -> str:
        with open(os.path.join(DATA_DIR_11, self.category, filename or self.file), encoding="utf-8") as f:
            return f.read()

    @property
    def key(self) -> str:
        return "11/" + self.category + "/" + self.test_iri.rsplit("#", 1)[-1]


def w3c11_entries(*types: str, ext: str | None = None) -> list[Entry11]:
    """The 1.1 index entries of the given types whose request file has the extension ``ext`` (``.rq``/``.ru``)."""
    index = os.path.join(DATA_DIR_11, "index.tsv")
    if not os.path.exists(index):
        return []
    with open(index, encoding="utf-8", newline="") as f:
        rows = [Entry11(**r) for r in csv.DictReader(f, delimiter="\t")]
    return [e for e in rows if e.test_type in types and (ext is None or e.file.endswith(ext))]
