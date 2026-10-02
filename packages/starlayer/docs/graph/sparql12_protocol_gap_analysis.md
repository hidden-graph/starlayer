# SPARQL 1.2 Protocol vs. Implementation — Conformance Status

**Reviewed:** 2026-09-27, against the editor's draft at `https://www.w3.org/TR/sparql12-protocol/`. This is a snapshot conformance checklist for the one place this document's requirements actually land in this codebase — `starlayergraph/backends/native.py`, the HTTP client the native (`backend="rdf-1.2"`) backend uses to talk to a real SPARQL endpoint (Fuseki, Oxigraph). The in-memory (`backend="rdf-1.1"`, default) backend never makes an HTTP request at all and is out of scope for this document entirely.

## What's new in the 1.2 revision

Almost nothing. Per the spec's own Appendix A changelog, the entire diff from SPARQL 1.1 Protocol is: an added informative example of reified triples, an added HTTP `QUERY` method (RFC 10008) as a third transport option alongside GET/POST, editorial polish, and "change[d] normative language regarding what media types must be returned for a query request." There is no new required media type, no new dataset-selection parameter, and no protocol-level field for triple-term or direction-tagged-literal bindings — those are governed entirely by the separate SPARQL 1.2 Query Results JSON/XML Format documents, not this one. The one genuinely new, RDF-1.2-relevant mechanism is the **`version` announcement** (§2.1): an optional `version` parameter (GET/form-POST) or `version` media-type parameter on `Content-Type: application/sparql-query`/`application/sparql-update` (direct POST), with a server optionally echoing it back on the response `Content-Type`. Both directions are **MAY**-level.

**The Graph Store HTTP Protocol is not part of this document** — §1 explicitly spins it off into its own separate spec. Nothing in this analysis concerns GSP.

## Role check: this project is a client, not a server

Confirmed by a repo-wide grep for any HTTP server framework (`flask`/`wsgi`/`http.server`/`BaseHTTPRequestHandler`/`serve_forever`) across every `.py` file in both `starlayergraph` and the sibling `starsparql` package: nothing. `backends/native.py` only ever calls `requests.post(...)` against a `query_endpoint`/`update_endpoint` resolved from an rdflib `SPARQLUpdateStore`. This project sends SPARQL Protocol requests; it never accepts them. That settles most of §4 (Policy Considerations/Security) and §5's server-side conformance obligations as inapplicable by role, not by gap.

## Section-by-section

### §2.2 Query Operation

| Spec mode | Used by `native.py`? |
|---|---|
| §2.2.1 GET, `query` in querystring | No |
| §2.2.2 POST, form-urlencoded | No |
| §2.2.3 POST direct, `Content-Type: application/sparql-query`, raw body | **Yes** — `http_select()`, `http_construct()`, `http_ask()` all use exactly this |

A legitimate, conformant single-mode choice — and a deliberate one: `docs/fuseki-upstream-issues.md` Issue 2 documents a real Fuseki (ARQ) bug specific to this submission mode (inconsistent blank-node labels across SELECT result rows when a blank node appears both as an ordinary binding and nested inside a `"type":"triple"` value). Switching to GET was considered and rejected there (query-length limits; inconsistency with `http_update()`, which has no GET equivalent at all). The affected W3C fixtures are instead marked as known Fuseki-only divergences.

- **§2.2.4 Dataset specification** (`default-graph-uri`/`named-graph-uri`): never sent. Scoping is instead handled entirely by `GRAPH <uri> { }` clauses already embedded in the query text — confirmed in `native_query()`'s own docstring. A legitimate alternative channel the spec itself treats as equally valid (protocol-level parameters only need to "win" if both channels are present simultaneously, which can't happen here since this project never populates the protocol-level one).
- **§2.2.5 Accepted Response Formats**: content negotiation is used, just never varied — `Accept: application/sparql-results+json` for SELECT/ASK, `Accept: text/turtle` for CONSTRUCT/DESCRIBE, always. No CSV/TSV/XML results, no N-Triples/RDF-XML/JSON-LD alternatives. Legitimate: the client only needs to request formats it can parse, and JSON results + `turtle12` cover this project's own term model (triple terms, dir-lang-strings) completely.
- **Minor real gap**: `http_construct()` never checks the response's actual `Content-Type` before parsing the body as `format='turtle12'`. Not exploitable against Fuseki/Oxigraph today (the `Accept` sent has no wildcard, so a conformant server can't substitute another format), but a future server ignoring `Accept` would fail with an opaque Turtle-parser error instead of a clear "unexpected response format" one.
- **§2.2.6/2.2.7 Success/failure**: every call ends in `resp.raise_for_status()` — a generic `requests.HTTPError` for any non-2xx status. The spec distinguishes 400 (malformed query, client-side bug) from 500 (server-side execution failure) as separately meaningful; `native.py` doesn't currently surface that distinction.

### §2.3 Update Operation

