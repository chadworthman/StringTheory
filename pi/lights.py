#!/usr/bin/env python3
"""String Theory: light show engine.

Any number of Tuya Wi-Fi light strings (tested on NOMA smart C9), laid end to end, driven as one long string over the LAN.

  lights.py run              # the service: plays the current show during ON hours, off otherwise
  lights.py <show>           # switch show (candycane, halloween, rainbow, chase5) - remembered
  lights.py status           # current show and schedule
  lights.py on [hours]       # force on (default 1 h), ignoring the schedule
  lights.py off [hours]      # force off (default 1 h)
  lights.py auto             # back to the schedule
  lights.py schedule 16:00 00:00   # change the daily on/off times

Timing notes (measured): each string applies at most ~1 frame / 0.3 s. Frames are sent without
waiting for the ~0.5 s ack, and each string only gets the newest frame once it has acked the last,
so a string with weak Wi-Fi skips frames but never falls behind. Animation position comes from the
clock, so every string always shows the same moment of the show.
"""
import base64, collections, colorsys, importlib.util, math, datetime, json, os, random, sys, threading, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
# Where your files live: devices.json (keys, from the tinytuya wizard), config.json (your strings) and the
# files the engine writes. Next to the code by default; set STRINGTHEORY_DATA to keep them elsewhere
# (the Docker image uses /data).
DATA = Path(os.environ.get('STRINGTHEORY_DATA') or HERE)
DEVICES = DATA / 'devices.json'
CONFIG = DATA / 'config.json'
STATE = DATA / 'state.json'
ENGINE = DATA / 'engine.json'   # where the current show's clock is, so the web page can mirror it
HEALTH = DATA / 'health.json'   # what each string is actually doing, for the web page
try: _CFG = json.loads(CONFIG.read_text())
except FileNotFoundError: _CFG = {}
# Your strings, in the order they're laid out (each one's last bulb meets the next one's first):
# (device name from devices.json, number of bulbs). Set them in config.json with configure.py.
STRINGS = [(s['name'], int(s['bulbs'])) for s in _CFG.get('strings', [])] or [('C9 Lights', 24), ('C9 Lights 2', 24)]
ORDER = [name for name, _ in STRINGS]
# Shows are built for one run of bulbs. This module is that run for all the strings; each zone gets its
# own copy of the module built for just its strings (see zone_module), so a show fills each zone.
ZONE_STRINGS = globals().get('_ZONE_STRINGS') or STRINGS
SIZES = [n for _, n in ZONE_STRINGS]
OFFSETS = [sum(SIZES[:i]) for i in range(len(SIZES))]     # where each string starts in the run
TOTAL = sum(SIZES)
N = SIZES[0]                                               # bulbs in the first string
# Tuya data points (DPs) used. These are the NOMA C9 (AL901B) numbers; other Tuya light strings
# often match, but check yours with tools/sniff.py while you change things in the Smart Life app.
DP_SWITCH = _CFG.get('dp_switch', 20)      # on/off
DP_PAINT = _CFG.get('dp_paint', 102)       # per-bulb colours: 00 00 00 01 01, then R G B 00 00 for each bulb
DP_EFFECT = _CFG.get('dp_effect', 104)     # the controller's built-in effects
DEFAULT_ON, DEFAULT_OFF = '16:00', '00:00'   # local time; changed from the page (saved in state.json)

RED, WHITE = (255, 0, 0), (255, 255, 255)   # pure white: a warmer (255,190,140) reads pink/peach on these LEDs
ORANGE, PURPLE = (255, 110, 0), (190, 0, 255)
C9 = [(255, 0, 0), (0, 255, 0), (255, 180, 0), (0, 40, 255), (255, 100, 0)]   # red, green, yellow, blue, orange
RAINBOW = [tuple(round(x * 255) for x in colorsys.hsv_to_rgb(i / TOTAL, 1, 1)) for i in range(TOTAL)]


