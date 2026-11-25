# Dry run of the renumbering: chapter 05

Produced on 2026-11-25 by `python scripts/renumber_guides.py plan --chapter 05` and `plan-files --chapter 05` (nothing was written to any guide or file). The working guides read were the checkout at HEAD e6ec46a7 plus the maintainer's uncommitted edits to `05.02` and `05.03`. Plan: `guide-renumbering-plan-2026-11-25.md` (old file names are written as plain text here, never as links). A sentence is shown as it reads after the link rewrite of the same line, with `](` written `] (` so that no sentence is a link.

How to read it: "rewrites it is sure about" are written by `apply`. A "decision" item is not written, unless `apply --with-proposals` is given and the item has a proposal. "Deferred" items name a guide in a chapter that is not renumbered yet; the stage of that chapter handles them. "Left alone" items are specification sections or numbers that are no heading of the guide.

Chapter 05: 11 guides, 5 referrer guides (other chapters that link into it). Nothing is written.

## Primary guides

### `05.01-validating-with-shacl-1.2.ipynb` (name unchanged)

Cells that change: 33

Heading rewrites: 29
- [H3-relative] cell a3010001: `### .3.1 Working with RDF 1.2 terms` -> `### 05.01.3.1 Working with RDF 1.2 terms`
- [H4-relative] cell 01c76d3c: `#### .3.1.1 Is a value a triple term? `sh:nodeKind ( sh:TripleTerm )`` -> `#### 05.01.3.1.1 Is a value a triple term? `sh:nodeKind ( sh:TripleTerm )``
- [H4-relative] cell ea000001: `#### .3.1.2 Reifiers of a value: `sh:reifierShape` and `sh:reificationRequired`` -> `#### 05.01.3.1.2 Reifiers of a value: `sh:reifierShape` and `sh:reificationRequired``
- [H4-relative] cell 25692a79: `#### .3.1.3 Direction-aware datatype constraints` -> `#### 05.01.3.1.3 Direction-aware datatype constraints`
- [H4-relative] cell ea000003: `#### .3.1.4 One value per language: `sh:uniqueLang`` -> `#### 05.01.3.1.4 One value per language: `sh:uniqueLang``
- [H3-relative] cell a3020001: `### .3.2 New constraint components` -> `### 05.01.3.2 New constraint components`
- [H4-relative] cell eb000001: `#### .3.2.1 No line breaks in a value: `sh:singleLine`` -> `#### 05.01.3.2.1 No line breaks in a value: `sh:singleLine``
- [H4-relative] cell eb000003: `#### .3.2.2 At least one value matches: `sh:someValue`` -> `#### 05.01.3.2.2 At least one value matches: `sh:someValue``
- [H4-relative] cell eb000011: `#### .3.2.3 Unique values across focus nodes: `sh:uniqueValuesFor`` -> `#### 05.01.3.2.3 Unique values across focus nodes: `sh:uniqueValuesFor``
- [H3-relative] cell a3030001: `### .3.3 Lists` -> `### 05.01.3.3 Lists`
- [H4-relative] cell eca00001: `#### .3.3.1 Constraints on the members of a list` -> `#### 05.01.3.3.1 Constraints on the members of a list`
- [H4-relative] cell ecb00001: `#### .3.3.2 A list of choices for `sh:class` and `sh:datatype`` -> `#### 05.01.3.3.2 A list of choices for `sh:class` and `sh:datatype``
- [H3-relative] cell a3040001: `### .3.4 Property path comparisons` -> `### 05.01.3.4 Property path comparisons`
- [H3-relative] cell a3050001: `### .3.5 Values below a root class: `sh:rootClass`` -> `### 05.01.3.5 Values below a root class: `sh:rootClass``
- [H3-relative] cell a3060001: `### .3.6 Targets` -> `### 05.01.3.6 Targets`
- [H4-relative] cell ed000001: `#### .3.6.1 Selecting targets with a shape: `sh:targetWhere`` -> `#### 05.01.3.6.1 Selecting targets with a shape: `sh:targetWhere``
- [H4-relative] cell ed000003: `#### .3.6.2 Selecting a node by naming its shape: `sh:shape`` -> `#### 05.01.3.6.2 Selecting a node by naming its shape: `sh:shape``
- [H3-relative] cell a3070001: `### .3.7 Severity, messages and conformance` -> `### 05.01.3.7 Severity, messages and conformance`
- [H4-relative] cell 1c65ebdc: `#### .3.7.1 New severity levels: `sh:Debug`, `sh:Trace`` -> `#### 05.01.3.7.1 New severity levels: `sh:Debug`, `sh:Trace``
- [H4-relative] cell 720d893c: `#### .3.7.2 Fine-grained severity via reification: `{| sh:severity ... |}`` -> `#### 05.01.3.7.2 Fine-grained severity via reification: `{| sh:severity ... |}``
- [H4-relative] cell ed000007: `#### .3.7.3 Which severities make a report fail: `sh:conformanceDisallows`` -> `#### 05.01.3.7.3 Which severities make a report fail: `sh:conformanceDisallows``
- [H3-relative] cell a3080001: `### .3.8 Constant value nodes: `sh:defaultValue` and `sh:values`` -> `### 05.01.3.8 Constant value nodes: `sh:defaultValue` and `sh:values``
- [H4-relative] cell a3080005: `#### .3.8.1 A value when none is stored: `sh:defaultValue`` -> `#### 05.01.3.8.1 A value when none is stored: `sh:defaultValue``
- [H4-relative] cell a3080006: `#### .3.8.2 Adding values: `sh:values`` -> `#### 05.01.3.8.2 Adding values: `sh:values``
- [H3-relative] cell 84518071: `### .4.1 Each graph of a dataset` -> `### 05.01.4.1 Each graph of a dataset`
- [H3-relative] cell 41afa3d7: `### .4.2 When the shapes are wrong` -> `### 05.01.4.2 When the shapes are wrong`
- [H3-relative] cell 5331f56f: `### .4.3 Entailment during validation` -> `### 05.01.4.3 Entailment during validation`
- [H3-relative] cell ed000009: `### .4.4 Naming the graphs in a report` -> `### 05.01.4.4 Naming the graphs in a report`
- [H3-relative] cell ed000016: `### .4.5 Recording the processor configuration` -> `### 05.01.4.5 Recording the processor configuration`

