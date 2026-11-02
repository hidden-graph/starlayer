"""Positive corpus for the SRL conformance suite.

Each ``Case`` names the grammar productions of the SPARQL 1.2 RL draft (W3C WD 14 October 2026, section
7.6) that it exercises (``covers``); the coverage-matrix test fails if any production is exercised by no case
or a case names a production that is not in the grammar table. Cases are small and one construct each, so a
failure points at one production.
"""

from __future__ import annotations

from dataclasses import dataclass

PRELUDE = """\
PREFIX : <http://example.org/>
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
"""


@dataclass(frozen=True)
class Case:
    id: str
    covers: tuple[str, ...]
    body: str
    prelude: bool = True

    @property
    def text(self) -> str:
        return (PRELUDE + self.body) if self.prelude else self.body


CASES: list[Case] = []


def _c(id: str, covers: str, body: str, *, prelude: bool = True) -> None:
    CASES.append(Case(id, tuple(covers.split()), body.rstrip("\n") + "\n", prelude=prelude))


R = "RULE { ?x :p ?y } WHERE { ?x :q ?y }"

# --- document and prologue ----------------------------------------------------------------------------
_c("doc-empty", "RuleSet RuleOrDataBlock Prologue", "")
_c("doc-prefix-only", "PrefixDecl PNAME_NS IRIREF Prologue1", "PREFIX ex: <http://example.org/ex#>")
_c("doc-base", "BaseDecl IRIREF", "BASE <http://example.org/base/>\nRULE { ?x <p> ?y } WHERE { ?x <q> ?y }")
_c("doc-version-double", "VersionDecl VersionSpecifier STRING_LITERAL2", 'VERSION "1.2"\n' + R)
_c("doc-version-single", "VersionSpecifier STRING_LITERAL1", "VERSION '1.2'\n" + R)
_c("doc-imports", "ImportsDecl iri", "IMPORTS <http://example.org/other>\n" + R)
_c("doc-imports-prefixed", "ImportsDecl PrefixedName", "IMPORTS :other\n" + R)
_c("doc-prologue-after-rule", "RuleOrDataBlock Prologue1 RuleOrData",
   R + "\nPREFIX ex: <http://example.org/ex#>\nRULE { ?x ex:p ?y } WHERE { ?x ex:q ?y }")
_c("doc-prologue-between-three", "RuleOrDataBlock",
   R + "\nPREFIX a: <http://a/>\n" + R + "\nBASE <http://b/>\n" + R)
_c("doc-rule-then-data", "RuleOrData Rule Data", R + "\nDATA { :a :b :c }")
_c("doc-data-then-rule", "RuleOrData", "DATA { :a :b :c }\n" + R)
_c("doc-comments", "WS", "# a comment\n" + R + " # trailing\n")

# --- rules ---------------------------------------------------------------------------------------------
_c("rule-minimal", "Rule HeadTemplate BodyPattern", R)
_c("rule-id-iri", "Rule iri IRIREF", "RULE <http://example.org/r1> { ?x :p ?y } WHERE { ?x :q ?y }")
_c("rule-id-prefixed", "Rule PrefixedName PNAME_LN", "RULE :r1 { ?x :p ?y } WHERE { ?x :q ?y }")
_c("rule-id-pname-ns", "PNAME_NS", "RULE : { ?x :p ?y } WHERE { ?x :q ?y }")
_c("rule-where-data", "Rule", "RULE { ?x :p ?y } WHERE DATA { ?x :q ?y }")
_c("rule-empty-head", "HeadTemplate", "RULE { } WHERE { ?x :q ?y }")
_c("rule-empty-body", "BodyPattern", "RULE { :a :b :c } WHERE { }")
_c("rule-lowercase-keywords", "Rule", "rule { ?x :p ?y } where { ?x :q ?y }")
_c("rule-many", "RuleOrData", "\n".join(f"RULE {{ ?x :p{i} ?y }} WHERE {{ ?x :q{i} ?y }}" for i in range(4)))

# --- body elements -------------------------------------------------------------------------------------
_c("body-filter-brackets", "Filter Constraint BrackettedExpression BodyNotTriples", "RULE { ?x :p ?y } WHERE { ?x :q ?y FILTER (?y > 1) }")
_c("body-filter-builtin", "Constraint BuiltInCall", "RULE { ?x :p ?y } WHERE { ?x :q ?y FILTER isIRI(?y) }")
_c("body-filter-function", "Constraint FunctionCall ArgList", "RULE { ?x :p ?y } WHERE { ?x :q ?y FILTER xsd:integer(?y) }")
_c("body-filter-function-nil", "FunctionCall NIL", "RULE { ?x :p ?y } WHERE { ?x :q ?y FILTER :f() }")
_c("body-filter-multiple", "BodyNotTriples", "RULE { ?x :p ?y } WHERE { ?x :q ?y FILTER (?y > 1) FILTER (?y < 9) }")
_c("body-triples-between-elements", "BodyPattern BodyTriplesBlock",
   "RULE { ?x :p ?z } WHERE { ?x :q ?y FILTER (?y > 1) ?x :r ?z }")
