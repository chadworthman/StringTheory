"""Log every DP update from both C9 strings, raw DPs decoded to hex."""
import base64, json, sys, threading, time, tinytuya
DEVS = [d for d in json.load(open(sys.argv[1])) if d.get('category') == 'hcdc']
def fmt(dps):
    out = {}
    for k, v in dps.items():
        if isinstance(v, str):
            try: v = base64.b64decode(v, validate=True).hex(' ')
            except Exception: pass
        out[k] = v
    return out
def watch(d):
    dev = tinytuya.Device(d['id'], d['ip'], d['key'], version=float(d['version']), persist=True)
    dev.set_socketTimeout(30)
    dev.status()
    last = time.time()
    while True:
        r = dev.receive()
        if r and 'dps' in r:
            print(time.strftime('%H:%M:%S'), d['name'], json.dumps(fmt(r['dps'])), flush=True)
        if time.time() - last > 10:
            dev.heartbeat(nowait=True); last = time.time()
for d in DEVS:
    threading.Thread(target=watch, args=(d,), daemon=True).start()
print('watching', [d['name'] for d in DEVS], flush=True)
while True: time.sleep(1)
