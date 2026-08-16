import pytest
from rdflib import Namespace
from starlayergraph.graph.starlayer_graph import StarLayerGraph
from starshacl import StarShaclValidator

EX = Namespace("http://example.org/")
SH = Namespace("http://www.w3.org/ns/shacl#")

pyshacl = pytest.importorskip("pyshacl")

# RDF 1.2's rdf:dirLangString (direction-tagged language strings, added to
# starlayergraph this session via StarLayerGraph's DirLangString) exposed a
# hard crash and three real correctness bugs once wired into starShacl:
#
# 1. Any data graph containing a DirLangString value crashed validate()
#    outright (AssertionError from TripleTermAdapter.encode_graph, which
#    didn't know about the new value type) - fixed in starshacl/adapters.py,
#    covered by tests/unit/test_adapters.py::test_round_trip_dirlangstring_value.
# 2. sh:datatype rdf:dirLangString (single-IRI form) always spuriously
#    failed via pySHACL, since a DirLangString is encoded internally as a
#    Literal with starlayergraph's own packing datatype URI, never the real
#    rdf:dirLangString URI.
# 3. sh:languageIn always spuriously failed for a DirLangString value, since
#    pySHACL's check keys off Literal.language, which is never set for one
#    (it's stored via datatype=, not lang=).
# 4. sh:uniqueLang silently missed genuine duplicates (two DirLangString
#    values sharing the same language AND direction), for the same reason -
#    pySHACL never even groups them by language at all.
#
# All four are native passes now (starshacl/validator.py); these tests cover
# 2-4 end-to-end. The existing list-valued sh:class/sh:datatype/sh:nodeKind
# native pass also gained DirLangString-awareness (_effective_datatype/
# _matches_any_datatype/_matches_node_kind) as part of the same fix.


def _validator() -> StarShaclValidator:
    return StarShaclValidator()


def _violation_components(result) -> list:
    return [o for _, _, o in result.report_graph.triples((None, SH.sourceConstraintComponent, None))]


def _data(ttl: str) -> StarLayerGraph:
    data = StarLayerGraph()
    data.parse(data=ttl, format="turtle12")
    return data


def _shapes(ttl: str) -> StarLayerGraph:
    shapes = StarLayerGraph()
    shapes.parse(data=ttl, format="turtle")
    return shapes


# --- sh:datatype rdf:dirLangString (single-IRI form) -----------------------


def test_datatype_dirlangstring_conforms_for_genuine_dirlangstring_value() -> None:
    data = _data(
        '@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl .'
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:datatype rdf:dirLangString ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True


def test_datatype_dirlangstring_violates_for_plain_string() -> None:
    data = _data('@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "hello" .')
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:datatype rdf:dirLangString ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert SH.DatatypeConstraintComponent in _violation_components(result)


def test_datatype_dirlangstring_decode_report_false_does_not_crash() -> None:
    data = _data('@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "hello" .')
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:datatype rdf:dirLangString ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False, decode_report=False)
    assert result.conforms is False


# --- sh:languageIn -----------------------------------------------------------


def test_language_in_matches_dirlangstring_by_real_language_tag() -> None:
    data = _data(
        '@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl .'
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:languageIn ( "ar" "en" ) ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True


def test_language_in_violates_for_dirlangstring_with_unlisted_language() -> None:
    data = _data(
        '@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl .'
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:languageIn ( "fr" "en" ) ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert SH.LanguageInConstraintComponent in _violation_components(result)


def test_language_in_still_matches_subtag_ranges_for_plain_lang_strings() -> None:
    # Regression guard: this native pass replaces pySHACL's own languageIn
    # check entirely, so plain (non-dirlang) subtag-range matching - already
    # correct via pySHACL - must keep working identically.
    data = _data('@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "hi"@en-US .')
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:languageIn ( "en" ) ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True


def test_language_in_violates_for_plain_string_with_no_language() -> None:
    data = _data('@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "hi" .')
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:languageIn ( "en" ) ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False


# --- sh:uniqueLang -----------------------------------------------------------


def test_unique_lang_flags_genuine_duplicate_same_language_and_direction() -> None:
    data = _data(
        """
        @prefix ex: <http://example.org/> .
        ex:Alice a ex:Person ; ex:greeting "marhaba"@ar--rtl, "ahlan"@ar--rtl .
        """
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:uniqueLang true ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert SH.UniqueLangConstraintComponent in _violation_components(result)


def test_unique_lang_allows_same_language_different_direction() -> None:
    # Spec's own example: "1"@ar--rtl and "1"@ar--ltr are different.
    data = _data(
        """
        @prefix ex: <http://example.org/> .
        ex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl, "marhaba"@ar--ltr .
        """
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:uniqueLang true ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True


def test_unique_lang_allows_same_language_with_and_without_direction() -> None:
    # Spec's own example: "1"@ar--rtl and "1"@ar are different.
    data = _data(
        """
        @prefix ex: <http://example.org/> .
        ex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl, "marhaba"@ar .
        """
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:uniqueLang true ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True


def test_unique_lang_still_flags_plain_language_duplicates() -> None:
    # Regression guard: this native pass replaces pySHACL's own uniqueLang
    # check entirely, so the plain (pre-existing, already-correct) case must
    # keep working identically - confirmed to match pySHACL's own violation
    # shape (one result per over-used tag, no sh:value).
    data = _data(
        """
        @prefix ex: <http://example.org/> .
        ex:Bob a ex:Person ; ex:greeting "Bob"@en, "Bobby"@en .
        """
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:uniqueLang true ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is False
    assert SH.UniqueLangConstraintComponent in _violation_components(result)


def test_unique_lang_string_literal_false_is_rejected_not_silently_enabled() -> None:
    """Found 2026-07-20 via the same audit that caught the analogous
    sh:closed "false" bug (see tests/integration/test_closed_by_types.py):
    UniqueLangConstraintComponent.__init__ used bare bool(value) instead of
    checking the literal's datatype - bool("false") is True in Python
    regardless of the string's content, so sh:uniqueLang "false" was
    silently *enabling* the check instead of disabling it. Now raises a
    clean ValueError instead.
    """
    data = _data(
        """
        @prefix ex: <http://example.org/> .
        ex:Bob a ex:Person ; ex:greeting "Bob"@en, "Bobby"@en .
        """
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:uniqueLang "false" ] .
        """
    )
    with pytest.raises(ValueError, match="xsd:boolean literal"):
        _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)


# --- list-valued sh:class/sh:datatype/sh:nodeKind gained DirLangString awareness too ----


def test_list_valued_datatype_recognizes_dirlangstring_member() -> None:
    data = _data(
        '@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl .'
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        @prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
        @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:datatype ( xsd:string rdf:dirLangString rdf:langString ) ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True


def test_list_valued_node_kind_recognizes_dirlangstring_as_literal() -> None:
    data = _data(
        '@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ; ex:greeting "مرحبا"@ar--rtl .'
    )
    shapes = _shapes(
        """
        @prefix ex: <http://example.org/> .
        @prefix sh: <http://www.w3.org/ns/shacl#> .
        ex:S a sh:NodeShape ; sh:targetClass ex:Person ;
          sh:property [ sh:path ex:greeting ; sh:nodeKind ( sh:Literal sh:IRI ) ] .
        """
    )
    result = _validator().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True
