"""Human-readable report text and run diagnostics for an engine run.

``report_text`` reproduces the layout the old ``ValidationReport.report_text`` carries (the pySHACL listing, which the old
validator then extended with a provenance appendix): the same header, the same per-result block, results sorted by their
block text, then the ``Provenance:`` appendix. Natively written: nothing here imports pyshacl or the old validator.

Everything here works on engine (pyoxigraph) terms; a graph is any engine-term graph (``StarLayerGraph``, an overlay), and its
prefixes are those it binds (``namespaces()``), when it has any.

Known differences from the old text: the default result messages are the engine's own wording (``Needs at least 1 value for
ex:p``), not pySHACL's (``Less than 1 values on ex:a->ex:p``); a SPARQL-based component names itself ``ConstraintComponent``
in pySHACL and by its own IRI local name here.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

import pyoxigraph as ox

from starlayer.graph.namespaces import PROV
from starlayer.shacl.engine import terms as T
from starlayer.shacl.engine import xsd_values as xv
from starlayer.shacl.engine.executor import Result
from starlayer.shacl.engine.plan import Path
from starlayer.shacl.engine.terms import DCTERMS, RDF, SH

_MAX_DEPTH = 12


def _prefixes(graph: Any) -> dict[str, str]:
    try:
        return {prefix: ns for prefix, ns in graph.namespaces()}  # noqa: C416
    except (AttributeError, TypeError):
        return {}


class _View:
    """A graph read as ``primary`` (its triples) whose terms are abbreviated with the prefixes of ``primary``, then of
    ``fallback``: the first graph that binds a namespace for an IRI names it (a prefix name is only ever used for the
    namespace the graph that supplies it binds it to). Everything else is the primary graph's."""

    def __init__(self, primary: Any, fallback: Any) -> None:
        self.primary = primary
        self.fallback = fallback

    def __getattr__(self, name: str) -> Any:
        return getattr(self.primary, name)


def _n3(graph: Any, term: Any) -> str:
    """``term`` with the prefixes ``graph`` binds (for a ``_View``, then those of its fallback graph); an IRI none fits stays ``<iri>``."""
    from starlayer.graph import qnames

    out = T.n3(term)
    while graph is not None:
        view = graph if isinstance(graph, _View) else None
        own = view.primary if view is not None else graph
        try:
            text = qnames.n3(_prefixes(own), term)
        except Exception:  # noqa: BLE001  (a rendering is never worth failing for)
            text = T.n3(term)
        if not text.startswith("<") or isinstance(term, ox.Literal):
            return text
        out = text
        graph = view.fallback if view is not None else None
    return out


def _predicates(graph: Any, node: Any) -> list[Any]:
    return list(dict.fromkeys(p for _s, p, _o in graph.triples((node, None, None))))


def _items(graph: Any, head: Any) -> list[Any]:
    out: list[Any] = []
    seen: set = set()
    while head is not None and head != RDF.nil and head not in seen:
        seen.add(head)
        first = next(iter(graph.objects(head, RDF.first)), None)
        if first is None:
            break
        out.append(first)
        head = next(iter(graph.objects(head, RDF.rest)), None)
    return out


def _python_value(node: ox.Literal) -> str | None:
    """The text of the Python value of a numeric or boolean literal (what ``Literal.value`` held in the old text), else ``None``."""
    value = xv.parse(node)
    if value is None or value.kind not in (xv.NUMERIC, xv.BOOLEAN):
        return None
    if isinstance(value.value, bool):
        return repr(value.value)
    try:
        return f"{value.value}"
    except ValueError:  # an integer over CPython's 4300-digit str limit: the report shows the lexical form only
        return None


