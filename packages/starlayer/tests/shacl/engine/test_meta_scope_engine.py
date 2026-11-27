"""The engine-level scoped meta check: ``engine.meta.meta_validate(add=, remove=, nodes=, with_dependents=)`` and ``meta_scope`` (both
internal; the public ``starlayer.shacl.meta_validate`` has only ``add``, ``remove`` and ``full``, tested in ``test_meta_scope.py``
in ``tests/shacl/integration``). An edit that other nodes inherit from goes through the full check."""

import time

import pyoxigraph as ox
import pytest
from starlayer.errors import ShapeError
from starlayer.graph import StarLayerGraph as Graph
from starlayer.shacl.engine.meta import meta_scope
from starlayer.shacl.engine.meta import meta_validate as engine_meta_validate
from starlayer.shacl.engine.meta_scope import MetaScope
from starlayer.shacl.engine.terms import RDF, SH, to_engine

SHNS = str(SH)
EX = "http://example.org/"
XSD = "http://www.w3.org/2001/XMLSchema#"
PREFIX = (f"@prefix sh: <{SHNS}> . @prefix ex: <{EX}> . @prefix xsd: <{XSD}> . "
          "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n")


def meta_validate(g, **kwargs):
    """The engine function with the public function's contract: raises on a defect, returns (conforms, report_graph, report_text)."""
    result = engine_meta_validate(g, **kwargs)
    result.raise_if_invalid()
    return result.conforms, result.report_graph, result.report_text


def iri(name):
    return ox.NamedNode(EX + name)


def graph(ttl: str) -> Graph:
    g = Graph()
    g.parse(data=PREFIX + ttl, format="turtle")
    return g


def lit(text, datatype=None):
    return ox.Literal(text, datatype=ox.NamedNode(datatype)) if datatype else ox.Literal(text)


def generated(n: int, extra: str = "") -> Graph:
    lines = [
        f"ex:S{i} a sh:NodeShape ; sh:targetClass ex:T{i} ; sh:property "
        "[ sh:path ex:a ; sh:datatype xsd:string ; sh:minCount 1 ] , [ sh:path ex:b ; sh:datatype xsd:integer ; sh:maxCount 2 ] , "
        "[ sh:path ex:c ; sh:nodeKind sh:IRI ] ."
        for i in range(n)
    ]
    return graph("\n".join(lines) + extra)


# a graph with every kind of thing the check reads across nodes, and one defect of each of eight kinds
MIXED = """
ex:Prefixes a owl:Ontology ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
ex:Comp a sh:ConstraintComponent ; sh:parameter [ sh:path ex:minLen ; sh:datatype xsd:integer ] ;
  sh:validator [ a sh:SPARQLAskValidator ; sh:ask "ASK { }" ] .
ex:Tmpl a sh:SPARQLRuleTemplate ; sh:construct "CONSTRUCT { } WHERE { }" ; sh:parameter [ sh:path ex:p ] .
ex:Query a sh:NodeShape ; sh:targetClass ex:Q ; sh:sparql [ sh:select "SELECT $this WHERE { $this a ex:Q }" ; sh:prefixes ex:Prefixes ] .
ex:UsesComp a sh:NodeShape ; sh:targetClass ex:U ; ex:minLen 3 .
ex:Dup a sh:NodeShape ; sh:targetClass ex:Dup ; sh:property [ sh:path ex:a ; sh:datatype xsd:string , xsd:integer ] .
ex:Many a sh:NodeShape ; sh:targetClass ex:Many ; sh:property [ sh:path ex:a ; sh:minCount "many" ] .
ex:BadPattern a sh:NodeShape ; sh:targetClass ex:BP ; sh:property [ sh:path ex:a ; sh:pattern "[unclosed" ] .
ex:BadLang a sh:NodeShape ; sh:targetClass ex:BL ; sh:property [ sh:path ex:a ; sh:languageIn ( "en" 5 ) ] .
ex:BadSelect a sh:NodeShape ; sh:targetClass ex:BS ; sh:sparql [ sh:select "SELEKT nothing" ; sh:prefixes ex:Prefixes ] .
ex:Unknown a sh:NodeShape ; sh:targetClass ex:UN ; sh:nonsenseTerm 1 .
ex:BadParam a sh:NodeShape ; sh:targetClass ex:BP2 ; ex:minLen "abc" .
ex:NoPath a sh:NodeShape ; sh:targetClass ex:NP ; sh:property [ sh:minCount 1 ] .
ex:Ref a sh:NodeShape ; sh:targetClass ex:R ; sh:node ex:Referenced .
ex:Referenced a sh:NodeShape ; sh:property [ sh:path ex:a ; sh:minCount 1 ] .
"""


