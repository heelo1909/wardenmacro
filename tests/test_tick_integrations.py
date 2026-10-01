"""Phase 7: TickLoop actually drives the webhook/toast integrations, not
just constructs them. observe_only forced per warden-testing-safety.
"""

import shutil

from warden.config import load_all
from warden.core.events import EventBus
from warden.core.state_machine import State
from warden.core.tick import TickLoop


def make_loop(bundled_config, tmp_path, monkeypatch):
    work = tmp_path / "config"
    shutil.copytree(bundled_config, work)
    monkeypatch.setenv("WARDEN_HOME", str(tmp_path / "home"))
    loaded = load_all(work / "default.yaml")
    loaded.app.observe_only = True
    loaded.app.integrations.discord_webhook.enabled = True
    loaded.app.integrations.discord_webhook.url = "https://discord.test/webhook"
    # DiscordWebhook's _last_status_at starts at -inf, so the very first
    # maybe_send_status() call always fires regardless of interval_min - no
    # need to shrink it for these single-bookkeep-call tests.
    return TickLoop(loaded.app, loaded.preset, EventBus())


def test_disconnect_incident_alerts_the_webhook_and_toasts(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    posted = []
    toasted = []
    loop.webhook.poster = lambda url, payload: posted.append(payload)
    loop.toasts.notify = lambda title, msg: toasted.append((title, msg)) or True

    loop._session_active = True
    loop.bus.emit("incident", "incident: disconnect", level="warn", cause="disconnect")

    assert any("Disconnected" in p["embeds"][0]["title"] for p in posted)
    assert toasted  # a toast fired too


def test_bookkeep_sends_periodic_status_and_stops_at_target(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    posted = []
    loop.webhook.poster = lambda url, payload: posted.append(payload)
    loop.preset.contract.target_hours = 0.001
    loop.preset.contract.auto_stop_at_target = True

    loop._in_match_seconds = 0.0
    loop._last_tick_monotonic = 0.0
    loop._incidents = []
    loop._session_active = True
    loop.persistence.start_session(loop.app.active_preset, loop.preset.contract.label, 0.001)

    loop._bookkeep(State.IN_MATCH, now=10.0)
    assert any("status" in p["embeds"][0]["title"].lower() for p in posted)
    assert loop.sm.state is State.STOPPED  # target reached -> scheduled stop fired


def test_milestone_and_target_toast_on_reaching_target(bundled_config, tmp_path, monkeypatch):
    loop = make_loop(bundled_config, tmp_path, monkeypatch)
    loop.webhook.poster = lambda url, payload: None  # check_target_reached must succeed for the toast to fire
    toasted = []
    loop.toasts.notify = lambda title, msg: toasted.append((title, msg)) or True
    loop.preset.contract.target_hours = 0.001
    loop.preset.contract.auto_stop_at_target = False  # isolate the toast from the auto-stop path

    loop._in_match_seconds = 0.0
    loop._last_tick_monotonic = 0.0
    loop._session_active = True
    loop.persistence.start_session(loop.app.active_preset, loop.preset.contract.label, 0.001)

    loop._bookkeep(State.IN_MATCH, now=10.0)
    assert any("Target reached" in msg for _, msg in toasted)
