"""``query(entailment=RDFS)`` answers what ``infer(entailment=RDFS)`` materializes, for the patterns that ask for it.

The query-time regime rewrites the query and never copies the data, so a fact enters an answer only when a pattern can match it
(a type pattern, ``rdfs:subClassOf``, ``rdfs:subPropertyOf`` or an open ``?s ?p ?o``). For each graph below and each such pattern
the answers must equal the matching triples of the closure ``infer()`` returns, as sets. The graphs keep the RDFS vocabulary out
of the places where a term could be both data and schema (a class that is ``rdfs:Resource``, say): the contract is about the
rules, not about those corners. One known difference is left out of the graphs: the query-time regime types the subject and the
object of an ``rdfs:subPropertyOf`` triple ``rdf:Property`` even if nothing uses them as a predicate (GitHub issue #97), and
``infer()`` types only the predicates it sees.
"""

import pytest
from starlayer.graph import StarLayerGraph
from starlayer.graph.entailment.infer import ENTAILMENT

PREFIXES = """@prefix ex: <http://example.org/> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
"""

GRAPHS = {
    "supervises": """
        ex:Manager rdfs:subClassOf ex:Employee . ex:Employee a rdfs:Class .
        ex:supervises rdfs:domain ex:Manager ; rdfs:range ex:Employee ; rdfs:subPropertyOf ex:worksWith .
        ex:alice ex:supervises ex:bob ; ex:age "42"^^xsd:integer ; ex:nick "Al" .
    """,
    "list-and-vocabulary": """
        ex:alice ex:skills ( ex:python ex:sql ) .
        ex:member1 a rdfs:ContainerMembershipProperty .
        ex:Years a rdfs:Datatype .
        ex:Thing a rdfs:Class .
    """,
    "subclass-cycle": """
        ex:A rdfs:subClassOf ex:B . ex:B rdfs:subClassOf ex:C . ex:C rdfs:subClassOf ex:A .
        ex:x a ex:A .
    """,
    "subproperty-chain": """
        ex:p rdfs:subPropertyOf ex:q . ex:q rdfs:subPropertyOf ex:r .
        ex:r rdfs:domain ex:D . ex:q rdfs:range ex:R .
        ex:a ex:p ex:b .
    """,
    "blank-and-language": """
        _:b ex:label "x"@en ; ex:knows ex:carol .
        ex:carol a ex:Person .
    """,
    "triple-term": """
        ex:report ex:says << ex:alice ex:worksFor ex:AcmeCorp >> .
    """,
    "class-by-domain": """
        ex:classifies rdfs:domain rdfs:Class ; rdfs:range rdfs:ContainerMembershipProperty .
        ex:Thing ex:classifies ex:slot .
    """,
    "empty": "",
}

PATTERNS = {
    "types": ("SELECT ?s ?o WHERE { ?s rdf:type ?o }", lambda s, p, o: p == RDF_TYPE),
    "resources": ("SELECT ?s WHERE { ?s rdf:type rdfs:Resource }", lambda s, p, o: p == RDF_TYPE and o == RESOURCE),
    "subclasses": ("SELECT ?s ?o WHERE { ?s rdfs:subClassOf ?o }", lambda s, p, o: p == SUBCLASS),
    "subproperties": ("SELECT ?s ?o WHERE { ?s rdfs:subPropertyOf ?o }", lambda s, p, o: p == SUBPROPERTY),
    "everything": ("SELECT ?s ?p ?o WHERE { ?s ?p ?o }", lambda s, p, o: True),
}

RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
RESOURCE = "http://www.w3.org/2000/01/rdf-schema#Resource"
SUBCLASS = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
SUBPROPERTY = "http://www.w3.org/2000/01/rdf-schema#subPropertyOf"


def _key(term):
    return term if isinstance(term, str) else getattr(term, "value", str(term))


def _graph(turtle):
    g = StarLayerGraph()
    g.parse(data=PREFIXES + turtle, format="turtle")
    return g


