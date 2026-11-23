"""Spike: 48-hue rainbow rotating along both strings as one long string."""
import base64, colorsys, json, sys, threading, time, tinytuya
N = 24
ORDER = ['C9 Lights', 'C9 Lights 2']  # device names, first string's end meets second's start
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 180
STEP = float(sys.argv[3]) if len(sys.argv) > 3 else 0.6
SHIFT = int(sys.argv[4]) if len(sys.argv) > 4 else 1   # bulbs moved per step
TOTAL = N * len(ORDER)
RAINBOW = [tuple(round(x * 255) for x in colorsys.hsv_to_rgb(i / TOTAL, 1, 1)) for i in range(TOTAL)]
devs = {d['name']: d for d in json.load(open(sys.argv[1]))}
conns = []
for did in ORDER:
    d = devs[did]
    c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True); c.set_socketTimeout(3); c.status(); c.set_socketTimeout(0.01); conns.append(c)
def frame(bulbs):
    return base64.b64encode(bytes([0, 0, 0, 1, 1]) + b''.join(bytes(c) + b'\x00\x00' for c in bulbs)).decode()
end = time.time() + SECONDS; offset = 0; steps = 0
while time.time() < end:
    t0 = time.time()
    full = [RAINBOW[(p - offset) % TOTAL] for p in range(TOTAL)]
    for i, c in enumerate(conns):
        c.set_value(102, frame(full[i * N:(i + 1) * N]), nowait=True)   # don't wait for the ~0.5 s ack
    while time.time() - t0 < STEP - 0.02:                                # drain acks so buffers don't fill
        for c in conns: c.receive()
    offset += SHIFT; steps += 1
    time.sleep(max(0, STEP - (time.time() - t0)))
print('steps', steps, 'full rotations', steps * SHIFT / TOTAL)
