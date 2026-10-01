"""Validated configuration schema.

Two documents make up the effective config:

* ``AppConfig`` (config.yaml) - machine/app settings: detectors, timings,
  input, recovery, hotkeys, integrations, scheduler, GUI.
* ``Preset`` (presets/*.yaml) - per-contract settings: contract target,
  launch target, loadout, behavior profile, abilities, game keybinds.

All screen positions are fractions of the Roblox client area, never pixels.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Frac = Annotated[float, Field(ge=0.0, le=1.0)]
Seconds = Annotated[float, Field(ge=0.0)]


class _Model(BaseModel):
    # Typos in YAML keys should be loud, not silently ignored.
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


# --------------------------------------------------------------------------- vision


class ROI(_Model):
    """Region of interest as client-area fractions: x1, y1, x2, y2."""

    x1: Frac
    y1: Frac
    x2: Frac
    y2: Frac

    @model_validator(mode="before")
    @classmethod
    def _from_list(cls, value):
        if isinstance(value, (list, tuple)):
            if len(value) != 4:
                raise ValueError(f"ROI needs 4 numbers [x1, y1, x2, y2], got {len(value)}")
            return dict(zip(("x1", "y1", "x2", "y2"), value))
        return value

    @model_validator(mode="after")
    def _ordered(self):
        if self.x1 >= self.x2:
            raise ValueError(f"x1 ({self.x1}) must be less than x2 ({self.x2})")
        if self.y1 >= self.y2:
            raise ValueError(f"y1 ({self.y1}) must be less than y2 ({self.y2})")
        return self

    def as_list(self) -> list[float]:
        return [self.x1, self.y1, self.x2, self.y2]


class HSVRange(_Model):
    """OpenCV HSV bounds: H 0-179, S 0-255, V 0-255 (inclusive)."""

    lower: tuple[int, int, int]
    upper: tuple[int, int, int]

    @model_validator(mode="after")
    def _bounds(self):
        limits = (179, 255, 255)
        for name, triple in (("lower", self.lower), ("upper", self.upper)):
            for channel, value, limit in zip("HSV", triple, limits):
                if not 0 <= value <= limit:
                    raise ValueError(f"{name} {channel}={value} is outside 0..{limit}")
        for channel, lo, hi in zip("SV", self.lower[1:], self.upper[1:]):
            if lo > hi:
                raise ValueError(f"{channel} lower ({lo}) is above upper ({hi})")
        # Hue may wrap (lower H > upper H means a red-style range across 0).
        return self


class TemplateSpec(_Model):
    path: str
    threshold: Frac = 0.80
    scale_min: Annotated[float, Field(gt=0)] = 0.75
    scale_max: Annotated[float, Field(gt=0)] = 1.25
    scale_steps: Annotated[int, Field(ge=1, le=41)] = 11
    ref_width: Annotated[int, Field(gt=0)] | None = None  # client width the template was captured at

    @model_validator(mode="after")
    def _scales(self):
        if self.scale_min > self.scale_max:
            raise ValueError("scale_min must not exceed scale_max")
        return self


class OCRSpec(_Model):
    contains: list[str] = Field(default_factory=list)  # any of these, case-insensitive
    psm: Annotated[int, Field(ge=0, le=13)] = 7


class DetectorConfig(_Model):
    enabled: bool = True
    method: Literal["color", "template", "ocr", "window", "frozen", "composite"] = "color"
    roi: ROI = Field(default_factory=lambda: ROI(x1=0, y1=0, x2=1, y2=1))
    hsv: list[HSVRange] = Field(default_factory=list)
    fallback_hsv: list[HSVRange] = Field(default_factory=list)
    min_area: Frac = 0.0005
    max_area: Frac = 0.25
    aspect_min: Annotated[float, Field(gt=0)] = 0.05
    aspect_max: Annotated[float, Field(gt=0)] = 50.0
    template: TemplateSpec | None = None
    ocr: OCRSpec | None = None
    confirm_frames: Annotated[int, Field(ge=1, le=50)] = 2
    params: dict[str, float] = Field(default_factory=dict)  # method-specific tuning knobs

    @model_validator(mode="after")
    def _ranges(self):
        if self.min_area > self.max_area:
            raise ValueError(f"min_area ({self.min_area}) is above max_area ({self.max_area})")
        if self.aspect_min > self.aspect_max:
            raise ValueError(f"aspect_min ({self.aspect_min}) is above aspect_max ({self.aspect_max})")
        if self.method == "color" and self.enabled and not self.hsv:
            raise ValueError("a color detector needs at least one hsv range")
        return self


DETECTOR_NAMES = (
    "lobby_play",
    "mode_list",
    "ffa_tile",
    "health_bar",
    "respawn_prompt",
    "weapon_picker",
    "switch_weapons",
    "midgame_join",
    "match_end",
    "disconnect_modal",
    "roblox_updating",
    "frozen",
    "idle_warning",
)


# --------------------------------------------------------------------------- app sections


class StateTimeouts(_Model):
    launching: Seconds = 90
    loading: Seconds = 120
    lobby: Seconds = 30
    mode_select: Seconds = 60
    midgame_join: Seconds = 15
    loadout: Seconds = 45
    dead: Seconds = 20
    match_end: Seconds = 60
    unknown_after: Seconds = 45


class Timings(_Model):
    tick_ms: Annotated[int, Field(ge=50, le=5000)] = 250
    jitter_pct: Annotated[float, Field(ge=0, le=60)] = 15
    click_verify_ms: Annotated[int, Field(ge=50, le=5000)] = 400
    respawn_repress_s: Seconds = 1.5
    switch_window_watch_s: Seconds = 6
    state_save_s: Seconds = 30
    timeouts: StateTimeouts = Field(default_factory=StateTimeouts)


class InputConfig(_Model):
    methods: list[Literal["sendinput", "pydirectinput", "pynput"]] = ["sendinput", "pydirectinput", "pynput"]
    jiggle_px: Annotated[int, Field(ge=0, le=50)] = 3
    key_hold_ms: tuple[int, int] = (40, 110)
    emergency_corner_px: Annotated[int, Field(ge=1, le=50)] = 5
    emergency_hold_s: Seconds = 0.3
    mode_list_scroll_steps: Annotated[int, Field(ge=1, le=100)] = 12

    @field_validator("methods")
    @classmethod
    def _non_empty(cls, value):
        if not value:
            raise ValueError("at least one input method is required")
        return value


class LoadoutSlotUI(_Model):
    """Where to find and verify one loadout slot in the weapon picker (client fractions).

    All placeholders until Calibration (Phase 8) captures the real picker layout.
    """

    tab: tuple[Frac, Frac]              # click position to open this slot's category tab
    grid_roi: ROI                       # scrollable area where weapon tiles can be found
    verify_roi: ROI                     # where the now-equipped weapon's icon/name is shown


class LoadoutUI(_Model):
    slots: dict[str, LoadoutSlotUI] = Field(default_factory=dict)
    max_search_scrolls: Annotated[int, Field(ge=0, le=30)] = 6
    verify_threshold: Frac = 0.75
    scroll_notches: Annotated[int, Field(ge=1, le=10)] = 2

    @field_validator("slots")
    @classmethod
    def _known_slots(cls, value: dict[str, LoadoutSlotUI]):
        unknown = sorted(set(value) - set(SLOTS))
        if unknown:
            raise ValueError(f"unknown loadout slot(s): {', '.join(unknown)}; known: {', '.join(SLOTS)}")
        return value


class RecoveryConfig(_Model):
    prefer_button: Literal["leave", "reconnect"] = "leave"
    confirm_captures: Annotated[int, Field(ge=1)] = 3
    confirm_seconds: Seconds = 1.5
    leave_wait_s: Seconds = 10
    close_grace_s: Seconds = 10
    max_attempts: Annotated[int, Field(ge=1, le=20)] = 3
    in_match_confirmations: Annotated[int, Field(ge=1)] = 2
    confirmation_gap_s: Seconds = 5
    browser_fallback: bool = True
    backoff_initial_s: Seconds = 30
    backoff_cap_s: Seconds = 600
    alert_after_cycles: Annotated[int, Field(ge=1)] = 3
    frozen_seconds: Seconds = 30
    error_codes: list[int] = [277, 279, 267, 268, 529]


class Hotkeys(_Model):
    start: str = "F6"
    pause: str = "F7"
    stop: str = "F8"
    screenshot: str = "F9"


class DiscordWebhook(_Model):
    enabled: bool = False
    url: str = ""
    interval_min: Annotated[float, Field(ge=1)] = 15
    milestone_hours: Annotated[float, Field(gt=0)] = 4
    include_screenshot: bool = True


class DiscordBot(_Model):
    enabled: bool = False
    token: str = ""
    allowed_user_id: str = ""


class LanDashboard(_Model):
    enabled: bool = False
    host: str = "0.0.0.0"  # LAN only; checked against private ranges at runtime
    port: Annotated[int, Field(ge=1024, le=65535)] = 8765
    pin: str = ""


class Integrations(_Model):
    discord_webhook: DiscordWebhook = Field(default_factory=DiscordWebhook)
    discord_bot: DiscordBot = Field(default_factory=DiscordBot)
    lan_dashboard: LanDashboard = Field(default_factory=LanDashboard)
    toasts: bool = True


def _parse_hhmm(value: str) -> str:
    parts = str(value).split(":")
    if len(parts) != 2 or not all(p.isdigit() for p in parts):
        raise ValueError(f"'{value}' is not HH:MM")
    h, m = int(parts[0]), int(parts[1])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"'{value}' is not a valid time")
    return f"{h:02d}:{m:02d}"


class TimeWindow(_Model):
    start: str  # "HH:MM"
    end: str

    @field_validator("start", "end")
    @classmethod
    def _hhmm(cls, value: str):
        return _parse_hhmm(value)


class Scheduler(_Model):
    stop_at_time: str | None = None  # "HH:MM"
    windows: list[TimeWindow] = Field(default_factory=list)
    after_stop: Literal["nothing", "sleep", "shutdown"] = "nothing"
    countdown_s: Annotated[int, Field(ge=5, le=600)] = 60

    @field_validator("stop_at_time")
    @classmethod
    def _hhmm(cls, value):
        if value is None or value == "":
            return None
        return _parse_hhmm(value)


class Automation(_Model):
    auto_reconnect: bool = True
    respawn_recovery: bool = True
    auto_requeue: bool = True
    abilities: bool = True
    anti_idle: bool = True


class GuiConfig(_Model):
    always_on_top: bool = False
    mini_overlay: bool = False
    log_verbosity: Literal["debug", "info", "warn", "error"] = "info"
    minimize_on_start: bool = True


class ContractEstimate(_Model):
    count_lobby_time: bool = False  # unconfirmed whether the game credits lobby time
    ocr_verify: bool = True


class OwnedWeapons(_Model):
    """Pool used by the Random preset; one random pick per slot per match."""

    primary: list[str] = Field(default_factory=list)
    secondary: list[str] = Field(default_factory=list)
    melee: list[str] = Field(default_factory=list)
    utility: list[str] = Field(default_factory=list)


class AppConfig(_Model):
    active_preset: str = "glass_wrap"
    contract_queue: list[str] = Field(default_factory=list)  # preset ids, run in order
    observe_only: bool = False
    timings: Timings = Field(default_factory=Timings)
    input: InputConfig = Field(default_factory=InputConfig)
    recovery: RecoveryConfig = Field(default_factory=RecoveryConfig)
    hotkeys: Hotkeys = Field(default_factory=Hotkeys)
    automation: Automation = Field(default_factory=Automation)
    integrations: Integrations = Field(default_factory=Integrations)
    scheduler: Scheduler = Field(default_factory=Scheduler)
    gui: GuiConfig = Field(default_factory=GuiConfig)
    estimate: ContractEstimate = Field(default_factory=ContractEstimate)
    owned_weapons: OwnedWeapons = Field(default_factory=OwnedWeapons)
    weapon_templates_dir: str = "templates/weapons"
    loadout_ui: LoadoutUI = Field(default_factory=LoadoutUI)
    detectors: dict[str, DetectorConfig] = Field(default_factory=dict)

    @field_validator("detectors")
    @classmethod
    def _known_detectors(cls, value: dict[str, DetectorConfig]):
        unknown = sorted(set(value) - set(DETECTOR_NAMES))
        if unknown:
            raise ValueError(f"unknown detector(s): {', '.join(unknown)}; known: {', '.join(DETECTOR_NAMES)}")
        return value


# --------------------------------------------------------------------------- presets


class LaunchMode(str, Enum):
    public = "public"
    share_link = "share_link"


class Contract(_Model):
    label: str
    target_hours: Annotated[float, Field(gt=0)] = 24
    auto_stop_at_target: bool = True


class Launch(_Model):
    mode: LaunchMode = LaunchMode.public
    place_id: Annotated[int, Field(gt=0)] = 17625359962
    share_code: str = ""

    @model_validator(mode="after")
    def _share_needs_code(self):
        if self.mode is LaunchMode.share_link and not self.share_code.strip():
            raise ValueError("launch.mode is share_link but share_code is empty")
        return self


SLOTS = ("primary", "secondary", "melee", "utility")


class Loadout(_Model):
    random: bool = False  # pick from owned_weapons each match
    primary: str = ""
    secondary: str = ""
    melee: str = ""
    utility: str = ""

    def slots(self) -> dict[str, str]:
        return {slot: getattr(self, slot) for slot in SLOTS}


class Behavior(_Model):
    profile: Literal["idle_nudge", "patrol", "fire_loop", "hide_spot"] = "idle_nudge"
    anti_idle_seconds: Annotated[float, Field(ge=10, le=1100)] = 75
    jitter_pct: Annotated[float, Field(ge=0, le=60)] = 15
    fire_slot: Literal["primary", "secondary", "melee", "utility"] = "primary"
    fire_every_seconds: Annotated[float, Field(gt=0)] = 8
    aim_offset: tuple[float, float] = (0.0, 0.0)  # client fractions from centre
    hide_path: list[dict] = Field(default_factory=list)  # recorded [{key, hold_s}] steps


class AbilityKey(_Model):
    key: str
    every_seconds: Annotated[float, Field(gt=0)]


class Abilities(_Model):
    enabled: bool = False
    keys: list[AbilityKey] = Field(default_factory=lambda: [AbilityKey(key="F", every_seconds=20)])


class GameKeys(_Model):
    respawn: str = "SPACE"
    loadout: str = "M"


class Preset(_Model):
    name: str
    contract: Contract
    launch: Launch = Field(default_factory=Launch)
    loadout: Loadout = Field(default_factory=Loadout)
    behavior: Behavior = Field(default_factory=Behavior)
    abilities: Abilities = Field(default_factory=Abilities)
    keys: GameKeys = Field(default_factory=GameKeys)
