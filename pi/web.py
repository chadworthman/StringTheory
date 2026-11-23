#!/usr/bin/env python3
"""Home-network control page for the light show. Standard library only.

Reads/writes the same state.json that lights.py watches, so changes apply within a second.
Listens on port 8080 on the LAN. No login, so never expose it to the internet (no port forward,
tunnel or reverse proxy) without adding authentication first. POSTs must be JSON, which browsers won't
send cross-site without a CORS preflight this server never approves, so other websites can't
drive it from your phone's browser.
"""
import datetime, gzip, json, os, re, sys, time
from urllib.parse import urlsplit, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lights as L

PORT = int(os.environ.get('PORT', 8080))
PAGE = (Path(__file__).resolve().parent / 'index.html')
HELP = (Path(__file__).resolve().parent / 'help.html')
STATIC = {'/logo.svg': ('logo.svg', 'image/svg+xml'), '/icon.png': ('icon.png', 'image/png'),
          '/icon-192.png': ('icon-192.png', 'image/png'), '/icon-512.png': ('icon-512.png', 'image/png'),
          '/icon-maskable.png': ('icon-maskable.png', 'image/png'),
          '/manifest.webmanifest': ('manifest.webmanifest', 'application/manifest+json'),
          '/fonts/pacifico.woff2': ('fonts/pacifico.woff2', 'font/woff2')}
DEFAULT_NAME = 'My lights'
# Each time zone's main city, from the public-domain tz database (zone1970.tab): Locate me uses it when the
# browser won't share a precise position, which is always the case on a plain-http page like this one.
TZ_COORDS = json.loads((Path(__file__).resolve().parent / 'tz_coords.json').read_text())
def local_timezone():
    """This computer's time zone name, e.g. 'America/Toronto', if it can be found."""
    if os.environ.get('TZ') in TZ_COORDS: return os.environ['TZ']
    try: return Path('/etc/timezone').read_text().strip()
    except OSError: pass
    try: return str(Path('/etc/localtime').resolve()).split('zoneinfo/')[-1]
    except OSError: return None

