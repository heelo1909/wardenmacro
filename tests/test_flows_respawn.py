from warden.flows.respawn import RespawnFlow


class FakeActions:
    def __init__(self):
        self.presses = 0
        self.reapplied = 0

    def press_respawn(self):
        self.presses += 1

    def reapply_loadout_if_due(self):
        self.reapplied += 1
        return True


def test_single_press_when_prompt_clears_quickly():
    actions = FakeActions()
    t = [0.0]
    flow = RespawnFlow(actions, clock=lambda: t[0], repress_s=1.5, switch_watch_s=6.0)
    assert flow.tick(respawn_visible=True, switch_visible=False, health_visible=False, now=t[0]) is False
    assert actions.presses == 1
    t[0] = 0.5
    # prompt gone already (respawned fast) -> move to watching, no re-press
    assert flow.tick(False, False, False, now=t[0]) is False
    assert actions.presses == 1


def test_repress_after_1_5s_if_prompt_still_visible():
    actions = FakeActions()
    t = [0.0]
    flow = RespawnFlow(actions, clock=lambda: t[0])
    flow.tick(True, False, False, now=0.0)
    t[0] = 1.0
    flow.tick(True, False, False, now=t[0])  # too soon
    assert actions.presses == 1
    t[0] = 1.6
    flow.tick(True, False, False, now=t[0])  # past 1.5s since first press
    assert actions.presses == 2


def test_switch_window_triggers_reapply_and_completes():
    actions = FakeActions()
    t = [0.0]
    flow = RespawnFlow(actions, clock=lambda: t[0])
    flow.tick(True, False, False, now=0.0)
    t[0] = 0.2
    flow.tick(False, False, False, now=t[0])  # respawned -> watching
    t[0] = 0.5
    done = flow.tick(False, True, False, now=t[0])  # switch window appears
    assert done is True
    assert actions.reapplied == 1


def test_switch_window_timeout_without_switch_screen_still_completes():
    actions = FakeActions()
    t = [0.0]
    flow = RespawnFlow(actions, clock=lambda: t[0], switch_watch_s=6.0)
    flow.tick(True, False, False, now=0.0)
    flow.tick(False, False, False, now=0.1)  # watching starts at t=0.1
    t[0] = 6.2
    done = flow.tick(False, False, False, now=t[0])
    assert done is True
    assert actions.reapplied == 0


def test_health_bar_shortcircuits_watch_without_reapply():
    actions = FakeActions()
    t = [0.0]
    flow = RespawnFlow(actions, clock=lambda: t[0])
    flow.tick(True, False, False, now=0.0)
    flow.tick(False, False, False, now=0.1)
    done = flow.tick(False, False, True, now=0.3)
    assert done is True
    assert actions.reapplied == 0


def test_reset_restarts_the_sequence():
    actions = FakeActions()
    t = [0.0]
    flow = RespawnFlow(actions, clock=lambda: t[0])
    flow.tick(True, False, False, now=0.0)
    flow.reset()
    assert flow.stage == "pending"
    flow.tick(True, False, False, now=1.0)
    assert actions.presses == 2
