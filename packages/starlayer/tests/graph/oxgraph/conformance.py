"""Scenarios run on both the old ``StarLayerGraph`` / ``StarLayerDataset`` and the new ``OxGraph`` / ``OxDataset``.

Each scenario takes an ``Impl`` and returns plain, comparable data (terms normalised to N-Triples-like text, blank nodes
numbered by first appearance, row sets sorted). ``test_conformance.py`` runs every scenario on both and compares; the
scenarios in ``KNOWN`` differ on purpose and carry a verdict. ``python -m`` the module (see ``__main__``) prints a report.
"""

from __future__ import annotations

from typing import Any

import pyoxigraph as ox

EX = "http://example.org/"


class _Norm:
    """Terms to text; blank nodes numbered by first appearance within one scenario result."""

    def __init__(self) -> None:
        self.bn: dict[str, str] = {}

    def __call__(self, t: Any) -> Any:
        if t is None:
            return None
        if isinstance(t, (list, tuple)) and not isinstance(t, ox.Triple):
            return tuple(self(x) for x in t)
        if isinstance(t, ox.DefaultGraph):
            return "DEFAULT"
        if isinstance(t, ox.BlankNode):
            return self._bn(t.value)
        if isinstance(t, ox.Triple):
            return "<<( " + " ".join(str(self(x)) for x in (t.subject, t.predicate, t.object)) + " )>>"
        if isinstance(t, ox.NamedNode):
            return f"<{t.value}>"
        if isinstance(t, ox.Literal):
            q = '"' + t.value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
            if t.language:
                return f"{q}@{t.language}" + (f"--{str(t.direction).lower().split('.')[-1]}" if t.direction else "")
            if t.datatype.value != "http://www.w3.org/2001/XMLSchema#string":
                return f"{q}^^<{t.datatype.value}>"
            return q
        if t == "DEFAULT":
            return t
        # rdflib / StarLayer terms
        from rdflib import BNode, Literal, URIRef
        from starlayer.graph.model.dirlangstring import DirLangString
        from starlayer.graph.model.triple import TripleTerm

        if isinstance(t, TripleTerm):
            return "<<( " + " ".join(str(self(x)) for x in (t.subject, t.predicate, t.object)) + " )>>"
        if isinstance(t, BNode):
            return self._bn(str(t))
        if isinstance(t, URIRef):
            return f"<{t}>"
        if isinstance(t, DirLangString):
            return f'"{t}"@{t.language}--{t.direction}'
        if isinstance(t, Literal):
            s = '"' + str(t).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'
            if t.language:
                return f"{s}@{t.language}"
            if t.datatype and str(t.datatype) != "http://www.w3.org/2001/XMLSchema#string":
                return f"{s}^^<{t.datatype}>"
            return s
        return repr(t)

    def _bn(self, label: str) -> str:
        return self.bn.setdefault(label, f"_:b{len(self.bn)}")


def norm_set(rows: Any, n: _Norm | None = None) -> list:
    n = n or _Norm()
    return sorted(repr(n(r)) for r in rows)


class Impl:
    name = ""

    def graph(self): ...
    def dataset(self): ...
    def dataset_no_union(self):
        return self.dataset()

    def iri(self, s: str): ...
    def lit(self, v: str, lang: str | None = None, dt: str | None = None): ...
    def triples(self, g, pat=(None, None, None)): ...
    def quads(self, ds): ...
    def rows(self, res): ...
    def graph_names(self, ds): ...
    def get_graph(self, ds, name): ...
    def remove_graph(self, ds, name): ...
    def prefixes(self, g): ...


