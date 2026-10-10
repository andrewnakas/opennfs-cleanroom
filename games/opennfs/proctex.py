"""Original procedural textures (numpy + PIL). Nothing here is derived from any game data."""
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 256


def rng(seed):
    return np.random.default_rng(seed)


def tile_noise(seed, size=S, octaves=5, persistence=0.55, base=4):
    """Tileable value noise in 0..1."""
    r = rng(seed)
    out = np.zeros((size, size), np.float32)
    amp, total, cells = 1.0, 0.0, base
    for _ in range(octaves):
        grid = r.random((cells, cells), dtype=np.float32)
        img = Image.fromarray((grid * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC)
        # wrap-around blend so the result tiles
        layer = np.asarray(img, np.float32) / 255.0
        layer = (layer + np.roll(layer, size // 2, 0) + np.roll(layer, size // 2, 1) + np.roll(layer, (size // 2, size // 2), (0, 1))) / 4.0
        out += layer * amp
        total += amp
        amp *= persistence
        cells *= 2
    out /= total
    out -= out.min()
    return out / max(out.max(), 1e-6)


def grain(seed, size=S, strength=1.0):
    return (rng(seed).random((size, size), dtype=np.float32) - 0.5) * strength


def rgba(rgb, alpha=None):
    h, w = rgb.shape[:2]
    a = np.full((h, w, 1), 255, np.float32) if alpha is None else alpha.reshape(h, w, 1).astype(np.float32)
    return np.clip(np.concatenate([rgb, a], axis=2), 0, 255).astype(np.uint8)


def colourise(v, dark, light):
    v = v[..., None]
    return np.asarray(dark, np.float32) * (1 - v) + np.asarray(light, np.float32) * v


def asphalt(seed=1):
    n = tile_noise(seed, octaves=6, base=8) * 0.5 + 0.5 * tile_noise(seed + 9, octaves=3, base=3)
    v = 0.42 + 0.22 * (n - 0.5) + grain(seed + 3, strength=0.16)
    rgb = colourise(np.clip(v, 0, 1), (38, 38, 42), (150, 148, 144))
    return rgb


def paint(rgb, mask, colour, wear_seed=5):
    wear = 0.75 + 0.25 * tile_noise(wear_seed, octaves=4, base=16)
    m = (mask * wear)[..., None]
    return rgb * (1 - m) + np.asarray(colour, np.float32) * m


def vline_mask(u0, u1, v0=0.0, v1=1.0):
    """Mask for a painted stripe running along v (direction of travel)."""
    m = np.zeros((S, S), np.float32)
    m[int(v0 * S):int(v1 * S), int(u0 * S):int(u1 * S)] = 1.0
    return m


def road_outer():
    # u=0 is the road edge (solid white line), u=1 the lane divider (half a dashed line)
    rgb = asphalt(1)
    rgb = paint(rgb, vline_mask(0.05, 0.10), (225, 225, 215))
    rgb = paint(rgb, vline_mask(0.98, 1.0, 0.0, 0.5), (225, 225, 215))
    return rgba(rgb)


def road_inner():
    # u=0 lane divider (other half of the dashed line), u=1 centre of the road (one of a double yellow)
    rgb = asphalt(2)
    rgb = paint(rgb, vline_mask(0.0, 0.02, 0.0, 0.5), (225, 225, 215))
    rgb = paint(rgb, vline_mask(0.93, 0.975), (228, 182, 40))
    return rgba(rgb)


def start_line():
    rgb = asphalt(3)
    m = np.zeros((S, S), np.float32)
    cell = S // 8
    for y in range(2):
        for x in range(8):
            if (x + y) % 2 == 0:
                m[S // 2 - cell + y * cell:S // 2 + y * cell, x * cell:(x + 1) * cell] = 1
    band = np.zeros((S, S), np.float32)
    band[S // 2 - cell:S // 2 + cell, :] = 1
    rgb = paint(rgb, band, (25, 25, 25))
    rgb = paint(rgb, m, (235, 235, 235))
    return rgba(rgb)


def shoulder():
    # u=0 outer (gravel), u=1 road side (asphalt)
    a = asphalt(4)
    n = tile_noise(11, octaves=6, base=16)
    g = colourise(np.clip(n + grain(12, strength=0.35), 0, 1), (92, 84, 72), (176, 166, 148))
    u = np.linspace(0, 1, S, dtype=np.float32)[None, :].repeat(S, 0)
    edge = np.clip((u - 0.45 + (tile_noise(13, base=8) - 0.5) * 0.25) * 6, 0, 1)[..., None]
    return rgba(g * (1 - edge) + a * edge)


def grass(seed=20, dry=0.0, dark=(34, 62, 22), light=(118, 150, 58)):
    n = tile_noise(seed, octaves=6, base=6)
    blades = tile_noise(seed + 1, octaves=3, base=48)
    v = np.clip(0.55 * n + 0.45 * blades + grain(seed + 2, strength=0.18), 0, 1)
    rgb = colourise(v, dark, light)
    if dry:
        patch = np.clip((tile_noise(seed + 5, base=3) - 0.5) * 4 + dry, 0, 1)[..., None]
        rgb = rgb * (1 - patch) + colourise(v, (96, 84, 50), (168, 150, 96)) * patch
    return rgba(rgb)


def verge(dry=0.3, dark=(34, 62, 22), light=(118, 150, 58)):
    # u=0 grass, u=1 gravel
    g = grass(24, dry=dry, dark=dark, light=light)[:, :, :3].astype(np.float32)
    n = tile_noise(31, octaves=6, base=16)
    gr = colourise(np.clip(n + grain(32, strength=0.35), 0, 1), (92, 84, 72), (176, 166, 148))
    u = np.linspace(0, 1, S, dtype=np.float32)[None, :].repeat(S, 0)
    edge = np.clip((u - 0.5 + (tile_noise(33, base=8) - 0.5) * 0.4) * 5, 0, 1)[..., None]
    return rgba(g * (1 - edge) + gr * edge)


def hillside(seed=40, dark=(28, 52, 22), light=(96, 128, 52), rock_dark=(70, 64, 58), rock_light=(150, 142, 130), rock=0.42):
    n = tile_noise(seed, octaves=6, base=4)
    rock_n = tile_noise(seed + 1, octaves=6, base=10)
    g = colourise(np.clip(0.6 * n + 0.4 * tile_noise(seed + 2, base=40) + grain(seed + 3, strength=0.15), 0, 1), dark, light)
    r = colourise(np.clip(rock_n + grain(seed + 4, strength=0.2), 0, 1), rock_dark, rock_light)
    m = np.clip((tile_noise(seed + 6, base=3) - (1.0 - rock)) * 6, 0, 1)[..., None]
    return rgba(g * (1 - m) + r * m)


def barrier():
    # concrete barrier with red/white chevron band on top
    n = tile_noise(50, octaves=6, base=12)
    rgb = colourise(np.clip(0.75 * n + grain(51, strength=0.2) + 0.1, 0, 1), (120, 118, 112), (200, 198, 190))
    v = np.linspace(0, 1, S, dtype=np.float32)[:, None].repeat(S, 1)
    u = np.linspace(0, 1, S, dtype=np.float32)[None, :].repeat(S, 0)
    stripe = (((u * 4 + v * 1.2) % 1.0) < 0.5).astype(np.float32)
    band = ((v > 0.08) & (v < 0.42)).astype(np.float32)
    rgb = paint(rgb, band * stripe, (196, 36, 30), 52)
    rgb = paint(rgb, band * (1 - stripe), (232, 232, 226), 53)
    # grime towards the base
    rgb *= (1.0 - 0.35 * np.clip((v - 0.7) / 0.3, 0, 1))[..., None]
    return rgba(rgb)


def clear():
    return np.zeros((S, S, 4), np.uint8)


def tree(seed=60, kind="broadleaf"):
    r = rng(seed)
    img = Image.new("L", (S, S), 0)
    d = ImageDraw.Draw(img)
    if kind == "pine":
        for i in range(9):
            y0 = 14 + i * 22
            half = 16 + i * 11
            d.polygon([(S // 2, y0 - 16), (S // 2 - half, y0 + 34), (S // 2 + half, y0 + 34)], fill=255)
    else:
        for _ in range(70):
            cx = S / 2 + r.normal(0, 46)
            cy = 96 + r.normal(0, 40)
            rad = r.uniform(16, 34)
            d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=255)
    crown = np.asarray(img.filter(ImageFilter.GaussianBlur(1.2)), np.float32) / 255.0
    crown = (crown * (0.55 + 0.6 * tile_noise(seed + 1, octaves=4, base=24)) > 0.42).astype(np.float32)
    trunk = np.zeros((S, S), np.float32)
    trunk[150:S, S // 2 - 7:S // 2 + 7] = 1
    leaf = tile_noise(seed + 2, octaves=5, base=20)
    v = np.linspace(0, 1, S, dtype=np.float32)[:, None].repeat(S, 1)
    shade = np.clip(leaf * 0.7 + 0.45 - v * 0.35 + grain(seed + 3, strength=0.2), 0, 1)
    if kind == "pine":
        lrgb = colourise(shade, (10, 34, 20), (58, 104, 52))
    else:
        lrgb = colourise(shade, (18, 46, 14), (104, 148, 50))
    trgb = colourise(np.clip(tile_noise(seed + 4, base=30) + grain(seed + 5, strength=0.3), 0, 1), (48, 34, 22), (104, 80, 54))
    alpha = np.maximum(crown, trunk)
    rgb = trgb * (1 - crown[..., None]) + lrgb * crown[..., None]
    # bleed colour into transparent texels so filtering does not show dark fringes
    return rgba(rgb, alpha * 255)


def _font(size):
    return ImageFont.load_default(size)


def sign(text, fg=(245, 245, 240), bg=(20, 28, 60), border=(245, 245, 240), size=120):
    img = Image.new("RGB", (S * 4, S), bg)
    d = ImageDraw.Draw(img)
    d.rectangle([6, 6, S * 4 - 7, S - 7], outline=border, width=8)
    f = _font(size)
    box = d.textbbox((0, 0), text, font=f)
    d.text(((S * 4 - (box[2] - box[0])) / 2 - box[0], (S - (box[3] - box[1])) / 2 - box[1]), text, font=f, fill=fg)
    img = img.resize((S, S), Image.LANCZOS)
    return rgba(np.asarray(img, np.float32))


def chevron(direction=1):
    """Corner marker board: arrows pointing right for direction=1."""
    img = Image.new("RGB", (S, S), (236, 196, 24))
    d = ImageDraw.Draw(img)
    for i in range(3):
        x = 14 + i * 82
        pts = [(x, 30), (x + 34, 30), (x + 76, S // 2), (x + 34, S - 30), (x, S - 30), (x + 42, S // 2)]
        if direction < 0:
            pts = [(S - px, py) for px, py in pts]
        d.polygon(pts, fill=(18, 18, 18))
    d.rectangle([0, 0, S - 1, S - 1], outline=(18, 18, 18), width=8)
    return rgba(np.asarray(img, np.float32))


def metal():
    n = tile_noise(70, octaves=5, base=24)
    return rgba(colourise(np.clip(n * 0.6 + 0.2 + grain(71, strength=0.1), 0, 1), (70, 74, 80), (170, 174, 180)))


def debug_orient():
    """F-shaped marker to verify texture orientation in engine screenshots."""
    img = Image.new("RGB", (S, S), (255, 0, 255))
    d = ImageDraw.Draw(img)
    d.text((40, 10), "F", font=_font(220), fill=(255, 255, 255))
    d.rectangle([0, 0, 40, 40], fill=(255, 0, 0))  # red = top-left
    d.rectangle([S - 40, 0, S - 1, 40], fill=(0, 255, 0))  # green = top-right
    return rgba(np.asarray(img, np.float32))
