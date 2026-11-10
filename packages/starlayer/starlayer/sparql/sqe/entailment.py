"""Query-time RDF and RDFS entailment as a rewrite of the query's parse tree into plain SPARQL that Oxigraph evaluates.

The data is not copied or closed. Every triple pattern that the regime widens is replaced, in place, by a group of patterns
over the same graph (a ``UNION`` of alternatives, or a property path), so the engine sees an ordinary query. This is the
rewrite ``sparql/entailment_rdf.py`` and ``sparql/entailment_rdfs.py`` made on rdflib's algebra, moved to the owned parser's
tree (``parse_sparql.Node``) and out to text, like ``sqe/rewrite.py``; no rdflib algebra or evaluator is involved. Entry point:
:func:`rewrite_for_entailment`.

Rules (RDF Semantics numbering), for ``ENTAILMENT.RDFS``; ``ENTAILMENT.RDF`` is rdfD2 alone:

- ``?s rdf:type C``: rdfs9 (``C`` is a subclass of the asserted class), rdfs2 (domain of the predicate used), rdfs3 (range),
  each also through sub-properties of ``rdf:type`` / of the predicate (rdfs7), and rdfD2 (a term used as a predicate, or the
  subject of ``rdfs:subPropertyOf`` / ``rdfs:domain`` / ``rdfs:range``, or the object of ``rdfs:subPropertyOf``, is an
  ``rdf:Property``, at every superclass of ``rdf:Property``).
- ``?s rdfs:subClassOf ?o`` and ``?s rdfs:subPropertyOf ?o``: the transitive-reflexive closure (rdfs11, rdfs10; rdfs5, rdfs6).
  Reflexivity is unconditional (a zero-length path matches every term), a superset of the strict rules, as before.
- ``?s P ?o`` with an IRI ``P``: asserted with ``P`` or any sub-property of it (rdfs7).
- ``?s ?p ?o``: ``?p`` ranges over the asserted predicate and its super-properties, over ``rdf:type`` for the entailed types, and
  over the transitive (two steps or more) ``rdfs:subClassOf`` / ``rdfs:subPropertyOf`` triples.

Left out on purpose, as before (vocabulary-level facts, not about the data): rdfs4a/4b and rdfs8 (everything is an
``rdfs:Resource``), rdfs12/13, rdfD1, and the axiomatic triples (including ``rdf:_n`` container membership properties and
``rdfs:member``: no ``rdf:_1 rdfs:subPropertyOf rdfs:member`` is entailed). A property path in the query, a ``SERVICE`` body and a
triple term inside a pattern are not widened.

What changes in the query text besides the patterns: blank nodes in the WHERE clause become variables (a label cannot be
written in two groups, and in a pattern it is a variable anyway), ``SELECT *`` and ``DESCRIBE *`` become explicit lists of the
variables the original query had (the rewrite adds variables of its own), and ``CONSTRUCT WHERE`` gets its template written out.
What cannot be rewritten exactly raises :class:`EntailmentRewriteError`; nothing is ever sent unrewritten.

Rows are a bag, as in the rdflib version: a fact derivable in two ways (an asserted type and a domain) is one row per way.
"""

from __future__ import annotations

import functools
from typing import Any

import pyoxigraph as ox

from .._oxterms import NS, RDF
from ..parse_sparql import (
    Node,
    SparqlSyntaxError,
    _pattern_vars,
    _values_vars,
    ast_to_triples,
    parse_sparql,
)
from ._memtree import TreeIndex

RDFS = NS("http://www.w3.org/2000/01/rdf-schema#")
BNode, Literal, URIRef, Variable = ox.BlankNode, ox.Literal, ox.NamedNode, ox.Variable

__all__ = ["EntailmentRewriteError", "RDF_REGIME", "RDFS_REGIME", "rewrite_for_entailment"]

RDF_REGIME = "http://www.w3.org/ns/entailment/RDF"
RDFS_REGIME = "http://www.w3.org/ns/entailment/RDFS"

_TYPE = RDF.type
_SUBCLASS = RDFS.subClassOf
_SUBPROPERTY = RDFS.subPropertyOf
_SUBPROPERTY_PLUS = Node("MulPath", path=_SUBPROPERTY, mod="+")
# a subject of one of these is an rdf:Property (the domains of rdfs:subPropertyOf, rdfs:domain and rdfs:range are rdf:Property)
_PROPERTY_SUBJECT_PATH = Node("AlternativePath", args=[_SUBPROPERTY, RDFS.domain, RDFS.range])
_PREFIX = "_sl_ent"
_QUERY_KINDS = ("SelectQuery", "AskQuery", "ConstructQuery", "DescribeQuery")


class EntailmentRewriteError(NotImplementedError):
    """The query cannot be evaluated under the requested entailment regime by this rewrite."""


