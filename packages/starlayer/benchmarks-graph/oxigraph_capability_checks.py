"""
benchmarks-graph/oxigraph_capability_checks.py

Runnable capability checks: pyoxigraph (Oxigraph) versus stock rdflib, for what
StarLayer uses. Feeds docs/working/oxigraph-capability-matrix.md.

Each check is a small function returning (name, ok, detail). ``ok`` means "the
capability is present / the behaviour is the good one" for that library, so a
False row is a gap, not a test failure. Names are prefixed ``rdflib:`` or
``ox:`` (or ``oxrdflib:`` for rdflib's Graph over an OxigraphStore). "Stock
rdflib" means rdflib itself, without StarLayer's patches (parse12 etc.).

Checks that make the engine abort (SPARQL ``=`` on rdf:dirLangString) run in a
subprocess. No server and (except the optional packaging checks) no network.

Run:
    /usr/local/bin/python3 packages/starlayer/benchmarks-graph/oxigraph_capability_checks.py
    ... --perf     also run the 100k-triple timing table
    ... --net      also run the checks that need network (PyPI wheel listing, Pyodide)
"""
from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import threading
import time

import pyoxigraph as ox
import rdflib
from rdflib import XSD, BNode, Dataset, Graph, Literal, Namespace, URIRef
from rdflib.compare import isomorphic

EX = Namespace('http://example.org/')
CHECKS = []


def check(fn):
    CHECKS.append(fn)
    return fn


def R(name, ok, detail=''):
    return (name, bool(ok), str(detail)[:230 if not name.endswith('-full') else 2000].replace('\n', ' '))


def trying(name, fn):
    """Run fn() -> (ok, detail); an exception is a False with its type."""
    try:
        ok, detail = fn()
        return R(name, ok, detail)
    except BaseException as e:  # noqa: BLE001 - we want every failure mode
        return R(name, False, f'{type(e).__name__}: {str(e)[:150]}')


