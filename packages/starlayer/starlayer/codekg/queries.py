"""starlayer.codekg.queries - ask the code knowledge graph questions without writing SPARQL.

The code knowledge graph (``codekg.trig``, about 90,000 triples) is too big to read and too awkward to query by
hand, so this module is the narrow way in: a library of **named queries**, each with parameters, that return a
small table. Start with ``list_queries()``, or ``find-symbol``::

    >>> from starlayer.codekg import queries
    >>> [q.name for q in queries.list_queries(topic="call-graph")]
    ['call-chain-from', 'call-cycles', 'callees-of', 'callers-of', 'who-instantiates']
    >>> print(queries.run_query("callers-of", symbol="starlayer.graph.model.encoding.tt_hash"))

Every result is limited (25 rows by default; ``limit=`` and ``offset=`` page through it) and says when it was cut
short. The graph is built from the source and **can lag it**: line numbers in a result should be checked against
the file, and ``python scripts/build.py --only codekg apidocs`` rebuilds it.

The queries are stored as RDF, not text: ``curated/query-library.ttl`` holds each one as an ``sqe:`` tree
(``starlayer.sparql.sqe``) under a ``slkg:NamedQuery``, and ``run_query`` decodes the tree and runs it. That file is
the source, edited directly (nothing generates it); ``validate_library()`` checks it, and
``scripts/build_query_catalogue.py`` runs that check and writes the readable catalogue.

Also runnable from a shell: ``python -m starlayer.codekg.queries --help``.

This is repo tooling like the rest of ``starlayer.codekg``: it is not part of the installed wheel.
"""

from __future__ import annotations

import argparse
import difflib
import functools
import sys
from dataclasses import dataclass, field
from pathlib import Path

from rdflib import RDF, RDFS, Literal, URIRef, Variable

from . import CODEKG_NS, get_codekg_dataset

_HERE = Path(__file__).parent
LIBRARY_TTL = _HERE / "curated" / "query-library.ttl"

DEFAULT_LIMIT = 25
MAX_LIMIT = 500
_CELL_WIDTH = 70
_MAX_IDENTIFIER = 160

_DEFAULT_PREFIXES = {
    "slkg": str(CODEKG_NS),
    "dcterms": "http://purl.org/dc/terms/",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
}

# the values of slkg:cqStatus
_STATUSES = ("answerable", "roadmap", "curated", "out-of-scope")


# ---------------------------------------------------------------------------
# what the library describes


@dataclass(frozen=True)
class Parameter:
    """A value a named query needs; bound to the query variable of the same name."""

    name: str
    description: str
    example: str
    required: bool


@dataclass(frozen=True)
class NamedQuery:
    """One query in the library."""

    name: str
    label: str
    description: str
    topic: str
    parameters: tuple[Parameter, ...] = ()
    answers: tuple[str, ...] = ()

    def usage(self) -> str:
        """A ready-to-copy call using each parameter's example value."""
        args = "".join(f", {p.name}={p.example!r}" for p in self.parameters if p.required)
        return f"run_query({self.name!r}{args})"


@dataclass(frozen=True)
class CompetencyQuestion:
    """A question the graph should answer, and the queries that answer it."""

    question: str
    status: str
    topic: str
    note: str = ""
    answered_by: tuple[str, ...] = ()


