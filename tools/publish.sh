#!/bin/bash
# Publish: gates -> curated source export (main) -> site (gh-pages). Usage: tools/publish.sh "commit message"
# Nothing is pushed unless the taint scan and all name scans pass.
set -uo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
WORK=/d/n64work/opennfs
SLUG=andrewnakas/opennfs-cleanroom
MSG=${1:-"Update"}
SIGN="Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
cd "$REPO"

echo "== gates"
python tools/taint_scan.py | tail -5 || { echo "TAINT SCAN FAILED: not publishing"; exit 1; }
python tools/name_scan.py $WORK/site $WORK/clean | tail -3 || { echo "NAME SCAN (site) FAILED: not publishing"; exit 1; }
# forbidden file kinds must only exist inside the track packs (never loose on the site)
LOOSE=$(find $WORK/site -type f \( -iname '*.frd' -o -iname '*.col' -o -iname '*.qfs' -o -iname '*.viv' -o -iname '*.iso' -o -iname '*.exe' \) | wc -l)
[ "$LOOSE" = "0" ] || { echo "loose game-format files on the site: not publishing"; exit 1; }

echo "== source export"
SRC=$WORK/public_repo
if [ ! -d $SRC/.git ]; then
  mkdir -p $SRC && git -C $SRC init -q -b main
  git -C $SRC config user.name "andrewnakas"; git -C $SRC config user.email "andrewnakas@users.noreply.github.com"
  git -C $SRC remote add origin https://github.com/$SLUG.git
fi
find $SRC -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
mkdir -p $SRC/ports $SRC/games $SRC/tools
cp README.md STATUS.md $SRC/
cp -r assets $SRC/assets
cp -r ports/opennfs $SRC/ports/opennfs
mkdir -p $SRC/ports/wasm && cp ports/wasm/serve.py ports/wasm/headless_shot.py ports/wasm/cdp_shot.py ports/wasm/cdp_stack.py $SRC/ports/wasm/
cp -r games/opennfs $SRC/games/opennfs
cp tools/build_web.sh tools/make_site.py tools/name_scan.py tools/taint_scan.py tools/drive_test.sh tools/publish.sh $SRC/tools/
find $SRC -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
cat > $SRC/.gitignore <<'EOF'
__pycache__/
*.pyc
# never commit game files, specs or build outputs
*.viv
*.frd
*.col
*.qfs
*.fsh
*.fce
*.can
*.hrz
*.iso
/site/
/build/
/spec/
EOF
python tools/name_scan.py $SRC | tail -3 || { echo "NAME SCAN (sources) FAILED: not publishing"; exit 1; }
git -C $SRC add -A
git -C $SRC commit -q -m "$MSG

$SIGN" || echo "(sources unchanged)"
git -C $SRC push -q -u origin main || exit 1

echo "== site"
PAGES=$WORK/pages
if [ ! -d $PAGES/.git ]; then
  mkdir -p $PAGES && git -C $PAGES init -q -b gh-pages
  git -C $PAGES config user.name "andrewnakas"; git -C $PAGES config user.email "andrewnakas@users.noreply.github.com"
  git -C $PAGES remote add origin https://github.com/$SLUG.git
fi
find $PAGES -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
cp -r $WORK/site/. $PAGES/
touch $PAGES/.nojekyll
git -C $PAGES add -A
git -C $PAGES commit -q -m "Site: $MSG

$SIGN" || echo "(site unchanged)"
git -C $PAGES push -q -f -u origin gh-pages || exit 1
echo "published: https://andrewnakas.github.io/opennfs-cleanroom/ ($(du -sh $WORK/site | cut -f1))"
