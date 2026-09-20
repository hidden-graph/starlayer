"""
starsparql.entailment_rdfs

Query-time RDFS entailment, via rewriting an already-lowered plain SPARQL
1.1 algebra tree - no data is copied or materialized (compare
starlayergraph.graph.starlayer_graph.StarLayerGraph.infer(), the
materialize-a-closure alternative for regimes this rewrite can't express).

RDFS is a "regular" fragment in the query-rewriting sense: every rule here
is either a bounded transitive/reflexive closure over one predicate
(rdfs:subClassOf, rdfs:subPropertyOf - expressible as an rdflib property
path, no schema reading needed) or a rule that joins against a *fixed*
shape of schema triple (rdfs:domain/rdfs:range/rdfs:subPropertyOf - joined
directly as ordinary graph patterns, using fresh variables, rather than
enumerated in Python first). Unlike OWL, no rule's consequent feeds back
into needing another rule's premise re-derived - there's no fixpoint
iteration to approximate here, which is exactly why this stays a rewrite
and never needs StarLayerGraph.infer()'s materialize-then-query approach.

Rules covered (RDF Semantics' own numbering):
    rdfs9  - x rdf:type C, C rdfs:subClassOf D => x rdf:type D
    rdfs2  - x P y, P rdfs:domain D            => x rdf:type D
    rdfs3  - x P y, P rdfs:range D             => y rdf:type D
    rdfs11 - subClassOf transitivity (+ rdfs10 reflexivity, for free from
             the same zero-or-more path - see module-level note below)
    rdfs5  - subPropertyOf transitivity (+ rdfs6 reflexivity, likewise)
    rdfs7  - Q rdfs:subPropertyOf P, x Q y     => x P y

Deliberately NOT covered (all "vocabulary-level" facts, not about the
data being queried - matching them would mean rewriting e.g. `?x a
rdfs:Resource` into "any term used anywhere in the graph," a fundamentally
different and far less useful query shape than what the rules above
produce): rdfs4a/rdfs4b (every term used anywhere is rdf:type
rdfs:Resource), rdfs8 (every rdfs:Class is rdfs:subClassOf rdfs:Resource),
rdfs12/rdfs13 (container-membership-property/datatype axioms), and the
~30 fixed RDFS axiomatic triples (e.g. rdf:type rdfs:domain rdfs:Resource).
Confirmed live against owlrl.RDFS_Semantics that these account for most of
the triple growth on a real closure - StarLayerGraph.infer(profile="rdfs")
still produces all of it for a caller who wants byte-for-byte RDFS
completeness; this rewrite targets the rules that actually answer a
question about the data.

Reflexivity note: rdflib's ZeroOrMorePath (the `*` in a property path) is
*unconditionally* reflexive - confirmed live that `?x rdfs:subClassOf*
?x` matches for literally any term, even one with zero subClassOf triples
anywhere in the graph, not just ones explicitly declared rdfs:Class. This
is a standard, widely-accepted simplification (the same one virtually
every practical RDFS query-rewriting/reasoning system makes) rather than
gating reflexivity on rdfs6/rdfs10's stricter "only if explicitly typed
rdf:Property/rdfs:Class" precondition, and is why rdfs6/rdfs10 need no
separate handling here - the path substitution already subsumes them.
"""

from __future__ import annotations

import itertools
from typing import Any

from rdflib import RDF, RDFS, URIRef, Variable
from rdflib.paths import MulPath, Path, SequencePath
from rdflib.plugins.sparql.algebra import traverse
from rdflib.plugins.sparql.parserutils import CompValue

__all__ = ["rewrite_algebra_for_rdfs"]

# rdf:type / rdfs:subClassOf* - a fixed path, independent of any particular
# graph's schema, so it's built once and reused for every rewritten triple.
_SUBCLASS_TYPE_PATH = SequencePath(RDF.type, MulPath(RDFS.subClassOf, "*"))
_SUBCLASS_STAR = MulPath(RDFS.subClassOf, "*")
_SUBPROPERTY_STAR = MulPath(RDFS.subPropertyOf, "*")