@dataclass
class QueryResult:
    """The rows of a query, already limited. ``str(result)`` is a compact table."""

    query: str
    columns: list[str]
    rows: list[tuple[str, ...]]
    total: int
    offset: int = 0
    limit: int = DEFAULT_LIMIT
    warnings: list[str] = field(default_factory=list)
    kg_note: str = ""  # how old the code KG is, from its build stamp

    @property
    def truncated(self) -> bool:
        return self.offset + len(self.rows) < self.total

    def as_dicts(self) -> list[dict[str, str]]:
        return [dict(zip(self.columns, row, strict=True)) for row in self.rows]

    def __str__(self) -> str:
        lines = [f"[{self.query}]"]
        lines += [f"warning: {w}" for w in self.warnings]
        if not self.columns:
            return "\n".join(lines + ["(no result)"])
        cells = [[_clip(c) for c in row] for row in self.rows]
        widths = [max([len(col)] + [len(r[i]) for r in cells]) for i, col in enumerate(self.columns)]
        lines.append("  ".join(col.ljust(w) for col, w in zip(self.columns, widths, strict=True)).rstrip())
        lines.append("  ".join("-" * w for w in widths))
        lines += ["  ".join(c.ljust(w) for c, w in zip(row, widths, strict=True)).rstrip() for row in cells]
        if not self.rows:
            lines.append("(no rows - for a call-graph question that means none this extractor could resolve)")
        shown = f"rows {self.offset + 1}-{self.offset + len(self.rows)} of {self.total}" if self.rows else "0 rows"
        footer = f"{shown}."
        if self.truncated:
            footer += f" More: pass offset={self.offset + len(self.rows)}, or narrow the query."
        footer += f" {self.kg_note}" if self.kg_note else ""
        lines.append(footer + " The code KG can lag the source; check line numbers in the file.")
        return "\n".join(lines)


def _clip(text: str) -> str:
    """Prose is cut to a readable width; an identifier or path (no spaces) is kept whole, because a result is
    only useful if its symbols can be pasted into the next query."""
    text = " ".join(text.split())
    if " " not in text and len(text) <= _MAX_IDENTIFIER:
        return text
    return text if len(text) <= _CELL_WIDTH else text[: _CELL_WIDTH - 1] + "…"


# ---------------------------------------------------------------------------
# the stored library and the graph it queries (each built once per process, read only, never handed out)


@functools.lru_cache(maxsize=1)
def _library():
    from starlayer.graph import StarLayerGraph

    graph = StarLayerGraph()
    graph.parse(str(LIBRARY_TTL), format="turtle")
    return graph


@functools.lru_cache(maxsize=1)
def _kg():
    """All the code KG's module graphs merged into one graph, plus the curated layer (capabilities and the query library)."""
    from starlayer.graph import StarLayerGraph

    graph = StarLayerGraph()
    for s, p, o, _g in get_codekg_dataset(include_curated=True).quads((None, None, None, None)):
        graph.add((s, p, o))
    return graph


@functools.lru_cache(maxsize=1)
def kg_status() -> str:
    """One sentence on how old the code KG is: when it was built, from which commit, and what changed in the source since.

    Read from the ``slkg:KGBuild`` stamp the extractor writes, compared with the git repository as it is now. Empty
    when there is no stamp (a graph built before stamps existed).
    """
    from starlayer.codekg.extractor.stamp import freshness

    found = freshness(_kg(), Path(__file__).resolve().parents[4])
    return found.sentence() if found else ""


def _slkg(term: str) -> URIRef:
    return CODEKG_NS[term]


def _topic_id(library, node) -> str:
    return str(node).rsplit("topic-", 1)[-1]


def _questions_answered_by(library, query_node) -> tuple[str, ...]:
    return tuple(sorted(str(library.value(q, RDFS.label)) for q in library.objects(query_node, _slkg("answersCompetencyQuestion"))))


def _named_query(library, node) -> NamedQuery:
    params = []
    for p in library.objects(node, _slkg("queryParameter")):
        params.append(
            Parameter(
                name=str(library.value(p, _slkg("paramName"))),
                description=str(library.value(p, RDFS.comment) or ""),
                example=str(library.value(p, _slkg("paramExample")) or ""),
                required=bool(library.value(p, _slkg("paramRequired"))),
            )
        )
    params.sort(key=lambda p: (not p.required, p.name))
    return NamedQuery(
        name=str(node).rsplit("#", 1)[-1],
        label=str(library.value(node, RDFS.label)),
        description=str(library.value(node, RDFS.comment)),
        topic=_topic_id(library, library.value(node, _slkg("aboutTopic"))),
        parameters=tuple(params),
        answers=_questions_answered_by(library, node),
    )


