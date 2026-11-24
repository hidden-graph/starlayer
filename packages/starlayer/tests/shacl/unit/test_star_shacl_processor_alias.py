"""``StarShaclSchema`` is the deprecated alias of ``StarShaclProcessor``."""

import importlib

import pytest
import starlayer
import starlayer.shacl
import starlayer.shacl.validator
from starlayer.shacl import StarShaclProcessor

pytestmark = pytest.mark.shacl

MESSAGE = "StarShaclSchema is renamed StarShaclProcessor"
MODULES = ["starlayer", "starlayer.shacl", "starlayer.shacl.validator"]


@pytest.mark.parametrize("module_name", MODULES)
def test_alias_warns_and_is_the_same_class(module_name):
    module = importlib.import_module(module_name)
    with pytest.warns(DeprecationWarning, match=MESSAGE) as record:
        alias = module.StarShaclSchema
    assert alias is StarShaclProcessor
    assert record[0].filename == __file__


def test_from_import_warns():
    with pytest.warns(DeprecationWarning, match=MESSAGE):
        from starlayer.shacl import StarShaclSchema
    assert issubclass(StarShaclSchema, StarShaclProcessor)
    assert isinstance(StarShaclProcessor(), StarShaclSchema)


def test_alias_is_not_in_all_but_the_new_name_is():
    assert "StarShaclSchema" not in starlayer.shacl.__all__
    assert "StarShaclProcessor" in starlayer.shacl.__all__
    assert "StarShaclSchema" not in starlayer.__all__
    assert "StarShaclProcessor" in starlayer.__all__


def test_unknown_attribute_still_raises():
    with pytest.raises(AttributeError):
        starlayer.shacl.NoSuchName  # noqa: B018


def test_validate_through_the_new_name():

    from starlayer.graph import StarLayerGraph


    shapes = StarLayerGraph()
    shapes.parse(
        data="""
        @prefix sh: <http://www.w3.org/ns/shacl#> . @prefix ex: <http://example.org/> .
        ex:S a sh:NodeShape ; sh:targetClass ex:P ;
          sh:property [ sh:path ex:name ; sh:minCount 1 ] .
        """,
        format="turtle",
    )
    data = StarLayerGraph()
    data.parse(data="@prefix ex: <http://example.org/> . ex:a a ex:P . ex:b a ex:P ; ex:name 'b' .", format="turtle")
    result = StarShaclProcessor(shacl_graph=shapes).validate(data)
    assert result.conforms is False
