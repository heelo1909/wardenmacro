from warden.platform.hotkeys import Hotkeys, to_pynput


def test_to_pynput_converts_function_keys_and_combos():
    assert to_pynput("F6") == "<f6>"
    assert to_pynput("ctrl+shift+s") == "<ctrl>+<shift>+s"
    assert to_pynput("m") == "m"


class FakeGlobalHotKeys:
    """Stands in for pynput.keyboard.GlobalHotKeys - no real OS hook installed."""

    instances = []

    def __init__(self, mapping):
        self.mapping = mapping
        self.daemon = None
        self.started = False
        self.stopped = False
        FakeGlobalHotKeys.instances.append(self)

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


def test_hotkeys_builds_pynput_mapping_and_skips_empty_bindings(monkeypatch):
    import pynput.keyboard as kb

    monkeypatch.setattr(kb, "GlobalHotKeys", FakeGlobalHotKeys)
    calls = []
    hk = Hotkeys({"F6": lambda: calls.append("start"), "": lambda: calls.append("never")})
    assert hk.start() is True
    listener = FakeGlobalHotKeys.instances[-1]
    assert set(listener.mapping) == {"<f6>"}
    listener.mapping["<f6>"]()  # the wrapped, exception-safe callback
    assert calls == ["start"]
    hk.stop()
    assert listener.stopped is True


def test_hotkeys_handler_exceptions_are_swallowed(monkeypatch, caplog):
    import logging

    import pynput.keyboard as kb

    monkeypatch.setattr(kb, "GlobalHotKeys", FakeGlobalHotKeys)

    def boom():
        raise RuntimeError("bad handler")

    hk = Hotkeys({"F8": boom})
    hk.start()
    listener = FakeGlobalHotKeys.instances[-1]
    with caplog.at_level(logging.ERROR):
        listener.mapping["<f8>"]()  # must not raise
    assert "hotkey handler failed" in caplog.text


def test_hotkeys_start_returns_false_if_pynput_unavailable(monkeypatch):
    import warden.platform.hotkeys as hotkeys_mod

    def broken_import():
        raise ImportError("no pynput")

    # Simulate the import failing inside start() without needing to uninstall the real package.
    monkeypatch.setattr(hotkeys_mod, "Hotkeys", hotkeys_mod.Hotkeys)  # sanity no-op
    hk = hotkeys_mod.Hotkeys({"F6": lambda: None})

    class _BrokenModule:
        def __getattr__(self, name):
            raise ImportError("no pynput")

    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pynput":
            raise ImportError("no pynput")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert hk.start() is False