def topics() -> dict[str, str]:
    """Topic id -> label, for ``list_queries(topic=...)``."""
    library = _library()
    return {_topic_id(library, t): str(library.value(t, RDFS.label)) for t in library.subjects(RDF.type, _slkg("Topic"))}


def list_queries(topic: str | None = None) -> list[NamedQuery]:
    """The named queries, sorted by name; only those about ``topic`` (an id such as ``"call-graph"``) if given."""
    library = _library()
    queries = [_named_query(library, n) for n in library.subjects(RDF.type, _slkg("NamedQuery"))]
    if topic is not None:
        if topic not in topics():
            raise KeyError(f"unknown topic {topic!r}; topics: {sorted(topics())}")
        queries = [q for q in queries if q.topic == topic]
    return sorted(queries, key=lambda q: q.name)


def queries_for_topic(topic: str) -> list[NamedQuery]:
    """The queries about a topic, given by id (``"call-graph"``), label or ``slkg:Topic`` IRI."""
    library = _library()
    wanted = str(topic)
    for node in library.subjects(RDF.type, _slkg("Topic")):
        if wanted in (str(node), _topic_id(library, node), str(library.value(node, RDFS.label))):
            return list_queries(topic=_topic_id(library, node))
    raise KeyError(f"unknown topic {topic!r}; topics: {sorted(topics())}")


def get_query(name: str) -> NamedQuery:
    """One named query's description. Raises ``KeyError`` (with close matches) for an unknown name."""
    library = _library()
    node = next(iter([n for n in library.subjects(RDF.type, _slkg("NamedQuery")) if str(n).endswith("#" + name)]), None)
    if node is None:
        known = [q.name for q in list_queries()]
        close = difflib.get_close_matches(name, known, n=3)
        raise KeyError(f"no named query {name!r}" + (f"; did you mean {close}?" if close else f"; names: {known}"))
    return _named_query(library, node)


def query_text(name: str) -> str:
    """The SPARQL text of a named query, rendered from its stored sqe tree."""
    from starlayer.sparql.sqe import sqe_tree_to_text

    return sqe_tree_to_text(_library(), _root(name))


def competency_questions(status: str | None = None, unanswered: bool = False) -> list[CompetencyQuestion]:
    """The questions the graph should answer (the ``slkg:CompetencyQuestion`` nodes), sorted by topic then text.

    ``status`` filters by ``"answerable"``, ``"roadmap"``, ``"curated"`` or ``"out-of-scope"``; ``unanswered=True``
    keeps those no named query answers yet.
    """
    if status is not None and status not in _STATUSES:
        raise ValueError(f"status must be one of {_STATUSES}")
    library = _library()
    found = []
    for node in library.subjects(RDF.type, _slkg("CompetencyQuestion")):
        answered_by = tuple(sorted(str(q).rsplit("#", 1)[-1] for q in library.subjects(_slkg("answersCompetencyQuestion"), node)))
        item = CompetencyQuestion(
            question=str(library.value(node, RDFS.label)),
            status=str(library.value(node, _slkg("cqStatus"))),
            topic=_topic_id(library, library.value(node, _slkg("aboutTopic"))),
            note=str(library.value(node, RDFS.comment) or ""),
            answered_by=answered_by,
        )
        if (status is None or item.status == status) and (not unanswered or not item.answered_by):
            found.append(item)
    return sorted(found, key=lambda q: (q.topic, q.question))


def _tree_triples(library, root) -> list:
    """The triples of the ``sqe:`` tree under ``root``: everything reachable through blank nodes."""
    from rdflib import BNode

    seen, todo, triples = set(), [root], []
    while todo:
        node = todo.pop()
        if node in seen:
            continue
        seen.add(node)
        for p, o in library.predicate_objects(node):
            triples.append((node, p, o))
            if isinstance(o, BNode):
                todo.append(o)
    return triples


