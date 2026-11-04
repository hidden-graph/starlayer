"""sqe feature coverage: one small query per SPARQL feature, each parsed to an
sqe tree and compared with the same query run on a StarLayerDataset holding a synthetic dataset, three
ways: the decoded query, the regenerated text, and the text re-parsed. Every
tree is also checked against the sqe shapes and for stray salg: terms.

Opt-in (``pytest --sqe-coverage``).
"""

import pytest
from rdflib import Literal, Namespace
from starlayer.graph import StarLayerDataset
from starlayer.sparql.sqe import (
    sqe_parse_to_tree,
    sqe_tree_to_query,
    sqe_tree_to_text,
    sqe_validate,
)
from tests.sparql.sqe_coverage.test_w3c_through_sqe import assert_no_salg_terms

pytestmark = pytest.mark.sqe_coverage

EX = Namespace("http://x/")
P = "PREFIX ex: <http://x/>\nPREFIX xsd: <http://www.w3.org/2001/XMLSchema#>\n"


RDF12_TURTLE = """
PREFIX ex: <http://x/>
ex:s0 ex:believes <<( ex:s1 ex:num 1 )>> .
ex:s2 ex:believes <<( ex:s3 ex:num 3 )>> .
ex:s1 ex:num 1 {| ex:certainty 9 |} .
ex:s0 ex:title "hello"@en--ltr .
ex:s1 ex:title "shalom"@he--rtl .
ex:s2 ex:title "plain" .
"""


def synthetic_triples():
    """(triples, tags): the plain data, and the two ex:tag triples that go in the second named graph."""
    triples = []
    for i in range(8):
        s = EX[f"s{i}"]
        triples.append((s, EX.num, Literal(i)))
        triples.append((s, EX.name, Literal(f"name{i % 3}")))
        triples.append((s, EX.kind, EX.even if i % 2 == 0 else EX.odd))
        if i % 3 == 0:
            triples.append((s, EX.next, EX[f"s{i + 1}"]))
        if i < 3:
            triples.append((s, EX.lang, Literal(f"w{i}", lang="en")))
    triples.append((EX.s1, EX.next, EX.s2))  # so a two-step ex:next path (s0 -> s1 -> s2) exists
    tags = [(EX.s0, EX.tag, Literal("in-g2")), (EX.s1, EX.tag, Literal("also-g2"))]
    return triples, tags


def build_dataset(dataset=None, rdf12=True):
    """The synthetic data. Everything is in the default graph (so ordinary queries see it) and the same
    triples are also in named graphs (so GRAPH queries see them): a dataset that held the triples only in
    named graphs made every default-graph query return nothing, and the comparisons vacuous."""
    ds = dataset if dataset is not None else StarLayerDataset()
    g = ds.graph(EX.g1)
    h = ds.graph(EX.g2)
    triples, tags = synthetic_triples()
    for triple in triples + tags:
        ds.add(triple)
    for triple in triples:
        g.add(triple)
    for triple in tags:
        h.add(triple)
    if rdf12:
        ds.parse(data=RDF12_TURTLE, format="turtle12")
    return ds


@pytest.fixture(scope="module")
def data():
    return build_dataset()


def _rows(graph, query):
    res = graph.query(query)
    if res.type == "CONSTRUCT":
        return sorted(res.graph)
    if res.type == "ASK":
        return res.askAnswer
    return [tuple(sorted((str(k), str(v)) for k, v in row.asdict().items() if v is not None)) for row in res]