def regime_iri(regime: Any) -> str:
    """The IRI string of a regime given as ``ENTAILMENT.RDFS`` (rdflib), a ``pyoxigraph.NamedNode`` (or an rdflib ``URIRef``) or a plain string."""
    return str(getattr(regime, "value", regime))


def rewrite_for_entailment(text: str, regime: Any, *, prefixes: Any = None, base: str | None = None) -> str:
    """SPARQL ``text`` rewritten so that evaluating it on the plain data gives the answers under ``regime``.

    Args:
        text: A SPARQL query (SELECT, ASK, CONSTRUCT or DESCRIBE).
        regime: ``ENTAILMENT.RDF`` or ``ENTAILMENT.RDFS`` (an IRI, as a string, ``NamedNode`` or ``URIRef``).
        prefixes: Prefix declarations the text relies on (they are written into the result).
        base: The base IRI of the query.

    Returns:
        The rewritten query text; ``text`` itself when no pattern is widened.

    Raises:
        NotImplementedError: ``regime`` is neither RDF nor RDFS (OWL regimes need ``infer()``).
        EntailmentRewriteError: The query cannot be rewritten exactly.
        SparqlSyntaxError: ``text`` is not a query.
    """
    iri = regime_iri(regime)
    if iri not in (RDF_REGIME, RDFS_REGIME):
        raise NotImplementedError(
            f"query-time entailment supports ENTAILMENT.RDF and ENTAILMENT.RDFS, not {iri!r} "
            "(use infer() for a materialized closure of the OWL regimes)"
        )
    pfx = tuple(sorted((str(k), str(getattr(v, "value", v))) for k, v in (prefixes.items() if hasattr(prefixes, "items") else prefixes or ())))
    return _rewrite_cached(text, iri, pfx, base)


@functools.lru_cache(maxsize=256)
def _rewrite_cached(text: str, iri: str, prefixes: tuple, base: str | None) -> str:
    head = "".join(f"PREFIX {k}: <{v}>\n" for k, v in prefixes)
    tree = parse_sparql(head + text, base)
    if tree.kind not in _QUERY_KINDS:
        raise EntailmentRewriteError(f"query-time entailment needs a query, not a {tree.kind}")
    rw = _Rewriter(iri == RDFS_REGIME, tree)
    try:
        if rw.rewritten or not rw.widens(tree):
            return text
        rw.query(tree)
    except RecursionError as e:
        raise EntailmentRewriteError("the query is nested too deeply for the entailment rewrite") from e
    try:
        from .to_text import sqe_tree_to_text

        triples, root = ast_to_triples(tree)
        out = sqe_tree_to_text(TreeIndex(triples), root)
        parse_sparql(out, base)  # what is sent must itself be well-formed
    except (SparqlSyntaxError, ValueError, KeyError, NotImplementedError, RecursionError, TypeError, AttributeError) as e:
        raise EntailmentRewriteError(f"the rewritten query could not be written out as SPARQL: {e}") from e
    return out


def _mul(path: Any, mod: str) -> Node:
    return Node("MulPath", path=path, mod=mod)


def _tp(s: Any, p: Any, o: Any) -> Node:
    return Node("TriplePattern", s=s, p=p, o=o)


def _union(alts: list[list]) -> Node:
    return Node("Union", alts=alts)


def _is_node(t: Any) -> bool:
    """A term that can be the subject of a triple (not a literal or triple term)."""
    return isinstance(t, (Variable, URIRef))


