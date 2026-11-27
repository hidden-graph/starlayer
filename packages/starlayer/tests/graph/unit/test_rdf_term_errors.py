"""Error scheme stage 4: a malformed RDF document is ``FormatError`` kind ``"rdf"`` and invalid term text is kind ``"rdf"`` too (context names the term);
a bad argument stays ``ValueError`` / ``TypeError`` and an unreadable file stays ``OSError``."""

from __future__ import annotations

import pyoxigraph as ox
import pytest
from starlayer.errors import FormatError, StarLayerError
from starlayer.graph import StarLayerDataset, StarLayerGraph, literal, parse_term, qnames, terms, to_python
from starlayer.graph.interop import from_basic
from starlayer.sparql.triple_term import TripleTermNode

XSD = "http://www.w3.org/2001/XMLSchema#"
BAD_DOCUMENTS = [("turtle", "<a> <b> ."), ("nt", "<a> <b> <c> ."), ("xml", "<rdf"), ("json-ld", "{"), ("trig", "<a> <b> .")]


@pytest.mark.parametrize("fmt,text", BAD_DOCUMENTS)
def test_a_malformed_document_is_a_format_error_of_kind_rdf(fmt, text):
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(data=text, format=fmt)
    assert info.value.kind == "rdf" and isinstance(info.value, StarLayerError)
    assert not isinstance(info.value, (SyntaxError, ValueError))
    assert isinstance(info.value.__cause__, SyntaxError)


def test_a_dataset_parse_is_the_same_error():
    with pytest.raises(FormatError) as info:
        StarLayerDataset().parse(data="<a> <b> .", format="turtle")
    assert info.value.kind == "rdf"


def test_the_position_is_the_one_the_parser_gives_as_attributes():
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(data="\n\n<a> <b> <c> <d> .", format="turtle")
    assert (info.value.line, info.value.col) == (3, 1)
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(data="<a> <b> <c> .\nVERSION 1.2\n", format="nt")
    assert (info.value.line, info.value.col) == (2, 1)
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(data="<rdf", format="xml")
    assert (info.value.line, info.value.col) == (None, None)  # the XML parser gives none: nothing is read out of its message


def test_the_source_is_the_context(tmp_path):
    path = tmp_path / "bad.ttl"
    path.write_text("<a> <b> .")
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(str(path))
    assert info.value.context == str(path)


def test_a_failed_parse_keeps_the_graph_as_it_was():
    graph = StarLayerGraph().parse(data="<urn:a> <urn:p> <urn:o> .")
    with pytest.raises(FormatError):
        graph.parse(data="<urn:a> <urn:p> <urn:o2> . broken")
    assert len(graph) == 1


def test_what_is_not_a_malformed_document_keeps_its_class(tmp_path):
    with pytest.raises(FileNotFoundError):  # an unreadable file is an I/O failure, there is no document to be malformed
        StarLayerGraph().parse(str(tmp_path / "missing.ttl"))
    with pytest.raises(ValueError, match="unknown RDF format"):
        StarLayerGraph().parse(data="", format="no-such-format")
    with pytest.raises(ValueError, match="named graphs"):  # the wrong target for a quad document: an argument
        StarLayerGraph().parse(data="<urn:g> { <urn:a> <urn:p> <urn:o> }", format="trig")
    with pytest.raises(ValueError):
        StarLayerGraph().parse()
    with pytest.raises(TypeError):
        StarLayerGraph().parse(data=5)
    with pytest.raises(ValueError, match="unknown RDF format"):
        StarLayerGraph().serialize(format="no-such-format")


def test_an_rdf_list_that_is_not_one_is_kind_rdf():
    graph = StarLayerGraph()
    a, b = ox.BlankNode("a"), ox.BlankNode("b")
    first, rest = ox.NamedNode(terms.RDF_FIRST.value), ox.NamedNode(terms.RDF_REST.value)
    for node, other in ((a, b), (b, a)):
        graph.add((node, first, ox.Literal("x")))
        graph.add((node, rest, other))
    with pytest.raises(FormatError) as info:
        list(graph.items(a))
    assert info.value.kind == "rdf"
    with pytest.raises(FormatError):
        graph.remove_list(a)
    with pytest.raises(FormatError):
        list(StarLayerGraph().items(ox.BlankNode("nowhere")))


def test_the_basic_encoding_of_a_damaged_proposition_form_is_kind_rdf():
    rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
    form = ox.BlankNode("f")
    dg = ox.DefaultGraph()
    quads = [ox.Quad(form, ox.NamedNode(rdf + "type"), ox.NamedNode(rdf + "PropositionForm"), dg)]
    with pytest.raises(FormatError) as info:
        from_basic(quads)
    assert info.value.kind == "rdf" and info.value.context == "rdf:PropositionForm encoding"


def test_a_lexical_form_that_is_not_valid_for_its_datatype_is_kind_term():
    for datatype, text in (("integer", "abc"), ("boolean", "yes"), ("dateTime", "nope")):
        with pytest.raises(FormatError) as info:
            to_python(ox.Literal(text, datatype=ox.NamedNode(XSD + datatype)))
        assert info.value.kind == "rdf" and not isinstance(info.value, ValueError)
    with pytest.raises(TypeError):
        to_python(ox.NamedNode("urn:x"))


@pytest.mark.parametrize("text", ["", "   ", "a b", "<urn:a> <urn:b>", "<not an iri>", "{|", "ex:alice"])
def test_text_that_is_not_one_term_is_kind_term(text):
    with pytest.raises(FormatError) as info:
        parse_term(text)
    assert info.value.kind == "rdf"


def test_parse_term_wants_text():
    with pytest.raises(TypeError):
        parse_term(5)


