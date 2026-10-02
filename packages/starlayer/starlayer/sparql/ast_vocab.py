"""The RDF vocabulary for the *parse-tree* (AST) level SPARQL representation
— a prototype, sibling to ``vocab.py``'s ``salg:`` (algebra) vocabulary, one
level lower: it mirrors ``rdflib.plugins.sparql.parser.parseQuery``'s raw
output (before ``translateQuery`` runs) instead of the compiled algebra.

Same generic-mirror design as ``salg:`` (``node.name`` -> ``rdf:type``,
``key: value`` -> predicate, recursively), pointed at a different tree.
Confirmed empirically (see ``to_ast_rdf.py``'s module docstring) that the
raw parse tree is *already* almost entirely ``CompValue``-shaped, using real
SPARQL grammar production names (``OptionalGraphPattern``, ``Filter``,
``TriplesBlock``, ``ConditionalOrExpression``, ``PathAlternative``, ...) —
closer to spec terminology than ``salg:``'s compiled algebra names. This is
why this file exists as a *separate* namespace rather than trying to unify
with ``salg:``: some names collide (``Filter`` exists at both layers, with a
genuinely different shape — the algebra's ``Filter`` nests the pattern it
filters as ``salg:p``; the parse tree's ``Filter`` doesn't, the pattern is a
sibling in the enclosing group instead), so merging namespaces would be
actively ambiguous, not just redundant.

``PyStr``/``Variable`` are the one deliberate exception to "kept fully
self-contained" below: reused directly from ``vocab.py`` (``salg:PyStr``/
``salg:Variable``), not re-minted here. These two are pure encoding-
primitive tags — they mark "this Python value needs to survive RDF
round-tripping faithfully," not an AST or algebra *concept* whose meaning
differs by layer, unlike every other name in this file. Minting a separate
``sast:Variable`` was tried first and found to have a real cost, not just
redundancy: it made the *same* SPARQL variable decode to two unequal RDF
terms depending on which layer's encoder wrote it (``Literal`` equality
includes datatype), which breaks the one thing a shared variable identity
is for — matching "the same variable" across a layer boundary via ordinary
term equality, e.g. tracing which ``WHERE``-clause variable a ``salg:``-
encoded expression subtree references. Everything else here (grammar
production names, ``sast:Query``/``sast:prologue``) stays genuinely
separate from ``salg:``, since those *do* differ in meaning by layer — see
the rest of this docstring.
"""

from __future__ import annotations

from rdflib import Namespace

from .vocab import (  # noqa: F401 - re-exported, see module docstring
    PY_STR_DATATYPE,
    VARIABLE_DATATYPE,
)

SAST = Namespace("https://github.com/hidden-graph/starsparql/ns/ast#")

# Root marker: the resource holding the parsed query tree is typed sast:Query
# in addition to its own grammar-production name (SelectQuery/AskQuery/
# ConstructQuery/DescribeQuery) — same convention as vocab.QUERY.
QUERY = SAST.Query

# The Prologue (BASE/PREFIX directives) at this layer is just an ordinary
# list of PrefixDecl/Base CompValues — parseQuery() hasn't turned it into a
# real Prologue object yet (translateQuery does that) — so, unlike
# to_rdf.py's algebra layer, this needs no bespoke Prologue encoding at all;
# it round-trips through the same generic list/CompValue machinery as
# everything else. This property just points at that list.
PROLOGUE = SAST.prologue
