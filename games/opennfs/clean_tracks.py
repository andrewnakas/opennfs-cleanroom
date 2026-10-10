"""CLEAN ROOM. Builds playable track folders from the spec only (never reads the game folder).

    python games/opennfs/clean_tracks.py [spec_dir] [out_tracks_dir]

Per track: kept geometry files are copied from the spec; every texture is regenerated from its
4x4 colour grid and 2-bit alpha outline with original procedural detail; the horizon file is
rewritten from the two kept sky colours.
"""
import colorsys
import zlib
import json
import os
import shutil
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import nfsfmt  # noqa: E402
import signs  # noqa: E402

with open(os.path.join(HERE, "briefs.json")) as _fh:
    BRIEFS = json.load(_fh)

SPEC = sys.argv[1] if len(sys.argv) > 1 else "D:/n64work/opennfs/spec/gen3"
OUT = sys.argv[2] if len(sys.argv) > 2 else "D:/n64work/opennfs/clean/resources/NFS_3/gamedata/tracks"

# Our own names for the circuits (the retail titles are not used anywhere)
NAMES = {
    "trk000": "Maple Hollow", "trk001": "Red Mesa", "trk002": "Glass Harbor", "trk003": "Larch Valley", "trk004": "Snowfield",
    "trk005": "Ember Gulch", "trk006": "Midnight Harbor", "trk007": "Winter Larch", "trk008": "Neon Mile",
}


def value_noise(seed, h, w, cells, octaves=4):
    """Tileable multi-octave value noise in 0..1 at an arbitrary size."""
    r = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, total = 1.0, 0.0
    for _ in range(octaves):
        c = max(1, min(cells, max(h, w)))
        grid = r.random((c, c), dtype=np.float32)
        tiled = np.tile(grid, (3, 3))
        img = Image.fromarray((tiled * 255).astype(np.uint8)).resize((w * 3, h * 3), Image.BICUBIC)
        out += np.asarray(img, np.float32)[h:2 * h, w:2 * w] / 255.0 * amp
        total += amp
        amp *= 0.5
        cells *= 2
    out /= total
    lo, hi = float(out.min()), float(out.max())
    return (out - lo) / max(hi - lo, 1e-6)


def classify(grid):
    """Pick a detail recipe from the coarse colours alone. -> (name, amplitude, cells, octaves)"""
    mean = grid.reshape(-1, 3).mean(axis=0) / 255.0
    h, s, v = colorsys.rgb_to_hsv(*mean)
    spread = float(grid.reshape(-1, 3).std(axis=0).mean()) / 255.0
    if s < 0.13:
        return ("stone", 0.10 if v > 0.25 else 0.07, 12, 4)       # asphalt, concrete, snow, metal
    if 0.19 <= h <= 0.46:
        return ("foliage", 0.26, 7, 4)                              # grass, trees, bushes
    if h < 0.14 or h > 0.92:
        return ("earth", 0.17, 8, 4)                                # dirt, rock, brick, sand
    if 0.5 <= h <= 0.72:
        return ("smooth", 0.05, 3, 2)                               # sky, water, glass
    return ("plain", 0.10 + min(spread, 0.1), 8, 3)


def make_texture(entry, alpha2, seed, brief=None):
    w, h = entry["width"], entry["height"]
    if entry["grid"] is None:
        grid = np.full((4, 4, 3), 128, np.uint8)
    else:
        grid = np.array(entry["grid"], np.uint8).reshape(4, 4, 3)
    # smooth colour field from the 16 kept colours
    base = np.asarray(Image.fromarray(grid, "RGB").resize((max(w, 1), max(h, 1)), Image.BICUBIC), np.float32)
    name, amp, cells, octaves = classify(grid)
    if min(w, h) >= 8:
        cells = max(2, min(cells, min(w, h) // 3))
        n = value_noise(seed, h, w, cells, octaves)
        # a little grain, kept below one 5-bit step so the 16-bit files still compress well
        fine = value_noise(seed + 1, h, w, max(2, min(w, h) // 2), 1)
        detail = (n - 0.5) * 2.0 * amp + (fine - 0.5) * amp * 0.35
        if name == "foliage":
            # leafy speckle: darker pockets between brighter clumps
            clump = value_noise(seed + 2, h, w, max(2, min(w, h) // 4), 2)
            detail += (clump - 0.5) * 0.22
        rgb = base * (1.0 + detail[..., None])
    else:
        rgb = base
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[:, :, :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    if brief is not None:
        # lettering or a symbol: re-typeset from the brief (colours from the kept grid, wording ours)
        drawn = signs.render(brief, w, h, grid, rgba[:, :, :3].copy())
        if drawn is not None:
            rgba[:, :, :3] = drawn
            name = "sign"
    rgba[:, :, 3] = 255 if alpha2 is None else (alpha2.astype(np.uint16) * 85).astype(np.uint8)
    return rgba, name


def build_track(track_id):
    src = os.path.join(SPEC, track_id)
    with open(os.path.join(src, "textures.json")) as fh:
        spec = json.load(fh)
    alphas = np.load(os.path.join(src, "alpha.npz"))
    out = os.path.join(OUT, track_id)
    os.makedirs(out, exist_ok=True)
    stem = track_id.replace("k0", "", 1)
    for name in os.listdir(os.path.join(src, "kept")):
        shutil.copyfile(os.path.join(src, "kept", name), os.path.join(out, name))
    images, kinds = [], {}
    for entry in spec["textures"]:
        key = "a%d" % entry["index"]
        alpha2 = alphas[key] if key in alphas.files else None
        brief = BRIEFS.get(track_id, {}).get(str(entry["index"]))
        rgba, kind = make_texture(entry, alpha2, seed=zlib.crc32(("%s:%d" % (track_id, entry["index"])).encode()), brief=brief)
        images.append(rgba)
        kinds[kind] = kinds.get(kind, 0) + 1
    with open(os.path.join(out, stem + "0.qfs"), "wb") as fh:
        fh.write(nfsfmt.fsh16(images))
    top = spec["sky_top"] or [80, 130, 200]
    bottom = spec["sky_bottom"] or [200, 210, 220]
    with open(os.path.join(out, "3" + stem + ".hrz"), "wb") as fh:
        fh.write(nfsfmt.hrz(tuple(top), tuple(bottom)))
    print("%s: %3d textures regenerated (%s)" % (track_id, len(images), ", ".join("%s %d" % kv for kv in sorted(kinds.items()))))
    lap = (spec.get("facts") or {}).get("lap_m", 0)
    return dict(id=track_id, name=NAMES.get(track_id, "Circuit %d" % (int(track_id[-1]) + 1)), length_m=int(round(lap)), n_textures=len(images))


def main():
    if not os.path.isdir(SPEC):
        print("no spec at %s: retail-geometry tracks are skipped (dirty room has not been run)" % SPEC)
        return []
    return [build_track(t) for t in sorted(os.listdir(SPEC)) if os.path.isdir(os.path.join(SPEC, t))]


if __name__ == "__main__":
    main()
