// String Theory demo: a pretend Pi that runs in the browser.
//
// The demo page is the real control app. This script answers its /api/... requests itself, from a
// snapshot of a real install (data.json, built by tools/build_site.py) plus whatever the visitor
// changes, saved in this browser only. No lights, no network, nothing leaves the page.
(() => {
  const realFetch = window.fetch.bind(window);
  const BASE = document.currentScript.src;            // only set while this script first runs
  const data = realFetch(new URL('data.json', BASE)).then(r => r.json());
  const KEY = 'stringtheory-demo';
  const TSTEP = 0.4, CHASE_STEP = 0.6;
  const SPEEDS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3];
  const now = () => Date.now() / 1000;

  // Saved in this browser when allowed; some browsers block storage in embedded frames, so carry on without it.
  const store = (() => { try { localStorage.setItem(KEY + '-test', '1'); return localStorage; } catch { return null; } })();
  let st = store ? JSON.parse(store.getItem(KEY) || 'null') : null;
  if (st && st.name === 'Porch lights') st.name = 'Home Lights';   // the demo's old default name
  const save = () => { if (store) store.setItem(KEY, JSON.stringify(st)); };

  function fresh(D) {
    return {show: D.state.show, mode: 'on', speeds: {}, rule: {...D.state.schedule.rule}, location: null,
            name: D.state.lights_name, customs: {}, effectNames: {}, started: now()};
  }

  // ---- custom shows, built here the way lights.py builds them ----
  const hex = c => c.replace('#', '').toLowerCase();
  function pattern(spec) { return spec.colours.flatMap(c => Array(spec.width || 1).fill(hex(c))); }
  function frame(spec, total, t) {
    const pat = pattern(spec), L = pat.length;
    const off = spec.effect === 'chase' || spec.effect === 'converge' ? Math.floor(t / CHASE_STEP) : 0;
    const at = p => pat[(((p - off) % L) + L) % L];
    if (spec.effect === 'converge') {
      const left = Array.from({length: Math.floor(total / 2)}, (_, p) => at(p));
      return left.concat(left.slice().reverse(), total % 2 ? [left[left.length - 1]] : []);
    }
    return Array.from({length: total}, (_, p) => at(p));
  }
  function timeline(spec, total) {
    if (spec.effect === 'playlist') {
      const items = spec.items.map(it => ({...it, tdur: it.transition === 'chase' ? total * TSTEP : it.transition === 'fade' ? 4 : 0}));
      return {period: items.reduce((a, it) => a + it.hold + it.tdur, 0), tstep: TSTEP, items};
    }
    if (spec.effect === 'chase' || spec.effect === 'converge') {
      const n = pattern(spec).length;
      return {period: n * CHASE_STEP, frames: Array.from({length: n}, (_, k) => [+(k * CHASE_STEP).toFixed(2), frame(spec, total, k * CHASE_STEP).join('')])};
    }
    return {period: 0, frames: [[0, frame(spec, total, 0).join('')]]};
  }
  const WORDS = {still: 'Still', chase: 'Chases along', converge: 'Flows toward the join'};
  function describe(spec, D) {
    if (spec.effect === 'playlist') {
      const title = k => D.state.shows.find(x => x.id === k)?.name || st.customs[k.slice(7)]?.name || k;
      const secs = v => v >= 60 ? `${v / 60} min` : `${v} s`;
      return 'Playlist: ' + spec.items.map(it => `${title(it.show)} ${secs(it.hold)}`).join(', ') + '.';
    }
    const n = spec.colours.length, w = spec.width || 1;
    const what = `${n} colour${n === 1 ? '' : 's'}` + (w > 1 ? `, ${w} bulbs each` : '');
    if (spec.effect === 'builtin') {
      const nm = st.effectNames[spec.mode];
      return `${what}. Built-in effect ${spec.mode}${nm ? ` (${nm})` : ''}, run by the controllers. (The demo can only show its colours.)`;
    }
    return `${what}. ${WORDS[spec.effect]}.`;
  }
  function customItem(id, spec, D) {
    const moving = spec.effect === 'chase' || spec.effect === 'converge' || spec.effect === 'playlist';
    const max = spec.effect === 'playlist' ? 1 : moving ? 1.5 : 1;
    return {id: 'custom:' + id, name: id === 'try' ? 'Custom pattern' : spec.name, desc: describe(spec, D), group: '',
            preview: spec.effect === 'playlist' ? D.state.shows[0].preview : frame(spec, D.state.total, 0).map(c => '#' + c),
            speed: Math.min(st.speeds['custom:' + id] || 1, max), max_speed: max, animated: moving, spec,
            kind: id === 'try' ? 'draft' : spec.effect === 'playlist' ? 'playlist' : 'custom'};
  }

  // ---- schedule (the same rules and sun formula as lights.py, in this browser's local time) ----
  const SUN = ['sunset', 'sunrise'], DAY = 86400e3;
  function sunTime(day, lat, lon, rising) {             // NOAA / Almanac for Computers, good to about a minute
    const r = Math.PI / 180, n = Math.round((day - new Date(day.getFullYear(), 0, 0)) / DAY), lng = lon / 15;
    const t = n + ((rising ? 6 : 18) - lng) / 24, m = 0.9856 * t - 3.289;
    const L = ((m + 1.916 * Math.sin(m * r) + 0.020 * Math.sin(2 * m * r) + 282.634) % 360 + 360) % 360;
    let ra = ((Math.atan(0.91764 * Math.tan(L * r)) / r) % 360 + 360) % 360;
    ra = (ra + Math.floor(L / 90) * 90 - Math.floor(ra / 90) * 90) / 15;
    const sinDec = 0.39782 * Math.sin(L * r), cosDec = Math.cos(Math.asin(sinDec));
    const cosH = (Math.cos(90.833 * r) - sinDec * Math.sin(lat * r)) / (cosDec * Math.cos(lat * r));
    if (cosH < -1 || cosH > 1) return null;
    const h = (rising ? 360 - Math.acos(cosH) / r : Math.acos(cosH) / r) / 15;
    const ut = ((h + ra - 0.06571 * t - 6.622 - lng) % 24 + 24) % 24;
    let d = new Date(Date.UTC(day.getFullYear(), day.getMonth(), day.getDate()) + ut * 3600e3);
    while (d.toDateString() !== day.toDateString()) d = new Date(d.getTime() + (d < day ? DAY : -DAY));
    return new Date(Math.round(d / 60e3) * 60e3);
  }
  function at(spec, offset, day, dflt) {
    if (SUN.includes(spec) && st.location) {
      const t = sunTime(day, st.location.lat, st.location.lon, spec === 'sunrise');
      if (t) return new Date(t.getTime() + (offset || 0) * 60e3);
    }
    const [h, m] = (/^\d\d:\d\d$/.test(spec) ? spec : dflt).split(':').map(Number);
    return new Date(day.getFullYear(), day.getMonth(), day.getDate(), h, m);
  }
  function dayWindow(day) {
    const r = st.rule, start = at(r.on_at, r.on_offset, day, '16:00');
    if (r.off_at === 'after') return [start, new Date(start.getTime() + (r.off_after || 360) * 60e3)];
    let end = at(r.off_at, r.off_offset, day, '00:00');
    while (end <= start) end = new Date(end.getTime() + DAY);
    return [start, end];
  }
  const today = (k = 0) => { const d = new Date(); return new Date(d.getFullYear(), d.getMonth(), d.getDate() + k); };
  function currentWindow() { const t = new Date(); for (const k of [-1, 0]) { const w = dayWindow(today(k)); if (w[0] <= t && t < w[1]) return w; } return null; }
  function nextWindow() { const t = new Date(); for (const k of [0, 1, 2]) { const w = dayWindow(today(k)); if (w[0] > t) return w; } return dayWindow(today(1)); }
  const hm = d => `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  function ruleText() {
    const r = st.rule;
    const when = (spec, off) => {
      if (!SUN.includes(spec)) return `at ${spec}`;
      if (!off) return `at ${spec}`;
      const m = Math.abs(off), amt = m >= 60 ? (m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} h`) : `${m} min`;
      return `${amt} ${off < 0 ? 'before' : 'after'} ${spec}`;
    };
    const f = r.fade || 0, fades = !f ? '' : f >= 60 ? `, fading over ${f / 60} min` : `, fading over ${f} s`;
    if (r.off_at === 'after') { const h = (r.off_after || 360) / 60; return `On ${when(r.on_at, r.on_offset)}, for ${h} hour${h === 1 ? '' : 's'}${fades}`; }
    return `On ${when(r.on_at, r.on_offset)}, off ${when(r.off_at, r.off_offset)}${fades}`;
  }

  function payload(D) {
    const p = JSON.parse(JSON.stringify(D.state));
    if (!st.rule) st.rule = {on_at: st.on || '16:00', on_offset: 0, off_at: st.off || '00:00', off_offset: 0, off_after: 360};
    const cur = currentWindow(), nxt = nextWindow(), win = cur || nxt;
    const lit = st.mode === 'auto' ? !!cur : st.mode === 'on';
    p.brightness = p.brightnesses.includes(st.brightness) ? st.brightness : 1;
    p.shows = p.shows.map(x => ({...x, speed: Math.min(st.speeds[x.id] || 1, x.max_speed)}))
      .concat(Object.entries(st.customs).map(([id, spec]) => customItem(id, spec, D)));
    p.show = p.shows.some(x => x.id === st.show) ? st.show : D.state.show;
    p.lights_name = st.name; p.zones = [{...p.zones[0], name: st.name}];
    p.schedule = {on: hm(win[0]), off: hm(win[1]), text: ruleText(), rule: {...st.rule}};
    p.location = st.location;
    p.mode = st.mode; p.lit = lit;
    p.override_until = st.mode === 'auto' ? null : hm(cur ? cur[1] : st.mode === 'on' ? nxt[0] : nxt[1]);
    p.playable = D.state.playable.concat(Object.entries(st.customs)
      .filter(([id, c]) => id !== 'try' && c.effect !== 'builtin' && c.effect !== 'playlist')
      .map(([id, c]) => ({id: 'custom:' + id, name: c.name})));
    p.effects = p.effects.map(e => ({...e, name: st.effectNames[e.mode] || ''}));
    p.health = {engine: true, strings: p.strings.map(s => ({label: s.label, level: 'ok',
      text: lit ? 'On (pretend lights in this demo)' : 'Off (pretend lights in this demo)'}))};
    p.started = st.started; p.now = now();
    return p;
  }

  function ok(body) { return new Response(JSON.stringify(body), {status: 200, headers: {'Content-Type': 'application/json'}}); }
  function no(error) { return new Response(JSON.stringify({error}), {status: 400, headers: {'Content-Type': 'application/json'}}); }
  const HEX = /^#[0-9a-fA-F]{6}$/;

  async function handle(path, body, D) {
    if (path === '/api/state') return ok(payload(D));
    if (path === '/api/previews') {
      const out = {...D.previews};
      for (const [id, spec] of Object.entries(st.customs)) out['custom:' + id] = timeline(spec, D.state.total);
      return ok(out);
    }
    if (!body) return no('Not found');
    switch (path) {
      case '/api/show':
        if (!payload(D).shows.some(x => x.id === body.show)) return no('Unknown show.');
        st.show = body.show; st.started = now(); break;
      case '/api/power':
        if (!['on', 'off', 'auto'].includes(body.mode)) return no('Mode must be on, off or auto.');
        st.mode = body.mode; break;
      case '/api/follow': case '/api/goal-delay': case '/api/celebrate':
        return no('Following games needs your own String Theory at home: it watches the NHL\'s live scores and lights up for goals.');
      case '/api/brightness':
        if (!D.state.brightnesses.includes(body.brightness)) return no('Pick a brightness from the list.');
        st.brightness = body.brightness; break;
      case '/api/speed': {
        if (!SPEEDS.includes(body.speed)) return no('Pick a speed from the list.');
        const old = st.speeds[body.show] || 1, t = now();
        if (body.show === st.show) st.started = t - (t - st.started) * old / body.speed;   // keep its place
        st.speeds[body.show] = body.speed; break;
      }
      case '/api/schedule': {
        const time = v => /^\d\d:\d\d$/.test(v || ''), {on, off} = body;
        if (!(time(on) || SUN.includes(on)) || !(time(off) || SUN.includes(off) || off === 'after')) return no('Pick a time, sunset or sunrise.');
        if ((SUN.includes(on) || SUN.includes(off)) && !st.location) return no('Set your location first, so String Theory can work out sunset.');
        if (on === off && !SUN.includes(on)) return no('On and off times need to be different.');
        if (body.fade !== undefined && !D.state.fades.includes(body.fade)) return no('Pick a fade time from the list.');
        st.rule = {on_at: on, on_offset: SUN.includes(on) ? body.on_offset || 0 : 0, off_at: off,
                   off_offset: SUN.includes(off) ? body.off_offset || 0 : 0, off_after: body.off_after || 360, fade: body.fade || 0};
        break;
      }
      case '/api/location': {
        if (body.lat == null) {                         // Locate me by time zone: that zone's main city
          const zones = await realFetch(new URL('tz_coords.json', BASE)).then(r => r.json()).catch(() => ({}));
          const c = zones[body.timezone];
          if (!c) return no("Couldn't work out where you are. Enter coordinates instead.");
          st.location = {lat: c[0], lon: c[1], name: `the ${body.timezone.split('/').pop().replace(/_/g, ' ').replace('St Johns', "St. John's").replace('St ', 'St. ')} area`};
          break;
        }
        const lat = Math.round(parseFloat(body.lat) * 100) / 100, lon = Math.round(parseFloat(body.lon) * 100) / 100;
        if (!(Math.abs(lat) <= 90 && Math.abs(lon) <= 180)) return no('Latitude is -90 to 90 and longitude -180 to 180.');
        st.location = {lat, lon, name: String(body.name || 'the coordinates you entered').slice(0, 40)}; break;
      }
      case '/api/name':
        if (!String(body.name || '').trim()) return no('Use a name of 1 to 40 characters.');
        st.name = String(body.name).trim().slice(0, 40); break;
      case '/api/effect-name':
        if (String(body.name || '').trim()) st.effectNames[body.mode] = String(body.name).trim().slice(0, 30);
        else delete st.effectNames[body.mode];
        break;
      case '/api/custom': {
        let spec;
        if (body.effect === 'playlist') {
          if (!Array.isArray(body.items) || !body.items.length) return no('Add at least one theme.');
          spec = {effect: 'playlist', items: body.items.map(it => ({show: it.show, hold: it.hold, transition: it.transition}))};
        } else {
          if (!Array.isArray(body.colours) || !body.colours.length || body.colours.length > 8 || !body.colours.every(c => HEX.test(c)))
            return no('Pick between 1 and 8 colours.');
          spec = {colours: body.colours.map(c => c.toLowerCase()), width: body.width || 1, effect: body.effect,
                  mode: body.mode || 0, speed: body.speed || 50};
        }
        let id = String(body.id || '');
        if (id !== 'try') {
          spec.name = String(body.name || '').trim().slice(0, 40);
          if (!spec.name) return no('Give the show a name.');
          if (!st.customs[id]) id = String(Math.max(0, ...Object.keys(st.customs).filter(k => /^\d+$/.test(k)).map(Number)) + 1);
        }
        st.customs[id] = spec;
        if (body.play) { st.show = 'custom:' + id; st.started = now(); }
        break;
      }
      case '/api/custom/delete': {
        const id = String(body.id || '');
        if (!st.customs[id]) return no('No such custom show.');
        const used = Object.values(st.customs).filter(c => c.effect === 'playlist' && c.items.some(it => it.show === 'custom:' + id));
        if (used.length) return no(`It's used in ${used.map(c => c.name).join(', ')}. Remove it from there first.`);
        delete st.customs[id];
        if (st.show === 'custom:' + id) st.show = 'classic';
        break;
      }
      default:
        if (path.startsWith('/api/zones/')) return no('Zones work on your own String Theory at home. This demo has a single zone.');
        return no('Not found');
    }
    save();
    return ok(payload(D));
  }

  window.fetch = async (input, opts = {}) => {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!url.pathname.startsWith('/api/')) return realFetch(input, opts);
    const D = await data;
    if (!st) { st = fresh(D); save(); }
    const body = opts.method === 'POST' ? JSON.parse(opts.body || '{}') : null;
    await new Promise(r => setTimeout(r, 60));          // feel a little like a real network
    return handle(url.pathname, body, D);
  };
  window.stringTheoryDemoReset = () => { store?.removeItem(KEY); location.reload(); };
})();
