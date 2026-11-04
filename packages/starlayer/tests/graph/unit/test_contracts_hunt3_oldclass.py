"""test_contracts_hunt3: tests of the hand-written Turtle splitter (parsers/syntax.py), deleted with it at D1."""

import time

from starlayer.graph.parsers.syntax import split_statements_with_lines


def test_split_statements_line_numbers():
    text = "@prefix : <http://e/> .\n:a :p :b .\n\n:c :p :d .\n"
    assert [line for _, line in split_statements_with_lines(text)] == [1, 2, 4]


def test_split_statements_line_numbers_do_not_rescan_the_prefix(monkeypatch):
    from starlayer.graph.parsers import syntax

    line = ":s :p :o .\n"
    document = line * 100_000
    # Hand the line counter many statement offsets without the (separately linear) splitter: counting newlines from the
    # start of the document for every statement is quadratic, about 5 GB of scanning here.
    monkeypatch.setattr(syntax, "_split_statements_impl", lambda data: ((":s :p :o", i * len(line)) for i in range(100_000)))
    start = time.perf_counter()
    pairs = split_statements_with_lines(document)
    assert time.perf_counter() - start < 3
    assert pairs[-1][1] == 100_000