Link and file-name rewrites: 15
- [link-target] cell 391d95f3: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`
- [link-target] cell 391d95f3: `05b-shacl-and-sparql.ipynb` -> `05.05-shacl-and-sparql.ipynb`
- [link-target] cell 391d95f3: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-target] cell 391d95f3: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`
- [link-target] cell 391d95f3: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-target] cell 391d95f3: `05f-shacl-subgraph-extraction.ipynb` -> `05.09-shacl-subgraph-extraction.ipynb`
- [link-target] cell 391d95f3: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-target] cell 391d95f3: `05h-shacl-evaluate.ipynb` -> `05.11-shacl-evaluate.ipynb`
- [link-target] cell 5a28c71d: `05h-shacl-evaluate.ipynb` -> `05.11-shacl-evaluate.ipynb`
- [link-target] cell 5a28c71d: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-target] cell a3080001: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`
- [link-target] cell a3080006: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`
- [link-target] cell 5331f56f: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-target] cell ed000009: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-target] cell ed000009: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`

In-text rewrites it is sure about: 13
- [bullet-relative] cell 1ce6a456: `.3.1` -> `05.01.3.1`: - **.3.1 Working with RDF 1.2 terms**: triple terms, reifiers and direction-tagged strings.
- [bullet-relative] cell 1ce6a456: `.3.2` -> `05.01.3.2`: - **.3.2 New constraint components**: `sh:singleLine`, `sh:someValue` and `sh:uniqueValuesFor`.
- [bullet-relative] cell 1ce6a456: `.3.3` -> `05.01.3.3`: - **.3.3 Lists**: constraints on the members of an RDF list, and lists of classes and datatypes.
- [bullet-relative] cell 1ce6a456: `.3.4` -> `05.01.3.4`: - **.3.4 Property path comparisons**: `sh:equals`, `sh:lessThan` and similar expressions.
- [bullet-relative] cell 1ce6a456: `.3.5` -> `05.01.3.5`: - **.3.5 Values below a root class**: `sh:rootClass`. Shapes that are also classes have a [guide of their own] (05.03-shapes-as-classes.ipynb).
- [bullet-relative] cell 1ce6a456: `.3.6` -> `05.01.3.6`: - **.3.6 Targets**: `sh:targetWhere` and `sh:shape`.
- [bullet-relative] cell 1ce6a456: `.3.7` -> `05.01.3.7`: - **.3.7 Severity, messages and conformance**: the new severities, fine-grained severity, and which severities make a report fail.
- [bullet-relative] cell 1ce6a456: `.3.8` -> `05.01.3.8`: - **.3.8 Constant value nodes**: `sh:defaultValue` and `sh:values`.
- [bullet-relative] cell a5040001: `.4.1` -> `05.01.4.1`: - **.4.1 Each graph of a dataset**: `validate_each()`.
- [bullet-relative] cell a5040001: `.4.2` -> `05.01.4.2`: - **.4.2 When the shapes are wrong**: `ShapeCompileError` and `MetaShaclError`, which are both `ShapeError`s.
- [bullet-relative] cell a5040001: `.4.3` -> `05.01.4.3`: - **.4.3 Entailment during validation**: requesting an entailment regime, and its cache.
- [bullet-relative] cell a5040001: `.4.4` -> `05.01.4.4`: - **.4.4 Naming the graphs in a report**: `sh:usedDataGraph` and `sh:usedShapesGraph` on the validation activity.
- [bullet-relative] cell a5040001: `.4.5` -> `05.01.4.5`: - **.4.5 Recording the processor configuration**: `include_used_configuration=True`.

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 1
- [section-relative] cell ed000016: `section .4.3`. Proposal: `05.01.4.3`. Sentence: Recording the options lets a reader of the report, or a later run, see how a result was produced, for example whether RDFS entailment was applied (see section .4.3) or whether `rdfs:subClassOf` was read from the shapes graph (see [shapes...

Deferred (the referent guide is in a chapter that is not renamed yet): 1
- [section-other-guide] cell 5331f56f: `section 5`. Sentence: The regimes StarLayer can apply, and which one to choose, are described in [section 5 of the inferencing guide] (02e-graphs-inferencing.ipynb).

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05.02-starlayer-shacl-engine.ipynb` (name unchanged)

Cells that change: 8

Heading rewrites: 5
- [H3-relative] cell c0f90002: `### .2.1 Overriding the configuration` -> `### 05.02.2.1 Overriding the configuration`
- [H3-relative] cell e9020010: `### .2.2 Imports of the shapes graph: `ignore_imports` and `shapes_graph_loader`` -> `### 05.02.2.2 Imports of the shapes graph: `ignore_imports` and `shapes_graph_loader``
- [H3-relative] cell e9317540: `### .3.1 Updating a shape: `template_graph`` -> `### 05.02.3.1 Updating a shape: `template_graph``
- [H3-relative] cell e9020014: `### .4.1 Adding your own checks: `meta_shapes_extra`` -> `### 05.02.4.1 Adding your own checks: `meta_shapes_extra``
- [H3-relative] cell e9020020: `### .4.2 Checking an edit before it is made` -> `### 05.02.4.2 Checking an edit before it is made`

Link and file-name rewrites: 40
- [link-target] cell e9020001: `05h-shacl-evaluate.ipynb` -> `05.11-shacl-evaluate.ipynb`
- [link-text] cell e9020001: `05h` -> `05.11`
- [link-target] cell e9020001: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-text] cell e9020001: `05c` -> `05.06`
- [link-target] cell e9020001: `05f-shacl-subgraph-extraction.ipynb` -> `05.09-shacl-subgraph-extraction.ipynb`
- [link-text] cell e9020001: `05f` -> `05.09`
- [link-target] cell e9020001: `05f-shacl-subgraph-extraction.ipynb` -> `05.09-shacl-subgraph-extraction.ipynb`
- [link-text] cell e9020001: `05f` -> `05.09`
- [link-target] cell e9020001: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-text] cell e9020001: `05e` -> `05.08`
- [link-target] cell e9020001: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`
- [link-text] cell e9020001: `05d` -> `05.07`
- [link-target] cell e9020001: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`
- [link-text] cell e9020001: `05d` -> `05.07`
- [link-target] cell e9020001: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`
- [link-text] cell e9020001: `05d` -> `05.07`
- [link-target] cell e9020001: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020001: `05g` -> `05.10`
- [link-target] cell e9020001: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020001: `05g` -> `05.10`
- [link-target] cell e9020001: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020001: `05g` -> `05.10`
- [link-target] cell e9020001: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020001: `05g` -> `05.10`
- [link-target] cell e9020001: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020001: `05g` -> `05.10`
- [link-target] cell e9020001: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020001: `05g` -> `05.10`
- [link-target] cell e9020001: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-text] cell e9020001: `05e` -> `05.08`
- [link-target] cell c0f90001: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`
- [link-target] cell c0f90001: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-text] cell c0f90001: `05c` -> `05.06`
- [link-target] cell c0f90001: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-text] cell c0f90001: `05c` -> `05.06`
- [link-target] cell e9020010: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-target] cell e9020030: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-text] cell e9020030: `05c` -> `05.06`
- [link-target] cell e9020030: `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`
- [link-text] cell e9020030: `05g` -> `05.10`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 3
- [known-fix] cell f5b00004: `see section 2.1)`. Proposal: `see section 05.01.2)`. Sentence: # (StarLayerGraphs, see section 2.1); the StarLayerGraph inputs are built by parsing Turtle.
- [section-other-guide] cell c0f90001: `section 12`. Proposal: `05.06.12`. Sentence: [05.06] (05.06-shacl-inference-rules.ipynb), section 12
- [section-other-guide] cell c0f90001: `section 12`. Proposal: `05.06.12`. Sentence: [05.06] (05.06-shacl-inference-rules.ipynb), section 12

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05.03-shapes-as-classes.ipynb` (name unchanged)

Cells that change: 0

Heading rewrites: 0

Link and file-name rewrites: 0

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`

Cells that change: 31

Heading rewrites: 29
- [H1] cell b0b6238e0b0f: `# 05a SHACL 1.2 Node Expressions` -> `# 05.04 SHACL 1.2 Node Expressions`
- [H2] cell 83db67d9cccb: `## 1. Selecting target nodes` -> `## 05.04.1 Selecting target nodes`
- [H3] cell 3772623b8f50: `### 1.1 Narrowing the target set` -> `### 05.04.1.1 Narrowing the target set`
- [H2] cell 9d14974cb43a: `## 2. Constraint checks: using `sh:expression`` -> `## 05.04.2 Constraint checks: using `sh:expression``
- [H3] cell 9b769b77: `### 2.1 Using `shnex:pathValues` with `sh:expression`` -> `### 05.04.2.1 Using `shnex:pathValues` with `sh:expression``
- [H3] cell 58af1220d7d9: `### 2.2 Using special variables: `"value"` and `"focusNode"` with `sh:expression`` -> `### 05.04.2.2 Using special variables: `"value"` and `"focusNode"` with `sh:expression``
- [H2] cell 7439aee5d5d9: `## 3. Computed properties: `sh:values`` -> `## 05.04.3 Computed properties: `sh:values``
- [H2] cell de0aa70a6376: `## 4. SPARQL built-ins as node expressions` -> `## 05.04.4 SPARQL built-ins as node expressions`
- [H3] cell 04adba77: `### 4.1 Arithmetic functions` -> `### 05.04.4.1 Arithmetic functions`
- [H3] cell d76b74f1: `### 4.2 Numeric, date/time, hash & term-type functions` -> `### 05.04.4.2 Numeric, date/time, hash & term-type functions`
- [H3] cell f29320ac: `### 4.3 RDF-1.2 triple-term functions` -> `### 05.04.4.3 RDF-1.2 triple-term functions`
- [H3] cell de5245ea: `### 4.4 RDF-1.2 directional language string functions` -> `### 05.04.4.4 RDF-1.2 directional language string functions`
- [H3] cell 0132e7ec: `### 4.5 Additional sparql: functions` -> `### 05.04.4.5 Additional sparql: functions`
- [H3] cell a5698acf: `### 4.6 Comparison, logical & string functions` -> `### 05.04.4.6 Comparison, logical & string functions`
- [H2] cell 55160c12: `## 5. The `shnex:` vocabulary` -> `## 05.04.5 The `shnex:` vocabulary`
- [H3] cell acee7d31: `### 5.1 Selecting & filtering nodes` -> `### 05.04.5.1 Selecting & filtering nodes`
- [H3] cell 71315e51: `### 5.2 Reading values` -> `### 05.04.5.2 Reading values`
- [H3] cell 26b55713: `### 5.3 Aggregates: count, min & max` -> `### 05.04.5.3 Aggregates: count, min & max`
- [H3] cell 74a3c208: `### 5.4 Control flow: if / then / else` -> `### 05.04.5.4 Control flow: if / then / else`
- [H3] cell f73c077a: `### 5.5 Set/list transformations` -> `### 05.04.5.5 Set/list transformations`
- [H3] cell f4b504de: `### 5.6 Sorting & paging` -> `### 05.04.5.6 Sorting & paging`
- [H3] cell 628d906e: `### 5.7 Mapping over a list: flatMap` -> `### 05.04.5.7 Mapping over a list: flatMap`
- [H3] cell f5fd1d37: `### 5.8 Shape-matching operators` -> `### 05.04.5.8 Shape-matching operators`
- [H2] cell 28b835b929e0: `## 6. Dynamic activation: with `sh:deactivated`` -> `## 05.04.6 Dynamic activation: with `sh:deactivated``
- [H2] cell 60be504ab09c: `## 7. Extending the vocabulary: custom node expression functions` -> `## 05.04.7 Extending the vocabulary: custom node expression functions`
- [H3] cell d3ab6b80: `### 7.1 Custom List Parameter Functions` -> `### 05.04.7.1 Custom List Parameter Functions`
- [H3] cell 89d7a453: `### 7.2 Custom Named Parameter Functions` -> `### 05.04.7.2 Custom Named Parameter Functions`
- [H2] cell 1b045768: `## 8. `sh:nodeByExpression`: choosing a shape to check via a node expression` -> `## 05.04.8 `sh:nodeByExpression`: choosing a shape to check via a node expression`
- [H2] cell 2f33594a: `## 9. SHACL rules: `sh:rule` and `apply_rules()`` -> `## 05.04.9 SHACL rules: `sh:rule` and `apply_rules()``

