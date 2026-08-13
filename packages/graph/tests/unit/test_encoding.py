"""
Tests for starlayergraph.model.encoding — tt_hash() and the _TT_HASH_MEMO cache.
"""

from rdflib import URIRef

from starlayergraph.model import encoding


def test_tt_hash_is_16_hex_chars():
    h = encoding.tt_hash('http://example.org/s', 'http://example.org/p', 'http://example.org/o')
    assert len(h) == 16
    int(h, 16)  # must be valid hex


def test_tt_hash_deterministic_and_content_sensitive():
    h1 = encoding.tt_hash('s', 'p', 'o')
    h2 = encoding.tt_hash('s', 'p', 'o')
    h3 = encoding.tt_hash('s', 'p', 'x')
    assert h1 == h2
    assert h1 != h3


def test_tt_hash_memo_remember_and_lookup_roundtrip():
    uri = URIRef('http://example.org/tt#test-roundtrip')
    encoding.remember_tt_hash(uri, URIRef('a'), URIRef('b'), URIRef('c'))
    assert encoding.lookup_tt_hash(uri) == (URIRef('a'), URIRef('b'), URIRef('c'))
    assert encoding.lookup_tt_hash(URIRef('http://example.org/tt#never-remembered')) is None


def test_tt_hash_memo_is_bounded_lru(monkeypatch):
    # Cap the memo down to a small size so eviction is observable without
    # inserting 100,000 real entries. remember_tt_hash/lookup_tt_hash read
    # _TT_HASH_MEMO_MAXSIZE from module scope on every call, so patching the
    # module attribute is sufficient - no need to reconstruct the module.
    monkeypatch.setattr(encoding, '_TT_HASH_MEMO_MAXSIZE', 3)
    encoding._TT_HASH_MEMO.clear()

    uris = [URIRef(f'http://example.org/tt#{i}') for i in range(5)]
    for i, uri in enumerate(uris):
        encoding.remember_tt_hash(uri, i, i, i)

    # Only the 3 most recently inserted survive; the oldest 2 were evicted.
    assert len(encoding._TT_HASH_MEMO) == 3
    assert encoding.lookup_tt_hash(uris[0]) is None
    assert encoding.lookup_tt_hash(uris[1]) is None
    assert encoding.lookup_tt_hash(uris[4]) == (4, 4, 4)


def test_tt_hash_memo_lookup_refreshes_lru_order(monkeypatch):
    monkeypatch.setattr(encoding, '_TT_HASH_MEMO_MAXSIZE', 2)
    encoding._TT_HASH_MEMO.clear()

    a, b, c = (URIRef('http://example.org/tt#a'), URIRef('http://example.org/tt#b'),
               URIRef('http://example.org/tt#c'))
    encoding.remember_tt_hash(a, 1, 1, 1)
    encoding.remember_tt_hash(b, 2, 2, 2)
    # Touch 'a' so it becomes the most-recently-used, ahead of 'b'.
    encoding.lookup_tt_hash(a)
    # Inserting a third entry should now evict 'b' (least recently used), not 'a'.
    encoding.remember_tt_hash(c, 3, 3, 3)

    assert encoding.lookup_tt_hash(a) == (1, 1, 1)
    assert encoding.lookup_tt_hash(b) is None
    assert encoding.lookup_tt_hash(c) == (3, 3, 3)
