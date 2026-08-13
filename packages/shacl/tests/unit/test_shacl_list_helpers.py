from rdflib import RDF, Graph, URIRef

from starshacl.validator import _is_shacl_list, _shacl_list_members


EX = "http://example.org/"


def test_rdf_nil_is_an_empty_shacl_list() -> None:
    g = Graph()
    assert _is_shacl_list(g, RDF.nil) is True
    assert _shacl_list_members(g, RDF.nil) == []


def test_well_formed_list_has_correct_members_in_order() -> None:
    g = Graph()
    b1, b2 = URIRef(EX + "b1"), URIRef(EX + "b2")
    g.add((b1, RDF.first, URIRef(EX + "a")))
    g.add((b1, RDF.rest, b2))
    g.add((b2, RDF.first, URIRef(EX + "b")))
    g.add((b2, RDF.rest, RDF.nil))

    assert _is_shacl_list(g, b1) is True
    assert _shacl_list_members(g, b1) == [URIRef(EX + "a"), URIRef(EX + "b")]


def test_cyclic_list_is_not_a_shacl_list() -> None:
    g = Graph()
    b1, b2 = URIRef(EX + "b1"), URIRef(EX + "b2")
    g.add((b1, RDF.first, URIRef(EX + "a")))
    g.add((b1, RDF.rest, b2))
    g.add((b2, RDF.first, URIRef(EX + "b")))
    g.add((b2, RDF.rest, b1))

    assert _is_shacl_list(g, b1) is False


def test_plain_node_with_no_rdf_first_rest_is_not_a_shacl_list() -> None:
    g = Graph()
    assert _is_shacl_list(g, URIRef(EX + "not_a_list")) is False


def test_rdf_nil_with_extraneous_first_is_not_a_valid_shacl_list() -> None:
    # Per spec, rdf:nil must have no rdf:first/rdf:rest values of its own to
    # qualify as the (empty) SHACL list terminator.
    g = Graph()
    g.add((RDF.nil, RDF.first, URIRef(EX + "a")))
    assert _is_shacl_list(g, RDF.nil) is False