Link and file-name rewrites: 5
- [link-target] cell a5f0e001: `05h-shacl-evaluate.ipynb` -> `05.11-shacl-evaluate.ipynb`
- [link-target] cell 2f33594a: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-target] cell 2f33594a: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`
- [link-text] cell 2f33594a: `05c` -> `05.06`
- [link-target] cell 6578c39c4c4f: `05b-shacl-and-sparql.ipynb` -> `05.05-shacl-and-sparql.ipynb`

In-text rewrites it is sure about: 7
- [section-ref] cell 55160c12: `section 1` -> `section 05.04.1`: - `shnex:instancesOf`/`filterShape` selecting a shape's targets (section 1),
- [section-ref] cell 55160c12: `section 2` -> `section 05.04.2`: - `shnex:pathValues`/`var` reading values for a `sh:expression` check (section 2),
- [section-ref] cell 55160c12: `section 3` -> `section 05.04.3`: - `shnex:count` computing a `sh:values` property (section 3).
- [section-ref] cell 55160c12: `section 5` -> `section 05.04.5`: This section 5 is a complete list of the `shnex:` vocabulary.
- [section-ref] cell acee7d31: `section 1` -> `section 05.04.1`: Both were already used with `sh:targetNode` in section 1 to select a shape's targets - here they're shown using `sh:values`.
- [section-ref] cell 71315e51: `section 2` -> `section 05.04.2`: Both were already used with `sh:expression` in section 2 to check a constraint - here they're shown using `sh:values`.
- [section-ref] cell 26b55713: `section 3` -> `section 05.04.3`: `shnex:count` was used with `sh:values` in section 3 to compute a friend count.

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 2
- [section-with-marker] cell 55160c12: `section 4`. Sentence: `shnex:` is SHACL 1.2 Node Expressions' own native vocabulary — operators the specification defines directly, for selecting, reading, aggregating, and transforming nodes — distinct from `sparql:` (section 4), which instead exposes ordina...
- [section-other-guide] cell 2f33594a: `section 2`. Proposal: `05.06.2`. Sentence: [05.06] (05.06-shacl-inference-rules.ipynb), section 2, shows node expressions inside rule templates.

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05b-shacl-and-sparql.ipynb` -> `05.05-shacl-and-sparql.ipynb`

Cells that change: 7

Heading rewrites: 6
- [H1] cell d1344ca5: `# 05b SHACL and SPARQL` -> `# 05.05 SHACL and SPARQL`
- [H2] cell bd37c621: `## 1. `sh:sparql` constraints` -> `## 05.05.1 `sh:sparql` constraints`
- [H3] cell 0c741040: `### 1.1 RDF 1.2 syntax inside the query` -> `### 05.05.1.1 RDF 1.2 syntax inside the query`
- [H3] cell b39359b5: `### 1.2 `sh:resultAnnotation`: inject extra properties into a violation` -> `### 05.05.1.2 `sh:resultAnnotation`: inject extra properties into a violation`
- [H2] cell 602ebba8: `## 2. User-defined `sh:ConstraintComponent`` -> `## 05.05.2 User-defined `sh:ConstraintComponent``
- [H3] cell 2cef2d92: `### 2.1 RDF 1.2 values inside a custom validator` -> `### 05.05.2.1 RDF 1.2 values inside a custom validator`

Link and file-name rewrites: 2
- [link-target] cell 419ec2e1: `05a-shacl-node-expressions.ipynb#7.-Extending-the-vocabulary:-custom-node-expression-functions` -> `05.04-shacl-node-expressions.ipynb#05.04.7-Extending-the-vocabulary:-custom-node-expression-functions`
- [link-anchor] cell 419ec2e1: `#7.-Extending-the-vocabulary:-custom-node-expression-functions` -> `#05.04.7-Extending-the-vocabulary:-custom-node-expression-functions`

In-text rewrites it is sure about: 1
- [section-ref] cell bd37c621: `section 2` -> `section 05.05.2`: No parameter, no reusable component — for that, see section 2.

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 1
- [link-anchor] cell 419ec2e1: `[SHACL shapes guide] (05.01-validating-with-shacl-1.2.ipynb#Known-limitations)`. Sentence: - **Content-level validation of `sh:select`/`sh:ask`/`sh:construct` query text** (is the string actually syntactically valid SPARQL, not just an `xsd:string`) is checked structurally by meta-shacl today, not parsed as real SPARQL — a del...

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`

Cells that change: 15

Heading rewrites: 14
- [H1] cell 4ac26b06: `# 05c SHACL Inference Rules` -> `# 05.06 SHACL Inference Rules`
- [H2] cell 6540e6cd: `## 1. Basic rules: `sh:TripleRule`` -> `## 05.06.1 Basic rules: `sh:TripleRule``
- [H2] cell 95f97060: `## 2. Node expressions inside rule templates` -> `## 05.06.2 Node expressions inside rule templates`
- [H2] cell cbcd66cb: `## 3. `sh:SPARQLRule`` -> `## 05.06.3 `sh:SPARQLRule``
- [H2] cell 649b3f07: `## 4. `sh:condition`` -> `## 05.06.4 `sh:condition``
- [H2] cell e9ac389e: `## 5. Rules run to a fixpoint` -> `## 05.06.5 Rules run to a fixpoint`
- [H2] cell a3fa58db: `## 6. Ordering: `sh:layer` and `sh:runOnce`` -> `## 05.06.6 Ordering: `sh:layer` and `sh:runOnce``
- [H2] cell cea54478: `## 7. Rule sets: running only some rules` -> `## 05.06.7 Rule sets: running only some rules`
- [H2] cell b5fab030: `## 8. Global rules: not attached to any shape` -> `## 05.06.8 Global rules: not attached to any shape`
- [H2] cell 2b5e7a51: `## 9. Provenance: `sh:sourceRule`` -> `## 05.06.9 Provenance: `sh:sourceRule``
- [H2] cell 5a767e52: `## 10. Rules and RDF 1.2: triple terms` -> `## 05.06.10 Rules and RDF 1.2: triple terms`
- [H2] cell 65173206: `## 11. `apply_rules()` never mutates its input` -> `## 05.06.11 `apply_rules()` never mutates its input`
- [H2] cell b1fe08d8: `## 12. Error behavior: the iteration and triple caps and unsupported rule types` -> `## 05.06.12 Error behavior: the iteration and triple caps and unsupported rule types`
- [H2] cell c13a7e01: `## 13. Checking the result: `apply_rules()` validates nothing` -> `## 05.06.13 Checking the result: `apply_rules()` validates nothing`

