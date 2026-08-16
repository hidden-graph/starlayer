"""Regression suite for starShacl's own meta-shacl preflight
(``starshacl/meta_shapes.py``), which replaces reliance on pySHACL's own
``meta_shacl`` kwarg (confirmed to have no extension point - it always
validates against its own hardcoded, process-cached ``shacl-shacl.pickle``).

Two confirmed problems motivated this: 11 brand-new SHACL 1.2 predicates
were silently under-validated (no rule at all), and 8 shadowed predicates
whose value space SHACL 1.2 widened (list-valued sh:class/sh:datatype/
sh:nodeKind, path-valued sh:equals/sh:disjoint/sh:lessThan/
sh:lessThanOrEquals, sh:closed sh:ByTypes) were *actively rejected* by
pySHACL's still-SHACL-1.0/1.1-era bundled meta-shapes, under starShacl's
own default ``meta_shacl=True``.
"""

import pytest
from rdflib import Graph, Namespace
from starshacl import StarShaclValidator
from starshacl.meta_shapes import (
    _SHSH_SHAPE_SHAPE,
    _TOO_STRICT_PATHS,
    _load_pyshacl_base_meta_shapes,
    build_meta_shapes_graph,
    meta_validate,
)

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")


def _validate(data_ttl: str, shapes_ttl: str, **kwargs):
    data = Graph()
    data.parse(data=data_ttl, format="turtle")
    shapes = Graph()
    shapes.parse(data=shapes_ttl, format="turtle")
    return StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, **kwargs)


_TRIVIAL_DATA = "@prefix ex: <http://example.org/> . ex:r1 a ex:Record ."


# ---------------------------------------------------------------------------
# The 8 previously-actively-rejected shadowed-predicate forms - the
# regression-fix core of this suite. Each must now pass meta_shacl=True
# (the default) without raising, since starShacl's own components fully
# support these SHACL 1.2 forms.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "label,shapes_ttl",
    [
        (
            "list-valued sh:class",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:class ( ex:A ex:B ) .
            """,
        ),
        (
            "list-valued sh:datatype",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:datatype ( xsd:string xsd:integer ) ] .
            """,
        ),
        (
            "list-valued sh:nodeKind",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:nodeKind ( sh:IRI sh:Literal ) ] .
            """,
        ),
        (
            "path-valued sh:equals",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:equals ( ex:q ex:r ) ] .
            """,
        ),
        (
            "path-valued sh:disjoint",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:disjoint ( ex:q ex:r ) ] .
            """,
        ),
        (
            "path-valued sh:lessThan",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:lessThan ( ex:q ex:r ) ] .
            """,
        ),
        (
            "path-valued sh:lessThanOrEquals",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:lessThanOrEquals ( ex:q ex:r ) ] .
            """,
        ),
        (
            "sh:closed sh:ByTypes",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:closed sh:ByTypes .
            """,
        ),
    ],
)
def test_widened_shadowed_predicate_passes_default_meta_shacl(label, shapes_ttl) -> None:
    # The point here is that meta-shacl (the shapes-graph well-formedness
    # preflight) doesn't reject this SHACL 1.2 form - not that the trivial
    # data used happens to satisfy the resulting constraint too (real data
    # conformance for these predicates is already covered by
    # tests/integration/test_native_component_composition.py). A raised
    # exception before this line would mean meta-shacl rejected the shape;
    # reaching this line at all is the thing under test.
    _validate(_TRIVIAL_DATA, shapes_ttl)


# ---------------------------------------------------------------------------
# New SHACL 1.2 predicates: malformed usage is now caught (closing the
# silent-pass-through gap); well-formed usage still passes.
# ---------------------------------------------------------------------------