def stringify_node(graph: Any, node: Any, depth: int = 0) -> str:
    """A node as text, as Turtle writes it: prefixed names, literals (``"x"``, ``"x"@en``, ``1``, ``"2026-01-02"^^xsd:date``),
    blank nodes as ``[ p o ; ... ]``, lists as ``( a b )``, triple terms as ``<<( s p o )>>``."""
    if isinstance(node, ox.Triple):
        return "<<( {} {} {} )>>".format(  # str-ok: stringify_node returns text
            *(stringify_node(graph, t, depth + 1) for t in (node.subject, node.predicate, node.object))
        )
    if isinstance(node, ox.Literal):
        return _literal(graph, node)
    if isinstance(node, ox.BlankNode):
        return _blank(graph, node, depth + 1)
    if isinstance(node, ox.NamedNode):
        return _n3(graph, node)
    return f"{node}"  # str-ok: a plain value (a Python str or number), not a term


_BARE_DATATYPES = frozenset(T.XSD[n] for n in ("integer", "decimal", "double", "boolean"))


def _literal(graph: Any, node: ox.Literal) -> str:
    """A literal as Turtle writes it: ``"text"``, ``"text"@en``, a number or boolean bare (``1``, ``true``), any other datatype as ``"lexical"^^xsd:date``."""
    lex = node.value
    if node.language:
        return f'"{lex}"@{node.language}'  # str-ok: rendered text
    if node.datatype == T.XSD.string:
        return f'"{lex}"'  # str-ok: rendered text
    if node.datatype in _BARE_DATATYPES:
        return lex
    return f'"{lex}"^^{stringify_node(graph, node.datatype)}'  # str-ok: rendered text


def _blank(graph: Any, node: ox.BlankNode, depth: int) -> str:
    if depth >= _MAX_DEPTH:
        return "<http://recursion.too.deep>"
    predicates = _predicates(graph, node)
    if not predicates:
        return "[ ]"
    if RDF.first in predicates:
        return "( {} )".format(" ".join(stringify_node(graph, i, depth + 1) for i in _items(graph, node)))
    rendered: dict[str, str] = {}
    for p in predicates:
        objs = list(graph.objects(node, p))
        if not objs:
            continue
        texts = ["<self>" if o == node else stringify_node(graph, o, depth + 1) for o in objs]
        rendered[_n3(graph, p)] = ", ".join(sorted(texts)) if len(texts) > 1 else texts[0]
    return "[ {} ]".format(" ; ".join(f"{p} {o}" for p, o in sorted(rendered.items())))  # str-ok: rendered text


def _params(shapes: Any, r: Result, predicate: Any) -> list[Any]:
    return list(shapes.objects(r.shape, predicate))


def _list_items(shapes: Any, head: Any) -> list[Any]:
    try:
        return _items(shapes, head)
    except Exception:  # noqa: BLE001
        return []


def _component_name(component: Any) -> str:
    return T.iri_text(component).rsplit("#", 1)[-1].rsplit("/", 1)[-1]


_NODE_KINDS = {
    "IRI": "an IRI",
    "BlankNode": "a blank node",
    "Literal": "a literal",
    "BlankNodeOrIRI": "an IRI or a blank node",
    "IRIOrLiteral": "an IRI or a literal",
    "BlankNodeOrLiteral": "a blank node or a literal",
    "TripleTerm": "a triple term",
}
_RANGE_WORDS = {
    "MinExclusiveConstraintComponent": ("minExclusive", "greater than"),
    "MinInclusiveConstraintComponent": ("minInclusive", "at least"),
    "MaxExclusiveConstraintComponent": ("maxExclusive", "less than"),
    "MaxInclusiveConstraintComponent": ("maxInclusive", "at most"),
}
_PAIR_WORDS = {
    "DisjointConstraintComponent": (SH.disjoint, "should not also be a value of {q}"),
}
_SHAPE_LISTS = {
    "AndConstraintComponent": ("and", "all of"),
    "OrConstraintComponent": ("or", "at least one of"),
    "XoneConstraintComponent": ("xone", "exactly one of"),
}


_LINE_BREAKS = str.maketrans({"\n": "\\n", "\r": "\\r", "\f": "\\f", "\v": "\\v"})


