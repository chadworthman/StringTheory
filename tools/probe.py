#!/usr/bin/env python3
"""Find out how your Tuya light controller works, so String Theory can drive it. See docs/adapting.md.

Run from the folder holding devices.json (and tinytuya.json for `dps`), with tinytuya installed:

  python tools/probe.py list                     # your devices: name, IP, protocol version, model
  python tools/probe.py dps "Porch lights"       # its data points (DPs): numbers, names, current values
  python tools/probe.py sniff "Porch lights"     # print every DP change while you use the Smart Life app
  python tools/probe.py paint "Porch lights" 24  # test String Theory's per-bulb format on it, bulb by bulb
  python tools/probe.py power "Porch lights" on  # switch it on or off (DP 20 unless you pass --dp)

Options: --dp N picks the data point to use for `paint` (default 102) or `power` (default 20).
It never prints your keys.
"""
import base64, json, sys, time
from pathlib import Path

try:
    import tinytuya
except ImportError:
    sys.exit('Install tinytuya first:  pip install tinytuya')

def devices():
    p = Path('devices.json')
    if not p.exists(): sys.exit('Run this in the folder that has devices.json (made by: python -m tinytuya wizard).')
    return json.loads(p.read_text())

def find(name):
    ds = devices()
    d = next((d for d in ds if d.get('name') == name), None) or next((d for d in ds if d.get('id') == name), None)
    if not d: sys.exit(f'No device called "{name}". Run: python tools/probe.py list')
    if not d.get('ip'): sys.exit(f'"{name}" has no IP address in devices.json. Run: python -m tinytuya scan, then the wizard again.')
    return d

def connect(d):
    c = tinytuya.Device(d['id'], d['ip'], d['key'], version=float(d.get('version') or 3.3), persist=True,
                        connection_timeout=5, connection_retry_limit=2)
    c.set_socketTimeout(5)
    r = c.status()
    if not r or 'Error' in r:
        sys.exit(f"Couldn't talk to it: {r}. Check it's on, its IP is right, and the Smart Life app is closed.")
    return c, r

def show(v):
    """Raw DPs arrive base64-encoded; show them as hex bytes, which is how the docs talk about them."""
    if isinstance(v, str):
        try: return 'raw: ' + base64.b64decode(v, validate=True).hex(' ')
        except Exception: pass
    return repr(v)

def opt(args, name, default):
    if name in args:
        i = args.index(name); v = args[i + 1]; del args[i:i + 2]; return v
    return default

def cmd_list(args):
    for d in devices():
        print(f"{d.get('name', '?'):28} {d.get('ip') or '(no IP)':16} v{d.get('version') or '?':5} "
              f"{d.get('product_name') or ''} {d.get('model') or ''}".rstrip())

def cmd_dps(args):
    d = find(args[0]); c, r = connect(d)
    local = r.get('dps', {})
    names = {}
    if Path('tinytuya.json').exists():
        try:     # every DP the device has, with names and types, from Tuya's cloud (needs your project's trial active)
            res = tinytuya.Cloud().cloudrequest(f"/v2.0/cloud/thing/{d['id']}/shadow/properties")
            for prop in (res.get('result') or {}).get('properties', []):
                names[str(prop.get('dp_id'))] = (prop.get('code'), prop.get('type'))
            if not names: print(f"(The Tuya cloud didn't list this device's DPs: {res.get('msg') or res}.)")
        except Exception as e:
            print(f'(Could not reach the Tuya cloud for DP names: {e})')
    else:
        print('(No tinytuya.json here, so DP names are unknown. Run in the folder the wizard wrote to.)')
    print(f"\n{d['name']}: protocol {d.get('version')}\n")
    for k in sorted(set(local) | set(names), key=int):
        code, typ = names.get(k, ('', ''))
        val = show(local[k])[:70] if k in local else '(not reporting right now)'
        print(f'  DP {k:>4}  {code or "":22} {typ or "":7} {val}')
    print('\nLook for an on/off switch (NOMA: DP 20 "switch_led") and a raw DP for per-bulb colours')
    print('(NOMA: DP 102 "color_bar"; other brands may call it something like "paint" or "dreamlight").')
    print('Many DPs only report once used: run `sniff` and paint some bulbs in the Smart Life app to see them.')

def cmd_sniff(args):
    d = find(args[0]); c, r = connect(d)
    c.set_socketTimeout(30)
    print(f"Watching {d['name']}. Change things in the Smart Life app (colour each bulb in its DIY or paint mode,"
          " pick effects, switch on and off) and the DPs that change are printed. Ctrl-C to stop.\n")
    last = time.time()
    while True:
        m = c.receive()
        if m and 'dps' in m:
            for k, v in m['dps'].items(): print(time.strftime('%H:%M:%S'), f'DP {k}:', show(v), flush=True)
        if time.time() - last > 10: c.heartbeat(nowait=True); last = time.time()

def cmd_paint(args):
    dp = int(opt(args, '--dp', 102))
    d = find(args[0]); n = int(args[1]) if len(args) > 1 else 24
    c, r = connect(d)
    def frame(cols): return base64.b64encode(bytes([0, 0, 0, 1, 1]) + b''.join(bytes(x) + b'\0\0' for x in cols)).decode()
    def send(cols, what):
        c.set_value(dp, frame(cols)); print(' ', what); time.sleep(1.2)
    off, red, blue, green = (0, 0, 0), (255, 0, 0), (0, 0, 255), (0, 255, 0)
    print(f"Sending String Theory's per-bulb format to DP {dp} on {d['name']} ({n} bulbs). Watch the string:")
    c.set_value(20, True); time.sleep(0.5)
    send([red] * n, '1. every bulb red')
    send([off] * n, '2. every bulb off')
    send([red] + [off] * (n - 1), '3. only the FIRST bulb red (the end the controller is on, usually)')
    send([off] * (n - 1) + [blue], '4. only the LAST bulb blue')
    send([red if i % 2 == 0 else green for i in range(n)], '5. red and green, every other bulb')
    print('  6. one red bulb walking from first to last:')
    for i in range(n):
        c.set_value(dp, frame([red if j == i else off for j in range(n)])); time.sleep(0.4)
    print('\nIf all six looked right, this controller works with String Theory as it is: add it with configure.py.')
    print('If nothing changed, try another raw DP from `dps` with --dp. If bulbs were wrong or shifted, see')
    print('"When the format is different" in docs/adapting.md.')

def cmd_power(args):
    dp = int(opt(args, '--dp', 20))
    d = find(args[0]); on = (args[1:] or ['on'])[0].lower() in ('on', '1', 'true')
    c, r = connect(d); c.set_value(dp, on)
    print(f"Sent {'on' if on else 'off'} to DP {dp} on {d['name']}.")

if __name__ == '__main__':
    a = sys.argv[1:]
    cmds = {'list': cmd_list, 'dps': cmd_dps, 'sniff': cmd_sniff, 'paint': cmd_paint, 'power': cmd_power}
    if not a or a[0] not in cmds or (a[0] != 'list' and len(a) < 2): sys.exit(__doc__)
    try: cmds[a[0]](a[1:])
    except KeyboardInterrupt: pass
