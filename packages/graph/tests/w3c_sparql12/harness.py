"""Shared helpers for this repo's own W3C SPARQL 1.2 test-suite harness -
see ``test_w3c_sparql12_eval.py`` for the actual pytest test functions and
``download_w3c_sparql12_tests.py`` for how ``data/`` gets populated.

Adapted from (not imported from) the downstream ``starsparql``
project's own ``tests/w3c_sparql12/harness.py`` - duplicated rather than
imported across repos, since starlayergraph's own test suite shouldn't depend on
a specific sibling checkout existing. Kept deliberately small so the
duplication stays cheap to keep in sync.

Includes a small, hand-written SPARQL JSON Results parser
(``parse_srj``/``_parse_json_term``) rather than using rdflib's own built-in
one (``rdflib.query.Result.parse``) - confirmed empirically that rdflib's
parser doesn't understand the RDF 1.2 ``"type": "triple"`` result-term shape
at all (`NotImplementedError: json term type 'triple'`), a pre-existing gap
unrelated to this repo's own work. The shape itself is simple and documented
in the SPARQL 1.2 Results JSON format, and is handled here recursively (a
`"type": "triple"` value has its own nested subject/predicate/object,
themselves ordinary term JSON) to build ``starlayergraph.model.triple.TripleTerm``
values - the same type ``StarLayerGraph.query()`` itself returns for a
triple-term-valued binding, confirmed by inspection, so comparison is
apples-to-apples.
"""

from __future__ import annotations

import csv
import itertools
import json
import os
from dataclasses import dataclass

import requests
from rdflib import BNode, Literal, URIRef, Variable

from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.model.encoding import RR_NS
from starlayergraph.model.triple import TripleTerm

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
    """The correct StarLayerGraph.parse format= for entry.data_file, keyed
    off its actual file extension - StarLayerGraph.parse's format= isn't
    resolved via rdflib's plugin registry for any of these (confirmed:
    none are registered Parser plugins at all), it's a bespoke dispatch
    with a genuinely different parser per RDF *syntax* (TriG's `GRAPH { }`
    blocks are not valid Turtle, etc) - a fixture's actual syntax has to
    match the format passed in.
    """
    for suffix, fmt in _DATA_FORMAT_BY_SUFFIX.items():
        if entry.data_file.endswith(suffix):
            return fmt
    raise ValueError(f"no known RDF-1.2 format for data file {entry.data_file!r}")


# ---------------------------------------------------------------------------
# Oxigraph endpoint config
# ---------------------------------------------------------------------------
#
# Loading itself goes through the ordinary public StarLayerGraph/
# StarLayerDataset.parse() path (see test_w3c_sparql12_eval.py's
# _new_oxigraph_graph()) - no bespoke loader needed here. That wasn't always
# true: an earlier version of this module worked around two real production
# bugs (StarLayerGraph._native_add() always wrapping writes in
# `GRAPH <self.identifier>`, including for a dataset's own default graph;
# and blank-node identity breaking across the separate HTTP requests one
# `.add()` per triple makes) with its own raw-HTTP loader. Both are now
# fixed at the source (starlayergraph_graph.py's _native_scoped(),
# backends/native.py's skolemize_bnode()/deskolemize_bnode()), so this file
# only needs the endpoint's base URL and a couple of small test-isolation
# helpers.

OXIGRAPH_BASE = "http://localhost:7878"
OXIGRAPH_QUERY_URL = f"{OXIGRAPH_BASE}/query"
OXIGRAPH_UPDATE_URL = f"{OXIGRAPH_BASE}/update"


def oxigraph_available() -> bool:
    try:
        return requests.get(OXIGRAPH_BASE, timeout=2).status_code == 200
    except Exception:
        return False


def clear_oxigraph() -> None:
    """Remove the default graph's own triples and every named graph -
    full test isolation regardless of what graph names a given fixture uses."""
    resp = requests.post(
        OXIGRAPH_UPDATE_URL,
        data="CLEAR ALL",
        headers={"Content-Type": "application/sparql-update"},
        timeout=10,
    )
    resp.raise_for_status()


# Same shape as the Oxigraph helpers above, for the second native rdf-1.2
# engine. Endpoint/dataset-name convention matches
# tests/integration/test_fuseki_backend.py exactly (a pre-created "starlayergraph"
# dataset, checked via Fuseki's own /$/ping admin endpoint rather than the
# dataset URL itself - a missing dataset would otherwise look identical to
# "Fuseki isn't running at all", which /$/ping disambiguates).
FUSEKI_BASE = "http://localhost:3030/starlayergraph"
FUSEKI_QUERY_URL = f"{FUSEKI_BASE}/query"
FUSEKI_UPDATE_URL = f"{FUSEKI_BASE}/update"


def fuseki_available() -> bool:
    try:
        return requests.get("http://localhost:3030/$/ping", timeout=2).status_code == 200
    except Exception:
        return False


