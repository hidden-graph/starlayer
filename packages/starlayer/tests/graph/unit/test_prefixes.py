"""used_prefixes() and the namespace handling around it (GitHub issue #29). The graph and dataset methods are the API.
reduce_prefixes() is not ported: ``_reduced`` below is its documented replacement (used_prefixes + unbind on a copy)."""

import pyoxigraph as ox
import pytest
from rdflib import Graph, Namespace
from starlayer.graph.oxgraph import OxGraph

EX = Namespace("http://e/")
TTL = "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix unused: <http://unused/> . ex:S a sh:NodeShape ; sh:name 'x' ."


def _graph(ttl: str = TTL, **kwargs) -> OxGraph:
    g = OxGraph(**kwargs)
    g.parse(data=ttl, format="turtle12")
    return g


def used_prefixes(graph) -> list[tuple[str, str]]:
    return graph.used_prefixes()


def _names(graph) -> list[str]:
    return [prefix for prefix, _ in used_prefixes(graph)]


def _reduced(graph, keep=()):
    """The documented replacement of ``reduce_prefixes(keep)``: a copy that binds only the used prefixes and ``keep``."""
    out = graph.copy()
    used = {p for p, _ in out.used_prefixes()}
    for p in set(out.prefixes) - used - set(keep):
        out.unbind(p)
    return out


def test_only_the_prefixes_an_iri_is_in_are_returned_not_the_defaults() -> None:
    assert _names(_graph()) == ["ex", "sh"]


def test_a_declared_but_unused_prefix_is_not_returned() -> None:
    assert "unused" not in _names(_graph())


def test_a_literal_datatype_counts() -> None:
    # Oxigraph's writer does not abbreviate a datatype IRI, so even a bound xsd is not "used" (used_prefixes() is the writer's own answer)
    assert "xsd" not in _names(_graph('@prefix ex: <http://e/> . ex:a ex:p "2020-01-01"^^<http://www.w3.org/2001/XMLSchema#date> .'))
    # a bare 1 is written without a datatype, so it needs no xsd prefix (used_prefixes() is the writer's own answer; GitHub issue #132)
    assert "xsd" not in _names(_graph("@prefix ex: <http://e/> . ex:a ex:p 1 ."))


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
    assert _names(OxGraph.from_rdflib(g)) == ["ex", "sh"]


def test_the_turtle12_writer_declares_exactly_these_prefixes() -> None:
    g = _graph()
    written = [line.split()[1].rstrip(":") for line in g.serialize(format="turtle12", only_used=True).splitlines() if line.startswith("@prefix")]
    assert sorted(written) == _names(g)


def test_a_graph_created_with_core_namespaces_can_still_query_and_update() -> None:
    """query()/update() bound rdflib's defaults into the shared store while iterating it, which raised."""
    g = OxGraph()
    g.parse(data="@prefix ex: <http://e/> . ex:a ex:p 1 .", format="turtle12")
    assert len(list(g.query("SELECT ?s WHERE { ?s ?p ?o }"))) == 1
    g.update("INSERT DATA { <http://e/b> <http://e/p> 2 }")
    assert len(g) == 2


def test_parsing_turtle12_does_not_add_rdflibs_default_prefixes_to_a_core_graph() -> None:
    g = _graph()
    assert {p for p, _ in g.namespaces()} == {"ex", "sh", "unused"}  # an OxGraph starts with no prefixes


def test_a_declared_prefix_keeps_its_name_when_the_graph_has_no_default_for_it() -> None:
    g = _graph("@prefix geo: <http://my/geo#> . geo:a geo:p 1 .")
    assert "@prefix geo: <http://my/geo#>" in g.serialize(format="turtle12")


# ---------------------------------------------------------------- methods on OxGraph and OxDataset (GitHub issue #29)
from rdflib import Dataset as RdflibDataset  # noqa: E402
from starlayer.graph.oxgraph import OxDataset  # noqa: E402

TT_TTL = "@prefix ex: <http://e/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix u: <http://u/> . ex:a a sh:NodeShape ; ex:p <<( ex:b ex:q ex:c )>> ."
TRIG = (
    "@prefix ex: <http://e/> . @prefix g: <http://graphs/> . @prefix unused: <http://unused/> . "
    "GRAPH <http://graphs/one> { ex:a ex:p 1 } GRAPH <http://other/two> { ex:b ex:q 'x' }"
)


def _dataset(trig: str = TRIG, **kwargs) -> OxDataset:
    d = OxDataset(**kwargs)
    d.parse(data=trig, format="trig12")
    return d


def test_the_graph_method_gives_the_same_answer_as_the_function() -> None:
    g = _graph(TT_TTL)
    assert g.used_prefixes() == used_prefixes(g) and [p for p, _ in g.used_prefixes()] == ["ex", "sh"]


