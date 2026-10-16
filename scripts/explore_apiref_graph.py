"""Exploratory script - NOT part of the production package, not wired into
any build/test pipeline.

Parses docs/api-reference.md into a small in-memory RDF graph (an ad hoc
apiref: vocabulary - one apiref:Entry node per table row: name/kind/status/
description/module), then tries to resolve each entry to the matching
codekg entity (packages/starlayer/starlayer/codekg/codekg.trig) via its
dcterms:identifier (a fully-qualified dotted Python path string already
stored on every Class/Function/Method node - confirmed directly, e.g.
"starlayer.shacl.validator.StarShaclSchema.validate").

Resolution is suffix-match (the entry's own dotted name, e.g.
"StarShaclSchema.validate" or a bare "extract_subgraph") filtered by the
enclosing section's module-path prefix (e.g. "starlayer.shacl") - the
section header only gives the *package*, not which specific submodule
actually declares the name, so an exact concatenation doesn't work; a
suffix match naturally handles that gap. Reports resolved/unresolved/
ambiguous counts, not a persisted artifact - the whole point of this pass
is to see whether the idea holds up before building the real, persisted
version (a committed .trig + parser/serializer + SHACL shapes, matching
the manch:/salg:/srl: pattern) that a later pass would do properly.
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from rdflib import Dataset, Graph, Literal, Namespace, RDF, URIRef

REPO_ROOT = Path(__file__).resolve().parents[1]
API_REF_PATH = REPO_ROOT / "docs" / "api-reference.md"
CODEKG_PATH = REPO_ROOT / "packages" / "starlayer" / "starlayer" / "codekg" / "codekg.trig"

APIREF = Namespace("urn:starlayer:apiref-exploratory#")
DCTERMS = Namespace("http://purl.org/dc/terms/")

_HEADER_RE = re.compile(r"^##\s+`([\w.]+)`")
_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_NAME_CLEAN_RE = re.compile(r"[`()]")


def _clean_name(raw: str) -> str:
    name = _NAME_CLEAN_RE.sub("", raw).strip()
    # A handful of entries read "Also available from starlayer.graph below"
    # or similar prose dressed up as a cell - keep only the leading
    # dotted-identifier-shaped token.
    m = re.match(r"^[\w.]+", name)
    return m.group(0) if m else name


def parse_api_reference(path: Path) -> Graph:
    g = Graph()
    g.bind("apiref", APIREF)
    g.bind("dcterms", DCTERMS)

    module_context: str | None = None
    in_table = False
    row_index = 0

    for raw_line in path.read_text().splitlines():
        header_match = _HEADER_RE.match(raw_line.strip())
        if header_match:
            module_context = header_match.group(1)
            in_table = False
            continue

        row_match = _TABLE_ROW_RE.match(raw_line.strip())
        if not row_match:
            in_table = False
            continue

        cells = [c.strip() for c in row_match.group(1).split("|")]
        if len(cells) != 4:
            continue
        name_cell, kind_cell, status_cell, desc_cell = cells

        if name_cell.lower() == "name" and kind_cell.lower() == "kind":
            in_table = True
            continue
        if set(name_cell) <= {"-", ":"} and in_table:
            continue  # the markdown header-separator row
        if not in_table or module_context is None:
            continue

        row_index += 1
        entry = APIREF[f"entry-{row_index}"]
        g.add((entry, RDF.type, APIREF.Entry))
        g.add((entry, APIREF.rawName, Literal(name_cell)))
        g.add((entry, APIREF.name, Literal(_clean_name(name_cell))))
        g.add((entry, APIREF.kind, Literal(kind_cell)))
        g.add((entry, APIREF.status, Literal(status_cell)))
        g.add((entry, APIREF.description, Literal(desc_cell)))
        g.add((entry, APIREF.module, Literal(module_context)))

    return g


def build_identifier_index(codekg_path: Path) -> dict[str, URIRef]:
    # codekg.trig stores its content in per-module NAMED graphs, not the
    # default graph - a plain Graph().parse(..., format="trig") silently
    # keeps only the (empty) default graph's triples. Dataset() sees every
    # named graph's content too (confirmed live: 0 triples via Graph(),
    # 78,857 quads via Dataset() against the same file).
    ds = Dataset()
    ds.parse(codekg_path, format="trig")
    index: dict[str, URIRef] = {}
    for s, _p, o, _ctx in ds.quads((None, DCTERMS.identifier, None, None)):
        index[str(o)] = s
    return index


def resolve(apiref_graph: Graph, identifier_index: dict[str, URIRef]) -> dict:
    # Group identifiers by their own dotted suffixes of every length, so a
    # 1- or 2-segment entry name can match regardless of how deep the real
    # module/class nesting actually goes.
    by_suffix: dict[str, list[str]] = defaultdict(list)
    for identifier in identifier_index:
        parts = identifier.split(".")
        for n in (1, 2, 3):
            if len(parts) >= n:
                by_suffix[".".join(parts[-n:])].append(identifier)

    resolved = []
    unresolved = []
    ambiguous = []

    for entry in apiref_graph.subjects(RDF.type, APIREF.Entry):
        name = str(apiref_graph.value(entry, APIREF.name))
        module = str(apiref_graph.value(entry, APIREF.module))
        n_segments = len(name.split("."))
        candidates = by_suffix.get(name, [])
        filtered = [c for c in candidates if c == module or c.startswith(module + ".")]
        if len(filtered) == 1:
            resolved.append((entry, name, module, filtered[0]))
            apiref_graph.add((entry, APIREF.codekgIdentifier, Literal(filtered[0])))
            apiref_graph.add((entry, APIREF.codekgEntity, identifier_index[filtered[0]]))
        elif len(filtered) == 0:
            unresolved.append((entry, name, module))
        else:
            ambiguous.append((entry, name, module, filtered))

    return {"resolved": resolved, "unresolved": unresolved, "ambiguous": ambiguous}


def _entry_row_index(entry: URIRef) -> int:
    # "urn:...#entry-<N>" - recovers the original document row order, since
    # that's the only thing the entry IRI itself encodes.
    return int(str(entry).rsplit("-", 1)[-1])


def render_report(apiref_graph: Graph) -> str:
    """Render the parsed (and resolved) graph back out as a text report
    shaped like docs/api-reference.md's own content - demonstrating that
    the graph actually holds everything needed to reproduce it, plus the
    one thing the hand-written original doesn't show: each entry's own
    resolved codekg identifier, when one was found.

    Grouped by module, in each module's own first-seen order; entries
    within a module kept in their original document row order.
    """
    entries_by_module: dict[str, list[URIRef]] = defaultdict(list)
    module_order: list[str] = []
    for entry in apiref_graph.subjects(RDF.type, APIREF.Entry):
        module = str(apiref_graph.value(entry, APIREF.module))
        if module not in entries_by_module:
            module_order.append(module)
        entries_by_module[module].append(entry)

    lines: list[str] = []
    lines.append("# StarLayer API Reference (generated from the apiref/codekg graphs)")
    lines.append("")
    lines.append(
        "Regenerated from the apiref: graph parsed out of docs/api-reference.md, "
        "cross-linked to packages/starlayer/starlayer/codekg/codekg.trig - "
        "exploratory, see scripts/explore_apiref_graph.py."
    )
    lines.append("")

    for module in module_order:
        lines.append(f"## `{module}`")
        lines.append("")
        lines.append("| Name | Kind | Status | Description | codekg identifier |")
        lines.append("|---|---|---|---|---|")
        for entry in sorted(entries_by_module[module], key=_entry_row_index):
            name = str(apiref_graph.value(entry, APIREF.rawName))
            kind = str(apiref_graph.value(entry, APIREF.kind))
            status = str(apiref_graph.value(entry, APIREF.status))
            description = str(apiref_graph.value(entry, APIREF.description))
            codekg_id = apiref_graph.value(entry, APIREF.codekgIdentifier)
            codekg_cell = f"`{codekg_id}`" if codekg_id is not None else "_unresolved_"
            lines.append(f"| {name} | {kind} | {status} | {description} | {codekg_cell} |")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    print(f"Parsing {API_REF_PATH.relative_to(REPO_ROOT)} ...")
    apiref_graph = parse_api_reference(API_REF_PATH)
    total_entries = len(list(apiref_graph.subjects(RDF.type, APIREF.Entry)))
    print(f"  {total_entries} apiref:Entry nodes parsed")

    print(f"Loading {CODEKG_PATH.relative_to(REPO_ROOT)} ...")
    identifier_index = build_identifier_index(CODEKG_PATH)
    print(f"  {len(identifier_index)} dcterms:identifier entries indexed")

    print("Resolving entries against codekg ...")
    result = resolve(apiref_graph, identifier_index)

    print()
    print("=== Summary ===")
    print(f"total:      {total_entries}")
    print(f"resolved:   {len(result['resolved'])}")
    print(f"unresolved: {len(result['unresolved'])}")
    print(f"ambiguous:  {len(result['ambiguous'])}")

    print()
    print("=== Sample resolved (first 10) ===")
    for _entry, name, module, identifier in result["resolved"][:10]:
        print(f"  [{module}] {name:40s} -> {identifier}")

    print()
    print("=== Unresolved (first 30) ===")
    for _entry, name, module in result["unresolved"][:30]:
        print(f"  [{module}] {name}")
    if len(result["unresolved"]) > 30:
        print(f"  ... and {len(result['unresolved']) - 30} more")

    print()
    print("=== Ambiguous (first 15) ===")
    for _entry, name, module, candidates in result["ambiguous"][:15]:
        print(f"  [{module}] {name} -> {candidates}")

    report_text = render_report(apiref_graph)
    report_path = REPO_ROOT / "scripts" / "apiref_report.generated.md"
    report_path.write_text(report_text)
    print()
    print(f"=== Report written to {report_path.relative_to(REPO_ROOT)} ({len(report_text)} chars) ===")


if __name__ == "__main__":
    main()
