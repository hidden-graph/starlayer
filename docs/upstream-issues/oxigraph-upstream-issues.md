# Oxigraph Upstream Issues

*Last reviewed: 2026-10-16*

Bugs found in [Oxigraph](https://github.com/oxigraph/oxigraph), the engine behind this project's `rdf-1.2` Oxigraph backends (in-process through `pyoxigraph`, or remote through `oxigraph serve`). Each issue has two parts:

- **Upstream report** - a self-contained write-up that says nothing about this project, written to be pasted into a GitHub issue on `oxigraph/oxigraph` as-is.
- **In this project** - how it was found here, what it affects, how it is tested, and its status.

Same overall conventions as `rdflib-upstream-issues.md`.

## Status Summary

| # | Issue | Where the defect is | Reported upstream? |
| --- | --- | --- | --- |
| 1 | SPARQL `=` panics the whole engine on any `rdf:dirLangString` term | Oxigraph core (`spareval` crate) - affects both `pyoxigraph` and `oxigraph serve` | **Not yet** - ready to file |

---

## Issue 1 - SPARQL `=` panics on any `rdf:dirLangString` term (aborts the whole process)

### Upstream report

*(Everything in this subsection is project-neutral and can be pasted into a GitHub issue as written.)*

#### Summary

Evaluating the SPARQL `=` operator on a term of datatype `rdf:dirLangString` (an RDF 1.2 base-direction literal such as `"hi"@en--ltr`) hits an `unreachable!()` in the `spareval` crate and panics. The panic is a hard process abort: the Python interpreter dies under `pyoxigraph`, and `oxigraph serve` exits, so the client sees only a dropped connection and no SPARQL error.

The operand does not matter. Comparing a single stored value with itself is enough.

#### Minimal reproduction

```python
import pyoxigraph as ox

store = ox.Store()
store.update('INSERT DATA { <http://example.org/a> <http://example.org/title> "hi"@en--ltr }')
list(store.query('SELECT ?s WHERE { ?s <http://example.org/title> ?t . FILTER(?t = ?t) }'))
```

The same defect through the server (the data loaded the same way into a graph):

```
curl -X POST http://localhost:7878/query \
     -H 'Content-Type: application/sparql-query' \
     --data 'SELECT ?s WHERE { ?s <http://example.org/title> ?t . FILTER(?t = ?t) }'
```

#### Observed

```
thread '<unnamed>' panicked at lib/spareval/src/dataset.rs:350:27:
internal error: entered unreachable code
```

then `SIGABRT`. Under the server the container exits with status 133 (`128 + SIGABRT`), and the client gets `ConnectionError` / `RemoteDisconnected` with no response body.

#### Expected

`=` over two `rdf:dirLangString` terms returns `true` when value, language and direction all match, `false` otherwise, as for the other literal datatypes.

#### Which operations are affected

Tested one at a time, so the trigger is not mistaken for a particular function:

| Scenario | Aborts? |
| --- | --- |
| Construct a `dirLangString` with `STRLANGDIR()`, no comparison | No |
| Read a stored `dirLangString` value, no comparison | No |
| `sameTerm(?t, ?t)` on a stored value | No |
| `FILTER(?t = ?t)` - one stored value against itself | **Yes** |
| `FILTER(?t1 = ?t2)` - two independently stored values | **Yes** |
| `STRLANGDIR(...) = STRLANGDIR(...)` - no stored data at all | **Yes** |
| A stored value `=` a `STRLANGDIR()`-built one | **Yes** |

So the trigger is `=` (value equality) applied to a `dirLangString`, unconditionally. `sameTerm()` is a different operator with no per-datatype value-equality dispatch, and is unaffected.

#### Root cause

In `lib/spareval/src/dataset.rs`, `impl PartialEq for ExpressionTerm` has an explicit match arm for every variant of the enum except `DirLangStringLiteral`, which falls through to the final `(_, _) => unreachable!()`. The sibling `impl Hash for ExpressionTerm` a few lines below does handle `DirLangStringLiteral` (`(value, language, direction).hash(state)`), so the variant was wired into `Hash` but the matching `PartialEq` arm was never added.

A one-arm fix:

```rust
(
    Self::DirLangStringLiteral { value: lv, language: ll, direction: ld },
    Self::DirLangStringLiteral { value: rv, language: rl, direction: rd },
) => lv == rv && ll == rl && ld == rd,
```

#### Where it lives

In Oxigraph itself, not in a language binding. `spareval` is part of the Oxigraph repository and is shared by every front end. The identical defect was confirmed through:

- `pyoxigraph` 0.5.11 (the Python package), and
- the official `ghcr.io/oxigraph/oxigraph` server image reporting `oxigraph 0.5.9`.

It was also checked directly against `main` through the GitHub API on 2026-10-16: the missing arm is still absent from current unreleased code, so it is not fixed and awaiting a release.

#### Not a spec ambiguity

Apache Jena Fuseki 6.1.0 (ARQ) returns correct results for every row of the table above, including `?t = ?t` and `?t = STRLANGDIR(...)`, with the server healthy throughout. So this is a gap in `spareval`, not a corner where engines reasonably disagree.

#### Duplicate check

Searched `oxigraph/oxigraph` issues and pull requests, open and closed, with `gh search issues` / `gh search prs`, for: `dirLangString`, `DirLangStringLiteral`, `BaseDirection`, `STRLANGDIR`, `spareval` + `dirLang`, `entered unreachable code`, `RDFterm-equal`, and `direction literal`. No existing report matches.

---

### In this project

#### How it was found

By answering the question "have we run all the tests with an Oxigraph?". A temporary diagnostic on an experimental branch (`oxigraph-wip-2026-10-16`; nothing like it remains on the working branches) redirected every bare `StarLayerGraph()` / `StarLayerDataset()` in the whole test suite onto an in-process Oxigraph. The suite aborted partway through (`Fatal Python error: Aborted`) at `tests/graph/unit/test_dirlangstring.py::TestSparqlFunctions::test_strlangdir_constructs_matching_value`, a query filtering on `?t = STRLANGDIR(...)`.

**That test is not an Oxigraph test.** It is a unit test of the `STRLANGDIR()` function that normally runs on the default in-memory store; it reached Oxigraph's engine only because the diagnostic redirected it. The Oxigraph-backed `dirLangString` coverage that did exist (cross-backend parity's write/read and function scenarios, the W3C `lang-basedir` fixtures) never compares two `dirLangString` values with `=`, the one operation that aborts. So the bug sat in a gap between tests that all passed.

