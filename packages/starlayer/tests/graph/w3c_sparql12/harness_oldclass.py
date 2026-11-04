"""Shared helpers for this repo's own W3C SPARQL 1.2 test-suite harness -
see ``test_w3c_sparql12_eval.py`` for the actual pytest test functions and
``download_w3c_sparql12_tests.py`` for how ``data/`` gets populated.

Forked from (not imported from) the sibling ``tests/sparql/w3c_sparql12/
harness.py`` - both ``starlayer.graph`` and ``starlayer.sparql`` are the
same installed package since the 2026-09-30 merge, so the original
"shouldn't depend on a specific sibling package existing" reasoning for
keeping these separate no longer applies (confirmed stale 2026-10-12).
Kept as two files anyway, deliberately: each test file in this pair pulls
in exactly what *it* needs (this one adds Oxigraph/Fuseki live-store
helpers for ``test_w3c_sparql12_eval.py``'s own round-trip tests; the
sparql-side copy adds ``skolemize_graph()`` for its own CONSTRUCT-test
isomorphism comparisons neither file's sibling tests exercise) rather
than one shared module carrying both suites' full union of helpers. Keep
each file's own prose/logic in sync when fixing a bug common to both
(like ``bindings_match()``'s factorial-search fix, 2026-10-12) - but
don't assume the two files should converge to identical content.

Includes a small, hand-written SPARQL JSON Results parser
(``parse_srj``/``_parse_json_term``) rather than using rdflib's own built-in
one (``rdflib.query.Result.parse``) - confirmed empirically that rdflib's
parser doesn't understand the RDF 1.2 ``"type": "triple"`` result-term shape
at all (`NotImplementedError: json term type 'triple'`), a pre-existing gap
unrelated to this repo's own work. The shape itself is simple and documented
in the SPARQL 1.2 Results JSON format, and is handled here recursively (a
`"type": "triple"` value has its own nested subject/predicate/object,
themselves ordinary term JSON) to build ``starlayer.graph.model.triple.TripleTerm``
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
from starlayer.graph.model.dirlangstring import DirLangString
from starlayer.graph.model.triple import TripleTerm

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
# fixed at the source (starlayer_graph.py's _native_scoped(),
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
# tests/integration/test_fuseki_backend.py exactly (a pre-created "starlayer.graph"
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
        # starlayer.graph.backends.native._parse_json_term, which already handles
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
    starlayer.sparql project's own copy of this harness: `TripleTerm.n3()`
    (starlayer.graph/model/triple.py) falls back to a `_namespace_manager`
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
    starlayer.graph.model.dirlangstring's module docstring - deliberately, so it
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

    A real BNode (what the W3C fixtures themselves use for an anonymous
    reifier, and also what StarLayerGraph/StarLayerDataset now produce for
    one - see starlayer.graph.parsers.turtle_parser._skolemize_encoding)
    names "some anonymous reifier, identity otherwise irrelevant" - the
    exact label is never semantically meaningful, only a *consistent*
    relabeling matters, so this is folded into the same opaque-identifier
    treatment bindings_match already needs for plain BNode-vs-BNode label
    differences (see its own docstring)."""
    if isinstance(v, BNode):
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


class _AllKeysToWildcard(dict):
    """A ``bmap`` stand-in for ``_canon_term_bmap`` that renders *every*
    opaque key through the same fixed placeholder, regardless of its real
    identity - used only to build a renaming-invariant per-key signature
    (``_opaque_key_signature`` below), never for the real equality check
    itself (``_canon_bindings_bmap`` below still gets a real, specific
    per-key ``bmap`` for that - this class never touches it).
    """

    def get(self, key, default=None):
        return "*"


_WILDCARD_BMAP = _AllKeysToWildcard()


def _row_contains_key(row: dict, key: str) -> bool:
    def _walk(v) -> bool:
        if isinstance(v, TripleTerm):
            return _walk(v.subject) or _walk(v.predicate) or _walk(v.object)
        return _opaque_key(v) == key

    return any(_walk(v) for v in row.values())


def _opaque_key_signature(key: str, bindings: list[dict]) -> tuple:
    """A renaming-invariant fingerprint for one opaque key: the (sorted,
    multiplicity-preserving) collection of canonical row-shapes it
    actually occurs in, with every *other* opaque key in those rows
    rendered through the same shared wildcard rather than its own
    identity - this says "what context does this key appear in," not
    "exactly which other identifiers accompany it," which is exactly the
    part ``bindings_match`` below still needs the real search for.

    Two keys that could possibly map to each other under *some* valid
    bijection always share this signature - sound as a search-space
    partition (never excludes a valid answer), even though it's not a
    full substitute for the real bijection check (that's still
    ``_canon_bindings_bmap`` below, unchanged).
    """
    canons = [
        frozenset((str(k), _canon_term_bmap(v, _WILDCARD_BMAP)) for k, v in row.items())
        for row in bindings
        if _row_contains_key(row, key)
    ]
    return tuple(sorted(canons, key=lambda s: sorted(s)))


def bindings_match(actual: list[dict], expected: list[dict]) -> bool:
    """SPARQL result-set equality up to renaming of anonymous identifiers.

    The exact label a store mints for an anonymous node is never
    semantically meaningful in a SPARQL result set - only a *consistent*
    relabeling matters (SPARQL 1.1 Protocol/Results semantics; this is also
    exactly how the official W3C test suite's own comparison tooling treats
    QueryEvaluationTest results). Comparing via canon_bindings alone
    therefore produces false mismatches whenever the two sides mint
    different (but structurally equivalent) identifiers for "the same"
    anonymous node - confirmed via the graphs-2 fixture, where
    StarLayerDataset labels a blank node ``_:bc_0_b0_b`` while the W3C .srj
    fixture's own expected value is ``_:b`` - both are "some anonymous
    identifier, exact spelling irrelevant" and get the same treatment here
    (see _opaque_key; this also now covers an anonymous reifier's own BNode
    label the same way, op-1/op-2/results-reifiedtriples-1j).

    Both sides are canonicalized through the *same* opaque-identifier
    substitution (see _canon_term_bmap) rather than expected being
    stringified as-is, so a differently-labeled BNode on either side for
    "the same" role never fails to match purely because of the label.

    A plain brute-force search over *all* key bijections at once is only
    fast when a result set has a handful of distinct anonymous
    identifiers, as most W3C SPARQL 1.2 fixtures do - but it's factorial
    in that count, and at least one real fixture
    (``eval-triple-terms/results-reifiedtriples-1j``) has 9, which alone
    took several seconds (362,880 permutations) with no pruning at all.
    Most of those 9 are already structurally distinguishable from each
    other (different variable, different co-occurring non-opaque values)
    without needing to search at all - ``_opaque_key_signature`` groups
    keys that *could* be interchangeable first, so the brute-force search
    below only ever has to permute within one such group, never across
    all distinct keys at once. Worst case (every key shares one
    indistinguishable group) falls back to exactly the original
    all-at-once search - no correctness change, pure pruning.
    """
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

    # A valid bijection can only ever match keys within the *same*
    # signature group, never across two different ones - if some actual
    # group's signature has no expected counterpart of the same size, no
    # bijection exists at all, full stop.
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
