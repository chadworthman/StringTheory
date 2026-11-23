"""Measure how fast one string really applies frames.
Sends frames without waiting for acks at several intervals; each frame lights a different bulb,
so the device's echoes tell us exactly which frames it applied."""
import base64, json, sys, time, tinytuya
N = 24
devfile, did = sys.argv[1], sys.argv[2]
intervals = [float(x) for x in sys.argv[3:]] or [0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1]
d = {x['id']: x for x in json.load(open(devfile))}[did]
c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True); c.set_socketTimeout(0.02); c.status()
def frame(i):
    return base64.b64encode(bytes([0,0,0,1,1]) + b''.join((b'\xff\x00\x00' if j == i else b'\x00\x00\x00') + b'\x00\x00' for j in range(N))).decode()
def lit(v):
    h = base64.b64decode(v)
    return [j for j in range(N) if h[5+5*j:8+5*j] != b'\x00\x00\x00']
def drain(seen, until):
    while time.time() < until:
        r = c.receive()
        if r and isinstance(r, dict) and '102' in r.get('dps', {}):
            seen.append((time.time(), tuple(lit(r['dps']['102']))))
for iv in intervals:
    seen = []; sent = 0; t_start = time.time()
    for i in range(N):
        c.set_value(102, frame(i), nowait=True); sent += 1
        drain(seen, t_start + (i + 1) * iv)
    drain(seen, time.time() + 2.5)   # let stragglers arrive
    applied = sorted({s[1][0] for s in seen if len(s[1]) == 1})
    missing = [i for i in range(N) if i not in applied]
    print(f"interval {iv:.2f}s ({1/iv:4.1f}/s): sent {sent}, echoed {len(seen)}, applied {len(applied)}/{N}, missing {missing}", flush=True)
    time.sleep(1)
