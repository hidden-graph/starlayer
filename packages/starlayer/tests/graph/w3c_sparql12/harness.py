"""Shared helpers for this repo's own W3C SPARQL 1.2 test-suite harness - see ``test_w3c_sparql12_eval.py`` for the pytest
test functions and ``download_w3c_sparql12_tests.py`` for how ``data/`` gets populated.

Terms are pyoxigraph terms, the type ``OxGraph.query()`` returns, so expected and actual results compare directly.
``parse_srj`` is a small SPARQL JSON Results reader that understands the RDF 1.2 ``"type": "triple"`` term and the
``its:dir`` direction key.

Oxigraph keeps literals in canonical lexical form (``"123.0"^^xsd:decimal`` is ``"123"``; owner decision O1), so both sides are
rewritten through a store before they are compared: the W3C expected value is compared as the store would hold it.
"""

from __future__ import annotations

import csv
import functools
import itertools
import json
import os
from dataclasses import dataclass

import pyoxigraph as ox

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
INDEX_FILE = os.path.join(DATA_DIR, "index.tsv")


@dataclass
class TestEntry:
    category: str
    test_type: str
    name: str
    query_file: str
    update_file: str
    data_file: str
    result_file: str
    test_iri: str

    def path(self, filename: str) -> str:
        return os.path.join(DATA_DIR, self.category, filename)

    def read(self, filename: str) -> str:
        with open(self.path(filename), encoding="utf-8") as f:
            return f.read()


def load_index() -> list[TestEntry]:
    if not os.path.exists(INDEX_FILE):
        return []
    with open(INDEX_FILE, encoding="utf-8", newline="") as f:
        return [TestEntry(**row) for row in csv.DictReader(f, delimiter="\t")]


_DATA_FORMAT_BY_SUFFIX = {
    ".ttl": "turtle12",
    ".trig": "trig12",
    ".nq": "nq12",
    ".nt": "nt12",
}


def data_format(entry: TestEntry) -> str:
    """The ``format=`` for ``parse()`` of ``entry.data_file``, keyed off its extension (TriG's ``GRAPH { }`` blocks are not
    valid Turtle, so the syntax has to match)."""
    for suffix, fmt in _DATA_FORMAT_BY_SUFFIX.items():
        if entry.data_file.endswith(suffix):
            return fmt
    raise ValueError(f"no known RDF-1.2 format for data file {entry.data_file!r}")


_DIRECTIONS = {"ltr": ox.BaseDirection.LTR, "rtl": ox.BaseDirection.RTL}


def _parse_json_term(term: dict):
    kind = term["type"]
    if kind == "uri":
        return ox.NamedNode(term["value"])
    if kind == "bnode":
        return ox.BlankNode(term["value"])
    if kind == "literal":
        lang = term.get("xml:lang") or term.get("lang")
        direction = term.get("its:dir")
        if lang and direction:
            return ox.Literal(term["value"], language=lang, direction=_DIRECTIONS[direction])
        if lang:
            return ox.Literal(term["value"], language=lang)
        if term.get("datatype"):
            return ox.Literal(term["value"], datatype=ox.NamedNode(term["datatype"]))
        return ox.Literal(term["value"])
    if kind == "triple":
        v = term["value"]
        return ox.Triple(_parse_json_term(v["subject"]), _parse_json_term(v["predicate"]), _parse_json_term(v["object"]))
    raise NotImplementedError(f"w3c_sparql12 harness: unhandled SPARQL JSON term type {kind!r}")


def parse_srj(text: str) -> list[dict]:
    """Parse SPARQL JSON Results into a list of binding dicts (variable name -> pyoxigraph term)."""
    doc = json.loads(text)
    bindings = doc.get("results", {}).get("bindings", [])
    return [{var: _parse_json_term(term) for var, term in row.items()} for row in bindings]


_S, _P = ox.NamedNode("urn:harness:s"), ox.NamedNode("urn:harness:p")


@functools.cache
def _store_form(lit: ox.Literal) -> ox.Literal:
    """The literal as a store holds it (canonical lexical form)."""
    store = ox.Store()
    store.add(ox.Quad(_S, _P, lit, ox.DefaultGraph()))
    return next(iter(store)).object


def _canon_term(v) -> str:
    """A comparable string for one term (a triple term's components recursively)."""
    if v is None:
        return "UNDEF"
    if isinstance(v, ox.Triple):
        return f"<<( {_canon_term(v.subject)} {_canon_term(v.predicate)} {_canon_term(v.object)} )>>"
    if isinstance(v, ox.Literal):
        return str(_store_form(v))
    return str(v)


def _opaque_key(v) -> str | None:
    """A blank node's label: the exact label a store mints is never meaningful, only a consistent relabelling is."""
    if isinstance(v, ox.BlankNode):
        return v.value
    return None


