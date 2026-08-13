from rdflib import Namespace

from starshacl.adapters import TripleTermGraph


EX = Namespace("http://example.org/")


def test_add_keeps_unique_triples() -> None:
    g = TripleTermGraph()
    triple = (EX.s, EX.p, EX.o)

    g.add(triple)
    g.add(triple)

    assert list(g) == [triple]


def test_remove_pattern_clears_only_matches() -> None:
    g = TripleTermGraph(
        triples=[
            (EX.s1, EX.p, EX.o),
            (EX.s2, EX.p, EX.o),
            (EX.s3, EX.other, EX.o),
        ]
    )

    g.remove((None, EX.p, EX.o))

    assert (EX.s1, EX.p, EX.o) not in g
    assert (EX.s2, EX.p, EX.o) not in g
    assert (EX.s3, EX.other, EX.o) in g


def test_remove_all_pattern_clears_graph() -> None:
    g = TripleTermGraph(triples=[(EX.s, EX.p, EX.o)])

    g.remove((None, None, None))

    assert list(g) == []
