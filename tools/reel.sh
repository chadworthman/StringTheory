#!/bin/bash
# Demo reel: 4 twinkle variants, 30 s each, with 2 s of darkness between them.
PY=${PY:-python3}             # a Python with tinytuya installed
cd "$(dirname "$0")/.."        # project root, where devices.json lives
RGW='[[255,0,0],[0,255,0],[255,140,0],[120,180,255],[255,255,255]]'
TRAD='[[255,0,0],[0,255,0],[255,140,0]]'
ICE='[[120,180,255],[255,255,255],[0,60,255]]'
gap(){ $PY tools/twinkle_test.py devices.json 2 '[0,0,0]' 0.1 '[0,0]' >/dev/null; }
echo "1: busy multicolour";  $PY tools/twinkle_test.py devices.json 30 '[150,100,45]' 0.75 '[3,5]' "$RGW"; gap
echo "2: medium multicolour"; $PY tools/twinkle_test.py devices.json 30 '[130,85,35]' 0.8 '[2,3]' "$RGW"; gap
echo "3: red/green/gold";    $PY tools/twinkle_test.py devices.json 30 '[150,100,45]' 0.75 '[3,4]' "$TRAD"; gap
echo "4: icy blue/white";    $PY tools/twinkle_test.py devices.json 30 '[40,60,110]' 0.75 '[3,4]' "$ICE"
