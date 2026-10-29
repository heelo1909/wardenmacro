"""License gate (Licensing & Distribution Proposal, Phase 1 "Ship it"): a
Gumroad storefront-key check so a purchased copy doesn't become unlimited
free copies, without running a backend of our own.

Two product tiers share one mechanism - Gumroad's own per-license
``uses_count``, incremented once and never again:

* pass - cheap, time-boxed. Starts a local clock on first activation and
  stops granting access once ``pass_hours`` have elapsed; no server call
  needed to enforce that part.
* lifetime - pricier, never expires once activated.

Both lock to one device: the FIRST successful verify increments Gumroad's
own use counter, and Warden only ever accepts a key whose ``uses_count``
comes back as 1 on that call - then remembers the result locally
(``license.yaml`` under the data home) and never calls Gumroad again for
that key. A second device (or the same key re-entered after a pass expires -
by design a pass is single-use, see the proposal) gets ``uses_count`` >= 2
back and is refused. No custom backend, per the proposal's recommended
starting point.

Disabled by default (``config.license.enabled = False``) so a from-source
dev copy - including the one in this repo - never asks for a key. Only a
config shipped to customers should flip it on, after filling in the two
real Gumroad product permalinks (see ``sales-bot/README.md``).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict

from warden.config.loader import save_model
from warden.config.schema import LicenseConfig

log = logging.getLogger(__name__)

GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"

Tier = Literal["pass", "lifetime"]


class LicenseState(BaseModel):
    """What's remembered locally after a key activates. Never re-sent to
    Gumroad once ``device_confirmed`` is true - that one call already spent
    the key's one allowed fresh ``uses_count``.
    """

    model_config = ConfigDict(extra="forbid")

    key: str = ""
    tier: Tier | None = None
    activated_at: float = 0.0  # time.time() of the first successful verify
    device_confirmed: bool = False


@dataclass
class LicenseResult:
    ok: bool
    tier: Tier | None = None
    message: str = ""


def state_path(data_home: Path) -> Path:
    return Path(data_home) / "license.yaml"


def load_state(data_home: Path) -> LicenseState:
    """Never raises - an unreadable or missing file just means unactivated,
    so a corrupt state file re-prompts for a key instead of crashing startup.
    """
    path = state_path(data_home)
    if not path.exists():
        return LicenseState()
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return LicenseState.model_validate(data)
    except Exception:
        log.exception("license state file unreadable; treating as unactivated")
        return LicenseState()


def save_state(data_home: Path, state: LicenseState) -> None:
    save_model(state, state_path(data_home))


def _default_verifier(permalink: str, key: str) -> dict:
    """The real Gumroad call, isolated so tests never touch the network -
    same injectable pattern as ``integrations/discord_webhook.py``'s
    ``poster``.
    """
    import requests

    resp = requests.post(
        GUMROAD_VERIFY_URL,
        data={"product_permalink": permalink, "license_key": key, "increment_uses_count": "true"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def verify_and_activate(
    key: str,
    config: LicenseConfig,
    verifier: Callable[[str, str], dict] = _default_verifier,
) -> LicenseResult:
    """First-run check only - call this once per key, never on every launch
    (that would increment ``uses_count`` again and lock the buyer's own
    device out). Tries the pass permalink, then lifetime, since a key's tier
    isn't known up front; whichever Gumroad recognizes wins. Accepts only
    ``uses_count == 1`` - anything higher means this key already activated
    somewhere (or was already spent).
    """

    key = key.strip()
    if not key:
        return LicenseResult(ok=False, message="Enter a license key.")

    attempts: list[tuple[Tier, str]] = []
    if config.pass_permalink:
        attempts.append(("pass", config.pass_permalink))
    if config.lifetime_permalink:
        attempts.append(("lifetime", config.lifetime_permalink))
    if not attempts:
        return LicenseResult(ok=False, message="No Gumroad product is configured - contact support.")

    last_error = "That key wasn't recognized."
    for tier, permalink in attempts:
        try:
            data = verifier(permalink, key)
        except Exception as exc:
            log.exception("license verify call failed")
            return LicenseResult(ok=False, message=f"Couldn't reach the license server: {exc}")
        if not data.get("success"):
            last_error = data.get("message") or last_error
            continue
        if data.get("uses_count", 1) > 1:
            return LicenseResult(ok=False, message="This key has already been activated and can't be used again.")
        return LicenseResult(ok=True, tier=tier)

    return LicenseResult(ok=False, message=last_error)


def has_access(state: LicenseState, config: LicenseConfig, now: float | None = None) -> bool:
    """Whether a previously-activated key still grants access - purely
    local, no network call (the proposal's "ask for the key once"; this just
    checks the pass clock, or passes lifetime through unconditionally).
    """

    if not config.enabled:
        return True
    if not state.device_confirmed or state.tier is None:
        return False
    if state.tier == "lifetime":
        return True
    now = time.time() if now is None else now
    return (now - state.activated_at) < config.pass_hours * 3600
