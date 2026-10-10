"""Re-typeset signs for textures that carried lettering or symbols (clean side).

A brief (games/opennfs/briefs.json) says what kind of sign a texture is and what it should say. The wording is
ours and generic; colours come from the texture's kept 4x4 grid; the kept alpha outline is applied by the caller.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = os.path.join(os.path.dirname(os.path.dirname(HERE)), "assets", "ui", "fonts", "ui-font.ttf")
SS = 8  # supersampling

NAMED = {"white": (245, 245, 240), "black": (16, 16, 16), "yellow": (240, 196, 40), "red": (200, 32, 28), "cream": (240, 226, 184),
         "green": (60, 220, 110), "blue": (70, 110, 220), "ice": (220, 235, 255), "grey": (150, 150, 150), "dark": (40, 44, 52)}

# arrow centre lines in a unit square (x right, y down); the last point carries the head
ARROWS = {
    "bend_left": [(0.62, 0.92), (0.62, 0.55), (0.34, 0.24)],
    "u_left": [(0.70, 0.92), (0.70, 0.42), (0.52, 0.26), (0.34, 0.42), (0.34, 0.70)],
    "winding": [(0.50, 0.94), (0.34, 0.70), (0.66, 0.46), (0.50, 0.18)],
    "up": [(0.50, 0.92), (0.50, 0.18)],
    "up_left": [(0.80, 0.84), (0.26, 0.26)],
}


def colour(value, grid, fallback):
    if value is None:
        return fallback
    if isinstance(value, str):
        return NAMED[value]
    return tuple(value)


def background(grid):
    """Dominant colour of the kept grid (median per channel)."""
    return tuple(int(v) for v in np.median(grid.reshape(-1, 3), axis=0))


def fit_text(draw, lines, box, fill, vertical=False):
    x0, y0, x1, y1 = box
    if vertical:  # letters stacked top to bottom
        lines = list("".join(lines))
    size = int((y1 - y0) / max(len(lines), 1) * 1.05)
    while size > 6:
        font = ImageFont.truetype(FONT, size)
        boxes = [draw.textbbox((0, 0), ln, font=font) for ln in lines]
        widths = [b[2] - b[0] for b in boxes]
        line_h = max(b[3] - b[1] for b in boxes) * 1.12
        if max(widths) <= (x1 - x0) and line_h * len(lines) <= (y1 - y0):
            break
        size -= max(1, size // 14)
    y = y0 + ((y1 - y0) - line_h * len(lines)) / 2
    for ln, b, wd in zip(lines, boxes, widths):
        draw.text((x0 + ((x1 - x0) - wd) / 2 - b[0], y - b[1] + (line_h - (b[3] - b[1])) / 2), ln, font=font, fill=fill)
        y += line_h


def arrow(draw, shape, w, h, fill):
    mirror = shape.endswith("_right")
    base = shape.replace("_right", "_left")
    if base == "chevron_left":
        pts = [(0.78, 0.12), (0.26, 0.50), (0.78, 0.88), (0.58, 0.88), (0.06, 0.50), (0.58, 0.12)]
        pts = [((1 - x) if mirror else x, y) for x, y in pts]
        draw.polygon([(x * w, y * h) for x, y in pts], fill=fill)
        return
    path = ARROWS[base]
    path = [((1 - x) if mirror else x, y) for x, y in path]
    px = [(x * w, y * h) for x, y in path]
    draw.line(px, fill=fill, width=int(0.13 * w), joint="curve")
    (ax, ay), (bx, by) = px[-2], px[-1]
    d = np.array([bx - ax, by - ay], np.float64)
    d /= max(np.linalg.norm(d), 1e-6)
    n = np.array([-d[1], d[0]])
    tip = np.array([bx, by]) + d * 0.10 * w
    back = np.array([bx, by]) - d * 0.12 * w
    draw.polygon([tuple(tip), tuple(back + n * 0.17 * w), tuple(back - n * 0.17 * w)], fill=fill)


def render(brief, w, h, grid, base_rgb):
    """-> (h, w, 3) uint8, or None to keep the regenerated texture. base_rgb is that regenerated texture."""
    kind = brief["sign"]
    part, parts = brief.get("part", [0, 1])
    W, H = w * SS * parts, h * SS
    bg = colour(brief.get("bg"), grid, background(grid))
    fg = colour(brief.get("fg"), grid, NAMED["black"])
    if kind in ("arrow", "warn") and brief.get("bg") is None:
        # symbols are drawn over the regenerated texture so the sign keeps its own colours and wear
        img = Image.fromarray(base_rgb, "RGB").resize((W, H), Image.BICUBIC)
    else:
        img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)
    margin = int(0.08 * min(W, H))
    if kind == "speed":
        white, black = NAMED["white"], NAMED["black"]
        draw.rectangle([0, 0, W - 1, H - 1], fill=white, outline=black, width=max(2, int(0.05 * W)))
        fit_text(draw, [brief["text"]], (margin * 2, int(H * 0.08), W - margin * 2, int(H * 0.70)), black)
        fit_text(draw, [brief.get("unit", "")], (margin * 2, int(H * 0.68), W - margin * 2, int(H * 0.94)), black)
    elif kind == "arrow":
        arrow(draw, brief["shape"], W, H, fg)
    elif kind == "warn":
        fit_text(draw, ["!"], (margin, margin, W - margin, H - margin), fg)
    elif kind == "plate":
        text = brief["text"]
        lines = text if isinstance(text, list) else [text]
        if brief.get("border"):
            draw.rectangle([0, 0, W - 1, H - 1], outline=fg, width=max(2, int(0.04 * H)))
        fit_text(draw, lines, (margin, margin, W - margin, H - margin), fg, vertical=brief.get("vertical", False))
    else:
        return None
    if parts > 1:
        img = img.crop((part * w * SS, 0, (part + 1) * w * SS, H))
    img = img.resize((w, h), Image.LANCZOS)
    if brief.get("mirror"):
        img = img.transpose(Image.FLIP_LEFT_RIGHT)
    return np.asarray(img, np.uint8)
