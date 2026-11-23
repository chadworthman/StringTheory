# Lights that work with String Theory

## Tested

**NOMA Smart RGB C9 25 LED Outdoor Christmas Lights, 25 ft 7 in** (Canadian Tire product 251-2320-P): [product page](https://www.canadiantire.ca/en/pdp/noma-smart-rgb-c9-25-led-outdoor-christmas-lights-25-ft-7-in-2512320p.html)

- **Controller:** Wi-Fi, model AL901B. It's set up in the Smart Life (Tuya) app, and appears in it as "C9 Lights".
- **Protocol:** Tuya local protocol 3.5. String Theory talks to it over your home Wi-Fi, with no cloud.
- **Bulbs:** Canadian Tire lists 25 LEDs, but the controller's per-bulb frame has 24 colours, so give `configure.py` 24 for each string. Play **Bulb walk** on the Tests tab and count, to check yours.
- **Data points:** on/off is DP 20 (`switch_led`), per-bulb colours DP 102 (`color_bar`) and built-in effects DP 104 (`effect_control`). These are String Theory's defaults, so there's nothing to set.
- **Several strings:** this is tested with two strings laid end to end, each with its own controller on Wi-Fi. Any number works. Each controller needs a decent Wi-Fi signal: one with a weak signal drops frames, and its part of a chase stutters.
- **Speed:** each controller takes at most about three frames a second. String Theory's shows are built around that.

## Probably works

Other Tuya Wi-Fi light strings where each bulb can be its own colour. These are often sold as RGBIC, "colour bar", "dreamcolor" or "paint" lights, and are set up in the Smart Life or Tuya Smart app. They may use different data points, or pack bulb colours differently. [docs/adapting.md](adapting.md) shows how to check yours in about 20 minutes, and what to change.

### Where to look

None of these are tested with String Theory. They're Amazon searches for lights that are likely to work. Check each listing against the list below before buying.

| What | Amazon.com (US) | Amazon.ca (Canada) |
|---|---|---|
| Tuya / Smart Life RGBIC string lights | [search](https://www.amazon.com/s?k=tuya+smart+life+rgbic+string+lights) | [search](https://www.amazon.ca/s?k=tuya+smart+life+rgbic+string+lights) |
| Smart Life RGBIC Christmas lights | [search](https://www.amazon.com/s?k=smart+life+rgbic+christmas+lights) | [search](https://www.amazon.ca/s?k=smart+life+rgbic+christmas+lights) |
| Smart Life RGBIC globe (patio) string lights | [search](https://www.amazon.com/s?k=smart+life+rgbic+globe+string+lights) | [search](https://www.amazon.ca/s?k=smart+life+rgbic+globe+string+lights) |
| NOMA Smart RGB C9 lights (the tested set) | [search](https://www.amazon.com/s?k=noma+smart+rgb+c9+lights) | [search](https://www.amazon.ca/s?k=noma+smart+rgb+c9+lights) |

The tested NOMA set is sold mainly at [Canadian Tire](https://www.canadiantire.ca/en/pdp/noma-smart-rgb-c9-25-led-outdoor-christmas-lights-25-ft-7-in-2512320p.html). The [NOMA Smart Permanent RGB LED Lights, 100 ft](https://www.canadiantire.ca/en/pdp/noma-smart-permanent-rgb-led-lights-72-pc-100-ft-2511136p.html) there are probably the same Smart Life family, but that isn't confirmed.

Before buying, check the listing for all of these:
- It says **Smart Life** or **Tuya Smart** app.
- It says **2.4 GHz Wi-Fi**, not Bluetooth-only.
- It says **RGBIC**, "addressable" or "each bulb a different colour" (plain "RGB" usually means the whole string is one colour).

Avoid **Govee**, **Twinkly**, **Lepro**, **eufy** and **NOMA Advanced**. They use their own apps and protocols, not Tuya.

## Doesn't work

- **NOMA Advanced** lights and the **NOMA Advanced Smart Voice Command Hub** (Canadian Tire 151-3973-6). These are a separate product line, made by Gemmy and controlled by the NOMA Advanced Christmas app through the hub, not by Tuya. Their protocol isn't published, so String Theory can't drive them.
- **Single-colour or whole-string-colour lights.** They can't show a different colour on each bulb, so most shows can't work.
- **Bluetooth-only lights.** String Theory needs a controller on your Wi-Fi.

If you get another model working, you're welcome to share the model, protocol version, data points and any code change in a pull request or your own fork. No support is provided (see [SUPPORT.md](../SUPPORT.md)), so pull requests may not be reviewed.
