# Plan: build shows online, import them at home

Status: proposal, not built yet.

## The idea

A public String Theory website (hosted on Spacefast) where anyone can design custom patterns and playlists and watch them animate, with no lights or Pi needed. When they like something, they send it to their own lights in one tap. The website never talks to anyone's lights. It hands the show to the String Theory page on the person's home network, which checks it and saves it like any other custom show.

This keeps the project's main rule: **everything that touches the lights stays at home.** No accounts, cloud relay or credentials are needed.

## What gets shared: a show file

A small JSON document that holds data only, never code:

```json
{
  "stringtheory": 1,
  "kind": "playlist",
  "name": "Christmas Eve",
  "author": "optional display name",
  "show": {
    "effect": "playlist",
    "items": [
      {"show": "classic", "hold": 120, "transition": "chase"},
      {"show": "@0", "hold": 60, "transition": "fade"}
    ]
  },
  "includes": [
    {"name": "Grinch", "show": {"colours": ["#00ff00", "#ff0000"], "width": 3, "effect": "chase"}}
  ]
}
```

- `stringtheory` is the format version, so older Pis can say "update String Theory to import this" instead of guessing.
- A **pattern** has the same fields the Custom tab saves: colours, bulbs per colour, effect, built-in effect number and speed.
- A **playlist** refers to built-in shows by their ID (`classic`, `snowfall`…). It can also bundle the custom patterns it uses, under `includes`, referenced as `@0`, `@1` and so on, so one file carries everything it needs.
- Shows are always built to fit the receiving zone's length, so a show made on the 48-bulb website preview works on 24 or 200 bulbs.

## Getting it from the website to your lights

Three ways, from easiest to most manual. All three end in the same **Import** screen.

1. **Send to my lights (one tap).** The first time, the website asks for your String Theory address (for example `http://192.168.x.x:8080`) and remembers it only in that browser. "Send to my lights" then simply *opens* `http://<your-pi>:8080/#import=<show>` in a new tab, with the show encoded in the address after the `#`. Opening a page is allowed where a website reaching into your network isn't, and the part after `#` never leaves your phone except to your own Pi's page. This only works on your home Wi-Fi, as intended.
2. **Share code.** The website shows the same encoded show as text, or as a QR code. On the Custom tab, **Import** and **Paste a code** accept it. This is handy for sending a show to a friend in a message.
3. **File.** Download a `.stringtheory.json` file and pick it on the Custom tab with **Import** and **Choose a file**. Files also make good backups.

## The Import screen (on the Pi's page)

- Shows what's arriving: its name, kind, preview animation (built from your own zone's previews) and any bundled patterns.
- Checks it with the same rules as the Custom tab (colours, times, transitions, IDs it knows, size limits). Anything it can't use is explained in plain words. For example: "This playlist uses *Lunar New Year*, which your String Theory doesn't have yet. Update to get it."
- Name clashes offer **Keep both** (it adds "2" to the name) or **Replace**.
- Buttons: **Save**, **Save and play** (in the current zone) and **Cancel**. Nothing is saved until you choose.

Server side, this becomes one new endpoint, `POST /api/import`. It reuses `clean_custom()` for each pattern and playlist, rewrites `@n` references to the new custom IDs, and saves everything in one go.

## Export (the other direction)

Each saved custom pattern or playlist gets **Share** next to Edit and Delete. Share produces the same file, code or QR code. Built-in playlists get it too, after **Edit a copy**. So shows can travel between two homes as well as from the website.

## The website

- A copy of the control page's Custom tab: the pattern editor, the playlist builder, and every built-in show's preview (exported once from the Pi code at 48 bulbs, so the website runs no Python).
- **Gallery (optional, later):** people publish shows to a shared list stored in the Spacefast space's database. Others browse it by holiday or colour, preview the shows, and send them home. That needs moderation and a report button, so it's a separate step.
- Built-in effects can't be previewed anywhere but on real controllers. Patterns that use them say so.

## Steps

1. Define the show file format and add **Import** (code and file) and **Share** to the Custom tab. This is useful on its own for backups and sharing with friends.
2. Add `#import=` link handling, so a tap on a link opens the Import screen.
3. Build the Spacefast website: the builders, previews, "Send to my lights", share codes and QR codes.
4. Optionally, a public gallery.

## Open questions

- Should imported shows remember where they came from (author, website link) and show that on the card?
- Do we want a public gallery at all, or just private sharing by link and code?
