"""Fourth round of SHACL fixes (GitHub issues #82, #94, #104, #131, #136): each test fails on the code before the fix.

Where plain pySHACL is the oracle it is run in a separate interpreter (``python -I``) so StarLayer's process-global patches
cannot colour the answer."""

import subprocess
import sys
import textwrap

import pytest
from rdflib import Namespace, URIRef
from rdflib.namespace import SH
from starlayer import StarLayerGraph
from starlayer.shacl import StarShaclSchema, apply_rules, extract_subgraph, validate
from starlayer.shacl.shape_types import infer_types
from starlayer.shacl.xpath_regex import needs_translation, xpath_regex_to_python

EX = Namespace("http://example.org/")
P = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "


def _graph(ttl: str) -> StarLayerGraph:
    graph = StarLayerGraph()
    graph.parse(data=ttl, format="turtle12")
    return graph


def _plain_pyshacl(shapes: str, data: str) -> str:
    """'True'/'False' (conforms) or the exception class name, from plain pySHACL in a fresh interpreter."""
    code = textwrap.dedent(
        """
        import sys, pyshacl
        from rdflib import Graph
        shapes, data = sys.argv[1], sys.argv[2]
        try:
            print(pyshacl.validate(Graph().parse(data=data, format="turtle"), shacl_graph=Graph().parse(data=shapes, format="turtle"))[0])
        except Exception as exc:
            print(type(exc).__name__)
        """
    )
    out = subprocess.run([sys.executable, "-I", "-c", code, shapes, data], capture_output=True, text=True, timeout=120)
    return out.stdout.strip().splitlines()[-1]


# --- close_shape / extract_subgraph ------------------------------------------------------------------------------------


@pytest.mark.parametrize(("keyword", "q_min"), [("or", 1), ("xone", 1), ("and", 0)])
def test_closed_form_accepts_the_fragment_of_a_logical_shape(keyword, q_min):
    shapes = _graph(
        P + f"ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:{keyword} ([sh:property [sh:path ex:p ; sh:minCount 1]] "
        f"[sh:property [sh:path ex:q ; sh:minCount {q_min}]]) ."
    )
    data = _graph(P + "ex:n a ex:C ; ex:p 1 ; ex:z 2 .")
    fragment = extract_subgraph(data, shapes)
    assert len(fragment) > 0
    closed = StarShaclSchema(shacl_graph=shapes).close_shape(EX.S)
    assert validate(fragment, closed, meta_shacl=False).conforms
    # the closed form is still strict: the whole data graph (with ex:z) does not conform
    assert not validate(data, closed, meta_shacl=False).conforms


def test_closed_form_accepts_the_fragment_of_complex_paths_and_equals():
    shapes = _graph(
        P + "ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [sh:path ex:p ; sh:equals ex:q] ; "
        "sh:property [sh:path (ex:r ex:s) ; sh:minCount 1] ."
    )
    data = _graph(P + "ex:n a ex:C ; ex:p 1 ; ex:q 1 ; ex:r ex:m ; ex:z 2 . ex:m ex:s 3 .")
    fragment = extract_subgraph(data, shapes)
    closed = StarShaclSchema(shacl_graph=shapes).close_shape(EX.S)
    assert validate(fragment, closed, meta_shacl=False).conforms


def test_extract_subgraph_of_a_deactivated_shape_is_empty():
    shapes = _graph(P + "ex:D a sh:NodeShape ; sh:deactivated true ; sh:targetClass ex:C ; sh:property [sh:path ex:q ; sh:minCount 1] .")
    data = _graph(P + "ex:a a ex:C ; ex:q 2 .")
    assert len(extract_subgraph(data, shapes, shape=EX.D)) == 0
    assert len(extract_subgraph(data, shapes)) == 0


# --- infer_types -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "ttl",
    [
        "ex:S sh:targetClass ex:C ; sh:property [sh:path ex:p ; sh:node ex:T ; sh:minCount 1] .",
        "ex:S sh:targetClass ex:C ; sh:or ( ex:A ex:B ) . ex:A sh:path ex:q .",
    ],
)
def test_infer_types_is_idempotent_and_never_types_vocabulary_terms(ttl):
    graph = _graph(P + ttl)
    first = infer_types(graph)
    assert len(first) > 0
    for triple in first:
        graph.add(triple)
    assert len(infer_types(graph)) == 0
    assert not [s for s, _p, _o in first if str(s).startswith(str(SH))]


# --- rules -------------------------------------------------------------------------------------------------------------

_DECLARE = '<http://ex/> sh:declare [ sh:prefix "ex" ; sh:namespace "http://ex/"^^<http://www.w3.org/2001/XMLSchema#anyURI> ] . '
_NO_BINDING_DATA = "<http://ex/q> <http://ex/r> <http://ex/s> ."


def test_global_sparql_rule_resolves_its_own_sh_prefixes_not_the_data_graphs_bindings():
    shapes = _graph(
        P
        + _DECLARE
        + '<http://ex/R> a sh:SPARQLRule ; sh:prefixes <http://ex/> ; sh:construct "CONSTRUCT { ex:g ex:made ex:c } WHERE { }" .'
    )
    result = apply_rules(_graph(_NO_BINDING_DATA), shacl_graph=shapes)
    assert (URIRef("http://ex/g"), URIRef("http://ex/made"), URIRef("http://ex/c")) in result.inferred_graph


@pytest.mark.parametrize(
    "construct",
    ["CONSTRUCT { ?s <http://ex/p> ?o WHERE { ?s ?p ?o }", "CONSTRUCT { ?s zz:p ?o } WHERE { ?s ?p ?o }"],
)
def test_global_sparql_rule_with_a_bad_construct_raises(construct):
    from pyshacl.errors import RuleLoadError

    shapes = _graph(P + f'<http://ex/R> a sh:SPARQLRule ; sh:construct "{construct}" .')
    with pytest.raises(RuleLoadError, match="could not be run"):
        apply_rules(_graph(_NO_BINDING_DATA), shacl_graph=shapes)


