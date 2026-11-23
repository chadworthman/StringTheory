"""Spike: one red bulb scans across both strings as one long string, there and back."""
import base64, json, sys, time, tinytuya
N = 24          # bulbs per string (5 bytes each: R G B + 2 white?)
FPS = 8
ORDER = ['C9 Lights', 'C9 Lights 2']  # device names, first string's end meets second's start
devs = {d['name']: d for d in json.load(open(sys.argv[1]))}
conns = []
for did in ORDER:
    d = devs[did]
    c = tinytuya.Device(d['id'], d['ip'], d['key'], version=float(d['version']), persist=True)
    c.set_socketTimeout(2); c.status(); conns.append(c)
def frame(colors):  # colors: list of N (r,g,b)
    raw = bytes([0, 0, 0, 1, 1]) + b''.join(bytes(c) + b'\x00\x00' for c in colors)
    return base64.b64encode(raw).decode()
OFF = (0, 0, 0)
blank = frame([OFF] * N)
total = N * len(conns)
path = list(range(total)) + list(range(total - 2, -1, -1))
prev = None
for pos in path:
    t0 = time.time()
    s = pos // N
    for i, c in enumerate(conns):
        if i == s:
            cols = [OFF] * N; cols[pos % N] = (255, 0, 0)
            c.set_value(102, frame(cols), nowait=True)
        elif prev is not None and prev // N == i:
            c.set_value(102, blank, nowait=True)   # clear the string the dot just left
    prev = pos
    time.sleep(max(0, 1 / FPS - (time.time() - t0)))
print('done', len(path), 'frames')