_c("body-dot-after-filter", "BodyPattern", "RULE { ?x :p ?y } WHERE { ?x :q ?y . FILTER (?y > 1) . ?x :r ?z . }")
_c("body-not", "Negation BodyBasic", "RULE { ?x :p ?y } WHERE { ?x :q ?y NOT { ?x :r ?y } }")
_c("body-not-data", "Negation", "RULE { ?x :p ?y } WHERE { ?x :q ?y NOT DATA { ?x :r ?y } }")
_c("body-not-filter", "BodyBasicNotTriples", "RULE { ?x :p ?y } WHERE { ?x :q ?y NOT { ?x :r ?z FILTER (?z > ?y) } }")
_c("body-not-several-patterns", "BodyBasic", "RULE { ?x :p ?y } WHERE { ?x :q ?y NOT { ?x :r ?z . ?z :s ?y } }")
_c("body-not-empty", "Negation", "RULE { ?x :p ?y } WHERE { ?x :q ?y NOT { } }")
_c("body-set", "Assignment", "RULE { ?x :p ?z } WHERE { ?x :q ?y SET (?z := ?y + 1) }")
_c("body-set-chain", "Assignment", "RULE { ?x :p ?w } WHERE { ?x :q ?y SET (?z := ?y + 1) SET (?w := ?z * 2) }")
_c("body-set-dollar-var", "VAR2", "RULE { ?x :p $z } WHERE { ?x :q $y SET ($z := $y + 1) }")
_c("body-all-elements", "BodyNotTriples",
   "RULE { ?x :p ?w } WHERE { ?x :q ?y FILTER (?y > 0) NOT { ?x :r ?y } SET (?w := ?y * 2) }")

# --- triple patterns: paths, lists, blank nodes ------------------------------------------------------
_c("pat-a-verb", "TriplesBlockPattern Verb VerbPath PathElt", "RULE { ?x a :C } WHERE { ?x a :D }")
_c("pat-var-verb", "PropertyListNotEmptyPattern Var", "RULE { ?x ?p ?y } WHERE { ?x ?p ?y }")
_c("pat-path-sequence", "Path PathSequence PathEltOrInverse", "RULE { ?x :p ?z } WHERE { ?x :a/:b ?z }")
_c("pat-path-inverse", "PathEltOrInverse", "RULE { ?x :p ?z } WHERE { ?x ^:a ?z }")
_c("pat-path-inverse-in-sequence", "PathSequence", "RULE { ?x :p ?z } WHERE { ?x :a/^:b/:c ?z }")
_c("pat-path-group", "PathElt", "RULE { ?x :p ?z } WHERE { ?x (:a/:b)/:c ?z }")
_c("pat-path-a", "PathElt", "RULE { ?x :p ?z } WHERE { ?x a/:b ?z }")
_c("pat-predicate-object-lists", "PropertyListNotEmptyPattern ObjectListPattern ObjectPattern",
   "RULE { ?x :p ?y } WHERE { ?x :a ?y, ?z ; :b ?w }")
_c("pat-trailing-semicolon", "PropertyListPattern", "RULE { ?x :p ?y } WHERE { ?x :a ?y ; }")
_c("pat-blank-property-list", "BlankNodePropertyListPattern TriplesNodePattern", "RULE { ?x :p ?y } WHERE { [ :a ?x ; :b ?y ] :c ?z }")
_c("pat-blank-property-list-object", "GraphNodePattern", "RULE { ?x :p ?y } WHERE { ?x :a [ :b ?y ] }")
_c("pat-collection", "CollectionPattern", "RULE { ?x :p ?y } WHERE { ?x :a (?y ?z) }")
_c("pat-collection-subject", "TriplesSameSubjectPattern", "RULE { ?y :p ?z } WHERE { (?y ?z) :a :b }")
_c("pat-nil", "NIL", "RULE { ?x :p () } WHERE { ?x :q () }")
_c("pat-nil-with-space", "NIL WS", "RULE { ?x :p ( ) } WHERE { ?x :q ( ) }")
_c("pat-anon", "ANON BlankNode", "RULE { ?x :p [] } WHERE { ?x :q [] }")
_c("pat-anon-with-space", "ANON", "RULE { ?x :p [ ] } WHERE { ?x :q [ ] }")
_c("pat-blank-label", "BLANK_NODE_LABEL", "RULE { ?x :p ?y } WHERE { ?x :q _:b1 . _:b1 :r ?y }")
_c("pat-literal-subject-position", "VarOrRDFTerm", "RULE { ?x :p ?y } WHERE { :a :q ?x . ?x :r ?y }")