def test_malformed_unique_values_for_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueValuesFor "not a property" .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_malformed_min_list_length_now_caught_cleanly_not_a_raw_crash() -> None:
    """Previously this crashed with a raw, unhandled ``ValueError`` from
    the component's own __init__ (int("not-a-number")) since nothing
    caught it earlier - now the meta-shacl preflight rejects it first,
    with a clean SHACL-style report, before that component ever runs.
    """
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:minListLength "not-a-number" .
            """,
        )
    message = str(exc_info.value)
    assert "metashacl" in message.lower()
    assert "ValueError" not in message


def test_malformed_some_value_now_caught() -> None:
    with pytest.raises(Exception):
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:someValue "not a shape" ] .
            """,
        )


# ---------------------------------------------------------------------------
# The remaining 8 of the 11 new SHACL 1.2 predicates: previously had
# well-formed-usage coverage (below) but no malformed-usage regression test,
# despite the changelog's "malformed uses of the 11 new predicates now
# caught cleanly" claim - found via a test-coverage audit that specifically
# looked for this pattern (well-formed-only coverage masquerading as full
# coverage of a "done" row). Mirrors the three malformed-usage tests above.
# ---------------------------------------------------------------------------


def test_malformed_single_line_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:singleLine "not a boolean" ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_malformed_subset_of_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:subsetOf "not an IRI" ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_malformed_root_class_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:rootClass "not an IRI or a list" ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_malformed_member_shape_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:memberShape "not a shape" ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_member_shape_value_must_be_a_node_shape_not_a_property_shape() -> None:
    """Found 2026-08-01 by diffing against the official SHACL 1.2 WG draft
    meta-shapes (tests/vendor/shacl12-vocabularies/shacl-shacl.ttl) - it
    requires sh:memberShape's value conform to shsh:NodeShapeShape
    specifically, not shsh:ShapeShape generically (which also accepts a
    property shape). A property shape has no natural "does this node
    conform" semantics without an implicit sh:path, unlike a node shape.
    """
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:BadPropShapeMember a sh:PropertyShape ; sh:path ex:p .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:tags ; sh:memberShape ex:BadPropShapeMember ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_member_shape_value_as_a_node_shape_still_passes() -> None:
    # As with test_well_formed_new_predicate_usage_still_passes: the point
    # is that meta-shacl doesn't reject this well-formed shape - a raised
    # exception would mean meta-shacl rejected it.
    _validate(
        _TRIVIAL_DATA,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:GoodNodeShapeMember a sh:NodeShape .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:property [ sh:path ex:tags ; sh:memberShape ex:GoodNodeShapeMember ] .
        """,
    )


def test_malformed_max_list_length_now_caught_cleanly_not_a_raw_crash() -> None:
    """Mirrors ``test_malformed_min_list_length_now_caught_cleanly_not_a_raw_crash``:
    ``MaxListLengthConstraintComponent.__init__`` does the same unguarded
    ``int(...)`` coercion as ``MinListLengthConstraintComponent`` - without
    the meta-shacl preflight, a non-numeric value would raise a raw
    ``ValueError`` from inside the component instead of a clean SHACL-style
    meta-shacl report.
    """
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:maxListLength "not-a-number" .
            """,
        )
    message = str(exc_info.value)
    assert "metashacl" in message.lower()
    assert "ValueError" not in message


def test_malformed_unique_members_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueMembers "not a boolean" .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_malformed_reifier_shape_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:reifierShape "not a shape" ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_malformed_reification_required_now_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:reificationRequired "not a boolean" .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


# --- Gaps found and closed 2026-08-01 by diffing against the official
# SHACL 1.2 WG draft meta-shapes (tests/vendor/shacl12-vocabularies/
# shacl-shacl.ttl) - none of these are among the 11 new predicates the
# tests above cover; found only by comparison, not from this project's
# own spec reading. See docs/shacl12-gap-matrix.md's "Official SHACL 1.2
# meta-shapes (shsh:) comparison" section.


