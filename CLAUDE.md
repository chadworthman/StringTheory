# String Theory

Local control of Tuya-based Wi-Fi light strings from a Raspberry Pi: a show engine, a daily schedule and a phone control page. NOMA smart C9 (AL901B) is the tested hardware, and the project aims to work with any Tuya light string that takes per-bulb colours. See README.md for setup and usage.

Machine-specific details (Pi host alias, device IPs and IDs, other services on the Pi, firewall rules) are in `CLAUDE.local.md`. That file is gitignored. Never copy anything from it into tracked files.

## Building on your own copy

This file is written for an AI coding assistant (such as Claude Code) working on String Theory, and it's meant for anyone who clones the project, not just its author. Everything below records what was learned building it against real NOMA C9 lights: the protocol, the engine's timing rules, and what does and doesn't look good on the bulbs. Use it to keep developing your own copy.

When you start on someone's own copy:

- **Find out their setup first.** Ask, or check: which controller (`python tools/probe.py list`), how it runs (Raspberry Pi installer, Docker, or `scripts/run.sh` / `run.ps1` on a home computer), and where their data folder is (`STRINGTHEORY_DATA`, usually `<repo>/data`). If it's not a NOMA C9 (model AL901B), follow `docs/adapting.md` before changing shows: the DPs and `frame()` must be right first.
- **Put their private details in `CLAUDE.local.md`** (gitignored): controller IPs, device names, how to reach the machine it runs on, their timezone. The rules under Secrets apply to their copy too, especially if they plan to publish a fork.
- **Test without their lights when you can.** A `devices.json` with made-up controllers at documentation addresses (such as `192.0.2.10`) plus a `config.json` lets the engine and page run anywhere; the strings just show as "Not responding". The page works fully against that, so layout and show previews can be checked in a browser. Only `tools/probe.py paint` and the real engine touch the lights, and both interrupt whatever is playing, so ask first.
- **The lights are the test.** The page preview isn't proof: the person judges by looking at the real string. Tell them what to look for (which bulbs, which colours, how fast), and don't claim it looks right until they say so.
- **Common requests and where they go:** a new show or theme (Writing shows, then `SHOWS` in `lights.py` and `SHOW_INFO`/`GROUPS` in `web.py`), a different string count or order (`pi/configure.py`, never hard-code), another brand (`docs/adapting.md`), a page change (`pi/index.html`, no build step), a schedule or power behaviour (`schedule()`/`is_on_hours()` in `lights.py`).
- **The Website section** describes the author's public site. Ignore it unless they're publishing their own. Older installs made before `scripts/install-pi.sh` may use the service names `smartlights` and `smartlights-web` and keep data next to the code; check with `systemctl list-units | grep -i -e string -e smartlights`.
- **No support from the author.** The project is offered as-is as a starting point (see `SUPPORT.md`). Don't tell people to ask the author for help or to file issues expecting a reply; help them solve it in their own copy.
- **Sharing back (optional):** if they get another controller working or make a show worth sharing, they can offer a pull request or document it in their fork with the model, protocol version, DPs and any `frame()` change, with no keys, IPs or device IDs.

## Secrets

- `devices.json` and `tinytuya.json` hold the controllers' local keys and Tuya cloud credentials. Never print, log, paste or commit them. They stay `chmod 600` and gitignored.
- Keep IP addresses, device IDs, hostnames, usernames, timezones and other home-network details out of tracked files, comments and commit messages. Use placeholders like `<pi-address>`.

## Layout

- `pi/lights.py`: engine. Contains `SHOWS`, the show builders, the schedule, the per-string worker threads and the `lights` CLI. Runs as the `string-theory` service.
- `pi/web.py` + `pi/index.html`: control page on port 8080, standard library only, runs as `string-theory-web`. The page is a single HTML file with no build step. `web.py` reads it on every request, so HTML changes need no restart.
- `tools/`: protocol and speed experiments, throwaway and not deployed, except `tools/probe.py` (user-facing: list, dps, sniff, paint, power) and `tools/build_site.py`. `docs/adapting.md` is the guide for other controllers; keep it in step with `frame()`, `effect_payload()` and the `dp_*` config keys.

