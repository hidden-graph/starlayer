"""Shared helpers for the W3C SPARQL 1.2 test-suite harness — see
``tests/test_w3c_sparql12.py`` for the actual pytest test functions and
``download_w3c_sparql12_tests.py`` for how ``data/`` gets populated.

A deliberate, still-live fork of the sibling
``tests/graph/w3c_sparql12/harness.py`` - see that file's own docstring
for why the two stay separate rather than converging into one shared
module.

Includes a small, hand-written SPARQL JSON Results parser
(``parse_srj``/``_parse_json_term``) rather than using rdflib's own built-in
one (``rdflib.query.Result.parse``) — confirmed empirically that rdflib's
parser doesn't understand the RDF 1.2 ``"type": "triple"`` result-term shape
at all (`NotImplementedError: json term type 'triple'`), a pre-existing gap
unrelated to this project's own translation work. The shape itself is
simple and documented in the SPARQL 1.2 Results JSON format, and is handled
here recursively (a `"type": "triple"` value has its own nested
subject/predicate/object, themselves ordinary term JSON) to build
``starlayer.graph.model.triple.TripleTerm`` values — the same type
``StarLayerGraph.query()`` itself returns for a triple-term-valued binding,
confirmed by inspection, so comparison is apples-to-apples.
"""

from __future__ import annotations

import csv
import itertools
import json
import os
from dataclasses import dataclass

from rdflib import BNode, Graph, Literal, URIRef, Variable
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