# --- RDF 1.2: reification, annotations, triple terms -------------------------------------------------
_c("rdf12-reified-triple", "ReifiedTriple ReifiedTripleBlockPattern", "RULE { ?x :p ?y } WHERE { << ?x :q ?y >> :source ?s }")
_c("rdf12-reified-with-reifier-var", "Reifier ReifierId", "RULE { ?x :p ?y } WHERE { << ?x :q ?y ~ ?r >> :source ?s }")
_c("rdf12-reified-with-reifier-iri", "Reifier ReifierId", "RULE { ?x :p ?y } WHERE { << ?x :q ?y ~ :r1 >> :source ?s }")
_c("rdf12-reified-bare-tilde", "Reifier", "RULE { ?x :p ?y } WHERE { << ?x :q ?y ~ >> :source ?s }")
_c("rdf12-reified-as-object", "GraphNodePattern ReifiedTripleObject ReifiedTripleSubject", "RULE { ?x :p ?y } WHERE { ?s :says << ?x :q ?y >> }")
_c("rdf12-reified-nested", "ReifiedTripleSubject", "RULE { ?x :p ?y } WHERE { << << ?x :q ?y >> :r ?z >> :s ?w }")
_c("rdf12-annotation-reifier", "AnnotationPattern ObjectPattern", "RULE { ?x :p ?y } WHERE { ?x :q ?y ~ ?r }")
_c("rdf12-annotation-block", "AnnotationBlockPattern", "RULE { ?x :p ?y } WHERE { ?x :q ?y {| :conf ?c |} }")
_c("rdf12-annotation-both", "AnnotationPattern", "RULE { ?x :p ?y } WHERE { ?x :q ?y ~ ?r {| :conf ?c |} }")
_c("rdf12-triple-term", "TripleTerm TripleTermSubject TripleTermObject", "RULE { ?x :p ?y } WHERE { ?z :a <<( ?x :q ?y )>> }")
_c("rdf12-triple-term-nested", "TripleTermObject", "RULE { ?x :p ?y } WHERE { ?z :a <<( ?x :q <<( ?y :r :s )>> )>> }")
_c("rdf12-triple-term-literal", "ReifiedTripleObject RDFLiteral", 'RULE { ?x :p ?c } WHERE { << ?x :q "v" >> :conf ?c }')
_c("rdf12-triple-term-in-expression", "ExprTripleTerm ExprTripleTermSubject ExprTripleTermObject",
   "RULE { ?x :p ?y } WHERE { ?x :q ?y . ?x :r ?z FILTER (?y = <<( ?x :r ?z )>>) }")
_c("rdf12-triple-term-in-expression-nested", "ExprTripleTermObject",
   "RULE { ?x :p ?y } WHERE { ?x :q ?y . ?x :r ?a . ?a :s ?c FILTER (?y = <<( ?x :r <<( ?a :b ?c )>> )>>) }")

# --- head templates -------------------------------------------------------------------------------------
_c("head-multiple-triples", "GraphNodeTemplate PropertyListTemplate HeadTemplateBlock TriplesBlockTemplate TriplesSameSubjectTemplate", "RULE { ?x :p ?y . ?y :r ?x } WHERE { ?x :q ?y }")
_c("head-lists", "PropertyListNotEmptyTemplate ObjectListTemplate ObjectTemplate", "RULE { ?x :p ?y, :c ; :r ?y } WHERE { ?x :q ?y }")
_c("head-blank-property-list", "BlankNodePropertyListTemplate TriplesNodeTemplate", "RULE { [ :a ?x ; :b ?y ] :c :d } WHERE { ?x :q ?y }")
_c("head-collection", "CollectionTemplate", "RULE { ?x :p (?y 1 2) } WHERE { ?x :q ?y }")
_c("head-annotation", "AnnotationTemplate AnnotationBlockTemplate", "RULE { ?x :p ?y {| :conf 0.9 |} } WHERE { ?x :q ?y }")
_c("head-reifier", "AnnotationTemplate Reifier", "RULE { ?x :p ?y ~ :r1 } WHERE { ?x :q ?y }")
_c("head-reified-triple", "ReifiedTripleBlockTemplate", "RULE { << ?x :p ?y >> :source :s } WHERE { ?x :q ?y }")
_c("head-triple-term", "TripleTerm", "RULE { ?x :says <<( ?y :p ?z )>> } WHERE { ?x :q ?y . ?y :r ?z }")
_c("head-a", "Verb", "RULE { ?x a :C } WHERE { ?x :q ?y }")
_c("head-var-predicate", "VarOrIri", "RULE { ?x ?p ?y } WHERE { ?x ?p ?y }")
_c("head-trailing-dot", "TriplesBlockTemplate", "RULE { ?x :p ?y . } WHERE { ?x :q ?y }")