## Protocol facts (measured on NOMA C9, Tuya local protocol 3.5 via `tinytuya`)

DP numbers are `DP_SWITCH`, `DP_PAINT` and `DP_EFFECT` at the top of `lights.py`. Never hard-code them, so that other Tuya lights only need those changed. Keep brand-specific assumptions (frame layout in `frame()`, effect bytes in `effect_payload()`) in those functions.


- DP 20 is the on/off switch.
- DP 102 is a raw per-bulb frame, base64 of `00 00 00 01 01` followed by 24 × `R G B 00 00`. If the 5th byte is `00`, the frame is a single solid colour.
- DP 104 holds the built-in effects: `00 00 00 80 <mode> <speed> 00×7 <count> <colours × 5 bytes>`.
- DP 103 is listed as brightness but has never been seen to change. Brightness is done in software instead: each zone's `brightness` (one of `BRIGHTNESS`, 10–100%) scales every colour in the worker (`dim()`, and `dim_effect()` for built-in effect payloads). Shows always build colours at full value.
- A controller applies at most about one frame every 0.3 s. Acks take about 0.5 s, but that's latency, not throughput, so send with `nowait=True` on a persistent socket and drain acks.
- Connect with a blocking `status()` handshake (the 3.5 session-key negotiation) before you drop the socket timeout for streaming. Use short connect timeouts and few retries: tinytuya's default retries block for about 25 s.
- The engine's design depends on these rules, so keep them:
  - Show position comes from the clock.
  - A string gets the newest frame only after acking the last one.
  - Each string has its own thread.
  - Unchanged frames are resent every 30 s.

## Writing shows

- A show is `f(t) -> list of TOTAL (r, g, b)`, where `t` is show time in seconds. It must be deterministic in `t`, so both string threads agree. If it needs randomness, seed it from `t`.
- Moving shows need `show.period` (loop length) and `show.step` (shortest time between changes). The builders set both. The web previews and the speed cap (`MIN_STEP = 0.4` s) depend on them.
- Naming: when a theme has both versions, the still one gets the plain name and the moving one gets "Name (moving)". Themes with only one version keep their own name. Don't use "(still)", "Moving …" or other suffixes.
- Still/animated pairs live in `MOVING_OF` in `web.py`. The animated one gets kind `variant`, so it's hidden from the lists and reached through the **Animate** switch on the still card (it still appears by name in playlists). Every still theme should have one; the default is a chase of its stripes at 0.6 s (stripes three bulbs wide so the chase reads as movement). The switch is on only while that card plays its animated version: flipping it plays that card, and picking another card turns it off. Shows that are animations of their own (fireworks, Snowfall…) stay as separate Moving shows.
- The live bulbs read like wrapped text: every row runs left to right, and `joins()` draws an S-shaped SVG wire from the end of each string, under its bulbs, to the start of the next. It redraws on resize and when the rows change.
- Add every new show to `SHOW_INFO` in `web.py` with a friendly name and a one-line description, and to a group in `GROUPS`. `GROUPS` sets the page order: groups first, then shows within each group, with holidays in calendar order. `web.py` won't start if the two disagree. The help page (`help.html`, at `/help`) lists every show A to Z from `/api/state`, so it needs no edits.
- The page's tabs are worked out from the show:
  - Playlists (built-in, or saved with `effect: playlist`) go on Playlists.
  - Other saved custom shows go on Custom.
  - Shows in `TESTS` in `web.py` go on Tests.
  - Anything else with `.period` goes on Moving, and the rest on Still.
