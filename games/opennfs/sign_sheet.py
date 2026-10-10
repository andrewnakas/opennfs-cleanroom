"""Clean-side check: one sheet of every re-typeset sign texture (from the generated track folders).

    python games/opennfs/sign_sheet.py <tracks_dir> out.png
"""
import json
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tools_shpi  # noqa: E402

CELL = 80


def main():
    tracks_dir, out = sys.argv[1], sys.argv[2]
    with open(os.path.join(HERE, "briefs.json")) as fh:
        briefs = json.load(fh)
    tiles = []
    for track in sorted(k for k in briefs if not k.startswith("_")):
        stem = track.replace("k0", "", 1)
        path = os.path.join(tracks_dir, track, stem + "0.qfs")
        if not os.path.exists(path):
            continue
        with open(path, "rb") as fh:
            textures = tools_shpi.read(fh.read())
        for idx in sorted(briefs[track], key=int):
            im = Image.fromarray(textures[int(idx)], "RGBA")
            bg = Image.new("RGBA", im.size, (255, 0, 255, 255))
            bg.alpha_composite(im)
            tiles.append(("%s %s" % (track[-1], idx), bg.convert("RGB").resize((CELL, CELL), Image.NEAREST)))
    cols = 16
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * (CELL + 2), rows * (CELL + 12)), (24, 24, 24))
    draw = ImageDraw.Draw(sheet)
    for i, (label, tile) in enumerate(tiles):
        x, y = (i % cols) * (CELL + 2), (i // cols) * (CELL + 12)
        sheet.paste(tile, (x, y + 11))
        draw.text((x + 1, y), label, fill=(240, 240, 240))
    sheet.save(out)
    print("%d sign textures -> %s" % (len(tiles), out))


if __name__ == "__main__":
    main()
