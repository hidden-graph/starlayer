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
_F3 = "F3 'Annotations:' in the Ontology: header is refused (manchester_parser.py: 'not supported yet'; same in starontology/manchester.py). The W3C Note's ontology production allows { annotations } and OWL API accepts it."
_F6 = "F6 nodeID individuals (_:b1) are not supported in individual positions (frame name, SameAs/DifferentFrom target, Facts target, enumeration member, 'value'): raises 'unknown prefix _'. The Note's individual production allows nodeID."
_F7 = "F7 data-range fillers in restrictions go through the class-expression path: wrong OWL types (owl:Class instead of rdfs:Datatype), owl:complementOf instead of owl:datatypeComplementOf, owl:onClass instead of owl:onDataRange for qualified cardinalities, and for 'd some xsd:integer[>= 5]' the facet restriction is DROPPED entirely (silent semantic loss)."
_F8 = "F8 facet 'langRange' is rejected ('unknown facet'); documented as narrow in manchester_syntax_gap_analysis.md but the Note lists it in the facet production and OWL API accepts it."
_F9 = "F9 annotation-of-annotation ('Annotations: Annotations: p v p2 v2') is not supported: the inner 'Annotations' is read as a prefixed name ('unknown prefix Annotations'). The Note's annotation list allows a nested annotations prefix."
_F10 = "F10 inline Annotations: on top-level Misc axioms (EquivalentClasses: etc.) are refused; documented as deliberately unsupported in manchester_syntax_gap_analysis.md, but the Note's misc production has 'annotations' and OWL API accepts and maps them."
_F12 = "F12 facet tokenisation: '>=1' with no space is lexed as one unknown facet; the Note's grammar does not require whitespace between a facet symbol and its value."
_F13 = "F13 length facets (length/minLength/maxLength): our value literal is xsd:integer ('5'^^xsd:integer, from the Note's integerLiteral); the OWL API writes a plain literal '5'. Which is right per the OWL 2 RDF mapping is UNRESOLVED - needs the W3C Mapping check before deciding which side to change."
_F14a = "F14 oracle quirk (pending W3C check): OWL API additionally types the annotated propertyChain list as rdf:List."
_F14b = "F14 oracle quirk (pending W3C check): OWL API emits the annotated owl:sameAs axiom in both directions (i->j and j->i); we emit one. The property is symmetric so likely equivalent, but not isomorphic."

# case id -> reason: the oracle accepts it, but our parse is not OWL-equivalent (or raises). Real gaps
# to close, except F13/F14 which are pending a W3C check.
DIFFERENTIAL_FAILURES: dict[str, str] = {
    "hdr-annotations-nested": _F3 + " " + _F9,
    "ce-enumeration-with-nodeid": _F6,
    "ind-nodeid-frame": _F6,
    "ind-nodeid-fact-target": _F6,
    "ind-nodeid-sameas": _F6,
    "dr-some-restricted": _F7,
    "dr-some-enumeration": _F7,
    "dr-some-not": _F7,
    "dr-some-union": _F7,
    "dr-min-qualified": _F7,
    "dr-max-qualified": _F7,
    "dr-exactly-qualified": _F7,
    "facet-langrange": _F8,
    "class-subclassof-annotation-nested": _F9,
    "class-annotations-annotated": _F9,
    "misc-equivalentclasses-annotated": _F10,
    "misc-disjointclasses-annotated": _F10,
    "misc-equivalentproperties-annotated": _F10,
    "misc-disjointproperties-annotated": _F10,
    "misc-sameindividual-annotated": _F10,
    "misc-differentindividuals-annotated": _F10,
    "layout-no-space-in-facet": _F12,
    "facet-length": _F13,
    "facet-minlength": _F13,
    "facet-maxlength": _F13,
    "facet-min-and-max-length": _F13,
    "op-chain-annotated": _F14a,
    "ind-sameas-annotated": _F14b,
}

_REJ_ACCEPTED_OK = "OWL API rejects; our parser accepts and the construct is allowed by the W3C Note. Output checked by test_mc_note_only.py."
_REJ_ORACLE_MODEL = "OWL API rejects because of its typed object model (it needs the name's entity type resolvable from context); our parser accepts, which is the deliberate design difference documented in manchester_syntax_gap_analysis.md."

# case id -> disposition for inputs the OWL API rejects (nothing to diff against). Where the Note allows
# the construct, test_mc_note_only.py checks our output against an expectation derived from the Note.
ORACLE_REJECTS: dict[str, str] = {
    "iri-mixed-forms": _REJ_ORACLE_MODEL + " (full-IRI class in a SubClassOf list.)",
    "lit-typed-short-datatype-names": _REJ_ACCEPTED_OK + " (The note's Datatype production allows the short names integer/decimal/float/string, meaning the xsd datatypes.)",
    "lit-annotation-target-forms": "F6 nodeID as annotation target: the Note allows annotationTarget ::= nodeID; OWL API rejects; we raise 'unknown prefix _'.",
    "r-value-nodeid": "F6 'value _:anon': the Note allows an individual (nodeID); OWL API rejects; we raise.",
    "r-some-not-filler": _REJ_ACCEPTED_OK + " (primary ::= [not] (restriction | atomic), so 'p some not B' is valid.)",
    "r-some-chained": _REJ_ACCEPTED_OK + " (primary may be a restriction, so 'p some q some B' is valid.)",
    "that-not": _REJ_ACCEPTED_OK + " (conjunction ::= classIRI 'that' [ 'not' ] restriction ...)",
    "that-and-not": _REJ_ACCEPTED_OK + " (... { 'and' [ 'not' ] restriction })",
    "dr-short-datatype-name": "F11 short datatype name in a data restriction: Note allows; OWL API rejects; WE MIS-PARSE it as :integer.",
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
    "data-property-transitive": _N_ORACLE_AGREES + "'Characteristics: Transitive' on a DataProperty is accepted; the Note allows only 'Functional' for data properties.",
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
