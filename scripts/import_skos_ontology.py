"""scripts/import_skos_ontology.py - replaces the ``skos-ontology.ttl`` named
graph in starontology.trig with the W3C's own SKOS vocabulary, converted from
the unmodified RDF/XML original kept beside it as ``starontology/skos.rdf``.

Source: https://www.w3.org/TR/skos-reference/skos.rdf (retrieved 2026-10-17),
part of the SKOS Reference W3C Recommendation of 18 August 2009. It is used
under the W3C Software and Document License
(https://www.w3.org/copyright/document-license-2023/): copied unmodified in
content, converted from RDF/XML to Turtle, with the notice below kept.

Only that one named graph's text is replaced. The result is re-parsed and
checked isomorphic to the original before anything is written.

Run:
    python scripts/import_skos_ontology.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_PACKAGES_STARLAYER = Path(__file__).resolve().parents[1] / "packages" / "starlayer"
if str(_PACKAGES_STARLAYER) not in sys.path:
    sys.path.insert(0, str(_PACKAGES_STARLAYER))

from rdflib import Dataset, Graph, URIRef  # noqa: E402
from rdflib.compare import to_isomorphic  # noqa: E402

_DIR = _PACKAGES_STARLAYER / "starlayer" / "starontology"
_TRIG = _DIR / "starontology.trig"
_ORIGINAL = _DIR / "skos.rdf"
_HEADER = "starontology:skos-ontology.ttl {"
_DCTERMS_PREFIX = "@prefix dcterms: <http://purl.org/dc/terms/> .\n"

NOTICE = """\
# Copyright (c) 2009 World Wide Web Consortium. https://www.w3.org/copyright/document-license-2023/
# SKOS vocabulary: https://www.w3.org/TR/skos-reference/skos.rdf (original, RDF/XML)
# Part of: SKOS Simple Knowledge Organization System Reference,
#   W3C Recommendation, 18 August 2009, https://www.w3.org/TR/skos-reference/
# This file includes material copied from that document, converted from RDF/XML to
# Turtle with no change to its content.
"""


def main() -> int:
    text = _TRIG.read_text(encoding="utf-8")
    original = Graph().parse(_ORIGINAL, format="xml")

    if _DCTERMS_PREFIX not in text:
        text = _DCTERMS_PREFIX + text
    start = text.index("\n" + _HEADER) + 1
    end = text.index("\n}\n", start) + 3

    probe = Dataset()
    probe.parse(data=text, format="trig")
    for prefix, ns in probe.namespaces():
        original.bind(prefix, ns, override=True)
    body = original.serialize(format="turtle")
    statements = "\n".join(line for line in body.splitlines() if not line.startswith("@prefix")).strip()
    commented = "".join("    " + line + "\n" for line in NOTICE.splitlines())
    new_block = _HEADER + "\n" + commented + "\n" + statements + "\n}\n"
    new_text = text[:start] + new_block + text[end:]

    check = Dataset()
    check.parse(data=new_text, format="trig")
    iri = URIRef("https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/starontology/skos-ontology.ttl")
    stored = Graph()
    for triple in check.graph(iri):
        stored.add(triple)
    if to_isomorphic(stored) != to_isomorphic(original):
        print("ABORT: converted block is not isomorphic to the original skos.rdf", file=sys.stderr)
        return 1
    before = {str(g.identifier): len(g) for g in probe.graphs()}
    after = {str(g.identifier): len(g) for g in check.graphs()}
    if before.keys() != after.keys() or any(before[k] != after[k] for k in before if k != str(iri)):
        print("ABORT: another named graph changed", file=sys.stderr)
        return 1
    _TRIG.write_text(new_text, encoding="utf-8")
    print(f"skos-ontology.ttl: {len(stored)} triples written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
