# SHACL engine: plan format and executor contract (for the Rust port)

Status: draft, branch `shacl-engine`. Code: `starlayer/shacl_engine/plan_json.py` (serialiser, `python -m
starlayer.shacl_engine.plan_json shapes.ttl > plan.json`), `component_table.py` (generated component and operator table,
`python -m starlayer.shacl_engine.component_table`), tests in `tests/shacl_engine/test_plan_json.py`. Background:
`shacl-engine-design.md` (Plan format), `shacl-engine-cutover.md` section 6 (Rust port notes),
`shacl-engine-feasibility.md` (deviations and open points).

The Python engine reads a shapes graph into `Shape`/`Path` data (lazily, per shape node) and executes it over a data graph.
This document fixes the JSON form of that data and what an executor must do with it so a Rust implementation gives the
same results. The round trip `plan_from_json(plan_to_json(p))` is checked for every graph in the vendored W3C suites
(shape for shape, as `Shape` dataclasses), and the engine run with the rebuilt plan gives the same validation outcome as
with the original on all 166 core, sparql and node-expr Validate entries.

## 1. Term encoding

Every RDF term is a tagged object. Blank node labels are kept, so references between shapes, lists and expressions hold.

| Term | JSON |
|---|---|
| IRI | `{"t":"iri","v":"http://example.org/a"}` |
| Blank node | `{"t":"bnode","v":"b12"}` |
| Literal | `{"t":"lit","v":"<lexical form>","dt":"<datatype IRI>"\|null,"lang":"<tag>"\|null,"dir":"ltr"\|"rtl"\|null}` |
| Triple term | `{"t":"triple","s":<term>,"p":<term>,"o":<term>}` |

Literal rules: `v` is the lexical form exactly as stored (`"01"^^xsd:integer` stays `"01"`; an ill-formed `"abc"^^xsd:byte`
is kept). A plain literal has `dt: null` and an explicit `"x"^^xsd:string` has `dt` `xsd:string` (the Python model keeps them apart);
a reader treats both as `xsd:string`. A language-tagged literal has `lang` and `dt: null`; a directional one also has `dir` (its
datatype is `rdf:dirLangString`). Language tags are lower-cased on read. Triple terms nest; subject is IRI or bnode, predicate
an IRI, object any term.

## 2. Plan JSON

Top-level object (all keys always present):

| Key | Content |
|---|---|
| `format_version` | Integer, currently 1. A reader rejects other values. |
| `declared` | Shape nodes the executor visits, in order (`Plan.all_shape_nodes`: typed `sh:NodeShape`/`PropertyShape`/`Shape`/`ShapeClass`, or subject of a target predicate). |
| `shapes` | One object per shape reachable from `declared` (through `sh:property`, `sh:node`, `sh:not`, `sh:and/or/xone` lists, `sh:qualifiedValueShape`, `sh:memberShape`, `sh:reifierShape`, `sh:targetWhere`, rule `sh:condition`, and shape references inside node expressions). |
| `errors` | `[{node, message}]`: shapes that failed to build (`ShapeError`). Evaluating one is a validation failure. |
| `rules` | `rules.read_rule` records: `node, types, layer, order, run_once, shapes, conditions, expected_predicates`, or `{node, error}` (e.g. `sh:ruleProcessor`). |
| `rule_sets` | `[{node, rules, includes}]` for `sh:RuleSet` nodes. |
| `entailment` | `{values, rules_active, rule_sets}`: the `sh:entailment` values and what `rules.entailment_selection` makes of them. |
| `prefixes` | `{default, holders:[{holder, declarations}]}`: SPARQL prefix maps (section 4.2). |
| `graph` | The term store: `[[s,p,o],...]` of the shapes graph (below). |

A shape object (`Shape` field for field):

