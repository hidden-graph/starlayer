# Native SHACL 1.2 engine: design

Status: draft for discussion, branch `shacl-engine`. Background: `shacl-engine-feasibility.md`.

## Goals and non-goals
- Implement all of SHACL 1.2 as the drafts define it: Core, SPARQL-Related Features, Node Expressions, Inference Rules
  (including `sh:TripleRule`, `sh:SPARQLRule`, layers, rule sets), targets (including `sh:targetWhere`, `sh:SPARQLTarget`),
  reports with annotations and provenance.
- Triple terms and `rdf:dirLangString` are first-class. No encode to RDF 1.1 and decode back.
- No pyshacl, no rdflib object model inside the engine core.
- No backward compatibility with the 2017 SHACL-AF note, pySHACL extensions or earlier-draft forms (issue #185).
- Designed so the plan format and the interface carry over to a Rust port when the specs settle.
- Non-goals: the UI, Profiling and SRL parsing. Those stay in their own modules and call the engine.

## Layers
1. **Plan builder** (Python, runs once per shapes graph). Reads a shapes graph through the graph interface and produces
   an immutable plan: shapes, targets, paths, constraint components with their parameters, rules with layer and order.
   Resolves `owl:imports`, deactivation, severity, messages. Reports malformed shapes as plan errors.
2. **Executor.** Given a plan, a data graph and options, computes focus nodes, value nodes and constraint results and
   returns result records. Pure functions over the interface; no global state, no monkeypatching.
3. **Rule runner.** Runs rule sets by layer, then `sh:runOnce` rules, then iterating rules to fixpoint, as the
   Inference Rules draft's pseudocode specifies, on top of the executor (conditions and targets reuse it).
4. **Report builder.** Turns result records into a `sh:ValidationReport` graph and text. Provenance and
   `sh:usedConfiguration` stay in our layer on top.

The existing `starlayer/shacl/engine/` (`ComponentRequest`, `target_nodes`, `build_report`) is the starting seam; the new
engine lives in a new subpackage so `shacl/` keeps working beside it as the differential oracle.

## Graph interface (the only thing the executor touches)
A small protocol, not rdflib types:
- `match(s, p, o, g=None)` yields triples of terms; any position may be unbound.
- Terms are immutable values with a `kind` (iri, bnode, literal, triple-term), plus for literals the lexical form,
  datatype, language and base direction. Equality is RDF term equality.
- `shapes` and `data` graphs are separate objects; a data graph may be a union or a view with extra inferred triples.
- Entailment and rule output are layers over a graph (a view), never mutations of the caller's graph.
- Capability flags: `preserves_lexical_forms` (needed for datatype and pattern checks; see the parked literal issue),
  `native_sparql` (can run SPARQL itself).
- Implementations: StarLayerGraph/rdflib (first), Oxigraph (second), later Rust.

## Plan format
Plain data (dataclasses now, serializable to JSON so the Rust executor can read it): `Plan { shapes, rule_sets,
prefixes, imports }`; `Shape { id, kind, targets, constraints, severity, deactivated, messages }`; `Constraint
{ component, params }`; `Path` as a small tree (predicate, inverse, sequence, alternative, zero-or-more, one-or-more,
zero-or-one); `Rule { id, kind, layer, order, run_once, conditions, body }`. Node expressions compile to an expression
tree evaluated by the executor.

## Components in scope
From the vendored 1.2 vocabulary (`scripts/assets/vendor/w3c-shacl.ttl`):
- Value type: class, datatype, nodeKind. Cardinality: minCount, maxCount.
- Value range: minExclusive, minInclusive, maxExclusive, maxInclusive.
- String: minLength, maxLength, pattern/flags, languageIn, uniqueLang, singleLine.
- Property pair: equals, disjoint, lessThan, lessThanOrEquals.
- Logical: not, and, or, xone. Shape-based: node, property, qualifiedValueShape (+ disjoint), reifierShape and
  reificationRequired.
- Other: closed/ignoredProperties, hasValue, in, rootClass, someValue, memberShape, minListLength, maxListLength,
  uniqueMembers, subsetOf, uniqueValuesFor.
- Node expressions: sh:expression, sh:nodeByExpression, the `shnex:` operators and the `sparql:` function namespace.
- SPARQL: sh:sparql constraints, SPARQL-based constraint components, validators, prefix declarations, pre-bound
  variables.
- Rules: TripleRule, SPARQLRule, rule templates, layers, order, runOnce, conditions, rule sets, ruleProcessor.
Each component gets: parameters, the spec clause, the W3C test directory that covers it, and our native tests. Our
`native_components.py` holds many 1.2 components already; port their logic, change the base class.

## Test strategy
- The vendored W3C SHACL 1.2 suite (core, sparql, node-expr, rules) is the primary oracle; the engine must reach the
  current pass rate with the same known failures, no new ones.
- Our ~16k-line SHACL test set is the second oracle.
- Differential mode: run pyshacl-backed validation and the new engine on the same inputs; list differences; each
  difference is either an engine bug or a pyshacl bug we document and keep the spec behaviour.
- The graph interface gets contract tests that every implementation (rdflib, Oxigraph, later Rust) must pass.

## Build order
1. Interface and plan format, with the plan builder for targets and paths. Executor for the Core value-type, cardinality
   and logical components. Gate: W3C `core/` subset passes.
2. Remaining Core components and property pairs. Gate: all W3C `core/`.
3. Reports and options (severity, messages, annotations, provenance). Gate: validation-report tests.
4. SPARQL-based constraints and targets (needs the SPARQL engine hook). Gate: W3C `sparql/`.
5. Node expressions (port `node_expressions.py` to the `shnex:` form only). Gate: W3C `node-expr/`.
6. Rules, layers, runOnce, rule sets. Gate: W3C `rules/` and our rule tests.
7. Cut-over behind the existing validator API, differential run clean, retire pyshacl and delete the patches.
8. Oxigraph implementation of the interface; port to Rust on spec stability.

## Open questions
- Which SPARQL engine the executor calls for SPARQL constraints: rdflib's, Oxigraph's, or our own algebra evaluator.
- Whether the plan is built from a shapes graph each call or cached by graph hash.
- Where recursion (`sh:node` cycles) is bounded, per the draft's rules.
- Which of the issue #185 candidates are confirmed legacy before the node-expression port in step 5.
