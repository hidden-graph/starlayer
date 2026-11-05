# D3 notes: guides, docs and clean-up after the switch (branch `mig-d3`, from `shacl-engine` at 29ad8aa)

1. **Guide 06b is kept, not retired, and cut down.** StarLayer has no remote SPARQL client any more (`backends/native` with `http_select`,
   `http_update`, `http_construct`, `http_ask` was deleted at D1) and no public module replaces it: a graph object does not talk to an endpoint,
   and nothing sends SPARQL updates to one. What does exist is `SERVICE` inside a query run on a `StarLayerGraph` (pyoxigraph's HTTP client;
   checked against a local stub endpoint: the call goes out as a POST and joins the answer; an unreachable endpoint raises an `OSError`
   subclass, `SERVICE SILENT` returns no rows). So the guide now has two sections: the on-disk store (unchanged cell) and a read-only
   `SERVICE` query (one cell, skips on `OSError`). Removed: the `demo_sparql_endpoint` cell, the RDF 1.1 endpoint section and its cell, the
   reasoning-enabled Fuseki section and its cell. Writing to a remote endpoint and a Fuseki that reasons are now the reader's own HTTP
   client; the guide says so. The file name and its README entry stay (README line rewritten). The one notebook link of the guide
   (`06b-252791c5`) now points at `_Base.query` (the cell is a `StarLayerGraph.query` call) and was restamped after reading the cell.
   `_no_backend()`'s `TypeError` in `oxgraph/core.py` no longer names the deleted HTTP functions; it says a query can read an endpoint with `SERVICE`.
2. **Notebooks were run with a script, not `pytest --notebooks`.** `pytest --notebooks` executes the guides but throws the outputs away.
   The run used nbclient with `allow_errors=True` (as the test does), `PYTHONHASHSEED=0`, `PYTHONPATH=packages/starlayer`, cwd `docs/guides`,
   and wrote the executed notebook back with `nbformat.write`. Result: 29 of 29 ran with no cell error after the 06b fix (the first run had
   one: 06b's `SERVICE` cell raised `ConnectionRefusedError`, not `URLError`, for `localhost:7878`, so the cell and the markdown now say `OSError`).
   Stored outputs now contain no `OxGraph` / `OxDataset`. Two source comments in 04 and 04a still said "OxGraphs" and were changed to
   "StarLayerGraphs" (comment-only; their stored outputs did not change).
3. **`graph/CLAUDE.md` and `sparql/CLAUDE.md`**: everything below "Rules that bite" was replaced by a short "How the code is laid out" /
   "What is here" section, each claim checked against the modules. The three standing "tracking upstream" notes of `graph/CLAUDE.md` are
   folded into the rules block, which already had them; the dated history entries (about 400 lines each) are dropped, git history keeps them.
   Two stale code texts found while checking: the docstring of `oxgraph/run.py` (named `graph.query.direct`) and the docstring and error
   message of `sparql/spexpr_codec.py::_encode_list` (said `import starlayer.graph` applies a rdflib patch that D1 deleted).
   `README.md` listed TriX, "Fuseki or SQLAlchemy" storage and JSON-LD 1.1 as features of `starlayer.graph`: reworded to what `oxgraph/formats.py` offers.
   The older design notes in `packages/starlayer/docs/graph/` (`starlayergraph.md`, `starlayergraph_vs_rdflib.md`, `sparql12_design.md`,
   `sparql12_protocol_gap_analysis.md`, `fuseki-reasoning-setup.md`, `performance.md`) are marked "Historical" at the top and in that folder's README; they were
   not rewritten.
4. **Removed**: `scripts/b1_flip_experiment.py` (patches `graph/graph/starlayer_graph.py` / `starlayer_dataset.py`, deleted at D1),
   `scripts/b1_classify.py` (classifies the output of that experiment) and `tests/shacl/integration/test_expression_node_types.py-E` (a sed
   backup of the real test from before the rename). `docs/working/b1-classification.md` still mentions the scripts; it is history.
5. **Left alone, for a decision**: the `sqlalchemy` and `oxigraph` extras in `pyproject.toml` (`rdflib-sqlalchemy`, `oxrdflib`) serve only the
   deleted rdflib store paths (the `oxigraph` comment still describes `StarLayerGraph(store=OxigraphStore(...), backend='rdf-1.2')`);
   README and AGENTS list them. Removing them touches `uv.lock`. Also `packages/starlayer/docs/future_enhancements.md` has many entries about the old class
   and `backends/native.py`.
