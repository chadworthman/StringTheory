# Plan: strings in any direction (horizontal and vertical)

Status: proposal, not built yet.

## Why

Today every show treats the strings as one long line, in wiring order: bulb 0 of the first string to the last bulb of the last. That works whatever way the strings hang, because a chase just follows the wire. It doesn't know which way is up, though. Once some strings hang vertically (down porch posts, beside a door, as drops from the eaves), you'd want shows that use the space:

- snow that falls *down* the vertical strings
- a sunset that rises from the bottom
- a rainbow or wipe that sweeps *left to right* across everything, whether it's on the eaves or a post
- a playlist transition that wipes across the porch, not along the wire

## The idea: give each string a place

Add an optional layout to each entry in `STRINGS`: where the string's first bulb is, and which way the string runs.

```python
STRINGS = [
    ('Left post',   24, {'start': (0, 0),  'run': 'up'}),     # bottom of the left post, going up
    ('C9 Lights',   24, {'start': (0, 24), 'run': 'right'}),  # along the eaves
    ('C9 Lights 2', 24, {'start': (24, 24), 'run': 'right'}),
    ('Right post',  24, {'start': (47, 23), 'run': 'down'}),  # top of the right post, going down
]
```

Positions are in bulb spacings, with x running across and y running up. A string with no layout keeps working exactly as today.

From this the engine works out an `(x, y)` position for every bulb, once at start-up.

## Two kinds of show

1. **Line shows (every show today).** `f(t)` returns one colour per bulb in wiring order. Nothing about them changes, and they look the same on any layout.
2. **Space shows (new).** `f(x, y, t)` returns the colour at a point on the porch. The engine samples it at every bulb's position. Shows written this way automatically do the right thing on horizontal and vertical strings alike:
   - Snowfall (space): flakes fall in y. On the eaves they twinkle in place; on the posts they run down.
   - Sunset rising: colour bands move up in y.
   - Rainbow sweep: hue moves in x across the whole porch.
   - Northern lights (space): the real thing. Green low down shading to purple higher up on the vertical strings, with curtains rippling across in x. On horizontal strings alone this can't be done, which is why today's shows are named "Aurora colours".

   Playlists gain a **Wipe across** transition that uses x.

The engine already converts each show into per-string slices, so supporting both kinds is a small change in one place (`String.run`). Previews on the page come from the same frames, so they keep working.

## The page

- The top of the page draws each string where it really is: horizontal strings as rows, vertical strings as columns. It uses the layout's positions, scaled to fit the phone. Today's one-row-per-string view becomes the default when no layout is given.
- Show cards keep a single strip preview, which is simpler and still readable.

## Tests

- **Find the seams** (built) shows where each string starts and ends. Its first bulb blinks white and its last is bright. On a vertical string, that also tells you which end is the top.
- A new **Layout check** test sweeps a white bar left to right, then a second bar bottom to top. If a string lights up at the wrong moment, its `start` or `run` is wrong.

## Steps

1. Layout config and per-bulb positions, the Layout check test, and the docs. Line shows are untouched.
2. Space-show support in the engine, plus Rainbow sweep and Sunset rising as the first two space shows.
3. The page draws strings in their real layout.
4. Space versions of Snowfall and a true Northern lights (vertical gradient), and the Wipe across playlist transition.

Each step is usable on its own, and step 1 changes nothing you can see unless you add layouts.

## Open questions

- How will the vertical strings actually be mounted (posts, door frame, drops from the eaves)? Will any string bend round a corner partway along? A bend would need a layout with more than one run per string.
- Should line shows on a mixed layout keep following the wire, or default to their space version where one exists?
