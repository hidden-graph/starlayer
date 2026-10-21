"""The meta-shapes check the values of sh:name, sh:description, sh:order, sh:group and sh:defaultValue, and sh:PropertyGroup
(GitHub issues #12 and #16). SHACL 1.0 section 2.3.2: sh:name/sh:description are xsd:string or rdf:langString; sh:order has
at most one value, a decimal; sh:group names an sh:PropertyGroup. SHACL 1.2: at most one sh:defaultValue, a node expression."""

import pytest
from pyshacl.errors import ReportableRuntimeError
from rdflib import Graph
from starlayer.shacl.meta_shapes import meta_validate

P = (
    "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
    "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . "
    "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "
)


def _check(shapes_ttl: str) -> None:
    shapes = Graph()
    shapes.parse(data=P + shapes_ttl, format="turtle")
    meta_validate(shapes)


def _prop(body: str) -> str:
    return f"ex:S a sh:NodeShape ; sh:property [ sh:path ex:p ; {body} ] ."


VALID = {
    "name string": _prop('sh:name "first name"'),
    "name language string": _prop('sh:name "first name"@en'),
    "several names": _prop('sh:name "first name"@en, "Vorname"@de'),
    "description string": _prop('sh:description "The given name"'),
    "order integer": _prop("sh:order 1"),
    "order decimal": _prop("sh:order 1.5"),
    "order on a node shape": "ex:S a sh:NodeShape ; sh:order 2 .",
    "group": "ex:G a sh:PropertyGroup . " + _prop("sh:group ex:G"),
    "default value constant": _prop('sh:defaultValue "pending"'),
    "default value IRI": _prop("sh:defaultValue ex:open"),
    "default value expression": _prop("sh:defaultValue [ shnex:pathValues ex:q ]"),
    "property group": 'ex:G a sh:PropertyGroup ; rdfs:label "Identity"@en ; sh:order 1 .',
    "property group with two labels": 'ex:G a sh:PropertyGroup ; rdfs:label "Identity"@en, "Identität"@de .',
    "property group, no label": "ex:G a sh:PropertyGroup .",
}
INVALID = {
    "name integer": _prop("sh:name 5"),
    "name IRI": _prop("sh:name ex:n"),
    "name typed as something else": _prop('sh:name "x"^^xsd:token'),
    "description boolean": _prop("sh:description true"),
    "order string": _prop('sh:order "1"'),
    "order double": _prop("sh:order 1e0"),
    "two orders": _prop("sh:order 1, 2"),
    "group literal": _prop('sh:group "g"'),
    "group not a property group": _prop("sh:group ex:G"),
    "default value twice": _prop('sh:defaultValue "a", "b"'),
    "default value malformed expression": _prop("sh:defaultValue [ shnex:pathValuess ex:q ]"),
    "property group label integer": "ex:G a sh:PropertyGroup ; rdfs:label 5 .",
    "property group two orders": "ex:G a sh:PropertyGroup ; sh:order 1, 2 .",
    "property group literal order": 'ex:G a sh:PropertyGroup ; sh:order "first" .',
}


@pytest.mark.parametrize("ttl", VALID.values(), ids=VALID.keys())
def test_well_formed_usage_passes(ttl):
    _check(ttl)


@pytest.mark.parametrize("ttl", INVALID.values(), ids=INVALID.keys())
def test_malformed_usage_is_rejected(ttl):
    with pytest.raises(ReportableRuntimeError):
        _check(ttl)
