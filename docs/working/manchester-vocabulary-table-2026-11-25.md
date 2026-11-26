# OWL 2 Manchester Syntax to manch tree vocabulary: proposed end state (2026-11-25)

Status: untracked working note for John to review; nothing was renamed by this note. Written before the ordinal migration (commit 2); that
migration uses it only for the one addition marked "new" below (`manch:values`). Not for commit.

## Summary

1. Scope: every `manch:` class and property that `manchester_parse_to_tree` produces or the ontology declares, in the order of the W3C
   OWL 2 Manchester Syntax Note (ontologyDocument, prologue, frames, clauses, class expressions, data ranges, annotations, misc).
   Column 1 is what the user types, with the Note's production in parentheses (names from the repo's vendored production table,
   `tests/starontology/manchester_conformance/vendor/owl2-manchester-productions.json`); column 2 the proposed tree term; column 3 what
   it represents; column 4 notes. A cell that says "unchanged" means the term as shipped today is also the proposed one.
2. Naming rule (same as the SQE table): class = the Note's production name where the tree node is a whole production, else the keyword as
   typed (`And`, `Some`, `Self`); property = the grammar field or keyword. Where the Note has no name (clause wrappers, list wrappers, the
   data-range prefix, annotation pairs) the term is a modelling helper and its row says what it stands for.
3. The Note names no field for most children (`objectPropertyExpression 'some' primary` has no "filler" or "onProperty"). The tree uses
   the OWL words (`onProperty`, `filler`, `cardinality`, `operand`) for those; Q8.
4. Written spelling that is not kept (by design, stored expanded): prefixed and simple names (stored as full IRIs), the datatype
   abbreviations `integer` `decimal` `float` `string` (stored as the xsd IRIs), the literal spellings (`+7`, `2f`, stored as typed
   literals), comments, blank lines, `that` and the `onlysome` shortcut (desugared by the parser), and every `Prefix:` use. The only
   keyword spelling the tree does remember is `SuperClassOf:`/`SuperPropertyOf:`, because it reverses the compiled axiom (`manch:reversed`).
5. Every ordered list is now written with `tree:ord` (commit 2): the child carries its ordinal, a name or literal sits in a `tree:Item`.
   Rows say "ordered (tree:ord)". Before commit 2 they were `rdf:List`.
6. Sources: `manchester-ast-ontology.ttl`, `manchester_shapes.ttl`, `starontology/manchester/__init__.py`, the vendored production table,
   and probes: 273 Manchester texts parse out of 771 string constants and corpus cases found in `tests/starontology/manchester_conformance`
   (252 conformance cases) and the `*manchester*` tests under `tests/graph/unit` and `tests/starontology/unit`; "seen Nx" is the number of
   tree nodes (classes) or triples (properties) those 273 documents produced under the term. The conformance cases share a prelude
   (3 classes frames, 3 properties, 3 individuals, a datatype), so frame and prefix counts are inflated; clause and expression counts are not.
7. Not in the corpus: `manch:reversed` (used only by unit tests). Everything else in the ontology is exercised. The conformance suite's
   coverage matrix (71 productions + 13 labelled alternatives) is the check that no Note production lacks a case.
8. Open naming questions: below, each with a recommendation. This table is a proposal; the migration in commit 2 renamed nothing.

## Open naming questions