def _parse_json_term(term: dict):
    kind = term["type"]
    if kind == "uri":
        return URIRef(term["value"])
    if kind == "bnode":
        return BNode(term["value"])
    if kind == "literal":
        # its:dir (not "direction") is the real SPARQL 1.2 JSON Results key
        # for a dirLangString's base direction - confirmed against live
        # Fuseki 5.5.0 and Oxigraph 0.5.9 (see
        # starlayer.graph.backends.native._parse_json_term, and the sibling
        # starlayer.graph repo's own copy of this harness, both of which
        # already handle this correctly; this copy didn't, so an expected
        # .srj fixture with a "text"@lang--dir value parsed as a plain
        # lang-tagged Literal instead of a DirLangString - confirmed via
        # this exact W3C fixture, expression/triple-on-str-literals).
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
    - confirmed a real, reproducible false-mismatch bug in this harness
    itself (not a translation-correctness issue) via the W3C test
    `basic-2`: `TripleTerm.n3()` (starlayer.graph/model/triple.py) falls back to
    a `_namespace_manager` remembered on the instance when no explicit one
    is passed (`_restore()` sets this so query results print with
    prefixes) - so a TripleTerm coming back from `StarLayerGraph.query()`
    renders prefixed (`<<( :a :b :c )>>`), while the "expected" side built
    fresh from the .srj file by `_parse_json_term` has no such attribute
    and renders full-IRI (`<<( <http://example/a> ... )>>`) - two
    semantically identical values producing different strings purely from
    this asymmetry, with ordinary terms (URIRef/BNode/Literal) unaffected
    since they have no such fallback. Recursing through each of a
    TripleTerm's own subject/predicate/object via this same function
    (rather than delegating to TripleTerm's own `.n3()`) sidesteps the
    attached-namespace-manager path entirely, so both sides always compare
    on the same, prefix-independent basis.
    """
    if v is None:
        # An UNDEF/unbound value (e.g. a VALUES row with an explicit UNDEF
        # cell) that survived whatever filtering the caller applies -
        # confirmed a real, reproducible AttributeError ('NoneType' object
        # has no attribute 'n3') via the W3C triple-on-undefs fixture
        # before this branch existed. Fixed the same way in
        # starlayer.graph's own copy of this harness
        # (tests/w3c_sparql12/harness.py there) - a fixed, distinct
        # sentinel string that never collides with a real term's own
        # canonical form.
        return "UNDEF"
    if isinstance(v, TripleTerm):
        return f"<<( {_canon_term(v.subject)} {_canon_term(v.predicate)} {_canon_term(v.object)} )>>"
    if isinstance(v, DirLangString):
        # Not an rdflib Node at all (see starlayer.graph.model.dirlangstring's own
        # module docstring - deliberately, so it stays invisible to
        # rdflib's own machinery), so it has no `.n3()` and would raise
        # AttributeError falling through to the generic case below, now
        # that _parse_json_term can actually produce one (see its own
        # its:dir handling above).
        return f'"{v.value}"@{v.language}--{v.direction}'
    return v.n3()


def canon_bindings(bindings: list[dict]) -> list[frozenset]:
    """A binding-row-order-independent, term-order-independent comparable
    form - mirrors the _canon() helper pattern used throughout this
    project's other tests (e.g. test_roundtrip.py). See _canon_term for why
    TripleTerm values need special handling here, unlike ordinary terms."""
    rows = [frozenset((str(k), _canon_term(v)) for k, v in b.items()) for b in bindings]
    return sorted(rows, key=lambda r: sorted(r))


# ---------------------------------------------------------------------------
# BNode-tolerant comparison - ported from starlayer.graph's own copy of this
# harness (tests/w3c_sparql12/harness.py there), confirmed there via real
# W3C fixtures (graphs-2, results-reifiedtriples-1j) that canon_bindings
# alone false-mismatches on: the exact label a store mints for an anonymous
# node (including an anonymous ~/{| |} reifier - an ordinary BNode, see
# starlayer.graph.parsers.turtle_parser._skolemize_encoding) is never
# semantically meaningful, only a *consistent* relabeling is - exactly the
# case two independently-executed queries (original vs regenerated text)
# hit here, since each execution mints its own arbitrary identifiers.
# ---------------------------------------------------------------------------

def _opaque_key(v) -> str | None:
    """This term's identity as far as bindings_match is concerned, or None
    if it's an ordinary (non-renameable) term."""
    if isinstance(v, BNode):
        return str(v)
    return None


def _canon_term_bmap(v, bmap: dict) -> str:
    """Like _canon_term, but every opaque identifier (including one nested
    inside a TripleTerm's own subject/predicate/object) is rewritten
    through bmap first - see bindings_match for why this indirection
    exists."""
    if v is None:
        return "UNDEF"
    if isinstance(v, TripleTerm):
        return (
            f"<<( {_canon_term_bmap(v.subject, bmap)} "
            f"{_canon_term_bmap(v.predicate, bmap)} "
            f"{_canon_term_bmap(v.object, bmap)} )>>"
        )
    if isinstance(v, DirLangString):
        return f'"{v.value}"@{v.language}--{v.direction}'
    key = _opaque_key(v)
    if key is not None:
        return f"_:OPAQUE_{bmap.get(key, key)}"
    return v.n3()


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


# ---------------------------------------------------------------------------
# Graph-isomorphism-safe TripleTerm skolemization - ported from
# starlayer.graph's own test_w3c_sparql12_eval.py, replacing an EARLIER,
# broken version of this same helper that lived in this project's
# test_w3c_sparql12.py directly (a content hash of the *skolemized*
# subject/predicate/object, i.e. tt_hash(str(s), str(p), str(o)) where s/p/o
# may already be a freshly-minted, arbitrary BNode). That baked a
# non-canonical BNode label into a value rdflib.compare.to_isomorphic was
# never told it could relabel, so two graphs that were actually isomorphic
# (same structure, different arbitrary BNode label for "the" anonymous
# reifier) hashed to different URIs and compared as unequal - confirmed via
# starlayer.graph's own construct-3/expr-1 fixtures, both of which mix an
# anonymous-reifier BNode with a TripleTerm nesting it.
#
# Representing a TripleTerm as ordinary triples on a *fresh* BNode instead
# (rather than a single opaque hashed value) sidesteps the problem
# entirely: BNode canonicalization is exactly what to_isomorphic() already
# does correctly, so this lets it do the comparison itself instead of this
# function trying to pre-empt it with its own hash.
# ---------------------------------------------------------------------------

_SKOLEM_NS = "urn:starsparql-test:skolem-tt#"
_SK_SUBJECT   = URIRef(_SKOLEM_NS + "subject")
_SK_PREDICATE = URIRef(_SKOLEM_NS + "predicate")
_SK_OBJECT    = URIRef(_SKOLEM_NS + "object")
_SK_TT_MARKER = URIRef(_SKOLEM_NS + "TripleTerm")

from rdflib.namespace import RDF as _RDF  # noqa: E402 (kept near point of use)


def skolemize_graph(graph) -> Graph:
    """Convert every TripleTerm value in `graph` into ordinary triples on a
    fresh BNode, so the whole thing can be handed to
    rdflib.compare.to_isomorphic() (which requires every term to be a real
    rdflib.term.Node - TripleTerm deliberately isn't one). An anonymous
    reifier is already an ordinary BNode by the time it reaches here (see
    starlayer.graph.parsers.turtle_parser._skolemize_encoding) and needs no
    further mapping."""
    out = Graph()

    def skolemize(term):
        if isinstance(term, TripleTerm):
            node = BNode()
            out.add((node, _RDF.type, _SK_TT_MARKER))
            out.add((node, _SK_SUBJECT, skolemize(term.subject)))
            out.add((node, _SK_PREDICATE, skolemize(term.predicate)))
            out.add((node, _SK_OBJECT, skolemize(term.object)))
            return node
        return term

    for s, p, o in graph:
        out.add((skolemize(s), p, skolemize(o)))
    return out