def validate_library() -> list[str]:
    """Problems in the stored library, or an empty list when it is sound.

    Checks the library against ``query-library-shapes.ttl``, then validates each query's tree on its own against
    the sqe shapes (one tree at a time: validating the whole library at once re-checks every tree for each one)
    and checks that it decodes back to SPARQL text.
    """
    from rdflib import Graph

    import starlayer.shacl
    from starlayer.sparql.sqe import sqe_tree_to_text, sqe_validate

    library = _library()
    problems: list[str] = []
    shapes = Graph().parse(str(_HERE / "query-library-shapes.ttl"), format="turtle")
    report = starlayer.shacl.validate(library, shacl_graph=shapes)
    if not report.conforms:
        problems.append(f"library does not conform to query-library-shapes.ttl:\n{report.report_text}")
    for node in library.subjects(RDF.type, _slkg("NamedQuery")):
        name = str(node).rsplit("#", 1)[-1]
        root = library.value(node, _slkg("queryRoot"))
        if root is None:
            continue  # the shapes report the missing root
        tree = Graph()
        for triple in _tree_triples(library, root):
            tree.add(triple)
        if not len(tree):
            problems.append(f"{name}: the query root {root} has no tree")
            continue
        conforms, _report, text = sqe_validate(tree)
        if not conforms:
            problems.append(f"{name}: the sqe tree is invalid:\n{text}")
            continue
        try:
            sqe_tree_to_text(library, root)
        except Exception as error:  # noqa: BLE001 - any failure to decode is a problem to report
            problems.append(f"{name}: the tree does not decode to SPARQL: {error}")
    return problems


# ---------------------------------------------------------------------------
# running


def _root(name: str):
    library = _library()
    get_query(name)  # raises a helpful KeyError for an unknown name
    node = next(n for n in library.subjects(RDF.type, _slkg("NamedQuery")) if str(n).endswith("#" + name))
    return library.value(node, _slkg("queryRoot"))


def _term_text(term) -> str:
    if term is None:
        return ""
    if isinstance(term, URIRef):
        text = str(term)
        return text.split("/blob/main/", 1)[1] if "/blob/main/" in text else text.replace(str(CODEKG_NS), "slkg:")
    return str(term)


def _bounded(query_name: str, result, limit: int, offset: int, warnings: list[str]) -> QueryResult:
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAX_LIMIT}")
    if offset < 0:
        raise ValueError("offset must not be negative")
    if result.type == "ASK":
        return QueryResult(query_name, ["answer"], [(str(bool(result.askAnswer)).lower(),)], 1, 0, limit, warnings)
    columns = [str(v) for v in result.vars]
    rows = [tuple(_term_text(t) for t in row) for row in result]
    return QueryResult(query_name, columns, rows[offset : offset + limit], len(rows), offset, limit, warnings, kg_status())


def run_query(name: str, *, limit: int = DEFAULT_LIMIT, offset: int = 0, **params) -> QueryResult:
    """Run a named query and return a limited table.

    Args:
        name: A query from ``list_queries()``.
        limit: The most rows to return (1 to 500).
        offset: Rows to skip, to page through a long result.
        **params: The query's parameters by name (see ``get_query(name).parameters``).

    Raises:
        KeyError: For an unknown query name.
        ValueError: For a missing required parameter or an unknown one.
    """
    from starlayer.sparql.sqe import sqe_tree_to_query

    described = get_query(name)
    declared = {p.name: p for p in described.parameters}
    unknown = sorted(set(params) - set(declared))
    if unknown:
        raise ValueError(f"{name}: unknown parameter(s) {unknown}; parameters: {sorted(declared)}")
    missing = [p.name for p in described.parameters if p.required and p.name not in params]
    if missing:
        raise ValueError(f"{name}: missing required parameter(s) {missing}. Example: {described.usage()}")
    bindings = {Variable(k): Literal(v) for k, v in params.items() if v is not None}
    query = sqe_tree_to_query(_library(), _root(name))
    return _bounded(name, _kg().query(query, initBindings=bindings), limit, offset, [])


