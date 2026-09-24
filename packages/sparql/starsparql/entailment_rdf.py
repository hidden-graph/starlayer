"""
starsparql.entailment_rdf

Query-time RDF entailment, via rewriting an already-lowered plain SPARQL 1.1
algebra tree - no data is copied or materialized. Sibling to
starsparql.entailment_rdfs (RDFS entailment, one step stronger); this module
covers the SPARQL 1.1/1.2 Entailment Regimes spec's separate, weaker "RDF
Entailment" regime (https://www.w3.org/TR/rdf11-mt/#rdf-entailment).

RDF entailment = simple entailment plus, per the RDF 1.1 Semantics spec:
    rdfD2 - if the graph contains any triple `xxx aaa yyy`, it RDF-entails
        `aaa rdf:type rdf:Property` - every term used anywhere as a
        predicate is entailed to be an rdf:Property. The only rule
        implemented here - the one rule that actually answers a question
        about the data being queried.

Deliberately NOT covered, matching the exact precedent entailment_rdfs.py
already set for its own "vocabulary-level" exclusions (rdfs4a/4b/8/12/13,
the fixed RDFS axiomatic triples):
    rdfD1 - for a typed literal with a *recognized* datatype, entails an
        existential blank node witnessing "_:nnn rdf:type <that datatype>".
        Depends on an implementation-defined "recognized datatype map," and
        produces a fact about an anonymous witness node a query could
        rarely usefully target.
    The fixed set of ~9 RDF axiomatic triples (rdf:type rdf:type
        rdf:Property, rdf:subject rdf:type rdf:Property, ...,
        rdf:nil rdf:type rdf:List), plus one more such triple *per
        container-membership-property IRI* (rdf:_1, rdf:_2, ...) that
        actually occurs in the graph or query - an infinite family, only
        ever instantiated for IRIs actually present, and - like RDFS's own
        excluded axiomatic triples - vocabulary-level noise that doesn't
        answer a real question about the data being queried.

Scoping note, unlike entailment_rdfs.py's rdf:type handling: the rewrite
here only triggers when the *object* is the literal bound term rdf:Property,
not a variable. RDFS's rdf:type rewrite generalizes correctly to a variable
object because it walks a real class hierarchy via a property path; rdfD2
is a single fixed axiom about one specific class, and a generic
`?p rdf:type ?class` query has no principled bounded rewrite that adds "and
?class could also be rdf:Property" without turning this into an unbounded,
schema-independent search over every possible additional type-fact - the
same "regular fragment" tractability constraint entailment_rdfs.py's own
module docstring describes for RDFS.
"""

from __future__ import annotations

import itertools
from typing import Any

from rdflib import RDF, Variable
from rdflib.plugins.sparql.algebra import traverse
from rdflib.plugins.sparql.parserutils import CompValue

__all__ = ["rewrite_algebra_for_rdf"]

# Fresh variables introduced by this rewrite all share this prefix - see
# entailment_rdfs.py's own _FRESH_PREFIX for why a plain prefix (no
# collision-avoidance machinery beyond a per-call itertools.count()) is
# sufficient.
_FRESH_PREFIX = "__starlayer_rdf_"


def _rewrite_bgp(bgp: CompValue, fresh: itertools.count) -> CompValue:
    """Return the algebra node replacing one BGP: a Join of a "simple" BGP
    (every triple whose entailment is exactly one alternative, matching what
    a plain BGP already does) with one Union node per triple matching
    rdfD2's trigger shape (s, rdf:type, rdf:Property).
    """
    simple_triples: list[tuple[Any, Any, Any]] = []
    unions: list[CompValue] = []

    for s, p, o in bgp.triples:
        if p == RDF.type and o == RDF.Property:
            unions.append(_property_union(s, fresh))
        else:
            simple_triples.append((s, p, o))

    result: CompValue = CompValue("BGP", triples=simple_triples)
    for union in unions:
        result = CompValue("Join", p1=result, p2=union)
    return result


def _property_union(s: Any, fresh: itertools.count) -> CompValue:
    """rdfD2 for one ``(s, rdf:type, rdf:Property)`` triple pattern: match
    either the literal asserted fact, or "s is used as a predicate
    anywhere" - a fresh-variable BGP joined via Union, the same composition
    pattern entailment_rdfs.py's own _type_union already establishes.
    """
    literal_branch = CompValue("BGP", triples=[(s, RDF.type, RDF.Property)])

    fs, fo = (Variable(f"{_FRESH_PREFIX}{next(fresh)}") for _ in range(2))
    predicate_branch = CompValue("BGP", triples=[(fs, s, fo)])

    return CompValue("Union", p1=literal_branch, p2=predicate_branch)


def rewrite_algebra_for_rdf(algebra: Any) -> Any:
    """Return ``algebra`` with every BGP rewritten for RDF entailment (see
    module docstring for exactly which rule). Mutates and returns the same
    tree (matching ``rdflib.plugins.sparql.algebra.traverse``'s own
    contract) - idempotent, since every triple this rewrite produces uses a
    fresh ``__starlayer_rdf_N`` variable in a slot that never matches the
    ``p == RDF.type and o == RDF.Property`` trigger a second time (the
    fresh predicate variable is never literally ``rdf:Property``).
    """
    fresh = itertools.count()

    def _visit(node: Any) -> Any:
        if isinstance(node, CompValue) and node.name == "BGP":
            return _rewrite_bgp(node, fresh)
        return None

    return traverse(algebra, visitPost=_visit)
