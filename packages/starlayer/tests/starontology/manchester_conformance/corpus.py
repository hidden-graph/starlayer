"""Positive corpus for the Manchester conformance suite.

Every ``Case`` names the W3C grammar productions it exercises (``covers``); the coverage-matrix test
fails if any production is exercised by no case, or if a case names a production that is not in the
grammar table. Cases are minimal and one construct each, so a failure points at one production.

Most cases are a ``PRELUDE`` (declares the entities the cases use - OWL API requires every name to be
declared before use, see docs/graph/manchester_syntax_gap_analysis.md "Declaration-order strictness")
followed by a ``body``. Cases that exercise the document header or prefix handling set
``prelude=False`` and are complete documents.
"""

from __future__ import annotations

from dataclasses import dataclass

PRELUDE = """\
Prefix: : <http://example.org/o#>
Prefix: owl: <http://www.w3.org/2002/07/owl#>
Prefix: rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
Prefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>
Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>
Ontology: <http://example.org/o>
Class: A
Class: B
Class: C
Class: D
ObjectProperty: p
ObjectProperty: q
ObjectProperty: r
DataProperty: d
DataProperty: e
AnnotationProperty: note
AnnotationProperty: note2
Individual: i
Individual: j
Individual: k
Datatype: dt
"""

HEADER = """\
Prefix: : <http://example.org/o#>
Prefix: owl: <http://www.w3.org/2002/07/owl#>
Prefix: rdfs: <http://www.w3.org/2000/01/rdf-schema#>
Prefix: xsd: <http://www.w3.org/2001/XMLSchema#>
"""


@dataclass(frozen=True)
class Case:
    id: str
    covers: tuple[str, ...]
    body: str
    prelude: bool = True
    # False for cases the OWL API oracle cannot be asked about (it would dereference an owl:imports
    # IRI over the network, for instance). Reason in ``note``.
    oracle: bool = True
    note: str = ""

    @property
    def text(self) -> str:
        return (PRELUDE + self.body) if self.prelude else self.body


CASES: list[Case] = []


def _c(id: str, covers: str, body: str, **kw) -> None:
    CASES.append(Case(id, tuple(covers.split()), body.rstrip("\n") + "\n", **kw))


# ---------------------------------------------------------------------------
# Document header: prefixes, ontology IRI/version, imports, ontology annotations
# ---------------------------------------------------------------------------
_c("hdr-no-iri", "ontologyDocument prefixDeclaration prefixName fullIRI ontology",
   HEADER + "Ontology:\nClass: A\n", prelude=False)
_c("hdr-iri", "ontologyIRI IRI fullIRI",
   HEADER + "Ontology: <http://example.org/o>\nClass: A\n", prelude=False)
_c("hdr-iri-and-version", "versionIRI ontologyIRI",
   HEADER + "Ontology: <http://example.org/o> <http://example.org/o/1.0>\nClass: A\n", prelude=False)
_c("hdr-import", "import",
   HEADER + "Ontology: <http://example.org/o>\nImport: <http://example.org/other>\nClass: A\n",
   prelude=False, oracle=False, note="OWL API would dereference the imported IRI over the network")
_c("hdr-two-imports", "import",
   HEADER + "Ontology: <http://example.org/o>\nImport: <http://example.org/one>\nImport: <http://example.org/two>\nClass: A\n",
   prelude=False, oracle=False, note="OWL API would dereference the imported IRIs over the network")
_c("hdr-annotations", "annotations annotation annotationAnnotatedList annotationPropertyIRI literal stringLiteralNoLanguage quotedString",
   HEADER + 'Ontology: <http://example.org/o>\nAnnotations: rdfs:comment "an ontology"\nClass: A\n', prelude=False)
_c("hdr-annotations-list", "annotationAnnotatedList",
   HEADER + 'Ontology: <http://example.org/o>\nAnnotations: rdfs:comment "one", rdfs:label "two"\nClass: A\n', prelude=False)
_c("hdr-annotations-nested", "annotations annotation",
   HEADER + 'Ontology: <http://example.org/o>\nAnnotations: Annotations: rdfs:label "inner" rdfs:comment "outer"\nClass: A\n', prelude=False)
_c("hdr-prefix-default-and-named", "prefixDeclaration prefixName abbreviatedIRI",
   'Prefix: : <http://example.org/o#>\nPrefix: ex: <http://example.org/ex#>\nOntology: <http://example.org/o>\nClass: ex:A\nClass: :B\n', prelude=False)