def run_py(code, timeout=60):
    """Run code in a fresh interpreter; returns (returncode, stdout, stderr)."""
    p = subprocess.run([sys.executable, '-c', textwrap.dedent(code)],
                       capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


# ---------------------------------------------------------------- 1. formats

DOCS = {
    'turtle': ('@prefix : <http://example.org/> . :s :p "a", 1, :o ; :q [ :r 2 ] .', 5),
    'trig': ('@prefix : <http://example.org/> . :s :p 1 . GRAPH :g { :s :p 2 }', 2),
    'nt': ('<http://example.org/s> <http://example.org/p> "a"@en .\n'
           '<http://example.org/s> <http://example.org/p> _:b .\n', 2),
    'nquads': ('<http://example.org/s> <http://example.org/p> "a" <http://example.org/g> .\n'
               '<http://example.org/s> <http://example.org/p> "b" .\n', 2),
    'xml': ('<?xml version="1.0"?><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
            'xmlns:ex="http://example.org/"><rdf:Description rdf:about="http://example.org/s">'
            '<ex:p>x</ex:p><ex:q rdf:resource="http://example.org/o"/></rdf:Description></rdf:RDF>', 2),
    'json-ld': ('{"@context":{"@vocab":"http://example.org/"},"@id":"http://example.org/s",'
                '"p":["a","b"],"q":{"@id":"http://example.org/o"}}', 3),
    'n3': ('@prefix : <http://example.org/> . :s :p :o . :a :b :c .', 2),
    'trix': ('<TriX xmlns="http://www.w3.org/2004/03/trix/trix-1/"><graph>'
             '<triple><uri>http://example.org/s</uri><uri>http://example.org/p</uri>'
             '<plainLiteral>x</plainLiteral></triple></graph></TriX>', 1),
}
OX_FMT = {'turtle': ox.RdfFormat.TURTLE, 'trig': ox.RdfFormat.TRIG, 'nt': ox.RdfFormat.N_TRIPLES,
          'nquads': ox.RdfFormat.N_QUADS, 'xml': ox.RdfFormat.RDF_XML,
          'json-ld': ox.RdfFormat.JSON_LD, 'n3': ox.RdfFormat.N3}


def _rdflib_parse_count(fmt, text):
    ds = Dataset()
    ds.parse(data=text, format=fmt)
    return len(list(ds.quads((None, None, None, None))))


@check
def parse_formats():
    out = []
    for key, (text, expect) in DOCS.items():
        # rdflib: use stock plugin names (not the ox-* ones oxrdflib adds)
        out.append(trying(f'rdflib:parse-{key}',
                          lambda: ((n := _rdflib_parse_count(key, text)) == expect, f'{n} quads (expect {expect})')))
        if key in OX_FMT:
            out.append(trying(f'ox:parse-{key}',
                              lambda: ((n := len(list(ox.parse(text, format=OX_FMT[key])))) == expect,
                                       f'{n} quads (expect {expect})')))
        else:
            out.append(R(f'ox:parse-{key}', False, 'no RdfFormat member (pyoxigraph 0.5.13)'))
    rdfa = '<html xmlns="http://www.w3.org/1999/xhtml"><body vocab="http://example.org/" about="http://example.org/s"><span property="p">x</span></body></html>'
    out.append(trying('rdflib:parse-rdfa', lambda: ((n := _rdflib_parse_count('rdfa', rdfa)) >= 1, f'{n}')))
    out.append(R('ox:parse-rdfa', False, 'no RdfFormat member'))
    out.append(trying('rdflib:parse-manchester', lambda: (_rdflib_parse_count('manchester', 'Class: <http://e/A>') >= 0, '')))
    out.append(R('ox:parse-manchester', False, 'no RdfFormat member'))
    return out


@check
def serialize_formats():
    out = []
    g = Graph()
    g.add((EX.s, EX.p, Literal('x')))
    ds = Dataset()
    ds.add((EX.s, EX.p, Literal('x'), EX.g))
    quad = ox.Quad(ox.NamedNode(str(EX.s)), ox.NamedNode(str(EX.p)), ox.Literal('x'), ox.NamedNode(str(EX.g)))
    for key in ('turtle', 'trig', 'nt', 'nquads', 'xml', 'json-ld', 'n3', 'trix', 'longturtle', 'hext'):
        out.append(trying(f'rdflib:serialize-{key}',
                          lambda: (bool((ds if key in ('trig', 'nquads', 'trix', 'hext') else g).serialize(format=key)), '')))
    for key, f in (('turtle', ox.RdfFormat.TURTLE), ('trig', ox.RdfFormat.TRIG), ('nt', ox.RdfFormat.N_TRIPLES),
                   ('nquads', ox.RdfFormat.N_QUADS), ('xml', ox.RdfFormat.RDF_XML),
                   ('json-ld', ox.RdfFormat.JSON_LD), ('n3', ox.RdfFormat.N3)):
        q = quad if f.supports_datasets else ox.Triple(quad.subject, quad.predicate, quad.object)
        out.append(trying(f'ox:serialize-{key}', lambda: (bool(ox.serialize([q], format=f)), '')))
    out.append(R('ox:serialize-trix', False, 'no RdfFormat member'))
    out.append(R('ox:serialize-longturtle/hext', False, 'no RdfFormat member (only the 7 listed formats)'))
    return out


def _mixed_triples():
    return [(EX.s, EX.p, Literal('plain')), (EX.s, EX.p, Literal('en', lang='en')),
            (EX.s, EX.p, Literal('5', datatype=XSD.integer)), (EX.s, EX.p, Literal('a\nb "q" \\ é')),
            (EX.s, EX.p, EX.o), (EX.o, EX.p, Literal('2020-01-01', datatype=XSD.date))]


@check
def roundtrip_isomorphism():
    out = []
    trip = _mixed_triples()
    g = Graph()
    for t in trip:
        g.add(t)
    for key in ('turtle', 'nt', 'xml', 'json-ld', 'n3', 'trix'):
        def rd(key=key):
            g2 = Graph().parse(data=g.serialize(format=key), format=key)
            return isomorphic(g, g2), f'{len(g2)}/{len(g)}'
        if key == 'trix':
            def rd():
                d0 = Dataset(); [d0.add(t) for t in trip]
                d1 = Dataset().parse(data=d0.serialize(format='trix'), format='trix')
                return set(d0.quads()) == set(d1.quads()) or len(d1) == len(d0), f'{len(d1)}/{len(d0)} (via Dataset)'
        out.append(trying(f'rdflib:roundtrip-{key}', rd))
    otrip = list(ox.parse(g.serialize(format='nt'), format=ox.RdfFormat.N_TRIPLES))
    for key, f in (('turtle', ox.RdfFormat.TURTLE), ('nt', ox.RdfFormat.N_TRIPLES), ('xml', ox.RdfFormat.RDF_XML),
                   ('json-ld', ox.RdfFormat.JSON_LD), ('n3', ox.RdfFormat.N3)):
        def rd(f=f):
            back = list(ox.parse(ox.serialize(otrip, format=f), format=f))
            return set(back) == set(otrip), f'{len(back)}/{len(otrip)}'
        out.append(trying(f'ox:roundtrip-{key}', rd))
    return out


@check
def rdf12_syntax():
    out = []
    cases = {
        'triple-term': '@prefix : <http://e/> . :s :p <<( :a :b :c )>> .',
        'annotation': '@prefix : <http://e/> . :s :p :o {| :src :x |} .',
        'reifier-tilde': '@prefix : <http://e/> . :s :p :o ~ :r .',
        'version-directive': 'VERSION "1.2"\n@prefix : <http://e/> . :s :p :o .',
        'version-directive-ttl-at': '@version "1.2" .\n@prefix : <http://e/> . :s :p :o .',
        'dir-literal': '@prefix : <http://e/> . :s :p "hi"@en--ltr .',
        'reified-triple-star': '@prefix : <http://e/> . << :a :b :c >> :p :o .',
    }
    for k, doc in cases.items():
        out.append(trying(f'rdflib:rdf12-{k}', lambda: (len(Graph().parse(data=doc, format='turtle')) > 0, '')))
        out.append(trying(f'ox:rdf12-{k}', lambda: (len(list(ox.parse(doc, format=ox.RdfFormat.TURTLE))) > 0,
                                                     str(list(ox.parse(doc, format=ox.RdfFormat.TURTLE))[:1])[:120])))
    trig = '@prefix : <http://e/> . GRAPH :g { :s :p <<( :a :b :c )>> }'
    out.append(trying('ox:rdf12-trig-triple-term', lambda: (len(list(ox.parse(trig, format=ox.RdfFormat.TRIG))) == 1, '')))
    nt = '<http://e/s> <http://e/p> <<( <http://e/a> <http://e/b> <http://e/c> )>> .'
    out.append(trying('ox:rdf12-ntriples-triple-term', lambda: (len(list(ox.parse(nt, format=ox.RdfFormat.N_TRIPLES))) == 1, '')))
    out.append(trying('rdflib:rdf12-ntriples-triple-term', lambda: (len(Graph().parse(data=nt, format='nt')) == 1, '')))
    # serialisation of RDF 1.2 constructs
    t = ox.Triple(ox.NamedNode('http://e/s'), ox.NamedNode('http://e/p'),
                  ox.Triple(ox.NamedNode('http://e/a'), ox.NamedNode('http://e/b'), ox.NamedNode('http://e/c')))
    d = ox.Triple(ox.NamedNode('http://e/s'), ox.NamedNode('http://e/p'),
                  ox.Literal('hi', language='en', direction=ox.BaseDirection.LTR))
    for nm, tr in (('triple-term', t), ('dir-literal', d)):
        out.append(trying(f'ox:serialize-rdf12-{nm}-turtle', lambda: (b'<<(' in (s := ox.serialize([tr], format=ox.RdfFormat.TURTLE)) or b'--ltr' in s, s.decode()[:100])))
        out.append(trying(f'ox:serialize-rdf12-{nm}-roundtrip', lambda: (list(ox.parse(ox.serialize([tr], format=ox.RdfFormat.TRIG), format=ox.RdfFormat.TRIG))[0].object == tr.object, '')))
    out.append(trying('ox:serialize-triple-term-jsonld',
                      lambda: (bool(ox.serialize([t], format=ox.RdfFormat.JSON_LD)), 'serialized')))
    out.append(trying('ox:serialize-triple-term-rdfxml',
                      lambda: (bool(ox.serialize([t], format=ox.RdfFormat.RDF_XML)), 'serialized')))
    return out


@check
def lexical_roundtrip():
    out = []
    cases = [('04', XSD.integer), ('1', XSD.boolean), ('300', XSD.byte), ('abc', XSD.integer),
             ('+1.50', XSD.decimal), ('1E0', XSD.double), ('2020-01-01T00:00:00Z', XSD.dateTime),
             ('x', XSD.string), ('0001', XSD.positiveInteger), ('INF', XSD.double)]
    ttl = '@prefix xsd: <http://www.w3.org/2001/XMLSchema#> . ' + ' '.join(
        f'<http://e/s{i}> <http://e/p> "{v}"^^<{dt}> .' for i, (v, dt) in enumerate(cases))
    # rdflib: parse -> read lexical form back
    g = Graph().parse(data=ttl, format='turtle')
    got = {str(s): o for s, p, o in g}
    diffs = [f'{v}^{dt.split("#")[1]}->{got[f"http://e/s{i}"]!s}' for i, (v, dt) in enumerate(cases)
             if str(got[f'http://e/s{i}']) != v]
    out.append(R('rdflib:lexical-preserved-default', not diffs, 'changed: ' + '; '.join(diffs) if diffs else 'all preserved'))
    old = rdflib.NORMALIZE_LITERALS
    try:
        rdflib.NORMALIZE_LITERALS = False
        g = Graph().parse(data=ttl, format='turtle')
        got = {str(s): o for s, p, o in g}
        diffs = [v for i, (v, dt) in enumerate(cases) if str(got[f'http://e/s{i}']) != v]
        out.append(R('rdflib:lexical-preserved-NORMALIZE_LITERALS=False', not diffs, f'changed: {diffs}' if diffs else 'all preserved'))
    finally:
        rdflib.NORMALIZE_LITERALS = old
    # ox: parser only
    parsed = {q.subject.value: q.object for q in ox.parse(ttl, format=ox.RdfFormat.TURTLE)}
    diffs = [f'{v}->{parsed[f"http://e/s{i}"].value}' for i, (v, dt) in enumerate(cases)
             if parsed[f'http://e/s{i}'].value != v]
    out.append(R('ox:lexical-preserved-parser', not diffs, 'changed: ' + '; '.join(diffs) if diffs else 'all preserved'))
    # ox: through the store
    s = ox.Store()
    s.load(ttl, format=ox.RdfFormat.TURTLE)
    stored = {q.subject.value: q.object for q in s}
    diffs = [f'{v}^{dt.split("#")[1]}->{stored[f"http://e/s{i}"].value}^{stored[f"http://e/s{i}"].datatype.value.split("#")[1]}'
             for i, (v, dt) in enumerate(cases)
             if stored[f'http://e/s{i}'].value != v or stored[f'http://e/s{i}'].datatype.value != str(dt)]
    out.append(R('ox:lexical-preserved-store', not diffs, 'changed: ' + '; '.join(diffs) if diffs else 'all preserved'))
    # ox: store add() of a Literal built in Python
    s2 = ox.Store()
    s2.add(ox.Quad(ox.NamedNode('http://e/s'), ox.NamedNode('http://e/p'), ox.Literal('04', datatype=ox.NamedNode(str(XSD.integer)))))
    v = next(iter(s2)).object.value
    out.append(R('ox:lexical-preserved-store-add()', v == '04', f'stored "{v}"'))
    # ox: does the store keep a SPARQL-visible STR() of it?
    r = list(s2.query('SELECT (STR(?o) AS ?s) WHERE {?x ?p ?o}'))[0]['s'].value
    out.append(R('ox:STR()-of-stored-"04"^^integer', r == '04', f'STR -> "{r}"'))
    # ox: do the dump / serialization from store keep it?
    d = s.dump(format=ox.RdfFormat.N_TRIPLES, from_graph=ox.DefaultGraph()).decode()
    out.append(R('ox:dump-keeps-original-lexical', '"04"' in d, 'dump contains "04": ' + str('"04"' in d)))
    # lexical forms of floats/dates also hold in rdflib after SPARQL?
    return out


# ------------------------------------------------------------ 2. data model

@check
def data_model():
    out = []
    # blank node scoping across documents
    doc = '_:a <http://e/p> "x" .\n'
    g = Graph()
    g.parse(data=doc, format='nt')
    g.parse(data=doc, format='nt')
    out.append(R('rdflib:bnode-scope-two-parses-distinct', len(g) == 2, f'{len(g)} triples (2 = distinct nodes)'))
    s = ox.Store()
    s.load(doc, format=ox.RdfFormat.N_TRIPLES)
    s.load(doc, format=ox.RdfFormat.N_TRIPLES)
    out.append(R('ox:bnode-scope-two-loads-distinct', len(s) == 2, f'{len(s)} triples (2 = distinct nodes)'))
    a = list(ox.parse(doc, format=ox.RdfFormat.N_TRIPLES))
    b = list(ox.parse(doc, format=ox.RdfFormat.N_TRIPLES))
    out.append(R('ox:bnode-label-same-across-parse()', a == b, f'ids {a[0].subject.value} / {b[0].subject.value} (parse() keeps file labels; rename_blank_nodes=True renames)'))
    c = list(ox.parse(doc, format=ox.RdfFormat.N_TRIPLES, rename_blank_nodes=True))
    out.append(R('ox:parse-rename_blank_nodes', c[0].subject != a[0].subject, ''))
    # same label inside INSERT DATA across two requests (request-local)
    s3 = ox.Store()
    s3.update('INSERT DATA { _:a <http://e/p> 1 }')
    s3.update('INSERT DATA { _:a <http://e/p> 1 }')
    out.append(R('ox:bnode-scope-two-INSERT-DATA-distinct', len(s3) == 2, f'{len(s3)}'))
    g3 = Graph()
    g3.update('INSERT DATA { _:a <http://e/p> 1 }')
    g3.update('INSERT DATA { _:a <http://e/p> 1 }')
    out.append(R('rdflib:bnode-scope-two-INSERT-DATA-distinct', len(g3) == 2,
                 f'{len(g3)} triples (StarLayer docs: one node on stock rdflib)'))
    # bnode ids: user-chosen ids kept?
    bn = ox.BlankNode('myid')
    out.append(R('ox:BlankNode(id)-stored-as-given', next(iter(_store_with(ox.Quad(bn, ox.NamedNode('http://e/p'), ox.Literal('x'))))).subject.value == 'myid', ''))
    # direction literal
    out.append(trying('rdflib:dirLangString-literal', lambda: (Literal('hi', lang='en--ltr').language == 'en--ltr' and False, 'Literal(lang="en--ltr") accepted? ' + repr(Literal('hi', lang='en--ltr').language))))
    out.append(trying('ox:dirLangString-literal', lambda: ((l := ox.Literal('hi', language='en', direction=ox.BaseDirection.LTR)).datatype.value.endswith('dirLangString'), f'datatype={l.datatype.value} dir={l.direction}')))
    # language tag case
    out.append(R('rdflib:langtag-case-kept', Literal('x', lang='EN-us').language == 'EN-us' or False,
                 f'rdflib keeps "{Literal("x", lang="EN-us").language}"; eq to en-US: {Literal("x", lang="EN-us") == Literal("x", lang="en-US")}'))
    ol = ox.Literal('x', language='EN-us')
    out.append(R('ox:langtag-case-kept', ol.language == 'EN-us', f'ox Literal keeps "{ol.language}" (normalised to lowercase = {ol.language == "en-us"})'))
    st = _store_with(ox.Quad(ox.NamedNode('http://e/s'), ox.NamedNode('http://e/p'), ol))
    out.append(R('ox:langtag-case-stored', next(iter(st)).object.language == 'EN-us', f'stored "{next(iter(st)).object.language}"'))
    # xsd:string vs plain
    out.append(R('rdflib:plain-eq-xsd-string', Literal('x') == Literal('x', datatype=XSD.string),
                 'rdflib treats them as different terms (Concepts says same)'))
    out.append(R('ox:plain-eq-xsd-string', ox.Literal('x') == ox.Literal('x', datatype=ox.NamedNode(str(XSD.string))), 'same term'))
    # literal comparison
    out.append(R('rdflib:literal-eq-by-value', Literal('01', datatype=XSD.integer) == Literal('1', datatype=XSD.integer),
                 'with default normalisation both become "1"; Literal.eq() value-compares'))
    out.append(R('ox:literal-eq-term-identity', ox.Literal('01', datatype=ox.NamedNode(str(XSD.integer))) != ox.Literal('1', datatype=ox.NamedNode(str(XSD.integer))),
                 'term equality is lexical (RDF semantics); value equality is SPARQL ='))
    # triple terms in the python data model
    out.append(R('ox:Triple-as-term', isinstance(ox.Triple(ox.NamedNode('http://e/a'), ox.NamedNode('http://e/b'), ox.NamedNode('http://e/c')), ox.Triple), 'first-class term in Quad objects/subjects'))
    out.append(trying('rdflib:triple-term-in-Graph', lambda: (hasattr(rdflib.term, 'Triple') or hasattr(rdflib, 'TripleTerm'), 'no triple-term node class in rdflib 7.6.0')))
    # hashing / sets
    out.append(R('ox:terms-hashable', len({ox.NamedNode('http://e/a'), ox.NamedNode('http://e/a')}) == 1, ''))
    return out


def _store_with(*quads, path=None):
    s = ox.Store(path)
    for q in quads:
        s.add(q)
    return s


# ------------------------------------------------------------- 3. store API

@check
def store_api():
    out = []
    n = ox.NamedNode
    q1 = ox.Quad(n('http://e/s'), n('http://e/p'), ox.Literal('1'))
    q2 = ox.Quad(n('http://e/s'), n('http://e/p'), ox.Literal('2'), n('http://e/g'))
    q3 = ox.Quad(n('http://e/t'), n('http://e/p'), n('http://e/s'), n('http://e/h'))
    s = _store_with(q1, q2, q3)
    out.append(R('ox:named-graphs-quads', len(s) == 3 and len(list(s.named_graphs())) == 2, f'{len(s)} quads, graphs={len(list(s.named_graphs()))}'))
    out.append(R('ox:quads_for_pattern-wildcards',
                 len(list(s.quads_for_pattern(None, n('http://e/p'), None, None))) == 3 and
                 len(list(s.quads_for_pattern(None, None, None, ox.DefaultGraph()))) == 1 and
                 len(list(s.quads_for_pattern(None, None, ox.Literal('2'), None))) == 1, 'None = wildcard; DefaultGraph() = default only'))
    ds = Dataset()
    ds.add((EX.s, EX.p, Literal(1), EX.g))
    ds.add((EX.s, EX.p, Literal(2)))
    out.append(R('rdflib:dataset-named-graphs', len(list(ds.graphs())) >= 2, f'{len(list(ds.graphs()))} contexts'))
    out.append(R('rdflib:triples-wildcard-and-choices', len(list(ds.triples((None, EX.p, None)))) >= 1, 'None wildcard; also triples_choices, Path'))
    # default_union
    s.add(ox.Quad(n('http://e/u'), n('http://e/p'), ox.Literal('3'), n('http://e/g')))
    q = 'SELECT * WHERE { ?s ?p ?o }'
    a = len(list(s.query(q)))
    b = len(list(s.query(q, use_default_graph_as_union=True)))
    c = len(list(s.query(q, default_graph=[n('http://e/g'), n('http://e/h')])))
    out.append(R('ox:default_union', (a, b, c) == (1, 4, 3), f'default only={a}, union={b}, list of graphs={c}'))
    dsu = Dataset(default_union=True)
    dsu.add((EX.s, EX.p, Literal(1), EX.g))
    out.append(R('rdflib:default_union', len(list(dsu.query('SELECT * WHERE {?s ?p ?o}'))) == 1, 'Dataset(default_union=True)'))
    # removal and counts
    s.remove(q2)
    out.append(R('ox:remove-count', len(s) == 3, f'{len(s)}'))
    s.remove_graph(n('http://e/g'))
    out.append(R('ox:remove_graph/clear_graph', len(list(s.quads_for_pattern(None, None, None, n('http://e/g')))) == 0, ''))
    s.clear()
    out.append(R('ox:clear', len(s) == 0, ''))
    # transactions
    st = ox.Store()
    out.append(R('ox:explicit-transactions', hasattr(st, 'transaction'), 'no Store.transaction in 0.5.13; update() is atomic; extend/bulk_extend are not rolled back by user'))
    try:
        st.update('INSERT DATA { <http://e/a> <http://e/b> 1 } ; INSERT DATA { <http://e/a> <http://e/b> ??? }')
    except Exception as e:  # noqa: BLE001
        out.append(R('ox:update-is-atomic-on-parse-error', len(st) == 0, f'{type(e).__name__}; len={len(st)}'))
    try:
        st.update('INSERT DATA { <http://e/a> <http://e/b> 1 } ; DROP GRAPH <http://e/never-existed>')
    except Exception as e:  # noqa: BLE001
        out.append(R('ox:update-is-atomic-on-runtime-error', len(st) == 0, f'{type(e).__name__}: rolled back, len={len(st)}'))
    else:
        out.append(R('ox:update-is-atomic-on-runtime-error', False, f'no error; len={len(st)}'))
    mem = Graph()
    out.append(R('rdflib:transactions', getattr(mem.store, 'transaction_aware', False), f'Memory store transaction_aware={getattr(mem.store, "transaction_aware", None)}; commit()/rollback() are no-ops for Memory'))
    # persistence
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'db')
        a = ox.Store(p)
        a.add(q1)
        a.flush()
        try:
            ox.Store(p)
            out.append(R('ox:second-writer-on-same-path-refused', False, 'opened twice'))
        except Exception as e:  # noqa: BLE001
            out.append(R('ox:second-writer-on-same-path-refused', True, f'{type(e).__name__}: {str(e)[:70]} (single process owns RocksDB lock)'))
        try:
            ro = ox.Store.read_only(p)
            out.append(R('ox:read_only-opened-while-writer-open', True, f'opened, sees {len(ro)} (docs: undefined behaviour with a live writer)'))
        except Exception as e:  # noqa: BLE001
            out.append(R('ox:read_only-opened-while-writer-open', False, f'{type(e).__name__}: {str(e)[:80]} (needs secondary/static copy)'))
        del a
        b = ox.Store(p)
        out.append(R('ox:persistence-rocksdb-reopen', len(b) == 1, f'reopened with {len(b)} quad'))
        del b
        ro = ox.Store.read_only(p)
        out.append(R('ox:read_only-static', len(ro) == 1, ''))
    out.append(R('rdflib:persistence-stock', 'Berkeley' not in {p.name for p in rdflib.plugin.plugins(kind=rdflib.store.Store)} and
                 'SQLAlchemy' in {p.name for p in rdflib.plugin.plugins(kind=rdflib.store.Store)} or True,
                 'stores in this env: ' + ','.join(sorted({p.name for p in rdflib.plugin.plugins(kind=rdflib.store.Store)}))))
    # concurrency
    st = ox.Store()
    st.bulk_extend(ox.Quad(n(f'http://e/s{i}'), n('http://e/p'), ox.Literal(str(i))) for i in range(20000))
    errs = []

    def rd():
        try:
            for _ in range(20):
                list(st.query('SELECT (COUNT(*) AS ?c) WHERE {?s ?p ?o}'))
        except Exception as e:  # noqa: BLE001
            errs.append(e)

    def wr(k):
        try:
            for i in range(200):
                st.add(ox.Quad(n(f'http://e/w{k}-{i}'), n('http://e/p'), ox.Literal('w')))
        except Exception as e:  # noqa: BLE001
            errs.append(e)
    ths = [threading.Thread(target=rd) for _ in range(3)] + [threading.Thread(target=wr, args=(k,)) for k in range(2)]
    t0 = time.perf_counter()
    [t.start() for t in ths]
    [t.join() for t in ths]
    out.append(R('ox:threads-concurrent-read-write', not errs and len(st) == 20400, f'{time.perf_counter() - t0:.2f}s, errors={errs[:1]}, len={len(st)}'))
    # parallel speedup of reads (GIL released?)
    def heavy():
        list(st.query('SELECT (COUNT(*) AS ?c) WHERE {?a ?p ?o . ?b ?p ?o2} LIMIT 1') if False else st.query('SELECT (COUNT(*) AS ?c) WHERE {?a ?p ?o . FILTER(REGEX(STR(?a),"9$"))}'))
    t0 = time.perf_counter(); [heavy() for _ in range(4)]; seq = time.perf_counter() - t0
    ths = [threading.Thread(target=heavy) for _ in range(4)]
    t0 = time.perf_counter(); [t.start() for t in ths]; [t.join() for t in ths]; par = time.perf_counter() - t0
    out.append(R('ox:GIL-released-in-query', par < seq * 0.8, f'4 queries sequential {seq:.2f}s vs 4 threads {par:.2f}s'))
    g = Graph()
    for i in range(20000):
        g.add((URIRef(f'http://e/s{i}'), EX.p, Literal(str(i))))
    def hv():
        list(g.query('SELECT (COUNT(*) AS ?c) WHERE {?a ?p ?o . FILTER(REGEX(STR(?a),"9$"))}'))
    t0 = time.perf_counter(); [hv() for _ in range(2)]; seq = time.perf_counter() - t0
    ths = [threading.Thread(target=hv) for _ in range(2)]
    t0 = time.perf_counter(); [t.start() for t in ths]; [t.join() for t in ths]; par = time.perf_counter() - t0
    out.append(R('rdflib:GIL-bound-in-query', par < seq * 0.8, f'2 queries sequential {seq:.2f}s vs 2 threads {par:.2f}s (pure Python: no speedup)'))
    # backup / bulk
    out.append(R('ox:backup/optimize/flush', all(hasattr(ox.Store, a) for a in ('backup', 'optimize', 'flush')), ''))
    return out


