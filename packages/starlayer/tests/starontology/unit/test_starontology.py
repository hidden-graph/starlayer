"""tests/unit/test_starontology.py

starontology is pure data (eight .ttl files, plus the generated shacl_meta
entry) behind a thin registry (get_ontology_list()/get_ontology_graph()) -
this suite confirms every registered entry loads and parses, and the
registry's own list/lookup behavior is correct. The underlying
*_TTL_PATH constants are private as of 2026-10-02
(internal to this module's own registry, not public API) - there's no
dedicated "does the file exist" test anymore, since
TestGetOntologyGraph::test_every_registered_name_loads_and_parses already
proves it implicitly (a missing file would fail to parse). Not that any
vocabulary's own content is correct - that's each consuming package's own
test suite's job (packages/starlayer/tests/graph/unit/test_manchester_ast_shapes.py,
test_skos_shapes.py; packages/starlayer/tests/sparql/unit/test_shacl_shapes.py,
test_srl_shapes.py).
"""

import pytest
from starlayer import starontology
from starlayer.graph import StarLayerGraph


class TestGetOntologyList:
    def test_returns_all_thirteen_entries(self):
        names = {info.name for info in starontology.get_ontology_list()}
        assert names == {
            "manchester_owl", "manchester_shacl",
            "skos_owl", "skos_shacl",
            "sparql_owl", "sparql_shacl",
            "sqe_owl", "sqe_shacl",
            "srl_owl", "srl_shacl",
            "spexpr_owl", "spexpr_shacl",
            "shacl_meta",
        }

    def test_sorted_by_name(self):
        names = [info.name for info in starontology.get_ontology_list()]
        assert names == sorted(names)

    def test_every_entry_has_name_description_and_type(self):
        for info in starontology.get_ontology_list():
            assert info.name
            assert info.description
            assert info.type in ("shacl", "ast-graph", "owl")

    def test_shapes_entries_are_type_shacl(self):
        """shacl_meta is generated, not file-backed, but it's still a SHACL
        shapes graph - same type as the four file-backed shapes entries."""
        shacl_names = {info.name for info in starontology.get_ontology_list() if info.type == "shacl"}
        assert shacl_names == {
            "manchester_shacl", "skos_shacl", "sparql_shacl", "sqe_shacl", "srl_shacl",
            "spexpr_shacl", "shacl_meta",
        }

    def test_skos_owl_is_type_owl_not_ast_graph(self):
        """skos: is a real semantic ontology (formal axioms about an existing
        vocabulary), not a syntax tree represented as RDF like the other
        three - so it gets "owl", not "ast-graph"."""
        [skos_entry] = [info for info in starontology.get_ontology_list() if info.name == "skos_owl"]
        assert skos_entry.type == "owl"

    def test_manchester_sparql_sqe_srl_owl_entries_are_type_ast_graph(self):
        ast_graph_names = {info.name for info in starontology.get_ontology_list() if info.type == "ast-graph"}
        assert ast_graph_names == {"manchester_owl", "sparql_owl", "sqe_owl", "srl_owl", "spexpr_owl"}


class TestGetOntologyGraph:
    @pytest.mark.parametrize("name", [
        "manchester_owl", "manchester_shacl",
        "skos_owl", "skos_shacl",
        "sparql_owl", "sparql_shacl",
        "srl_owl", "srl_shacl",
        "shacl_meta",
    ])
    def test_every_registered_name_loads_and_parses(self, name):
        g = starontology.get_ontology_graph(name)
        assert isinstance(g, StarLayerGraph)
        assert len(g) > 0

    def test_unknown_name_raises_keyerror_naming_choices(self):
        with pytest.raises(KeyError, match="manchester_owl"):
            starontology.get_ontology_graph("not_a_real_name")

    def test_returns_a_fresh_graph_each_call(self):
        g1 = starontology.get_ontology_graph("manchester_owl")
        g2 = starontology.get_ontology_graph("manchester_owl")
        assert g1 is not g2

    def test_shacl_meta_is_wrapped_as_starlayergraph_not_left_plain(self):
        """build_meta_shapes_graph() (starlayer.shacl) returns a plain
        rdflib.Graph - confirmed in its own source - so this entry
        specifically needs StarLayerGraph.from_rdflib() wrapping to keep
        the same return type as every other entry. isinstance alone would
        pass on a plain Graph too (StarLayerGraph is not involved there),
        so check the exact type instead."""
        g = starontology.get_ontology_graph("shacl_meta")
        assert type(g) is StarLayerGraph


