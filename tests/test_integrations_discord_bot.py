from warden.integrations.discord_bot import NOT_AUTHORIZED, UNKNOWN_COMMAND, BotCommands, DiscordBotRunner


def make(allowed="12345"):
    calls = []
    return BotCommands(
        allowed_user_id=allowed,
        get_status=lambda: "IN_MATCH, 5.2h/24h",
        on_pause=lambda: calls.append("pause"),
        on_resume=lambda: calls.append("resume"),
        on_stop=lambda: calls.append("stop"),
        on_screenshot=lambda: (calls.append("screenshot"), "saved.png")[1],
    ), calls


def test_unauthorized_user_is_rejected():
    bot, calls = make()
    assert bot.handle("status", "99999") == NOT_AUTHORIZED
    assert calls == []


def test_authorized_user_gets_status():
    bot, calls = make()
    assert bot.handle("status", "12345") == "IN_MATCH, 5.2h/24h"


def test_authorized_user_can_pause_resume_stop():
    bot, calls = make()
    assert bot.handle("pause", 12345) == "Paused."  # int form also matches via str()
    assert bot.handle("resume", "12345") == "Resumed."
    assert bot.handle("stop", "12345") == "Stopped."
    assert calls == ["pause", "resume", "stop"]


def test_screenshot_returns_handler_result():
    bot, calls = make()
    assert bot.handle("screenshot", "12345") == "saved.png"
    assert calls == ["screenshot"]


def test_unknown_command():
    bot, calls = make()
    assert bot.handle("nuke", "12345") == UNKNOWN_COMMAND


def test_slash_prefix_is_stripped():
    bot, calls = make()
    assert bot.handle("/pause", "12345") == "Paused."


def test_handler_exception_is_caught_and_reported():
    bot = BotCommands("1", lambda: "ok", lambda: (_ for _ in ()).throw(RuntimeError("boom")),
                      lambda: None, lambda: None, lambda: "x")
    result = bot.handle("pause", "1")
    assert "Command failed" in result


def test_no_allowed_id_configured_rejects_everyone():
    bot, calls = make(allowed="")
    assert bot.handle("status", "anyone") == NOT_AUTHORIZED


def test_runner_reports_unavailable_without_discord_py(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "discord":
            raise ImportError("no discord.py")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    bot, _ = make()
    runner = DiscordBotRunner("token", bot)
    assert runner.available() is False
