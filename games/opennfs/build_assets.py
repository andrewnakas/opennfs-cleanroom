"""Generate the complete clean resource tree for the web build.

Everything is original (procedural) or CC0/permissively licensed; see assets/LICENSES.csv.
Nothing from the engine repository's bundled art or from any retail game is copied.

Usage: python games/opennfs/build_assets.py [out_root]
Layout written (matches what the engine expects relative to its working directory):
  <out>/resources/NFS_3/gamedata/{tracks,carmodel,render/pc}   synthetic track, cars, particle sheet
  <out>/resources/misc, <out>/resources/ui                        sky, fallback textures, UI
"""
import json
import math
import os
import shutil
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import nfsfmt  # noqa: E402
import proctex  # noqa: E402
import synth_car  # noqa: E402
import synth_track  # noqa: E402

OUT = sys.argv[1] if len(sys.argv) > 1 else "D:/n64work/opennfs/clean"
RES = os.path.join(OUT, "resources")


def save(img, path, mode=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    im = Image.fromarray(img) if isinstance(img, np.ndarray) else img
    if mode:
        im = im.convert(mode)
    im.save(path)


def lerp(a, b, t):
    return np.asarray(a, np.float32) * (1 - t) + np.asarray(b, np.float32) * t


def gradient_keys(keys, x):
    """keys: sorted [(pos, value array)], x in 0..1 -> interpolated value."""
    for (p0, v0), (p1, v1) in zip(keys[:-1], keys[1:]):
        if x <= p1:
            return lerp(v0, v1, 0.0 if p1 == p0 else (x - p0) / (p1 - p0))
    return np.asarray(keys[-1][1], np.float32)


def sky_tint(sun_side):
    """512x512: x = sun height (0 midnight, .5 horizon, 1 noon), row = height in sky (row 0 horizon)."""
    size = 512
    img = np.zeros((size, size, 4), np.float32)
    night = ((6, 8, 20), (2, 3, 10))
    dusk = ((250, 150, 70), (52, 62, 118)) if sun_side else ((150, 130, 150), (36, 46, 96))
    day = ((196, 220, 240), (52, 112, 200)) if sun_side else ((176, 206, 236), (46, 104, 196))
    for xi in range(size):
        x = xi / (size - 1)
        horizon = gradient_keys([(0.0, night[0]), (0.42, night[0]), (0.52, dusk[0]), (0.64, day[0]), (1.0, day[0])], x)
        zenith = gradient_keys([(0.0, night[1]), (0.42, night[1]), (0.52, dusk[1]), (0.64, day[1]), (1.0, day[1])], x)
        t = (np.arange(size, dtype=np.float32) / (size - 1)) ** 0.55
        img[:, xi, :3] = horizon[None, :] * (1 - t[:, None]) + zenith[None, :] * t[:, None]
    img[:, :, 3] = 255
    return img.astype(np.uint8)


def sun_tex():
    """x = distance from centre (0..1), row = sun height (row 0 low sun)."""
    size = 512
    img = np.zeros((size, size, 4), np.float32)
    r = np.arange(size, dtype=np.float32) / (size - 1)
    disc = np.clip((0.34 - r) / 0.03, 0, 1)
    glow = np.clip(1 - r, 0, 1) ** 2.2 * 0.75
    alpha = np.maximum(disc, glow)
    for yi in range(size):
        h = yi / (size - 1)
        col = gradient_keys([(0.0, (255, 120, 40)), (0.15, (255, 190, 110)), (0.4, (255, 244, 214)), (1.0, (255, 252, 240))], h)
        img[yi, :, :3] = col
        img[yi, :, 3] = alpha * 255
    return img.astype(np.uint8)


def moon_tex():
    size = 512
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.hypot(xx - size / 2, yy - size / 2) / (size * 0.36)
    disc = np.clip((1 - d) * 40, 0, 1)
    n = np.asarray(Image.fromarray((proctex.tile_noise(301, octaves=5, base=6) * 255).astype(np.uint8)).resize((size, size), Image.BICUBIC), np.float32) / 255
    shade = 150 + 90 * (n - 0.5) * 2
    r = np.random.default_rng(5)
    img = Image.fromarray(np.clip(shade, 0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    for _ in range(26):
        a, rad = r.uniform(0, 2 * math.pi), r.uniform(0, size * 0.33)
        cx, cy, cr = size / 2 + math.cos(a) * rad, size / 2 + math.sin(a) * rad, r.uniform(5, 26)
        dr.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=int(r.uniform(95, 140)))
    shade = np.asarray(img.filter(ImageFilter.GaussianBlur(2)), np.float32) * disc
    return np.stack([shade, shade, shade * 0.97], axis=2).astype(np.uint8)


def clouds_tex(seed, cover):
    """1024x512 coverage map (red channel used). Rows 256..511 map horizon..zenith of the dome."""
    w, h = 1024, 512
    n = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    r = np.random.default_rng(seed)
    for cells in (4, 8, 16, 32, 64):
        g = r.random((cells // 2, cells), dtype=np.float32)
        g = np.concatenate([g, g[:, :1]], axis=1)  # wrap in u
        layer = np.asarray(Image.fromarray((g * 255).astype(np.uint8)).resize((w + w // cells, h), Image.BICUBIC), np.float32)[:, :w] / 255
        n += layer * amp
        tot += amp
        amp *= 0.55
    n /= tot
    c = np.clip((n - (1 - cover)) / 0.22, 0, 1)
    # thin the clouds straight overhead a little and keep a soft band low on the horizon
    v = np.concatenate([np.zeros(h // 2), np.linspace(0, 1, h // 2)])[:, None]
    c *= (1.0 - 0.35 * v)
    g = (c * 255).astype(np.uint8)
    return np.stack([g, g, g], axis=2)


def env_map():
    """Sphere-map style reflection for car paint: sky above, dark ground below, bright horizon band."""
    s = 128
    img = np.zeros((s, s, 3), np.float32)
    for y in range(s):
        t = y / (s - 1)
        if t < 0.5:
            img[y] = lerp((70, 120, 200), (225, 236, 245), (t / 0.5) ** 1.6)
        else:
            img[y] = lerp((120, 112, 100), (36, 36, 40), ((t - 0.5) / 0.5) ** 0.7)
    n = np.asarray(Image.fromarray((proctex.tile_noise(88, octaves=4, base=4) * 255).astype(np.uint8)).resize((s, s), Image.BICUBIC), np.float32) / 255
    img[: s // 2] += (np.clip(n[: s // 2] - 0.55, 0, 1) * 260)[..., None]
    return np.clip(img, 0, 255).astype(np.uint8)


def sphere_obj(path, rings=14, sectors=28):
    lines = ["# unit sphere generated for the sky dome"]
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(sectors + 1):
            th = 2 * math.pi * s / sectors
            x, y, z = math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th)
            lines.append("v %.6f %.6f %.6f" % (x, y, z))
    for r in range(rings + 1):
        for s in range(sectors + 1):
            lines.append("vt %.6f %.6f" % (s / sectors, 1 - r / rings))
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(sectors + 1):
            th = 2 * math.pi * s / sectors
            lines.append("vn %.6f %.6f %.6f" % (math.sin(phi) * math.cos(th), math.cos(phi), math.sin(phi) * math.sin(th)))
    for r in range(rings):
        for s in range(sectors):
            a = r * (sectors + 1) + s + 1
            b, c, d = a + 1, a + sectors + 2, a + sectors + 1
            lines.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (a, a, a, b, b, b, c, c, c))
            lines.append("f %d/%d/%d %d/%d/%d %d/%d/%d" % (a, a, a, c, c, c, d, d, d))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")


def particle_sheet():
    """16 soft sprites (index 4 = light glow used by the engine's light billboards, 9+ = lane paint)."""
    s = 64
    yy, xx = np.mgrid[0:s, 0:s].astype(np.float32)
    d = np.hypot(xx - s / 2 + 0.5, yy - s / 2 + 0.5) / (s / 2)
    imgs = []
    for i in range(16):
        img = np.zeros((s, s, 4), np.float32)
        if i < 9:
            power = [1.0, 1.5, 2.0, 3.0, 2.2, 4.0, 0.7, 1.2, 2.6][i]
            a = np.clip(1 - d, 0, 1) ** power
            img[:, :, :3] = 255
            img[:, :, 3] = a * 255
        else:
            img[:, :, :3] = (232, 232, 224) if i % 2 else (228, 182, 40)
            img[:, s // 2 - 4:s // 2 + 4, 3] = 255
        imgs.append(img.astype(np.uint8))
    return imgs


def ui_images(root):
    # background pattern: subtle dark diagonal weave
    s = 128
    yy, xx = np.mgrid[0:s, 0:s]
    weave = (((xx + yy) // 8) % 2) * 10 + (((xx - yy) // 8) % 2) * 6
    bg = np.stack([14 + weave, 18 + weave, 26 + weave, np.full((s, s), 255)], axis=2).astype(np.uint8)
    save(bg, os.path.join(root, "bgGrillePattern.png"))

    def pill(w, h, fill, outline, name):
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle([2, 2, w - 3, h - 3], radius=h // 2 - 2, fill=fill, outline=outline, width=4)
        save(im, os.path.join(root, name))
    pill(512, 96, (26, 40, 70, 235), (240, 196, 40, 255), "pillButton.png")
    pill(512, 96, (20, 30, 52, 235), (160, 176, 200, 255), "dropdownButton.png")
    pill(512, 96, (30, 44, 74, 235), (90, 106, 130, 255), "dropdownEntry.png")
    curve = Image.new("RGBA", (512, 1024), (0, 0, 0, 0))
    d = ImageDraw.Draw(curve)
    d.ellipse([-900, -300, 440, 1324], fill=(16, 24, 44, 230), outline=(240, 196, 40, 255), width=6)
    save(curve, os.path.join(root, "leftMenuCurve.png"))
    logo = Image.new("RGBA", (512, 160), (0, 0, 0, 0))
    d = ImageDraw.Draw(logo)
    d.polygon([(10, 150), (70, 10), (502, 10), (442, 150)], fill=(240, 196, 40, 255))
    f = proctex._font(84)
    box = d.textbbox((0, 0), "OPEN ROAD", font=f)
    d.text(((512 - (box[2] - box[0])) / 2 - box[0], (160 - (box[3] - box[1])) / 2 - box[1]), "OPEN ROAD", font=f, fill=(16, 22, 40, 255))
    save(logo, os.path.join(root, "logo.png"))
    miss = np.zeros((16, 16, 4), np.uint8)
    miss[:, :, 3] = 255
    miss[:8, :8, 0] = miss[8:, 8:, 0] = 255
    miss[:8, :8, 2] = miss[8:, 8:, 2] = 255
    save(miss, os.path.join(root, "missingResource.png"))


def main():
    if os.path.isdir(RES):
        shutil.rmtree(RES)
    gamedata = os.path.join(RES, "NFS_3", "gamedata")
    tracks = [synth_track.generate(tid, os.path.join(gamedata, "tracks", tid)) for tid in synth_track.TRACKS]
    # circuits rebuilt from the dirty-room spec (kept geometry, regenerated textures), when the spec exists
    import clean_tracks
    kept_tracks = clean_tracks.main()
    for t in kept_tracks:
        t["blurb"] = "Classic circuit, rebuilt textures"
    tracks = kept_tracks + tracks
    for cid in synth_car.CARS:
        synth_car.build_car(cid, os.path.join(gamedata, "carmodel", cid))
    # the engine's asset scan expects the traffic and pursuit folders of the original layout
    synth_car.build_car("hat1", os.path.join(gamedata, "carmodel", "traffic", "tfc1"), car_id="tfc1")
    synth_car.build_car("cgt1", os.path.join(gamedata, "carmodel", "traffic", "pursuit", "ptl1"), car_id="ptl1")
    os.makedirs(os.path.join(gamedata, "render", "pc"), exist_ok=True)
    with open(os.path.join(gamedata, "render", "pc", "sfx.fsh"), "wb") as fh:
        fh.write(nfsfmt.fsh(particle_sheet()))

    misc = os.path.join(RES, "misc")
    sky = os.path.join(misc, "skydome")
    save(sky_tint(True), os.path.join(sky, "tint.tga"))
    save(sky_tint(False), os.path.join(sky, "tint2.tga"))
    save(sun_tex(), os.path.join(sky, "sun.tga"))
    save(moon_tex(), os.path.join(sky, "moon.tga"))
    save(clouds_tex(11, 0.46), os.path.join(sky, "clouds1.tga"))
    save(clouds_tex(12, 0.62), os.path.join(sky, "clouds2.tga"))
    sphere_obj(os.path.join(sky, "sphere.obj"))
    save(env_map(), os.path.join(misc, "sky_textures", "CHRD.BMP"))
    checker = Image.new("P", (2, 2))
    checker.putpalette([255, 0, 255, 0, 0, 0] + [0] * (254 * 3))
    checker.putdata([0, 1, 1, 0])
    save(checker, os.path.join(misc, "missing.bmp"))
    alpha = Image.new("P", (2, 2))
    alpha.putpalette([255, 255, 255] + [0] * (255 * 3))
    alpha.putdata([0, 0, 0, 0])
    save(alpha, os.path.join(misc, "missing-a.bmp"))
    racers = ["Ash", "Blue", "Comet", "Dash", "Ember", "Flint", "Gale", "Harbor", "Indigo", "Juniper", "Kite", "Lumen"]
    with open(os.path.join(misc, "racers.json"), "w", newline="\n") as fh:
        json.dump({"racers": [{"name": n} for n in racers]}, fh, indent=2)

    ui_images(os.path.join(RES, "ui", "menu", "images"))
    for sub in ("ui/fonts", "ui/menu/layout"):
        shutil.copytree(os.path.join(REPO, "assets", sub), os.path.join(RES, sub))
    shutil.copy(os.path.join(REPO, "assets", "ui", "menu", "resources.json"), os.path.join(RES, "ui", "menu", "resources.json"))

    # car list for the page's menu (the same facts as in the car files)
    import colorsys
    cars = []
    for cid, c in synth_car.CARS.items():
        cars.append(dict(id=cid, name=c["name"], top=round(c["top_speed"] * 3.6), mass=c["mass"],
                         stats=dict(zip(("accel", "speed", "handling", "brakes"), synth_car.STATS[c["klass"]]))))
    colours = []
    for name, (h, s, b, _) in synth_car.COLOURS:
        r, g, bl = colorsys.hsv_to_rgb((h / 255.0) % 1.0, s / 255.0, b / 255.0)
        colours.append(dict(name=name, rgb="#%02x%02x%02x" % (round(r * 255), round(g * 255), round(bl * 255))))
    os.makedirs(os.path.join(OUT, "page"), exist_ok=True)
    with open(os.path.join(OUT, "page", "cars.json"), "w", newline="\n") as fh:
        json.dump(dict(cars=cars, colours=colours, tracks=tracks), fh, indent=1)

    # manifest for the taint scan: the clean tree is exactly what was generated here
    import hashlib
    manifest = {}
    for d, _, fs in os.walk(RES):
        for f in fs:
            full = os.path.join(d, f)
            rel = os.path.relpath(full, OUT).replace("\\", "/")
            if "/tracks/trk0" in rel:
                kept = rel.endswith((".frd", ".col", ".can", "speedsf.bin"))
                source = "KEPT geometry from the dirty-room spec" if kept else "games/opennfs/clean_tracks.py"
            elif "/tracks/" in rel:
                source = "games/opennfs/synth_track.py"
            elif "/carmodel/" in rel:
                source = "games/opennfs/synth_car.py"
            elif "/ui/fonts/" in rel or rel.endswith("resources.json") or "/layout/" in rel:
                source = "assets/ui (see assets/LICENSES.csv)"
            else:
                source = "games/opennfs/build_assets.py"
            with open(full, "rb") as fh:
                manifest[rel] = dict(sha1=hashlib.sha1(fh.read()).hexdigest(), source=source)
    with open(os.path.join(OUT, "MANIFEST.json"), "w", newline="\n") as fh:
        json.dump(dict(files=manifest), fh, indent=1, sort_keys=True)

    total = sum(os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(RES) for f in fs)
    count = sum(len(fs) for _, _, fs in os.walk(RES))
    print("resources: %d files, %.1f MB -> %s" % (count, total / 1e6, RES))


if __name__ == "__main__":
    main()
