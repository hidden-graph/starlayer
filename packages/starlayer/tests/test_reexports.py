"""starlayer's __init__.py re-exports names from starlayer.graph/starlayer.shacl by
reference, not by copy or redefinition - these tests lock in `is` identity
(not just equal behavior) so a future refactor can't quietly turn a
re-export into a separate, divergent copy."""

import starlayer.graph
import starlayer.shacl

import starlayer


def test_reexports_are_the_same_objects_not_copies() -> None:
    for name in starlayer.__all__:
        source = starlayer.shacl if name == "StarLayerShacl" else starlayer.graph
        assert getattr(starlayer, name) is getattr(source, name), name


def test_all_matches_actual_module_exports() -> None:
    """``dir(starlayer)`` also legitimately includes ``graph``/``sparql``/
    ``shacl``/``ontology`` - Python always binds an imported submodule as an
    attribute of its parent package as a side effect of the import (not
    something any of this project's own code opts into). ``graph``/
    ``shacl``/``ontology`` are always present - ``starlayer/__init__.py``
    imports all three directly and unconditionally. ``sparql`` is
    order-dependent - nothing in ``starlayer/__init__.py`` imports it
    directly, but it can still end up bound here purely from process-wide
    import order - e.g. ``starlayer.shacl.meta_shapes`` lazily imports
    ``starlayer.sparql`` internally, and whether that's already run by the
    time this test executes depends on which other tests ran first in the
    same session (confirmed live: this test passes in isolation but fails
    when run alongside ``test_validator.py``, purely from that ordering).
    All four are deliberately excluded here rather than asserted against,
    since none of them are part of the curated ``__all__`` list (see this
    module's own docstring) - this test only needs to confirm every
    *curated* re-export is genuinely present, not that nothing else is ever
    visible."""
    exported = {name for name in dir(starlayer) if not name.startswith("_")}
    submodule_attrs = {"graph", "sparql", "shacl", "ontology"}
    assert exported - submodule_attrs == set(starlayer.__all__)


def test_graph_and_validator_work_together_through_the_single_import() -> None:
    from starlayer import Namespace, StarLayerGraph, StarLayerShacl

    ex = Namespace("http://example.org/")
    data = StarLayerGraph()
    data.add((ex.alice, ex.knows, ex.bob))

    shapes = StarLayerGraph()
    shapes.parse(
        data="""
            @prefix ex: <http://example.org/> .
            @prefix sh: <http://www.w3.org/ns/shacl#> .
            ex:S a sh:NodeShape ; sh:targetSubjectsOf ex:knows .
        """,
        format="turtle",
    )

    result = StarLayerShacl().validate(data_graph=data, shacl_graph=shapes, meta_shacl=False)
    assert result.conforms is True