def plain_term(graph: Any, node: Any) -> str:
    """A term as a UI reads it: prefixed IRIs, a literal as its quoted text (bare for numbers and booleans, with its
    language tag or prefixed datatype otherwise; a line break shown as ``\\n`` so a message stays on one line), a blank
    node as ``_:label``."""
    if isinstance(node, ox.Literal):
        lex = node.value.translate(_LINE_BREAKS)
        if node.language:
            return f'"{lex}"@{node.language}'
        if node.datatype == T.XSD.string:
            return f'"{lex}"'
        if isinstance(node.datatype, ox.NamedNode) and node.datatype.value.startswith(T.INVALID_LANG_PREFIX):  # lenient mode: a malformed tag
            return f'"{lex}"@{unquote(node.datatype.value[len(T.INVALID_LANG_PREFIX):], errors="surrogatepass")}'  # str-ok: text
        if node.datatype in (T.XSD.integer, T.XSD.decimal, T.XSD.double, T.XSD.boolean):
            return node.value
        return f'"{lex}"^^{_n3(graph, node.datatype)}'
    if isinstance(node, ox.BlankNode):
        return f"_:{node.value}"
    return stringify_node(graph, node)


class Words:
    """Terms of one validation worded for a sentence in a result message: a data term with the prefixes of the data graph,
    then of the shapes graph, a shapes term the other way round, and never a blank-node label (a list reads ``( a b )``,
    another blank node of the data ``a blank node``, one of the shapes ``[ p o ]``)."""

    def __init__(self, data: Any, shapes: Any, *, fallback: bool = True) -> None:
        """``fallback=False``: a term of one graph uses only that graph's prefixes (the report graph's own messages)."""
        self.data_graph = data if isinstance(data, _View) else _View(data, shapes if fallback else None)
        self.shapes_graph = shapes if isinstance(shapes, _View) else _View(shapes, data if fallback else None)

    def data(self, node: Any) -> str:
        """A data term (a value, a focus node, a member of a list)."""
        if isinstance(node, ox.BlankNode):
            return stringify_node(self.data_graph, node) if (node, RDF.first, None) in self.data_graph.primary else "a blank node"
        return plain_term(self.data_graph, node)

    def subject(self, node: Any) -> str:
        """``Value "x"`` / ``Value ex:a``; ``A blank node value`` for a blank node that is not a list."""
        text = self.data(node)
        return "A blank node value" if text == "a blank node" else f"Value {text}"

    def expectation(self, component: str, term: Any) -> str:
        """What one parameter value of sh:class, sh:datatype or sh:nodeKind asks of a value, as the tail of ``Value x should ...``;
        a list is a union (``one of``)."""
        shapes = self.shapes_graph
        is_list = isinstance(term, ox.BlankNode) and (term, RDF.first, None) in shapes.primary
        members = _list_items(shapes, term) if is_list else [term]
        if component == "NodeKindConstraintComponent":
            def kind(k: Any) -> str:
                phrase = _NODE_KINDS.get(T.iri_text(k).rsplit("#", 1)[-1]) if isinstance(k, ox.NamedNode) else None
                return phrase or self.shape(k)

            return "be " + " or ".join(dict.fromkeys(kind(k) for k in members))
        text = ", ".join(self.shape(m) for m in members)
        if component == "ClassConstraintComponent":
            return f"be an instance of {'one of ' if is_list else ''}{text}"  # str-ok: text
        return f"have {'one of the datatypes' if is_list else 'the datatype'} {text}"  # str-ok: text

    def shape(self, node: Any) -> str:
        """A shapes-graph term (a shape, a class, a parameter value)."""
        return stringify_node(self.shapes_graph, node) if isinstance(node, ox.BlankNode) else plain_term(self.shapes_graph, node)

    def path(self, node: Any) -> str:
        """A property path as SPARQL writes it (``ex:p``, ``^ex:p``, ``ex:p/ex:q``, ``ex:p|ex:q``, ``ex:p*``)."""
        from starlayer.shacl.engine.paths import parse_path

        try:
            return self._path(parse_path(self.shapes_graph.primary, node))
        except Exception:  # noqa: BLE001  (a rendering is never worth failing for)
            return self.shape(node)

    def _path(self, p: Path, outer: str = "") -> str:
        if p.kind == "pred":
            return plain_term(self.shapes_graph, p.iri)
        if p.kind in ("seq", "alt"):
            sep = "/" if p.kind == "seq" else "|"
            body = sep.join(self._path(a, p.kind) for a in p.args)
            return f"({body})" if outer == "unary" or (outer == "seq" and p.kind == "alt") or outer == p.kind else body
        mark = {"inverse": "^", "zero_or_more": "*", "one_or_more": "+", "zero_or_one": "?"}[p.kind]
        inner = self._path(p.args[0], "unary")
        return f"^{inner}" if p.kind == "inverse" else f"{inner}{mark}"  # str-ok: text

    def on(self, path: Any) -> str:
        """`` for ex:p`` for a path term, ``""`` for none."""
        return f" for {self.path(path)}" if path is not None else ""  # str-ok: text


