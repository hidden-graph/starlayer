"""`=` and `IN` between triple terms compare components by value (GitHub issue #74).

SPARQL 1.2 sameValue step 4 compares the components pairwise, so
<<(:s :p 1)>> = <<(:s :p 1.0)>> is true. Triple terms built inside the query
(constants, TRIPLE()) used to compare by name, and IN never used the rule.
"""

import pytest
from starlayer import StarLayerGraph

CASES = [
    ("<<(<a:s> <a:p> 1)>> = <<(<a:s> <a:p> 1.0)>>", True),
    ("<<(<a:s> <a:p> 1)>> != <<(<a:s> <a:p> 1.0)>>", False),
    ("<<(<a:s> <a:p> 1)>> IN (<<(<a:s> <a:p> 1.0)>>)", True),
    ("<<(<a:s> <a:p> 1)>> NOT IN (<<(<a:s> <a:p> 1.0)>>)", False),
    ("<<(<a:s> <a:p> 1)>> IN (<<(<a:s> <a:p> 2)>>, <<(<a:s> <a:p> 1.0)>>)", True),
    ("TRIPLE(<a:s>,<a:p>,1) = TRIPLE(<a:s>,<a:p>,1.0)", True),
    ("TRIPLE(<a:s>,<a:p>,1) = TRIPLE(<a:s>,<a:p>,2)", False),
    ("TRIPLE(<a:s>,<a:p>,\"a\") = TRIPLE(<a:s>,<a:p>,<a:o>)", False),
    ("TRIPLE(<a:s>,<a:p>,TRIPLE(<a:s>,<a:p>,1)) = TRIPLE(<a:s>,<a:p>,TRIPLE(<a:s>,<a:p>,1.0))", True),
]


@pytest.mark.parametrize(("expr", "expected"), CASES)
def test_constant_triple_terms_compare_by_value(expr, expected):
    rows = list(StarLayerGraph().query(f"SELECT (({expr}) AS ?x) {{}}"))
    assert [bool(r[0]) for r in rows] == [expected]


def test_bound_triple_terms_compare_by_value_in_filter_and_in():
    g = StarLayerGraph()
    g.parse(
        data="@prefix : <http://x/> . :a :q <<(:s :p 123)>> . :b :q <<(:s :p 123.0)>> .",
        format="turtle12",
    )
    for cond in ("?x = ?y", "?x IN (?y)"):
        rows = list(g.query(f"PREFIX : <http://x/> SELECT ?a ?b {{ ?a :q ?x . ?b :q ?y . FILTER({cond} && ?a != ?b) }}"))
        assert len(rows) == 2
