import pytest
from starlayer.shacl.validation_modes import (
    available_modes,
    get_mode,
    resolve_mode_options,
)


def test_available_modes_contains_expected_defaults() -> None:
    found = set(available_modes())
    assert {"validation", "rules", "debug"}.issubset(found)


def test_get_mode_returns_known_mode() -> None:
    mode = get_mode("rules")
    assert mode.name == "rules"
    assert mode.options["rules"] is True
    assert "advanced" not in mode.options
    assert mode.options["inplace"] is True


def test_get_mode_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown validation mode"):
        get_mode("nope")


def test_resolve_mode_allows_overrides() -> None:
    options = resolve_mode_options("rules", overrides={"rules": None})
    assert options["rules"] is None


def test_no_preset_sets_the_deprecated_advanced_option() -> None:
    assert all("advanced" not in get_mode(name).options for name in available_modes())