FEATURES = {
    # --- patterns
    "bgp": "SELECT ?s ?n WHERE { ?s ex:num ?n } ORDER BY ?n",
    "optional": "SELECT ?s ?x WHERE { ?s ex:num ?n . OPTIONAL { ?s ex:next ?x } } ORDER BY ?s",
    "union": "SELECT ?s WHERE { { ?s ex:kind ex:even } UNION { ?s ex:next ?x } } ORDER BY ?s",
    "minus": "SELECT ?s WHERE { ?s ex:num ?n MINUS { ?s ex:kind ex:odd } } ORDER BY ?s",
    "graph var": "SELECT ?g ?s WHERE { GRAPH ?g { ?s ex:tag ?t } } ORDER BY ?s",
    "graph iri": "SELECT ?s WHERE { GRAPH ex:g2 { ?s ex:tag ?t } } ORDER BY ?s",
    "values single": "SELECT ?s ?n WHERE { VALUES ?s { ex:s1 ex:s2 } ?s ex:num ?n } ORDER BY ?s",
    "values multi undef": "SELECT ?s ?k WHERE { VALUES (?s ?k) { (ex:s1 ex:even) (ex:s2 UNDEF) } ?s ex:kind ?k } ORDER BY ?s",
    "values trailing": "SELECT ?s ?n WHERE { ?s ex:num ?n } VALUES ?n { 1 3 } ",
    "subselect": "SELECT ?s ?m WHERE { ?s ex:num ?n { SELECT (MAX(?x) AS ?m) WHERE { ?q ex:num ?x } } } ORDER BY ?s LIMIT 3",
    "nested group": "SELECT ?s WHERE { ?s ex:num ?n . { ?s ex:kind ex:even } } ORDER BY ?s",
    "bind": "SELECT ?s ?d WHERE { ?s ex:num ?n BIND(?n * 2 AS ?d) } ORDER BY ?s",
    "filter exists": "SELECT ?s WHERE { ?s ex:num ?n FILTER EXISTS { ?s ex:next ?x } } ORDER BY ?s",
    "filter not exists": "SELECT ?s WHERE { ?s ex:num ?n FILTER NOT EXISTS { ?s ex:next ?x } } ORDER BY ?s",
    "blank node pattern": "SELECT ?s WHERE { ?s ex:next [ ex:num ?n ] } ORDER BY ?s",
    "property list": "SELECT ?s WHERE { ?s ex:kind ex:even ; ex:num ?n } ORDER BY ?s",
    "object list": "SELECT ?s WHERE { ?s ex:kind ex:even , ?k ; ex:num ?n } ORDER BY ?s",
    "a keyword": "SELECT ?s WHERE { ?s a ?t } ORDER BY ?s",
    # --- paths
    "path sequence": "SELECT ?s ?z WHERE { ?s ex:next/ex:next ?z } ORDER BY ?s",
    "path alt": "SELECT ?s ?o WHERE { ?s (ex:kind|ex:name) ?o } ORDER BY ?s ?o",
    "path inverse": "SELECT ?s WHERE { ex:s1 ^ex:next ?s }",
    "path star": "SELECT DISTINCT ?z WHERE { ex:s0 ex:next* ?z } ORDER BY ?z",
    "path plus": "SELECT DISTINCT ?z WHERE { ex:s0 ex:next+ ?z } ORDER BY ?z",
    "path optional": "SELECT DISTINCT ?z WHERE { ex:s0 ex:next? ?z } ORDER BY ?z",
    "path negated": "SELECT ?s ?o WHERE { ?s !(ex:num|ex:name|ex:lang|ex:kind|ex:tag|ex:date) ?o } ORDER BY ?s",
    # --- forms
    "ask true": "ASK { ?s ex:num 3 }",
    "ask false": "ASK { ?s ex:num 99 }",
    "construct": "CONSTRUCT { ?s ex:copy ?n } WHERE { ?s ex:num ?n }",
    "construct where": "CONSTRUCT WHERE { ?s ex:kind ?k }",
    "select star": "SELECT * WHERE { ?s ex:num ?n } ORDER BY ?n",
    # --- solution modifiers
    "distinct": "SELECT DISTINCT ?k WHERE { ?s ex:kind ?k } ORDER BY ?k",
    "order desc": "SELECT ?s WHERE { ?s ex:num ?n } ORDER BY DESC(?n)",
    "order multi": "SELECT ?s WHERE { ?s ex:name ?m ; ex:num ?n } ORDER BY ?m DESC(?n)",
    "limit offset": "SELECT ?s WHERE { ?s ex:num ?n } ORDER BY ?n LIMIT 2 OFFSET 3",
    # --- aggregates
    "count star": "SELECT (COUNT(*) AS ?c) WHERE { ?s ex:num ?n }",
    "count distinct": "SELECT (COUNT(DISTINCT ?m) AS ?c) WHERE { ?s ex:name ?m }",
    "sum avg min max": "SELECT (SUM(?n) AS ?a) (AVG(?n) AS ?b) (MIN(?n) AS ?c) (MAX(?n) AS ?d) WHERE { ?s ex:num ?n }",
    "sample": "SELECT (SAMPLE(?k) AS ?x) WHERE { ex:s0 ex:kind ?k }",
    "group_concat": "SELECT (GROUP_CONCAT(?m; SEPARATOR='|') AS ?g) WHERE { ex:s0 ex:name ?m }",
    "group by": "SELECT ?m (COUNT(?s) AS ?c) WHERE { ?s ex:name ?m } GROUP BY ?m ORDER BY ?m",
    "group by expr alias": "SELECT ?parity (COUNT(?s) AS ?c) WHERE { ?s ex:num ?n } GROUP BY (?n - 2 * FLOOR(?n / 2) AS ?parity) ORDER BY ?parity",
    "having": "SELECT ?m WHERE { ?s ex:name ?m } GROUP BY ?m HAVING (COUNT(?s) > 2) ORDER BY ?m",
    "projected expr": "SELECT ?s (?n + 1 AS ?m) WHERE { ?s ex:num ?n } ORDER BY ?s",
    # --- expressions and operators
    "arithmetic": "SELECT ?s WHERE { ?s ex:num ?n FILTER(?n * 2 + 1 - 3 / 3 > 6) } ORDER BY ?s",
    "unary": "SELECT ?s WHERE { ?s ex:num ?n FILTER(-?n < -2 && +?n > 0) } ORDER BY ?s",
    "logic": "SELECT ?s WHERE { ?s ex:num ?n FILTER((?n < 2 || ?n > 5) && !(?n = 6)) } ORDER BY ?s",
    "in": "SELECT ?s WHERE { ?s ex:num ?n FILTER(?n IN (1, 3, 5)) } ORDER BY ?s",
    "not in": "SELECT ?s WHERE { ?s ex:num ?n FILTER(?n NOT IN (1, 3, 5)) } ORDER BY ?s",
    "relational": "SELECT ?s WHERE { ?s ex:num ?n FILTER(?n >= 2 && ?n <= 4 && ?n != 3) } ORDER BY ?s",
    "if coalesce": "SELECT ?s (IF(?n > 3, 'big', 'small') AS ?sz) (COALESCE(?x, 'none') AS ?nx) WHERE { ?s ex:num ?n OPTIONAL { ?s ex:next ?x } } ORDER BY ?s",
    "bound": "SELECT ?s WHERE { ?s ex:num ?n OPTIONAL { ?s ex:next ?x } FILTER(!BOUND(?x)) } ORDER BY ?s",
    # --- builtins: strings
    "str fns": "SELECT ?s (STRLEN(?m) AS ?l) (UCASE(?m) AS ?u) (LCASE(?m) AS ?lo) WHERE { ?s ex:name ?m } ORDER BY ?s LIMIT 2",
    "substr": "SELECT ?s (SUBSTR(?m, 2) AS ?a) (SUBSTR(?m, 2, 3) AS ?b) WHERE { ?s ex:name ?m } ORDER BY ?s LIMIT 2",
    "strstarts etc": "SELECT ?s WHERE { ?s ex:name ?m FILTER(STRSTARTS(?m, 'na') && STRENDS(?m, '1') && CONTAINS(?m, 'me')) } ORDER BY ?s",
    "strbefore after": "SELECT ?s (STRBEFORE(?m, 'e') AS ?a) (STRAFTER(?m, 'e') AS ?b) WHERE { ?s ex:name ?m } ORDER BY ?s LIMIT 2",
    "concat": "SELECT ?s (CONCAT(?m, '-', STR(?n)) AS ?c) WHERE { ?s ex:name ?m ; ex:num ?n } ORDER BY ?s LIMIT 2",
    "regex": "SELECT ?s WHERE { ?s ex:name ?m FILTER(REGEX(?m, '^NAME1$', 'i')) } ORDER BY ?s",
    "replace": "SELECT ?s (REPLACE(?m, 'name', 'N', 'i') AS ?r) WHERE { ?s ex:name ?m } ORDER BY ?s LIMIT 2",
    "encode for uri": "SELECT (ENCODE_FOR_URI('a b/c') AS ?e) WHERE { }",
    "langmatches lang": "SELECT ?s WHERE { ?s ex:lang ?l FILTER(LANGMATCHES(LANG(?l), 'en')) } ORDER BY ?s",
    "strlang strdt": "SELECT (STRLANG('x', 'en') AS ?a) (STRDT('1', xsd:integer) AS ?b) WHERE { }",
    # --- builtins: numeric / terms / hashes
    "numeric fns": "SELECT ?s (ABS(-?n) AS ?a) (CEIL(?n / 2) AS ?c) (FLOOR(?n / 2) AS ?f) (ROUND(?n / 2) AS ?r) WHERE { ?s ex:num ?n } ORDER BY ?s LIMIT 3",
    "type tests": "SELECT ?s WHERE { ?s ?p ?o FILTER(isIRI(?o) && !isBLANK(?o) && !isLiteral(?o) && !isNumeric(?o)) } ORDER BY ?s LIMIT 3",
    "isnumeric isliteral": "SELECT ?s WHERE { ?s ex:num ?n FILTER(isNumeric(?n) && isLiteral(?n)) } ORDER BY ?s LIMIT 2",
    "datatype str": "SELECT ?s (DATATYPE(?n) AS ?d) (STR(?n) AS ?t) WHERE { ?s ex:num ?n } ORDER BY ?s LIMIT 2",
    "sameterm": "SELECT ?s WHERE { ?s ex:num ?n FILTER(sameTerm(?n, 3)) }",
    "iri uri": "SELECT (IRI('http://x/a') AS ?a) (URI('http://x/b') AS ?b) WHERE { }",
    "hashes": "SELECT (MD5('a') AS ?m) (SHA1('a') AS ?s1) (SHA256('a') AS ?s2) (SHA384('a') AS ?s3) (SHA512('a') AS ?s5) WHERE { }",
    "cast": "SELECT ?s (xsd:integer('4') AS ?i) (xsd:string(?n) AS ?t) (xsd:double(?n) AS ?d) WHERE { ?s ex:num ?n } ORDER BY ?s LIMIT 2",
    "deterministic time": "SELECT (YEAR('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?y) (MONTH('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?m) (DAY('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?d) (HOURS('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?h) (MINUTES('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?mi) (SECONDS('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?se) (TZ('2024-03-05T10:20:30Z'^^xsd:dateTime) AS ?tz) WHERE { }",
    "timezone": "SELECT (TIMEZONE('2024-03-05T10:20:30+01:00'^^xsd:dateTime) AS ?z) WHERE { }",
    "bnode fn": "SELECT (isBLANK(BNODE()) AS ?b) WHERE { }",
    "nondeterministic ok": "SELECT (isNumeric(RAND()) AS ?r) (STRLEN(STR(UUID())) AS ?u) (STRLEN(STRUUID()) AS ?su) (isLiteral(NOW()) AS ?n) WHERE { }",
    # --- RDF 1.2 / SPARQL 1.2
    "triple term pattern": "SELECT ?s ?x WHERE { ?s ex:believes <<( ?x ex:num ?n )>> } ORDER BY ?s",
    "triple term ground": "SELECT ?s WHERE { ?s ex:believes <<( ex:s1 ex:num 1 )>> }",
    "reified triple shorthand": "SELECT ?r WHERE { ?r ex:certainty 9 . ?r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ?s ex:num ?n )>> }",
    "annotation": "SELECT ?c WHERE { ex:s1 ex:num 1 {| ex:certainty ?c |} }",
    "reifier tilde": "SELECT ?r WHERE { ?s ex:num ?n ~ ?r } ORDER BY ?r LIMIT 3",
    "triple fn": "SELECT ?t WHERE { ?s ex:num ?n BIND(TRIPLE(?s, ex:num, ?n) AS ?t) FILTER(isTRIPLE(?t)) } ORDER BY ?t LIMIT 2",
    "triple accessors": "SELECT ?x ?p ?o WHERE { ?b ex:believes ?t BIND(SUBJECT(?t) AS ?x) BIND(PREDICATE(?t) AS ?p) BIND(OBJECT(?t) AS ?o) } ORDER BY ?x",
    "construct triple term": "CONSTRUCT { ?s ex:says <<( ?x ex:num ?n )>> } WHERE { ?s ex:believes <<( ?x ex:num ?n )>> }",
    "values triple term": "SELECT ?t WHERE { VALUES ?t { <<( ex:s1 ex:num 1 )>> } }",
    "dirlang literal": "SELECT ?s WHERE { ?s ex:title 'hello'@en--ltr }",
    "langdir fns": "SELECT ?s (LANG(?t) AS ?l) (LANGDIR(?t) AS ?d) (hasLANG(?t) AS ?hl) (hasLANGDIR(?t) AS ?hd) WHERE { ?s ex:title ?t } ORDER BY ?s",
    "strlangdir": "SELECT (STRLANGDIR('abc', 'en', 'rtl') AS ?x) WHERE { }",
    "dirlang string fns": "SELECT ?s (UCASE(?t) AS ?u) (STRLEN(?t) AS ?n) WHERE { ?s ex:title ?t FILTER(CONTAINS(?t, 'e')) } ORDER BY ?s",
    # --- literals
    "literal forms": "SELECT ?a ?b ?c ?d ?e WHERE { VALUES (?a ?b ?c ?d ?e) { (1 2.5 1e3 true 'x'@en) } }",
    "typed literal": "SELECT ?s WHERE { ?s ex:num '3'^^xsd:integer }",
    "iri function call": "SELECT ?s WHERE { ?s ex:num ?n FILTER(xsd:integer(?n) = 3) }",
}


