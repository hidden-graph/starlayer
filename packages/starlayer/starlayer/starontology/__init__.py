"""starlayer.starontology - the raw ontology/SHACL-shapes ``.ttl`` files
this stack ships, kept in one place, independent of which *other*
subpackage ends up consuming them.

**Why this exists as one place.** These files could otherwise live
scattered across whichever package happens to consume them first (e.g.
``manch:``/``skos:`` inside a graph-focused package, ``salg:`` inside a
sparql-focused one). That would make "where do I edit the ``manch:``
vocabulary" and "where do I edit the ``salg:`` vocabulary" different
answers depending on which package happens to need it - a real
editing/discoverability cost, not just an aesthetic one. Consolidating
them here means one place to look, one place to edit, regardless of which
sibling subpackage(s) end up consuming a given file.

**Why this is part of ``starlayer`` rather than a separately installed
package.** `starlayer.sparql` has a hard, eager runtime dependency on this
subpackage (`sparql_shapes.py`/`srl.py` both call `get_ontology_graph()`
to build their shapes). Two packages that can't function without each
other would be packaging overhead with no real isolation benefit - the
same reasoning that keeps `starlayer.graph`/`.sparql`/`.shacl` merged into
one `starlayer` package rather than split apart. `from starlayer import
starontology` (or `starlayer.starontology.X`) is the only way to reach
anything here.

**Why this stays its own named subpackage, not flattened into another
one.** Each `.ttl` file here is pure data with no logic of its own - one
place to look, one place to edit, regardless of which sibling subpackage
ends up consuming a given file. This top-level module
(`starontology/__init__.py` itself) stays that way: it loads a graph and
nothing more, never wraps `pyshacl`/`starlayer.shacl`. *How* to validate
(which reasoning settings, which severity flags) stays each vocabulary's
own concern, genuinely different per vocabulary -
`starlayer.sparql.salg.sparql_shapes.validate_query()` for `salg:` still lives
outside this subpackage entirely.

`starontology.manchester`/`starontology.skos` are the exceptions - real
logic for the `manch:`/`skos:` vocabularies (parse/serialize/validate for
`manch:`, just validate for `skos:`, which needs no encode/decode layer at
all), since validating (or, for `manch:`, editing) a vocabulary against/as
its own structure is an ontology-management concern in its own right, not
a `starlayer.graph`/`.sparql`/`.ontology` one. `srl:` is expected to join
them here eventually for the
same reason, once it's separable from the sibling `starlayer.sparql`
package's shared internals it currently depends on. So: this top-level
module stays data-only, but a named submodule (`starontology.manchester`/
`.skos`, and later `.srl`) can hold real logic when the vocabulary itself
needs more than a loader - see each submodule's own docstring for its full
reasoning (and, for `starontology.manchester`, the circular-import
discipline its logic follows - `starontology.skos` doesn't need that, since
it never touches `starlayer.graph` at all).

**Why every loader returns a `StarLayerGraph`, not a plain `rdflib.Graph`.**
API consistency with the rest of the stack: none of the registered
entries actually carry RDF 1.2 content (triple terms, direction-tagged
literals) themselves - they're ordinary RDF 1.1 vocabulary/shape
definitions - so a plain `rdflib.Graph` would be functionally sufficient,
but returning the same type every other loader in this stack returns
keeps callers from needing to special-case this subpackage. This means
depending on `starlayer.graph`; that import stays lazy (deferred inside
each loader function, not at module top level), matching every other
cross-subpackage import in this stack.

**Registry API.** One small registry: ``get_ontology_list()`` returns
every entry's metadata, ``get_ontology_graph(name)`` loads one by name.
Each entry's filename (``_FILENAME_BY_NAME``) is private internal
plumbing for this module's own registry and for computing that entry's
resource IRI - not a public way to reach the data. To get an entry's
content as Turtle text: ``get_ontology_graph(name).serialize(format=
'turtle12')``.

**What's here**: thirteen registered entries - an OWL/RDFS ontology and a
SHACL shapes graph for each of six vocabularies, plus one further
registered entry (``shacl_meta``, see below) with no ontology counterpart.
The filenames below are each entry's own identity (both as a dict key
into the dataset described further below and as the ``.../<filename>``
suffix of its ``get_resource_iri()`` IRI):

- ``manch:`` (``manchester-ast-ontology.ttl`` / ``manchester_shapes.ttl``) -
  OWL 2 Manchester Syntax's own internal AST as RDF. Type ``"ast-graph"``.
- ``skos:`` (``skos-ontology.ttl`` / ``skos_shapes.ttl``) - the W3C SKOS
  Reference's own formal axioms and integrity conditions, over the real
  ``skos:`` namespace. Type ``"owl"`` - unlike the other vocabularies,
  this is a real semantic ontology (actual axioms about an existing
  vocabulary), not a syntax tree represented as RDF, so it doesn't get the
  ``"ast-graph"`` label the others earn.
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
- ``spexpr:`` (``spexpr-ontology.ttl`` / ``spexpr_shapes.ttl``) - the
  SPARQL expression/variable/property-path vocabulary, the one slice
  ``salg:``/``sqe:``/``srl:`` all need identically (their own expression
  encoding, reused unchanged rather than reimplemented per-vocabulary);
  each of those three's own shapes file imports this one's shapes via
  ``owl:imports`` rather than defining it separately. Type ``"ast-graph"``.

Every shapes file (all six) is type ``"shacl"``, regardless of which of
the above its own target ontology is.

The further entry, ``shacl_meta`` (also type ``"shacl"``), is the SHACL
1.2 meta-shapes themselves (``starlayer.shacl``'s own shapes-about-shapes,
validating a shapes graph's own well-formedness) - loaded exactly like
every other entry, via the shared ``_load()``. There's no ``shacl_owl``
counterpart, since this entry has no ontology of its own to pair with.

The stored content is a one-time snapshot of
``starlayer.shacl.meta_shapes.build_meta_shapes_graph()``'s own output
with no ``extra_graphs`` - the common case, and the only one a *registry
entry* (a fixed, nameable resource) can represent at all.
``build_meta_shapes_graph()`` itself is deliberately **not** replaced or
removed: ``starlayer.shacl.validator.py``'s own internal meta-shacl
preflight (``meta_validate()``, used by every ``validate(meta_shacl=True)``
call) still calls it dynamically every time, since a *caller's own*
``extra_graphs`` there is genuinely per-call data this static snapshot
has no way to represent. (That preflight's own, separate performance
concern - re-running a full meta-validation pass on every call regardless
of ``extra_graphs`` - is addressed independently, by content-hash-keyed
result caching inside ``meta_validate()`` itself; see that module's own
comments.) The two code paths simply agree, rather than one replacing
the other: this registry's stored copy for "give me the meta-shapes
graph as data," ``build_meta_shapes_graph()`` live for "check this shapes
graph is well-formed, possibly with extra rules."

**One dataset, not thirteen files.** Every registered entry, plus the
ontology-shapes profile mapping (see below), lives as its own named graph
inside one file, ``starontology.trig`` (TriG - Turtle's own named-graph
extension, so every entry stays as readable/diffable as a standalone
``.ttl`` file would be). Each named graph's context IRI is the same
GitHub-blob-URL resource identity ``get_resource_iri()``/``_resource_iri()``
mints for that entry, so every ``prof:isProfileOf`` triple and every
caller's own ``validate(shapes_graph_resource=...)`` usage keeps working
regardless of how the data is actually stored on disk. ``_dataset()``
parses the whole file once and caches the result (never mutated, never
handed to a caller directly); ``_named_graph(context_iri)`` copies just one
named graph's triples into a fresh ``Graph`` per call, which is what every
public function below actually returns.

**``get_profile_graph()``**: every registered shapes graph is related by
the dx-prof vocabulary's ``prof:isProfileOf`` to the *real external
specification* it implements (SPARQL, SKOS, Manchester Syntax,
SPARQL-RL) - not to the bundled ontology/AST graph. The ontology/AST graph
is instead one of that same real specification's own
``prof:hasResource``/``prof:ResourceDescriptor`` entries (``prof:hasRole
role:schema``), a sibling of the shapes graph's own ``role:validation``
descriptor. ``sparql_shacl``/``sparql_owl`` (``salg:``) are deliberately
excluded from this mapping entirely - unlike the other pairs, ``salg:`` is
this project's own internal SPARQL algebra encoding, not something meant
to carry a public-facing conformance claim. This plugs directly into
``starlayer.shacl.profiling.derive_conforms_to()``'s own
``specification_graph=`` parameter - see ``get_profile_graph()``'s own
docstring for the full design and a worked example.

The mapping itself lives in a real, persisted document
(``ontology-shapes-profiles.ttl``, stored as its own named graph inside
``starontology.trig``), not assembled in memory from a Python dict - a
profile relationship is genuine, persisted metadata (the same way
``starlayer.shacl``'s own ``shacl12-conformance-profile.ttl`` is a real
file), deliberately independent of both endpoints it relates (mixing
profile metadata into either the ontology or the shapes graph would
conflate two different concerns - see that named graph's own header
comment). ``get_conformance_profiles(url=...)`` loads it (the bundled copy
by default, or any local path/``http(s)://`` location instead);
``get_profile_graph(shapes_name, url=...)`` is a thin filter over that
same document.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rdflib import Graph, Namespace, URIRef

if TYPE_CHECKING:
    from starlayer.graph import StarLayerGraph

PROF = Namespace("http://www.w3.org/ns/dx/prof/")

_HERE = Path(__file__).parent

# Every registered ontology/shapes entry, plus the ontology-shapes profile
# mapping, lives in ONE multi-graph dataset file (starontology.trig), not
# as separate .ttl files. Each entry keeps its own real identity as a
# *named graph* inside that one file, rather than as a separate file on
# disk - see _dataset()/_named_graph() below for how that's read back out,
# and this module's own docstring for the full reasoning (one dataset is
# easier to hand to tooling as a whole, and avoids many independently-
# tracked files for content that's always shipped and read together
# anyway).
_DATASET_TTL_PATH = _HERE / "starontology.trig"

# Each registered name's own filename *within* the dataset - reused only
# to compute _resource_iri() below (the same GitHub-blob-URL identity this
# project uses elsewhere), not to open a file directly.
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
    # shacl_meta gets a real resource IRI too (used by
    # ontology-shapes-profiles.ttl's own prof:isProfileOf entry for it -
    # see get_profile_graph()'s docstring) - it's a real named graph in
    # starontology.trig at this filename, loaded via the shared _load()
    # like every other entry (see the module docstring's "What's here"
    # section for why build_meta_shapes_graph() still exists separately).
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
                "(spexpr:), carved out of salg: - the one slice "
                "salg:/sqe:/srl: all need identically (their own expression "
                "encoding, reused unchanged, not reimplemented per-vocabulary)."
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
                "well-formedness) - a real stored snapshot (no "
                "extra_graphs) of starlayer.shacl.meta_shapes."
                "build_meta_shapes_graph()'s own output; there's still no "
                "shacl_owl counterpart, since this entry has no ontology "
                "of its own to pair with."
            ),
            type="shacl",
        ),
        lambda: _load("shacl_meta"),
    ),
}


_dataset_cache: Any | None = None


def _dataset() -> Any:
    """The shared ``rdflib.Dataset`` backing every file-based registry
    entry plus the ontology-shapes profile mapping - parsed from
    ``starontology.trig`` once and cached, not re-parsed on every
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
    ``starontology.trig``'s own header) onto ``graph``. This matters
    because copying triples one at a time via ``graph.add(triple)``
    (``_named_graph()``'s own approach, needed since two callers must
    never share - or corrupt - the same graph object) never carries over
    namespace bindings the way ``graph.parse(path)`` does when reading a
    standalone file directly. Without this,
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
    # initializes a parent package before any of its submodules). If
    # starontology is ever the thing being imported first, and something
    # in that chain reads back into this module's own registry before the
    # import finishes, a top-level import here would deadlock
    # (AttributeError on a "partially initialized module"). Deferring this
    # import until a loader is actually *called* means starontology always
    # finishes its own import first, breaking the cycle - kept this way as
    # defensive practice even though nothing in today's starlayer/__init__.py
    # triggers it, matching this module's own docstring on lazy imports.
    from starlayer.graph import StarLayerGraph

    # identifier=_resource_iri(name): without this, every returned graph
    # gets rdflib's own random default BNode identity, so a caller who
    # forgot to pass validate(..., shapes_graph_resource=...) explicitly
    # gets no sh:usedShapesGraph/sh:conformsTo/dcterms:conformsTo at all
    # (validate()'s own .identifier fallback only fires for a real
    # URIRef, never a BNode). Giving the graph its real resource IRI as
    # its own identity makes that fallback recover it automatically.
    g = StarLayerGraph(identifier=_resource_iri(name))
    _bind_dataset_namespaces(g)
    for triple in _named_graph(_resource_iri(name)):
        g.add(triple)
    return g


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
# validates - every "*_shacl" entry except "shacl_meta" (no "shacl_owl"
# entry exists, since shacl_meta has no ontology of its own to pair
# with). Just the name list - the actual prof:isProfileOf pairing itself
# lives in ontology-shapes-profiles.ttl, not here, deliberately: this
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
# does"). shacl_meta has a real prof:isProfileOf entry there too (against
# the public SHACL profile IRIs it represents) despite having no ontology
# counterpart at all - the two facts are independent.
_SHACL_ENTRIES_WITH_PROFILE_MAPPING = _SHACL_ENTRIES_WITH_ONTOLOGY_COUNTERPART + ("shacl_meta",)

