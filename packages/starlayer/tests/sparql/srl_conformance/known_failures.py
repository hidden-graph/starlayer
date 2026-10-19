"""Registry of corpus cases and checks with a known, reasoned disposition.

Same discipline as the Manchester suite and tests/shacl/w3c_shacl12/known_failures.py: a failing conformance
case is never silently skipped; each entry says *why* and is applied as a strict xfail, so it breaks loudly
(as an unexpected XPASS) the moment the underlying gap is closed.

Finding codes: S* = the text renderer / expression encoder (shared salg: machinery), P* = the parser or
lexer, L* = a SPARQL construct that leaks through the reused rdflib grammar, V* = validation, T = triple terms.
"""

from __future__ import annotations

# production name -> why no corpus case exercises it
UNCOVERED_PRODUCTIONS: dict[str, str] = {}

_CAUSES = {
    'S1': "Function calls in an expression render as the placeholder '{Function}': `FILTER xsd:integer(?y)` / `:f(?y, 2)` come back as unparseable, meaningless text (so do the spec's own Examples 9 and 10). The renderer is the shared salg:/ssyn expression renderer (ssyn_to_text._render_expr_text), not SRL code.",
    'S2': "Unary plus and minus render as the placeholders '{UnaryPlus}' / '{UnaryMinus}' (same shared expression renderer).",
    'S3': 'Parentheses are dropped on rendering: `(?y + 1) * 2` comes back as `?y + 1 * 2`, which parses fine and means something else. A SILENT change of meaning, caught by evaluating the expression before and after (same shared expression renderer).',
    'S4': '`?y IN ()` (empty expression list, spec [20] NIL) renders as `?y IN <rdf:nil>`; the tree path renders it correctly, the direct ruleset renderer does not.',
    'S5': "`BNODE()` (no argument, spec [118] 'BNODE' NIL) cannot be rendered or encoded to a tree: ExpressionNotCoveredException 'The expression None might not be covered yet' (shared salg: expression encoder).",
    'S6': "A triple term inside an expression (`?y = <<( ?x :r ?z )>>`, spec [114]) renders as the placeholder '{TripleTerm}' (shared expression renderer).",
    'P1': "A bare reifier `<< ?x :q ?y ~ >>` is rejected, though the grammar allows it: Reifier ::= '~' ReifierId? (spec [75]/[77]).",
    'P2': "String escapes: `\\'` (ECHAR, spec [139]) inside a double-quoted string is rejected.",
    'P2b': 'Unicode escapes in strings, `\\u00e9` and `\\U0001F600` (UCHAR, spec [140]), are rejected.',
    'P3': "Negative decimals are unusable: `-1.5`, `-0.5` (DECIMAL_NEGATIVE, spec [133]) raise 'Not a number'; `-1`, `-1e3` and all positive forms work.",
    'P4': 'PN_LOCAL_ESC (spec [153]) is not decoded: `:a\\-b` becomes the IRI `http://example.org/a\\-b` with a literal backslash, which is not a valid IRI and cannot be serialized.',
}

