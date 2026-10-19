"""Compatibility re-export: the expression-family table lives in ``starlayer.sparql.expr_families`` (shared by
``sqe:``, ``srl:`` and the encoder, so it cannot sit inside ``salg/``). ``salg`` imports it from there."""

from ..expr_families import _EXPR_NODE_FAMILY

__all__ = ["_EXPR_NODE_FAMILY"]