@pytest.mark.parametrize("form", ["SELECT * WHERE { ?s ?p ?o }", "ASK { ?s ?p ?o }"])
def test_global_sparql_rule_with_a_non_construct_query_raises_a_clear_error(form):
    from pyshacl.errors import RuleLoadError

    shapes = _graph(P + f'<http://ex/R> a sh:SPARQLRule ; sh:construct "{form}" .')
    with pytest.raises(RuleLoadError, match="must be a CONSTRUCT query"):
        apply_rules(_graph(_NO_BINDING_DATA), shacl_graph=shapes)


# --- validate() over composite inverse paths ---------------------------------------------------------------------------

_INVERSE_DATA = ":a :p :b . :b :q :c . :x :p :b ."
_INVERSE_PREFIX = "@prefix : <http://ex/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
_INVERSE_SHAPES = (
    ":S a sh:NodeShape ; sh:targetNode :c ; sh:property [ sh:path [ sh:inversePath ( :p :q ) ] ; sh:hasValue :a ] ."
)


def test_validate_follows_an_inverse_of_a_sequence_path():
    conforms = validate(
        _graph(_INVERSE_PREFIX + _INVERSE_DATA), _graph(_INVERSE_PREFIX + _INVERSE_SHAPES), meta_shacl=False
    ).conforms
    assert conforms
    # plain pySHACL follows nothing for this path: the answer comes from our patch, not from pySHACL
    assert _plain_pyshacl(_INVERSE_PREFIX + _INVERSE_SHAPES, _INVERSE_PREFIX + _INVERSE_DATA) == "False"


def test_validate_inverse_of_a_sequence_still_reports_a_missing_value():
    shapes = _INVERSE_SHAPES.replace("sh:hasValue :a", "sh:hasValue :nobody")
    assert not validate(_graph(_INVERSE_PREFIX + _INVERSE_DATA), _graph(_INVERSE_PREFIX + shapes), meta_shacl=False).conforms


# --- sh:pattern: XPath regular expressions ------------------------------------------------------------------------------

_PATTERN_SHAPES = P + 'ex:S a sh:NodeShape ; sh:targetNode ex:n ; sh:property [sh:path ex:p ; sh:pattern "{pattern}"] .'


def _pattern_conforms(pattern: str, value: str) -> bool:
    escaped = pattern.replace("\\", "\\\\")
    return validate(_graph(P + f'ex:n ex:p "{value}" .'), _graph(_PATTERN_SHAPES.format(pattern=escaped))).conforms


@pytest.mark.parametrize(
    ("pattern", "value", "expected"),
    [
        (r"^\p{L}+$", "é", True),
        (r"^\p{Lu}$", "é", False),
        (r"^\P{L}$", "1", True),
        (r"^[\p{L}\d]+$", "é1", True),
        (r"^\p{IsBasicLatin}+$", "abc", True),
        (r"^\p{IsBasicLatin}+$", "é", False),
        (r"^\i\c*$", "a-b", True),
        (r"^\i\c*$", "1a", False),
        (r"^[a-z-[aeiou]]+$", "bcd", True),
        (r"^[a-z-[aeiou]]+$", "bad", False),
    ],
)
def test_sh_pattern_accepts_xpath_only_syntax(pattern, value, expected):
    assert _pattern_conforms(pattern, value) is expected


def test_plain_pyshacl_has_the_same_limit_so_it_is_not_a_starlayer_variance():
    shapes = _PATTERN_SHAPES.format(pattern=r"^\\p{L}+$")
    assert _plain_pyshacl(shapes, P + 'ex:n ex:p "é" .') == "error"  # re.error: bad escape \p


@pytest.mark.parametrize("pattern", [r"^\p{Foo}$", r"^\p{IsFoo}$", "("])
def test_sh_pattern_that_cannot_be_translated_raises_a_clear_error(pattern):
    from pyshacl.errors import ConstraintLoadError

    with pytest.raises(ConstraintLoadError, match="sh:pattern"):
        _pattern_conforms(pattern, "a")


def test_translation_leaves_patterns_without_xpath_syntax_untouched():
    for pattern in [r"^[a-z]+\d*$", r"\\p", "a|b", r"[\[\]]"]:
        assert not needs_translation(pattern)
        assert xpath_regex_to_python(pattern) == pattern


def test_sh_sparql_on_a_triple_term_value_does_not_see_the_support_triples():
    # Pinned: the unverified #94 item did not reproduce on main; this keeps it so.
    shapes = _graph(
        P
        + 'ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:node ex:T ] . '
        + 'ex:T a sh:NodeShape ; sh:sparql [ sh:message "has properties" ; sh:select "SELECT $this WHERE { $this ?p ?o }" ] .'
    )
    data = _graph(P + "ex:a ex:p <<( ex:x ex:y ex:z )>> .")
    assert validate(data, shapes).conforms


# --- reifier results -----------------------------------------------------------------------------------------------------


def test_reifier_shape_violation_carries_a_result_message():
    shapes = _graph(
        P
        + "ex:S a sh:NodeShape ; sh:targetNode ex:a ; sh:property [ sh:path ex:p ; sh:reificationRequired true ] ."
    )
    result = validate(_graph(P + "ex:a ex:p ex:o ."), shapes)
    assert not result.conforms
    messages = [str(m) for m in result.report_graph.objects(None, SH.resultMessage)]
    assert messages and "reifier" in messages[0]