class OldImpl(Impl):
    name = "old"

    def graph(self):
        from starlayer.graph.graph.starlayer_graph import StarLayerGraph

        return StarLayerGraph()

    def dataset(self):
        from starlayer.graph.graph.starlayer_dataset import StarLayerDataset

        return StarLayerDataset()

    def iri(self, s):
        from rdflib import URIRef

        return URIRef(s)

    def lit(self, v, lang=None, dt=None):
        from rdflib import Literal, URIRef

        return Literal(v, lang=lang, datatype=URIRef(dt) if dt else None)

    def triples(self, g, pat=(None, None, None)):
        return list(g.triples(pat))

    def quads(self, ds):
        out = []
        for c in ds.contexts():
            ident = c.identifier
            name = "DEFAULT" if str(ident) == "urn:x-rdflib:default" else ident
            out += [(*t, name) for t in c.triples((None, None, None))]
        return out

    def rows(self, res):
        if res.type == "SELECT":
            vs = [str(v) for v in res.vars]
            return {"vars": vs, "rows": [tuple(row[i] for i in range(len(vs))) for row in res]}
        if res.type == "ASK":
            return {"ask": bool(res.askAnswer)}
        return {"triples": list(res.graph.triples((None, None, None)))}

    def graph_names(self, ds):
        return [c.identifier for c in ds.contexts() if str(c.identifier) != "urn:x-rdflib:default"]

    def get_graph(self, ds, name):
        return ds.get_context(name)

    def remove_graph(self, ds, name):
        ds.remove_graph(ds.get_context(name))

    def prefixes(self, g):
        return {p: str(n) for p, n in g.namespaces()}


class NewImpl(Impl):
    name = "new"

    def graph(self):
        from starlayer.graph.oxgraph import OxGraph

        return OxGraph()

    def dataset(self):
        from starlayer.graph.oxgraph import OxDataset

        return OxDataset()

    def dataset_no_union(self):
        from starlayer.graph.oxgraph import OxDataset

        return OxDataset(default_union=False)

    def iri(self, s):
        return ox.NamedNode(s)

    def lit(self, v, lang=None, dt=None):
        return ox.Literal(v, language=lang) if lang else ox.Literal(v, datatype=ox.NamedNode(dt)) if dt else ox.Literal(v)

    def triples(self, g, pat=(None, None, None)):
        return list(g.triples(pat))

    def quads(self, ds):
        return [(q.subject, q.predicate, q.object, q.graph_name) for q in ds.quads()]

    def rows(self, res):
        if res.type == "SELECT":
            vs = [v.value for v in res.vars]
            return {"vars": vs, "rows": [tuple(row) for row in res]}
        if res.type == "ASK":
            return {"ask": bool(res.askAnswer)}
        return {"triples": list(res.graph.triples((None, None, None)))}

    def graph_names(self, ds):
        return ds.graph_names()

    def get_graph(self, ds, name):
        return ds.graph(name)

    def remove_graph(self, ds, name):
        ds.remove_graph(name)

    def prefixes(self, g):
        return dict(g.prefixes)


def _data(I: Impl, *rows) -> Any:  # noqa: E741
    g = I.graph()
    for r in rows:
        g.add(r)
    return g


# ---- scenarios --------------------------------------------------------------------------------------------------------
SCENARIOS: dict[str, Any] = {}


def scenario(f):
    SCENARIOS[f.__name__] = f
    return f


TTL = """@prefix ex: <http://example.org/> .
ex:a ex:p ex:b , ex:c , "x" , "y"@en , 42 ; ex:q [ ex:r ex:d ] .
ex:b ex:p ex:c .
"""


@scenario
def add_remove_len_contains(I):  # noqa: E741
    a, b, c, p = (I.iri(EX + x) for x in "abcp")
    g = I.graph()
    for t in [(a, p, b), (a, p, c), (a, p, b), (b, p, c)]:
        g.add(t)
    out = {"len": len(g), "has": (a, p, b) in g, "hasnt": (c, p, a) in g}
    g.remove((a, p, b))
    out["after_remove"] = (len(g), (a, p, b) in g)
    g.remove((None, p, None))
    out["after_wild"] = len(g)
    return out


