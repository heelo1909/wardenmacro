import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from warden.integrations.lan_dashboard import create_app, ensure_pin, is_lan_only_bind  # noqa: E402


def make_client(pin="1234"):
    calls = []
    app = create_app(
        pin, get_status=lambda: {"state": "IN_MATCH", "hours": 5.2},
        on_pause=lambda: calls.append("pause"), on_resume=lambda: calls.append("resume"),
        on_stop=lambda: calls.append("stop"),
    )
    return TestClient(app), calls


def test_status_is_readable_without_a_pin():
    client, calls = make_client()
    resp = client.get("/api/status")
    assert resp.status_code == 200
    assert resp.json()["state"] == "IN_MATCH"


def test_pause_requires_the_correct_pin():
    client, calls = make_client(pin="1234")
    resp = client.post("/api/pause")  # no pin header at all
    assert resp.status_code == 401
    resp = client.post("/api/pause", headers={"X-Warden-Pin": "0000"})
    assert resp.status_code == 401
    assert calls == []


def test_correct_pin_allows_control():
    client, calls = make_client(pin="1234")
    resp = client.post("/api/pause", headers={"X-Warden-Pin": "1234"})
    assert resp.status_code == 200
    resp = client.post("/api/resume", headers={"X-Warden-Pin": "1234"})
    assert resp.status_code == 200
    resp = client.post("/api/stop", headers={"X-Warden-Pin": "1234"})
    assert resp.status_code == 200
    assert calls == ["pause", "resume", "stop"]


def test_ensure_pin_generates_one_when_blank(caplog):
    import logging

    with caplog.at_level(logging.WARNING):
        pin = ensure_pin("")
    assert pin.isdigit() and len(pin) == 6
    assert "generated" in caplog.text.lower()


def test_ensure_pin_keeps_a_configured_pin():
    assert ensure_pin("secret123") == "secret123"


@pytest.mark.parametrize("host,expected", [
    ("0.0.0.0", True), ("127.0.0.1", True), ("localhost", True),
    ("192.168.1.50", True), ("10.0.0.5", True), ("172.20.0.1", True),
    ("8.8.8.8", False), ("1.2.3.4", False), ("not-an-ip", False),
])
def test_is_lan_only_bind(host, expected):
    assert is_lan_only_bind(host) is expected
