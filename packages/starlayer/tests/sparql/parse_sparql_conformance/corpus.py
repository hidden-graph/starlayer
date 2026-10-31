"""One or more cases per SPARQL 1.2 Query production.

A case is a query text, the productions it exercises (``covers``) and whether it must parse. ``covers`` is checked
two ways in ``test_coverage_matrix.py``: every name must be a production of the vendored grammar, and for the
productions that have a dedicated method in ``parse_sparql._Parser`` that method must actually run on the case.
"""

from __future__ import annotations

from typing import NamedTuple

P = "PREFIX : <http://e/>\n"


class Case(NamedTuple):
    id: str
    text: str
    covers: tuple[str, ...]
    ok: bool = True


def _c(id: str, text: str, covers: str, ok: bool = True) -> Case:
    return Case(id, text, tuple(covers.split()), ok)


CASES: list[Case] = [
    # -- prologue, query forms ---------------------------------------------------------------------------
    _c("prologue", 'VERSION "1.2" BASE <http://b/> PREFIX p: <http://e/#> ASK { p:s p:p <o> }',
       "QueryUnit Query Prologue BaseDecl PrefixDecl VersionDecl VersionSpecifier IRIREF PNAME_NS AskQuery PNAME_LN"),
    _c("version-single-quote", "VERSION '1.2' ASK {}", "VersionSpecifier STRING_LITERAL1"),
    _c("select", P + "SELECT DISTINCT ?x $y (1 AS ?z) { ?x :p ?y }", "SelectQuery SelectClause Var VAR1 VAR2"),
    _c("select-star-reduced", P + "SELECT REDUCED * { ?x :p ?y }", "SelectClause"),
    _c("sub-select", P + "SELECT * { { SELECT ?x { ?x :p ?y } ORDER BY ?x VALUES ?x { :a } } }", "SubSelect"),
    _c("construct", P + "CONSTRUCT { ?x :q [ :r ?y ] } WHERE { ?x :p ?y } LIMIT 3",
       "ConstructQuery ConstructTemplate ConstructTriples"),
    _c("construct-where", P + "CONSTRUCT WHERE { ?x :p ?y }", "ConstructQuery TriplesTemplate"),
    _c("describe", P + "DESCRIBE ?x :a FROM <g> { ?x :p ?y }", "DescribeQuery VarOrIri"),
    _c("describe-star-no-where", "DESCRIBE <http://x>", "DescribeQuery"),
    _c("describe-star", P + "DESCRIBE * { ?x :p ?y }", "DescribeQuery"),
    _c("ask-modifiers", P + "ASK { ?x :p ?y } ORDER BY ?x LIMIT 1", "AskQuery SolutionModifier"),
    _c("dataset", P + "SELECT * FROM <g1> FROM NAMED <g2> WHERE { ?x :p ?y }",
       "DatasetClause DefaultGraphClause NamedGraphClause SourceSelector WhereClause"),
    # -- solution modifiers -----------------------------------------------------------------------------------
    _c("group-having", P + "SELECT ?x (COUNT(*) AS ?c) { ?x :p ?y } GROUP BY ?x HAVING (COUNT(*) > 1)",
       "SolutionModifier GroupClause GroupCondition HavingClause HavingCondition"),
    _c("group-expr-call", P + "SELECT (COUNT(*) AS ?c) { ?x :p ?y } GROUP BY (STR(?x) AS ?k) (?y) STR(?y) :f(?x) ?x",
       "GroupCondition BuiltInCall FunctionCall"),
    _c("order", P + "SELECT * { ?x :p ?y } ORDER BY ASC(?x) DESC(?y) ?x STR(?y) (?y + 1) :f(?x)",
       "OrderClause OrderCondition Constraint"),
    _c("limit-offset", P + "SELECT * { ?x :p ?y } OFFSET 1 LIMIT 2", "LimitOffsetClauses LimitClause OffsetClause"),
    _c("limit-offset-2", P + "SELECT * { ?x :p ?y } LIMIT 2 OFFSET 1", "LimitOffsetClauses"),
    _c("values-trailing", P + "SELECT * { ?x :p ?y } VALUES ?x { :a UNDEF }", "ValuesClause"),
    # -- group graph patterns ---------------------------------------------------------------------------------
    _c("group-elements",
       P + "SELECT * { ?x :p ?y . OPTIONAL { ?y :q ?z } MINUS { ?x :r 1 } FILTER (?y) BIND (1 AS ?b) "
           "GRAPH ?g { ?x :s ?w } SERVICE SILENT <http://s> { ?x :t ?u } { ?x :a 1 } UNION { ?x :b 2 } VALUES ?v { 1 } }",
       "GroupGraphPattern GroupGraphPatternSub GraphPatternNotTriples OptionalGraphPattern MinusGraphPattern Filter Bind "
       "GraphGraphPattern ServiceGraphPattern GroupOrUnionGraphPattern InlineData TriplesBlock"),
    _c("service-var", P + "SELECT * { SERVICE ?s { ?x :p ?y } }", "ServiceGraphPattern"),
    _c("values-forms", P + "SELECT * { VALUES ?a { 1 } VALUES (?a ?b) { (1 2) (UNDEF :c) } VALUES () { () } VALUES (?c) { }  }",
       "InlineData DataBlock InlineDataOneVar InlineDataFull NIL DataBlockValue"),
    _c("values-data", P + 'SELECT * { VALUES ?a { :i "s" "t"@en 1 1.5 1e0 true <<( :s :p :o )>> } }',
       "DataBlockValue TripleTermData TripleTermDataSubject TripleTermDataObject"),
    _c("values-data-nested", P + "SELECT * { VALUES ?a { <<( :s a <<( :s2 :p2 1 )>> )>> } }", "TripleTermData"),
    # -- triples ------------------------------------------------------------------------------------------------------
    _c("triples-lists", P + 'SELECT * { ?x a :C ; :p ?y , ?z ; . ?x :q [ :r 1 ] , ( 1 2 ) . [ :s 3 ] :t 4 . ( 5 ) :u 6 }',
       "TriplesSameSubjectPath PropertyListPath PropertyListPathNotEmpty VerbPath VerbSimple ObjectListPath ObjectPath "
       "GraphNodePath TriplesNodePath BlankNodePropertyListPath CollectionPath VarOrTerm"),
    _c("template-triples", P + "CONSTRUCT { ?x a :C ; :p ?y , ?z . [ :s 3 ] :t ( 4 ) . ( 5 ) :u 6 . :a :b :c {| :d :e |} } WHERE {}",
       "TriplesSameSubject PropertyList PropertyListNotEmpty Verb ObjectList Object GraphNode TriplesNode "
       "BlankNodePropertyList Collection Annotation AnnotationBlock"),
    _c("template-collection-subject", P + "CONSTRUCT { ( 1 ) :p 2 } WHERE {}", "Collection TriplesNode"),
    _c("template-anon-subject", P + "CONSTRUCT { [] :p [] } WHERE {}", "BlankNode ANON"),
    _c("property-paths", P + "SELECT * { ?x (:a|:b)/^:c*/:d+ ?y . ?x :e? ?y . ?x !:f ?y . ?x !(:g|^:h|a) ?y . ?x !() ?y . ?x a ?y }",
       "Path PathAlternative PathSequence PathElt PathEltOrInverse PathMod PathPrimary PathNegatedPropertySet "
       "PathOneInPropertySet"),
    _c("reified-triple", P + "SELECT * { << ?s :p ?o ~ :r >> :q ?z . << :s :p <<( :a :b :c )>> >> :q 1 }",
       "ReifiedTripleBlock ReifiedTripleBlockPath ReifiedTriple ReifiedTripleSubject ReifiedTripleObject Reifier VarOrReifierId"),
    _c("reified-nested", P + "SELECT * { << << ?s :p ?o >> :q 1 >> :r ?z }", "ReifiedTripleSubject ReifiedTripleObject"),
    _c("reified-in-template", P + "CONSTRUCT { << :s :p 1 >> :q 2 } WHERE {}", "ReifiedTripleBlock ReifiedTriple"),
    _c("reifier-forms", P + "SELECT * { ?s :p ?o ~ ~ :r ~ ?v ~ _:b }", "Reifier VarOrReifierId AnnotationPath"),
    _c("annotation", P + "SELECT * { ?s :p ?o {| :a :b ; :c [ :d 1 ] |} ~ :r {| :e 2 |} }",
       "AnnotationPath AnnotationBlockPath"),
    _c("triple-term", P + "SELECT * { ?s :p <<( ?x :q <<( :a :b 1 )>> )>> . <<( _:b :p :o )>> :q ?z }",
       "TripleTerm TripleTermSubject TripleTermObject"),
    _c("var-or-iri", P + "SELECT * { :s ?p :o . ?s :p :o }", "VarOrIri VarOrTerm"),
    _c("literals", P + 'SELECT * { ?s :p "a" , \'b\' , """c""" , \'\'\'d\'\'\' , "e"@en-US , "f"@ar--rtl , "g"^^:t , 1 , 1.5 , 1e3 , '
                       '+1 , +1.5 , +1e3 , -1 , -1.5 , -1e3 , true , false }',
       "RDFLiteral String NumericLiteral NumericLiteralUnsigned NumericLiteralPositive NumericLiteralNegative BooleanLiteral "
       "STRING_LITERAL1 STRING_LITERAL2 STRING_LITERAL_LONG1 STRING_LITERAL_LONG2 LANG_DIR INTEGER DECIMAL DOUBLE EXPONENT "
       "INTEGER_POSITIVE DECIMAL_POSITIVE DOUBLE_POSITIVE INTEGER_NEGATIVE DECIMAL_NEGATIVE DOUBLE_NEGATIVE"),
    _c("blank-nodes", P + "SELECT * { _:a :p [] . _:a :q _:b }", "BlankNode BLANK_NODE_LABEL ANON"),
    _c("nil-subject", P + "SELECT * { () :p () }", "NIL"),
    _c("nil-with-space", P + "SELECT * { ( ) :p ( \t) }", "NIL WS"),
    _c("anon-with-space", P + "SELECT * { [ ] :p [\n] }", "ANON WS"),
    # -- expressions --------------------------------------------------------------------------------------------------------
    _c("filter-forms", P + "SELECT * { ?x :p ?y FILTER (?y > 1) FILTER STR(?y) FILTER :f(?y) FILTER :g() FILTER :h(DISTINCT ?y, 2) }",
       "Filter Constraint FunctionCall ArgList BrackettedExpression BuiltInCall"),
    _c("expression-operators",
       P + "SELECT * { ?x :p ?y FILTER (!?y || ?y && 1 = 1 || 2 != 3 || 1 < 2 || 1 > 2 || 1 <= 2 || 1 >= 2 || ?y IN (1, 2) "
           "|| ?y NOT IN () || 1 + 2 - 3 * 4 / 5 || +?y || -?y || ?y -1 || ?y +1 * 2 || ?y -1 / 2) }",
       "Expression ConditionalOrExpression ConditionalAndExpression ValueLogical RelationalExpression NumericExpression "
       "AdditiveExpression MultiplicativeExpression UnaryExpression PrimaryExpression ExpressionList"),
    _c("double-negation", P + "SELECT * { ?x :p ?y FILTER (!!?y) }", "UnaryExpression"),
    _c("iri-or-function", P + "SELECT * { ?x :p ?y FILTER (:f(?y) = :c) }", "iriOrFunction"),
    _c("expr-triple-term", P + "SELECT * { ?x :p ?y FILTER (?y = <<( ?x :q <<( :a :b 1 )>> )>>) }",
       "ExprTripleTerm ExprTripleTermSubject ExprTripleTermObject"),
    _c("regex-substr-replace", P + 'SELECT * { ?x :p ?y FILTER (REGEX(?y, "a") && REGEX(?y, "a", "i") && SUBSTR(?y, 1) = SUBSTR(?y, 1, 2) && '
                              'REPLACE(?y, "a", "b") = REPLACE(?y, "a", "b", "i")) }',
       "BuiltInCall RegexExpression SubstringExpression StrReplaceExpression"),
    _c("exists", P + "SELECT * { ?x :p ?y FILTER EXISTS { ?x :q 1 } FILTER NOT EXISTS { ?x :r 2 } }", "ExistsFunc NotExistsFunc"),
    _c("aggregates",
       P + "SELECT (COUNT(*) AS ?a) (COUNT(DISTINCT ?x) AS ?b) (SUM(?y) AS ?c) (MIN(?y) AS ?d) (MAX(?y) AS ?e) (AVG(?y) AS ?f) "
           "(SAMPLE(?y) AS ?g) (GROUP_CONCAT(DISTINCT ?y ; SEPARATOR = \";\") AS ?h) (GROUP_CONCAT(?y) AS ?i) { ?x :p ?y }",
       "Aggregate"),
    _c("pn-chars", "PREFIX é_x.y-z·: <http://e/> SELECT * { ?é é_x.y-z·:a·.b ?_0 }",
       "PN_CHARS_BASE PN_CHARS_U PN_CHARS PN_PREFIX VARNAME PN_LOCAL"),
    _c("pn-local-plx", P + "SELECT * { :a%20b :a\\~b :1 . :_ :a:b ?x }", "PLX PERCENT HEX PN_LOCAL_ESC PN_LOCAL"),
    _c("string-escapes", P + 'SELECT * { ?x :p "\\t\\b\\n\\r\\f\\"\\\'\\\\\\u0041\\U00000042" }', "ECHAR UCHAR"),
    _c("iri-uchar", P + "SELECT * { <http://e/\\u0061> :p <http://e/\\U00000062> }", "UCHAR IRIREF"),
    _c("pname-ns-only", P + "SELECT * { : : : }", "PNAME_NS PrefixedName iri"),
    _c("prefixed-and-iriref", P + "SELECT * { <http://a> :p <b> }", "PrefixedName iri IRIREF"),
]

