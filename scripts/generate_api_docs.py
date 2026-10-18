"""Generates two cross-linked markdown documents straight from
``packages/starlayer/starlayer/codekg/codekg.trig`` - no hand-maintained
curated content involved, unlike ``docs/working/archive/api-reference.md``/
``docs/working/archive/functionality-overview.md``.

- ``docs/generated/api-overview.generated.md`` - one line per PublicAccess
  entity: its headline sentence(s) only, linked to its full entry.
- ``docs/generated/api-reference.generated.md`` - one section per entity:
  full signature, full docstring (the same text the headline's own
  opening sentence is drawn from - never a separate field), parameters/
  return value where codekg captured them, and a GitHub source link.

"PublicAccess" is defined the same way the 2026-10 docstring-headline
pass that made this script possible scoped it: every name in the real
``__all__`` list of the files in ``_ALL_FILES`` below, plus every
non-underscore-prefixed method declared directly by any class among
those names. See ``/tmp/scope_headlines.py`` (this session's own
scratch script) for where that definition was first worked out.

Run: ``python3 scripts/generate_api_docs.py`` (rebuild
``codekg.trig`` first via ``scripts/build_codekg.py`` if source
docstrings have changed since the last build).
"""

from __future__ import annotations

import pathlib
import ast
from collections import defaultdict

from rdflib import Dataset, Namespace, RDF, RDFS

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
CODEKG_PATH = REPO_ROOT / "packages/starlayer/starlayer/codekg/codekg.trig"
OUT_DIR = REPO_ROOT / "docs/generated"
OVERVIEW_PATH = OUT_DIR / "api-overview.generated.md"
REFERENCE_PATH = OUT_DIR / "api-reference.generated.md"

SLKG = Namespace("https://github.com/hidden-graph/starlayer/ns/codekg#")
DCTERMS = Namespace("http://purl.org/dc/terms/")

BLOB_BASE = "https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/"
PKG_ROOT = REPO_ROOT / "packages/starlayer/starlayer"

# (file relative to packages/starlayer/starlayer, display bucket)
_ALL_FILES = [
    ("__init__.py", "starlayer"),
    ("sparql/__init__.py", "starlayer.sparql"),
    ("sparql/entailment_rdf.py", "starlayer.sparql"),
    ("sparql/entailment_rdfs.py", "starlayer.sparql"),
    ("sparql/salg/__init__.py", "starlayer.sparql.salg"),
    ("sparql/sqe/__init__.py", "starlayer.sparql.sqe"),
    ("graph/rdfc.py", "starlayer.graph"),
    ("graph/compare.py", "starlayer.graph"),
    ("graph/__init__.py", "starlayer.graph"),
    ("graph/parsers/__init__.py", "starlayer.graph"),
    ("graph/graph/__init__.py", "starlayer.graph"),
    ("graph/model/__init__.py", "starlayer.graph"),
    ("graph/serializers/__init__.py", "starlayer.graph"),
    ("graph/query/__init__.py", "starlayer.graph"),
    ("shacl/__init__.py", "starlayer.shacl"),
    ("shacl/shacl_profiling.py", "starlayer.shacl"),
    ("shacl/engine/__init__.py", "starlayer.shacl"),
]
_BUCKET_ORDER = ["starlayer", "starlayer.graph", "starlayer.sparql", "starlayer.sparql.salg", "starlayer.sparql.sqe", "starlayer.shacl"]


def _load_dataset() -> Dataset:
    ds = Dataset()
    ds.parse(CODEKG_PATH, format="trig")
    return ds


def _val(ds, ent, pred):
    for _s, _p, o, _c in ds.quads((ent, pred, None, None)):
        return o
    return None


def _vals(ds, ent, pred):
    return [o for _s, _p, o, _c in ds.quads((ent, pred, None, None))]


def _is_external_type(ds, ent) -> bool:
    return any(True for _ in ds.quads((ent, RDF.type, SLKG.ExternalType, None)))


def _is_class(ds, ent) -> bool:
    return any(True for _ in ds.quads((ent, RDF.type, SLKG.Class, None)))


def _is_method(ds, ent) -> bool:
    return any(True for _ in ds.quads((ent, RDF.type, SLKG.Method, None)))


