"""Registry of corpus cases with a known, reasoned disposition.

Same discipline as ``tests/shacl/w3c_shacl12/known_failures.py``: a failing conformance case is never
silently skipped. Each entry names *why*, and is applied as a strict xfail, so it breaks loudly (as an
unexpected XPASS) the moment the underlying gap is closed instead of silently going stale.

Review as claims that should still be true, not as history. Findings are first discovered against the
OWL API 5.1.20 oracle; each still needs its W3C Note check (step 2 of the plan) - entries say which
side the Note is on where that is already clear.

Finding codes (used in the reason strings, summarised in README.md):
  F1  top-level truncation        F2  Ontology versionIRI           F3  Ontology header Annotations:
  F4  quoted-string escapes       F5  numeric literal forms         F6  nodeID (_:x) individuals
  F7  data-range fillers          F8  langRange facet               F9  annotation-of-annotation
  F10 Misc-axiom annotations      F11 short datatype names          F12 facet tokenisation
  F13 length-facet literal type   F14 oracle writing quirks
"""

from __future__ import annotations

_F1 = "F1 top-level truncation: a non-keyword token at top level ends parsing and silently drops the rest of the document (manchester_parser.py: peek_word() returns None for any non-WORD token and the top-level loop treats None as end of input)."
_F2 = "F2 Ontology: <iri> <versionIRI>: no owl:versionIRI triple is emitted and, via F1, every following frame is silently dropped."

# case id -> reason: the oracle accepts it and its output DIFFERS from ours, but ours is what the W3C
# OWL 2 RDF Mapping specifies. The oracle comparison is therefore not applied; the spec-derived
# expectation lives in test_mc_note_only.py (CHECKS) and is required to exist for every entry.
_FACET_LEN = (
    "OWL API writes length/minLength/maxLength facet values as plain literals ('5'); we keep the literal as "
    "written in the document (5 is an integer literal, so '5'^^xsd:integer), which is what the RDF Mapping's "
    "'_:y_i F_i lt_i' rule says (the facet value is the literal lt as given)."
)
ORACLE_DEVIATIONS: dict[str, str] = {
    "facet-length": _FACET_LEN,
    "facet-minlength": _FACET_LEN,
    "facet-maxlength": _FACET_LEN,
    "facet-min-and-max-length": _FACET_LEN,
    "op-chain-annotated": (
        "OWL API additionally types the annotated property-chain list rdf:List. The RDF Mapping's Table 1 builds "
        "a SEQ from rdf:first/rdf:rest only; rdf:type rdf:List appears only in the parsing direction."
    ),
    "ind-sameas-annotated": (
        "OWL API reifies an annotated owl:sameAs axiom in BOTH directions. RDF Mapping section 2.3.2: the axiom "
        "is split into pairwise triples and the annotation is repeated on each; two individuals give one triple."
    ),
    "misc-sameindividual-annotated": (
        "Same as ind-sameas-annotated, for the top-level SameIndividual: axiom (RDF Mapping section 2.3.2)."
    ),
}

# case id -> reason: the oracle accepts it, but our parse is not OWL-equivalent (or raises). Real gaps
# to close, except F13/F14 which are pending a W3C check.
DIFFERENTIAL_FAILURES: dict[str, str] = {
}

_REJ_ACCEPTED_OK = "OWL API rejects; our parser accepts and the construct is allowed by the W3C Note. Output checked by test_mc_note_only.py."
_REJ_ORACLE_MODEL = "OWL API rejects because of its typed object model (it needs the name's entity type resolvable from context); our parser accepts, which is the deliberate design difference documented in manchester_syntax_gap_analysis.md."

# case id -> disposition for inputs the OWL API rejects (nothing to diff against). Where the Note allows
# the construct, test_mc_note_only.py checks our output against an expectation derived from the Note.
ORACLE_REJECTS: dict[str, str] = {
    "iri-mixed-forms": _REJ_ORACLE_MODEL + " (full-IRI class in a SubClassOf list.)",
    "lit-typed-short-datatype-names": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "lit-annotation-target-forms": _REJ_ACCEPTED_OK + " (annotationTarget ::= nodeID | IRI | literal.)",
    "r-value-nodeid": _REJ_ACCEPTED_OK + " (individual ::= individualIRI | nodeID, so a nodeID is a valid value restriction filler.)",
    "r-some-not-filler": _REJ_ACCEPTED_OK + " (primary ::= [not] (restriction | atomic), so 'p some not B' is valid.)",
    "r-some-chained": _REJ_ACCEPTED_OK + " (primary may be a restriction, so 'p some q some B' is valid.)",
    "that-not": _REJ_ACCEPTED_OK + " (conjunction ::= classIRI 'that' [ 'not' ] restriction ...)",
    "that-and-not": _REJ_ACCEPTED_OK + " (... { 'and' [ 'not' ] restriction })",
    "dr-short-datatype-name": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "range-short-integer": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "range-short-decimal": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "range-short-float": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "range-short-string": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "facet-on-short-datatype": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "datatype-frame-equiv-annotations": _REJ_ORACLE_MODEL + " (annotated EquivalentTo: data range in a Datatype frame.)",
    "ap-domain-abbreviated": _REJ_ORACLE_MODEL + " (abbreviated IRI as an annotation-property Domain:.)",
    "ap-domain-annotated": _REJ_ORACLE_MODEL + " (annotated annotation-property Domain:.)",
    "ap-all-clauses": _REJ_ORACLE_MODEL + " (annotation-property frame with Domain:/Range:/SubPropertyOf:.)",
}

# "case-id::check" -> reason: the tree layer (parse_to_tree / tree_to_text / tree_to_owl) does not
# faithfully carry this case. check is one of validates | owl_matches | text_roundtrip | fixpoint.
# EMPTY on the first run: every case the parser accepts passes all four tree checks. (Cases the parser
# rejects are skipped by test_mc_tree.py until the parser gap is closed, then run automatically.)
TREE_FAILURES: dict[str, str] = {}

_N_ORACLE_AGREES = "oracle also rejects this input, so it is a genuine parser defect: "
_N_NOTE_STRICTER = "OWL API ACCEPTS this input but the W3C Note's grammar requires otherwise; policy decision pending (Note vs OWL API parity), not necessarily a defect: "

# negative case id -> reason the parser wrongly ACCEPTS it (silent mis-parse).
NEGATIVE_FAILURES: dict[str, str] = {
    "misc-single-member": _N_NOTE_STRICTER + "'DisjointClasses: A' (the Note's description2List needs at least two).",
    "chain-single-property": _N_NOTE_STRICTER + "'SubPropertyChain: q' (the Note needs at least two properties around 'o').",
    "disjointunion-single-member": _N_NOTE_STRICTER + "'DisjointUnionOf: B' (description2List needs at least two).",
    "language-tag-without-text": _N_NOTE_STRICTER + "'\"x\"@' (languageTag needs a nonempty sequence after '@').",
}

# ontology term (local name in the manch: namespace) -> reason nothing in manchester.py uses it.
ORPHAN_ONTOLOGY_TERMS: dict[str, str] = {}

# W3C production name -> reason no corpus case exercises it.
UNCOVERED_PRODUCTIONS: dict[str, str] = {
    "entity": (
        "Defined in the note (Datatype(...) / Class(...) / ... functional-style references) but not "
        "referenced by any Manchester production; it is used only to describe the annotation mapping "
        "(note, section on entity annotations). There is no Manchester surface syntax to test."
    ),
}