# One row of the grammar is exercised by several cases above; the rows with a dedicated parser method are also
# checked by tracing (test_coverage_matrix). The cases below are the negative side of a few productions.
CASES += [
    _c("bad-prefix-decl", "PREFIX a:b: <http://e/> ASK {}", "PrefixDecl", ok=False),
    _c("bad-version", 'VERSION """1.2""" ASK {}', "VersionDecl", ok=False),
    _c("bad-limit", P + "SELECT * { ?x :p ?y } LIMIT 1.5", "LimitClause", ok=False),
    _c("bad-describe-empty", "DESCRIBE", "DescribeQuery", ok=False),
    _c("bad-sub-select-dataset", P + "SELECT * { SELECT * FROM <g> { ?x :p ?y } }", "SubSelect", ok=False),
    _c("bad-values-arity", P + "SELECT * { VALUES (?a ?b) { (1) } }", "InlineDataFull", ok=False),
    _c("bad-path-in-template", P + "CONSTRUCT { ?x :a/:b ?y } WHERE {}", "ConstructTriples", ok=False),
    _c("bad-annotation-on-path", P + "SELECT * { ?x :a/:b ?y {| :c 1 |} }", "AnnotationBlockPath", ok=False),
    _c("bad-sign-space", P + "SELECT * { VALUES ?x { + 1 } }", "NumericLiteralPositive", ok=False),
]