| Field | Meaning |
|---|---|
| `node` | The shape's term (reported as `sh:sourceShape`). |
| `is_property` | True when it has `sh:path` or is typed `sh:PropertyShape`. |
| `path` | Path tree or `null`. |
| `targets` | `[[predicate IRI string, term]]` in graph order. Predicates: `sh:targetNode`, `targetClass`, `targetSubjectsOf`, `targetObjectsOf`, `targetWhere`, plus the implicit `(sh:targetClass, node)` for a shape that is also a class, and the pseudo target `(sh:shape, node)` that selects data nodes with `ex:x sh:shape <node>`. |
| `params` | Object: parameter predicate IRI -> list of terms, only predicates present, in graph order. Covers every registered component parameter and the parameters of SPARQL-based components declared in the shapes graph. List-valued parameters (`sh:in`, `sh:and`, ...) carry the list head; the cells are in the term store. |
| `property_shapes` | Values of `sh:property`. |
| `severity` | Term, default `sh:Violation`. |
| `deactivated` | True iff `sh:deactivated` has the term `"true"^^xsd:boolean` (`"1"` does not count). |
| `deactivated_exprs` | `sh:deactivated` values that are node expressions (blank nodes), evaluated per focus node. |
| `messages` | `sh:message` literals. |
| `values`, `default_values` | `sh:values` and `sh:defaultValue` node expressions. |
| `annotations` | `[{predicate, value, deactivated, severity}]`: from RDF 1.2 reifiers of the shape's own triples (`ex:S sh:datatype xsd:boolean {| sh:deactivated true |}`); `sh:property` uses the same key shape. |

A path node: `{"kind", "iri"?, "args"?, "node"}` with `kind` one of `pred` (has `iri`), `inverse`, `zero_or_more`, `one_or_more`,
`zero_or_one` (one arg), `seq`, `alt` (two or more args). `node` is the path's term in the shapes graph and is what
`sh:resultPath` reports.

The term store holds what the executor reads from the shapes graph by pattern instead of from the `Shape` fields: every
shape's own triples, the blank-node closure of everything the shapes refer to (lists, paths, node expression trees, `sh:sparql`
nodes), the declarations of SPARQL-based components, custom expression functions, rules and rule sets, the prefix
declarations with their `owl:imports` chains, all `sh:rule`/`sh:hasRule`/`sh:entailment` triples and all `rdfs:subClassOf`
triples. Node expressions and SPARQL queries are not compiled: they stay RDF subgraphs addressed by term in this store.

### JSON Schema