_c("hdr-version-and-annotations-and-frames", "ontology ontologyIRI versionIRI annotations frame",
   HEADER + 'Ontology: <http://example.org/o> <http://example.org/o/2>\nAnnotations: rdfs:label "v2"\nClass: A\nClass: B\n  SubClassOf: A\n', prelude=False)

# ---------------------------------------------------------------------------
# IRIs and names
# ---------------------------------------------------------------------------
_c("iri-full", "fullIRI IRI classIRI", "Class: <http://example.org/o#Full>")
_c("iri-abbreviated", "abbreviatedIRI IRI classIRI", "Class: :Abbrev")
_c("iri-simple", "simpleIRI IRI classIRI", "Class: Simple")
_c("iri-builtin-prefix", "abbreviatedIRI", "Class: A\n  SubClassOf: owl:Thing")
_c("iri-mixed-forms", "fullIRI abbreviatedIRI simpleIRI",
   "Class: A\n  SubClassOf: <http://example.org/o#B>, :C, D")
_c("iri-object-property", "objectPropertyIRI", "ObjectProperty: <http://example.org/o#pFull>")
_c("iri-data-property", "dataPropertyIRI", "DataProperty: :dAbbrev")
_c("iri-annotation-property", "annotationPropertyIRI", "AnnotationProperty: <http://example.org/o#nFull>")
_c("iri-individual", "individualIRI individual", "Individual: <http://example.org/o#iFull>")
_c("iri-datatype", "datatypeIRI Datatype", "Datatype: <http://example.org/o#dtFull>")

# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------
_c("lit-string", "literal stringLiteralNoLanguage quotedString", 'Individual: i\n  Facts: d "text"')
_c("lit-string-escapes", "quotedString", 'Individual: i\n  Facts: d "a\\"b\\\\c"')
_c("lit-string-lang", "stringLiteralWithLanguage languageTag", 'Individual: i\n  Facts: d "hello"@en')
_c("lit-string-lang-region", "languageTag", 'Individual: i\n  Facts: d "colour"@en-GB')
_c("lit-typed", "typedLiteral lexicalValue datatypeIRI", 'Individual: i\n  Facts: d "5"^^xsd:integer')
_c("lit-typed-full-iri", "typedLiteral",
   'Individual: i\n  Facts: d "5"^^<http://www.w3.org/2001/XMLSchema#integer>')
_c("lit-typed-short-datatype-names", "typedLiteral Datatype",
   'Individual: i\n  Facts: d "5"^^integer, d "1.5"^^decimal, d "2.5"^^float, d "x"^^string')
_c("lit-integer", "integerLiteral digits digit nonZero zero", "Individual: i\n  Facts: d 5, d 10, d 0")
_c("lit-integer-signed", "integerLiteral", "Individual: i\n  Facts: d -5, d +7")
_c("lit-decimal", "decimalLiteral", "Individual: i\n  Facts: d 5.0, d -2.50, d +0.125")
_c("lit-float", "floatingPointLiteral", "Individual: i\n  Facts: d 2f, d 1.5F, d .5f, d -3.25f")
_c("lit-float-exponent", "floatingPointLiteral exponent", "Individual: i\n  Facts: d 1.5e3f, d 2E-2F, d 1e+5f")
_c("lit-annotation-target-forms", "annotationTarget nodeID IRI literal",
   'Class: A\n  Annotations: note "lit", note <http://example.org/o#thing>, note _:blank')

# ---------------------------------------------------------------------------
# Class expressions
# ---------------------------------------------------------------------------
_c("ce-atomic", "description conjunction primary atomic classIRI", "Class: A\n  SubClassOf: B")
_c("ce-and", "conjunction primary", "Class: A\n  SubClassOf: B and C")
_c("ce-and-three", "conjunction", "Class: A\n  SubClassOf: B and C and D")
_c("ce-or", "description", "Class: A\n  SubClassOf: B or C")
_c("ce-or-three", "description", "Class: A\n  SubClassOf: B or C or D")
_c("ce-not", "primary", "Class: A\n  SubClassOf: not B")
_c("ce-not-group", "primary atomic", "Class: A\n  SubClassOf: not (B or C)")
_c("ce-double-not", "primary", "Class: A\n  SubClassOf: not (not B)")
_c("ce-precedence-and-over-or", "description conjunction", "Class: A\n  SubClassOf: B or C and D")
_c("ce-parens-override", "atomic description", "Class: A\n  SubClassOf: (B or C) and D")
_c("ce-nested-parens", "atomic", "Class: A\n  SubClassOf: ((B))")
_c("ce-enumeration", "atomic individualList individual", "Class: A\n  EquivalentTo: {i, j, k}")
_c("ce-enumeration-single", "atomic", "Class: A\n  EquivalentTo: {i}")
_c("ce-enumeration-with-nodeid", "atomic nodeID individual", "Class: A\n  EquivalentTo: {i, _:anon}")

