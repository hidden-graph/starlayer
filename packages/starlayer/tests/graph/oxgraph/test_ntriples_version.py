"""``StarLayerGraph`` / ``StarLayerDataset.parse`` accept the N-Triples / N-Quads ``VERSION`` directive (``oxgraph/ntversion.py``)."""

from __future__ import annotations

import io

import pytest
from starlayer.graph.oxgraph.core import StarLayerDataset, StarLayerGraph

T = '<http://e/a> <http://e/b> "x" .\n'
BAD_T = "<http://e/a> <http://e/b> .\n"  # a missing object


@pytest.mark.parametrize("directive", [
    'VERSION "1.2"', 'VERSION   "1.2"', 'VERSION\t"1.2"', '  VERSION "1.2"', 'VERSION "1.2" # a comment', 'VERSION "1.2"   ',
    'VERSION "1.3-draft"', 'VERSION "\\u0031.2"', 'VERSION ""',
])
def test_valid_directive_forms(directive: str) -> None:
    g = StarLayerGraph().parse(data=f"{directive}\n{T}", format="nt")
    assert len(g) == 1


def test_directive_anywhere_between_statements_and_repeated() -> None:
    g = StarLayerGraph().parse(data=f'{T}VERSION "1.2"\n<http://e/c> <http://e/b> "y" .\nVERSION "1.2"', format="nt")
    assert len(g) == 2


@pytest.mark.parametrize("eol", ["\n", "\r\n", "\r"])
def test_line_endings(eol: str) -> None:
    g = StarLayerGraph().parse(data=f'VERSION "1.2"{eol}{T.strip()}{eol}', format="nt")
    assert len(g) == 1


def test_nquads_and_dataset() -> None:
    ds = StarLayerDataset().parse(data='VERSION "1.2"\n<http://e/a> <http://e/b> "x" <http://e/g> .\n', format="nquads")
    assert len(ds) == 1


@pytest.mark.parametrize("directive", [
    "VERSION 1.2", "VERSION <http://example.org/version-1.2>", "VERSION '1.2'", 'VERSION "1.2" .', 'VERSION "1.2" "1.3"',
    'VERSION "1.2', "VERSION", 'VERSION "a\\qb"', 'VERSIONS "1.2"',
])
def test_malformed_directive_is_rejected_by_the_directive_check(directive: str) -> None:
    with pytest.raises(SyntaxError, match="VERSION directive"):
        StarLayerGraph().parse(data=f"{directive}\n{T}", format="nt")


@pytest.mark.parametrize("text", ['version "1.2"\n', 'Version "1.2"\n', '@version "1.2" .\n', 'VERSION"1.2"x\n'])
def test_not_a_directive_is_still_a_syntax_error(text: str) -> None:
    with pytest.raises(SyntaxError):
        StarLayerGraph().parse(data=text + T, format="nt")


def test_error_positions_keep_the_original_line_numbers() -> None:
    with pytest.raises(SyntaxError) as e:
        StarLayerGraph().parse(data=f'VERSION "1.2"\n{T}VERSION "1.2"\n{BAD_T}', format="nt")
    assert (e.value.args[1][1], "line 4 column 27") == (4, "line 4 column 27") and "line 4 column" in str(e.value)  # the bad statement is on line 4 of the original text
    with pytest.raises(SyntaxError) as e:
        StarLayerGraph().parse(data=f'{T}\nVERSION 1.2\n', format="nt")
    assert "line 3 column 1" in str(e.value) and e.value.args[1][1:3] == (3, 1)


def test_path_and_stream_sources(tmp_path) -> None:
    f = tmp_path / "d.nt"
    f.write_text(f'VERSION "1.2"\n{T}', encoding="utf-8")
    assert len(StarLayerGraph().parse(str(f))) == 1
    assert len(StarLayerGraph().parse(file=io.BytesIO(f.read_bytes()), format="nt")) == 1
    assert len(StarLayerGraph().parse(file=io.StringIO(f.read_text()), format="nt")) == 1
    bad = tmp_path / "b.nt"
    bad.write_text(f'VERSION "1.2"\n{T}{T.replace("a>", "c>")}VERSION 7\n', encoding="utf-8")
    with pytest.raises(SyntaxError, match="line 4 column 1"):
        StarLayerGraph().parse(str(bad))


def test_large_stream_crossing_chunk_boundaries() -> None:
    lines = [f'<http://e/s{i}> <http://e/p> "{i}" .\n' for i in range(60000)]
    lines.insert(30000, 'VERSION "1.2"\n')
    lines.insert(45000, "VERSION 1.2\n")
    with pytest.raises(SyntaxError, match="line 45001 column 1"):
        StarLayerGraph().parse(file=io.BytesIO("".join(lines).encode()), format="nt")
    del lines[45000]
    assert len(StarLayerGraph().parse(file=io.BytesIO("".join(lines).encode()), format="nt")) == 60000


def test_turtle_is_unchanged() -> None:
    assert len(StarLayerGraph().parse(data=f'VERSION "1.2"\n{T}', format="turtle")) == 1
