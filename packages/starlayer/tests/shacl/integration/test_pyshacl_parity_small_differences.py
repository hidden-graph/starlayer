"""Small differences from pySHACL that the adversarial hunt found (GitHub issues #50, #51, #52).

On SHACL 1.0 input StarLayer should give exactly pySHACL's answer unless a SHACL 1.2 change says otherwise. The oracle here is
pySHACL itself, run in a separate process that never imports starlayer (starlayer patches pySHACL process-wide).
"""

import json
import subprocess
import sys

import pytest
from rdflib import Graph, Namespace
from starlayer.shacl import validate

SH = Namespace("http://www.w3.org/ns/shacl#")
P = "@prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://ex/> . @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> . "

_ORACLE = """
import json, sys, warnings
warnings.simplefilter("ignore")
import pyshacl, rdflib
SH = rdflib.Namespace("http://www.w3.org/ns/shacl#")
shapes, data, options = json.load(sys.stdin)
conforms, rg, _ = pyshacl.validate(rdflib.Graph().parse(data=data, format="turtle"), shacl_graph=rdflib.Graph().parse(data=shapes, format="turtle"), **options)
out = []
for r in rg.subjects(SH.focusNode):
    out.append([str(rg.value(r, SH.focusNode)), str(rg.value(r, SH.sourceConstraintComponent)), str(rg.value(r, SH.resultSeverity)),
                sorted(str(m) for m in rg.objects(r, SH.resultMessage))])
print(json.dumps([bool(conforms), sorted(out)]))
"""


def _pyshacl(shapes: str, data: str, **options):
    done = subprocess.run([sys.executable, "-I", "-c", _ORACLE], input=json.dumps([P + shapes, P + data, options]), capture_output=True, text=True, check=True)
    conforms, results = json.loads(done.stdout)
    return conforms, [tuple(r[:3]) + (tuple(r[3]),) for r in results]


def _starlayer(shapes: str, data: str, **options):
    result = validate(Graph().parse(data=P + data, format="turtle"), Graph().parse(data=P + shapes, format="turtle"), meta_shacl=False, **options)
    g = result.report_graph
    out = [
        (str(g.value(r, SH.focusNode)), str(g.value(r, SH.sourceConstraintComponent)), str(g.value(r, SH.resultSeverity)), tuple(sorted(str(m) for m in g.objects(r, SH.resultMessage))))
        for r in g.subjects(SH.focusNode)
    ]
    return result.conforms, sorted(out)


def _same(shapes: str, data: str, **options) -> None:
    assert _starlayer(shapes, data, **options) == _pyshacl(shapes, data, **options)


# --- #50 language tags are case-insensitive, so 'x'@en and 'y'@EN are the same language
UNIQUE = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:uniqueLang true ] ."


@pytest.mark.parametrize(
    "values",
    ["'x'@en, 'y'@EN", "'x'@en, 'y'@en", "'x'@en, 'y'@de", "'x'@en-GB, 'y'@en-gb", "'x'@EN-gb, 'y'@en-GB, 'z'@en", "'x'@en, 'y'@en-GB", "'x'@fr, 'y'@FR, 'z'@FR"],
)
def test_unique_lang_compares_language_tags_without_regard_to_case(values) -> None:
    _same(UNIQUE, f"ex:a ex:p {values} .")


# --- #51 allowing warnings also allows infos (Info is below Warning)
SEVERITY = "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:q ; sh:minCount 1 ; sh:severity sh:{} ] ."
FLAGS = [{}, {"allow_infos": True}, {"allow_warnings": True}, {"allow_infos": True, "allow_warnings": True}]


@pytest.mark.parametrize("flags", FLAGS, ids=["none", "infos", "warnings", "both"])
@pytest.mark.parametrize("severity", ["Violation", "Warning", "Info"])
def test_allow_flags_decide_conformance_as_pyshacl_does(severity, flags) -> None:
    shapes, data = SEVERITY.format(severity), "ex:a ex:z 1 ."
    # all twelve combinations agree with pySHACL; with no flag an Info result blocks conformance in both
    assert _starlayer(shapes, data, **flags) == _pyshacl(shapes, data, **flags)


def test_allow_warnings_alone_lets_an_info_result_through() -> None:
    conforms, _ = _starlayer(SEVERITY.format("Info"), "ex:a ex:z 1 .", allow_warnings=True)
    assert conforms is True


# --- #52 the result messages of the replaced sh:closed, sh:languageIn and sh:uniqueLang components
@pytest.mark.parametrize(
    ("shapes", "data"),
    [
        ("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed true .", "ex:a ex:p 1 ."),
        ("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:closed true ; sh:ignoredProperties ( rdf:type ) ; sh:property [ sh:path ex:ok ] .", "ex:a ex:ok 1 ; ex:p 'v', 2 ; a ex:T ."),
        ("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:languageIn ( 'en' 'fr' ) ] .", "ex:a ex:p 'x'@en, 'y'@de, 'z' ."),
        ("ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:languageIn ( 'en' ) ] .", "ex:a ex:p 'x'@de ."),
        (UNIQUE, "ex:a ex:p 'x'@en, 'y'@en, 'z'@de ."),
    ],
    ids=["closed", "closed-with-ignored", "languageIn-several", "languageIn-one", "uniqueLang"],
)
def test_result_messages_are_pyshacls(shapes, data) -> None:
    expected_conforms, expected = _pyshacl(shapes, data)
    got_conforms, got = _starlayer(shapes, data)
    assert expected and all(r[3] for r in expected), "the oracle gives each of these results a message"
    assert (got_conforms, got) == (expected_conforms, expected)