_c("r-some", "restriction objectsome", "Class: A\n  SubClassOf: p some B")
_c("r-some-complex-filler", "restriction objectsome primary", "Class: A\n  SubClassOf: p some (B or C)")
_c("r-some-not-filler", "objectsome primary", "Class: A\n  SubClassOf: p some not B")
_c("r-some-chained", "objectsome primary restriction", "Class: A\n  SubClassOf: p some q some B")
_c("r-only", "restriction objectonly", "Class: A\n  SubClassOf: p only B")
_c("r-value", "restriction objectvalue", "Class: A\n  SubClassOf: p value i")
_c("r-value-nodeid", "objectvalue nodeID", "Class: A\n  SubClassOf: p value _:anon")
_c("r-self", "restriction objectSelf", "Class: A\n  SubClassOf: p Self")
_c("r-min-unqualified", "restriction objectmin nonNegativeInteger", "Class: A\n  SubClassOf: p min 2")
_c("r-min-qualified", "objectmin nonNegativeInteger primary", "Class: A\n  SubClassOf: p min 2 B")
_c("r-max-unqualified", "restriction objectmax", "Class: A\n  SubClassOf: p max 3")
_c("r-max-qualified", "objectmax", "Class: A\n  SubClassOf: p max 3 B")
_c("r-exactly-unqualified", "restriction objectexactly", "Class: A\n  SubClassOf: p exactly 1")
_c("r-exactly-qualified", "objectexactly", "Class: A\n  SubClassOf: p exactly 1 C")
_c("r-cardinality-zero", "nonNegativeInteger zero", "Class: A\n  SubClassOf: p max 0")
_c("r-cardinality-multidigit", "nonNegativeInteger positiveInteger", "Class: A\n  SubClassOf: p min 12")
_c("r-inverse-some", "objectPropertyExpression inverseObjectProperty", "Class: A\n  SubClassOf: inverse p some B")
_c("r-inverse-value", "inverseObjectProperty objectvalue", "Class: A\n  SubClassOf: inverse p value i")
_c("r-inverse-min", "inverseObjectProperty objectmin", "Class: A\n  SubClassOf: inverse p min 1")
_c("r-inverse-self", "inverseObjectProperty objectSelf", "Class: A\n  SubClassOf: inverse p Self")

_c("dr-some", "datasome dataPropertyExpression dataPrimary dataAtomic Datatype", "Class: A\n  SubClassOf: d some xsd:integer")
_c("dr-some-restricted", "datasome datatypeRestriction facet restrictionValue", "Class: A\n  SubClassOf: d some xsd:integer[>= 5]")
_c("dr-some-enumeration", "datasome dataAtomic literalList", "Class: A\n  SubClassOf: d some {1, 2, 3}")
_c("dr-some-not", "datasome dataPrimary", "Class: A\n  SubClassOf: d some not xsd:string")
_c("dr-some-union", "datasome dataRange dataConjunction", "Class: A\n  SubClassOf: d some (xsd:integer or xsd:string)")
_c("dr-only", "dataonly", "Class: A\n  SubClassOf: d only xsd:string")
_c("dr-value", "datavalue", 'Class: A\n  SubClassOf: d value "x"')
_c("dr-value-integer", "datavalue integerLiteral", "Class: A\n  SubClassOf: d value 5")
_c("dr-min-unqualified", "datamin", "Class: A\n  SubClassOf: d min 1")
_c("dr-min-qualified", "datamin dataPrimary", "Class: A\n  SubClassOf: d min 1 xsd:integer")
_c("dr-max-unqualified", "datamax", "Class: A\n  SubClassOf: d max 2")
_c("dr-max-qualified", "datamax", "Class: A\n  SubClassOf: d max 2 xsd:string")
_c("dr-exactly-unqualified", "dataexactly", "Class: A\n  SubClassOf: d exactly 2")
_c("dr-exactly-qualified", "dataexactly", "Class: A\n  SubClassOf: d exactly 2 xsd:string")
_c("dr-short-datatype-name", "Datatype dataAtomic", "Class: A\n  SubClassOf: d some integer")