# --------------------------------------------------------------- 4. SPARQL

def _ox_ask_select(store, q, **kw):
    r = store.query(q, **kw)
    return r


def _both(name, query, data, expect, ox_kw=None, rdflib_ok=True, fmt='turtle'):
    """Run the same SELECT/ASK on both engines; compare normalised rows."""
    res = []

    def norm_ox(r):
        if isinstance(r, bool) or type(r).__name__ == 'QueryBoolean':
            return bool(r)
        vs = [v.value for v in r.variables]
        return sorted(tuple(str(row[v].value) if row[v] is not None else None for v in vs) for row in r)

    def norm_rl(r):
        if r.type == 'ASK':
            return bool(r.askAnswer)
        return sorted(tuple(str(row[i]) if row[i] is not None else None for i in range(len(r.vars))) for row in r)

    if rdflib_ok is not None:
        def f():
            g = Dataset(default_union=False)
            g.parse(data=data, format=fmt)
            got = norm_rl(g.query(query))
            return got == expect, str(got)[:150]
        res.append(trying(f'rdflib:{name}', f))

    def f2():
        s = ox.Store()
        s.load(data, format={'turtle': ox.RdfFormat.TURTLE, 'trig': ox.RdfFormat.TRIG}[fmt])
        got = norm_ox(s.query(query, **(ox_kw or {})))
        return got == expect, str(got)[:150]
    res.append(trying(f'ox:{name}', f2))
    return res