The first write-up wrongly scoped the trigger to `STRLANGDIR()`; the narrower variants in the table above, run one at a time against bare `pyoxigraph`, corrected that the same day.

#### What it affects

`StarLayerGraph(store=OxigraphStore(...), backend='rdf-1.2')` (the in-process route) and a remote Oxigraph `rdf-1.2` graph both hand SPARQL straight to the affected engine. A caller who relies on `=` equality over `dirLangString` data (not only via `STRLANGDIR()`) will hit the abort today.

It is not worked around in this project's code: a process abort cannot be caught from Python, and rewriting `=` to `sameTerm()` is only valid where exact-term rather than value equality is acceptable. The default in-memory (`rdf-1.1`) representation is unaffected: `TestSparqlFunctions` exercises exactly this comparison there and passes, with no Oxigraph involved. A project-side guard is tracked in `packages/starlayer/docs/future_enhancements.md`.

#### How it is tested

`tests/graph/integration/test_oxigraph_store_rdf12.py::TestDirLangStringEquality`:

- confirms `sameTerm()` works over a `dirLangString` on the Oxigraph store route, and
- reproduces the abort in a subprocess for both the self-equality case and the original `STRLANGDIR()` comparison.

The abort tests fail loudly, with instructions, if Oxigraph fixes this upstream.

`oxigraph_dirlangstring_crash_repro.ipynb` (same folder) is a runnable version of the upstream report: the working baselines run live, and the crashing cases carry the real captured subprocess output (stderr panic trace and exit code), since executing them in the notebook's own kernel would kill it.

#### Status

Confirmed live, pending upstream report. Re-check against the latest `oxigraph` / `pyoxigraph` release before filing.