_c("that-single", "conjunction", "Class: A\n  EquivalentTo: B that p some C")
_c("that-two", "conjunction restriction", "Class: A\n  EquivalentTo: B that p some C and q some D")
_c("that-not", "conjunction", "Class: A\n  EquivalentTo: B that not p some C")
_c("that-and-not", "conjunction", "Class: A\n  EquivalentTo: B that p some C and not q some D")
_c("that-data-restriction", "conjunction datasome", "Class: A\n  EquivalentTo: B that d some xsd:integer")

# ---------------------------------------------------------------------------
# Data ranges and datatype restrictions
# ---------------------------------------------------------------------------
_c("range-atomic", "dataRange dataConjunction dataPrimary dataAtomic", "DataProperty: d\n  Range: xsd:integer")
_c("range-short-integer", "Datatype", "DataProperty: d\n  Range: integer")
_c("range-short-decimal", "Datatype", "DataProperty: d\n  Range: decimal")
_c("range-short-float", "Datatype", "DataProperty: d\n  Range: float")
_c("range-short-string", "Datatype", "DataProperty: d\n  Range: string")
_c("range-or", "dataRange", "DataProperty: d\n  Range: xsd:integer or xsd:string")
_c("range-and", "dataConjunction", "DataProperty: d\n  Range: xsd:integer and xsd:decimal")
_c("range-not", "dataPrimary", "DataProperty: d\n  Range: not xsd:integer")
_c("range-grouped", "dataAtomic", "DataProperty: d\n  Range: (xsd:integer or xsd:string) and not xsd:string")
_c("range-enumeration", "dataAtomic literalList", 'DataProperty: d\n  Range: {"a", "b"}')
_c("range-enumeration-mixed", "literalList", 'DataProperty: d\n  Range: {1, "two", 3.0}')
_c("facet-ge", "datatypeRestriction facet restrictionValue", "DataProperty: d\n  Range: xsd:integer[>= 1]")
_c("facet-le", "facet", "DataProperty: d\n  Range: xsd:integer[<= 10]")
_c("facet-gt", "facet", "DataProperty: d\n  Range: xsd:integer[> 0]")
_c("facet-lt", "facet", "DataProperty: d\n  Range: xsd:integer[< 100]")
_c("facet-two", "datatypeRestriction facet", "DataProperty: d\n  Range: xsd:integer[>= 1, < 10]")
_c("facet-decimal", "facet decimalLiteral", "DataProperty: d\n  Range: xsd:decimal[> 0.5]")
_c("facet-float", "facet floatingPointLiteral", "DataProperty: d\n  Range: xsd:float[<= 2.5f]")
_c("facet-length", "facet", "DataProperty: d\n  Range: xsd:string[length 5]")
_c("facet-minlength", "facet", "DataProperty: d\n  Range: xsd:string[minLength 1]")
_c("facet-maxlength", "facet", "DataProperty: d\n  Range: xsd:string[maxLength 9]")
_c("facet-min-and-max-length", "facet", "DataProperty: d\n  Range: xsd:string[minLength 1, maxLength 9]")
_c("facet-pattern", "facet", 'DataProperty: d\n  Range: xsd:string[pattern "[a-z]+"]')
_c("facet-langrange", "facet", 'DataProperty: d\n  Range: rdf:PlainLiteral[langRange "en"]')
_c("facet-on-short-datatype", "datatypeRestriction Datatype", "DataProperty: d\n  Range: integer[>= 1]")
_c("facet-restriction-in-union", "dataRange datatypeRestriction",
   "DataProperty: d\n  Range: xsd:integer[< 0] or xsd:integer[> 100]")

_c("datatype-frame-equivalent", "datatypeFrame dataRange", "Datatype: dt\n  EquivalentTo: xsd:integer[>= 0]")
_c("datatype-frame-annotations", "datatypeFrame annotations", 'Datatype: dt\n  Annotations: note "a datatype"')
_c("datatype-frame-equiv-annotations", "datatypeFrame annotations",
   'Datatype: dt\n  EquivalentTo: Annotations: note "why" xsd:integer[>= 0]')
