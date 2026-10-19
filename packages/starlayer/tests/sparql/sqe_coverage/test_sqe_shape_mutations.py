"""Adversarial audit of the sqe shapes: take rich, valid trees, corrupt one property at a time (remove it,
replace its value with a junk literal, add a second value) and require the shapes to notice.

Some corruptions are legitimately valid and are listed here, with the reason:

* removing an optional property (modifiers, ``sqe:negated``, prefixes, ...);
* a string literal where an expression operand is expected - a literal is a valid SPARQL operand;
* a literal as the object of a triple pattern or triple term - a valid RDF term;
* ``sqe:prologuePrefix`` / ``sqe:values`` ... repeated or removed - a query may declare many prefixes.

Opt-in (``pytest --sqe-coverage``); about 5 minutes.
"""

import pytest
from rdflib import RDF, Graph, Literal
from starlayer.sparql.sqe import sqe_parse_to_tree, sqe_validate

pytestmark = pytest.mark.sqe_coverage

TREES = [
    """PREFIX ex:<http://x/>
SELECT DISTINCT ?s (COUNT(?o) AS ?c) WHERE { ?s ex:p ?o . VALUES ?o { 1 2 } BIND(?o + 1 AS ?b)
 FILTER NOT EXISTS { ?s ex:q <<( ?s ex:p ?o )>> } { SELECT ?s WHERE { ?s ex:p ?x } } MINUS { ?s ex:z 1 }
 GRAPH ?g { ?s ex:p ?o } OPTIONAL { ?s ex:r ?w } { ?s ex:u ?u } UNION { ?s ex:v ?u }
 FILTER(STRLEN(STR(?o)) > 0 && REGEX(STR(?s),'a')) } GROUP BY ?s HAVING (COUNT(?o) > 0)
 ORDER BY DESC(?c) LIMIT 5 OFFSET 1""",
    "PREFIX ex:<http://x/> CONSTRUCT { ?s ex:out ?o } WHERE { ?s ex:p ?o } ORDER BY ?o LIMIT 2",
    "PREFIX ex:<http://x/> ASK { ?s ex:p ?o }",
    "PREFIX ex:<http://x/> SELECT * WHERE { ?s ex:p ?o } VALUES ?o { 1 UNDEF }",
]

# (property local names) whose removal is fine because they are optional
OPTIONAL_PROPERTIES = {
    "distinct", "reduced", "limit", "offset", "orderBy", "groupBy", "having", "values",
    "prologuePrefix", "base", "negated", "descending", "separator", "flags", "length", "other",
}
# (property local names) that may hold a plain literal because a literal is a valid operand or term
LITERAL_OK = {"expr", "other", "arg", "pattern", "text", "vars", "object", "arg1", "arg2", "arg3", "start", "length", "flags"}
REPEATABLE = {"prologuePrefix"}


def _local(uri) -> str:
    return str(uri).split("#")[-1]


_PARSED = [sqe_parse_to_tree(text) for text in TREES]  # parsed once: blank-node labels differ between parses


def _mutations():
    for index, (tree, _root) in enumerate(_PARSED):
        seen = set()
        for subject, kind in tree.subject_objects(RDF.type):
            if "/ns/sparql/" not in str(kind):
                continue
            for predicate, obj in tree.predicate_objects(subject):
                if predicate == RDF.type or (_local(kind), _local(predicate)) in seen:
                    continue
                seen.add((_local(kind), _local(predicate)))
                for mutation in ("remove", "junk", "duplicate"):
                    yield pytest.param(index, subject, predicate, obj, mutation, id=f"{index}:{_local(kind)}.{_local(predicate)}:{mutation}")


@pytest.mark.parametrize("index,subject,predicate,obj,mutation", list(_mutations()))
def test_corruption_is_noticed_unless_it_is_legitimately_valid(index, subject, predicate, obj, mutation):
    tree, _root = _PARSED[index]
    corrupted = Graph()
    for triple in tree:
        corrupted.add(triple)
    if mutation == "remove":
        corrupted.remove((subject, predicate, obj))
    elif mutation == "junk":
        corrupted.remove((subject, predicate, obj))
        corrupted.add((subject, predicate, Literal("JUNK")))
    else:
        corrupted.add((subject, predicate, Literal("EXTRA")))
    name = _local(predicate)
    allowed = (
        (mutation == "remove" and name in OPTIONAL_PROPERTIES)
        or (mutation == "junk" and name in LITERAL_OK)
        or (mutation == "duplicate" and name in REPEATABLE)
    )
    try:
        valid = sqe_validate(corrupted)[0]
    except Exception:  # noqa: BLE001 - a graph the validator cannot even process is also "noticed"
        valid = False
    if allowed:
        return  # either outcome is fine; the point is the cases below
    assert not valid, f"{mutation} of {name} on {_local(subject)} was accepted by the shapes"
