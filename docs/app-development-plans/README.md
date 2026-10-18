# App development plans

Planning documents for preparing starlayer for app development. **Status: planning only; none of this is implemented yet.**

| Plan | What it covers |
|---|---|
| [repo-prep-plan.md](repo-prep-plan.md) | Making the repo self-explaining for humans and agents: a root `AGENTS.md`, a knowledge-graph-first workflow (explore through bounded named queries, never ingest the whole graph), a query library stored as a graph of SQE graphs, curated-KG enrichment, runnable examples, stale-doc fixes with CI guards, a GitHub feedback channel, and a query log that feeds an auto-generated FAQ. Also records the default app stack (FastAPI + Jinja2 + HTMX). |
| [graph-workbench-app.md](graph-workbench-app.md) | The first app: a SHACL-driven graph viewer/editor with a lazy, cycle-safe tree, an edit/view panel whose widgets come from SHACL UI scoring, a base + edit layer model (deletions recorded as reifications), saveable TriG sessions, and in-app editing of the UI layer. Planned to live in a separate `hidden-graph/starlayer-apps` repo. |

Open questions are listed at the end of each plan. Where a plan's "Decisions" section conflicts with later text in the same file, the Decisions section wins.