# "case-id::check" -> reason (check is parses | fixpoint | meaning | tree | encoding)
CORPUS_FAILURES: dict[str, str] = {
    'body-filter-function-nil::fixpoint': _CAUSES['S1'],
    'body-filter-function-nil::meaning': _CAUSES['S1'],
    'body-filter-function::fixpoint': _CAUSES['S1'],
    'body-filter-function::meaning': _CAUSES['S1'],
    'expr-bnode-nil::fixpoint': _CAUSES['S5'],
    'expr-bnode-nil::meaning': _CAUSES['S5'],
    'expr-bnode-nil::tree': _CAUSES['S5'],
    'expr-function-two-args::fixpoint': _CAUSES['S1'],
    'expr-function-two-args::meaning': _CAUSES['S1'],
    'expr-in-empty::fixpoint': _CAUSES['S4'],
    'expr-in-empty::meaning': _CAUSES['S4'],
    'expr-in-empty::tree': _CAUSES['S4'],
    'expr-nested-function::fixpoint': _CAUSES['S1'],
    'expr-nested-function::meaning': _CAUSES['S1'],
    'expr-parens::fixpoint': _CAUSES['S3'],
    'expr-parens::meaning': _CAUSES['S3'],
    'expr-set-arith::fixpoint': _CAUSES['S3'],
    'expr-set-arith::meaning': _CAUSES['S3'],
    'expr-unary-minus::fixpoint': _CAUSES['S2'],
    'expr-unary-minus::meaning': _CAUSES['S2'],
    'expr-unary-plus::fixpoint': _CAUSES['S2'],
    'expr-unary-plus::meaning': _CAUSES['S2'],
    'iri-pname-escapes::encoding': _CAUSES['P4'],
    'iri-pname-escapes::fixpoint': _CAUSES['P4'],
    'iri-pname-escapes::meaning': _CAUSES['P4'],
    'iri-pname-escapes::tree': _CAUSES['P4'],
    'lit-escapes::encoding': _CAUSES['P2'],
    'lit-escapes::fixpoint': _CAUSES['P2'],
    'lit-escapes::meaning': _CAUSES['P2'],
    'lit-escapes::parses': _CAUSES['P2'],
    'lit-escapes::tree': _CAUSES['P2'],
    'lit-negative::encoding': _CAUSES['P3'],
    'lit-negative::fixpoint': _CAUSES['P3'],
    'lit-negative::meaning': _CAUSES['P3'],
    'lit-negative::parses': _CAUSES['P3'],
    'lit-negative::tree': _CAUSES['P3'],
    'lit-unicode-escape::encoding': _CAUSES['P2b'],
    'lit-unicode-escape::fixpoint': _CAUSES['P2b'],
    'lit-unicode-escape::meaning': _CAUSES['P2b'],
    'lit-unicode-escape::parses': _CAUSES['P2b'],
    'lit-unicode-escape::tree': _CAUSES['P2b'],
    'rdf12-reified-bare-tilde::encoding': _CAUSES['P1'],
    'rdf12-reified-bare-tilde::fixpoint': _CAUSES['P1'],
    'rdf12-reified-bare-tilde::meaning': _CAUSES['P1'],
    'rdf12-reified-bare-tilde::parses': _CAUSES['P1'],
    'rdf12-reified-bare-tilde::tree': _CAUSES['P1'],
    'rdf12-triple-term-in-expression-nested::fixpoint': _CAUSES['S6'],
    'rdf12-triple-term-in-expression-nested::meaning': _CAUSES['S6'],
    'rdf12-triple-term-in-expression::fixpoint': _CAUSES['S6'],
    'rdf12-triple-term-in-expression::meaning': _CAUSES['S6'],
}

_LEAK = "SPARQL function missing from SRL's BuiltInCall (spec [118]) but accepted: the expression grammar is rdflib's SPARQL one, only partly narrowed."

# SPARQL functions that SRL's BuiltInCall production does NOT include but the parser accepts.
BUILTIN_LEAKS: dict[str, str] = {
    'BOUND': _LEAK,
    'COALESCE': _LEAK,
    'RAND': _LEAK,
    'MD5': _LEAK,
    'SHA1': _LEAK,
    'SHA256': _LEAK,
    'SHA384': _LEAK,
    'SHA512': _LEAK,
    'EXISTS': _LEAK,
    'NOT EXISTS': _LEAK,
}

# functions that ARE in the spec's BuiltInCall but fail to parse or to be represented as a tree.
BUILTIN_FAILURES: dict[str, str] = {
    'TRIPLE': "TRIPLE(s, p, o) (spec [118]) parses but the resulting tree does not conform to the srl:/salg: expression shapes, so the rule cannot be encoded as a valid srl: tree.",
}

# negative case id -> reason the parser wrongly ACCEPTS it (or fails to refuse it with an SRL error)
NEGATIVE_FAILURES: dict[str, str] = {
    'missing-dot-between-triples': "L1 `?x :a ?y ?y :b ?z` is accepted and read as two triples; the grammar requires '.' between triples (TriplesBlockPattern, spec [62]).",
    'unknown-prefix': "V1 an undeclared prefix IS rejected, but with a bare `Exception('Unknown namespace prefix')` from rdflib, not an SRLParseError, so `except SRLError` does not catch it.",
    'filter-exists': "L2 FILTER (EXISTS {...}) is accepted; EXISTS is not in SRL's BuiltInCall and has no defined meaning in a rule body.",
    'filter-not-exists': 'L2 FILTER (NOT EXISTS {...}) is accepted; see filter-exists.',
    'filter-bound': "L2 BOUND() is accepted; not in SRL's BuiltInCall.",
    'filter-coalesce': "L2 COALESCE() is accepted; not in SRL's BuiltInCall.",
    'filter-rand': "L2 RAND() is accepted; not in SRL's BuiltInCall (and non-deterministic, which a fixpoint evaluation cannot allow).",
}

# spec example block number -> reason it fails
SPEC_EXAMPLE_FAILURES: dict[int, str] = {
    22: _CAUSES['S1'] + ' (Example 9)',
    24: _CAUSES['S1'] + ' (Example 10)',
}
