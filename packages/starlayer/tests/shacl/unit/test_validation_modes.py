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
    assert mode.options["advanced"] is True
    assert mode.options["inplace"] is True


def test_get_mode_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown validation mode"):
        get_mode("nope")


def test_resolve_mode_allows_overrides() -> None:
    options = resolve_mode_options("rules", overrides={"iterate_rules": False})
    assert options["advanced"] is True
    assert options["iterate_rules"] is False