Same single-mode pattern: `http_update()` always sends `Content-Type: application/sparql-update` with the raw update string as the body (§2.3.2's "POST directly" mode). `using-graph-uri`/`using-named-graph-uri` are never sent — dataset scoping goes entirely through `USING`/`WITH`/`GRAPH` clauses already present in the update text, confirmed in `native_update()`'s own docstring (which also documents bypassing rdflib's own store dispatch entirely, to work around `SPARQLStore._is_contextual()` wrapping updates in an illegal extra `GRAPH <urn:x-rdflib:default> { }` block). Since protocol-level `using-graph-uri` is never populated, the spec's stated error condition (supplying it alongside a query text that already has its own `USING`/`WITH`) can't arise here. §2.3.4 success responses are correctly never parsed (implementation-defined body; only status is checked).

### §2.1 Version Announcement — the one genuine, minor protocol gap

`starlayergraph` already takes the *in-band* SPARQL-text `VERSION "1.2"` directive seriously on the native path (`check_native_version_conformance()`, built specifically because neither Fuseki nor Oxigraph surfaces a warning for a text/usage mismatch on its own). But the Protocol spec's version announcement is a *separate*, out-of-band channel — a `version` parameter or `Content-Type` media-type parameter alongside the request, with an optional echo back on the response. `native.py` never sets either direction: every request's `Content-Type` is bare (`application/sparql-query`/`application/sparql-update`, no `version=` parameter), regardless of whether the query text itself declares `VERSION "1.2"`, and no response header is ever inspected for an echoed value.

This is **MAY**-level both directions, so its absence is not a conformance failure — but it's the one piece of this spec that's genuinely new for RDF 1.2 and genuinely unimplemented here; everything else `native.py` does (or deliberately doesn't do) predates or is orthogonal to the 1.2 revision.

### §4.1 Security / Authentication

Not this project's obligation beyond what it already does: credentials, when needed, are supplied via rdflib's own `SPARQLUpdateStore(auth=(...))`, pre-encoded into an `Authorization` header that `resolve_store_http()` picks up and every HTTP call merges in. The spec only says a service *may* require HTTP authentication — a server-side option this client already supports using when required, nothing further to implement.

## Not planned, and why

- **Any server-side implementation of this protocol.** Confirmed by repo-wide grep: no HTTP server anywhere. This project is, and has only ever been, a client/passthrough role.
- **GET-based query submission.** Deliberately avoided per `fuseki-upstream-issues.md` Issue 2 (query-length limits, plus consistency with `http_update()`'s POST-with-body convention, which has no GET equivalent under the spec).
- **Form-urlencoded submission for either operation.** No reason to prefer it over the direct-body mode already used consistently for both; would only matter against a target endpoint that rejected direct-body POST, which neither Fuseki nor Oxigraph does.
- **The HTTP `QUERY` method (RFC 10008).** New in this revision, explicitly optional, and not yet supported by either test target (Fuseki, Oxigraph) as far as this project's own testing has gone.
- **CSV/TSV/XML results, or non-Turtle CONSTRUCT alternatives.** The client only needs formats it already parses; adding more would add parsing surface for zero functional gain.
- **The Graph Store HTTP Protocol.** A separate W3C document by this spec's own hand, not part of it at all; this project has no graph-resource-management-via-HTTP code anywhere.
- **Dataset selection via protocol parameters.** Superseded by the existing, equally spec-legal convention of embedding `GRAPH`/`USING`/`WITH` clauses directly in query/update text, which already integrates cleanly with `StarLayerDataset`'s multi-graph model.

## If this were picked up: concrete, file-level changes

None of the following is a conformance requirement — they're the genuine minor loose ends found above:

1. **Out-of-band version announcement** (`backends/native.py`): add an optional `version` media-type parameter to the `Content-Type` header sent by `http_select()`/`http_construct()`/`http_update()`/`http_ask()`, sourced from whatever `check_native_version_conformance()`'s underlying `strip_version_directive()` (`starlayergraph/query/version_directive.py`) already parses out of the in-band `VERSION` directive - the value is already computed today, just never round-tripped onto the wire. Reading back an echoed response `version` has no clear present use (neither Fuseki nor Oxigraph populates it) and would need live verification first.
2. **Content-Type verification in `http_construct()`** before handing the body to `StarLayerGraph.parse(..., format='turtle12')` - raise a clear "server returned an unexpected format" error instead of an opaque Turtle-parser failure.
3. **Distinguish HTTP 400 vs 500** at all four `native.py` call sites - a dedicated exception carrying `resp.status_code` and body text, so a malformed-query bug reads differently from a transient server failure.

## Files read in full for this analysis

- `packages/graph/starlayergraph/backends/native.py` (entire file)
- `packages/graph/docs/rdf12_sparql12_gap_analysis.md` (template/model document)
- `packages/graph/docs/fuseki-upstream-issues.md` (Issue 2)
- `packages/graph/starlayergraph/graph/starlayer_graph.py` / `starlayer_dataset.py` (native-backend dispatch, auth usage)