# Friendly names and one-line descriptions, in the order they appear on the page.
SHOW_INFO = [
    *[(k, n, f'Every bulb {n.lower()}: a background for another zone, or a wash on its own.') for k, n, _ in L.WASHES],
    ('classicloop',  'Classic loop',     ''),
    ('medley',       'Christmas medley', ''),
    ('winter',       'Winter night',     ''),
    ('fireside',     'Fireside',         ''),
    ('spooky',       'Spooky night',     ''),
    ('rainbows',     'Rainbow tour',     ''),
    ('party',        'Party',            ''),
    ('classic',      'Classic',          'Red, green, yellow, blue and orange.'),
    ('chase5',       'Classic (moving)',    'Classic colours stepping slowly along.'),
    ('classicwhite', 'Classic & white',  'Classic colours stepping along, with an all-white sweep every minute or so.'),
    ('candycane',    'Candy cane (moving)', 'Red, white and green candy-cane stripes on the move.'),
    ('xmas',         'Meet in the middle', 'Red, green and white stripes flowing toward the join.'),
    ('redscan',      'Red with chasers', 'White and green chasers from opposite ends, crossing where the strings meet.'),
    ('whitescan',    'White with chasers', 'Red and green chasers from opposite ends, crossing where the strings meet.'),
    ('icy',          'Icy',              'Bands of deep blue, ice blue and white drifting along.'),
    ('embers',       'Embers',           'Glowing coals in deep red and amber, flickering like a fire.'),
    ('snowfall',     'Snowfall',         'White flakes drifting along a night-blue string, piling up at the end.'),
    ('marquee',      'Theatre marquee',  'Every third bulb lit, stepping along like an old cinema sign.'),
    ('newyear',      "New Year's Eve",   'Gold and white all evening, then a minute of flashes at midnight.'),
    ('hanukkah',     'Hanukkah',         'A blue and white menorah. During Hanukkah, one more candle each night.'),
    ('seasonal',     'Holiday autopilot', ''),
    ('eastermove',   'Easter (moving)',  'Pastel pink, yellow, mint, blue and lilac stripes chasing along.'),
    ('stpatsmove',   "St. Patrick's Day (moving)", 'Bright green, dark green and gold stepping along.'),
    ('sunrise',      'Sunrise & sunset', 'From a deep night blue, the colour rises from the centre out through blue, purple, red, orange and yellow until the centre glows white, holds for the day, then sets back to night blue the same way.'),
    ('sunsetmove',   'Sunset (moving)',  'Red, orange, amber, pink and purple stripes moving out from the centre, round and round.'),
    ('treetwinkle',  'Twinkling Christmas tree', 'Steady green with red, gold and blue ornaments that twinkle, each on its own rhythm.'),
    ('auroramove',   'Aurora colours (moving)', "The aurora bands holding still while the blue slowly widens and narrows around each purple centre."),
    ('rainbowmove',  'Rainbow (moving)', 'The colour wheel rolling along the whole length.'),
    ('doublemove',   'Double rainbow (moving)', 'Two colour wheels end to end, rolling along together.'),
    ('fibonacci',    'Fibonacci',        'On a white string, golden-angle colours grow from the start 1, 2, 3, 5, 8, 13, 21, 34 bulbs until it is full, then give way to white from the start the same way, so the colour travels along.'),
    ('ukraine',      'Slava Ukraini',    "Ukraine's blue and yellow, three ways in turn: stripes chasing along, the flag waving, then sunflowers opening on a blue sky."),
    ('chaos',        'Chaos',            'Colours changing at random, the whole string lurching about, sudden white bursts, strobes, and stretches of bulbs going dark.'),
    ('rainbow',      'Rainbow',          'The colour wheel in order, end to end.'),
    ('double',       'Double rainbow',   'The colour wheel twice, end to end.'),
    ('jostle',       'Confetti (moving)',  'The rainbow colours jostling and drifting along.'),
    ('confetti',     'Confetti',         'The rainbow colours in random spots.'),
    ('halloween',    'Halloween (moving)',        'Orange, purple and dark green stripes on the move.'),
    ('candystill',   'Candy cane', 'Red, white and green candy-cane stripes, three bulbs each.'),
    ('halloweenstill', 'Halloween', 'Orange, purple and dark green stripes.'),
    ('goldenangle',  'Golden angle',     'Each bulb turns 137.5° round the colour wheel from the last, like seeds in a sunflower.'),
    ('redgreen',     'Red & green',      'Red and green stripes, three bulbs each.'),
    ('holly',        'Holly',            'Three green leaves and a red berry, over and over.'),
    ('grinch',       'Grinch',           'Grinch green, yellow, lime and gold stripes, with a red bulb after the yellow and after the gold.'),
    ('tree',         'Christmas tree',   'Green with red, gold and blue ornaments.'),
    ('peppermint',   'Peppermint',       'Red and white, every other bulb.'),
    ('bluewhite',    'Blue & white',     'Blue and white stripes, three bulbs each.'),
    ('silvergold',   'Silver & gold',    'White and gold stripes, three bulbs each.'),
    ('aurora',       'Aurora colours',   "The northern lights' green, teal, blue and purple, in bands of three bulbs."),
    ('sunset',       'Sunset',           'Red, orange, amber, pink and purple stripes, mirrored about the centre.'),
    ('valentines',   "Valentine's Day",  'Red, pink and white stripes, three bulbs each.'),
    ('stpats',       "St. Patrick's Day", 'Bright green, dark green and gold stripes, three bulbs each.'),
    ('easter',       'Easter',           'Pastel pink, yellow, mint, blue and lilac stripes, three bulbs each.'),
    ('canada',       'Canada Day',       'Red and white bands.'),
    ('redgreenmove', 'Red & green (moving)', 'Red and green stripes chasing along.'),
    ('hollymove',    'Holly (moving)',   'Holly leaves and berries chasing along.'),
    ('grinchmove',   'Grinch (moving)',  'Grinch green, yellow, lime and gold stripes with red bulbs between, chasing along.'),
    ('peppermintmove', 'Peppermint (moving)', 'Red and white stripes chasing along.'),
    ('bluewhitemove', 'Blue & white (moving)', 'Blue and white stripes chasing along.'),
    ('silvergoldmove', 'Silver & gold (moving)', 'White and gold stripes chasing along.'),
    ('valentinesmove', "Valentine's Day (moving)", 'Red, pink and white stripes chasing along.'),
    ('canadamove',   'Canada Day (moving)', 'Red and white bands chasing along.'),
    ('ducks', 'Anaheim Ducks', 'Mostly orange, with gold and a black (unlit) edge.'),
    ('ducksmove', 'Anaheim Ducks (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('bruins', 'Boston Bruins', 'Gold and black (unlit) in equal stripes.'),
    ('bruinsmove', 'Boston Bruins (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('sabres', 'Buffalo Sabres', 'Royal blue, with gold and white.'),
    ('sabresmove', 'Buffalo Sabres (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('flames', 'Calgary Flames', 'Mostly red, with a gold flame and a black (unlit) edge.'),
    ('flamesmove', 'Calgary Flames (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('hurricanes', 'Carolina Hurricanes', 'Red, with a silver stripe and black (unlit).'),
    ('hurricanesmove', 'Carolina Hurricanes (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('blackhawks', 'Chicago Blackhawks', 'Red, with the white-black-white jersey stripe.'),
    ('blackhawksmove', 'Chicago Blackhawks (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('avalanche', 'Colorado Avalanche', 'Burgundy, blue and silver.'),
    ('avalanchemove', 'Colorado Avalanche (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('bluejackets', 'Columbus Blue Jackets', 'Mostly navy, with red and white.'),
    ('bluejacketsmove', 'Columbus Blue Jackets (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('stars', 'Dallas Stars', 'Victory green, with silver and black (unlit).'),
    ('starsmove', 'Dallas Stars (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('redwings', 'Detroit Red Wings', 'Mostly red, with a single white stripe.'),
    ('redwingsmove', 'Detroit Red Wings (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('oilers', 'Edmonton Oilers', 'Blue and orange stripes, three bulbs each.'),
    ('oilersmove', 'Edmonton Oilers (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('panthers', 'Florida Panthers', 'Red, navy and gold.'),
    ('panthersmove', 'Florida Panthers (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('kings', 'Los Angeles Kings', 'Black (unlit), silver and white.'),
    ('kingsmove', 'Los Angeles Kings (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('wild', 'Minnesota Wild', 'Forest green, with red and wheat.'),
    ('wildmove', 'Minnesota Wild (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('canadiens', 'Montréal Canadiens', 'Mostly red, with a blue band between white stripes.'),
    ('canadiensmove', 'Montréal Canadiens (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('predators', 'Nashville Predators', 'Mostly gold, with navy.'),
    ('predatorsmove', 'Nashville Predators (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('devils', 'New Jersey Devils', 'Red and black (unlit), two bulbs each.'),
    ('devilsmove', 'New Jersey Devils (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('islanders', 'New York Islanders', 'Royal blue, white and orange.'),
    ('islandersmove', 'New York Islanders (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('rangers', 'New York Rangers', 'Mostly blue, with a red stripe between white.'),
    ('rangersmove', 'New York Rangers (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('senators', 'Ottawa Senators', 'Mostly black (unlit bulbs), with red and a gold trim.'),
    ('senatorsmove', 'Ottawa Senators (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('flyers', 'Philadelphia Flyers', 'Mostly orange, with white and black (unlit).'),
    ('flyersmove', 'Philadelphia Flyers (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('penguins', 'Pittsburgh Penguins', 'Black (unlit), gold and white.'),
    ('penguinsmove', 'Pittsburgh Penguins (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('sharks', 'San Jose Sharks', 'Mostly teal, with black (unlit) and orange.'),
    ('sharksmove', 'San Jose Sharks (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('kraken', 'Seattle Kraken', 'Ice blue, deep navy and a red accent.'),
    ('krakenmove', 'Seattle Kraken (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('blues', 'St. Louis Blues', 'Blue, navy and a gold note.'),
    ('bluesmove', 'St. Louis Blues (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('lightning', 'Tampa Bay Lightning', 'Blue and white, two to one.'),
    ('lightningmove', 'Tampa Bay Lightning (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('leafs', 'Toronto Maple Leafs', 'Mostly blue, with a single white stripe.'),
    ('leafsmove', 'Toronto Maple Leafs (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('mammoth', 'Utah Mammoth', 'Black (unlit), mountain blue and white.'),
    ('mammothmove', 'Utah Mammoth (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('canucks', 'Vancouver Canucks', 'Blue and green, separated by white.'),
    ('canucksmove', 'Vancouver Canucks (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('goldenknights', 'Vegas Golden Knights', 'Gold, steel grey and a red accent.'),
    ('goldenknightsmove', 'Vegas Golden Knights (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('capitals', 'Washington Capitals', 'Red, white and navy.'),
    ('capitalsmove', 'Washington Capitals (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('jets', 'Winnipeg Jets', 'Mostly navy, with sky blue and a red accent.'),
    ('jetsmove', 'Winnipeg Jets (moving)', 'Its stripes chasing along, with the team colours flashing.'),
    ('fourthchase',  'Fourth of July (moving)', 'Red, white and blue stripes chasing along.'),
    ('goldenanglemove', 'Golden angle (moving)', 'The golden-angle colours rolling along.'),
    ('fourth',       'Fourth of July',   'Red, white and blue stripes, three bulbs each.'),
    ('fourthmove',   'Fourth of July fireworks', 'Red, white and blue fireworks bursting and fading over a night-blue sky.'),
    ('seams',        'Find the seams',   "Each string glows dimly in its own colour. A string's first bulb blinks white; its last bulb is bright. A bright bulb next to a blinking white one is a seam."),
    ('walk',         'Bulb walk',        'One red bulb steps along every bulb. A skipped bulb means a dropped update.'),
    ('strings',      'Which string is which', 'Each string its own colour: red, green, blue, yellow, purple, white.'),
    ('allwhite',     'All white',        'Every bulb full white, to spot dead or dim bulbs.'),
    ('quad',         'Test pattern',     'Colour bars like an old TV test card: white, yellow, cyan, green, magenta, red and blue, with the reversed band on the next string.'),
]

NOT_IN_PLAYLISTS = {'seasonal', 'seams', 'walk', 'strings', 'quad'} | set(L.PLAYLISTS)   # tests (bar All white) and playlists
# How each tab is organised: groups in order, shows in order within each group. Holidays follow
# the calendar. Every show in SHOW_INFO must appear here exactly once.
GROUPS = [
    ('Christmas', ['classic', 'redgreen', 'tree', 'holly', 'grinch', 'candystill', 'peppermint', 'silvergold',
                   'redgreenmove', 'hollymove', 'grinchmove', 'peppermintmove', 'silvergoldmove',
                   'chase5', 'classicwhite', 'candycane', 'treetwinkle', 'xmas', 'redscan', 'whitescan', 'marquee',
                   'classicloop', 'medley']),
    ('Winter', ['bluewhite', 'aurora', 'icy', 'snowfall', 'auroramove', 'bluewhitemove']),
    ('Holidays', ['seasonal', 'newyear', 'valentines', 'valentinesmove', 'stpats', 'stpatsmove', 'easter', 'eastermove',
                  'canada', 'canadamove', 'fourthchase',
                  'fourth', 'fourthmove', 'halloweenstill', 'halloween', 'hanukkah']),
    ('Seasonal', ['winter', 'fireside', 'spooky']),
    ('Colour', ['rainbow', 'double', 'confetti', 'goldenangle', 'goldenanglemove', 'sunset', 'sunrise',
                'rainbowmove', 'doublemove', 'jostle', 'sunsetmove', 'fibonacci', 'ukraine', 'embers', 'chaos']),
    ('Just for fun', ['rainbows', 'party']),
    ('Solid colours', [k for k, _, _ in L.WASHES]),
    ('Hockey', ['ducks', 'ducksmove', 'bruins', 'bruinsmove', 'sabres', 'sabresmove', 'flames', 'flamesmove', 'hurricanes', 'hurricanesmove', 'blackhawks', 'blackhawksmove', 'avalanche', 'avalanchemove', 'bluejackets', 'bluejacketsmove', 'stars', 'starsmove', 'redwings', 'redwingsmove', 'oilers', 'oilersmove', 'panthers', 'panthersmove', 'kings', 'kingsmove', 'wild', 'wildmove', 'canadiens', 'canadiensmove', 'predators', 'predatorsmove', 'devils', 'devilsmove', 'islanders', 'islandersmove', 'rangers', 'rangersmove', 'senators', 'senatorsmove', 'flyers', 'flyersmove', 'penguins', 'penguinsmove', 'sharks', 'sharksmove', 'kraken', 'krakenmove', 'blues', 'bluesmove', 'lightning', 'lightningmove', 'leafs', 'leafsmove', 'mammoth', 'mammothmove', 'canucks', 'canucksmove', 'goldenknights', 'goldenknightsmove', 'capitals', 'capitalsmove', 'jets', 'jetsmove']),
    ('Tests', ['seams', 'walk', 'strings', 'allwhite', 'quad']),
]
GROUP_OF = {k: g for g, keys in GROUPS for k in keys}
_rank = {k: i for i, k in enumerate(k for _, keys in GROUPS for k in keys)}
SHOW_INFO.sort(key=lambda x: _rank.get(x[0], len(_rank)))
assert set(GROUP_OF) == {k for k, _, _ in SHOW_INFO}, 'GROUPS and SHOW_INFO disagree'

# Still themes with an animated version: one card with an Animate switch. The animation differs by
# theme (a chase, a drift, twinkling ornaments...). Shows that are animations of their own stay on Moving.
# A link shown under a show's description (outside the card's play button).
DOUBLE_RAINBOW_VIDEO = {'text': 'What does it mean?', 'url': 'https://www.youtube.com/watch?v=OQSNhk5ICTI',
                        'title': 'The original Double Rainbow video (Yosemitebear, 2010) on YouTube'}
LINKS = {'double': DOUBLE_RAINBOW_VIDEO, 'doublemove': DOUBLE_RAINBOW_VIDEO}

MOVING_OF = {'classic': 'chase5', 'tree': 'treetwinkle', 'candystill': 'candycane', 'halloweenstill': 'halloween', 'rainbow': 'rainbowmove',
             'double': 'doublemove', 'confetti': 'jostle', 'aurora': 'auroramove', 'sunset': 'sunsetmove',
             'easter': 'eastermove', 'stpats': 'stpatsmove',
             # the rest simply chase their stripes
             'redgreen': 'redgreenmove', 'bluewhite': 'bluewhitemove', 'silvergold': 'silvergoldmove', 'holly': 'hollymove', 'grinch': 'grinchmove',
             'peppermint': 'peppermintmove', 'canada': 'canadamove', 'valentines': 'valentinesmove', 'fourth': 'fourthchase',
             'goldenangle': 'goldenanglemove',
             **{k: k + 'move' for k in L.NHL_TEAM}}   # hockey: Animate plays the team's chase
VARIANTS = set(MOVING_OF.values()) | {k + 'move' for k in L.NHL_TEAM}   # hockey moves: game mode and playlists only

FIND_SECS = 20   # how long "Find it" lights a bulb
TESTS = {'seams', 'walk', 'strings', 'allwhite', 'quad'}   # shown on the page's Tests tab

DAYS = {'hanukkah': 'Hanukkah', 'newyear': "New Year's", 'valentines': "Valentine's Day", 'stpats': "St. Patrick's Day",
        'easter': 'Easter', 'canada': 'Canada Day', 'fourthmove': 'the Fourth of July', 'halloween': 'Halloween', 'classicloop': 'Christmas', 'classic': 'no holiday'}
def autopilot_desc():
    pick = L.holiday_for(); name = dict((k, n) for k, n, _ in SHOW_INFO)[pick]
    return f"Picks a show by the date. Today it's {DAYS.get(pick, name)}, so it plays {name}."

def hexes(bulbs): return ['#%02x%02x%02x' % c for c in bulbs]

SAMPLE = 0.05      # seconds; every show changes on multiples of its step, all much longer than this
_timelines = {}
def timeline(key, st=None, zm=L):
    """The show's whole loop as [[start_seconds, 'rrggbb' per bulb], ...], one entry per change,
    built for the zone module zm (so for that zone's number of bulbs)."""
    if key == 'seasonal': return timeline(zm.holiday_for(), st, zm)
    if key.startswith('custom:'): key = 'custom:' + json.dumps((st or L.load_state()).get('customs', {}).get(key[7:]))
    ck = (tuple(zm.SIZES), key)
    if ck not in _timelines:
        fn = zm.SHOWS.get(key) or zm.custom_show(json.loads(key[7:]), st); period = getattr(fn, 'period', 0)
        if getattr(fn, 'items', None):
            # Playlists: send the recipe, not frames; the page assembles them from each theme's preview.
            _timelines[ck] = {'period': period, 'tstep': zm.TSTEP,
                              'items': [{**it, 'tdur': zm.TOTAL * zm.TSTEP if it['transition'] == 'chase'
                                         else zm.TRANSITION_SECS[it['transition']]} for it in fn.items]}
            return _timelines[ck]
        frames, last = [], None
        dt = getattr(fn, 'tick', SAMPLE)
        for i in range(max(1, round(period / dt))):
            f = ''.join('%02x%02x%02x' % c for c in fn(i * dt))
            if f != last: frames.append([round(i * dt, 2), f]); last = f
        _timelines[ck] = {'period': period, 'frames': frames}
    return _timelines[ck]

SMALL_ZONE = 6   # zones this short (a pair of floods) get a bar of each show's colours on its card
_palette_zone = []
def show_colours(key, st, depth=0):
    """Every colour the show uses over its whole loop, worked out on a full-length (48-bulb) run so a rainbow
    is a whole rainbow, in order of first appearance, dark left out. A zone of two bulbs can't show a pattern,
    so its cards show this instead: the colours the show is made of."""
    if not _palette_zone: _palette_zone.append(L.load_copy([('palette a', 24), ('palette b', 24)]))
    zm = _palette_zone[0]
    try: tl = timeline(key, st, zm)
    except Exception: return []
    out = []
    if 'items' in tl:                     # playlists: the colours of every show in them
        for it in tl['items'] if depth == 0 else []:
            out += [c for c in show_colours(it['show'], st, 1) if c not in out]
    else:
        for _, f in tl['frames']:
            for i in range(0, len(f), 6):
                c = '#' + f[i:i + 6]
                if c != '#000000' and c not in out: out.append(c)
    return out[:48]

def hockey_status(key):
    """What the engine's game watcher knows about the tracked team (written to hockey.json)."""
    if key not in L.NHL_TEAM: return None
    try: return json.loads((L.DATA / 'hockey.json').read_text()).get(L.NHL_TEAM[key])
    except (OSError, ValueError): return None

def zone_clock(st, z):
    """What a zone is playing and where its clock is, for drawing it in the house picture:
    {show, started, speed, reversed}. Game mode plays the team's theme, as in state_payload."""
    try: eng = json.loads(L.ENGINE.read_text()).get('zones', {}).get(z['id'], {})
    except Exception: eng = {}
    game = eng.get('game') if z.get('follow') else None
    view = L.zone_view(st, z); zm = L.zone_module(z)
    show = game or view.get('show', L.DEFAULT_SHOW)
    if zm.show_fn(show, view) is None: show = L.DEFAULT_SHOW
    return {'show': show, 'started': eng.get('game_t0') if game else show_started(view, zm),
            'speed': zm.speed_of(view, show), 'reversed': bool(view.get('reversed', {}).get(show)) and not game}

def house_of(st):
    """Where each string hangs, for the house picture at the top of the page (state.json 'house'), with
    defaults: strings on row 1 end to end in order, short strings (floods) as flood lights spread out.
    Each: {row: 1-3, place: 'after' | 'between' | 'flood', with: string it sits between, flip: bulb 1 at
    the right, spots: [left-to-right %, one per bulb] for floods}."""
    saved = (st.get('house') or {}).get('strings', {})
    right = {n for z in L.zones_of(st) if z.get('direction') == 'right' for n in z.get('strings', [])}
    out = {}
    for name, bulbs in L.STRINGS:
        p = dict(saved.get(name) or {})
        if p.get('place') not in ('after', 'between', 'flood'): p['place'] = 'flood' if bulbs <= SMALL_ZONE else 'after'
        p['row'] = p.get('row') if p.get('row') in (1, 2, 3) else 1
        if p['place'] == 'between' and p.get('with') not in dict(L.STRINGS): p['place'] = 'after'
        p['flip'] = bool(p['flip']) if 'flip' in p else name in right   # default: its zone's starting end
        spots = p.get('spots') if isinstance(p.get('spots'), list) else []
        p['spots'] = [max(0, min(100, int(x))) if isinstance(x, (int, float)) else round(100 * (i + 0.5) / bulbs)
                      for i, x in enumerate((spots + [None] * bulbs)[:bulbs])]
        out[name] = p
    return out

def zone_lit(st, z):
    """Whether a zone's lights are on now (its hold, else its schedule; game mode aside), for the All view."""
    if not L.zone_strings(z): return False
    v = L.zone_view(st, z); ov = L.override(v)
    return bool(L.is_on_hours(v) if ov is None else ov)

def pick_zone(st, zid):
    zones = L.zones_of(st)
    return next((z for z in zones if z['id'] == str(zid)), zones[0])

def show_started(view, zm):
    """Where the engine's clock for this zone is: show time = (now - started) * speed. The engine
    notices state.json changes within 0.5 s, so if it hasn't caught up yet, predict what it will do."""
    speed = zm.speed_of(view)
    try: e = json.loads(L.ENGINE.read_text()).get('zones', {}).get(view['id'], {})
    except Exception: e = {}
    if e.get('show') != view.get('show'):                   # new show: starts from the top on the change
        try: return L.STATE.stat().st_mtime
        except FileNotFoundError: return time.time()
    t0, old = e.get('t0', time.time()), e.get('speed', 1)
    if old != speed:                                       # speed change: same spot, new rate
        now = time.time(); t0 = now - (now - t0) * old / speed
    return t0

def normal_layout(codes, n):
    """A string's bulb layout as one code per real bulb ('on', 'off' or 'join'), as the engine reads it."""
    out, lit = [], False
    for i in range(n):
        c = codes[i] if i < len(codes) and codes[i] in L.LAYOUT_CODES else 'on'
        if c == 'join' and not lit: c = 'on'          # nothing lit before it to join
        out.append(c); lit = lit or c != 'off'
    return out

def save_layout(layouts):
    """Write strings' bulb layouts into config.json (made from the current strings if there isn't one)."""
    try: cfg = json.loads(L.CONFIG.read_text())
    except FileNotFoundError: cfg = {}
    if not cfg.get('strings'): cfg['strings'] = [{'name': n, 'bulbs': b} for n, b in L.PHYSICAL]
    for s in cfg['strings']:
        codes = layouts.get(s['name'])
        if codes is None: continue
        if all(c == 'on' for c in codes): s.pop('layout', None)
        else: s['layout'] = codes
    tmp = L.CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(cfg, indent=2) + '\n'); os.replace(tmp, L.CONFIG)

def scan_state():
    """What the last "Find new lights" scan found (scan.json, written by scan.py; no keys or addresses)."""
    try: sc = json.loads((L.DATA / 'scan.json').read_text())
    except (OSError, ValueError): return {}
    if sc.get('running'):
        try: os.kill(sc.get('pid', 0), 0)
        except (OSError, TypeError): sc = {**sc, 'running': False, 'error': 'The scan stopped before it finished.'}
    if sc.get('devices'):
        strings = dict(L.PHYSICAL)
        sc['devices'] = [{**d, 'in_use': d['name'] in strings} for d in sc['devices']]
    sc.pop('pid', None)
    return sc

def restart_soon():
    """Start this server again with the new config.json once the reply has gone (the engine restarts itself)."""
    import threading
    threading.Timer(0.5, lambda: os.execv(sys.executable, [sys.executable] + sys.argv)).start()

def string_label(name):
    i = L.ORDER.index(name)
    return f'String {chr(65 + i)}' if i < 26 else name

def string_health(names):
    """The real state of the named strings as the engine last saw them, in plain words for the page."""
    try: h = json.loads(L.HEALTH.read_text())
    except Exception: return {'engine': False, 'strings': []}
    if time.time() - h['at'] > 30: return {'engine': False, 'strings': []}
    out = []
    for s in h['strings']:
        if s['name'] not in names: continue
        label, want = string_label(s['name']), s.get('want_on', h.get('want_on'))
        if not s['online'] and not s['down_since']:
            out.append({'label': label, 'level': 'warn', 'text': 'Connecting'}); continue
        if not s['online']:
            since = s['down_since'] and datetime.datetime.fromtimestamp(s['down_since']).strftime('%H:%M')
            out.append({'label': label, 'level': 'bad', 'text': 'Not responding', 'since': since}); continue
        sent, acked = s['sent'], s['acked']
        on = s['switch']
        if want and on is False:
            out.append({'label': label, 'level': 'bad', 'text': 'Off, but should be on'}); continue
        if not want and on is True:
            out.append({'label': label, 'level': 'warn', 'text': 'Still on, turning off'}); continue
        state = 'On' if on else 'Off' if on is False else 'Connected'
        if want and sent >= 10 and acked < 0.8 * sent:
            out.append({'label': label, 'level': 'warn',
                        'text': f'{state}, but only {round(100 * acked / sent)}% of changes are getting through'})
        else:
            out.append({'label': label, 'level': 'ok', 'text': state + (', keeping up' if want and sent >= 10 else '')})
    return {'engine': True, 'strings': out}

def state_payload(zid=None):
    st = L.load_state()
    zone = pick_zone(st, zid)
    view = L.zone_view(st, zone); zm = L.zone_module(zone)
    on, off = L.schedule(view)
    ov = L.override(view)
    shows = []
    known = {k for k, _, _ in SHOW_INFO}
    customs = st.get('customs', {})
    names = st.get('effect_names', {})
    for key, name, desc in (SHOW_INFO + [(k, k, '') for k in zm.SHOWS if k not in known]
                            + [('custom:' + i, 'Custom pattern' if i == 'try' else c.get('name') or 'Custom', '') for i, c in customs.items()]):
        fn = zm.show_fn(key, view)
        if fn is None: continue
        item = {'id': key, 'name': name, 'desc': desc, 'preview': hexes(fn(0)), 'group': GROUP_OF.get(key, ''),
                'speed': zm.speed_of(view, key), 'max_speed': zm.max_speed(key, view),
                'animated': bool(getattr(fn, 'period', 0)),
                'reversed': bool(view.get('reversed', {}).get(key)),
                'reversible': bool(getattr(fn, 'period', 0)) and getattr(fn, 'builtin', None) is None,
                'kind': 'test' if key in TESTS else 'hockey' if key in L.NHL_TEAM else 'moving' if getattr(fn, 'period', 0) else 'still'}
        if key == 'seasonal': item['desc'] = autopilot_desc(); item['kind'] = 'moving'
        if getattr(fn, 'items', None) and not key.startswith('custom:'):           # built-in playlist
            item['playlist'] = fn.items; item['kind'] = 'playlist'
            item['desc'] = custom_desc({'effect': 'playlist', 'items': fn.items}, names)
        if key.startswith('custom:'):
            spec = customs[key[7:]]; item['spec'] = spec
            item['kind'] = 'draft' if key == 'custom:try' else 'playlist' if spec.get('effect') == 'playlist' else 'custom'
            item['desc'] = custom_desc(spec, names)
        if key in LINKS: item['link'] = LINKS[key]
        if zm.TOTAL <= SMALL_ZONE: item['colours'] = show_colours(key, st)
        if key in L.NHL_TEAM: item['team'] = L.NHL_TEAM[key]
        if key in MOVING_OF: item['moving_id'] = MOVING_OF[key]
        if key in VARIANTS: item['kind'] = 'variant'          # reached through its still card's Animate switch
        shows.append(item)
    zstrings = L.zone_strings(zone)
    try: eng = json.loads(L.ENGINE.read_text()).get('zones', {}).get(zone['id'], {})
    except (OSError, ValueError): eng = {}
    game = eng.get('game') if zone.get('follow') else None   # game mode: the engine is playing the team's theme
    shown = game or view.get('show', L.DEFAULT_SHOW)
    if not any(x['id'] == shown for x in shows): shown = L.DEFAULT_SHOW   # a show since removed: the engine plays the default
    return {
        'zone': zone['id'],
        'zones': [{'id': z['id'], 'name': z.get('name') or 'Lights', 'strings': [n for n, _ in L.zone_strings(z)],
                   'direction': 'right' if z.get('direction') == 'right' else 'left',
                   **zone_clock(st, z), 'lit': zone_lit(st, z), 'held': bool(z.get('override')) and L.override(L.zone_view(st, z)) is not None} for z in L.zones_of(st)],
        'all_strings': [{'name': n, 'label': string_label(n), 'bulbs': b} for n, b in L.STRINGS],
        'house': house_of(st),
        'find_secs': FIND_SECS,
        'layout': [{'name': n, 'label': string_label(n), 'bulbs': b,
                    'codes': normal_layout(L.LAYOUTS.get(n, []), b)} for n, b in L.PHYSICAL],
        'show': shown,
        'game_mode': bool(game),
        'lights_name': zone.get('name') or DEFAULT_NAME,
        'shows': shows,
        # on/off: the times of the on-period happening now (else the next one); rule: how they're worked out
        'schedule': {'on': f'{on:%H:%M}', 'off': f'{off:%H:%M}', 'on_date': f'{on:%Y-%m-%d}', 'text': L.schedule_text(view),
                     'rule': {'on_at': view.get('on_at') or L.DEFAULT_ON, 'on_offset': int(view.get('on_offset') or 0),
                              'off_at': view.get('off_at') or L.DEFAULT_OFF, 'off_offset': int(view.get('off_offset') or 0),
                              'off_after': int(view.get('off_after') or 360), 'fade': L.fade_of(view)}},
        'fades': L.FADES,
        'location': ({'lat': L.location_of(st)[0], 'lon': L.location_of(st)[1],
                      'name': (st.get('location') or {}).get('name') or 'your location'} if L.location_of(st) else None),
        'mode': 'auto' if ov is None else ('on' if ov else 'off'),
        'override_until': (datetime.datetime.fromtimestamp(zone['override']['until']).strftime('%H:%M')
                           if ov is not None else None),
        'lit': bool(zstrings) and (bool(game and zone.get('game_power', True) and ov is not False)
                                   or (L.is_on_hours(view) if ov is None else ov)),
        'started': eng.get('game_t0') if game else show_started(view, zm),
        'speeds': [s for s in L.SPEEDS],
        'brightness': L.brightness_of(view),
        'follow': zone.get('follow') if zone.get('follow') in L.NHL_TEAM else None,
        'game_power': zone.get('game_power', True),
        'teams': [{'id': k, 'name': n} for k, n, _ in SHOW_INFO if k in L.NHL_TEAM],
        'goal_delay': int(zone.get('goal_delay') or 0),
        'scan': scan_state(),
        'hockey': hockey_status(zone.get('follow')),
        'brightnesses': list(L.BRIGHTNESS),
        'strings': [{'label': string_label(n), 'name': n, 'bulbs': b} for n, b in zstrings],
        'total': zm.TOTAL if zstrings else 0,
        'playable': [{'id': k, 'name': n} for k, n, _ in SHOW_INFO if k in zm.SHOWS and k not in NOT_IN_PLAYLISTS]
                    + [{'id': 'custom:' + i, 'name': c.get('name')} for i, c in customs.items()
                       if i != 'try' and c.get('effect') not in ('builtin', 'playlist')],
        'effects': [{'mode': m, 'name': names.get(str(m), '')} for m in L.EFFECT_MODES],
        'health': string_health([n for n, _ in zstrings]),
        'now': time.time(),
    }

TRANSITION_WORDS = {'chase': 'chases in', 'fade': 'fades in', 'cut': 'switches'}
def secs(v): return f'{v // 60:g} min' if v >= 60 and v % 60 == 0 else (f'{v / 60:g} min' if v >= 60 else f'{v:g} s')
EFFECT_WORDS = {'still': 'Still', 'chase': 'Chases along', 'converge': 'Flows toward the join'}
def custom_desc(spec, names):
    if spec['effect'] == 'playlist':
        titles = dict((k, n) for k, n, _ in SHOW_INFO)
        st = L.load_state()
        def title(k): return titles.get(k) or st.get('customs', {}).get(k[7:], {}).get('name') or k
        parts = [f"{title(it['show'])} {secs(it['hold'])}" for it in spec['items']]
        how = {it['transition'] for it in spec['items']}
        joins = {frozenset({'chase'}): 'chasing in', frozenset({'fade'}): 'fading',
                 frozenset({'cut'}): 'quick changes'}.get(frozenset(how), 'mixed transitions')
        mins = round(sum(it['hold'] for it in spec['items']) / 60) or 1
        return f'Playlist, {joins}: ' + ', '.join(parts) + f'. About {mins} min round.'
    n = len(spec['colours']); w = spec.get('width', 1)
    what = f"{n} colour{'s' * (n != 1)}" + (f", {w} bulbs each" if w > 1 else '')
    if spec['effect'] == 'builtin':
        m = spec.get('mode', 0); label = f'effect {m}' + (f' ({names[str(m)]})' if names.get(str(m)) else '')
        return f"{what}. Built-in {label}, speed {spec.get('speed', 50)}, run by the controllers."
    return f"{what}. {EFFECT_WORDS[spec['effect']]}."

HEX = re.compile(r'^#[0-9a-fA-F]{6}$')
HOLDS = {15, 30, 60, 120, 300, 600, 900, 1800}
def clean_custom(body, st):
    """Validate a custom show from the page; returns (spec, error)."""
    name = str(body.get('name') or '').strip()[:40]
    if body.get('effect') == 'playlist':
        items = body.get('items')
        if not isinstance(items, list) or not 1 <= len(items) <= 20: return None, 'Add between 1 and 20 themes.'
        ok_shows = {k for k in L.SHOWS if k not in NOT_IN_PLAYLISTS} | {
            'custom:' + i for i, c in st.get('customs', {}).items() if i != 'try' and c.get('effect') not in ('builtin', 'playlist')}
        out = []
        for it in items:
            if not isinstance(it, dict) or it.get('show') not in ok_shows: return None, 'Pick a theme for every step.'
            if it.get('hold') not in HOLDS: return None, 'Pick how long each theme shows.'
            if it.get('transition') not in L.TRANSITION_SECS: return None, 'Pick a transition for every step.'
            out.append({'show': it['show'], 'hold': it['hold'], 'transition': it['transition']})
        return {'name': name, 'effect': 'playlist', 'items': out}, None
    cols = body.get('colours')
    if not isinstance(cols, list) or not 1 <= len(cols) <= 8 or not all(isinstance(c, str) and HEX.match(c) for c in cols):
        return None, 'Pick between 1 and 8 colours.'
    eff = body.get('effect')
    if eff not in ('still', 'chase', 'converge', 'builtin'): return None, 'Pick an effect.'
    width, mode, speed = body.get('width', 1), body.get('mode', 0), body.get('speed', 50)
    if not (isinstance(width, int) and 1 <= width <= 6): return None, 'Bulbs per colour must be 1 to 6.'
    if not (isinstance(mode, int) and mode in L.EFFECT_MODES): return None, 'Unknown built-in effect.'
    if not (isinstance(speed, int) and 1 <= speed <= 100): return None, 'Effect speed must be 1 to 100.'
    return {'name': name, 'colours': [c.lower() for c in cols], 'width': width, 'effect': eff,
            'mode': mode, 'speed': speed}, None

def valid_time(v):
    try: datetime.datetime.strptime(v, '%H:%M'); return True
    except Exception: return False

# ---- Login for access from outside the home network (such as a Cloudflare tunnel) --------------------------
# Requests from the home network (private addresses) need no login, as before. Anything else, including a
# tunnel, which reaches this server from the Pi itself (127.0.0.1) or carries Cloudflare's headers, must log in
# with HTTP basic auth against auth.json in the data folder (set with: python3 web.py --set-password <user>).
# With no auth.json, outside requests are refused outright, so a tunnel can never expose the page by accident.
import base64 as _b64, hashlib, hmac, ipaddress, secrets
AUTH = L.DATA / 'auth.json'
_fails = {}                                   # outside address -> [failure times], to slow down guessing
def from_home(handler):
    """True for a request straight from the home network: a private address, and no proxy or tunnel headers."""
    if any(h in handler.headers for h in ('Cf-Connecting-Ip', 'X-Forwarded-For', 'Cf-Ray', 'Forwarded')): return False
    try: ip = ipaddress.ip_address(handler.client_address[0])
    except ValueError: return False
    return ip.is_private and not ip.is_loopback
def hash_password(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), 200_000).hex()
def check_login(header):
    try: auth = json.loads(AUTH.read_text())
    except (OSError, ValueError): return None            # no password set: outside access is off
    if not header or not header.startswith('Basic '): return False
    try: user, _, pw = _b64.b64decode(header[6:]).decode().partition(':')
    except Exception: return False
    ok_user = hmac.compare_digest(user.encode(), auth['user'].encode())
    ok_pw = hmac.compare_digest(hash_password(pw, auth['salt']), auth['hash'])
    return ok_user and ok_pw

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *a): pass
    def gate(self):
        """None if the request may go ahead, else the refusal has been sent."""
        if from_home(self): return None
        who = self.headers.get('Cf-Connecting-Ip') or self.client_address[0]
        now = time.time(); recent = [t for t in _fails.get(who, []) if now - t < 600]
        if len(recent) >= 8:
            return self.send(429, {'error': 'Too many wrong passwords. Try again in 10 minutes.'}) or True
        ok = check_login(self.headers.get('Authorization'))
        if ok is None: return self.send(403, {'error': 'Outside access is off: set a password on the Pi first.'}) or True
        if ok: _fails.pop(who, None); return None
        _fails[who] = recent + [now]
        body = b'Log in to String Theory.'
        self.send_response(401); self.send_header('WWW-Authenticate', 'Basic realm="String Theory", charset="UTF-8"')
        self.send_header('Content-Type', 'text/plain'); self.send_header('Content-Length', str(len(body))); self.end_headers()
        self.wfile.write(body); return True

    def send(self, code, body, ctype='application/json', cache=False):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        if len(data) > 2000 and 'gzip' in self.headers.get('Accept-Encoding', ''):
            data = gzip.compress(data, 5); self.send_header('Content-Encoding', 'gzip')
        self.send_header('Content-Type', ctype)
        # The font and icons never change between updates: let browsers keep them (no flash of another font).
        self.send_header('Cache-Control', 'public, max-age=86400' if cache else 'no-store')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        if self.gate(): return
        url = urlsplit(self.path); path = url.path; zid = parse_qs(url.query).get('zone', [None])[0]
        if path in ('/', '/index.html'):
            return self.send(200, PAGE.read_bytes(), 'text/html; charset=utf-8')
        if path in STATIC:
            f, ctype = STATIC[path]
            return self.send(200, (PAGE.parent / f).read_bytes(), ctype, cache=f != 'manifest.webmanifest')
        if path in ('/help', '/help.html'):
            return self.send(200, HELP.read_bytes(), 'text/html; charset=utf-8')
        if path == '/api/state':
            return self.send(200, state_payload(zid))
        if path == '/api/previews':
            st = L.load_state(); zone = pick_zone(st, zid); zm = L.zone_module(zone)
            keys = list(zm.SHOWS) + ['custom:' + i for i in st.get('customs', {})]
            only = parse_qs(url.query).get('show', [None])[0]
            if only in keys:                     # just one show (and a playlist's themes): the house picture
                tl = timeline(only, st, zm)
                keys = [only] + [it['show'] for it in tl.get('items', [])]
            return self.send(200, {k: timeline(k, st, zm) for k in keys})
        self.send(404, {'error': 'Not found'})

    def do_POST(self):
        if self.gate(): return
        if not self.headers.get('Content-Type', '').startswith('application/json'):
            return self.send(415, {'error': 'Send JSON.'})
        try:
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0)) or 0) or b'{}')
        except Exception:
            return self.send(400, {'error': 'That request was not valid JSON.'})
        st = L.load_state()
        zones = L.materialise_zones(st)
        zone = pick_zone(st, body.get('zone'))
        view = L.zone_view(st, zone); zm = L.zone_module(zone)
        path = urlsplit(self.path).path
        if path == '/api/show':
            if zm.show_fn(body.get('show'), view) is None: return self.send(400, {'error': 'Unknown show.'})
            zone['show'] = body['show']
            hs = hockey_status(zone.get('follow'))       # picked mid-game: the game hands the lights back until the next one
            if hs and hs.get('active') and body['show'] != zone['follow'] + 'move': zone['skip_game'] = hs['active']
        elif path == '/api/power':
            mode = body.get('mode')
            if mode == 'auto':
                zone.pop('override', None)
            elif mode in ('on', 'off'):
                # Hold until the schedule would agree again, then hand back to it:
                #  On  during on-hours  -> on until tonight's off time (same as the schedule)
                #  On  outside on-hours -> on until the next scheduled on, when the schedule takes over
                #  Off during on-hours  -> off for the rest of tonight
                #  Off outside on-hours -> skip the next evening entirely
                cur, nxt = L.current_window(view), L.next_window(view)
                until = cur[1] if cur else nxt[0] if mode == 'on' else nxt[1]
                zone['override'] = {'power': mode == 'on', 'until': until.timestamp()}
            else:
                return self.send(400, {'error': 'Mode must be on, off or auto.'})
        elif path == '/api/speed':
            key, speed = body.get('show'), body.get('speed')
            if not getattr(zm.show_fn(key, view), 'period', 0):
                return self.send(400, {'error': "That show doesn't move, so it has no speed."})
            if speed not in L.SPEEDS or speed > zm.max_speed(key, view):
                return self.send(400, {'error': f'Pick a speed from {L.SPEEDS[0]}x to {zm.max_speed(key, view)}x.'})
            zone.setdefault('speeds', {})[key] = speed
        elif path == '/api/follow':
            # Follow a team (its theme key, e.g. 'leafs') or stop (null). game_power: lights on for its games.
            key = body.get('team')
            if key is not None and key not in L.NHL_TEAM: return self.send(400, {'error': 'Pick one of the hockey teams.'})
            if key: zone['follow'] = key
            else: zone.pop('follow', None)
            if isinstance(body.get('game_power'), bool): zone['game_power'] = body['game_power']
            zone.pop('skip_game', None)
        elif path == '/api/goal-delay':
            v = body.get('seconds')
            if not (isinstance(v, int) and 0 <= v <= 120): return self.send(400, {'error': 'Pick a delay of 0 to 120 seconds.'})
            zone['goal_delay'] = v
        elif path == '/api/celebrate':
            if not (zone.get('follow') or str(zone.get('show', '')).removesuffix('move') in L.NHL_TEAM):
                return self.send(400, {'error': 'Play a hockey theme, or follow a team, to test the celebration.'})
            zone['celebrate'] = time.time()
        elif path == '/api/direction':                  # which end of the zone its first bulb is at, from the street
            d = body.get('direction')
            if d not in ('left', 'right'): return self.send(400, {'error': 'Direction must be left or right.'})
            if d == 'right': zone['direction'] = 'right'
            else: zone.pop('direction', None)
        elif path == '/api/reverse':
            key, fn = body.get('show'), zm.show_fn(body.get('show'), view)
            if not getattr(fn, 'period', 0) or getattr(fn, 'builtin', None) is not None:
                return self.send(400, {'error': "That show doesn't move, so it has no direction."})
            rev = zone.setdefault('reversed', {})
            if body.get('reversed'): rev[key] = True
            else: rev.pop(key, None)
        elif path == '/api/brightness':
            b = body.get('brightness')
            if b not in L.BRIGHTNESS:
                return self.send(400, {'error': 'Pick a brightness from the list.'})
            zone['brightness'] = b
        elif path == '/api/custom':
            # Save a custom show (shared by every zone). id 'try' is the editor's scratch slot.
            spec, err = clean_custom(body, st)
            if err: return self.send(400, {'error': err})
            customs = st.setdefault('customs', {})
            cid = str(body.get('id') or '')
            if cid != 'try':
                if not spec['name']: return self.send(400, {'error': 'Give the show a name.'})
                if cid not in customs: cid = str(max([int(k) for k in customs if k.isdigit()] + [0]) + 1)
            customs[cid] = spec
            if body.get('play') or zone.get('show') == 'custom:' + cid: zone['show'] = 'custom:' + cid
        elif path == '/api/custom/delete':
            cid = str(body.get('id') or '')
            if cid not in st.get('customs', {}): return self.send(400, {'error': 'No such custom show.'})
            used = [c.get('name') for c in st['customs'].values()
                    if c.get('effect') == 'playlist' and any(it['show'] == 'custom:' + cid for it in c['items'])]
            if used: return self.send(400, {'error': f"It's used in {', '.join(used)}. Remove it from there first."})
            del st['customs'][cid]
            for z in zones:
                if z.get('show') == 'custom:' + cid: z['show'] = 'classic'
        elif path == '/api/name':
            name = str(body.get('name') or '').strip()
            if not 1 <= len(name) <= 40: return self.send(400, {'error': 'Use a name of 1 to 40 characters.'})
            zone['name'] = name
        elif path == '/api/zones/add':
            name = str(body.get('name') or '').strip()
            if not 1 <= len(name) <= 40: return self.send(400, {'error': 'Use a name of 1 to 40 characters.'})
            if len(zones) >= 12: return self.send(400, {'error': "That's plenty of zones."})
            nid = str(max([int(z['id']) for z in zones if z['id'].isdigit()] + [0]) + 1)
            zones.append({'id': nid, 'name': name, 'strings': [], 'show': 'classic',
                          **{k: zone[k] for k in ('on_at', 'off_at', 'on_offset', 'off_offset', 'off_after') if k in zone}})
            L.save_state(st)
            return self.send(200, state_payload(nid))
        elif path == '/api/zones/delete':
            if len(zones) == 1: return self.send(400, {'error': "You can't delete the only zone."})
            zones.remove(zone)
            zones[0]['strings'] = [n for n in L.ORDER if n in zones[0]['strings'] + zone.get('strings', [])]
            L.save_state(st)
            return self.send(200, state_payload(zones[0]['id']))
        elif path == '/api/zones/assign':
            # Move a string into this zone (out of whichever zone had it).
            name = body.get('string')
            if name not in L.ORDER: return self.send(400, {'error': 'Unknown string.'})
            for z in zones: z['strings'] = [n for n in z.get('strings', []) if n != name]
            zone['strings'] = [n for n in L.ORDER if n in zone['strings'] + [name]]
        elif path == '/api/effect-name':
            mode, name = body.get('mode'), str(body.get('name') or '').strip()[:30]
            if mode not in L.EFFECT_MODES: return self.send(400, {'error': 'Unknown built-in effect.'})
            names = st.setdefault('effect_names', {})
            if name: names[str(mode)] = name
            else: names.pop(str(mode), None)
        elif path == '/api/schedule':
            # on: 'HH:MM' | 'sunset' | 'sunrise' (+ on_offset min); off: 'HH:MM' | 'sunrise' | 'sunset' (+ off_offset)
            # | 'after' (+ off_after min)
            on, off = body.get('on'), body.get('off')
            on_off, off_off, after = body.get('on_offset', 0), body.get('off_offset', 0), body.get('off_after', 360)
            sun = L.SUN_EVENTS
            if not (valid_time(on) or on in sun) or not (valid_time(off) or off in sun or off == 'after'):
                return self.send(400, {'error': 'Pick a time, sunset or sunrise.'})
            if not all(isinstance(v, int) and -180 <= v <= 180 for v in (on_off, off_off)):
                return self.send(400, {'error': 'Offsets must be within 3 hours of the sun.'})
            if off == 'after' and not (isinstance(after, int) and 15 <= after <= 23 * 60):
                return self.send(400, {'error': 'Pick how long to stay on, up to 23 hours.'})
            if (on in sun or off in sun) and not L.location_of(st):
                return self.send(400, {'error': 'Set your location first, so String Theory can work out sunset.'})
            if on == off and on not in sun:
                return self.send(400, {'error': 'On and off times need to be different.'})
            fade = body.get('fade', zone.get('fade', 0))
            if fade not in L.FADES: return self.send(400, {'error': 'Pick a fade time from the list.'})
            zone['fade'] = fade
            zone.update(on_at=on, on_offset=on_off if on in sun else 0, off_at=off,
                        off_offset=off_off if off in sun else 0, off_after=after if off == 'after' else zone.get('off_after', 360))
        elif path == '/api/layout':                     # {layouts: {string name: [code per real bulb]}}
            layouts, phys = body.get('layouts'), dict(L.PHYSICAL)
            if not isinstance(layouts, dict) or not layouts: return self.send(400, {'error': 'Nothing to save.'})
            clean = {}
            for name, codes in layouts.items():
                n = phys.get(name)
                if n is None: return self.send(400, {'error': f'Unknown string {name}.'})
                if not isinstance(codes, list) or len(codes) != n or any(c not in L.LAYOUT_CODES for c in codes):
                    return self.send(400, {'error': f'Send one of on, off or join for each of the {n} bulbs.'})
                clean[name] = normal_layout(codes, n)
                if all(c == 'off' for c in clean[name]):
                    return self.send(400, {'error': f'Leave at least one bulb on in {string_label(name)}.'})
            save_layout(clean)
            st.pop('locate', None); L.save_state(st)
            self.send(200, {'restarting': True}); restart_soon(); return
        elif path == '/api/house':                      # {string, row, place, with, flip, spots}: where one string hangs
            name = body.get('string'); cur = house_of(st).get(name)
            if cur is None: return self.send(400, {'error': 'Unknown string.'})
            p = {**cur, **{k: body[k] for k in ('row', 'place', 'with', 'flip', 'spots') if k in body}}
            if p['place'] == 'between' and (p.get('with') == name or p.get('with') not in dict(L.STRINGS)):
                return self.send(400, {'error': 'Pick another string for it to sit between.'})
            st.setdefault('house', {}).setdefault('strings', {})[name] = {k: p.get(k) for k in ('row', 'place', 'with', 'flip', 'spots')}
            st['house']['strings'][name] = house_of(st)[name]
        elif path == '/api/scan':                       # "Find new lights": scan.py runs in the background
            sc = scan_state()
            if sc.get('running'): return self.send(400, {'error': 'Already looking.'})
            import subprocess
            subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent / 'scan.py')],
                             env={**os.environ, 'STRINGTHEORY_DATA': str(L.DATA)}, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            time.sleep(0.3)
        elif path == '/api/strings/add':                # add a found device as a string, after the others
            name, bulbs = body.get('name'), body.get('bulbs')
            try: known = {d.get('name') for d in json.loads(L.DEVICES.read_text())}
            except (OSError, ValueError): known = set()
            if name not in known: return self.send(400, {'error': 'Find it with Find new lights first.'})
            if name in dict(L.PHYSICAL): return self.send(400, {'error': 'That one is already a string.'})
            if not (isinstance(bulbs, int) and 1 <= bulbs <= 1000): return self.send(400, {'error': 'Bulbs must be 1 to 1000.'})
            try: cfg = json.loads(L.CONFIG.read_text())
            except FileNotFoundError: cfg = {}
            if not cfg.get('strings'): cfg['strings'] = [{'name': n, 'bulbs': b} for n, b in L.PHYSICAL]
            cfg['strings'].append({'name': name, 'bulbs': bulbs})
            tmp = L.CONFIG.with_suffix('.tmp'); tmp.write_text(json.dumps(cfg, indent=2) + '\n'); os.replace(tmp, L.CONFIG)
            self.send(200, {'restarting': True}); restart_soon(); return
        elif path == '/api/locate':
            name, n, bulb = body.get('string'), dict(L.PHYSICAL).get(body.get('string')), body.get('bulb')
            if bulb is None: st.pop('locate', None)
            elif n is None or not isinstance(bulb, int) or not 0 <= bulb < n:
                return self.send(400, {'error': 'Unknown bulb.'})
            else: st['locate'] = {'string': name, 'bulb': bulb, 'until': time.time() + FIND_SECS}
        elif path == '/api/location':
            # Shared by every zone. Either coordinates (from the device, or typed in), rounded to about 1 km, or a
            # time zone such as 'America/Toronto', placed at that zone's main city (good to a few minutes of sunset).
            if body.get('lat') is None:
                tz = str(body.get('timezone') or local_timezone() or '')
                if tz not in TZ_COORDS: return self.send(400, {'error': "Couldn't work out where you are. Enter coordinates instead."})
                lat, lon = TZ_COORDS[tz]
                city = tz.split('/')[-1].replace('_', ' ').replace('St Johns', "St. John's").replace('St ', 'St. ')
                name = f'the {city} area'
            else:
                try: lat, lon = round(float(body.get('lat')), 2), round(float(body.get('lon')), 2)
                except (TypeError, ValueError): return self.send(400, {'error': 'Enter latitude and longitude as numbers.'})
                if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                    return self.send(400, {'error': 'Latitude is -90 to 90 and longitude -180 to 180.'})
                name = str(body.get('name') or 'the coordinates you entered')[:40]
            st['location'] = {'lat': lat, 'lon': lon, 'name': name}
        else:
            return self.send(404, {'error': 'Not found'})
        L.save_state(st)
        self.send(200, state_payload(zone['id']))

def warm_previews():
    """Build each zone's previews in the background (a few seconds on the Pi), so the first visit is quick."""
    try:
        st = L.load_state()
        for z in L.zones_of(st):
            zm = L.zone_module(z)
            for k in zm.SHOWS:
                if k != 'seasonal': timeline(k, st, zm)
    except Exception as e: print('previews:', e, flush=True)

CODE = [Path(__file__).resolve(), Path(L.__file__).resolve()]
def watch_code():
    """When web.py or lights.py changes (a new show, say), start this server again with it, so adding a show
    needs no restart. The new code is checked first in a separate process; if it won't load, keep running."""
    import subprocess, threading
    def mtimes(): return [p.stat().st_mtime if p.exists() else None for p in CODE]
    seen = mtimes()
    def loop():
        nonlocal seen
        while True:
            time.sleep(2)
            now = mtimes()
            if now == seen: continue
            time.sleep(1); seen = mtimes()                 # let a copy finish landing
            r = subprocess.run([sys.executable, str(CODE[0]), '--check'], capture_output=True, text=True, timeout=120)
            if r.returncode == 0:
                print('code changed, restarting the page server', flush=True)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            print('code changed but has an error, keeping the old version:', (r.stderr or r.stdout).strip()[-500:], flush=True)
    threading.Thread(target=loop, daemon=True, name='watch-code').start()

if __name__ == '__main__':
    if '--set-password' in sys.argv:       # python3 web.py --set-password <user>: the login for outside access
        import getpass
        i = sys.argv.index('--set-password'); user = sys.argv[i + 1] if len(sys.argv) > i + 1 else input('User name: ').strip()
        pw = getpass.getpass('Password (12 characters or more): ')
        if len(pw) < 12: sys.exit('Use at least 12 characters.')
        if pw != getpass.getpass('Again: '): sys.exit("They didn't match.")
        salt = secrets.token_hex(16)
        fd = os.open(AUTH.with_suffix('.tmp'), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f: json.dump({'user': user, 'salt': salt, 'hash': hash_password(pw, salt)}, f)
        os.replace(AUTH.with_suffix('.tmp'), AUTH); print(f'Saved. Outside access now asks for {user} and that password.'); sys.exit(0)
    if '--check' in sys.argv:              # used by watch_code(): getting here means web.py and lights.py load
        L.zone_module({'strings': L.ORDER}); sys.exit(0)
    import threading
    threading.Thread(target=warm_previews, daemon=True, name='previews').start()
    watch_code()
    print(f'lights web on :{PORT}', flush=True)
    ThreadingHTTPServer(('0.0.0.0', PORT), Handler).serve_forever()
