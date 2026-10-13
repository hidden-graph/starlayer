"""starlayer.codekg.extractor.build - the wholesale-replace orchestration.

One public function, ``refresh()``: parse the existing ``codekg.trig`` (if
any), drop every per-module named graph (leaving the ontology's own graph
and the reserved curated graph untouched - neither is ever file-backed by
this extractor), re-extract each target path fresh via ``visitor.py``, and
re-serialize. "Wholesale replace" per module: a module that's no longer in
``target_paths`` simply stays dropped (its old graph was removed and never
rebuilt) - this function only ever adds back exactly the graphs it's told
to extract.
"""

from __future__ import annotations

from pathlib import Path

from starlayer.codekg import BLOB_BASE, CODEKG_TRIG_PATH, CURATED_GRAPH_IRI, ONTOLOGY_GRAPH_IRI


def refresh(target_paths: list[Path], repo_root: Path, *, trig_path: Path | None = None) -> None:
    """Re-extract every path in ``target_paths`` and wholesale-replace
    their named graphs in ``codekg.trig``.

    Args:
        target_paths: The ``.py`` files to extract (already resolved to
            individual files, not directories - see ``cli.py`` for the
            directory-globbing step).
        repo_root: The repository root, used to compute each path's
            repo-relative identity (``BLOB_BASE``-rooted module IRI and
            dotted import path) - every entry in ``target_paths`` must
            live under
            ``repo_root/packages/starlayer/starlayer/``.
        trig_path: Override for where ``codekg.trig`` is read from/written
            to - defaults to the real ``CODEKG_TRIG_PATH`` module constant.
            Exists for testability (so a test never touches the real,
            checked-in file).
    """
    from rdflib import URIRef

    from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

    from . import visitor

    path = trig_path if trig_path is not None else CODEKG_TRIG_PATH

    ds = StarLayerDataset()
    if path.exists():
        ds.parse(str(path), format="trig12")

    for ctx in list(ds.contexts()):
        iri = str(ctx.identifier)
        if iri.startswith(BLOB_BASE) and iri not in (str(CURATED_GRAPH_IRI), str(ONTOLOGY_GRAPH_IRI)):
            ds.remove_graph(ctx)

    starlayer_src_root = repo_root / "packages" / "starlayer" / "starlayer"

    for target_path in target_paths:
        rel_path = target_path.relative_to(starlayer_src_root)
        module_iri = URIRef(BLOB_BASE + str(rel_path))
        module_dotted_path = "starlayer." + str(rel_path.with_suffix("")).replace("/", ".")
        triples = visitor.extract_module(target_path, module_iri, module_dotted_path)
        fresh_ctx = ds.graph(module_iri)
        ds.addN((s, p, o, fresh_ctx) for (s, p, o) in triples)

    path.parent.mkdir(parents=True, exist_ok=True)
    ds.serialize(destination=str(path), format="trig12")