_EXPECTED_SPEC_IRIS = {
    "manchester_shacl": {"https://www.w3.org/TR/owl2-manchester-syntax"},
    "skos_shacl": {"https://www.w3.org/TR/skos-reference"},
    "sqe_shacl": {"https://www.w3.org/TR/sparql12-query"},
    "srl_shacl": {"https://www.w3.org/TR/sparql12-rl"},
}


class TestGetProfileGraph:
    """Corrected 2026-10-10 (direct user challenge to the original
    2026-10-08 design): a registered shapes graph is dx-prof
    prof:isProfileOf the real external *specification* (SPARQL, SKOS,
    Manchester Syntax, SPARQL-RL) - not the bundled ontology/AST graph,
    which is instead a prof:hasResource/ResourceDescriptor of that same
    real spec (role:schema, a sibling of the shapes graph's own
    role:validation descriptor). See get_profile_graph()'s own docstring
    for the full design and why the original mapping was wrong.

    sparql_shacl/sparql_owl (salg:) deliberately excluded (2026-10-11,
    direct user decision) - salg: is this project's own internal SPARQL
    algebra encoding, not something meant to carry a public-facing
    conformance claim the way manch:/skos:/sqe:/srl: do. It's still a
    registered entry with real content - get_profile_graph("sparql_shacl")
    now returns an empty graph (registered, but the document has nothing
    to say about its profile relationship), not None."""

    @pytest.mark.parametrize(
        "shapes_name,ontology_name",
        [
            ("manchester_shacl", "manchester_owl"),
            ("skos_shacl", "skos_owl"),
            ("sqe_shacl", "sqe_owl"),
            ("srl_shacl", "srl_owl"),
        ],
    )
    def test_each_pair_asserts_is_profile_of(self, shapes_name, ontology_name):
        from rdflib import Namespace, URIRef

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        ROLE = Namespace("http://www.w3.org/ns/dx/prof/role/")
        graph = starontology.get_profile_graph(shapes_name)
        assert graph is not None

        shapes_iri = starontology.get_resource_iri(shapes_name)
        ontology_iri = starontology.get_resource_iri(ontology_name)

        spec_iris = {str(o) for o in graph.objects(shapes_iri, PROF.isProfileOf)}
        assert spec_iris == _EXPECTED_SPEC_IRIS[shapes_name]

        # For every real specification this shapes graph is a profile of,
        # that spec's own prof:hasResource descriptors must identify the
        # shapes graph itself (role:validation) and the paired ontology/
        # AST graph (role:schema) - not the other way around. Checked by
        # existence, not uniqueness: sparql12-query is itself shared by
        # two pairs (sqe_shacl/spexpr_shacl), so its own hasResource set
        # legitimately has more than one role:validation/role:schema
        # descriptor - one set per pair sharing it.
        for spec_iri in spec_iris:
            descriptors = list(graph.objects(URIRef(spec_iri), PROF.hasResource))
            validation_artifacts = {
                next(graph.objects(d, PROF.hasArtifact))
                for d in descriptors
                if next(graph.objects(d, PROF.hasRole)) == ROLE.validation
            }
            schema_artifacts = {
                next(graph.objects(d, PROF.hasArtifact))
                for d in descriptors
                if next(graph.objects(d, PROF.hasRole)) == ROLE.schema
            }
            assert shapes_iri in validation_artifacts
            assert ontology_iri in schema_artifacts

    def test_sparql_shacl_is_registered_but_deliberately_has_no_profile(self):
        """salg: is excluded from the public profile mapping (2026-10-11) -
        sparql_shacl is still a real registered entry (get_ontology_graph()
        etc. work normally), but get_profile_graph() returns an empty
        graph for it, not None - the same "registered, but this document
        has nothing to say about it" case the url= override tests below
        already establish, just for the bundled default instead."""
        graph = starontology.get_profile_graph("sparql_shacl")
        assert graph is not None
        assert len(graph) == 0

    def test_shacl_meta_has_a_bare_isprofileof_entry_with_no_resource_pairing(self):
        """shacl_meta has no ontology counterpart (2026-10-12) - but it
        still gets a real profile-graph entry, just a bare
        prof:isProfileOf with no prof:hasResource/ResourceDescriptor
        structure alongside it (there's no sibling ontology/AST graph to
        describe via role:schema)."""
        from rdflib import Namespace

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        PROFILE = Namespace("http://www.w3.org/ns/shacl/profile/")
        graph = starontology.get_profile_graph("shacl_meta")
        assert graph is not None
        subject = starontology.get_resource_iri("shacl_meta")
        claimed = set(graph.objects(subject, PROF.isProfileOf))
        assert claimed == {
            PROFILE.core,
            PROFILE.sparql,
            PROFILE["node-expr"],
            PROFILE.rules,
            PROFILE.profiling,
        }
        assert list(graph.triples((subject, PROF.hasResource, None))) == []

    def test_unknown_name_returns_none_not_raise(self):
        assert starontology.get_profile_graph("not_a_real_name") is None

    def test_returns_independent_graphs_each_call(self):
        first = starontology.get_profile_graph("skos_shacl")
        second = starontology.get_profile_graph("skos_shacl")
        assert first is not second
        before = len(second)
        first.add((list(first)[0][0], list(first)[0][1], list(first)[0][0]))
        assert len(second) == before


