"""Whole-library SHACL-1.2-Profiling-style self-declaration (2026-10-09).

Generalizes ``starlayer.shacl.shacl_profiling.declared_conformance_profile()``'s
own pattern (SHACL 1.2 Profiling S3, "Profiles of SHACL" - ``dcterms:conformsTo``
plus the dx-prof vocabulary) beyond just the four named SHACL feature
profiles, to also cover the RDF 1.2/SPARQL 1.2 suite documents this project
already tracks (``docs/graph/rdf12_sparql12_gap_analysis.md``'s own seven
tracked documents, refreshed via
``tests/graph/vendor/spec_snapshots/refresh_snapshots.py``) - reused here as
a short, independently-maintained list of their stable TR URLs, not
imported from that test-tooling script (production code shouldn't depend
on a test-only module).

**Per-subpackage resources, not one flat "whole library" node (2026-10-09,
revised the same day it was first built)**: a claim like "conforms to
SPARQL 1.2 Query" is really a statement about ``starlayer.sparql``
specifically - the subpackage that actually implements the grammar/
rewriter - not about the library as an undifferentiated whole. Flattening
every claim onto one invented aggregate resource would lose exactly that
precision, so this module instead returns one graph containing *three*
real resources side by side: ``starlayer.shacl``'s own, already-existing
declaration (``declared_conformance_profile()``'s real resource, merged in
unchanged - its own subject, triples, and all), plus two new resources for
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

Deliberately used for only the two cases where the excluded thing has its
own real, dereferenceable IRI and the exclusion is total (not a partial/
scope-limited claim already made positively elsewhere, which would make
asserting both predicates on the same object self-contradictory):
``starlayer.shacl`` doesNotConformTo the UI Profile
(``http://www.w3.org/ns/shacl/profile/ui``), and ``starlayer.graph``
doesNotConformTo SPARQL 1.2 Entailment Regimes' D-Entailment regime
(``http://www.w3.org/ns/entailment/D``, known-but-unsupported per
``entailment_regimes.KNOWN_REGIMES - SUPPORTED_REGIMES``). Everything else
still has no real IRI to hang a predicate off at all - JSON-LD "1.2"/
TriX "1.2" (no real RDF 1.2 companion spec exists to name), RIF Core
Entailment (no IRI defined for it anywhere), the community-managed SHACL
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
- **SPARQL 1.2 RL (SRL)** - ``starlayer.sparql``. A full grammar/AST/
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

import os

from rdflib import Graph, Namespace, URIRef

DCTERMS = Namespace("http://purl.org/dc/terms/")

# Project-minted, not borrowed - see this module's own docstring for why
# no standard "does not conform" predicate exists to reuse instead.
CONFORMANCE = Namespace("https://github.com/hidden-graph/starlayer/ns/conformance#")
DOES_NOT_CONFORM_TO = CONFORMANCE.doesNotConformTo

_ASSET_PATH = os.path.join(os.path.dirname(__file__), "assets", "starlayer-conformance.ttl")

GRAPH_SUBJECT = URIRef(
    "https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/graph"
)
SPARQL_SUBJECT = URIRef(
    "https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/sparql"
)

# RDF 1.2 Concepts/Schema/Turtle/N-Triples/XML - starlayer.graph's own
# domain. docs/graph/rdf12_sparql12_gap_analysis.md confirms "no open
# items... a confirmed match" against all five (as of that document's own
# 2026-09-20 last review) - the same five RDF-prefixed documents
# tests/graph/vendor/spec_snapshots/refresh_snapshots.py re-fetches.
# RDF/XML 1.2's own documented scope limits still count as a "Match" per
# that review, not an exclusion - see this module's own docstring for why
# no RDF-level caveat predicate exists for that nuance.
#
# No trailing slash (2026-10-09), deliberately not the exact canonical
# form W3C serves these at - confirmed live via curl that
# https://www.w3.org/TR/rdf12-concepts (no slash) still 301-redirects to
# .../rdf12-concepts/ and resolves to the identical 200 OK content, so
# nothing is lost by omitting it; keeping it would otherwise make every
# one of these un-abbreviatable under any bound Turtle prefix (PN_LOCAL
# forbids "/", even a trailing one - confirmed the hard way while trying
# to prefix these in the profiling guide's own Section 4).
RDF12_CORE_TR_URLS = (
    "https://www.w3.org/TR/rdf12-concepts",
    "https://www.w3.org/TR/rdf12-schema",
    "https://www.w3.org/TR/rdf12-turtle",
    "https://www.w3.org/TR/rdf12-n-triples",
    "https://www.w3.org/TR/rdf12-xml",
)

# SPARQL 1.2 Query/Update - starlayer.sparql's own domain. Same
# gap-analysis document, same "confirmed match" verdict, for the two
# sparql-prefixed documents. Same no-trailing-slash reasoning as above.
SPARQL12_TR_URLS = (
    "https://www.w3.org/TR/sparql12-query",
    "https://www.w3.org/TR/sparql12-update",
)

# RDF Dataset Canonicalization (RDFC-1.0) and SPARQL 1.2 Protocol - also
# starlayer.graph's own domain (rdfc.py; backends/native.py). Same
# no-trailing-slash reasoning as above - both confirmed live to
# 301-redirect to the identical trailing-slash page.
GRAPH_EXTRA_TR_URLS = (
    "https://www.w3.org/TR/rdf-canon",
    "https://www.w3.org/TR/sparql12-protocol",
)

# SPARQL 1.2 RL (SRL) - starlayer.sparql's own domain.
SPARQL_EXTRA_TR_URLS = ("https://www.w3.org/TR/sparql12-rl",)


def declared_conformance() -> Graph:
    """starlayer's own multi-resource self-declared conformance statement -
    one graph containing three real, individually-identified resources:
    ``starlayer.shacl``'s own existing declaration
    (``declared_conformance_profile()``'s real graph, merged in verbatim -
    its own subject and triples, unchanged, so the two can never drift
    apart), plus new ``starlayer.graph``/``starlayer.sparql`` resources
    each asserting ``dcterms:conformsTo`` the RDF 1.2/SPARQL 1.2 suite
    documents specific to what that subpackage actually implements.

    Also asserts, on ``starlayer.graph``'s own resource: RDFC-1.0, SPARQL
    1.2 Protocol, and each *individually* supported SPARQL 1.2 Entailment
    Regime IRI (reused directly from ``entailment_regimes.SUPPORTED_REGIMES``,
    not hand-copied - the three genuinely unimplemented regimes are simply
    never added, no document-level claim is made for that spec as a whole).
    On ``starlayer.sparql``'s own resource: SPARQL 1.2 RL.

    A fresh graph on every call (matching ``declared_conformance_profile()``'s
    own "never share one mutable graph object across callers" convention -
    see ``starlayer/shacl/profiling.py``).
    """
    from starlayer.graph.graph.entailment_regimes import ENTAILMENT, SUPPORTED_REGIMES
    from starlayer.shacl.shacl_profiling import declared_conformance_profile

    graph = Graph()
    graph.parse(_ASSET_PATH, format="turtle")
    graph += declared_conformance_profile()

    for url in RDF12_CORE_TR_URLS + GRAPH_EXTRA_TR_URLS:
        graph.add((GRAPH_SUBJECT, DCTERMS.conformsTo, URIRef(url)))
    for regime in SUPPORTED_REGIMES:
        graph.add((GRAPH_SUBJECT, DCTERMS.conformsTo, regime))
    graph.add((GRAPH_SUBJECT, DOES_NOT_CONFORM_TO, ENTAILMENT.D))
    for url in SPARQL12_TR_URLS + SPARQL_EXTRA_TR_URLS:
        graph.add((SPARQL_SUBJECT, DCTERMS.conformsTo, URIRef(url)))

    return graph