class _Rewriter:
    def __init__(self, rdfs: bool, tree: Node) -> None:
        self.rdfs = rdfs
        self.count = 0
        self.bnodes: dict[BNode, Variable] = {}
        names: set[str] = set()
        _collect_names(tree, names)
        self.prefix = _PREFIX
        #: a query that already has variables of this rewrite's own naming is its output: left as it is (idempotent)
        self.rewritten = any(n.startswith(_PREFIX + "_") for n in names)

    # ---- fresh variables ------------------------------------------------------------------------------------------
    def fresh(self, n: int = 1) -> Any:
        out = []
        for _ in range(n):
            out.append(Variable(f"{self.prefix}_{self.count}"))
            self.count += 1
        return out[0] if n == 1 else out

    def star(self, s: Any, step: URIRef, o: Any) -> list:
        """``s step* o`` as elements of a group. A zero-length path on a constant end is not written as ``*``: Oxigraph matches
        it only when that constant occurs as a subject or object in the data (SPARQL: always), so the zero-length case is an
        explicit ``VALUES`` (or nothing, when both ends are the same constant) and the rest is ``step+`` (``!sameTerm`` keeps
        a term on a cycle from being counted twice)."""
        s_var, o_var = isinstance(s, Variable), isinstance(o, Variable)
        if s_var and o_var:
            return [_tp(s, _mul(step, "*"), o)]
        if not s_var and not o_var:
            return [] if s == o else [_tp(s, _mul(step, "+"), o)]
        var, const = (s, o) if s_var else (o, s)
        plus = [_tp(s, _mul(step, "+"), o), Node("Filter", expr=Node("UnaryNot", expr=Node("Builtin_sameTerm", arg1=var, arg2=const)))]
        return [_union([plus, [Node("Values", vars=[var], rows=[[const]])]])]

    # ---- is there anything to widen? ----------------------------------------------------------------------------------
    def widens(self, x: Any) -> bool:
        if isinstance(x, Node):
            if x.kind == "TriplePattern":
                return self.widened(x)
            if x.kind == "Service":
                return False
            return any(self.widens(v) for v in x.f.values())
        if isinstance(x, (list, tuple)):
            return any(self.widens(v) for v in x)
        return False

    def widened(self, tp: Node) -> bool:
        p, o = tp.f["p"], tp.f["o"]
        if not self.rdfs:
            return p == _TYPE and o == RDF.Property
        return isinstance(p, (URIRef, Variable))

    # ---- queries, groups, expressions -------------------------------------------------------------------------------
    def query(self, q: Node) -> None:
        where = q.f.get("where")
        if q.kind in ("SelectQuery", "SubSelect") and q.f["projection"] is None:
            names = _ordered_vars(where, q)
            if not names:
                raise EntailmentRewriteError("SELECT * with no variable in the pattern cannot be rewritten (the rewrite adds variables)")
            q.f["projection"] = [Node("ProjectVar", var=v) for v in names]
        if q.kind == "DescribeQuery" and q.f.get("targets") is None:
            names = _ordered_vars(where, q)
            if not names:
                raise EntailmentRewriteError("DESCRIBE * with no variable in the pattern cannot be rewritten")
            q.f["targets"] = names
        if q.kind == "ConstructQuery" and q.f.get("template") is None:
            q.f["template"] = list(where)  # CONSTRUCT WHERE: the template is the original pattern
        for k, v in q.f.items():
            if k not in ("where", "template"):
                self.expr(v)
        if isinstance(where, list):
            q.f["where"] = self.group(where)

    def expr(self, e: Any) -> None:
        if isinstance(e, Node):
            if e.kind in ("Builtin_EXISTS", "Builtin_NOTEXISTS"):
                e.f["graph"] = self.group(e.f["graph"])
                return
            for v in e.f.values():
                self.expr(v)
        elif isinstance(e, (list, tuple)):
            for v in e:
                self.expr(v)

    def group(self, where: list) -> list:
        out: list = []
        run: list[Node] = []

        def flush() -> None:
            if run:
                out.extend(self.triples(run))
                run.clear()

        for el in where:
            k = el.kind
            if k == "TriplePattern":
                run.append(el)
                continue
            flush()
            if k in ("Optional", "Minus"):
                out.append(Node(k, where=self.group(el.f["where"])))
            elif k == "Graph":
                out.append(Node(k, term=el.f["term"], where=self.group(el.f["where"])))
            elif k == "Union":
                out.append(Node(k, alts=[self.group(a) for a in el.f["alts"]]))
            elif k == "SubSelect":
                self.query(el)
                out.append(el)
            elif k == "Service":  # evaluated by the remote endpoint, which applies its own regime
                out.append(el)
            else:  # Filter, Bind, Values
                self.expr(list(el.f.values()))
                out.append(el)
        flush()
        return out

    # ---- triple patterns -------------------------------------------------------------------------------------------
    def term(self, t: Any) -> Any:
        """A blank node of a pattern is a variable; one name per label across the whole query."""
        if isinstance(t, BNode):
            if t not in self.bnodes:
                self.bnodes[t] = self.fresh()
            return self.bnodes[t]
        if isinstance(t, Node) and t.kind == "TripleTerm":
            return Node("TripleTerm", **{k: self.term(v) for k, v in t.f.items()})
        return t

    def triples(self, run: list[Node]) -> list:
        """One run of consecutive triple patterns: the single-alternative patterns first, then one ``UNION`` per pattern with
        several (the engine joins them in that order)."""
        simple: list = []
        unions: list = []
        for tp in run:
            s, p, o = self.term(tp.f["s"]), tp.f["p"], self.term(tp.f["o"])
            if isinstance(p, Node):  # a property path, left as written
                simple.append(_tp(s, p, o))
            elif not self.rdfs:
                if p == _TYPE and o == RDF.Property and _is_node(s):
                    unions.append(_union([[_tp(s, _TYPE, RDF.Property)], [_tp(self.fresh(), s, self.fresh())]]))
                else:
                    simple.append(_tp(s, p, o))
            elif p == _TYPE:
                unions.append(_union(self.type_alts(s, o)))
            elif p == _SUBCLASS:
                self.place(self.star(s, _SUBCLASS, o), simple, unions)
            elif p == _SUBPROPERTY:
                self.place(self.star(s, _SUBPROPERTY, o), simple, unions)
            elif isinstance(p, URIRef):
                # rdfs7: a fresh variable for the predicate actually used, joined to p through subPropertyOf* (the schema is
                # read by the engine, not enumerated here)
                q = self.fresh()
                simple.append(_tp(s, q, o))
                self.place(self.star(q, _SUBPROPERTY, p), simple, unions)
            else:
                unions.append(_union(self.variable_predicate_alts(s, p, o)))
        return simple + unions

    @staticmethod
    def place(elements: list, simple: list, unions: list) -> None:
        for el in elements:
            (simple if el.kind == "TriplePattern" else unions).append(el)

    def type_alts(self, s: Any, o: Any) -> list[list]:
        """rdfs9 | rdfs2 | rdfs3 | rdfD2 for ``s rdf:type o`` (rdfs7 composes with all of them, also for rdf:type itself)."""
        alts: list[list] = []
        q0, c0 = self.fresh(2)
        alts.append([_tp(s, q0, c0), *self.star(q0, _SUBPROPERTY, _TYPE), *self.star(c0, _SUBCLASS, o)])
        if _is_node(s):
            p1, o1, pp1, d1 = self.fresh(4)
            alts.append([_tp(s, p1, o1), *self.star(p1, _SUBPROPERTY, pp1), _tp(pp1, RDFS.domain, d1), *self.star(d1, _SUBCLASS, o)])
        s2, p2, pp2, d2 = self.fresh(4)
        alts.append([_tp(s2, p2, s), *self.star(p2, _SUBPROPERTY, pp2), _tp(pp2, RDFS.range, d2), *self.star(d2, _SUBCLASS, o)])
        if _is_node(s):
            # rdfD2: a term used as a predicate is an rdf:Property, and so is the subject of rdfs:subPropertyOf / rdfs:domain /
            # rdfs:range and the object of rdfs:subPropertyOf, at any class rdf:Property is a subclass of. The subclass
            # triple comes first so a type test rdf:Property can never satisfy fails before the scan.
            pf, po, ps, pr = self.fresh(4)
            alts.append([*self.star(RDF.Property, _SUBCLASS, o), _tp(pf, s, po)])
            alts.append([*self.star(RDF.Property, _SUBCLASS, o), _tp(s, _PROPERTY_SUBJECT_PATH, ps)])
            alts.append([*self.star(RDF.Property, _SUBCLASS, o), _tp(pr, _SUBPROPERTY, s)])
        return alts

    def variable_predicate_alts(self, s: Any, p: Variable, o: Any) -> list[list]:
        """``?p`` ranges over the entailed triples: the asserted one and the ones a strict super-property gives (rdfs7), the
        entailed types (``?p`` is ``rdf:type`` or a super-property of it), and the transitive subclass and subproperty triples."""
        q = self.fresh()
        alts: list[list] = [[_tp(s, p, o)], [_tp(s, q, o), _tp(q, _SUBPROPERTY_PLUS, p)]]
        if isinstance(o, (Literal, Node)):  # a literal or triple term is no class
            return alts
        alts.append([_union(self.type_alts(s, o)), *self.star(_TYPE, _SUBPROPERTY, p)])
        for predicate in (_SUBCLASS, _SUBPROPERTY):  # rdfs11 / rdfs5: two steps or more (one step is the asserted triple)
            alts.append([*self.star(predicate, _SUBPROPERTY, p), _tp(s, Node("SequencePath", args=[predicate, _mul(predicate, "+")]), o)])
        return alts


def _collect_names(x: Any, out: set[str]) -> None:
    if isinstance(x, Variable):
        out.add(x.value)
    elif isinstance(x, Node):
        for v in x.f.values():
            _collect_names(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _collect_names(v, out)


def _ordered_vars(where: list | None, q: Node) -> list[Variable]:
    """The variables in scope for ``SELECT *`` / ``DESCRIBE *``, in order of first appearance in the pattern."""
    scope = _pattern_vars(where) | _values_vars(q)
    seen: list[Variable] = []

    def walk(x: Any) -> None:
        if isinstance(x, Variable):
            if x in scope and x not in seen:
                seen.append(x)
        elif isinstance(x, Node):
            if x.kind in ("Filter", "Minus"):
                return
            for v in x.f.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)

    walk(where)
    walk(q.f.get("values"))
    return seen + sorted(scope - set(seen), key=lambda v: v.value)
