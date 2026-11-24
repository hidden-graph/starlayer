# Profiles of `starlayer` itself

*Moved from `docs/guides/05e-shacl-profiling.ipynb`, section 6 (2026-11-21). This is not implemented as code; it is the direction the profiling pattern would extend to.*

Extending the same pattern one level further: `starlayer` implements a documented subset of RDF 1.2, SPARQL 1.2, and SHACL 1.2. Following §3's own two-step relationship (a profile is a *specification*; an implementation *conforms to* it, rather than being a profile itself) — the actual profile isn't `starlayer` the software, it's `starlayer`'s own documented scope: the gap-analysis documents, the scope-reduction notes already scattered through each subpackage's own `CLAUDE.md` (SRL's documented grammar reductions, the RDF 1.2 interop gaps, etc.). `starlayer` would then *conform to* that profile — the same relationship a SHACL validator has with the Core Profile.

Breaking this down by subpackage:
- `starlayer.graph` would be a profile of RDF 1.2 (Concepts/Schema/Turtle/N-Triples/XML/Canonicalization), SPARQL 1.2 Protocol, and the individually-supported Entailment Regimes.
- `starlayer.sparql` would be a profile of SPARQL 1.2 Query/Update/RL.
- `starlayer.shacl` would be a profile of SHACL 1.2 (formalized in section 5 of the SHACL profiling guide).
- **`starlayer` specifics** — vocabulary/tooling with no external spec to be a profile *of* at all: `manch:`/`sqe:`/`spexpr:`/`srl:` (`starlayer`'s own invented syntax-tree encodings), the `shnex:` node-expression extensions. These don't fit the "profile of X" framing — there's no `prof:isProfileOf` target for them — and would need some other treatment, not a forced claim.
- The **whole-library roll-up** ("the `starlayer` profile" as the union of the above) has no ready-made formal mechanism to lean on. Even SHACL's own "Union Profile" is prose-only in the spec itself ("the conceptual whole... covers all aspects"), not a derivable triple anywhere in dx-prof — a precedent for staying prose-only here too, though reaching outside dx-prof entirely (e.g. Dublin Core's `dcterms:hasPart`) for something actually derivable is also an option.

What's still undecided: whether each subpackage should get its own real `prof:Profile` resource (mirroring SHACL's own Core/SPARQL/etc.), replacing the current plain `dcterms:conformsTo <raw TR document>` claim in `conformance.declared_conformance()`; what, if anything, the roll-up/union should assert beyond prose; and where the `starlayer`-specific vocabulary (no external spec) gets documented, if not as a profile claim at all.