@pytest.mark.parametrize("pattern", PATTERNS)
@pytest.mark.parametrize("name", GRAPHS)
def test_the_query_answers_what_the_closure_holds(name, pattern):
    g = _graph(GRAPHS[name])
    text, wanted = PATTERNS[pattern]
    closure = {(_key(s), _key(p), _key(o)) for s, p, o in g.infer(entailment=ENTAILMENT.RDFS).triples() if wanted(_key(s), _key(p), _key(o))}
    names = [v for v in "spo" if f"?{v}" in text.split("WHERE")[0]]
    rows = {tuple(_key(r[v]) for v in names) for r in g.query(PREFIXES.replace("@prefix", "PREFIX").replace(" .\n", "\n") + text, entailment=ENTAILMENT.RDFS)}
    expected = {tuple({"s": s, "p": p, "o": o}[v] for v in names) for s, p, o in closure}
    assert rows == expected, (sorted(expected - rows)[:6], sorted(rows - expected)[:6])


@pytest.mark.parametrize("name", GRAPHS)
def test_an_ask_for_a_resource_typing_agrees_with_the_closure(name):
    g = _graph(GRAPHS[name])
    terms = {t for s, p, o in g.infer(entailment=ENTAILMENT.RDFS).triples() for t in (s, p, o) if hasattr(t, "value") and t.__class__.__name__ == "NamedNode"}
    typed = {_key(s) for s, p, o in g.infer(entailment=ENTAILMENT.RDFS).triples() if _key(p) == RDF_TYPE and _key(o) == RESOURCE}
    for t in sorted(terms, key=_key)[:12]:
        ask = f"ASK {{ <{_key(t)}> <{RDF_TYPE}> <{RESOURCE}> }}"
        assert bool(g.query(ask, entailment=ENTAILMENT.RDFS)) == (_key(t) in typed), _key(t)


CONSTANT_PATTERNS = {
    "types of a term": ("SELECT ?o WHERE {{ <{t}> rdf:type ?o }}", lambda s, p, o, t: s == t and p == RDF_TYPE, "o"),
    "superclasses of a term": ("SELECT ?o WHERE {{ <{t}> rdfs:subClassOf ?o }}", lambda s, p, o, t: s == t and p == SUBCLASS, "o"),
    "subclasses of a term": ("SELECT ?s WHERE {{ ?s rdfs:subClassOf <{t}> }}", lambda s, p, o, t: o == t and p == SUBCLASS, "s"),
    "superproperties of a term": ("SELECT ?o WHERE {{ <{t}> rdfs:subPropertyOf ?o }}", lambda s, p, o, t: s == t and p == SUBPROPERTY, "o"),
    "subproperties of a term": ("SELECT ?s WHERE {{ ?s rdfs:subPropertyOf <{t}> }}", lambda s, p, o, t: o == t and p == SUBPROPERTY, "s"),
    "instances of a term": ("SELECT ?s WHERE {{ ?s rdf:type <{t}> }}", lambda s, p, o, t: o == t and p == RDF_TYPE, "s"),
}


@pytest.mark.parametrize("pattern", CONSTANT_PATTERNS)
@pytest.mark.parametrize("name", GRAPHS)
def test_a_pattern_with_one_term_answers_what_the_closure_holds(name, pattern):
    g = _graph(GRAPHS[name])
    template, wanted, var = CONSTANT_PATTERNS[pattern]
    closure = [(_key(s), _key(p), _key(o)) for s, p, o in g.infer(entailment=ENTAILMENT.RDFS).triples()]
    iris = sorted({k for triple in closure for k in triple if k.startswith("http")})
    prologue = PREFIXES.replace("@prefix", "PREFIX").replace(" .\n", "\n")
    for t in iris:
        expected = {{"s": s, "o": o}[var] for s, p, o in closure if wanted(s, p, o, t)}
        rows = {_key(r[var]) for r in g.query(prologue + template.format(t=t), entailment=ENTAILMENT.RDFS)}
        assert rows == expected, (t, sorted(expected - rows)[:4], sorted(rows - expected)[:4])
