"""test_update_hunt3: the tests that need behaviour OxGraph does not have (TypeError for a non-str query / update)."""

import pytest
from starlayer.graph import StarLayerDataset, StarLayerGraph


@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_update_and_query_of_none_raise_type_error(make):
    obj = make()
    with pytest.raises(TypeError):
        obj.update(None)
    with pytest.raises(TypeError):
        obj.query(None)


@pytest.mark.parametrize("bad", [5, 1.5, b"ASK {}", ["ASK {}"], object()])
@pytest.mark.parametrize("make", [StarLayerGraph, StarLayerDataset])
def test_update_and_query_of_a_non_string_raise_type_error_naming_the_type(make, bad):
    # Was AttributeError: object has no attribute algebra (issue #139).
    obj = make()
    with pytest.raises(TypeError, match=type(bad).__name__):
        obj.update(bad)
    with pytest.raises(TypeError, match=type(bad).__name__):
        obj.query(bad)