# --- data blocks ----------------------------------------------------------------------------------------
_c("data-empty", "Data", "DATA { }")
_c("data-simple", "PropertyListData DataTriplesBlock TriplesSameSubjectData RDFTermData", "DATA { :a :b :c }")
_c("data-lists", "PropertyListNotEmptyData ObjectListData ObjectData VerbData", "DATA { :a :b :c, :d ; a :C }")
_c("data-multiple", "DataTriplesBlock", "DATA { :a :b :c . :d :e :f . }")
_c("data-blank-property-list", "BlankNodePropertyListData TriplesNodeData", "DATA { [ :a :b ] :c :d }")
_c("data-collection", "CollectionData GraphNodeData", "DATA { :a :b (1 2 3) }")
_c("data-nil-subject", "NIL", "DATA { () :a :b }")
_c("data-annotation", "AnnotationData AnnotationBlockData", "DATA { :a :b :c {| :conf 0.9 |} }")
_c("data-reifier", "ReifierData ReifierIdData", "DATA { :a :b :c ~ :r1 }")
_c("data-reifier-blank", "ReifierIdData", "DATA { :a :b :c ~ _:r }")
_c("data-reified-triple", "ReifiedTripleData ReifiedTripleBlockData ReifiedTripleSubjectData ReifiedTripleObjectData", "DATA { << :a :b :c >> :source :s }")
_c("data-reified-with-reifier", "ReifiedTripleData", "DATA { << :a :b :c ~ :r1 >> :source :s }")
_c("data-triple-term", "TripleTermData TripleTermSubjectData TripleTermObjectData", "DATA { :s :says <<( :a :b :c )>> }")
_c("data-triple-term-nested", "TripleTermObjectData", "DATA { :s :says <<( :a :b <<( :c :d :e )>> )>> }")
_c("data-literals-subject-object", "RDFTermData", 'DATA { :a :b "x", 1, true }')

# --- literals, names, variables -----------------------------------------------------------------------
_c("lit-plain", "RDFLiteral String STRING_LITERAL2", 'DATA { :a :b "text" }')
_c("lit-single-quote", "STRING_LITERAL1", "DATA { :a :b 'text' }")
_c("lit-long-double", "STRING_LITERAL_LONG2", 'DATA { :a :b """line one\nline "two" """ }')
_c("lit-long-single", "STRING_LITERAL_LONG1", "DATA { :a :b '''line one\nline 'two' ''' }")
_c("lit-escapes", "ECHAR", r'DATA { :a :b "tab\t nl\n quote\" back\\ ap\' b\b r\r f\f" }')
_c("lit-unicode-escape", "UCHAR HEX", r'DATA { :a :b "é \U0001F600" }')
_c("lit-lang", "LANG_DIR", 'DATA { :a :b "chat"@fr }')
_c("lit-lang-region", "LANG_DIR", 'DATA { :a :b "colour"@en-GB }')
_c("lit-lang-dir", "LANG_DIR", 'DATA { :a :b "hello"@en--ltr, "shalom"@he--rtl }')
_c("lit-typed", "RDFLiteral", 'DATA { :a :b "5"^^xsd:integer }')
_c("lit-typed-iri", "RDFLiteral IRIREF", 'DATA { :a :b "5"^^<http://www.w3.org/2001/XMLSchema#integer> }')
_c("lit-integer", "NumericLiteral NumericLiteralUnsigned INTEGER", "DATA { :a :b 42 }")
_c("lit-decimal", "DECIMAL", "DATA { :a :b 4.2, .5 }")
_c("lit-double", "DOUBLE", "DATA { :a :b 4.2e3, 1E-2, .5e1, 7e0 }")
_c("lit-positive", "NumericLiteralPositive INTEGER_POSITIVE DECIMAL_POSITIVE DOUBLE_POSITIVE", "DATA { :a :b +1, +1.5, +1e3 }")
_c("lit-negative", "NumericLiteralNegative INTEGER_NEGATIVE DECIMAL_NEGATIVE DOUBLE_NEGATIVE", "DATA { :a :b -1, -1.5, -1e3 }")
_c("lit-boolean", "BooleanLiteral", "DATA { :a :b true, false }")
_c("iri-full", "iri IRIREF", "DATA { <http://example.org/a> <http://example.org/b> <http://example.org/c> }")
_c("iri-uchar", "UCHAR", r"DATA { <http://example.org/é> :b :c }")
_c("iri-pname-escapes", "PN_LOCAL_ESC PN_LOCAL PLX", r"DATA { :a\-b :c\.d :e }")
_c("iri-pname-percent", "PERCENT", "DATA { :a%20b :c :d }")
_c("iri-pname-colon-and-digit", "PN_LOCAL", "DATA { :1a :b:c :d }")
_c("iri-pname-prefix", "PN_PREFIX PN_CHARS PN_CHARS_BASE PN_CHARS_U",
   "PREFIX ab.c-d: <http://example.org/abcd#>\nDATA { ab.c-d:x ab.c-d:y ab.c-d:z }")
