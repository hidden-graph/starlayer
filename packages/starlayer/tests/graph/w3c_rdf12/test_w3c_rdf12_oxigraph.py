"""The W3C RDF 1.2 syntax suites (Turtle, TriG, N-Triples, N-Quads, RDF/XML) against Oxigraph's parsers and writers.

``data/`` holds the ``rdf/rdf12`` suites of w3c/rdf-tests at the commit in ``data/VENDORED_FROM.md``, unchanged. The manifests
(``manifest.ttl``) are read directly; nothing here is hand-listed.

* positive syntax: ``pyoxigraph.parse`` accepts the document; negative syntax: it raises ``SyntaxError``;
* evaluation: the parsed quads are isomorphic (RDFC-1.0, literals compared as terms) with the expected ``.nt`` / ``.nq``;
* canonical N-Triples / N-Quads: parse, then ``pyoxigraph.serialize`` gives exactly the expected text;
* through the wrapper: ``StarLayerDataset.parse`` stores what the parser produced (Oxigraph normalises numeric lexical forms on
  insert, so the expected graph goes through a store too).

``KNOWN_GAPS`` are tests Oxigraph fails today, each with its cause (``docs/working/phase-c-parser-measurement.md``). They are
not skipped: ``test_known_gap_still_fails`` fails when one starts to pass, so the entry is removed.
"""

from __future__ import annotations

from pathlib import Path

import pyoxigraph as ox
import pytest
from starlayer.graph import rdfc_native
from starlayer.graph.oxgraph import ntversion
from starlayer.graph.oxgraph.core import StarLayerDataset

DATA = Path(__file__).parent / "data"
MF = "http://www.w3.org/2001/sw/DataAccess/tests/test-manifest#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"

FORMATS = {
    "rdf-turtle": ox.RdfFormat.TURTLE,
    "rdf-trig": ox.RdfFormat.TRIG,
    "rdf-n-triples": ox.RdfFormat.N_TRIPLES,
    "rdf-n-quads": ox.RdfFormat.N_QUADS,
    "rdf-xml": ox.RdfFormat.RDF_XML,
}
EXPECTED_FORMATS = {".nt": ox.RdfFormat.N_TRIPLES, ".nq": ox.RdfFormat.N_QUADS}
MANIFESTS = [
    "rdf-turtle/eval", "rdf-turtle/syntax", "rdf-trig/eval", "rdf-trig/syntax", "rdf-n-triples/syntax", "rdf-n-quads/syntax",
    "rdf-xml/eval", "rdf-n-triples/c14n", "rdf-n-quads/c14n",
]

#: test id -> why Oxigraph (0.5.13) fails it
KNOWN_GAPS = {
    "rdf-xml/eval:rdf12-xml-an-13": "XMLLiteral keeps the in-scope namespace declarations (no exclusive canonicalisation)",
    "rdf-xml/eval:rdf12-xml-an-14": "XMLLiteral keeps the in-scope namespace declarations (no exclusive canonicalisation)",
}


def _manifest(rel: str) -> list[dict]:
    path = DATA / rel / "manifest.ttl"
    by_subject: dict = {}
    for t in ox.parse(path=str(path), format=ox.RdfFormat.TURTLE, base_iri=path.as_uri()):
        by_subject.setdefault(t.subject, []).append(t)

    def objects(s, predicate):
        return [t.object for t in by_subject.get(s, []) if t.predicate.value == predicate]

    nil = ox.NamedNode(RDF + "nil")
    manifest = next(s for s in by_subject if ox.NamedNode(MF + "Manifest") in objects(s, RDF + "type"))
    base = objects(manifest, MF + "assumedTestBase")[0].value
    here = path.parent.as_uri() + "/"
    out = []
    head = objects(manifest, MF + "entries")[0]
    while head != nil:
        entry = objects(head, RDF + "first")[0]
        head = objects(head, RDF + "rest")[0]
        kind = objects(entry, RDF + "type")[0].value.rsplit("#", 1)[-1]
        action = objects(entry, MF + "action")[0].value
        result = objects(entry, MF + "result")
        name = entry.value.rsplit("#", 1)[-1].rsplit("/", 1)[-1]
        out.append({
            "id": f"{rel}:{name}", "kind": kind, "file": path.parent / action[len(here):], "base": base + action[len(here):],
            "result": path.parent / result[0].value[len(here):] if result else None, "format": FORMATS[rel.split("/")[0]],
        })
    return out


