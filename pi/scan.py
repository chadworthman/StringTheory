#!/usr/bin/env python3
"""Find your Tuya lights: the page's "Find new lights" button runs this in the background.

  python3 scan.py          # in the data folder's parent, or with $STRINGTHEORY_DATA set

1. Asks the Tuya cloud for your devices and their local keys (needs tinytuya.json in the data folder, the
   same file the tinytuya wizard uses).
2. Looks for them on your home network: it listens for their broadcasts and also knocks on every address
   in your network on the Tuya port (6668), so it works even if a firewall blocks the broadcasts.
3. Any device it can't name from its broadcast is tried with each unplaced device's key until one answers.
4. Updates devices.json (keys stay there, chmod 600) and writes scan.json for the page, which never
   contains keys, IDs or addresses.
"""
import json, os, sys, time
from pathlib import Path

DATA = Path(os.environ.get('STRINGTHEORY_DATA') or Path(__file__).resolve().parent)
DEVICES, CREDS, CONFIG, OUT = DATA / 'devices.json', DATA / 'tinytuya.json', DATA / 'config.json', DATA / 'scan.json'

def write(obj, path, private=False):
    tmp = path.with_suffix('.scantmp')
    if private:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: f.write(json.dumps(obj, indent=2))
    else:
        tmp.write_text(json.dumps(obj))
    tmp.replace(path)

def report(**kw):
    """Write scan.json for the page. Until a scan finishes, keep the last list of devices it found, so a scan
    that fails (or is still running) doesn't hide the lights waiting to be added."""
    if 'devices' not in kw:
        try: kw['devices'] = json.loads(OUT.read_text()).get('devices')
        except (OSError, ValueError): pass
    write({'at': time.time(), **{k: v for k, v in kw.items() if v is not None}}, OUT)

def identify(tinytuya, ip, candidates):
    """Which of these devices is at ip: the one whose key gets an answer there. (device, protocol version)."""
    for d in candidates:
        for ver in (3.5, 3.4, 3.3):
            try:
                c = tinytuya.Device(d['id'], ip, d['key'], version=ver, connection_timeout=2, connection_retry_limit=1)
                c.set_socketTimeout(2); c.set_socketRetryLimit(1)
                r = c.status(); c.close()
                if r and 'dps' in r: return d, ver
            except Exception:
                pass
    return None, None

def main():
    report(running=True, step='Asking the Tuya cloud for your devices…', pid=os.getpid())
    try:
        import tinytuya
    except ImportError:
        return report(running=False, error='tinytuya is not installed.')
    if not CREDS.exists():
        return report(running=False, error="Can't look for new lights yet: the Pi needs your Tuya cloud details (tinytuya.json) "
                                            'in its data folder. See the README, under Zones.')
    try:
        cloud = tinytuya.Cloud(**{k: v for k, v in json.loads(CREDS.read_text()).items()
                                  if k in ('apiRegion', 'apiKey', 'apiSecret', 'apiDeviceID')})
        found = cloud.getdevices(False)
        if not isinstance(found, list): raise RuntimeError(found)
    except Exception as e:
        return report(running=False, error=f"Couldn't reach the Tuya cloud: {str(e)[:200]}")

    old = {d['id']: d for d in (json.loads(DEVICES.read_text()) if DEVICES.exists() else [])}
    devs = []
    for d in found:                                   # keep what we already know about each device (its address)
        was = old.get(d.get('id'), {})
        devs.append({**d, **{k: was[k] for k in ('ip', 'version') if was.get(k) and not d.get(k)}})
    by_id = {d['id']: d for d in devs}

    report(running=True, step='Looking for them on your network (about a minute)…', pid=os.getpid())
    write(devs, DEVICES, private=True)                 # the scanner reads keys from devices.json in its folder
    os.chdir(DATA)
    try:
        seen = tinytuya.deviceScan(False, 1, False, False, True) or {}
    except Exception as e:
        seen = {}; print('scan:', e, flush=True)
    unknown = []
    for ip, info in seen.items():
        did = info.get('gwId') or info.get('id')
        if did in by_id:
            by_id[did]['ip'] = ip
            if info.get('version') and str(info['version']) not in ('0', '0.0'): by_id[did]['version'] = str(info['version'])
        else:
            unknown.append(ip)

    # Addresses that answered on 6668 but didn't say who they are: try each unplaced device's key there.
    unplaced = [d for d in devs if d.get('key') and not d.get('sub') and (not d.get('ip') or d['ip'] not in seen)]
    if unknown and unplaced: report(running=True, step='Working out which device is which…', pid=os.getpid())
    for ip in unknown:
        d, ver = identify(tinytuya, ip, unplaced)
        if d: d['ip'], d['version'] = ip, str(ver); unplaced.remove(d)

    write(devs, DEVICES, private=True)
    strings = {s['name'] for s in json.loads(CONFIG.read_text()).get('strings', [])} if CONFIG.exists() else set()
    report(running=False, devices=[{'name': d.get('name') or '(no name)', 'product': d.get('product_name') or '',
                                    'model': d.get('model') or '', 'category': d.get('category') or '',
                                    'online': bool(d.get('ip')), 'in_use': d.get('name') in strings}
                                   for d in devs if not d.get('sub')])

if __name__ == '__main__':
    try: main()
    except Exception as e: report(running=False, error=f'The scan stopped: {str(e)[:200]}')
