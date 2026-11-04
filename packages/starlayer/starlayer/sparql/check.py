"""``check_query()``: is this text a SPARQL 1.2 query or update, and if not, what is wrong."""

from __future__ import annotations

__all__ = ["check_query"]


def check_query(text: str, prepare: bool = False) -> str | None:
    """``None`` when ``text`` is a SPARQL 1.2 query (or update) by StarLayer's grammar; else the parser's first line about what is wrong.

    ``prepare``: also prepare it as a query, which finds a prefix nothing declares (the grammar accepts it); for a query whose text
    carries all its ``PREFIX`` lines."""
    from starlayer.graph.oxgraph import OxGraph
    from starlayer.sparql import parse12

    try:
        parse12.parse_query_12(text)
        if prepare:
            OxGraph().query(text)  # an empty graph: preparing the query is cheap, and finds a prefix nothing declares
    except Exception as error:  # noqa: BLE001  (the parser reports its own kinds of exception)
        return " ".join(str(error).split())[:160]
    return None
