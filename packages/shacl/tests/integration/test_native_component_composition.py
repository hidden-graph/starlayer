"""Composition regression suite for native predicates migrated to real
pySHACL ``ConstraintComponent`` registration (``starshacl/native_components.py``).

Before this migration, native SHACL 1.2 predicates were evaluated outside
pySHACL and merged into the report afterward - correct in isolation, but
wrong whenever the predicate appeared inside ``sh:not``/``sh:and``/``sh:or``/
``sh:xone``, or combined with ``sh:deactivated``/``sh:severity`` (see
``docs/shacl12-gap-matrix.md``'s "Note on Architecture Direction", pattern
10, for the investigation and root cause).

Each case here is built so the *ignorant* answer (what you'd get if pySHACL
silently treated the migrated predicate as if it weren't there at all)
differs from the *correct* answer - not a case that would coincidentally
match either way. That's what makes these regression tests meaningful: a
case where both answers agree wouldn't catch a regression back to the old
merge-after behavior.
"""

import pytest
from rdflib import Graph, Literal, Namespace

from starshacl import StarShaclValidator


EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")


def _violation_components(result) -> set:
    return {o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))}


def _validate(data_ttl: str, shapes_ttl: str, **kwargs):
    data = Graph()
    data.parse(data=data_ttl, format="turtle")
    shapes = Graph()
    shapes.parse(data=shapes_ttl, format="turtle")
    return StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, **kwargs)


def _validate_rdf12(data_ttl12: str, shapes_ttl: str, **kwargs):
    # sh:reifierShape/sh:reificationRequired need real RDF-1.2 triple-term
    # identity (rdf:reifies), which only StarLayerGraph's turtle12 parser
    # produces - a plain rdflib.Graph can't represent it.
    from starlayergraph.graph.starlayergraph_graph import StarLayerGraph

    data = StarLayerGraph()
    data.parse(data=data_ttl12, format="turtle12")
    shapes = StarLayerGraph()
    shapes.parse(data=shapes_ttl, format="turtle")
    return StarShaclValidator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, **kwargs)


# alice has a cat, not a duck: sh:someValue(ex:Duck) directly VIOLATES.
_CAT_NOT_DUCK_DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice ex:pet ex:cat1 .
    ex:cat1 a ex:Cat .
"""

_SOME_VALUE_INNER = """
    sh:path ex:pet ;
    sh:someValue [ a sh:NodeShape ; sh:class ex:Duck ]
"""


def test_some_value_direct_violates_when_no_value_matches() -> None:
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ {_SOME_VALUE_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.SomeValueConstraintComponent in _violation_components(result)


def test_some_value_inside_not_conforms_via_double_negative() -> None:
    """Ignorant answer: pySHACL treats the inner property shape as having no
    real constraints (someValue unrecognized) -> it trivially conforms ->
    sh:not flips that to a violation -> conforms=False (WRONG). Correct
    answer: inner shape genuinely violates (no duck) -> sh:not flips that to
    conforms -> conforms=True.
    """
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:not [ {_SOME_VALUE_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_some_value_inside_and_still_violates() -> None:
    """Ignorant answer: inner shape trivially conforms (someValue
    unrecognized) -> sh:and conforms -> conforms=True (WRONG). Correct
    answer: inner shape genuinely violates -> sh:and violates too.
    """
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_SOME_VALUE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_some_value_inside_or_conforms_when_sibling_matches() -> None:
    """sh:or with one always-failing branch (someValue, no duck) and one
    always-passing branch (sh:minCount 0) should conform via the sibling -
    a regression here would mean the someValue branch broke the whole
    sh:or's evaluation path rather than just contributing correctly.
    """
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:AlwaysPasses a sh:NodeShape ; sh:property [ sh:path ex:nonexistent ; sh:minCount 0 ] .
        ex:SomeValueBranch a sh:NodeShape ; sh:property [ {_SOME_VALUE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:or ( ex:SomeValueBranch ex:AlwaysPasses ) .
        """,
    )
    assert result.conforms is True


