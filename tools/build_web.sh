#!/bin/bash
# Build the web port: patched tree -> cmake/ninja (emscripten) -> opennfs.js/.wasm
# Usage: tools/build_web.sh [jobs]     (prints a one-screen summary; full log in $WORK/build.log)
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK=/d/n64work/opennfs
EMS=/d/n64work/emsdk/upstream/emscripten
JOBS=${1:-3}
export EM_CONFIG=/d/n64work/emsdk/.emscripten
export PATH="/d/n64work/emsdk/upstream/bin:$PATH"
# one build at a time (two ninjas in the same directory corrupt each other's outputs)
LOCK=$WORK/build.lock
while ! mkdir "$LOCK" 2>/dev/null; do sleep 5; done
trap 'rmdir "$LOCK" 2>/dev/null' EXIT
python "$REPO/ports/opennfs/prepare.py" || exit 1
mkdir -p $WORK/build
cd $WORK/build
# re-run cmake when the set of source files changes (sources are globbed)
LIST=$(find $WORK/port/src -name '*.cpp' | sort | md5sum | cut -d' ' -f1)
if [ ! -f build.ninja ] || [ "$(cat srclist.md5 2>/dev/null)" != "$LIST" ]; then
  echo "$LIST" > srclist.md5
  "$EMS/emcmake.exe" cmake -G Ninja -DCMAKE_BUILD_TYPE=Release "$(cygpath -m "$REPO/ports/opennfs")" > $WORK/configure.log 2>&1 || { tail -20 $WORK/configure.log; exit 1; }
fi
ninja -j$JOBS -k 0 > $WORK/build.log 2>&1
RC=$?
echo "ninja exit $RC; $(grep -c 'error:' $WORK/build.log) errors, $(grep -c 'FAILED' $WORK/build.log) failed targets"
grep -E "error:" $WORK/build.log | sed -E 's/^.*(src|lib|include)\//\1\//' | sort | uniq -c | sort -rn | head -${SHOW:-40}
ls -la opennfs.js opennfs.wasm 2>/dev/null
exit $RC