Link and file-name rewrites: 2
- [link-target] cell 4ac26b06: `05f-shacl-subgraph-extraction.ipynb` -> `05.09-shacl-subgraph-extraction.ipynb`
- [link-target] cell 95f97060: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`

In-text rewrites it is sure about: 7
- [section-ref] cell 4ac26b06: `section 13` -> `section 05.06.13`: Rules are different from both: they **materialize new, real triples**, computed from existing ones, and return them in `result.inferred_graph`. `apply_rules()` validates nothing; section 13 shows how to check the result.
- [section-ref] cell 6540e6cd: `section 11` -> `section 05.06.11`: Here, every `ex:Person` gets a new `ex:isPerson true` triple. `apply_rules()` returns a `RulesResult` - use `result.inferred_graph` for just the newly-produced triples (see section 11 for exactly what happens to the graph object you pass...
- [section-ref] cell e9ac389e: `section 12` -> `section 05.06.12`: A rule set that never reaches a fixpoint is stopped by `max_iterations` (default 1000) or `max_triples` (default 5,000,000), which raise an `ExecutionError` of kind `"rule"`; see section 12.
- [section-ref] cell a3fa58db: `section 12` -> `section 05.06.12`: `sh:runOnce` marks a rule to fire at most once per focus node within its layer, rather than iterating to a fixpoint - essential for a rule that mints something new (like a fresh blank node) on every execution, which would otherwise look ...
- [section-ref] cell 0607f971: `section 8` -> `section 05.06.8`: - **`sh:tempTriple`** (a triple visible only during rule execution, stripped before the final result) isn't demonstrated here - it's supported for shape-attached rules but not yet wired into the global-rules path (section 8).
- [section-ref] cell 0607f971: `section 6` -> `section 05.06.6`: - **Cross-path layering.** The shape-attached layered loop (section 6) and the global-rules layered loop (section 8) are two separate fixpoints, not one unified cross-path fixpoint - a global `sh:runOnce` rule creating instances a shape-...
- [section-ref] cell 0607f971: `section 8` -> `section 05.06.8`: - **Cross-path layering.** The shape-attached layered loop (section 6) and the global-rules layered loop (section 8) are two separate fixpoints, not one unified cross-path fixpoint - a global `sh:runOnce` rule creating instances a shape-...

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 1
- [spec-sign] cell 4ac26b06: `§8`. Sentence: It briefly lived inside "SHACL 1.2 SPARQL Extensions" §8 and, before that, in a now-retired standalone "SHACL 1.2 Rules" document - the vocabulary and behavior haven't changed across any of these moves, only the citation has (see [shacl1...

UNMAPPED reference (stops the stage): 0

### `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`

Cells that change: 11

Heading rewrites: 9
- [H1] cell n01-title: `# 05d SHACL UI` -> `# 05.07 SHACL UI`
- [H2] cell n10-fixed-intro: `## 1. Fixed widgets` -> `## 05.07.1 Fixed widgets`
- [H2] cell n20-launch-intro: `## 2. Using widgets in a UI` -> `## 05.07.2 Using widgets in a UI`
- [H2] cell n30-scoring-intro: `## 3. Scoring` -> `## 05.07.3 Scoring`
- [H3] cell n39-shape-intro: `### 3.1 Letting the property shape decide` -> `### 05.07.3.1 Letting the property shape decide`
- [H3] cell n40-matcher-intro: `### 3.2 Letting the data decide` -> `### 05.07.3.2 Letting the data decide`
- [H3] cell n41-unimplemented-md: `### 3.3 Widgets your application does not implement` -> `### 05.07.3.3 Widgets your application does not implement`
- [H3] cell 8b57a7bb: `### 3.4 Why a widget was chosen` -> `### 05.07.3.4 Why a widget was chosen`
- [H2] cell n45-schema-intro: `## 4. Working with StarShaclProcessor` -> `## 05.07.4 Working with StarShaclProcessor`

Link and file-name rewrites: 0

In-text rewrites it is sure about: 3
- [section-ref] cell n12-select-editors: `Section 3` -> `Section 05.07.3`: Section 3 shows how a scoring catalog fills that gap.
- [section-ref] cell n28-launch: `section 1` -> `section 05.07.1`: Put it together with the person from section 1: an **editable form** (the fixed editors) and a **read-only page** (the fixed viewers).
- [section-ref] cell n30-scoring-intro: `section 1` -> `section 05.07.1`: First, the person shape with no catalog, as in section 1.

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 2
- [section-unresolved] cell n01-title: `section 8.4`. Sentence: Grouping, ordering and layout hints (its section 8.4) are still editor's notes, so this guide does not cover them.
- [section-unresolved] cell n50-appendix: `section 9`. Sentence: Each widget's scoring rules - when it is the best fit - are in section 9 of the [specification] (https://www.w3.org/TR/shacl12-ui/).

UNMAPPED reference (stops the stage): 0

### `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`

Cells that change: 13

Heading rewrites: 12
- [H1] cell 7f93b83c: `# 05e SHACL Profiling` -> `# 05.08 SHACL Profiling`
- [H2] cell 196701a5: `## 1. Packaging SHACL` -> `## 05.08.1 Packaging SHACL`
- [H3] cell e702dd89: `### 1.1 `starlayer.shacl`'s own packaging support` -> `### 05.08.1.1 `starlayer.shacl`'s own packaging support`
- [H3] cell fc13b2e8: `### 1.2 SHACL packaging and `owl:imports`` -> `### 05.08.1.2 SHACL packaging and `owl:imports``
- [H3] cell 1451e7a2: `### 1.3 Making a set of shapes self-contained` -> `### 05.08.1.3 Making a set of shapes self-contained`
- [H3] cell e0b10001: `### 1.4 The entailment a shapes graph needs: `sh:entailment`` -> `### 05.08.1.4 The entailment a shapes graph needs: `sh:entailment``
- [H2] cell 4ef4c393: `## 2. Validation reports and `sh:conformsToShapesGraph` inference` -> `## 05.08.2 Validation reports and `sh:conformsToShapesGraph` inference`
- [H3] cell 82b18c78: `### 2.1 Recording conformance` -> `### 05.08.2.1 Recording conformance`
- [H3] cell ed000011: `### 2.2 Describing graphs: `sh:dataGraph` and `sh:conformsToShapesGraph`` -> `### 05.08.2.2 Describing graphs: `sh:dataGraph` and `sh:conformsToShapesGraph``
- [H2] cell 8b581750: `## 3. Profiling with SHACL` -> `## 05.08.3 Profiling with SHACL`
- [H2] cell 37e4c721: `## 4. Profiles of `starlayer.starontology`` -> `## 05.08.4 Profiles of `starlayer.starontology``
- [H2] cell 32d1eb05: `## 5. Declaring `starlayer.shacl`'s own conformance (§3, "Profiles of SHACL")` -> `## 05.08.5 Declaring `starlayer.shacl`'s own conformance (§3, "Profiles of SHACL")`

