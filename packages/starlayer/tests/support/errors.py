"""Test helper for the one ``ExecutionError`` class: ``raises_kind("nesting")`` is ``pytest.raises(ExecutionError)`` that also
asserts which ``kind`` the error carries, so a test cannot pass on a failure of another kind."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from starlayer.shacl import ExecutionError


@contextmanager
def raises_kind(kind: str, match: str | None = None) -> Iterator[pytest.ExceptionInfo]:
    with pytest.raises(ExecutionError, match=match) as info:
        yield info
    assert info.value.kind == kind, f"expected an ExecutionError of kind {kind!r}, got {info.value.kind!r}: {info.value}"