class TestGetConformanceProfiles:
    """2026-10-09: the prof:isProfileOf mapping for every pair now lives
    in one real, persisted document (ontology-shapes-profiles.ttl), loaded
    via get_conformance_profiles() - not synthesized from a Python dict
    on every get_profile_graph() call, the original 2026-10-08 design.
    get_profile_graph() is now a thin filter over this. Six pairs as of
    2026-10-10 (spexpr: joined the original five once it was carved out of
    salg: into its own shared vocabulary - see starlayer/sparql/CLAUDE.md's
    dated entry)."""

    def test_bundled_copy_has_five_pairs(self):
        from rdflib import Namespace

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        graph = starontology.get_conformance_profiles()
        # 74 triples (2026-10-12: +5 for shacl_meta's own bare
        # prof:isProfileOf entry against the five public SHACL profile
        # IRIs it represents - no prof:ResourceDescriptor pairing, since
        # it has no ontology counterpart). Before that: 69 (2026-10-11:
        # sparql_shacl/sparql_owl (salg:) excluded as internal-only,
        # dropping the 2026-10-10 restructure's 86 down to this): 5
        # shapes graphs, each with its own single prof:isProfileOf (5
        # total) plus two prof:ResourceDescriptor bnodes per pair
        # (role:validation for the shapes graph, role:schema for the
        # paired ontology/AST graph), each carrying
        # hasArtifact/hasRole/rdfs:label/rdfs:comment, plus an rdfs:label
        # on each of the 4 distinct real specification IRIs involved
        # (sqe_shacl/spexpr_shacl share sparql12-query) - see
        # get_profile_graph()'s own docstring for the full design.
        assert len(graph) == 74
        # 6 subjects (5 shapes graphs + shacl_meta), 10 prof:isProfileOf
        # triples total (5 shapes graphs x 1 each, + shacl_meta x 5 public
        # SHACL profile IRIs).
        isprofileof_subjects = {s for s, _, _ in graph.triples((None, PROF.isProfileOf, None))}
        assert len(isprofileof_subjects) == 6
        assert len(list(graph.triples((None, PROF.isProfileOf, None)))) == 10

    def test_returns_independent_graphs_each_call(self):
        first = starontology.get_conformance_profiles()
        second = starontology.get_conformance_profiles()
        assert first is not second
        before = len(second)
        first.remove(list(first)[0])
        assert len(second) == before

    def test_url_overrides_the_bundled_default(self, tmp_path):
        """A caller can point at a different local file entirely - e.g. a
        local override for testing, confirmed here with a deliberately
        different (single-triple) document, not just the bundled one
        re-read from a copied path."""
        from rdflib import URIRef

        override = tmp_path / "override-profiles.ttl"
        override.write_text(
            "@prefix prof: <http://www.w3.org/ns/dx/prof/> .\n"
            "<urn:test:shapes> prof:isProfileOf <urn:test:ontology> .\n"
        )

        graph = starontology.get_conformance_profiles(url=str(override))

        assert len(graph) == 1
        assert (URIRef("urn:test:shapes"), None, URIRef("urn:test:ontology")) in graph

    def test_get_profile_graph_passes_url_through(self, tmp_path):
        """get_profile_graph()'s own url= reaches get_conformance_profiles()
        - confirmed by overriding with a document that pairs skos_shacl's
        real resource IRI against a different ontology than the bundled
        default declares."""
        from rdflib import URIRef

        skos_shacl_iri = starontology.get_resource_iri("skos_shacl")
        override = tmp_path / "override-profiles.ttl"
        override.write_text(
            "@prefix prof: <http://www.w3.org/ns/dx/prof/> .\n"
            f"<{skos_shacl_iri}> prof:isProfileOf <urn:test:a-different-ontology> .\n"
        )

        graph = starontology.get_profile_graph("skos_shacl", url=str(override))

        assert len(graph) == 1
        [(_, _, obj)] = list(graph)
        assert obj == URIRef("urn:test:a-different-ontology")

    def test_get_profile_graph_returns_empty_not_none_when_url_lacks_the_entry(self, tmp_path):
        """A registered name with an override document that simply doesn't
        mention it: empty graph, not None - None is reserved for "not a
        registered name at all" (shacl_meta, a typo), a different case
        than "registered, but this particular document has nothing to
        say about it"."""
        override = tmp_path / "empty-profiles.ttl"
        override.write_text("@prefix prof: <http://www.w3.org/ns/dx/prof/> .\n")

        graph = starontology.get_profile_graph("skos_shacl", url=str(override))

        assert graph is not None
        assert len(graph) == 0


