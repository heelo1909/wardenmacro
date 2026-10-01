from warden.platform.power import ES_CONTINUOUS, ES_DISPLAY_REQUIRED, ES_SYSTEM_REQUIRED, SleepGuard


class FakeKernel32:
    """Stands in for ctypes.windll.kernel32 - no real power state touched."""

    def __init__(self):
        self.calls = []

    def SetThreadExecutionState(self, flags):
        self.calls.append(flags)
        return 1  # non-zero = success, matches the real API


def test_acquire_sets_continuous_system_and_display_flags(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr("ctypes.windll.kernel32", fake, raising=False)
    guard = SleepGuard(keep_display_on=True)
    assert guard.acquire() is True
    assert guard.active is True
    assert fake.calls[-1] == ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED


def test_acquire_without_display_flag(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr("ctypes.windll.kernel32", fake, raising=False)
    guard = SleepGuard(keep_display_on=False)
    guard.acquire()
    assert fake.calls[-1] == ES_CONTINUOUS | ES_SYSTEM_REQUIRED


def test_release_restores_plain_continuous_and_clears_active(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr("ctypes.windll.kernel32", fake, raising=False)
    guard = SleepGuard()
    guard.acquire()
    guard.release()
    assert fake.calls[-1] == ES_CONTINUOUS
    assert guard.active is False


def test_release_without_prior_acquire_does_nothing(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr("ctypes.windll.kernel32", fake, raising=False)
    guard = SleepGuard()
    guard.release()
    assert fake.calls == []


def test_failed_acquire_reports_inactive(monkeypatch):
    class FailingKernel32:
        def SetThreadExecutionState(self, flags):
            return 0

    monkeypatch.setattr("ctypes.windll.kernel32", FailingKernel32(), raising=False)
    guard = SleepGuard()
    assert guard.acquire() is False
    assert guard.active is False


def test_context_manager_acquires_and_releases(monkeypatch):
    fake = FakeKernel32()
    monkeypatch.setattr("ctypes.windll.kernel32", fake, raising=False)
    with SleepGuard() as guard:
        assert guard.active is True
    assert guard.active is False
    assert fake.calls[-1] == ES_CONTINUOUS


def test_non_windows_platform_is_a_safe_noop(monkeypatch):
    import warden.platform.power as power_mod

    monkeypatch.setattr(power_mod.sys, "platform", "linux")
    guard = SleepGuard()
    assert guard.acquire() is False
    guard.release()  # must not raise
