#!/usr/bin/env python3
"""String Theory in Apple Home: one light called "Christmas Lights", so Siri can work the lights.

  python3 homekit.py          # runs as the string-theory-homekit service; needs: pip install HAP-python

"Hey Siri, turn on the Christmas lights", "turn off the Christmas lights", "set the Christmas lights to
40%", and a switch per show: "turn on Grinch Christmas Lights" (or "Moving Grinch Christmas Lights") plays
it everywhere and turns the lights on; "turn off Grinch Christmas Lights" turns them off if it's playing. It covers every zone at once: on and off hold the lights until the schedule next agrees, exactly
like the switch on the page, and brightness goes to the nearest of the page's steps (10% to 100%). In
Home it shows as on while any zone is lit. The name comes from state.json homekit.name if set.

It never touches the lights or state.json itself: every change goes through the control page on this
Pi (with the key in local.key, so the page's login doesn't apply), so it follows the same rules as the
app. It writes homekit-status.json (paired or not, and the setup code) for the page's Setup screen.
Pairing state lives in homekit.state in the data folder; delete it to pair again from scratch.
"""
import json, logging, os, sys, time, urllib.request
from pathlib import Path

DATA = Path(os.environ.get('STRINGTHEORY_DATA') or Path(__file__).resolve().parent)
PAGE = f"http://127.0.0.1:{os.environ.get('PORT', 8080)}"
PORT = int(os.environ.get('HOMEKIT_PORT', 51826))
STATUS = DATA / 'homekit-status.json'
NAME = 'Christmas Lights'
# Every show is a switch on the same accessory, named "<show> <NAME>": "Hey Siri, turn on Grinch Christmas
# Lights", "turn on Moving Grinch Christmas Lights". The list and the words come from the page
# (/api/summary shows: themes, moving versions, playlists, your patterns, followed teams). state.json
# homekit.shows ({key: spoken name}) replaces it with your own short list.

from pyhap.accessory import Accessory                    # noqa: E402
from pyhap.accessory_driver import AccessoryDriver       # noqa: E402
from pyhap.const import CATEGORY_LIGHTBULB               # noqa: E402

log = logging.getLogger('homekit')

def key():
    for _ in range(30):                                  # the page makes the key at startup; wait for it
        try: return (DATA / 'local.key').read_text().strip()
        except FileNotFoundError: time.sleep(2)
    sys.exit('No local.key: is the control page (string-theory-web) running?')

def call(path, body=None):
    req = urllib.request.Request(PAGE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers={'Content-Type': 'application/json', 'X-String-Theory-Key': KEY})
    with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())

def zones():
    """The zones that have strings: the ones the light controls."""
    return [z for z in SUMMARY.get('zones', []) if z['has_strings']]

class Lights(Accessory):
    category = CATEGORY_LIGHTBULB
    def __init__(self, driver, name):
        super().__init__(driver, name)
        s = self.add_preload_service('Lightbulb', chars=['On', 'Brightness'])
        self.on = s.configure_char('On', setter_callback=self.set_on)
        self.bright = s.configure_char('Brightness', setter_callback=self.set_bright)
        self.shows = {}
        shows = (SUMMARY.get('homekit') or {}).get('shows') or {x['id']: x['say'] for x in SUMMARY.get('shows', [])}
        for k, label in list(shows.items())[:98]:       # Home allows up to 100 services on one accessory
            sw = self.add_preload_service('Switch', chars=['Name', 'ConfiguredName'])
            sw.configure_char('Name', value=f'{label} {name}')
            sw.configure_char('ConfiguredName', value=f'{label} {name}')
            self.shows[k] = sw.configure_char('On', setter_callback=lambda v, k=k: self.set_show(k, v))
    def playing(self, z, k):
        """Whether zone z is playing show k (exactly: Grinch and Moving Grinch are separate switches)."""
        return z['show'] == k
    def set_show(self, k, value):
        if value:                                        # play it everywhere, and make sure the lights are on
            global SUMMARY
            for other, char in self.shows.items():       # one show at a time: the rest switch off now
                if other != k: char.set_value(False)
            self.each('/api/show', {'show': k})
            try: SUMMARY = call('/api/summary')          # fresh: is anything lit right now?
            except Exception as e: log.warning('page: %s', e)
            if not any(z['lit'] for z in zones()): self.each('/api/power', {'mode': 'on'})
        elif any(z['lit'] and self.playing(z, k) for z in zones()):   # "turn off Grinch Christmas Lights": lights off
            self.each('/api/power', {'mode': 'off'})
    def each(self, path, body):
        for z in zones():
            try: call(path, {**body, 'zone': z['id']})
            except Exception as e: log.warning('%s %s: %s', path, z['id'], e)
    def set_on(self, value):
        self.each('/api/power', {'mode': 'on' if value else 'off'})
    def set_bright(self, value):
        if value <= 0: return self.set_on(False)
        steps = SUMMARY.get('brightnesses') or [1.0]
        self.each('/api/brightness', {'brightness': min(steps, key=lambda x: abs(x * 100 - value))})
    @Accessory.run_at_interval(5)
    async def run(self):
        global SUMMARY
        try: SUMMARY = call('/api/summary')
        except Exception as e: return log.warning('page: %s', e)
        zs = zones()
        self.on.set_value(any(z['lit'] for z in zs))
        lit = [z for z in zs if z['lit']] or zs
        if lit: self.bright.set_value(round(max(z['brightness'] for z in lit) * 100))
        for k, char in self.shows.items():               # on while a lit zone plays it
            char.set_value(any(z['lit'] and self.playing(z, k) for z in zs))
        write_status(self.driver)

def write_status(driver):
    """For the page: whether Home is paired, and the code to pair it (shown on Setup until it is)."""
    st = {'paired': bool(driver.state.paired), 'code': driver.state.pincode.decode(), 'at': time.time(),
          'name': driver.accessory.display_name}
    tmp = STATUS.with_suffix('.tmp'); tmp.write_text(json.dumps(st)); tmp.replace(STATUS)

SUMMARY = {}
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
    KEY = key()
    while True:                                          # wait for the page to answer
        try: SUMMARY = call('/api/summary'); break
        except Exception as e: log.info('waiting for the control page: %s', e); time.sleep(5)
    driver = AccessoryDriver(port=PORT, persist_file=str(DATA / 'homekit.state'),
                             advertise=os.environ.get('HOMEKIT_ADVERTISE', '1') != '0')   # 0: testing, stay hidden
    driver.add_accessory(Lights(driver, (SUMMARY.get('homekit') or {}).get('name') or NAME))
    write_status(driver)
    log.info('Apple Home: %s', 'paired' if driver.state.paired else 'not paired yet: the setup code is on the page (Setup, Zones)')
    driver.start()
