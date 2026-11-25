"""The shapes-about-shapes check is strict: a result of any severity (Violation, Warning, Info), the SHACL 1.2 Core default set, makes
the shapes graph invalid, and nothing tolerates one. ``meta_validate()`` takes no ``allow_warnings`` / ``allow_infos``, and a processor
with ``meta_shacl=True`` ignores its own for this check (they describe the data validation), so the processor, ``meta_validate()`` and
pySHACL's meta check give one answer. The graphs: a warning only, an info note only, a valid one."""

from __future__ import annotations

import pytest
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl import MetaShaclError, StarShaclProcessor, meta_validate, validate

SH_RESULT_SEVERITY = "http://www.w3.org/ns/shacl#resultSeverity"
PRE = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . "
DATA = "@prefix ex: <http://example.org/> . ex:a a ex:Record ."

GRAPHS = {
    "warning only": "ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:minCountt 1 .",
    # shsh:DataGraphImportsShape: owl:imports without the type owl:Ontology is an Info note
    "info only": "ex:G a sh:DataGraph ; owl:imports ex:Other .",
    "valid": "ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:path ex:p ; sh:minCount 1 ] .",
}
INVALID = {"warning only": "Warning", "info only": "Info"}


def shapes(name: str) -> Graph:
    return Graph().parse(data=PRE + GRAPHS[name], format="turtle")


def meta_answer(name: str) -> bool:
    try:
        return bool(meta_validate(shapes(name)).conforms)
    except MetaShaclError:
        return False


def processor_answer(name: str, **options) -> bool:
    try:
        StarShaclProcessor(shacl_graph=shapes(name), meta_shacl=True, ignore_imports=True, **options)
    except MetaShaclError:
        return False
    return True


@pytest.mark.parametrize("name", GRAPHS)
def test_the_processor_and_meta_validate_agree_whatever_the_processor_allows(name) -> None:
    expected = name == "valid"
    assert meta_answer(name) is expected
    for options in ({}, {"allow_warnings": True}, {"allow_infos": True}, {"allow_warnings": True, "allow_infos": True}, {"allow_warnings": False}):
        assert processor_answer(name, **options) is expected, options


@pytest.mark.parametrize("name", GRAPHS)
def test_a_call_option_does_not_relax_the_check_either(name) -> None:
    def run():
        return validate(Graph().parse(data=DATA, format="turtle"), shapes(name), meta_shacl=True, allow_warnings=True, allow_infos=True, ignore_imports=True)

    if name == "valid":
        run()  # the meta check passes (the data itself is another question)
    else:
        with pytest.raises(MetaShaclError):
            run()


@pytest.mark.parametrize("name", INVALID)
def test_a_warning_or_info_raises_with_the_prefixed_problem_and_the_result_in_the_report(name) -> None:
    severity = INVALID[name]
    with pytest.raises(MetaShaclError) as error:
        meta_validate(shapes(name))
    assert error.value.problems and all(p.startswith(f"{severity}: ") for p in error.value.problems)
    import pyoxigraph as ox

    assert any(str(o.value).endswith("#" + severity) for o in error.value.report_graph.objects(None, ox.NamedNode(SH_RESULT_SEVERITY)))
    assert f"{severity} in" in error.value.report_text


def test_the_warning_names_the_unknown_term() -> None:
    with pytest.raises(MetaShaclError) as error:
        meta_validate(shapes("warning only"))
    assert error.value.problems == ("Warning: ex:S: sh:minCountt is not a term of the SHACL vocabulary",)


def test_a_valid_graph_returns_a_conforming_report() -> None:
    outcome = meta_validate(shapes("valid"))
    conforms = outcome.conforms
    report = outcome.report_graph
    text = outcome.report_text
    assert conforms is True and "Conforms: True" in text


@pytest.mark.parametrize("option", ["allow_warnings", "allow_infos"])
def test_meta_validate_has_no_way_to_tolerate_a_severity(option) -> None:
    with pytest.raises(TypeError):
        meta_validate(shapes("warning only"), **{option: True})


def test_the_scoped_form_is_strict_too() -> None:
    from starlayer.graph import StarLayerGraph

    base = shapes("valid")
    import pyoxigraph as ox

    s = ox.NamedNode("http://example.org/S")
    bad = (s, ox.NamedNode("http://www.w3.org/ns/shacl#minCountt"), ox.Literal("1", datatype=ox.NamedNode("http://www.w3.org/2001/XMLSchema#integer")))
    assert isinstance(base, StarLayerGraph)
    with pytest.raises(MetaShaclError):
        meta_validate(base, add=[bad])
