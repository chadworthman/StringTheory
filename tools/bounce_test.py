"""Spike: marquee chase across both strings as one 48-bulb string. Each step is sent to both strings in parallel."""
import base64, json, sys, time, threading, tinytuya
N = 24
ORDER = ['C9 Lights', 'C9 Lights 2']  # device names, first string's end meets second's start
COLORS = [(255,0,0),(0,255,0),(0,0,255),(255,170,0),(255,255,255)]
BLOCK = 1
SWING = 10
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 45
STEP = 0.6
devs = {d['name']: d for d in json.load(open(sys.argv[1]))}
conns = []
for did in ORDER:
    d = devs[did]
    c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True); c.set_socketTimeout(3); c.status(); conns.append(c)
period = len(COLORS) * BLOCK
def color_at(pos, offset):
    return COLORS[((pos - offset) % period) // BLOCK]
def frame(bulbs):
    return base64.b64encode(bytes([0,0,0,1,1]) + b''.join(bytes(c) + b'\x00\x00' for c in bulbs)).decode()
end = time.time() + SECONDS; offset = 0; steps = 0
while time.time() < end:
    t0 = time.time()
    full = [color_at(p, offset) for p in range(N * len(conns))]
    th = [threading.Thread(target=c.set_value, args=(102, frame(full[i*N:(i+1)*N]))) for i, c in enumerate(conns)]
    [t.start() for t in th]; [t.join() for t in th]
    steps += 1; offset += 1 if (steps // SWING) % 2 == 0 else -1
    time.sleep(max(0, STEP - (time.time() - t0)))
print('steps', steps)