def _count(n: Any, noun: str) -> str:
    """``1 value`` / ``2 values``: the singular only for exactly one."""
    text = (_python_value(n) if isinstance(n, ox.Literal) else None) or getattr(n, "value", f"{n}")  # str-ok: text
    return f"{text} {noun}" if text == "1" else f"{text} {noun}s"  # str-ok: text


def generic_message(r: Result, shapes: Any, data: Any) -> str | None:
    """The default result message for a constraint component of one parameter value, built from the result's structured
    fields (component, path, value) and the shape's parameter value, so it names the path, the offending value and the
    expected value or limit; ``None`` where the component's own message is kept. Conventions: ``shacl/CLAUDE.md``."""
    name = _component_name(r.component)
    words = Words(data, shapes, fallback=isinstance(data, _View))
    shapes, data = words.shapes_graph, words.data_graph
    sn, dn = words.shape, words.data
    path = r.path.node if r.path is not None and r.path.node is not None else None
    on_path = words.on(path)
    # a blank node's label means nothing to a reader (and differs between runs), so it is not printed
    if not r.has_value:
        subject = "Value"
    else:
        subject = "A blank node value" if dn(r.value) == "a blank node" else f"Value {dn(r.value)}"

    def one(predicate: Any) -> Any:
        vals = _params(shapes, r, predicate)
        return vals[0] if len(vals) == 1 else None

    if name == "MinCountConstraintComponent" and isinstance(n := one(SH.minCount), ox.Literal):
        return f"Needs at least {_count(n, 'value')}{on_path}"  # str-ok: text
    if name == "MaxCountConstraintComponent" and isinstance(n := one(SH.maxCount), ox.Literal):
        return f"Allows at most {_count(n, 'value')}{on_path}"  # str-ok: text
    if name in ("ClassConstraintComponent", "DatatypeConstraintComponent", "NodeKindConstraintComponent"):
        # several values are a conjunction and the result does not say which one failed: the component words that result
        vals = _params(shapes, r, {"ClassConstraintComponent": SH["class"], "DatatypeConstraintComponent": SH.datatype}.get(name, SH.nodeKind))
        return f"{subject} should {words.expectation(name, vals[0])}" if len(vals) == 1 else None  # str-ok: text
    if name in ("MinLengthConstraintComponent", "MaxLengthConstraintComponent"):
        low = name.startswith("Min")
        if (v := one(SH.minLength if low else SH.maxLength)) is not None:
            return f"{subject} should have {'at least' if low else 'at most'} {_count(v, 'character')}"  # str-ok: text
    if name in _RANGE_WORDS and (v := one(SH[_RANGE_WORDS[name][0]])) is not None:
        return f"{subject} should be {_RANGE_WORDS[name][1]} {sn(v)}"  # str-ok: text
    if name == "PatternConstraintComponent" and isinstance(v := one(SH.pattern), ox.Literal):
        flags = one(SH.flags)
        with_flags = f" (flags {flags.value})" if isinstance(flags, ox.Literal) and flags.value else ""
        return f"{subject} should match the pattern '{v.value}'{with_flags}"  # str-ok: text
    if name == "LanguageInConstraintComponent" and (heads := _params(shapes, r, SH.languageIn)):
        return f"{subject} should have a language tag in {', '.join(sn(i) for i in _list_items(shapes, heads[0]))}"  # str-ok: text
    if name == "SingleLineConstraintComponent":
        return f"{subject} should not contain a line break"  # str-ok: text
    if name in _PAIR_WORDS:
        pred, phrase = _PAIR_WORDS[name]
        if (v := one(pred)) is not None and r.has_value:
            return f"{subject} {phrase.format(q=words.path(v))}"  # str-ok: text
    if name == "SubsetOfConstraintComponent" and (v := one(SH.subsetOf)) is not None and r.has_value:
        return f"{subject}{on_path} is not reachable by {words.path(v)}"  # str-ok: text
    if name == "NotConstraintComponent" and (v := one(SH["not"])) is not None and r.has_value:
        return f"{subject} should not conform to the shape {sn(v)}"  # str-ok: text
    if name == "NodeConstraintComponent" and (v := one(SH.node)) is not None and r.has_value:
        return f"{subject} should conform to the shape {sn(v)}"  # str-ok: text
    if name in _SHAPE_LISTS and r.has_value:
        pred, phrase = _SHAPE_LISTS[name]
        heads = _params(shapes, r, SH[pred])
        if not heads:
            return None
        listed = lambda head: ", ".join(sn(i) for i in _list_items(shapes, head))  # noqa: E731
        body = listed(heads[0]) if len(heads) < 2 else " and ".join(f"({listed(h)})" for h in heads)  # str-ok: text
        return f"{subject} should conform to {phrase} the shapes {body}"  # str-ok: text
    if name == "InConstraintComponent" and (heads := _params(shapes, r, SH["in"])) and r.has_value:
        return f"{subject} should be one of {', '.join(sn(i) for i in _list_items(shapes, heads[0]))}"  # str-ok: text
    if name == "RootClassConstraintComponent" and (vals := _params(shapes, r, SH.rootClass)):
        roots = [i for c in vals for i in (_list_items(shapes, c) if isinstance(c, ox.BlankNode) else [c])]
        if len(roots) == 1:
            return f"{subject} should be {sn(roots[0])} or a subclass of it"  # str-ok: text
        return f"{subject} should be one of {', '.join(sn(c) for c in roots)} or a subclass of one of them"  # str-ok: text
    if name == "ExpressionConstraintComponent" and r.source_constraint is not None:
        return f"{subject} should satisfy the expression {_short(sn(r.source_constraint))}"  # str-ok: text
    if name == "NodeByExpressionConstraintComponent" and r.source_constraint is not None:
        return f"{subject} should conform to the shape {sn(r.source_constraint)}"  # str-ok: text
    if not r.messages and r.source_constraint is not None and name == "SPARQLConstraintComponent":
        return f"{subject if r.has_value and path is not None else dn(r.focus)}{on_path} does not satisfy the SPARQL constraint"  # str-ok: text
    if not r.messages and r.component != SH.SPARQLConstraintComponent and not r.component.value.startswith("http://www.w3.org/ns/shacl#"):
        return _custom_component_message(r, shapes, words, subject)
    return None