@scenario
def triples_patterns(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    a, p = I.iri(EX + "a"), I.iri(EX + "p")
    n = _Norm()
    return {
        "all": len(I.triples(g)),
        "s": len(I.triples(g, (a, None, None))),
        "p": len(I.triples(g, (None, p, None))),
        "o": len(I.triples(g, (None, None, I.iri(EX + "c")))),
        "sp": norm_set(I.triples(g, (a, p, None)), n),
        "spo": len(I.triples(g, (a, p, I.lit("x")))),
        "lit_subject_pattern": len(I.triples(g, (I.lit("x"), None, None))),
    }


@scenario
def literals_via_add(I):  # noqa: E741
    a, p = I.iri(EX + "a"), I.iri(EX + "p")
    g = I.graph()
    XSD = "http://www.w3.org/2001/XMLSchema#"
    for o in (I.lit("x", lang="EN-us"), I.lit("01", dt=XSD + "integer"), I.lit("1.0", dt=XSD + "decimal"),
              I.lit("1", dt=XSD + "boolean"), I.lit("x", dt=XSD + "string"), I.lit("1e0", dt=XSD + "double"),
              I.lit("+5", dt=XSD + "integer"), I.lit("abc", dt=XSD + "integer")):
        try:
            g.add((a, p, o))
        except Exception as e:  # noqa: BLE001
            return {"error_on_add": type(e).__name__}
    return norm_set(I.triples(g))


@scenario
def literals_via_turtle_parse(I):  # noqa: E741
    g = I.graph()
    g.parse(data='@prefix ex: <http://example.org/> . ex:a ex:p "x"@EN-us, 01, 1.0, "1"^^<http://www.w3.org/2001/XMLSchema#boolean>, '
                 '"+5"^^<http://www.w3.org/2001/XMLSchema#integer>, 1e0, "x"^^<http://www.w3.org/2001/XMLSchema#string>, "a\\tb" .',
            format="turtle")
    return norm_set(I.triples(g))


@scenario
def parse_formats_roundtrip(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    base = I.graph()
    base.parse(data=TTL, format="turtle")
    res = {"turtle": len(g)}
    for fmt in ("nt", "xml", "turtle", "json-ld", "n3"):
        text = g.serialize(format=fmt)
        if isinstance(text, bytes):
            text = text.decode()
        h = I.graph()
        h.parse(data=text, format=fmt)
        res[fmt] = (len(h), len(I.triples(h, (None, None, I.lit("x")))))
    return res


@scenario
def trig_nquads_roundtrip(I):  # noqa: E741
    ds = I.dataset()
    ds.parse(data="@prefix ex: <http://example.org/> . ex:a ex:p 1 . GRAPH ex:g { ex:b ex:p 2 . ex:c ex:p ex:d }", format="trig")
    res = {"trig": norm_set(I.quads(ds))}
    for fmt in ("trig", "nquads"):
        text = ds.serialize(format=fmt)
        text = text.decode() if isinstance(text, bytes) else text
        d2 = I.dataset()
        d2.parse(data=text, format=fmt)
        res[fmt] = norm_set(I.quads(d2))
    return res


@scenario
def blank_nodes_across_two_parses(I):  # noqa: E741
    g = I.graph()
    doc = '_:b <http://example.org/p> "1" .\n_:b <http://example.org/q> _:c .\n'
    g.parse(data=doc, format="nt")
    g.parse(data=doc, format="nt")
    t = Turtle = "@prefix ex: <http://example.org/> . [] ex:p 1 . ex:a ex:q [ ex:r 2 ] ."
    h = I.graph()
    h.parse(data=Turtle, format="turtle")
    h.parse(data=t, format="turtle")
    return {"nt_twice": len(g), "turtle_twice": len(h)}


@scenario
def query_select(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    n = _Norm()
    r = I.rows(g.query("PREFIX ex: <http://example.org/> SELECT ?s ?o WHERE { ?s ex:p ?o } ORDER BY ?s ?o"))
    star = I.rows(g.query("PREFIX ex: <http://example.org/> SELECT * WHERE { ?z ex:p ?a . ?a ex:p ?b }"))
    nn = _Norm()
    star = {"vars": sorted(star["vars"]), "rows": sorted(tuple(sorted(str(nn(t)) for t in r)) for r in star["rows"])}
    agg = I.rows(g.query("PREFIX ex: <http://example.org/> SELECT (COUNT(*) AS ?n) (SAMPLE(?s) AS ?x) WHERE { ?s ex:p ?o }"))
    opt = I.rows(g.query("PREFIX ex: <http://example.org/> SELECT ?s ?z WHERE { ?s ex:p ex:b OPTIONAL { ?s ex:nope ?z } }"))
    return {"vars": r["vars"], "rows": norm_set(r["rows"], n), "star_vars": star["vars"], "star_rows": star["rows"],
            "agg": norm_set(agg["rows"], _Norm())[0][:6], "opt": norm_set(opt["rows"], _Norm())}


@scenario
def select_star_column_order(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    r = I.rows(g.query("PREFIX ex: <http://example.org/> SELECT * WHERE { ?z ex:p ?a . ?a ex:p ?b }"))
    return r["vars"]


@scenario
def dataset_default_graph_in_query(I):  # noqa: E741
    ds = I.dataset()
    return _dataset_default_graph(I, ds)


@scenario
def dataset_default_graph_without_union(I):  # noqa: E741
    return _dataset_default_graph(I, I.dataset_no_union())


def _dataset_default_graph(I, ds):  # noqa: E741
    ds.parse(data="@prefix ex: <http://example.org/> . ex:a ex:p 1 . GRAPH ex:g { ex:b ex:p 2 }", format="trig")
    q = "SELECT ?s WHERE { ?s ?p ?o }"
    return {"plain": norm_set(I.rows(ds.query(q))["rows"]),
            "graph_clause": norm_set(I.rows(ds.query("SELECT ?s ?g WHERE { GRAPH ?g { ?s ?p ?o } }"))["rows"])}


@scenario
def blank_nodes_in_construct_and_describe(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    r = I.rows(g.query("PREFIX ex: <http://example.org/> CONSTRUCT { ?s ex:copy [ ex:of ?o ] } WHERE { ?s ex:p ?o }"))
    return len(r["triples"])


@scenario
def query_ask_construct_describe(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    pre = "PREFIX ex: <http://example.org/> "
    out = {
        "ask_t": I.rows(g.query(pre + "ASK { ex:a ex:p ex:b }")),
        "ask_f": I.rows(g.query(pre + "ASK { ex:a ex:p ex:zzz }")),
        "construct": norm_set(I.rows(g.query(pre + "CONSTRUCT { ?o ex:inv ?s } WHERE { ?s ex:p ?o }"))["triples"]),
    }
    try:
        d = I.rows(g.query(pre + "DESCRIBE ex:b"))
        out["describe"] = norm_set(d["triples"])
    except Exception as e:  # noqa: BLE001
        out["describe"] = f"error {type(e).__name__}"
    return out


@scenario
def query_init_bindings_and_ns(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    s = I.iri(EX + "b")
    r = I.rows(g.query("SELECT ?o WHERE { ?s <http://example.org/p> ?o }", initBindings={"s": s}))
    r2 = I.rows(g.query("SELECT ?o WHERE { ex:b ex:p ?o }", initNs={"ex": EX}))
    return {"bound": norm_set(r["rows"]), "ns": norm_set(r2["rows"])}


@scenario
def numeric_formatting(I):  # noqa: E741
    g = I.graph()
    r = I.rows(g.query("SELECT ?a ?b ?c ?d ?e ?f WHERE { BIND(1+2.5 AS ?a) BIND(1/3 AS ?b) BIND(xsd:decimal(3) AS ?c) "
                       "BIND(1e0*2 AS ?d) BIND(STR(0.1e0) AS ?e) BIND(xsd:double(100000000000000000000) AS ?f) }"
                       .replace("xsd:", "<http://www.w3.org/2001/XMLSchema#") .replace("decimal(", "decimal>(").replace("double(", "double>(")))
    return norm_set(r["rows"])


@scenario
def same_term_numeric_constants(I):  # noqa: E741
    g = I.graph()
    r = I.rows(g.query('ASK { FILTER(sameTerm("1"^^<http://www.w3.org/2001/XMLSchema#integer>, "01"^^<http://www.w3.org/2001/XMLSchema#integer>)) }'))
    r2 = I.rows(g.query("ASK { FILTER(sameTerm(1, 01)) }"))
    return {"quoted": r, "bare": r2}


@scenario
def sparql12_triple_terms(I):  # noqa: E741
    g = I.graph()
    g.parse(data="@prefix ex: <http://example.org/> . ex:r a ex:Rel ; <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ex:a ex:p ex:b )>> .", format="turtle12" if I.name == "old" else "turtle")
    r = I.rows(g.query("VERSION '1.2' SELECT ?t WHERE { ?r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> ?t . FILTER isTRIPLE(?t) }"))
    r2 = I.rows(g.query("SELECT ?s WHERE { ?r <http://www.w3.org/1999/02/22-rdf-syntax-ns#reifies> <<( ?s <http://example.org/p> ?o )>> }"))
    return {"t": norm_set(r["rows"]), "s": norm_set(r2["rows"])}


@scenario
def update_operations(I):  # noqa: E741
    ds = I.dataset()
    log = {}
    steps = [
        "INSERT DATA { <http://example.org/a> <http://example.org/p> 1 . GRAPH <http://example.org/g1> { <http://example.org/b> <http://example.org/p> 2 } }",
        "INSERT { <http://example.org/new> <http://example.org/p> ?o } WHERE { <http://example.org/a> <http://example.org/p> ?o }",
        "DELETE WHERE { <http://example.org/new> ?p ?o }",
        "CREATE GRAPH <http://example.org/g2>",
        "COPY <http://example.org/g1> TO <http://example.org/g3>",
        "ADD <http://example.org/g1> TO <http://example.org/g2>",
        "MOVE <http://example.org/g3> TO <http://example.org/g4>",
        "CLEAR GRAPH <http://example.org/g1>",
        "DROP GRAPH <http://example.org/g2>",
        "CLEAR DEFAULT",
    ]
    for i, st in enumerate(steps):
        try:
            ds.update(st)
            log[i] = norm_set(I.quads(ds))
        except Exception as e:  # noqa: BLE001
            log[i] = f"error {type(e).__name__}"
    return log


@scenario
def named_graph_management(I):  # noqa: E741
    ds = I.dataset()
    a, p = I.iri(EX + "a"), I.iri(EX + "p")
    g1, g2 = I.iri(EX + "g1"), I.iri(EX + "g2")
    I.get_graph(ds, g1).add((a, p, I.lit("1", dt="http://www.w3.org/2001/XMLSchema#integer")))
    I.get_graph(ds, g2).add((a, p, a))
    out = {"names": norm_set(I.graph_names(ds)), "len_g1": len(I.get_graph(ds, g1)), "quads": norm_set(I.quads(ds))}
    I.remove_graph(ds, g1)
    out["after_remove"] = norm_set(I.graph_names(ds))
    return out


@scenario
def set_operators(I):  # noqa: E741
    a, p, b, c, d = (I.iri(EX + x) for x in "apbcd")
    x = _data(I, (a, p, b), (a, p, c))
    y = _data(I, (a, p, c), (a, p, d))
    n = _Norm()
    return {k: norm_set(I.triples(f(x, y)), n) for k, f in {
        "add": lambda x, y: x + y, "sub": lambda x, y: x - y, "and": lambda x, y: x & y, "xor": lambda x, y: x ^ y}.items()}


@scenario
def error_types(I):  # noqa: E741
    g = I.graph()
    out = {}
    for label, fn in {
        "parse_syntax": lambda: g.parse(data="<a> <b> broken", format="turtle"),
        "query_syntax": lambda: g.query("SELEC * WHERE {}"),
        "update_syntax": lambda: g.update("INSER DATA {}"),
        "unknown_format": lambda: g.parse(data="x", format="nonsense-format"),
        "literal_subject": lambda: g.add((I.lit("x"), I.iri(EX + "p"), I.iri(EX + "o"))),
        "literal_predicate": lambda: g.add((I.iri(EX + "s"), I.lit("x"), I.iri(EX + "o"))),
    }.items():
        try:
            fn()
            out[label] = "no error"
        except Exception as e:  # noqa: BLE001
            out[label] = type(e).__name__
    return out


@scenario
def serialize_prefixes(I):  # noqa: E741
    g = I.graph()
    g.parse(data=TTL, format="turtle")
    text = g.serialize(format="turtle")
    text = text.decode() if isinstance(text, bytes) else text
    return {"has_prefix_line": "@prefix ex: <http://example.org/>" in text, "uses_curie": "ex:a" in text,
            "prefix_dict": I.prefixes(g) if I.name == "new" else {k: v for k, v in I.prefixes(g).items() if k == "ex"}}


@scenario
def fresh_graph_prefixes(I):  # noqa: E741
    return sorted(I.prefixes(I.graph()))[:5]


@scenario
def base_resolution(I):  # noqa: E741
    g = I.graph()
    g.parse(data="<a> <p> <b> .", format="turtle", **({"publicID": "http://example.org/"} if I.name == "old" else {"base": "http://example.org/"}))
    return norm_set(I.triples(g))


@scenario
def dirlang_and_lang_case_in_query(I):  # noqa: E741
    g = I.graph()
    g.parse(data='@prefix ex: <http://example.org/> . ex:a ex:p "x"@en-US, "y"@en--ltr .', format="turtle12" if I.name == "old" else "turtle")
    r = I.rows(g.query("SELECT ?o (LANG(?o) AS ?l) WHERE { ?s ?p ?o } ORDER BY ?o"))
    return norm_set(r["rows"])


#: scenario -> (verdict, why). Everything not listed must agree exactly; a listed one must still differ (strict), so the entry
#: is deleted when a library change makes the two agree.
ACCEPTED = "accepted give-up"
BUG = "bug"
KNOWN: dict[str, tuple[str, str]] = {
    "literals_via_add": (ACCEPTED, "Oxigraph lowercases language tags (EN-us -> en-us) and its store rewrites literals on insert "
                         "(decimal 1.0 -> 1, double 1e0 -> 1; starlayer #190). rdflib keeps the tag case and writes doubles/decimals "
                         "in its own canonical form (1.0)."),
    "literals_via_turtle_parse": (ACCEPTED, "Same two causes: language-tag case, and the store's literal rewrite after the parser "
                                  "kept the lexical form."),
    "numeric_formatting": (ACCEPTED, "Oxigraph's decimal arithmetic keeps 18 fractional digits (rdflib 28), prints whole decimals and "
                           "doubles without '.0' (3, 2 against 3.0, 2.0), and xsd:double of an integer constant above the i64 range "
                           "is an error (unbound) where Python ints are unbounded."),
    "same_term_numeric_constants": (ACCEPTED, "Oxigraph's SPARQL parser normalises numeric constants, so sameTerm(\"1\"^^xsd:integer, "
                                    "\"01\"^^xsd:integer) is true (rdflib: false)."),
    "error_types": (ACCEPTED, "Exception classes differ: SyntaxError (with position) / TypeError / ValueError instead of "
                    "BadSyntax / ParseException / ValueError / PluginException."),
    "dataset_default_graph_in_query": (ACCEPTED, "OxDataset defaults to default_union=True (the default graph of a query, and triples(), "
                                       "are the union of all graphs, as the engine's view and Oxigraph's query option do); "
                                       "StarLayerDataset defaults to the default graph only. default_union=False agrees "
                                       "(dataset_default_graph_without_union)."),
    "fresh_graph_prefixes": (ACCEPTED, "A new rdflib graph carries 29 default bindings (owl, rdf, xsd, ...); a new OxGraph has none "
                             "(decision 2.1/5.7: the global DEFAULT_PREFIXES, empty by default, is copied in)."),
    "dirlang_and_lang_case_in_query": (ACCEPTED, "Language-tag case: LANG() returns en-us, not en-US."),
}


#: results that depend on the process (hash seed), compared by their own test
NONDETERMINISTIC = {"select_star_column_order"}


def run_both() -> dict[str, tuple[Any, Any]]:
    out = {}
    for name, fn in SCENARIOS.items():
        res = []
        for impl in (OldImpl(), NewImpl()):
            try:
                res.append(fn(impl))
            except Exception as e:  # noqa: BLE001
                res.append(f"EXC {type(e).__name__}: {str(e)[:150]}")
        out[name] = tuple(res)
    return out


if __name__ == "__main__":
    import pprint

    for name, (old, new) in run_both().items():
        if old == new:
            print(f"== {name}: same")
        else:
            print(f"== {name}: DIFFERENT")
            print("  old:")
            pprint.pprint(old, width=150)
            print("  new:")
            pprint.pprint(new, width=150)
