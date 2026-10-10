"""DIRTY ROOM dev tool: compact sheet of one track's retail textures, to spot the ones that carry text or symbols
(they get a brief in games/opennfs/briefs.json and are re-typeset by the clean generator). Never published.

    python games/opennfs/dirty/text_sheet.py trk001 out.png
"""
import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dirty import fshread  # noqa: E402
from dirty.extract_spec import find_ci, find_game  # noqa: E402

CELL = 56


def main():
    track, out = sys.argv[1], sys.argv[2]
    game = find_game("D:/n64work/opennfs")
    stem = track.replace("k0", "", 1)
    src = find_ci(find_ci(find_ci(game, "gamedata"), "tracks"), track)
    textures = fshread.read_archive(find_ci(src, stem + "0.qfs"))
    cols = 22
    rows = (len(textures) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (CELL + 2), rows * (CELL + 12)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, tex in enumerate(textures):
        x, y = (i % cols) * (CELL + 2), (i // cols) * (CELL + 12)
        if tex["rgba"] is not None:
            im = Image.fromarray(tex["rgba"], "RGBA")
            bg = Image.new("RGBA", im.size, (255, 0, 255, 255))
            bg.alpha_composite(im)
            sheet.paste(bg.convert("RGB").resize((CELL, CELL), Image.NEAREST), (x, y + 11))
        draw.text((x + 1, y), str(i), fill=(240, 240, 240))
    sheet.save(out)
    print("%s: %d textures -> %s" % (track, len(textures), out))


if __name__ == "__main__":
    main()
