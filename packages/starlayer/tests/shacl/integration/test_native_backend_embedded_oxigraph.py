"""StarShaclSchema against an *embedded* (in-process ``pyoxigraph.Store``,
no HTTP) native (``backend='rdf-1.2'``) StarLayerGraph - the embedded-
transport counterpart to ``test_native_backend_oxigraph.py``'s own
HTTP/remote-transport tests. No live server needed (unlike that file), so
these run unconditionally, not under ``pytest.mark.integration``.

Specifically regression-tests the fix to
``validator.py::_patch_stringify_for_native_backend_bnodes()``: its own
``find_node_named_graph`` fallback used to be hardcoded to
``resolve_store_http()``/``http_select()`` and raised a specific
``RuntimeError`` for any embedded-pyoxigraph-backed dataset (see
``starlayer/graph/CLAUDE.md``'s dated entries) - fixed by routing the same
fallback through ``starlayer.graph.backends.native.execute_select()``, the
transport-agnostic dispatcher ``StarLayerGraph`` already uses everywhere
else, which works identically for embedded and HTTP stores.

Confirmed, not assumed, that ``meta_validate()`` (``meta_shapes.py``) is
the *only* path that actually exercises this fallback for an embedded
store: ordinary ``validate()``/``apply_rules()`` always re-encode
``data_graph``/``shacl_graph`` through ``TripleTermAdapter`` into a plain
in-memory graph before handing anything to pySHACL, so pySHACL's own
internal ``rdflib.Dataset`` is never built directly around the real
``EmbeddedOxigraphStore`` in that path - there's nothing broken there to
regression-test. ``meta_validate()`` is different: it passes
``shapes_graph`` (a native ``StarLayerGraph``) straight to
``pyshacl.validate()`` with no snapshot/re-encode step at all (see that
function's own docstring - the snapshot-first branch is scoped to
``StarLayerGraph._needs_bnode_skolemization``, which is only ever ``True``
for the unrelated rdf-1.1 + ``SPARQLUpdateStore`` combination), so
pySHACL's ``Dataset`` really is built directly around the embedded store -
the one place a blank node inside the shapes graph (e.g. a ``sh:rule``
blank node) can reach the broken ``find_node_named_graph`` path. Confirmed
live via a spy on ``pyshacl.rdfutil.stringify.find_node_named_graph``
before writing this file - a BNode value node in an ordinary ``validate()``
report never reaches it for an embedded graph, but ``apply_rules(...,
meta_shacl=True)`` against a shapes graph with a blank-node ``sh:rule``
does, every time.
"""

import pytest
from rdflib import Literal, Namespace, RDF

pyshacl = pytest.importorskip("pyshacl")
pyoxigraph = pytest.importorskip("pyoxigraph")

from starlayer.graph.backends.native_pyoxigraph import embedded_oxigraph_store  # noqa: E402
from starlayer.graph.graph.starlayer_graph import StarLayerGraph  # noqa: E402
from starlayer.shacl import StarShaclSchema  # noqa: E402

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")


def _embedded_graph(identifier, store=None) -> StarLayerGraph:
    if store is None:
        store = embedded_oxigraph_store()
    return StarLayerGraph(store=store, identifier=identifier, backend="rdf-1.2")


def test_apply_rules_with_meta_shacl_true_on_embedded_backend_conforming_shape() -> None:
    """The exact repro that originally motivated the embedded-transport
    guard: a shapes graph containing a blank-node sh:rule, validated with
    meta_shacl at its real default (True) - previously raised RuntimeError
    from inside meta-shacl's own structural check of the shapes graph
    itself; now conforms and infers correctly, matching the HTTP/remote
    transport's own already-passing equivalent in
    test_native_backend_oxigraph.py. Confirmed adversarially: this test
    fails (the pre-fix RuntimeError) against validator.py as it stood
    before the fix in this file's own module docstring.
    """
    store = embedded_oxigraph_store()
    data = _embedded_graph(EX.data, store=store)
    data.add((EX.alice, RDF.type, EX.Person))

    shapes = _embedded_graph(EX.shapes, store=store)
    shapes.parse(
        data="""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PersonRule a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:isPerson ; sh:object true ] .
        """,
        format="turtle12",
    )

    result = StarShaclSchema(shacl_graph=shapes).apply_rules(data_graph=data)

    assert (EX.alice, EX.isPerson, Literal(True)) in result.inferred_graph
    assert result.validation.conforms is True