class TestGetResourceIri:
    """get_resource_iri() exists so a caller can give validate()'s own
    shapes_graph_resource= the exact same identity get_profile_graph() asserts
    prof:isProfileOf on - otherwise derive_conforms_to()'s second rule can
    never fire (its WHERE clause requires the same IRI in both places)."""

    def test_matches_the_subject_get_profile_graph_uses(self):
        from rdflib import Namespace

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        profile_graph = starontology.get_profile_graph("skos_shacl")
        [(subject, _, _)] = list(profile_graph.triples((None, PROF.isProfileOf, None)))
        assert starontology.get_resource_iri("skos_shacl") == subject

    def test_matches_the_hasartifact_for_the_ontology_side(self):
        """get_resource_iri("skos_owl") still identifies the ontology/AST
        graph correctly - reachable via the real spec's own
        prof:hasResource/prof:hasArtifact (role:schema) now, not as the
        object of prof:isProfileOf directly (2026-10-10 correction - see
        get_profile_graph()'s own docstring: the ontology graph is a
        *resource of* the real specification, not what the shapes graph
        itself is a profile of)."""
        from rdflib import Namespace

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        ROLE = Namespace("http://www.w3.org/ns/dx/prof/role/")
        profile_graph = starontology.get_profile_graph("skos_shacl")
        [(_, _, spec_iri)] = list(profile_graph.triples((None, PROF.isProfileOf, None)))
        [descriptor] = [
            d
            for d in profile_graph.objects(spec_iri, PROF.hasResource)
            if (d, PROF.hasRole, ROLE.schema) in profile_graph
        ]
        [artifact] = list(profile_graph.objects(descriptor, PROF.hasArtifact))
        assert starontology.get_resource_iri("skos_owl") == artifact

    def test_shacl_meta_has_a_real_resource_iri(self):
        """shacl_meta (2026-10-12) gets a real, stable IRI here too - used
        by ontology-shapes-profiles.ttl's own prof:isProfileOf entry for
        it - even though the file at this path doesn't exist yet (still
        generated Python, see docs/future_enhancements.md)."""
        iri = starontology.get_resource_iri("shacl_meta")
        assert iri is not None
        assert str(iri).endswith("shacl_meta_shapes.ttl")

    def test_unknown_name_returns_none(self):
        assert starontology.get_resource_iri("not_a_real_name") is None

    def test_end_to_end_chain_actually_derives_dcterms_conforms_to(self):
        """The real motivating workflow: validate against a starontology
        shapes graph, using get_resource_iri() for shapes_graph_resource=, then
        derive_conforms_to() with get_profile_graph() as
        specification_graph= - confirms the second rule actually fires,
        not just that the two pieces exist independently."""
        from starlayer.graph import StarLayerGraph
        from starlayer.shacl import StarShaclSchema
        from starlayer.shacl.shacl_profiling import derive_conforms_to
        from rdflib.namespace import DCTERMS
        from rdflib import URIRef

        data = StarLayerGraph()
        data.parse(
            data="""
                @prefix skos: <http://www.w3.org/2004/02/skos/core#> .
                @prefix ex: <http://example.org/> .
                ex:scheme1 a skos:ConceptScheme .
                ex:concept1 a skos:Concept ; skos:inScheme ex:scheme1 ; skos:prefLabel "Example"@en .
            """,
            format="turtle",
        )
        shapes = starontology.get_ontology_graph("skos_shacl")
        result = StarShaclSchema(shacl_graph=shapes).validate(
            data_graph=data,
            meta_shacl=False,
            data_graph_iri="http://example.org/graphs/mydata",
            shapes_graph_resource=starontology.get_resource_iri("skos_shacl"),
        )
        assert result.conforms is True

        derived = derive_conforms_to(
            result.report_graph, specification_graph=starontology.get_profile_graph("skos_shacl")
        )

        # dcterms:conformsTo now derives against the real SKOS Reference
        # spec IRI (2026-10-10 correction) - not starontology's own
        # internal skos_owl encoding, which is a role:schema *resource of*
        # that spec, not what skos_shacl itself is a profile of.
        assert (
            URIRef("http://example.org/graphs/mydata"),
            DCTERMS.conformsTo,
            URIRef("https://www.w3.org/TR/skos-reference"),
        ) in derived