_c("datatype-frame-annotations-both-sides", "datatypeFrame",
   'Datatype: dt\n  Annotations: note "before"\n  EquivalentTo: xsd:integer\n  Annotations: note "after"')

# ---------------------------------------------------------------------------
# Class frame clauses
# ---------------------------------------------------------------------------
_c("class-subclassof", "classFrame descriptionAnnotatedList", "Class: A\n  SubClassOf: B")
_c("class-subclassof-list", "descriptionAnnotatedList", "Class: A\n  SubClassOf: B, C, D")
_c("class-subclassof-annotated", "descriptionAnnotatedList annotations",
   'Class: A\n  SubClassOf: Annotations: note "why" B')
_c("class-subclassof-annotated-one-of-two", "descriptionAnnotatedList",
   'Class: A\n  SubClassOf: Annotations: note "why" B, C')
_c("class-subclassof-annotated-both", "descriptionAnnotatedList",
   'Class: A\n  SubClassOf: Annotations: note "x" B, Annotations: note "y" C')
_c("class-subclassof-annotation-nested", "annotations annotation",
   'Class: A\n  SubClassOf: Annotations: Annotations: note2 "inner" note "outer" B')
_c("class-equivalentto", "classFrame", "Class: A\n  EquivalentTo: B")
_c("class-equivalentto-list", "descriptionAnnotatedList", "Class: A\n  EquivalentTo: B, C")
_c("class-equivalentto-annotated", "annotations", 'Class: A\n  EquivalentTo: Annotations: note "x" B')
_c("class-disjointwith", "classFrame", "Class: A\n  DisjointWith: B")
_c("class-disjointwith-list", "descriptionAnnotatedList", "Class: A\n  DisjointWith: B, C")
_c("class-disjointwith-annotated", "annotations", 'Class: A\n  DisjointWith: Annotations: note "x" B')
_c("class-disjointunionof", "description2List", "Class: A\n  DisjointUnionOf: B, C")
_c("class-disjointunionof-three", "description2List", "Class: A\n  DisjointUnionOf: B, C, D")
_c("class-disjointunionof-annotated", "annotations", 'Class: A\n  DisjointUnionOf: Annotations: note "x" B, C')
_c("class-disjointunionof-expressions", "description2List", "Class: A\n  DisjointUnionOf: p some B, p some C")
_c("class-haskey-object", "objectPropertyExpression", "Class: A\n  HasKey: p")
_c("class-haskey-data", "dataPropertyExpression", "Class: A\n  HasKey: d")
_c("class-haskey-mixed", "dataPropertyExpression objectPropertyExpression", "Class: A\n  HasKey: p, d")
_c("class-haskey-inverse", "inverseObjectProperty", "Class: A\n  HasKey: inverse p")
_c("class-haskey-annotated", "annotations", 'Class: A\n  HasKey: Annotations: note "x" p, d')
_c("class-annotations", "annotation annotationAnnotatedList", 'Class: A\n  Annotations: note "a"')
_c("class-annotations-list", "annotationAnnotatedList", 'Class: A\n  Annotations: note "a", note2 "b"')
_c("class-annotations-annotated", "annotations", 'Class: A\n  Annotations: Annotations: note2 "meta" note "a"')
_c("class-annotations-lang", "stringLiteralWithLanguage", 'Class: A\n  Annotations: rdfs:label "Chat"@fr')
_c("class-annotations-typed", "typedLiteral", 'Class: A\n  Annotations: note "5"^^xsd:integer')
_c("class-annotations-integer", "integerLiteral", "Class: A\n  Annotations: note 5")
_c("class-annotations-iri-target", "annotationTarget", "Class: A\n  Annotations: rdfs:seeAlso <http://example.org/more>")
_c("class-all-clauses", "classFrame",
   'Class: A\n  Annotations: note "x"\n  SubClassOf: B\n  EquivalentTo: C\n  DisjointWith: D\n  HasKey: p')
_c("class-repeated-frame", "frame", "Class: A\n  SubClassOf: B\nClass: A\n  SubClassOf: C")
_c("class-clause-order-reversed", "classFrame", "Class: A\n  DisjointWith: D\n  EquivalentTo: C\n  SubClassOf: B")
_c("class-repeated-clause", "classFrame", "Class: A\n  SubClassOf: B\n  SubClassOf: C")
_c("class-no-clauses", "classFrame", "Class: Lonely")