def test_data_graph_owl_imports_without_ontology_type_now_caught() -> None:
    """Mirrors the official draft's own shsh:DataGraphImportsShape (Info
    severity - a hint, not a hard rejection like the sh:Violation-severity
    tests above, but still enough to flip conforms=False under
    meta_validate's default disallow set, which - confirmed separately -
    already includes Info by default, matching SHACL 1.2's own stated
    default sh:conformanceDisallows set)."""
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            @prefix owl: <http://www.w3.org/2002/07/owl#> .
            ex:MyDataGraph a sh:DataGraph ; owl:imports ex:Other .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_data_graph_with_owl_ontology_type_passes() -> None:
    _validate(
        _TRIVIAL_DATA,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex:MyDataGraph a sh:DataGraph, owl:Ontology ; owl:imports ex:Other .
        """,
    )


def test_empty_sh_in_list_now_caught() -> None:
    """Mirrors the official draft's own shsh:inSubjectsShape (Warning
    severity - an unsatisfiable sh:in ()) can never match any value."""
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:in () ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_empty_sh_xone_list_now_caught() -> None:
    """Unlike sh:in above, this is Violation severity, not Warning like the
    official draft's own shsh:xoneSubjectsShape - pySHACL's own shape
    loader unconditionally rejects an empty sh:and/sh:or/sh:xone list with
    a raw ShapeLoadError the moment real validation runs, regardless of
    allow_warnings, so a Warning severity here would advertise a working
    opt-out that doesn't actually exist. See test_allow_warnings_below for
    the confirmation that allow_warnings genuinely works for sh:in but not
    sh:xone."""
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:xone () .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_empty_sh_xone_list_still_rejected_by_meta_shacl_even_with_allow_warnings() -> None:
    """Confirms the severity choice above is honest, and specifically that
    it's OUR meta-shacl preflight (not pySHACL's own independent
    ShapeLoadError, which fires regardless of severity and would make this
    test pass for the wrong reason) that's still rejecting it:
    allow_warnings=True does NOT let an empty sh:xone list through - it's
    Violation severity (never suppressible) here, not Warning like sh:in
    (see test_allow_warnings_on_validate_relaxes_warning_severity_meta_shacl_check,
    where allow_warnings genuinely does let sh:in () through). Asserting
    "metashacl" in the message - not just any Exception - is essential:
    without the severity fix, this same call still raises (pySHACL's own
    loader crashes independently), but with a plain ShapeLoadError that
    never mentions "metashacl" at all - confirmed by temporarily reverting
    the severity to sh:Warning and re-running this exact assertion, which
    then fails as expected.
    """
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:xone () .
            """,
            allow_warnings=True,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_non_empty_sh_in_and_xone_still_pass() -> None:
    _validate(
        _TRIVIAL_DATA,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:property [ sh:path ex:p ; sh:in ( "a" "b" ) ] ;
          sh:xone ( [ sh:property [ sh:path ex:p ] ] [ sh:property [ sh:path ex:q ] ] ) .
        """,
    )


def test_empty_sh_ignored_properties_now_caught() -> None:
    """Mirrors the official draft's own minListLength addition to
    sh:ignoredProperties - unlike sh:in/sh:xone above, this one has no
    severity override in the official draft either, so it's a hard
    sh:Violation like the malformed-predicate tests above, not a Warning."""
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:closed true ;
              sh:ignoredProperties () .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_empty_sh_language_in_now_caught() -> None:
    """Mirrors the official draft's own minListLength addition to
    sh:languageIn."""
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
              sh:property [ sh:path ex:p ; sh:languageIn () ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_non_empty_sh_ignored_properties_and_language_in_still_pass() -> None:
    _validate(
        _TRIVIAL_DATA,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:closed true ;
          sh:ignoredProperties ( rdf:type ) ;
          sh:property [ sh:path ex:p ; sh:languageIn ( "en" ) ] .
        """,
    )


