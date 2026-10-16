"""Exploratory script - NOT part of the production package, not wired into
any build/test pipeline.

Answers a direct question: can packages/starlayer/starlayer/codekg/codekg.trig
*alone* - no docs/api-reference.md involved at all - produce something that
reads like standard generated API documentation (the Sphinx autodoc/pdoc
shape: signature, docstring, a Parameters list with type/default/
description, a Returns line, a source-location link)?

Queries codekg.trig directly for a small, deliberately mixed sample of real
functions - one whose docstring uses a structured Args:/Returns: section
(so every parameter gets its own description), and one whose docstring is
prose-only (so parameters have type/position but no individual
description) - to show both cases honestly, not just the favorable one.
"""

from __future__ import annotations

from pathlib import Path

from rdflib import Dataset, Literal, Namespace

REPO_ROOT = Path(__file__).resolve().parents[1]
CODEKG_PATH = REPO_ROOT / "packages" / "starlayer" / "starlayer" / "codekg" / "codekg.trig"

SLKG = Namespace("https://github.com/hidden-graph/starlayer/ns/codekg#")
DCTERMS = Namespace("http://purl.org/dc/terms/")
RDFS_NS = Namespace("http://www.w3.org/2000/01/rdf-schema#")

# Deliberately mixed: one with Args:/Returns:-sourced per-parameter
# descriptions, one with a prose-only docstring (no per-parameter text).
SAMPLE_IDENTIFIERS = [
    "starlayer.graph.graph._timeout.run_with_timeout",
    "starlayer.shacl.subgraph_extraction.extract_subgraph",
]


def load(path: Path) -> Dataset:
    ds = Dataset()
    ds.parse(path, format="trig")
    return ds


def find_by_identifier(ds: Dataset, identifier: str):
    for s, _p, _o, _c in ds.quads((None, DCTERMS.identifier, Literal(identifier), None)):
        return s
    return None


def render_entity(ds: Dataset, entity) -> str:
    def val(pred):
        for _s, _p, o, _c in ds.quads((entity, pred, None, None)):
            return o
        return None

    def vals(pred):
        return [o for _s, _p, o, _c in ds.quads((entity, pred, None, None))]

    label = val(RDFS_NS.label)
    comment = val(RDFS_NS.comment)
    signature = val(SLKG.signature)
    file_path = val(SLKG.filePath)
    line_start = val(SLKG.lineStart)
    line_end = val(SLKG.lineEnd)
    return_value = val(SLKG.hasReturnValue)
    param_nodes = vals(SLKG.hasParameter)

    lines = []
    lines.append(f"### `{label}`")
    lines.append("")
    lines.append(f"```python\n{signature}\n```")
    lines.append("")
    if comment:
        lines.append(str(comment).strip())
        lines.append("")

    if param_nodes:
        # Sort by slkg:position for a stable, declaration-order listing.
        def position_of(p):
            for _s, _pp, o, _c in ds.quads((p, SLKG.position, None, None)):
                return int(o)
            return 999

        lines.append("**Parameters:**")
        lines.append("")
        for p in sorted(param_nodes, key=position_of):
            def pval(pred):
                for _s, _pp, o, _c in ds.quads((p, pred, None, None)):
                    return o
                return None

            p_name = pval(RDFS_NS.label)
            p_type = pval(SLKG.annotationText)
            p_default = pval(SLKG.defaultValue)
            p_desc = pval(RDFS_NS.comment)
            default_str = f" = {p_default}" if p_default is not None else ""
            desc_str = f" - {p_desc}" if p_desc is not None else " - _(no per-parameter description available)_"
            lines.append(f"- `{p_name}: {p_type}{default_str}`{desc_str}")
        lines.append("")

    if return_value is not None:
        def rval(pred):
            for _s, _pp, o, _c in ds.quads((return_value, pred, None, None)):
                return o
            return None

        r_type = rval(SLKG.annotationText)
        r_desc = rval(RDFS_NS.comment)
        desc_str = f" - {r_desc}" if r_desc is not None else " - _(no description available)_"
        lines.append(f"**Returns:** `{r_type}`{desc_str}")
        lines.append("")

    if file_path is not None:
        lines.append(f"**Source:** `{file_path}` lines {line_start}-{line_end}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    print(f"Loading {CODEKG_PATH.relative_to(REPO_ROOT)} ...")
    ds = load(CODEKG_PATH)
    print(f"  {len(list(ds))} quads loaded")
    print()

    for identifier in SAMPLE_IDENTIFIERS:
        entity = find_by_identifier(ds, identifier)
        if entity is None:
            print(f"!! {identifier} not found in codekg")
            continue
        print(render_entity(ds, entity))
        print("---")
        print()


if __name__ == "__main__":
    main()
