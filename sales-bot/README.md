# Warden sales bot

Answers `/buy`, `/latest`, and `/help` in your Discord server. Gumroad already
emails the license key automatically on purchase, so this bot doesn't touch
keys or payments at all - it just saves you from manually answering "where do
I buy this" and "what's the latest version" all day.

This folder is separate from the rest of Warden on purpose. It never gets
bundled into the `.exe` you ship to customers.

## 1. Create your Discord bot

1. Go to <https://discord.com/developers/applications> and log in.
2. Click **New Application**, give it a name (e.g. "Warden"), accept the
   terms, click **Create**.
3. In the left sidebar, click **Bot**.
4. Click **Reset Token** (or it may already show one) and copy it somewhere
   safe for a minute - you'll need it in step 4 below. Never paste this
   token into Discord itself, a public repo, or anywhere else public.
5. Still on the Bot page, scroll down and turn on nothing extra - this bot
   doesn't need Message Content or any privileged intent.
6. In the left sidebar, click **OAuth2** → **URL Generator**. Under
   **Scopes** check `bot` and `applications.commands`. Under **Bot
   Permissions** check `Send Messages` and `Use Slash Commands`. Copy the
   generated URL at the bottom, open it in your browser, and add the bot to
   your server.

## 2. Set up Gumroad

1. Create a seller account at <https://gumroad.com> if you don't have one.
2. Create two products: a 24-hour pass and a lifetime key.
3. License keys live on the product's **Content** tab, not Settings. Open
   each product → **Content** → click the **⋯** (three-dot) menu → **License
   key** to add that block to the page. Leave "Allow customers to choose
   number of seats" off - Warden expects exactly one key per sale. Turning
   this on also retroactively generates a key for any past sales of that
   product.
4. Copy each product's public purchase link - you'll put these in
   `config.json` below.

## 3. Configure the bot

1. Copy `config.example.json` to `config.json` in this same folder.
2. Fill in your real Gumroad links for `pass_link` and `lifetime_link`.
3. Set `latest_version` and `latest_link` to whatever your current build is.
4. Set `admin_ids` to your own Discord user ID (and anyone else who should
   be able to run `/setlatest`). To find your ID: Discord Settings →
   Advanced → turn on Developer Mode, then right-click your name anywhere →
   **Copy User ID**.

`config.json` is already in `.gitignore` - it won't get committed.

## 4. Turn on Warden's own license check

This bot only answers questions - Warden itself is what actually checks a
key at startup. That's a separate switch, in Warden's own `config.yaml`
(`license:` section, added by the Licensing & Distribution Proposal's Phase
1), not in this bot's `config.json`.

1. Take the same two purchase links from step 2 above
   (`https://yourname.gumroad.com/l/warden-24h` and `.../warden-lifetime`).
   The **permalink** Warden needs is just the last part of that URL -
   `warden-24h` and `warden-lifetime` in that example.
2. In the `config.yaml` that ships inside the build you distribute (not your
   own dev copy - see the warning below), set:
   ```yaml
   license:
     enabled: true
     pass_permalink: "warden-24h"
     lifetime_permalink: "warden-lifetime"
     pass_hours: 24
   ```
3. Run `Rebuild Warden.exe.bat` so that `.exe` actually contains this change.

**Leave `enabled: false` in your own working copy of this repo.** It's
`false` by default for exactly that reason - so you (and Claude Code) can
keep running and testing Warden from source without ever needing a key.
Only the config inside a build meant for a paying customer should flip it
on.

## 5. Run it

```powershell
cd sales-bot
pip install -r requirements.txt
$env:WARDEN_BOT_TOKEN = "paste-your-bot-token-here"
python bot.py
```

Leave that terminal window open - the bot only answers commands while this
is running. For it to work even when your PC is off, run it instead on a
free-tier host (Railway, Render, Fly.io all work) - same two commands, just
set `WARDEN_BOT_TOKEN` in that host's environment variable settings instead
of your own terminal.

## Updating the "latest" link

Whenever you ship a new build, either edit `latest_version`/`latest_link` in
`config.json` directly and restart the bot, or - without restarting
anything - run `/setlatest` in Discord (only works for the user IDs listed
in `admin_ids`).

## What this bot deliberately doesn't do

No payment processing, no license-key generation, no database, and it never
checks whether a key is valid - Warden itself does that (step 4 above), this
bot only answers "where do I buy this." If you later want the bot to also DM
keys automatically right after purchase, that's a separate, bigger piece of
work (a small listener for Gumroad's "Ping" webhook) - ask and we can scope
that out when you're ready for it.
