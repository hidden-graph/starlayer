"""used_prefixes() and the namespace handling around it (GitHub issue #29)."""

from rdflib import Graph, Namespace
from starlayer.graph import StarLayerGraph, used_prefixes

EX = Namespace("http://e/")
TTL = "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix unused: <http://unused/> . ex:S a sh:NodeShape ; sh:name 'x' ."


def _graph(ttl: str = TTL, **kwargs) -> StarLayerGraph:
    g = StarLayerGraph(**kwargs)
    g.parse(data=ttl, format="turtle12")
    return g


def _names(graph) -> list[str]:
    return [prefix for prefix, _ in used_prefixes(graph)]


def test_only_the_prefixes_an_iri_is_in_are_returned_not_the_defaults() -> None:
    assert _names(_graph()) == ["ex", "sh"]


def test_a_declared_but_unused_prefix_is_not_returned() -> None:
    assert "unused" not in _names(_graph())


def test_a_literal_datatype_counts() -> None:
    assert "xsd" in _names(_graph("@prefix ex: <http://e/> . ex:a ex:p 1 ."))


def test_the_namespace_comes_with_the_prefix_and_the_result_is_sorted() -> None:
    result = used_prefixes(_graph())
    assert result == sorted(result)
    assert str(dict(result)["sh"]) == "http://www.w3.org/ns/shacl#"


def test_triple_term_parts_count() -> None:
    g = _graph("@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . ex:a ex:p <<( ex:b sh:name ex:c )>> .")
    assert {"ex", "sh"} <= set(_names(g))


def test_the_internal_prefixes_are_never_returned() -> None:
    g = _graph("@prefix ex: <http://e/> . ex:a ex:p <<( ex:b ex:q ex:c )>> .")
    assert "tt" not in _names(g) and "sl" not in _names(g)


def test_it_works_on_a_plain_rdflib_graph() -> None:
    g = Graph()
    g.parse(data=TTL, format="turtle")
    assert _names(g) == ["ex", "sh"]


def test_the_turtle12_writer_declares_exactly_these_prefixes() -> None:
    g = _graph()
    written = [line.split()[1].rstrip(":") for line in g.serialize(format="turtle12").splitlines() if line.startswith("@prefix")]
    assert written == _names(g)


def test_a_graph_created_with_core_namespaces_can_still_query_and_update() -> None:
    """query()/update() bound rdflib's defaults into the shared store while iterating it, which raised."""
    g = StarLayerGraph(bind_namespaces="core")
    g.parse(data="@prefix ex: <http://e/> . ex:a ex:p 1 .", format="turtle12")
    assert len(list(g.query("SELECT ?s WHERE { ?s ?p ?o }"))) == 1
    g.update("INSERT DATA { <http://e/b> <http://e/p> 2 }")
    assert len(g) == 2


def test_parsing_turtle12_does_not_add_rdflibs_default_prefixes_to_a_core_graph() -> None:
    g = _graph(bind_namespaces="core")
    assert {p for p, _ in g.namespaces()} == {"owl", "rdf", "rdfs", "xml", "xsd", "ex", "sh", "unused"} | {p for p, _ in g.namespaces() if p == "tt"}


def test_a_declared_prefix_keeps_its_name_when_the_graph_has_no_default_for_it() -> None:
    g = _graph("@prefix geo: <http://my/geo#> . geo:a geo:p 1 .", bind_namespaces="core")
    assert "@prefix geo: <http://my/geo#>" in g.serialize(format="turtle12")
