# Plan: Graph Workbench — a SHACL-driven tree viewer/editor (first app)

Status: planning only. No code has been written. Companion to [repo-prep-plan.md](repo-prep-plan.md) (repo-wide prep plan, workstream 5).

> Where the "Decisions" section below conflicts with later sections, the Decisions section wins. The later sections (including the milestone list and "Open questions") were drafted before the round-2 decisions and are kept for their detail.

## Context

First app built on starlayer; both a reference example for agents and a usable tool. Core idea:

- Inputs: a **data graph** (being edited), a **shapes graph** (validation + UI construction), optional **scoring graph** (SHACL UI widget scoring; falls back to the bundled one if present).
- Left: the data graph shown as a **tree**, conceptually infinite and recursive. Cycles are allowed: children load **lazily** on expand, so a cycle just means the same node can be expanded again at a deeper tree position.
- Right: selecting a tree node opens an **edit/view panel** whose fields are chosen from the `shui:` annotations (`shui:editor`/`shui:viewer`) and the SHACL UI scoring algorithm (`select_widgets`), validated live against the shapes.

Constraint from the user: do not disrupt the library being worked on. So the app is **additive and lives outside the library repo** (a separate `hidden-graph/starlayer-apps` repo, see Decisions; paths like `apps/graph_workbench/` below mean `graph_workbench/` in that repo). Library gaps found while building are logged (issue/TODO), not patched in place, unless the user decides otherwise.

## Decisions (round 2, from the user)
1. **Widget selection**: the SHACL UI scoring algorithm is built into starlayer. Running a node against a shape plus a scoring graph (`select_widgets`) yields a widget IRI per property; the app never scores. `shui:editor`/`shui:viewer` annotations feed the candidate set rather than bypassing scoring. The app's only widget logic is the **widget IRI → HTML template mapping** (one Jinja partial per widget class; visible fallback for unmapped IRIs). Gaps in the scoring graph are library/data issues; gaps in the mapping are app issues.
2. **Baseline scores**: starlayer should ship a generic datatype-keyed baseline scoring graph (curated, validated against `stsh:WidgetScoreShape`). That is a library addition, so it is deferred to a separate approved PR; until then the app carries a private copy with a "move upstream" TODO.
3. **UI layer is editable in the app**: scores, matchers, `shui:editor`/`viewer` pins, `sh:order`/`sh:group`, `shui:propertyRole`/label property. Shapes and scoring graphs get the same base + edit layer treatment as data; changes save to a **user scoring file**, never silently into the shipped baseline, so upgrades don't clobber user intent. A "UI config" tab shows each property's candidate widgets, scores and why (which matcher accepted or rejected), with live preview.
4. **Location** (revised 2026-10-20): its own repository, `hidden-graph/graph-workbench` (private), one repository per app, not a shared apps repo. An older private repo, `starlayer-apps`, already holds two PySide6 desktop editors (shapes and SPARQL) written against the pre-merge package names; it is separate and untouched. The workbench depends on `starlayer` (editable path locally, a pinned git URL in CI). Prior art to skim, in the personal `jclem326` account: `KnowledgeGraphExplorer`, `RDF_Tree_Claude`.
5. **Files are sufficient for v1** (Turtle/TriG/N-Triples). Store backends (Oxigraph/Fuseki) come later.
6. **Roots are selectable**, first-class: shape targets, `rdf:type`/class, explicit IRI list, SPARQL SELECT, all subjects, no-incoming. Root choice and display mode persist in a sidecar `.workbench.json`.
7. **Triple terms**: start with the easiest, read-only `<<( s p o )>>` chips; a `TripleTermEditor` widget (s/p/o sub-slots) lands in M3.
8. **Two-layer editing**: an immutable **base layer** and an **edit layer**. New triples go to the edit layer. A deletion is recorded in the edit layer as a `wb:Deletion` that `rdf:reifies` the deleted triple term (plus timestamp and optional reason); the base is never touched. A modification is a deletion plus an addition sharing a `wb:edit` id. Effective view = (base − deletions) ∪ additions, with display modes **merged / merged + highlights / base only / edits only** (deletions hidden or struck through). Validation runs on the effective view; undo/redo operate on the edit layer. Layers are combined on demand: **Save**, **Save As**, or **save edit layer only**, preceded by a diff view.
9. **Sessions are saveable as TriG**: "Save session" writes one TriG dataset with the edit layer (additions and `wb:Deletion` reifications), the UI-config edit layers (shapes, scoring), and a `wb:Session` metadata graph (base file paths plus RDFC hashes so a changed base is detected on reopen, chosen roots, display mode, selected node, undo/redo history). "Open session" restores it exactly. Default is reference + hash for base files, with an "embed base" option for portability. Save session is distinct from combine; the app warns on exit with unsaved edits. (This replaces any notion of an automatic sidecar edits file.)

