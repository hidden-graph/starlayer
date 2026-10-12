"""starlayer.starontology - the raw ontology/SHACL-shapes ``.ttl`` files
this stack ships, kept in one place, independent of which *other*
subpackage ends up consuming them.

**Why this exists as one place.** These files used to live scattered
across whichever package happened to consume them first: ``manch:``/``skos:``
inside ``packages/graph/starlayergraph/ontology/``, ``salg:`` inside
``packages/sparql/starsparql/ontology/``. That made "where do I edit the
``manch:`` vocabulary" and "where do I edit the ``salg:`` vocabulary"
different answers depending on which package happened to need it first - a
real editing/discoverability cost, not just an aesthetic one. Consolidating
them here means one place to look, one place to edit, regardless of which
sibling subpackage(s) end up consuming a given file.

**Formerly a separate, independently-installed package (`pip install
ontology`), folded into `starlayer` as `starlayer.starontology` 2026-10-03.**
It never actually achieved independence in practice: `starlayer.sparql`
had a hard, eager runtime dependency on it (`sparql_shapes.py`/`srl.py` both
call `get_ontology_graph()` to build their shapes), and this package in turn
depended back on `starlayer.graph` (and, for the `shacl_meta` entry, on
`starlayer.shacl` too - see the old "Dependency note" this replaces). Two
pip-installed packages that can't function without each other was packaging
overhead with no real isolation benefit - the same reasoning that already
justified merging `starlayergraph`/`starsparql`/`starshacl` into one
`starlayer` package. `from starlayer import starontology` (or
`starlayer.starontology.X`) is the only way to reach anything here now; if a
genuine need for a standalone install resurfaces later, nothing stops
publishing it separately again then.

**Why this stays its own named subpackage, not flattened into another
one.** Each `.ttl` file here is pure data with no logic of its own - one
place to look, one place to edit, regardless of which sibling subpackage
ends up consuming a given file. This top-level module
(`starontology/__init__.py` itself) stays that way: it loads a graph and
nothing more, never wraps `pyshacl`/`starlayer.shacl`. *How* to validate
(which reasoning settings, which severity flags) stays each vocabulary's
own concern, genuinely different per vocabulary -
`starlayer.sparql.salg.sparql_shapes.validate_query()` for `salg:` still lives
outside this subpackage entirely, for now.

**Revised 2026-10-03: not every vocabulary stops there.**
`starontology.manchester`/`starontology.skos` are the exceptions - real
logic for the `manch:`/`skos:` vocabularies (parse/serialize/validate for
`manch:`, just validate for `skos:`, which needs no encode/decode layer at
all), moved here deliberately because validating (or, for `manch:`,
editing) a vocabulary against/as its own structure is an ontology-
management concern in its own right, not a `starlayer.graph`/`.sparql`/
`.ontology` one. `srl:` is expected to join them here eventually for the
same reason, once it's separable from the sibling `starlayer.sparql`
package's shared internals it currently depends on. So: this top-level
module stays data-only, but a named submodule (`starontology.manchester`/
`.skos`, and later `.srl`) can hold real logic when the vocabulary itself
needs more than a loader - see each submodule's own docstring for its full
reasoning (and, for `starontology.manchester`, the circular-import
discipline its logic follows - `starontology.skos` doesn't need that, since
it never touches `starlayer.graph` at all).

**Dependency note, revised 2026-10-03 for the move into `starlayer`.**
Every loader below returns a `StarLayerGraph`, not a plain `rdflib.Graph` -
a deliberate choice depending on `starlayer.graph`, plus `starlayer.shacl`
for exactly one entry (`shacl_meta` - see "What's here" below). Both
imports stay lazy (deferred inside each loader function, not at module top
level) as defensive practice, matching every other cross-subpackage import
in this stack - but the circular-import deadlock this originally guarded
against (when `starontology` was a separately-installed package with no
guaranteed load order relative to `starlayer` at all) is now structurally
impossible, not just avoided by convention: `starlayer.starontology` is a
subpackage of `starlayer`, and Python always fully executes a parent
package's own `__init__.py` before importing any of its submodules - so by
the time any code in this file runs, `starlayer.graph`/`.shacl` are
already loaded, every time, as a language guarantee rather than today's
particular import order holding up. Staying lazy costs nothing and keeps
this file consistent with its own submodules (`manchester.py`/`skos.py`
below), so it's kept - just no longer load-bearing the way it was.

**Registry API (replaced the eight separately-named functions 2026-10-02).**
Was ``manchester_ontology_graph()``/``manchester_shapes_graph()``/...,
eight separate top-level functions plus eight public ``*_TTL_PATH``
constants - replaced by one small registry (``get_ontology_list()``/
``get_ontology_graph(name)``). A near-identical cross-vocabulary registry
briefly existed one level up as ``starlayer.registry``, delegating its own
manch:/skos:/salg:/srl: entries straight into this one - removed
2026-10-03: nothing in this codebase ever called it by a bare name string
rather than the vocabulary-specific function it would have delegated to
anyway (``starontology.manchester.manchester_validate()``, ``starlayer
.sparql.srl.srl_validate()``, etc.), so it added a lookup layer with no
real caller.
The path constants were private (``_MANCHESTER_ONTOLOGY_TTL_PATH``, etc.) -
internal plumbing for this module's own registry, not a public way to
reach the data - and are gone entirely as of 2026-10-10 (see "What's here"
below: one dataset file replaced the ten separate ones they each pointed
at). Anyone who wants an entry's content uses ``get_ontology_graph(name)``
instead (``.serialize(format='turtle12')`` on the result for Turtle text -
a dedicated ``get_ontology_turtle12()`` wrapper existed briefly but was
removed 2026-10-03, since it was exactly that one-line composition and
nothing more).

**What's here**: ten entries, two per vocabulary (an OWL/RDFS ontology and
a SHACL shapes graph) for five vocabularies - plus an eleventh
*registered entry* (``shacl_meta``, see below) backed by generated Python
rather than any stored data at all. **Not ten separate files as of
2026-10-10** - see "One dataset, not eleven files" further below for
where they actually live now; the filenames named here are still each
entry's own identity (both as a dict key into that dataset and as the
``.../<filename>`` suffix of its ``get_resource_iri()`` IRI), just no
longer standalone files on disk:

- ``manch:`` (``manchester-ast-ontology.ttl`` / ``manchester_shapes.ttl``) -
  OWL 2 Manchester Syntax's own internal AST as RDF. Type ``"ast-graph"``.
- ``skos:`` (``skos-ontology.ttl`` / ``skos_shapes.ttl``) - the W3C SKOS
  Reference's own formal axioms and integrity conditions, over the real
  ``skos:`` namespace. Type ``"owl"`` - unlike the other three, this is a
  real semantic ontology (actual axioms about an existing vocabulary), not
  a syntax tree represented as RDF, so it doesn't get the ``"ast-graph"``
  label the other three legitimately earn.
- ``salg:`` (``salg-ontology.ttl`` / ``sparql_shapes.ttl``) - a SPARQL 1.2
  query/update's own algebra as RDF. Type ``"ast-graph"``.
- ``sqe:`` (``sqe-ontology.ttl`` / ``sqe_shapes.ttl``) - a SPARQL
  `SELECT`/`ASK`/`CONSTRUCT` query's own raw parse tree (pre-
  `translateQuery`), as a flat, human-readable RDF tree meant for hand/UI
  editing - deliberately not `salg:`'s resolved algebra, which isn't
  readable or editable the same way (see
  `starlayer.sparql.sqe`'s own module docstrings). Type ``"ast-graph"``.
- ``srl:`` (``srl-ontology.ttl`` / ``srl_shapes.ttl``) - SRL/SPARQL-RL's
  own rule-set abstract syntax as RDF (see `starlayer.sparql.srl`).
  Type ``"ast-graph"``.

Every shapes file (all five) is type ``"shacl"``, regardless of which of
the above its own target ontology is.

An eleventh entry, ``shacl_meta``, is also registered here (``type="shacl"``) -
the SHACL 1.2 meta-shapes themselves (``starlayer.shacl``'s own
shapes-about-shapes). The *generation code* deliberately stays in
``starlayer.shacl.meta_shapes.build_meta_shapes_graph()``, not duplicated
here - this registry only calls it and wraps the result, the same way the
other ten entries call ``_load(name)`` to pull their own named graph out
of the shared dataset (see "One dataset, not eleven files" below). Not
registered in that dataset at all (nothing to point at - it's generated,
not file-backed).

**One dataset, not eleven files (2026-10-10).** Previously: ten separate
``.ttl`` files (two per vocabulary) plus an eleventh,
``ontology-shapes-profiles.ttl`` - eleven independently-tracked files for
content that's always shipped and read together anyway. Now: one file,
``starontology.trig`` (TriG - Turtle's own named-graph extension, so
every entry stays as readable/diffable as it was as a standalone ``.ttl``
file), with each of the eleven entries as its own named graph inside it.
Each named graph's context IRI is the *exact same* GitHub-blob-URL
resource identity ``get_resource_iri()``/``_resource_iri()`` already
minted for that entry before this move - deliberately kept stable rather
than reminted, so every existing ``prof:isProfileOf`` triple and every
caller's own ``validate(shapes_graph_resource=...)`` usage keeps working
unchanged. ``_dataset()`` parses the whole file once and caches the
result (never mutated, never handed to a caller directly);
``_named_graph(context_iri)`` copies just one named graph's triples into
a fresh ``Graph`` per call, which is what every public function below
actually returns.

Every loader returns a **fresh ``StarLayerGraph``** - see the "Dependency
note" above for what that costs and why it was accepted. None of these
nine entries actually carry RDF 1.2 content (triple terms,
direction-tagged literals) themselves - they're ordinary RDF 1.1
vocabulary/shape definitions - so a plain ``rdflib.Graph`` would have been
functionally sufficient; ``StarLayerGraph`` is used for API consistency
with the rest of the stack instead.

**``get_profile_graph()`` (2026-10-08, corrected 2026-10-10)**: every
registered shapes graph is related by the dx-prof vocabulary's
``prof:isProfileOf`` to the *real external specification* it implements
(SPARQL, SKOS, Manchester Syntax, SPARQL-RL) - **not** to the bundled
ontology/AST graph, which the original 2026-10-08 design wrongly treated
as "the specification." The ontology/AST graph is instead one of that
same real specification's own ``prof:hasResource``/
``prof:ResourceDescriptor`` entries (``prof:hasRole role:schema``), a
sibling of the shapes graph's own ``role:validation`` descriptor - found
wrong via direct user challenge, confirmed against the real dx-prof spec
(``https://www.w3.org/TR/dx-prof/``) before fixing. ``sparql_shacl``/
``sparql_owl`` (``salg:``) are deliberately excluded from this mapping
entirely (2026-10-11) - unlike the other five pairs, ``salg:`` is this
project's own internal SPARQL algebra encoding, not something meant to
carry a public-facing conformance claim. This plugs directly into
``starlayer.shacl.profiling.derive_conforms_to()``'s own
``specification_graph=`` parameter - see ``get_profile_graph()``'s own
docstring for the full design and a worked example.

**Revised 2026-10-09: that mapping now lives in a real, persisted third
document (``ontology-shapes-profiles.ttl``), not a Python dict.** The
original design assembled each ``prof:isProfileOf`` triple fresh, in
memory, from a lookup dict - nothing existed on disk unless
``get_profile_graph()`` happened to be called. A profile relationship is
supposed to be genuine, persisted metadata (the same way
``starlayer.shacl``'s own ``shacl12-conformance-profile.ttl`` is a real
file), so this moved to one hand-maintained ``.ttl`` document, deliberately
independent of both endpoints it relates - see that file's own header
comment for the full reasoning (mixing profile metadata into either the
ontology or the shapes graph would conflate two different concerns).
``get_conformance_profiles(url=...)`` loads it (the bundled copy by
default, or any local path/``http(s)://`` location instead);
``get_profile_graph(shapes_name, url=...)`` is now a thin filter over that
same document, same return contract as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from rdflib import Graph, Namespace, URIRef

if TYPE_CHECKING:
    from starlayer.graph import StarLayerGraph

PROF = Namespace("http://www.w3.org/ns/dx/prof/")

_HERE = Path(__file__).parent

# Every registered ontology/shapes entry, plus the ontology-shapes profile
# mapping, now lives in ONE multi-graph dataset file (starontology.trig,
# 2026-10-10) - not 11 separate .ttl files. Each entry keeps its own real
# identity as a *named graph* inside that one file, rather than as a
# separate file on disk - see _dataset()/_named_graph() below for how
# that's read back out, and this module's own docstring for the full
# reasoning (one dataset is easier to hand to tooling as a whole, and
# avoids 11 independently-tracked files for content that's always shipped
# and read together anyway).
_DATASET_TTL_PATH = _HERE / "starontology.trig"

# Each registered name's own filename *within* the dataset - reused only
# to compute _resource_iri() below (the same GitHub-blob-URL identity this
# project already uses elsewhere), not to open a file directly anymore.
_FILENAME_BY_NAME: dict[str, str] = {
    "manchester_owl": "manchester-ast-ontology.ttl",
    "manchester_shacl": "manchester_shapes.ttl",
    "skos_owl": "skos-ontology.ttl",
    "skos_shacl": "skos_shapes.ttl",
    "sparql_owl": "salg-ontology.ttl",
    "sparql_shacl": "sparql_shapes.ttl",
    "sqe_owl": "sqe-ontology.ttl",
    "sqe_shacl": "sqe_shapes.ttl",
    "srl_owl": "srl-ontology.ttl",
    "srl_shacl": "srl_shapes.ttl",
    "spexpr_owl": "spexpr-ontology.ttl",
    "spexpr_shacl": "spexpr_shapes.ttl",
    # 2026-10-12: shacl_meta gets a real resource IRI too (used by
    # ontology-shapes-profiles.ttl's own prof:isProfileOf entry for it -
    # see get_profile_graph()'s docstring), even though no file at this
    # name exists yet - _load_shacl_meta() still generates the graph
    # itself from Python, not from this filename. See
    # docs/future_enhancements.md's dated entry: shacl_meta should
    # eventually become a real static file like every other entry here,
    # at which point this filename becomes the real one, not provisional.
    "shacl_meta": "shacl_meta_shapes.ttl",
}

# The ontology-shapes profile mapping's own filename/named-graph identity -
# see get_conformance_profiles()/get_profile_graph() below, and
# _dataset()'s own comment for why it's a named graph inside the same
# dataset rather than embedded in either endpoint it relates.
_PROFILES_FILENAME = "ontology-shapes-profiles.ttl"


@dataclass(frozen=True)
class OntologyInfo:
    """One registered ontology/shapes file's metadata - no ``validate``
    hook alongside it, since this package itself does no validation (see
    this module's own docstring); ``get_ontology_graph()`` is the way to
    actually load one."""

    name: str
    description: str
    type: str  # "shacl" | "ast-graph" | "owl"


_REGISTRY: dict[str, tuple[OntologyInfo, Callable[[], StarLayerGraph]]] = {
    "manchester_owl": (
        OntologyInfo(
            name="manchester_owl",
            description=(
                "OWL 2 Manchester Syntax's own internal AST as RDF (manch:) - "
                "frames/clauses/class- and property-expressions/data-ranges, "
                "one level upstream of the compiled OWL RDF mapping."
            ),
            type="ast-graph",
        ),
        lambda: _load("manchester_owl"),
    ),
    "manchester_shacl": (
        OntologyInfo(
            name="manchester_shacl",
            description="SHACL shapes validating a manch: AST graph's own structural well-formedness.",
            type="shacl",
        ),
        lambda: _load("manchester_shacl"),
    ),
    "skos_owl": (
        OntologyInfo(
            name="skos_owl",
            description=(
                "The W3C SKOS Reference's own formal axioms and numbered "
                "Documented Consistency and Integrity Conditions, over the "
                "real skos: namespace."
            ),
            type="owl",
        ),
        lambda: _load("skos_owl"),
    ),
    "skos_shacl": (
        OntologyInfo(
            name="skos_shacl",
            description="SHACL shapes checking SKOS's own numbered integrity conditions against a data graph.",
            type="shacl",
        ),
        lambda: _load("skos_shacl"),
    ),
    "sparql_owl": (
        OntologyInfo(
            name="sparql_owl",
            description=(
                "A SPARQL 1.2 query/update's own algebra as RDF (salg:) - "
                "encode/edit/decode/re-execute a query as data."
            ),
            type="ast-graph",
        ),
        lambda: _load("sparql_owl"),
    ),
    "sparql_shacl": (
        OntologyInfo(
            name="sparql_shacl",
            description="SHACL shapes validating a salg: algebra graph's own structural well-formedness.",
            type="shacl",
        ),
        lambda: _load("sparql_shacl"),
    ),
    "sqe_owl": (
        OntologyInfo(
            name="sqe_owl",
            description=(
                "A SPARQL SELECT/ASK/CONSTRUCT query's own raw parse tree, "
                "pre-translateQuery, as a flat, human-readable RDF tree "
                "(sqe:) meant for hand/UI editing - deliberately not the "
                "resolved salg: algebra, which isn't readable or editable "
                "the same way. v1 scope reduction: no aggregates/"
                "subqueries/VALUES/Update yet (property paths ARE covered)."
            ),
            type="ast-graph",
        ),
        lambda: _load("sqe_owl"),
    ),
    "sqe_shacl": (
        OntologyInfo(
            name="sqe_shacl",
            description=(
                "SHACL shapes validating an sqe: query-edit graph's own "
                "structural well-formedness, designed for UI-editor field-"
                "level validation, not just decode-ability."
            ),
            type="shacl",
        ),
        lambda: _load("sqe_shacl"),
    ),
    "srl_owl": (
        OntologyInfo(
            name="srl_owl",
            description=(
                "SRL/SPARQL-RL's own rule-set abstract syntax as RDF (srl:) - "
                "a Datalog-style rules language, general-purpose and SHACL-independent."
            ),
            type="ast-graph",
        ),
        lambda: _load("srl_owl"),
    ),
    "srl_shacl": (
        OntologyInfo(
            name="srl_shacl",
            description="SHACL shapes validating an srl: rule-set graph's own structural well-formedness.",
            type="shacl",
        ),
        lambda: _load("srl_shacl"),
    ),
    "spexpr_owl": (
        OntologyInfo(
            name="spexpr_owl",
            description=(
                "The SPARQL expression/variable/property-path vocabulary "
                "(spexpr:), carved out of salg: 2026-10-10 - the one slice "
                "salg:/sqe:/srl: all need identically (their own expression "
                "encoding, reused unchanged, not reimplemented per-vocabulary), "
                "originally minted under salg: only because salg: was built "
                "first, before sqe: existed to need sharing it."
            ),
            type="ast-graph",
        ),
        lambda: _load("spexpr_owl"),
    ),
    "spexpr_shacl": (
        OntologyInfo(
            name="spexpr_shacl",
            description=(
                "SHACL shapes validating an spexpr: expression/variable/path "
                "value's own well-formedness - imported by salg:/sqe:/srl: "
                "alike (each via owl:imports), not defined separately by any "
                "one of them."
            ),
            type="shacl",
        ),
        lambda: _load("spexpr_shacl"),
    ),
    "shacl_meta": (
        OntologyInfo(
            name="shacl_meta",
            description=(
                "The SHACL 1.2 meta-shapes themselves (starlayer.shacl's own "
                "shapes-about-shapes, validating a shapes graph's own "
                "well-formedness) - generated Python, not a static file, so "
                "there's no shacl_owl counterpart to this entry."
            ),
            type="shacl",
        ),
        lambda: _load_shacl_meta(),
    ),
}


_dataset_cache: Any | None = None


def _dataset() -> Any:
    """The shared ``rdflib.Dataset`` backing every file-based registry
    entry plus the ontology-shapes profile mapping (2026-10-10) - parsed
    from ``starontology.trig`` once and cached, not re-parsed on every
    call. This file never changes at runtime (bundled, static), so
    re-reading ~3000 triples from disk on every single
    ``get_ontology_graph()`` call would be pure waste - same reasoning as
    ``_real_shapes_graph_iri_to_name()``'s own caching below.

    Never mutated, and never handed to a caller directly - every accessor
    (``_named_graph()`` below) copies just the one named graph it needs
    into a fresh, independent ``Graph`` first, so this cached object stays
    safe to share across every call without any caller being able to see
    (or corrupt) another caller's view of it.
    """
    global _dataset_cache
    if _dataset_cache is None:
        from rdflib import Dataset

        ds = Dataset()
        ds.parse(str(_DATASET_TTL_PATH), format="trig")
        _dataset_cache = ds
    return _dataset_cache


def _bind_dataset_namespaces(graph: Graph) -> None:
    """Bind every prefix the shared dataset itself has (``manch:``/
    ``salg:``/``sqe:``/``srl:``/``skshp:``/etc., bound in
    ``starontology.trig``'s own header) onto ``graph`` - a real regression
    this fixes, caught live via the full test suite, not anticipated in
    advance: copying triples one at a time via ``graph.add(triple)``
    (``_named_graph()``'s own approach, needed since two callers must
    never share - or corrupt - the same graph object) never carries over
    namespace bindings the way ``graph.parse(path)`` used to when each
    registry entry was still its own standalone file. Without this,
    ``get_ontology_graph(name).serialize(...)`` falls back to rdflib's own
    auto-generated ``ns1:``/``ns2:`` prefixes instead of the expected
    ``salg:``/``sqe:`` - breaking real downstream callers
    (``starlayer/sparql/salg/sparql_shapes.py``'s own
    ``SHAPES_TURTLE = get_ontology_graph("sparql_shacl").serialize(...)``,
    later string-concatenated with more hand-written ``salg:``-prefixed
    Turtle text that assumes that exact prefix is already bound in the
    combined document). Binding every dataset-wide prefix on every
    extracted graph (not just the subset that entry's own triples
    actually use) is harmless - rdflib's Turtle serializer only ever
    emits an ``@prefix`` line for a namespace actually used by the
    triples being serialized, so an unused binding here costs nothing."""
    for prefix, namespace in _dataset().namespaces():
        graph.bind(prefix, namespace, override=False)


def _named_graph(context_iri: URIRef) -> Graph:
    """A fresh, independent ``Graph`` containing just the triples from one
    named graph in the shared, cached dataset - never the shared
    ``Dataset`` object itself, and never a graph object owned by it
    either, so two callers (or two calls) never see or mutate the same
    object."""
    graph = Graph()
    _bind_dataset_namespaces(graph)
    for triple in _dataset().graph(context_iri):
        graph.add(triple)
    return graph


def _load(name: str) -> StarLayerGraph:
    # Lazy, not top-level: a top-level `from starlayer.graph import
    # StarLayerGraph` pulls in the whole starlayer package (Python always
    # initializes a parent package before any of its submodules) - a real
    # circular-import deadlock when starontology is the thing being
    # imported first and something in that chain reads back into this
    # module's own registry before it's finished (confirmed live:
    # AttributeError on a "partially initialized module", back when
    # starlayer eagerly imported the now-removed starlayer.registry).
    # Deferring this import until a loader is actually *called* means
    # starontology always finishes its own import first, breaking the
    # cycle - kept this way even though today's starlayer/__init__.py
    # doesn't trigger it, per this module's own "Dependency note" above.
    from starlayer.graph import StarLayerGraph

    # identifier=_resource_iri(name) (2026-10-11): without this, every
    # returned graph got rdflib's own random default BNode identity, so a
    # caller who forgot to pass validate(..., shapes_graph_resource=...) explicitly
    # got no sh:usedShapesGraph/sh:conformsTo/dcterms:conformsTo at all -
    # confirmed live as a real footgun, not hypothetical (validate()'s own
    # .identifier fallback only fires for a real URIRef, never a BNode).
    # Giving the graph its real resource IRI as its own identity makes
    # that fallback recover it automatically.
    g = StarLayerGraph(identifier=_resource_iri(name))
    _bind_dataset_namespaces(g)
    for triple in _named_graph(_resource_iri(name)):
        g.add(triple)
    return g


def _load_shacl_meta() -> StarLayerGraph:
    # Same lazy-import discipline as _load() above, same reason - see its
    # own comment. starlayer.shacl has zero dependency back on
    # starontology (confirmed), so this isn't a real cycle, but the import
    # still has to happen in here, not at module top level, or it would be.
    from starlayer.graph import StarLayerGraph
    from starlayer.shacl.meta_shapes import build_meta_shapes_graph

    # build_meta_shapes_graph() returns a plain rdflib.Graph, not a
    # StarLayerGraph (confirmed in its own source) - wrap it so every
    # registry entry keeps the same return type, with no exceptions.
    return StarLayerGraph.from_rdflib(build_meta_shapes_graph())


def get_ontology_list() -> tuple[OntologyInfo, ...]:
    """Every registered ontology/shapes file's metadata, sorted by name."""
    return tuple(sorted((info for info, _loader in _REGISTRY.values()), key=lambda info: info.name))


def get_ontology_graph(name: str) -> StarLayerGraph:
    """A fresh ``StarLayerGraph`` of the named ontology/shapes file.

    Raises ``KeyError`` (naming every valid choice) for an unknown name,
    rather than returning ``None`` - a typo'd name should fail loudly at
    the call site, not surface as a confusing ``AttributeError`` two lines
    later on a ``None``.
    """
    try:
        _info, loader = _REGISTRY[name]
    except KeyError:
        raise KeyError(f"{name!r} is not a registered ontology - choices are {sorted(_REGISTRY)}") from None
    return loader()


# Every registered shapes entry that has a paired ontology/AST entry it
# validates - every "*_shacl" entry except "shacl_meta" (no ontology
# counterpart in this registry: no "shacl_owl" entry exists, since it's
# generated by starlayer.shacl.meta_shapes, not file-backed). Just the
# name list - the actual prof:isProfileOf pairing itself now lives in
# ontology-shapes-profiles.ttl (2026-10-09), not here, deliberately: this
# tuple is reused below by _real_shapes_graph_iri_to_name() for an
# unrelated reason (deciding which shapes files to scan), which has
# nothing to do with declaring a profile relationship and shouldn't share
# a name with the thing that does.
_SHACL_ENTRIES_WITH_ONTOLOGY_COUNTERPART = (
    "manchester_shacl",
    "skos_shacl",
    "sparql_shacl",
    "sqe_shacl",
    "srl_shacl",
    "spexpr_shacl",
)

# Every registered shacl-type entry get_profile_graph() will look up in
# ontology-shapes-profiles.ttl - a genuinely different list than the one
# above, on purpose (see that tuple's own comment: it's reused for an
# unrelated reason and "shouldn't share a name with the thing that
# does"). shacl_meta (2026-10-12) has a real prof:isProfileOf entry
# there too (against the public SHACL profile IRIs it represents) despite
# having no ontology counterpart at all - the two facts are independent.
_SHACL_ENTRIES_WITH_PROFILE_MAPPING = _SHACL_ENTRIES_WITH_ONTOLOGY_COUNTERPART + ("shacl_meta",)

# Same "GitHub blob URL as a resource identity" convention
# starlayer.shacl's own shacl12-conformance-profile.ttl already established
# for its one self-declaration resource - but computed from each entry's
# own current, correct filename here (that file's own existing resource
# IRI is actually stale, still naming the pre-consolidation "packages/shacl"
# path - a pre-existing, unrelated drift bug, not fixed here, but not
# propagated into these new IRIs either). Unchanged by the 2026-10-10 move
# into one dataset file (below) - each entry's resource identity is still
# "the GitHub blob URL its content used to live at as a standalone file,"
# deliberately kept stable across that migration rather than reminted, so
# nothing that already depends on this IRI (prof:isProfileOf triples,
# validate(shapes_graph_resource=...) callers) silently breaks.
_GITHUB_BLOB_BASE = "https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/starontology/"


def _resource_iri(name: str) -> URIRef:
    return URIRef(_GITHUB_BLOB_BASE + _FILENAME_BY_NAME[name])


def get_resource_iri(name: str) -> URIRef | None:
    """The stable resource IRI ``get_profile_graph()`` uses to identify
    ``name``'s own registered file (a GitHub blob URL - see that
    function's own neighboring comment for the convention). Returns
    ``None`` for an unregistered name, matching ``get_profile_graph()``'s
    own no-raise convention.

    ``"shacl_meta"`` (2026-10-12) gets a real IRI here too, even though
    it's still generated Python, not an actual file at this path yet -
    see ``docs/future_enhancements.md``'s dated entry on making it a
    real static file like every other registered entry. The IRI is
    provisional in that sense, but stable: it's the same one
    ``ontology-shapes-profiles.ttl`` already uses for its own
    ``prof:isProfileOf`` entry, so a caller can rely on it today.

    Exists so a caller validating against one of this registry's own
    shapes graphs can give it the *same* identity `derive_conforms_to()`'s
    ``specification_graph=`` chain expects - `derive_conforms_to()`'s
    second rule only fires when the shapes-graph IRI the caller supplied
    to `validate(..., shapes_graph_resource=...)` is the *exact same* IRI
    `get_profile_graph()` asserts `prof:isProfileOf` on, not merely some
    other identity for "the same" file:

    >>> shapes = starontology.get_ontology_graph("skos_shacl")
    >>> result = StarShaclSchema(shacl_graph=shapes).validate(
    ...     data_graph=my_data,
    ...     data_graph_iri="http://example.org/graphs/mydata",
    ...     shapes_graph_resource=starontology.get_resource_iri("skos_shacl"),
    ... )
    >>> derive_conforms_to(
    ...     result.report_graph,
    ...     specification_graph=starontology.get_profile_graph("skos_shacl"),
    ... )  # doctest: +SKIP
    """
    if name not in _FILENAME_BY_NAME:
        return None
    return _resource_iri(name)


def get_conformance_profiles(url: str | None = None) -> StarLayerGraph:
    """Every registered shapes graph's real relationship to its
    specification, as one real persisted named graph
    (``<.../ontology-shapes-profiles.ttl>`` inside ``starontology.trig``) -
    not synthesized from this module's own registry on the fly. See that
    named graph's own context (and this module's own docstring) for why
    the mapping is a third, independent identity rather than embedded in
    either endpoint.

    Corrected 2026-10-10 (direct user challenge to the original 2026-10-08
    design - see ``get_profile_graph()``'s own docstring for the full
    account): each registered shapes graph is ``prof:isProfileOf`` the
    real external specification it implements (SPARQL, SKOS, Manchester
    Syntax, SPARQL-RL) - not the bundled ontology/AST-as-RDF graph, which
    is instead one of that same real specification's own
    ``prof:hasResource``/``prof:ResourceDescriptor`` entries
    (``prof:hasRole role:schema``), a sibling of the shapes graph's own
    ``role:validation`` descriptor. Confirmed against the real dx-prof
    spec (``https://www.w3.org/TR/dx-prof/``) before making this change.

    Loads the bundled copy by default. Pass ``url=`` to load a different
    local path or ``http(s)://`` location instead - ``rdflib.Graph.parse()``
    handles both natively - e.g. a community-hosted canonical copy, or a
    local override for testing, without needing a new ``starontology``
    release to pick up a change. An override is read as a plain Turtle
    document (not a dataset) - it's expected to carry just the
    ``prof:isProfileOf``/``prof:hasResource`` triples themselves, the same
    shape ``get_profile_graph()`` itself returns.

    A fresh graph on every call, matching this stack's "never share one
    mutable graph object across callers" convention (see
    ``starlayer.shacl.profiling.declared_conformance_profile()``).

    Returns a ``StarLayerGraph``, matching this module's own
    ``get_ontology_graph()``/``_load()`` convention - originally a plain
    ``rdflib.Graph`` (2026-10-10 fix, found via a real guide-notebook
    failure: ``.serialize(format="turtle12")`` is handled by
    ``StarLayerGraph.serialize()``'s own override, not a real globally-
    registered rdflib plugin, so it only ever worked on this registry's
    other 11 "real" graphs, never on this one).
    """
    from starlayer.graph import StarLayerGraph  # lazy: avoids a circular-import deadlock, see _load()'s own comment

    if url is not None:
        graph = StarLayerGraph()
        graph.parse(url, format="turtle")
        return graph
    g = StarLayerGraph()
    _bind_dataset_namespaces(g)
    for triple in _named_graph(URIRef(_GITHUB_BLOB_BASE + _PROFILES_FILENAME)):
        g.add(triple)
    return g


def get_profile_graph(shapes_name: str, url: str | None = None) -> StarLayerGraph | None:
    """A small, fresh ``StarLayerGraph`` describing ``shapes_name``'s own
    registered shapes graph's real relationship to its *actual*
    specification - a thin filter over ``get_conformance_profiles(url)`` -
    pass ``url=`` through to load the mapping from somewhere other than
    the bundled default.

    The convention this project follows, corrected 2026-10-10 (direct user
    challenge to the original 2026-10-08 design - see below): the shapes
    graph itself is ``prof:isProfileOf`` the real external specification
    (e.g. SPARQL 1.2 Query, the SKOS Reference, OWL 2 Manchester Syntax) -
    the same predicate ``starlayer.shacl.profiling.derive_conforms_to()``'s
    own ``specification_graph=`` parameter already expects, and the exact
    shape SHACL 1.2 Profiling's own S5.5 rule requires to fire at all (it
    looks for ``?shapesGraph prof:isProfileOf ?spec`` directly - no way to
    walk through ``prof:hasResource``/``prof:hasArtifact``/``prof:hasRole``
    instead). The bundled ontology/AST-as-RDF graph (``manch:``/``sqe:``/
    ``srl:``/``spexpr:``/``skos_owl``) is **not** what the shapes
    graph profiles - it's a ``prof:hasResource``/``prof:ResourceDescriptor``
    of the *same* real specification, tagged ``prof:hasRole
    role:schema`` ("machine-readable structural descriptions of data"),
    a sibling of the shapes graph's own ``role:validation`` descriptor
    ("supplies instructions about how to verify conformance") - not
    something the shapes graph is itself a profile *of*. Confirmed against
    the real dx-prof spec (``https://www.w3.org/TR/dx-prof/``) before
    making this change, not assumed.

    **Original 2026-10-08 design, found wrong and replaced**: the shapes
    graph was declared ``prof:isProfileOf`` the bundled ontology/AST graph
    itself - treating this project's own internal RDF encoding as "the
    specification," when the real specification is the external standard
    (SPARQL, SKOS, Manchester Syntax, SPARQL-RL) that encoding represents.
    A pair with no real external specification of its own (``sqe:``,
    ``spexpr:``) still profiles one correctly under this fix - both are
    genuinely part of SPARQL 1.2 Query's own grammar (raw parse tree /
    shared expression vocabulary respectively), so both point at
    ``https://www.w3.org/TR/sparql12-query``.

    **``sparql_shacl``/``sparql_owl`` (``salg:``) excluded entirely
    (2026-10-11, direct user decision)**: unlike the other five pairs,
    ``salg:`` is this project's own internal SPARQL algebra encoding -
    not something meant to carry a public-facing conformance claim.
    ``get_profile_graph("sparql_shacl")`` returns an empty graph (it's
    still a real registered entry, just one this document has nothing to
    say about), never ``None``.

    ``"shacl_meta"`` (2026-10-12) has a real entry too, despite having no
    ontology counterpart at all - ``starlayer``'s own SHACL meta-shapes
    graph declares ``prof:isProfileOf`` the public SHACL 1.2 profile IRIs
    it represents (Core/SPARQL/Node-Expressions/Rules/Profiling - the
    same five ``declared_conformance_profile()`` already claims). No
    ``prof:hasResource`` structure accompanies it, unlike the six real
    pairs above - there's no sibling ontology/AST graph to describe via
    ``role:schema``, so this entry is just the bare ``isProfileOf``
    triples.

    Returns ``None`` only for a name not registered at all, rather than
    raising - this is optional enrichment, not something every caller
    needs.

    Ready to pass straight through as ``derive_conforms_to()``'s own
    ``specification_graph=`` argument: validate real data against
    ``get_ontology_graph("skos_shacl")``, derive ``sh:conformsTo`` against
    the shapes graph, then
    ``derive_conforms_to(result.report_graph, specification_graph=
    get_profile_graph("skos_shacl"))`` additionally derives
    ``dcterms:conformsTo`` against the real SKOS Reference spec IRI - one
    real inference chain from validated data up through the shapes graph
    up to the actual external standard it implements.
    """
    if shapes_name not in _SHACL_ENTRIES_WITH_PROFILE_MAPPING:
        return None

    from starlayer.graph import StarLayerGraph  # lazy: avoids a circular-import deadlock, see _load()'s own comment

    mapping = get_conformance_profiles(url)
    subject = _resource_iri(shapes_name)
    graph = StarLayerGraph()
    _bind_dataset_namespaces(graph)

    # Breadth-first walk outward from `subject`, following every outgoing
    # predicate - not a hardcoded hop count or predicate list - so this
    # stays correct regardless of how many hops the real structure needs.
    # Today that's: shapes -> prof:isProfileOf -> specification ->
    # prof:hasResource -> ResourceDescriptor bnode -> its own
    # hasArtifact/hasRole/rdfs:label/rdfs:comment (3 hops) - but nothing
    # here assumes that specific shape. Terminates naturally: a Literal or
    # a leaf URIRef with no further outgoing triples contributes nothing
    # new to the frontier.
    seen_nodes = {subject}
    frontier = [subject]
    while frontier:
        next_frontier = []
        for node in frontier:
            for triple in mapping.triples((node, None, None)):
                graph.add(triple)
                obj = triple[2]
                if obj not in seen_nodes:
                    seen_nodes.add(obj)
                    next_frontier.append(obj)
        frontier = next_frontier
    return graph


# Every registered shapes entry's own real sh:ShapesGraph node IRI (the one
# each shapes file's own owl:imports triples actually point at, e.g.
# sqe_shapes.ttl's sqe:ShapesGraph owl:imports salg:ShapesGraph) - a
# genuinely different identity than get_resource_iri()'s own GitHub-blob-URL
# scheme (built for prof:isProfileOf, a separate concern - see
# starlayer/shacl/CLAUDE.md's dated entry for why these two identities exist
# and don't currently match each other). Lazily built, cached: every
# registered file is static and bundled, never changes at runtime, so
# re-parsing all five on every local_loader() call would be pure waste.
_REAL_SHAPES_GRAPH_IRI_TO_NAME: dict | None = None


def _real_shapes_graph_iri_to_name() -> dict:
    global _REAL_SHAPES_GRAPH_IRI_TO_NAME
    if _REAL_SHAPES_GRAPH_IRI_TO_NAME is None:
        from rdflib import RDF

        SH = Namespace("http://www.w3.org/ns/shacl#")
        mapping: dict = {}
        for name in _SHACL_ENTRIES_WITH_ONTOLOGY_COUNTERPART:
            for s in get_ontology_graph(name).subjects(RDF.type, SH.ShapesGraph):
                mapping[s] = name
        _REAL_SHAPES_GRAPH_IRI_TO_NAME = mapping
    return _REAL_SHAPES_GRAPH_IRI_TO_NAME


def local_loader(iri: URIRef) -> StarLayerGraph | None:
    """A ``StarLayerGraph.resolve_imports()``-compatible loader that only
    ever reads this package's own bundled files - never the network,
    never anything outside this registry. Reverse-maps ``iri`` against
    every registered shapes entry's own real ``sh:ShapesGraph`` node
    (confirmed via ``_real_shapes_graph_iri_to_name()`` above - not
    ``get_resource_iri()``'s own, separate GitHub-blob-URL identity).
    Returns ``None`` for anything not registered here, rather than
    raising - exactly what ``resolve_imports()`` already expects for "this
    loader doesn't know that one," so an attempt to import something
    genuinely external through this loader is safely skipped, not an
    error.

    This is what makes resolving ``starontology``'s own imports safe to
    do without any of the caution a general, caller-supplied
    ``shacl_graph``/``ont_graph`` needs: this loader provably never
    leaves the package, so there's no network dependency, no
    non-determinism, and nothing to secure against - unlike an arbitrary
    graph's own ``owl:imports``, which could point anywhere.
    """
    name = _real_shapes_graph_iri_to_name().get(iri)
    if name is None:
        return None
    return get_ontology_graph(name)
