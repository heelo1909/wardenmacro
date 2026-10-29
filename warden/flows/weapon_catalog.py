"""RIVALS' known weapons, grouped by loadout slot, for the Loadout page's
picker dropdowns.

This is Warden's own reference list - it isn't read from the game at
runtime, so it will drift as RIVALS ships new weapons in seasonal updates.
Add a name to the right list below (then restart Warden) to keep it
current; nothing else depends on a weapon appearing here. The zero-setup
"teach by clicking" flow (``flows/loadout.py``) still works for any weapon
name at all, listed or not - this catalog only makes picking one you
already know faster and less typo-prone than free text.

Transcribed 2026-10-03 directly from the game's own in-game weapon-select
screens (all 4 slot tabs, screenshotted and sent over), not from web
research - this supersedes an earlier, incomplete web-sourced draft of this
file. Includes weapons not yet unlocked (e.g. Distortion, Permafrost,
Warper, Maul, Jump Pad, Warpstone, Grappler) since the point of this list is
every weapon that exists, not just ones any one player currently owns.
"""

from __future__ import annotations

PRIMARY: list[str] = [
    "Assault Rifle", "Bow", "Burst Rifle", "Crossbow", "Distortion",
    "Energy Rifle", "Flamethrower", "Grenade Launcher", "Gunblade", "Minigun",
    "Paintball Gun", "Permafrost", "RPG", "Shotgun", "Sniper", "Wildcat",
]

SECONDARY: list[str] = [
    "Daggers", "Energy Pistols", "Exogun", "Flare Gun", "Handgun", "Revolver",
    "Shorty", "Slingshot", "Spray", "Uzi", "Warper",
]

MELEE: list[str] = [
    "Battle Axe", "Chainsaw", "Fists", "Katana", "Knife", "Maul",
    "Riot Shield", "Scythe", "Spear", "Trowel",
]

UTILITY: list[str] = [
    "Flashbang", "Freeze Ray", "Grappler", "Grenade", "Jump Pad", "Medkit",
    "Molotov", "Satchel", "Smoke Grenade", "Subspace Tripmine", "War Horn",
    "Warpstone",
]

BY_SLOT: dict[str, list[str]] = {
    "primary": PRIMARY,
    "secondary": SECONDARY,
    "melee": MELEE,
    "utility": UTILITY,
}


def weapons_for(slot: str) -> list[str]:
    """Known weapon names for one slot, alphabetical. Empty list for an
    unrecognized slot rather than raising - callers just get no suggestions.
    """
    return list(BY_SLOT.get(slot, []))