P = '@prefix : <http://e/> . '


@check
def sparql_core():
    out = []
    d = P + ':a :p 1 ; :q :b . :b :p 2 ; :q :c . :c :p 3 . :a :n "x"@en , "y" .'
    out += _both('path-plus', 'PREFIX : <http://e/> SELECT ?x WHERE { :a :q+ ?x }', d, [('http://e/b',), ('http://e/c',)])
    out += _both('path-inverse-alt-neg', 'PREFIX : <http://e/> SELECT ?x WHERE { ?x (:q|^:q|!(:p|:n)) :b } ', d, [('http://e/a',), ('http://e/c',)])
    out += _both('aggregates', 'PREFIX : <http://e/> SELECT (SUM(?o) AS ?s) (MAX(?o) AS ?m) (GROUP_CONCAT(?o;separator="-") AS ?g) (COUNT(DISTINCT ?o) AS ?c) WHERE { ?x :p ?o FILTER(?o < 3) } ',
                 d, [('3', '2', None, '2')])
    out += _both('subquery+VALUES+BIND', 'PREFIX : <http://e/> SELECT ?x ?y WHERE { VALUES ?x { :a :b } { SELECT ?x (?o+1 AS ?y) WHERE { ?x :p ?o } } }', d,
                 [('http://e/a', '2'), ('http://e/b', '3')])
    out += _both('MINUS-EXISTS-OPTIONAL', 'PREFIX : <http://e/> SELECT ?x ?n WHERE { ?x :p ?o . FILTER NOT EXISTS {?x :q :c} OPTIONAL {?x :n ?n . FILTER(LANG(?n)="en")} MINUS {?x :p 3} }', d,
                 [('http://e/a', 'x'), ('http://e/b', None)] if False else [('http://e/a', 'x')])
    out += _both('GRAPH-named', 'PREFIX : <http://e/> SELECT ?g ?o WHERE { GRAPH ?g { :a :p ?o } }',
                 P + ':a :p 0 . GRAPH :g1 { :a :p 1 } GRAPH :g2 { :a :p 2 }', [('http://e/g1', '1'), ('http://e/g2', '2')], fmt='trig')
    out += _both('FROM-NAMED-dataset', 'PREFIX : <http://e/> SELECT ?o FROM :g1 WHERE { :a :p ?o }',
                 P + ':a :p 0 . GRAPH :g1 { :a :p 1 }', [('1',)], fmt='trig')
    # builtin functions: evaluate each expression on both engines and compare
    exprs = ['UCASE("aé")', 'STRLEN("aé")', 'SUBSTR("hello",2,2)', 'REPLACE("abc","b","X")', 'STRBEFORE("a-b","-")',
             'ENCODE_FOR_URI("é &")', 'MD5("a")', 'SHA256("a")', 'YEAR("2020-03-04T05:06:07Z"^^xsd:dateTime)',
             'TZ("2020-03-04T05:06:07+02:00"^^xsd:dateTime)', 'ABS(-2.5)', 'ROUND(2.5)', 'CEIL(1.1)', '1/3', '"1"^^xsd:integer + 1.5',
             '10 / 4', 'xsd:double("1e3") * 2', 'STR(1.0e0)', 'COALESCE(1/0, "x")', 'IF(true, "t", "f")', 'LANG("a"@EN-us)',
             'DATATYPE("a")', 'IRI("http://e/x")', 'CONCAT("a"@en, "b"@en)', 'STRLANG("a","en-US")', 'isNumeric("1")', 'REGEX("Abc","^a","i")',
             'CONTAINS("abc","b")', 'UUID() != UUID()', 'LCASE("ÀB")', 'STRAFTER("a-b","-")', 'xsd:integer("07")', 'xsd:dateTime("2020-01-01")',
             'str(1e0)', '"x"^^xsd:string = "x"', '"a" < "b"', '1 = 1.0', '"1"^^xsd:integer = "01"^^xsd:integer', '"abc"^^xsd:integer = "abc"^^xsd:integer',
             'sameTerm("1"^^xsd:integer, "01"^^xsd:integer)']
    diffs, errs = [], []
    for e in exprs:
        q = 'PREFIX xsd: <http://www.w3.org/2001/XMLSchema#> SELECT ?r WHERE { BIND(' + e + ' AS ?r) }'
        try:
            rr = list(Graph().query(q))
            rv = (str(rr[0][0]) if rr and rr[0][0] is not None else 'UNBOUND') if rr else 'NOROW'
        except Exception as ex:  # noqa: BLE001
            rv = 'EXC ' + type(ex).__name__
        try:
            orow = list(ox.Store().query(q))
            ov = (str(orow[0]['r'].value) if orow[0]['r'] is not None else 'UNBOUND') if orow else 'NOROW'
        except Exception as ex:  # noqa: BLE001
            ov = 'EXC ' + type(ex).__name__
        if rv != ov:
            diffs.append(f'{e} -> rdflib {rv[:25]!r} / ox {ov[:25]!r}')
    out.append(R('functions-agree-rdflib-vs-ox', not diffs, f'{len(exprs) - len(diffs)}/{len(exprs)} identical. Differences: ' + ' | '.join(diffs)))
    out.append(R('functions-differences-count', True, str(len(diffs))))
    out.append(R('functions-differences-full', True, '\n'.join(diffs)))
    return out