def test_some_value_inside_xone_conforms_when_exactly_one_matches() -> None:
    """sh:xone: the someValue branch violates (no duck), the other branch
    conforms (alice does have a pet) -> exactly one of the two shapes
    conforms -> sh:xone itself conforms.
    """
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:HasAPet a sh:NodeShape ; sh:property [ sh:path ex:pet ; sh:minCount 1 ] .
        ex:SomeValueBranch a sh:NodeShape ; sh:property [ {_SOME_VALUE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:xone ( ex:SomeValueBranch ex:HasAPet ) .
        """,
    )
    assert result.conforms is True


def test_some_value_deactivated_conforms() -> None:
    """Ignorant/broken answer (pre-migration): sh:deactivated was never
    checked by the old merge-after pass -> conforms=False (WRONG). Correct
    answer: a deactivated shape contributes no violations.
    """
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:deactivated true ; {_SOME_VALUE_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_some_value_severity_warning_conforms_when_allowed() -> None:
    """Ignorant/broken answer (pre-migration): severity was hardcoded to
    sh:Violation for every native event, so allow_warnings had no effect ->
    conforms=False (WRONG). Correct answer: sh:severity sh:Warning +
    allow_warnings=True together mean the violation doesn't affect conforms.
    """
    result = _validate(
        _CAT_NOT_DUCK_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:severity sh:Warning ; {_SOME_VALUE_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:bob has an rdfs:label with an embedded line break: sh:singleLine(true)
# directly VIOLATES.
_MULTILINE_LABEL_DATA = """
    @prefix ex: <http://example.org/> .
    @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
    ex:bob rdfs:label "hello\\nworld" .
"""

_SINGLE_LINE_INNER = "sh:path rdfs:label ; sh:singleLine true"


def test_single_line_direct_violates_on_line_break() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ {_SINGLE_LINE_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.SingleLineConstraintComponent in _violation_components(result)


def test_single_line_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:not [ {_SINGLE_LINE_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_single_line_inside_and_still_violates() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_SINGLE_LINE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_single_line_inside_or_conforms_when_sibling_matches() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:AlwaysPasses a sh:NodeShape ; sh:property [ sh:path ex:nonexistent ; sh:minCount 0 ] .
        ex:SingleLineBranch a sh:NodeShape ; sh:property [ {_SINGLE_LINE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:or ( ex:SingleLineBranch ex:AlwaysPasses ) .
        """,
    )
    assert result.conforms is True


def test_single_line_inside_xone_conforms_when_exactly_one_matches() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:HasLabel a sh:NodeShape ; sh:property [ sh:path rdfs:label ; sh:minCount 1 ] .
        ex:SingleLineBranch a sh:NodeShape ; sh:property [ {_SINGLE_LINE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:xone ( ex:SingleLineBranch ex:HasLabel ) .
        """,
    )
    assert result.conforms is True


def test_single_line_deactivated_conforms() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ sh:deactivated true ; {_SINGLE_LINE_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_single_line_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _MULTILINE_LABEL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ sh:severity sh:Warning ; {_SINGLE_LINE_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_single_line_false_is_explicit_opt_out() -> None:
    """sh:singleLine false must remain a no-op (matches the SHACL 1.2 Core
    spec's own example), not accidentally start enforcing anything now that
    the predicate is a real, always-constructed pySHACL component.
    """
    result = _validate(
        _MULTILINE_LABEL_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ sh:path rdfs:label ; sh:singleLine false ] .
        """,
    )
    assert result.conforms is True


# ex:bob's favoriteChild (ex:alex) is not among his children (ex:sam):
# sh:subsetOf(ex:child) directly VIOLATES.
_NOT_A_SUBSET_DATA = """
    @prefix ex: <http://example.org/> .
    ex:bob ex:favoriteChild ex:alex ; ex:child ex:sam .
"""

_SUBSET_OF_INNER = "sh:path ex:favoriteChild ; sh:subsetOf ex:child"


def test_subset_of_direct_violates_when_not_a_subset() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ {_SUBSET_OF_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.SubsetOfConstraintComponent in _violation_components(result)


def test_subset_of_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:not [ {_SUBSET_OF_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_subset_of_inside_and_still_violates() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_SUBSET_OF_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_subset_of_inside_or_conforms_when_sibling_matches() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:AlwaysPasses a sh:NodeShape ; sh:property [ sh:path ex:nonexistent ; sh:minCount 0 ] .
        ex:SubsetOfBranch a sh:NodeShape ; sh:property [ {_SUBSET_OF_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:or ( ex:SubsetOfBranch ex:AlwaysPasses ) .
        """,
    )
    assert result.conforms is True


def test_subset_of_inside_xone_conforms_when_exactly_one_matches() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:HasFavoriteChild a sh:NodeShape ; sh:property [ sh:path ex:favoriteChild ; sh:minCount 1 ] .
        ex:SubsetOfBranch a sh:NodeShape ; sh:property [ {_SUBSET_OF_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:xone ( ex:SubsetOfBranch ex:HasFavoriteChild ) .
        """,
    )
    assert result.conforms is True


def test_subset_of_deactivated_conforms() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ sh:deactivated true ; {_SUBSET_OF_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_subset_of_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _NOT_A_SUBSET_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ sh:severity sh:Warning ; {_SUBSET_OF_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:zoo holds ex:rock, which is not an ex:Animal or any subclass of it:
# sh:rootClass(ex:Animal) directly VIOLATES.
_NOT_AN_ANIMAL_DATA = """
    @prefix ex: <http://example.org/> .
    ex:zoo ex:holds ex:rock .
"""

_ROOT_CLASS_INNER = "sh:path ex:holds ; sh:rootClass ex:Animal"


def test_root_class_direct_violates_when_not_a_subclass() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:property [ {_ROOT_CLASS_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.RootClassConstraintComponent in _violation_components(result)


def test_root_class_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:not [ {_ROOT_CLASS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_root_class_inside_and_still_violates() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_ROOT_CLASS_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_root_class_inside_or_conforms_when_sibling_matches() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:AlwaysPasses a sh:NodeShape ; sh:property [ sh:path ex:nonexistent ; sh:minCount 0 ] .
        ex:RootClassBranch a sh:NodeShape ; sh:property [ {_ROOT_CLASS_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:or ( ex:RootClassBranch ex:AlwaysPasses ) .
        """,
    )
    assert result.conforms is True


def test_root_class_inside_xone_conforms_when_exactly_one_matches() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:HoldsSomething a sh:NodeShape ; sh:property [ sh:path ex:holds ; sh:minCount 1 ] .
        ex:RootClassBranch a sh:NodeShape ; sh:property [ {_ROOT_CLASS_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:xone ( ex:RootClassBranch ex:HoldsSomething ) .
        """,
    )
    assert result.conforms is True


def test_root_class_deactivated_conforms() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:property [ sh:deactivated true ; {_ROOT_CLASS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_root_class_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _NOT_AN_ANIMAL_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:zoo ;
          sh:property [ sh:severity sh:Warning ; {_ROOT_CLASS_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:r1 and ex:r2 both have ex:id "dup": sh:uniqueValuesFor(ex:id) directly
# VIOLATES for both, when both are targeted together.
_DUPLICATE_ID_DATA = """
    @prefix ex: <http://example.org/> .
    ex:r1 a ex:Record ; ex:id "dup" .
    ex:r2 a ex:Record ; ex:id "dup" .
"""


def test_unique_values_for_direct_violates_on_duplicates() -> None:
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:uniqueValuesFor ex:id .
        """,
    )
    assert result.conforms is False
    violating = {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}
    assert violating == {EX.r1, EX.r2}


def test_unique_values_for_deactivated_conforms() -> None:
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:deactivated true ; sh:uniqueValuesFor ex:id .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:severity sh:Warning ; sh:uniqueValuesFor ex:id .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_unique_values_for_inside_and_correctly_detects_duplicate() -> None:
    """sh:and/sh:or/sh:xone/sh:not shadow pySHACL's own logical-operator
    components (see AndConstraintComponent's docstring in
    starshacl/native_components.py): when a nested shape declares
    sh:uniqueValuesFor (or any other cross-node predicate), it's invoked
    ONCE with the full batch of value nodes as focus - not one node at a
    time, pySHACL's own default - so it can genuinely compare candidates
    against each other. This used to vacuously conform (silently missing
    the real duplicate); it's now correctly data-sensitive.
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False
    violating = {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}
    assert violating == {EX.r1, EX.r2}


def test_unique_values_for_inside_and_conforms_when_no_duplicate() -> None:
    """Same shape as above, genuinely-unique data - proves the result is
    data-sensitive in both directions, not just "always violates now".
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "one" .
        ex:r2 a ex:Record ; ex:id "two" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_not_conforms_via_double_negative() -> None:
    """sh:not correctly inverts the now-accurate inner result: a genuine
    duplicate makes the inner shape violate, so sh:not flips that to
    conforms (double negative) - the opposite of the old vacuous-violates
    bug, and now data-sensitive (see the sibling test below for the flip).
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetNode ex:r1, ex:r2 ;
          sh:not ex:Inner .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_not_violates_when_no_duplicate() -> None:
    """Same sh:not shape, genuinely-unique data: the inner shape now
    conforms (no duplicate), so sh:not correctly flips that to a violation
    for both nodes - the mirror image of the test above, proving this is a
    real computation, not a fixed answer either way.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "one" .
        ex:r2 a ex:Record ; ex:id "two" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetNode ex:r1, ex:r2 ;
          sh:not ex:Inner .
        """,
    )
    assert result.conforms is False
    violating = {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}
    assert violating == {EX.r1, EX.r2}


def test_unique_values_for_inside_and_blank_node_inner_shape() -> None:
    """Same fix, but the nested shape is an anonymous blank node instead of
    a named IRI - confirms the full-batch branch doesn't depend on shape
    identity (matches how pySHACL's own get_other_shape() resolves either
    form identically).
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( [ sh:uniqueValuesFor ex:id ] ) .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_inside_and_two_properties_one_duplicated() -> None:
    """Two separate inner shapes, each checking a different property: id1
    is genuinely duplicated between Record2/Record3, id2 is not. sh:and
    requires both to be satisfied, so the real id1 duplicate must still be
    caught even though id2 alone would conform.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:Record2 a ex:Record ; ex:id1 "Two" ; ex:id2 "X" .
        ex:Record3 a ex:Record ; ex:id1 "Two" ; ex:id2 "Y" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner1 a sh:NodeShape ; sh:uniqueValuesFor ex:id1 .
        ex:Inner2 a sh:NodeShape ; sh:uniqueValuesFor ex:id2 .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( ex:Inner1 ex:Inner2 ) .
        """,
    )
    assert result.conforms is False
    # sh:and reports its own AndConstraintComponent violation, not the
    # child's specific component type - matches pySHACL's own existing
    # convention (it doesn't propagate a nested shape's own violation
    # details up through sh:and either).
    assert SH.AndConstraintComponent in _violation_components(result)


def test_unique_values_for_inside_or_conforms_via_ordinary_sibling() -> None:
    """Mixed sh:or: one branch is an ordinary (non-cross-node) shape that
    always passes, the other is a genuinely-violating sh:uniqueValuesFor
    branch. sh:or only needs one branch satisfied, so this should still
    conform via the ordinary sibling - confirms the "mixed" evaluation path
    (one full-batch shape alongside one per-node shape in the same list)
    combines them correctly rather than one clobbering the other.
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:AlwaysPasses a sh:NodeShape ; sh:property [ sh:path ex:nonexistent ; sh:minCount 0 ] .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:or ( ex:Inner ex:AlwaysPasses ) .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_xone_correctly_detects_duplicate() -> None:
    """sh:xone with a genuinely-violating sh:uniqueValuesFor branch and an
    always-failing ordinary sibling: exactly zero of the two branches
    conform, so sh:xone (needs exactly one) correctly violates.
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:AlwaysFails a sh:NodeShape ; sh:property [ sh:path ex:nonexistent ; sh:minCount 1 ] .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:xone ( ex:Inner ex:AlwaysFails ) .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_composition_does_not_affect_ordinary_and() -> None:
    """Parity check: an sh:and with no cross-node shape anywhere in it must
    still delegate to pySHACL's own unmodified AndConstraintComponent -
    confirms the branch condition doesn't accidentally divert ordinary
    composition onto the custom path.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:t1 a ex:Thing ; ex:a "x" ; ex:b "y" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:HasA a sh:NodeShape ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .
        ex:HasB a sh:NodeShape ; sh:property [ sh:path ex:b ; sh:minCount 1 ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:and ( ex:HasA ex:HasB ) .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_nested_and_two_levels_deep() -> None:
    """sh:and containing an sh:and containing the sh:uniqueValuesFor shape -
    two levels of composition before reaching the cross-node predicate. A
    shallow, one-level "does this shape directly declare it" check misses
    this (the middle shape doesn't declare sh:uniqueValuesFor itself, only
    something *it* composes does); the recursive/transitive detection
    (``_cross_node_reachable_shapes``) is what catches it.
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:Middle a sh:NodeShape ; sh:and ( ex:Inner ) .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( ex:Middle ) .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_inside_nested_and_two_levels_deep_no_duplicate() -> None:
    """Same two-level nesting as above, but with non-duplicate data - the
    data-sensitivity control for the case above."""
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "a" .
        ex:r2 a ex:Record ; ex:id "b" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:Middle a sh:NodeShape ; sh:and ( ex:Inner ) .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( ex:Middle ) .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_direct_node_correctly_detects_duplicate() -> None:
    """sh:node has the identical per-value-node recursion bug as the four
    logical operators (confirmed by reading pySHACL's
    NodeConstraintComponent._evaluate_node_shape) - and is the natural way
    to reference a sh:uniqueValuesFor-bearing shape, since sh:node's target
    must be a node shape."""
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:node ex:Inner .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_inside_direct_node_conforms_when_no_duplicate() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "a" .
        ex:r2 a ex:Record ; ex:id "b" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:node ex:Inner .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_via_property_path_then_node_correctly_detects_duplicate() -> None:
    """The real sh:property-adjacent manifestation of this bug: sh:property
    resolves a path to value nodes (pets, not the owner), which are then
    handed one at a time to the property shape's own sh:node - the focus
    node at the point of the nested check is the value node reached via the
    path, not the top-level owner. Patching sh:node covers this path too,
    without needing any special-casing for sh:property itself.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:petId "same" .
        ex:pet2 ex:petId "same" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PetShape a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShapePet a sh:PropertyShape ; sh:path ex:pet ; sh:node ex:PetShape .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ; sh:property ex:OwnerShapePet .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_via_property_path_then_node_conforms_when_no_duplicate() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:petId "a" .
        ex:pet2 ex:petId "b" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PetShape a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShapePet a sh:PropertyShape ; sh:path ex:pet ; sh:node ex:PetShape .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ; sh:property ex:OwnerShapePet .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_qualified_value_shape_correctly_detects_duplicate() -> None:
    """sh:qualifiedValueShape has the identical per-value-node recursion bug
    (confirmed by reading pySHACL's QualifiedValueShapeConstraintComponent.
    _evaluate_value_shape). With sh:qualifiedMinCount 2, both pets must
    conform to the inner shape for the property to conform - a real
    duplicate petId means Inner (correctly) says neither conforms, so the
    qualified count is 0, violating min count 2.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:petId "same" .
        ex:pet2 ex:petId "same" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [ sh:path ex:pet ; sh:qualifiedValueShape ex:Inner ; sh:qualifiedMinCount 2 ] .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_inside_qualified_value_shape_conforms_when_no_duplicate() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:petId "a" .
        ex:pet2 ex:petId "b" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [ sh:path ex:pet ; sh:qualifiedValueShape ex:Inner ; sh:qualifiedMinCount 2 ] .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_inside_and_via_node_mixed_mechanism_nesting() -> None:
    """sh:and containing a shape reached only via sh:node containing
    sh:uniqueValuesFor - composition mechanisms mixed at different levels
    of the same tree, not just repeated levels of the same operator.
    Confirms the transitive detection walks through *any* combination of
    _COMPOSITION_PREDICATES, not just same-predicate chains.
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:ViaNode a sh:NodeShape ; sh:node ex:Inner .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ;
          sh:and ( ex:ViaNode ) .
        """,
    )
    assert result.conforms is False


def test_plain_node_still_conforms_and_violates_correctly() -> None:
    """Parity check: sh:node with no cross-node shape anywhere in it must
    still behave exactly as plain sh:node always has - confirms the branch
    condition doesn't accidentally divert ordinary sh:node onto the custom
    path."""
    shapes = """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ sh:path ex:petId ; sh:minCount 1 ] .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [ sh:path ex:pet ; sh:node ex:Inner ] .
    """
    violating = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1 .
        ex:pet1 a ex:Pet .
        """,
        shapes,
    )
    assert violating.conforms is False

    conforming = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1 .
        ex:pet1 ex:petId "x" .
        """,
        shapes,
    )
    assert conforming.conforms is True


# ex:p1's ex:skills list has 0 members: sh:minListLength(1) directly VIOLATES.
_EMPTY_SKILLS_DATA = """
    @prefix ex: <http://example.org/> .
    ex:p1 ex:skills () .
"""

_MIN_LIST_LENGTH_INNER = "sh:path ex:skills ; sh:minListLength 1"


def test_min_list_length_direct_violates_when_too_short() -> None:
    result = _validate(
        _EMPTY_SKILLS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p1 ;
          sh:property [ {_MIN_LIST_LENGTH_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.MinListLengthConstraintComponent in _violation_components(result)


def test_min_list_length_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _EMPTY_SKILLS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p1 ;
          sh:not [ {_MIN_LIST_LENGTH_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_min_list_length_deactivated_conforms() -> None:
    result = _validate(
        _EMPTY_SKILLS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p1 ;
          sh:property [ sh:deactivated true ; {_MIN_LIST_LENGTH_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_min_list_length_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _EMPTY_SKILLS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p1 ;
          sh:property [ sh:severity sh:Warning ; {_MIN_LIST_LENGTH_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:p2's ex:hobbies list has 3 members: sh:maxListLength(2) directly VIOLATES.
_THREE_HOBBIES_DATA = """
    @prefix ex: <http://example.org/> .
    ex:p2 ex:hobbies ( "a" "b" "c" ) .
"""

_MAX_LIST_LENGTH_INNER = "sh:path ex:hobbies ; sh:maxListLength 2"


def test_max_list_length_direct_violates_when_too_long() -> None:
    result = _validate(
        _THREE_HOBBIES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p2 ;
          sh:property [ {_MAX_LIST_LENGTH_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.MaxListLengthConstraintComponent in _violation_components(result)


def test_max_list_length_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _THREE_HOBBIES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p2 ;
          sh:not [ {_MAX_LIST_LENGTH_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_max_list_length_deactivated_conforms() -> None:
    result = _validate(
        _THREE_HOBBIES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p2 ;
          sh:property [ sh:deactivated true ; {_MAX_LIST_LENGTH_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_max_list_length_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _THREE_HOBBIES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p2 ;
          sh:property [ sh:severity sh:Warning ; {_MAX_LIST_LENGTH_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:p3's ex:preferences list has a duplicate: sh:uniqueMembers(true) directly
# VIOLATES.
_DUPLICATE_PREFERENCES_DATA = """
    @prefix ex: <http://example.org/> .
    ex:p3 ex:preferences ( "x" "x" ) .
"""

_UNIQUE_MEMBERS_INNER = "sh:path ex:preferences ; sh:uniqueMembers true"


def test_unique_members_direct_violates_on_duplicate() -> None:
    result = _validate(
        _DUPLICATE_PREFERENCES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p3 ;
          sh:property [ {_UNIQUE_MEMBERS_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.UniqueMembersConstraintComponent in _violation_components(result)


def test_unique_members_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _DUPLICATE_PREFERENCES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p3 ;
          sh:not [ {_UNIQUE_MEMBERS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_unique_members_deactivated_conforms() -> None:
    result = _validate(
        _DUPLICATE_PREFERENCES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p3 ;
          sh:property [ sh:deactivated true ; {_UNIQUE_MEMBERS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_unique_members_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _DUPLICATE_PREFERENCES_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p3 ;
          sh:property [ sh:severity sh:Warning ; {_UNIQUE_MEMBERS_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_unique_members_false_is_explicit_opt_out() -> None:
    result = _validate(
        _DUPLICATE_PREFERENCES_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:p3 ;
          sh:property [ sh:path ex:preferences ; sh:uniqueMembers false ] .
        """,
    )
    assert result.conforms is True


# ex:agenda's ex:speakerOrder list has a non-IRI member ("not an iri"):
# sh:memberShape([ sh:nodeKind sh:IRI ]) directly VIOLATES.
_NON_IRI_MEMBER_DATA = """
    @prefix ex: <http://example.org/> .
    ex:agenda ex:speakerOrder ( ex:alice "not an iri" ) .
"""

_MEMBER_SHAPE_INNER = "sh:path ex:speakerOrder ; sh:memberShape [ a sh:NodeShape ; sh:nodeKind sh:IRI ]"


def test_member_shape_direct_violates_when_a_member_fails() -> None:
    result = _validate(
        _NON_IRI_MEMBER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:agenda ;
          sh:property [ {_MEMBER_SHAPE_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.MemberShapeConstraintComponent in _violation_components(result)


def test_member_shape_one_result_per_list_with_detail_per_bad_member() -> None:
    """Found 2026-07-31 via the W3C SHACL 1.2 test suite's memberShape-001
    fixture: MemberShapeConstraintComponent used to append one independent
    top-level sh:result *per non-conforming member*, blaming the same list
    each time (double-counting a single bad list as N violations), and
    discarded each member's own nested violation report entirely instead of
    nesting it under sh:detail. Now: exactly one sh:result per non-conforming
    list (sh:value the list itself), with one sh:detail entry per
    non-conforming member (that member's own violation against the
    referenced shape) - standard SHACL composite-constraint reporting, same
    as sh:and/sh:node.
    """
    data = """
        @prefix ex: <http://example.org/> .
        ex:agenda ex:speakerOrder ( "not an iri" "also not an iri" ex:alice ) .
    """
    shapes = f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:agenda ;
          sh:property [ {_MEMBER_SHAPE_INNER} ] .
    """
    result = _validate(data, shapes)

    assert result.conforms is False
    member_shape_results = [
        s
        for s, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))
        if o == SH.MemberShapeConstraintComponent
    ]
    assert len(member_shape_results) == 1, (
        f"expected exactly one sh:result for the one non-conforming list, got {len(member_shape_results)}"
    )
    (result_node,) = member_shape_results
    details = list(result.report_graph.objects(result_node, SH.detail))
    assert len(details) == 2, "expected one sh:detail per non-conforming member (two of the three)"
    detail_values = {o for d in details for _, _, o in result.report_graph.triples((d, SH.value, None))}
    assert detail_values == {Literal("not an iri"), Literal("also not an iri")}


def test_member_shape_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _NON_IRI_MEMBER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:agenda ;
          sh:not [ {_MEMBER_SHAPE_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_member_shape_inside_and_still_violates() -> None:
    result = _validate(
        _NON_IRI_MEMBER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_MEMBER_SHAPE_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:agenda ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_member_shape_deactivated_conforms() -> None:
    result = _validate(
        _NON_IRI_MEMBER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:agenda ;
          sh:property [ sh:deactivated true ; {_MEMBER_SHAPE_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_member_shape_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _NON_IRI_MEMBER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:agenda ;
          sh:property [ sh:severity sh:Warning ; {_MEMBER_SHAPE_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    # The outer sh:memberShape violation inherits the shape's own
    # sh:severity sh:Warning. Also present: the nested sh:detail result (the
    # failing member's own NodeKindConstraintComponent violation against the
    # anonymous inner shape, which has no severity override of its own, so
    # it keeps the default sh:Violation) - a *descriptive* sub-result, not an
    # independent top-level one, so it doesn't affect conforms itself
    # (correctly still True here).
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning, SH.Violation}


# ex:alice's ex:value "A" has no reifier at all: sh:reificationRequired(true)
# directly VIOLATES.
_NO_REIFIER_DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice ex:value "A" .
"""

_REIFICATION_REQUIRED_INNER = "sh:path ex:value ; sh:reificationRequired true"


def test_reification_required_direct_violates_when_no_reifier() -> None:
    result = _validate_rdf12(
        _NO_REIFIER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ {_REIFICATION_REQUIRED_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.ReifierShapeConstraintComponent in _violation_components(result)


def test_reification_required_inside_not_conforms_via_double_negative() -> None:
    result = _validate_rdf12(
        _NO_REIFIER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:not [ {_REIFICATION_REQUIRED_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_reification_required_inside_and_still_violates() -> None:
    result = _validate_rdf12(
        _NO_REIFIER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_REIFICATION_REQUIRED_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_reification_required_deactivated_conforms() -> None:
    result = _validate_rdf12(
        _NO_REIFIER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:deactivated true ; {_REIFICATION_REQUIRED_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_reification_required_severity_warning_conforms_when_allowed() -> None:
    result = _validate_rdf12(
        _NO_REIFIER_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:severity sh:Warning ; {_REIFICATION_REQUIRED_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:dog1 a ex:Dog with an ex:meows property that ex:Dog's sh:closed
# sh:ByTypes shape doesn't allow: directly VIOLATES.
_UNLISTED_DOG_PROPERTY_DATA = """
    @prefix ex: <http://example.org/> .
    ex:dog1 a ex:Dog ; ex:barks true ; ex:meows false .
"""

_CLOSED_BY_TYPES_SHAPE = """
    @prefix ex: <http://example.org/> .
    @prefix sh: <http://www.w3.org/ns/shacl#> .
    ex:Dog sh:closed sh:ByTypes ;
      sh:property [ sh:path ex:barks ] .
"""


def test_closed_by_types_direct_violates_on_unlisted_property() -> None:
    result = _validate(
        _UNLISTED_DOG_PROPERTY_DATA,
        _CLOSED_BY_TYPES_SHAPE
        + """
        ex:Dog sh:targetClass ex:Dog .
        """,
    )
    assert result.conforms is False
    assert SH.ClosedConstraintComponent in _violation_components(result)


def test_closed_by_types_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _UNLISTED_DOG_PROPERTY_DATA,
        _CLOSED_BY_TYPES_SHAPE
        + """
        ex:S a sh:NodeShape ; sh:targetClass ex:Dog ;
          sh:not ex:Dog .
        """,
    )
    assert result.conforms is True


def test_closed_by_types_inside_and_still_violates() -> None:
    result = _validate(
        _UNLISTED_DOG_PROPERTY_DATA,
        _CLOSED_BY_TYPES_SHAPE
        + """
        ex:S a sh:NodeShape ; sh:targetClass ex:Dog ;
          sh:and ( ex:Dog ) .
        """,
    )
    assert result.conforms is False


def test_closed_by_types_deactivated_conforms() -> None:
    result = _validate(
        _UNLISTED_DOG_PROPERTY_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:Dog a rdfs:Class, sh:NodeShape ; sh:targetClass ex:Dog ;
          sh:deactivated true ;
          sh:closed sh:ByTypes ;
          sh:property [ sh:path ex:barks ] .
        """,
    )
    assert result.conforms is True


def test_closed_by_types_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _UNLISTED_DOG_PROPERTY_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
        ex:Dog a rdfs:Class, sh:NodeShape ; sh:targetClass ex:Dog ;
          sh:severity sh:Warning ;
          sh:closed sh:ByTypes ;
          sh:property [ sh:path ex:barks ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_closed_plain_boolean_parity_still_violates_on_unlisted_property() -> None:
    """Parity check for the non-extended case: plain boolean sh:closed
    (not sh:ByTypes) must keep behaving exactly like pySHACL's own
    ClosedConstraintComponent, since the new component fully replaces
    pySHACL's dispatch entry for sh:closed/sh:ignoredProperties rather than
    adding a second one alongside it. Confirmed byte-for-byte equivalent to
    unregistered pySHACL's own behavior (including the well-known gotcha
    that rdf:type itself gets closed off unless explicitly allowed).
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:t1 ex:allowed "ok" ; ex:extra "bad" ; ex:ignoredOne "fine" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:closed true ;
          sh:ignoredProperties ( ex:ignoredOne ) ;
          sh:property [ sh:path ex:allowed ] .
        """,
    )
    assert result.conforms is False
    violations = _violation_components(result)
    assert violations == {SH.ClosedConstraintComponent}
    violating_paths = {o for _, _, o in result.report_graph.triples((None, SH.resultPath, None))}
    assert violating_paths == {EX.extra}


# ex:fluffy a ex:Unicorn - not in the list-valued sh:class(ex:Cat, ex:Dog):
# directly VIOLATES.
_UNLISTED_CLASS_DATA = """
    @prefix ex: <http://example.org/> .
    ex:fluffy a ex:Unicorn .
"""

_LIST_VALUED_CLASS_INNER = "sh:path ex:pet ; sh:class ( ex:Cat ex:Dog )"


def test_list_valued_class_direct_violates_for_unlisted_class() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:owner ex:pet ex:fluffy .
        ex:fluffy a ex:Unicorn .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:owner ;
          sh:property [ {_LIST_VALUED_CLASS_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH["ClassConstraintComponent"] in _violation_components(result)


def test_list_valued_class_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:owner ex:pet ex:fluffy .
        ex:fluffy a ex:Unicorn .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:owner ;
          sh:not [ {_LIST_VALUED_CLASS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_list_valued_class_deactivated_conforms() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:owner ex:pet ex:fluffy .
        ex:fluffy a ex:Unicorn .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:owner ;
          sh:property [ sh:deactivated true ; {_LIST_VALUED_CLASS_INNER} ] .
        """,
    )
    assert result.conforms is True


# ex:label "42" is xsd:integer, not among list-valued sh:datatype(xsd:string,
# rdf:langString): directly VIOLATES.
_LIST_VALUED_DATATYPE_INNER = "sh:path ex:label ; sh:datatype ( xsd:string rdf:langString )"


def test_list_valued_datatype_direct_violates_for_unlisted_datatype() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:t1 ex:label 42 .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:property [ {_LIST_VALUED_DATATYPE_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.DatatypeConstraintComponent in _violation_components(result)


def test_list_valued_datatype_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:t1 ex:label 42 .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:not [ {_LIST_VALUED_DATATYPE_INNER} ] .
        """,
    )
    assert result.conforms is True


# ex:bob knows a Literal, not among list-valued sh:nodeKind(sh:IRI,
# sh:BlankNode): directly VIOLATES.
_LIST_VALUED_NODE_KIND_INNER = "sh:path ex:knows ; sh:nodeKind ( sh:IRI sh:BlankNode )"


def test_list_valued_node_kind_direct_violates_for_literal() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:bob ex:knows "not a node" .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:property [ {_LIST_VALUED_NODE_KIND_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.NodeKindConstraintComponent in _violation_components(result)


def test_list_valued_node_kind_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:bob ex:knows "not a node" .
        """,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:bob ;
          sh:not [ {_LIST_VALUED_NODE_KIND_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_datatype_dirlangstring_direct_violates_for_plain_string() -> None:
    """Parity/extension check: sh:datatype rdf:dirLangString on a plain
    (non-DirLangString) value must still violate, and composes correctly.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:t1 ex:greeting "hello" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:property [ sh:path ex:greeting ; sh:datatype rdf:dirLangString ] .
        """,
    )
    assert result.conforms is False
    assert SH.DatatypeConstraintComponent in _violation_components(result)


# ex:t1's ex:label is "@fr", not in sh:languageIn("en"): directly VIOLATES.
_UNLISTED_LANGUAGE_DATA = """
    @prefix ex: <http://example.org/> .
    ex:t1 ex:label "bonjour"@fr .
"""

_LANGUAGE_IN_INNER = 'sh:path ex:label ; sh:languageIn ( "en" )'


def test_language_in_direct_violates_for_unlisted_language() -> None:
    result = _validate(
        _UNLISTED_LANGUAGE_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:property [ {_LANGUAGE_IN_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.LanguageInConstraintComponent in _violation_components(result)


def test_language_in_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _UNLISTED_LANGUAGE_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:not [ {_LANGUAGE_IN_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_language_in_deactivated_conforms() -> None:
    result = _validate(
        _UNLISTED_LANGUAGE_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:property [ sh:deactivated true ; {_LANGUAGE_IN_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_language_in_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _UNLISTED_LANGUAGE_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t1 ;
          sh:property [ sh:severity sh:Warning ; {_LANGUAGE_IN_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


# ex:t2's ex:label has two "@en"-tagged values: sh:uniqueLang(true) directly
# VIOLATES.
_DUPLICATE_LANG_DATA = """
    @prefix ex: <http://example.org/> .
    ex:t2 ex:label "hello"@en, "hi"@en .
"""

_UNIQUE_LANG_INNER = "sh:path ex:label ; sh:uniqueLang true"


def test_unique_lang_direct_violates_on_duplicate_language() -> None:
    result = _validate(
        _DUPLICATE_LANG_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t2 ;
          sh:property [ {_UNIQUE_LANG_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.UniqueLangConstraintComponent in _violation_components(result)


def test_unique_lang_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _DUPLICATE_LANG_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t2 ;
          sh:not [ {_UNIQUE_LANG_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_unique_lang_deactivated_conforms() -> None:
    result = _validate(
        _DUPLICATE_LANG_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t2 ;
          sh:property [ sh:deactivated true ; {_UNIQUE_LANG_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_unique_lang_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _DUPLICATE_LANG_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t2 ;
          sh:property [ sh:severity sh:Warning ; {_UNIQUE_LANG_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_unique_lang_false_is_explicit_opt_out() -> None:
    result = _validate(
        _DUPLICATE_LANG_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:t2 ;
          sh:property [ sh:path ex:label ; sh:uniqueLang false ] .
        """,
    )
    assert result.conforms is True


# ex:alice's ex:hasFriend/ex:hasFriend sequence path reaches ex:carol, but
# ex:knowsIndirectly is ex:dave: sh:equals(sequence path) directly VIOLATES.
_PATH_VALUED_EQUALS_DATA = """
    @prefix ex: <http://example.org/> .
    ex:alice ex:hasFriend ex:bob ; ex:knowsIndirectly ex:dave .
    ex:bob ex:hasFriend ex:carol .
"""

_PATH_VALUED_EQUALS_INNER = "sh:path ex:knowsIndirectly ; sh:equals ( ex:hasFriend ex:hasFriend )"


def test_path_valued_equals_direct_violates_on_mismatch() -> None:
    result = _validate(
        _PATH_VALUED_EQUALS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ {_PATH_VALUED_EQUALS_INNER} ] .
        """,
    )
    assert result.conforms is False
    assert SH.EqualsConstraintComponent in _violation_components(result)


def test_path_valued_equals_inside_not_conforms_via_double_negative() -> None:
    result = _validate(
        _PATH_VALUED_EQUALS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:not [ {_PATH_VALUED_EQUALS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_path_valued_equals_inside_and_still_violates() -> None:
    result = _validate(
        _PATH_VALUED_EQUALS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:property [ {_PATH_VALUED_EQUALS_INNER} ] .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:and ( ex:Inner ) .
        """,
    )
    assert result.conforms is False


def test_path_valued_equals_deactivated_conforms() -> None:
    result = _validate(
        _PATH_VALUED_EQUALS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:deactivated true ; {_PATH_VALUED_EQUALS_INNER} ] .
        """,
    )
    assert result.conforms is True


def test_path_valued_equals_severity_warning_conforms_when_allowed() -> None:
    result = _validate(
        _PATH_VALUED_EQUALS_DATA,
        f"""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:severity sh:Warning ; {_PATH_VALUED_EQUALS_INNER} ] .
        """,
        allow_warnings=True,
    )
    assert result.conforms is True
    severities = {o for _, _, o in result.report_graph.triples((None, SH.resultSeverity, None))}
    assert severities == {SH.Warning}


def test_path_valued_equals_simple_iri_still_delegates_correctly() -> None:
    """Parity check: a simple-IRI sh:equals value (the pre-existing SHACL
    1.0/1.1 form) must keep working via delegation to pySHACL's own
    component, not be broken by the presence of the path-valued case.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice ex:hasFriend ex:bob ; ex:sameAs ex:bob .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:path ex:sameAs ; sh:equals ex:hasFriend ] .
        """,
    )
    assert result.conforms is True


def test_path_valued_disjoint_direct_violates_on_overlap() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice ex:hasFriend ex:bob ; ex:knowsIndirectly ex:carol .
        ex:bob ex:hasFriend ex:carol .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:alice ;
          sh:property [ sh:path ex:knowsIndirectly ; sh:disjoint ( ex:hasFriend ex:hasFriend ) ] .
        """,
    )
    assert result.conforms is False
    assert SH.DisjointConstraintComponent in _violation_components(result)


def test_path_valued_less_than_or_equals_direct_violates() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:meeting1 ex:startTime 15 ; ex:relatedEvent ex:meeting2 .
        ex:meeting2 ex:endTime 10 .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetNode ex:meeting1 ;
          sh:property [ sh:path ex:startTime ; sh:lessThanOrEquals ( ex:relatedEvent ex:endTime ) ] .
        """,
    )
    assert result.conforms is False
    assert SH.LessThanOrEqualsConstraintComponent in _violation_components(result)


# ---------------------------------------------------------------------------
# Adversarial edge cases for the full-batch composition fix, added after a
# targeted review of test coverage. Two of these (the qualifiedValueShapes
# Disjoint sibling cases) caught a real bug: the branch condition deciding
# whether to take the full-batch path only checked the primary
# sh:qualifiedValueShape shape, never a disjoint *sibling* shape - so a
# cross-node predicate reached only through a sibling silently fell through
# to pySHACL's unpatched per-node path and was vacuously satisfied for every
# value, exactly the bug this whole fix exists to prevent. Fixed in
# QualifiedValueShapeConstraintComponent (_resolve_sibling_shapes/
# _needs_full_batch_for in starshacl/native_components.py).
# ---------------------------------------------------------------------------


def test_cross_node_reachability_terminates_on_pure_composition_cycle() -> None:
    """A<->B cycle in the composition graph with no cross-node predicate
    anywhere - the transitive-reachability DFS (_cross_node_reachable_shapes)
    must terminate via its own cycle guard rather than hang or recurse
    forever, independent of pySHACL's own separate shape-recursion guard.
    """
    from starshacl.native_components import _cross_node_reachable_shapes

    g = Graph()
    g.parse(
        data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:A a sh:NodeShape ; sh:and ( ex:B ) .
        ex:B a sh:NodeShape ; sh:and ( ex:A ) .
        """,
        format="turtle",
    )
    assert _cross_node_reachable_shapes(g) == frozenset()


def test_cross_node_reachability_correct_through_a_cycle() -> None:
    """Same cyclic shape graph as above, but C (reachable from the cycle)
    genuinely declares a cross-node predicate - confirms the cycle guard
    stops infinite recursion without also suppressing real reachability
    through the cyclic part of the graph.
    """
    from starshacl.native_components import _cross_node_reachable_shapes

    g = Graph()
    g.parse(
        data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:C a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:A a sh:NodeShape ; sh:and ( ex:B ex:C ) .
        ex:B a sh:NodeShape ; sh:and ( ex:A ) .
        """,
        format="turtle",
    )
    reachable = _cross_node_reachable_shapes(g)
    assert EX.A in reachable
    assert EX.B in reachable
    assert EX.C in reachable


def test_cross_node_reachability_correct_through_a_cycle_regardless_of_hash_seed() -> None:
    """The bug the test above was written to catch turned out to only
    manifest under specific ``PYTHONHASHSEED`` values (a DFS+memo
    implementation memoized a node's answer using its cycle guard's early
    ``False`` return, which is unsound and order-dependent - fixed by
    replacing it with fixed-point/worklist propagation, which is order-
    independent by construction). A single in-process run can't exercise
    more than one hash seed, so this drives the same check across several
    fixed seeds in subprocesses - the actual regression-catching test for
    this bug, not just the single-seed case above.
    """
    import os
    import subprocess
    import sys

    script = (
        "from rdflib import Graph, Namespace\n"
        "from starshacl.native_components import _cross_node_reachable_shapes\n"
        "EX = Namespace('http://example.org/')\n"
        "g = Graph()\n"
        "g.parse(data='''\n"
        "    @prefix ex: <http://example.org/> .\n"
        "    @prefix sh: <http://www.w3.org/ns/shacl#> .\n"
        "    ex:C a sh:NodeShape ; sh:uniqueValuesFor ex:id .\n"
        "    ex:A a sh:NodeShape ; sh:and ( ex:B ex:C ) .\n"
        "    ex:B a sh:NodeShape ; sh:and ( ex:A ) .\n"
        "''', format='turtle')\n"
        "result = _cross_node_reachable_shapes(g)\n"
        "assert {EX.A, EX.B, EX.C} == result, result\n"
    )
    for seed in ("0", "1", "6", "13", "42", "1000"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run(
            [sys.executable, "-c", script],
            env=env,
            check=False,
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0, f"seed={seed}: {proc.stderr}"


def test_cross_node_reachability_terminates_on_self_cycle() -> None:
    from starshacl.native_components import _cross_node_reachable_shapes

    g = Graph()
    g.parse(
        data="""
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Z a sh:NodeShape ; sh:and ( ex:Z ) .
        """,
        format="turtle",
    )
    assert _cross_node_reachable_shapes(g) == frozenset()


def test_qualified_max_count_with_cross_node_value_shape_conforms_via_vacuous_exclusion() -> None:
    """sh:qualifiedMaxCount, not just sh:qualifiedMinCount, must route
    through the full-batch path. With max count 1 and a real duplicate
    petId, the cross-node inner shape correctly says *neither* pet
    conforms (0 <= max 1), so this conforms - the opposite answer from the
    no-duplicate case below, proving it's data-sensitive.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:petId "same" .
        ex:pet2 ex:petId "same" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [ sh:path ex:pet ; sh:qualifiedValueShape ex:Inner ; sh:qualifiedMaxCount 1 ] .
        """,
    )
    assert result.conforms is True


def test_qualified_max_count_with_cross_node_value_shape_violates_when_both_conform() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:petId "a" .
        ex:pet2 ex:petId "b" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [ sh:path ex:pet ; sh:qualifiedValueShape ex:Inner ; sh:qualifiedMaxCount 1 ] .
        """,
    )
    assert result.conforms is False


def test_unique_values_for_via_node_deactivated_outer_conforms_despite_duplicate() -> None:
    """sh:deactivated on the shape that carries sh:node (not the inner
    cross-node shape itself) must still short-circuit the whole check -
    confirms sh:node's shadow component didn't accidentally bypass
    Shape.validate()'s own generic sh:deactivated handling.
    """
    result = _validate(
        _DUPLICATE_ID_DATA,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:deactivated true ; sh:node ex:Inner .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_via_property_node_conforms_with_zero_value_nodes() -> None:
    """An owner with no pets at all - the full-batch path must handle an
    empty value-node set gracefully (no crash, no spurious violation),
    not just the "at least one value" cases exercised elsewhere.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:PetShape a sh:NodeShape ; sh:uniqueValuesFor ex:petId .
        ex:OwnerShapePet a sh:PropertyShape ; sh:path ex:pet ; sh:node ex:PetShape .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ; sh:property ex:OwnerShapePet .
        """,
    )
    assert result.conforms is True


def test_unique_values_for_via_node_self_reference_warns_instead_of_hanging() -> None:
    """A shape that both declares sh:uniqueValuesFor (triggering the
    full-batch path) and references itself via sh:node - genuine shape
    recursion reached through the *new* full-batch mechanism, not the
    logical operators. Must still raise ShapeRecursionWarning and stop
    (matching pySHACL's own recursion handling), not hang or crash - and
    the cross-node check itself must still be evaluated correctly despite
    the self-reference short-circuiting.
    """
    with pytest.warns(Warning, match="[Rr]ecursi"):
        result = _validate(
            _DUPLICATE_ID_DATA,
            """
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:Inner a sh:NodeShape ; sh:uniqueValuesFor ex:id ; sh:node ex:Inner .
            ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:node ex:Inner .
            """,
        )
    assert result.conforms is False


def test_two_independent_cross_node_shapes_in_and_list_do_not_cross_contaminate() -> None:
    """Two unrelated sh:uniqueValuesFor shapes (different properties) in
    the same sh:and list, each violated by a different pair of records -
    confirms the full-batch violation sets are tracked and combined
    per-shape, not merged into one undifferentiated pool that could
    over- or under-report which records actually violate.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "dup1" ; ex:code "c1" .
        ex:r2 a ex:Record ; ex:id "dup1" ; ex:code "c2" .
        ex:r3 a ex:Record ; ex:id "u3" ; ex:code "dup2" .
        ex:r4 a ex:Record ; ex:id "u4" ; ex:code "dup2" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:InnerA a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:InnerB a sh:NodeShape ; sh:uniqueValuesFor ex:code .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:and ( ex:InnerA ex:InnerB ) .
        """,
    )
    assert result.conforms is False
    focus_nodes = {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}
    assert focus_nodes == {EX.r1, EX.r2, EX.r3, EX.r4}


def test_multi_valued_node_two_independent_cross_node_shapes_do_not_cross_contaminate() -> None:
    """Same idea as the sh:and case above but for multi-valued sh:node -
    a shape can have more than one sh:node triple (AND semantics across all
    of them, evaluated in NodeConstraintComponent's own per-node_shape loop,
    a different code path than sh:and's list evaluation). Two independent
    sh:uniqueValuesFor shapes, each reached via its own sh:node triple, each
    violated by a different pair of records - confirms the two independent
    full-batch calls (one per node_shape) don't interfere with each other.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "dup1" ; ex:code "c1" .
        ex:r2 a ex:Record ; ex:id "dup1" ; ex:code "c2" .
        ex:r3 a ex:Record ; ex:id "u3" ; ex:code "dup2" .
        ex:r4 a ex:Record ; ex:id "u4" ; ex:code "dup2" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:InnerA a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:InnerB a sh:NodeShape ; sh:uniqueValuesFor ex:code .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:node ex:InnerA ; sh:node ex:InnerB .
        """,
    )
    assert result.conforms is False
    focus_nodes = {o for _, _, o in result.report_graph.triples((None, SH.focusNode, None))}
    assert focus_nodes == {EX.r1, EX.r2, EX.r3, EX.r4}


def test_multi_valued_node_two_independent_cross_node_shapes_conform_when_no_duplicate() -> None:
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:r1 a ex:Record ; ex:id "a" ; ex:code "w" .
        ex:r2 a ex:Record ; ex:id "b" ; ex:code "x" .
        ex:r3 a ex:Record ; ex:id "c" ; ex:code "y" .
        ex:r4 a ex:Record ; ex:id "d" ; ex:code "z" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:InnerA a sh:NodeShape ; sh:uniqueValuesFor ex:id .
        ex:InnerB a sh:NodeShape ; sh:uniqueValuesFor ex:code .
        ex:S a sh:NodeShape ; sh:targetClass ex:Record ; sh:node ex:InnerA ; sh:node ex:InnerB .
        """,
    )
    assert result.conforms is True


def test_qualified_value_shapes_disjoint_with_cross_node_sibling_conforms_via_duplicate() -> None:
    """The bug this test caught: sh:qualifiedValueShapesDisjoint's sibling
    check invokes the *sibling* shape per-value too (in pySHACL's own
    unmodified _evaluate_value_shape), so a cross-node predicate reached
    only through a sibling - not the primary sh:qualifiedValueShape - needs
    the same full-batch treatment. Before the fix, the branch condition
    only checked the primary shape, so this sibling's sh:uniqueValuesFor
    silently ran through the vacuous per-node path and every pet
    "conformed" to it regardless of real duplicate status, making this
    incorrectly violate no matter what the data said.

    Setup: both pets are adults (conform to the primary shape ex:Adult)
    and share the same altId (so the sibling ex:UniqueAlt, correctly
    full-batch-evaluated, says *neither* conforms to it). Disjoint means a
    pet counts toward Adult's qualifiedMinCount only if it does NOT also
    conform to the sibling - since neither conforms to UniqueAlt, both
    count toward Adult, satisfying qualifiedMinCount 1.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:age 5 ; ex:altId "same" .
        ex:pet2 ex:age 5 ; ex:altId "same" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Adult a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:minInclusive 1 ] .
        ex:UniqueAlt a sh:NodeShape ; sh:uniqueValuesFor ex:altId .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [
            sh:path ex:pet ;
            sh:qualifiedValueShape ex:Adult ;
            sh:qualifiedMinCount 1 ;
            sh:qualifiedValueShapesDisjoint true
          ] ;
          sh:property [ sh:path ex:pet ; sh:qualifiedValueShape ex:UniqueAlt ; sh:qualifiedMinCount 0 ] .
        """,
    )
    assert result.conforms is True


def test_qualified_value_shapes_disjoint_with_cross_node_sibling_violates_when_excluded() -> None:
    """Data-sensitivity control for the case above: both pets have distinct
    altId, so both correctly conform to the (full-batch-evaluated) sibling
    ex:UniqueAlt, and disjoint excludes both from Adult's count - 0 < min
    count 1, violating.
    """
    result = _validate(
        """
        @prefix ex: <http://example.org/> .
        ex:alice a ex:Owner ; ex:pet ex:pet1, ex:pet2 .
        ex:pet1 ex:age 5 ; ex:altId "a" .
        ex:pet2 ex:age 5 ; ex:altId "b" .
        """,
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:Adult a sh:NodeShape ; sh:property [ sh:path ex:age ; sh:minInclusive 1 ] .
        ex:UniqueAlt a sh:NodeShape ; sh:uniqueValuesFor ex:altId .
        ex:OwnerShape a sh:NodeShape ; sh:targetClass ex:Owner ;
          sh:property [
            sh:path ex:pet ;
            sh:qualifiedValueShape ex:Adult ;
            sh:qualifiedMinCount 1 ;
            sh:qualifiedValueShapesDisjoint true
          ] ;
          sh:property [ sh:path ex:pet ; sh:qualifiedValueShape ex:UniqueAlt ; sh:qualifiedMinCount 0 ] .
        """,
    )
    assert result.conforms is False
