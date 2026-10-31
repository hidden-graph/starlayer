"""The minimum-pyoxigraph check (``starlayer.graph.backends._versions``). No engine needed."""
import pytest

from starlayer.graph.backends import _versions
from starlayer.graph.backends._versions import check_pyoxigraph_version, require_supported_pyoxigraph


@pytest.mark.parametrize('version', ['0.5.13', '0.5.14', '0.6.0', '1.0.0', 'v0.5.13', '0.5.13-rc1', '0.5.13.dev0'])
def test_supported_versions_pass(version):
    check_pyoxigraph_version(version)


@pytest.mark.parametrize('version', ['0.5.12', '0.5.0', '0.4.9', '0.0.1', 'junk', '', None, '0.5'])
def test_older_or_unreadable_versions_raise(version):
    with pytest.raises(ImportError, match=r'pyoxigraph >= 0\.5\.13.*oxigraph#1982'):
        check_pyoxigraph_version(version)


def test_the_installed_pyoxigraph_is_supported():
    require_supported_pyoxigraph.cache_clear()
    require_supported_pyoxigraph()


def test_the_installed_version_is_read_from_pyoxigraph(monkeypatch):
    import pyoxigraph
    require_supported_pyoxigraph.cache_clear()
    monkeypatch.setattr(pyoxigraph, '__version__', '0.5.12')
    try:
        with pytest.raises(ImportError, match='found .0.5.12.'):
            require_supported_pyoxigraph()
        monkeypatch.delattr(pyoxigraph, '__version__')
        require_supported_pyoxigraph.cache_clear()
        with pytest.raises(ImportError, match='pyoxigraph >= 0.5.13'):
            require_supported_pyoxigraph()
    finally:
        monkeypatch.undo()
        require_supported_pyoxigraph.cache_clear()


def test_the_check_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(_versions, 'check_pyoxigraph_version', calls.append)
    require_supported_pyoxigraph.cache_clear()
    try:
        require_supported_pyoxigraph()
        require_supported_pyoxigraph()
        assert len(calls) == 1
    finally:
        monkeypatch.undo()
        require_supported_pyoxigraph.cache_clear()