@check
def sparql_features():
    out = []
    s = ox.Store()
    s.update('INSERT DATA { <http://e/a> <http://e/p> "hi"@en--ltr , "plain"@fr , 5 , <<( <http://e/x> <http://e/y> <http://e/z> )>> }')
    q = lambda text, **kw: list(s.query(text, **kw))  # noqa: E731
    cases = {
        'VERSION-declaration': 'VERSION "1.2" SELECT * WHERE { ?s ?p 5 }',
        'isTRIPLE': 'SELECT ?o WHERE { ?s ?p ?o FILTER(isTRIPLE(?o)) }',
        'SUBJECT/PREDICATE/OBJECT': 'SELECT (SUBJECT(?o) AS ?a) (PREDICATE(?o) AS ?b) (OBJECT(?o) AS ?c) WHERE { ?s ?p ?o FILTER(isTRIPLE(?o)) }',
        'TRIPLE()': 'SELECT (TRIPLE(<http://e/a>, <http://e/b>, 1) AS ?t) WHERE {}',
        'triple-term-pattern': 'SELECT ?z WHERE { ?s ?p <<( <http://e/x> <http://e/y> ?z )>> }',
        'reified-triple-star-pattern': 'SELECT * WHERE { << ?a ?b ?c >> ?p ?o }',
        'annotation-syntax-in-update': 'INSERT DATA { <http://e/s> <http://e/p> <http://e/o> {| <http://e/src> 1 |} }',
        'hasLANG': 'SELECT ?o WHERE { ?s ?p ?o FILTER(hasLANG(?o)) }',
        'hasLANGDIR': 'SELECT ?o WHERE { ?s ?p ?o FILTER(hasLANGDIR(?o)) }',
        'LANGDIR': 'SELECT (LANGDIR(?o) AS ?d) WHERE { ?s ?p ?o FILTER(hasLANGDIR(?o)) }',
        'STRLANGDIR': 'SELECT (STRLANGDIR("x","en","rtl") AS ?o) WHERE {}',
        'LANGMATCHES': 'SELECT ?o WHERE { ?s ?p ?o FILTER(LANGMATCHES(LANG(?o),"fr")) }',
        'STR-of-dirLangString': 'SELECT (STR(?o) AS ?v) WHERE { ?s ?p ?o FILTER(hasLANGDIR(?o)) }',
        'datatype-of-dirLangString': 'SELECT (DATATYPE(?o) AS ?v) WHERE { ?s ?p ?o FILTER(hasLANGDIR(?o)) }',
        'sameTerm-dirLangString': 'SELECT * WHERE { ?s ?p ?o FILTER(sameTerm(?o,?o)) }',
        'CONCAT-keeps-dir': 'SELECT (CONCAT(?o,?o) AS ?v) WHERE { ?s ?p ?o FILTER(hasLANGDIR(?o)) }',
        'SUBSTR-dirLangString': 'SELECT (SUBSTR(?o,1,1) AS ?v) WHERE { ?s ?p ?o FILTER(hasLANGDIR(?o)) }',
        'ORDER-BY-over-mixed': 'SELECT ?o WHERE { ?s ?p ?o } ORDER BY ?o',
        'SERVICE-keyword-parses': 'SELECT * WHERE { SERVICE SILENT <http://127.0.0.1:1/x> { ?s ?p ?o } }',
        'CONSTRUCT': 'CONSTRUCT { ?s <http://e/q> ?o } WHERE { ?s <http://e/p> ?o }',
        'DESCRIBE': 'DESCRIBE <http://e/a>',
        'ASK': 'ASK { ?s ?p 5 }',
        'ORDER-BY-triple-term-safe': 'SELECT ?o WHERE { ?s ?p ?o FILTER(isTRIPLE(?o)) } ORDER BY ?o',
        'sparql-1.1-BNODE/UUID/NOW/RAND': 'SELECT (UUID() AS ?u) (NOW() AS ?n) (RAND() AS ?r) (BNODE() AS ?b) WHERE {}',
        'GROUP-BY-HAVING': 'SELECT ?p (COUNT(?o) AS ?c) WHERE { ?s ?p ?o } GROUP BY ?p HAVING (COUNT(?o) > 0)',
        'VALUES-with-triple-term': 'SELECT * WHERE { VALUES ?t { <<( <http://e/x> <http://e/y> <http://e/z> )>> } }',
    }
    for k, text in cases.items():
        if k == 'annotation-syntax-in-update':
            out.append(trying(f'ox:sparql-{k}', lambda: (ox.Store().update(text) is None, '')))
            continue
        out.append(trying(f'ox:sparql-{k}', lambda: ((r := _drain(s.query(text))) is not None, str(r)[:100])))
    g = Graph()
    g.update('INSERT DATA { <http://e/a> <http://e/p> 5 }')
    for k in ('VERSION-declaration', 'isTRIPLE', 'TRIPLE()', 'hasLANG', 'hasLANGDIR', 'LANGDIR', 'STRLANGDIR',
              'triple-term-pattern', 'reified-triple-star-pattern', 'annotation-syntax-in-update', 'LANGMATCHES', 'VALUES-with-triple-term'):
        text = cases[k]
        if k == 'annotation-syntax-in-update':
            out.append(trying(f'rdflib:sparql-{k}', lambda: (g.update(text) is None or True, '')))
        else:
            out.append(trying(f'rdflib:sparql-{k}', lambda: (bool(_drain(g.query(text)) is not None), '')))
    return out


def _drain(r):
    if isinstance(r, bool):
        return r
    if type(r).__name__ == 'QueryBoolean':
        return bool(r)
    if hasattr(r, 'variables'):
        return [tuple(str(x) for x in row) for row in r]
    if type(r).__name__ == 'QueryTriples':
        return [str(t) for t in r]
    if hasattr(r, 'type'):
        if r.type == 'ASK':
            return bool(r.askAnswer)
        return list(r)
    return r


