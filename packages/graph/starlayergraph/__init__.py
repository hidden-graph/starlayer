"""StarLayer — RDF 1.2 / RDF-star graph library built on rdflib.

Re-exports the most commonly needed rdflib primitives so downstream code can
import everything from ``starlayergraph`` rather than mixing ``starlayergraph.*`` and
``rdflib.*`` imports.
"""

# Core rdflib term types
from rdflib import BNode, Literal, URIRef, Variable

# Namespace utilities
from rdflib import Namespace
from rdflib.namespace import RDF, RDFS, XSD

# Graph / dataset base classes (aliased so consumers can stay on starlayergraph.*)
from rdflib import Graph, Dataset
from rdflib.collection import Collection

# StarLayer-specific additions
from starlayergraph.model.triple import TripleTerm
from starlayergraph.model.dirlangstring import DirLangString
from starlayergraph.graph.starlayergraph_graph import StarLayerGraph
from starlayergraph.graph.starlayergraph_dataset import StarLayerDataset
from starlayergraph.parsers.errors import TurtleSyntaxError

# Registers starlayergraph's own custom SPARQL extension functions (TRIPLE()'s
# hash constructor, SUBJECT()/PREDICATE()/OBJECT() accessors, STRLANGDIR())
# with rdflib's global function registry, as an import-time side effect -
# every query going through starsparql's lowering compiles these down
# to Function algebra nodes that need a real, registered implementation to
# evaluate against. Imported explicitly (not relied on as a transitive side
# effect of some other import) so registration always happens regardless of
# what a caller imports first. See starlayergraph/query/custom_functions.py.
import starlayergraph.query.custom_functions as _custom_functions  # noqa: F401

# Compatibility shims for confirmed bugs in plain rdflib's own SPARQL
# arithmetic evaluation - applied eagerly so every consumer gets
# spec-correct results. See starlayergraph/query/operator_patches.py.
from starlayergraph.query.operator_patches import apply_all_operator_patches as _apply_all_operator_patches

# Compatibility shims for confirmed bugs in plain rdflib's own
# _AlgebraTranslator/translateAlgebra (algebra-tree-to-SPARQL-text
# serialization, not evaluation) - applied eagerly for the same reason.
# Not exercised by starlayergraph's own pipeline (it never calls
# translateAlgebra itself), but protects any other consumer that does. See
# starlayergraph/query/algebra_translator_patches.py and
# docs/rdflib-upstream-issues.md issues 3, 4, and 6.
from starlayergraph.query.algebra_translator_patches import (
    patch_algebra_translator_bugs as _patch_algebra_translator_bugs,
)

# Compatibility shim for a confirmed bug in plain rdflib's own SPARQL
# *evaluator* (evalExtend/BIND) - the most important of these patches,
# since the bug it fixes silently produces wrong query results with no
# error at all, rather than failing loudly. Applies to every query
# evaluated through rdflib, including starlayergraph's own (unlike the
# algebra-translator patches above, this one *is* exercised by starlayergraph's
# own pipeline). See starlayergraph/query/evaluate_patches.py and
# docs/rdflib-upstream-issues.md issue 5.
from starlayergraph.query.evaluate_patches import (
    patch_evalextend_forgotten_bind_vars as _patch_evalextend_forgotten_bind_vars,
)

# Same confirmed rdflib bug as the evalExtend patch immediately above,
# reached through FILTER instead of BIND (evalFilter's own
# `c.forget(ctx, _except=part._vars)`) - not covered by that patch, since
# it only touches evalExtend. See
# starlayergraph/query/evaluate_patches.py::patch_evalfilter_forgotten_vars.
from starlayergraph.query.evaluate_patches import (
    patch_evalfilter_forgotten_vars as _patch_evalfilter_forgotten_vars,
)

# Fix for a confirmed bug in plain rdflib's own evalModify (a different
# module, rdflib.plugins.sparql.update, from the evalExtend/evalFilter
# patches above): it writes DELETE/INSERT changes through
# ctx.dataset.default_context instead of ctx.graph whenever ctx.graph isn't
# exactly a bare Graph instance - silently failing to remove/insert a
# triple-term-valued triple against this library's own in-memory backend,
# even though the WHERE clause matches correctly. See
# starlayergraph/query/evaluate_patches.py::patch_evalmodify_default_graph_selection.
from starlayergraph.query.evaluate_patches import (
    patch_evalmodify_default_graph_selection as _patch_evalmodify_default_graph_selection,
)

# Fix for a confirmed bug in plain rdflib's own evalInsertData (same
# rdflib.plugins.sparql.update module as evalModify above, a distinct
# function): `g = ctx.graph; g += u.triples` assumes `+=` accepts a plain
# iterable of triples, which isn't true once ctx.graph is a genuine
# Dataset/ConjunctiveGraph (StarLayerDataset's default graph) - its own
# `__iadd__` override expects already-quad tuples, so a plain `INSERT DATA`
# with no triple terms involved raises `ValueError: not enough values to
# unpack`. Not symmetric with DELETE DATA (`evalDeleteData`'s `-=` doesn't
# have the same quad-only override and already works correctly) - see
# starlayergraph/query/evaluate_patches.py::patch_evalinsertdata_quad_unpacking.
from starlayergraph.query.evaluate_patches import (
    patch_evalinsertdata_quad_unpacking as _patch_evalinsertdata_quad_unpacking,
)

