"""Registry of corpus cases and checks with a known, reasoned disposition.

Same discipline as the Manchester suite and tests/shacl/w3c_shacl12/known_failures.py: a failing conformance
case is never silently skipped; each entry says *why* and is applied as a strict xfail, so it breaks loudly
(as an unexpected XPASS) the moment the underlying gap is closed.

Finding codes: P* = the parser or lexer, L* = a SPARQL construct that leaks through the reused rdflib grammar, V* =
validation. (S* = the text renderer / expression encoder and T = triple terms were closed on 2026-10-19 by encoding,
rendering and validating SRL expressions the way sqe: does; see README.)
"""

from __future__ import annotations

# production name -> why no corpus case exercises it
UNCOVERED_PRODUCTIONS: dict[str, str] = {}

_CAUSES = {
    'P1': "A bare reifier `<< ?x :q ?y ~ >>` is rejected, though the grammar allows it: Reifier ::= '~' ReifierId? (spec [75]/[77]).",
    'P2': "String escapes: `\\'` (ECHAR, spec [139]) inside a double-quoted string is rejected.",
    'P2b': 'Unicode escapes in strings, `\\u00e9` and `\\U0001F600` (UCHAR, spec [140]), are rejected.',
    'P3': "Negative decimals are unusable: `-1.5`, `-0.5` (DECIMAL_NEGATIVE, spec [133]) raise 'Not a number'; `-1`, `-1e3` and all positive forms work.",
    'P4': 'PN_LOCAL_ESC (spec [153]) is not decoded: `:a\\-b` becomes the IRI `http://example.org/a\\-b` with a literal backslash, which is not a valid IRI and cannot be serialized.',
    'V2': 'A function call with NO arguments (`FILTER :f()`, spec [18] ArgList NIL) does not validate: spexpr:_FunctionExprBodyShape requires every function node to carry an argument list and a `distinct` marker, which the encoder omits for a zero-argument call. This is a defect in the SHARED spexpr: shape/encoder, not in SRL: sqe: rejects `FILTER(<f>())` with an SQEValidationError too. (Parsing and rendering are fine; only validation fails.)',
}

# "case-id::check" -> reason (check is parses | fixpoint | meaning | tree | encoding)
CORPUS_FAILURES: dict[str, str] = {
    'body-filter-function-nil::encoding': _CAUSES['V2'],
    'body-filter-function-nil::tree': _CAUSES['V2'],
    'body-filter-function-nil::meaning': _CAUSES['V2'],
    'body-filter-function-nil::fixpoint': _CAUSES['V2'],
    'body-filter-function-nil::parses': _CAUSES['V2'],
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
}

# SPARQL functions that SRL's BuiltInCall does NOT include but the parser accepted: none since L2 was fixed.
BUILTIN_LEAKS: dict[str, str] = {}

# functions that ARE in the spec's BuiltInCall but fail to parse or to be represented as a tree.
BUILTIN_FAILURES: dict[str, str] = {}

# negative case id -> reason the parser wrongly ACCEPTS it (or fails to refuse it with an SRL error)
NEGATIVE_FAILURES: dict[str, str] = {}

# spec example block number -> reason it fails
SPEC_EXAMPLE_FAILURES: dict[int, str] = {}
