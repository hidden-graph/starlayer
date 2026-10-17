"""starlayer.shacl.asset_urls - where to actually fetch this package's own
bundled SHACL assets from, as real GitHub URLs.

Unlike starontology's 13 registered ontology/shapes entries (consolidated
into one starontology.trig dataset - see that package's own get_raw_url()
for the publish-step story that makes its URLs real), the file
here is already a real, standalone file on disk - no publish step
needed, this module just mints the right URL for each.
"""

from __future__ import annotations

_GITHUB_RAW_BASE = "https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/shacl/assets/"

_FILENAME_BY_NAME = {
    "conformance_profile": "shacl12-conformance-profile.ttl",
}


def get_raw_url(name: str) -> str | None:
    """A ``raw.githubusercontent.com`` URL for one of this package's own
    bundled SHACL asset files - real, fetchable content (unlike a GitHub
    blob URL, which returns an HTML viewer page to a plain HTTP GET).

    Args:
        name: ``"conformance_profile"``.

    Returns:
        The raw URL, or ``None`` for an unrecognized name.
    """
    filename = _FILENAME_BY_NAME.get(name)
    if filename is None:
        return None
    return _GITHUB_RAW_BASE + filename
