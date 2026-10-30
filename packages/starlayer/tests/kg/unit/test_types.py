"""Unit tests for codekg.extractor.types.

Covers resolve_annotation_names(), has_none_member(), and
resolve_type_name() against small synthetic annotation snippets - never
against a real project file.
"""

import ast
import logging

from codekg.extractor.types import (
    has_none_member,
    resolve_annotation_names,
    resolve_type_name,
)


def _annotation(expr_source: str) -> ast.expr:
    """Parse a bare expression string into the ast.expr for an annotation,
    e.g. "tuple[str, str] | None"."""
    module = ast.parse(expr_source, mode="eval")
    return module.body


class TestResolveAnnotationNamesSimple:
    def test_bare_name(self):
        assert resolve_annotation_names(_annotation("Node")) == ["Node"]

    def test_attribute_chain(self):
        assert resolve_annotation_names(_annotation("rdflib.term.Literal")) == ["rdflib.term.Literal"]

    def test_two_level_attribute_chain(self):
        assert resolve_annotation_names(_annotation("rdflib.URIRef")) == ["rdflib.URIRef"]


class TestResolveAnnotationNamesUnions:
    def test_union_pipe_with_none(self):
        names = resolve_annotation_names(_annotation("str | None"))
        assert names == ["str"]

    def test_none_pipe_union(self):
        names = resolve_annotation_names(_annotation("None | str"))
        assert names == ["str"]

    def test_union_pipe_two_real_types(self):
        names = resolve_annotation_names(_annotation("str | int"))
        assert names == ["str", "int"]

    def test_optional_unwraps_without_emitting_optional_itself(self):
        names = resolve_annotation_names(_annotation("Optional[str]"))
        assert names == ["str"]
        assert "Optional" not in names

    def test_typing_dotted_optional_unwraps(self):
        names = resolve_annotation_names(_annotation("typing.Optional[str]"))
        assert names == ["str"]
        assert "typing.Optional" not in names


class TestResolveAnnotationNamesSubscripts:
    def test_tuple_subscript(self):
        names = resolve_annotation_names(_annotation("tuple[str, str]"))
        # deduplicated - "str" appears twice in source but once in result
        assert names == ["tuple", "str"]

    def test_dict_subscript_two_distinct_args(self):
        names = resolve_annotation_names(_annotation("dict[str, int]"))
        assert names == ["dict", "str", "int"]

    def test_tuple_str_str_none_combo(self):
        names = resolve_annotation_names(_annotation("tuple[str, str] | None"))
        assert names == ["tuple", "str"]

    def test_list_of_attribute_type(self):
        names = resolve_annotation_names(_annotation("list[rdflib.URIRef]"))
        assert names == ["list", "rdflib.URIRef"]


class TestHasNoneMember:
    def test_plain_type_has_no_none(self):
        assert has_none_member(_annotation("str")) is False

    def test_pipe_none_suffix(self):
        assert has_none_member(_annotation("str | None")) is True

    def test_pipe_none_prefix(self):
        assert has_none_member(_annotation("None | str")) is True

    def test_pipe_no_none(self):
        assert has_none_member(_annotation("str | int")) is False

    def test_optional_counts_as_none_member(self):
        assert has_none_member(_annotation("Optional[str]")) is True

    def test_dotted_optional_counts_as_none_member(self):
        assert has_none_member(_annotation("typing.Optional[str]")) is True

    def test_union_with_none_counts(self):
        assert has_none_member(_annotation("Union[str, None]")) is True

    def test_union_without_none_does_not_count(self):
        assert has_none_member(_annotation("Union[str, int]")) is False

    def test_tuple_subscript_without_none_is_false(self):
        assert has_none_member(_annotation("tuple[str, str]")) is False


class TestResolveTypeNameLocalClass:
    def test_bare_name_in_local_classes_wins(self):
        result = resolve_type_name("TripleTerm", {}, {"TripleTerm"})
        assert result == ("TripleTerm", True)

    def test_dotted_name_never_matches_local_classes(self):
        # resolve_type_name only checks bare (no-dot) names against
        # local_classes - a dotted name skips that check even if its
        # last component matches a local class name.
        result = resolve_type_name("other.TripleTerm", {}, {"TripleTerm"})
        assert result[1] is False


class TestResolveTypeNameBuiltins:
    def test_str_resolves_to_builtins_str(self):
        canonical, is_local = resolve_type_name("str", {}, set())
        assert canonical == "builtins.str"
        assert is_local is False

    def test_int_resolves_to_builtins_int(self):
        canonical, is_local = resolve_type_name("int", {}, set())
        assert canonical == "builtins.int"
        assert is_local is False


class TestResolveTypeNameRealExternal:
    def test_uriref_via_import_table_canonicalizes_through_rdflib_term(self):
        # "from rdflib import URIRef" -> import_table maps the bare name
        # URIRef -> "rdflib.URIRef"; live introspection should canonicalize
        # that through to URIRef's real defining module/qualname.
        import rdflib

        canonical, is_local = resolve_type_name("URIRef", {"URIRef": "rdflib.URIRef"}, set())
        assert is_local is False
        assert canonical == f"{rdflib.URIRef.__module__}.{rdflib.URIRef.__qualname__}"

    def test_dotted_rdflib_literal_written_directly_canonicalizes_same_as_import(self):
        # Someone wrote `rdflib.Literal` directly in an annotation without
        # importing bare `Literal` - "rdflib" isn't a bound simple name in
        # the import table, but it IS itself a real importable module, so
        # this should still resolve correctly via the fallback path.
        import rdflib

        canonical, _is_local = resolve_type_name("rdflib.Literal", {}, set())
        assert canonical == f"{rdflib.Literal.__module__}.{rdflib.Literal.__qualname__}"

    def test_import_table_and_direct_dotted_form_converge(self):
        # from rdflib.term import Literal (bound as "Literal") and writing
        # rdflib.Literal directly should converge on the SAME canonical
        # path - that's the whole point of live introspection here.
        via_import, _ = resolve_type_name("Literal", {"Literal": "rdflib.term.Literal"}, set())
        via_direct, _ = resolve_type_name("rdflib.Literal", {}, set())
        assert via_import == via_direct


class TestResolveTypeNameUnresolvable:
    def test_made_up_name_falls_back_gracefully_and_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="codekg.extractor.types"):
            canonical, is_local = resolve_type_name("TotallyMadeUpThing", {}, set())

        assert is_local is False
        assert canonical == "TotallyMadeUpThing"
        assert any("TotallyMadeUpThing" in record.message for record in caplog.records)

    def test_made_up_dotted_name_falls_back_gracefully_and_logs_warning(self, caplog):
        with caplog.at_level(logging.WARNING, logger="codekg.extractor.types"):
            canonical, is_local = resolve_type_name(
                "totally.fake.module.Thing", {}, set()
            )

        assert is_local is False
        assert canonical == "totally.fake.module.Thing"
        assert len(caplog.records) >= 1

    def test_unresolvable_via_import_table_still_falls_back(self, caplog):
        # import_table maps a bound name to a dotted path that doesn't
        # actually exist - resolution should still fail soft.
        with caplog.at_level(logging.WARNING, logger="codekg.extractor.types"):
            canonical, is_local = resolve_type_name(
                "Ghost", {"Ghost": "nonexistent_pkg_xyz.Ghost"}, set()
            )

        assert is_local is False
        assert canonical == "nonexistent_pkg_xyz.Ghost"
        assert len(caplog.records) >= 1

    def test_no_exception_raised(self):
        # Never raises, regardless of how unresolvable the input is.
        resolve_type_name("!!!not even a real identifier shape!!!", {}, set())
