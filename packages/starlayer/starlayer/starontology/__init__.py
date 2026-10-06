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
The path constants are now private (``_MANCHESTER_ONTOLOGY_TTL_PATH``, etc.) -
internal plumbing for this module's own registry, not a public way to
reach the data. Anyone who wants the file's content uses
``get_ontology_graph(name)`` instead (``.serialize(format='turtle12')`` on
the result for Turtle text - a dedicated ``get_ontology_turtle12()``
wrapper existed briefly but was removed 2026-10-03, since it was exactly
that one-line composition and nothing more); anyone who genuinely needs
the raw on-disk bytes (none of this stack's own code does - checked) can
still find the file next to this module, it's just not exposed as a named
constant anymore.

**What's here**: ten *files* on disk, two per vocabulary (an OWL/RDFS
ontology and a SHACL shapes graph) for five vocabularies - plus an
eleventh *registered entry* (``shacl_meta``, see below) backed by
generated Python rather than a file:

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
other eight entries call ``_load()`` on their own ``.ttl`` file. No
``*_TTL_PATH`` constant exists for it (nothing to point at - it's
generated, not file-backed).

Every loader returns a **fresh ``StarLayerGraph``** - see the "Dependency
note" above for what that costs and why it was accepted. None of these
nine entries actually carry RDF 1.2 content (triple terms,
direction-tagged literals) themselves - they're ordinary RDF 1.1
vocabulary/shape definitions - so a plain ``rdflib.Graph`` would have been
functionally sufficient; ``StarLayerGraph`` is used for API consistency
with the rest of the stack instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from starlayer.graph import StarLayerGraph

_HERE = Path(__file__).parent

_MANCHESTER_ONTOLOGY_TTL_PATH = _HERE / "manchester-ast-ontology.ttl"
_MANCHESTER_SHAPES_TTL_PATH = _HERE / "manchester_shapes.ttl"
_SKOS_ONTOLOGY_TTL_PATH = _HERE / "skos-ontology.ttl"
_SKOS_SHAPES_TTL_PATH = _HERE / "skos_shapes.ttl"
_SPARQL_ONTOLOGY_TTL_PATH = _HERE / "salg-ontology.ttl"
_SPARQL_SHAPES_TTL_PATH = _HERE / "sparql_shapes.ttl"
_SQE_ONTOLOGY_TTL_PATH = _HERE / "sqe-ontology.ttl"
_SQE_SHAPES_TTL_PATH = _HERE / "sqe_shapes.ttl"
_SRL_ONTOLOGY_TTL_PATH = _HERE / "srl-ontology.ttl"
_SRL_SHAPES_TTL_PATH = _HERE / "srl_shapes.ttl"


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
        lambda _p=_MANCHESTER_ONTOLOGY_TTL_PATH: _load(_p),
    ),
    "manchester_shacl": (
        OntologyInfo(
            name="manchester_shacl",
            description="SHACL shapes validating a manch: AST graph's own structural well-formedness.",
            type="shacl",
        ),
        lambda _p=_MANCHESTER_SHAPES_TTL_PATH: _load(_p),
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
        lambda _p=_SKOS_ONTOLOGY_TTL_PATH: _load(_p),
    ),
    "skos_shacl": (
        OntologyInfo(
            name="skos_shacl",
            description="SHACL shapes checking SKOS's own numbered integrity conditions against a data graph.",
            type="shacl",
        ),
        lambda _p=_SKOS_SHAPES_TTL_PATH: _load(_p),
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
        lambda _p=_SPARQL_ONTOLOGY_TTL_PATH: _load(_p),
    ),
    "sparql_shacl": (
        OntologyInfo(
            name="sparql_shacl",
            description="SHACL shapes validating a salg: algebra graph's own structural well-formedness.",
            type="shacl",
        ),
        lambda _p=_SPARQL_SHAPES_TTL_PATH: _load(_p),
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
        lambda _p=_SQE_ONTOLOGY_TTL_PATH: _load(_p),
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
        lambda _p=_SQE_SHAPES_TTL_PATH: _load(_p),
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
        lambda _p=_SRL_ONTOLOGY_TTL_PATH: _load(_p),
    ),
    "srl_shacl": (
        OntologyInfo(
            name="srl_shacl",
            description="SHACL shapes validating an srl: rule-set graph's own structural well-formedness.",
            type="shacl",
        ),
        lambda _p=_SRL_SHAPES_TTL_PATH: _load(_p),
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


def _load(path: Path) -> StarLayerGraph:
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

    g = StarLayerGraph()
    g.parse(source=str(path), format="turtle")
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