def _short(text: str, limit: int = 80) -> str:
    """``text`` unless it is long (an inline expression), then a pointer to the result's ``sh:sourceConstraint``."""
    return text if len(text) <= limit else "(see the source constraint)"


def _custom_component_message(r: Result, shapes: Any, words: Words, subject: str) -> str:
    """A SPARQL-based component's result with no ``sh:message`` anywhere: the component and the parameter values the shape gave it."""
    given = []
    for param in shapes.objects(r.component, SH.parameter):
        for p in shapes.objects(param, SH.path):
            given.extend(f"{words.shape(p)} {words.shape(v)}" for v in shapes.objects(r.shape, p))  # str-ok: text
    shown = f" ({', '.join(sorted(given))})" if given else ""
    return f"{subject} does not satisfy {words.shape(r.component)}{shown}"  # str-ok: text


def result_messages(r: Result, shapes: Any, data: Any) -> list:
    """The messages of a result (engine terms): the shape's own ``sh:message`` as is; otherwise the old (pySHACL) generic
    wording where it is known, else what the engine component wrote."""
    own = set(shapes.objects(r.shape, SH.message))
    messages = list(r.messages)
    if not r.messages_stated and not own.intersection(messages):
        try:
            generic = generic_message(r, shapes, data)
        except Exception:  # noqa: BLE001  (a message is never worth failing a validation for)
            generic = None
        if generic is not None:
            return [ox.Literal(T.unmask(generic))]
    return [_unmasked(m) for m in messages]