- The page is four screens (`.view`: now, shows, create, setup) chosen from the fixed bottom bar. The last screen is kept in `localStorage` `view`, and links like `#setup` open a screen. Show cards only animate while Shows is visible. The live bulbs (`.live`) sit outside the screens and are `position: sticky`, so they stay at the top on every screen. When the window allows about 14px a bulb, every string goes on one continuous row (`.hero.oneline`, no S-joins); otherwise one row per string. Layouts: phone (under 700px, also iPad Split View), tablet (700px and up, iPad portrait: two columns of show cards, other screens 600px wide) and wide (1150px and up, iPad Pro landscape and desktops: three columns). The manifest allows any orientation.
- Bulbs are drawn so each is exactly one colour: glows sit underneath and every bulb's body is drawn on top (`.bulb b::after`, with `isolation` on `.wire`). Without that, a neighbour's glow tints part of a bulb and it looks like one bulb showing two colours.
- Within Shows, the filter chip opens on the one named in the link, else the last tab used on that phone (`localStorage` `tab`), else Still.
- Link shortcuts: `#still`, `#moving`, `#playlist`, `#custom` and `#test` open a tab. `#newplaylist` opens the playlist builder.
- Blended shades from bulb to bulb are fine, since each bulb can show any colour. What must never happen is a single bulb looking like it shows more than one colour (see the drawing note above). Stripes three bulbs wide chase best.
- Fades look poor at about 3 frames per second. Prefer chases, steps and slides. One-bulb chasers need steps of 0.6 s or more or they visibly skip.
- On these LEDs:
  - White is `(255, 255, 255)`. Warmer whites look pink or peach.
  - The approved classic palette is red `(255,0,0)`, green `(0,255,0)`, yellow `(255,180,0)`, blue `(0,40,255)` and orange `(255,100,0)`.
  - `(255,60,0)` looks red.

## Schedule

- Each zone has `on_at` (`HH:MM`, `sunset` or `sunrise`) with `on_offset` minutes (negative = before), and `off_at` (`HH:MM`, `sunrise`, `sunset`, or `after` with `off_after` minutes). `day_window()` turns that into the on-period starting on a date; `current_window()`/`next_window()` drive `is_on_hours()`, the power holds and the page's times. Everything is in the device's local time.
- Sun times come from `sun_times()` (the NOAA / Almanac for Computers formula, good to about a minute) and `state['location'] = {lat, lon, name}`, shared by all zones. Without a location, sun rules fall back to the default times. `demo.js` has a JavaScript copy of the formula and rules; keep them in step.
- **Locate me** uses the browser's position on secure pages (the website demo), else the device's time zone looked up in `pi/tz_coords.json` (each zone's main city, generated from the public-domain tz database's `zone1970.tab`). The Pi's page is plain http, so it always uses the time zone there. Coordinates are rounded to 2 decimals. Never commit a real location: it lives in `state.json` in the data folder.
- CLI: `lights schedule sunset-5 6h`, `lights schedule sunset sunrise`, `lights location <lat> <lon>`.

## Hockey game tracking

- Zone keys: `follow` (a hockey theme key such as `leafs`; `NHL_TEAM` maps it to the NHL abbreviation), `game_power` (lights on for games, default true), `goal_delay` (seconds), `celebrate` (a timestamp from **Test celebration**) and `skip_game` (a game id: picking a show mid-game hands the lights back until the next game). Set from Setup → Hockey or the pop-up that offers to follow a team when its theme is picked (asked once per team per device, `localStorage asked-follow:<key>`).
- `HockeyWatcher` (a thread in the engine) is the only code that goes online, and only for followed teams. It reads `api-web.nhle.com/v1/club-schedule/<TEAM>/week/now` every 3 hours, and `/v1/gamecenter/<id>/landing` every 30 s from 15 min before puck drop, then every 5 s while `LIVE`/`CRIT`. A rise in the team's score queues a celebration at detection time + `goal_delay`. It writes `hockey.json` (with `active` = the game id during game mode) for the page. Joining mid-game takes the current score as the baseline.
- Game mode: from 15 min before puck drop until `FINAL`, the engine plays `<team>move` (`Shared.game_show`) instead of the zone's show, without changing `state.json`, and turns the lights on if `game_power`. `engine.json` carries `game` and `game_t0`; `web.py` then reports that as the show (`game_mode: true`).
- A celebration (`goal_flash()`: a red goal-light beam sweeping over dim red, then team-colour flashes) sets `Shared.party` for `GOAL_SECS`; the string workers play it over everything.
- The demo can't follow games, so it answers these endpoints with an explanation.

## Zones

