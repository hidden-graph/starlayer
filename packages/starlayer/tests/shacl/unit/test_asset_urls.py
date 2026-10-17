"""Tests for starlayer.shacl.asset_urls - real raw.githubusercontent.com
URLs for this package's own bundled SHACL asset files, which
is already a real, standalone file on disk (unlike starontology's
consolidated entries) - so this is pure URL-minting, no publish step or
isomorphism check needed, just confirming the implied path is real.
"""

from pathlib import Path

from starlayer.shacl import asset_urls

_ASSETS_DIR = Path(__file__).resolve().parents[3] / "starlayer" / "shacl" / "assets"
_RAW_BASE = "https://raw.githubusercontent.com/hidden-graph/starlayer/main/packages/starlayer/starlayer/shacl/assets/"


def _published_path(name: str) -> Path:
    url = asset_urls.get_raw_url(name)
    filename = url[len(_RAW_BASE) :]
    return _ASSETS_DIR / filename


class TestGetRawUrl:
    def test_is_a_real_raw_githubusercontent_url(self):
        url = asset_urls.get_raw_url("conformance_profile")
        assert url == _RAW_BASE + "shacl12-conformance-profile.ttl"

    def test_supplementary_shapes_are_not_published(self):
        # shacl12-shacl.ttl (starontology) is the published meta-shapes graph;
        # the two supplementary source files are internal.
        for name in ("presentation_shapes", "validation_shapes"):
            assert asset_urls.get_raw_url(name) is None

    def test_unknown_name_returns_none(self):
        assert asset_urls.get_raw_url("not_a_real_name") is None


class TestPublishedFiles:
    def test_every_asset_url_resolves_to_a_real_file_on_disk(self):
        for name in ("conformance_profile",):
            path = _published_path(name)
            assert path.is_file(), f"{name}: no file at {path}"
