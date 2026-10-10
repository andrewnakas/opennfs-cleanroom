"""DIRTY ROOM -> spec. The only script that reads the owner's retail game folder.

    python games/opennfs/dirty/extract_spec.py [game_dir] [spec_dir]

What crosses into the spec (the owner's kept-fact scope for this project):
  kept         track geometry and collision (FRD, COL: vertices, polygons, texture mapping, virtual road,
               object placement and motion), camera path (CAN), AI speed table (speedsf.bin)
  coarse       the per-vertex colours inside FRD/COL: one average colour per track block / object, 2-bit alpha
  numbers      the two sky colours of the horizon file
  coarse       per texture: size, a 4x4 colour grid, and the alpha channel reduced to 2 bits
Nothing else is read out: no texture pixels, no audio, no car models, no menus, no text.
The spec lives in the work dir (not in the repository) and is the only input of the clean generator.
"""
import glob
import json
import os
import re
import shutil
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dirty import fshread, kept_geometry  # noqa: E402

WORK = "D:/n64work/opennfs"
SPEC = sys.argv[2] if len(sys.argv) > 2 else WORK + "/spec/gen3"


def find_ci(folder, name):
    """Case-insensitive file lookup (the disc uses upper case names)."""
    for f in os.listdir(folder):
        if f.lower() == name.lower():
            return os.path.join(folder, f)
    return None


def colour_grid(rgba):
    """4x4 grid of mean colours, ignoring fully transparent texels. -> (4, 4, 3) uint8"""
    h, w = rgba.shape[:2]
    grid = np.zeros((4, 4, 3), np.float64)
    opaque = rgba[:, :, 3] > 0
    overall = rgba[:, :, :3][opaque].mean(axis=0) if opaque.any() else np.array([0.0, 0.0, 0.0])
    for gy in range(4):
        y0, y1 = gy * h // 4, max((gy + 1) * h // 4, gy * h // 4 + 1)
        for gx in range(4):
            x0, x1 = gx * w // 4, max((gx + 1) * w // 4, gx * w // 4 + 1)
            cell = rgba[y0:min(y1, h), x0:min(x1, w)]
            mask = cell[:, :, 3] > 0
            grid[gy, gx] = cell[:, :, :3][mask].mean(axis=0) if mask.any() else overall
    return np.clip(np.round(grid), 0, 255).astype(np.uint8)


def sky_colours(hrz_path):
    top = bottom = None
    with open(hrz_path, "r", encoding="latin-1") as fh:
        lines = fh.read().splitlines()
    for i, line in enumerate(lines):
        if "top of Gourad shaded SKY" in line:
            top = [int(v) for v in re.findall(r"-?\d+", lines[i + 1])[:3]]
        if "base of Gourad shaded SKY" in line:
            bottom = [int(v) for v in re.findall(r"-?\d+", lines[i + 1])[:3]]
    return top, bottom


def find_game(work):
    """The owner's game folder: the first folder in the work dir that holds 'gamedata' and 'fedata' folders."""
    for name in sorted(os.listdir(work)):
        full = os.path.join(work, name)
        if os.path.isdir(full) and find_ci(full, "gamedata") and find_ci(full, "fedata"):
            return full
    return None


def main():
    game = sys.argv[1] if len(sys.argv) > 1 else find_game(WORK)
    if not game:
        print("no game folder found in %s: the dirty room stays BLOCKED on game files" % WORK)
        return
    tracks_dir = find_ci(find_ci(game, "gamedata"), "tracks")
    summary = []
    for folder in sorted(os.listdir(tracks_dir)):
        track_id = folder.lower()
        src = os.path.join(tracks_dir, folder)
        stem = track_id.replace("k0", "", 1)
        out = os.path.join(SPEC, track_id)
        kept = os.path.join(out, "kept")
        os.makedirs(kept, exist_ok=True)
        missing = []
        facts = {}
        for name in (stem + ".frd", stem + ".col", stem + "00a.can", "speedsf.bin"):
            path = find_ci(src, name)
            if path is None:
                missing.append(name)
                continue
            if name.endswith((".frd", ".col")):
                # geometry is kept; the per-vertex colours in these files are reduced to one colour per block
                with open(path, "rb") as fh:
                    raw = fh.read()
                data, info = (kept_geometry.coarsen_frd if name.endswith(".frd") else kept_geometry.coarsen_col)(raw)
                facts.update(info)
                with open(os.path.join(kept, name), "wb") as fh:
                    fh.write(data)
            else:
                shutil.copyfile(path, os.path.join(kept, name))
        hrz = find_ci(src, "3" + stem + ".hrz")
        top, bottom = sky_colours(hrz) if hrz else (None, None)

        qfs = find_ci(src, stem + "0.qfs")
        textures = fshread.read_archive(qfs)
        entries, alphas = [], {}
        n_alpha = 0
        for i, tex in enumerate(textures):
            rgba = tex["rgba"]
            entry = dict(index=i, width=tex["width"], height=tex["height"], format=tex["code"])
            if rgba is None:
                entry["grid"] = None
            else:
                entry["grid"] = colour_grid(rgba).reshape(-1).tolist()
                alpha2 = np.round(rgba[:, :, 3].astype(np.float32) / 85.0).astype(np.uint8)  # 0..3
                if (alpha2 < 3).any():
                    alphas["a%d" % i] = alpha2
                    n_alpha += 1
            entries.append(entry)
        with open(os.path.join(out, "textures.json"), "w", newline="\n") as fh:
            json.dump(dict(track=track_id, sky_top=top, sky_bottom=bottom, facts=facts, textures=entries), fh)
        np.savez_compressed(os.path.join(out, "alpha.npz"), **alphas)
        summary.append("%s: %3d textures (%2d with alpha), %3d blocks, %5d polygons, lap %4.0f m, kept %s" % (
            track_id, len(entries), n_alpha, facts.get("blocks", 0), facts.get("polygons", 0), facts.get("lap_m", 0),
            "frd col can speeds" if not missing else "MISSING " + ",".join(missing)))
    print("\n".join(summary))
    print("spec -> %s (%d tracks)" % (SPEC, len(summary)))


if __name__ == "__main__":
    main()
