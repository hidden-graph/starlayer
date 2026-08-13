import pytest

from starshacl.profiles import available_profiles, get_profile, resolve_profile_options


def test_available_profiles_contains_expected_defaults() -> None:
    found = set(available_profiles())
    assert {"validation", "rules", "debug"}.issubset(found)


def test_get_profile_returns_known_profile() -> None:
    profile = get_profile("rules")
    assert profile.name == "rules"
    assert profile.options["advanced"] is True
    assert profile.options["inplace"] is True


def test_get_profile_rejects_unknown_name() -> None:
    with pytest.raises(ValueError, match="Unknown validation profile"):
        get_profile("nope")


def test_resolve_profile_allows_overrides() -> None:
    options = resolve_profile_options("rules", overrides={"iterate_rules": False})
    assert options["advanced"] is True
    assert options["iterate_rules"] is False
