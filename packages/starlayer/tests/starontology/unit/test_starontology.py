"""tests/unit/test_starontology.py

starontology is pure data (one TriG dataset, starontology.trig, holding
every registered entry including shacl_shacl as of 2026-10-12) behind a
thin registry (get_ontology_list()/get_ontology_graph()) -
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
    def test_returns_all_entries_except_the_internal_salg_pair(self):
        """sparql_owl/sparql_shacl (salg:) are deliberately excluded (2026-10-14) -
        salg: is purely an internal encoding (starlayer.sparql's own
        query_to_rdf()/rdf_to_query() machinery; sqe:/srl: import its
        shared expression vocabulary), not something an external caller
        is meant to reach for directly - sqe: is the human-readable,
        UI-editable public-facing analog. They're still real, fully
        registered entries otherwise - see TestGetOntologyGraph below,
        which confirms get_ontology_graph() still resolves them by name."""
        names = {info.name for info in starontology.get_ontology_list()}
        assert names == {
            "manchester_owl", "manchester_shacl",
            "skos_owl", "skos_shacl",
            "sqe_owl", "sqe_shacl",
            "srl_owl", "srl_shacl",
            "spexpr_owl", "spexpr_shacl",
            "shacl_shacl",
        }

    def test_sorted_by_name(self):
        names = [info.name for info in starontology.get_ontology_list()]
        assert names == sorted(names)

    def test_every_entry_has_name_description_and_type(self):
        for info in starontology.get_ontology_list():
            assert info.name
            assert info.description
            assert info.type in ("shacl", "syntax-tree-graph", "owl")

    def test_shapes_entries_are_type_shacl(self):
        """shacl_shacl has no ontology counterpart to pair with, but it's
        still a SHACL shapes graph - same type as the four entries that
        do (sparql_shacl excluded from this list - see the class's own
        test above)."""
        shacl_names = {info.name for info in starontology.get_ontology_list() if info.type == "shacl"}
        assert shacl_names == {
            "manchester_shacl", "skos_shacl", "sqe_shacl", "srl_shacl",
            "spexpr_shacl", "shacl_shacl",
        }

    def test_skos_owl_is_type_owl_not_syntax_tree_graph(self):
        """skos: is a real semantic ontology (formal axioms about an existing
        vocabulary), not a syntax tree represented as RDF like the other
        three - so it gets "owl", not "syntax-tree-graph"."""
        [skos_entry] = [info for info in starontology.get_ontology_list() if info.name == "skos_owl"]
        assert skos_entry.type == "owl"

    def test_manchester_sqe_srl_spexpr_owl_entries_are_type_syntax_tree_graph(self):
        """sparql_owl excluded from this list too - see the class's own
        first test above."""
        syntax_tree_graph_names = {
            info.name for info in starontology.get_ontology_list() if info.type == "syntax-tree-graph"
        }
        assert syntax_tree_graph_names == {"manchester_owl", "sqe_owl", "srl_owl", "spexpr_owl"}

    def test_salg_pair_is_excluded_from_the_list_but_still_a_real_registered_entry(self):
        names = {info.name for info in starontology.get_ontology_list()}
        assert "sparql_owl" not in names
        assert "sparql_shacl" not in names
        # still real and loadable directly by name - just not enumerated.
        assert len(starontology.get_ontology_graph("sparql_owl")) > 0
        assert len(starontology.get_ontology_graph("sparql_shacl")) > 0


class TestGetOntologyGraph:
    @pytest.mark.parametrize("name", [
        "manchester_owl", "manchester_shacl",
        "skos_owl", "skos_shacl",
        "sparql_owl", "sparql_shacl",
        "srl_owl", "srl_shacl",
        "shacl_shacl",
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

    def test_shacl_shacl_is_wrapped_as_starlayergraph_not_left_plain(self):
        """build_meta_shapes_graph() (starlayer.shacl) returns a plain
        rdflib.Graph - confirmed in its own source - so this entry
        specifically needs StarLayerGraph.from_rdflib() wrapping to keep
        the same return type as every other entry. isinstance alone would
        pass on a plain Graph too (StarLayerGraph is not involved there),
        so check the exact type instead."""
        g = starontology.get_ontology_graph("shacl_shacl")
        assert type(g) is StarLayerGraph


_SLP = "https://github.com/hidden-graph/starlayer/ns/profile#"
# StarLayer profile -> (public things it is a profile of, shapes entry, ontology entries)
_EXPECTED_PROFILES = {
    "Manchester": ({"https://www.w3.org/TR/owl2-manchester-syntax"}, ["manchester_shacl"], ["manchester_owl"]),
    "Skos": ({"https://www.w3.org/TR/skos-reference"}, ["skos_shacl"], ["skos_owl"]),
    "SparqlQuery": ({"https://www.w3.org/TR/sparql12-query"}, ["sqe_shacl", "spexpr_shacl"], ["sqe_owl", "spexpr_owl"]),
    "SparqlRL": ({"https://www.w3.org/TR/sparql12-rl"}, ["srl_shacl"], ["srl_owl"]),
    "Shacl": (
        {
            "http://www.w3.org/ns/shacl/profile/core",
            "http://www.w3.org/ns/shacl/profile/sparql",
            "http://www.w3.org/ns/shacl/profile/node-expr",
            "http://www.w3.org/ns/shacl/profile/rules",
            "http://www.w3.org/ns/shacl/profile/profiling",
        },
        ["shacl_shacl"],
        [],
    ),
}


class TestConformanceProfilesContent:
    """The StarLayer profiles in starlayer-profiles.ttl, checked directly
    against get_conformance_profiles()'s own full graph. Each StarLayer
    profile (slp:) is a prof:Profile that is prof:isProfileOf the public
    specification (or public SHACL profiles) it relates to, and lists its
    ontology (role:schema) and shapes (role:validation) files with
    prof:hasResource. A shapes graph is not itself declared a profile of the
    public specification: data that conforms to it conforms to the
    StarLayer profile that lists it, and that profile's own isProfileOf link
    carries the claim up.

    sparql_shacl/sparql_owl (salg:) are deliberately not in any profile -
    salg: is this project's own internal SPARQL algebra encoding, not
    something meant to carry a public-facing conformance claim."""

    @pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES))
    def test_each_profile_is_a_profile_of_the_public_layer(self, name):
        from rdflib import RDF, Namespace, URIRef

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        graph = starontology.get_conformance_profiles()
        profile = URIRef(_SLP + name)
        assert (profile, RDF.type, PROF.Profile) in graph
        assert {str(o) for o in graph.objects(profile, PROF.isProfileOf)} == _EXPECTED_PROFILES[name][0]

    @pytest.mark.parametrize("name", sorted(_EXPECTED_PROFILES))
    def test_each_profile_lists_its_shapes_and_ontology_files(self, name):
        from rdflib import Namespace, URIRef

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        ROLE = Namespace("http://www.w3.org/ns/dx/prof/role/")
        graph = starontology.get_conformance_profiles()
        profile = URIRef(_SLP + name)
        by_role = {ROLE.validation: set(), ROLE.schema: set()}
        for descriptor in graph.objects(profile, PROF.hasResource):
            role = next(graph.objects(descriptor, PROF.hasRole))
            by_role[role].add(next(graph.objects(descriptor, PROF.hasArtifact)))
        _, shapes, ontologies = _EXPECTED_PROFILES[name]
        assert by_role[ROLE.validation] == {starontology.get_resource_iri(n) for n in shapes}
        assert by_role[ROLE.schema] == {starontology.get_resource_iri(n) for n in ontologies}

    def test_shapes_graphs_are_not_declared_profiles_of_the_public_layer(self):
        """The layering: no registered file has its own prof:isProfileOf."""
        from rdflib import Namespace

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        graph = starontology.get_conformance_profiles()
        for info in starontology.get_ontology_list():
            assert (starontology.get_resource_iri(info.name), PROF.isProfileOf, None) not in graph

    def test_sparql_shacl_is_registered_but_in_no_profile(self):
        """salg: is excluded from the public profiles (2026-10-11)."""
        from rdflib import Namespace

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        graph = starontology.get_conformance_profiles()
        for name in ("sparql_shacl", "sparql_owl"):
            assert (None, PROF.hasArtifact, starontology.get_resource_iri(name)) not in graph


class TestGetConformanceProfiles:
    """2026-10-09: the prof:isProfileOf mapping for every pair now lives
    in one real, persisted document (starlayer-profiles.ttl), loaded
    via get_conformance_profiles() - not synthesized from a Python dict
    on every call, the original 2026-10-08 design. Six pairs as of
    2026-10-10 (spexpr: joined the original five once it was carved out of
    salg: into its own shared vocabulary - see starlayer/sparql/CLAUDE.md's
    dated entry). No per-entry filter function exists (removed
    2026-10-14) - a caller wanting one entry's own slice extracts it
    themselves from this full graph."""

    def test_bundled_copy_has_five_profiles_and_three_module_resources(self):
        from rdflib import RDF, Namespace, URIRef

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        graph = starontology.get_conformance_profiles()
        profiles = set(graph.subjects(RDF.type, PROF.Profile))
        assert profiles == {URIRef(_SLP + name) for name in _EXPECTED_PROFILES}
        pkg = "https://github.com/hidden-graph/starlayer/tree/main/packages/starlayer/starlayer/"
        for module in ("graph", "sparql", "shacl"):
            assert (URIRef(pkg + module), None, None) in graph

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


class TestGetResourceIri:
    """get_resource_iri() exists so a caller can give validate()'s own
    shapes_graph_resource= the exact same identity the conformance-profiles
    mapping document asserts prof:isProfileOf on - otherwise
    derive_conforms_to()'s second rule can never fire (its WHERE clause
    requires the same IRI in both places)."""

    def test_matches_the_artifact_listed_in_the_profile(self):
        from rdflib import Namespace, URIRef

        PROF = Namespace("http://www.w3.org/ns/dx/prof/")
        ROLE = Namespace("http://www.w3.org/ns/dx/prof/role/")
        graph = starontology.get_conformance_profiles()
        profile = URIRef(_SLP + "Skos")
        artifacts = {
            (next(graph.objects(d, PROF.hasRole)), next(graph.objects(d, PROF.hasArtifact)))
            for d in graph.objects(profile, PROF.hasResource)
        }
        assert (ROLE.validation, starontology.get_resource_iri("skos_shacl")) in artifacts
        assert (ROLE.schema, starontology.get_resource_iri("skos_owl")) in artifacts

    def test_shacl_shacl_has_a_real_resource_iri(self):
        """shacl_shacl gets a real, stable IRI here too - used by
        starlayer-profiles.ttl's slp:Shacl as its validation artifact.
        A real stored named graph in starontology.trig since 2026-10-12,
        and a real standalone published file since 2026-10-14 (see
        TestGetRawUrl/TestPublishedFiles below) - this IRI's own path
        predates both and needed no change for either."""
        iri = starontology.get_resource_iri("shacl_shacl")
        assert iri is not None
        assert str(iri).endswith("shacl12-shacl.ttl")

    def test_unknown_name_returns_none(self):
        assert starontology.get_resource_iri("not_a_real_name") is None


class TestGetRawUrl:
    """get_raw_url() is deliberately a different URL from
    get_resource_iri() - a raw.githubusercontent.com URL for actually
    fetching real content, not the resource's own stable blob-URL
    identity (which doubles as starontology.trig's own internal named-
    graph context IRI and must never change - see get_raw_url()'s own
    docstring for why these are two separate concerns)."""

    def test_differs_from_get_resource_iri_but_names_the_same_file(self):
        iri = starontology.get_resource_iri("skos_shacl")
        url = starontology.get_raw_url("skos_shacl")
        assert url != str(iri)
        assert iri.rsplit("/", 1)[-1] == url.rsplit("/", 1)[-1]

    def test_is_a_real_raw_githubusercontent_url(self):
        url = starontology.get_raw_url("skos_shacl")
        assert url.startswith("https://raw.githubusercontent.com/hidden-graph/starlayer/main/")

    def test_covers_every_registered_ontology_list_entry(self):
        for info in starontology.get_ontology_list():
            assert starontology.get_raw_url(info.name) is not None

    def test_shacl_shacl_has_a_real_raw_url_too(self):
        url = starontology.get_raw_url("shacl_shacl")
        assert url is not None
        assert url.endswith("shacl12-shacl.ttl")

    def test_starlayer_profiles_has_a_raw_url_despite_no_resource_iri(self):
        """Not one of the 13 registered ontology/shapes entries - its own
        get_resource_iri() equivalent doesn't exist - but it's still a
        real published document that needs a real fetch URL."""
        assert starontology.get_resource_iri("starlayer_profiles") is None
        url = starontology.get_raw_url("starlayer_profiles")
        assert url is not None
        assert url.endswith("starlayer-profiles.ttl")

    def test_unknown_name_returns_none(self):
        assert starontology.get_raw_url("not_a_real_name") is None


class TestPublishedFiles:
    """scripts/publish_starontology_files.py regenerates a real, standalone
    file for every get_raw_url() entry, derived from starontology.trig -
    these tests are the regression guard against "edited the dataset,
    forgot to re-publish": every raw URL's implied path must be a real
    file on disk, and that file's content must stay isomorphic to the
    live named graph in starontology.trig. A filesystem/parse check, not
    a live network call - consistent with this project's "no network in
    the normal suite" convention."""

    _RAW_BASE = "https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/starontology/"

    def _published_path(self, name):
        from pathlib import Path

        url = starontology.get_raw_url(name)
        filename = url[len(self._RAW_BASE) :]
        return Path(starontology.__file__).parent / filename

    def _all_names(self):
        return [info.name for info in starontology.get_ontology_list()] + ["starlayer_profiles"]

    def test_every_entry_has_a_real_published_file_on_disk(self):
        for name in self._all_names():
            path = self._published_path(name)
            assert path.is_file(), f"{name}: no published file at {path}"

    def test_every_published_file_is_isomorphic_to_the_live_named_graph(self):
        from rdflib.compare import to_isomorphic

        from starlayer.graph import StarLayerGraph

        for name in self._all_names():
            path = self._published_path(name)
            on_disk = StarLayerGraph()
            on_disk.parse(str(path), format="turtle12")

            live = (
                starontology.get_conformance_profiles()
                if name == "starlayer_profiles"
                else starontology.get_ontology_graph(name)
            )
            assert to_isomorphic(on_disk) == to_isomorphic(live), f"{name}: published file is stale"

    def test_end_to_end_chain_actually_derives_dcterms_conforms_to(self):
        """The real motivating workflow: validate against a starontology
        shapes graph, using get_resource_iri() for shapes_graph_resource=, then
        derive_conforms_to() with get_conformance_profiles() as
        specification_graph= - confirms the second rule actually fires,
        not just that the two pieces exist independently. The full,
        unfiltered mapping graph works fine here - derive_conforms_to()'s
        own WHERE clause already filters by the exact shapes-graph IRI."""
        from rdflib import URIRef
        from rdflib.namespace import DCTERMS
        from starlayer.graph import StarLayerGraph
        from starlayer.shacl import StarShaclSchema
        from starlayer.shacl.shacl_profiling import derive_conforms_to

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
            result.report_graph, specification_graph=starontology.get_conformance_profiles()
        )

        # The report says the data conforms to StarLayer's SKOS profile and,
        # through that profile's prof:isProfileOf link, to the public SKOS
        # Reference.
        data_iri = URIRef("http://example.org/graphs/mydata")
        assert (data_iri, DCTERMS.conformsTo, URIRef(_SLP + "Skos")) in derived
        assert (data_iri, DCTERMS.conformsTo, URIRef("https://www.w3.org/TR/skos-reference")) in derived


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

        SALG = RdfNamespace("https://github.com/hidden-graph/starlayer/ns/sparql/algebra#")
        resolved = starontology.local_loader(SALG.ShapesGraph)
        assert resolved is not None
        assert len(resolved) > 0

    def test_returns_none_for_an_unregistered_iri(self):
        from rdflib import URIRef

        assert starontology.local_loader(URIRef("http://example.org/not-registered")) is None

    def test_sqe_shacl_alone_is_missing_spexpr_expression_shape(self):
        """Confirms the real gap this whole mechanism exists to close -
        not just that the pieces exist independently."""
        from rdflib import RDF
        from rdflib import Namespace as RdfNamespace
        SH = RdfNamespace("http://www.w3.org/ns/shacl#")
        SPEXPR = RdfNamespace("https://github.com/hidden-graph/starlayer/ns/sparql/expr#")

        sqe_alone = starontology.get_ontology_graph("sqe_shacl")
        assert (SPEXPR.ExpressionShape, RDF.type, SH.NodeShape) not in sqe_alone

    def test_resolve_imports_with_local_loader_closes_the_gap(self):
        from rdflib import RDF
        from rdflib import Namespace as RdfNamespace
        SH = RdfNamespace("http://www.w3.org/ns/shacl#")
        SPEXPR = RdfNamespace("https://github.com/hidden-graph/starlayer/ns/sparql/expr#")

        sqe_alone = starontology.get_ontology_graph("sqe_shacl")
        merged = sqe_alone.resolve_imports(loader=starontology.local_loader, mode="full")

        assert (SPEXPR.ExpressionShape, RDF.type, SH.NodeShape) in merged
        assert len(merged) > len(sqe_alone)

    def test_srl_shacl_also_resolves_its_spexpr_import(self):
        from rdflib import RDF
        from rdflib import Namespace as RdfNamespace
        SH = RdfNamespace("http://www.w3.org/ns/shacl#")
        SPEXPR = RdfNamespace("https://github.com/hidden-graph/starlayer/ns/sparql/expr#")

        srl_alone = starontology.get_ontology_graph("srl_shacl")
        merged = srl_alone.resolve_imports(loader=starontology.local_loader, mode="full")

        assert (SPEXPR.ExpressionShape, RDF.type, SH.NodeShape) in merged

    def test_entries_with_no_owl_imports_are_unaffected(self):
        """skos_shacl declares no owl:imports at all - resolve_imports()
        with local_loader must be a safe no-op, not an error."""
        skos_alone = starontology.get_ontology_graph("skos_shacl")
        merged = skos_alone.resolve_imports(loader=starontology.local_loader, mode="full")
        assert set(merged) == set(skos_alone)


