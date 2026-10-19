# Changelog

Tracks when `codekg.trig` was last regenerated via `scripts/build_codekg.py`, with what paths were covered and what the extractor could pull out of the code as of that run. The graph is **not** regenerated on every change - update this file whenever it *is* regenerated, even if the extractor itself didn't change, so a reader can tell how stale the graph might be without re-running anything. The competency questions (what the graph can and cannot answer) are in `curated/query-library.ttl`; `docs/generated/query-library.generated.md` lists them.

## 2026-10-19 — regenerated (automatic entry)

- Built from commit 92bae39: 357 files, 95,051 triples.

## 2026-10-19 — regenerated (repo-relative `slkg:filePath`, named-tuple types)

- Extractor change: `Name = namedtuple("Name", [...])` (and `typing.NamedTuple`'s functional form) is extracted as a `slkg:Class` with one `slkg:Attribute` per field (defaults included), a `rdfs:subClassOf` builtins.tuple edge, and counts as the target of constructor calls (`slkg:instantiates`). `starlayer.starontology.manchester` defines eight such types that were missing.
- Extractor change: `slkg:filePath` is now the path relative to the repository root (`packages/starlayer/starlayer/graph/model/encoding.py`). It used to be the absolute path on the machine that ran the extractor, which was wrong for anyone else reading the committed graph.
- Known gap found while building the query library: `slkg:importsModule` only records imports of external modules (third-party and standard library). Imports between starlayer's own modules are not extracted. Dependencies inside the project have to come from `slkg:calls`.

## 2026-10-14 — regenerated (cross-file `slkg:overrides`)

- 277 files extracted (96 source + 181 tests), 75,766 triples.
- Extractor change: `slkg:overrides` generalized from same-file-only to project-wide, reusing `SymbolIndex.resolve_method_in_chain()` (the same mechanism `self`/`cls` call resolution already used). Surfaced 7 real cross-file override edges, previously invisible (`starontology/manchester.py`'s `_AstCursor` overriding `graph/parsers/manchester_parser.py`'s `_Cursor`).

## 2026-10-14 — regenerated (constructor calls + `tests/` extraction)

- 277 files extracted (96 source + 181 tests), 75,745 triples.
- Extractor changes: `slkg:instantiates` (constructor-call resolution, previously resolved to nothing) and `tests/` extracted as a second named root alongside source (closing the "testing linkage" competency questions - a test calling the function it exercises is now an ordinary `slkg:calls` edge across roots).

## 2026-10-14 — regenerated (call graph, overrides, visibility)

- Source only (`tests/` not yet extracted), 33,041 triples.
- Extractor changes: `slkg:calls` (project-wide, via a whole-codebase symbol-index pre-pass), `slkg:overrides` (same-file only at this point), `slkg:isPrivate`/`slkg:isDunder`. Found and fixed a real resolution-priority bug along the way (`shacl/validator.py::_default_validate()`'s own local import shadowing a same-named module-level function).

## Earlier

Docstring-cleanup initiative (multiple phases) plus the initial extractor build - not individually dated here; see git history for `codekg/extractor/` and `ontology.ttl` if needed.
