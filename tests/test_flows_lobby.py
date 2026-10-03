from warden.flows.lobby import ModeSelectSearch


class FakeActions:
    """By default every action succeeds, like a healthy, focused game window."""

    def __init__(self, scrolls_ok=True, clicks_ok=True):
        self.clicks = 0
        self.scrolls = 0
        self.scrolls_ok = scrolls_ok
        self.clicks_ok = clicks_ok

    def click_ffa(self):
        self.clicks += 1
        return self.clicks_ok

    def scroll_mode_list(self):
        self.scrolls += 1
        return self.scrolls_ok


def test_clicks_ffa_once_when_visible_and_does_not_reclick_every_tick():
    actions = FakeActions()
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0])
    search.tick(True, now=0.0)
    search.tick(True, now=0.1)
    assert actions.clicks == 1


def test_scrolls_with_cooldown_while_ffa_not_visible():
    actions = FakeActions()
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], scroll_cooldown_s=1.0)
    search.tick(False, now=0.0)
    search.tick(False, now=0.5)  # inside cooldown, no scroll
    search.tick(False, now=1.1)  # cooldown elapsed
    assert actions.scrolls == 2


def test_gives_up_scrolling_after_max_attempts():
    actions = FakeActions()
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], max_attempts=2, scroll_cooldown_s=0.1)
    for i in range(10):
        search.tick(False, now=i * 0.2)
    assert actions.scrolls == 2


def test_reset_allows_scrolling_again():
    actions = FakeActions()
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], max_attempts=1, scroll_cooldown_s=0.0)
    search.tick(False, now=0.0)
    search.tick(False, now=0.1)
    assert actions.scrolls == 1
    search.reset()
    search.tick(False, now=0.2)
    assert actions.scrolls == 2


def test_click_flag_resets_if_ffa_disappears_then_reappears():
    actions = FakeActions()
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0])
    search.tick(True, now=0.0)
    search.tick(False, now=0.1)
    search.tick(True, now=0.2)
    assert actions.clicks == 2


def test_a_blocked_scroll_does_not_spend_the_attempt_budget():
    """2026-10-03 user report: the FFA scroll gets 'stuck in a loop' - a
    focus hiccup blocked every scroll, but the old code counted each blocked
    attempt against the same 12-try budget as a real scroll, so the whole
    budget burned down doing nothing and mode-select just went quiet."""
    actions = FakeActions(scrolls_ok=False)
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], max_attempts=2, scroll_cooldown_s=1.0)
    for i in range(20):
        search.tick(False, now=i * 0.2)
    assert actions.scrolls > 2          # kept trying - never silently gave up
    assert search.attempts == 0         # none of those attempts ever actually landed


def test_a_blocked_scroll_retries_sooner_than_the_normal_cooldown():
    actions = FakeActions(scrolls_ok=False)
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], scroll_cooldown_s=1.0, retry_cooldown_s=0.2)
    search.tick(False, now=0.0)
    search.tick(False, now=0.25)  # well under the 1.0s cooldown, past the 0.2s retry cooldown
    assert actions.scrolls == 2


def test_scrolling_resumes_once_blocks_clear_up():
    actions = FakeActions(scrolls_ok=False)
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], max_attempts=5, scroll_cooldown_s=1.0,
                              retry_cooldown_s=0.1)
    search.tick(False, now=0.0)
    search.tick(False, now=0.1)  # still blocked
    assert search.attempts == 0
    actions.scrolls_ok = True  # focus recovered
    search.tick(False, now=0.2)
    assert search.attempts == 1
    assert actions.scrolls == 3


def test_a_blocked_ffa_click_is_retried_not_abandoned():
    actions = FakeActions(clicks_ok=False)
    t = [0.0]
    search = ModeSelectSearch(actions, clock=lambda: t[0], click_interval_s=2.5)
    search.tick(True, now=0.0)
    search.tick(True, now=0.05)  # blocked click shouldn't arm the long click_interval wait
    assert actions.clicks == 2