def clear_fuseki() -> None:
    """Same as clear_oxigraph(), against the Fuseki endpoint instead."""
    resp = requests.post(
        FUSEKI_UPDATE_URL,
        data="CLEAR ALL",
        headers={"Content-Type": "application/sparql-update"},
        timeout=10,
    )
    resp.raise_for_status()


def _parse_json_term(term: dict):
    kind = term["type"]
    if kind == "uri":
        return URIRef(term["value"])
    if kind == "bnode":
        return BNode(term["value"])
    if kind == "literal":
        # its:dir (not "direction") is the real SPARQL 1.2 JSON Results key
        # for a dirLangString's base direction - confirmed 2026-07-16 against
        # live Fuseki 5.5.0 and Oxigraph 0.5.9 (see
        # starlayergraph.backends.native._parse_json_term, which already handles
        # this correctly; this harness's own separate copy didn't, so an
        # expected .srj fixture with a "text"@lang--dir value parsed as a
        # plain lang-tagged Literal instead of a DirLangString - confirmed
        # via the W3C SPARQL 1.2 expression/triple-on-str-literals fixture).
        lang = term.get("xml:lang") or term.get("lang")
        direction = term.get("its:dir")
        if lang and direction:
            return DirLangString(term["value"], lang, direction)
        return Literal(
            term["value"],
            lang=lang,
            datatype=term.get("datatype"),
        )
    if kind == "triple":
        v = term["value"]
        return TripleTerm(
            _parse_json_term(v["subject"]),
            _parse_json_term(v["predicate"]),
            _parse_json_term(v["object"]),
        )
    raise NotImplementedError(f"w3c_sparql12 harness: unhandled SPARQL JSON term type {kind!r}")


def parse_srj(text: str) -> list[dict]:
    """Parse SPARQL JSON Results format into a list of binding dicts
    (Variable -> term), understanding the RDF 1.2 "triple" term type
    rdflib's own parser doesn't (see module docstring)."""
    doc = json.loads(text)
    bindings = doc.get("results", {}).get("bindings", [])
    return [
        {Variable(var): _parse_json_term(term) for var, term in row.items()}
        for row in bindings
    ]


def _canon_term(v) -> str:
    """A namespace-manager-independent .n3()-equivalent string for one term.

    NOT the same as calling `v.n3()` directly for a TripleTerm specifically
    - confirmed a real, reproducible false-mismatch bug (not a
    correctness issue in what's being tested) via the sibling
    starsparql project's own copy of this harness: `TripleTerm.n3()`
    (starlayergraph/model/triple.py) falls back to a `_namespace_manager`
    remembered on the instance when no explicit one is passed (`_restore()`
    sets this so query results print with prefixes) - so a TripleTerm
    coming back from `StarLayerGraph.query()` renders prefixed
    (`<<( :a :b :c )>>`), while the "expected" side built fresh from the
    .srj file by `_parse_json_term` has no such attribute and renders
    full-IRI (`<<( <http://example/a> ... )>>`) - two semantically
    identical values producing different strings purely from this
    asymmetry, with ordinary terms (URIRef/BNode/Literal) unaffected since
    they have no such fallback. Recursing through each of a TripleTerm's
    own subject/predicate/object via this same function (rather than
    delegating to TripleTerm's own `.n3()`) sidesteps the
    attached-namespace-manager path entirely, so both sides always compare
    on the same, prefix-independent basis.

    DirLangString also needs its own branch here for a more basic reason,
    not just a prefix mismatch: it isn't an rdflib Node at all (see
    starlayergraph.model.dirlangstring's module docstring - deliberately, so it
    stays invisible to rdflib's own machinery), so it has no `.n3()` at all
    and would raise AttributeError falling through to the generic case.
    """
    if v is None:
        # An UNDEF/unbound value in a row that survived bindings_match's/
        # canon_bindings' own {k: v for ... if v is not None} filtering
        # elsewhere (e.g. a VALUES row with an explicit UNDEF cell, rather
        # than a variable simply never appearing in a solution at all) -
        # confirmed a real, reproducible AttributeError ('NoneType' object
        # has no attribute 'n3') via the W3C triple-on-undefs fixture
        # before this branch existed. A fixed, distinct sentinel string:
        # never collides with a real term's own canonical form (no valid
        # term canonicalizes to a bare word with no delimiters/prefix).
        return "UNDEF"
    if isinstance(v, TripleTerm):
        return f"<<( {_canon_term(v.subject)} {_canon_term(v.predicate)} {_canon_term(v.object)} )>>"
    if isinstance(v, DirLangString):
        return f'"{v.value}"@{v.language}--{v.direction}'
    return v.n3()