def mixed() -> Graph:
    return generated(30, MIXED)


def identities(report) -> set:
    """What a result is, independent of the blank nodes' labels: focus, path, component, source shape, severity, value."""
    from starlayer.shacl import report_results

    out = set()
    for r in report_results(report):
        out.add(tuple(None if x is None else _stable(x) for x in (r.focus, r.path, r.component, r.source_shape, r.severity, r.value)))
    return out


def _stable(term):
    return "_:" if isinstance(term, ox.BlankNode) else term


def problem_report(g, **kwargs):
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta") as raised:
        meta_validate(g, **kwargs)
    return raised.value


def all_terms(g):
    seen = {}
    for s, _p, o in g.triples((None, None, None)):
        seen.setdefault(s, None)
        seen.setdefault(o, None)
    return list(seen)


# (1) equivalence

def test_the_union_of_one_node_checks_is_the_full_check():
    """Exact, by identity. A scoped check covers a node and the blank nodes it is described through, so a result on a property shape
    can be reported by two single-node checks (the shape's and its own); the set of results is still the full check's."""
    g = mixed()
    full = engine_meta_validate(g)
    assert len(full.problems) >= 8
    union = set()
    for node in all_terms(g):  # every node of the graph, literals included
        result = engine_meta_validate(g, nodes=[node], with_dependents=False)  # meta_validate raises on violations only
        union |= identities(result.report_graph)
        assert not result.scope.full and node in result.scope.nodes
    assert union == identities(full.report_graph)
    assert len(union) >= 8


def test_each_defect_kind_is_found_by_the_check_of_its_own_node_without_dependents():
    g = mixed()
    for name in ("Dup", "Many", "BadPattern", "BadLang", "NoPath", "BadSelect", "Unknown", "BadParam"):
        result = engine_meta_validate(g, nodes=[iri(name)], with_dependents=False)
        assert result.problems, name
    assert not engine_meta_validate(g, nodes=[iri("Query")], with_dependents=False).problems


# (2) speed

def test_a_scoped_check_of_one_node_of_2000_shapes_is_fast_and_the_full_check_is_unchanged():
    g = generated(2000)
    node = iri("S1000")
    meta_validate(g, nodes=[node])  # warm: plan and class caches
    best = min(_time(lambda: meta_validate(g, nodes=[node])) for _ in range(3))
    assert best < 0.100, best
    # the same check of a proposed edit includes copying the graph: slower, never a full check
    add = [(node, to_engine(ox.NamedNode(SHNS + "name")), lit("x"))]
    edit = min(_time(lambda: meta_validate(g, add=add)) for _ in range(3))
    assert edit < 0.200, edit
    # the full check is what it was: it still reports the defects, and on all nodes
    assert meta_validate(generated(30))[0] is True


def _time(call):
    start = time.perf_counter()
    call()
    return time.perf_counter() - start


def test_meta_scope_does_no_validation_and_is_fast():
    g = generated(2000)
    node = iri("S1000")
    add = [(node, to_engine(ox.NamedNode(SHNS + "name")), lit("x"))]
    best = min(_time(lambda: meta_scope(g, add=add)) for _ in range(3))
    assert best < 0.020, best


# (3) risk

def _t(s, p, o):
    return (ox.NamedNode(EX + s), ox.NamedNode(p if p.startswith("http") else EX + p), o)