# ---------------------------------------------------------------------------
# Object property frame clauses
# ---------------------------------------------------------------------------
_c("op-domain", "objectPropertyFrame", "ObjectProperty: p\n  Domain: A")
_c("op-domain-complex", "objectPropertyFrame descriptionAnnotatedList", "ObjectProperty: p\n  Domain: A or B")
_c("op-range", "objectPropertyFrame", "ObjectProperty: p\n  Range: B")
_c("op-domain-range-annotated", "annotations", 'ObjectProperty: p\n  Domain: Annotations: note "x" A\n  Range: Annotations: note "y" B')
_c("op-subpropertyof", "objectPropertyExpressionAnnotatedList", "ObjectProperty: p\n  SubPropertyOf: q")
_c("op-subpropertyof-inverse", "inverseObjectProperty", "ObjectProperty: p\n  SubPropertyOf: inverse q")
_c("op-subpropertyof-list", "objectPropertyExpressionAnnotatedList", "ObjectProperty: p\n  SubPropertyOf: q, r")
_c("op-subpropertyof-annotated", "annotations", 'ObjectProperty: p\n  SubPropertyOf: Annotations: note "x" q')
_c("op-equivalentto", "objectPropertyFrame", "ObjectProperty: p\n  EquivalentTo: q")
_c("op-equivalentto-inverse", "inverseObjectProperty", "ObjectProperty: p\n  EquivalentTo: inverse q")
_c("op-disjointwith", "objectPropertyFrame", "ObjectProperty: p\n  DisjointWith: q")
_c("op-disjointwith-list", "objectPropertyExpressionAnnotatedList", "ObjectProperty: p\n  DisjointWith: q, r")
_c("op-inverseof", "objectPropertyFrame", "ObjectProperty: p\n  InverseOf: q")
_c("op-inverseof-annotated", "annotations", 'ObjectProperty: p\n  InverseOf: Annotations: note "x" q')
_c("op-chain-two", "objectPropertyFrame", "ObjectProperty: p\n  SubPropertyChain: q o r")
_c("op-chain-three", "objectPropertyFrame", "ObjectProperty: p\n  SubPropertyChain: q o r o q")
_c("op-chain-inverse-member", "inverseObjectProperty", "ObjectProperty: p\n  SubPropertyChain: q o inverse r")
_c("op-chain-annotated", "annotations", 'ObjectProperty: p\n  SubPropertyChain: Annotations: note "x" q o r')
_c("op-char-functional", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: Functional")
_c("op-char-inversefunctional", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: InverseFunctional")
_c("op-char-reflexive", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: Reflexive")
_c("op-char-irreflexive", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: Irreflexive")
_c("op-char-symmetric", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: Symmetric")
_c("op-char-asymmetric", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: Asymmetric")
_c("op-char-transitive", "objectPropertyCharacteristic", "ObjectProperty: p\n  Characteristics: Transitive")
_c("op-char-list", "objectPropertyCharacteristicAnnotatedList", "ObjectProperty: p\n  Characteristics: Functional, Transitive, Symmetric")
_c("op-char-annotated", "annotations", 'ObjectProperty: p\n  Characteristics: Annotations: note "x" Functional')
_c("op-annotations", "annotationAnnotatedList", 'ObjectProperty: p\n  Annotations: note "a"')
_c("op-all-clauses", "objectPropertyFrame",
   'ObjectProperty: p\n  Annotations: note "x"\n  Domain: A\n  Range: B\n  Characteristics: Functional\n  SubPropertyOf: q\n  EquivalentTo: r\n  InverseOf: q\n  DisjointWith: r')

# ---------------------------------------------------------------------------
# Data property frame clauses
# ---------------------------------------------------------------------------
_c("dp-domain", "dataPropertyFrame", "DataProperty: d\n  Domain: A")
_c("dp-range-atomic", "dataPropertyFrame dataRangeAnnotatedList", "DataProperty: d\n  Range: xsd:integer")
_c("dp-range-list", "dataRangeAnnotatedList", "DataProperty: d\n  Range: xsd:integer, xsd:decimal")
_c("dp-range-annotated", "annotations", 'DataProperty: d\n  Range: Annotations: note "x" xsd:integer')
_c("dp-characteristics-functional", "dataPropertyFrame", "DataProperty: d\n  Characteristics: Functional")
_c("dp-characteristics-annotated", "annotations", 'DataProperty: d\n  Characteristics: Annotations: note "x" Functional')
_c("dp-subpropertyof", "dataPropertyExpressionAnnotatedList", "DataProperty: d\n  SubPropertyOf: e")
_c("dp-subpropertyof-annotated", "annotations", 'DataProperty: d\n  SubPropertyOf: Annotations: note "x" e')
_c("dp-equivalentto", "dataPropertyFrame", "DataProperty: d\n  EquivalentTo: e")
_c("dp-disjointwith", "dataPropertyFrame", "DataProperty: d\n  DisjointWith: e")
_c("dp-annotations", "annotationAnnotatedList", 'DataProperty: d\n  Annotations: note "a"')
_c("dp-all-clauses", "dataPropertyFrame",
   'DataProperty: d\n  Annotations: note "x"\n  Domain: A\n  Range: xsd:integer\n  Characteristics: Functional\n  SubPropertyOf: e')

# ---------------------------------------------------------------------------
# Annotation property frame clauses
# ---------------------------------------------------------------------------
_c("ap-annotations", "annotationPropertyFrame", 'AnnotationProperty: note\n  Annotations: note2 "meta"')
_c("ap-domain", "annotationPropertyFrame IRIAnnotatedList", "AnnotationProperty: note\n  Domain: <http://example.org/o#A>")
_c("ap-domain-abbreviated", "IRIAnnotatedList", "AnnotationProperty: note\n  Domain: :A")
_c("ap-range", "annotationPropertyFrame", "AnnotationProperty: note\n  Range: <http://example.org/o#B>")
_c("ap-subpropertyof", "annotationPropertyIRIAnnotatedList", "AnnotationProperty: note\n  SubPropertyOf: note2")
_c("ap-subpropertyof-annotated", "annotations", 'AnnotationProperty: note\n  SubPropertyOf: Annotations: note2 "x" rdfs:label')
_c("ap-domain-annotated", "annotations", 'AnnotationProperty: note\n  Domain: Annotations: note2 "x" :A')
_c("ap-all-clauses", "annotationPropertyFrame",
   'AnnotationProperty: note\n  Annotations: note2 "x"\n  Domain: :A\n  Range: :B\n  SubPropertyOf: note2')

# ---------------------------------------------------------------------------
# Individual frame clauses
# ---------------------------------------------------------------------------
_c("ind-types", "individualFrame", "Individual: i\n  Types: A")
_c("ind-types-complex", "descriptionAnnotatedList", "Individual: i\n  Types: A and p some B")
_c("ind-types-list", "descriptionAnnotatedList", "Individual: i\n  Types: A, B")
_c("ind-types-annotated", "annotations", 'Individual: i\n  Types: Annotations: note "x" A')
_c("ind-fact-object", "fact objectPropertyFact factAnnotatedList", "Individual: i\n  Facts: p j")
_c("ind-fact-data", "dataPropertyFact", 'Individual: i\n  Facts: d "x"')
_c("ind-fact-data-typed", "dataPropertyFact", "Individual: i\n  Facts: d 5")
_c("ind-fact-negative-object", "fact", "Individual: i\n  Facts: not p j")
_c("ind-fact-negative-data", "fact", 'Individual: i\n  Facts: not d "x"')
_c("ind-fact-list", "factAnnotatedList", 'Individual: i\n  Facts: p j, p k, d 5, not d 6')
_c("ind-fact-annotated-object", "annotations", 'Individual: i\n  Facts: Annotations: note "x" p j')
_c("ind-fact-annotated-data", "annotations", 'Individual: i\n  Facts: Annotations: note "x" d 5')
_c("ind-fact-annotated-negative", "annotations", 'Individual: i\n  Facts: Annotations: note "x" not p j')
_c("ind-sameas", "individualFrame", "Individual: i\n  SameAs: j")
_c("ind-sameas-list", "individualAnnotatedList", "Individual: i\n  SameAs: j, k")
_c("ind-sameas-annotated", "annotations", 'Individual: i\n  SameAs: Annotations: note "x" j')
_c("ind-differentfrom", "individualFrame", "Individual: i\n  DifferentFrom: j")
_c("ind-differentfrom-list", "individualAnnotatedList", "Individual: i\n  DifferentFrom: j, k")
_c("ind-annotations", "annotationAnnotatedList", 'Individual: i\n  Annotations: note "a"')
_c("ind-nodeid-frame", "nodeID individual", "Individual: _:b1\n  Types: A")
_c("ind-nodeid-fact-target", "nodeID objectPropertyFact", "Individual: i\n  Facts: p _:b1")
_c("ind-nodeid-sameas", "nodeID", "Individual: i\n  SameAs: _:b1")
_c("ind-all-clauses", "individualFrame",
   'Individual: i\n  Annotations: note "x"\n  Types: A\n  Facts: p j, d 5\n  SameAs: k\n  DifferentFrom: j')

# ---------------------------------------------------------------------------
# Top-level (misc) axioms
# ---------------------------------------------------------------------------
_c("misc-equivalentclasses-two", "misc description2List", "EquivalentClasses: A, B")
_c("misc-equivalentclasses-three", "description2List", "EquivalentClasses: A, B, C")
_c("misc-equivalentclasses-expressions", "description2List", "EquivalentClasses: A, p some B")
_c("misc-equivalentclasses-annotated", "annotations", 'EquivalentClasses: Annotations: note "x" A, B')
_c("misc-disjointclasses-two", "misc", "DisjointClasses: A, B")
_c("misc-disjointclasses-three", "description2List", "DisjointClasses: A, B, C")
_c("misc-disjointclasses-annotated", "annotations", 'DisjointClasses: Annotations: note "x" A, B, C')
_c("misc-equivalentproperties-object", "objectProperty2List", "EquivalentProperties: p, q")
_c("misc-equivalentproperties-object-three", "objectProperty2List", "EquivalentProperties: p, q, r")
_c("misc-equivalentproperties-data", "dataProperty2List", "EquivalentProperties: d, e")
_c("misc-equivalentproperties-annotated", "annotations", 'EquivalentProperties: Annotations: note "x" p, q')
_c("misc-disjointproperties-object", "misc", "DisjointProperties: p, q")
_c("misc-disjointproperties-object-three", "objectProperty2List", "DisjointProperties: p, q, r")
_c("misc-disjointproperties-data", "dataProperty2List", "DisjointProperties: d, e")
_c("misc-disjointproperties-annotated", "annotations", 'DisjointProperties: Annotations: note "x" p, q, r')
_c("misc-sameindividual-two", "misc individual2List", "SameIndividual: i, j")
_c("misc-sameindividual-three", "individual2List", "SameIndividual: i, j, k")
_c("misc-sameindividual-annotated", "annotations", 'SameIndividual: Annotations: note "x" i, j')
_c("misc-differentindividuals-two", "misc", "DifferentIndividuals: i, j")
_c("misc-differentindividuals-three", "individual2List", "DifferentIndividuals: i, j, k")
_c("misc-differentindividuals-annotated", "annotations", 'DifferentIndividuals: Annotations: note "x" i, j, k')

# ---------------------------------------------------------------------------
# Layout, whitespace and mixed documents
# ---------------------------------------------------------------------------
_c("layout-single-line", "frame", "Class: A SubClassOf: B Class: C SubClassOf: A")
_c("layout-crlf", "frame", "Class: A\r\n  SubClassOf: B\r\n")
_c("layout-tabs", "frame", "Class:\tA\n\tSubClassOf:\tB")
_c("layout-blank-lines", "frame", "Class: A\n\n\n  SubClassOf: B\n\n")
_c("layout-comma-no-space", "descriptionAnnotatedList", "Class: A\n  SubClassOf: B,C,D")
_c("layout-no-space-in-braces", "individualList", "Class: A\n  EquivalentTo: {i,j,k}")
_c("layout-no-space-in-facet", "facet", "DataProperty: d\n  Range: xsd:integer[>=1,<10]")
_c("mixed-document", "frame",
   'Class: A\n  SubClassOf: p some B\nObjectProperty: p\n  Domain: A\n  Range: B\nIndividual: i\n  Types: A\n  Facts: p j\n'
   'DisjointClasses: A, B, C\nDataProperty: d\n  Range: xsd:integer[>= 0]')
_c("mixed-misc-between-frames", "frame misc", "Class: A\nDisjointClasses: B, C\nClass: D\n  SubClassOf: A")
