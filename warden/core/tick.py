"""The main loop (HANDOFF section 4.2): capture -> detect -> decide -> act.

``LiveActions`` implements ``GameActions`` against the real window/input/
vision stack from Phase 1, with a verified loadout transaction (Phase 3) and
the full leave/close/relaunch/backoff recovery sequence (Phase 4) behind it;
``TickLoop`` drives it all.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from warden import paths
from warden.behaviors.humanize import Humanizer
from warden.config.schema import AppConfig, Preset
from warden.core.events import EventBus
from warden.core.state_machine import Signals, State, StateMachine, Transition
from warden.core.persistence import PersistenceManager
from warden.core.scheduler import Scheduler, ShutdownCountdown, power_action
from warden.flows.calibration import calibration_gaps, parse_contract_hours, template_library
from warden.flows.loadout import LoadoutTransaction, SequentialLoadoutTransaction
from warden.flows.recovery import RecoverySequence
from warden.geometry import Rect
from warden.integrations.discord_bot import BotCommands, DiscordBotRunner
from warden.integrations.discord_webhook import DiscordWebhook
from warden.integrations.lan_dashboard import LanDashboardServer
from warden.integrations.toast import ToastNotifier
from warden.platform import dpi
from warden.platform.power import SleepGuard
from warden.platform.input import InputController, build_methods
from warden.platform.process import Launcher, RobloxProcess
from warden.platform.window import FocusGate, Win32Windows, pick_client, pick_updater
from warden.vision.capture import MssCapturer, WindowCapturer
from warden.vision.detectors import Detection, FrozenDetector, WindowStateDetector, build_detectors
from warden.vision.templates import TemplateLibrary

log = logging.getLogger(__name__)

_DEFAULT_CONTINUE_POS = (0.5, 0.9)  # fallback click spot when a detector gave no box


class LiveActions:
    def __init__(
        self,
        app: AppConfig,
        preset: Preset,
        input_ctl: InputController,
        window_backend: Win32Windows,
        launcher: Launcher,
        process: RobloxProcess,
        focus_gate: FocusGate,
        weapon_templates: TemplateLibrary,
        bus: EventBus | None = None,
        humanizer: Humanizer | None = None,
    ):
        self.app = app
        self.preset = preset
        self.input = input_ctl
        self.window_backend = window_backend
        self.launcher = launcher
        self.process = process
        self.focus_gate = focus_gate
        self.bus = bus
        self.h = humanizer or Humanizer(app.timings.jitter_pct)
        self.detections: dict[str, Detection] = {}
        # Set by TickLoop: grabs a *fresh* frame of the client. The loadout
        # flow needs one after each click - the per-tick frame was captured
        # before the click happened.
        self.frame_grabber = None
        transaction = (SequentialLoadoutTransaction if app.loadout_ui.mode == "sequential"
                       else LoadoutTransaction)
        self.loadout = transaction(
            self, weapon_templates, app.loadout_ui, get_frame=self._loadout_frame,
            diagnostics_dir=paths.data_dir("diagnostics") / "loadout",
            settle_s=app.timings.ui_settle_s, verify_attempts=3,
        )
        self.recovery = RecoverySequence(self, app.recovery, clock=time.monotonic)
        from warden.behaviors.profiles import InMatchBehavior

        self.behavior = InMatchBehavior(
            input_ctl, preset.behavior, preset.abilities, preset.keys,
            anti_idle=app.automation.anti_idle, abilities_enabled=app.automation.abilities,
            humanizer=Humanizer(preset.behavior.jitter_pct),
            on_action=lambda m: self._emit("behavior.action", m, "debug"),
        )

    def update_detections(self, detections: dict[str, Detection]) -> None:
        self.detections = detections

    def _loadout_frame(self):
        if self.frame_grabber is not None:
            try:
                frame = self.frame_grabber()
                if frame is not None:
                    return frame
            except Exception:
                log.exception("fresh frame grab failed; using the tick's frame")
        return self.detections.get("_last_frame")

    # -- LoadoutActions (LoadoutTransaction calls back into us) --------------------

    def click_frac(self, fx: float, fy: float, what: str = "") -> bool:
        return self.input.click_frac(fx, fy, what=what)

    def scroll(self, notches: int, at: tuple[float, float]) -> bool:
        return self.input.wheel(notches, at=at)

    # -- RecoveryActions (RecoverySequence calls back into us) --------------------

    def click_leave_or_reconnect(self, prefer: str) -> None:
        pos = self.app.recovery_ui.leave_pos if prefer == "leave" else self.app.recovery_ui.reconnect_pos
        self.input.click_frac(*pos, what=f"disconnect modal: {prefer}")

    def process_is_running(self) -> bool:
        return self.process.is_running()

    def process_close(self, grace_s: float) -> None:
        self.process.close(self.focus_gate.hwnd or None, grace_s=grace_s)

    def open_browser_and_play(self) -> None:
        url = self.launcher.open_browser(self.preset)
        self._emit("action.browser_fallback", f"opened browser fallback: {url}", "warn")

    def open_client(self) -> None:
        self.launch()

    def _center(self, name: str, fallback: tuple[float, float] = _DEFAULT_CONTINUE_POS) -> tuple[float, float]:
        det = self.detections.get(name)
        if det is not None and det.box is not None:
            x1, y1, x2, y2 = det.box
            return ((x1 + x2) / 2, (y1 + y2) / 2)
        return fallback

    def _emit(self, topic: str, message: str, level: str = "info", **data) -> None:
        if self.bus is not None:
            self.bus.emit(topic, message, level=level, **data)

    # -- GameActions ------------------------------------------------------------

    def launch(self) -> None:
        uri = self.launcher.open_client(self.preset)
        self._emit("action.launch", f"opened launch target: {uri}")

    def click_play(self) -> None:
        self.input.click_frac(*self._center("lobby_play", (0.5, 0.9)), what="lobby play button")

    def scroll_mode_list(self) -> None:
        # Scroll over the middle of the menu - the mode_list detector's own box
        # may be a corner marker (e.g. RIVALS' red close button), where the
        # wheel wouldn't scroll the list.
        self.input.wheel(-2, at=(0.5, 0.55))

    def click_ffa(self) -> None:
        self.input.click_frac(*self._center("ffa_tile"), what="FFA tile")

    def click_midgame_join(self) -> None:
        self.input.click_frac(*self._center("midgame_join"), what="mid-game join prompt")

    def click_match_continue(self) -> None:
        self.input.click_frac(*self._center("match_end"), what="match end continue")

    def press_respawn(self) -> None:
        self.input.key_tap(self.preset.keys.respawn)

    def _loadout_target(self) -> dict[str, str]:
        return self.preset.loadout.slots() if not self.preset.loadout.random else self._random_loadout()

    def begin_loadout(self) -> None:
        """The picker just opened: start one fresh transaction for this visit.
        (Resetting whenever the last one was "done" restarted it every tick
        after a failure, re-clicking the picker over and over.)"""
        self.loadout.reset(self._loadout_target())
        self._loadout_reported = False
        self._loadout_begun = True

    def _start_loadout_if_idle(self) -> None:
        if self.loadout.done:
            self.loadout.reset(self._loadout_target())

    def _random_loadout(self) -> dict[str, str]:
        import random

        owned = self.app.owned_weapons
        picks = {}
        for slot in ("primary", "secondary", "melee", "utility"):
            pool = getattr(owned, slot)
            if pool:
                picks[slot] = random.choice(pool)
        return picks

    def run_loadout(self) -> bool:
        """One tick's worth of the loadout transaction (HANDOFF 6.3). Verified,
        never guesses a position, and is interruptible between slots - the
        state machine aborts this itself (death/picker-closed/disconnect).
        """
        if not getattr(self, "_loadout_begun", False):
            self.begin_loadout()
        done = self.loadout.tick()
        if done and getattr(self, "_loadout_reported", False):
            return self.loadout.result.success
        if done:
            self._loadout_reported = True
            if self.loadout.result.success:
                self._emit("loadout.committed", f"loadout committed ({self.loadout.result.fixes} slot(s) fixed)",
                           "success")
            else:
                failed = [s for s, o in self.loadout.result.slots.items() if not o.verified]
                self._emit("loadout.incomplete", f"loadout incomplete, slot(s) failed: {', '.join(failed)}", "warn")
            return self.loadout.result.success
        return False

    def reapply_loadout_if_due(self) -> bool:
        """Called by the respawn flow during the post-respawn switch-weapons
        window. Runs the check-and-fix pass inline (each slot's "already
        equipped" pre-check makes repeated calls cheap, and this window is
        brief enough that blocking a few ticks here is fine).
        """
        self._start_loadout_if_idle()
        # Never block this thread forever (capture could stall); each step
        # grabs a fresh frame and the transaction itself waits out UI settle.
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            if self.loadout.tick():
                break
            time.sleep(0.05)
        self._emit("loadout.reapplied", f"post-respawn loadout check ({self.loadout.result.fixes} slot(s) fixed)")
        return self.loadout.result.fixes > 0

    def save_unknown_frame(self) -> None:
        out = paths.data_dir("unknown") / f"{time.strftime('%Y%m%d_%H%M%S')}.png"
        frame = self.detections.get("_last_frame")
        if frame is not None:
            import cv2

            cv2.imwrite(str(out), frame)
        self._emit("unknown.saved", f"saved unknown-screen frame to {out}", "warn")

    def press_escape(self) -> None:
        self.input.key_tap("ESCAPE")

    def handle_recovering(self, cause: str) -> State:
        return self.recovery.tick(cause)

    def on_incident(self, cause: str) -> None:
        self._emit("incident", f"incident: {cause}", "warn", cause=cause)

    def on_recovered(self) -> None:
        self.recovery.full_reset()

    def on_stuck(self, message: str) -> None:
        self._emit("session.stuck", message, "error")

    def enter_match(self) -> None:
        self.behavior.on_spawn()

    def in_match_tick(self, idle_warning: bool) -> None:
        self.behavior.tick(idle_warning)

    def leave_match(self) -> None:
        self.behavior.stop()


class TickLoop:
    def __init__(self, app: AppConfig, preset: Preset, bus: EventBus):
        self.app = app
        self.preset = preset
        self.bus = bus
        dpi.ensure_dpi_awareness()

        self.window_backend = Win32Windows()
        self.focus_gate = FocusGate(self.window_backend)
        # Window capture: whatever is on top of Roblox (Warden itself, chat
        # apps) never ends up in the frame; falls back to a screen grab.
        self.capturer = WindowCapturer(fallback=MssCapturer())
        self.humanizer = Humanizer(app.timings.jitter_pct)
        methods = build_methods(app.input.methods)
        self.input = InputController(
            methods, self.focus_gate, rect=lambda: self._client_rect,
            humanizer=self.humanizer, bus=bus, observe_only=app.observe_only,
            jiggle_px=app.input.jiggle_px, key_hold_ms=tuple(app.input.key_hold_ms),
        )
        self.launcher = Launcher()
        self.process = RobloxProcess(send_close=self.window_backend.send_close)
        weapon_templates = template_library(app.weapon_templates_dir)
        self.actions = LiveActions(app, preset, self.input, self.window_backend, self.launcher,
                                    self.process, self.focus_gate, weapon_templates, bus=bus,
                                    humanizer=self.humanizer)

        # Detector template paths (e.g. "templates/mode_list.png") are relative to the
        # repo root, not the weapons subfolder - a separate library, same cache behavior.
        detector_templates = template_library()
        self._detector_templates = detector_templates
        self._weapon_templates = weapon_templates
        self.actions.frame_grabber = self._grab_fresh
        self.detectors = build_detectors(app.detectors, detector_templates)
        self.frozen_detector = FrozenDetector(seconds=app.recovery.frozen_seconds)

        self.sm = StateMachine(
            self.actions, timeouts=app.timings.timeouts, on_transition=self._on_transition,
            disconnect_confirm_captures=app.recovery.confirm_captures,
            disconnect_confirm_seconds=app.recovery.confirm_seconds,
            recovery_confirm_gap=app.recovery.confirmation_gap_s,
            mode_select_scroll_attempts=app.input.mode_list_scroll_steps,
            lobby_click_interval=app.timings.lobby_click_interval_s,
            ffa_click_interval=app.timings.ffa_click_interval_s,
            max_soft_resets=app.recovery.max_soft_resets,
            max_stuck_relaunches=app.recovery.max_stuck_relaunches,
        )

        self._client_rect: Rect | None = None
        self._recovering_since: float | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        # -- Phase 6: persistence + scheduler -------------------------------------------------------
        self.persistence = PersistenceManager(
            paths.data_home() / "state.json", paths.data_dir("sessions"),
            save_interval_s=app.timings.state_save_s,
        )
        self.scheduler = Scheduler(app.scheduler)
        self._in_match_seconds = 0.0
        self._last_tick_monotonic = time.monotonic()
        self._session_active = False
        self._incidents: list[str] = []
        self._countdown: ShutdownCountdown | None = None
        self.sleep_guard = SleepGuard()
        bus.subscribe(self._on_incident_event, min_level="warn", topics=["incident"])

        # -- Phase 7: integrations (each off unless its own config flag is set) ---------------------
        wh = app.integrations.discord_webhook
        self.webhook = DiscordWebhook(wh.url, enabled=wh.enabled, interval_min=wh.interval_min,
                                      milestone_hours=wh.milestone_hours)
        self.toasts = ToastNotifier(enabled=app.integrations.toasts)
        self.lan_dashboard: LanDashboardServer | None = None
        if app.integrations.lan_dashboard.enabled:
            ld = app.integrations.lan_dashboard
            try:
                self.lan_dashboard = LanDashboardServer(
                    ld.host, ld.port, ld.pin, get_status=self.status_snapshot,
                    on_pause=self.pause, on_resume=self.resume, on_stop=self.stop,
                )
            except ValueError:
                log.exception("LAN dashboard config rejected; leaving it off")
            except ImportError:
                log.warning("LAN dashboard enabled but fastapi/uvicorn aren't installed; leaving it off")
        self.bot_runner: DiscordBotRunner | None = None
        if app.integrations.discord_bot.enabled:
            db = app.integrations.discord_bot
            commands = BotCommands(
                db.allowed_user_id, get_status=lambda: str(self.status_snapshot()),
                on_pause=self.pause, on_resume=self.resume, on_stop=self.stop,
                on_screenshot=lambda: "screenshot requested",
            )
            self.bot_runner = DiscordBotRunner(db.token, commands)

    def _grab_fresh(self):
        if self._client_rect is None:
            return None
        return self.capturer.grab(self._client_rect)

    def calibration_gaps(self) -> list[tuple[str, str]]:
        return calibration_gaps(self.app, self.preset, self._detector_templates, self._weapon_templates)

    def client_already_running(self) -> bool:
        """A Roblox client is up with a visible window - attach instead of launching."""
        try:
            if not self.process.is_running():
                return False
            client = pick_client(self.window_backend.list_windows())
        except Exception:
            log.exception("couldn't check for a running client")
            return False
        if client is None:
            return False
        self.focus_gate.set_target(client.hwnd)
        if hasattr(self.capturer, "hwnd"):
            self.capturer.hwnd = client.hwnd
        self._client_rect = client.client if not client.client.is_empty() else None
        return True

    def status_snapshot(self) -> dict:
        return {
            "state": self.sm.state.value,
            "in_match_hours": round(self._in_match_seconds / 3600.0, 3),
            "target_hours": self.preset.contract.target_hours,
            "counters": {
                "respawns": self.sm.counters.respawns, "reconnects": self.sm.counters.reconnects,
                "re_queues": self.sm.counters.re_queues, "loadout_fixes": self.sm.counters.loadout_fixes,
                "time_lost_s": self.sm.counters.time_lost_s,
            },
        }

    def _on_incident_event(self, event) -> None:
        self._incidents.append(f"{time.strftime('%H:%M:%S')} {event.message}")
        cause = event.data.get("cause", event.message)
        self.toasts.notify("Warden incident", event.message)
        if cause == "disconnect":
            self.webhook.alert_disconnect(event.message)
        elif cause == "unknown_screen":
            self.webhook.alert_unknown_screen()
        elif str(cause).startswith("recovery_resolved"):
            self.webhook.alert_recovery_result(True, self.actions.recovery.stats.attempts, "relaunch")

    def _on_transition(self, t: Transition) -> None:
        self.bus.emit("state.transition", f"{t.frm.value} -> {t.to.value} ({t.cause})", level="info",
                      frm=t.frm.value, to=t.to.value, cause=t.cause)
        if t.to is State.RECOVERING and self._recovering_since is None:
            self._recovering_since = t.ts
        if t.to is State.IN_MATCH:
            # on_recovered() (called by the state machine itself) already reset
            # the recovery flow; this just finishes the time-lost bookkeeping.
            if self._recovering_since is not None:
                self.sm.counters.time_lost_s += t.ts - self._recovering_since
                self._recovering_since = None

    # -- one cycle ------------------------------------------------------------

    def tick_once(self) -> State:
        windows = self.window_backend.list_windows()
        client = pick_client(windows)
        updater = pick_updater(windows)
        process_running = self.process.is_running()

        if client is not None:
            self.focus_gate.set_target(client.hwnd)
            if hasattr(self.capturer, "hwnd"):
                self.capturer.hwnd = client.hwnd
            self._client_rect = client.client if not client.client.is_empty() else None
        else:
            self._client_rect = None

        detections: dict = {}
        frame = None
        if self._client_rect is not None:
            try:
                frame = self.capturer.grab(self._client_rect)
            except Exception:
                log.exception("capture failed")
        if frame is not None:
            for name, det in self.detectors.items():
                detections[name] = det.evaluate(frame)
            detections["frozen"] = self.frozen_detector.evaluate(frame)
            detections["_last_frame"] = frame
        self.actions.update_detections(detections)

        def confirmed(name: str) -> bool:
            d = detections.get(name)
            return bool(d and d.confirmed)

        signals = Signals(
            lobby_play=confirmed("lobby_play"), mode_list=confirmed("mode_list"),
            ffa_tile=confirmed("ffa_tile"), health_bar=confirmed("health_bar"),
            respawn_prompt=confirmed("respawn_prompt"), weapon_picker=confirmed("weapon_picker"),
            switch_weapons=confirmed("switch_weapons"), midgame_join=confirmed("midgame_join"),
            match_end=confirmed("match_end"), disconnect_modal=confirmed("disconnect_modal"),
            roblox_updating=updater is not None, frozen=confirmed("frozen"),
            idle_warning=confirmed("idle_warning"),
            client_window_exists=client is not None, process_running=process_running,
        )
        result_state = self.sm.tick(signals)
        self._maybe_verify_contract(detections, result_state)
        self._bookkeep(result_state)
        return result_state

    def _maybe_verify_contract(self, detections: dict, result_state: State) -> None:
        """Opportunistically OCR the game's own progress counter while
        safely in the lobby, and correct the banked estimate (HANDOFF 8.1).
        """
        if not (self._session_active and self.app.estimate.ocr_verify and result_state is State.LOBBY):
            return
        det = detections.get("contract_progress")
        if det is None or not det.text:
            return
        hours = parse_contract_hours(det.text)
        if hours is None:
            return
        self.persistence.verify_contract_hours(self.app.active_preset, self.preset.contract.label,
                                               self.preset.contract.target_hours, hours)
        self._in_match_seconds = 0.0
        self.bus.emit("contract.verified", f"contract progress verified via OCR: {hours:.2f}h", level="success")

    def _bookkeep(self, result_state: State, now: float | None = None) -> None:
        """Credited-time tracking + persistence flush + scheduler check - split
        out from tick_once() so it's testable without the real capture/detect
        pipeline (no Roblox/window enumeration required).
        """
        now = time.monotonic() if now is None else now
        dt = now - self._last_tick_monotonic
        self._last_tick_monotonic = now
        if self.app.estimate.count_lobby_time:
            credited = result_state not in (State.IDLE, State.PAUSED, State.STOPPED, State.LAUNCHING)
        else:
            credited = result_state is State.IN_MATCH
        if credited and self._session_active:
            self._in_match_seconds += dt

        if self._session_active:
            self.persistence.maybe_flush(self._in_match_seconds, self.sm.counters)
            hours = self._in_match_seconds / 3600.0
            target = self.preset.contract.target_hours
            c = self.sm.counters
            counters_dict = {"respawns": c.respawns, "reconnects": c.reconnects, "re_queues": c.re_queues,
                              "loadout_fixes": c.loadout_fixes, "time_lost_s": c.time_lost_s}
            self.webhook.maybe_send_status(result_state.value, counters_dict, hours, target)
            self.webhook.check_milestone(hours)
            if self.webhook.check_target_reached(hours, target):
                self.toasts.notify("Warden", f"Target reached: {target:.1f}h")
            decision = self.scheduler.check(
                in_match_hours=self._in_match_seconds / 3600.0,
                target_hours=self.preset.contract.target_hours,
                auto_stop_at_target=self.preset.contract.auto_stop_at_target,
            )
            if decision:
                self._scheduled_stop(decision.reason)

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> None:
        self._in_match_seconds = 0.0
        self._last_tick_monotonic = time.monotonic()
        self._incidents = []
        self._session_active = True
        self.persistence.start_session(self.app.active_preset, self.preset.contract.label,
                                        self.preset.contract.target_hours)
        self.sleep_guard.acquire()
        self.webhook.reset_session_state()
        if self.lan_dashboard is not None:
            self.lan_dashboard.start()
        if self.bot_runner is not None and self.bot_runner.available():
            threading.Thread(target=self._run_bot_safely, daemon=True, name="warden-discord-bot").start()
        for severity, message in self.calibration_gaps():
            self.bus.emit("calibration.missing", message, level="error" if severity == "error" else "warn")
        attach = self.client_already_running()
        if attach:
            self.bus.emit("session.attach", "Roblox is already running - taking over the open client "
                                            "instead of relaunching it", level="info")
        self.sm.start(attach=attach)

        def loop():
            while not self._stop.is_set():
                started = time.monotonic()
                try:
                    self.tick_once()
                except Exception:
                    log.exception("tick failed")
                elapsed = time.monotonic() - started
                interval = self.humanizer.jitter(self.app.timings.tick_ms / 1000.0, pct=10)
                self._stop.wait(max(0.0, interval - elapsed))

        self._stop.clear()
        self._thread = threading.Thread(target=loop, name="warden-tick", daemon=True)
        self._thread.start()

    def pause(self) -> None:
        self.sm.pause()

    def resume(self) -> None:
        self.sm.resume()

    def stop(self) -> None:
        self.sm.stop()
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.input.release_all()  # never leave W (or anything) held after Stop
        self._finalize_session()

    def _scheduled_stop(self, reason: str) -> None:
        """A stop triggered from inside the tick thread itself (scheduler) -
        must never join self._thread (that would be the thread joining itself).
        """
        self.bus.emit("schedule.stop", f"stopping: {reason}", level="warn")
        target_reached = reason.startswith("target reached")
        self.sm.stop()
        self._stop.set()
        self._finalize_session()
        if target_reached:
            # Section 8.11 contract queue: let whoever owns preset-switching
            # (AppContext) decide whether to advance and restart - TickLoop
            # itself only has its own single preset, not the whole queue. If
            # it does advance, it's responsible for cancelling the countdown
            # started just below (cancel_shutdown_countdown()).
            self.bus.emit("schedule.target_reached", f"target reached for '{self.app.active_preset}'",
                          level="success", preset_id=self.app.active_preset)
        if self.app.scheduler.after_stop != "nothing":
            self._countdown = ShutdownCountdown(
                seconds=self.app.scheduler.countdown_s,
                action=lambda: power_action(self.app.scheduler.after_stop),
            )
            self.bus.emit("schedule.countdown", f"{self.app.scheduler.after_stop} in "
                                                f"{self.app.scheduler.countdown_s}s unless cancelled", "warn")
            self._countdown.start()

    def cancel_shutdown_countdown(self) -> bool:
        if self._countdown is not None and not self._countdown.fired:
            self._countdown.cancel()
            self.bus.emit("schedule.countdown_cancelled", "shutdown/sleep cancelled", "info")
            return True
        return False

    def _run_bot_safely(self) -> None:
        try:
            self.bot_runner.run()
        except Exception:
            log.exception("discord bot crashed")

    def _finalize_session(self) -> None:
        self.sleep_guard.release()
        if self.lan_dashboard is not None:
            self.lan_dashboard.stop()
        if self._session_active:
            self.persistence.end_session(self._in_match_seconds, self.sm.counters, list(self._incidents))
            self._session_active = False