@pytest.mark.parametrize(
    "label,shapes_ttl",
    [
        (
            "sh:uniqueValuesFor (IRI)",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueValuesFor ex:id .
            """,
        ),
        (
            "sh:someValue (real shape)",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Inner a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:minCount 1 ] .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:path ex:p ; sh:someValue ex:Inner ] .
            """,
        ),
        (
            "sh:minListLength (integer)",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:path ex:p ; sh:minListLength 2 ] .
            """,
        ),
        (
            "sh:reifierShape (real shape)",
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Inner a sh:NodeShape ; sh:property [ sh:path ex:q ; sh:minCount 1 ] .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:path ex:p ; sh:reifierShape ex:Inner ] .
            """,
        ),
    ],
)
def test_well_formed_new_predicate_usage_still_passes(label, shapes_ttl) -> None:
    # As above: the point is that meta-shacl doesn't reject a well-formed
    # shapes graph using these predicates, not that the trivial data
    # (which has no ex:p at all) happens to satisfy the resulting
    # constraint - a raised exception would mean meta-shacl rejected it.
    _validate(_TRIVIAL_DATA, shapes_ttl)


# ---------------------------------------------------------------------------
# Regression control: a genuinely malformed SHACL 1.0/1.1 shape must still
# be caught (no regression on pySHACL's own base coverage) - complements
# tests/integration/test_meta_shacl_integration.py's own coverage of this.
# ---------------------------------------------------------------------------


def test_genuinely_malformed_shacl_11_shape_still_caught() -> None:
    with pytest.raises(Exception) as exc_info:
        _validate(
            _TRIVIAL_DATA,
            """
            @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:minCount 1 ] .
            """,
        )
    assert "metashacl" in str(exc_info.value).lower()


def test_meta_shacl_false_still_skips_preflight_entirely() -> None:
    result = _validate(
        _TRIVIAL_DATA,
        """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueValuesFor "not a property" .
        """,
        meta_shacl=False,
    )
    assert result.conforms is True


def test_allow_infos_on_validate_relaxes_info_severity_meta_shacl_check() -> None:
    """meta_validate() itself already forwards allow_warnings/allow_infos
    to pySHACL correctly (it calls pyshacl.validate() directly, so pySHACL's
    own handling of these two kwargs applies unmodified) - the gap was
    validator.py's own call site never forwarding the caller's
    validate(..., allow_infos=...) through to meta_validate() at all. Uses
    the sh:DataGraph/owl:imports check (Info severity) as the probe."""
    shapes_ttl = """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix owl: <http://www.w3.org/2002/07/owl#> .
        ex:MyDataGraph a sh:DataGraph ; owl:imports ex:Other .
    """
    with pytest.raises(Exception) as exc_info:
        _validate(_TRIVIAL_DATA, shapes_ttl)
    assert "metashacl" in str(exc_info.value).lower()

    result = _validate(_TRIVIAL_DATA, shapes_ttl, allow_infos=True)
    assert result.conforms is True


def test_allow_warnings_on_validate_relaxes_warning_severity_meta_shacl_check() -> None:
    # sh:in (), not sh:xone () - an empty sh:xone list also trips pySHACL's
    # own separate "Shape-Expecting & List-Expecting predicate" shape-load
    # requirement once the meta-shacl preflight is relaxed past it, which
    # would fail this test for an unrelated reason. sh:in's value is an
    # ordinary value list, not a list-of-shapes, so it has no such
    # pySHACL-side load requirement.
    shapes_ttl = """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:path ex:p ; sh:in () ] .
    """
    with pytest.raises(Exception) as exc_info:
        _validate(_TRIVIAL_DATA, shapes_ttl)
    assert "metashacl" in str(exc_info.value).lower()

    result = _validate(_TRIVIAL_DATA, shapes_ttl, allow_warnings=True)
    assert result.conforms is True


# ---------------------------------------------------------------------------
# meta_shapes_extra extensibility hook - the "let other users/editors add
# their own rules" requirement, exercised end-to-end through the public
# StarShaclValidator.validate() API, not just at the graph-assembly level.
# ---------------------------------------------------------------------------


