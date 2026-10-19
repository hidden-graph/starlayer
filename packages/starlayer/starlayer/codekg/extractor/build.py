"""starlayer.codekg.extractor.build - the wholesale-replace orchestration.

One public function, ``refresh()``: parse the existing ``codekg.trig`` (if
any), drop every per-module named graph (leaving the ontology's own graph
and the reserved curated graph untouched, and replacing the build-stamp graph - neither is ever file-backed by
this extractor), re-extract each target path fresh via ``visitor.py``, and
re-serialize. "Wholesale replace" per module: a module that's no longer in
``target_paths`` simply stays dropped (its old graph was removed and never
rebuilt) - this function only ever adds back exactly the graphs it's told
to extract.

Before any single file's own triples are extracted, a whole-project
``symbol_index.build_symbol_index()`` pass runs once across every target
path - this is what lets ``slkg:calls`` resolve a call to a function
defined in a different file than the one making the call (see
``symbol_index.py``'s own module docstring).
"""

from __future__ import annotations

from pathlib import Path

from starlayer.codekg import (
    BLOB_BASE,
    CODEKG_TRIG_PATH,
    CURATED_GRAPH_IRI,
    ONTOLOGY_GRAPH_IRI,
    TESTS_BLOB_BASE,
)


def refresh(target_paths: list[Path], repo_root: Path, *, trig_path: Path | None = None) -> None:
    """Re-extract every path in ``target_paths`` and wholesale-replace
    their named graphs in ``codekg.trig``.

    Args:
        target_paths: The ``.py`` files to extract (already resolved to
            individual files, not directories - see ``cli.py`` for the
            directory-globbing step).
        repo_root: The repository root, used to compute each path's
            repo-relative identity (module IRI and dotted import path) via
            ``symbol_index.module_identity()`` - every entry in
            ``target_paths`` must live under one of that function's own
            known roots (``packages/starlayer/starlayer/`` or
            ``packages/starlayer/tests/`` - see
            ``symbol_index.resolve_root()``).
        trig_path: Override for where ``codekg.trig`` is read from/written
            to - defaults to the real ``CODEKG_TRIG_PATH`` module constant.
            Exists for testability (so a test never touches the real,
            checked-in file).
    """
    from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

    from . import stamp, symbol_index, visitor

    path = trig_path if trig_path is not None else CODEKG_TRIG_PATH

    ds = StarLayerDataset()
    if path.exists():
        ds.parse(str(path), format="trig12")

    for ctx in list(ds.contexts()):
        iri = str(ctx.identifier)
        if (iri.startswith(BLOB_BASE) or iri.startswith(TESTS_BLOB_BASE)) and iri not in (
            str(CURATED_GRAPH_IRI),
            str(ONTOLOGY_GRAPH_IRI),
        ):
            ds.remove_graph(ctx)

    index = symbol_index.build_symbol_index(target_paths, repo_root)

    for target_path in target_paths:
        module_iri, module_dotted_path = symbol_index.module_identity(target_path, repo_root)
        triples = visitor.extract_module(target_path, module_iri, module_dotted_path, index)
        fresh_ctx = ds.graph(module_iri)
        ds.addN((s, p, o, fresh_ctx) for (s, p, o) in triples)

    stamp.write_stamp(ds, repo_root, len(target_paths))

    path.parent.mkdir(parents=True, exist_ok=True)
    ds.serialize(destination=str(path), format="trig12")