1. Document: `manch:Document` or the production name `manch:OntologyDocument` (`ontologyDocument`)? Recommend `OntologyDocument`.
2. Prologue names: `PrefixDecl` / `prefixLabel` / `prefixIri` or the Note's `PrefixDeclaration` / `prefixName` / `fullIRI`? Recommend
   `PrefixDeclaration`, `prefixName`, and `namespace` for the IRI (`fullIRI` is a lexical production, not a field), and the same
   `...IRI` spelling for `ontologyIRI`, `versionIRI` as the Note writes them (today `ontologyIri`, `versionIri`). If the house style is
   camel-case `Iri` (the repo's `sqe:` and `srl:` use `iri`), keep `Iri` everywhere and rename only the class.
3. Clause class names: keep `ObjProp...`, `DataProp...`, `AnnProp...` abbreviations or spell out `ObjectProperty...`, `DataProperty...`,
   `AnnotationProperty...` like the frame classes? Recommend spell out: one rule, "frame class name + keyword + Clause" (43 classes
   change, nothing else).
4. Restrictions: `Exact` or `Exactly` (the keyword is `exactly`)? `SelfR` or `Self`? The data variants `DSome DOnly DMin DMax DExact`,
   `DAnd DOr DNot DOneOf DRestriction`: keep the `D` prefix or spell out `Data...`? Recommend `Exactly`, `Self` (`SelfR` is a Python-tag
   artefact; nothing in RDF needs it), and `Data` spelled out (`DataSome`, `DataOnly`, `DataMin`, `DataMax`, `DataExactly`, `DataAnd`,
   `DataOr`, `DataNot`, `DataOneOf`, `DatatypeRestriction`), the last because the Note calls the production `datatypeRestriction`.
5. `Value` stands for both `objectvalue` and `datavalue` (told apart by whether the value is an individual or a literal), and an
   unqualified data cardinality (`d min 2`) is the object class `Min` because there is no filler to tell data from object. Keep, or add
   `DataValue` and always emit `DataMin` for a data property? Recommend keep: the parser decides data versus object from the property's
   declaration, which an unqualified cardinality does not need; changing it would change the parser's AST.
6. `AnnotationAssertion` (OWL functional-syntax word, and the object is only an annotation) to `Annotation` (the Note's `annotation`);
   `annotationProperty`/`annotationValue` to `annotationPropertyIRI`/`annotationTarget`? Recommend `Annotation`, `annotationProperty`
   unchanged, `annotationTarget` (the Note's production for the value).
7. Facets: `FacetRestriction` with `facetPredicate`/`facetValue`, versus the Note's `facet` and `restrictionValue`? Recommend keep the
   class (OWL's own term, no Note production for the pair), rename the properties to `facet` and `restrictionValue`.
8. Restriction operands: `onProperty`, `filler`, `cardinality`, `operand`, `operands`, `individuals`, `literals`, `onDatatype`: the Note
   has no field names, so any name is invented; these are OWL RDF-mapping words. Recommend keep all eight except `onDatatype` to `datatype`.
9. `ClassExpression`, `PropertyExpression`, `DataRange` (abstract superclasses): the Note's productions are `description`,
   `objectPropertyExpression`/`dataPropertyExpression` and `dataRange`. Recommend keep all three (they are what OWL users say; `description`
   is OWL 1 wording), `Description` only if production names win over readability.
10. `ClauseItem` for one entry of an `<NT>AnnotatedList` (`[annotations] <NT>`), `FactItem` for `fact`. Recommend `FactItem` to `Fact`
    (a production), `ClauseItem` unchanged (no production; helper). A `Clause` is the whole `'SubClassOf:' descriptionAnnotatedList`.
11. Misc axioms: `MiscEquivalentClassesAxiom` etc. (abstract `MiscAxiom`) or the keyword alone (`EquivalentClasses`, abstract `Misc`)?
    Recommend keep: the keyword alone would clash in spelling with the frame clauses of the same name in a reader's head.
12. New (commit 2): `manch:values`, the ordered children of the one `ClauseItem` of `DisjointUnionOf:`, `HasKey:` and
    `SubPropertyChain:`, where `manch:value` used to hold a nested `rdf:List`. Alternatives: `manch:items` on the ClauseItem, or a typed
    list node. Recommend `values` (a ClauseItem has `value` or `values`, never both, and the shapes can say so).
13. `manch:reversed` (not in the Note; the OWL API accepts `SuperClassOf:`): keep the flag, or give `SuperClassOf:` and `SuperPropertyOf:`
    their own clause classes (`ClassSuperClassOfClause`)? Recommend keep the flag: the compiled OWL is the same axiom read the other way.
14. `manch:PlainString` (datatype that tags a prefix label so a Python `str` and an RDF string literal stay distinct): with pyoxigraph terms
    the distinction is probably unnecessary; recommend check and retire it (prefix name as an ordinary `xsd:string` literal) in a later
    step, not in this migration.
15. nodeID individuals (`_:b1`) are stored as the reserved IRI `urn:starlayer:manchester:nodeid:b1` because the tree uses blank nodes for
    its own structure. Keep, or add `manch:NodeID` with a `manch:label`? Recommend keep (it works, validates, and round-trips).

## 1. Document and prologue

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| (the whole text) (ontologyDocument) | `manch:OntologyDocument` | the root of one parsed document; one per graph | Q1; today `manch:Document`; seen 273x |
| `Prefix: p: <iri>` (prefixDeclaration) | `manch:PrefixDeclaration` (class) | one prefix declaration, kept so rendering reuses the author's prefix labels; prefixed names themselves are stored expanded | Q2; today `PrefixDecl`; seen 1266x (prelude-inflated) |
| (link root to declaration) | `manch:prefixes` | the document's declarations, ordered (tree:ord) | seen 273x (one empty-sequence per doc is not written after commit 2) |
| `p:` (prefixName) | `manch:prefixName` | the label before the colon, a `manch:PlainString` literal (empty for the default prefix) | Q2, Q14; today `prefixLabel`; seen 1266x |
| `<iri>` (fullIRI) | `manch:namespace` | the namespace IRI as a plain string literal (not an IRI: it defines the prefix) | Q2; today `prefixIri`; seen 1266x |
| `Ontology: <iri> <version>` (ontology, ontologyIRI, versionIRI) | `manch:OntologyHeader` (class) | the head of the `ontology` production: its IRI, version, imports and annotations; the frames are on the document, not here | helper split of one production; seen 265x |
| (link document to header) | `manch:header` | at most one header per document; absent when the text has no `Ontology:` | seen 265x |
| `Ontology: <iri>` (ontologyIRI) | `manch:ontologyIRI` | the optional ontology IRI; absent for a bare `Ontology:` | Q2; today `ontologyIri`; seen 262x |
| `<version>` (versionIRI) | `manch:versionIRI` | the optional version IRI (only with an ontology IRI) | Q2; today `versionIri`; seen 3x |
| `Import: <iri>` (import) | `manch:imports` | the imported IRIs, ordered (tree:ord), each held in a tree:Item | seen 265x before commit 2 (always present, empty list written); no import-node class |
| `Annotations: ...` before the frames (annotations) | `manch:annotations` | on the header: the ontology's own annotations, ordered | seen 42x with the other annotations rows |
| (the nodeID `_:b1`) (nodeID) | reserved IRI `urn:starlayer:manchester:nodeid:b1` | stands for a blank-node individual; decoded back to `_:b1` | Q15; not a manch term |

## 2. Frames

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| any frame (frame) | `manch:Frame` (abstract) | superclass of the six frame classes | grammar production `frame` also lists `misc`; Misc is separate here; never asserted |
| `Class: A` (classFrame) | `manch:ClassFrame` | a class frame | unchanged; seen 1098x |
| `ObjectProperty: p` (objectPropertyFrame) | `manch:ObjectPropertyFrame` | an object property frame | unchanged; seen 761x |
| `DataProperty: d` (dataPropertyFrame) | `manch:DataPropertyFrame` | a data property frame | unchanged; seen 528x |
| `AnnotationProperty: n` (annotationPropertyFrame) | `manch:AnnotationPropertyFrame` | an annotation property frame | unchanged; seen 496x |
| `Individual: i` (individualFrame) | `manch:IndividualFrame` | an individual frame (the name may be a nodeID) | unchanged; seen 767x |
| `Datatype: dt` (datatypeFrame) | `manch:DatatypeFrame` | a datatype frame | unchanged; seen 249x |
| the name after the keyword (classIRI, objectPropertyIRI, individual, ...) | `manch:subject` | the frame's own name, one IRI | unchanged; seen 3899x |
| (the clause list) | `manch:clauses` | the frame's clauses in written order, ordered (tree:ord) | seen 3899x |
| (link document to frame) | `manch:frames` | the document's frames in written order, ordered (tree:ord) | seen 273x |

## 3. Clauses (one class per frame kind and keyword)

The Note has no production per clause: each is an alternative inside the frame production (`'SubClassOf:' descriptionAnnotatedList`).
Q3 is the only naming question; the table gives the proposed spelled-out names, and the shipped abbreviation in the notes column.
Every clause has `manch:items` (ordered), whose members are `manch:ClauseItem` (one per comma-separated entry, with its own optional
`Annotations:`), except the rows that say otherwise.

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| (any clause) | `manch:Clause` (abstract) | superclass of the 43 clause classes | never asserted |
| (one entry of an `<NT>AnnotatedList`) (descriptionAnnotatedList item etc.) | `manch:ClauseItem` | one entry: `manch:value` (or `manch:values`, below) and optional `manch:annotations` | Q10; seen 229x |
| (the list of entries) | `manch:items` | the clause's entries, ordered (tree:ord) | seen 280x |
| `SuperClassOf:` / `SuperPropertyOf:` (OWL API extension) | `manch:reversed` | boolean true on the SubClassOf / SubPropertyOf clause that was written with the Super form | Q13; not in the Note; never seen in the corpus |
| `Class: ... SubClassOf: D1, D2` (classFrame) | `manch:ClassSubClassOfClause` | items are ClauseItems whose value is a class expression | seen 74x |
| `EquivalentTo:` in a class frame | `manch:ClassEquivalentToClause` | same shape | seen 14x |
| `DisjointWith:` in a class frame | `manch:ClassDisjointWithClause` | same shape | seen 5x |
| `DisjointUnionOf: D1, D2, ...` | `manch:ClassDisjointUnionOfClause` | single axiom: one ClauseItem whose `manch:values` are the class expressions, ordered; annotated once | Q12; seen 4x |
| `HasKey: p1, p2` | `manch:ClassHasKeyClause` | single axiom: one ClauseItem, `manch:values` are property expressions | Q12; seen 6x |
| `Annotations: ...` in a class frame | `manch:ClassAnnotationsClause` | items are annotations (no ClauseItem wrapper) | seen 9x |
| `Domain: D` (objectPropertyFrame) | `manch:ObjectPropertyDomainClause` | value is a class expression | Q3; today `ObjPropDomainClause`; seen 5x |
| `Range: D` (objectPropertyFrame) | `manch:ObjectPropertyRangeClause` | value is a class expression | Q3; seen 4x |
| `SubPropertyOf: p` (objectPropertyFrame) | `manch:ObjectPropertySubPropertyOfClause` | value is a property expression | Q3; seen 5x |
| `EquivalentTo: p` | `manch:ObjectPropertyEquivalentToClause` | same | Q3; seen 3x |
| `DisjointWith: p` | `manch:ObjectPropertyDisjointWithClause` | same | Q3; seen 3x |
| `InverseOf: p` | `manch:ObjectPropertyInverseOfClause` | same | Q3; seen 3x |
| `Characteristics: Functional, ...` (objectPropertyCharacteristic) | `manch:ObjectPropertyCharacteristicsClause` | value is the OWL class IRI (`owl:FunctionalProperty`...), not the keyword | Q3; seen 10x |
| `SubPropertyChain: p1 o p2 o p3` | `manch:ObjectPropertySubPropertyChainClause` | single axiom: one ClauseItem, `manch:values` are property expressions in chain order | Q3, Q12; seen 4x |
| `Annotations:` in an object property frame | `manch:ObjectPropertyAnnotationsClause` | items are annotations | Q3; seen 2x |
| `Domain: D` (dataPropertyFrame) | `manch:DataPropertyDomainClause` | value is a class expression | Q3; seen 3x |
| `Range: R` (dataPropertyFrame) | `manch:DataPropertyRangeClause` | value is a data range | Q3; seen 33x |
| `SubPropertyOf:`, `EquivalentTo:`, `DisjointWith:` (dataPropertyFrame) | `manch:DataPropertySubPropertyOfClause`, `...EquivalentToClause`, `...DisjointWithClause` | value is a property expression | Q3; seen 3x, 1x, 1x |
| `Characteristics: Functional` (dataPropertyFrame) | `manch:DataPropertyCharacteristicsClause` | value `owl:FunctionalProperty` (the only legal one) | Q3; seen 3x |
| `Annotations:` in a data property frame | `manch:DataPropertyAnnotationsClause` | items are annotations | Q3; seen 2x |
| `Domain:`, `Range:`, `SubPropertyOf:` (annotationPropertyFrame) | `manch:AnnotationPropertyDomainClause`, `...RangeClause`, `...SubPropertyOfClause` | value is an IRI | Q3; seen 4x, 2x, 3x |
| `Annotations:` in an annotation property frame | `manch:AnnotationPropertyAnnotationsClause` | items are annotations | Q3; seen 2x |
| `Types: D` (individualFrame) | `manch:IndividualTypesClause` | value is a class expression | seen 7x |
| `Facts: [not] p v` (fact, factAnnotatedList) | `manch:IndividualFactsClause` | items are `manch:Fact`s | seen 24x |
| `SameAs: i` / `DifferentFrom: i` | `manch:IndividualSameAsClause`, `manch:IndividualDifferentFromClause` | value is an individual IRI | seen 5x, 3x |
| `Annotations:` in an individual frame | `manch:IndividualAnnotationsClause` | items are annotations | seen 2x |
| `EquivalentTo: R` (datatypeFrame) | `manch:DatatypeEquivalentToClause` | value is a data range | seen 3x |
| `Annotations:` in a datatype frame | `manch:DatatypeAnnotationsClause` | items are annotations | seen 3x |
| (one `Facts:` entry) (fact) | `manch:Fact` | `manch:negative`, `manch:property`, `manch:value`, optional `manch:annotations` | Q10; today `FactItem`; seen 41x |
| `not` in a fact | `manch:negative` | boolean literal, always written | seen 41x |
| `p` in `p v` (objectPropertyIRI / dataPropertyIRI) | `manch:property` | the fact's property IRI | seen 41x |
| `v` in `p v` (individual / literal) | `manch:value` | the fact's value (an IRI or a literal) | seen 270x together with ClauseItem |
| (the value of an entry) | `manch:value` | on a ClauseItem: a class expression, property expression, data range, IRI or literal, by clause | polymorphic by design |
| (the members of a single-axiom entry) | `manch:values` | new (commit 2), replaces the nested list in `manch:value`; ordered (tree:ord) | Q12 |

## 4. Class expressions

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| any class expression (description, conjunction, primary, atomic) | `manch:ClassExpression` (abstract) | superclass of the 14 class-expression classes; an atomic class is a bare IRI | Q9 |
| `C1 and C2` (conjunction) | `manch:And` | `manch:operands`, ordered, two or more | unchanged; seen 11x |
| `C1 or C2` (description) | `manch:Or` | same | seen 7x |
| `not C` (primary) | `manch:Not` | `manch:operand` | seen 7x |
| `{ i1, i2 }` (atomic) | `manch:OneOf` | `manch:individuals`, ordered, IRIs in tree:Items | seen 5x |
| `p some C` (objectsome) | `manch:Some` | `manch:onProperty`, `manch:filler` | seen 18x |
| `p only C` (objectonly) | `manch:Only` | same | seen 1x |
| `p value i` / `d value lit` (objectvalue, datavalue) | `manch:Value` | `manch:onProperty`, `manch:filler` is the individual IRI or the literal | Q5; seen 5x |
| `p Self` (objectSelf) | `manch:Self` | `manch:onProperty` only | Q4; today `SelfR`; seen 2x |
| `p min n [C]` (objectmin) | `manch:Min` | `manch:onProperty`, `manch:cardinality`, optional `manch:filler`; also the unqualified data cardinality | Q5; seen 5x |
| `p max n [C]` (objectmax) | `manch:Max` | same | seen 4x |
| `p exactly n [C]` (objectexactly) | `manch:Exactly` | same | Q4; today `Exact`; seen 3x |
| `d some R` (datasome) | `manch:DataSome` | `manch:onProperty`, `manch:filler` is a data range | Q4; today `DSome`; seen 9x |
| `d only R` (dataonly) | `manch:DataOnly` | same | Q4; seen 1x |
| `d min n R` (datamin) | `manch:DataMin` | qualified only: `manch:filler` required | Q4, Q5; seen 1x |
| `d max n R` (datamax) | `manch:DataMax` | same | Q4; seen 1x |
| `d exactly n R` (dataexactly) | `manch:DataExactly` | same | Q4; seen 1x |
| `n` in a cardinality (nonNegativeInteger) | `manch:cardinality` | an integer literal (Oxigraph stores it as `xsd:integer` whatever datatype was written) | seen 15x |
| `p` before the keyword (objectPropertyExpression, dataPropertyExpression) | `manch:onProperty` | the restricted property: an IRI or a `manch:Inverse` | Q8; seen 51x |
| the filler after the keyword (primary, dataPrimary) | `manch:filler` | the filler (class expression, data range, individual or literal) | Q8; seen 40x |
| the operand of `not` | `manch:operand` | one operand, also used by DataNot and Inverse | seen 18x |
| the operands of `and`/`or` | `manch:operands` | ordered operands, also used by DataAnd and DataOr | seen 24x |
| `inverse p` (inverseObjectProperty) | `manch:Inverse` | `manch:operand`, the property IRI; the only wrapped property expression | seen 8x |
| a property expression (objectPropertyExpression) | `manch:PropertyExpression` (abstract) | superclass of `Inverse`; a plain property is a bare IRI | Q9 |

## 5. Data ranges

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| any data range (dataRange, dataConjunction, dataPrimary, dataAtomic) | `manch:DataRange` (abstract) | superclass; an atomic datatype is a bare IRI | Q9 |
| `R1 and R2` (dataConjunction) | `manch:DataAnd` | `manch:operands`, ordered | Q4; today `DAnd`; seen 2x |
| `R1 or R2` (dataRange) | `manch:DataOr` | same | Q4; today `DOr`; seen 4x |
| `not R` (dataPrimary) | `manch:DataNot` | `manch:operand` | Q4; today `DNot`; seen 3x |
| `{ 1, 2 }` (dataAtomic) | `manch:DataOneOf` | `manch:literals`, ordered, each literal in a tree:Item | Q4; today `DOneOf`; seen 4x |
| `integer[>= 5, < 10]` (datatypeRestriction) | `manch:DatatypeRestriction` | `manch:onDatatype`, `manch:facets` (ordered) | Q4; today `DRestriction`; seen 22x |
| the datatype before `[` (Datatype) | `manch:datatype` | the restricted datatype IRI | Q8; today `onDatatype`; seen 22x |
| `>= 5` (facet restrictionValue) | `manch:FacetRestriction` | one facet and value; no Note production for the pair | Q7; seen 26x |
| `>=` (facet) | `manch:facet` | the xsd facet IRI (`xsd:minInclusive`...), or `rdf:langRange`; the written symbol is mapped to the IRI the Note's table likely meant (see README F15) | Q7; today `facetPredicate`; seen 26x |
| `5` (restrictionValue) | `manch:restrictionValue` | the literal | Q7; today `facetValue`; seen 26x |
| (the facets of a restriction) | `manch:facets` | ordered (tree:ord) | seen 22x |
| (the literals of an enumeration) | `manch:literals` | ordered (tree:ord) | seen 4x |

## 6. Annotations

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| `Annotations: p v` (annotations, annotation) | `manch:Annotation` | one annotation: property and target; may itself carry annotations | Q6; today `AnnotationAssertion`; seen 66x |
| `p` (annotationPropertyIRI) | `manch:annotationProperty` | the annotation property IRI | unchanged; seen 66x |
| `v` (annotationTarget) | `manch:annotationTarget` | an IRI (also a nodeID IRI) or a literal | Q6; today `annotationValue`; seen 66x |
| (annotations on an entry, header, misc axiom or annotation) | `manch:annotations` | ordered (tree:ord) | seen 42x |

## 7. Misc axioms (no subject frame)

| Manchester as written (production) | Proposed manch term | What the term represents | Notes |
|---|---|---|---|
| any misc axiom (misc) | `manch:MiscAxiom` (abstract) | superclass; `manch:items` (ordered), optional leading `manch:annotations` (one list for the whole axiom) | Q11 |
| `EquivalentClasses: C1, C2` | `manch:MiscEquivalentClassesAxiom` | items are class expressions | seen 6x |
| `DisjointClasses: C1, C2` | `manch:MiscDisjointClassesAxiom` | same | seen 5x |
| `EquivalentProperties: p1, p2` | `manch:MiscEquivalentPropertiesAxiom` | items are property expressions | seen 4x |
| `DisjointProperties: p1, p2` | `manch:MiscDisjointPropertiesAxiom` | same | seen 4x |
| `SameIndividual: i1, i2` | `manch:MiscSameIndividualAxiom` | items are individual IRIs, each in a tree:Item | seen 3x |
| `DifferentIndividuals: i1, i2` | `manch:MiscDifferentIndividualsAxiom` | same | seen 3x |
| (link document to misc axiom) | `manch:misc` | in written order, ordered (tree:ord) | seen 273x |

## 8. Shared structure terms

| Written | Term | What the term represents | Notes |
|---|---|---|---|
| (the position of a child among its siblings) | `tree:ord` | non-negative integer on the child (on its `tree:Item` for a name or literal); order is ascending ordinal, gaps allowed, a tie is an error | shared with sqe: and srl:; from commit 2 |
| (a name or literal as an ordered child) | `tree:Item`, `tree:value` | wrapper for an IRI or literal in an ordered position, so the IRI may sit in many places | commit 2 |
| (prefix label datatype) | `manch:PlainString` | the datatype of `manch:prefixName`; see Q14 | seen 1266x |

## 9. Coverage and removed terms

- Every class and property in `manchester-ast-ontology.ttl` appears above. Dead terms: none (the introspection test
  `test_every_ontology_term_is_used_by_the_code` keeps it so).
- Not representable (by design): spelling and layout, comments, the `that` and `onlysome` shorthand, prefixed-name spelling (all stored
  expanded), SWRL `Rule:` (not in the Note's grammar; refused by the parser).
- Removed by the ordinal migration (commit 2), no rename: the 13 list shapes of `manchester_shapes.ttl` (`WellFormedListShape` and its
  twelve users), the `rdf:List` ranges of `manch:items`, `operands`, `frames`, `clauses`, `prefixes`, `imports`, `individuals`, `literals`,
  `facets` and `annotations`, and the list-cycle pre-flight check of `manchester_validate`.

## 10. Applied (2026-11-26)

The maintainer took all recommendations of the 15 open questions; the table above is now the shipped vocabulary (commit `abacf813`,
renames only: no alias, the encoding with `tree:ord` and every behaviour unchanged).

- Renamed in `manchester-ast-ontology.ttl` (44 names): 36 classes and 8 properties.
  - Q1 `Document` to `OntologyDocument`; Q2 `PrefixDecl` to `PrefixDeclaration`, `prefixLabel` to `prefixName`, `prefixIri` to `namespace`,
    `ontologyIri` to `ontologyIRI`, `versionIri` to `versionIRI`.
  - Q3 20 clause classes spelled out: 9 `ObjProp...Clause` to `ObjectProperty...Clause`, 7 `DataProp...Clause` to `DataProperty...Clause`, 4
    `AnnProp...Clause` to `AnnotationProperty...Clause`. The table said "43 classes change": the ontology has 33 clause classes in all (the 43
    counts the keyword rows of section 3), 20 of which had an abbreviated name.
  - Q4 `Exact` to `Exactly`, `SelfR` to `Self`, `DSome` `DOnly` `DMin` `DMax` `DExact` `DAnd` `DOr` `DNot` `DOneOf` to `DataSome` `DataOnly` `DataMin`
    `DataMax` `DataExactly` `DataAnd` `DataOr` `DataNot` `DataOneOf`, `DRestriction` to `DatatypeRestriction` (12 classes).
  - Q6 `AnnotationAssertion` to `Annotation`, `annotationValue` to `annotationTarget`; Q7 `facetPredicate` to `facet`, `facetValue` to
    `restrictionValue`; Q8 `onDatatype` to `datatype`; Q10 `FactItem` to `Fact`.
- Kept (Q5, Q8, Q9, Q11, Q12, Q13, Q14, Q15 as recommended): `Value`, `Min`, `Max`, `onProperty`, `filler`, `cardinality`, `operand`, `operands`,
  `individuals`, `literals`, `ClassExpression`, `PropertyExpression`, `DataRange`, `ClauseItem`, `MiscAxiom` and the six `Misc...Axiom` classes,
  `values`, `reversed`, `PlainString`, the reserved nodeID IRI.
- `manchester_shapes.ttl`: the same names (44) plus 20 shape names that carried an old name (`ExactShape` to `ExactlyShape`, `DocumentShape` to
  `OntologyDocumentShape`, `FactItemShape` to `FactShape`, `OrderedFactItemShape` to `OrderedFactShape`, `PrefixDeclShape` to
  `PrefixDeclarationShape`, `AnnotationAssertionShape` to `AnnotationShape`, the `D...Shape` ones to `Data...Shape`, the characteristic item shapes).
- Python: `MANCH.<name>` uses and docstrings; the parser's own AST tags (`'Exact'`, `'SelfR'`, `'DSome'`...) stay (graph/manchester/parser.py is not
  part of this step) and map to the class name through `_CLASS_OF_TAG` in `starontology/manchester/__init__.py`. The private decode namedtuples
  (`Document`, `PrefixDecl`, `FactItem`, `AnnotationAssertion`) keep their names.
- Snapshots and `SNAPSHOT_FROM.md` refreshed (SHA-256 `8ad40d51...` ontology, `897b8ff7...` shapes); guard test
  `tests/starontology/unit/test_manchester_vocabulary.py`.
- Guide cells still showing old names (06.05 cells `3a4f516b` and `6b2e0002`) are listed in the hand-off; notebooks are re-run by the maintainer.
