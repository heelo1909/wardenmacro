"""Warden sales bot - answers /buy, /latest, /help in your Discord server.

This is Jason's own storefront tooling. It is never bundled into Warden's
packaged .exe and never shipped to customers - it just runs continuously
somewhere (your own always-on PC, or a free host like Railway/Render) so
buyers can self-serve purchase links and the current download link without
pinging you directly.

Setup (see README.md for the full walkthrough):
  1. pip install -r requirements.txt
  2. Copy config.example.json to config.json and fill in your real links/IDs.
  3. Set the WARDEN_BOT_TOKEN environment variable to your bot's token
     (never put the token in config.json or in this file).
  4. python bot.py

Deliberately simple by design: no payment processing, no license-key
generation, no database. Gumroad already emails the key automatically on
purchase - this bot's only job is answering questions so you don't have to.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import discord
from discord import app_commands

log = logging.getLogger("sales-bot")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CONFIG_PATH = Path(__file__).parent / "config.json"
REQUIRED_KEYS = ("pass_link", "lifetime_link", "latest_version", "latest_link", "admin_ids")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(
            f"config.json not found at {CONFIG_PATH}.\n"
            "Copy config.example.json to config.json and fill in your real values first."
        )
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        sys.exit(f"config.json is not valid JSON: {exc}")
    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        sys.exit(f"config.json is missing: {', '.join(missing)}")
    if not isinstance(data["admin_ids"], list) or not all(isinstance(i, int) for i in data["admin_ids"]):
        sys.exit('config.json\'s "admin_ids" must be a list of Discord user IDs (numbers, not text).')
    return data


def save_config(data: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


config = load_config()

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


@client.event
async def on_ready() -> None:
    await tree.sync()
    log.info("Logged in as %s - commands synced.", client.user)


@tree.command(name="buy", description="Get Warden's purchase links")
async def buy(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="Get Warden",
        description="Pick whichever fits how long you're grinding for:",
        color=discord.Color.dark_grey(),
    )
    embed.add_field(name="24-hour pass", value=config["pass_link"], inline=False)
    embed.add_field(name="Lifetime", value=config["lifetime_link"], inline=False)
    embed.set_footer(text="Your license key is emailed automatically right after checkout.")
    await interaction.response.send_message(embed=embed)


@tree.command(name="latest", description="Get the current Warden version and download link")
async def latest(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title=f"Warden {config['latest_version']}",
        description=config["latest_link"],
        color=discord.Color.dark_grey(),
    )
    await interaction.response.send_message(embed=embed)


@tree.command(name="help", description="List what this bot can do")
async def help_cmd(interaction: discord.Interaction) -> None:
    embed = discord.Embed(
        title="Warden bot commands",
        color=discord.Color.dark_grey(),
        description=(
            "/buy - purchase links for the 24-hour pass and the lifetime key\n"
            "/latest - current version and download link\n"
            "/help - this message"
        ),
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@tree.command(name="setlatest", description="(admin only) Update the current version and download link")
@app_commands.describe(version="e.g. v1.4.0", link="the new download link")
async def setlatest(interaction: discord.Interaction, version: str, link: str) -> None:
    if interaction.user.id not in config["admin_ids"]:
        await interaction.response.send_message(
            "That one's admin-only.", ephemeral=True
        )
        return
    config["latest_version"] = version
    config["latest_link"] = link
    save_config(config)
    await interaction.response.send_message(
        f"Updated - /latest now points to {version}.", ephemeral=True
    )


def main() -> None:
    token = os.environ.get("WARDEN_BOT_TOKEN")
    if not token:
        sys.exit(
            "WARDEN_BOT_TOKEN environment variable is not set.\n"
            "Set it to your bot's token from discord.com/developers, then run this again."
        )
    client.run(token)


if __name__ == "__main__":
    main()