RISKY_EDITS = {
    "sh:declare": (_t("Prefixes", SHNS + "declare", iri("Other")), "sh:declare"),
    "sh:prefix": (_t("P", SHNS + "prefix", lit("x")), "sh:prefix"),
    "sh:namespace": (_t("P", SHNS + "namespace", lit("http://x/", XSD + "anyURI")), "sh:namespace"),
    "sh:prefixes": (_t("Query", SHNS + "prefixes", iri("Prefixes")), "sh:prefixes"),
    "owl:imports": (_t("Prefixes", "http://www.w3.org/2002/07/owl#imports", iri("Other")), "owl:imports"),
    "owl:versionIRI": (_t("Prefixes", "http://www.w3.org/2002/07/owl#versionIRI", iri("V1")), "owl:versionIRI"),
    "sh:parameter": (_t("Comp", SHNS + "parameter", iri("Param")), "sh:parameter"),
    "sh:validator": (_t("Comp", SHNS + "validator", iri("Val")), "sh:validator"),
    "sh:nodeValidator": (_t("Comp", SHNS + "nodeValidator", iri("Val")), "sh:nodeValidator"),
    "sh:propertyValidator": (_t("Comp", SHNS + "propertyValidator", iri("Val")), "sh:propertyValidator"),
    "rdf:type": (_t("S1", RDF.type.value, iri("Whatever")), "rdf:type"),
    "rdf:type of a component": (_t("New", RDF.type.value, SH.ConstraintComponent), "rdf:type"),
    "rdf:type of a template": (_t("New", RDF.type.value, to_engine(SH.SPARQLRuleTemplate)), "rdf:type"),
    "rdf:type of a parameter": (_t("New", RDF.type.value, to_engine(SH.Parameter)), "rdf:type"),
    "rdf:type of a shapes graph": (_t("New", RDF.type.value, to_engine(SH.ShapesGraph)), "rdf:type"),
    "rdfs:subClassOf on a template": (_t("Tmpl", "http://www.w3.org/2000/01/rdf-schema#subClassOf", to_engine(SH.Rule)), "rdfs:subClassOf"),
    "sh:entailment": (_t("S1", SHNS + "entailment", iri("Regime")), "sh:entailment"),
    "sh:shapesGraph": (_t("S1", SHNS + "shapesGraph", iri("G")), "sh:shapesGraph"),
    # by what the subject is, whatever the predicate
    "a parameter's own property": (_t("Comp", "ignored", lit("1")), None),
}


@pytest.mark.parametrize("name", [n for n in RISKY_EDITS if n != "a parameter's own property"])
def test_each_risky_class_forces_the_full_check_and_names_the_triple(name):
    triple, predicate = RISKY_EDITS[name]
    scope = meta_scope(mixed(), add=[triple])
    assert scope.full and scope.nodes == ()
    assert any(predicate in reason for reason in scope.reasons), scope.reasons
    assert scope.reasons[0].startswith("full check: ")
    # a removed triple is judged by the triple itself
    assert meta_scope(mixed(), remove=[triple]).full


def test_a_change_on_a_component_a_parameter_a_prefix_holder_or_a_template_is_risky_whatever_the_predicate():
    g = mixed()
    name = ox.NamedNode(SHNS + "name")
    holders = [iri("Comp"), iri("Prefixes"), iri("Tmpl")]
    parameter = next(iter(g.objects(iri("Comp"), to_engine(SH.parameter))))
    validator = next(iter(g.objects(iri("Comp"), to_engine(SH.validator))))
    for holder in [*holders, parameter, validator]:
        scope = meta_scope(g, add=[(holder, name, lit("x"))])
        assert scope.full, holder
    prefix_entry = next(iter(g.objects(iri("Prefixes"), to_engine(SH.declare))))
    assert meta_scope(g, add=[(prefix_entry, name, lit("x"))]).full


def test_a_local_change_is_scoped_to_its_node_and_its_dependents():
    g = mixed()
    prop = next(iter(g.objects(iri("Referenced"), to_engine(SH.property))))
    min_count = to_engine(SH.minCount)
    scope = meta_scope(g, remove=[(prop, min_count, lit("1", XSD + "integer"))], add=[(prop, min_count, lit("2", XSD + "integer"))])
    assert isinstance(scope, MetaScope) and not scope.full
    assert scope.nodes == (prop, iri("Referenced")), scope.nodes  # one step: the shape that holds it, not the one that refers to that
    assert scope.reasons == ("checked 2 nodes: 1 changed, 1 dependent",), scope.reasons
    name = meta_scope(g, add=[(iri("S3"), to_engine(SH.name), lit("three"))])
    assert name.nodes[0] == iri("S3") and name.reasons == ("checked 4 nodes: 1 changed, 3 inline",)


def test_a_new_property_link_types_its_object_and_covers_both():
    g = generated(3)
    fresh = ox.BlankNode()
    scope = meta_scope(g, add=[(iri("S1"), to_engine(SH.property), fresh)])
    assert {iri("S1"), fresh} <= set(scope.nodes)
    assert scope.reasons == ("checked 5 nodes: 2 changed, 3 inline",)  # S1's three property shapes are part of it