# The BuiltInCall alternatives, one query each (parsed and round-tripped in test_parse_sparql_builtins).
BUILTINS: dict[str, str] = {
    **{n: f"{n}()" for n in ("RAND", "NOW", "UUID", "STRUUID")},
    **{
        n: f"{n}(?x)"
        for n in (
            "STR LANG DATATYPE IRI URI ABS CEIL FLOOR ROUND STRLEN UCASE LCASE ENCODE_FOR_URI YEAR MONTH DAY HOURS "
            "MINUTES SECONDS TIMEZONE TZ MD5 SHA1 SHA256 SHA384 SHA512 isIRI isURI isBLANK isLITERAL isNUMERIC isTRIPLE "
            "SUBJECT PREDICATE OBJECT LANGDIR hasLANG hasLANGDIR"
        ).split()
    },
    **{n: f"{n}(?x, ?y)" for n in "LANGMATCHES CONTAINS STRSTARTS STRENDS STRBEFORE STRAFTER STRLANG STRDT sameTerm".split()},
    "BOUND": "BOUND(?x)",
    "BNODE": "BNODE(?x)",
    "BNODE-nil": "BNODE()",
    "IF": "IF(?x, ?y, 1)",
    "CONCAT": "CONCAT(?x, ?y)",
    "CONCAT-nil": "CONCAT()",
    "COALESCE": "COALESCE(?x, ?y)",
    "STRLANGDIR": 'STRLANGDIR(?x, "en", "ltr")',
    "TRIPLE": "TRIPLE(?x, ?y, 1)",
    "REGEX": 'REGEX(?x, "a")',
    "SUBSTR": "SUBSTR(?x, 1)",
    "REPLACE": 'REPLACE(?x, "a", "b")',
}