def run_sparql(text: str, *, limit: int = DEFAULT_LIMIT, offset: int = 0) -> QueryResult:
    """Run your own SELECT or ASK query against the code KG, with the same limits as a named query.

    The prefixes ``slkg:``, ``dcterms:`` and ``rdfs:`` are predeclared. ``CONSTRUCT``, ``DESCRIBE`` and updates are
    refused because they can return the whole graph; a named query is usually the better start (``list_queries``).
    """
    from rdflib.plugins.sparql.parser import parseQuery

    from starlayer.sparql.parse12 import prepare_query_12

    parsed = parseQuery(text)
    form = parsed[1].name
    if form not in ("SelectQuery", "AskQuery"):
        raise ValueError(f"run_sparql runs SELECT and ASK queries only, not {form.removesuffix('Query').upper()}")
    warnings = []
    if form == "SelectQuery" and not parsed[1].projection:
        warnings.append("SELECT * returns every variable; list the ones you need")
    if form == "SelectQuery" and not parsed[1].limitoffset:
        warnings.append(f"no LIMIT in the query; the result is cut to {limit} rows")
    query = prepare_query_12(text, initNs=_DEFAULT_PREFIXES)
    return _bounded("free-form", _kg().query(query), limit, offset, warnings)


# ---------------------------------------------------------------------------
# command line


def _print_queries(queries) -> None:
    for q in queries:
        params = " ".join(f"{p.name}{'' if p.required else '?'}" for p in q.parameters)
        print(f"{q.name:26} {q.label}" + (f"   [{params}]" if params else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m starlayer.codekg.queries", description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="list the named queries")
    p.add_argument("--topic", help="only this topic (see 'topics')")
    sub.add_parser("topics", help="list the topics")
    sub.add_parser("status", help="how old the code KG is compared with the source (loads the graph)")
    p = sub.add_parser("show", help="describe a query and print its SPARQL")
    p.add_argument("name")
    p = sub.add_parser("run", help="run a named query: run NAME param=value ...")
    p.add_argument("name")
    p.add_argument("params", nargs="*", metavar="param=value")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--offset", type=int, default=0)
    p = sub.add_parser("sparql", help="run your own SELECT or ASK query")
    p.add_argument("text")
    p.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    p.add_argument("--offset", type=int, default=0)
    p = sub.add_parser("questions", help="list the competency questions")
    p.add_argument("--status", choices=_STATUSES)
    p.add_argument("--unanswered", action="store_true", help="only those no named query answers")
    args = parser.parse_args(argv)

    try:
        if args.command == "list":
            _print_queries(list_queries(topic=args.topic))
        elif args.command == "topics":
            for key, label in sorted(topics().items()):
                print(f"{key:14} {label}")
        elif args.command == "status":
            print(kg_status() or "The code KG has no build stamp; rebuild it: python scripts/build.py --only codekg apidocs")
        elif args.command == "show":
            q = get_query(args.name)
            print(f"{q.name}: {q.label}\n{q.description}\n")
            for prm in q.parameters:
                print(f"  {prm.name} ({'required' if prm.required else 'optional'}): {prm.description}  e.g. {prm.example}")
            print(f"\n{q.usage()}\n\n{query_text(args.name)}")
        elif args.command == "run":
            params = dict(item.split("=", 1) for item in args.params)
            print(run_query(args.name, limit=args.limit, offset=args.offset, **params))
        elif args.command == "sparql":
            print(run_sparql(args.text, limit=args.limit, offset=args.offset))
        elif args.command == "questions":
            for cq in competency_questions(status=args.status, unanswered=args.unanswered):
                print(f"{cq.status:12} {cq.topic:14} {cq.question}" + (f"   -> {', '.join(cq.answered_by)}" if cq.answered_by else ""))
    except (KeyError, ValueError) as error:
        print(error.args[0] if error.args else error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