def first_paragraph(text: str) -> str:
    """Isolate the first paragraph of ``text`` (the headline, per this
    project's own "headline is the opening of the same docstring"
    design), joining its own wrapped physical lines into one logical
    line.
    """
    first_para = text.strip().split("\n\n")[0]
    return " ".join(line.strip() for line in first_para.splitlines())


def collect_public_entities(ds: Dataset) -> list[tuple[str, str]]:
    """Returns ``[(identifier, bucket), ...]`` for every PublicAccess
    entity, in the same order/definition ``/tmp/scope_headlines.py``
    established.
    """
    all_names_by_bucket: dict[str, set[str]] = defaultdict(set)
    for rel_path, bucket in _ALL_FILES:
        tree = ast.parse((PKG_ROOT / rel_path).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
            ):
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    for elt in node.value.elts:
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            all_names_by_bucket[bucket].add(elt.value)

    label_index: dict[str, list] = defaultdict(list)
    for s, _p, o, _c in ds.quads((None, RDFS.label, None, None)):
        label_index[str(o)].append(s)

    entities: list[tuple[str, str]] = []
    seen: set[str] = set()

    for bucket in _BUCKET_ORDER:
        for name in sorted(all_names_by_bucket.get(bucket, ())):
            # Sorted: the dataset's own iteration order is not stable across builds.
            for ent in sorted(label_index.get(name, []), key=str):
                if _is_external_type(ds, ent):
                    continue
                ident = _val(ds, ent, DCTERMS.identifier)
                if ident is None:
                    continue
                ident = str(ident)
                if ident not in seen:
                    seen.add(ident)
                    entities.append((ident, bucket))
                if _is_class(ds, ent):
                    methods = sorted((o for _s2, _p2, o, _c2 in ds.quads((ent, SLKG.declares, None, None))), key=str)
                    for method_ent in methods:
                        if not _is_method(ds, method_ent):
                            continue
                        m_label = str(_val(ds, method_ent, RDFS.label) or "")
                        if m_label.startswith("_"):
                            continue
                        m_ident = _val(ds, method_ent, DCTERMS.identifier)
                        if m_ident is None:
                            continue
                        m_ident = str(m_ident)
                        if m_ident not in seen:
                            seen.add(m_ident)
                            entities.append((m_ident, bucket))
    return entities


def _anchor(identifier: str) -> str:
    return "entity-" + identifier.replace(".", "-")


def _display_name(ds: Dataset, ent, identifier: str) -> str:
    parts = identifier.split(".")
    if _is_method(ds, ent) and len(parts) >= 2:
        return ".".join(parts[-2:])
    return parts[-1]


def _source_link(ds: Dataset, ent) -> str | None:
    file_path = _val(ds, ent, SLKG.filePath)
    line_start = _val(ds, ent, SLKG.lineStart)
    line_end = _val(ds, ent, SLKG.lineEnd)
    if file_path is None:
        return None
    try:
        rel = pathlib.Path(str(file_path)).relative_to(PKG_ROOT)
    except ValueError:
        return None
    url = BLOB_BASE + str(rel)
    if line_start is not None and line_end is not None:
        url += f"#L{line_start}-L{line_end}"
    return url


def render_overview(ds: Dataset, entities: list[tuple[str, dict]]) -> str:
    lines = [
        "# StarLayer API Overview (generated)",
        "",
        "Generated directly from `packages/starlayer/starlayer/codekg/codekg.trig` - "
        "every PublicAccess entity's own headline sentence(s), nothing hand-curated. "
        "Each name links to its full entry in "
        "[api-reference.generated.md](api-reference.generated.md).",
        "",
    ]
    by_bucket: dict[str, list] = defaultdict(list)
    for ident, info in entities:
        by_bucket[info["bucket"]].append((ident, info))

    for bucket in _BUCKET_ORDER:
        rows = by_bucket.get(bucket, [])
        if not rows:
            continue
        lines.append(f"## `{bucket}`")
        lines.append("")
        for ident, info in rows:
            name = info["display_name"]
            kind = info["kind"]
            headline = info["headline"] or "_(no docstring)_"
            anchor = _anchor(ident)
            lines.append(
                f"- **[`{name}`](api-reference.generated.md#{anchor})** ({kind}) - {headline}"
            )
        lines.append("")
    return "\n".join(lines)