def test_meta_shapes_extra_hook_enforced_end_to_end() -> None:
    custom_rule = Graph()
    custom_rule.parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        [] a sh:NodeShape ;
          sh:targetClass sh:NodeShape ;
          sh:property [ sh:path rdfs:label ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    shapes_ttl = """
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record .
    """

    # Without the custom rule, this shape is perfectly well-formed.
    assert _validate(_TRIVIAL_DATA, shapes_ttl).conforms is True

    # With the custom rule (every NodeShape must carry rdfs:label), the
    # same shape is now caught as ill-formed by meta-shacl.
    with pytest.raises(Exception) as exc_info:
        _validate(_TRIVIAL_DATA, shapes_ttl, meta_shapes_extra=[custom_rule])
    assert "metashacl" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# build_meta_shapes_graph() / meta_validate() unit-level checks
# ---------------------------------------------------------------------------


def test_too_strict_base_triples_absent_from_assembled_graph() -> None:
    assembled = build_meta_shapes_graph()
    for path in _TOO_STRICT_PATHS:
        still_present = any(
            (_SHSH_SHAPE_SHAPE, SH.property, bn) in assembled and (bn, SH.path, path) in assembled
            for bn in assembled.objects(_SHSH_SHAPE_SHAPE, SH.property)
        )
        assert not still_present, f"{path} should have been stripped from the assembled graph"


def test_pyshacl_own_base_meta_shapes_never_mutated() -> None:
    build_meta_shapes_graph()  # exercise the assembly path once
    fresh_base = _load_pyshacl_base_meta_shapes()
    still_present = any(
        (_SHSH_SHAPE_SHAPE, SH.property, bn) in fresh_base and (bn, SH.path, SH["class"]) in fresh_base
        for bn in fresh_base.objects(_SHSH_SHAPE_SHAPE, SH.property)
    )
    assert still_present, "pySHACL's own base meta-shapes must be untouched by our assembly"


def test_meta_validate_raises_reportable_runtime_error_with_expected_message() -> None:
    from pyshacl.errors import ReportableRuntimeError

    shapes = Graph()
    shapes.parse(
        data="""
        @prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:property [ sh:minCount 1 ] .
        """,
        format="turtle",
    )
    with pytest.raises(ReportableRuntimeError) as exc_info:
        meta_validate(shapes)
    assert "SHACL File does not validate against the SHACL Shapes SHACL (MetaSHACL) file" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Well-formedness rules for SHACL 1.2 Rules / SPARQL Extensions predicates
# (sh:sparql, sh:rule, sh:condition, sh:ConstraintComponent) - previously
# had zero meta-shacl coverage at all, so a malformed use crashed with a
# raw exception (e.g. ConstraintLoadError/RuleLoadError) instead of a clean
# meta-shacl report. meta_validate() raises pyshacl.errors.
# ReportableRuntimeError on rejection (see the test above), not a returned
# conforms=False - every "malformed" case below asserts that raise.
# ---------------------------------------------------------------------------

_RULES_PREFIX = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
_RULES_PREFIX_SHNEX = _RULES_PREFIX + "@prefix shnex: <http://www.w3.org/ns/shacl-node-expr#> . "


class TestSparqlWellFormedness:
    def test_valid_sh_sparql_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:sparql [ sh:select "SELECT $this WHERE { FILTER NOT EXISTS { $this ex:email ?e } }" ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_sh_sparql_missing_select_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:sparql [ sh:message "oops" ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)


class TestRuleWellFormedness:
    def test_valid_triple_rule_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ; sh:object [ sh:path ex:q ] ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_triple_rule_missing_object_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_valid_sparql_rule_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this ex:x ex:y } WHERE {}" ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_sparql_rule_missing_construct_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:SPARQLRule ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)


def _triple_rule_shape(obj_expr: str, *, prefix: str = _RULES_PREFIX_SHNEX) -> str:
    return (
        prefix
        + f"""
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:p ; sh:object {obj_expr} ] .
        """
    )


class TestNodeExpressionWellFormedness:
    """stsh:NodeExpressionShape, wired into stsh:RuleShape's sh:subject/
    sh:predicate/sh:object checks - deliberately "shallow but broad": accepts
    any recognized top-level node-expression form (constant, a known sh:/
    shnex: defining predicate, or a structurally-shaped SHACL Function call)
    without recursing into the internal correctness of whichever form
    matched. See the rdfs:comment on stsh:NodeExpressionShape/
    stsh:NodeExpressionFunctionCallShape in shacl12-validation-shapes.ttl for
    the exact scope boundary, and docs/shacl12-gap-matrix.md.
    """

    @pytest.mark.parametrize(
        "label,obj_expr",
        [
            ("constant IRI", "ex:SomeConstant"),
            ("sh:this", "sh:this"),
            ("old sh:path form", "[ sh:path ex:q ]"),
            ("old sh:union form", "[ sh:union ( ex:a ex:b ) ]"),
            ("old sh:intersection form", "[ sh:intersection ( ex:a ex:b ) ]"),
            ("old sh:filterShape form", "[ sh:filterShape ex:SomeShape ; sh:nodes ( ex:a ) ]"),
            ("shnex:pathValues", "[ shnex:pathValues ex:q ]"),
            ("shnex:if", "[ shnex:if ( true ex:a ex:b ) ]"),
            ("shnex:concat", "[ shnex:concat ( ex:a ex:b ) ]"),
            ("shnex:count", "[ shnex:count ( ex:a ex:b ) ]"),
            ("shnex:instancesOf", "[ shnex:instancesOf ex:Class ]"),
            ("SHACL Function call", "[ ex:identity ( [ sh:path ex:says ] ) ]"),
        ],
    )
    def test_recognized_node_expression_forms_pass(self, label, obj_expr) -> None:
        shapes = Graph()
        shapes.parse(data=_triple_rule_shape(obj_expr), format="turtle")
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True, label

    def test_compound_path_expression_passes(self) -> None:
        # A real (non-trivial) property path exercises shsh:PathNodeShape's
        # own recursive grammar underneath stsh:NodeExpressionShape, not just
        # a bare IRI - also a regression guard for the max_validation_depth
        # bump in meta_shapes.meta_validate (this nesting previously tripped
        # pySHACL's "Validation path too deep!" guard at its 15 default).
        shapes = Graph()
        shapes.parse(
            data=_triple_rule_shape(
                "[ sh:path ( ex:a [ sh:inversePath ex:b ] [ sh:zeroOrMorePath ex:c ] ) ]"
            ),
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    @pytest.mark.parametrize(
        "label,obj_expr",
        [
            ("unknown predicate, no list object", "[ ex:bogusThing ex:x ]"),
            ("empty blank node", "[]"),
            ("typo'd shnex predicate", "[ shnex:pathValuess ex:q ]"),
            ("structurally invalid path", "[ sh:path [ sh:bogusPathKind ex:x ] ]"),
        ],
    )
    def test_malformed_node_expression_forms_are_rejected(self, label, obj_expr) -> None:
        shapes = Graph()
        shapes.parse(data=_triple_rule_shape(obj_expr), format="turtle")
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_real_function_call_fixture_still_works_end_to_end(self) -> None:
        # Not just meta-validation - the actual fixture already relied on by
        # tests/integration/test_shnex_node_expressions.py, run through the
        # full apply_rules() pipeline with meta_shacl=True, confirming the
        # new well-formedness rule doesn't reject real, working shapes.
        from starlayergraph.graph.starlayer_graph import StarLayerGraph

        from ._shape_loader import load_shape

        data = StarLayerGraph()
        data.parse(data="@prefix ex: <http://example.org/> . ex:alice ex:says \"hello\" .", format="turtle")

        shapes = StarLayerGraph()
        shapes.parse(data=load_shape("rdf12_node_expression_function.ttl"), format="turtle12")

        result = StarShaclValidator().apply_rules(data_graph=data, shacl_graph=shapes, meta_shacl=True)
        assert result.conforms is True
        derived = list(result.data_graph.triples((EX.alice, EX.derivedFn, None)))
        assert len(derived) == 1


class TestConditionWellFormedness:
    """sh:condition's value has a stricter requirement than sh:someValue/
    sh:memberShape/sh:reifierShape: unlike those three (auto-typed by
    starshacl.native_components.SHAPE_EXPECTING_PREDICATES before pySHACL
    runs), sh:condition's value is NOT auto-typed - pySHACL's own
    lookup_shape_from_node requires it to already be explicitly
    `a sh:NodeShape`/`a sh:PropertyShape`, confirmed via a live
    apply_rules() reproduction that raises RuleLoadError otherwise. The
    meta-shacl rule (stsh:ExplicitlyTypedShapeReferenceShape) mirrors that
    real runtime requirement exactly.
    """

    def test_explicitly_typed_condition_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:condition ex:AdultShape ;
                        sh:subject sh:this ; sh:predicate ex:p ; sh:object ex:v ] .
            ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_untyped_condition_passes_meta_validate_standalone(self) -> None:
        """meta_validate() called standalone (not through the full
        validate() pipeline) doesn't see the auto-typing injection that
        starshacl.validator.StarShaclValidator._ensure_native_component_shapes_typed()
        applies before meta-validation runs as part of a real validate()/
        apply_rules() call - so, exactly like sh:someValue/sh:memberShape/
        sh:reifierShape already do, an untyped reference here still
        vacuously conforms in isolation. That's fine: the real guarantee
        (an untyped sh:condition value works correctly, auto-typed
        transparently) is tested end-to-end via the full pipeline in
        tests/integration/test_rule_condition.py, not via this function in
        isolation - see that file's test_condition_shape_does_not_need_explicit_typing.
        """
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:condition ex:AdultShape ;
                        sh:subject sh:this ; sh:predicate ex:p ; sh:object ex:v ] .
            ex:AdultShape sh:class ex:Adult .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_reference_to_a_non_shape_vacuously_conforms_consistent_with_other_shape_referencing_predicates(
        self,
    ) -> None:
        """Known, accepted characteristic shared by all four shape-
        referencing predicates (sh:someValue/sh:memberShape/
        sh:reifierShape/sh:condition), not unique to sh:condition: pySHACL's
        own shsh:NodeShapeShape is entirely maxCount-0 "must not have"
        rules, so any IRI lacking real SHACL-specific structure vacuously
        satisfies stsh:ShapeReferenceShape regardless of whether it's an
        intentional shape. Not tightened further deliberately - a stricter
        check risks rejecting legitimately minimal/empty shapes, which are
        valid SHACL, and would make sh:condition inconsistent with the
        other three again.
        """
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:condition ex:NotAShape ;
                        sh:subject sh:this ; sh:predicate ex:p ; sh:object ex:v ] .
            ex:NotAShape a ex:SomeRandomClass .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_list_of_explicitly_typed_conditions_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:rule [ a sh:TripleRule ; sh:condition ( ex:AdultShape ex:ActiveShape ) ;
                        sh:subject sh:this ; sh:predicate ex:p ; sh:object ex:v ] .
            ex:AdultShape a sh:NodeShape ; sh:class ex:Adult .
            ex:ActiveShape a sh:NodeShape ; sh:hasValue ex:active .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True


