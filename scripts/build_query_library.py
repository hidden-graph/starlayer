"""scripts/build_query_library.py - the code-KG query library, as RDF.

Reads the query sources in ``packages/starlayer/starlayer/codekg/query-library/*.rq`` and the competency
questions in ``codekg/competency-questions.md``, and writes
``packages/starlayer/starlayer/codekg/curated/query-library.ttl``: for each query a ``slkg:NamedQuery`` that
points at the query's ``sqe:`` tree (the RDF form of a SPARQL query; see ``starlayer.sparql.sqe``), plus the
``slkg:Topic`` and ``slkg:CompetencyQuestion`` nodes they hang from. Also writes
``docs/generated/query-library.generated.md``, a catalogue small enough to read whole.

A ``.rq`` file is the authoring form. Its leading ``#`` lines say what the query is:

    # name: callers-of                     (required; the file is <name>.rq)
    # label: Who calls a function?         (required)
    # comment: Direct callers ...          (required)
    # topic: call-graph                    (required; see TOPICS)
    # answers: What calls function X       (zero or more; the start of a competency question)
    # param: symbol | description | example | required     (zero or more; "optional" for the last field)

followed by the SPARQL. A parameter is a query variable that the caller supplies when running the query. It
must not appear in the SELECT list. A parameter that no triple pattern binds (one used only in a FILTER, which is
every optional one) is declared in the query with ``VALUES ?name { UNDEF }``, so the query is valid on its own.

Build-time only, like the other scripts here. Run: ``python scripts/build_query_library.py [--check]``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODEKG = ROOT / "packages/starlayer/starlayer/codekg"
SOURCES = CODEKG / "query-library"
QUESTIONS = CODEKG / "competency-questions.md"
OUTPUT = CODEKG / "curated/query-library.ttl"
CATALOGUE = ROOT / "docs/generated/query-library.generated.md"

QL_NS = "https://github.com/hidden-graph/starlayer/ns/codekg/curated/query-library#"
SLKG_NS = "https://github.com/hidden-graph/starlayer/ns/codekg#"

# topic id -> (label, comment). The first group mirrors the section headings of competency-questions.md.
TOPICS = {
    "navigation": ("Structure and navigation", "Finding a symbol and seeing what it is: kind, location, parameters."),
    "call-graph": ("Relationships and the call graph", "Who calls what, call chains, instantiation."),
    "inheritance": ("Inheritance", "Overrides and base classes."),
    "api-surface": ("Visibility and API surface", "What is public, what is private, and where private names leak."),
    "dead-code": ("Dead code and unused surface", "Functions nothing calls."),
    "testing": ("Testing linkage", "Which tests exercise which code."),
    "architecture": ("Architecture and coupling", "Imports between modules and subpackages; where the size is."),
    "upstream-bugs": ("Known upstream bugs and workarounds", "Code that exists to work around a bug in another project."),
    "specifications": ("Specifications and standards grounding", "Which code cites which specification."),
    "capabilities": ("Capabilities", "The curated list of what StarLayer does, and the code behind each item."),
}
# competency-questions.md section heading -> topic id
SECTION_TOPIC = {
    "Structure / navigation": "navigation",
    "Relationships / call graph": "call-graph",
    "Inheritance": "inheritance",
    "Visibility / API surface": "api-surface",
    "Dead code / unused surface": "dead-code",
    "Testing linkage": "testing",
    "Architecture / coupling": "architecture",
    "Known upstream bugs / workarounds": "upstream-bugs",
    "Specifications / standards grounding": "specifications",
}
STATUS_BY_MARK = {"✅": "answerable", "🔜": "roadmap", "🗂️": "curated", "⛔": "out-of-scope"}


def _slug(text: str, words: int = 7) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", text.lower())[:words])


def parse_rq(path: Path) -> dict:
    """The front matter and SPARQL text of one ``.rq`` source."""
    meta = {"answers": [], "params": []}
    body: list[str] = []
    in_header = True
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"#\s*(\w+):\s*(.*)$", line) if in_header else None
        if match:
            key, value = match.group(1), match.group(2).strip()
            if key == "answers":
                meta["answers"].append(value)
            elif key == "param":
                fields = [f.strip() for f in value.split("|")]
                if len(fields) != 4 or fields[3] not in ("required", "optional"):
                    raise SystemExit(f"{path.name}: bad '# param:' line (name | description | example | required/optional): {value}")
                meta["params"].append(dict(zip(("name", "description", "example", "required"), fields)))
            else:
                meta[key] = value
        else:
            in_header = False
            body.append(line)
    meta["text"] = "\n".join(body).strip() + "\n"
    for key in ("name", "label", "comment", "topic"):
        if key not in meta:
            raise SystemExit(f"{path.name}: missing '# {key}:'")
    if meta["name"] != path.stem:
        raise SystemExit(f"{path.name}: '# name: {meta['name']}' does not match the file name")
    if meta["topic"] not in TOPICS:
        raise SystemExit(f"{path.name}: unknown topic {meta['topic']!r}; choices: {sorted(TOPICS)}")
    return meta


def parse_questions(path: Path) -> list[dict]:
    """The competency questions in the markdown file: topic, status, question text, and any note after the dash."""
    questions, topic = [], None
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = re.match(r"##\s+(.*)$", line)
        if heading:
            topic = SECTION_TOPIC.get(heading.group(1).strip())
            continue
        bullet = re.match(r"-\s+(✅|🔜|🗂️|⛔)\s+(.*)$", line)
        if bullet and topic:
            text = bullet.group(2).strip()
            question, _, note = text.partition(" — ")
            questions.append(
                {"topic": topic, "status": STATUS_BY_MARK[bullet.group(1)], "question": question.strip(), "note": note.strip()}
            )
    return questions


def build_graph():
    from rdflib import RDF, RDFS, BNode, Graph, Literal, Namespace, URIRef
    from rdflib.namespace import XSD

    from starlayer.sparql.sqe import sqe_parse_to_tree

    ql, slkg = Namespace(QL_NS), Namespace(SLKG_NS)
    graph = Graph()
    graph.bind("ql", ql)
    graph.bind("slkg", slkg)
    graph.bind("rdfs", RDFS)

    for topic_id, (label, comment) in TOPICS.items():
        node = ql[f"topic-{topic_id}"]
        graph.add((node, RDF.type, slkg.Topic))
        graph.add((node, RDFS.label, Literal(label)))
        graph.add((node, RDFS.comment, Literal(comment)))

    questions = parse_questions(QUESTIONS)
    question_nodes: dict[str, URIRef] = {}
    for item in questions:
        node = ql[f"cq-{_slug(item['question'])}"]
        if node in question_nodes.values():
            raise SystemExit(f"two competency questions share the slug {node}")
        question_nodes[item["question"]] = node
        graph.add((node, RDF.type, slkg.CompetencyQuestion))
        graph.add((node, RDFS.label, Literal(item["question"])))
        if item["note"]:
            graph.add((node, RDFS.comment, Literal(item["note"])))
        graph.add((node, slkg.cqStatus, Literal(item["status"])))
        graph.add((node, slkg.aboutTopic, ql[f"topic-{item['topic']}"]))

    queries = [parse_rq(p) for p in sorted(SOURCES.glob("*.rq"))]
    for meta in queries:
        node = ql[meta["name"]]
        graph.add((node, RDF.type, slkg.NamedQuery))
        graph.add((node, RDFS.label, Literal(meta["label"])))
        graph.add((node, RDFS.comment, Literal(meta["comment"])))
        graph.add((node, slkg.aboutTopic, ql[f"topic-{meta['topic']}"]))
        for start in meta["answers"]:
            matches = [n for q, n in question_nodes.items() if q.startswith(start)]
            if len(matches) != 1:
                raise SystemExit(f"{meta['name']}: '# answers: {start}' matches {len(matches)} competency questions")
            graph.add((node, slkg.answersCompetencyQuestion, matches[0]))
        for param in meta["params"]:
            p = BNode()
            graph.add((node, slkg.queryParameter, p))
            graph.add((p, RDF.type, slkg.QueryParameter))
            graph.add((p, slkg.paramName, Literal(param["name"])))
            graph.add((p, RDFS.comment, Literal(param["description"])))
            graph.add((p, slkg.paramExample, Literal(param["example"])))
            graph.add((p, slkg.paramRequired, Literal(param["required"] == "required", datatype=XSD.boolean)))
        root = ql[f"{meta['name']}-tree"]
        # Each tree is parsed (and validated, which raises SQEValidationError for a tree the sqe shapes reject)
        # in a graph of its own: validating inside the growing library graph re-checks every earlier tree each time.
        tree, _ = sqe_parse_to_tree(meta["text"], None, root)
        for triple in tree:
            graph.add(triple)
        graph.add((node, slkg.queryRoot, root))
    return graph, queries, questions


def render_catalogue(queries: list[dict], questions: list[dict]) -> str:
    lines = [
        "# Code knowledge graph: query library",
        "",
        "<!-- Generated by scripts/build_query_library.py from codekg/query-library/*.rq. Do not edit. -->",
        "",
        "Named queries over the code knowledge graph. Run one with `starlayer.codekg.queries.run_query(name, **params)`, or",
        "`python -m starlayer.codekg.queries run <name> param=value`. Results are limited to 25 rows by default.",
        "",
    ]
    for topic_id, (label, _comment) in TOPICS.items():
        members = [q for q in queries if q["topic"] == topic_id]
        if not members:
            continue
        lines += [f"## {label}", ""]
        for q in members:
            params = ", ".join(f"`{p['name']}`" + ("" if p["required"] == "required" else " (optional)") for p in q["params"])
            lines.append(f"- **`{q['name']}`** ({params or 'no parameters'}): {q['label']}. {q['comment']}")
        lines.append("")
    open_items = [q for q in questions if q["status"] != "out-of-scope"]
    answered = sum(1 for q in queries for _ in q["answers"])
    lines += [
        "## Competency questions",
        "",
        f"{len(open_items)} questions are tracked in `codekg/competency-questions.md` (loaded as `slkg:CompetencyQuestion`). "
        f"{answered} query-to-question links exist. List the ones no query answers yet with "
        "`starlayer.codekg.queries.competency_questions(unanswered=True)`.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--check", action="store_true", help="change nothing; exit 1 if the outputs are stale")
    args = parser.parse_args()

    sys.path.insert(0, str(ROOT / "packages/starlayer"))
    from rdflib.compare import isomorphic

    graph, queries, questions = build_graph()
    catalogue = render_catalogue(queries, questions)

    if args.check:
        from rdflib import Graph

        stale = []
        if not OUTPUT.exists() or not isomorphic(Graph().parse(OUTPUT, format="turtle"), graph):
            stale.append(str(OUTPUT.relative_to(ROOT)))
        if not CATALOGUE.exists() or CATALOGUE.read_text(encoding="utf-8") != catalogue:
            stale.append(str(CATALOGUE.relative_to(ROOT)))
        if stale:
            print("stale: " + ", ".join(stale) + " - run `python scripts/build_query_library.py`", file=sys.stderr)
            return 1
        print("query library is current")
        return 0

    header = (
        "# Generated by scripts/build_query_library.py from codekg/query-library/*.rq and\n"
        "# codekg/competency-questions.md. Do not edit by hand: change a .rq file and rebuild.\n"
        "# Each query is an sqe: tree (the RDF form of a SPARQL query) reached through slkg:queryRoot.\n\n"
    )
    OUTPUT.write_text(header + graph.serialize(format="turtle"), encoding="utf-8")
    CATALOGUE.write_text(catalogue, encoding="utf-8")
    print(f"wrote {OUTPUT.relative_to(ROOT)} ({len(graph)} triples, {len(queries)} queries) and {CATALOGUE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