_c("var-question", "Var VAR1 VARNAME", "RULE { ?x1 :p ?y_2 } WHERE { ?x1 :q ?y_2 }")
_c("var-unicode-name", "VARNAME", "RULE { ?é :p ?y } WHERE { ?é :q ?y }")
_c("var-digit-start", "VARNAME", "RULE { ?1 :p ?y } WHERE { ?1 :q ?y }")

# --- expressions ----------------------------------------------------------------------------------------
def _expr(id: str, covers: str, expr: str) -> None:
    _c(id, covers, f"RULE {{ ?x :p ?y }} WHERE {{ ?x :q ?y FILTER ({expr}) }}")


_expr("expr-or", "Expression ConditionalOrExpression", "?y > 1 || ?y < 0")
_expr("expr-and", "ConditionalAndExpression ValueLogical", "?y > 0 && ?y < 9")
_expr("expr-or-and-precedence", "ConditionalOrExpression", "?y = 1 || ?y = 2 && ?y = 3")
_expr("expr-relational-eq", "RelationalExpression NumericExpression", "?y = 1")
_expr("expr-relational-ne", "RelationalExpression", "?y != 1")
_expr("expr-relational-lt", "RelationalExpression", "?y < 1")
_expr("expr-relational-gt", "RelationalExpression", "?y > 1")
_expr("expr-relational-le", "RelationalExpression", "?y <= 1")
_expr("expr-relational-ge", "RelationalExpression", "?y >= 1")
_expr("expr-in", "RelationalExpression ExpressionList", "?y IN (1, 2, 3)")
_expr("expr-not-in", "RelationalExpression", "?y NOT IN (1, 2)")
_expr("expr-in-empty", "ExpressionList NIL", "?y IN ()")
_expr("expr-additive", "AdditiveExpression MultiplicativeExpression", "?y + 1 - 2 > 0")
_expr("expr-additive-signed-literal", "AdditiveExpression NumericLiteralPositive", "?y +1 > 0")
_expr("expr-additive-signed-literal-mult", "AdditiveExpression", "?y +1 * 2 > 0")
_expr("expr-multiplicative", "MultiplicativeExpression UnaryExpression", "?y * 2 / 4 > 0")
_expr("expr-unary-not", "UnaryExpression PrimaryExpression", "!isBLANK(?y)")
_expr("expr-unary-plus", "UnaryExpression", "+?y > 0")
_expr("expr-unary-minus", "UnaryExpression", "-?y < 0")
_expr("expr-parens", "BrackettedExpression", "(?y + 1) * 2 > 0")
_expr("expr-nested-function", "iriOrFunction", "xsd:integer(?y) > 0")
_expr("expr-iri-as-value", "iriOrFunction", "?y = :c")
_expr("expr-function-two-args", "iriOrFunction ArgList", ":f(?y, 2) > 0")
_expr("expr-literal-forms", "PrimaryExpression RDFLiteral NumericLiteral BooleanLiteral", '?y = "a" || ?y = 1 || ?y = true')
_expr("expr-builtin-nesting", "BuiltInCall", "STRLEN(STR(?y)) > 1")
_expr("expr-bnode-nil", "BuiltInCall NIL", "isBLANK(BNODE())")
_expr("expr-bnode-arg", "BuiltInCall", "isBLANK(BNODE(?y))")
_c("expr-set-arith", "Assignment Expression", "RULE { ?x :p ?z } WHERE { ?x :q ?y SET (?z := (?y + 1) * 2 - ?y / 4) }")
