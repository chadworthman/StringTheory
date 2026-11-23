"""Spike: twinkle across both strings. Each string is paced independently: it only gets the newest
frame once it has acked the previous one (latest-frame-wins), so a slow string never builds a backlog."""
import base64, json, random, sys, time, tinytuya
N = 24
ORDER = ['C9 Lights', 'C9 Lights 2']  # device names, first string's end meets second's start
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 300
FADE = float(sys.argv[4]) if len(sys.argv) > 4 else 0.75
SPARK_RANGE = tuple(json.loads(sys.argv[5])) if len(sys.argv) > 5 else (3, 5)
TICK = 0.3                    # how often the pattern itself evolves
BASE = tuple(json.loads(sys.argv[3])) if len(sys.argv) > 3 else (150, 100, 45)  # warm white glow (perceived)
SPARKS = [tuple(c) for c in json.loads(sys.argv[6])] if len(sys.argv) > 6 else [(255, 0, 0), (0, 255, 0), (255, 140, 0), (120, 180, 255), (255, 255, 255)]
devs = {d['name']: d for d in json.load(open(sys.argv[1]))}
strings = []
for did in ORDER:
    d = devs[did]; c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True)
    c.set_socketTimeout(3); c.status(); c.set_socketTimeout(0.01)
    strings.append({'name': d['name'], 'c': c, 'busy_since': None, 'sent': 0})
TOTAL = N * len(strings)
level = [0.0] * TOTAL          # 0..1 sparkle brightness per bulb
color = [BASE] * TOTAL
GAMMA = 2.2
def mix(a, b, t):
    """Blend colours in *perceived* brightness, then convert to the LED's linear PWM value.
    LEDs are linear, eyes aren't: without this, the dim end of a fade jumps in big visible steps."""
    return tuple(round(255 * ((x + (y - x) * t) / 255) ** GAMMA) for x, y in zip(a, b))
def frame(bulbs): return base64.b64encode(bytes([0,0,0,1,1]) + b''.join(bytes(c) + b'\0\0' for c in bulbs)).decode()
end = time.time() + SECONDS; next_tick = time.time()
while time.time() < end:
    now = time.time()
    if now >= next_tick:                       # evolve the pattern
        next_tick += TICK
        for p in range(TOTAL):
            level[p] *= FADE
        for _ in range(random.randint(*SPARK_RANGE)):
            p = random.randrange(TOTAL); level[p] = 1.0; color[p] = random.choice(SPARKS)
        bulbs = [mix(BASE, color[p], level[p]) for p in range(TOTAL)]
        for i, s in enumerate(strings):        # send newest frame to any string that's ready
            if s['busy_since'] is None or now - s['busy_since'] > 3:
                s['c'].set_value(102, frame(bulbs[i*N:(i+1)*N]), nowait=True)
                s['busy_since'] = now; s['sent'] += 1
    for s in strings:                          # an echo means the string is ready for more
        r = s['c'].receive()
        if r and isinstance(r, dict) and '102' in r.get('dps', {}):
            s['busy_since'] = None
print({s['name']: s['sent'] for s in strings}, 'frames sent in', SECONDS, 's')
