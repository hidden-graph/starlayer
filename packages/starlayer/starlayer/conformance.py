"""starlayer's own self-declared conformance, read from the profiles
document (``starontology.get_conformance_profiles()``, the
``starlayer-profiles.ttl`` named graph).

The claims are data, written out in that document - not built in code. This
module only reads the three module resources out of it: ``starlayer.graph``
(the RDF 1.2 documents, RDFC-1.0, the SPARQL 1.2 Protocol, and each
supported entailment regime by its own IRI), ``starlayer.sparql`` (SPARQL
1.2 Query, Update and RL) and ``starlayer.shacl`` (the SHACL profiles it
implements). A test checks the entailment regimes listed in the document
against ``entailment_regimes.SUPPORTED_REGIMES``, the one claim that
depends on code.

**Per-subpackage resources, not one flat "whole library" node (2026-10-09,
revised the same day it was first built)**: a claim like "conforms to
SPARQL 1.2 Query" is really a statement about ``starlayer.sparql``
specifically - the subpackage that actually implements the grammar/
rewriter - not about the library as an undifferentiated whole. Flattening
every claim onto one invented aggregate resource would lose exactly that
precision, so this module instead returns one graph containing *three*
real resources side by side: ``starlayer.shacl``'s own, already-existing
declaration (``declared_conformance_profile()`` reads the same
resource), plus two new resources for
``starlayer.graph`` (the RDF 1.2 Concepts/Schema/Turtle/N-Triples/XML
documents) and ``starlayer.sparql`` (SPARQL 1.2 Query/Update). No
aggregate "the whole library" node is minted at all - three real,
individually-identified resources together *are* the whole-library report.

Confirmed directly (fresh fetch of the SPARQL 1.2 Query spec) that there is
no SPARQL analog to SHACL's named-profile mechanism - no
``http://www.w3.org/ns/sparql/profile/`` vocabulary exists; SPARQL only has
hierarchical *version* labels ("1.1"/"1.2-basic"/"1.2"), a different,
simpler compatibility concept, not a feature-area breakdown. So
``starlayer.sparql``'s own claim here is just ``dcterms:conformsTo`` the
two real TR documents directly, the same as ``starlayer.graph``'s.

Lives at this top level deliberately, not inside ``starlayer.shacl`` or
``starlayer.starontology``: ``starlayer/__init__.py``'s own documented
"minimal surface, pick a subpackage" policy doesn't fit a declaration that
spans multiple subpackages at once, and ``starontology`` is specifically
the bundled vocabulary/shapes registry, not a home for the processing
engine's own spec conformance.

**``conformance:doesNotConformTo`` - a project-minted term for the cases
where a clean negative claim is possible (2026-10-09, reversing the
decision above)**: confirmed directly against the DX Profiles Vocabulary
spec (https://www.w3.org/TR/dx-prof/) that no standard "does not conform"
predicate exists anywhere in the vocabularies this module otherwise reuses
- so asserting one at all means minting our own, under this project's own
established ``https://github.com/hidden-graph/<subpackage>/ns/<name>#``
pattern (see ``starlayer.sparql.vocab.SALG``/``SRL``/etc. for precedent).
User feedback: prose alone buries an exclusion inside a header comment a
caller querying the graph would never see - the same problem the
per-resource ``rdfs:comment`` triples (above) already partly addressed,
but ``rdfs:comment`` is free text, not a queryable claim with a real
object IRI.

Deliberately used for only the case where the excluded thing has its own
real, dereferenceable IRI and the exclusion is total (not a partial/
scope-limited claim already made positively elsewhere, which would make
asserting both predicates on the same object self-contradictory):
``starlayer.graph`` doesNotConformTo SPARQL 1.2 Entailment Regimes'
D-Entailment regime
(``http://www.w3.org/ns/entailment/D``, known-but-unsupported per
``entailment_regimes.KNOWN_REGIMES - SUPPORTED_REGIMES``). Everything else
still has no real IRI to hang a predicate off at all - JSON-LD "1.2"/
TriX "1.2" (no real RDF 1.2 companion spec exists to name), RIF Core
Entailment (no IRI defined for it anywhere), the SHACL UI Profile
(``http://www.w3.org/ns/shacl/profile/ui`` - SHACL 1.2 Profiling A.3
defines it only as an unlisted subset of SHACL Core with no conformance
requirements, so there is nothing to claim or exclude; it was asserted as
a doesNotConformTo until 2026-10-17, on a reason that confused the UI
profile with the SHACL UI widget-selection specification), the community-managed SHACL
profiles in S3 (none has a published IRI), and OWL 2 RDF-Based Semantics'
*full* regime (shares the exact same IRI as the RL fragment this project
already claims ``dcterms:conformsTo`` for - the gap is "more than the RL
fragment," not a cleanly separate resource to say no to). Those stay
prose-only, in this docstring and each asset's own header comment,
because there's genuinely no IRI to assert anything - positive or
negative - about.

**Three more real, verified implementations added (2026-10-09), found by
auditing the project's own docs/code for every W3C document mentioned
rather than assuming the original seven were exhaustive**:

- **RDF Dataset Canonicalization (RDFC-1.0)** - ``starlayer.graph``.
  ``starlayer/graph/rdfc.py``'s own docstring: "every algorithm step...
  transcribed directly from the spec text", verified against the
  official W3C RDFC-1.0 test suite, with a documented RDF 1.2
  triple-term extension and a couple of named Appendix-A escaping edge
  cases skipped.
- **SPARQL 1.2 Protocol** - ``starlayer.graph`` (lands in
  ``backends/native.py``, the native backend's HTTP client).
  ``docs/graph/sparql12_protocol_gap_analysis.md``'s own verdict:
  "already conforms to everything it needs... deliberate design
  choices, not gaps", with three small, already-documented optional
  loose ends.
- **SRL (SPARQL Rules)** - ``starlayer.sparql``. A full grammar/syntax-tree/
  SHACL-shapes/stratified-Datalog-evaluation engine, verified
  end-to-end by reproducing the spec's own S6.6 worked example exactly.
  Documented, deliberate grammar scope reductions (no ``,``-chained
  object lists, limited property paths, no reified-triple syntax yet,
  ``IMPORTS`` hard-rejected) - see ``starlayer/sparql/CLAUDE.md``.

**SPARQL 1.2 Entailment Regimes handled differently from the above three
- individual regime IRIs, not one document-level claim.** Of the six
regimes that document defines, three (full OWL 2 RDF-Based Semantics,
D-Entailment, RIF Core) are genuinely unimplemented, not just
scope-limited - too partial to honestly claim conformance to the
*document* even with a caveat, the way RDF/XML's narrower scope limits
could be. But entailment regimes - unlike the document itself - each
have their own real, individually dereferenceable IRI
(``http://www.w3.org/ns/entailment/*``, confirmed live via ``curl``),
the same shape as SHACL's own named profiles. So instead of a blanket
claim, ``starlayer.graph``'s resource asserts ``dcterms:conformsTo``
each *individually supported* regime - reusing
``entailment_regimes.SUPPORTED_REGIMES`` directly (not hand-copied),
the same real constant ``infer()``/``query()`` already use to decide
what they'll actually run.
"""