class TestConstraintComponentWellFormedness:
    def test_valid_custom_constraint_component_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:MinScoreConstraintComponent a sh:ConstraintComponent ;
              sh:parameter [ sh:path ex:minScore ] ;
              sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK { FILTER (?value >= ?minScore) }" ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_constraint_component_missing_parameter_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:BadComponent a sh:ConstraintComponent ;
              sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK {}" ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_validator_missing_ask_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:BadComponent a sh:ConstraintComponent ;
              sh:parameter [ sh:path ex:minScore ] ;
              sh:validator [ a sh:SPARQLAskValidator ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_component_with_no_validator_form_at_all_is_rejected(self) -> None:
        """pySHACL's own make_validator_for_shape raises "Cannot select a
        validator to use, according to the rules" if none of
        sh:validator/sh:nodeValidator/sh:propertyValidator are present -
        previously uncaught by meta-shacl (only checked the *shape* of
        whichever validator form was present, not that one existed at all).
        """
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:BadComponent a sh:ConstraintComponent ;
              sh:parameter [ sh:path ex:minScore ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_component_with_node_validator_only_still_passes(self) -> None:
        """Confirms the at-least-one-validator check is a genuine OR, not
        an accidental requirement for sh:validator specifically.
        """
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:GoodComponent a sh:ConstraintComponent ;
              sh:parameter [ sh:path ex:minScore ] ;
              sh:nodeValidator [ a sh:SPARQLSelectValidator ; sh:select "SELECT $this WHERE {}" ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True


class TestShuiWellFormedness:
    """shui: (SHACL 1.2 User Interfaces) has zero data-validation semantics
    of its own, but its own predicates still have expected value shapes
    worth checking - scoped to the three predicates actually documented
    (shui:editor/shui:viewer/shui:propertyRole), all of which reference a
    named widget/role instance and so must be IRIs.
    """

    _SHUI_PREFIX = _RULES_PREFIX + "@prefix shui: <http://www.w3.org/ns/shacl-ui#> . "

    def test_valid_shui_editor_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=self._SHUI_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:birthDate ; shui:editor shui:DatePickerEditor ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_shui_editor_as_literal_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=self._SHUI_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:birthDate ; shui:editor "not-an-iri" ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_valid_shui_property_role_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=self._SHUI_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:name ; shui:propertyRole shui:LabelRole ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_shui_viewer_as_blank_node_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=self._SHUI_PREFIX
            + """
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:property [ sh:path ex:homepage ; shui:viewer [ a ex:SomeBlankThing ] ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)


class TestSparqlPrefixesWellFormedness:
    """sh:prefixes/sh:declare - confirmed functionally implemented
    (pyshacl.helper.sparql_query_helper.SPARQLQueryHelper.collect_prefixes())
    and confirmed working end-to-end through starShacl's full pipeline
    (tests/integration/test_sparql_shacl_integration.py). Unlike
    sh:resultAnnotation/sh:annotationProperty/etc. (confirmed to have zero
    implementation anywhere in pySHACL, not even its own consts.py
    predicate registry - so no meta-shacl rule was written for those, there
    being nothing to protect against).
    """

    def test_valid_prefixes_declaration_passes(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:PrefixSet sh:declare [ sh:prefix "myex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:sparql [ sh:prefixes ex:PrefixSet ; sh:select "SELECT $this WHERE {}" ] .
            """,
            format="turtle",
        )
        conforms, _report_graph, _report_text = meta_validate(shapes)
        assert conforms is True

    def test_declare_missing_namespace_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            ex:PrefixSet sh:declare [ sh:prefix "myex" ] .
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:sparql [ sh:prefixes ex:PrefixSet ; sh:select "SELECT $this WHERE {}" ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)

    def test_declare_prefix_wrong_datatype_is_rejected(self) -> None:
        shapes = Graph()
        shapes.parse(
            data=_RULES_PREFIX
            + """
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:PrefixSet sh:declare [ sh:prefix 42 ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
            ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
              sh:sparql [ sh:prefixes ex:PrefixSet ; sh:select "SELECT $this WHERE {}" ] .
            """,
            format="turtle",
        )
        with pytest.raises(pyshacl.errors.ReportableRuntimeError):
            meta_validate(shapes)