_TTL_FILENAME = {
    "manchester_owl": "manchester-ast-ontology.ttl",
    "manchester_shacl": "manchester_shapes.ttl",
    "skos_owl": "skos-ontology.ttl",
    "skos_shacl": "skos_shapes.ttl",
    "sparql_owl": "salg-ontology.ttl",
    "sparql_shacl": "sparql_shapes.ttl",
    "sqe_owl": "sqe-ontology.ttl",
    "sqe_shacl": "sqe_shapes.ttl",
    "srl_owl": "srl-ontology.ttl",
    "srl_shacl": "srl_shapes.ttl",
}


class TestLocalLoader:
    """starontology.local_loader() - a StarLayerGraph.resolve_imports()-
    compatible loader that only ever reads this package's own bundled
    files. The real motivating case: sqe_shapes.ttl/srl_shapes.ttl both
    owl:imports spexpr:ShapesGraph (salg:ShapesGraph before 2026-10-10 -
    see starlayer/sparql/CLAUDE.md's dated entry on the spexpr: carve-out)
    because their own shapes genuinely reference
    spexpr:ExpressionShape/spexpr:VariableShape, which aren't defined in
    sqe_shapes.ttl/srl_shapes.ttl themselves."""

    def test_resolves_a_real_sh_shapesgraph_iri(self):
        from rdflib import Namespace as RdfNamespace

        SALG = RdfNamespace("https://github.com/hidden-graph/starsparql/ns/algebra#")
        resolved = starontology.local_loader(SALG.ShapesGraph)
        assert resolved is not None
        assert len(resolved) > 0

    def test_returns_none_for_an_unregistered_iri(self):
        from rdflib import URIRef

        assert starontology.local_loader(URIRef("http://example.org/not-registered")) is None

    def test_sqe_shacl_alone_is_missing_spexpr_expression_shape(self):
        """Confirms the real gap this whole mechanism exists to close -
        not just that the pieces exist independently."""
        from rdflib import Namespace as RdfNamespace, RDF
        SH = RdfNamespace("http://www.w3.org/ns/shacl#")
        SPEXPR = RdfNamespace("https://github.com/hidden-graph/starsparql/ns/expr#")

        sqe_alone = starontology.get_ontology_graph("sqe_shacl")
        assert (SPEXPR.ExpressionShape, RDF.type, SH.NodeShape) not in sqe_alone

    def test_resolve_imports_with_local_loader_closes_the_gap(self):
        from rdflib import Namespace as RdfNamespace, RDF
        SH = RdfNamespace("http://www.w3.org/ns/shacl#")
        SPEXPR = RdfNamespace("https://github.com/hidden-graph/starsparql/ns/expr#")

        sqe_alone = starontology.get_ontology_graph("sqe_shacl")
        merged = sqe_alone.resolve_imports(loader=starontology.local_loader, mode="full")

        assert (SPEXPR.ExpressionShape, RDF.type, SH.NodeShape) in merged
        assert len(merged) > len(sqe_alone)

    def test_srl_shacl_also_resolves_its_spexpr_import(self):
        from rdflib import Namespace as RdfNamespace, RDF
        SH = RdfNamespace("http://www.w3.org/ns/shacl#")
        SPEXPR = RdfNamespace("https://github.com/hidden-graph/starsparql/ns/expr#")

        srl_alone = starontology.get_ontology_graph("srl_shacl")
        merged = srl_alone.resolve_imports(loader=starontology.local_loader, mode="full")

        assert (SPEXPR.ExpressionShape, RDF.type, SH.NodeShape) in merged

    def test_entries_with_no_owl_imports_are_unaffected(self):
        """skos_shacl declares no owl:imports at all - resolve_imports()
        with local_loader must be a safe no-op, not an error."""
        skos_alone = starontology.get_ontology_graph("skos_shacl")
        merged = skos_alone.resolve_imports(loader=starontology.local_loader, mode="full")
        assert set(merged) == set(skos_alone)


