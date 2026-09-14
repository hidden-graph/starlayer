# 3.a SPARQL rules (pending)

SPARQL-RL (SRL) — a separate, Datalog-style rules language, published standalone at [SPARQL 1.2 RL](https://www.w3.org/TR/sparql12-rl/) — is deliberately out of scope for this project. starshacl already executes RDF-native SHACL rules (`sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, covered in the [SHACL inference rules guide](04b-shacl-inference-rules.ipynb)); SRL is a parallel *human-authoring text syntax* for a similar idea, not something those rules depend on, and starshacl has no parser for it (RDF is the real interchange format either way).

See `packages/shacl/docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred" table for the full reasoning and status.