def test_reduce_prefixes_leaves_only_the_used_bindings_and_leaves_the_graph_alone() -> None:
    g = _graph(TT_TTL)
    before = len(list(g.namespaces()))
    reduced = _reduced(g)
    assert {p for p, _ in reduced.namespaces()} == {"ex", "sh"}
    assert len(list(g.namespaces())) == before == 3  # the original keeps its bindings (ex, sh, u)


def test_reduce_prefixes_keeps_every_triple_triple_terms_included() -> None:
    g = _graph(TT_TTL)
    reduced = _reduced(g)
    assert len(reduced) == len(g) and set(reduced) == set(g)
    assert len(list(reduced.triple_terms())) == len(list(g.triple_terms())) == 1


def test_reduce_prefixes_can_be_asked_to_keep_a_prefix() -> None:
    reduced = _reduced(_graph(TT_TTL), keep=["u", "nonesuch"])
    assert {p for p, _ in reduced.namespaces()} == {"ex", "sh", "u"}


def test_the_reduced_graph_serializes_the_same_turtle() -> None:
    g = _graph(TT_TTL)
    # store order differs between a graph and its copy, so compare the lines (prefix declarations and statements), not the text
    assert sorted(_reduced(g).serialize(format="turtle12").split()) == sorted(g.serialize(format="turtle12", only_used=True).split())


def test_reduce_prefixes_of_a_graph_with_nothing_in_a_namespace_has_no_bindings() -> None:
    g = OxGraph()
    g.add((EX.a, EX.p, EX.b))
    g.bind("ex", EX)
    assert [p for p, _ in _reduced(g).namespaces()] == ["ex"]
    assert list(_reduced(OxGraph()).namespaces()) == []


def test_the_dataset_method_counts_every_graph_and_the_graph_names() -> None:
    names = [p for p, _ in _dataset().used_prefixes()]
    assert "ex" in names  # used inside the graphs
    assert "g" in names  # only the name of a named graph is in it
    assert "unused" not in names


def test_reduce_prefixes_on_a_dataset_keeps_every_graph_and_only_the_used_bindings() -> None:
    d = _dataset()
    reduced = _reduced(d)
    assert {p for p, _ in reduced.namespaces()} == {p for p, _ in d.used_prefixes()}
    assert set(reduced.graph_names()) == set(d.graph_names())
    assert set(reduced.quads()) == set(d.quads())
    assert len(list(d.namespaces())) == 3  # the original is unchanged (ex, g, unused)


def test_a_dataset_can_start_without_the_default_prefixes() -> None:
    assert list(OxDataset().namespaces()) == []  # the old class started with 29 default bindings; an OxDataset has none


def test_the_dataset_method_agrees_with_rdflib_on_a_dataset_it_did_not_build() -> None:
    rdflib_ds = RdflibDataset()
    rdflib_ds.parse(data=TRIG, format="trig")
    assert [p for p, _ in OxDataset.from_rdflib(rdflib_ds).used_prefixes()] == [p for p, _ in _dataset().used_prefixes()]


# --- a TriG prefix declaration written without a space before the IRI was ignored, leaving "ex:a" as a literal IRI
@pytest.mark.parametrize(
    "declaration",
    ["@prefix ex:<http://e/> .", "@prefix ex: <http://e/> .", "PREFIX ex:<http://e/>", "PREFIX ex: <http://e/>"],
)
def test_trig_prefix_declarations_work_with_or_without_a_space_before_the_iri(declaration) -> None:
    d = _dataset(f"{declaration}\nGRAPH <http://graphs/one> {{ ex:a ex:p 1 }}")
    assert {q.subject.value for q in d.quads()} == {"http://e/a"}


# --- #63 a reduced copy behaves like its source: the same union setting, and a named graph keeps its name
from rdflib import Namespace as _Namespace  # noqa: E402

_EX = _Namespace("http://ex.org/")


def test_a_reduced_dataset_copy_keeps_default_union_so_queries_return_the_same_rows() -> None:
    d = OxDataset(default_union=True)
    d.bind("ex", _EX)
    d.graph(_EX.g).add((_EX.a, _EX.p, _EX.b))
    reduced = _reduced(d)
    query = "SELECT * WHERE { ?s ?p ?o }"
    assert reduced.default_union is True
    assert len(list(reduced.query(query))) == len(list(d.query(query))) == 1


def test_a_reduced_dataset_copy_without_default_union_stays_without_it() -> None:
    d = OxDataset(default_union=False)
    d.graph(_EX.g).add((_EX.a, _EX.p, _EX.b))
    reduced = _reduced(d)
    assert reduced.default_union is False
    assert len(list(reduced.query("SELECT * WHERE { ?s ?p ?o }"))) == 0


def test_a_reduced_copy_of_a_named_graph_keeps_its_name() -> None:
    d = OxDataset()
    named = d.graph(_EX.g)
    named.add((_EX.a, _EX.p, _EX.b))
    assert _reduced(named).identifier == ox.NamedNode(str(_EX.g))