```json schema
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "SHACL engine plan",
  "type": "object",
  "required": ["format_version", "declared", "shapes", "errors", "rules", "rule_sets", "entailment", "prefixes", "graph"],
  "additionalProperties": false,
  "properties": {
    "format_version": {"const": 1},
    "declared": {"type": "array", "items": {"$ref": "#/$defs/term"}},
    "shapes": {"type": "array", "items": {"$ref": "#/$defs/shape"}},
    "errors": {"type": "array", "items": {"type": "object", "required": ["node", "message"],
      "properties": {"node": {"$ref": "#/$defs/term"}, "message": {"type": "string"}}}},
    "rules": {"type": "array", "items": {"type": "object", "required": ["node"],
      "properties": {"node": {"$ref": "#/$defs/term"}, "error": {"type": "string"}, "types": {"type": "array"},
        "layer": {"type": "number"}, "order": {"type": "number"}, "run_once": {"type": "boolean"},
        "shapes": {"type": "array"}, "conditions": {"type": "array"}, "expected_predicates": {"type": "array"}}}},
    "rule_sets": {"type": "array", "items": {"type": "object", "required": ["node", "rules", "includes"]}},
    "entailment": {"type": "object", "required": ["values", "rules_active", "rule_sets"]},
    "prefixes": {"type": "object", "required": ["default", "holders"],
      "properties": {"default": {"type": "object", "additionalProperties": {"type": "string"}},
        "holders": {"type": "array", "items": {"type": "object", "required": ["holder"]}}}},
    "graph": {"type": "array", "items": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"$ref": "#/$defs/term"}}}
  },
  "$defs": {
    "term": {"oneOf": [
      {"type": "object", "required": ["t", "v"], "properties": {"t": {"enum": ["iri", "bnode"]}, "v": {"type": "string"}}},
      {"type": "object", "required": ["t", "v", "dt", "lang", "dir"], "properties": {"t": {"const": "lit"},
        "v": {"type": "string"}, "dt": {"type": ["string", "null"]}, "lang": {"type": ["string", "null"]},
        "dir": {"enum": ["ltr", "rtl", null]}}},
      {"type": "object", "required": ["t", "s", "p", "o"], "properties": {"t": {"const": "triple"},
        "s": {"$ref": "#/$defs/term"}, "p": {"$ref": "#/$defs/term"}, "o": {"$ref": "#/$defs/term"}}}]},
    "path": {"type": ["object", "null"], "required": ["kind", "node"], "properties": {
      "kind": {"enum": ["pred", "inverse", "seq", "alt", "zero_or_more", "one_or_more", "zero_or_one"]},
      "iri": {"$ref": "#/$defs/term"}, "args": {"type": "array", "items": {"$ref": "#/$defs/path"}},
      "node": {"oneOf": [{"$ref": "#/$defs/term"}, {"type": "null"}]}}},
    "terms": {"type": "array", "items": {"$ref": "#/$defs/term"}},
    "shape": {"type": "object", "additionalProperties": false,
      "required": ["node", "is_property", "path", "targets", "params", "property_shapes", "severity", "deactivated",
        "deactivated_exprs", "messages", "values", "default_values", "annotations"],
      "properties": {
        "node": {"$ref": "#/$defs/term"}, "is_property": {"type": "boolean"}, "path": {"$ref": "#/$defs/path"},
        "targets": {"type": "array", "items": {"type": "array", "minItems": 2, "maxItems": 2}},
        "params": {"type": "object", "additionalProperties": {"$ref": "#/$defs/terms"}},
        "property_shapes": {"$ref": "#/$defs/terms"}, "severity": {"$ref": "#/$defs/term"},
        "deactivated": {"type": "boolean"}, "deactivated_exprs": {"$ref": "#/$defs/terms"},
        "messages": {"$ref": "#/$defs/terms"}, "values": {"$ref": "#/$defs/terms"},
        "default_values": {"$ref": "#/$defs/terms"},
        "annotations": {"type": "array", "items": {"type": "object",
          "required": ["predicate", "value", "deactivated", "severity"]}}}}
  }
}
```

## 3. Component and operator table