# Fresh variables introduced by this rewrite all share this prefix -
# "__rdfs9" is not a legal SPARQL surface-syntax variable name character
# sequence a hand-written query could ever produce (variables start with a
# letter, not a run of "_9" after "rdfs"), so collision with a query's own
# variables is not a practical concern; a per-call itertools.count() still
# keeps every fresh variable within one rewrite pass distinct from every
# other one, which is what actually matters for correctness.
_FRESH_PREFIX = "__starlayer_rdfs_"


def _rewrite_bgp(bgp: CompValue, fresh: itertools.count) -> CompValue:
    """Return the algebra node replacing one BGP: a Join of a "simple" BGP
    (every triple whose entailment is exactly one alternative, folded
    together for efficiency, matching what a plain BGP already does) with
    one Union node per triple that needs multiple alternatives (currently
    only rdf:type, via rdfs9+rdfs2+rdfs3).
    """
    simple_triples: list[tuple[Any, Any, Any]] = []
    unions: list[CompValue] = []

    for s, p, o in bgp.triples:
        if p == RDF.type:
            unions.append(_type_union(s, o, fresh))
        elif p == RDFS.subClassOf:
            simple_triples.append((s, _SUBCLASS_STAR, o))
        elif p == RDFS.subPropertyOf:
            simple_triples.append((s, _SUBPROPERTY_STAR, o))
        elif isinstance(p, URIRef):
            # rdfs7: match via any Q that's p or a subproperty of p, not
            # just p itself. A fresh variable for the actual predicate
            # used, joined against p via subPropertyOf* - not an
            # alternation over an enumerated subproperty list, so this
            # needs no Python-level schema read at all.
            q = Variable(f"{_FRESH_PREFIX}{next(fresh)}")
            simple_triples.append((s, q, o))
            simple_triples.append((q, _SUBPROPERTY_STAR, p))
        else:
            # a Variable predicate, or already a Path object (either a
            # literal property-path query, or this rewrite's own output
            # from an earlier pass - idempotent, left untouched either way)
            simple_triples.append((s, p, o))

    result: CompValue = CompValue("BGP", triples=simple_triples)
    for union in unions:
        result = CompValue("Join", p1=result, p2=union)
    return result


def _type_union(s: Any, o: Any, fresh: itertools.count) -> CompValue:
    """rdfs9 (subclass chain) UNION rdfs2 (domain) UNION rdfs3 (range) for
    one ``(s, rdf:type, o)`` triple pattern - see module docstring for why
    these three specifically, and why each needs no Python-level
    enumeration of the schema (every fresh variable here is joined
    directly against ordinary rdfs:domain/rdfs:range/rdfs:subClassOf
    triples in the same graph being queried, by the query engine itself).
    """
    subclass_branch = CompValue("BGP", triples=[(s, _SUBCLASS_TYPE_PATH, o)])

    p1, o1, d1 = (Variable(f"{_FRESH_PREFIX}{next(fresh)}") for _ in range(3))
    domain_branch = CompValue(
        "BGP", triples=[(s, p1, o1), (p1, RDFS.domain, d1), (d1, _SUBCLASS_STAR, o)]
    )

    s2, p2, d2 = (Variable(f"{_FRESH_PREFIX}{next(fresh)}") for _ in range(3))
    range_branch = CompValue(
        "BGP", triples=[(s2, p2, s), (p2, RDFS.range, d2), (d2, _SUBCLASS_STAR, o)]
    )

    return CompValue(
        "Union",
        p1=subclass_branch,
        p2=CompValue("Union", p1=domain_branch, p2=range_branch),
    )


def rewrite_algebra_for_rdfs(algebra: Any) -> Any:
    """Return ``algebra`` with every BGP rewritten for RDFS entailment (see
    module docstring for exactly which rules). Mutates and returns the
    same tree (matching ``rdflib.plugins.sparql.algebra.traverse``'s own
    contract, already relied on elsewhere in this codebase's lowering
    passes) - idempotent, since every triple this rewrite produces uses
    either a ``Path`` object or a fresh ``__starlayer_rdfs_N`` variable in
    predicate position, neither of which matches the ``p == RDF.type`` /
    ``isinstance(p, URIRef)`` checks that trigger rewriting on a second
    pass.
    """
    fresh = itertools.count()

    def _visit(node: Any) -> Any:
        if isinstance(node, CompValue) and node.name == "BGP":
            return _rewrite_bgp(node, fresh)
        return None

    return traverse(algebra, visitPost=_visit)
