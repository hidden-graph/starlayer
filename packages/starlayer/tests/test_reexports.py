"""starlayer's __init__.py re-exports names from starlayer.graph/starlayer.shacl by
reference, not by copy or redefinition - these tests lock in `is` identity
(not just equal behavior) so a future refactor can't quietly turn a
re-export into a separate, divergent copy."""

import starlayer
import starlayer.graph
import starlayer.shacl
import starlayer.sparql

_SOURCE_BY_NAME = {
    "StarShaclSchema": starlayer.shacl,
    "StarQuery": starlayer.sparql,
}


def test_reexports_are_the_same_objects_not_copies() -> None:
    for name in starlayer.__all__:
        source = _SOURCE_BY_NAME.get(name, starlayer.graph)
        assert getattr(starlayer, name) is getattr(source, name), name


def test_all_matches_actual_module_exports() -> None:
    """``dir(starlayer)`` also legitimately includes ``graph``/``sparql``/
    ``shacl``/``starontology``/``conformance`` - Python always binds an
    imported submodule as an attribute of its parent package as a side
    effect of the import (not something any of this project's own code
    opts into). ``graph``/``shacl``/``sparql`` are always present -
    ``starlayer/__init__.py`` imports all three directly and
    unconditionally (``sparql`` joined 2026-10-14, for `StarQuery` -
    see that same date's entry in ``starlayer/sparql/CLAUDE.md``).
    ``starontology``/``conformance`` are order-dependent instead - nothing
    in ``starlayer/__init__.py`` imports either directly, but they can
    still end up bound here purely from process-wide import order -
    ``starontology`` ends up bound this way since ``starlayer.sparql``'s
    own submodules import it eagerly (so it was already order-dependent
    before ``sparql`` itself became unconditional - that only fixed
    ``sparql``'s own presence, not its transitive import's), and
    ``conformance`` the same way again, since ``starlayer.conformance``'s
    own ``declared_conformance()`` lazily imports
    ``starlayer.shacl.shacl_profiling`` internally - whichever test file
    happens to import ``starlayer.conformance`` first in a given session
    (e.g. ``test_conformance.py``) is what binds it. ``codekg`` joins the
    list for the identical reason (2026-10-13): nothing in
    ``starlayer/__init__.py`` imports it, but the code-KG extractor's own
    tests (``tests/codekg/``) import ``starlayer.codekg``/
    ``starlayer.codekg.extractor.*`` directly, so whether it's bound here
    depends purely on whether one of those test modules already ran in
    the same session. All six (``sparql`` included, even though it's now
    unconditionally present - keeping it in this subtraction set is
    harmless and avoids re-deriving which ones are guaranteed vs. not)
    are deliberately excluded here rather than asserted against, since
    none of them are part of the curated ``__all__`` list (see this
    module's own docstring) - this test only needs to confirm every
    *curated* re-export is genuinely present, not that nothing else is
    ever visible."""
    exported = {name for name in dir(starlayer) if not name.startswith("_")}
    submodule_attrs = {"graph", "sparql", "shacl", "starontology", "conformance", "codekg"}
    assert exported - submodule_attrs == set(starlayer.__all__)


def test_graph_and_validator_work_together_through_the_single_import() -> None:
    from starlayer import StarLayerGraph, StarShaclSchema
    from starlayer.graph import Namespace

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

    result = StarShaclSchema(shacl_graph=shapes).validate(data_graph=data, meta_shacl=False)
    assert result.conforms is True