from __future__ import annotations

from rdflib import Graph, Namespace, URIRef

DCTERMS = Namespace("http://purl.org/dc/terms/")

CONFORMANCE = Namespace("https://github.com/hidden-graph/starlayer/ns/conformance#")
DOES_NOT_CONFORM_TO = CONFORMANCE.doesNotConformTo

_PKG = "https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/"
GRAPH_SUBJECT = URIRef(_PKG + "graph")
SPARQL_SUBJECT = URIRef(_PKG + "sparql")
SHACL_SUBJECT = URIRef(_PKG + "shacl")


def declared_conformance() -> Graph:
    """starlayer's own multi-resource self-declared conformance statement -
    one graph containing three real, individually-identified resources
    (``starlayer.graph``, ``starlayer.sparql``, ``starlayer.shacl``), each
    read from the profiles document with all its ``dcterms:conformsTo``,
    ``conformance:doesNotConformTo`` and ``rdfs:comment`` triples.

    A fresh graph on every call (matching ``declared_conformance_profile()``'s
    own "never share one mutable graph object across callers" convention -
    see ``starlayer/shacl/profiling.py``).
    """
    from starlayer import starontology

    whole = starontology.get_conformance_profiles()
    graph = Graph()
    for prefix, namespace in whole.namespaces():
        graph.bind(prefix, namespace)
    for subject in (GRAPH_SUBJECT, SPARQL_SUBJECT, SHACL_SUBJECT):
        for triple in whole.triples((subject, None, None)):
            graph.add(triple)
    return graph