Link and file-name rewrites: 1
- [link-target] cell 32d1eb05: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`

In-text rewrites it is sure about: 2
- [section-ref] cell 8b581750: `section 2` -> `section 05.08.2`: Once that relationship is declared, validating an expense data graph with a shapes graph implementing that policy not only allows the assertion that the data conforms to the shapes graph (section 2 above), but that the data conforms to t...
- [section-ref] cell f1a2b3c4: `Sections 3 and 4` -> `Sections 05.08.3 and 05.08.4`: Validating any shapes graph against `shacl_shacl` and calling `derive_conforms_to()` then derives a real `dcterms:conformsTo` claim against those public profiles directly, the same mechanism Sections 3 and 4 used for the expense policy a...

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 4
- [section-range] cell 196701a5: `sections 2-4`. Proposal: `05.08.2 to 05.08.4`. Sentence: SHACL 1.2 Profiling provides guidance for three related activities: **packaging SHACL** (identifying a shapes graph as a named resource, and describing its constituent shapes and dependencies - this section), **profiling with SHACL** (de...
- [section-with-marker] cell 196701a5: `section 5`. Sentence: SHACL 1.2 Profiling provides guidance for three related activities: **packaging SHACL** (identifying a shapes graph as a named resource, and describing its constituent shapes and dependencies - this section), **profiling with SHACL** (de...
- [section-relative] cell 4ef4c393: `section .4.4`. Proposal: `05.01.4.4`. Sentence: When available, the validation report records identifiers for the data graph (`sh:usedDataGraph`) and shapes graph (`sh:usedShapesGraph`) on a `sh:ValidationActivity` that generated the report, as the Profiling draft describes (see secti...
- [section-with-marker] cell 32d1eb05: `Sections 3 and 4`. Sentence: Separately, the Profiling draft's "conforms to standard" rule shows that a SHACL *shapes graph* can declare itself `prof:isProfileOf` a specification, and `derive_conforms_to()`'s second rule then lets data that conforms to that shapes g...

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 2
- [spec-sign] cell 32d1eb05: `§3`. Sentence: SHACL Profiling 1.2 §3 demonstrates how to create a profile *of* a specification — using SHACL's own seven feature-area profiles (Core, SPARQL, Node Expressions, Rules, UI, Profiling, and a Union of all of them) — each with its own IRI.
- [spec-sign] cell 32d1eb05: `§4.4`. Sentence: Profiles can, in principle, declare relationships to *other* profiles (§4.4, "Profile Hierarchies").

UNMAPPED reference (stops the stage): 0

### `05f-shacl-subgraph-extraction.ipynb` -> `05.09-shacl-subgraph-extraction.ipynb`

Cells that change: 14

Heading rewrites: 13
- [H1] cell f8f3bc8d: `# 05f SHACL Shape-Scoped Subgraph Extraction` -> `# 05.09 SHACL Shape-Scoped Subgraph Extraction`
- [H2] cell 798fcaa2: `## 1. Basic extraction` -> `## 05.09.1 Basic extraction`
- [H2] cell 103ad365: `## 2. Extracting across a whole shapes graph` -> `## 05.09.2 Extracting across a whole shapes graph`
- [H2] cell 8625a6e1: `## 3. The closed-shape acceptance test` -> `## 05.09.3 The closed-shape acceptance test`
- [H2] cell 0d2a8db0: `## 4. Comparing extractions: isomorphism` -> `## 05.09.4 Comparing extractions: isomorphism`
- [H2] cell 99b5abfc: `## 5. Checking a pending addition before it lands` -> `## 05.09.5 Checking a pending addition before it lands`
- [H2] cell 07c4b63d: `## 6. Multi-hop paths` -> `## 05.09.6 Multi-hop paths`
- [H2] cell 9a6451dd: `## 7. Nested shapes` -> `## 05.09.7 Nested shapes`
- [H2] cell 1c1226e9: `## 8. Logical constraints: `sh:or` and `sh:xone`` -> `## 05.09.8 Logical constraints: `sh:or` and `sh:xone``
- [H2] cell a45bad48: `## 9. Qualified value shapes and determinism` -> `## 05.09.9 Qualified value shapes and determinism`
- [H2] cell da7debd2: `## 10. Cycles and unbounded paths` -> `## 05.09.10 Cycles and unbounded paths`
- [H2] cell 79158c39: `## 11. Non-conformance` -> `## 05.09.11 Non-conformance`
- [H2] cell 3cc57fb3: `## 12. Putting it together: hashing a subgraph` -> `## 05.09.12 Putting it together: hashing a subgraph`

Link and file-name rewrites: 0

