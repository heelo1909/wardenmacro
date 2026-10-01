import logging
import threading

from warden.core.events import EventBus, Level
from warden.core.logs import bridge_bus_to_logging, setup_logging


def test_level_and_topic_filtering():
    bus = EventBus()
    seen_warn, seen_state = [], []
    bus.subscribe(seen_warn.append, min_level="warn")
    bus.subscribe(seen_state.append, topics=["state"])
    bus.emit("state.transition", "LOBBY -> MODE_SELECT")
    bus.emit("statex.other", "not a state event")
    bus.emit("detect.disconnect_modal", "candidate", level="warn", confidence=0.71)
    assert [e.topic for e in seen_warn] == ["detect.disconnect_modal"]
    assert seen_warn[0].confidence == 0.71
    assert [e.topic for e in seen_state] == ["state.transition"]


def test_success_level_orders_between_info_and_warn():
    assert Level.INFO < Level.SUCCESS < Level.WARN
    assert Level.parse("warning") is Level.WARN


def test_failing_subscriber_is_isolated(caplog):
    bus = EventBus()
    good = []

    def broken(_event):
        raise RuntimeError("boom")

    bus.subscribe(broken)
    bus.subscribe(good.append)
    with caplog.at_level(logging.ERROR):
        bus.emit("x", "hello")
    assert len(good) == 1
    assert "subscriber" in caplog.text


def test_unsubscribe_and_history():
    bus = EventBus(history=3)
    got = []
    token = bus.subscribe(got.append)
    bus.emit("a", "1", level="debug")
    bus.unsubscribe(token)
    for i in range(4):
        bus.emit("b", str(i), level="error")
    assert len(got) == 1
    assert [e.message for e in bus.history()] == ["1", "2", "3"]
    assert all(e.level is Level.ERROR for e in bus.history("error"))


def test_thread_safe_sequence_numbers():
    bus = EventBus(history=10_000)

    def spam():
        for _ in range(500):
            bus.emit("t", "x")

    threads = [threading.Thread(target=spam) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    seqs = [e.seq for e in bus.history()]
    assert len(seqs) == 2000 and len(set(seqs)) == 2000


def test_bus_events_reach_log_file(tmp_path):
    log_file = setup_logging(log_dir=tmp_path, console=False)
    bus = EventBus()
    bridge_bus_to_logging(bus)
    bus.emit("recovery.done", "back in match", level="success", confidence=0.93)
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = log_file.read_text(encoding="utf-8")
    assert "SUCCESS" in text and "[recovery.done] back in match (conf 0.93)" in text
