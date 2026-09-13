"""RDF Dataset Canonicalization (RDFC-1.0), extended for RDF 1.2 triple terms.

Implements the actual W3C algorithm (https://www.w3.org/TR/rdf-canon/,
sections 4.4.3 main algorithm, 4.5 Issue Identifier, 4.6 Hash First Degree
Quads, 4.7 Hash Related Blank Node, 4.8 Hash N-Degree Quads, and Appendix A's
canonical N-Quads form) - not a re-implementation of rdflib's own
``compare.py`` digest (a different, older Sayers & Karp/traces algorithm;
see ``starlayergraph.compare`` for that one, used for the narrower
isomorphism-comparison bug fix). Every algorithm step below is transcribed
directly from the spec text, fetched and read section-by-section rather than
assumed from memory or a summary - the permutation/recursion logic in Hash
N-Degree Quads in particular is exactly the part most implementations get
subtly wrong.

**RDF 1.2 extension**: RDFC-1.0 as published (confirmed by fetching the spec
text directly) is scoped entirely to RDF 1.1 and says nothing about triple
terms. The W3C RCH Working Group discussed this
(https://github.com/w3c/rdf-canon/issues/2, closed as "future work" in 2023,
no substantive follow-up since as of a repo-activity check through late
2025) and leaned toward exactly the approach used here: "the input of the
c14n algorithm is an RDF Dataset as defined in RDF 1.1, which may be derived
from pre-processing of later versions of RDF" - i.e. "unstar" triple terms
into an RDF-1.1-shaped form before running the (otherwise unmodified)
algorithm, rather than modifying the algorithm's internals to understand
triple terms directly (the alternative approach, "HNDQ descent", used by a
sibling tool per a live cross-ecosystem issue,
https://github.com/sparq-org/sparq/issues/4732). This module reuses
``starlayergraph.compare._decompose()`` for that pre-processing step (fresh
blank node per triple-term occurrence, recursing for a nested triple term,
plus one-line re-encoding for ``DirLangString`` - see that module's
docstring for why both are needed and why the decomposition is correct).

``StarLayerGraph``/plain-``Graph`` input (this codebase's own model) is
triples-only and always goes through ``_decompose()`` (triple terms
unstarred, ``DirLangString`` re-encoded) - graph name is always absent for
that path. A real ``rdflib.Dataset``/``ConjunctiveGraph`` with actual named
graphs is also accepted directly (bypassing decomposition, since named
graphs are how the official W3C RDFC-1.0 test suite - used to verify this
module - exercises the graph-name/"position g" parts of the algorithm;
``StarLayerGraph`` itself has no triple-term-in-a-named-graph combination to
worry about in practice). Escaping in canonical N-Quads term serialization
covers the ECHAR set (backslash, double-quote, and the ASCII control chars
N-Quads defines short escapes for) and a UCHAR fallback for other C0
controls/DEL; it does not attempt the XML11-Char-production exclusion or
non-BMP \\U escapes from Appendix A's fullest generality - both are edge
cases well outside any realistic input this codebase produces.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from rdflib import BNode, Literal, URIRef
from rdflib.namespace import XSD

from starlayergraph.compare import _decompose

__all__ = ["to_canonical_nquads", "rdfc10_hash", "CanonicalizationComplexityError"]

# Default total permutation-loop-iteration budget shared across every call to
# Hash N-Degree Quads for one canonicalization run (not per-call - a
# pathological input can trigger many calls, each individually small, whose
# *sum* is still explosive). 100_000 comfortably covers every legitimate
# fixture in the official W3C RDFC-1.0 test suite (the largest tie-broken
# group there needs low triple digits of permutations) while failing fast
# (well under a second) on the suite's own DoS-poisoning negative test (a
# fully-symmetric 10-blank-node clique - a naive worst case is 10! =
# 3,628,800 permutations *per call*, and this shape recurses).
_DEFAULT_PERMUTATION_BUDGET = 100_000


class CanonicalizationComplexityError(RuntimeError):
    """Raised when canonicalizing would require exploring more permutations
    than the configured budget - the spec's own required defense against
    "Dataset Poisoning" (section 7.1): "Implementations MUST defend against
    potential denial-of-service attacks by raising suitable exceptions and
    terminating early." Confirmed live that without this, the official test
    suite's own poisoning fixture (test074, a 10-node blank-node clique)
    hangs indefinitely rather than raising anything."""


_Quad = Tuple[Any, Any, Any, Any]  # (subject, predicate, object, graph-name-or-None)

# The spec requires supporting at least these two ("Implementations MUST
# support SHA-256 and SHA-384"); anything else hashlib recognizes works too
# via the same name, passed straight through.
_HASH_CTORS: Dict[str, Callable[[], Any]] = {
    "sha256": hashlib.sha256,
    "sha384": hashlib.sha384,
}


def _hash_func_for(hash_algorithm: str) -> Callable[[str], str]:
    ctor = _HASH_CTORS.get(hash_algorithm.lower()) or getattr(hashlib, hash_algorithm.lower(), None)
    if ctor is None:
        raise ValueError(f"Unsupported hash algorithm: {hash_algorithm!r}")

    def _hash(s: str) -> str:
        return ctor(s.encode("utf-8")).hexdigest()

    return _hash


def _normalize_input(graph: Any) -> List[_Quad]:
    """Return every quad in ``graph`` as an ``(s, p, o, g)`` 4-tuple, ``g``
    being ``None`` for the default graph. A real quad-store
    (``rdflib.Dataset``/``ConjunctiveGraph``, detected via ``.quads()``) is
    read directly; anything else is treated as triples-only and routed
    through ``_decompose()`` first (see module docstring)."""
    quads_method = getattr(graph, "quads", None)
    # `or` on a Graph is unsafe here - Graph.__bool__ reflects triple count,
    # not "is this attribute present", so an empty-but-real default graph
    # would wrongly fall through to the deprecated `default_context` alias.
    # Explicit `is not None` avoids that (and the spurious deprecation
    # warning that fell out of it - confirmed live in this module's own
    # tests before this fix).
    default = getattr(graph, "default_graph", None)
    if default is None:
        default = getattr(graph, "default_context", None)
    is_quad_store = callable(quads_method) and default is not None
    if is_quad_store:
        default_id = default.identifier
        return [(s, p, o, None if g == default_id else g) for s, p, o, g in quads_method()]
    return [(s, p, o, None) for s, p, o in _decompose(graph)]


class IdentifierIssuer:
    """Blank Node Identifier Issuer State (spec section 4.3)."""

    def __init__(self, prefix: str = "c14n") -> None:
        self.prefix = prefix
        self.counter = 0
        # dict preserves insertion order - relied on by 4.4.3 step 5.3's
        # "in the same order" requirement.
        self.issued: Dict[str, str] = {}

    def get(self, existing_identifier: str) -> Optional[str]:
        """Read-only lookup - never mints. Distinct from ``issue()``; several
        algorithm steps explicitly require checking "has an identifier been
        issued" without issuing one as a side effect (4.7.3 step 3, 4.8.3
        step 5.4.4.1/5.4.4.2.1)."""
        return self.issued.get(existing_identifier)

    def issue(self, existing_identifier: str) -> str:
        """Issue Identifier algorithm (4.5.2)."""
        if existing_identifier in self.issued:
            return self.issued[existing_identifier]
        issued_identifier = f"{self.prefix}{self.counter}"
        self.issued[existing_identifier] = issued_identifier
        self.counter += 1
        return issued_identifier

    def copy(self) -> "IdentifierIssuer":
        new = IdentifierIssuer(self.prefix)
        new.counter = self.counter
        new.issued = dict(self.issued)
        return new


@dataclass
class _CanonState:
    bnode_to_quads: Dict[str, List[_Quad]] = field(default_factory=dict)
    canonical_issuer: IdentifierIssuer = field(default_factory=IdentifierIssuer)
    hash_func: Callable[[str], str] = field(default_factory=lambda: _hash_func_for("sha256"))
    permutation_budget: int = _DEFAULT_PERMUTATION_BUDGET


def _escape_literal_value(s: str) -> str:
    out = []
    for ch in s:
        cp = ord(ch)
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif cp == 0x09:
            out.append("\\t")
        elif cp == 0x08:
            out.append("\\b")
        elif cp == 0x0C:
            out.append("\\f")
        elif cp < 0x20 or cp == 0x7F:
            out.append(f"\\u{cp:04X}")
        else:
            out.append(ch)
    return "".join(out)


def _term_str(term: Any) -> str:
    """Canonical N-Quads form of a non-blank-node term (Appendix A)."""
    if isinstance(term, URIRef):
        return f"<{term}>"
    if isinstance(term, Literal):
        value = _escape_literal_value(str(term))
        if term.language:
            return f'"{value}"@{term.language}'
        if term.datatype is not None and str(term.datatype) != str(XSD.string):
            return f'"{value}"^^<{term.datatype}>'
        return f'"{value}"'
    raise TypeError(f"Unexpected term in a decomposed (triple-term-free) graph: {type(term)!r}")


def _quad_line(s: Any, p: Any, o: Any, g: Any, component) -> str:
    """One canonical-N-Quads-form line, ``component`` deciding how a
    blank-node subject/object/graph-name is rendered (real canonical label,
    or Hash First Degree Quads' a/z placeholder)."""
    line = f"{component(s)} {_term_str(p)} {component(o)}"
    if g is not None:
        line += f" {component(g)}"
    return line + " .\n"


def _hash_first_degree_quads(state: _CanonState, reference_id: str) -> str:
    """4.6.3 Algorithm."""
    nquads: List[str] = []
    for s, p, o, g in state.bnode_to_quads[reference_id]:

        def component(t: Any) -> str:
            if isinstance(t, BNode):
                return "_:a" if str(t) == reference_id else "_:z"
            return _term_str(t)

        nquads.append(_quad_line(s, p, o, g, component))
    nquads.sort()
    return state.hash_func("".join(nquads))


def _hash_related_blank_node(
    state: _CanonState, related_id: str, quad: _Quad, issuer: IdentifierIssuer, position: str
) -> str:
    """4.7.3 Algorithm."""
    _s, p, _o, _g = quad
    input_str = position
    if position != "g":
        input_str += f"<{p}>"
    canonical_id = state.canonical_issuer.get(related_id)
    temp_id = issuer.get(related_id)
    if canonical_id is not None or temp_id is not None:
        input_str += f"_:{canonical_id if canonical_id is not None else temp_id}"
    else:
        input_str += _hash_first_degree_quads(state, related_id)
    return state.hash_func(input_str)


def _hash_n_degree_quads(
    state: _CanonState, identifier: str, path_identifier_issuer: IdentifierIssuer
) -> Tuple[IdentifierIssuer, str]:
    """4.8.3 Algorithm. Returns (issuer, hash)."""
    Hn: Dict[str, List[str]] = {}
    for quad in state.bnode_to_quads[identifier]:
        s, _p, o, g = quad
        for component, position in ((s, "s"), (o, "o"), (g, "g")):
            if isinstance(component, BNode) and str(component) != identifier:
                related_id = str(component)
                h = _hash_related_blank_node(state, related_id, quad, path_identifier_issuer, position)
                Hn.setdefault(h, []).append(related_id)

    data_to_hash: List[str] = []
    issuer = path_identifier_issuer
    for related_hash in sorted(Hn):
        data_to_hash.append(related_hash)
        chosen_path: Optional[str] = None
        chosen_issuer: Optional[IdentifierIssuer] = None

        for perm in itertools.permutations(Hn[related_hash]):
            state.permutation_budget -= 1
            if state.permutation_budget < 0:
                raise CanonicalizationComplexityError(
                    "Canonicalization aborted: exceeded the permutation budget "
                    f"({_DEFAULT_PERMUTATION_BUDGET}) exploring blank nodes that share a hash - "
                    "this graph is either pathologically symmetric (e.g. a dense blank-node "
                    "clique) or a deliberate dataset-poisoning attack (RDFC-1.0 section 7.1)."
                )
            issuer_copy = issuer.copy()
            path = ""
            recursion_list: List[str] = []
            skip = False

            for related in perm:
                canonical_id = state.canonical_issuer.get(related)
                if canonical_id is not None:
                    path += f"_:{canonical_id}"
                else:
                    if issuer_copy.get(related) is None:
                        recursion_list.append(related)
                    path += f"_:{issuer_copy.issue(related)}"
                if chosen_path is not None and len(path) >= len(chosen_path) and path > chosen_path:
                    skip = True
                    break
            if skip:
                continue

            for related in recursion_list:
                result_issuer, result_hash = _hash_n_degree_quads(state, related, issuer_copy)
                path += f"_:{issuer_copy.issue(related)}"
                path += f"<{result_hash}>"
                issuer_copy = result_issuer
                if chosen_path is not None and len(path) >= len(chosen_path) and path > chosen_path:
                    skip = True
                    break
            if skip:
                continue

            if chosen_path is None or path < chosen_path:
                chosen_path = path
                chosen_issuer = issuer_copy

        data_to_hash.append(chosen_path or "")
        issuer = chosen_issuer if chosen_issuer is not None else issuer

    return issuer, state.hash_func("".join(data_to_hash))


def _canonicalize(
    graph: Any, hash_algorithm: str = "sha256", permutation_budget: int = _DEFAULT_PERMUTATION_BUDGET
) -> _CanonState:
    """4.4.3 Algorithm, steps 1-6 (state-building; step 7's serialization is
    ``to_canonical_nquads()`` below, which reuses this state)."""
    quads = _normalize_input(graph)
    state = _CanonState(hash_func=_hash_func_for(hash_algorithm), permutation_budget=permutation_budget)

    # Steps 1-2: blank node to quads map.
    for s, p, o, g in quads:
        for component in (s, o, g):
            if isinstance(component, BNode):
                state.bnode_to_quads.setdefault(str(component), []).append((s, p, o, g))

    # Step 3: first-degree hashes.
    hash_to_bnodes: Dict[str, List[str]] = {}
    for n in state.bnode_to_quads:
        h = _hash_first_degree_quads(state, n)
        hash_to_bnodes.setdefault(h, []).append(n)

    # Step 4: unique hashes get canonical identifiers immediately.
    for h in sorted(hash_to_bnodes):
        identifier_list = hash_to_bnodes[h]
        if len(identifier_list) > 1:
            continue
        state.canonical_issuer.issue(identifier_list[0])
    # Remove the entries step 4 consumed (spec: "Remove the map entry for
    # hash from the hash to blank nodes map"), so step 5 only sees the
    # remaining, shared-hash entries.
    hash_to_bnodes = {h: ids for h, ids in hash_to_bnodes.items() if len(ids) > 1}

    # Step 5: shared hashes, resolved via Hash N-Degree Quads.
    for h in sorted(hash_to_bnodes):
        identifier_list = hash_to_bnodes[h]
        hash_path_list: List[Tuple[str, IdentifierIssuer]] = []
        for n in identifier_list:
            if state.canonical_issuer.get(n) is not None:
                continue
            temp_issuer = IdentifierIssuer(prefix="b")
            temp_issuer.issue(n)
            result_issuer, result_hash = _hash_n_degree_quads(state, n, temp_issuer)
            hash_path_list.append((result_hash, result_issuer))
        for _result_hash, result_issuer in sorted(hash_path_list, key=lambda r: r[0]):
            for existing_id in result_issuer.issued:
                state.canonical_issuer.issue(existing_id)

    return state


def to_canonical_nquads(
    graph: Any, hash_algorithm: str = "sha256", permutation_budget: int = _DEFAULT_PERMUTATION_BUDGET
) -> str:
    """The canonical N-Quads serialization of ``graph`` (spec section 5),
    correct for triple terms and directional language strings.

    ``graph`` is decomposed first (triple terms unstarred into synthetic
    blank-node reification, directional language strings re-encoded) - see
    module and ``starlayergraph.compare`` docstrings.
    """
    state = _canonicalize(graph, hash_algorithm, permutation_budget)
    quads = _normalize_input(graph)

    def component(t: Any) -> str:
        if isinstance(t, BNode):
            canonical_id = state.canonical_issuer.get(str(t))
            if canonical_id is None:
                raise AssertionError(f"blank node {t!r} was never assigned a canonical identifier")
            return f"_:{canonical_id}"
        return _term_str(t)

    lines = [_quad_line(s, p, o, g, component) for s, p, o, g in quads]
    lines.sort()
    return "".join(lines)


def rdfc10_hash(
    graph: Any, hash_algorithm: str = "sha256", permutation_budget: int = _DEFAULT_PERMUTATION_BUDGET
) -> str:
    """A single hex digest for ``graph``'s canonical N-Quads form - the
    portable, spec-compliant equivalent of ``starlayergraph.compare.
    to_canonical_hash()`` (which uses rdflib's own, different digest
    algorithm and returns a plain Python ``int``, not a hex string)."""
    return _hash_func_for(hash_algorithm)(to_canonical_nquads(graph, hash_algorithm, permutation_budget))
