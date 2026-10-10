#!/bin/bash
# Headless driving test: tools/drive_test.sh <name> "<query>" [secs] [wait]
# Prints non-log console lines (deduplicated) and a telemetry table sampled from the ?hb=1 heartbeat.
REPO="$(cd "$(dirname "$0")/.." && pwd)"
NAME=${1:-drive}; QUERY=${2:-}; SECS=${3:-20,40}; WAIT=${4:-48}
OUT=/d/n64work/opennfs/shots/$NAME
python "$REPO/ports/wasm/headless_shot.py" $OUT --base http://localhost:8171/index.html --secs $SECS --query "hb=1&mute=1&$QUERY" --webgl --wait $WAIT 2>&1 | tail -1
grep -v "^hb \|^INFO\|^DEBUG" $OUT/console.txt | sed -E 's/WebGL-0x[0-9a-f]+/WebGL/' | sort | uniq -c | sort -rn | cut -c1-220 | head -${SHOWLOG:-10}
grep "^hb " $OUT/console.txt | python -c "
import sys, json
rows=[]
for line in sys.stdin:
    p=line.split(' ',2)
    try: s=json.loads(p[2])
    except Exception: continue
    if s: rows.append((p[1], s))
step=max(1,len(rows)//${ROWS:-24})
for i,(t,s) in enumerate(rows):
    if i%step==0 or i==len(rows)-1:
        print('%6s ph%d t%6.1f spd%6.1f lap%d pos%d/%d gnd%d skid%.2f wrong%d vr%4d/%d off%+5.1f hw%4.1f head%+4.0f best%.1f fin%.1f' % (t, s['phase'], s['time'], s['speed'], s['lap'], s['pos'], s['n'], s['gnd'], s['skid'], s['wrong'], s.get('vr',0), s.get('nvr',0), s.get('off',0), s.get('hw',0), s.get('head',0), s['best'], s['finish']))
if rows: print('results:', ' | '.join('%s %.1f' % (r['name'], r['t']) for r in rows[-1][1]['results']))
"