- `state.json` has `zones: [{id, name, strings, show, speeds, brightness, override, on_at, off_at, on_offset, off_offset, off_after}]` and a shared `location`. `customs` and `effect_names` are shared by all zones. Old single-zone state, with those keys at the top level, is read as one zone by `zones_of()` and rewritten by `materialise_zones()` on the next save.
- `zone_view(st, zone)` is what the per-zone functions take (`show_fn`, `speed_of`, `schedule`, `override`, `is_on_hours`).
- `zone_module(zone)` loads a separate copy of `lights.py` built for just that zone's strings, through `_ZONE_STRINGS`, so `TOTAL` and every show constant fit the zone. Use the zone module, not `L`, for anything about shows in a zone. Web previews are cached per zone length.
- The engine keeps one `Shared` per zone. Each `String` gets `.shared` and `.offset` for its zone. A string in no zone stays off. `engine.json` is `{zones: {id: {t0, speed, show}}}`, and `health.json` has `want_on` for each string.
- Every page request carries `zone`. The page remembers the zone in `localStorage`, and `/api/state?zone=` and `/api/previews?zone=` select it.

## Running it (Pi, Docker, home computer)

- Data lives in `STRINGTHEORY_DATA`, defaulting to the code folder (that's how the original Pi install works): `devices.json`, `tinytuya.json`, `config.json`, and `state`, `engine` and `health.json`. New installs use `<repo>/data`, Docker uses `/data`, and both are gitignored and dockerignored.
- `config.json` holds `strings: [{name, bulbs}]` (written by `pi/configure.py`) and optional `dp_switch`, `dp_paint` and `dp_effect`. Without it, the built-in defaults are used, which keeps the original Pi working.
- `scripts/install-pi.sh` (systemd services `string-theory` and `string-theory-web`, the `lights` wrapper, an optional ufw rule), `scripts/run.sh` and `scripts/run.ps1` (home computer), and `Dockerfile`, `compose.yaml` and `docker/start.sh` (one container running both processes).
- Docker on macOS can't reach LAN devices until Docker or OrbStack is allowed under Privacy & Security → Local Network. This was seen in testing: the container timed out while the Mac itself reached the controllers.

## Strings

- `STRINGS` (from `config.json`, else the defaults in `lights.py`) lists `(device name, bulbs)` in physical order. `TOTAL`, `SIZES` and `OFFSETS` are derived from it, and each string's worker sends its own slice of the frame.
- Never hard-code 24, 48 or two strings in shows or the page. Use `TOTAL` (or `state.total` and `state.strings` on the page).

## Custom shows and built-in effects

- Custom shows are stored in `state.json` under `customs: {id: {name, colours, width, effect, mode, speed}}` and are played as show key `custom:<id>`. `custom:try` is the editor's scratch slot: it plays, but isn't listed. `show_fn(key, state)` in `lights.py` resolves any key, so use it, not `SHOWS[key]`, wherever a key might be a custom show.
- `effect: builtin` sends DP 104 once per string (`effect_payload`), and the controller animates by itself. The worker resends only on a show or power change, a reconnect, or if the effect wasn't acked. Resending restarts the effect, so don't resend on a timer.
- The meaning of each built-in effect number is unknown: only 0 and 18 have been seen from the app. The page offers `EFFECT_MODES` (0–31). The user names effects as they find out what they do, and the names are stored in `state.json` `effect_names`.
- Playlists are custom shows with `effect: playlist, items: [{show, hold, transition}]` (`build_playlist`). Transitions are `chase` (`TOTAL × 0.4 s`), `fade` (4 s) and `cut`. Playlists can't contain built-in effects, other playlists, Holiday autopilot or test patterns (`NOT_IN_PLAYLISTS`). A custom show that a playlist uses can't be deleted.
- Built-in playlists live in `PLAYLISTS` in `lights.py`. They need a `SHOW_INFO` entry, and their description is generated. Keep their hold times to values in `HOLDS` (`web.py`), or **Edit a copy** can't save them. For playlists, `/api/previews` sends the recipe (items plus transition durations) instead of frames, and `playlistFrame()` in `index.html` assembles the frames from each theme's preview. Keep it in step with `build_playlist`.
- A show can set `.tick` to control how often the page preview samples it. The default is 0.05 s; use `tick = step` for heavy shows.
- `Seasonal` (Holiday autopilot) delegates to `holiday_for(date)`. Hanukkah dates come from a table (`HANUKKAH`) that runs to 2035.

## Runtime state (in the data folder)

- `state.json`: `{show, override:{power, until}, on_at, off_at, speeds:{show: x}, customs, effect_names}`. Written by the CLI and `web.py`, always atomically. The engine polls its modification time every 0.5 s.
- `engine.json`: `{t0, speed, show}`. The engine writes this so the page can mirror the live show. Changing the speed or power keeps the show's position; only a new show restarts it.
- `health.json`: per-string status (online, the real DP 20 value from acks, frames sent and acked in the last 60 s), written every 5 s.

## Deploying and checking

- Installs made by `scripts/install-pi.sh` run from the cloned repo: pull or edit there, then `sudo systemctl restart string-theory string-theory-web`. Check with `systemctl is-active string-theory string-theory-web`, `journalctl -u string-theory -n 20` (it prints per-string sent/acked counts every minute) and `curl localhost:8080/api/state`. Docker: `docker compose up -d --build` and `docker compose logs`. Home computer: stop and rerun the script.
- The author's Pi has used the installer since 2026-11-23 (details in `CLAUDE.local.md`): copy changed `pi/` files into that clone's `pi/` folder, or pull there, then restart as above.
- After a Python change, restart; a restart blinks the show for a couple of seconds. HTML changes need no restart.
- The user judges the result by looking at the real lights. Say what to look for, and don't claim something looks right without their confirmation.
- README screenshots in `docs/` come from a local copy of `web.py` serving fake `state.json`/`engine.json`/`health.json`, never from the real install, so no addresses or real state show up. Capture them at 2x inside a 390 px iframe and crop to 780 px wide.
- For page changes, verify the layout at phone width (around 390 px). Headless Chrome can't make a window that narrow, so screenshot the page inside a 390 px iframe.

## Website (Spacefast; the author's public site, not needed to run String Theory)

- The public site is https://stringtheory.space.fast/ (Spacefast space `stringtheory`, id spc_fe319933c4ad44c4be00d1add94b3bd4, Chad's Team). There's no other address: the hyphenated `string-theory` space was archived on 2026-11-23. The source is `site/src/` (`home.html`, `demo.js`), built by `tools/build_site.py` into `site/dist/` (gitignored). Publish with `sf publish site/dist`. `site/dist/.spacefast` links it to the Space, and the build keeps it.
- Search and share previews: `home.html` carries its own description, canonical, Open Graph/Twitter tags and JSON-LD; `share()` in `build_site.py` adds them to the demo pages. The share image is `site/src/og.png` (1200×630), rendered from `site/src/og.html`. The build also writes `robots.txt` and `sitemap.xml`. Site links into the demo use `/demo/#still`, so they open on the show list.
- The demo is `pi/index.html` and `pi/help.html` with `demo.js`: a fake `/api/*` in the browser, backed by `data.json` from a throwaway state. It must never contain real device names, IPs or the user's zone names. Rebuild and republish after app changes so the demo matches.

## Look

- The look is year-round, not Christmas: a night-slate palette (`--night`, `--panel`, `--edge`, `--text`, `--muted`) with amber (`--amber`) for anything lit or selected, and `--alert` for off. The logo, icons and manifest use the same background. Don't bring back seasonal colours or names in the UI.

## Web page rules

- The page shows the project name (String Theory, with `logo.svg`) at the top. Below that come the zone switcher, when there's more than one zone, and the current zone's name, set with Rename.
- `manifest.webmanifest` plus `icon-192.png`, `icon-512.png` and `icon-maskable.png` make the page installable as a full-screen app. Regenerate the icons from `logo.svg` if the logo changes.
- The title font is preloaded and uses `font-display: block`, and `web.py` lets browsers cache static files (fonts, icons) for a day, so the title never flashes in a fallback font. The site's `_headers` (written by `build_site.py`) does the same.
- The page has no login and stays LAN-only. Never expose it through a port forward, tunnel or proxy without adding authentication.
- POSTs must use `Content-Type: application/json`. Keep that check, because it's the CSRF protection.
