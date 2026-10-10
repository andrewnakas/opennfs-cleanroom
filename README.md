# Open Road: clean-room web build of an open racing engine

**Play: https://andrewnakas.github.io/opennfs-cleanroom/**

A classic late-90s style arcade racer running in the browser (WebAssembly + WebGL2).
The engine is the open-source [OpenNFS](https://github.com/OpenNFS/OpenNFS) project (MIT), ported to the
web and extended with what a race needs: starting grid, countdown, laps, timing, positions, AI drivers,
a HUD, touch and gamepad controls, and synthesised sound.

**No commercial game data is in this repository or on the site.**

## What "clean room" means here

The engine reads the track and car file formats of several classic PC racing games. This project feeds it
files that are either completely original or rebuilt from *facts only*:

| Content | Where it comes from |
|---|---|
| Circuits "Cedar Ridge", "Harbor Loop", "Granite Pass" | Original. Generated from formulas by `games/opennfs/synth_track.py` |
| Cars "Clean Coupe", "Clean Hatch", "Clean Wedge" | Original shapes by the fictional "Cleanroom Motors" (`games/opennfs/synth_car.py`). Not based on any real vehicle |
| Classic circuits 1-9 (only when the owner has run the dirty room) | **Kept facts:** road and scenery geometry, collision, driving line, camera path. **Regenerated:** every texture, from a 4x4 colour grid and a 2-bit alpha outline per texture (`games/opennfs/clean_tracks.py`) |
| Textures, sky, particles, menu images | Procedural (`games/opennfs/proctex.py`, `build_assets.py`) |
| All sound and music | Synthesised live with WebAudio (`ports/opennfs/web/audio.js`). No samples |
| Engine art bundled with the upstream repository | Not used. Regenerated too |

The full ledger is in [`assets/LICENSES.csv`](assets/LICENSES.csv).

Two gates must pass before anything is published:

- `python tools/taint_scan.py` compares the clean tree with every reference file (upstream engine art and,
  when present, the owner's game folder): no identical files, no look-alike images, and for rebuilt
  textures no correlation with the detail of the texture they replace. Must print `0 failing`.
- `python tools/name_scan.py <site> <clean>` searches the output for publisher, game and car-maker names. Must print `0 hits`.

## Layout

```
ports/opennfs/     the web port: CMake project, patch list (patches.py), overlay sources, page (web/)
games/opennfs/     asset generators (file format writers, tracks, cars, textures, sky, UI)
games/opennfs/dirty/   the only code that reads a retail game folder; it writes a coarse spec, nothing else
tools/             build_web.sh, make_site.py, taint_scan.py, name_scan.py, drive_test.sh
assets/            the UI font (DejaVu) and the licence ledger
```

The upstream engine is not vendored. `ports/opennfs/prepare.py` builds the port tree from a pristine clone:
overlay files + `patches.py` + a pass that removes retail titles from log and assert strings.

## Building

Requirements: emsdk, CMake, Ninja, Python 3.12 with numpy and Pillow.

```sh
git clone --recurse-submodules https://github.com/OpenNFS/OpenNFS.git   # pristine engine (paths are set at the top of the scripts)
python games/opennfs/build_assets.py      # clean asset tree + manifest
tools/build_web.sh                        # port tree -> emscripten build
python tools/make_site.py --release       # site: engine + core pack + one pack per track
python tools/taint_scan.py && python tools/name_scan.py <site> <clean>
python ports/wasm/serve.py <site> 8171    # then open http://localhost:8171/
```

Optional dirty room (needs your own copy of the supported classic game; nothing of it is published):
`python games/opennfs/dirty/extract_spec.py <game folder>` writes the spec that `clean_tracks.py` rebuilds circuits from.

## Controls

W / Up accelerate, S / Down brake and reverse, A D / Left Right steer, Space handbrake, R back on track,
C camera, L lights, M sound, Esc menu. Gamepad (standard mapping) and touch buttons are supported.
Developer overlay of the engine: F1.

## Credits and licences

- Engine and format parsers: OpenNFS / LibOpenNFS, (c) Amrik Sadhra and contributors, MIT
- Bullet Physics (Zlib), Dear ImGui / ImPlot (MIT), GLM (MIT), FreeType (FTL), nlohmann/json, stb, tinyobjloader, magic_enum, argparse (MIT), Emscripten (MIT/NCSA)
- Font: DejaVu Sans (Bitstream Vera / DejaVu licence)
- Everything written for this project: code MIT, generated content CC0 1.0

This is an unofficial fan project, not affiliated with or endorsed by any game publisher or car maker.
