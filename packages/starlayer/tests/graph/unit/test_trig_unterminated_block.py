"""An unterminated graph block ends the parse; it does not send the splitter back to the start of the text, forever."""

import signal

import pytest
from starlayer.graph.graph.starlayer_dataset import StarLayerDataset
from starlayer.graph.parsers.trig12 import (
    _consume_balanced,
    _split_trig_blocks_with_ids,
)


@pytest.fixture(autouse=True)
def _fail_instead_of_hanging():
    def timed_out(*_args):
        raise AssertionError("the splitter did not return")

    previous = signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(10)
    yield
    signal.alarm(0)
    signal.signal(signal.SIGALRM, previous)


@pytest.mark.parametrize(
    "text",
    [
        "ex:n { ex:p ex:o . # a comment on the last line, no newline",
        "ex:n { ex:p <http://example.org/unterminated .",
        'GRAPH <http://example.org/g> { ex:a ex:p "never closed" .',
        "GRAPH <http://example.org/g> { ex:a ex:p ex:b .\n# comment\n",
    ],
)
def test_an_unterminated_block_is_split_without_looping(text):
    chunks = _split_trig_blocks_with_ids(text)
    assert chunks  # the open block is returned as what it is, up to the end of the text


def test_consume_balanced_stops_at_the_end_of_an_unterminated_block():
    block, end = _consume_balanced("{ ex:a ex:p ex:b . # trailing comment", 0)
    assert end == len("{ ex:a ex:p ex:b . # trailing comment")
    assert block.startswith("{ ex:a")
    block, end = _consume_balanced("{ ex:a ex:p <http://x", 0)
    assert end == len("{ ex:a ex:p <http://x")


def test_parsing_an_unterminated_block_returns():
    dataset = StarLayerDataset()
    dataset.parse(data="GRAPH <http://example.org/g> { <http://e/a> <http://e/p> <http://e/b> . # no close", format="trig12")
    assert isinstance(len(dataset), int)  # it returned; what it read of the open block is not the point here
