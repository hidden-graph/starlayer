"""The Python example in the root README must keep running and printing what its
comments say."""

import io
import re
from contextlib import redirect_stdout
from pathlib import Path

README = Path(__file__).resolve().parents[3] / "README.md"


def test_the_readme_example_runs():
    code = re.search(r"```python\n(.*?)```", README.read_text(), re.S).group(1)
    out = io.StringIO()
    with redirect_stdout(out):
        exec(compile(code, "README.md", "exec"), {})
    lines = out.getvalue().splitlines()
    assert lines == ["http://example.org/alice 0.9", "False"]