# Features that exist only in SPARQL 1.2. A prepared 1.2 Query object cannot be executed directly by
# starlayer (that holds for the project's own prepare_query_12 too): 1.2 queries run as text, so for
# these the decoded Query is regenerated to 1.2 text first, the way the W3C harness checks it.
SPARQL_12 = {
    "triple term pattern", "triple term ground", "reified triple shorthand", "annotation",
    "reifier tilde", "triple fn", "triple accessors", "construct triple term", "values triple term",
    "dirlang literal", "langdir fns", "strlangdir", "dirlang string fns",
}


def _run_decoded(data, query, text, name):
    if name not in SPARQL_12:
        return _rows(data, query)
    from starlayer.sparql.serialize12 import _translate_algebra_12

    return _rows(data, _translate_algebra_12(query))


# Queries whose correct answer is empty or trivially false on this data; every other feature query must
# return something, or "same as the original" would compare nothing with nothing.
MAY_BE_EMPTY = {"ask false", "sameterm"}


def _check(data, text, name):
    tree, root = sqe_parse_to_tree(text)
    assert sqe_validate(tree)[0]
    assert_no_salg_terms(tree)
    expected = _rows(data, text)
    if name not in MAY_BE_EMPTY:
        assert expected not in ([], False), f"feature query {name!r} returns nothing on the test data"
    decoded = sqe_tree_to_query(tree, root)
    assert _run_decoded(data, decoded, text, name) == expected, "decoded query differs"
    regenerated = sqe_tree_to_text(tree, root)
    assert _rows(data, regenerated) == expected, f"regenerated text differs:\n{regenerated}"
    tree2, root2 = sqe_parse_to_tree(regenerated)
    assert _run_decoded(data, sqe_tree_to_query(tree2, root2), regenerated, name) == expected


@pytest.mark.parametrize("name", list(FEATURES))
def test_feature_round_trips(name, data):
    _check(data, P + FEATURES[name], name)


def test_prefixes_and_base_are_preserved(data):
    text = "BASE <http://x/> PREFIX e: <http://x/> SELECT ?s WHERE { ?s e:num 3 }"
    tree, root = sqe_parse_to_tree(text)
    rendered = sqe_tree_to_text(tree, root)
    assert "PREFIX e: <http://x/>" in rendered and "BASE <http://x/>" in rendered
    assert _rows(data, rendered) == _rows(data, text)


def test_custom_function_call(data):
    text = P + "SELECT ?s WHERE { ?s ex:num ?n FILTER(<http://x/f>(?n) ) }"
    tree, root = sqe_parse_to_tree(text)
    assert "ex:f(" in sqe_tree_to_text(tree, root)
    sqe_tree_to_query(tree, root)  # decodes; rdflib has no such function to run