# Same "GitHub blob URL as a resource identity" convention
# starlayer.shacl's own shacl12-conformance-profile.ttl already established
# for its one self-declaration resource (that file's own subject IRI was
# stale, still naming the pre-merge "packages/shacl" path, until fixed
# 2026-10-14 alongside this same pass - see that file's own header
# comment) - computed from each entry's own current, correct filename
# here. Each entry's resource identity is "the GitHub blob URL its
# content used to live at as a standalone file," kept stable even though
# the content itself now lives as a named graph inside one dataset file
# (below) rather than as that standalone file - so nothing that already
# depends on this IRI (prof:isProfileOf triples,
# validate(shapes_graph_resource=...) callers) breaks when the storage
# format changes.
_GITHUB_BLOB_BASE = "https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/starontology/"

# A *different* URL from the resource identity above - this one is for
# actually fetching an entry's real bytes, not for identifying it. A blob
# URL (above) renders a nice HTML page to a plain HTTP GET, not the file's
# real content; raw.githubusercontent.com does. Deliberately a second,
# separate base rather than changing _GITHUB_BLOB_BASE itself - the blob
# value is also the dataset's own internal named-graph context IRI (see
# _resource_iri()'s own callers), so changing it would silently break
# every lookup into starontology.trig and the identities already asserted
# in ontology-shapes-profiles.ttl's own prof:isProfileOf triples. Standard
# Linked Data move: a resource's IRI need not be the same URL you fetch a
# representation from. See scripts/publish_starontology_files.py - this
# URL is only real once that script's own output has been committed.
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/starontology/"


