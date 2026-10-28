"""A constraint component is built once per shape, not once per focus node (slow parts hunt, sh:in over many nodes)."""

import rdflib
from starlayer import StarLayerGraph
from starlayer.shacl import validate

P = "@prefix ex: <http://example.org/> . @prefix sh: <http://www.w3.org/ns/shacl#> . "
N = 40


def _graph(ttl):
    g = StarLayerGraph()
    g.parse(data=ttl, format="turtle12")
    return g


def _shapes(list_size):
    members = " ".join(f'"v{i}"' for i in range(list_size))
    return _graph(P + f"ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:in ( {members} ) ] .")


def _data(bad_every=None):
    lines = []
    for i in range(N):
        value = "bad" if bad_every and i % bad_every == 0 else "v1"
        lines.append(f'ex:n{i} a ex:C ; ex:p "{value}" .')
    return _graph(P + "\n".join(lines))


def test_sh_in_list_is_walked_once_not_once_per_focus_node(monkeypatch):
    walked = []
    original = rdflib.Graph.items

    def counting_items(self, list):
        walked.append(list)
        return original(self, list)

    monkeypatch.setattr(rdflib.Graph, "items", counting_items)
    result = validate(_data(), _shapes(30), meta_shacl=False)
    assert result.conforms
    assert 0 < len(walked) < 5  # was one walk per focus node (40 here)


def test_results_are_unchanged_by_reusing_the_component():
    result = validate(_data(bad_every=4), _shapes(30), meta_shacl=False)
    assert not result.conforms
    focus_nodes = {str(o) for o in result.report_graph.objects(None, rdflib.URIRef("http://www.w3.org/ns/shacl#focusNode"))}
    assert focus_nodes == {f"http://example.org/n{i}" for i in range(0, N, 4)}


def test_a_changed_shapes_graph_is_not_served_from_an_earlier_run():
    data = _data()
    assert validate(data, _shapes(30), meta_shacl=False).conforms
    narrower = _graph(P + 'ex:S a sh:NodeShape ; sh:targetClass ex:C ; sh:property [ sh:path ex:p ; sh:in ( "other" ) ] .')
    assert not validate(data, narrower, meta_shacl=False).conforms