def render_reference(ds: Dataset, entities: list[tuple[str, dict]]) -> str:
    lines = [
        "# StarLayer API Reference (generated)",
        "",
        "Generated directly from `packages/starlayer/starlayer/codekg/codekg.trig` - "
        "every PublicAccess entity's own full signature and docstring, nothing "
        "hand-curated. See [api-overview.generated.md](api-overview.generated.md) "
        "for the headline-only index this expands on.",
        "",
    ]
    by_bucket: dict[str, list] = defaultdict(list)
    for ident, info in entities:
        by_bucket[info["bucket"]].append((ident, info))

    for bucket in _BUCKET_ORDER:
        rows = by_bucket.get(bucket, [])
        if not rows:
            continue
        lines.append(f"## `{bucket}`")
        lines.append("")
        lines.append(f"[Back to overview](api-overview.generated.md#{bucket.replace('.', '')})")
        lines.append("")
        for ident, info in rows:
            anchor = _anchor(ident)
            lines.append(f'<a id="{anchor}"></a>')
            lines.append(f"### `{info['display_name']}`  _({info['kind']})_")
            lines.append("")
            if info["signature"]:
                lines.append(f"```python\n{info['signature']}\n```")
                lines.append("")
            if info["comment"]:
                lines.append(info["comment"].strip())
                lines.append("")
            if info["params"]:
                lines.append("**Parameters:**")
                lines.append("")
                for p_name, p_type, p_default, p_desc in info["params"]:
                    default_str = f" = {p_default}" if p_default is not None else ""
                    desc_str = f" - {p_desc}" if p_desc else ""
                    lines.append(f"- `{p_name}: {p_type}{default_str}`{desc_str}")
                lines.append("")
            if info["return_type"] is not None:
                desc_str = f" - {info['return_desc']}" if info["return_desc"] else ""
                lines.append(f"**Returns:** `{info['return_type']}`{desc_str}")
                lines.append("")
            if info["source_link"]:
                lines.append(f"**Source:** [{ident}]({info['source_link']})")
                lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


def build_entity_info(ds: Dataset, ident: str, ent, bucket: str) -> dict:
    comment = _val(ds, ent, RDFS.comment)
    comment = str(comment) if comment is not None else None
    headline = first_paragraph(comment) if comment else None

    param_nodes = _vals(ds, ent, SLKG.hasParameter)

    def position_of(p):
        pos = _val(ds, p, SLKG.position)
        return int(pos) if pos is not None else 999

    params = []
    for p in sorted(param_nodes, key=position_of):
        p_name = _val(ds, p, RDFS.label)
        p_type = _val(ds, p, SLKG.annotationText)
        p_default = _val(ds, p, SLKG.defaultValue)
        p_desc = _val(ds, p, RDFS.comment)
        params.append((p_name, p_type, p_default, p_desc))

    return_value = _val(ds, ent, SLKG.hasReturnValue)
    return_type = _val(ds, return_value, SLKG.annotationText) if return_value is not None else None
    return_desc = _val(ds, return_value, RDFS.comment) if return_value is not None else None

    kind = (
        "method" if _is_method(ds, ent) else "class" if _is_class(ds, ent) else "function"
    )

    return {
        "bucket": bucket,
        "kind": kind,
        "display_name": _display_name(ds, ent, ident),
        "signature": _val(ds, ent, SLKG.signature),
        "comment": comment,
        "headline": headline,
        "params": params,
        "return_type": return_type,
        "return_desc": return_desc,
        "source_link": _source_link(ds, ent),
    }


def main() -> None:
    ds = _load_dataset()
    label_index: dict[str, list] = defaultdict(list)
    for s, _p, o, _c in ds.quads((None, DCTERMS.identifier, None, None)):
        label_index[str(o)].append(s)

    raw_entities = collect_public_entities(ds)
    entities: list[tuple[str, dict]] = []
    for ident, bucket in raw_entities:
        candidates = sorted((e for e in label_index.get(ident, []) if not _is_external_type(ds, e)), key=str)
        if not candidates:
            continue
        ent = candidates[0]
        entities.append((ident, build_entity_info(ds, ident, ent, bucket)))

    OUT_DIR.mkdir(exist_ok=True)
    OVERVIEW_PATH.write_text(render_overview(ds, entities))
    REFERENCE_PATH.write_text(render_reference(ds, entities))

    print(f"{len(entities)} PublicAccess entities")
    print(f"Wrote {OVERVIEW_PATH.relative_to(REPO_ROOT)}")
    print(f"Wrote {REFERENCE_PATH.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
