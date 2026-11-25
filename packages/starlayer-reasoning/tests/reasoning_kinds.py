"""``raises_kind`` for the reasoning tests: ``pytest.raises(ExecutionError)`` that also asserts the error's ``kind`` (the core's own
copy is ``packages/starlayer/tests/support/errors.py``, not importable from here)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from starlayer.errors import ExecutionError


@contextmanager
def raises_kind(kind: str, match: str | None = None) -> Iterator[pytest.ExceptionInfo]:
    with pytest.raises(ExecutionError, match=match) as info:
        yield info
    assert info.value.kind == kind, f"expected an ExecutionError of kind {kind!r}, got {info.value.kind!r}: {info.value}"
