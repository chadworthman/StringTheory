"""Spike: single red dot across ONE string at a given rate, waiting for each ack. Prints ack latency."""
import base64, json, sys, time, tinytuya
devfile, did, fps = sys.argv[1], sys.argv[2], float(sys.argv[3])
N = 24
d = {x['id']: x for x in json.load(open(devfile))}[did]
c = tinytuya.Device(d['id'], d['ip'], d['key'], version=3.5, persist=True); c.set_socketTimeout(2); c.status()
def frame(i):
    return base64.b64encode(bytes([0,0,0,1,1]) + b''.join((b'\xff\x00\x00' if j == i else b'\x00\x00\x00') + b'\x00\x00' for j in range(N))).decode()
lat = []
for i in range(N):
    t0 = time.time()
    r = c.set_value(102, frame(i))
    lat.append(round((time.time() - t0) * 1000))
    time.sleep(max(0, 1 / fps - (time.time() - t0)))
print('ack ms:', lat)