def _resource_iri(name: str) -> URIRef:
    return URIRef(_GITHUB_BLOB_BASE + _FILENAME_BY_NAME[name])


def _raw_filename(name: str) -> str | None:
    if name == "ontology_shapes_profiles":
        return _PROFILES_FILENAME
    return _FILENAME_BY_NAME.get(name)


def get_resource_iri(name: str) -> URIRef | None:
    """The stable resource IRI ``get_profile_graph()`` uses to identify
    ``name``'s own registered file (a GitHub blob URL - see
    ``_GITHUB_BLOB_BASE``'s own neighboring comment for the convention).
    Returns ``None`` for an unregistered name, matching
    ``get_profile_graph()``'s own no-raise convention.

    ``"shacl_meta"`` gets a real IRI here too, despite having no ontology
    counterpart - it's the same one ``ontology-shapes-profiles.ttl``
    already uses for its own ``prof:isProfileOf`` entry.

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


def get_raw_url(name: str) -> str | None:
    """Where to actually fetch ``name``'s own real content from - a
    ``raw.githubusercontent.com`` URL, unlike :func:`get_resource_iri`'s
    GitHub blob URL (which identifies the resource but returns an HTML
    viewer page to a plain HTTP GET, not the file's real bytes).

    Accepts every name :func:`get_resource_iri` does, plus
    ``"ontology_shapes_profiles"`` for the profiles-mapping document
    itself (:func:`get_conformance_profiles`'s own bundled default,
    not one of the 13 registered ontology/shapes entries, so it has no
    :func:`get_resource_iri` equivalent). Returns ``None`` for any other
    unrecognized name.

    Only real once ``scripts/publish_starontology_files.py``'s own output
    has been committed - that script regenerates the standalone file this
    URL points at from ``starontology.trig``, the one real source of
    truth. Nothing about how :func:`get_ontology_graph`/
    :func:`get_conformance_profiles` read data at runtime depends on this
    URL or the file it points at - both still read ``starontology.trig``
    directly.
    """
    filename = _raw_filename(name)
    if filename is None:
        return None
    return _GITHUB_RAW_BASE + filename


def get_conformance_profiles(url: str | None = None) -> StarLayerGraph:
    """Every registered shapes graph's real relationship to its
    specification, as one real persisted named graph
    (``<.../ontology-shapes-profiles.ttl>`` inside ``starontology.trig``) -
    not synthesized from this module's own registry on the fly. See that
    named graph's own context (and this module's own docstring) for why
    the mapping is a third, independent identity rather than embedded in
    either endpoint.

    Each registered shapes graph is ``prof:isProfileOf`` the real external
    specification it implements (SPARQL, SKOS, Manchester Syntax,
    SPARQL-RL) - not the bundled ontology/AST-as-RDF graph, which is
    instead one of that same real specification's own
    ``prof:hasResource``/``prof:ResourceDescriptor`` entries
    (``prof:hasRole role:schema``), a sibling of the shapes graph's own
    ``role:validation`` descriptor. See ``get_profile_graph()``'s own
    docstring for the full design.

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
    ``get_ontology_graph()``/``_load()`` convention. This matters because
    ``.serialize(format="turtle12")`` is handled by
    ``StarLayerGraph.serialize()``'s own override, not a real globally-
    registered rdflib plugin - a plain ``rdflib.Graph`` wouldn't support
    it, so a caller calling that format on this result gets the same
    behavior as on every other registered entry.
    """
    from starlayer.graph import (
        StarLayerGraph,  # lazy: avoids a circular-import deadlock, see _load()'s own comment
    )

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

    The convention this project follows: the shapes graph itself is
    ``prof:isProfileOf`` the real external specification (e.g. SPARQL 1.2
    Query, the SKOS Reference, OWL 2 Manchester Syntax) - the same
    predicate ``starlayer.shacl.profiling.derive_conforms_to()``'s own
    ``specification_graph=`` parameter already expects, and the exact
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
    something the shapes graph is itself a profile *of*.

    A pair with no real external specification of its own (``sqe:``,
    ``spexpr:``) still profiles one correctly - both are genuinely part of
    SPARQL 1.2 Query's own grammar (raw parse tree / shared expression
    vocabulary respectively), so both point at
    ``https://www.w3.org/TR/sparql12-query``.

    **``sparql_shacl``/``sparql_owl`` (``salg:``) excluded entirely**:
    unlike the other five pairs, ``salg:`` is this project's own internal
    SPARQL algebra encoding - not something meant to carry a
    public-facing conformance claim. ``get_profile_graph("sparql_shacl")``
    returns an empty graph (it's still a real registered entry, just one
    this document has nothing to say about), never ``None``.

    ``"shacl_meta"`` has a real entry too, despite having no ontology
    counterpart at all - ``starlayer``'s own SHACL meta-shapes graph
    declares ``prof:isProfileOf`` the public SHACL 1.2 profile IRIs it
    represents (Core/SPARQL/Node-Expressions/Rules/Profiling - the same
    five ``declared_conformance_profile()`` already claims). No
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

    from starlayer.graph import (
        StarLayerGraph,  # lazy: avoids a circular-import deadlock, see _load()'s own comment
    )

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
# starlayer/shacl/CLAUDE.md for why these two identities exist and don't
# currently match each other). Lazily built, cached: every registered
# file is static and bundled, never changes at runtime, so re-parsing all
# six on every local_loader() call would be pure waste.
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
    (via ``_real_shapes_graph_iri_to_name()`` above - not
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
