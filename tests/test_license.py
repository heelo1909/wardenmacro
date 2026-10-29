from warden.config.schema import LicenseConfig
from warden.flows.license import LicenseState, has_access, load_state, save_state, verify_and_activate


class FakeVerifier:
    """Maps a permalink to the Gumroad-shaped response it should return.
    ``calls`` records every (permalink, key) pair actually sent, so a test
    can assert the lifetime permalink was never tried once pass succeeded.
    """

    def __init__(self, responses: dict[str, dict], fail: bool = False):
        self.responses = responses
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def __call__(self, permalink: str, key: str) -> dict:
        self.calls.append((permalink, key))
        if self.fail:
            raise ConnectionError("no network")
        return self.responses.get(permalink, {"success": False, "message": "This license does not exist."})


def config(**kw) -> LicenseConfig:
    base = dict(enabled=True, pass_permalink="warden-24h", lifetime_permalink="warden-lifetime", pass_hours=24)
    base.update(kw)
    return LicenseConfig(**base)


# --------------------------------------------------------------------------- verify_and_activate


def test_blank_key_is_rejected_without_calling_the_verifier():
    verifier = FakeVerifier({})
    result = verify_and_activate("   ", config(), verifier=verifier)
    assert result.ok is False
    assert verifier.calls == []


def test_no_permalinks_configured_is_rejected_without_calling_the_verifier():
    verifier = FakeVerifier({})
    result = verify_and_activate("ABCD-1234", config(pass_permalink="", lifetime_permalink=""), verifier=verifier)
    assert result.ok is False
    assert "configured" in result.message
    assert verifier.calls == []


def test_fresh_pass_key_activates_as_pass_tier():
    verifier = FakeVerifier({"warden-24h": {"success": True, "uses_count": 1}})
    result = verify_and_activate("ABCD-1234", config(), verifier=verifier)
    assert result.ok is True
    assert result.tier == "pass"
    assert verifier.calls == [("warden-24h", "ABCD-1234")]  # lifetime never tried once pass matched


def test_fresh_lifetime_key_falls_through_after_pass_rejects_it():
    verifier = FakeVerifier({
        "warden-24h": {"success": False, "message": "This license does not exist for the provided product."},
        "warden-lifetime": {"success": True, "uses_count": 1},
    })
    result = verify_and_activate("WXYZ-9999", config(), verifier=verifier)
    assert result.ok is True
    assert result.tier == "lifetime"
    assert [c[0] for c in verifier.calls] == ["warden-24h", "warden-lifetime"]


def test_already_used_key_is_refused():
    verifier = FakeVerifier({"warden-24h": {"success": True, "uses_count": 2}})
    result = verify_and_activate("SHARED-KEY", config(), verifier=verifier)
    assert result.ok is False
    assert "already been activated" in result.message


def test_unrecognized_key_is_refused_with_gumroads_own_message():
    verifier = FakeVerifier({
        "warden-24h": {"success": False, "message": "This license does not exist for the provided product."},
        "warden-lifetime": {"success": False, "message": "This license does not exist for the provided product."},
    })
    result = verify_and_activate("MADE-UP", config(), verifier=verifier)
    assert result.ok is False
    assert "does not exist" in result.message


def test_network_failure_is_reported_not_raised():
    verifier = FakeVerifier({}, fail=True)
    result = verify_and_activate("ABCD-1234", config(), verifier=verifier)
    assert result.ok is False
    assert "Couldn't reach" in result.message


# --------------------------------------------------------------------------- has_access


def test_disabled_licensing_always_grants_access_without_any_state():
    assert has_access(LicenseState(), config(enabled=False)) is True


def test_unactivated_state_has_no_access_when_enabled():
    assert has_access(LicenseState(), config()) is False


def test_lifetime_tier_never_expires():
    state = LicenseState(key="K", tier="lifetime", activated_at=0.0, device_confirmed=True)
    assert has_access(state, config(), now=10_000_000.0) is True


def test_pass_tier_expires_after_its_window():
    state = LicenseState(key="K", tier="pass", activated_at=0.0, device_confirmed=True)
    cfg = config(pass_hours=24)
    assert has_access(state, cfg, now=23 * 3600) is True
    assert has_access(state, cfg, now=25 * 3600) is False


# --------------------------------------------------------------------------- state persistence


def test_load_state_with_no_file_returns_a_fresh_unactivated_state(tmp_path):
    state = load_state(tmp_path)
    assert state == LicenseState()


def test_load_state_tolerates_a_corrupt_file(tmp_path):
    bad = tmp_path / "license.yaml"
    bad.write_text("not: [valid, {jason: true", encoding="utf-8")
    assert load_state(tmp_path) == LicenseState()


def test_save_then_load_round_trips(tmp_path):
    state = LicenseState(key="ABCD-1234", tier="lifetime", activated_at=123.0, device_confirmed=True)
    save_state(tmp_path, state)
    assert load_state(tmp_path) == state
