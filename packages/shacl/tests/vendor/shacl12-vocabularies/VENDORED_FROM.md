# Vendored snapshot provenance

Do not hand-edit `shacl-shacl.ttl` in this directory - it's a manually re-fetched snapshot (no sync script yet, unlike `tests/vendor/shacl12-test-suite/`), so any local edit will be silently overwritten the next time someone re-syncs it.

- Source: https://github.com/w3c/data-shapes/blob/gh-pages/shacl12-vocabularies/shacl-shacl.ttl
- File's own last-touching commit SHA (`gh-pages` branch): `922c034d7e03e5253da17c6dd4a065496f269241` (2026-06-18)
- Fetched: 2026-08-01
- File itself is headed "THIS VERSION IS UNDER DEVELOPMENT BY THE DATA-SHAPES (SHACL 1.2) WG" - an active work in progress, not a stable/versioned release. Re-fetch and re-diff periodically rather than treating this snapshot as final - see `docs/shacl12-gap-matrix.md`'s "Official SHACL 1.2 meta-shapes (shsh:) comparison" section for the current comparison and what to re-check when this file changes.
