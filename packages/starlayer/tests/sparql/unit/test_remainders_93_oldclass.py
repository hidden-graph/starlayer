"""Leftovers of issue #93: annotations and reifiers wherever the grammar allows
them, MINUS over a triple-term pattern, TRIPLE() arguments, and the syntax rules
for VALUES triple terms, BIND scope and SELECT * with grouping."""

from __future__ import annotations

import pytest
from starlayer.sparql.lower_rdf11 import query_to_rdf11, rdf11_to_sparql11_text
from starlayer.sparql.parse12 import prepare_query_12

P = "PREFIX : <http://e/> "
REIFIES = "<http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies>"

ANNOTATION_FORMS = [
    ":a :p :b ~ :r , :c",
    ":a :p :b ~ :r ; :q 1",
    ":a :p :b {| :c 1 |} ; :q 1",
    ":a :p :b , :c ~ :r",
    ":a :p :b ; :q 1 ~ :r",
    ":a a :T ~ :r",
    ":a a :T {| :c 1 |}",
    ":a :p :b {| :c 1 , 2 |}",
    ":a :p :b {| :c 1 ; |}",
    ":a :p :b {| :c 1 {| :d 2 |} |}",
    "[ :p :b ~ :r ] :q 1",
    "( :a :b ) :p :b {| :c 1 |}",
    ":a :p ( 1 2 ) ~ :r",
    ":a :p [ :q :x ] ~ :r",
    ":a :p :b {| :c 1 ~ :r2 |}",
]


















@pytest.mark.parametrize("form", ["ASK { ?s :p ?o }", "DESCRIBE :a"])
def test_sparql11_text_for_ask_and_describe_is_not_implemented(form):
    graph, root = query_to_rdf11(prepare_query_12(P + form))
    with pytest.raises(NotImplementedError):
        rdf11_to_sparql11_text(graph, root)