`component_table.py` generates the table from the live registries (`components.registry.REGISTRY`, `expressions.OPERATORS`), so
it cannot drift: a test fails if a registered component or operator has no row, or a row has no annotation. It holds 42
components and 103 operators today. Per component: IRI, parameter predicates, required and optional ones, `scope`
(`value_node`: one verdict per value node; `focus_node`: a verdict over the focus node's whole value set), the `needs` flags
(`graph` only, `shapes_graph` for lists and path terms, `sparql` engine, `conforms` recursion, `cross_focus` state), the spec
clause (`unverified` where the code does not quote one) and the implementing function. Per operator: key predicate,
auxiliary predicates, arity (`const`, `1`, `list`, `list:N`, `shape`) and needs (`graph`, `conforms`, `sparql_engine` for
`sh:select`/`sh:sparqlExpr`, `sparql_functions` for the `sparql:` scalar functions).

Exactly one component needs cross-focus-node state (`sh:uniqueValuesFor`: it groups the shape's whole target set). Components
with `conforms` call back into the executor (`not and or xone node qualified* memberShape someValue reifierShape expression
nodeByExpression`). Only `sh:sparql` needs a SPARQL engine among the static components; SPARQL-based components declared in a
shapes graph (SPARQL-Related Features 4) also do and are not in the static table (a port reads them from the term store).
The table's component order is the registry insertion order, which is the evaluation order (section 4.4).

## 4. Executor contract

### 4.1 Graph interface

The executor touches a graph only through five methods (`interface.GraphView`): `triples((s,p,o))` with any position
`None`; `objects(s, p)`; `subjects(p, o)`; `predicate_objects(s)`; `(s,p,o) in graph`. The first and last are the primitives; the
others are conveniences. Terms are the model of section 1 with equality = RDF term equality: lexical forms preserved, ill-formed
literals kept, triple terms first-class (object position only), `rdf:dirLangString` literals compared on (lexical, lang, dir).
Iteration order is the graph's; a stable order matters only for result ordering, which is unspecified (compare as multisets).
Capability flags: `preserves_lexical_forms` (needed for `sh:datatype`, `sh:pattern` and `sh:in` on stored text; an executor on a
store that normalises literals must keep a side table or run SHACL in memory) and `native_sparql`. The shapes graph is a second
graph with the same interface (the term store, or the original); the data graph may be a union or an overlay.

### 4.2 SPARQL capability

`sparql_query(text, init_bindings) -> Solutions` where `Solutions` is `(variables, rows, boolean)`; rows map variable names
(no `?`) to terms, unbound variables absent. It runs SELECT or ASK text (SPARQL 1.2 syntax, triple terms, `rdf:dirLangString`)
on the data graph.

Pre-binding is SHACL SPARQL Appendix A semantics, not an outer join and not "bind then evaluate": the variables in
`init_bindings` are joined, as a one-row table, into every basic graph pattern, property path and `GRAPH` pattern of the
query. `SELECT $this ?value WHERE { FILTER (?value < ?minScore) }` with `minScore` pre-bound has no solutions (the pattern
has nothing to join). Pre-bound variables: `this` (focus node; always), `value` (ASK validators), each parameter by the local
name of its path, scope variables of SPARQL node expressions (`value` for `sh:expression`, integer `n` as `arg<n>`, parameter paths
by local name). `$PATH` is textually replaced by the shape's path in SPARQL form (`<p>`, `^(p)`, `(a/b)`, `(a|b)`, `(p)*`)
on property shapes, and is left unbound on node shapes. Not bound: `shapesGraph`, `currentShape` (removed, Appendix F).

The executor, not the SPARQL engine, rejects the queries the spec forbids (`ShapeError`, a validation failure): text that does not
parse, SELECT where ASK is required or the reverse, `MINUS`, `SERVICE`, a `VALUES` that mentions a pre-bound variable
(a `VALUES` over other variables is allowed: a deliberate deviation from fixture `unsupported-sparql-002`), `AS` of a pre-bound
variable, and a SELECT constraint that does not project `?this`.

Prefixes: query text gets `PREFIX p: <ns>` lines from `prefixes`: with `sh:prefixes` on the holder, the `sh:declare` of the
holder and of its `owl:imports` closure (`(^owl:versionIRI)?` resolved); without it the `default` map (`sh:declare` on instances
of `sh:ShapesGraph`, `sh:DataGraph`, `sh:RulesGraph`, then `owl:Ontology`, which only adds unbound prefixes). Ambient `@prefix`
is never used. One prefix with two namespaces is ill-formed (recorded as `default_error` / holder `error`).

SELECT solutions to results: one result per solution; `?this` is the focus; `?path` (an IRI) overrides `sh:resultPath`; `?value`
is `sh:value` (default for node shapes: the focus node); `?message` overrides the message templates; `{?var}` / `{$var}` in
`sh:message` are filled with lexical forms; `?failure true` fails the whole validation. `sh:resultAnnotation` (one
`sh:annotationProperty` with `sh:annotationVarName` or `sh:annotationValue`) adds annotation triples. A SPARQL evaluation error
is a validation failure, never a silent pass. ASK validators run once per value node and violate on `false`. Node-expression
functions called from SPARQL (`sh:ListParameterExpressionFunction` by IRI) need an extension-function hook.

### 4.3 Entailment overlay

Entailment and rule output are overlays over the data graph (`InferredView`: base graph plus a set of added triples), never
mutations of the caller's graph. `sh:entailment` on the shapes graph (or the caller's `inference`) selects regimes (RDFS,
OWL RL via an external reasoner today) and, with `sh:RulesEntailment` or rule-set IRIs, the rule runner. Order: entailment
closure first (over data plus an optional ontology graph that is visible to the reasoning but not copied into the view), then
rules, then validation over the resulting view. Class targets and `sh:class` read `rdf:type` / `rdfs:subClassOf` straight from
that view. Rules: by `layer` ascending, `sh:runOnce` rules once, the others iterated to a fixpoint, `order` ascending inside a
layer; `sh:TripleRule` and `sh:SPARQLRule`; conditions are shapes the focus node must conform to; `sh:ruleProcessor` is an error.

### 4.4 Order of evaluation

1. For each `declared` node in order: skip if `deactivated`; compute focus nodes once per shape (targets in order, each node once:
   `targetNode` (a blank-node value is a node expression evaluated with the shape as focus), `targetClass` over the
   `rdfs:subClassOf*` closure in the data graph, `targetSubjectsOf`, `targetObjectsOf`, `targetWhere` (every subject and object
   of the data graph that conforms to the shape), `sh:shape`). The set is cached per shape (`sh:uniqueValuesFor` needs it).
2. For each focus node, `validate_shape_at(shape, focus)`: nothing if `deactivated` or any `deactivated_exprs` evaluates to
   exactly `true` at the focus (a failing expression does not deactivate); fail if the nesting depth would exceed
   `max_validation_depth`.
3. Value nodes: the focus node for a node shape; for a property shape the path values (a set, each node once, breadth-first, cycle
   safe, `zero_or_more`/`zero_or_one` include the start), then the outputs of `values`, then, only if still empty, the outputs of
   `default_values`; an expression that fails contributes nothing.
4. Components, in registry order (static components, then declared SPARQL-based ones): a component applies when the shape has at
   least one of its parameters present and all its `required` ones, after dropping parameter values whose annotation says
   `deactivated`; the severity is the first annotation severity among the present values, else the shape's. Each yields violation
   records (value, message, path override, component override, source constraint, severity override, annotations).
5. After the components, for each `property_shapes` value (skipping annotated-deactivated ones) and each value node, recurse
   with the value node as focus.
6. `abort_on_first` stops at the first shape that produces a result, and at the first component within it: so the result
   depends on component order (frozen decision 14).

### 4.5 Recursion

`conforms(shape, node)` is "no result of `shape` at `node`". It keeps an active set of `(shape, node)` pairs and a count of `sh:not`
crossings. A re-entry on an active pair is assumed to conform (greatest fixpoint), unless the number of `sh:not` crossings
differs from when the pair was entered: then the cycle passes through `sh:not` and the run fails with `ShapeError` (no fixpoint
or several). Answers that leaned on an assumption are not memoised; assumption-free answers are memoised with their nesting
height so `max_validation_depth` is still enforced on replay. Core 6.7.3 leaves recursion to implementations: this is a choice
(section 6).

### 4.6 Result record

One record per violation: `focus`, `path` (a Path whose `node` is reported as `sh:resultPath`, or none), `value` and `has_value`
(`sh:value` only when present), `component` (IRI), `shape` (`sh:sourceShape`), `severity`, `messages` (the violation's own, else
the shape's `sh:message`s, else the component's default), `source_constraint` (`sh:sourceConstraint`: the `sh:sparql` node,
the expression, or the shape a `sh:nodeByExpression` output named), `annotations` (property/value pairs).

### 4.7 Report building

`conforms` is true when no result has severity at or above `conformanceDisallows`: severities order Trace < Debug < Info < Warning <
Violation; the default floor is Info; an unknown severity blocks. The report is a `sh:ValidationReport` with `sh:conforms`, optional
`sh:conformanceDisallows`, and one `sh:ValidationResult` per record carrying `sh:focusNode`, `sh:resultPath`, `sh:value`,
`sh:sourceConstraintComponent`, `sh:sourceShape`, `sh:sourceConstraint`, `sh:resultSeverity`, annotations and `sh:resultMessage`.
Blank nodes are copied with their full closure for the focus node and value (from the data graph) and for the path and
annotation values (from the shapes graph); result order is unspecified. Provenance (`sh:usedDataGraph`, `sh:usedShapesGraph`,
`sh:usedConfiguration`) is layered on afterwards.

## 5. Worked example

Shapes (Turtle):

```turtle
ex:PersonShape a sh:NodeShape ; sh:targetClass ex:Person ;
  sh:property [ sh:path ex:age ; sh:datatype xsd:integer ; sh:minCount 1 ; sh:maxInclusive 150 ; sh:message "age"@en ] .
```

Plan JSON (the `graph` array, 8 triples, and empty sections elided; `NPROP` stands for the property shape's blank node label):

```json
{"format_version": 1,
 "declared": [{"t":"iri","v":"http://example.org/PersonShape"}],
 "shapes": [
  {"node": {"t":"iri","v":"http://example.org/PersonShape"}, "is_property": false, "path": null,
   "targets": [["http://www.w3.org/ns/shacl#targetClass", {"t":"iri","v":"http://example.org/Person"}],
               ["http://www.w3.org/ns/shacl#shape", {"t":"iri","v":"http://example.org/PersonShape"}]],
   "params": {}, "property_shapes": [{"t":"bnode","v":"NPROP"}],
   "severity": {"t":"iri","v":"http://www.w3.org/ns/shacl#Violation"}, "deactivated": false,
   "deactivated_exprs": [], "messages": [], "values": [], "default_values": [], "annotations": []},
  {"node": {"t":"bnode","v":"NPROP"}, "is_property": true,
   "path": {"kind":"pred","iri":{"t":"iri","v":"http://example.org/age"},"node":{"t":"iri","v":"http://example.org/age"}},
   "targets": [["http://www.w3.org/ns/shacl#shape", {"t":"bnode","v":"NPROP"}]],
   "params": {
     "http://www.w3.org/ns/shacl#datatype": [{"t":"iri","v":"http://www.w3.org/2001/XMLSchema#integer"}],
     "http://www.w3.org/ns/shacl#minCount": [{"t":"lit","v":"1","dt":"http://www.w3.org/2001/XMLSchema#integer","lang":null,"dir":null}],
     "http://www.w3.org/ns/shacl#maxInclusive": [{"t":"lit","v":"150","dt":"http://www.w3.org/2001/XMLSchema#integer","lang":null,"dir":null}]},
   "property_shapes": [], "severity": {"t":"iri","v":"http://www.w3.org/ns/shacl#Violation"}, "deactivated": false,
   "deactivated_exprs": [], "messages": [{"t":"lit","v":"age","dt":null,"lang":"en","dir":null}],
   "values": [], "default_values": [], "annotations": []}],
 "errors": [], "rules": [], "rule_sets": [],
 "entailment": {"values": [], "rules_active": false, "rule_sets": []},
 "prefixes": {"default": {}, "holders": []}, "graph": []}
```

Data: `ex:alice a ex:Person ; ex:age 30 . ex:bob a ex:Person ; ex:age "old" . ex:carol a ex:Person .`

Focus nodes of `PersonShape`: alice, bob, carol (from `targetClass`); the pseudo target `sh:shape` finds none. For each, the property
shape runs with the focus as `$this`; value nodes are `ex:age` values. Alice conforms. Bob's `"old"` is not an `xsd:integer`, and a
non-comparable value violates `sh:maxInclusive`. Carol has no value for `sh:minCount 1`. Expected results (compare as a multiset;
this is the order the Python engine emits):

```json
[{"focus":{"t":"iri","v":"http://example.org/bob"},"path":{"t":"iri","v":"http://example.org/age"},
  "value":{"t":"lit","v":"old","dt":null,"lang":null,"dir":null},
  "component":"http://www.w3.org/ns/shacl#DatatypeConstraintComponent","shape":{"t":"bnode","v":"NPROP"},
  "severity":"http://www.w3.org/ns/shacl#Violation","messages":["age@en"],"source_constraint":null,"annotations":[]},
 {"focus":{"t":"iri","v":"http://example.org/bob"},"path":{"t":"iri","v":"http://example.org/age"},
  "value":{"t":"lit","v":"old","dt":null,"lang":null,"dir":null},
  "component":"http://www.w3.org/ns/shacl#MaxInclusiveConstraintComponent","shape":{"t":"bnode","v":"NPROP"},
  "severity":"http://www.w3.org/ns/shacl#Violation","messages":["age@en"],"source_constraint":null,"annotations":[]},
 {"focus":{"t":"iri","v":"http://example.org/carol"},"path":{"t":"iri","v":"http://example.org/age"},"value":null,
  "component":"http://www.w3.org/ns/shacl#MinCountConstraintComponent","shape":{"t":"bnode","v":"NPROP"},
  "severity":"http://www.w3.org/ns/shacl#Violation","messages":["age@en"],"source_constraint":null,"annotations":[]}]
```

The report has `sh:conforms false` and three `sh:ValidationResult` nodes with the same fields as RDF.

## 6. Spec decisions to freeze before porting

Numbers 1-14 are `shacl-engine-cutover.md` 6.3; the rest come from the feasibility notes (open points and deliberate deviations).

1. Recursion: positive re-entry conforms, a cycle through `sh:not` is a failure (Core 6.7.3 leaves it open).
2. `sh:uniqueValuesFor` peers are the shape's own targets (Core 7.9.5); "no values for any listed property" is ambiguous, the engine
   skips a node missing any; the old validator and 15 project tests use the outer shape's focus nodes.
3. `sh:class`, `sh:datatype`, `sh:nodeKind` accept an `rdf:List` as a union (two fixtures need it; unconfirmed in the text).
4. `sh:nodeKind` with triple terms (only `sh:TripleTerm` matches), and `sh:targetWhere` candidates (all subjects and objects;
   triple-term components are not enumerated).
5. Subclass triples for class targets and `sh:rootClass` come from the data graph only.
6. Only the term `"true"^^xsd:boolean` activates boolean parameters; `sh:deactivated` may be a node expression per focus node.
7. Pre-binding rules (section 4.2), which of `this`, `value`, `PATH` are bound per validator type; `sh:value` for ASK validators.
8. Report content: blank-node closure copied in full; `sh:detail` for list components is not emitted; result order unspecified.
9. Rules: layer/order/`runOnce`/termination, `sh:tempTriple`, `sh:expectedPredicate`, `sh:ruleProcessor` (an error today),
   rule sets, `sh:sourceRule` (not recorded), overlay never mutates the caller's graph.
10. Entailment regimes and the oracle (`owlrl` today; RDFS closure is small, OWL RL is not).
11. Prefixes: `sh:declare` / `sh:prefixes` only, no ambient `@prefix`, `owl:Ontology` declares only fill gaps (W3C `prefixes-002`).
12. Which malformed shapes are plan errors (`errors` here) and which are tolerated; `meta_shacl` preflight; the default of
    `max_validation_depth` (none in `run`).
13. Term model: lexical forms preserved, ill-formed literals kept, triple terms first-class.
14. Evaluation order and `abort_on_first` (component order is the registry order).
15. VALUES in SHACL SPARQL: reject only when it mentions a pre-bound variable (draft), against fixture `unsupported-sparql-002`;
    MINUS and SERVICE are rejected.
16. `sh:SPARQLTarget`, `sh:SPARQLTargetType`, `$currentShape`, `$shapesGraph` are dropped (Appendix F).
17. `shape_targets` adds the pseudo target `(sh:shape, node)` (fixture shape-001); decide whether it belongs in the plan or the
    executor.
18. `sh:values` / `sh:defaultValue` failure handling and chaining across shapes follow `validator.py`, not verified against the draft.
19. SPARQL pre-binding conformance: fixture `pre-binding-002` fails today (issue #186); `seconds-example` is a fixture defect.
20. Legacy 2017 AF forms (`sh:union`, `sh:minus`, `sh:filterShape` as expression, `sh:path` expression) are `ShapeError` (issue #185).

What the plan does not carry (the executor must supply it): the node-expression and SPARQL semantics (only the RDF subgraphs),
the regex dialect for `sh:pattern`, XSD value comparison and ordering for the range and `sh:lessThan` components, the SPARQL 1.2
function library behind the `sparql:` operators, the rule runner and entailment reasoner, the rule bodies of `sh:SPARQLRule`
and `sh:TripleRule` (term store only), and the report builder.