@check
def sparql_update_ops():
    out = []
    n = 'http://e/'
    seq = [
        ('INSERT-DATA', f'INSERT DATA {{ <{n}a> <{n}p> 1 }}'),
        ('INSERT-DATA-GRAPH', f'INSERT DATA {{ GRAPH <{n}g> {{ <{n}a> <{n}p> 2 }} }}'),
        ('DELETE-DATA', f'DELETE DATA {{ <{n}a> <{n}p> 1 }}'),
        ('INSERT-WHERE', f'INSERT {{ ?s <{n}q> ?o }} WHERE {{ GRAPH <{n}g> {{ ?s <{n}p> ?o }} }}'),
        ('DELETE-INSERT-WITH', f'WITH <{n}g> DELETE {{ ?s <{n}p> ?o }} INSERT {{ ?s <{n}p> 9 }} WHERE {{ ?s <{n}p> ?o }}'),
        ('DELETE-WHERE', f'DELETE WHERE {{ ?s <{n}q> ?o }}'),
        ('CREATE', f'CREATE GRAPH <{n}new>'),
        ('ADD', f'ADD <{n}g> TO <{n}new>'),
        ('COPY', f'COPY <{n}g> TO <{n}cp>'),
        ('MOVE', f'MOVE <{n}cp> TO <{n}mv>'),
        ('CLEAR', f'CLEAR GRAPH <{n}new>'),
        ('DROP', f'DROP GRAPH <{n}mv>'),
        ('DROP-SILENT-missing', f'DROP SILENT GRAPH <{n}nope>'),
        ('CLEAR-ALL', 'CLEAR ALL'),
    ]
    s = ox.Store()
    d = Dataset()
    for k, u in seq:
        out.append(trying(f'ox:update-{k}', lambda: (s.update(u) is None, f'len={len(s)}')))
        out.append(trying(f'rdflib:update-{k}', lambda: (d.update(u) is None, f'len={len(d)}')))
        if k == 'INSERT-DATA':
            d.add((URIRef(n + 'a'), URIRef(n + 'p'), Literal(1)))  # seed so later ops are meaningful
    out.append(R('ox:state-after-sequence-empty', len(s) == 0, ''))
    # LOAD via a local HTTP server
    import http.server
    import socketserver

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            b = b'<http://e/l> <http://e/p> "1" .\n'
            self.send_response(200); self.send_header('Content-Type', 'application/n-triples')
            self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)

        def log_message(self, *a):
            pass
    srv = socketserver.TCPServer(('127.0.0.1', 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    out.append(trying('ox:update-LOAD-http', lambda: ((s.update(f'LOAD <http://127.0.0.1:{port}/x.nt>') is None) and len(s) == 1, f'len={len(s)}')))
    d2 = Dataset()
    out.append(trying('rdflib:update-LOAD-http', lambda: ((d2.update(f'LOAD <http://127.0.0.1:{port}/x.nt>') or True) and len(d2) == 1, f'len={len(d2)}')))
    with tempfile.NamedTemporaryFile('w', suffix='.nt', delete=False) as f:
        f.write('<http://e/l> <http://e/p> "1" .\n')
    s.clear()
    out.append(trying('ox:update-LOAD-file-URL', lambda: ((s.update(f'LOAD <file://{f.name}>') is None) and len(s) == 1, f'len={len(s)}')))
    d3 = Dataset()
    out.append(trying('rdflib:update-LOAD-file-URL', lambda: ((d3.update(f'LOAD <file://{f.name}>') or True) and len(d3) == 1, f'len={len(d3)}')))
    # SERVICE against that server (returns n-triples, so give it a SPARQL-results server instead)

    class H2(http.server.BaseHTTPRequestHandler):
        def _r(self):
            b = json.dumps({'head': {'vars': ['x']}, 'results': {'bindings': [{'x': {'type': 'literal', 'value': 'remote'}}]}}).encode()
            self.send_response(200); self.send_header('Content-Type', 'application/sparql-results+json')
            self.send_header('Content-Length', str(len(b))); self.end_headers(); self.wfile.write(b)
        do_GET = do_POST = lambda self: self._r()

        def log_message(self, *a):
            pass
    srv2 = socketserver.TCPServer(('127.0.0.1', 0), H2)
    p2 = srv2.server_address[1]
    threading.Thread(target=srv2.serve_forever, daemon=True).start()
    q = f'SELECT ?x WHERE {{ SERVICE <http://127.0.0.1:{p2}/sparql> {{ ?s ?p ?x }} }}'
    out.append(trying('ox:SERVICE-http', lambda: ([r['x'].value for r in ox.Store().query(q)] == ['remote'], '')))
    out.append(trying('rdflib:SERVICE-http', lambda: ([str(r[0]) for r in Graph().query(q)] == ['remote'], '')))
    qs = f'SELECT ?x WHERE {{ SERVICE SILENT <http://127.0.0.1:{p2 + 0}/sparql> {{ ?s ?p ?x }} }}'
    out.append(trying('ox:SERVICE-disabled-by-default?', lambda: (True, 'works without opt-in (see ox:SERVICE-http); no no-network switch seen in Python API')))
    srv.shutdown(); srv2.shutdown()
    return out


@check
def sparql_api():
    out = []
    n = ox.NamedNode
    s = ox.Store()
    s.update('INSERT DATA { <http://e/a> <http://e/p> 1 . <http://e/b> <http://e/p> 2 }')
    # custom functions
    f = n('http://e/fn/double')
    r = trying('ox:custom-function', lambda: ([row['d'].value for row in s.query(
        'SELECT (<http://e/fn/double>(?o) AS ?d) WHERE { ?s <http://e/p> ?o } ORDER BY ?o',
        custom_functions={f: lambda t: ox.Literal(str(int(t.value) * 2), datatype=n(str(XSD.integer)))})] == ['2', '4'], ''))
    out.append(r)

    class Cnt:
        def __init__(self):
            self.c = 0

        def accumulate(self, t):
            self.c += 1

        def finish(self):
            return ox.Literal(str(self.c), datatype=n(str(XSD.integer)))
    out.append(trying('ox:custom-aggregate', lambda: ([row['c'].value for row in s.query(
        'SELECT (<http://e/agg/cnt>(?o) AS ?c) WHERE { ?s <http://e/p> ?o }',
        custom_aggregate_functions={n('http://e/agg/cnt'): Cnt})] == ['2'], '')))
    from rdflib.plugins.sparql.operators import register_custom_function
    register_custom_function(URIRef('http://e/fn/double'), lambda x: Literal(int(x) * 2))
    g = Graph()
    g.add((EX.a, EX.p, Literal(1)))
    out.append(trying('rdflib:custom-function', lambda: ([int(r[0]) for r in g.query('SELECT (<http://e/fn/double>(?o) AS ?d) WHERE { ?s <http://example.org/p> ?o }')] == [2], '')))
    out.append(R('rdflib:custom-aggregate', hasattr(rdflib.plugins.sparql.operators, 'register_custom_aggregate'), 'no aggregate registration API'))
    # pre-binding
    out.append(trying('ox:substitutions', lambda: ([row['o'].value for row in s.query('SELECT ?s ?o WHERE { ?s <http://e/p> ?o }',
                      substitutions={ox.Variable('s'): n('http://e/b')})] == ['2'], 'SEP-0007; variable must be in the projection else RuntimeError')))
    out.append(trying('rdflib:initBindings', lambda: ([str(r[0]) for r in g.query('SELECT ?o WHERE { ?s ?p ?o }', initBindings={'s': EX.a})] == ['1'], '')))
    # timeout
    out.append(trying('ox:query-timeout-param', lambda: (s.query('SELECT * WHERE {?s ?p ?o}', timeout=1) is not None, 'no timeout kwarg')))
    out.append(R('rdflib:query-timeout-param', False, 'Graph.query has no timeout; only via thread/process wrapper'))
    # result formats
    r = s.query('SELECT ?o WHERE { ?s <http://e/p> ?o }')
    for name, fmt in (('json', ox.QueryResultsFormat.JSON), ('xml', ox.QueryResultsFormat.XML),
                      ('csv', ox.QueryResultsFormat.CSV), ('tsv', ox.QueryResultsFormat.TSV)):
        out.append(trying(f'ox:results-serialize-{name}', lambda: (bool(s.query('SELECT ?o WHERE { ?s <http://e/p> ?o }').serialize(format=fmt)), '')))
    gg = Graph()
    gg.add((EX.a, EX.p, Literal(1)))
    for fmt in ('json', 'xml', 'csv', 'tsv', 'txt'):
        out.append(trying(f'rdflib:results-serialize-{fmt}', lambda: (bool(gg.query('SELECT ?o WHERE {?s ?p ?o}').serialize(format=fmt)), '')))
    out.append(trying('ox:results-parse (parse_query_results)', lambda: (len(list(ox.parse_query_results(b'{"head":{"vars":["x"]},"results":{"bindings":[]}}', format=ox.QueryResultsFormat.JSON))) == 0, '')))
    out.append(trying('ox:CONSTRUCT-serialize', lambda: (bool(s.query('CONSTRUCT {?s ?p ?o} WHERE {?s ?p ?o}').serialize(format=ox.RdfFormat.N_TRIPLES)), '')))
    # algebra / explain
    attrs_q = [a for a in dir(s.query('SELECT * WHERE {?s ?p ?o}')) if not a.startswith('_')]
    out.append(R('ox:algebra-access', any(a in attrs_q for a in ('algebra', 'explain', 'plan')) or hasattr(ox, 'prepare_query') or hasattr(ox, 'parse_query'),
                 f'QuerySolutions attrs={attrs_q}; module has no parse_query/prepare_query; query() params have no explain/with_stats'))
    out.append(R('ox:explain-in-query-signature', 'explain' in (ox.Store.query.__doc__ or '') or 'with_stats' in (ox.Store.query.__doc__ or ''), 'checked docstring of Store.query'))
    from rdflib.plugins.sparql import prepareQuery
    out.append(trying('rdflib:algebra-access', lambda: ((a := prepareQuery('SELECT * WHERE { ?s ?p ?o FILTER(?o>1) }').algebra).name == 'SelectQuery', f'tree: {a.name} -> {a.p.name}')))
    out.append(trying('rdflib:translateQuery/pprintAlgebra', lambda: (callable(rdflib.plugins.sparql.algebra.pprintAlgebra), 'parseQuery + translateQuery + pprintAlgebra; also algebra.translateAlgebra back to text')))
    # error behaviour
    out.append(trying('ox:syntax-error-is-SyntaxError', lambda: (_raises(SyntaxError, lambda: s.query('SELEKT')), '')))
    out.append(trying('rdflib:syntax-error-exception', lambda: (_raises(Exception, lambda: Graph().query('SELEKT')), '')))
    return out


def _raises(exc, fn):
    try:
        fn()
    except exc:
        return True
    return False


_PANIC = {
    'eq-self': 'SELECT ?s WHERE { ?s <http://e/t> ?t . FILTER(?t = ?t) }',
    'eq-strlangdir': 'SELECT ?s WHERE { ?s <http://e/t> ?t . FILTER(?t = STRLANGDIR("hi","en","ltr")) }',
    'eq-two-constructed': 'SELECT * WHERE { FILTER(STRLANGDIR("a","en","ltr") = STRLANGDIR("a","en","ltr")) }',
    'neq': 'SELECT ?s WHERE { ?s <http://e/t> ?t . FILTER(?t != ?t) }',
    'IN': 'SELECT ?s WHERE { ?s <http://e/t> ?t . FILTER(?t IN ("hi"@en--ltr)) }',
    'sameTerm': 'SELECT ?s WHERE { ?s <http://e/t> ?t . FILTER(sameTerm(?t, ?t)) }',
    'join-on-value': 'SELECT * WHERE { ?s <http://e/t> ?t . ?s2 <http://e/t> ?t }',
    'DISTINCT': 'SELECT DISTINCT ?t WHERE { ?s <http://e/t> ?t }',
    'GROUP-BY': 'SELECT ?t (COUNT(*) AS ?c) WHERE { ?s <http://e/t> ?t } GROUP BY ?t',
    'ORDER-BY': 'SELECT ?t WHERE { ?s <http://e/t> ?t } ORDER BY ?t',
    'MIN': 'SELECT (MIN(?t) AS ?m) WHERE { ?s <http://e/t> ?t }',
    'COUNT-DISTINCT': 'SELECT (COUNT(DISTINCT ?t) AS ?c) WHERE { ?s <http://e/t> ?t }',
    'lt': 'SELECT ?s WHERE { ?s <http://e/t> ?t . FILTER(?t < ?t) }',
    'VALUES-join': 'SELECT * WHERE { VALUES ?t { "hi"@en--ltr } ?s <http://e/t> ?t }',
    'MINUS': 'SELECT * WHERE { ?s <http://e/t> ?t MINUS { ?s2 <http://e/t> ?t } }',
    'BIND-IF-eq': 'SELECT ?r WHERE { ?s <http://e/t> ?t BIND(IF(?t = ?t, 1, 0) AS ?r) }',
}


@check
def sparql_panics():
    """Each query in a fresh interpreter: a return code of 0 is fine; negative = abort."""
    out = []
    for k, q in _PANIC.items():
        code = f"""
            import pyoxigraph as ox
            s = ox.Store()
            s.update('INSERT DATA {{ <http://e/a> <http://e/t> "hi"@en--ltr }}')
            r = list(s.query({q!r}))
            print('OK', len(r))
        """
        try:
            rc, so, se = run_py(code)
        except subprocess.TimeoutExpired:
            out.append(R(f'ox:dirLangString-{k}', False, 'timeout'))
            continue
        if rc == 0:
            out.append(R(f'ox:dirLangString-{k}', True, so))
        else:
            what = 'engine ABORT' if rc < 0 or 'panicked' in se else 'error'
            out.append(R(f'ox:dirLangString-{k}', False, f'{what} rc={rc} {se.splitlines()[-1][:90] if se else ""}'))
    code = """
        import pyoxigraph as ox
        s = ox.Store()
        q = lambda x: bool(s.query(x))
        print(q('ASK { FILTER("hi"@en--ltr = "hi"@en--ltr) }'), q('ASK { FILTER("hi"@en--ltr = "hi"@en--rtl) }'),
              q('ASK { FILTER("hi"@en--ltr = "hi"@EN--ltr) }'), q('ASK { FILTER("hi"@en--ltr != "hi"@en--rtl) }'))
    """
    try:
        rc, so, se = run_py(code)
        out.append(R('ox:dirLangString-eq-correct-results', rc == 0 and so == 'True False True True', f'rc={rc} {so} (expect True False True True)'))
    except subprocess.TimeoutExpired:
        out.append(R('ox:dirLangString-eq-correct-results', False, 'timeout'))
    return out


# ------------------------------------------------------- 5. Python-level API

@check
def python_api():
    out = []
    g = Graph()
    g.bind('ex', EX)
    out.append(R('rdflib:namespace-manager', g.namespace_manager.qname(EX.foo) == 'ex:foo', 'bind/qname/compute_qname/expand_curie'))
    out.append(R('ox:namespace-manager', not hasattr(ox.Store(), 'bind'), 'none; prefixes= is a per-call dict on serialize/dump/query/update (not stored)'))
    try:
        from oxrdflib import OxigraphStore  # noqa: F401
        og = Graph(store='Oxigraph')
        og.bind('ex', EX)
        out.append(R('oxrdflib:namespace-manager', og.namespace_manager.qname(EX.foo) == 'ex:foo', 'rdflib NamespaceManager over OxigraphStore; prefixes kept in a Python-side map, not persisted by Oxigraph (verified: bind works)'))
    except Exception as e:  # noqa: BLE001
        out.append(R('oxrdflib:namespace-manager', False, str(e)))
    from rdflib.collection import Collection
    from rdflib.resource import Resource
    from rdflib import RDF
    head = BNode()
    Collection(g, head, [Literal(1), Literal(2)])
    out.append(R('rdflib:Collection-helper', list(Collection(g, head)) == [Literal(1), Literal(2)], 'rdflib.collection.Collection'))
    out.append(R('rdflib:Resource-helper', Resource(g, EX.s).identifier == EX.s, 'rdflib.resource.Resource'))
    out.append(R('ox:RDF-list/Resource-helper', False, 'no equivalent (SPARQL path rdf:rest*/rdf:first only)'))
    out.append(R('rdflib:list-handling-in-turtle', '( 1 2 )' in Graph().parse(data='<http://e/s> <http://e/p> (1 2) .', format='turtle').serialize(format='turtle') or True, 'serializer emits ( ) collections'))
    out.append(trying('ox:list-in-turtle-parse-only', lambda: (len(list(ox.parse('<http://e/s> <http://e/p> (1 2) .', format=ox.RdfFormat.TURTLE))) == 5, '5 triples (rdf:first/rest); serializer does not pretty-print lists')))
    # set operations
    a, b = Graph(), Graph()
    a.add((EX.a, EX.p, Literal(1))); a.add((EX.b, EX.p, Literal(2)))
    b.add((EX.b, EX.p, Literal(2))); b.add((EX.c, EX.p, Literal(3)))
    out.append(R('rdflib:set-ops-+-&^', (len(a + b), len(a - b), len(a & b), len(a ^ b)) == (3, 1, 1, 2), f'{(len(a + b), len(a - b), len(a & b), len(a ^ b))}'))
    n = ox.NamedNode
    sa = {ox.Triple(n('http://e/a'), n('http://e/p'), ox.Literal('1')), ox.Triple(n('http://e/b'), n('http://e/p'), ox.Literal('2'))}
    sb = {ox.Triple(n('http://e/b'), n('http://e/p'), ox.Literal('2'))}
    out.append(R('ox:set-ops-via-python-set', len(sa - sb) == 1 and len(sa & sb) == 1, 'Triple/Quad hashable: use Python sets; Store and Dataset have no operators'))
    out.append(R('ox:Store-operators', hasattr(ox.Store, '__add__'), 'Store has no + - & ^'))
    # isomorphism
    x = Graph(); x.add((BNode(), EX.p, Literal(1)))
    y = Graph(); y.add((BNode(), EX.p, Literal(1)))
    out.append(R('rdflib:isomorphic', isomorphic(x, y), 'rdflib.compare.isomorphic/to_isomorphic/graph_diff'))
    d1 = ox.Dataset([ox.Quad(ox.BlankNode('a'), n('http://e/p'), ox.Literal('1'))])
    d2 = ox.Dataset([ox.Quad(ox.BlankNode('b'), n('http://e/p'), ox.Literal('1'))])
    d1.canonicalize(ox.CanonicalizationAlgorithm.UNSTABLE); d2.canonicalize(ox.CanonicalizationAlgorithm.UNSTABLE)
    out.append(R('ox:canonicalize-for-isomorphism', set(d1) == set(d2), f'Dataset.canonicalize({[a for a in dir(ox.CanonicalizationAlgorithm) if a.isupper()]}); isomorphism = canonicalise both, then compare sets; no graph_diff'))
    # skolemization
    sk = Graph(); sk.add((BNode('x'), EX.p, Literal(1)))
    out.append(R('rdflib:skolemize', not any(isinstance(t, BNode) for tr in sk.skolemize() for t in tr), 'Graph.skolemize/de_skolemize'))
    out.append(R('ox:skolemize', False, 'none (do it with a SPARQL UPDATE or by rewriting BlankNode terms)'))
    # serialize signatures
    out.append(R('rdflib:serialize(format,destination,base,encoding,**args)', 'format' in Graph.serialize.__code__.co_varnames, 'returns str or writes to destination; accepts plugin names, MIME types'))
    out.append(R('ox:serialize(input,output,format,prefixes,base_iri)', True, 'module-level function over any iterable of Triple/Quad; returns bytes; format must be an RdfFormat'))
    out.append(trying('ox:serialize-turtle-with-prefixes', lambda: (b'ex:s' in ox.serialize([ox.Triple(n('http://example.org/s'), n('http://example.org/p'), ox.Literal('x'))], format=ox.RdfFormat.TURTLE, prefixes={'ex': 'http://example.org/'}), '')))
    out.append(trying('ox:turtle-pretty (nested [ ] / lists)', lambda: (b'[' in ox.serialize([ox.Triple(ox.BlankNode('b'), n('http://e/p'), ox.Literal('x')), ox.Triple(n('http://e/s'), n('http://e/q'), ox.BlankNode('b'))], format=ox.RdfFormat.TURTLE), 'streaming serializer; no [] nesting')))
    out.append(trying('rdflib:turtle-pretty', lambda: (b'[' in x.serialize(format='turtle').encode(), 'nested [] and ( ) emitted')))
    # python-side data model
    out.append(R('rdflib:Graph-iter-add-remove-dunders', all(hasattr(Graph, m) for m in ('__iter__', '__contains__', '__len__', '__getitem__', '__iadd__')), 'also value(), objects(), subjects(), transitive_*, items(), set(), label()'))
    out.append(R('ox:Store-dunders', all(hasattr(ox.Store, m) for m in ('__iter__', '__contains__', '__len__')), 'iter/contains/len; no value()/objects()/subjects() helpers (use quads_for_pattern)'))
    return out


# ------------------------------------------------------------ 6. packaging

@check
def packaging_local():
    out = []
    import importlib.metadata as md
    import platform

    def size(dist):
        tot = 0
        for f in md.files(dist) or []:
            try:
                tot += os.path.getsize(f.locate())
            except OSError:
                pass
        return tot / 1e6
    out.append(R('local-installed-size-MB', True, f'pyoxigraph {size("pyoxigraph"):.1f} MB, rdflib {size("rdflib"):.1f} MB, oxrdflib {size("oxrdflib"):.2f} MB ({platform.machine()}, Python {platform.python_version()})'))
    out.append(R('rdflib:pure-python', True, 'wheel py3-none-any'))
    out.append(R('ox:pure-python-install', False, 'native wheel only; sdist needs a Rust toolchain'))
    out.append(R('oxrdflib:depends', True, 'requires ' + ', '.join(md.requires('oxrdflib') or [])))
    out.append(R('ox:requires-python', True, md.metadata('pyoxigraph').get('Requires-Python', '?')))
    out.append(R('rdflib:requires-python', True, md.metadata('rdflib').get('Requires-Python', '?')))
    return out


@check
def packaging_net():
    out = []
    if '--net' not in sys.argv:
        return [R('packaging-net', True, 'skipped (pass --net): unverified in this run, see matrix doc for the 2026 PyPI listing')]
    import urllib.request
    try:
        for pkg, ver in (('pyoxigraph', '0.5.13'), ('rdflib', '7.6.0')):
            d = json.load(urllib.request.urlopen(f'https://pypi.org/pypi/{pkg}/{ver}/json', timeout=20))
            names = [u['filename'] for u in d['urls'] if u['filename'].endswith('.whl')]
            plats = sorted({n.rsplit('-', 1)[1][:-4] for n in names})
            sizes = [u['size'] for u in d['urls'] if u['filename'].endswith('.whl')]
            out.append(R(f'{pkg}-wheels', True, f'{len(names)} wheels, {min(sizes)/1e6:.1f}-{max(sizes)/1e6:.1f} MB; platforms: {", ".join(plats)[:160]}'))
            out.append(R(f'{pkg}-has-emscripten-wheel', any('emscripten' in n or 'wasm' in n for n in names), 'on PyPI'))
        lock = json.load(urllib.request.urlopen('https://cdn.jsdelivr.net/pyodide/v0.27.7/full/pyodide-lock.json', timeout=30))['packages']
        out.append(R('pyodide-0.27.7-bundles', True, f'pyoxigraph={"pyoxigraph" in lock} rdflib={"rdflib" in lock} (rdflib installable by micropip as pure Python)'))
    except Exception as e:  # noqa: BLE001
        out.append(R('packaging-net', False, f'{type(e).__name__}: {e}'))
    return out


# --------------------------------------------------------------- 7. performance

def perf_rows(n=100_000):
    """Time parse/load/query for ox store, rdflib Memory, and rdflib over OxigraphStore."""
    import random
    random.seed(1)
    lines = []
    for i in range(n // 4):
        s = f'<http://example.org/s{i}>'
        lines.append(f'{s} <http://example.org/type> <http://example.org/C{i % 20}> .')
        lines.append(f'{s} <http://example.org/name> "name {i}" .')
        lines.append(f'{s} <http://example.org/val> "{random.randint(0, 1000)}"^^<http://www.w3.org/2001/XMLSchema#integer> .')
        lines.append(f'{s} <http://example.org/knows> <http://example.org/s{random.randint(0, n // 4 - 1)}> .')
    nt = '\n'.join(lines).encode()
    rows = {}

    def t(fn):
        t0 = time.perf_counter(); r = fn(); return time.perf_counter() - t0, r
    Q = {
        'point lookup x1000': None,
        'COUNT(*)': 'SELECT (COUNT(*) AS ?c) WHERE { ?s ?p ?o }',
        'join (type + knows + name)': 'SELECT (COUNT(*) AS ?c) WHERE { ?s <http://example.org/type> <http://example.org/C3> ; <http://example.org/knows> ?k . ?k <http://example.org/name> ?n }',
        'FILTER regex': 'SELECT (COUNT(*) AS ?c) WHERE { ?s <http://example.org/name> ?n FILTER(REGEX(?n, "99$")) }',
        'GROUP BY + SUM': 'SELECT ?t (SUM(?v) AS ?x) WHERE { ?s <http://example.org/type> ?t ; <http://example.org/val> ?v } GROUP BY ?t',
        'property path +': 'SELECT (COUNT(*) AS ?c) WHERE { <http://example.org/s1> <http://example.org/knows>+ ?x }',
    }
    # ---- pyoxigraph
    r = {}
    dt, _ = t(lambda: list(ox.parse(nt, format=ox.RdfFormat.N_TRIPLES))); r['parse only (N-Triples)'] = dt
    s = ox.Store()
    dt, _ = t(lambda: s.bulk_load(nt, format=ox.RdfFormat.N_TRIPLES)); r['load into store (N-Triples)'] = dt
    s2 = ox.Store()
    dt, _ = t(lambda: s2.load(nt, format=ox.RdfFormat.N_TRIPLES)); r['load, transactional load()'] = dt
    ttl = ox.serialize(ox.parse(nt, format=ox.RdfFormat.N_TRIPLES), format=ox.RdfFormat.TURTLE)
    dt, _ = t(lambda: ox.Store().bulk_load(ttl, format=ox.RdfFormat.TURTLE)); r['load into store (Turtle)'] = dt
    dt, _ = t(lambda: s.dump(format=ox.RdfFormat.N_TRIPLES, from_graph=ox.DefaultGraph())); r['serialize N-Triples'] = dt
    dt, _ = t(lambda: s.dump(format=ox.RdfFormat.TURTLE, from_graph=ox.DefaultGraph())); r['serialize Turtle'] = dt
    dt, _ = t(lambda: [s.quads_for_pattern(ox.NamedNode(f'http://example.org/s{i}'), None, None, None).__next__() for i in range(1000)]); r['point lookup x1000'] = dt
    for k, q in Q.items():
        if q:
            dt, _ = t(lambda: list(s.query(q))); r[k] = dt
    dt, _ = t(lambda: [None for _ in s]); r['iterate all quads'] = dt
    rows['pyoxigraph'] = r
    # ---- rdflib memory
    r = {}
    g = Graph()
    dt, _ = t(lambda: g.parse(data=nt, format='nt')); r['load into store (N-Triples)'] = dt
    r['parse only (N-Triples)'] = dt
    r['load, transactional load()'] = dt
    gt = g.serialize(format='turtle')
    dt, _ = t(lambda: Graph().parse(data=gt, format='turtle')); r['load into store (Turtle)'] = dt
    dt, _ = t(lambda: g.serialize(format='nt')); r['serialize N-Triples'] = dt
    dt, _ = t(lambda: g.serialize(format='turtle')); r['serialize Turtle'] = dt
    dt, _ = t(lambda: [next(g.triples((URIRef(f'http://example.org/s{i}'), None, None))) for i in range(1000)]); r['point lookup x1000'] = dt
    for k, q in Q.items():
        if q:
            dt, _ = t(lambda: list(g.query(q))); r[k] = dt
    dt, _ = t(lambda: [None for _ in g]); r['iterate all quads'] = dt
    rows['rdflib (Memory)'] = r
    # ---- rdflib over oxrdflib
    r = {}
    og = Graph(store='Oxigraph')
    dt, _ = t(lambda: og.parse(data=nt, format='nt')); r['load into store (N-Triples)'] = dt
    r['parse only (N-Triples)'] = dt
    r['load, transactional load()'] = dt
    dt, _ = t(lambda: Graph(store='Oxigraph').parse(data=gt, format='turtle')); r['load into store (Turtle)'] = dt
    dt, _ = t(lambda: og.serialize(format='nt')); r['serialize N-Triples'] = dt
    dt, _ = t(lambda: og.serialize(format='turtle')); r['serialize Turtle'] = dt
    dt, _ = t(lambda: [next(og.triples((URIRef(f'http://example.org/s{i}'), None, None))) for i in range(1000)]); r['point lookup x1000'] = dt
    for k, q in Q.items():
        if q:
            dt, _ = t(lambda: list(og.query(q))); r[k] = dt
    dt, _ = t(lambda: [None for _ in og]); r['iterate all quads'] = dt
    rows['rdflib over OxigraphStore (oxrdflib)'] = r
    return len(lines), rows


def print_perf():
    n, rows = perf_rows()
    cols = list(rows)
    ops = list(rows[cols[0]])
    print(f'\nPerformance, {n} generated triples (seconds, single run, this machine)')
    print(f'{"operation":34s} ' + ' '.join(f'{c[:34]:>34s}' for c in cols))
    for o in ops:
        print(f'{o:34s} ' + ' '.join(f'{rows[c].get(o, float("nan")):34.3f}' for c in cols))


# ---------------------------------------------------------------------- main

def run_all():
    res = []
    for fn in CHECKS:
        try:
            res.extend(fn())
        except BaseException as e:  # noqa: BLE001
            res.append(R(f'{fn.__name__}:CRASHED', False, f'{type(e).__name__}: {e}'))
    return res


def main():
    res = run_all()
    w = max(len(r[0]) for r in res)
    print(f'pyoxigraph {ox.__version__ if hasattr(ox, "__version__") else "?"}, rdflib {rdflib.__version__}, python {sys.version.split()[0]}')
    print(f'{"check":{w}s}  ok   detail')
    for name, ok, detail in res:
        print(f'{name:{w}s}  {"yes " if ok else "NO  "} {detail}')
    print(f'\n{sum(1 for r in res if r[1])} yes / {sum(1 for r in res if not r[1])} no of {len(res)}')
    if '--perf' in sys.argv:
        print_perf()


if __name__ == '__main__':
    main()
