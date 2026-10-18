# Documentation map

Every document in the repository, by what you want to do. Files marked *generated* are built by `python scripts/build.py`; do not edit them by hand.

## Learn StarLayer
- [User guides](guides/README.md): notebooks, from [getting started](guides/01-getting-started.ipynb) through graphs, SPARQL, SHACL, ontologies and storage. [STYLE_GUIDE.md](guides/STYLE_GUIDE.md) is for guide authors.
- [Appendix A: public resources](guides/appendix-a-public-resources.ipynb): the ontologies, shapes and profiles the library publishes, with links.

## Look something up
- [Functionality overview](generated/functionality-overview.generated.md) (*generated*): what StarLayer does today and what is planned.
- [API overview](generated/api-overview.generated.md) and [API reference](generated/api-reference.generated.md) (*generated*): the public API, one line per symbol and in full.
- Rules and gotchas for each area, at the top of [graph](../packages/starlayer/starlayer/graph/CLAUDE.md), [sparql](../packages/starlayer/starlayer/sparql/CLAUDE.md) and [shacl](../packages/starlayer/starlayer/shacl/CLAUDE.md) `CLAUDE.md`. What changed, by theme: the `CHANGELOG.md` beside each.

## How it is designed, and how closely it follows the specs
- Graph: [docs/graph/](../packages/starlayer/docs/graph/README.md) (architecture, SPARQL 1.2 design, the RDF 1.2 and SPARQL 1.2 gap analyses, the Protocol and Interoperability analyses, performance, testing strategy).
- SPARQL and SRL: [docs/sparql/](../packages/starlayer/docs/sparql/README.md); [design of `StarQuery` and the SRL `RuleSet` enhancements](../packages/starlayer/docs/sparql_srl_object_model_design.md).
- SHACL: [docs/shacl/](../packages/starlayer/docs/shacl/README.md) (implementation plan, the SHACL 1.2 gap matrix, compatibility, W3C test suite plan).
- [Open items and deferred follow-ups](../packages/starlayer/docs/future_enhancements.md). Some entries are stale; check before relying on one.

## Known bugs in other projects
[docs/upstream-issues/](upstream-issues/): rdflib, pySHACL, Oxigraph and Fuseki bugs we found, each with a minimal repro and where we work around it.

## The knowledge graph
The code knowledge graph (`codekg.trig`) and the capability graph (`functionality.ttl`) are in [`starlayer/codekg/`](../packages/starlayer/starlayer/codekg/). Its [competency questions](../packages/starlayer/starlayer/codekg/competency-questions.md) list what it can answer. Do not read `codekg.trig` directly; see [AGENTS.md](../AGENTS.md).

## Plans
- [App development plans](app-development-plans/README.md): preparing the repository for app development, and the first app. Planning only.
- [docs/working/](working/): archived and in-progress material (the retired hand-written API reference, the SHACL presentation shapes). Not maintained.

## For contributors
[CONTRIBUTING.md](../CONTRIBUTING.md) and [AGENTS.md](../AGENTS.md).