def test_a_prefix_edit_needs_the_full_check_to_find_the_query_in_another_node():
    g = graph("""
ex:Prefixes a owl:Ontology ; sh:declare [ sh:prefix "ex" ; sh:namespace "http://example.org/"^^xsd:anyURI ] .
ex:Query a sh:NodeShape ; sh:targetClass ex:Q ; sh:sparql [ sh:select "SELECT $this WHERE { $this a ex:Q }" ; sh:prefixes ex:Prefixes ] .
""")
    assert meta_validate(g)[0]
    entry = next(iter(g.objects(iri("Prefixes"), to_engine(SH.declare))))
    prefix = to_engine(SH.prefix)
    edit = {"remove": [(entry, prefix, lit("ex"))], "add": [(entry, prefix, lit("other"))]}
    # the narrow check of the edited node alone does not see the query break
    narrow = meta_validate(g, nodes=[entry], with_dependents=False)
    assert narrow[0]
    # the edit as proposed is risky, so it is checked in full and finds the query in the other node
    scope = meta_scope(g, **edit)
    assert scope.full and "sh:prefix" in scope.reasons[0]
    error = problem_report(g, **edit)
    assert error.scope.full
    assert any("Query" in line or "ex:Query" in line for line in error.problems), error.problems
    # and the graph was not changed by any of it
    assert meta_validate(g)[0]


# (4) dependents

def test_editing_a_referenced_shape_rechecks_the_referrer_and_without_dependents_it_does_not():
    g = graph("""
ex:Ref a sh:NodeShape ; sh:targetClass ex:R ; sh:node ex:Referenced .
ex:Referenced a sh:NodeShape .
ex:Both a sh:NodeShape ; sh:and ( ex:Referenced ex:Referenced ) .
ex:Unrelated a sh:NodeShape .
""")
    edit = {"add": [(iri("Referenced"), to_engine(SH.name), lit("n"))]}
    with_deps = meta_scope(g, **edit)
    assert set(with_deps.nodes) == {iri("Referenced"), iri("Ref"), iri("Both")}
    assert with_deps.reasons == ("checked 3 nodes: 1 changed, 2 dependents",)
    without = meta_scope(g, with_dependents=False, **edit)
    assert without.nodes == (iri("Referenced"),)


def test_a_result_is_reported_on_the_focus_node_the_engine_gives_it_and_only_when_that_node_is_covered():
    g = mixed()
    prop = next(iter(g.objects(iri("Many"), to_engine(SH.property))))
    own = engine_meta_validate(g, nodes=[prop], with_dependents=False)
    assert own.problems and all("ex:Many" in line for line in own.problems)  # the property shape's own results, focus the blank node
    via_owner = engine_meta_validate(g, nodes=[iri("Many")], with_dependents=False)  # the owner covers its property shapes
    assert identities(own.report_graph) == identities(via_owner.report_graph)
    elsewhere = engine_meta_validate(g, nodes=[iri("S1")], with_dependents=False)  # visible to the check, but not covered
    assert not elsewhere.problems
    # the same property shape seen only through a referrer: the referrer's results are its own, the property shape's are not added
    referrer = engine_meta_validate(g, nodes=[iri("Ref")], with_dependents=False)
    assert not referrer.problems


# (5) nodes and edits that are not in the graph, no scope, refusals

def test_a_term_that_is_not_in_the_graph_has_nothing_to_check():
    g = generated(3)
    assert meta_validate(g, nodes=[iri("Nowhere")])[0]
    assert meta_scope(g, nodes=[iri("Nowhere")]).nodes == (iri("Nowhere"),)
    assert meta_validate(g, remove=[(iri("Gone"), to_engine(SH.name), lit("x"))])[0]


def test_neither_nodes_nor_an_edit_is_the_full_check_with_the_same_results_and_return_shape():
    g = mixed()
    full = problem_report(g)
    assert full.scope.full and full.scope.nodes == () and full.scope.reasons
    assert len(full.problems) >= 8
    ok = meta_validate(generated(3))
    assert isinstance(ok, tuple) and len(ok) == 3 and ok[0] is True and isinstance(ok[2], str)
    assert full.problems and full.report_text.startswith("Validation Report")
    assert str(full).startswith("The shapes graph is not valid SHACL")


def test_an_rdflib_graph_is_refused():
    rdflib = pytest.importorskip("rdflib")
    with pytest.raises(TypeError):
        meta_validate(rdflib.Graph(), nodes=[iri("S")])
    with pytest.raises(TypeError):
        meta_scope(rdflib.Graph(), nodes=[iri("S")])


