"""Send frames to both strings nowait at a fixed interval; measure each string's send->echo lag over time."""
import base64, json, sys, time, tinytuya
N = 24; ORDER = ['C9 Lights', 'C9 Lights 2']  # device names, first string's end meets second's start
iv = float(sys.argv[2]); frames = int(sys.argv[3])
devs = {d['name']: d for d in json.load(open(sys.argv[1]))}
conns = []
for did in ORDER:
    d = devs[did]; c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True)
    c.set_socketTimeout(3); c.status(); c.set_socketTimeout(0.01); conns.append((d['name'], c))
def frame(k):  # encode frame number k as bulb k%24 lit, colour varies with k//24
    return base64.b64encode(bytes([0,0,0,1,1]) + b''.join((bytes([255, (k//N)*40 % 256, 0]) if j == k % N else b'\0\0\0') + b'\0\0' for j in range(N))).decode()
def decode(v):
    h = base64.b64decode(v)
    for j in range(N):
        if h[5+5*j] == 255: return (h[6+5*j] // 40) * N + j
sent = {}; lags = {n: [] for n, _ in conns}
t0 = time.time()
for k in range(frames):
    sent[k] = time.time()
    for n, c in conns: c.set_value(102, frame(k), nowait=True)
    while time.time() < t0 + (k + 1) * iv:
        for n, c in conns:
            r = c.receive()
            if r and isinstance(r, dict) and '102' in r.get('dps', {}):
                f = decode(r['dps']['102'])
                if f is not None and f in sent: lags[n].append((f, round((time.time() - sent[f]) * 1000)))
end = time.time() + 3
while time.time() < end:
    for n, c in conns:
        r = c.receive()
        if r and isinstance(r, dict) and '102' in r.get('dps', {}):
            f = decode(r['dps']['102'])
            if f is not None: lags[n].append((f, round((time.time() - sent[f]) * 1000)))
for n, l in lags.items():
    got = {f for f, _ in l}
    print(f"{n}: applied {len(got)}/{frames}; lag ms first10 {[x for _, x in l[:10]]} last10 {[x for _, x in l[-10:]]}")