10. **The shapes tab is editable, like the data tab** (added 2026-10-20, revised the same day): a tab changes what the tree and panel browse from the **data graph** to the **shapes graph itself** (and, the same way, the scoring layers), and the shapes are edited with the same machinery: the same tree, the same panel, the same working copy with undo and redo, the same validation. A change to the shapes shows on the data tab at once: labels, field order and sections, widgets and validation all recompute from the edited shapes, so the effect of a change can be seen as it is made. What drives the panel on the shapes tab is a **shapes-of-shapes**: SHACL shapes for `sh:NodeShape` and `sh:PropertyShape` with `shui:` widget annotations and form groups and order. The app writes its own, small and by hand, in standard terms only, covering the properties people actually set; validation of the shapes graph uses StarLayer's shipped meta-shapes (`shacl_shacl`), which also supply the name and description of every SHACL predicate. The archived presentation file in StarLayer's `docs/working/` is **not** used. StarLayer may later ship a UI-annotated version of its own (the item in `future_enhancements.md`, "Create SHACL UI (`shui:`) files for the SHACL validation files"), and the app's copy would then be dropped. Edits go to a shapes **edit layer** and save to a user shapes file, never silently into a shipped one (decision 3). Open questions: how to keep a shapes graph that is also its own subject from confusing the two views, and what "base" means for a shapes file the user created.
11. **The label, the order and the grouping come from the shapes** (built 2026-10-20): a node's tree label is a property shape marked `shui:propertyRole shui:LabelRole`, stored or computed with `sh:values`; the order of fields and of the tree's predicate groups is `sh:order`; sections are `sh:group` with the group's own `sh:order` and `rdfs:label`. Only standard terms are read: `shui:group` and `shui:order` are proposals in the SHACL UI draft (section 8.4 is a placeholder), so they are not looked for.
12. **Scoring is layered** (built 2026-10-20): the scoring catalog is a dataset of named graphs, a generic **baseline** (meant to move into StarLayer; feature request hidden-graph/starlayer#10), the app's own, and the user's `--scoring` file; a higher layer replaces a lower one widget by widget, and the result is split by role because `select_widgets` does not filter by role (#9).

### Revised milestones
- **M0** (done) skeleton in its own repo, CLI, fixtures (cyclic data), the import boundary.
- **M1** (done) lazy tree + root selection modes.
- **M2** (done) panel on the effective view, editing on a working copy with undo/redo, validation beside the field and in the tree, display modes (merged, highlights, base), grouping. The reified-deletion form of the edit layer is part of **saving the session** (M3).
- **M3** **the shapes tab, editable** (decision 10: two graphs being edited, each with its own undo, edits to the shapes recomputing the data view), then richer widgets (nested details/blank node, InstancesSelect at scale, language-tagged editors), `TripleTermEditor`, add/delete node, **TriG session save/open** (both graphs).
- **M4** UI-config editing (scoring layers in the UI), and the shapes-of-shapes moving into StarLayer.
- **M5** dogfood on the code KG, scoped validation and caching (see starlayer#7: `evaluate()` cannot be limited to one node), 50K-triple perf guard, "Report an issue" button.
- **Later**: store backends, native rdf-1.2 triple terms, baseline scoring graph moved into the library.

### Still open
- Vocabulary details for `wb:` (namespace, `wb:Session` fields) to be settled in M0 and shaped with SHACL.
- Whether the session TriG embeds the base by default (currently: no).

Stack follows the repo-wide starting assumptions: FastAPI/Starlette + Jinja2 + HTMX, no Node build, one vendored graph-viz lib only if/when needed (not in the first milestones — the tree is the primary view).

## What starlayer already gives us (reuse)
- `starlayer.shacl.ui_widget_selection.select_widgets(shape_node, focus_node, role, data_graph, scoring_graph)` (and `StarShaclSchema.select_widgets`, `validator.py:1916`) → a widget IRI per property of a node shape. Note: it runs SHACL validations per property, so results must be cached.
- `shui:editor` / `shui:viewer` annotations on property shapes (explicit widget choice; shapes in `starontology/` use ~20 widget classes: TextFieldEditor, TextAreaEditor, NumberFieldEditor, DatePickerEditor, DateTimePickerEditor, BooleanEditor, EnumSelectEditor, InstancesSelectEditor, IRIEditor, TextFieldWithLangEditor, TextAreaWithLangEditor, DetailsEditor, BlankNodeEditor, AutoCompleteEditor, and viewers LabelViewer, LangStringViewer, LiteralViewer, HyperlinkViewer, IRIViewer, ImageViewer, HTMLViewer, ValueTableViewer, DetailsViewer, BlankNodeViewer). `shui:propertyRole shui:LabelRole` marks label properties.
- `StarShaclSchema.validate` / `starlayer.shacl.validate` → `ValidationResult` (focus node, path, constraint component, message) to place errors on fields.
- `starlayer.shacl.target_nodes` → which nodes a shape targets (root nodes, and which shape(s) apply to a selected node).
- `starlayer.shacl.extract_subgraph` → shape-scoped neighbourhood (for scoped validation and a future "export this node" action).
- `StarLayerGraph` (rdf-1.1 default; rdf-1.2 + Oxigraph for native triple terms), `StarLayerDataset`, RDFC hashing for change detection.
- Guide `docs/guides/04d-shacl-ui.ipynb` for the intended semantics.

## Architecture

```
apps/graph_workbench/
  pyproject.toml            # depends on starlayer, starlette/fastapi, jinja2, uvicorn; extra [test]
  src/graph_workbench/
    __main__.py / cli.py    # python -m graph_workbench --data d.ttl --shapes s.ttl [--scoring sc.ttl] [--port]
    session.py              # Workspace: working graph, shapes, scoring, undo/redo change log, dirty state
    tree.py                 # TreeService: roots(), children(path, page), label(node)  (pure, no web)
    forms.py                # FormModelBuilder: (node, shape, role) -> neutral form model (dataclasses/JSON)
    edits.py                # EditOps: set/add/remove value, add/remove property, create/delete node -> ChangeSet
    validation.py           # ValidationIndex: run validate, index results by (focus, path), subtree error counts
    persistence.py          # load/save (Turtle, TriG, N-Triples; keep original format), diff of ChangeSet
    web/app.py, routes.py   # thin HTTP layer, returns HTML fragments (HTMX) or JSON (/api/...)
    web/templates/          # base, tree, panel, widgets/<WidgetName>.html, errors, diff
    web/static/             # vendored htmx.min.js, minimal css
  tests/ ; fixtures/ (small cyclic data + shapes + scoring)
```

Layering rule: `tree.py`, `forms.py`, `edits.py`, `validation.py` have no web imports and are unit-testable; `web/` only renders them. The form model is the contract that keeps other frontends possible.

## Key design

### 1. Tree: lazy, infinite, cycle-safe
- **Tree position identity = path**, not the RDF term. A tree node id is the sequence of `(predicate, direction, object)` steps from a root (hash-compact, e.g. `r:<root>/<step>/<step>`). The same RDF node reached via a cycle is a different tree position, so the tree is conceptually infinite and nothing is ever fully materialized.
- `children(path, page=0)` runs one bounded query for the node at the end of the path: outgoing object-valued triples (IRIs/blank nodes/triple terms), grouped under **predicate group rows** (label from the property shape's `sh:name`, else qname). Literals are not tree children; they live in the panel (optionally a count badge).
- **Lazy loading**: each expandable row carries `hx-get="/tree/children?path=…"` triggered on first expand (`hx-trigger="click once"`); nothing recursive is pre-rendered. Page size ~50 children per group with a "load more" row.
- **Cycle indication, not cycle prevention**: when the node already occurs in the ancestor path, the row gets a ↻ badge and tooltip "already open above (depth N); click to jump" — but it stays expandable (user wants the infinite view). Optional setting "collapse cycles" off by default.
- **Roots**: (a) instances targeted by node shapes (`target_nodes`), grouped by shape; (b) fallback "all subjects without incoming edges"; (c) user-entered focus IRI / search box. A root picker exists so huge graphs never load a complete root list (paged).
- **Inverse edges**: toggle "show incoming" to add inverse predicate groups (`^p`), off by default.
- **Labels**: `shui:LabelRole` property value → `rdfs:label`/`skos:prefLabel`/`schema:name` → qname → IRI tail; blank nodes show `_:b` + class/first property.
- **Error badges**: each row shows a count of violations on its own focus node; ancestor rows show a rolled-up count computed lazily from the ValidationIndex (cheap because results are indexed by focus node; roll-up only for rows already rendered).
- The `TreeService` takes a small `GraphAccess` interface (`out_edges(node, page)`, `in_edges`, `count`), implemented first over the in-memory `StarLayerGraph`, later over a SPARQL store (Oxigraph/Fuseki) so large graphs never load fully.

### 2. Edit/view panel driven by SHACL UI
- On selecting a row, `GET /panel?path=…&role=editor|viewer&shape=…`.
- **Which shape(s)**: all node shapes whose targets/`sh:class` apply to the node (via `target_nodes`); one → used; several → tabs; none → generic "no shape" panel (plain predicate/value list, editable as raw triples with datatype guesser).
- **Which widget per property**, in order: explicit `shui:editor`/`shui:viewer` on the property shape → else `select_widgets(shape_node, focus_node, role, data_graph, scoring_graph)` → else a built-in fallback by `sh:datatype`/`sh:class`/`sh:nodeKind`/`sh:in`.
- **Form model** (neutral, also served at `/api/panel?...` as JSON): shape, node, role, `fields[]` each with `path`, `label` (`sh:name`), `description`, `order` (`sh:order`), `group` (`sh:group`), `widget` IRI + render kind, `constraints` (min/max count, datatype, in-values, pattern, ranges), `values[]` (term, lang/dir, datatype), `errors[]` (message, constraint component, severity), `nested` (for details/blank-node widgets, the child form model, lazily fetched).
- **Widget templates**: one Jinja partial per widget class, shipped in tiers: M2 core (TextField, TextArea, NumberField, Boolean, IRI, EnumSelect, DatePicker/DateTimePicker, Label/Literal/LangString/Hyperlink/IRI viewers) → M3 (InstancesSelect, AutoComplete, Details/BlankNode, lang-aware editors, ValueTable) → later (RichText, Image, HTML viewer). Unknown widget IRI → fallback widget + visible "unsupported widget" note (feeds the feedback channel).
- **Object-valued fields**: an IRI/node-valued property shows the value as a link that selects/expands the matching tree row (and for `DetailsEditor`/`BlankNodeEditor`, an inline nested form).
- **Multi-valued fields** (`sh:maxCount` > 1 or absent): repeatable rows with add/remove; enforce min/max in UI hints but let the user violate and see the error (the shapes are the authority, not the UI).
- Viewer/editor **role toggle** and a global read-only mode.

### 3. Editing semantics and validation
- Edits operate on an in-memory **working graph**; each edit becomes a `ChangeSet` of triple adds/removes pushed onto an **undo/redo stack**. Nothing is written to disk until **Save**.
- On each applied edit: re-validate. v1 = full-graph `validate` debounced/background with the previous result shown until done; v2 = scoped validation using `extract_subgraph` around the edited node plus shape closure, merged into the index (measure first; do not optimize blindly). HTMX responds with the updated field (inline errors) and an out-of-band swap for the tree badges.
- **Pending changes panel**: human-readable diff (added/removed triples grouped by subject) before Save; RDFC hash (`starlayer.graph.rdfc`) detects "dirty" reliably.
- **Create / delete node**: "add instance of shape S" (pre-fills `rdf:type`, required properties per `sh:minCount`, `sh:defaultValue`), delete node (with warn about incoming references).
- **Blank nodes**: stable ids within a session; edit via nested forms; serialization preserves them.
- **Save**: back to the loaded file in its original syntax (Turtle/TriG/N-Triples), or Save As; backend-store save (Oxigraph/Fuseki) is a later milestone.
- RDF 1.2 features: show/edit language+base direction (`DirLangString`); triple terms displayed read-only in M1–M3 (editing them needs the rdf-1.2/Oxigraph path — decide later).

### 4. HTTP surface (all single-user, local, localhost-bound by default)
`GET /` shell · `GET /tree/roots?shape&q&page` · `GET /tree/children?path&page` · `GET /panel?path&role&shape` · `POST /edit` (op payload → returns updated field fragment + OOB tree badge) · `POST /undo` `/redo` · `GET /changes` · `POST /save` · `GET /validation` (summary list, click-to-select) · `GET /api/panel`, `/api/tree/*` (JSON mirror of the form model/tree for agents and other frontends) · `POST /feedback-url` (later; builds a pre-filled GitHub issue URL, never posts).

### 5. Session/concurrency
Single user, one workspace per process for v1. Server-side state in memory, guarded by a lock. No auth; bind to 127.0.0.1 and refuse non-local binds unless an explicit flag is passed. Concurrent-tab safety: edits carry a workspace version; stale edit → 409 with refresh fragment.

## Milestones (each independently shippable and tested)
- **M0 Skeleton**: package, CLI loads data+shapes(+scoring), serves shell, fixtures (small cyclic data e.g. persons who `knows` each other and an org hierarchy; shapes with `shui:editor/viewer` and `sh:order/group`).
- **M1 Lazy tree**: roots, children paging, predicate groups, labels, cycle badge, inverse toggle, search. Pure `TreeService` tests (cycle, depth, paging, determinism).
- **M2 Viewer/editor panel (core widgets)**: shape resolution, widget resolution (explicit → `select_widgets` → fallback), form model JSON, core widget templates, edit ops, undo/redo, inline validation errors + tree badges, role toggle.
- **M3 Richer UI**: nested details/blank-node forms, InstancesSelect/AutoComplete, lang-aware editors, add/delete node, pending-changes diff, Save/Save As.
- **M4 Scale and stores**: `GraphAccess` over Oxigraph/Fuseki via SPARQL for `children`, scoped validation, caching of `select_widgets` per (shape, focus-class), large-graph smoke test.
- **M5 Dogfood + polish**: load the code KG (`codekg` slice) with a hand-written shapes file to browse it (bounded paging, per the "explore, never ingest" principle); "Report an issue" button; docs page `docs/app-stack-guidance.md` first "did the default stack hold?" note; `examples/` entry + curated-KG nodes linking the app to the capabilities it exercises.

## Testing
- Unit (no web): `TreeService` (cycle → distinct paths, lazy bounded queries, paging, inverse edges), `FormModelBuilder` (explicit `shui:editor` wins, scoring fallback, defaults), `EditOps` + undo/redo round-trip, `ValidationIndex` (indexing, roll-ups), persistence round-trip (RDFC-isomorphic after save/load).
- Web: Starlette `TestClient` on fragments (expand returns only one level; edit returns the field with the error; OOB badge present); JSON API snapshot tests of the form model.
- Browser: 2–3 Playwright smoke tests (expand a cyclic node twice; edit invalid value → inline error → fix → clears; save and reload).
- Conformance/spec: widget selection cases reuse the SHACL UI fixtures already in `tests/shacl/` where possible; unsupported-widget fallback test.
- Performance guard: a generated 50K-triple graph test asserts `children` and `panel` stay within a latency budget and never touch more than a page of data.

## Open questions for the user
1. "`sh:ui`" — I'm reading this as the SHACL UI vocabulary (`shui:`): `shui:editor`/`shui:viewer` plus widget scoring. Confirm, and whether `shui:` annotations or scoring-based selection should win when both exist (plan: explicit annotation wins).
2. Location: separate `apps/graph_workbench/` project (recommended, zero library disruption) vs. `examples/` inside the library repo tree vs. a new GitHub repo.
3. Editing target for v1: in-memory file (Turtle/TriG) only, or must a live store (Oxigraph/Fuseki) be supported from the start?
4. Roots: are node-shape targets the right default roots, or should the first screen be a "pick a focus node / query" picker?
5. Do triple terms (RDF 1.2) need to be editable in v1, or is display-only fine?

## Risks
- `select_widgets` cost (validation per property) → cache per (shape, focus node class); measure in M2.
- SHACL UI is a draft spec and the matcher cardinality is contested upstream (w3c/data-shapes#1249) → treat unsupported cases as fallback + visible note, not errors.
- Full-graph revalidation latency on large graphs → debounce + scoped validation in M4.
- HTMX fits forms well; a very interactive drag-to-connect view would need more JS → deferred; tree + forms first.
- Any library bug/gap discovered → record as a feedback-style issue, don't patch while the library is in flux.