def test_nodes_alone_is_never_risky_and_a_nodes_check_of_the_current_graph():
    g = mixed()
    scope = meta_scope(g, nodes=[iri("Comp"), iri("Prefixes")])
    assert not scope.full and set(scope.nodes) >= {iri("Comp"), iri("Prefixes")}
    assert scope.reasons[0].startswith("checked ")


# (6) the error carries the scope; the edit is not applied

def test_a_scoped_failure_carries_its_scope():
    g = mixed()
    error = problem_report(g, nodes=[iri("Many")], with_dependents=False)
    assert error.scope == meta_scope(g, nodes=[iri("Many")], with_dependents=False)
    assert error.scope.nodes[0] == iri("Many") and len(error.scope.nodes) == 2  # and its one property shape


def test_the_proposed_edit_is_not_applied_to_the_callers_graph():
    g = generated(20)
    before = set(g.triples((None, None, None)))
    count = len(g)
    prop = next(p for p in g.objects(iri("S3"), to_engine(SH.property)) if (p, to_engine(SH.path), iri("a")) in g)
    with pytest.raises(ShapeError, check=lambda e: e.kind == "meta"):
        meta_validate(g, add=[(prop, to_engine(SH.datatype), ox.NamedNode(XSD + "integer"))])
    assert len(g) == count and set(g.triples((None, None, None))) == before


def test_an_edit_that_would_introduce_a_defect_is_reported_before_the_graph_changes():
    g = generated(20)
    s3 = iri("S3")
    prop = next(p for p in g.objects(s3, to_engine(SH.property)) if (p, to_engine(SH.path), iri("a")) in g)
    assert meta_validate(g)[0]
    # a second sh:datatype
    error = problem_report(g, add=[(prop, to_engine(SH.datatype), to_engine(ox.NamedNode(XSD + "integer")))])
    assert not error.scope.full and prop in error.scope.nodes and error.problems
    # a property shape without sh:path
    error = problem_report(g, remove=[(prop, to_engine(SH.path), iri("a"))])
    assert error.problems
    # a pattern that does not compile
    error = problem_report(g, add=[(prop, to_engine(SH.pattern), lit("[unclosed"))])
    assert error.problems and not error.scope.full
    assert meta_validate(g)[0]  # none of it reached the graph


def test_an_edit_that_fixes_a_defect_conforms():
    g = generated(20, "ex:Dup a sh:NodeShape ; sh:property [ sh:path ex:a ; sh:datatype xsd:string , xsd:integer ] .")
    assert problem_report(g).problems
    prop = next(iter(g.objects(iri("Dup"), to_engine(SH.property))))
    fixed = meta_validate(g, remove=[(prop, to_engine(SH.datatype), to_engine(ox.NamedNode(XSD + "integer")))])
    assert fixed[0] is True
    # the caller's graph still has the defect
    assert problem_report(g).problems


# (7) a fresh subject's type triple is local, an existing one's is not

RDFTYPE = to_engine(RDF.type)
SUBCLASS = ox.NamedNode("http://www.w3.org/2000/01/rdf-schema#subClassOf")


def _new_shape_edit(datatypes=("string",)):
    new, p1, p2 = iri("New"), ox.BlankNode(), ox.BlankNode()
    add = [
        (new, RDFTYPE, to_engine(SH.NodeShape)), (new, to_engine(SH.targetClass), iri("NewClass")),
        (new, to_engine(SH.property), p1), (new, to_engine(SH.property), p2),
        (p1, to_engine(SH.path), iri("a")), (p1, to_engine(SH.minCount), lit("1", XSD + "integer")),
        (p2, to_engine(SH.path), iri("b")),
        *[(p2, to_engine(SH.datatype), ox.NamedNode(XSD + d)) for d in datatypes],
    ]
    return add, new, p1, p2


def test_a_new_node_shape_with_property_shapes_is_scoped_to_itself():
    g = generated(30)
    add, new, p1, p2 = _new_shape_edit()
    scope = meta_scope(g, add=add)
    assert not scope.full, scope.reasons
    assert set(scope.nodes) >= {new, p1, p2} and iri("S1") not in scope.nodes
    assert scope.reasons == ("checked 8 nodes: 7 changed, 1 new",), scope.reasons
    assert meta_validate(g, add=add)[0]