def _all(*kinds_suffix: str, exclude_known: bool = False, only_known: bool = False):
    params = []
    for rel in MANIFESTS:
        for t in _manifest(rel):
            if not t["kind"].endswith(kinds_suffix):
                continue
            known = t["id"] in KNOWN_GAPS
            if (exclude_known and known) or (only_known and not known):
                continue
            params.append(pytest.param(t, id=t["id"]))
    return params


def _parse(t: dict) -> list[ox.Quad]:
    """Oxigraph's parser behind the wrapper's N-Triples / N-Quads ``VERSION`` handling (``oxgraph/ntversion.py``): Oxigraph
    itself rejects that directive, so these two syntaxes are the wrapper's parser, the others are Oxigraph's own."""
    kw = ntversion.accept_version_directive({"input": t["file"].read_bytes()}, t["format"])
    return list(ox.parse(format=t["format"], base_iri=t["base"], **kw))


def _expected(t: dict) -> list[ox.Quad]:
    return list(ox.parse(input=t["result"].read_bytes(), format=EXPECTED_FORMATS[t["result"].suffix]))


def test_the_suites_are_there() -> None:
    kinds = {t["kind"] for rel in MANIFESTS for t in _manifest(rel)}
    assert {"TestTurtleEval", "TestTrigEval", "TestXMLEval", "TestNTriplesPositiveSyntax", "TestNQuadsNegativeSyntax",
            "TestNTriplesPositiveC14N", "TestNQuadsPositiveC14N"} <= kinds
    assert sum(len(_manifest(rel)) for rel in MANIFESTS) == 351  # 269 syntax and evaluation tests, 82 canonical-form tests


@pytest.mark.parametrize("t", _all("PositiveSyntax", exclude_known=True))
def test_positive_syntax(t: dict) -> None:
    _parse(t)


@pytest.mark.parametrize("t", _all("NegativeSyntax", exclude_known=True))
def test_negative_syntax(t: dict) -> None:
    with pytest.raises(SyntaxError):
        _parse(t)


@pytest.mark.parametrize("t", _all("Eval", exclude_known=True))
def test_evaluation(t: dict) -> None:
    assert rdfc_native.isomorphic(_parse(t), _expected(t))


@pytest.mark.parametrize("t", _all("PositiveC14N"))
def test_canonical_ntriples_and_nquads(t: dict) -> None:
    got = ox.serialize(_parse(t), format=t["format"]).decode()
    assert got == t["result"].read_text(encoding="utf-8")


@pytest.mark.parametrize("t", _all("Eval", exclude_known=True))
def test_wrapper_stores_what_the_parser_produced(t: dict) -> None:
    ds = StarLayerDataset()
    ds.parse(data=t["file"].read_bytes(), format=t["format"], base=t["base"])
    expected = ox.Store()
    expected.extend(_expected(t))
    assert rdfc_native.isomorphic(list(ds.store), list(expected))


@pytest.mark.parametrize("t", _all("Eval", "Syntax", only_known=True))
def test_known_gap_still_fails(t: dict) -> None:
    try:
        parsed = _parse(t)
        ok = rdfc_native.isomorphic(parsed, _expected(t)) if t["kind"].endswith("Eval") else True
    except SyntaxError:
        ok = False
    assert not ok, f"{t['id']} now passes; remove it from KNOWN_GAPS ({KNOWN_GAPS[t['id']]})"


def test_ntriples_version_negatives_are_rejected_for_the_right_reason() -> None:
    """Each ``ntriples-version-bad-*`` is rejected, and the directive check is what rejects the ones that are directives."""
    base = DATA / "rdf-n-triples" / "syntax"
    for n, message in ((1, None), (2, "VERSION directive"), (3, "VERSION directive"), (4, None)):
        text = (base / f"ntriples-version-bad-{n}.nt").read_bytes()
        with pytest.raises(SyntaxError) as e:
            list(ox.parse(format=ox.RdfFormat.N_TRIPLES, **ntversion.accept_version_directive({"input": text}, ox.RdfFormat.N_TRIPLES)))
        assert (message is None) or (message in str(e.value)), (n, str(e.value))
    # wrong case and the Turtle-style directive are not VERSION directives: Oxigraph rejects them as statements
    assert ntversion.accept_version_directive({"input": b'version "1.2"\n'}, ox.RdfFormat.N_TRIPLES) == {"input": b'version "1.2"\n'}
