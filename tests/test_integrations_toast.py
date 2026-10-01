from warden.integrations.toast import ToastNotifier


class FakeNotification:
    shown = []

    def __init__(self, app_id, title, msg, duration="short"):
        self.app_id, self.title, self.msg = app_id, title, msg

    def show(self):
        FakeNotification.shown.append((self.app_id, self.title, self.msg))


def test_notify_calls_backend_and_shows():
    FakeNotification.shown.clear()
    notifier = ToastNotifier(backend_factory=lambda: FakeNotification)
    assert notifier.notify("Milestone", "4h reached") is True
    assert FakeNotification.shown == [("Warden", "Milestone", "4h reached")]


def test_disabled_never_calls_backend():
    calls = []
    notifier = ToastNotifier(enabled=False, backend_factory=lambda: calls.append(1) or None)
    assert notifier.notify("x", "y") is False
    assert calls == []


def test_missing_dependency_degrades_gracefully():
    notifier = ToastNotifier(backend_factory=lambda: None)
    assert notifier.available() is False
    assert notifier.notify("x", "y") is False


def test_backend_exception_is_caught():
    class Broken:
        def __init__(self, **kw):
            pass

        def show(self):
            raise RuntimeError("no notification center")

    notifier = ToastNotifier(backend_factory=lambda: Broken)
    assert notifier.notify("x", "y") is False


def test_available_reflects_backend_presence():
    assert ToastNotifier(backend_factory=lambda: FakeNotification).available() is True
    assert ToastNotifier(backend_factory=lambda: None).available() is False