def test_a_new_node_shape_in_2000_shapes_is_scoped_finds_its_defect_and_is_fast(capsys):
    g = generated(2000)
    before = len(g)
    ok, _o, _t = meta_validate(g, add=_new_shape_edit()[0])
    assert ok
    add, new, _p1, p2 = _new_shape_edit(("string", "integer"))  # two sh:datatype values on one property shape
    assert not meta_scope(g, add=add).full
    error = problem_report(g, add=add)
    assert not error.scope.full and p2 in error.scope.nodes and error.problems
    best = min(_time(lambda: meta_validate(g, add=_new_shape_edit()[0])) for _ in range(3))
    with capsys.disabled():
        print(f"\nadd a new node shape to 2000 shapes, scoped: {best:.3f} s")
    assert best < 0.200, best
    assert len(g) == before and not list(g.triples((new, None, None)))


def test_a_new_blank_node_property_shape_is_local():
    g = generated(5)
    bnode = ox.BlankNode()
    scope = meta_scope(g, add=[(iri("S1"), to_engine(SH.property), bnode), (bnode, RDFTYPE, to_engine(SH.PropertyShape)),
                               (bnode, to_engine(SH.path), iri("z"))])
    assert not scope.full and bnode in scope.nodes and "1 new" in scope.reasons[0]


@pytest.mark.parametrize("risky", [SH.ConstraintComponent, SH.SPARQLRuleTemplate, SH.Parameter, SH.ShapesGraph])
def test_a_new_node_typed_as_a_risky_class_is_full(risky):
    scope = meta_scope(generated(5), add=[(iri("Fresh"), RDFTYPE, to_engine(risky))])
    assert scope.full and "rdf:type" in scope.reasons[0]
    # a second, harmless type on the same fresh subject does not hide it
    both = meta_scope(generated(5), add=[(iri("Fresh"), RDFTYPE, to_engine(SH.NodeShape)), (iri("Fresh"), RDFTYPE, to_engine(risky))])
    assert both.full


def test_an_existing_node_getting_a_type_is_full_and_so_is_a_removed_type():
    g = generated(5)
    assert meta_scope(g, add=[(iri("S1"), RDFTYPE, iri("Other"))]).full
    assert meta_scope(g, remove=[(iri("S1"), RDFTYPE, to_engine(SH.NodeShape))]).full
    # a type on a subject that is only mentioned as an object is not fresh when it has triples; one with none is
    assert not meta_scope(g, add=[(iri("S1"), to_engine(SH.node), iri("Mentioned")), (iri("Mentioned"), RDFTYPE, to_engine(SH.NodeShape))]).full


def test_a_new_subject_of_subclassof_is_local_unless_it_extends_a_risky_class():
    g = generated(5)
    assert not meta_scope(g, add=[(iri("NewClass"), SUBCLASS, iri("Other"))]).full
    assert meta_scope(g, add=[(iri("NewClass"), SUBCLASS, to_engine(SH.SPARQLRuleTemplate))]).full
    assert meta_scope(g, add=[(iri("S1"), SUBCLASS, iri("Other"))]).full


def test_a_new_validator_is_still_found_through_the_link_that_names_it():
    g = generated(5)
    scope = meta_scope(g, add=[(iri("Comp2"), to_engine(SH.validator), iri("V")), (iri("V"), RDFTYPE, to_engine(SH.SPARQLAskValidator))])
    assert scope.full


def test_an_edit_to_a_reifier_covers_the_shape_that_holds_the_reified_triple():
    g = graph("ex:Holder a sh:NodeShape ; sh:targetClass ex:H ; sh:property ex:P ~ ex:r .\n"
              "ex:P sh:path ex:a . ex:Other a sh:NodeShape .")
    scope = meta_scope(g, add=[(iri("r"), to_engine(SH.message), lit("note"))], with_dependents=False)
    assert not scope.full
    assert iri("Holder") in scope.nodes and iri("r") in scope.nodes, scope.nodes
    assert scope.reasons == ("checked 2 nodes: 2 changed",), scope.reasons  # the reifier and the shape holding the link


def test_full_overrides_a_scoped_edit_and_keeps_the_edit_applied():
    g = generated(20, "ex:Dup a sh:NodeShape ; sh:property [ sh:path ex:a ; sh:datatype xsd:string , xsd:integer ] .")
    add = [(iri("S3"), to_engine(SH.name), lit("three"))]
    narrow = engine_meta_validate(g, add=add)
    assert narrow.conforms and not narrow.scope.full
    wide = engine_meta_validate(g, add=add, full=True)
    assert not wide.conforms and wide.scope.full and wide.scope.reasons == ("full check: requested",)
    assert engine_meta_validate(g, full=True).problems == engine_meta_validate(g).problems
