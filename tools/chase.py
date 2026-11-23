"""5-colour chase across both strings as one 48-bulb string.
Position is computed from the clock, and each string only gets the newest frame once it has acked
the last one, so a slow string skips steps but never falls behind."""
import base64, json, sys, time, tinytuya
N = 24
ORDER = ['C9 Lights', 'C9 Lights 2']  # device names, first string's end meets second's start
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 600
STEP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.4
COLORS = [tuple(c) for c in json.loads(sys.argv[4])] if len(sys.argv) > 4 else [(255, 0, 0), (0, 255, 0), (255, 100, 0), (0, 40, 255), (255, 150, 40)]
devs = {d['name']: d for d in json.load(open(sys.argv[1]))}
strings = []
for did in ORDER:
    d = devs[did]; c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True)
    c.set_socketTimeout(3); c.status(); c.set_socketTimeout(0.01)
    strings.append({'c': c, 'busy_since': None, 'shown': None})
TOTAL = N * len(strings)
def frame(bulbs): return base64.b64encode(bytes([0,0,0,1,1]) + b''.join(bytes(c) + b'\0\0' for c in bulbs)).decode()
t0 = time.time(); end = t0 + SECONDS
while time.time() < end:
    now = time.time()
    offset = int((now - t0) / STEP)
    for i, s in enumerate(strings):
        ready = s['busy_since'] is None or now - s['busy_since'] > 3
        if ready and s['shown'] != offset:
            bulbs = [COLORS[(p - offset) % len(COLORS)] for p in range(i * N, (i + 1) * N)]
            s['c'].set_value(102, frame(bulbs), nowait=True)
            s['busy_since'] = now; s['shown'] = offset
        r = s['c'].receive()
        if r and isinstance(r, dict) and '102' in r.get('dps', {}):
            s['busy_since'] = None
