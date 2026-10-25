"""``sh:TripleRule`` as SHACL 1.2 Inference Rules section 11.2 defines it (GitHub issue #82).

pySHACL's ``TripleRule`` insists on a ``sh:subject``, ``sh:predicate`` and ``sh:object`` (``RuntimeError: No sh:subject``) and
writes whatever it computes. The spec says: "Where sh:subject, sh:predicate, or sh:object are absent, use the list consisting
of the current focus node" (the spec's own Examples 11 and 12 leave ``sh:subject`` out), and "Skip ill-formed triples, for
example when a blank node is used as predicate". This replaces ``__init__`` (missing terms default to ``sh:this``) and ``apply``
(an ill-formed triple, a literal as subject or a non-IRI as predicate, is skipped) on pySHACL's class. The expression
evaluator is looked up in pySHACL's module at call time, so the ``shnex:`` patch still takes effect.

Process-global and idempotent, like the other pySHACL patches.
"""

from __future__ import annotations

import itertools
from typing import Any

import rdflib
from rdflib import BNode, Literal, URIRef
from rdflib.namespace import Namespace

SH = Namespace("http://www.w3.org/ns/shacl#")
_SENTINEL = "_starlayer_shacl_triple_rule_patch"


def _well_formed(triple: tuple) -> bool:
    """A subject is an IRI, blank node or triple term; a predicate is an IRI."""
    subject, predicate, _object = triple
    return isinstance(predicate, URIRef) and not isinstance(subject, Literal) and (
        isinstance(subject, (URIRef, BNode)) or hasattr(subject, "subject")
    )


def install_triple_rule_patch() -> bool:
    """Replace ``TripleRule.__init__`` and ``TripleRule.apply``. True if installed or already installed."""
    try:
        import pyshacl.rules.triple as triple_module
        from pyshacl.errors import ReportableRuntimeError
        from pyshacl.rules.shacl_rule import SHACLRule
        from pyshacl.rules.triple import TRIPLE_RULE_ITERATE_LIMIT, TripleRule

        if getattr(TripleRule.__init__, _SENTINEL, False):
            return True

        def _term(self, predicate) -> Any:
            nodes = set(self.shape.sg.objects(self.node, predicate))
            if len(nodes) > 1:
                raise RuntimeError(f"Too many {predicate}")
            return next(iter(nodes)) if nodes else SH.this  # absent: the focus node

        def __init__(self, executor, shape, rule_node, **kwargs):
            SHACLRule.__init__(self, executor, shape, rule_node, **kwargs)
            self.s = _term(self, SH.subject)
            self.p = _term(self, SH.predicate)
            self.o = _term(self, SH.object)

        def apply(self, data_graph, focus_nodes=None, target_graph_identifier=None) -> int:
            focus_list = list(focus_nodes) if focus_nodes is not None else list(self.shape.focus_nodes(data_graph))
            if self.executor.focus_nodes is not None and len(self.executor.focus_nodes) > 0:
                focus_list = [f for f in focus_list if isinstance(f, rdflib.URIRef) and f in self.executor.focus_nodes]
                if not focus_list:
                    return 0
            applicable_nodes = self.filter_conditions(focus_list, data_graph)
            all_added = 0
            iterate_limit = int(TRIPLE_RULE_ITERATE_LIMIT)
            while True:
                if iterate_limit < 1:
                    raise ReportableRuntimeError(
                        f"sh:rule iteration exceeded iteration limit of {TRIPLE_RULE_ITERATE_LIMIT}."
                    )
                iterate_limit -= 1
                added = 0
                to_add = []
                evaluate = triple_module.nodes_from_node_expression  # looked up now: the shnex: patch replaces it
                for a in applicable_nodes:
                    s_set = evaluate(self.s, a, data_graph, self.shape.sg)
                    p_set = evaluate(self.p, a, data_graph, self.shape.sg)
                    o_set = evaluate(self.o, a, data_graph, self.shape.sg)
                    this_added = False
                    for candidate in itertools.product(s_set, p_set, o_set):
                        if not _well_formed(candidate):
                            continue
                        if not this_added and candidate not in data_graph:
                            this_added = True
                        to_add.append(candidate)
                    if this_added:
                        added += 1
                if added > 0:
                    if isinstance(data_graph, rdflib.Dataset):
                        if target_graph_identifier is not None:
                            target_graph = data_graph.get_context(target_graph_identifier)
                        else:
                            target_graph = data_graph.default_graph
                    else:
                        target_graph = data_graph
                    for triple in to_add:
                        target_graph.add(triple)
                    all_added += added
                    if self.iterate:
                        continue
                break
            return all_added

        setattr(__init__, _SENTINEL, True)
        setattr(apply, _SENTINEL, True)
        TripleRule.__init__ = __init__
        TripleRule.apply = apply
        return True
    except Exception:
        return False
