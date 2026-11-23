#!/usr/bin/env python3
"""Build the String Theory website (site/dist) for Spacefast.

  python3 tools/build_site.py          # then: sf publish site/dist

The demo is the real control app (pi/index.html and pi/help.html) with site/src/demo.js in front of it:
a pretend Pi that answers the app's requests in the browser. data.json holds what that pretend Pi
knows: a snapshot of a two-string install (made with the real lights.py and web.py, using a throwaway
state file, so nothing from your own setup gets in) and every show's preview.
"""
import json, shutil, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PI, SRC, OUT = ROOT / 'pi', ROOT / 'site' / 'src', ROOT / 'site' / 'dist'
sys.path.insert(0, str(PI))
import lights as L          # noqa: E402
import web                  # noqa: E402

def demo_data():
    tmp = Path(tempfile.mkdtemp())
    L.STATE, L.ENGINE, L.HEALTH = tmp / 'state.json', tmp / 'engine.json', tmp / 'health.json'
    L.save_state({'zones': [{'id': '1', 'name': 'Home Lights', 'strings': list(L.ORDER), 'show': 'redscan',
                             'on_at': '16:00', 'off_at': '00:00'}]})
    state = web.state_payload('1')
    # Use generic string names, never the device names from a real setup.
    rename = {name: f'String {chr(65 + i)}' for i, name in enumerate(L.ORDER)}
    for s in state['strings'] + state['all_strings']: s['name'] = rename[s['name']]
    for z in state['zones']: z['strings'] = [rename[n] for n in z['strings']]
    st = L.load_state()
    previews = {k: web.timeline(k, st, L) for k in L.SHOWS}
    shutil.rmtree(tmp)
    return {'state': state, 'previews': previews}

def page(src, extra_head, replacements):
    s = src.read_text()
    for old, new in replacements:
        assert old in s, f'{src.name}: {old!r} not found'
        s = s.replace(old, new)
    return s.replace('</title>', '</title>\n' + extra_head, 1)

SITE = 'https://stringtheory.space.fast'
# On the site, the logo and title at the top of the demo pages lead back to the landing page.
BRAND = ('<div class="brand"><img src="/logo.svg" alt="" width="34" height="34"><span>String Theory</span></div>', '<a class="brand" href="/" target="_top" title="About String Theory"><img src="/logo.svg" alt="" width="34" height="34"><span>String Theory</span></a>')
BRAND_CSS = '<style>a.brand { color: inherit; text-decoration: none; width: fit-content; }</style>\n'

def share(path, title, desc):
    """Search and share-preview tags for a page on the site."""
    return (f'<meta name="description" content="{desc}">\n<link rel="canonical" href="{SITE}{path}">\n'
            f'<meta property="og:type" content="website">\n<meta property="og:site_name" content="String Theory">\n'
            f'<meta property="og:title" content="{title}">\n<meta property="og:description" content="{desc}">\n'
            f'<meta property="og:url" content="{SITE}{path}">\n<meta property="og:image" content="{SITE}/og.png">\n'
            f'<meta property="og:image:width" content="1200">\n<meta property="og:image:height" content="630">\n'
            f'<meta name="twitter:card" content="summary_large_image">\n<meta name="twitter:image" content="{SITE}/og.png">\n')

DEMO_HEAD = '''<script src="/demo/demo.js"></script>
<style>
  a.brand { color: inherit; text-decoration: none; width: fit-content; }
  .demo-note { max-width: 520px; margin: 0 auto 12px; padding: 10px 14px; border-radius: 12px; font-size: 14px;
               background: #1e2633; border: 1px solid #2b3442; color: #d5dbe4; }
  .demo-note a { color: #ffbe55; }
  @media (min-width: 700px) { .demo-note { max-width: 980px; } }
  @media (min-width: 1150px) { .demo-note { max-width: 1200px; } }
</style>'''

def build():
    if OUT.exists():                    # clear the old build, but keep .spacefast (the link to the Space)
        for f in OUT.iterdir():
            if f.name != '.spacefast': shutil.rmtree(f) if f.is_dir() else f.unlink()
    (OUT / 'demo').mkdir(parents=True); (OUT / 'fonts').mkdir()
    for f in ('logo.svg', 'icon.png', 'icon-192.png', 'icon-512.png'):
        shutil.copy(PI / f, OUT / f)
    shutil.copy(PI / 'fonts' / 'pacifico.woff2', OUT / 'fonts')
    shutil.copy(PI / 'fonts' / 'Pacifico-OFL.txt', OUT / 'fonts')
    shutil.copy(SRC / 'home.html', OUT / 'index.html')
    shutil.copy(SRC / 'demo.js', OUT / 'demo' / 'demo.js')
    shutil.copy(PI / 'tz_coords.json', OUT / 'demo' / 'tz_coords.json')
    (OUT / 'demo' / 'data.json').write_text(json.dumps(demo_data(), separators=(',', ':')))
    shutil.copy(SRC / 'og.png', OUT / 'og.png')
    # Let browsers keep the title font and icons, so the title never flashes in another font while it loads.
    (OUT / '_headers').write_text('/fonts/*\n  Cache-Control: public, max-age=604800\n\n/logo.svg\n  Cache-Control: public, max-age=86400\n')
    (OUT / 'robots.txt').write_text(f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')
    (OUT / 'sitemap.xml').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + ''.join(f'  <url><loc>{SITE}{p}</loc></url>\n' for p in ('/', '/demo/', '/demo/help')) + '</urlset>\n')
    (OUT / 'demo' / 'index.html').write_text(page(PI / 'index.html', share('/demo/', 'String Theory demo: try it with pretend lights',
        'The real String Theory app with pretend lights: browse every show, build a playlist and try the controls in your browser.') + DEMO_HEAD, [
        ('<link rel="manifest" href="/manifest.webmanifest">\n', ''),
        ('<title>String Theory</title>', '<title>String Theory demo</title>'),
        ('href="/help"', 'href="/demo/help"'),
        BRAND,
        ('<main>\n', '<main>\n  <p class="demo-note">This is a demo with pretend lights. Everything you change stays in this browser. '
                     '<a href="/" target="_top">About String Theory</a></p>\n'),
    ]))
    (OUT / 'demo' / 'help.html').write_text(page(PI / 'help.html', share('/demo/help', 'String Theory shows A to Z',
        'Every String Theory light show, A to Z, with a live preview of each.') + BRAND_CSS + '<script src="/demo/demo.js"></script>', [
        ('<link rel="manifest" href="/manifest.webmanifest">\n', ''),
        ('<a class="back" href="/">Back to the lights</a>', '<a class="back" href="/demo/">Back to the demo</a>'),
        BRAND,
    ]))
    size = sum(f.stat().st_size for f in OUT.rglob('*') if f.is_file())
    print(f'built {OUT.relative_to(ROOT)}: {sum(1 for f in OUT.rglob("*") if f.is_file())} files, {size // 1024} KB')

if __name__ == '__main__':
    build()