def _unmasked(m: Any) -> Any:
    """A message with the lenient-mode stand-in IRIs in its text mapped back to the original terms (``terms.unmask``)."""
    if isinstance(m, str):
        return T.unmask(m)
    if isinstance(m, ox.Literal) and T.INVALID_IRI_PREFIX in m.value:
        text = T.unmask(m.value)
        if m.language:
            return ox.Literal(text, language=m.language, direction=m.direction)
        return ox.Literal(text, datatype=m.datatype)
    return m


class MessageMemo:
    """The messages of one run, worded once for each distinct result shape instead of once for each result.

    A result's messages are a function of its shape, component, path node, value (when it has one), source constraint, own messages and, for
    a SPARQL constraint only, its focus node: the shapes graph and the data graph do not change while a report is built. Every result of a
    shape that fails the same way on the same value therefore has the same messages, so they are worded once (the shapes graph is read and
    the sentence built once). Use one memo for one pair of graphs: a call with another pair is answered without the memo."""

    __slots__ = ("_messages", "_fixed", "_graphs")

    def __init__(self) -> None:
        self._messages: dict = {}
        self._fixed: dict = {}  # shapes-graph term -> its text in a result block
        self._graphs: tuple | None = None

    def _same_graphs(self, shapes: Any, data: Any) -> bool:
        if self._graphs is None:
            self._graphs = (shapes, data)
        return self._graphs[0] is shapes and self._graphs[1] is data

    def __call__(self, r: Result, shapes: Any, data: Any) -> list:
        """``result_messages(r, shapes, data)``, from the memo when a result like this one was worded."""
        if not self._same_graphs(shapes, data):
            return result_messages(r, shapes, data)
        key = (
            r.shape, r.component, r.path.node if r.path is not None else None, r.has_value, r.value if r.has_value else None,
            r.source_constraint, r.messages, r.messages_stated, r.focus if r.component == SH.SPARQLConstraintComponent else None,
        )
        try:
            found = self._messages.get(key)
        except TypeError:  # (an unhashable own message: not memoised)
            return result_messages(r, shapes, data)
        if found is None:
            found = self._messages[key] = result_messages(r, shapes, data)
        return list(found)

    def shape_text(self, shapes: Any, term: Any) -> str:
        """``stringify_node(shapes, term)`` for a term of the shapes graph, written once."""
        found = self._fixed.get(term)
        if found is None:
            found = self._fixed[term] = stringify_node(shapes, term)
        return found


def _message_text(m: Any) -> str:
    return T.text(m) if isinstance(m, (ox.NamedNode, ox.BlankNode, ox.Literal, ox.Triple)) else f"{m}"  # str-ok: a plain str


