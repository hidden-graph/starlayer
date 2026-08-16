import pytest
from starshacl.adapters import TripleTermValue
from starshacl.types import (
    ensure_graph_mutable,
    is_dirlangstring_like,
    is_triple_term_like,
)


class FakeTriple:
    def __init__(self) -> None:
        self.subject = "s"
        self.predicate = "p"
        self.object = "o"


class MissingObject:
    def __init__(self) -> None:
        self.subject = "s"
        self.predicate = "p"


def test_is_triple_term_like_for_value_object() -> None:
    assert is_triple_term_like(TripleTermValue("s", "p", "o")) is True


def test_is_triple_term_like_for_custom_object() -> None:
    assert is_triple_term_like(FakeTriple()) is True


def test_is_triple_term_like_false_for_incomplete_shape() -> None:
    assert is_triple_term_like(MissingObject()) is False


class FakeDirLangString:
    def __init__(self) -> None:
        self.value = "hello"
        self.language = "ar"
        self.direction = "rtl"


def test_is_dirlangstring_like_for_matching_shape() -> None:
    assert is_dirlangstring_like(FakeDirLangString()) is True


def test_is_dirlangstring_like_false_for_triple_term() -> None:
    # A DirLangString and a TripleTerm are structurally disjoint - neither
    # duck-type check should accept the other's shape.
    assert is_dirlangstring_like(TripleTermValue("s", "p", "o")) is False


def test_is_dirlangstring_like_false_for_plain_string() -> None:
    assert is_dirlangstring_like("just a string") is False


def test_is_dirlangstring_like_false_for_incomplete_shape() -> None:
    class MissingDirection:
        def __init__(self) -> None:
            self.value = "hello"
            self.language = "ar"

    assert is_dirlangstring_like(MissingDirection()) is False


class _FakeGraph:
    def __init__(self, *, mutable: bool = True) -> None:
        self.namespace_manager = object()
        self._triples: list = []
        self._mutable = mutable

    def __iter__(self):
        return iter(self._triples)

    def add(self, triple):
        self._triples.append(triple)
        return self

    def remove(self, pattern):
        return self


def test_ensure_graph_mutable_accepts_mutable_graph_like_object() -> None:
    ensure_graph_mutable(_FakeGraph(), name="data_graph")


def test_ensure_graph_mutable_rejects_non_iterable_non_namespaced_object() -> None:
    with pytest.raises(TypeError, match="must be a StarLayerGraph"):
        ensure_graph_mutable(object(), name="data_graph")


def test_ensure_graph_mutable_rejects_iterable_missing_add_remove() -> None:
    class IterableOnly:
        namespace_manager = object()

        def __iter__(self):
            return iter(())

    with pytest.raises(TypeError, match="must support mutable graph operations"):
        ensure_graph_mutable(IterableOnly(), name="data_graph")