def _canon_term_bmap(v, bmap: dict) -> str:
    """Like ``_canon_term``, but every blank node label (also inside a triple term) goes through ``bmap`` first."""
    if v is None:
        return "UNDEF"
    if isinstance(v, ox.Triple):
        return (
            f"<<( {_canon_term_bmap(v.subject, bmap)} "
            f"{_canon_term_bmap(v.predicate, bmap)} "
            f"{_canon_term_bmap(v.object, bmap)} )>>"
        )
    key = _opaque_key(v)
    if key is not None:
        return f"_:OPAQUE_{bmap.get(key, key)}"
    return _canon_term(v)


def canon_bindings(bindings: list[dict]) -> list[frozenset]:
    """A row-order-independent comparable form (blank node labels are part of it: use ``bindings_match`` when either side
    may contain one)."""
    rows = [frozenset((str(k), _canon_term(v)) for k, v in b.items()) for b in bindings]
    return sorted(rows, key=lambda r: sorted(r))


def _collect_opaque_keys(bindings: list[dict]) -> set[str]:
    keys: set[str] = set()

    def _walk(v) -> None:
        if isinstance(v, ox.Triple):
            _walk(v.subject)
            _walk(v.predicate)
            _walk(v.object)
        else:
            key = _opaque_key(v)
            if key is not None:
                keys.add(key)

    for row in bindings:
        for v in row.values():
            _walk(v)
    return keys


def _canon_bindings_bmap(bindings: list[dict], bmap: dict) -> list[frozenset]:
    rows = [frozenset((str(k), _canon_term_bmap(v, bmap)) for k, v in row.items()) for row in bindings]
    return sorted(rows, key=lambda r: sorted(r))


class _AllKeysToWildcard(dict):
    """A ``bmap`` that renders every blank node label through one placeholder (a renaming-invariant signature)."""

    def get(self, key, default=None):
        return "*"


_WILDCARD_BMAP = _AllKeysToWildcard()


def _row_contains_key(row: dict, key: str) -> bool:
    def _walk(v) -> bool:
        if isinstance(v, ox.Triple):
            return _walk(v.subject) or _walk(v.predicate) or _walk(v.object)
        return _opaque_key(v) == key

    return any(_walk(v) for v in row.values())


def _opaque_key_signature(key: str, bindings: list[dict]) -> tuple:
    """A renaming-invariant fingerprint of one blank node label: the canonical shapes of the rows it occurs in, every other
    label rendered as a wildcard. Labels that could map to each other under some bijection always share it."""
    canons = [
        frozenset((str(k), _canon_term_bmap(v, _WILDCARD_BMAP)) for k, v in row.items())
        for row in bindings
        if _row_contains_key(row, key)
    ]
    return tuple(sorted(canons, key=lambda s: sorted(s)))


def bindings_match(actual: list[dict], expected: list[dict]) -> bool:
    """SPARQL result-set equality up to renaming of blank nodes (SPARQL 1.1 Protocol / Results semantics, and how the W3C
    comparison tooling treats QueryEvaluationTest results).

    A search over all label bijections at once is factorial (one fixture has 9 labels), so labels are first grouped by
    ``_opaque_key_signature`` and only permuted within a group; the worst case is the all-at-once search."""
    actual_keys = sorted(_collect_opaque_keys(actual))
    expected_keys = sorted(_collect_opaque_keys(expected))
    if len(actual_keys) != len(expected_keys):
        return False
    if not actual_keys:
        return canon_bindings(actual) == canon_bindings(expected)

    target = _canon_bindings_bmap(expected, {k: k for k in expected_keys})

    actual_groups: dict[tuple, list[str]] = {}
    for k in actual_keys:
        actual_groups.setdefault(_opaque_key_signature(k, actual), []).append(k)
    expected_groups: dict[tuple, list[str]] = {}
    for k in expected_keys:
        expected_groups.setdefault(_opaque_key_signature(k, expected), []).append(k)

    pending_actual_groups: list[list[str]] = []
    pending_expected_groups: list[list[str]] = []
    remaining_expected = dict(expected_groups)
    for sig, a_group in actual_groups.items():
        e_group = remaining_expected.pop(sig, None)
        if e_group is None or len(e_group) != len(a_group):
            return False
        pending_actual_groups.append(a_group)
        pending_expected_groups.append(e_group)
    if remaining_expected:
        return False

    for combo in itertools.product(*(itertools.permutations(g) for g in pending_expected_groups)):
        bmap: dict[str, str] = {}
        for a_group, e_perm in zip(pending_actual_groups, combo, strict=True):
            bmap.update(zip(a_group, e_perm, strict=True))
        if _canon_bindings_bmap(actual, bmap) == target:
            return True
    return False
