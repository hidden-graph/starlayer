"""``check_query()``: is this text a SPARQL 1.2 query or update, and if not, what is wrong."""

from __future__ import annotations

__all__ = ["check_query"]


def _calls_service(text: str) -> bool:
    from starlayer.shacl_engine.sparql_support import _analyse

    return any(item[0] == "service" for item in _analyse(text)[2])


def check_query(text: str, prepare: bool = False) -> str | None:
    """``None`` when ``text`` is a SPARQL 1.2 query (or update) by StarLayer's grammar; else the parser's first line about what is wrong.

    ``prepare``: also prepare a query with Oxigraph, for a query whose text carries all its ``PREFIX`` lines; an update is
    only parsed, and so is a query with a ``SERVICE`` clause (preparing it would send the request)."""
    from starlayer.graph.oxgraph import StarLayerGraph
    from starlayer.sparql.parse_sparql import (
        SparqlSyntaxError,
        parse_sparql,
        parse_sparql_update,
    )

    try:
        is_query = True
        try:
            parse_sparql(text)
        except SparqlSyntaxError as query_error:
            try:
                parse_sparql_update(text)  # not a query: an update is fine too
            except SparqlSyntaxError:
                raise query_error from None
            is_query = False
        if prepare and is_query and not _calls_service(text):
            # an empty graph: preparing the query is cheap, and finds a prefix nothing declares. Oxigraph has no prepare-only call
            # and would run a SERVICE clause as an outbound request, so a query with one is only parsed.
            StarLayerGraph().query(text)
    except Exception as error:  # noqa: BLE001  (the parser reports its own kinds of exception)
        return " ".join(str(error).split())[:160]
    return None