def _opaque_key(v) -> str | None:
    """This term's identity as far as bindings_match is concerned, or None
    if it's an ordinary (non-renameable) term.

    Two distinct term *kinds* count as "opaque" here, deliberately treated
    identically: a real BNode (what the W3C fixtures themselves use for an
    anonymous reifier), and a URIRef under starlayergraph's own RR_NS (what
    StarLayerGraph/StarLayerDataset actually produce for one - confirmed in
    starlayergraph/model/encoding.py: anonymous ``~``/``{| |}`` reifiers are
    deliberately skolemized to a sequential ``rr:N`` URIRef rather than left
    as a BNode, a real, load-bearing, deliberate design used across parsers/
    serializers/multiple backends - not something to change just for this
    test suite's benefit). Both name "some anonymous reifier, identity
    otherwise irrelevant" - a URIRef is normally a stricter, globally
    identified term than a BNode, but for *this* comparison (do two SPARQL
    executions of the same query agree, up to a consistent renaming of
    whatever anonymous identifiers each one happened to mint) that
    distinction isn't the thing being tested, so both are folded into the
    same opaque-identifier treatment bindings_match already needs for plain
    BNode-vs-BNode label differences (see its own docstring)."""
    if isinstance(v, BNode):
        return str(v)
    if isinstance(v, URIRef) and str(v).startswith(RR_NS):
        return str(v)
    return None


def _canon_term_bmap(v, bmap: dict) -> str:
    """Like _canon_term, but every opaque identifier (see _opaque_key,
    including one nested inside a TripleTerm's own subject/predicate/
    object) is rewritten through bmap first - see bindings_match for why
    this indirection exists."""
    if v is None:
        return "UNDEF"
    if isinstance(v, TripleTerm):
        return (
            f"<<( {_canon_term_bmap(v.subject, bmap)} "
            f"{_canon_term_bmap(v.predicate, bmap)} "
            f"{_canon_term_bmap(v.object, bmap)} )>>"
        )
    key = _opaque_key(v)
    if key is not None:
        return f"_:OPAQUE_{bmap.get(key, key)}"
    if isinstance(v, DirLangString):
        return f'"{v.value}"@{v.language}--{v.direction}'
    return v.n3()


def canon_bindings(bindings: list[dict]) -> list[frozenset]:
    """A binding-row-order-independent, term-order-independent comparable
    form. See _canon_term for why TripleTerm values need special handling
    here, unlike ordinary terms.

    Blank node *labels* are not part of this canonicalization - two
    binding sets that differ only in which arbitrary label was minted for
    "the same" anonymous node are not meaningfully different results (see
    bindings_match, which is the comparison actually meant to be used
    whenever either side may contain a BNode - this function alone will
    report a false mismatch in that case)."""
    rows = [frozenset((str(k), _canon_term(v)) for k, v in b.items()) for b in bindings]
    return sorted(rows, key=lambda r: sorted(r))


def _collect_opaque_keys(bindings: list[dict]) -> set[str]:
    keys: set[str] = set()

    def _walk(v) -> None:
        if isinstance(v, TripleTerm):
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


def bindings_match(actual: list[dict], expected: list[dict]) -> bool:
    """SPARQL result-set equality up to renaming of anonymous identifiers.

    The exact label a store mints for an anonymous node is never
    semantically meaningful in a SPARQL result set - only a *consistent*
    relabeling matters (SPARQL 1.1 Protocol/Results semantics; this is also
    exactly how the official W3C test suite's own comparison tooling treats
    QueryEvaluationTest results). Comparing via canon_bindings alone
    therefore produces false mismatches whenever the two sides mint
    different (but structurally equivalent) identifiers for "the same"
    anonymous node - confirmed two distinct ways: (1) the graphs-2 fixture,
    where StarLayerDataset labels a blank node ``_:bc_0_b0_b`` while the
    W3C .srj fixture's own expected value is ``_:b``; (2) op-1/op-2/
    results-reifiedtriples-1j, where an anonymous reifier is a real BNode
    in the W3C fixture but a stable ``rr:N`` URIRef once it round-trips
    through StarLayerGraph/StarLayerDataset (see _opaque_key) - both cases
    are "some anonymous identifier, exact spelling irrelevant" and get the
    same treatment here.

    Both sides are canonicalized through the *same* opaque-identifier
    substitution (see _canon_term_bmap) rather than expected being
    stringified as-is, so a BNode on one side and an RR_NS URIRef on the
    other for "the same" role never fail to match purely because they're
    different rdflib term *types*.

    Brute-force search over key bijections is fine here - real W3C
    SPARQL 1.2 test fixtures never have more than a handful of distinct
    anonymous identifiers in a single result set, so this stays fast in
    practice.
    """
    actual_keys = sorted(_collect_opaque_keys(actual))
    expected_keys = sorted(_collect_opaque_keys(expected))
    if len(actual_keys) != len(expected_keys):
        return False
    if not actual_keys:
        return canon_bindings(actual) == canon_bindings(expected)

    target = _canon_bindings_bmap(expected, {k: k for k in expected_keys})
    for perm in itertools.permutations(expected_keys):
        bmap = dict(zip(actual_keys, perm))
        if _canon_bindings_bmap(actual, bmap) == target:
            return True
    return False