# Compatibility shim for a second, distinct confirmed bug in plain rdflib's
# own SPARQL evaluator (evalJoin/evalLazyJoin) - same root cause as the
# evalExtend patch above (a BIND's own expression-only variables aren't
# visible in _vars), but affects join *ordering* rather than evalExtend's
# own variable-forgetting, and isn't covered by that fix. See
# starlayergraph/query/evaluate_patches.py::patch_lazy_join_expr_dependency_order.
from starlayergraph.query.evaluate_patches import (
    patch_lazy_join_expr_dependency_order as _patch_lazy_join_expr_dependency_order,
)

# Fix for a starlayergraph-side (not rdflib) gap: CONSTRUCT has no equivalent of
# SELECT's own encoding-triple row filtering, so an unconstrained WHERE
# pattern (e.g. a bare `?s ?p ?o`) can leak internal rdf:subject/predicate/
# object encoding triples into CONSTRUCT output. See
# starlayergraph/query/evaluate_patches.py's own docstring for the full
# root-cause trace.
from starlayergraph.query.evaluate_patches import (
    patch_construct_skips_encoding_solutions as _patch_construct_skips_encoding_solutions,
)

# Fix for a starlayergraph-side (not rdflib) gap: the in-memory backend's
# tt:HASH encoding is opaque to stock rdflib's `=`/`!=`, which can only ever
# agree with `sameTerm` for two different encoded URIRefs - never true for
# two triple terms differing only in a component's lexical form, which
# SPARQL's own value-equality rules require. See
# starlayergraph/query/evaluate_patches.py::patch_relational_expression_tt_hash_equality.
from starlayergraph.query.evaluate_patches import (
    patch_relational_expression_tt_hash_equality as _patch_relational_expression_tt_hash_equality,
)

# Fix for a starlayergraph-side (not rdflib) gap: the in-memory backend's
# tt:HASH encoding is opaque to stock rdflib's ORDER BY comparator, which
# has no term-kind bucket for triple terms at all (rdflib predates RDF 1.2)
# and so sorts one as an ordinary IRI instead of in its own, RDF-1.2-
# mandated bucket after literals. See
# starlayergraph/query/evaluate_patches.py::patch_order_by_tt_hash_term_kind.
from starlayergraph.query.evaluate_patches import (
    patch_order_by_tt_hash_term_kind as _patch_order_by_tt_hash_term_kind,
)

# Fix for a starlayergraph-side (not rdflib) gap: an *unconstrained* BGP match
# (e.g. a bare `?s ?p ?o` inside a nested SELECT subquery, not just
# CONSTRUCT - see patch_construct_skips_encoding_solutions above, which only
# covers that one case) can incidentally match the in-memory backend's own
# internal tt:HASH encoding triples. See
# starlayergraph/query/evaluate_patches.py::patch_bgp_skips_encoding_triples.
from starlayergraph.query.evaluate_patches import (
    patch_bgp_skips_encoding_triples as _patch_bgp_skips_encoding_triples,
)

# Fix for a confirmed rdflib bug (a different phase from every patch above -
# parse-tree-to-algebra *translation*, not evaluation): a parenthesized,
# un-aliased computed GROUP BY key (`GROUP BY (?o+1)`, no `AS ?var`) - legal
# per SPARQL 1.1's own grammar - produces an algebra shape that crashes
# evalAggregateJoin outright, with zero RDF 1.2/starlayergraph involvement. See
# docs/rdflib-upstream-issues.md Issue 9 and
# starlayergraph/query/evaluate_patches.py::patch_group_by_unaliased_expression_key.
from starlayergraph.query.evaluate_patches import (
    patch_group_by_unaliased_expression_key as _patch_group_by_unaliased_expression_key,
)

# Fix for a confirmed rdflib bug (a different module/phase again - result
# *materialization*, rdflib.query.Result, not parsing/algebra/evaluation): a
# SELECT row with zero variable bindings (SELECT * over a pattern with no
# variables at all - "does this fact exist?") is a real, correct solution,
# but Result.__iter__ checks `if b:` before yielding it, and an empty dict is
# falsy - so it's silently dropped, indistinguishable from "no more rows".
# Result.bindings/len() are unaffected; only iterating the Result object
# (list(result), for row in result) loses it. See
# docs/rdflib-upstream-issues.md Issue 6 and
# starlayergraph/query/result_patches.py::patch_result_iter_empty_binding_row.
from starlayergraph.query.result_patches import (
    patch_result_iter_empty_binding_row as _patch_result_iter_empty_binding_row,
)

_apply_all_operator_patches()
_patch_algebra_translator_bugs()
_patch_evalextend_forgotten_bind_vars()
_patch_evalfilter_forgotten_vars()
_patch_evalmodify_default_graph_selection()
_patch_evalinsertdata_quad_unpacking()
_patch_lazy_join_expr_dependency_order()
_patch_construct_skips_encoding_solutions()
_patch_relational_expression_tt_hash_equality()
_patch_order_by_tt_hash_term_kind()
_patch_bgp_skips_encoding_triples()
_patch_group_by_unaliased_expression_key()
_patch_result_iter_empty_binding_row()

__all__ = [
    # rdflib primitives
    "BNode",
    "Literal",
    "URIRef",
    "Variable",
    # namespaces
    "Namespace",
    "RDF",
    "RDFS",
    "XSD",
    # graph types
    "Graph",
    "Dataset",
    "Collection",
    # starlayergraph additions
    "TripleTerm",
    "DirLangString",
    "StarLayerGraph",
    "StarLayerDataset",
    "TurtleSyntaxError",
]
