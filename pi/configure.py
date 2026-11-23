#!/usr/bin/env python3
"""Tell String Theory which of your Tuya devices are light strings, in what order, and how many bulbs each has.

  python3 configure.py            # asks, then writes config.json next to devices.json

Run it after the tinytuya wizard has made devices.json (in this folder, or in $STRINGTHEORY_DATA). It never
prints your keys.
"""
import json, os, sys
from pathlib import Path

DATA = Path(os.environ.get('STRINGTHEORY_DATA') or Path(__file__).resolve().parent)
DEVICES, CONFIG = DATA / 'devices.json', DATA / 'config.json'

def ask(prompt, default=''):
    try: v = input(f'{prompt} [{default}]: ' if default else f'{prompt}: ').strip()
    except EOFError: v = ''
    return v or default

def main():
    if not DEVICES.exists():
        sys.exit(f"Can't find {DEVICES}. Run the tinytuya wizard first (python -m tinytuya wizard) in that folder.")
    devices = json.loads(DEVICES.read_text())
    print(f'\nDevices in {DEVICES.name}:\n')
    for i, d in enumerate(devices, 1):
        print(f"  {i:2}. {d.get('name') or '(no name)'}   {d.get('product_name') or d.get('model') or ''}")
    current = json.loads(CONFIG.read_text()).get('strings', []) if CONFIG.exists() else []
    default = ','.join(str(1 + next(i for i, d in enumerate(devices) if d.get('name') == s['name']))
                       for s in current if any(d.get('name') == s['name'] for d in devices))
    print('\nWhich are your light strings? List their numbers in the order the strings are laid out:')
    print('the end of each string should meet the start of the next. For example: 3,1')
    picks = ask('Light strings', default)
    try: idx = [int(x) - 1 for x in picks.replace(' ', '').split(',') if x]
    except ValueError: sys.exit('Use the numbers from the list, separated by commas.')
    if not idx or any(i < 0 or i >= len(devices) for i in idx): sys.exit('Pick at least one number from the list.')
    strings = []
    for i in idx:
        name = devices[i].get('name')
        old = next((s['bulbs'] for s in current if s['name'] == name), 24)
        bulbs = ask(f'  Bulbs on "{name}"', str(old))
        if not bulbs.isdigit() or not 1 <= int(bulbs) <= 1000: sys.exit('Bulbs must be a number.')
        entry = {'name': name, 'bulbs': int(bulbs)}
        was = next((s for s in current if s['name'] == name), {})
        if was.get('layout') and was.get('bulbs') == entry['bulbs']: entry['layout'] = was['layout']   # keep its bulb layout
        strings.append(entry)
    cfg = json.loads(CONFIG.read_text()) if CONFIG.exists() else {}
    cfg['strings'] = strings
    CONFIG.write_text(json.dumps(cfg, indent=2) + '\n')
    print(f'\nSaved {CONFIG}. Restart String Theory to use it, then play "Find the seams" to check the order.')

if __name__ == '__main__':
    main()
