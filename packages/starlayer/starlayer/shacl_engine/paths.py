"""SHACL property paths: parsing a path term from the shapes graph and evaluating it on the data graph.

OWNER (agent D). Skeleton: predicate paths only. Implement inverse, sequence (rdf:List), alternative (sh:alternativePath),
sh:zeroOrMorePath, sh:oneOrMorePath, sh:zeroOrOnePath, with correct cycle handling and distinct value nodes where the
spec says so; malformed paths raise ``ShapeError``.
"""

from __future__ import annotations

from typing import Any

from rdflib import URIRef

from starlayer.shacl_engine.plan import Path, ShapeError, Term


def parse_path(graph: Any, node: Term) -> Path:
    if isinstance(node, URIRef):
        return Path(kind="pred", iri=node, node=node)
    raise ShapeError(f"unsupported path {node!r} (paths.py not implemented yet)")


def eval_path(data: Any, path: Path, focus: Term) -> list[Term]:
    """Value nodes reached from ``focus`` along ``path``, in a stable order, without duplicates removed for pred paths."""
    if path.kind == "pred":
        return list(data.objects(focus, path.iri))
    raise NotImplementedError(path.kind)