In-text rewrites it is sure about: 7
- [section-ref] cell f8f3bc8d: `section 2` -> `section 05.09.2`: `shape=`/`focus_node=` are optional filters, not required inputs - given neither, `extract_subgraph()` discovers every real entry point the whole shapes graph declares (every shape's own SHACL targets) and returns the union of everything...
- [section-ref] cell 103ad365: `section 1` -> `section 05.09.1`: Passing both reproduces section 1's single-pair behavior exactly.
- [section-ref] cell 0d2a8db0: `section 2` -> `section 05.09.2`: Now that section 2 has verified extraction is exactly right, what happens when the underlying data actually changes over time?
- [section-ref] cell a45bad48: `section 12` -> `section 05.09.12`: This trades minimality for determinism: the result never depends on store iteration order, which matters because this feature feeds a hash (see section 12).
- [section-ref] cell 3cc57fb3: `section 5` -> `section 05.09.5`: The walkthrough below is a full lifecycle for one JE, tying this together with section 5's staging pattern:
- [section-ref] cell 89087497: `Section 5` -> `Section 05.09.5`: - **Protecting *existing* commitments against unrelated writes isn't feasible in general.** Section 5's staging pattern pre-checks a write safely because it already knows which commitment it's protecting - extract before/after for that o...
- [section-ref] cell 89087497: `Section 12` -> `Section 05.09.12`: Section 12's commitment binds the shape's *identity* (its IRI), which catches a verifier using the wrong shape entirely - but it doesn't hash the shape's own *definition*, so a shape silently redefined under the same IRI (that happens to...

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05g-building-on-shacl.ipynb` -> `05.10-building-on-shacl.ipynb`

Cells that change: 13

Heading rewrites: 13
- [H1] cell e3a6cd4a: `# 05g Building on SHACL` -> `# 05.10 Building on SHACL`
- [H2] cell a5f64d84: `## 1. What a shapes graph is made of` -> `## 05.10.1 What a shapes graph is made of`
- [H3] cell a5f64d84: `### 1.1 The types a shapes graph entails` -> `### 05.10.1.1 The types a shapes graph entails`
- [H3] cell c0a19dc0: `### 1.2 Which graph a shape belongs to` -> `### 05.10.1.2 Which graph a shape belongs to`
- [H3] cell 0cf9ff50: `### 1.3 Problems in embedded SPARQL` -> `### 05.10.1.3 Problems in embedded SPARQL`
- [H3] cell s05g0014: `### 1.4 Parameter values of constraint components` -> `### 05.10.1.4 Parameter values of constraint components`
- [H2] cell 548b9175: `## 2. Following a path` -> `## 05.10.2 Following a path`
- [H2] cell f504cab4: `## 3. Node expressions` -> `## 05.10.3 Node expressions`
- [H2] cell 212cf303: `## 4. Widgets and properties of a form` -> `## 05.10.4 Widgets and properties of a form`
- [H2] cell s05g0020: `## 5. What a field can offer` -> `## 05.10.5 What a field can offer`
- [H3] cell s05g0022: `### 5.1 How a value is held, and whether one would be accepted` -> `### 05.10.5.1 How a value is held, and whether one would be accepted`
- [H2] cell s05g0024: `## 6. Reading a report` -> `## 05.10.6 Reading a report`
- [H2] cell s05g0030: `## 7. The form for a node` -> `## 05.10.7 The form for a node`

Link and file-name rewrites: 3
- [link-target] cell c0a19dc0: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`
- [link-target] cell f504cab4: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`
- [link-target] cell 212cf303: `05d-shacl-ui.ipynb` -> `05.07-shacl-ui.ipynb`

In-text rewrites it is sure about: 2
- [section-ref] cell 209a3d2a: `section 1` -> `section 05.10.1`: Run cells from top to bottom; later sections reuse the shapes graph of section 1.
- [section-ref] cell s05g0022: `section 6` -> `section 05.10.6`: It returns a `ValueCheck` with `conforms` and the `results` as report records (section 6).

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 3
- [dotted-id] cell c0a19dc0: `[4.e] (05e-shacl-profiling.ipynb)`. Proposal: `05.08`. Sentence: `shapes_graph_members(graph, shapes_graph)` returns the elements that belong to a `sh:ShapesGraph` by `rdfs:member`, `rdfs:isDefinedBy` or `owl:imports` ([4.e] (05e-shacl-profiling.ipynb)), or `None` when the IRI is not a `sh:Graph` in t...
- [dotted-id] cell f504cab4: `[4.a] (05a-shacl-node-expressions.ipynb)`. Proposal: `05.04`. Sentence: `evaluate_expression(shapes_graph, data_graph, expression, focus=None, *, scope=None)` evaluates a node expression, a node of the shapes graph, for a focus node and returns the nodes it gives, in order. An expression that cannot be evalu...
- [dotted-id] cell 212cf303: `[4.d] (05d-shacl-ui.ipynb)`. Proposal: `05.07`. Sentence: `select_widget(shape_node=, focus_node=, data_graph=, shapes_graph=, scoring_graph=, role=)` chooses the widget for one property shape; `select_widgets()` does it for every property of a node shape, and `explain_widgets()` says why ([4.d...

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

### `05h-shacl-evaluate.ipynb` -> `05.11-shacl-evaluate.ipynb`

Cells that change: 4

Heading rewrites: 3
- [H1] cell f5a00002: `# 05h SHACL `evaluate()`: shaping data for another process` -> `# 05.11 SHACL `evaluate()`: shaping data for another process`
- [H2] cell f5a00005: `## 1. Selecting nodes and values, and computing a value` -> `## 05.11.1 Selecting nodes and values, and computing a value`
- [H2] cell s05n0011: `## 2. Stored values, computed values and defaults` -> `## 05.11.2 Stored values, computed values and defaults`

Link and file-name rewrites: 2
- [link-target] cell f5a00002: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`
- [link-target] cell f5a00006: `05a-shacl-node-expressions.ipynb` -> `05.04-shacl-node-expressions.ipynb`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 1
- [known-fix] cell f5a00004: `see section 2.1)`. Proposal: `see section 05.01.2)`. Sentence: # (StarLayerGraphs, see section 2.1); the StarLayerGraph inputs are built by parsing Turtle.

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

## Referrer guides (only the cells named here change)

### `02e-graphs-inferencing.ipynb` (name unchanged in this stage)

Cells that change: 1

Heading rewrites: 0

Link and file-name rewrites: 1
- [link-target] cell ef916509: `05c-shacl-inference-rules.ipynb` -> `05.06-shacl-inference-rules.ipynb`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

Cells changed in this guide: ef916509

### `06-starlayer-schemas-and-ontologies.ipynb` (name unchanged in this stage)

Cells that change: 1

Heading rewrites: 0

Link and file-name rewrites: 1
- [link-target] cell 4809830b: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

Cells changed in this guide: 4809830b

### `06d-shacl-library-registry.ipynb` (name unchanged in this stage)

Cells that change: 1

Heading rewrites: 0

Link and file-name rewrites: 1
- [link-target] cell 4809830b: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

Cells changed in this guide: 4809830b

### `07c-canonical-hashing.ipynb` (name unchanged in this stage)

Cells that change: 1

Heading rewrites: 0

Link and file-name rewrites: 1
- [link-target] cell eb53b9dc: `05f-shacl-subgraph-extraction.ipynb` -> `05.09-shacl-subgraph-extraction.ipynb`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

Cells changed in this guide: eb53b9dc

### `appendix-a-public-resources.ipynb` (name unchanged in this stage)

Cells that change: 1

Heading rewrites: 0

Link and file-name rewrites: 1
- [link-target] cell faf23228: `05e-shacl-profiling.ipynb` -> `05.08-shacl-profiling.ipynb`

In-text rewrites it is sure about: 0

Needs a decision (not written unless --with-proposals, and only where a proposal exists): 0

Deferred (the referent guide is in a chapter that is not renamed yet): 0

Left alone, listed for a read (probably a specification section or no heading of this guide): 0

UNMAPPED reference (stops the stage): 0

Cells changed in this guide: faf23228

## Counts (guides)

Rewrites by rule:
- H1: 8
- H2: 54
- H3: 37
- H3-relative: 18
- H4-relative: 16
- bullet-relative: 13
- link-anchor: 1
- link-target: 49
- link-text: 20
- referrer:link-target: 5
- section-ref: 29

Flags by category and rule:
- decision:dotted-id: 3
- decision:known-fix: 2
- decision:link-anchor: 1
- decision:section-other-guide: 3
- decision:section-range: 1
- decision:section-relative: 2
- decision:section-with-marker: 3
- deferred:section-other-guide: 1
- left:section-unresolved: 2
- left:spec-sign: 3

Cells that change in the primary guides: 149. Cells that change in referrer guides: 5.

## Files that are not guides (plan-files --chapter 05)

### `docs/guides/README.md`: 10 edits, 0 flags
- [readme-row] line 28: `- **5.2 [The StarLayer SHACL engine] (05.02-starlayer-shacl-engine.ipynb)** - the processor and the functions of `sta...` -> `- **05.02 [The StarLayer SHACL engine] (05.02-starlayer-shacl-engine.ipynb)** - the processor and the functions of `s...`
- [readme-row] line 29: `- **5.3 [SHACL shapes as classes] (05.03-shapes-as-classes.ipynb)** - a shape that is also a class (`sh:ShapeClass`) ...` -> `- **05.03 [SHACL shapes as classes] (05.03-shapes-as-classes.ipynb)** - a shape that is also a class (`sh:ShapeClass`...`
- [readme-row] line 30: `- **5.a [SHACL node expressions] (05a-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vocabu...` -> `- **05.04 [SHACL node expressions] (05.04-shacl-node-expressions.ipynb)** - the `shnex:`/`sparql:` node-expression vo...`
- [readme-row] line 31: `- **5.b [SHACL and SPARQL] (05b-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintCompo...` -> `- **05.05 [SHACL and SPARQL] (05.05-shacl-and-sparql.ipynb)** - `sh:sparql` constraints, user-defined `sh:ConstraintC...`
- [readme-row] line 32: `- **5.c [SHACL inference rules] (05c-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, exec...` -> `- **05.06 [SHACL inference rules] (05.06-shacl-inference-rules.ipynb)** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`, ...`
- [readme-row] line 33: `- **5.d [SHACL UI] (05d-shacl-ui.ipynb)** - `shui:` widgets: fixed `shui:editor`/`shui:viewer` choices via `select_wi...` -> `- **05.07 [SHACL UI] (05.07-shacl-ui.ipynb)** - `shui:` widgets: fixed `shui:editor`/`shui:viewer` choices via `selec...`
- [readme-row] line 34: `- **5.e [SHACL profiling] (05e-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging con...` -> `- **05.08 [SHACL profiling] (05.08-shacl-profiling.ipynb)** - `sh:ShapesGraph`/`sh:DataGraph`/`owl:imports` packaging...`
- [readme-row] line 35: `- **5.f [SHACL subgraph extraction & hashing] (05f-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `close_...` -> `- **05.09 [SHACL subgraph extraction & hashing] (05.09-shacl-subgraph-extraction.ipynb)** - `extract_subgraph()`, `cl...`
- [readme-row] line 36: `- **5.g [Building on SHACL] (05g-building-on-shacl.ipynb)** - what an application that edits or displays shapes asks ...` -> `- **05.10 [Building on SHACL] (05.10-building-on-shacl.ipynb)** - what an application that edits or displays shapes a...`
- [readme-row] line 37: `- **5.h [SHACL `evaluate()`] (05h-shacl-evaluate.ipynb)** - using a shape to select the nodes and values to present, ...` -> `- **05.11 [SHACL `evaluate()`] (05.11-shacl-evaluate.ipynb)** - using a shape to select the nodes and values to prese...`

### `docs/user-guide-version.json`: 8 edits, 0 flags
- [file-name] line 28: `"docs/guides/05a-shacl-node-expressions.ipynb",` -> `"docs/guides/05.04-shacl-node-expressions.ipynb",`
- [file-name] line 29: `"docs/guides/05b-shacl-and-sparql.ipynb",` -> `"docs/guides/05.05-shacl-and-sparql.ipynb",`
- [file-name] line 30: `"docs/guides/05c-shacl-inference-rules.ipynb",` -> `"docs/guides/05.06-shacl-inference-rules.ipynb",`
- [file-name] line 31: `"docs/guides/05d-shacl-ui.ipynb",` -> `"docs/guides/05.07-shacl-ui.ipynb",`
- [file-name] line 32: `"docs/guides/05e-shacl-profiling.ipynb",` -> `"docs/guides/05.08-shacl-profiling.ipynb",`
- [file-name] line 33: `"docs/guides/05f-shacl-subgraph-extraction.ipynb",` -> `"docs/guides/05.09-shacl-subgraph-extraction.ipynb",`
- [file-name] line 34: `"docs/guides/05g-building-on-shacl.ipynb",` -> `"docs/guides/05.10-building-on-shacl.ipynb",`
- [file-name] line 35: `"docs/guides/05h-shacl-evaluate.ipynb",` -> `"docs/guides/05.11-shacl-evaluate.ipynb",`

### `tools/kg/codekg/curated/notebook-links.ttl`: 38 edits, 0 flags
- [ttl-id] line 114: `nl:05-22edd3bd a slkg:NotebookExample ;` -> `nl:05.01-22edd3bd a slkg:NotebookExample ;`
- [ttl-path] line 125: `slkg:notebookPath "docs/guides/05c-shacl-inference-rules.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.06-shacl-inference-rules.ipynb" ;`
- [ttl-id] line 124: `nl:05c-442768db a slkg:NotebookExample ;` -> `nl:05.06-442768db a slkg:NotebookExample ;`
- [ttl-path] line 134: `slkg:notebookPath "docs/guides/05d-shacl-ui.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.07-shacl-ui.ipynb" ;`
- [ttl-id] line 133: `nl:04d-n13-editors a slkg:NotebookExample ;` -> `nl:05.07-n13-editors a slkg:NotebookExample ;`
- [ttl-path] line 143: `slkg:notebookPath "docs/guides/05d-shacl-ui.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.07-shacl-ui.ipynb" ;`
- [ttl-id] line 142: `nl:04d-n45-schema-select a slkg:NotebookExample ;` -> `nl:05.07-n45-schema-select a slkg:NotebookExample ;`
- [ttl-path] line 152: `slkg:notebookPath "docs/guides/05e-shacl-profiling.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.08-shacl-profiling.ipynb" ;`
- [ttl-id] line 151: `nl:05e-96560f37 a slkg:NotebookExample ;` -> `nl:05.08-96560f37 a slkg:NotebookExample ;`
- [ttl-path] line 160: `slkg:notebookPath "docs/guides/05e-shacl-profiling.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.08-shacl-profiling.ipynb" ;`
- [ttl-id] line 159: `nl:05e-c2a7c429 a slkg:NotebookExample ;` -> `nl:05.08-c2a7c429 a slkg:NotebookExample ;`
- [ttl-path] line 169: `slkg:notebookPath "docs/guides/05f-shacl-subgraph-extraction.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.09-shacl-subgraph-extraction.ipynb" ;`
- [ttl-id] line 168: `nl:05f-98caadf5 a slkg:NotebookExample ;` -> `nl:05.09-98caadf5 a slkg:NotebookExample ;`
- [ttl-path] line 178: `slkg:notebookPath "docs/guides/05f-shacl-subgraph-extraction.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.09-shacl-subgraph-extraction.ipynb" ;`
- [ttl-id] line 177: `nl:05f-80d50838 a slkg:NotebookExample ;` -> `nl:05.09-80d50838 a slkg:NotebookExample ;`
- [ttl-path] line 269: `slkg:notebookPath "docs/guides/05h-shacl-evaluate.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.11-shacl-evaluate.ipynb" ;`
- [ttl-id] line 268: `nl:05h-88a5feb0 a slkg:NotebookExample ;` -> `nl:05.11-88a5feb0 a slkg:NotebookExample ;`
- [ttl-path] line 362: `slkg:notebookPath "docs/guides/05d-shacl-ui.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.07-shacl-ui.ipynb" ;`
- [ttl-id] line 361: `nl:05d-98809341 a slkg:NotebookExample ;` -> `nl:05.07-98809341 a slkg:NotebookExample ;`
- [ttl-path] line 371: `slkg:notebookPath "docs/guides/05e-shacl-profiling.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.08-shacl-profiling.ipynb" ;`
- [ttl-id] line 370: `nl:05e-352c1708 a slkg:NotebookExample ;` -> `nl:05.08-352c1708 a slkg:NotebookExample ;`
- [ttl-id] line 380: `nl:05i-30c67e26 a slkg:NotebookExample ;` -> `nl:05.02-30c67e26 a slkg:NotebookExample ;`
- [ttl-id] line 389: `nl:05-57dcbbde a slkg:NotebookExample ;` -> `nl:05.01-57dcbbde a slkg:NotebookExample ;`
- [ttl-id] line 398: `nl:05-a9353f25 a slkg:NotebookExample ;` -> `nl:05.01-a9353f25 a slkg:NotebookExample ;`
- [ttl-id] line 407: `nl:05-f41bd5ea a slkg:NotebookExample ;` -> `nl:05.01-f41bd5ea a slkg:NotebookExample ;`
- [ttl-id] line 417: `nl:05-8c133de1 a slkg:NotebookExample ;` -> `nl:05.01-8c133de1 a slkg:NotebookExample ;`
- [ttl-path] line 503: `slkg:notebookPath "docs/guides/05g-building-on-shacl.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.10-building-on-shacl.ipynb" ;`
- [ttl-id] line 502: `nl:05g-64f05da5 a slkg:NotebookExample ;` -> `nl:05.10-64f05da5 a slkg:NotebookExample ;`
- [ttl-path] line 512: `slkg:notebookPath "docs/guides/05g-building-on-shacl.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.10-building-on-shacl.ipynb" ;`
- [ttl-id] line 511: `nl:05g-263cfdfb a slkg:NotebookExample ;` -> `nl:05.10-263cfdfb a slkg:NotebookExample ;`
- [ttl-path] line 521: `slkg:notebookPath "docs/guides/05g-building-on-shacl.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.10-building-on-shacl.ipynb" ;`
- [ttl-id] line 520: `nl:05g-f5157b68 a slkg:NotebookExample ;` -> `nl:05.10-f5157b68 a slkg:NotebookExample ;`
- [ttl-path] line 530: `slkg:notebookPath "docs/guides/05g-building-on-shacl.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.10-building-on-shacl.ipynb" ;`
- [ttl-id] line 529: `nl:05g-0cd16b52 a slkg:NotebookExample ;` -> `nl:05.10-0cd16b52 a slkg:NotebookExample ;`
- [ttl-path] line 540: `slkg:notebookPath "docs/guides/05g-building-on-shacl.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.10-building-on-shacl.ipynb" ;`
- [ttl-id] line 539: `nl:05g-5839b261 a slkg:NotebookExample ;` -> `nl:05.10-5839b261 a slkg:NotebookExample ;`
- [ttl-path] line 550: `slkg:notebookPath "docs/guides/05g-building-on-shacl.ipynb" ;` -> `slkg:notebookPath "docs/guides/05.10-building-on-shacl.ipynb" ;`
- [ttl-id] line 549: `nl:05g-55975daa a slkg:NotebookExample ;` -> `nl:05.10-55975daa a slkg:NotebookExample ;`

### `packages/starlayer/tests/repo/test_hunt_docs_notebooks.py`: 4 edits, 0 flags
- [file-name] line 69: `assert "keyword to ask for" not in _text("05e-shacl-profiling.ipynb")` -> `assert "keyword to ask for" not in _text("05.08-shacl-profiling.ipynb")`
- [file-name] line 115: `nb = _text("05f-shacl-subgraph-extraction.ipynb", ("markdown", "code"))` -> `nb = _text("05.09-shacl-subgraph-extraction.ipynb", ("markdown", "code"))`
- [known-fix] line 116: `heads = dict(re.findall(r"^## (\d+)\. (.*)$", nb, re.M))` -> `heads = dict(re.findall(r"^## 05\.09\.(\d+) (.*)$", nb, re.M))`
- [known-fix] line 114: `def test_guide_04f_section_references_point_at_the_right_sections` -> `def test_guide_05_09_section_references_point_at_the_right_sections`

### `docs/app-development-plans/graph-workbench-app.md`: 1 edits, 0 flags
- [file-name] line 50: `- Guide `docs/guides/05d-shacl-ui.ipynb` for the intended semantics.` -> `- Guide `docs/guides/05.07-shacl-ui.ipynb` for the intended semantics.`

### `docs/app-development-plans/repo-prep-plan.md`: 2 edits, 0 flags
- [file-name] line 63: `- Still open in workstream 6: Appendix A status and the 4 unexecuted code cells in `05d-shacl-ui.ipynb` (notebook edi...` -> `- Still open in workstream 6: Appendix A status and the 4 unexecuted code cells in `05.07-shacl-ui.ipynb` (notebook e...`
- [file-name] line 107: `- `docs/guides/`: move the stray "Notes on guides and other comments" to the repo task tracker/`docs/working/`; move ...` -> `- `docs/guides/`: move the stray "Notes on guides and other comments" to the repo task tracker/`docs/working/`; move ...`

### `docs/design/future_enhancements.md`: 3 edits, 2 flags
- [file-name] line 30: `- **Notebooks never show how to fetch one of `starontology`'s own bundled registry files directly by URL, bypassing `...` -> `- **Notebooks never show how to fetch one of `starontology`'s own bundled registry files directly by URL, bypassing `...`
- [file-name] line 37: `- **Build a dedicated user guide for `validate()`/`StarShaclProcessor` validation itself** (2026-10-09) - none of the...` -> `- **Build a dedicated user guide for `validate()`/`StarShaclProcessor` validation itself** (2026-10-09) - none of the...`
- [file-name] line 306: `4. **Refresh the widget appendix in `docs/guides/05d-shacl-ui.ipynb`.** The appendix is a deliberately *static* markd...` -> `4. **Refresh the widget appendix in `docs/guides/05.07-shacl-ui.ipynb`.** The appendix is a deliberately *static* mar...`
- FLAG [letter-id] line 255: - *`data` renamed to the spec's `evaldata`, with the spec's polarity.* In the AST, the parser, evaluation, the `srl:` vocabulary (`srl:ruleEvaldata`/`srl:neg...
- FLAG [letter-id] line 15: - **DONE 2026-10-17: the shape-authoring UI vocabulary (`stsh:` presentation shapes) was archived, not deleted.** Moved to the repo-root `docs/working/archiv...

### `docs/design/shacl/shacl12-gap-matrix.md`: 1 edits, 0 flags
- [file-name] line 223: `| ~~`shui:WidgetScore`/`shui:WidgetAcceptMatcher` widget-selection algorithm (given a shape + focus node + scoring gr...` -> `| ~~`shui:WidgetScore`/`shui:WidgetAcceptMatcher` widget-selection algorithm (given a shape + focus node + scoring gr...`

### `docs/design/shacl/starlayer-profile-direction.md`: 1 edits, 0 flags
- [file-name] line 3: `*Moved from `docs/guides/05e-shacl-profiling.ipynb`, section 6 (2026-11-21). This is not implemented as code; it is t...` -> `*Moved from `docs/guides/05.08-shacl-profiling.ipynb`, section 6 (2026-11-21). This is not implemented as code; it is...`

### `docs/guides/STYLE_GUIDE.md`: 3 edits, 0 flags
- [file-name] line 33: `2. at least one concrete thing it unlocks that the reader couldn't do (or would do awkwardly) without it — not just "...` -> `2. at least one concrete thing it unlocks that the reader couldn't do (or would do awkwardly) without it — not just "...`
- [file-name] line 73: `Baseline voice is impersonal third person: "`X` does `Y`," "This covers...," "A `sh:TripleRule` builds..." — this is ...` -> `Baseline voice is impersonal third person: "`X` does `Y`," "This covers...," "A `sh:TripleRule` builds..." — this is ...`
- [file-name] line 98: `No hard cap, but a guideline: if a guide grows past roughly 40–50 cells, it's probably covering more than one coheren...` -> `No hard cap, but a guideline: if a guide grows past roughly 40–50 cells, it's probably covering more than one coheren...`

### `docs/working/guide-coverage-2026-11-13.md`: 1 edits, 5 flags
- [file-name] line 38: `| Building on SHACL: `infer_types`, `shapes_graph_members`, `sparql_query_problems`, `path_values`, `is_inverse`, `ev...` -> `| Building on SHACL: `infer_types`, `shapes_graph_members`, `sparql_query_problems`, `path_values`, `is_inverse`, `ev...`
- FLAG [letter-id] line 12: - `05c`: said a graph has no `set`; it has one now. `02b`, `03a`: say that OWL-RL needs `starlayer-reasoning`. `05`: a typo in a heading.
- FLAG [letter-id] line 31: RDF 1.2 terms, reifiers, annotations and directional literals (`02`); datasets and the store boundary (`02a`, `02d`); RDFS, OWL-RL and OWL-DL inference and q...
- FLAG [letter-id] line 3: Method: every name in `starlayer.graph.__all__`, `starlayer.shacl.__all__` and `starlayer.sparql.__all__`, and every public method of `StarLayerGraph`, was s...
- FLAG [letter-id] line 31: RDF 1.2 terms, reifiers, annotations and directional literals (`02`); datasets and the store boundary (`02a`, `02d`); RDFS, OWL-RL and OWL-DL inference and q...
- FLAG [letter-id] line 67: Nothing from this review. The list of names that stay out of the guides on purpose is above; `05d` is run again after the next push, when the URLs it fetches...

### `packages/starlayer/starlayer/shacl/ui/widget_selection.py`: 1 edits, 0 flags
- [file-name] line 14: ```docs/guides/05d-shacl-ui.ipynb``.` -> ```docs/guides/05.07-shacl-ui.ipynb``.`

### `packages/starlayer/starlayer/starontology/_sources/shacl12-validation-shapes.ttl`: 28 edits, 0 flags
- [file-name] line 2090: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2098: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2111: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2117: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2123: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2129: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2135: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2141: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2147: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2153: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2159: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2165: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2171: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2177: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2183: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2190: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2196: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2202: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2208: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2214: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2220: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2226: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2232: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2238: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2245: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2251: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2258: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`
- [file-name] line 2264: `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...` -> `rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget (see docs/g...`

### `packages/starlayer/starlayer/starontology/shacl/shacl12-shacl.ttl`: 28 edits, 0 flags
- [file-name] line 71: `shui:ValueTableViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...` -> `shui:ValueTableViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...`
- [file-name] line 75: `shui:DetailsViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...` -> `shui:DetailsViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...`
- [file-name] line 80: `shui:BlankNodeViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...` -> `shui:BlankNodeViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...`
- [file-name] line 84: `shui:LabelViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a w...` -> `shui:LabelViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a w...`
- [file-name] line 89: `shui:ImageViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a w...` -> `shui:ImageViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a w...`
- [file-name] line 93: `shui:HyperlinkViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...` -> `shui:HyperlinkViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...`
- [file-name] line 97: `shui:IRIViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a wid...` -> `shui:IRIViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a wid...`
- [file-name] line 101: `shui:HTMLViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a wi...` -> `shui:HTMLViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a wi...`
- [file-name] line 105: `shui:LangStringViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...` -> `shui:LangStringViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...`
- [file-name] line 109: `shui:LiteralViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...` -> `shui:LiteralViewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...`
- [file-name] line 113: `shui:DetailsEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...` -> `shui:DetailsEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...`
- [file-name] line 117: `shui:BlankNodeEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...` -> `shui:BlankNodeEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...`
- [file-name] line 121: `shui:SubClassEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses ...` -> `shui:SubClassEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses ...`
- [file-name] line 126: `shui:InstancesSelectEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it c...` -> `shui:InstancesSelectEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it c...`
- [file-name] line 130: `shui:EnumSelectEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...` -> `shui:EnumSelectEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...`
- [file-name] line 134: `shui:AutoCompleteEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choo...` -> `shui:AutoCompleteEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choo...`
- [file-name] line 138: `shui:IRIEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a wid...` -> `shui:IRIEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a wid...`
- [file-name] line 142: `shui:DateTimePickerEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it ch...` -> `shui:DateTimePickerEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it ch...`
- [file-name] line 146: `shui:DatePickerEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...` -> `shui:DatePickerEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choose...`
- [file-name] line 150: `shui:BooleanEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...` -> `shui:BooleanEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a...`
- [file-name] line 154: `shui:NumberFieldEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choos...` -> `shui:NumberFieldEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it choos...`
- [file-name] line 158: `shui:RichTextEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses ...` -> `shui:RichTextEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses ...`
- [file-name] line 162: `shui:TextAreaWithLangEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it ...` -> `shui:TextAreaWithLangEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it ...`
- [file-name] line 166: `shui:TextAreaEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses ...` -> `shui:TextAreaEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses ...`
- [file-name] line 170: `shui:TextFieldWithLangEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it...` -> `shui:TextFieldWithLangEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it...`
- [file-name] line 174: `shui:TextFieldEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...` -> `shui:TextFieldEditor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses...`
- [file-name] line 183: `shui:viewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget...` -> `shui:viewer rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget...`
- [file-name] line 189: `shui:editor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget...` -> `shui:editor rdfs:comment "ignored by validation; read by starlayer.shacl.ui.widget_selection when it chooses a widget...`

### Counts of the file edits
- file-name: 79
- flag:letter-id: 7
- known-fix: 2
- readme-row: 10
- ttl-id: 22
- ttl-path: 16

