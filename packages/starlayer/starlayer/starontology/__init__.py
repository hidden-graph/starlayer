"""starlayer.starontology - the raw ontology/SHACL-shapes ``.ttl`` files
this stack ships, kept in one place, independent of which *other*
subpackage ends up consuming them.

**Why this exists as one place.** These files could otherwise live
scattered across whichever package happens to consume them first (e.g.
``manch:``/``skos:`` inside a graph-focused package, ``sqe:``/``srl:`` inside a
sparql-focused one). That would make "where do I edit the ``manch:``
vocabulary" and "where do I edit the ``sqe:`` vocabulary" different
answers depending on which package happens to need it - a real
editing/discoverability cost, not just an aesthetic one. Consolidating
them here means one place to look, one place to edit, regardless of which
sibling subpackage(s) end up consuming a given file.

**Why this is part of ``starlayer`` rather than a separately installed
package.** `starlayer.sparql` has a hard, eager runtime dependency on this
subpackage (`srl.py`/`sqe/shapes.py` both call `get_ontology_graph()`
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
`starlayer.sparql.srl.srl_validate()` for `srl:` lives
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

**What the loaders return.** ``get_ontology_graph(name)`` and ``get_conformance_profiles()`` return a fresh `StarLayerGraph` (pyoxigraph
terms; only the prefixes the graph's IRIs use). None of the registered entries carries RDF 1.2 content (triple terms,
direction-tagged literals): they are ordinary RDF 1.1 vocabulary and shape definitions. The files are parsed once by Oxigraph
and cached; each call copies the cached triples. The ``starlayer.graph`` import stays lazy (deferred inside the loader
functions), matching every other cross-subpackage import in this stack.

**Registry API.** One small registry: ``get_ontology_list()`` returns
every entry's metadata, ``get_ontology_graph(name)`` loads one by name.
Each entry's filename (``_FILENAME_BY_NAME``) is private internal
plumbing for this module's own registry and for computing that entry's
resource IRI - not a public way to reach the data. To get an entry's
content as Turtle text: ``get_ontology_graph(name).serialize(format=
'turtle12')``.

**What's here**: an OWL/RDFS ontology and a SHACL shapes graph for each of
five vocabularies, plus further registered entries with no ontology
counterpart: ``shacl_shacl`` (see below), and the SHACL vocabulary, UI and
rules entries ``shacl_vocabulary``, ``shacl_shacl_rules``, ``shacl_shacl_ui``,
``shacl_shacl_ui_scores`` and ``shacl_ui_baseline`` (each described in its
registry entry). ``sorted(_REGISTRY)`` is the full list.
The filenames below are each entry's own identity (both as a dict key
into the dataset described further below and as the ``.../<filename>``
suffix of its ``get_resource_iri()`` IRI):

- ``manch:`` (``manchester-ast-ontology.ttl`` / ``manchester_shapes.ttl``) -
  OWL 2 Manchester Syntax's own internal syntax tree, as RDF. Type
  ``"syntax-tree-graph"``.
- ``skos:`` (``skos-ontology.ttl`` / ``skos_shapes.ttl``) - the W3C's own
  SKOS vocabulary (``skos.rdf`` from the SKOS Reference, copied unchanged
  in content and converted to Turtle, under the W3C Software and Document
  License - see the notice at the top of ``skos-ontology.ttl``), paired
  with our own shapes for the Reference's numbered conditions and a
  lightweight set of form-widget annotations, over the
  real ``skos:`` namespace. Type ``"owl"`` - unlike the other vocabularies,
  this is a real semantic ontology (actual axioms about an existing
  vocabulary), not a syntax tree represented as RDF, so it doesn't get the
  ``"syntax-tree-graph"`` label the others earn.
- ``sqe:`` (``sqe-ontology.ttl`` / ``sqe_shapes.ttl``) - a SPARQL
  `SELECT`/`ASK`/`CONSTRUCT` query's own raw parse tree (pre-
  `translateQuery`), as a flat, human-readable RDF tree meant for hand/UI
  editing (see `starlayer.sparql.sqe`'s own module docstrings). Type ``"syntax-tree-graph"``.
- ``srl:`` (``srl-ontology.ttl`` / ``srl_shapes.ttl``) - SRL's
  own rule-set syntax tree, as RDF (see `starlayer.sparql.srl`).
  Type ``"syntax-tree-graph"``.
- ``spexpr:`` (``spexpr-ontology.ttl`` / ``spexpr_shapes.ttl``) - the
  SPARQL expression/variable/property-path vocabulary, the one slice
  ``sqe:``/``srl:`` both need identically (their own expression
  encoding, reused unchanged rather than reimplemented per-vocabulary);
  each of those two's own shapes file imports this one's shapes via
  ``owl:imports`` rather than defining it separately. Type
  ``"syntax-tree-graph"``.

Every shapes file (all six) is type ``"shacl"``, regardless of which of
the above its own target ontology is.

The further entry, ``shacl_shacl`` (also type ``"shacl"``), is the SHACL
1.2 meta-shapes themselves (``starlayer.shacl``'s own shapes-about-shapes,
validating a shapes graph's own well-formedness) - loaded exactly like
every other entry, via the shared ``_load()``. There's no ``shacl_owl``
counterpart, since this entry has no ontology of its own to pair with.

This stored graph (``shacl12-shacl.ttl``) is the one
``starlayer.shacl.meta_shapes.meta_validate()`` reads at run time, via
``load_meta_shapes_graph()``, instead of reassembling it on every call.
It is generated by ``scripts/build_starontology.py`` (via
``scripts/build_meta_shapes.py``) - the W3C Data Shapes Working Group's
SHACL-for-SHACL (a pinned copy) plus starShacl's additions; nothing in the
Working Group's file is deleted. Editing the additions, or updating the pinned
copy, changes nothing at run time until that script is re-run; a test fails
while the stored copy and a fresh build disagree.
The build code is not part of the installed library.

**One Turtle file per entry, a TriG copy for convenience.** Every registered
entry, and the profiles document (see below), is one ``.ttl`` file in this
directory, and those files are the source. ``get_ontology_graph()`` parses
only the file it is asked for, once, and caches it (``_file_graph()``);
``_named_graph(context_iri)`` copies its triples into a fresh ``StarLayerGraph`` per
call, which is what every public function below returns. Each entry's
identity is the GitHub-blob-URL resource IRI ``get_resource_iri()`` mints
for it, which is also its ``.../<filename>`` file, so every
``prof:isProfileOf`` triple and every caller's own
``validate(shapes_graph_resource=...)`` usage keeps working. Two files are
generated, not hand-edited: ``shacl12-shacl.ttl`` and ``skos-ontology.ttl``
(see ``scripts/build_starontology.py``). ``starontology.trig`` holds the same
graphs as named graphs in a single file, for tooling that wants everything
at once; the build script regenerates it and a test fails if it drifts from
the ``.ttl`` files, but nothing in the library reads it.

**``get_conformance_profiles()``**: StarLayer defines its own profiles
(``slp:Manchester``, ``slp:Skos``, ``slp:SparqlQuery``, ``slp:SparqlRL``,
``slp:Shacl``), each a ``prof:Profile`` that is ``prof:isProfileOf`` the
public specification or public SHACL profiles it relates to, and lists its
ontology/syntax-tree graph (``role:schema``) and shapes graph
(``role:validation``) as ``prof:hasResource`` entries. A shapes graph does
not claim to be a profile of the public specification itself: data that
conforms to it conforms to the StarLayer profile that lists it, and that
profile's ``prof:isProfileOf`` link carries the claim to the public layer.
This plugs directly into
``starlayer.shacl.profiling.derive_conforms_to()``'s own
``specification_graph=`` parameter - see ``get_conformance_profiles()``'s
own docstring for the full design and a worked example. There is
deliberately no per-entry filter function - a caller who only wants one
pair's own triples can query/extract that slice from the full graph
themselves (e.g. ``graph.triples((profile, PROF.hasResource, None))``).

The profiles document (``starlayer-profiles.ttl``) holds StarLayer's profiles and
its conformance declaration together, in a real persisted document rather
than assembled in memory: each StarLayer profile (``slp:``) is a
``prof:Profile`` of a public specification or public SHACL profile and
lists its ontology and shapes files as resources; the document also
declares the conformance of ``starlayer.graph``, ``starlayer.sparql`` and
``starlayer.shacl`` themselves. It is deliberately independent of the
files it describes (mixing profile metadata into an ontology or shapes
graph would conflate two concerns - see that file's own header comment). ``get_conformance_profiles(url=...)`` loads it - the bundled copy
by default, or any local path/``http(s)://`` location instead.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyoxigraph as ox


def __getattr__(name: str) -> Any:
    """``PROF``, the profiles vocabulary as a namespace of pyoxigraph ``NamedNode`` constants (``PROF.hasResource``), is built on first use."""
    if name == "PROF":
        from starlayer.shacl_engine.terms import NS

        return NS("http://www.w3.org/ns/dx/prof/")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


_HERE = Path(__file__).parent

# Every registered ontology/shapes entry, and the profiles document, is one
# Turtle file in this directory (the file named in _FILENAME_BY_NAME below).
# Those files are the source: edit them directly, except the two generated
# ones (shacl12-shacl.ttl, skos-ontology.ttl), which scripts/ rebuilds.
# Each is parsed on first use and cached, so asking for one entry never
# parses the others. starontology.trig, the same graphs in one TriG file, is
# generated from these files by scripts/build_starontology.py as a
# convenience for tooling that wants everything at once; nothing here reads
# it.
_DATASET_TTL_PATH = _HERE / "starontology.trig"

# Prefixes bound onto every graph this module hands out (and written into the
# header of starontology.trig). Callers rely on them being present.
_PREFIXES: dict[str, str] = {
    "conformance": "https://github.com/hidden-graph/starlayer/ns/conformance#",
    "dcterms": "http://purl.org/dc/terms/",
    "manch": "https://github.com/hidden-graph/starlayer/ns/graph/manchester-ast#",
    "owl": "http://www.w3.org/2002/07/owl#",
    "pkg": "https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/",
    "prof": "http://www.w3.org/ns/dx/prof/",
    "profile": "http://www.w3.org/ns/shacl/profile/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "role": "http://www.w3.org/ns/dx/prof/role/",
    "sh": "http://www.w3.org/ns/shacl#",
    "shnex": "http://www.w3.org/ns/shacl-node-expr#",
    "shsh": "http://www.w3.org/ns/shacl-shacl#",
    "shui": "http://www.w3.org/ns/shacl-ui#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
    "skshp": "https://github.com/hidden-graph/starlayer/ns/graph/skos-shapes#",
    "slp": "https://github.com/hidden-graph/starlayer/ns/profile#",
    "spexpr": "https://github.com/hidden-graph/starlayer/ns/sparql/expr#",
    "sqe": "https://github.com/hidden-graph/starlayer/ns/sparql/query-edit#",
    "srl": "https://github.com/hidden-graph/starlayer/ns/sparql/srl#",
    "starontology": "https://github.com/hidden-graph/starlayer/blob/main/packages/starlayer/starlayer/starontology/",
    "stsh": "https://github.com/hidden-graph/starlayer/ns/shacl#",
    "tr": "https://www.w3.org/TR/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

# Each registered name's own filename *within* the dataset - reused only
# to compute _resource_iri() below (the same GitHub-blob-URL identity this
# project uses elsewhere), not to open a file directly.
_FILENAME_BY_NAME: dict[str, str] = {
    "manchester_owl": "manchester-ast-ontology.ttl",
    "manchester_shacl": "manchester_shapes.ttl",
    "skos_owl": "skos-ontology.ttl",
    "skos_shacl": "skos_shapes.ttl",
    "sqe_owl": "sqe-ontology.ttl",
    "sqe_shacl": "sqe_shapes.ttl",
    "srl_owl": "srl-ontology.ttl",
    "srl_shacl": "srl_shapes.ttl",
    "spexpr_owl": "spexpr-ontology.ttl",
    "spexpr_shacl": "spexpr_shapes.ttl",
    # shacl_shacl gets a real resource IRI too (used by
    # starlayer-profiles.ttl's own prof:isProfileOf entry for it -
    # see get_conformance_profiles()'s docstring) - a generated .ttl at this
    # filename, loaded via the shared _load() like every other entry.
    "shacl_shacl": "shacl12-shacl.ttl",
    # The SHACL 1.2 vocabulary (the W3C WG's shacl.ttl): what the sh: terms are, for reasoning about types. Generated.
    "shacl_vocabulary": "shacl12-vocabulary.ttl",
    # Companions of shacl_shacl and the SHACL UI widget selection (GitHub issues #12 and #10). Hand-edited files.
    "shacl_shacl_ui": "shacl12-shacl-ui.ttl",
    "shacl_ui_baseline": "shacl-ui-baseline.ttl",
    "shacl_shacl_ui_scores": "shacl12-shacl-ui-scores.ttl",
    # What the structure of a shapes graph entails about it: rules that add the shape types (GitHub issues #24, #27, #28).
    "shacl_shacl_rules": "shacl12-shacl-rules.ttl",
}

# The ontology-shapes profile mapping's own filename/named-graph identity -
# see get_conformance_profiles() below, and the module docstring for
# why it's a named graph inside the same dataset rather than embedded in
# either endpoint it relates.
_PROFILES_FILENAME = "starlayer-profiles.ttl"


@dataclass(frozen=True)
class OntologyInfo:
    """One registered ontology/shapes file's metadata - no ``validate``
    hook alongside it, since this package itself does no validation (see
    this module's own docstring); ``get_ontology_graph()`` is the way to
    actually load one."""

    name: str
    description: str
    type: str  # "shacl" | "syntax-tree-graph" | "owl" | "scoring-catalog"


_REGISTRY: dict[str, tuple[OntologyInfo, Callable[[], Any]]] = {
    "manchester_owl": (
        OntologyInfo(
            name="manchester_owl",
            description=(
                "OWL 2 Manchester Syntax's own internal syntax tree, as RDF "
                "(manch:) - frames/clauses/class- and property-expressions/"
                "data-ranges, one level upstream of the compiled OWL RDF mapping."
            ),
            type="syntax-tree-graph",
        ),
        lambda: _load("manchester_owl"),
    ),
    "manchester_shacl": (
        OntologyInfo(
            name="manchester_shacl",
            description="SHACL shapes validating a manch: syntax tree's own structural well-formedness.",
            type="shacl",
        ),
        lambda: _load("manchester_shacl"),
    ),
    "skos_owl": (
        OntologyInfo(
            name="skos_owl",
            description=(
                "The W3C's own SKOS vocabulary (skos.rdf from the SKOS "
                "Reference, W3C Recommendation 2009), over the real skos: "
                "namespace."
            ),
            type="owl",
        ),
        lambda: _load("skos_owl"),
    ),
    "skos_shacl": (
        OntologyInfo(
            name="skos_shacl",
            description=(
                "SHACL shapes for SKOS: the Reference's numbered conditions as "
                "validation shapes, plus form shapes carrying shui:editor/"
                "shui:viewer widgets chosen by each property's datatype."
            ),
            type="shacl",
        ),
        lambda: _load("skos_shacl"),
    ),
    "sqe_owl": (
        OntologyInfo(
            name="sqe_owl",
            description=(
                "A SPARQL SELECT/ASK/CONSTRUCT query's own raw parse tree, "
                "pre-translateQuery, as a flat, human-readable RDF tree "
                "(sqe:) meant for hand/UI editing. v1 scope reduction: no aggregates/"
                "subqueries/VALUES/Update yet (property paths ARE covered)."
            ),
            type="syntax-tree-graph",
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
                "SRL's own rule-set syntax tree, as RDF (srl:) - "
                "a Datalog-style rules language, general-purpose and SHACL-independent."
            ),
            type="syntax-tree-graph",
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
                "(spexpr:), shared by sqe: and srl: - the one slice "
                "they both need identically (their own expression "
                "encoding, reused unchanged, not reimplemented per-vocabulary)."
            ),
            type="syntax-tree-graph",
        ),
        lambda: _load("spexpr_owl"),
    ),
    "spexpr_shacl": (
        OntologyInfo(
            name="spexpr_shacl",
            description=(
                "SHACL shapes validating an spexpr: expression/variable/path "
                "value's own well-formedness - imported by sqe:/srl: "
                "alike (each via owl:imports), not defined separately by any "
                "one of them."
            ),
            type="shacl",
        ),
        lambda: _load("spexpr_shacl"),
    ),
    "shacl_shacl": (
        OntologyInfo(
            name="shacl_shacl",
            description=(
                "The SHACL 1.2 meta-shapes themselves (starlayer.shacl's own "
                "shapes-about-shapes, validating a shapes graph's own "
                "well-formedness) - the stored graph meta_validate() reads, "
                "generated from build_meta_shapes_graph(); there's still no "
                "shacl_owl counterpart, since this entry has no ontology "
                "of its own to pair with."
            ),
            type="shacl",
        ),
        lambda: _load("shacl_shacl"),
    ),
    "shacl_vocabulary": (
        OntologyInfo(
            name="shacl_vocabulary",
            description=(
                "The SHACL 1.2 vocabulary, the W3C Data Shapes WG's shacl.ttl: every sh: class and property with its "
                "rdfs:domain, rdfs:range and rdfs:subClassOf. Reasoning over it (RDFS entailment) tells what type an "
                "entity of a shapes graph has without being told, e.g. a value of sh:group is a sh:PropertyGroup. "
                "Adds stsh:ShapesGraphShape, one property shape per kind of entity a shapes graph defines, on the "
                "inverse of rdfs:isDefinedBy. Not a set of constraints: do not load it for validation."
            ),
            type="owl",
        ),
        lambda: _load("shacl_vocabulary"),
    ),
    "shacl_shacl_ui": (
        OntologyInfo(
            name="shacl_shacl_ui",
            description=(
                "Presentation for shacl_shacl, to build a form for editing a shapes graph: sh:PropertyGroup "
                "sections, sh:group and sh:order on each SHACL predicate, and form flags. It contains no widget: "
                "widget choice is in shacl_shacl_ui_scores. Adds no constraints, so loading it with shacl_shacl "
                "never changes what validates."
            ),
            type="shacl",
        ),
        lambda: _load("shacl_shacl_ui"),
    ),
    "shacl_ui_baseline": (
        OntologyInfo(
            name="shacl_ui_baseline",
            description=(
                "The generic SHACL UI scoring catalog, in three tiers: a default that matches everything "
                "(score 1), defaults by datatype (2), and defaults by a constraint that lists the answers "
                "(sh:in, sh:class, sh:nodeKind; 3). Each condition is written on its own score, with no "
                "per-widget matchers, so a layer on top can add scores freely. One catalog serves both roles. "
                "Pass it as scoring_graph= to select_widgets; nothing uses it by default."
            ),
            type="scoring-catalog",
        ),
        lambda: _load("shacl_ui_baseline"),
    ),
    "shacl_shacl_ui_scores": (
        OntologyInfo(
            name="shacl_shacl_ui_scores",
            description=(
                "The scoring layer for editing SHACL, built on shacl_ui_baseline: widget scores at 40 that pick "
                "the editor for each SHACL predicate (a number field for sh:minCount, an enum select for "
                "sh:nodeKind, ...). An application layer that ships with starlayer; pass it with the generic "
                "catalog as scoring_graph=. Editors only."
            ),
            type="scoring-catalog",
        ),
        lambda: _load("shacl_shacl_ui_scores"),
    ),
    "shacl_shacl_rules": (
        OntologyInfo(
            name="shacl_shacl_rules",
            description=(
                "SHACL rules for a shapes graph read as data: which nodes are shapes (a target, a constraint parameter, "
                "the value of a shape-valued parameter, a member of an sh:and/sh:or/sh:xone list) and which kind (node "
                "shape or property shape, by sh:path), per SHACL 1.2 Core 3.1-3.3. Run with "
                "starlayer.shacl.shape_types.infer_types(). Applied to a shapes graph, never a data graph, so loading it "
                "never changes what validates."
            ),
            type="shacl",
        ),
        lambda: _load("shacl_shacl_rules"),
    ),
}


_file_graph_cache: dict[str, tuple[Any, dict[str, str]]] = {}


def _file_graph(filename: str) -> tuple[Any, dict[str, str]]:
    """The parsed contents of one bundled Turtle file (an ``StarLayerGraph``) and the ``_PREFIXES`` its IRIs use, read once and cached.

    Never mutated and never handed to a caller directly: ``_named_graph()`` copies the triples into a fresh ``StarLayerGraph``
    first, so no caller can see or corrupt another caller's view of the cached one.
    """
    cached = _file_graph_cache.get(filename)
    if cached is None:
        from starlayer.graph.oxgraph.core import StarLayerGraph

        graph = StarLayerGraph(prefixes={})
        graph.parse(str(_HERE / filename), format="turtle")
        cached = (graph, _used_prefixes(graph))
        _file_graph_cache[filename] = cached
    return cached


def _used_prefixes(graph: Any) -> dict[str, str]:
    """The ``_PREFIXES`` some IRI of ``graph`` (subject, predicate, object or literal datatype) lives in: ``get_ontology_graph(name)``
    binds only these, so a serialization declares what it uses."""
    import pyoxigraph as ox

    by_namespace = {ns: prefix for prefix, ns in _PREFIXES.items()}
    seen: set[str] = set()
    used: dict[str, str] = {}

    def visit(term: Any) -> None:
        if isinstance(term, ox.Triple):
            for part in (term.subject, term.predicate, term.object):
                visit(part)
            return
        if isinstance(term, ox.Literal):
            term = term.datatype
        if not isinstance(term, ox.NamedNode) or term.value in seen:
            return
        seen.add(term.value)
        cut = max(term.value.rfind("#"), term.value.rfind("/")) + 1
        prefix = by_namespace.get(term.value[:cut])
        if prefix is not None:
            used[prefix] = term.value[:cut]

    for s, p, o in graph:
        visit(s)
        visit(p)
        visit(o)
    return used


def _named_graph(context_iri: Any) -> Any:
    """A fresh, independent ``StarLayerGraph`` with the triples of the entry whose resource IRI is ``context_iri`` (the IRI is
    ``_GITHUB_BLOB_BASE`` plus the entry's filename), its identifier that IRI and its prefixes those its IRIs use."""
    import pyoxigraph as ox

    from starlayer.graph.oxgraph.core import StarLayerGraph

    iri = getattr(context_iri, "value", str(context_iri))
    filename = iri[len(_GITHUB_BLOB_BASE) :]
    source, used = _file_graph(filename)
    graph = StarLayerGraph(prefixes=dict(used), identifier=ox.NamedNode(iri))
    graph.extend(list(source))
    return graph


def _load(name: str) -> Any:
    """A fresh ``StarLayerGraph`` of the named entry, its identifier the entry's resource IRI: without it a caller who forgot to pass
    ``validate(..., shapes_graph_resource=...)`` gets no ``sh:usedShapesGraph`` / ``sh:conformsTo`` / ``dcterms:conformsTo`` at all
    (``validate()``'s own ``.identifier`` fallback recovers it from the graph). The import of ``StarLayerGraph`` is lazy (inside
    ``_named_graph``) so that importing ``starontology`` first cannot deadlock on the ``starlayer.graph`` package."""
    return _named_graph(_resource_iri(name))


def get_ontology_list() -> tuple[OntologyInfo, ...]:
    """Every registered ontology/shapes file's metadata, sorted by name."""
    return tuple(
        sorted(
            (info for info, _loader in _REGISTRY.values()),
            key=lambda info: info.name,
        )
    )


def get_ontology_graph(name: str) -> Any:
    """A fresh ``StarLayerGraph`` of the named ontology/shapes file (pyoxigraph terms; only the prefixes the graph's IRIs use; its
    identifier is the resource IRI).

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


# Every registered shapes entry that has a paired ontology/syntax-tree entry it
# validates - every "*_shacl" entry except "shacl_shacl" (no "shacl_owl"
# entry exists, since shacl_shacl has no ontology of its own to pair
# with). Just the name list - the actual prof:isProfileOf pairing itself
# lives in starlayer-profiles.ttl, not here, deliberately: this
# tuple is reused below by _real_shapes_graph_iri_to_name() for an
# unrelated reason (deciding which shapes files to scan), which has
# nothing to do with declaring a profile relationship and shouldn't share
# a name with the thing that does.
_SHACL_ENTRIES_WITH_ONTOLOGY_COUNTERPART = (
    "manchester_shacl",
    "skos_shacl",
    "sqe_shacl",
    "srl_shacl",
    "spexpr_shacl",
)

# Same "GitHub blob URL as a resource identity" convention
# starlayer.shacl's own starlayer-conformance.ttl already established
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
# value is also each entry's resource identity (see _resource_iri()'s own
# callers, and the named graphs in starontology.trig), so changing it would
# silently break the identities already asserted in
# starlayer-profiles.ttl's own prof:isProfileOf triples. Standard
# Linked Data move: a resource's IRI need not be the same URL you fetch a
# representation from. The files are the source in this
# directory, so this URL is real once they are committed and pushed.
_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/starontology/"


def _resource_iri(name: str) -> Any:
    """The resource IRI as a pyoxigraph ``NamedNode``."""
    return ox.NamedNode(_GITHUB_BLOB_BASE + _FILENAME_BY_NAME[name])


def _raw_filename(name: str) -> str | None:
    if name == "starlayer_profiles":
        return _PROFILES_FILENAME
    return _FILENAME_BY_NAME.get(name)


def get_resource_iri(name: str) -> Any:
    """The stable resource IRI (a pyoxigraph ``NamedNode``, whatever is installed) ``get_conformance_profiles()`` uses to
    identify ``name``'s own registered file as a ``prof:isProfileOf``
    subject (a GitHub blob URL - see ``_GITHUB_BLOB_BASE``'s own
    neighboring comment for the convention). Returns ``None`` for an
    unregistered name.

    ``"shacl_shacl"`` gets a real IRI here too, despite having no ontology
    counterpart - it's the same one ``starlayer-profiles.ttl``
    already uses as the ``prof:hasArtifact`` of ``slp:Shacl``.

    Exists so a caller validating against one of this registry's own
    shapes graphs can give it the *same* identity `derive_conforms_to()`'s
    ``specification_graph=`` chain expects - `derive_conforms_to()`'s
    second rule only fires when the shapes-graph IRI the caller supplied
    to `validate(..., shapes_graph_resource=...)` is the *exact same* IRI
    the conformance-profiles graph lists as a `prof:hasArtifact` (or
    `prof:isProfileOf` subject), not merely some other identity for "the same" file:

    >>> shapes = starontology.get_ontology_graph("skos_shacl")
    >>> result = StarShaclSchema(shacl_graph=shapes).validate(
    ...     data_graph=my_data,
    ...     data_graph_iri="http://example.org/graphs/mydata",
    ...     shapes_graph_resource=starontology.get_resource_iri("skos_shacl"),
    ... )
    >>> derive_conforms_to(
    ...     result.report_graph,
    ...     specification_graph=starontology.get_conformance_profiles(),
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
    ``"starlayer_profiles"`` for the profiles document
    itself (:func:`get_conformance_profiles`'s own bundled default,
    not one of the registered ontology/shapes entries, so it has no
    :func:`get_resource_iri` equivalent). Returns ``None`` for any other
    unrecognized name.

    The URL points at the entry's own ``.ttl`` file in this package, which
    is also what :func:`get_ontology_graph` and
    :func:`get_conformance_profiles` read, so it is real once the file is
    committed and pushed.
    """
    filename = _raw_filename(name)
    if filename is None:
        return None
    return _GITHUB_RAW_BASE + filename


def get_conformance_profiles(url: str | None = None) -> Any:
    """StarLayer's profiles and its conformance declaration, as one real
    persisted document (``starlayer-profiles.ttl``) - not synthesized from this module's own
    registry on the fly.

    It has three layers: the public specifications and SHACL profiles
    (labels only); StarLayer's own profiles (``slp:Skos``, ``slp:Shacl``,
    ...), each ``prof:isProfileOf`` a public specification or profile and
    listing its ontology (``role:schema``) and shapes (``role:validation``)
    files with ``prof:hasResource``; and the declared conformance of
    ``starlayer.graph``/``starlayer.sparql``/``starlayer.shacl``
    (``dcterms:conformsTo``, ``conformance:doesNotConformTo``). A shapes
    graph is checked against by validating data, and that data then
    conforms to the StarLayer profile that lists the shapes graph - and,
    through that profile's ``prof:isProfileOf`` chain, to the public
    specification (see ``starlayer.shacl.derive_conforms_to()``).

    Loads the bundled copy by default. Pass ``url=`` to load a different
    local path or ``http(s)://`` location instead - ``StarLayerGraph.parse()``
    handles both - e.g. a community-hosted canonical copy, or a
    local override for testing, without needing a new ``starontology``
    release to pick up a change. An override is read as a plain Turtle
    document (not a dataset) - it's expected to carry just the
    ``prof:isProfileOf``/``prof:hasResource`` triples themselves.

    Returns the whole mapping document - every registered pair's own
    relationship, not just one. There is deliberately no per-entry filter
    function: a caller who wants just one pair's own triples can extract
    that slice themselves (e.g. via ``graph.triples((get_resource_iri(name),
    PROF.hasResource, None))``, or a full subgraph walk if the
    ``prof:hasResource``/``prof:ResourceDescriptor`` detail is wanted too) -
    the full graph works equally well as ``derive_conforms_to()``'s own
    ``specification_graph=`` argument either way, since its WHERE clause
    already filters by the exact shapes-graph IRI.

    A fresh graph on every call, matching this stack's "never share one
    mutable graph object across callers" convention (see
    ``starlayer.shacl.profiling.declared_conformance_profile()``).

    Returns an ``StarLayerGraph`` (pyoxigraph terms, only the prefixes its IRIs use), as ``get_ontology_graph()`` does.
    """
    if url is not None:
        from starlayer.graph.oxgraph.core import StarLayerGraph

        graph = StarLayerGraph(prefixes={})
        graph.parse(url, format="turtle")
        for prefix, namespace in _used_prefixes(graph).items():
            graph.bind(prefix, namespace)
        return graph
    return _named_graph(ox.NamedNode(_GITHUB_BLOB_BASE + _PROFILES_FILENAME))


# get_profile_graph() (a per-entry filter over get_conformance_profiles())
# was removed 2026-10-14 - a user only ever needs the full mapping graph;
# anyone wanting one entry's own slice can extract it themselves from
# get_conformance_profiles()'s result. See starlayer/shacl/CLAUDE.md's
# dated entry for the removal.


# Every registered shapes entry's own real sh:ShapesGraph node IRI (the one
# each shapes file's own owl:imports triples actually point at, e.g.
# sqe_shapes.ttl's sqe:ShapesGraph owl:imports spexpr:ShapesGraph) - a
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
        from starlayer.shacl_engine.terms import RDF, SH

        mapping: dict = {}
        for name in _SHACL_ENTRIES_WITH_ONTOLOGY_COUNTERPART:
            for s in get_ontology_graph(name).subjects(RDF.type, SH.ShapesGraph):
                mapping[s] = name
        _REAL_SHAPES_GRAPH_IRI_TO_NAME = mapping
    return _REAL_SHAPES_GRAPH_IRI_TO_NAME


def local_loader(iri: Any) -> Any:
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
    from starlayer.shacl_engine.terms import to_engine

    name = _real_shapes_graph_iri_to_name().get(to_engine(iri))
    if name is None:
        return None
    return get_ontology_graph(name)