CANDY = [RED] * 3 + [WHITE] * 3 + [(0, 255, 0)] * 3 + [WHITE] * 3   # candy cane with green, three bulbs a stripe
ICE = [(0, 40, 255), (120, 180, 255), (255, 255, 255)]
DEEP, MID, PALE = (0, 40, 255), (0, 120, 255), (80, 200, 255)
ICY = [DEEP] * 3 + [PALE] * 3 + [WHITE] * 3 + [PALE] * 3   # bands of deep blue, ice blue and white (no in-between shades)
GHOUL = (0, 90, 10)            # dark Halloween green (a dimmer, slightly cool green)
STRING_COLOURS = [(255, 0, 0), (0, 255, 0), (0, 40, 255), (255, 180, 0), (190, 0, 255), (255, 255, 255)]   # red, green, blue, yellow, purple, white
def tile(pattern, n): return [pattern[i % len(pattern)] for i in range(n)]
# Test pattern: the old TV colour bars. Strings take turns: the main bars across one string, then the
# reversed "castellation" band (blue, black, magenta, black, cyan, black, white) across the next.
BARS = [WHITE, (255, 180, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 40, 255)]
CASTELLATION = [(0, 40, 255), (0, 0, 0), (255, 0, 255), (0, 0, 0), (0, 255, 255), (0, 0, 0), WHITE]
def bars(colours, n): return [colours[i * len(colours) // n] for i in range(n)]   # equal-width bars over n bulbs
TEST_PATTERN = [c for i, n in enumerate(SIZES) for c in bars(BARS if i % 2 == 0 or len(SIZES) == 1 else CASTELLATION, n)]

GAMMA = 2.2
def blend(a, b, t):
    """Mix colour a→b by t (0..1) in perceived brightness, so fades look even on linear LEDs."""
    lin = lambda v: (v / 255) ** GAMMA
    return tuple(round(255 * (lin(x) + (lin(y) - lin(x)) * t) ** (1 / GAMMA)) for x, y in zip(a, b))

def scanner(base, dot, step, span=TOTAL, trail=None, gap=2, mirror=None, tail=()):
    """All `base`, with one `dot` bouncing over the first `span` bulbs.
    Optional `trail` colour follows `gap` steps behind the dot (so it bounces too)."""
    period = 2 * (span - 1)
    def where(k):
        k %= period
        return k if k < span else period - k
    def show(t):
        k = int(t / step)
        bulbs = [base] * TOTAL
        for j, strength in reversed(list(enumerate(tail, 1))):      # fading tails, faintest first
            bulbs[where(k - j)] = blend(base, dot, strength)
            if mirror is not None: bulbs[span - 1 - where(k - j)] = blend(base, mirror, strength)
        if trail is not None: bulbs[where(k - gap)] = trail
        if mirror is not None: bulbs[span - 1 - where(k)] = mirror   # starts at the far end, crosses mid-way
        bulbs[where(k)] = dot                # dot wins if they overlap at a turnaround
        return bulbs
    show.period = period * step; show.step = step
    return show

def converge(pattern, step):
    """Pattern flows from both outer ends toward the join in the middle (mirror-image halves)."""
    half = TOTAL // 2
    def show(t):
        off = int(t / step)
        left = [pattern[(p - off) % len(pattern)] for p in range(half)]
        return left + left[::-1]
    show.period = len(pattern) * step; show.step = step
    return show

def chase_with_white(pattern, step, wipe_step=0.5, chase_secs=30, hold_secs=8, white=WHITE):
    """Chase, then white wipes in along the chase direction, holds, then the chase wipes back in."""
    wipe = TOTAL * wipe_step
    cycle = chase_secs + wipe + hold_secs + wipe
    base = chase(pattern, step)
    def show(t):
        bulbs = base(t); c = t % cycle
        if c < chase_secs: return bulbs
        c -= chase_secs
        if c < wipe:                                   # white sweeps in from bulb 0
            n = int(c / wipe_step) + 1
            return [white] * n + bulbs[n:]
        c -= wipe
        if c < hold_secs: return [white] * TOTAL
        c -= hold_secs
        n = int(c / wipe_step) + 1                     # colours sweep back in from bulb 0
        return bulbs[:n] + [white] * (TOTAL - n)
    show.period = cycle; show.step = min(step, wipe_step)
    return show

def static_white_loop(pattern, hold=120, step=0.5, white=WHITE):
    """Static pattern (hold) -> pattern chases out the far end with white filling in behind it ->
    all white (hold) -> pattern chases back in from the start, pushing white out -> repeat.
    The pattern lands exactly on its static position, so there's no jump at either end."""
    move = TOTAL * step
    cycle = hold + move + hold + move
    L = len(pattern)
    def show(t):
        c = t % cycle
        if c < hold: return [pattern[p % L] for p in range(TOTAL)]
        c -= hold
        if c < move:
            k = int(c / step) + 1
            return [white if p < k else pattern[(p - k) % L] for p in range(TOTAL)]
        c -= move
        if c < hold: return [white] * TOTAL
        c -= hold
        k = int(c / step) + 1
        return [pattern[(p + TOTAL - k) % L] if p < k else white for p in range(TOTAL)]
    show.period = cycle; show.step = step
    return show

def playlist(items, hold=120, step=0.5, white=WHITE):
    """items: [(pattern, via_white), ...]. Each pattern is held still, then slides out toward the far
    end while the next one slides in behind it. If via_white, it slides out to all-white, white is
    held, then the next pattern slides in. Patterns always land exactly on their still position."""
    move = TOTAL * step
    WHITE_ALL = [white]
    def still(pat): return [pat[p % len(pat)] for p in range(TOTAL)]
    def slide(old, new, k):   # new pattern pushes in from bulb 0; old pattern moves on ahead of it
        return [new[(p + TOTAL - k) % len(new)] if p < k else old[(p - k) % len(old)] for p in range(TOTAL)]
    phases = []               # (duration, fn(c) -> bulbs)
    for i, (pat, via_white) in enumerate(items):
        nxt = items[(i + 1) % len(items)][0]
        phases.append((hold, lambda c, pat=pat: still(pat)))
        if via_white:
            phases.append((move, lambda c, pat=pat: slide(pat, WHITE_ALL, int(c / step) + 1)))
            phases.append((hold, lambda c: [white] * TOTAL))
            phases.append((move, lambda c, nxt=nxt: slide(WHITE_ALL, nxt, int(c / step) + 1)))
        else:
            phases.append((move, lambda c, pat=pat, nxt=nxt: slide(pat, nxt, int(c / step) + 1)))
    cycle = sum(d for d, _ in phases)
    def show(t):
        c = t % cycle
        for d, fn in phases:
            if c < d: return fn(c)
            c -= d
    show.period = cycle; show.step = step
    return show

def jostle(step=0.5, swaps=5, half=72, drift_every=3):
    """Confetti on the move: the 48 rainbow colours in random spots, neighbours swapping places
    every step while the whole lot drifts slowly along. The swaps play forward for `half` steps,
    then back, so it loops without a jump; the seed is fixed so the page preview matches the lights."""
    rnd = random.Random(1225)
    perms = [rnd.sample(RAINBOW, TOTAL)]
    for _ in range(half):
        p = list(perms[-1])
        for _ in range(swaps):
            i = rnd.randrange(TOTAL - 1); p[i], p[i + 1] = p[i + 1], p[i]
        perms.append(p)
    loop = 2 * half                          # also a multiple of TOTAL * drift_every, so the drift loops too
    def show(t):
        k = int(t / step); m = k % loop
        p = perms[m if m <= half else loop - m]
        d = k // drift_every
        return [p[(x - d) % TOTAL] for x in range(TOTAL)]
    show.period = loop * step * TOTAL * drift_every // math.gcd(loop, TOTAL * drift_every); show.step = step
    return show

def seams(step=0.6):
    """Where every string starts and ends. Each string glows dimly in its own colour (red, green,
    blue...); its first bulb blinks white and its last bulb is its colour at full brightness. So at a
    seam you see a bright bulb, then a blinking white one: the end of one string meeting the next."""
    def show(t):
        blink = int(t / step) % 2 == 0
        bulbs = []
        for i, n in enumerate(SIZES):
            c = STRING_COLOURS[i % len(STRING_COLOURS)]
            body = [blend(OFF, c, 0.18)] * n
            body[-1] = c
            body[0] = WHITE if blink else OFF
            bulbs += body
        return bulbs
    show.period = 2 * step; show.step = step
    return show

def walk(colour, step):
    """One bulb lit, stepping along every bulb in order, the rest dark. A skipped step = a dropped update."""
    def show(t):
        bulbs = [(0, 0, 0)] * TOTAL
        bulbs[int(t / step) % TOTAL] = colour
        return bulbs
    show.period = TOTAL * step; show.step = step
    return show

def chase(pattern, step):
    def show(t):
        off = int(t / step)
        return [pattern[(p - off) % len(pattern)] for p in range(TOTAL)]
    show.period = len(pattern) * step; show.step = step
    return show


# ---- themes ----------------------------------------------------------------------------------
OFF = (0, 0, 0)
GREEN, BLUE, GOLD = (0, 255, 0), (0, 40, 255), (255, 150, 0)
PINK = (255, 30, 90)

def gradient(stops, n=TOTAL):
    """n colours blending through `stops` (evenly spaced), in perceived brightness."""
    out = []
    for i in range(n):
        x = i / (n - 1) * (len(stops) - 1); j = min(int(x), len(stops) - 2)
        out.append(blend(stops[j], stops[j + 1], x - j))
    return out

def embers(step=0.4, loop=150):
    """Glowing coals: each bulb sits somewhere between deep red and amber, drifting every couple of
    steps, with quick random flare-ups. Chunky flicker reads as fire, so the slow update rate suits it."""
    heat = [(120, 5, 0), (190, 20, 0), (255, 45, 0), (255, 90, 0), (255, 140, 0), (255, 190, 40)]
    def show(t):
        k = int(t / step) % loop
        out = []
        for i in range(TOTAL):
            glow = random.Random(i * 7919 + (k // 3) * 104729).random()       # slow per-bulb glow
            flick = random.Random(i * 31 + k * 1009).random()                # fast flicker
            lvl = int(glow * 4) + (flick > 0.8) + (flick > 0.96)
            out.append(heat[min(lvl, len(heat) - 1)])
        return out
    show.period = loop * step; show.step = step
    return show

def snowfall(step=0.5):
    """Night-blue string with white flakes drifting toward the far end at different speeds, where
    snow slowly piles up and melts away again."""
    night, drift = (0, 15, 110), (90, 140, 255)
    flakes = [(0, 1), (9, 2), (17, 1), (25, 3), (31, 2), (40, 1), (44, 3)]   # (start bulb, steps per move)
    loop = TOTAL * 6                                             # every flake speed divides this evenly
    pile_max = max(2, TOTAL // 8)
    def show(t):
        k = int(t / step) % loop
        bulbs = [night] * TOTAL
        half = loop // 2
        pile = round(pile_max * (k / half if k < half else (loop - k) / half))
        for start, every in flakes:
            p = (start + k // every) % TOTAL
            if p > 0: bulbs[p - 1] = drift if bulbs[p - 1] == night else bulbs[p - 1]   # faint trail
            bulbs[p] = WHITE
        for i in range(TOTAL - pile, TOTAL): bulbs[i] = WHITE
        return bulbs
    show.period = loop * step; show.step = step
    return show

def new_year(step=1.0, burst_step=0.4):
    """Gold and white stepping calmly along, then for the first minute after midnight a burst of
    rapid gold and white flashes (by the Pi's clock, whatever the show speed)."""
    calm = chase([GOLD, GOLD, WHITE, WHITE, OFF], step)
    def show(t):
        now = datetime.datetime.now()
        if now.hour == 0 and now.minute == 0:
            rnd = random.Random(int(time.time() / burst_step))
            return [rnd.choice((WHITE, WHITE, GOLD, OFF)) for _ in range(TOTAL)]
        return calm(t)
    show.period = calm.period; show.step = step
    return show

# First evening of Hanukkah (candle 1 is lit that evening).
HANUKKAH = {2026: (12, 4), 2027: (12, 24), 2028: (12, 12), 2029: (12, 1), 2030: (12, 20),
            2031: (12, 9), 2032: (11, 27), 2033: (12, 16), 2034: (12, 6), 2035: (12, 25)}
def hanukkah_night(day=None):
    """1-8 on the evenings of Hanukkah, else None."""
    day = day or datetime.date.today()
    for y, (m, d) in HANUKKAH.items():
        n = (day - datetime.date(y, m, d)).days + 1
        if 1 <= n <= 8: return n
    return None

def hanukkah(step=0.4, loop=100):
    """A menorah across the whole length: the shamash in the middle, four candles either side. During
    Hanukkah one more candle is lit each night (right to left); other times all eight are lit."""
    unlit, body, flame = (0, 8, 60), BLUE, (255, 190, 60)
    mid = TOTAL // 2
    w = max(1, min(5, (mid - 2) // 4))                                     # bulbs per candle (5 on 48 bulbs)
    left = [list(range(mid - 2 - w * (4 - g), mid - 2 - w * (3 - g))) for g in range(4)]
    right = [list(range(mid + 2 + w * g, mid + 2 + w * (g + 1))) for g in range(4)]
    order = right[::-1] + left[::-1]                                       # candle 1 = far right
    def show(t):
        k = int(t / step) % loop
        n = hanukkah_night() or 8
        bulbs = [unlit] * TOTAL
        def fl(i): return WHITE if random.Random(i * 97 + k * 7).random() < 0.6 else flame
        for c, cand in enumerate(order):
            if c < n:
                look = [body, PALE, None, PALE, body] if w == 5 else [body] * w
                for j, i in enumerate(cand): bulbs[i] = look[j] if j != w // 2 else fl(i)
            else:
                for i in cand: bulbs[i] = (0, 20, 120)
        bulbs[mid - 2] = bulbs[mid + 1] = PALE                             # shamash in the middle
        for i in (mid - 1, mid): bulbs[i] = fl(i)
        return bulbs
    show.period = loop * step; show.step = step
    return show

def easter_sunday(y):
    """Gregorian Easter (anonymous algorithm)."""
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25; g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31; day = (h + l - 7 * m + 114) % 31 + 1
    return datetime.date(y, month, day)

def holiday_for(day=None):
    """Which show suits the date."""
    day = day or datetime.date.today()
    md = (day.month, day.day)
    if hanukkah_night(day): return 'hanukkah'
    if md == (12, 31) or md == (1, 1): return 'newyear'
    if (2, 7) <= md <= (2, 14): return 'valentines'
    if (3, 10) <= md <= (3, 17): return 'stpats'
    if 0 <= (easter_sunday(day.year) - day).days <= 7: return 'easter'
    if (6, 24) <= md <= (7, 1): return 'canada'
    if (7, 2) <= md <= (7, 4): return 'fourthmove'
    if day.month == 10: return 'halloween'
    if md >= (11, 15) or md <= (1, 6): return 'classicloop'
    return 'classic'

class Seasonal:
    """Plays whichever show suits today's date (see holiday_for)."""
    def pick(self): return holiday_for()
    def __call__(self, t): return SHOWS[self.pick()](t)
    @property
    def period(self): return getattr(SHOWS[self.pick()], 'period', 0)
    @property
    def step(self): return getattr(SHOWS[self.pick()], 'step', None)

GOLDEN = (3 - 5 ** 0.5) / 2          # 0.382: the golden angle (137.5 degrees) as a fraction of a turn
def hue(h, v=1.0): return tuple(round(x * 255 * v) for x in colorsys.hsv_to_rgb(h % 1, 1, 1))
GOLDEN_ANGLE = [hue(i * GOLDEN) for i in range(TOTAL)]     # each bulb a golden-angle turn round the colour wheel

def fibonacci(stage=1.0, full=4.0):
    """On a white string, golden-angle colours growing from the first bulb by Fibonacci numbers (1, 2, 3, 5, 8, 13,
    21, 34...) until the whole string is lit, holding, then going out from the first bulb by the
    same numbers, so the light travels along the string and off the far end. Each round turns the
    colour wheel a third, so three rounds make one loop."""
    sizes, a, b = [], 1, 2
    while a < TOTAL: sizes.append(a); a, b = b, a + b
    sizes.append(TOTAL)
    # (first lit bulb, bulbs lit up to, seconds)
    frames = ([(0, n, stage) for n in sizes] + [(0, TOTAL, full)]
              + [(n, TOTAL, stage) for n in sizes] + [(TOTAL, TOTAL, stage)])
    cycle = sum(d for _, _, d in frames)
    def show(t):
        r = int(t // cycle) % 3; c = t % cycle
        for lo, hi, d in frames:
            if c < d: break
            c -= d
        return [hue(i * GOLDEN + r / 3) if lo <= i < hi else WHITE for i in range(TOTAL)]   # on a white base
    show.period = cycle * 3; show.step = stage
    return show

def chaos(step=0.4, loop=300, change=0.3):
    """Saturated colours changing at random, the whole string lurching back and forth, with
    random white bursts, the odd full-string strobe, and sudden blackouts of a stretch or the whole string. Deterministic per step, so every string agrees."""
    def colour(i, k):
        for j in range(k, k - 30, -1):                  # most recent step at which this bulb changed
            r = random.Random((j % loop) * 1000003 + i)
            if r.random() < change: return hue(r.random())
        return hue(random.Random(i).random())
    rnd = random.Random(4242); walk = [0]
    for _ in range(loop): walk.append(walk[-1] + rnd.choice((-3, -2, -1, 0, 1, 2, 3, 5)))
    wob = [walk[m] - round(walk[loop] * m / loop) for m in range(loop)]   # ends where it starts
    def show(t):
        k = int(t / step) % loop
        bulbs = [colour((x - wob[k]) % TOTAL, k) for x in range(TOTAL)]
        ev = random.Random(k * 31337)
        if ev.random() < 0.08:                          # a white burst somewhere
            a = ev.randrange(TOTAL); n = ev.randint(3, 10)
            for x in range(a, min(TOTAL, a + n)): bulbs[x] = WHITE
        if ev.random() < 0.03:                          # whole-string strobe
            bulbs = [hue(ev.random())] * TOTAL
        for j in range(k, k - 3, -1):                   # dark segments: a stretch of 4-14 bulbs out for 1-3 steps
            g = random.Random((j % loop) * 104729 + 3)
            if g.random() < 0.15 and k - j < g.randint(1, 3):
                a = g.randrange(TOTAL); n = g.randint(4, 14)
                for x in range(a, min(TOTAL, a + n)): bulbs[x] = (0, 0, 0)
        for j in range(k, k - 4, -1):                   # a sudden blackout, 1 to 4 steps long
            b = random.Random((j % loop) * 7919 + 17)
            if b.random() < 0.035 and k - j < b.randint(1, 4):
                return [(0, 0, 0)] * TOTAL
        return bulbs
    show.period = loop * step; show.step = step; show.tick = step
    return show

# Aurora colours: solid bands of the northern lights' colours, one colour per bulb in each band (no
# blending; a string of single-colour bulbs can't show the real aurora's top-to-bottom shading).
AURORA_BANDS = [(0, 255, 60)] * 3 + [(0, 200, 160)] * 3 + [(0, 60, 255)] * 3 + [(150, 0, 255)] * 3 \
             + [(0, 60, 255)] * 3 + [(0, 200, 160)] * 3

def aurora_waves(step=0.5, period=24.0, cell=21):
    """Aurora colours breathing: the bands stay put while the blue on either side of each purple
    centre slowly widens and narrows (2 to 4 bulbs), taking room from the teal and green. Each group
    breathes a little out of step with its neighbours, so the whole string doesn't pulse at once."""
    green, teal, blue, purple = (0, 255, 60), (0, 200, 160), (0, 60, 255), (150, 0, 255)
    mid = cell // 2
    def show(t):
        t = int(t / step) * step
        out = []
        for x in range(TOTAL):
            k, d = divmod(x, cell)
            d = abs(d - mid)                                     # distance from this group's purple centre
            w = round(3 + math.sin(2 * math.pi * (t / period + k * 0.3)))   # blue width, 2..4
            out.append(purple if d <= 1 else blue if d <= 1 + w else teal if d <= 4 + w else green)
        return out
    show.period = period; show.step = step
    return show

TREE = [GREEN, GREEN, RED, GREEN, GREEN, GOLD, GREEN, GREEN, BLUE]   # green with red, gold and blue ornaments

def twinkle_tree(step=0.4, loop=120):
    """The Christmas tree with its ornaments twinkling: every non-green bulb dips out and glows back
    in (0.15, 0.45, 0.8, then full) on its own rhythm, so a few are always mid-twinkle. Green stays steady."""
    dip = [0.15, 0.45, 0.8]
    lengths = [8, 10, 12, 15, 20, 24]                      # all divide `loop`, so it repeats cleanly
    rnd = random.Random(2512)
    rhythm = {i: (rnd.choice(lengths), rnd.randrange(24)) for i in range(TOTAL) if TREE[i % len(TREE)] != GREEN}
    def show(t):
        k = int(t / step) % loop
        bulbs = tile(TREE, TOTAL)
        for i, (n, phase) in rhythm.items():
            j = (k + phase) % n
            if j < len(dip): bulbs[i] = blend(OFF, bulbs[i], dip[j])
        return bulbs
    show.period = loop * step; show.step = step; show.tick = step
    return show

# Sunset: stripes of red, orange, amber, pink and purple, three bulbs each, mirrored about the centre.
SUNSET_BANDS = [(255, 0, 0), (255, 110, 0), (255, 180, 0), (255, 40, 90), (150, 0, 200)]

def sunrise(step=0.5, ramp=44.0, hold=8.0, night=3.0, lead=0.7):
    """Sunrise and sunset as one continuous journey for every bulb: deep night blue -> blue -> purple -> red -> orange ->
    yellow -> white, and back, each colour change taking the same time, so the string never rests on red.
    The centre leads and the ends follow (lead = how far behind the ends are). At the peak the centre is
    white and the ends bright yellow. Then it holds, sets the same way to dark, rests a moment and repeats."""
    path = [(0, 0, 50), (0, 40, 255), (150, 0, 200), (255, 0, 0),     # deep night blue (never black), blue, purple, red,
            (255, 0, 0),                                             # red again: a wider band of red bulbs
            (255, 100, 0), (255, 180, 0), (255, 255, 255)]           # orange, yellow, white
    steps = len(path) - 1
    def along(h):                                     # h 0..1 along the whole path, blended
        x = max(0.0, min(1.0, h)) * steps
        i = min(int(x), steps - 1); f = x - i
        a, b = path[i], path[i + 1]
        return tuple(round(a[k] + (b[k] - a[k]) * f) for k in range(3))
    mid = (TOTAL - 1) / 2
    dist = [abs(x - mid) / max(mid, 1) for x in range(TOTAL)]
    top = [(4 + min(1.0, 1.3 - 0.55 * d) * 3) / steps for d in dist]   # how far each bulb gets: ends stop at yellow
    period = 2 * ramp + hold + night
    def show(t):
        t = (int(t / step) * step) % period
        if t < ramp: v = t / ramp                              # rising
        elif t < ramp + hold: v = 1.0                          # full day
        elif t < 2 * ramp + hold: v = 1 - (t - ramp - hold) / ramp   # setting
        else: v = 0.0                                          # night
        return [along(top[x] * max(0.0, min(1.0, v * (1 + lead) - lead * dist[x]))) for x in range(TOTAL)]
    show.period = period; show.step = step
    return show

def chase_flash(pat, step=0.6, flash=0.4, chase_secs=8.0, rounds=2):
    """Hockey: the team's stripes chase along for about chase_secs, then the whole string flashes each
    team colour in turn with a dark blink between (like a goal celebration), then back to the chase."""
    run = chase(pat, step)
    loops = max(1, round(chase_secs / (step * len(pat))))
    c_len = loops * step * len(pat)                            # whole loops, so the chase ends where it began
    cols = list(dict.fromkeys(c for c in pat if c != (0, 0, 0)))
    flashes = [f for c in cols for f in ([c] * TOTAL, [(0, 0, 0)] * TOTAL)] * rounds
    period = c_len + flash * len(flashes)
    def show(t):
        t = t % period
        if t < c_len: return run(t)
        return flashes[min(int((t - c_len) / flash + 1e-6), len(flashes) - 1)]
    show.period = period; show.step = min(step, flash)
    return show

def sunset_rise(step=1.0, band=3):
    """Sunset stripes moving out from the centre toward both ends, a whole bulb at a time, round and round
    (red, orange, amber, pink, purple, red...). No blended shades: every bulb is one of the five colours."""
    mid = (TOTAL - 1) / 2
    n = len(SUNSET_BANDS) * band
    def show(t):
        shift = int(t / step)
        return [SUNSET_BANDS[(int(abs(x - mid)) - shift) % n // band] for x in range(TOTAL)]
    show.period = n * step; show.step = step
    return show

EASTER = [(255, 110, 170), (255, 210, 60), (110, 255, 150), (120, 170, 255), (190, 110, 255)]   # pastel pink, yellow, mint, blue, lilac
EASTER_STRIPES = [c for c in EASTER for _ in range(3)]   # three bulbs of each pastel

def flow(stops, width=20, period=40.0, step=0.5):
    """Colours blended into one another, drifting slowly along the string (painted between bulbs,
    so each step is a fraction of a bulb). `stops` loop, `width` bulbs per full round of colours."""
    n = len(stops)
    def at(x):
        f = (x % width) / width * n; j = int(f) % n
        return blend(stops[j], stops[(j + 1) % n], f - int(f))
    def show(t):
        t = int(t / step) * step
        shift = width * t / period
        return [at(x - shift) for x in range(TOTAL)]
    show.period = period; show.step = step
    return show

def fireworks(step=0.4, loop=150, launch=0.3, life=7):
    """Fireworks on a night-blue string: bursts go off at random spots, flash white, then spread
    outward both ways in red, white or blue, fading as they go."""
    night = (0, 0, 25)
    def show(t):
        k = int(t / step) % loop
        bulbs = [night] * TOTAL
        for j in range(k - life + 1, k + 1):           # every burst still alive, oldest first
            r = random.Random((j % loop) * 7907 + 13)
            if r.random() >= launch: continue
            centre, colour, age = r.randrange(TOTAL), r.choice((RED, WHITE, BLUE, RED, BLUE)), k - j
            if age == 0: bulbs[centre] = WHITE; continue
            fade = 1 - age / life
            for d in range(1, age + 1):                    # the ring, with a dimmer trail behind it
                f = fade * (1 if d == age else 0.35)
                for p in (centre - d, centre + d):
                    if 0 <= p < TOTAL: bulbs[p] = blend(night, colour, f)
        return bulbs
    show.period = loop * step; show.step = step; show.tick = step
    return show

# Stripe patterns for still themes (three bulbs a stripe, so their Animate chase reads as movement)
REDGREEN = [RED] * 3 + [GREEN] * 3
# Canadian NHL teams' colours, three bulbs a stripe. Black is an unlit bulb; navy and green are tuned for these LEDs.
OFF, YELLOW, ORANGE_C9 = (0, 0, 0), (255, 180, 0), (255, 100, 0)
HOCKEY = {   # proportions follow each team's jersey, so teams that share colours still look different
    'flames':    [RED] * 4 + [YELLOW] * 2 + [OFF],                                    # Calgary: red, gold flame, black edge
    'oilers':    [BLUE] * 3 + [ORANGE_C9] * 3,                                        # Edmonton: blue, orange
    'canadiens': [RED] * 4 + [WHITE] + [BLUE] * 2 + [WHITE],                          # Montréal: red, blue band in white
    'senators':  [OFF] * 3 + [RED] * 2 + [YELLOW],                                    # Ottawa: black, red, gold trim
    'leafs':     [BLUE] * 4 + [WHITE],                                                # Toronto: blue, one white stripe
    'canucks':   [BLUE] * 3 + [WHITE] + [(0, 200, 60)] * 2 + [WHITE],                 # Vancouver: blue, green, white
    'jets':      [(0, 0, 150)] * 4 + [(0, 120, 255)] * 2 + [RED],                     # Winnipeg: navy, sky blue, red
}
BLUEWHITE = [BLUE] * 3 + [WHITE] * 3
SILVERGOLD = [WHITE] * 3 + [GOLD] * 3
HOLLY = [(0, 190, 20)] * 3 + [RED]                       # holly: three green leaves, one red berry
CANADA = [RED] * 3 + [WHITE] * 3
VALENTINES = [RED] * 3 + [PINK] * 3 + [WHITE] * 3
STPATS = [GREEN] * 3 + [GHOUL] * 3 + [GOLD] * 3
FOURTH = [RED] * 3 + [WHITE] * 3 + [BLUE] * 3

DOUBLE_RAINBOW = [hue(2 * i / TOTAL) for i in range(TOTAL)]   # the colour wheel twice, end to end

TRANSITION_SECS = {'cut': 0, 'fade': 4.0, 'chase': None}   # chase: one bulb per TSTEP across the string
TSTEP = 0.4
def build_playlist(items, state=None):
    """A show that plays each item's theme for its time, moving to the next with its transition:
    items = [{'show': key, 'hold': seconds, 'transition': 'chase' | 'fade' | 'cut'}, ...]. Moving
    themes keep moving through their hold and their transitions."""
    fns = [show_fn(it['show'], state) or SHOWS['classic'] for it in items]
    tdur = [TOTAL * TSTEP if it['transition'] == 'chase' else TRANSITION_SECS[it['transition']] for it in items]
    phases = []                       # (duration, fn(c) -> bulbs); item i's own clock starts as it begins to come in
    for i, it in enumerate(items):
        j = (i + 1) % len(items)
        into = tdur[i - 1]            # how long item i has already been showing when its hold starts
        phases.append((it['hold'], lambda c, i=i, into=into: fns[i](c + into)))
        if tdur[i]:
            def trans(c, i=i, j=j, into=into, kind=it['transition']):
                old, new = fns[i](c + into + items[i]['hold']), fns[j](c)
                if kind == 'chase':
                    k = int(c / TSTEP) + 1                    # the new theme pushes in from bulb 0
                    return new[:k] + old[k:]
                f = (int(c / TSTEP) + 1) * TSTEP / tdur[i]    # fade in TSTEP steps
                return [blend(a, b, min(f, 1)) for a, b in zip(old, new)]
            phases.append((tdur[i], trans))
    cycle = sum(d for d, _ in phases)
    def show(t):
        c = t % cycle
        for d, fn in phases:
            if c < d: return fn(c)
            c -= d
        return phases[-1][1](0)
    steps = [getattr(f, 'step', None) for f in fns] + [TSTEP]
    show.period = cycle; show.step = min(x for x in steps if x)
    show.tick = 0.05 if cycle < 600 else 0.2           # preview sampling for long playlists
    show.items = items
    return show

# ---- custom shows (made on the web page) ------------------------------------------------------
EFFECT_MODES = range(32)        # DP 104 effect numbers to offer; only 0 and 18 have been seen from the app
def rgb(h): h = h.lstrip('#'); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
def effect_payload(mode, speed, colours):
    """DP 104 (effect_control): 00 00 00 80 <effect> <speed 1-100> 00x7 <count> then R G B 00 00 per colour."""
    return (bytes([0, 0, 0, 0x80, mode, speed] + [0] * 7 + [len(colours)])
            + b''.join(bytes(c) + b'\0\0' for c in colours))

def custom_show(spec, state=None):
    """spec: {colours: ['#rrggbb', ...], width: bulbs per colour, effect: still|chase|converge|builtin,
    mode: built-in effect number, speed: built-in effect speed 1-100}."""
    if spec.get('effect') == 'playlist': return build_playlist(spec['items'], state)
    cols = [rgb(c) for c in spec.get('colours') or ['#ffffff']]
    pat = [c for c in cols for _ in range(spec.get('width', 1))]
    eff = spec.get('effect', 'still')
    if eff == 'chase': return chase(pat, 0.6)
    if eff == 'converge': return converge(pat, 0.6)
    def show(t): return tile(pat, TOTAL)
    if eff == 'builtin':
        show.builtin = effect_payload(spec.get('mode', 0), spec.get('speed', 50), cols)
    return show

def show_fn(key, state=None):
    """The show function for a key: a built-in show, or a custom one ('custom:<id>') from state."""
    if key in SHOWS: return SHOWS[key]
    if key and key.startswith('custom:'):
        spec = (state or load_state()).get('customs', {}).get(key[7:])
        if spec: return custom_show(spec, state)
    return None

SHOWS = {
    'candycane': chase(CANDY, 0.5),                       # the candy cane stripes, green included, chasing
    'halloween': chase([ORANGE] * 3 + [PURPLE] * 3 + [GHOUL] * 3, 0.5),   # orange, purple, dark green
    'chase5':    chase(C9, 1.5),                      # classic C9 colours, slow chase
    'rainbow':   lambda t: RAINBOW,          # static
    'classicwhite': chase_with_white(C9, 1.5),   # slow classic chase, with an all-white wipe every ~1.5 min
    'classic':   lambda t: [C9[p % len(C9)] for p in range(TOTAL)],  # static red/green/orange/blue/warm white
    'xmas':      converge([RED, RED, (0, 255, 0), (0, 255, 0), WHITE, WHITE], 0.6),  # stripes meet at the join
    'redscan':   scanner(RED, WHITE, 0.6, mirror=(0, 255, 0), tail=(0.6, 0.3, 0.12)),   # red; white + green from opposite ends of both strings, cross at the join
    'whitescan': scanner(WHITE, RED, 0.6, mirror=(0, 255, 0), tail=(0.6, 0.3, 0.12)),   # white; red + green from opposite ends, cross at the join
    'icy':       chase(ICY, 0.6),   # deep blue swelling to white and back, drifting along both strings
    'quad':      lambda t: TEST_PATTERN,     # TV colour bars (key kept from the old Four patterns)
    'jostle':    jostle(),                # confetti colours swapping places and drifting
    # test patterns
    'strings':   lambda t: [STRING_COLOURS[i % len(STRING_COLOURS)] for i, n in enumerate(SIZES) for _ in range(n)],
    'allwhite':  lambda t: [WHITE] * TOTAL,
    'walk':      walk(RED, 0.6),
    'seams':     seams(),
    'confetti':  lambda t: CONFETTI,         # static: the 48 rainbow colours in random spots
    # moving themes
    'embers':    embers(),
    'snowfall':  snowfall(),
    'marquee':   chase([WHITE, OFF, OFF], 0.5),           # every third bulb lit, stepping like a theatre sign
    'newyear':   new_year(),
    'hanukkah':  hanukkah(),
    'seasonal':  Seasonal(),
    'fibonacci': fibonacci(),
    'auroramove': aurora_waves(),
    'treetwinkle': twinkle_tree(),
    'sunsetmove': sunset_rise(),
    'sunrise':   sunrise(),
    'eastermove': chase(EASTER_STRIPES, 0.6),               # the pastel stripes chasing along
    'fourthmove': fireworks(),
    'fourth':    lambda t: tile(FOURTH, TOTAL),                             # pastels blending and drifting along
    'stpatsmove': chase(STPATS, 0.6),
    'rainbowmove': chase(RAINBOW, 0.5),                  # the colour wheel rolling along
    'doublemove': chase(DOUBLE_RAINBOW, 0.5),
    'double':    lambda t: DOUBLE_RAINBOW,
    'chaos':     chaos(),
    # still themes
    'candystill': lambda t: tile(CANDY, TOTAL),
    'halloweenstill': lambda t: tile([ORANGE] * 3 + [PURPLE] * 3 + [GHOUL] * 3, TOTAL),
    'goldenangle': lambda t: GOLDEN_ANGLE,
    'redgreen':  lambda t: tile(REDGREEN, TOTAL),
    'bluewhite': lambda t: tile(BLUEWHITE, TOTAL),
    'silvergold': lambda t: tile(SILVERGOLD, TOTAL),
    'holly':     lambda t: tile(HOLLY, TOTAL),
    'tree':      lambda t: tile(TREE, TOTAL),
    'peppermint': lambda t: tile([RED, WHITE], TOTAL),
    'aurora':    lambda t: AURORA,
    'sunset':    lambda t: SUNSET,
    'canada':    lambda t: tile(CANADA, TOTAL),
    **{k: (lambda p: lambda t: tile(p, TOTAL))(p) for k, p in HOCKEY.items()},
    'stpats':    lambda t: tile(STPATS, TOTAL),
    'valentines': lambda t: tile(VALENTINES, TOTAL),
    # Animate versions of still themes: the same stripes chasing along
    'redgreenmove':   chase(REDGREEN, 0.6),
    'bluewhitemove':  chase(BLUEWHITE, 0.6),
    'silvergoldmove': chase(SILVERGOLD, 0.6),
    'hollymove':      chase(HOLLY, 0.6),
    'peppermintmove': chase([RED, RED, WHITE, WHITE], 0.6),    # single-bulb alternation only blinks when chased
    'canadamove':     chase(CANADA, 0.6),
    **{k + 'move': chase_flash(p) for k, p in HOCKEY.items()},
    'valentinesmove': chase(VALENTINES, 0.6),
    'fourthchase':    chase(FOURTH, 0.6),
    'goldenanglemove': chase(GOLDEN_ANGLE, 0.6),
    'easter':    lambda t: tile(EASTER_STRIPES, TOTAL),
}
# Built-in playlists (same engine as the ones made on the web page)
CLASSIC_LOOP = [{'show': 'classic', 'hold': 120, 'transition': 'chase'},
                {'show': 'allwhite', 'hold': 120, 'transition': 'chase'},
                {'show': 'candystill', 'hold': 120, 'transition': 'chase'}]
def _pl(*steps): return [{'show': a, 'hold': b, 'transition': c} for a, b, c in steps]
PLAYLISTS = {
    'classicloop': CLASSIC_LOOP,
    'medley':   _pl(('chase5', 300, 'fade'), ('candycane', 300, 'chase'), ('tree', 300, 'fade'),
                    ('snowfall', 300, 'chase'), ('redscan', 300, 'chase')),
    'winter':   _pl(('icy', 300, 'fade'), ('snowfall', 300, 'fade'), ('auroramove', 300, 'fade'), ('bluewhite', 120, 'fade')),
    'fireside': _pl(('embers', 600, 'fade'), ('classic', 300, 'fade')),
    'spooky':   _pl(('halloween', 300, 'fade'), ('embers', 120, 'cut'), ('chaos', 30, 'cut'),
                    ('halloweenstill', 120, 'chase')),
    'rainbows': _pl(('rainbowmove', 120, 'fade'), ('doublemove', 120, 'chase'), ('jostle', 120, 'fade'),
                    ('goldenangle', 60, 'chase'), ('fibonacci', 60, 'fade')),
    'party':    _pl(('chaos', 30, 'cut'), ('rainbowmove', 30, 'cut'), ('marquee', 30, 'cut'),
                    ('jostle', 30, 'cut'), ('doublemove', 30, 'cut')),
}
for _k, _items in PLAYLISTS.items(): SHOWS[_k] = build_playlist(_items, {})
AURORA = tile(AURORA_BANDS, TOTAL)
SUNSET = sunset_rise()(0)                      # the still sunset is the moving one's first moment
DEFAULT_SHOW = 'confetti'
CONFETTI = random.sample(RAINBOW, TOTAL)    # reshuffled whenever the show (re)starts

def load_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {'show': DEFAULT_SHOW}

def save_state(s):
    tmp = STATE.with_suffix('.tmp'); tmp.write_text(json.dumps(s)); os.replace(tmp, STATE)

def override(state):
    o = state.get('override')
    if o and time.time() < o.get('until', 0): return o['power']
    return None

# ---- schedule -----------------------------------------------------------------------------------
# A zone's schedule: on_at is 'HH:MM', 'sunset' or 'sunrise' (plus on_offset minutes, negative = before);
# off_at is 'HH:MM', 'sunrise' or 'sunset' (plus off_offset), or 'after' with off_after minutes from the on
# time. Sun times need state['location'] = {lat, lon}, shared by every zone; without it they fall back to
# the default times. Everything is in this computer's local time.
SUN_EVENTS = ('sunset', 'sunrise')

def sun_times(day, lat, lon):
    """(sunrise, sunset) for a date at a place, as naive local datetimes, or None for either when the sun
    doesn't rise or set that day. The NOAA / Almanac for Computers formula, good to about a minute."""
    n = day.timetuple().tm_yday
    rad, deg = math.radians, math.degrees
    def event(rising):
        lng = lon / 15
        t = n + ((6 if rising else 18) - lng) / 24
        m = 0.9856 * t - 3.289
        L_ = (m + 1.916 * math.sin(rad(m)) + 0.020 * math.sin(rad(2 * m)) + 282.634) % 360
        ra = deg(math.atan(0.91764 * math.tan(rad(L_)))) % 360
        ra = (ra + (L_ // 90) * 90 - (ra // 90) * 90) / 15
        sin_dec = 0.39782 * math.sin(rad(L_)); cos_dec = math.cos(math.asin(sin_dec))
        cos_h = (math.cos(rad(90.833)) - sin_dec * math.sin(rad(lat))) / (cos_dec * math.cos(rad(lat)))
        if not -1 <= cos_h <= 1: return None
        h = (360 - deg(math.acos(cos_h)) if rising else deg(math.acos(cos_h))) / 15
        ut = (h + ra - 0.06571 * t - 6.622 - lng) % 24
        utc = datetime.datetime.combine(day, datetime.time(), datetime.timezone.utc) + datetime.timedelta(hours=ut)
        local = utc.astimezone().replace(tzinfo=None)
        local += datetime.timedelta(days=(day - local.date()).days)       # keep it on the asked-for date
        return (local + datetime.timedelta(seconds=30)).replace(second=0, microsecond=0)
    return event(True), event(False)

def location_of(state):
    loc = (state or {}).get('location') or {}
    try:
        lat, lon = float(loc['lat']), float(loc['lon'])
        return (lat, lon) if -90 <= lat <= 90 and -180 <= lon <= 180 else None
    except (KeyError, TypeError, ValueError):
        return None

def _at(spec, offset, day, state, default):
    """When 'HH:MM' / 'sunset' / 'sunrise' (+ offset minutes) falls on a date, as a naive datetime."""
    if spec in SUN_EVENTS:
        loc = location_of(state)
        if loc:
            rise, set_ = sun_times(day, *loc)
            t = set_ if spec == 'sunset' else rise
            if t: return t + datetime.timedelta(minutes=int(offset or 0))
        spec = default                                  # no location, or no sunset today: use the default
    try: hm = datetime.datetime.strptime(spec, '%H:%M').time()
    except (TypeError, ValueError): hm = datetime.datetime.strptime(default, '%H:%M').time()
    return datetime.datetime.combine(day, hm)

def day_window(state, day):
    """(start, end) of the on-period that starts on this date."""
    st = state or {}
    start = _at(st.get('on_at') or DEFAULT_ON, st.get('on_offset'), day, st, DEFAULT_ON)
    if st.get('off_at') == 'after':
        return start, start + datetime.timedelta(minutes=int(st.get('off_after') or 360))
    end = _at(st.get('off_at') or DEFAULT_OFF, st.get('off_offset'), day, st, DEFAULT_OFF)
    while end <= start: end += datetime.timedelta(days=1)        # off at 00:00 or sunrise: the next day
    return start, end

def current_window(state, now=None):
    now = now or datetime.datetime.now()
    for d in (now.date() - datetime.timedelta(days=1), now.date()):
        a, b = day_window(state, d)
        if a <= now < b: return a, b
    return None

def next_window(state, now=None):
    now = now or datetime.datetime.now()
    for k in range(0, 3):
        a, b = day_window(state, now.date() + datetime.timedelta(days=k))
        if a > now: return a, b
    return day_window(state, now.date() + datetime.timedelta(days=1))

def schedule(state):
    """(on, off) datetimes: the on-period happening now, else the next one."""
    return current_window(state) or next_window(state)

def is_on_hours(state=None, now=None):
    st = state if state is not None else load_state()
    a, b = day_window(st, (now or datetime.datetime.now()).date())
    if a == b: return False
    return current_window(st, now) is not None

def schedule_text(state):
    """The rule in words, e.g. '5 min before sunset, for 6 hours'."""
    st = state or {}
    def when(spec, off):
        if spec in SUN_EVENTS:
            off = int(off or 0)
            if not off: return f'at {spec}'
            m = abs(off); amt = f'{m // 60} h {m % 60} min' if m >= 60 and m % 60 else f'{m // 60} h' if m >= 60 else f'{m} min'
            return f"{amt} {'before' if off < 0 else 'after'} {spec}"
        return f'at {spec}'
    on = when(st.get('on_at') or DEFAULT_ON, st.get('on_offset'))
    if st.get('off_at') == 'after':
        h = int(st.get('off_after') or 360) / 60
        return f"On {on}, for {h:g} hour{'s' if h != 1 else ''}"
    return f"On {on}, off {when(st.get('off_at') or DEFAULT_OFF, st.get('off_offset'))}"

def parse_rule(on, off):
    """CLI: 'sunset-5' / 'sunrise+10' / '16:00', and '6h' / 'sunrise' / '00:00'. -> zone fields or raises ValueError."""
    import re as _re
    def one(v, which):
        m = _re.fullmatch(r'(sunset|sunrise)([+-]\d+)?', v)
        if m: return {f'{which}_at': m.group(1), f'{which}_offset': int(m.group(2) or 0)}
        datetime.datetime.strptime(v, '%H:%M'); return {f'{which}_at': v, f'{which}_offset': 0}
    out = one(on, 'on')
    m = _re.fullmatch(r'(\d+(?:\.\d+)?)h', off)
    if m: out.update(off_at='after', off_after=round(float(m.group(1)) * 60), off_offset=0)
    else: out.update(one(off, 'off'))
    return out

# ---- zones ------------------------------------------------------------------------------------
# state.json holds  zones: [{id, name, strings: [device names], show, speeds, brightness, override, on_at, off_at,
# on_offset, off_offset, off_after}] plus customs, effect_names and location shared by every zone. Older single-zone state is read as one zone.
ZONE_KEYS = ('show', 'speeds', 'brightness', 'override', 'on_at', 'off_at', 'on_offset', 'off_offset', 'off_after')
def zones_of(st):
    if st.get('zones'): return st['zones']
    z = {k: st[k] for k in ZONE_KEYS if k in st}
    z.update(id='1', name=st.get('lights_name') or 'My lights', strings=list(ORDER))
    return [z]
def materialise_zones(st):
    """Make st['zones'] real (migrating old state) and return it, so it can be edited and saved."""
    st['zones'] = zones_of(st)
    for k in ZONE_KEYS + ('lights_name',): st.pop(k, None)
    return st['zones']
def zone_view(st, zone):
    """A zone's settings plus the shared custom shows: what show_fn, speed_of, schedule etc. expect."""
    return {**zone, 'customs': st.get('customs', {}), 'effect_names': st.get('effect_names', {}),
            'location': st.get('location')}
def zone_strings(zone):
    """(name, bulbs) for the zone's strings, in physical order."""
    return [(n, b) for n, b in STRINGS if n in zone.get('strings', [])]
_zone_modules = {}
def zone_module(zone):
    """This module rebuilt for just the zone's strings, so shows span exactly that zone."""
    zs = zone_strings(zone)
    if not zs or zs == list(STRINGS) == list(ZONE_STRINGS): return sys.modules[__name__]
    key = tuple(zs)
    if key not in _zone_modules:
        spec = importlib.util.spec_from_file_location(f'lights_zone_{len(_zone_modules)}', __file__)
        m = importlib.util.module_from_spec(spec)
        m.__dict__['_ZONE_STRINGS'] = list(zs)
        spec.loader.exec_module(m)
        _zone_modules[key] = m
    return _zone_modules[key]

MIN_STEP = 0.4      # seconds; faster than this per change and the strings start skipping frames
SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3]
def max_speed(key, state=None):
    """Fastest speed a show can run without asking the strings for changes quicker than MIN_STEP."""
    fn = show_fn(key, state)
    step = getattr(fn, 'step', None)
    if not getattr(fn, 'period', 0) or step is None: return 1
    return max([s for s in SPEEDS if step / s >= MIN_STEP - 1e-9] + [1])   # never below how it runs today
# Overall brightness, per zone: every bulb's colour is scaled by it before sending (the controllers'
# own brightness DP has never been seen to do anything). Below about 10% colours start to break up.
BRIGHTNESS = [0.1, 0.2, 0.3, 0.45, 0.6, 0.8, 1.0]
def brightness_of(state):
    v = state.get('brightness', 1.0)
    return v if v in BRIGHTNESS else 1.0
def dim(bulbs, b):
    return bulbs if b >= 1 else [(round(r * b), round(g * b), round(bl * b)) for r, g, bl in bulbs]
def dim_effect(payload, b):
    """Scale the colours inside a built-in effect payload (14-byte header, then R G B 00 00 per colour)."""
    if b >= 1: return payload
    p = bytearray(payload)
    for i in range(14, len(p) - 2, 5):
        for k in range(3): p[i + k] = round(p[i + k] * b)
    return bytes(p)

def speed_of(state, key=None):
    key = key or state.get('show')
    v = state.get('speeds', {}).get(key, 1)
    return v if v in SPEEDS and v <= max_speed(key, state) else 1

def log(*a): print(time.strftime('%Y-%m-%d %H:%M:%S'), *a, flush=True)

class Shared:
    """What every string worker needs to know; written by the main thread."""
    def __init__(self):
        self.show = SHOWS[DEFAULT_SHOW]; self.t0 = time.time(); self.speed = 1.0; self.bright = 1.0; self.power = None; self.epoch = 0
    def t(self, now): return (now - self.t0) * self.speed   # how far into the show we are, in show time

class String(threading.Thread):
    """One worker per string, so a string with flaky Wi-Fi can never stall the other."""
    def __init__(self, dev, index, shared):
        super().__init__(daemon=True, name=dev['name'])
        import tinytuya
        self.tinytuya = tinytuya; self.dev = dev; self.i = index; self.shared = shared
        self.offset, self.size = 0, SIZES[index]      # this string's place within its zone's run
        self.seen_shared = None
        self.c = None; self.busy_since = None; self.shown = None; self.last_send = 0; self.epoch = -1
        self.sent = 0; self.acked = 0; self.fails = 0
        self.recent_sent = collections.deque(); self.recent_acked = collections.deque()   # times, last 60 s
        self.last_ack = None; self.switch = None; self.down_since = None
    def heard(self, r, now):
        """Note a reply from the controller; DP 20 in it is the string's real on/off state."""
        self.last_ack = now; self.down_since = None
        if str(DP_SWITCH) in r.get('dps', {}): self.switch = r['dps'][str(DP_SWITCH)]
    def health(self, now):
        for q in (self.recent_sent, self.recent_acked):
            while q and q[0] < now - 60: q.popleft()
        return {'name': self.name, 'online': self.c is not None, 'switch': self.switch,
                'last_ack': self.last_ack, 'down_since': self.down_since,
                'sent': len(self.recent_sent), 'acked': len(self.recent_acked)}
    def connect(self):
        d = self.dev
        c = self.tinytuya.Device(d['id'], d['ip'], d['key'], version=float(d['version']), persist=True,
                                 connection_timeout=3, connection_retry_limit=1, connection_retry_delay=0)
        c.set_socketRetryLimit(1); c.set_socketTimeout(3)
        r = c.status()                       # blocking handshake (v3.5 negotiates a session key)
        if not r or 'Error' in r: raise ConnectionError(r)
        self.heard(r, time.time())
        c.set_socketTimeout(0.01)            # then near-non-blocking for streaming
        self.c = c; self.busy_since = None; self.shown = None
        if self.fails: log(self.name, 'reconnected after', self.fails, 'failures'); self.fails = 0
    def drop(self, why):
        self.fails += 1
        if self.fails in (1, 10) or self.fails % 100 == 0: log(self.name, 'connection lost:', why)
        try: self.c and self.c.close()
        except Exception: pass
        self.c = None; self.switch = None
        if self.down_since is None: self.down_since = time.time()
    def send(self, dp, value, now):
        self.c.set_value(dp, value, nowait=True)
        self.busy_since = now; self.last_send = now; self.sent += 1; self.recent_sent.append(now)
    def run(self):
        while True:
            try:
                if self.c is None:
                    self.connect()
                r = self.c.receive()
                if r and isinstance(r, dict) and 'dps' in r:
                    self.busy_since = None; self.acked += 1; self.recent_acked.append(time.time()); self.heard(r, time.time())
                now = time.time(); sh = self.shared
                if self.epoch != sh.epoch or self.seen_shared is not sh:
                    self.epoch = sh.epoch; self.seen_shared = sh; self.shown = None
                if self.busy_since is not None and now - self.busy_since < 3:
                    continue                 # receive() above already waited ~10 ms
                builtin = getattr(sh.show, 'builtin', None)
                if sh.power and builtin is not None:
                    # Built-in effect: the controller animates by itself. Send it once (both strings get
                    # it in the same moment, so they start together); resend only if it wasn't acked.
                    if self.shown == builtin and self.last_ack is not None and self.last_ack < self.last_send \
                            and now - self.last_send > 3:
                        self.shown = None
                    if self.shown != builtin:
                        if self.shown is None or self.shown == 'off': self.send(DP_SWITCH, True, now)
                        self.send(DP_EFFECT, base64.b64encode(dim_effect(builtin, sh.bright)).decode(), now); self.shown = builtin
                elif sh.power:
                    part = dim(sh.show(sh.t(now))[self.offset:self.offset + self.size], sh.bright)
                    # resend unchanged frames every 30 s so a string that missed one recovers
                    if part != self.shown or now - self.last_send > 30:
                        if self.shown is None: self.send(DP_SWITCH, True, now)
                        self.send(DP_PAINT, frame(part), now); self.shown = part
                elif sh.power is False:
                    if self.shown != 'off' or now - self.last_send > 60:
                        self.send(DP_SWITCH, False, now); self.shown = 'off'
            except Exception as e:
                self.drop(e); time.sleep(2)

def frame(bulbs):
    return base64.b64encode(bytes([0, 0, 0, 1, 1]) + b''.join(bytes(c) + b'\0\0' for c in bulbs)).decode()

def run():
    if not DEVICES.exists():
        sys.exit(f'No {DEVICES}. Run the tinytuya wizard (see the README) and put devices.json there.')
    devs = {d['name']: d for d in json.loads(DEVICES.read_text())}
    missing = [n for n in ORDER if n not in devs]
    if missing:
        sys.exit(f"These strings aren't in devices.json: {', '.join(missing)}. Run configure.py to pick your strings.")
    idle = Shared(); idle.power = False                  # strings that aren't in any zone stay off
    strings = [String(devs[name], i, idle) for i, name in enumerate(ORDER)]
    zones = {}                                           # zone id -> Shared (with .cur = what it's playing)
    state_mtime = None
    log('started')
    for s in strings: s.start()
    next_stats = time.time() + 60; next_health = 0
    state = load_state()
    while True:
        now = time.time()
        try:                                             # pick up changes from the page or the CLI
            m = STATE.stat().st_mtime
            if m != state_mtime:
                state_mtime = m; state = load_state()
                seen = set()
                for z in zones_of(state):
                    if not zone_strings(z): continue
                    seen.add(z['id'])
                    zm = zone_module(z); view = zone_view(state, z)
                    sh = zones.get(z['id'])
                    if sh is None: sh = zones[z['id']] = Shared(); sh.cur = None
                    sh.view, sh.name = view, z.get('name', z['id'])
                    speed = zm.speed_of(view)
                    key = view.get('show'); fn = zm.show_fn(key, view) or zm.SHOWS[DEFAULT_SHOW]
                    custom = json.dumps(view['customs'].get((key or '')[7:])) if (key or '').startswith('custom:') else ''
                    sig = (key, custom, tuple(z['strings']))
                    if sig != sh.cur:                    # new show (or edited custom show): start from the top
                        zm.CONFETTI = random.sample(zm.RAINBOW, zm.TOTAL)
                        sh.cur = sig; sh.show = fn; sh.t0, sh.speed = now, speed; sh.epoch += 1
                        log(f'{sh.name}: show =', key, f'at {speed}x')
                    elif speed != sh.speed:              # same show, new speed: carry on from where it is
                        sh.t0 = now - sh.t(now) / speed; sh.speed = speed; sh.epoch += 1
                        log(f'{sh.name}: speed =', f'{speed}x')
                    bright = brightness_of(view)
                    if bright != sh.bright:              # resend at the new brightness (built-in effects restart)
                        sh.bright = bright; sh.epoch += 1
                        log(f'{sh.name}: brightness =', f'{round(bright * 100)}%')
                for zid in list(zones):
                    if zid not in seen: del zones[zid]
                for s in strings:                        # give each string its zone and its slice of it
                    z = next((z for z in zones_of(state) if z['id'] in zones and s.name in z['strings']), None)
                    if z is None: s.shared = idle; continue
                    names = [n for n, _ in zone_strings(z)]
                    s.offset = sum(b for n, b in zone_strings(z)[:names.index(s.name)])
                    s.shared = zones[z['id']]
                tmp = ENGINE.with_suffix('.tmp')
                tmp.write_text(json.dumps({'zones': {zid: {'t0': sh.t0, 'speed': sh.speed, 'show': sh.cur[0]}
                                                     for zid, sh in zones.items()}}))
                tmp.replace(ENGINE)
        except FileNotFoundError:
            pass
        for zid, sh in zones.items():
            ov = override(sh.view)
            want_on = is_on_hours(sh.view) if ov is None else ov
            if want_on != sh.power:
                log(f'{sh.name}: power', 'ON' if want_on else 'OFF'); sh.power = want_on; sh.epoch += 1
        if now >= next_health:
            next_health = now + 5
            h = {'at': now, 'strings': [{**s.health(now), 'want_on': bool(s.shared.power)} for s in strings]}
            tmp = HEALTH.with_suffix('.htmp'); tmp.write_text(json.dumps(h)); tmp.replace(HEALTH)
        if now >= next_stats:
            next_stats = now + 60
            log('last minute:', ', '.join(f"{s.name} sent {s.sent} acked {s.acked}" + (f" (offline, {s.fails} fails)" if s.c is None else "") for s in strings))
            for s in strings: s.sent = s.acked = 0
        time.sleep(0.5)

def main():
    args = sys.argv[1:]
    zname = None
    if '--zone' in args:
        i = args.index('--zone'); zname = args[i + 1]; del args[i:i + 2]
    arg = args[0] if args else 'status'
    if arg == 'run': return run()
    st = load_state(); zones = materialise_zones(st) if arg != 'status' else zones_of(st)
    if arg == 'status':
        for z in zones:
            v = zone_view(st, z); ov = override(v); on, off = schedule(v)
            hold = f", held {'ON' if ov else 'OFF'} until {datetime.datetime.fromtimestamp(z['override']['until']):%H:%M}" if ov is not None else ''
            print(f"{z.get('name')}: {', '.join(z.get('strings', [])) or 'no strings'}   show: {z.get('show', DEFAULT_SHOW)}"
                  f"   schedule: {schedule_text(v)} ({on:%H:%M}-{off:%H:%M}){hold}")
        print('shows:', ', '.join(SHOWS)); return
    z = next((z for z in zones if z.get('name', '').lower() == (zname or '').lower()), zones[0])
    if arg in SHOWS:
        z['show'] = arg; save_state(st); print(f"{z['name']}: show set to", arg); return
    if arg in ('on', 'off'):
        hours = float(args[1]) if len(args) > 1 else 1
        z['override'] = {'power': arg == 'on', 'until': time.time() + hours * 3600}
        save_state(st); print(f"{z['name']}: forced {arg} for {hours:g} h, then back to the schedule"); return
    if arg == 'schedule' and len(args) == 3:            # lights schedule 16:00 00:00 | sunset-5 6h | sunset sunrise
        try: rule = parse_rule(args[1], args[2])
        except ValueError: sys.exit('Use times like 16:00, sunset or sunrise with an offset like sunset-5, or hours like 6h.')
        if (rule['on_at'] in SUN_EVENTS or rule['off_at'] in SUN_EVENTS) and not location_of(st):
            sys.exit('Set your location first: lights location <latitude> <longitude>')
        z.update(rule); save_state(st)
        a, b = schedule(zone_view(st, z))
        print(f"{z['name']}: {schedule_text(zone_view(st, z))} (next: {a:%a %H:%M} to {b:%H:%M})"); return
    if arg == 'location' and len(args) == 3:            # lights location 43.65 -79.38
        lat, lon = round(float(args[1]), 2), round(float(args[2]), 2)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180): sys.exit('Latitude is -90 to 90, longitude -180 to 180.')
        st['location'] = {'lat': lat, 'lon': lon}; save_state(st)
        r, s_ = sun_times(datetime.date.today(), lat, lon)
        print(f"Location set. Today: sunrise {r:%H:%M}, sunset {s_:%H:%M}" if r and s_ else 'Location set.'); return
    if arg == 'auto':
        z.pop('override', None); save_state(st); print(f"{z['name']}: following the schedule"); return
    sys.exit(f"unknown command {arg!r}. shows: {', '.join(SHOWS)}")

if __name__ == '__main__':
    main()
