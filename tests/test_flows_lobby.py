from warden.flows.lobby import ModeSelectSearch


class FakeActions:
    def __init__(self):
        self.clicks = 0
        self.scrolls = 0

    def click_ffa(self):
        self.clicks += 1

    def scroll_mode_list(self):
        self.scrolls += 1


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
