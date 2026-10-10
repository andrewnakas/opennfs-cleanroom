"""DIRTY ROOM dev tool: side-by-side sheet of retail textures and their regenerated versions.
The output is for looking at once (to write briefs); it is never committed or published.

    python games/opennfs/dirty/contact_sheet.py trk000 out.png [game_dir] [clean_tracks_dir]
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dirty import fshread  # noqa: E402
from dirty.extract_spec import find_ci  # noqa: E402
import tools_shpi  # noqa: E402

CELL = 64


def tile(rgba):
    im = Image.fromarray(rgba, "RGBA")
    bg = Image.new("RGBA", im.size, (255, 0, 255, 255))
    bg.alpha_composite(im)
    return bg.convert("RGB").resize((CELL, CELL), Image.NEAREST)


def main():
    track = sys.argv[1]
    out = sys.argv[2]
    from dirty.extract_spec import find_game
    game = sys.argv[3] if len(sys.argv) > 3 else find_game("D:/n64work/opennfs")
    clean = sys.argv[4] if len(sys.argv) > 4 else "D:/n64work/opennfs/clean/resources/NFS_3/gamedata/tracks"
    stem = track.replace("k0", "", 1)
    src = find_ci(find_ci(find_ci(game, "gamedata"), "tracks"), track)
    dirty = fshread.read_archive(find_ci(src, stem + "0.qfs"))
    with open(os.path.join(clean, track, stem + "0.qfs"), "rb") as fh:
        regenerated = tools_shpi.read(fh.read())
    cols = 12
    rows = (len(dirty) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (2 * CELL + 6), rows * (CELL + 14)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, tex in enumerate(dirty):
        x, y = (i % cols) * (2 * CELL + 6), (i // cols) * (CELL + 14)
        if tex["rgba"] is not None:
            sheet.paste(tile(tex["rgba"]), (x, y + 12))
        if i < len(regenerated):
            sheet.paste(tile(regenerated[i]), (x + CELL, y + 12))
        draw.text((x + 2, y), "%d %dx%d" % (i, tex["width"], tex["height"]), fill=(230, 230, 230))
    sheet.save(out)
    print("sheet %s: %d textures (left retail, right regenerated) -> %s" % (track, len(dirty), out))


if __name__ == "__main__":
    main()
