# SHACL Presentation Content (Draft)

*Draft content for `starshacl/assets/shacl-presentation-shapes.ttl` (renamed from
`shacl12-presentation-shapes.ttl` once this lands) — full SHACL Core + SHACL 1.2
predicate coverage, written for a downstream SHACL-training editor. Edit here;
conversion to TTL happens after this is reviewed.*

## Field → RDF mapping

**Which file a field belongs to** (decided 2026-07-19, see `starshacl/assets/shacl12-validation-shapes.ttl`'s and `shacl12-presentation-shapes.ttl`'s own header comments for the canonical statement of this split): the **validation file** owns the single canonical (`@en`) description of anything it defines — no duplicated labels/comments once merged. The **presentation/UI file** only adds genuinely UI-specific content on top: rendering hints (`sh:order`/`sh:group`), additional language-variant `sh:name`/`sh:description` values, and (future) widget/editor assignment. `Example`/`See also` are judgment calls placed with the canonical/validation content below (definitional, not rendering-specific, and not language-variant in nature) — flag if you intended otherwise.

Each predicate entry below becomes a set of triples on the predicate IRI:

| Field here | RDF property | Lives in | Notes |
| --- | --- | --- | --- |
| Name | `sh:name` | Validation (canonical, `@en`); UI file adds other-language values | Single source of truth for a UI label. |
| Description | `sh:description` | Validation (canonical, `@en`); UI file adds other-language values | The main explanatory text. |
| Example | `skos:example` | Validation | Standard SKOS documentation property. |
| Comment | `rdfs:comment` | Validation | Commentary such as common mistakes or caveats. |
| See also | `rdfs:seeAlso` | Validation | Related predicate(s). |
| Group | `sh:group` | UI | One of the `stsh:*Group` instances defined below — rendering-specific, not canonical identity. |
| Order | `sh:order` | UI | Position within its group, for UI ordering — rendering-specific. |
| Spec provenance | `rdfs:isDefinedBy` | Validation | Repeatable. Which W3C document(s) the predicate comes from — see "Spec Provenance" below for the controlled vocabulary. Replaces the old `**[1.2]**` tag with something precise and machine-queryable. |
| Required engine | `stsh:requiredEngine` | Validation | Single-valued. The minimum engine under which the predicate actually works — see "Required Engine" below. |
| Widget | `stsh:widgetType` | UI | Single-valued string tag suggesting an input control (see `stsh:widgetType`'s own `rdfs:comment` in the UI file for the full suggested-value vocabulary). A **default**, not a binding contract — downstream editors are expected to override per-predicate as needed. |
| Node form field | `stsh:nodeFormField` | UI | Boolean. True when this predicate should appear as a field in a NodeShape editor. See "17. Form-Field Membership" below. |
| Property form field | `stsh:propertyFormField` | UI | Boolean. True when this predicate should appear as a field in a PropertyShape editor. See "17. Form-Field Membership" below. |
| Form max count | `stsh:formMaxCount` | UI | Integer. Maximum cardinality in the editing form; absent means multi-valued. |

Predicates marked **[1.2]** in the entries below are pre-conversion shorthand for "has at least one SHACL 1.2 `rdfs:isDefinedBy` value" - kept as a quick visual scan aid while this file is still hand-edited Markdown, but the real, queryable source of truth is the `rdfs:isDefinedBy` values once converted to TTL. Everything else is SHACL Core (1.0/1.1), previously undocumented by this file.

## Spec Provenance

Resolves the open question from the earlier review: reuses `rdfs:isDefinedBy` (a standard property, repeatable for free) rather than inventing a new predicate, pointing at the canonical TR URI for each spec a concept comes from.

**Tag only where a document genuinely adds or changes something - not every document a predicate happens to remain valid in.** A predicate unchanged from SHACL Core into SHACL 1.2 Core (e.g. `sh:path`, `sh:targetClass`) gets a single value, `SHACL Core` - tagging every such predicate with `SHACL 1.2 Core` too would be true but useless, since it would erase the one signal this field exists to give (which predicates are actually new-or-changed in 1.2, replacing the old blunt `**[1.2]**` tag). Multi-valued is for the two cases where a second document genuinely contributes something:
- **Widened in SHACL 1.2 Core** - the 8 predicates whose value space SHACL 1.2 widened (`sh:class`, `sh:datatype`, `sh:nodeKind`, `sh:equals`, `sh:disjoint`, `sh:lessThan`, `sh:lessThanOrEquals`, `sh:closed`) get both `SHACL Core` (where the predicate and its original form originate) and `SHACL 1.2 Core` (where the widening is defined).
- **Migrated across documents** - `sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`/`sh:condition` originate in SHACL-AF and are also now normatively part of SHACL 1.2 Rules; similarly for SPARQL Extensions and Node Expressions content that used to live in SHACL-AF. Both values apply.

Controlled vocabulary (8 values, reusing the six-document split already tracked in `docs/shacl12-gap-matrix.md`, plus the two pre-1.2 baseline specs):

| Spec | `rdfs:isDefinedBy` value |
| --- | --- |
| SHACL Core (1.0/1.1) | `<https://www.w3.org/TR/shacl/>` |
| SHACL Advanced Features (SHACL-AF, pre-1.2) | `<https://www.w3.org/TR/shacl-af/>` |
| SHACL 1.2 Core | `<https://www.w3.org/TR/shacl12-core/>` |
| SHACL 1.2 SPARQL Extensions | `<https://www.w3.org/TR/shacl12-sparql/>` |
| SHACL 1.2 Node Expressions | `<https://www.w3.org/TR/shacl12-node-expr/>` |
| SHACL 1.2 Rules | `<https://www.w3.org/TR/shacl12-rules/>` |
| SHACL 1.2 User Interfaces | `<https://www.w3.org/TR/shacl12-ui/>` |
| SHACL 1.2 Profiling | `<https://www.w3.org/TR/shacl12-profiling/>` |

## Required Engine

New `stsh:` predicate (no standard vocabulary fits an operational fact like "which validation engine implements this," unlike spec provenance) — single-valued, since `starshacl` is a strict superset of pySHACL: anything that works under plain pySHACL works under `starshacl` too, so there's never a need to tag both. Tag with the *minimum* engine required:

| Value | Meaning |
| --- | --- |
| `stsh:PySHACL` | Works under plain pySHACL (and therefore under `starshacl` too - no second tag needed). |
| `stsh:StarShacl` | Requires `starshacl` specifically - not available under vanilla pySHACL at all (e.g. most new SHACL 1.2 predicates). |

Practical purpose: this is being built as the engine for a downstream SHACL 1.2 editor project, which will consume this same `stsh:` vocabulary directly (not a copy - the namespace stays as-is here specifically so that project can reference these terms). One concrete use: filtering the full meta-shapes graph down to just the rules where `stsh:requiredEngine stsh:PySHACL`, to validate a shapes graph intended for plain-pySHACL compatibility rather than the full `starshacl` feature set.

## Groups (with suggested UI section order)

Unlike predicates, a `sh:PropertyGroup` has no validation-layer counterpart at all — it exists purely to organize form rendering, so (unlike the split above) a group's own `sh:name`/`sh:description`/`sh:order` all belong entirely in the presentation/UI file, not divided.

| # | Group | `sh:name` | `sh:order` | `sh:description` |
| --- | --- | --- | --- | --- |
| 1 | `stsh:TargetGroup` | Targeting | 1 | How a shape selects its focus nodes — `sh:targetClass`, `sh:targetNode`, and the rest of the targeting predicates. |
| 2 | `stsh:PathGroup` | Property Paths | 2 | `sh:path` and its operators (inverse, alternative, repeated) that connect a focus node to its value nodes. |
| 3 | `stsh:CardinalityGroup` | Cardinality | 3 | How many values a path may or must have — `sh:minCount`/`sh:maxCount`. |
| 4 | `stsh:ValueTypeGroup` | Value Type | 4 | What kind of RDF term or class a value node must be — `sh:class`/`sh:datatype`/`sh:nodeKind`. |
| 5 | `stsh:ValueRangeGroup` | Value Range | 5 | Numeric/ordinal bounds on a value — `sh:minInclusive` and its siblings. |
| 6 | `stsh:StringGroup` | String Constraints | 6 | Constraints on a value's string form — length, pattern, language. |
| 7 | `stsh:ValueEnumerationGroup` | Value Enumeration | 7 | Allow-listing or requiring specific values — `sh:in`/`sh:hasValue`. |
| 8 | `stsh:ComparisonGroup` | Value Comparison | 8 | Comparing one property's values against another's — `sh:equals`/`sh:disjoint`/`sh:lessThan` and siblings. |
| 9 | `stsh:CompositionGroup` | Shape Composition | 9 | Combining shapes logically or by nesting — `sh:not`/`sh:and`/`sh:or`/`sh:xone`/`sh:node`/`sh:property`. |
| 10 | `stsh:QualifiedGroup` | Qualified Value Shapes | 10 | Counting how many values conform to a shape, rather than requiring all-or-none. |
| 11 | `stsh:ClosedGroup` | Closed Shapes | 11 | Restricting a focus node to only the explicitly listed properties. |
| 12 | `stsh:ListGroup` | List Constraints **[1.2]** | 12 | Well-formedness and length/uniqueness rules for SHACL-list-valued properties. |
| 13 | `stsh:CrossNodeGroup` | Cross-Node & Reification **[1.2]** | 13 | Constraints spanning multiple focus nodes or RDF 1.2 triple-term reification. |
| 14 | `stsh:MetadataGroup` | Non-Validating Metadata | 14 | Annotation-only predicates with no effect on conformance — `sh:message`/`sh:severity`/`sh:name`/etc. |
| 15 | `stsh:RulesGroup` | Rules & SPARQL Extensions **[1.2]** | 15 | SPARQL-based constraints, user-defined constraint components, and SHACL-AF inference rules — `sh:sparql`/`sh:rule`/`sh:condition`/`sh:TripleRule`/`sh:SPARQLRule` and their supporting predicates. |
| 16 | `stsh:WidgetGroup` | SHACL 1.2 UI Widgets **[1.2]** | 16 | `shui:` vocabulary for form generation — widget/editor/viewer assignment and the built-in widget instances. Documented for training purposes; not an implemented starshacl feature. |

---

Fields below use RDF-prefixed names directly (`sh:name`, `sh:description`, `skos:example`, `rdfs:comment`, `rdfs:seeAlso`, `sh:group`, `sh:order`) rather than plain-English labels, so the mapping to actual triples is unambiguous at a glance.

## 1. Targeting

### `sh:targetClass`
- **sh:name:** target class
- **sh:description:** Every instance of this class (including subclasses, when RDFS/OWL reasoning is used) is a focus node for the shape. The most common way to attach a shape to "all things of type X."
- **skos:example:** `ex:PersonShape sh:targetClass ex:Person .`
- **rdfs:seeAlso:** `sh:targetNode`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:TargetGroup — **sh:order:** 1

### `sh:targetNode`
- **sh:name:** target node
- **sh:description:** A single, specific IRI or literal is a focus node for the shape, regardless of its type. Useful for validating one known resource directly, or in training examples where you want to point at exactly one node.
- **skos:example:** `ex:AliceShape sh:targetNode ex:alice .`
- **rdfs:comment:** Doesn't scale — for validating "all instances of a class," use `sh:targetClass` instead.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:TargetGroup — **sh:order:** 2

### `sh:targetSubjectsOf`
- **sh:name:** target subjects of
- **sh:description:** Any node that is the subject of at least one triple with this predicate becomes a focus node. A quick way to target "everything that has an `ex:email`," without needing a shared class.
- **skos:example:** `sh:targetSubjectsOf ex:email` — targets every node with at least one `ex:email` value.
- **rdfs:seeAlso:** `sh:targetObjectsOf`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:TargetGroup — **sh:order:** 3

### `sh:targetObjectsOf`
- **sh:name:** target objects of
- **sh:description:** Any node that appears as the *object* of at least one triple with this predicate becomes a focus node — the mirror image of `sh:targetSubjectsOf`.
- **skos:example:** `sh:targetObjectsOf ex:manager` — targets every node that's someone's manager.
- **rdfs:comment:** Easy to mix up with `sh:targetSubjectsOf` — subjects-of targets the thing *with* the property, objects-of targets the thing *pointed to*.
- **rdfs:seeAlso:** `sh:targetSubjectsOf`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:TargetGroup — **sh:order:** 4

## 2. Property Paths

### `sh:path`
- **sh:name:** path
- **sh:description:** Required on every property shape. Names the property more complex path expression that connects a focus node to its value nodes. The simplest form is a single IRI; SHACL also supports sequence, alternative, inverse, and repeated (`*`/`+`/`?`) paths.
- **skos:example:** `sh:path ex:email` — the simple case, a single predicate.
- **rdfs:seeAlso:** `sh:inversePath`, `sh:alternativePath`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** prop_path_expr — the general/compound case (full recursive path grammar); a plain IRI is the simple special case of this, not the reverse
- **sh:group:** stsh:PathGroup — **sh:order:** 1

### `sh:inversePath`
- **sh:name:** inverse path
- **sh:description:** Traverses a triple backwards — from object to subject — instead of the normal subject-to-object direction. Used to write constraints in terms of "things that point at me" rather than "things I point at."
- **skos:example:** `sh:path [ sh:inversePath ex:parent ]` — matches a node's children, by walking `ex:parent` triples backwards.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** prop_path_expr
- **sh:group:** stsh:PathGroup — **sh:order:** 2

### `sh:alternativePath`
- **sh:name:** alternative path
- **sh:description:** A list of paths, any one of which may match — like a logical OR over predicates. Useful when a value could arrive via one of several equivalent properties (e.g. `schema:name` or `rdfs:label`).
- **skos:example:** `sh:path [ sh:alternativePath ( schema:name rdfs:label ) ]`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** prop_path_expr
- **sh:group:** stsh:PathGroup — **sh:order:** 3

### `sh:zeroOrMorePath`
- **sh:name:** zero-or-more path
- **sh:description:** Matches the given path repeated zero or more times — the SHACL equivalent of a regular expression's `*`. Commonly used to walk a transitive hierarchy (e.g. every ancestor via `rdfs:subClassOf*`).
- **skos:example:** `sh:path [ sh:zeroOrMorePath rdfs:subClassOf ]`
- **rdfs:comment:** Zero repetitions means the *starting node itself* is included in the match set — easy to forget when counting results.
- **rdfs:seeAlso:** `sh:oneOrMorePath`, `sh:zeroOrOnePath`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** prop_path_expr
- **sh:group:** stsh:PathGroup — **sh:order:** 4

### `sh:oneOrMorePath`
- **sh:name:** one-or-more path
- **sh:description:** Matches the given path repeated one or more times — like `+` in a regular expression. Same as `sh:zeroOrMorePath` but excludes the zero-repetition (starting-node) case.
- **skos:example:** `sh:path [ sh:oneOrMorePath ex:parent ]` — every ancestor, not including the node itself.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** prop_path_expr
- **sh:group:** stsh:PathGroup — **sh:order:** 5

### `sh:zeroOrOnePath`
- **sh:name:** zero-or-one path
- **sh:description:** Matches the given path zero times (the node itself) or exactly once — like `?` in a regular expression. Useful for "this node, or its immediate parent if it has one."
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** prop_path_expr
- **sh:group:** stsh:PathGroup — **sh:order:** 6

## 3. Cardinality

### `sh:minCount`
- **sh:name:** minimum count
- **sh:description:** The minimum number of value nodes a path must have for a given focus node. `sh:minCount 1` is the standard way to express "this property is required." There is no default minimum — omitting `sh:minCount` means any number of values, including zero, is allowed.
- **skos:example:** `sh:path ex:email ; sh:minCount 1` — every focus node must have at least one `ex:email` value.
- **rdfs:comment:** A frequent mistake: writing `sh:minCount 0` to mean "optional." This is a no-op — 0 is already the default. Omit `sh:minCount` entirely for an optional property.
- **rdfs:seeAlso:** `sh:maxCount`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CardinalityGroup — **sh:order:** 1

### `sh:maxCount`
- **sh:name:** maximum count
- **sh:description:** The maximum number of value nodes a path may have for a given focus node. `sh:maxCount 1` is the standard way to express "at most one value" (a functional property).
- **skos:example:** `sh:path ex:birthDate ; sh:maxCount 1`
- **rdfs:seeAlso:** `sh:minCount`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CardinalityGroup — **sh:order:** 2

## 4. Value Type

### `sh:class`
- **sh:name:** class
- **sh:description:** Every value node must be an instance of this class (or a subclass, under RDFS/OWL reasoning). SHACL 1.2 widens this to also accept a list of classes — the value must be an instance of *at least one* of them (a union, not an intersection).
- **skos:example:** `sh:path ex:employer ; sh:class ex:Organization`
- **rdfs:comment [1.2]:** A list value here means "any of these classes," not "all of these classes" — for an intersection, nest a separate `sh:node` shape instead.
- **rdfs:seeAlso:** `sh:datatype`, `sh:nodeKind`
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain single-value form only — the SHACL 1.2 list-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ValueTypeGroup — **sh:order:** 1

### `sh:datatype`
- **sh:name:** datatype
- **sh:description:** Every value node must be a literal with this exact XSD (or other) datatype IRI. SHACL 1.2 widens this to also accept a list of datatypes (a union, same as `sh:class`).
- **skos:example:** `sh:path ex:age ; sh:datatype xsd:integer`
- **rdfs:comment:** `xsd:integer` and `xsd:int`/`xsd:decimal` are *not* the same datatype to SHACL — the match is exact, not numerically-compatible.
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain single-value form only — the SHACL 1.2 list-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ValueTypeGroup — **sh:order:** 2

### `sh:nodeKind`
- **sh:name:** node kind
- **sh:description:** Restricts what *kind* of RDF term a value node may be, independent of class or datatype: `sh:IRI`, `sh:BlankNode`, `sh:Literal`, or one of the three compound kinds (`sh:BlankNodeOrIRI`, `sh:BlankNodeOrLiteral`, `sh:IRIOrLiteral`). SHACL 1.2 widens this to also accept a list of node kinds.
- **skos:example:** `sh:path ex:homepage ; sh:nodeKind sh:IRI` — the value must be a real IRI, not a literal string.
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain single-value form only — the SHACL 1.2 list-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ValueTypeGroup — **sh:order:** 3

### `sh:rootClass` **[1.2]**
- **sh:name:** root class
- **sh:description:** Every value node must be an IRI that is, or is a transitive `rdfs:subClassOf` subclass of, this class - like `sh:class` but subclass-aware without needing full RDFS/OWL reasoning enabled. Not a targeting mechanism (despite the similar name to implicit class-based targeting) - it constrains a property's *value nodes*, the same role as `sh:class`/`sh:datatype`/`sh:nodeKind`.
- **skos:example:** `sh:path ex:worksFor ; sh:rootClass ex:Organization` — the value must be `ex:Organization` itself or a transitive subclass of it.
- **rdfs:seeAlso:** `sh:class`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:ValueTypeGroup — **sh:order:** 4

## 5. Value Range

### `sh:minInclusive`
- **sh:name:** minimum inclusive value
- **sh:description:** Every value node must be numerically or ordinally ≥ this value. Requires an orderable datatype (numbers, dates).
- **skos:example:** `sh:path ex:age ; sh:minInclusive 0`
- **rdfs:seeAlso:** `sh:minExclusive`, `sh:maxInclusive`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ValueRangeGroup — **sh:order:** 1

### `sh:minExclusive`
- **sh:name:** minimum exclusive value
- **sh:description:** Every value node must be strictly greater than this value (boundary itself not allowed).
- **skos:example:** `sh:path ex:temperature ; sh:minExclusive 0` — must be above absolute freezing on some scale, never equal to it.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ValueRangeGroup — **sh:order:** 2

### `sh:maxInclusive`
- **sh:name:** maximum inclusive value
- **sh:description:** Every value node must be numerically or ordinally ≤ this value.
- **skos:example:** `sh:path ex:percentage ; sh:maxInclusive 100`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ValueRangeGroup — **sh:order:** 3

### `sh:maxExclusive`
- **sh:name:** maximum exclusive value
- **sh:description:** Every value node must be strictly less than this value.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ValueRangeGroup — **sh:order:** 4

## 6. String Constraints

### `sh:minLength`
- **sh:name:** minimum length
- **sh:description:** The string form of every value node must have at least this many characters. Applies to both literals and IRIs (an IRI's length is measured too).
- **skos:example:** `sh:path ex:username ; sh:minLength 3`
- **rdfs:seeAlso:** `sh:maxLength`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:StringGroup — **sh:order:** 1

### `sh:maxLength`
- **sh:name:** maximum length
- **sh:description:** The string form of every value node must have at most this many characters.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:StringGroup — **sh:order:** 2

### `sh:pattern`
- **sh:name:** pattern
- **sh:description:** Every value node's string form must match this regular expression (XPath/XSD regex syntax, not PCRE — mostly compatible, but check character class and anchoring differences for anything nontrivial).
- **skos:example:** `sh:path ex:productCode ; sh:pattern "^[A-Z]{3}-[0-9]{4}$"`
- **rdfs:comment:** SHACL patterns are *not* implicitly anchored — `sh:pattern "abc"` matches a value that merely *contains* "abc" anywhere, not one that equals it. Use `^...$` explicitly for a full-string match.
- **rdfs:seeAlso:** `sh:flags`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:StringGroup — **sh:order:** 3

### `sh:flags`
- **sh:name:** flags
- **sh:description:** Regex flags to apply alongside `sh:pattern` (e.g. `"i"` for case-insensitive). Has no effect without a `sh:pattern` on the same shape.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:StringGroup — **sh:order:** 4

### `sh:languageIn`
- **sh:name:** language in
- **sh:description:** Every value node must be a language-tagged literal (or `rdf:dirLangString` under RDF 1.2) whose language tag is in this list. A plain literal with no language tag never matches.
- **skos:example:** `sh:path ex:label ; sh:languageIn ( "en" "en-US" "fr" )`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL (plain literals only — `rdf:dirLangString` recognition requires stsh:StarShacl)
- **sh:group:** stsh:StringGroup — **sh:order:** 5

### `sh:uniqueLang`
- **sh:name:** unique language
- **sh:description:** When true, at most one value node may use each language tag — prevents two `"Hello"@en` values on the same focus node, without restricting which languages are used at all. SHACL 1.2 extends the uniqueness condition to also consider base direction for `rdf:dirLangString` values (`"1"@ar--rtl` and `"1"@ar--ltr` are different, as is the pair `"1"@ar--rtl` and `"1"@ar`).
- **skos:example:** `sh:path ex:label ; sh:uniqueLang true`
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain language-tag uniqueness only — `rdf:dirLangString` direction-awareness requires stsh:StarShacl)
- **sh:group:** stsh:StringGroup — **sh:order:** 6

### `sh:singleLine` **[1.2]**
- **sh:name:** single line
- **sh:description:** When true, every value node's string form must not contain a line break — a lightweight way to reject accidentally-pasted multi-paragraph text in a field meant to hold a short label.
- **skos:example:** `sh:path ex:title ; sh:singleLine true`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:StringGroup — **sh:order:** 7

## 7. Value Enumeration

### `sh:in`
- **sh:name:** in
- **sh:description:** Every value node must be exactly one of the members of this list — an enumeration/allow-list constraint.
- **skos:example:** `sh:path ex:status ; sh:in ( "active" "inactive" "pending" )`
- **rdfs:comment:** List membership is exact-value matching, including datatype — `sh:in (1 2 3)` (integers) will not match the string `"1"`.
- **rdfs:seeAlso:** `sh:hasValue`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ValueEnumerationGroup — **sh:order:** 1

### `sh:hasValue`
- **sh:name:** has value
- **sh:description:** At least one value node must equal exactly this one specific value — the opposite granularity from `sh:in` (one required value, rather than a list of allowed ones).
- **skos:example:** `sh:path rdf:type ; sh:hasValue ex:Person` — requires the focus node to be typed `ex:Person` (among possibly other types).
- **rdfs:seeAlso:** `sh:in`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ValueEnumerationGroup — **sh:order:** 2

## 8. Value Comparison

### `sh:equals`
- **sh:name:** equals
- **sh:description:** The set of value nodes at this shape's path must be exactly equal (as a set) to the set of value nodes at the given path or property. SHACL 1.2 widens the object from a plain IRI to any property path.
- **skos:example:** `sh:path ex:homeAddress ; sh:equals ex:mailingAddress`
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain-IRI object only — the SHACL 1.2 path-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ComparisonGroup — **sh:order:** 1

### `sh:disjoint`
- **sh:name:** disjoint
- **sh:description:** The set of value nodes at this shape's path must share *no* members with the set of value nodes at the given path. SHACL 1.2 widens the object to any property path.
- **skos:example:** `sh:path ex:blockedUsers ; sh:disjoint ex:friends` — a user can't be both blocked and a friend.
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain-IRI object only — the SHACL 1.2 path-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ComparisonGroup — **sh:order:** 2

### `sh:lessThan`
- **sh:name:** less than
- **sh:description:** Every value node at this shape's path must be strictly less than every value node at the given path, for the same focus node. Requires an orderable datatype. SHACL 1.2 widens the object to any property path.
- **skos:example:** `sh:path ex:startDate ; sh:lessThan ex:endDate`
- **rdfs:seeAlso:** `sh:lessThanOrEquals`
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain-IRI object only — the SHACL 1.2 path-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ComparisonGroup — **sh:order:** 3

### `sh:lessThanOrEquals`
- **sh:name:** less than or equal to
- **sh:description:** Same as `sh:lessThan`, but allows equality. SHACL 1.2 widens the object to any property path.
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain-IRI object only — the SHACL 1.2 path-valued form requires stsh:StarShacl)
- **sh:group:** stsh:ComparisonGroup — **sh:order:** 4

