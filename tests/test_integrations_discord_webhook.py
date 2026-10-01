from warden.integrations.discord_webhook import DiscordWebhook


class FakePoster:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, url, payload):
        self.calls.append((url, payload))
        if self.fail:
            raise ConnectionError("no network")


def make(url="https://discord.test/webhook", **kw):
    t = [0.0]
    poster = kw.pop("poster", FakePoster())
    hook = DiscordWebhook(url, clock=lambda: t[0], poster=poster, **kw)
    return hook, poster, t


def test_disabled_never_posts():
    hook, poster, t = make(enabled=False)
    assert hook.maybe_send_status("IN_MATCH", {}, 1.0, 24.0) is False
    assert hook.alert_disconnect("x") is False
    assert poster.calls == []


def test_empty_url_never_posts():
    hook, poster, t = make(url="")
    assert hook.alert_disconnect("x") is False
    assert poster.calls == []


def test_status_respects_interval():
    hook, poster, t = make(interval_min=1.0)  # 60s
    assert hook.maybe_send_status("LOBBY", {"respawns": 0}, 0.0, 24.0) is True
    t[0] = 30.0
    assert hook.maybe_send_status("LOBBY", {}, 0.0, 24.0) is False
    t[0] = 61.0
    assert hook.maybe_send_status("LOBBY", {}, 0.0, 24.0) is True
    assert len(poster.calls) == 2


def test_status_embed_includes_progress_fields():
    hook, poster, t = make()
    hook.maybe_send_status("IN_MATCH", {"respawns": 3, "reconnects": 1, "loadout_fixes": 2}, 5.0, 24.0)
    embed = poster.calls[0][1]["embeds"][0]
    values = {f["name"]: f["value"] for f in embed["fields"]}
    assert values["Respawns"] == "3"
    assert "5.00h" in values["Progress"]


def test_alert_disconnect_ignores_interval():
    hook, poster, t = make(interval_min=60.0)
    hook.alert_disconnect("modal confirmed")
    hook.alert_disconnect("modal confirmed again")
    assert len(poster.calls) == 2  # alerts are never throttled, unlike status


def test_recovery_result_alert_titles():
    hook, poster, t = make()
    hook.alert_recovery_result(True, 2, "normal relaunch")
    hook.alert_recovery_result(False, 4, "browser fallback")
    assert poster.calls[0][1]["embeds"][0]["title"] == "Recovery succeeded"
    assert poster.calls[1][1]["embeds"][0]["title"] == "Recovery failed"


def test_milestone_fires_once_per_threshold_crossing():
    hook, poster, t = make(milestone_hours=4.0)
    assert hook.check_milestone(3.9) is False
    assert hook.check_milestone(4.1) is True
    assert hook.check_milestone(4.5) is False  # still in the same 4h bucket
    assert hook.check_milestone(8.2) is True
    assert len(poster.calls) == 2


def test_milestone_disabled_when_zero():
    hook, poster, t = make(milestone_hours=0)
    assert hook.check_milestone(100.0) is False


def test_target_reached_fires_once():
    hook, poster, t = make()
    assert hook.check_target_reached(23.9, 24.0) is False
    assert hook.check_target_reached(24.1, 24.0) is True
    assert hook.check_target_reached(25.0, 24.0) is False  # already alerted
    assert len(poster.calls) == 1


def test_reset_session_state_allows_target_and_milestone_to_fire_again():
    hook, poster, t = make(milestone_hours=4.0)
    hook.check_milestone(5.0)
    hook.check_target_reached(25.0, 24.0)
    hook.reset_session_state()
    assert hook.check_milestone(5.0) is True
    assert hook.check_target_reached(25.0, 24.0) is True


def test_poster_exception_is_caught_and_reported_as_failure():
    hook, poster, t = make(poster=FakePoster(fail=True))
    assert hook.alert_disconnect("x") is False
