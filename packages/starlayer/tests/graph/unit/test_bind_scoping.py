"""A BIND sees only the group it is written in (SPARQL 1.1 section 18.2.2.6).

Groups are evaluated on their own and then joined, so a variable bound in a
sibling group is not visible to a BIND (GitHub issue #54). starlayer used to
reorder lazy joins so such a BIND saw it; plain rdflib, and every other
engine, does not.
"""

import pytest
from rdflib import Graph

import starlayer.graph  # noqa: F401  (installs the rdflib patches under test)


def _rows(query: str) -> list[dict[str, str]]:
    return sorted(
        ({str(k): str(v) for k, v in r.asdict().items()} for r in Graph().query(query)),
        key=lambda d: sorted(d.items()),
    )


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * WHERE { VALUES ?x {1 2} { BIND(?x+1 AS ?y) } }",
        "SELECT * WHERE { BIND(?x+1 AS ?y) { VALUES ?x {1 2} } }",
        "SELECT * WHERE { { VALUES ?x {1 2} } { BIND(?x+1 AS ?y) } }",
    ],
)
def test_bind_does_not_see_a_variable_bound_in_a_sibling_group(query):
    assert _rows(query) == [{"x": "1"}, {"x": "2"}]


def test_filter_over_a_bind_that_could_not_see_its_input_removes_the_row():
    query = "SELECT ?t { FILTER(?a0 = 1) { BIND(?t + 0 AS ?a0) { BIND(1 AS ?t) } } }"
    assert _rows(query) == []


def test_bind_still_sees_variables_bound_earlier_in_its_own_group():
    assert _rows("SELECT * WHERE { VALUES ?x {1 2} BIND(?x+1 AS ?y) }") == [
        {"x": "1", "y": "2"},
        {"x": "2", "y": "3"},
    ]
