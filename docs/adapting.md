# Make String Theory work with your lights

String Theory is tested on **NOMA smart C9** strings (Wi-Fi controller AL901B). Many other Tuya light strings work the same way. Some need a setting changed, and a few need one small function adapted. This guide shows how to find out which applies to yours, in about 20 minutes, with the `tools/probe.py` helper.

You'll need:
- your `devices.json` and `tinytuya.json` from the wizard (step 1 of the README)
- Python with tinytuya (`pip install tinytuya`)
- your phone with the Smart Life app

Run every command below from the folder that holds `devices.json`. Close the Smart Life app before running `paint` or `power`, because some controllers only accept one local connection at a time.

## 1. Find your controller

```sh
python tools/probe.py list
```

This lists every device the wizard found, with its IP address, protocol version and model:

```
Porch left                   192.168.1.40     v3.5   C9 Lights AL901B
```

- **No IP address:** the device wasn't found on your network. Make sure the computer is on the same Wi-Fi, run `python -m tinytuya scan`, then run the wizard again.
- **The model:** if it's **AL901B**, you have NOMA C9 controllers. Skip to step 5.

## 2. See its data points

Tuya controllers expose everything as numbered **data points (DPs)**.

```sh
python tools/probe.py dps "Porch left"
```

```
  DP   20  switch_led             bool    True
  DP  102  color_bar              raw     (not reporting right now)
  DP  104  effect_control         raw     (not reporting right now)
```

You're looking for two things:
- **An on/off switch.** Usually DP 20, named `switch_led`, type bool.
- **A per-bulb colour DP.** Type raw, with a name like `color_bar`, `paint_colour`, `dreamlight` or `segment`. On NOMA C9 it's DP 102.

The names come from Tuya's cloud and need your developer project's trial to be active (see the README).

## 3. Watch what the app sends

Many DPs only show up once they're used. Run:

```sh
python tools/probe.py sniff "Porch left"
```

Then, in the Smart Life app:
- Open the light's **DIY**, **paint** or **colour each bulb** mode, and give a couple of bulbs different colours.
- Switch the light off and on.
- Pick a few built-in effects.

Each change prints the DP that changed. Raw DPs are shown as hex bytes:

```
20:14:03 DP 102: raw: 00 00 00 01 01 ff 00 00 00 00 00 ff 00 00 00 ...
```

Make a note of:
- the DP that changed when you painted bulbs: your **paint DP**
- the bytes it sent
- the DP that changed when you picked an effect: your **effect DP**

## 4. Compare with NOMA's format

String Theory sends each string a paint frame like this:

```
00 00 00 01 01 | R G B 00 00 | R G B 00 00 | ...   (5 bytes per bulb)
```

That's a 5-byte header, then 5 bytes for each bulb: red, green and blue, then two zero bytes.

- **Your paint bytes look like this:** your controller uses the same format. Go to step 5.
- **Same idea, but a different DP number:** that's only a setting. Use step 5 with `--dp`, then step 6.
- **A different layout of bytes:** see [When the format is different](#when-the-format-is-different).

## 5. Test it on the lights

With the string in view, close the Smart Life app and run this, using your bulb count and your paint DP if it isn't 102:

```sh
python tools/probe.py paint "Porch left" 24 --dp 102
```

You should see these six steps:
1. every bulb red
2. all off
3. only the first bulb red
4. only the last bulb blue
5. red and green alternating
6. one red bulb walking from the first bulb to the last

- **All six were right:** your lights work with String Theory as they are.
- **Nothing happened:** try your other raw DPs with `--dp`.
- **The wrong bulbs lit up, or the colours were wrong:** see the next section.

## 6. Tell String Theory

Run `python pi/configure.py` to add your strings and their bulb counts. If your DPs aren't NOMA's, add them to `data/config.json`:

```json
{
  "strings": [{"name": "Porch left", "bulbs": 24}, {"name": "Porch right", "bulbs": 24}],
  "dp_switch": 20,
  "dp_paint": 102,
  "dp_effect": 104
}
```

Then start String Theory and play **Find the seams** and **Bulb walk** on the Tests tab. Find the seams shows where each string starts and ends. Bulb walk shows one bulb at a time, and any skipped bulb is a dropped update.

## When the format is different

All brand-specific code lives in two small functions in `pi/lights.py`:

- **`frame(bulbs)`** turns a list of `(r, g, b)` colours into the bytes for the paint DP.
- **`effect_payload(mode, speed, colours)`** builds the bytes for the controller's built-in effects. These are only used by Create → Built into the controllers, so String Theory works without them.

Common differences are:
- a different header
- 3 or 4 bytes per bulb instead of 5
- colours sent as hue, saturation and value instead of RGB
- a bulb count in the header
- groups of bulbs ("segments") instead of single bulbs

The bytes you captured with `sniff` in step 3 are the answer key. Paint a known pattern in the app, such as the first bulb red and the rest off, compare the bytes to it, and change `frame()` to produce the same thing.

### Let an AI coding assistant do it

The project includes a `CLAUDE.md` that explains how String Theory works, so an assistant such as Claude Code can make this change safely. Open the project folder in it and paste this prompt, filling in the parts in brackets:

> My Tuya light strings aren't NOMA C9. The model is [model from probe.py list], protocol [version].
> `tools/probe.py dps` shows: [paste the output].
> When I painted [describe exactly what you painted, e.g. "bulb 1 red, the rest off"] in the Smart Life app, `tools/probe.py sniff` printed: [paste the line].
> Please adapt String Theory to my controller: set the DPs in `data/config.json` and change `frame()` in `pi/lights.py` if the byte layout differs. Then give me a `tools/probe.py paint` command to check it.

Never paste your `devices.json`, `tinytuya.json` or any local keys into a chat. The assistant doesn't need them.

### Share what you found

No help is offered with this (see [SUPPORT.md](../SUPPORT.md)): this guide, `probe.py` and an AI coding assistant are the tools for doing it yourself.

If you get another brand working, you're welcome to share it in a pull request or in your own fork's README. Include:
- the controller model
- the protocol version
- your DP numbers
- any change to `frame()`

That way, the next person with the same lights won't have to do this. Pull requests may not be reviewed.
