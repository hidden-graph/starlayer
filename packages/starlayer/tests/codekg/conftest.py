"""Fixtures shared by the code-KG tests: the code graph is large, so it is loaded once per run, not once per module."""

from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def codekg_dataset():
    """``codekg.trig`` plus the curated files, loaded once (about 15 s). Read it; never change it."""
    from starlayer.codekg import get_codekg_dataset

    return get_codekg_dataset(include_curated=True)