def test_invalid_iri_and_language_text_is_kind_term_but_a_wrong_argument_combination_is_not():
    with pytest.raises(FormatError) as info:
        literal("x", "not an iri")
    assert info.value.kind == "rdf"
    with pytest.raises(FormatError) as info:
        literal("x", lang="!!")
    assert info.value.kind == "rdf"
    with pytest.raises(FormatError) as info:
        terms.graph_name("a b")
    assert info.value.kind == "rdf"
    with pytest.raises(ValueError, match="not both"):
        literal("x", XSD + "integer", lang="en")
    with pytest.raises(ValueError, match="direction"):
        literal("x", lang="en", direction="up")
    with pytest.raises(ValueError, match="language"):
        literal("x", direction="ltr")


def test_a_chosen_direction_is_a_value_error_and_the_same_text_in_a_parsed_value_is_a_format_error():
    """Review decision Q2 (2026-11-26): a parsed value is ``FormatError``, a chosen or combined one is ``ValueError``."""
    with pytest.raises(ValueError, match="direction"):
        literal("x", lang="sv", direction="up")
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(data='<http://a> <http://b> "x"@sv--up .', format="turtle")
    assert info.value.kind == "rdf"
    with pytest.raises(FormatError) as info:
        parse_term('"x"@sv--up')
    assert info.value.kind == "rdf"
    with pytest.raises(FormatError) as info:
        literal("x", lang="not a tag!")
    assert info.value.kind == "rdf"


def test_a_curie_that_is_not_one_is_kind_term():
    with pytest.raises(FormatError):
        qnames.expand_curie({}, "nocolon")
    with pytest.raises(FormatError):
        qnames.expand_curie({"ex": "http://e/"}, "ex:a b")
    with pytest.raises(TypeError):
        qnames.expand_curie({}, 5)


def test_a_triple_term_nested_in_subject_position_is_kind_term():
    inner = TripleTermNode("TripleTerm", subject=ox.NamedNode("urn:s"), predicate=ox.NamedNode("urn:p"), object=ox.NamedNode("urn:o"))
    TripleTermNode("TripleTerm", subject=ox.NamedNode("urn:s"), predicate=ox.NamedNode("urn:p"), object=inner).validate()  # object position is legal
    with pytest.raises(FormatError) as info:
        TripleTermNode("TripleTerm", subject=inner, predicate=ox.NamedNode("urn:p"), object=ox.NamedNode("urn:o")).validate()
    assert info.value.kind == "rdf"


def test_an_rdflib_term_that_rdf_rejects_is_kind_term():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(FormatError) as info:
        StarLayerGraph.from_rdflib(_rdflib_graph(rdflib, "not an iri"))
    assert info.value.kind == "rdf"


def _rdflib_graph(rdflib, subject):
    graph = rdflib.Graph()
    graph.add((rdflib.URIRef(subject), rdflib.URIRef("http://e/p"), rdflib.URIRef("http://e/o")))
    return graph


def test_json_ld_cannot_hold_a_triple_term_and_that_is_unsupported_not_an_os_error(tmp_path):
    """Review decision Q8 (2026-11-26): valid data the chosen format cannot represent is ``unsupported``; real I/O errors stay ``OSError``."""
    from starlayer.errors import ExecutionError

    g = StarLayerGraph()
    g.add((ox.NamedNode("http://a"), ox.NamedNode("http://b"), ox.Triple(ox.NamedNode("http://x"), ox.NamedNode("http://y"), ox.NamedNode("http://z"))))
    with pytest.raises(ExecutionError) as info:
        g.serialize(format="json-ld")
    assert info.value.kind == "unsupported" and info.value.context == "JSON-LD serialize" and not isinstance(info.value, OSError)
    with pytest.raises(OSError):  # an unwritable path is still an I/O error
        g.serialize(str(tmp_path / "no" / "such" / "dir" / "x.nt"), format="nt")


QUAD_DOCS = {
    "trig": ("<urn:a> <urn:p> <urn:o> .", "<urn:a> <urn:p> <urn:o> .\n<urn:g> { <urn:b> <urn:p> <urn:o> }", "<urn:g> { <urn:b> <urn:p> "),
    "nquads": ("<urn:a> <urn:p> <urn:o> .\n", "<urn:a> <urn:p> <urn:o> .\n<urn:b> <urn:p> <urn:o> <urn:g> .\n", "<urn:a> <urn:p> .\n"),
}


@pytest.mark.parametrize("fmt", sorted(QUAD_DOCS))
def test_a_quad_document_into_a_single_graph_is_decided_by_its_quads(fmt):
    plain, named, broken = QUAD_DOCS[fmt]
    graph = StarLayerGraph()
    graph.parse(data=plain, format=fmt)  # no named graph: loads
    assert len(graph) == 1
    with pytest.raises(ValueError, match="the document has named graphs; parse it into a StarLayerDataset"):
        graph.parse(data=named, format=fmt)
    assert len(graph) == 1  # nothing of the refused document was added, not even its default-graph triple
    with pytest.raises(FormatError) as info:
        StarLayerGraph().parse(data=broken, format=fmt)
    assert info.value.kind == "rdf"
    dataset = StarLayerDataset()
    dataset.parse(data=named, format=fmt)
    assert len(list(dataset.named_graphs())) == 1


def test_a_refused_quad_document_leaves_a_named_graph_view_unchanged():
    dataset = StarLayerDataset()
    view = dataset.graph(ox.NamedNode("urn:v"))
    with pytest.raises(ValueError, match="named graphs"):
        view.parse(data=QUAD_DOCS["trig"][1], format="trig")
    assert len(view) == 0 and len(dataset) == 0