### `sh:subsetOf` **[1.2]**
- **sh:name:** subset of
- **sh:description:** The set of value nodes at this shape's path must be a subset of the set of value nodes at the given path — every value here must also appear there, but not vice versa.
- **skos:example:** `sh:path ex:selectedTags ; sh:subsetOf ex:availableTags`
- **rdfs:seeAlso:** `sh:equals`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:ComparisonGroup — **sh:order:** 5

## 9. Shape Composition

### `sh:not`
- **sh:name:** not
- **sh:description:** A value node conforms only if it does *not* conform to the given shape — logical negation. A common way to express "must not be of this type" or "must not match this pattern."
- **skos:example:** `sh:not [ sh:hasValue ex:Deleted ]`
- **rdfs:comment:** Negating a shape with its own violations can be confusing to debug — the validation report shows that `sh:not`'s inner shape *did* conform (which is why the outer shape failed), which reads backwards at first glance.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CompositionGroup — **sh:order:** 1

### `sh:and`
- **sh:name:** and
- **sh:description:** A value node must conform to every shape in this list — logical conjunction. Rarely needed for simple cases (a single node shape's own constraints are already implicitly ANDed), but useful for combining reusable shape fragments.
- **skos:example:** `sh:and ( ex:HasNameShape ex:HasEmailShape )`
- **rdfs:seeAlso:** `sh:or`, `sh:xone`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CompositionGroup — **sh:order:** 2

### `sh:or`
- **sh:name:** or
- **sh:description:** A value node must conform to at least one shape in this list — logical disjunction. Commonly used to allow a value to be one of several alternative shapes (e.g. either an IRI reference or an inline literal).
- **skos:example:** `sh:or ( [ sh:datatype xsd:string ] [ sh:datatype xsd:integer ] )`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CompositionGroup — **sh:order:** 3

### `sh:xone`
- **sh:name:** exactly one
- **sh:description:** A value node must conform to *exactly one* shape in this list — not zero, not two or more. Stricter than `sh:or`, useful when alternatives are meant to be mutually exclusive.
- **skos:example:** `sh:xone ( ex:IndividualShape ex:OrganizationShape )` — a party is one or the other, never both.
- **rdfs:comment:** If two shapes in the list overlap (a value could satisfy both), a value that matches both fails `sh:xone` even though it would pass `sh:or` — easy to trip over when shapes aren't as mutually exclusive as intended.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CompositionGroup — **sh:order:** 4

### `sh:node`
- **sh:name:** node
- **sh:description:** Every value node must conform to the given (node) shape. The main way to nest shapes — validating the *shape* of a related resource, not just a scalar constraint on it.
- **skos:example:** `sh:path ex:address ; sh:node ex:AddressShape`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CompositionGroup — **sh:order:** 5

### `sh:property`
- **sh:name:** property
- **sh:description:** Attaches a property shape to a node shape. Nearly every real-world shape uses this — it's how a node shape says "and also, here's a constraint on one of my properties."
- **skos:example:** `ex:PersonShape sh:property [ sh:path ex:email ; sh:minCount 1 ]`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:CompositionGroup — **sh:order:** 6

### `sh:someValue` **[1.2]**
- **sh:name:** some value
- **sh:description:** At least one value node must conform to the given shape. Unlike `sh:node` (which requires *every* value node to conform), a single non-conforming value here is not itself a violation — only the absence of *any* conforming value is.
- **skos:example:** `sh:path ex:contactMethod ; sh:someValue [ sh:datatype xsd:anyURI ]` — at least one contact method must be a URI, others can be anything.
- **rdfs:seeAlso:** `sh:node`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:CompositionGroup — **sh:order:** 7

### `sh:memberShape` **[1.2]**
- **sh:name:** member shape
- **sh:description:** The value node must be a well-formed SHACL list, and every member of that list must conform to the given shape. Combines list-well-formedness checking with per-member validation in one predicate.
- **skos:example:** `sh:path ex:tags ; sh:memberShape [ sh:datatype xsd:string ]`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:CompositionGroup — **sh:order:** 8

## 10. Qualified Value Shapes

### `sh:qualifiedValueShape`
- **sh:name:** qualified value shape
- **sh:description:** Works together with `sh:qualifiedMinCount`/`sh:qualifiedMaxCount` to count *how many* value nodes conform to a given shape (rather than requiring all or none to conform, like `sh:node` does).
- **skos:example:** `sh:path ex:contact ; sh:qualifiedValueShape ex:PhoneShape ; sh:qualifiedMinCount 1`
- **rdfs:seeAlso:** `sh:qualifiedMinCount`, `sh:qualifiedMaxCount`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:QualifiedGroup — **sh:order:** 1

### `sh:qualifiedMinCount`
- **sh:name:** qualified minimum count
- **sh:description:** The minimum number of value nodes that must conform to the sibling `sh:qualifiedValueShape`.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:QualifiedGroup — **sh:order:** 2

### `sh:qualifiedMaxCount`
- **sh:name:** qualified maximum count
- **sh:description:** The maximum number of value nodes that may conform to the sibling `sh:qualifiedValueShape`.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:QualifiedGroup — **sh:order:** 3

### `sh:qualifiedValueShapesDisjoint`
- **sh:name:** qualified value shapes disjoint
- **sh:description:** When true, a value node counted toward *this* qualified shape's count is excluded from counting toward any sibling qualified shape on the same property shape — prevents one value from double-counting across two overlapping qualified constraints.
- **rdfs:comment:** Only affects counting against *sibling* qualified shapes on the same `sh:property` blank node list — it has no effect with only one `sh:qualifiedValueShape` present.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:QualifiedGroup — **sh:order:** 4

## 11. Closed Shapes

### `sh:closed`
- **sh:name:** closed
- **sh:description:** When true, a conforming focus node may only have values for paths explicitly listed via `sh:property` (plus anything in `sh:ignoredProperties`) — any other property present is a violation. SHACL 1.2 adds `sh:ByTypes`, which closes the shape per-`rdf:type` rather than universally, useful when a class hierarchy adds properties incrementally.
- **skos:example:** `ex:PersonShape sh:closed true ; sh:property [ sh:path ex:name ] .` — `ex:Person` nodes may *only* have `ex:name` (and `rdf:type`).
- **rdfs:comment:** `rdf:type` is always implicitly allowed on a closed shape. `sh:ignoredProperties` is needed to permit other "bookkeeping" properties (e.g. `dcterms:created`) without listing each as `sh:property`.
- **rdfs:seeAlso:** `sh:ignoredProperties`
- **rdfs:isDefinedBy:** SHACL Core, SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:PySHACL (plain `xsd:boolean` value only — `sh:closed sh:ByTypes` requires stsh:StarShacl)
- **sh:group:** stsh:ClosedGroup — **sh:order:** 1

### `sh:ignoredProperties`
- **sh:name:** ignored properties
- **sh:description:** A list of properties exempted from `sh:closed`'s restriction — present without needing a matching `sh:property` entry.
- **skos:example:** `sh:ignoredProperties ( rdf:type dcterms:created )`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:ClosedGroup — **sh:order:** 2

## 12. List Constraints **[1.2]**

### `sh:minListLength`
- **sh:name:** minimum list length
- **sh:description:** The value node must be a well-formed SHACL list with at least this many members.
- **skos:example:** `sh:path ex:coordinates ; sh:minListLength 2`
- **rdfs:seeAlso:** `sh:maxListLength`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:ListGroup — **sh:order:** 1

### `sh:maxListLength`
- **sh:name:** maximum list length
- **sh:description:** The value node must be a well-formed SHACL list with at most this many members.
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:ListGroup — **sh:order:** 2

### `sh:uniqueMembers`
- **sh:name:** unique members
- **sh:description:** When true, the value node must be a well-formed SHACL list with no duplicate members (by RDF term equality).
- **skos:example:** `sh:path ex:coordinates ; sh:uniqueMembers true`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:ListGroup — **sh:order:** 3

## 13. Cross-Node & Reification **[1.2]**

### `sh:uniqueValuesFor`
- **sh:name:** unique values for
- **sh:description:** Requires that the values reached via the given path (or list of paths) are unique *across every focus node* the shape applies to — not just within one focus node, like `sh:uniqueLang`/`sh:uniqueMembers` are. The classic use is enforcing a unique key (e.g. no two people share a username).
- **skos:example:** `ex:PersonShape sh:targetClass ex:Person ; sh:uniqueValuesFor ex:username .`
- **rdfs:comment:** Because this checks *across* focus nodes rather than within one, it needs the *entire* batch of candidate focus nodes evaluated together — composing it inside `sh:and`/`sh:or`/`sh:not`/`sh:node`/`sh:qualifiedValueShape` requires special handling to still see the full batch (which starshacl's native components provide — see `docs/shacl12-gap-matrix.md`).
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:CrossNodeGroup — **sh:order:** 1

### `sh:reifierShape`
- **sh:name:** reifier shape
- **sh:description:** Requires that the reifier of a triple term (the node connected to it via `rdf:reifies`) conforms to the given shape — a way to put constraints on the metadata *about* a statement, not just the statement's own subject/predicate/object.
- **skos:example:** `sh:path ex:claims ; sh:reifierShape [ sh:property [ sh:path ex:confidence ; sh:minCount 1 ] ]` — every reifier of a claim must carry a confidence score.
- **rdfs:seeAlso:** `sh:reificationRequired`
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:CrossNodeGroup — **sh:order:** 2

### `sh:reificationRequired`
- **sh:name:** reification required
- **sh:description:** When true, every triple term reached by the shape's path must actually have at least one reifier in the data — not just be well-formed, but be genuinely annotated/reified somewhere.
- **rdfs:isDefinedBy:** SHACL 1.2 Core
- **stsh:requiredEngine:** stsh:StarShacl
- **sh:group:** stsh:CrossNodeGroup — **sh:order:** 3

## 14. Non-Validating Metadata

### `sh:message`
- **sh:name:** message
- **sh:description:** A human-readable explanation shown in the validation report when this shape is violated. Can use `{$this}`, `{?path}`, and similar placeholders that get filled in per-violation. Purely informational — has no effect on whether the shape conforms.
- **skos:example:** `sh:message "Age must be a non-negative integer."@en`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 1

### `sh:severity`
- **sh:name:** severity
- **sh:description:** How seriously to treat a violation of this shape: `sh:Violation` (default — fails conformance), `sh:Warning`, or `sh:Info` (both reported but don't fail conformance). Useful for phasing in stricter rules without breaking existing data immediately.
- **skos:example:** `sh:severity sh:Warning`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 2

### `sh:deactivated`
- **sh:name:** deactivated
- **sh:description:** When true, this shape is skipped entirely during validation — as if it weren't there. Useful for temporarily disabling a rule without deleting it, e.g. while a training exercise focuses on a different constraint.
- **skos:example:** `sh:deactivated true`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 3

### `sh:name`
- **sh:name:** name
- **sh:description:** A short, human-readable label for a shape — this exact same annotation property is what this presentation file itself uses for every predicate's display label.
- **skos:example:** `sh:name "email address"@en`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 4

### `sh:description`
- **sh:name:** description
- **sh:description:** A longer human-readable explanation of a shape's purpose — again, the same property this file uses for every predicate's own description.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 5

### `sh:order`
- **sh:name:** order
- **sh:description:** A number suggesting where a property shape should appear relative to its siblings when a UI renders a form — lower numbers first. Purely a rendering hint.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 6

### `sh:group`
- **sh:name:** group
- **sh:description:** Links a property shape to a `sh:PropertyGroup`, letting a UI cluster related fields into named sections — exactly how this presentation file's own groups (Targeting, Cardinality, etc.) work.
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 7

### `sh:defaultValue`
- **sh:name:** default value
- **sh:description:** A suggested default value for a property shape, for a UI to pre-fill when creating a new instance. Purely informational — has no effect on validation.
- **skos:example:** `sh:path ex:status ; sh:defaultValue "pending"`
- **rdfs:isDefinedBy:** SHACL Core
- **stsh:requiredEngine:** stsh:PySHACL
- **sh:group:** stsh:MetadataGroup — **sh:order:** 8

## 15. Rules & SPARQL Extensions **[1.2]**

*Scope note: this covers the confirmed, tested subset (SHACL 1.2 SPARQL Extensions + Rules docs) — `sh:declare`/`sh:prefix`/`sh:namespace`/`sh:prefixes` (explicit prefix-declaration sets) and `sh:resultAnnotation`/`sh:annotationProperty`/`sh:annotationVarName`/`sh:annotationValue` remain out of scope, still unverified per `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred" table.*

### `sh:sparql`
- **sh:name:** SPARQL constraint
- **sh:description:** Attaches a SPARQL-based constraint to a shape — the query is evaluated once per focus node, and any result row it returns is treated as a violation.
- **skos:example:** `sh:sparql [ sh:select "SELECT $this WHERE { FILTER NOT EXISTS { $this ex:email ?e } }" ]`
- **rdfs:comment:** The query must project `$this` (or `?this`); `MINUS` and `VALUES` against pre-bound variables are disallowed per spec.
- **rdfs:seeAlso:** `sh:select`, `sh:ConstraintComponent`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — resolves to a nested SPARQLConstraint shape (stsh:SelectValidatorShape), an open-ended structure
- **sh:group:** stsh:RulesGroup — **sh:order:** 1

### `sh:select`
- **sh:name:** SELECT query
- **sh:description:** The SPARQL SELECT query text for a `sh:sparql` constraint or a custom `sh:ConstraintComponent`'s `sh:nodeValidator`/`sh:propertyValidator`. Any row returned counts as a violation; bindings for `?value`/`?path`/`?this` in the result customize the reported focus/value/path.
- **skos:example:** `sh:select "SELECT $this ?value WHERE { ?value ex:score ?s . FILTER (?s < 0) }"`
- **rdfs:seeAlso:** `sh:sparql`, `sh:ask`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** multiline — confirmed sh:datatype xsd:string (plain, not language-tagged) in the validation shapes
- **sh:group:** stsh:RulesGroup — **sh:order:** 2

### `sh:ask`
- **sh:name:** ASK query
- **sh:description:** The SPARQL ASK query text for a custom `sh:ConstraintComponent`'s generic `sh:validator`. The value node conforms only if the query returns `true`.
- **skos:example:** `sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK { FILTER (?value >= ?minScore) }" ]`
- **rdfs:comment:** Unlike `sh:select`, `false` means *violation* here — the query must return `true` for conformance, the opposite polarity from a SELECT constraint's "any row is a violation."
- **rdfs:seeAlso:** `sh:select`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** multiline — confirmed sh:datatype xsd:string in the validation shapes
- **sh:group:** stsh:RulesGroup — **sh:order:** 3

### `sh:ConstraintComponent`
- **sh:name:** constraint component
- **sh:description:** Declares a reusable, user-defined SHACL constraint type, similar to a built-in one like `sh:minCount`. Combines one or more `sh:parameter` declarations with a `sh:validator` (or `sh:nodeValidator`/`sh:propertyValidator`) that implements the check.
- **skos:example:** `ex:MinScoreConstraintComponent a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minScore ] ; sh:validator [ a sh:SPARQLAskValidator ; sh:ask "..." ]`
- **rdfs:comment:** Requires at least one non-optional `sh:parameter` — a component with only optional parameters fails to load.
- **rdfs:seeAlso:** `sh:parameter`, `sh:validator`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — a component definition (sh:parameter list + a validator), open-ended nested content, not a leaf value
- **sh:group:** stsh:RulesGroup — **sh:order:** 4

### `sh:parameter`
- **sh:name:** parameter
- **sh:description:** Declares one input parameter of a custom `sh:ConstraintComponent` — the parameter's own `sh:path` becomes the predicate a shape uses to supply that argument's value (e.g. `ex:minScore` in the example above).
- **skos:example:** `sh:parameter [ sh:path ex:minScore ; sh:optional false ]`
- **rdfs:seeAlso:** `sh:ConstraintComponent`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — each parameter is a nested blank node with its own sh:path
- **sh:group:** stsh:RulesGroup — **sh:order:** 5

### `sh:validator`
- **sh:name:** validator
- **sh:description:** The generic SPARQL ASK validator for a custom `sh:ConstraintComponent`, used when the component doesn't need to distinguish node vs. property shapes.
- **rdfs:seeAlso:** `sh:nodeValidator`, `sh:propertyValidator`, `sh:ask`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — resolves to a nested stsh:AskValidatorShape
- **sh:group:** stsh:RulesGroup — **sh:order:** 6

### `sh:nodeValidator`
- **sh:name:** node validator
- **sh:description:** A SELECT-based validator for a custom `sh:ConstraintComponent`, used specifically when the component is applied via a node shape.
- **rdfs:seeAlso:** `sh:propertyValidator`, `sh:select`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — resolves to a nested stsh:SelectValidatorShape
- **sh:group:** stsh:RulesGroup — **sh:order:** 7

### `sh:propertyValidator`
- **sh:name:** property validator
- **sh:description:** A SELECT-based validator for a custom `sh:ConstraintComponent`, used specifically when the component is applied via a property shape.
- **rdfs:seeAlso:** `sh:nodeValidator`, `sh:select`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 SPARQL Extensions
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — resolves to a nested stsh:SelectValidatorShape
- **sh:group:** stsh:RulesGroup — **sh:order:** 8

### `sh:rule`
- **sh:name:** rule
- **sh:description:** Attaches a SHACL-AF inference rule to a shape, applied to every focus node the shape targets when rule execution (not plain validation) is requested. `sh:TripleRule` and `sh:SPARQLRule` are the two concrete rule types.
- **skos:example:** `ex:R sh:rule [ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:derived ; sh:object [ sh:path ex:source ] ]`
- **rdfs:seeAlso:** `sh:TripleRule`, `sh:SPARQLRule`, `sh:condition`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — resolves to a nested stsh:RuleShape (sh:TripleRule or sh:SPARQLRule)
- **sh:group:** stsh:RulesGroup — **sh:order:** 9

### `sh:condition`
- **sh:name:** condition
- **sh:description:** Restricts which focus nodes a rule actually applies to — only nodes conforming to the given shape have the rule run for them; every other focus node is skipped entirely for that rule.
- **skos:example:** `sh:rule [ a sh:TripleRule ; sh:condition ex:AdultShape ; ... ]`
- **rdfs:comment:** The condition shape needs a real constraint to be discriminating — a shape with only a target predicate (e.g. `sh:targetClass`) trivially "conforms" for any node when checked ad hoc, since targeting doesn't itself constrain anything.
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — resolves to a nested shape (or list of shapes) restricting which focus nodes the rule applies to
- **sh:group:** stsh:RulesGroup — **sh:order:** 10

### `sh:TripleRule`
- **sh:name:** triple rule
- **sh:description:** A rule type that derives one new triple per matching focus node from three independently-evaluated node expressions — `sh:subject`/`sh:predicate`/`sh:object` — without needing any SPARQL.
- **skos:example:** `[ a sh:TripleRule ; sh:subject sh:this ; sh:predicate ex:ancestor ; sh:object [ sh:path ex:parent ] ]`
- **rdfs:seeAlso:** `sh:SPARQLRule`, `sh:subject`, `sh:predicate`, `sh:object`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — a class marker on a rule node that itself carries sh:subject/sh:predicate/sh:object, open-ended nested content
- **sh:group:** stsh:RulesGroup — **sh:order:** 11

### `sh:SPARQLRule`
- **sh:name:** SPARQL rule
- **sh:description:** A rule type that derives new triples via an arbitrary SPARQL CONSTRUCT query (`sh:construct`), for derivations too complex for a single `sh:TripleRule`.
- **skos:example:** `[ a sh:SPARQLRule ; sh:construct "CONSTRUCT { $this ex:ancestor ?a } WHERE { $this ex:parent+ ?a }" ]`
- **rdfs:seeAlso:** `sh:TripleRule`, `sh:construct`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — a class marker on a rule node that itself carries sh:construct (query text), open-ended nested content
- **sh:group:** stsh:RulesGroup — **sh:order:** 12

### `sh:construct`
- **sh:name:** CONSTRUCT query
- **sh:description:** The SPARQL CONSTRUCT query text for a `sh:SPARQLRule` — its WHERE clause is evaluated once per matching focus node (bound to `$this`), and every triple in its result is added to the data graph.
- **skos:example:** `sh:construct "PREFIX ex: <http://example.org/> CONSTRUCT { $this ex:ancestor ?a } WHERE { $this ex:parent ?a }"`
- **rdfs:seeAlso:** `sh:SPARQLRule`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** multiline — confirmed sh:datatype xsd:string in the validation shapes
- **sh:group:** stsh:RulesGroup — **sh:order:** 13

### `sh:subject`
- **sh:name:** subject expression
- **sh:description:** The node expression producing the subject of the triple a `sh:TripleRule` derives — most commonly just `sh:this`, the rule's own focus node.
- **rdfs:seeAlso:** `sh:TripleRule`, `sh:predicate`, `sh:object`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — confirmed sh:node stsh:NodeExpressionShape in the validation shapes, a potentially-recursive node expression, not guaranteed a plain term
- **sh:group:** stsh:RulesGroup — **sh:order:** 14

### `sh:predicate`
- **sh:name:** predicate expression
- **sh:description:** The node expression producing the predicate of the triple a `sh:TripleRule` derives — typically a constant IRI naming the derived property.
- **rdfs:seeAlso:** `sh:TripleRule`, `sh:subject`, `sh:object`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — confirmed sh:node stsh:NodeExpressionShape in the validation shapes, a potentially-recursive node expression, not guaranteed a plain term
- **sh:group:** stsh:RulesGroup — **sh:order:** 15

### `sh:object`
- **sh:name:** object expression
- **sh:description:** The node expression producing the object of the triple a `sh:TripleRule` derives — often a `shnex:pathValues`/`sh:path` expression pulling a value from elsewhere in the data.
- **rdfs:seeAlso:** `sh:TripleRule`, `sh:subject`, `sh:predicate`
- **rdfs:isDefinedBy:** SHACL-AF, SHACL 1.2 Rules
- **stsh:requiredEngine:** stsh:PySHACL
- **stsh:widgetType:** inline_shape — confirmed sh:node stsh:NodeExpressionShape in the validation shapes, a potentially-recursive node expression, not guaranteed a plain term
- **sh:group:** stsh:RulesGroup — **sh:order:** 16

## 16. SHACL 1.2 UI Widgets **[1.2]**

*Scope note: `shui:` (`http://www.w3.org/ns/shacl-ui#`) is a separate vocabulary from `sh:`, confirmed compatible with starshacl's engine (annotations pass through harmlessly) but not implemented as a feature — this documents the vocabulary for training purposes only. The `shui:WidgetScore`/`shui:WidgetAcceptMatcher` selection-algorithm machinery itself remains out of scope (see `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred") - its exact property definitions weren't verifiable with confidence, so no entries for `shui:score`/`shui:dataGraphShape`/`shui:shapesGraphShape` are included below.*

### `shui:editor`
- **sh:name:** editor widget
- **sh:description:** Suggests which widget a form-generating UI should use to *edit* this property shape's values — one of the built-in editors below, or a custom one.
- **skos:example:** `sh:property [ sh:path ex:birthDate ; shui:editor shui:DatePickerEditor ]`
- **rdfs:seeAlso:** `shui:viewer`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 1

### `shui:viewer`
- **sh:name:** viewer widget
- **sh:description:** Suggests which widget a UI should use to *display* (read-only) this property shape's values, as opposed to editing them.
- **skos:example:** `sh:property [ sh:path ex:homepage ; shui:viewer shui:HyperlinkViewer ]`
- **rdfs:seeAlso:** `shui:editor`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 2

### `shui:propertyRole`
- **sh:name:** property role
- **sh:description:** Marks a property shape as playing a special semantic role for UI purposes — currently just `shui:LabelRole`, marking "this is the property whose value should be used as the resource's own display label."
- **skos:example:** `sh:property [ sh:path ex:name ; shui:propertyRole shui:LabelRole ]`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 3

### `shui:TextFieldEditor`
- **sh:name:** text field
- **sh:description:** A single-line plain-text input.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 4

### `shui:TextFieldWithLangEditor`
- **sh:name:** text field with language
- **sh:description:** A single-line text input paired with a language-tag selector, for editing one language-tagged literal.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 5

### `shui:TextAreaEditor`
- **sh:name:** text area
- **sh:description:** A multi-line plain-text input.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 6

### `shui:TextAreaWithLangEditor`
- **sh:name:** text area with language
- **sh:description:** A multi-line text input paired with a language-tag selector.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 7

### `shui:RichTextEditor`
- **sh:name:** rich text editor
- **sh:description:** A formatted (e.g. HTML/Markdown) text editor, for values meant to render with styling.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 8

### `shui:NumberFieldEditor`
- **sh:name:** number field
- **sh:description:** A numeric input, for `xsd:integer`/`xsd:decimal`/`xsd:double`-typed values.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 9

### `shui:BooleanEditor`
- **sh:name:** boolean editor
- **sh:description:** A checkbox or toggle, for `xsd:boolean`-typed values.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 10

### `shui:DatePickerEditor`
- **sh:name:** date picker
- **sh:description:** A calendar-style date picker, for `xsd:date`-typed values.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 11

### `shui:DateTimePickerEditor`
- **sh:name:** date-time picker
- **sh:description:** A calendar-and-time picker, for `xsd:dateTime`-typed values.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 12

### `shui:IRIEditor`
- **sh:name:** IRI editor
- **sh:description:** A plain-text input constrained to well-formed IRIs.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 13

### `shui:AutoCompleteEditor`
- **sh:name:** autocomplete editor
- **sh:description:** A text input with suggestions, typically backed by `shui:resourceFilter`-style search against existing resources.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 14

### `shui:EnumSelectEditor`
- **sh:name:** enum select
- **sh:description:** A dropdown/select list, for a value constrained by `sh:in` to a fixed set of options.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 15

### `shui:InstancesSelectEditor`
- **sh:name:** instances select
- **sh:description:** A dropdown/select list populated dynamically from existing instances of a class, rather than a fixed `sh:in` list.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 16

### `shui:SubClassEditor`
- **sh:name:** subclass editor
- **sh:description:** A class picker constrained to subclasses of a given root class — the editor-side counterpart to `sh:rootClass`.
- **rdfs:seeAlso:** `sh:rootClass`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 17

### `shui:BlankNodeEditor`
- **sh:name:** blank node editor
- **sh:description:** A nested sub-form for editing a blank-node-valued property in place, rather than as a reference.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 18

### `shui:DetailsEditor`
- **sh:name:** details editor
- **sh:description:** An expandable/collapsible nested editor for a complex (typically shape-constrained) value.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 19

### `shui:LiteralViewer`
- **sh:name:** literal viewer
- **sh:description:** Plain read-only display of a literal value's lexical form.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 20

### `shui:LangStringViewer`
- **sh:name:** language string viewer
- **sh:description:** Read-only display of a language-tagged literal, typically showing the language tag alongside the text.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 21

### `shui:HTMLViewer`
- **sh:name:** HTML viewer
- **sh:description:** Renders a value's content as formatted HTML rather than as plain escaped text.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 22

### `shui:IRIViewer`
- **sh:name:** IRI viewer
- **sh:description:** Read-only display of an IRI value, typically abbreviated with a known prefix.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 23

### `shui:HyperlinkViewer`
- **sh:name:** hyperlink viewer
- **sh:description:** Displays an IRI value as a clickable link.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 24

### `shui:ImageViewer`
- **sh:name:** image viewer
- **sh:description:** Renders an IRI value inline as an image, for properties known to point at image resources.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 25

### `shui:LabelViewer`
- **sh:name:** label viewer
- **sh:description:** Displays a resource by its resolved human-readable label (e.g. via `shui:LabelRole`/`shui:displayProvider`) rather than its raw IRI.
- **rdfs:seeAlso:** `shui:propertyRole`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 26

### `shui:BlankNodeViewer`
- **sh:name:** blank node viewer
- **sh:description:** Read-only nested display of a blank-node-valued property's own properties.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 27

### `shui:DetailsViewer`
- **sh:name:** details viewer
- **sh:description:** An expandable/collapsible read-only view for a complex value, the viewer counterpart to `shui:DetailsEditor`.
- **rdfs:seeAlso:** `shui:DetailsEditor`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 28

### `shui:ValueTableViewer`
- **sh:name:** value table viewer
- **sh:description:** Displays multiple values for a property as rows of a table, rather than a simple list.
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 29

### `shui:LabelRole`
- **sh:name:** label role
- **sh:description:** The one built-in `shui:propertyRole` value — marks a property shape's values as the resource's own display label.
- **rdfs:seeAlso:** `shui:propertyRole`
- **rdfs:isDefinedBy:** SHACL 1.2 User Interfaces
- **stsh:requiredEngine:** stsh:StarShacl (annotation passes through inertly — not an implemented starshacl feature; see Scope note above)
- **sh:group:** stsh:WidgetGroup — **sh:order:** 30

## 17. Form-Field Membership (NodeShape vs PropertyShape)

*Added 2026-08-15. A NodeShape and a PropertyShape don't accept the same set of predicates — an
editor rendering a shape's form needs to know, per predicate, whether it belongs on a NodeShape
form, a PropertyShape form, both, or neither. `stsh:nodeFormField`/`stsh:propertyFormField` (see
"Field → RDF mapping" above) answer exactly that, declared in bulk in `shacl12-presentation-shapes.ttl`'s
"Form-field membership" section rather than repeated per predicate-entry above.*

**Evidence, not guesswork.** Rather than inventing a restriction list from scratch, this was checked
against two authoritative sources, in priority order:

1. **The official SHACL 1.2 WG draft's own meta-shapes**, vendored at
   `tests/vendor/shacl12-vocabularies/shacl-shacl.ttl`. Its `shsh:ShapeShape` targets both `sh:NodeShape`
   and `sh:PropertyShape` and lists the predicates valid on either via `sh:targetSubjectsOf`; its
   `shsh:NodeShapeShape` explicitly forbids (`sh:maxCount 0`) `sh:path`, `sh:lessThan`,
   `sh:lessThanOrEquals`, `sh:maxCount`, `sh:minCount`, `sh:qualifiedValueShape`, `sh:uniqueLang` on a
   NodeShape specifically (i.e. PropertyShape-only); `shsh:PropertyShapeShape` requires `sh:path`
   (`sh:minCount 1`). This is a newer/more complete draft than pySHACL's own bundled
   `pyshacl/assets/shacl-shacl.ttl`, which was consulted first during investigation but superseded by
   this vendored copy once found — pySHACL's copy omits `sh:hasValue`-adjacent Core predicates the
   official draft does cover, and doesn't yet model `sh:memberShape`/`sh:maxListLength`/`sh:minListLength`/
   `sh:uniqueMembers`/`sh:singleLine` at all.
2. **Spec-semantics judgment**, only for predicates neither file above models at all: SHACL-AF rule
   attachment (`sh:sparql`, `sh:rule` — judged generic by analogy to `sh:and`/`sh:or`/`sh:not`, which the
   official draft *does* confirm generic) and the newest RDF 1.2 extensions not covered by either meta-shapes
   file (`sh:someValue`, `sh:subsetOf`, `sh:rootClass`, `sh:uniqueValuesFor` — judged generic by analogy to
   their nearest Core siblings `sh:hasValue`/`sh:equals`/`sh:class`, which *are* confirmed generic;
   `sh:reifierShape`/`sh:reificationRequired` — judged PropertyShape-only, since reifying
   "`focusNode <path> value`" is only meaningful in the context of a specific path, matching `sh:path`/
   `sh:minCount`'s own confirmed PropertyShape-only treatment rather than `sh:hasValue`'s).

**Both** (appear on NodeShape and PropertyShape forms): `sh:name`, `sh:description`, `sh:message`,
`sh:severity`, `sh:deactivated`, `sh:order`, `sh:nodeKind`, `sh:class`, `sh:datatype`, `sh:minInclusive`,
`sh:maxInclusive`, `sh:minExclusive`, `sh:maxExclusive`, `sh:pattern`, `sh:flags`, `sh:minLength`,
`sh:maxLength`, `sh:languageIn`, `sh:in`, `sh:hasValue`, `sh:and`, `sh:node`, `sh:not`, `sh:or`,
`sh:property`, `sh:xone`, `sh:memberShape`, `sh:maxListLength`, `sh:minListLength`, `sh:uniqueMembers`,
`sh:singleLine`, `sh:targetClass`, `sh:targetNode`, `sh:targetObjectsOf`, `sh:targetSubjectsOf`,
`sh:sparql`, `sh:rule`, `sh:someValue`, `sh:subsetOf`, `sh:rootClass`, `sh:uniqueValuesFor`.

**NodeShape only**: `sh:closed`, `sh:ignoredProperties` — a deliberately narrower default than the
official draft's own generic treatment of these two (which permits them on either shape type); closing
a property shape's own outgoing properties is rarely useful in practice, and downstream editors remain
free to override per the standing "default for everything, override as needed" philosophy.

**PropertyShape only**: `sh:path`, `sh:expression`, `sh:minCount`, `sh:maxCount`, `sh:group`, `sh:uniqueLang`,
`sh:equals`, `sh:disjoint`, `sh:lessThan`, `sh:lessThanOrEquals`, `sh:qualifiedMinCount`,
`sh:qualifiedMaxCount`, `sh:qualifiedValueShapesDisjoint`, `sh:defaultValue`, `sh:qualifiedValueShape`
(explicitly forbidden on NodeShape by `shsh:NodeShapeShape` even though it's otherwise in the official
draft's generic `sh:targetSubjectsOf` list — the explicit restriction wins), `sh:reifierShape`,
`sh:reificationRequired`.

**Deliberately neither** (not a direct field of a NodeShape/PropertyShape form at all — a field of a
*nested* sub-form instead, which this binary doesn't model): property path operators
(`sh:alternativePath`, `sh:inversePath`, `sh:oneOrMorePath`, `sh:zeroOrMorePath`, `sh:zeroOrOnePath` —
nested inside a `sh:path` value, not a direct shape predicate), rule/validator/component internals
(`sh:condition`, `sh:select`, `sh:ask`, `sh:construct`, `sh:subject`, `sh:predicate`, `sh:object`,
`sh:parameter`, `sh:validator`, `sh:nodeValidator`, `sh:propertyValidator` — fields of a Rule,
ConstraintComponent, or Validator sub-form), and class markers used only via `rdf:type`
(`sh:ConstraintComponent`, `sh:TripleRule`, `sh:SPARQLRule`). A downstream editor needing to know
"which fields belong on a Rule sub-form" needs a separate mechanism this vocabulary doesn't yet provide
— tracked as future work in `packages/shacl/CLAUDE.md`, not force-fit into this binary.

---

## Scope notes / open questions

*Updated 2026-07-19 — this section predates the discovery that "SHACL 1.2" is six separate W3C documents (Core, SPARQL Extensions, Node Expressions, Rules, UI, Profiling — see `docs/shacl12-gap-matrix.md`) and the subsequent work that gave starshacl real functional coverage of most of them. Several notes below were written when that coverage didn't exist yet and are corrected here rather than silently left stale.*

- **`sh:rule`/`sh:TripleRule`/`sh:SPARQLRule`/`sh:condition`** (SHACL 1.2 Rules) and **`sh:sparql`**/user-defined **`sh:ConstraintComponent`** (SHACL 1.2 SPARQL Extensions) are functionally supported and tested in starshacl (`tests/integration/test_rule_iteration.py`, `test_rule_condition.py`, `test_custom_constraint_components.py`, `test_sparql_shacl_integration.py`). **Update 2026-07-19: presentation content for these predicates now exists** — see "15. Rules & SPARQL Extensions" below (`sh:sparql`, `sh:select`, `sh:ask`, `sh:ConstraintComponent`, `sh:parameter`, `sh:validator`/`sh:nodeValidator`/`sh:propertyValidator`, `sh:rule`, `sh:condition`, `sh:TripleRule`, `sh:SPARQLRule`, `sh:construct`, `sh:subject`/`sh:predicate`/`sh:object`), converted into both `.ttl` files. **Update 2026-07-19: meta-shacl well-formedness validation rules for these predicates are now done too** — real `sh:property`/`sh:node`/`sh:or` logic (not just descriptive text) in `stsh:RulesAndSparqlShapes`/`stsh:ConstraintComponentShape`/`stsh:SparqlPrefixesShapes`/`stsh:NodeExpressionShape`, covering `sh:sparql`/`sh:rule`/`sh:condition`, custom `sh:ConstraintComponent`, `sh:declare`/`sh:prefix`/`sh:namespace`/`sh:prefixes`, and node expressions themselves (`sh:subject`/`sh:predicate`/`sh:object`'s own values). See `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred" for the exact scope boundaries still in place (e.g. SPARQL query text content isn't parsed). `sh:resultAnnotation`/etc. remain undocumented, since pySHACL itself has zero implementation of them.
- **`shui:` (SHACL 1.2 User Interfaces)** is a separate vocabulary entirely (namespace `http://www.w3.org/ns/shacl-ui#`, not `sh:`), confirmed compatible with starshacl's validation/rules engine (`tests/integration/test_shacl_ui_compatibility.py`). **Update 2026-07-19: now documented** — see "16. SHACL 1.2 UI Widgets" below (`shui:editor`/`shui:viewer`/`shui:propertyRole`/`shui:LabelRole` plus the ~26 built-in editor/viewer instances), converted into both `.ttl` files, ahead of the general training-app phase resuming.
  - **Update 2026-08-15: the `stsh:widgetType` question below is now decided and done** — not via `shui:editor`/`shui:viewer` (those stay documentation-only, per the Scope note at the top of section 16), but via `stsh:widgetType`, this project's own simpler string-tag mechanism (see its `rdfs:comment` in `shacl12-presentation-shapes.ttl` for the full suggested-value vocabulary: `text`, `multiline`, `int`, `number`, `bool`, `severity`, `datatype`, `node_kind`, `class_multi`, `property_multi`, `prop_path_expr`, `has_value_pick`, `in_list`, `uri_list`, `message_list`, `inline_shape`, `group`). Every one of the 108 documented predicates now has a `stsh:widgetType` default (the ~30 `shui:` vocabulary reference entries themselves are the one deliberate exception — they're widget *definitions*, not shape-authoring predicates, so they don't need one). Design intent, per direct instruction: this is a **default**, not a binding contract — a downstream editor is expected to override per-predicate as it sees fit; `stsh:widgetType`'s own `rdfs:comment` already says as much ("not a binding UI contract").
  - The `shui:WidgetScore`/`shui:WidgetAcceptMatcher` *selection algorithm* remains a separate, deferred capability (see `docs/shacl12-gap-matrix.md`'s "Not Covered / Deferred") — not a presentation-content concern at all, and its own supporting vocabulary (`shui:score`, `shui:dataGraphShape`, `shui:shapesGraphShape`) is deliberately excluded from the Widgets section below for the same reason.
  - **Update 2026-08-15: `stsh:nodeFormField`/`stsh:propertyFormField` coverage is now complete for direct shape-level predicates** — was 35/108, now 60/108, with the remaining 48 being either the ~30 `shui:` vocabulary reference entries (widget definitions, not shape-authoring predicates, same exception as `stsh:widgetType` above) or the ~18 nested-sub-form predicates enumerated in "17. Form-Field Membership" above (deliberately out of scope for this binary — they belong to a not-yet-built sub-form field-membership mechanism). Grounded in the official SHACL 1.2 WG draft's own meta-shapes (`tests/vendor/shacl12-vocabularies/shacl-shacl.ttl`'s `shsh:ShapeShape`/`NodeShapeShape`/`PropertyShapeShape`) wherever it applies, not invented from scratch — see section 17 for the full reasoning and predicate lists.
- **SHACL 1.2 Profiling** (`sh:ShapesGraph`/`sh:DataGraph` packaging vocabulary) is out of scope for this file specifically — it's organizational/packaging metadata about *groups* of shapes, not individual predicates a form would render fields for. **Update 2026-07-19: its overall adoption status is now resolved** (confirmed no validator runtime behavior gap, see `docs/shacl12-gap-matrix.md`'s Profiling row) — this file's own scope decision to exclude it is unaffected by that, since it's still not individual-predicate content a form would render fields for.
- The existing 8 "widened" SHACL 1.2 predicates (`sh:class`, `sh:datatype`, `sh:nodeKind`, `sh:equals`, `sh:disjoint`, `sh:lessThan`, `sh:lessThanOrEquals`, `sh:closed`) are documented once each above (in their Core section), with the 1.2 change folded into the description/comment rather than duplicated as a separate entry. **Update 2026-07-21:** each is now also precisely identified via its dual `rdfs:isDefinedBy` (`SHACL Core, SHACL 1.2 Core`) and `stsh:requiredEngine` tag (`stsh:PySHACL` for the plain form, with a parenthetical noting the widened form needs `stsh:StarShacl`) — the prose description is no longer the only signal that a predicate is in this "widened" family.
- **Update 2026-07-21: the `rdfs:isDefinedBy`/`stsh:requiredEngine` schema retrofit (see "Field → RDF mapping", "Spec Provenance", "Required Engine" above) is now complete across all 16 groups / 108 predicate entries** — every entry in this file, including `shui:` widgets and the Rules/SPARQL Extensions group, carries both tags. This resolves the "Open question from review" referenced at the top of the Spec Provenance section; there is no longer an unresolved schema question in this file.