def _result_block(r: Result, shapes: Any, data: Any, memo: MessageMemo | None = None) -> str:
    """One result block; ``shapes`` and ``data`` are the ``_View`` of each graph (a nested ``sh:detail`` block gets the same). ``memo``: the
    messages and the lines that are fixed per shape are worded once for a run."""
    words = memo.shape_text if memo is not None else stringify_node
    messages = memo if memo is not None else result_messages
    kind = "Constraint Violation" if r.severity == SH.Violation else "Validation Result"
    component_text, severity_text, shape_text = words(shapes, r.component), words(shapes, r.severity), words(shapes, r.shape)
    text = f"{kind} in {component_text}:\n\tSeverity: {severity_text}\n\tSource Shape: {shape_text}\n\tFocus Node: {stringify_node(data, r.focus)}\n"
    if r.has_value:
        text += f"\tValue Node: {stringify_node(data, r.value)}\n"
    path: Path | None = r.path
    if path is not None and path.node is not None:
        path_text = words(shapes, path.node)
        text += f"\tResult Path: {path_text}\n"
    if r.source_constraint is not None:
        constraint_text = words(shapes, r.source_constraint)
        text += f"\tSource Constraint: {constraint_text}\n"
    for m in sorted(messages(r, shapes, data), key=_message_text):
        text += f"\tMessage: {_message_text(m)}\n"  # str-ok: message text
    for detail in r.details:  # sh:detail: the nested result, indented under the result it explains
        nested = _result_block(detail, shapes, data, memo)
        text += "\tDetail:\n" + "".join(f"\t\t{line}\n" for line in nested.splitlines())
    return text


def _prefixed(term: Any, *graphs: Any) -> str:
    """``term`` with the prefixes of the first graph that binds one for it (the report graph itself binds only ``sh``)."""
    out = T.n3(term)
    for graph in graphs:
        if graph is not None:
            text = _n3(graph, term)
            if not text.startswith("<") or isinstance(term, ox.Literal):
                return text
            out = text
    return out


def provenance_text(report: Any, data_graph_iri: Any = None, *graphs: Any) -> str:
    """The ``Provenance:`` appendix: used data/shapes graph (from the activity that generated the report) and the ``sh:conformsToShapesGraph`` / ``dcterms:conformsTo`` triples on
    the data graph's identity. Empty when there is nothing to say."""
    node = next(iter(report.subjects(RDF.type, SH.ValidationReport)), None)
    if node is None:
        return ""
    lines: list[str] = []
    activities = sorted(report.subjects(PROV.generated, node), key=T.n3)
    for label, predicate in (("Used Data Graph", SH.usedDataGraph), ("Used Shapes Graph", SH.usedShapesGraph)):
        values = [o for a in activities for o in report.objects(a, predicate)]
        if values:
            lines.append(f"\t{label}: {', '.join(_prefixed(v, *graphs, report) for v in values)}")
    if data_graph_iri is not None:
        subject = data_graph_iri if isinstance(data_graph_iri, (ox.NamedNode, ox.Literal)) else ox.NamedNode(f"{data_graph_iri}")  # str-ok: an IRI given as a str
        for predicate in (SH.conformsToShapesGraph, DCTERMS.conformsTo):
            lines.extend(
                f"\t{_prefixed(subject, *graphs, report)} {_prefixed(predicate, *graphs, report)} {_prefixed(o, *graphs, report)} ."
                for o in report.objects(subject, predicate)
            )
    return "\n".join(["", "Provenance:", *lines]) if lines else ""


def report_text(
    results: list[Result], conforms: bool, shapes: Any, data: Any, report: Any = None, data_graph_iri: Any = None
) -> str:
    """The human-readable validation report text: header, sorted result blocks, then the ``Provenance:`` appendix.

    Result blocks are sorted by their text, so the output does not depend on result order.

    Args:
        report: the report graph; the appendix is built from it, and is omitted when this is ``None``.
        data_graph_iri: the data graph's IRI (or str); the ``conformsTo`` triples on it in ``report`` are listed in the appendix. Ignored without ``report``.
    """
    text = f"Validation Report\nConforms: {conforms}\n"
    if results:
        text += f"Results ({len(results)}):\n"
    # a term is abbreviated with the prefixes of the graph it belongs to, then of the other graph (text only: the report graph is built elsewhere)
    shapes_view, data_view = _View(shapes, data), _View(data, shapes)
    memo = MessageMemo()
    text += "".join(sorted(_result_block(r, shapes_view, data_view, memo) for r in results))
    if report is not None:
        text += provenance_text(report, data_graph_iri, data, shapes)
    return T.unmask(text)
