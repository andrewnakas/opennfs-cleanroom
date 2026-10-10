"""Original synthetic circuits written in the FRD/COL track format (no retail data involved).

Design space is the engine world (metres, y up, right = forward x up). Files store raw space,
which mirrors x (the loader multiplies by (-1, 1, 1)).
"""
import math
import os

import numpy as np

import nfsfmt
import proctex

SEG = 6.0  # metres between virtual road positions
ROWS = 8  # positions per block
# lateral column offsets (metres, + = right of travel) and what lies between them
COLS = [-48.0, -30.0, -18.0, -10.5, -8.5, -7.0, -3.5, 0.0, 3.5, 7.0, 8.5, 10.5, 18.0, 30.0, 48.0]
RAIL_D = 9.4

TEXTURES = ["road_outer", "road_inner", "start_line", "shoulder", "verge", "grass", "hill", "hill2", "barrier", "clear",
            "tree_a", "tree_b", "pine", "banner_a", "banner_b", "chev_r", "chev_l", "metal"]
TEX = {name: i for i, name in enumerate(TEXTURES)}

UV_N = [0, 0, 0, 1, 1, 1, 1, 0]  # v0 near-left, v1 far-left, v2 far-right, v3 near-right
UV_M = [1, 0, 1, 1, 0, 1, 0, 0]  # mirrored across the road
UV_B = [0, 1, 0, 0, 1, 0, 1, 1]  # upright board: v0 bottom-left, v1 top-left, v2 top-right, v3 bottom-right
UV_X = [1, 1, 1, 0, 0, 0, 0, 1]  # the same for extra objects, whose u the loader inverts

# Each circuit is a closed polar curve r(t) = radius + sum(a * cos(k t + p)) with a height profile of the same form.
TRACKS = {
    "trk100": dict(
        name="Cedar Ridge", blurb="Rolling hills, flowing bends", seed=7, radius=330.0,
        radial=[(70.0, 2, 0.6), (45.0, 3, 2.1), (18.0, 5, -1.27)], height=[(10.0, 1, -1.17), (5.0, 3, -0.57), (2.0, 5, 0.0)],
        hills=10.0, trees=9, tree_mix=(0.4, 0.3, 0.3), sky=((70, 120, 190), (190, 210, 225)),
        grass=dict(dry=0.15), hill=dict(), hill2=dict()),
    "trk101": dict(
        name="Harbor Loop", blurb="Flat out: long straights, fast sweepers", seed=21, radius=400.0,
        radial=[(150.0, 2, 0.2), (22.0, 4, 1.1), (10.0, 6, 0.4)], height=[(3.0, 1, 0.5), (1.5, 2, 2.0)],
        hills=5.0, trees=4, tree_mix=(0.55, 0.45, 0.0), sky=((80, 130, 200), (210, 215, 215)),
        grass=dict(dry=0.75, dark=(70, 78, 30), light=(170, 164, 84)),
        hill=dict(dark=(92, 90, 44), light=(186, 172, 104), rock_dark=(120, 108, 84), rock_light=(206, 192, 160), rock=0.5),
        hill2=dict(dark=(84, 86, 40), light=(176, 166, 100), rock_dark=(112, 102, 80), rock_light=(198, 186, 156), rock=0.6)),
    "trk102": dict(
        name="Granite Pass", blurb="Tight and twisty mountain road", seed=33, radius=250.0,
        radial=[(48.0, 2, 1.0), (40.0, 3, 0.2), (26.0, 4, 2.0), (14.0, 7, 0.9)], height=[(15.0, 1, 2.0), (7.0, 2, 0.3), (3.0, 4, 1.0)],
        hills=17.0, trees=11, tree_mix=(0.1, 0.1, 0.8), sky=((60, 105, 175), (180, 196, 214)),
        grass=dict(dry=0.05, dark=(26, 50, 26), light=(92, 126, 62)),
        hill=dict(dark=(30, 48, 28), light=(84, 108, 60), rock=0.62), hill2=dict(dark=(38, 44, 34), light=(96, 104, 80), rock=0.8)),
}


def build_textures(spec):
    p = proctex
    g = spec["grass"]
    verge_args = {k: v for k, v in g.items() if k in ("dark", "light")}
    imgs = {
        "road_outer": p.road_outer(), "road_inner": p.road_inner(), "start_line": p.start_line(), "shoulder": p.shoulder(),
        "verge": p.verge(dry=min(1.0, g.get("dry", 0.2) + 0.15), **verge_args), "grass": p.grass(20, **g),
        "hill": p.hillside(40, **spec["hill"]), "hill2": p.hillside(47, **spec["hill2"]),
        "barrier": p.barrier(), "clear": p.clear(), "tree_a": p.tree(60), "tree_b": p.tree(66), "pine": p.tree(72, "pine"),
        "banner_a": p.sign("START", size=170), "banner_b": p.sign("FINISH", size=170),
        "chev_r": p.chevron(1), "chev_l": p.chevron(-1), "metal": p.metal(),
    }
    return [imgs[n] for n in TEXTURES]


class TexTable:
    def __init__(self):
        self.blocks, self.index = [], {}

    def get(self, name, uv):
        key = (name, tuple(uv))
        if key not in self.index:
            self.index[key] = len(self.blocks)
            self.blocks.append(nfsfmt.texblock(proctex.S, proctex.S, uv, TEX[name]))
        return self.index[key]


def centreline(spec):
    """Closed circuit -> row centres, forward, right, signed curvature (engine space), spacing."""
    th = np.linspace(0.0, 2.0 * math.pi, 60000, endpoint=False)
    r = np.full_like(th, spec["radius"])
    for amp, k, phase in spec["radial"]:
        r += amp * np.cos(k * th + phase)
    y = np.zeros_like(th)
    for amp, k, phase in spec["height"]:
        y += amp * np.cos(k * th + phase)
    x, z = r * np.cos(th), r * np.sin(th)
    d = np.hypot(np.diff(x, append=x[0]), np.diff(z, append=z[0]))
    s = np.concatenate([[0.0], np.cumsum(d)])
    length = s[-1]
    n = int(length / SEG / ROWS) * ROWS
    targets = np.arange(n) * (length / n)
    idx = np.searchsorted(s, targets, side="right") - 1
    frac = (targets - s[idx]) / d[idx]
    nxt = (idx + 1) % len(th)
    pos = np.stack([x[idx] + (x[nxt] - x[idx]) * frac, y[idx] + (y[nxt] - y[idx]) * frac, z[idx] + (z[nxt] - z[idx]) * frac], axis=1)
    fwd = np.roll(pos, -1, axis=0) - np.roll(pos, 1, axis=0)
    fwd /= np.linalg.norm(fwd, axis=1)[:, None]
    right = np.cross(fwd, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right, axis=1)[:, None]
    # signed curvature in plan view: positive = turning right
    # (turning right moves forward towards right = forward x up, which makes cross(prev, next).y negative)
    curv = -np.cross(np.roll(fwd, 1, axis=0), np.roll(fwd, -1, axis=0))[:, 1] / (2.0 * length / n)
    curv = np.convolve(np.concatenate([curv[-4:], curv, curv[:4]]), np.ones(9) / 9.0, mode="valid")
    return pos, fwd, right, curv, length / n


def generate(track_id, out_dir):
    spec = TRACKS[track_id]
    rnd = np.random.default_rng(spec["seed"])
    pos, fwd, right, curv, seg = centreline(spec)
    n = len(pos)
    n_blocks = n // ROWS
    up = np.array([0.0, 1.0, 0.0])
    cols = np.array(COLS)
    ph = 2.0 * math.pi * np.arange(n) / n
    base_hill = spec["hills"]
    hill_l = base_hill * (1.0 + 0.6 * np.sin(3 * ph + 1.0) + 0.4 * np.sin(7 * ph + 2.2) + 0.2 * np.sin(13 * ph))
    hill_r = base_hill * (1.0 + 0.6 * np.sin(4 * ph + 4.0) + 0.4 * np.sin(6 * ph + 0.7) + 0.2 * np.sin(11 * ph + 1.3))
    hill_l, hill_r = np.maximum(hill_l, 0.8), np.maximum(hill_r, 0.8)
    bank = np.clip(curv * 5.5, -0.085, 0.085)  # tan(bank): road leans into the turn

    def lateral_height(i, d):
        """Height above the centreline of the ground at lateral offset d on row i."""
        i %= n
        hill = hill_r[i] if d > 0 else hill_l[i]
        a = abs(d)
        base = -bank[i] * max(-10.5, min(10.5, d))
        if a <= 8.5:
            return base
        if a <= 10.5:
            return base - 0.12 * (a - 8.5) / 2.0
        if a <= 18.0:
            return base - 0.12 + (0.08 * hill + 0.7) * (a - 10.5) / 7.5
        if a <= 30.0:
            t = (a - 18.0) / 12.0
            return base - 0.12 + (0.08 * hill + 0.7) + (0.36 * hill) * t
        t = min(1.0, (a - 30.0) / 18.0)
        return base - 0.12 + (0.44 * hill + 0.7) + (0.56 * hill) * t

    def clamp_inside(i, d):
        # keep the inside of tight corners from folding over itself
        i %= n
        if abs(curv[i]) > 1e-6 and d * curv[i] > 0:
            return math.copysign(min(abs(d), 0.8 / abs(curv[i])), d)
        return d

    def world(i, d, extra_h=0.0):
        i %= n
        return pos[i] + right[i] * clamp_inside(i, d) + up * (lateral_height(i, d) + extra_h)

    def raw(p):
        return (-float(p[0]), float(p[1]), float(p[2]))

    def shade(v):
        g = int(max(0, min(255, v)))
        return 0xFF000000 | (g << 16) | (g << 8) | g

    tex = TexTable()
    strip_tex = [  # per column strip, left to right
        ("hill2", UV_N), ("hill", UV_N), ("grass", UV_N), ("verge", UV_N), ("shoulder", UV_N), ("road_outer", UV_N), ("road_inner", UV_N),
        ("road_inner", UV_M), ("road_outer", UV_M), ("shoulder", UV_M), ("verge", UV_M), ("grass", UV_M), ("hill", UV_M), ("hill2", UV_M),
    ]
    blocks = []
    n_trees = n_signs = 0
    for b in range(n_blocks):
        blk = nfsfmt.Block()
        r0 = b * ROWS
        blk.start_pos, blk.n_positions = r0, ROWS
        blk.neighbours = [(b + k) % n_blocks for k in (0, 1, -1, 2, -2, 3, -3)]
        blk.polys_per_row = len(COLS) - 1
        centre = pos[[(r0 + k) % n for k in range(ROWS + 1)]].mean(axis=0)
        blk.centre = raw(centre)
        grid = {}
        for r in range(ROWS + 1):
            i = r0 + r
            for c, d in enumerate(cols):
                # deterministic per-vertex tone so the shared edge of two blocks matches
                tone = math.sin((i % n) * 12.9898 + c * 78.233) * 43758.5453
                tone = (tone - math.floor(tone)) * 16.0 - 8.0
                dark = 232 - 26 * min(1.0, abs(d) / 48.0) + tone * (abs(d) > 8.5)
                grid[(r, c)] = blk.add_vert(raw(world(i, d)), shade(dark))
        for r in range(ROWS):
            for c in range(len(COLS) - 1):
                name, uv = strip_tex[c]
                if (r0 + r) % n == 0 and name.startswith("road"):
                    name = "start_line"
                # winding chosen so the loader's quad normal points up in raw space
                quad = (grid[(r, c)], grid[(r + 1, c)], grid[(r + 1, c + 1)], grid[(r, c + 1)])
                blk.road_polys.append((quad, tex.get(name, uv), 0))
                blk.row_of_poly.append(r)
            i = (r0 + r) % n
            blk.vroad.append(((0.0, 1.0, 0.0), raw(fwd[i])))
        # barriers: visible concrete, plus an invisible extension so nothing vaults it
        for side in (-1, 1):
            d = side * RAIL_D
            vis, inv, ids = [], [], []
            for r in range(ROWS + 1):
                i = r0 + r
                ids.append((blk.add_vert(raw(world(i, d, -0.3)), shade(170)), blk.add_vert(raw(world(i, d, 0.85)), shade(235)),
                            blk.add_vert(raw(world(i, d, 5.0)), shade(255))))
            for r in range(ROWS):
                lo0, top0, sky0 = ids[r]
                lo1, top1, sky1 = ids[r + 1]
                vis.append(((lo0, top0, top1, lo1), tex.get("barrier", UV_B), 0x20))
                inv.append(((top0, sky0, sky1, top1), tex.get("clear", UV_B), 0x20))
            blk.objects.append(vis)
            blk.objects.append(inv)

        def board(axis, width, height, name, uv=UV_X, y0=0.0, shift=0.0):
            axis = np.asarray(axis, dtype=np.float64)
            half = axis * (width / 2.0)
            centre = axis * shift
            lift0, lift1 = up * y0, up * (y0 + height)
            pts = [centre - half + lift0, centre - half + lift1, centre + half + lift1, centre + half + lift0]
            return [raw(p) for p in pts], name, uv

        def add_xobj(base, boards, light=235):
            verts, shading, polys = [], [], []
            for pts, name, uv in boards:
                k = len(verts)
                verts.extend(pts)
                shading.extend([shade(light)] * 4)
                polys.append(((k, k + 1, k + 2, k + 3), tex.get(name, uv), 0))
            blk.xobjs.append(dict(ref=raw(base), verts=verts, shading=shading, polys=polys))

        # scenery: trees as crossed boards
        for _ in range(spec["trees"]):
            r = int(rnd.integers(0, ROWS))
            side = -1 if rnd.random() < 0.5 else 1
            d = side * rnd.uniform(13.0, 44.0)
            i = r0 + r
            kind = rnd.choice(["tree_a", "tree_b", "pine"], p=spec["tree_mix"])
            h = rnd.uniform(8.0, 13.0) if kind == "pine" else rnd.uniform(6.5, 10.0)
            light = int(rnd.uniform(190, 245))
            if abs(clamp_inside(i, d)) < abs(d) - 0.01:
                continue  # would stand in the folded inside of a tight bend
            base = world(i, d, -0.2)
            w = h * (0.55 if kind == "pine" else 0.9)
            add_xobj(base, [board((1, 0, 0), w, h, kind), board((0, 0, 1), w, h, kind)], light=light)
            n_trees += 1

        # corner marker boards on the outside of bends, facing oncoming traffic
        for r in range(0, ROWS, 2):
            i = (r0 + r) % n
            if abs(curv[i]) < 1.0 / 140.0:
                continue
            outside = -1.0 if curv[i] > 0 else 1.0
            base = world(i, outside * 12.0, 0.0)
            name = "chev_r" if curv[i] > 0 else "chev_l"
            add_xobj(base, [board(right[i], 3.2, 1.1, name, y0=0.9), board(right[i], 0.18, 0.9, "metal", y0=0.0)])
            n_signs += 1

        if b == 0:  # start/finish gantry: two banner halves and two posts
            base = world(0, 0.0, 0.0)
            span = RAIL_D + 0.5
            boards = [board(right[0], span, 2.0, "banner_a", y0=6.0, shift=-span / 2.0),
                      board(right[0], span, 2.0, "banner_b", y0=6.0, shift=span / 2.0)]
            for side in (-1, 1):
                boards.append(board(right[0], 0.4, 8.0, "metal", shift=side * (span + 0.2)))
                boards.append(_shifted(board(fwd[0], 0.4, 8.0, "metal"), raw(right[0] * side * (span + 0.2))))
            add_xobj(base, boards, light=250)
        blocks.append(blk)

    vroad = []
    for i in range(n):
        vroad.append(dict(pos=raw(pos[i]), normal=(0.0, 1.0, 0.0), forward=raw(fwd[i]), right=raw(right[i]),
                          left_wall=RAIL_D - 0.6, right_wall=RAIL_D - 0.6))

    # opening camera sweep: a slow arc above the start line
    cam = []
    for k in range(60):
        a = k / 59.0
        p = pos[0] - fwd[0] * (40.0 - 30.0 * a) + right[0] * (18.0 * math.cos(a * math.pi)) + up * (10.0 - 6.0 * a)
        cam.append((raw(p), (0.0, 0.0, 0.0, 1.0)))

    os.makedirs(out_dir, exist_ok=True)
    stem = track_id.replace("k0", "", 1)  # the loader's naming rule for this track generation
    files = {
        stem + ".frd": nfsfmt.frd(blocks, tex.blocks),
        stem + ".col": nfsfmt.col(len(TEXTURES), vroad),
        stem + "00a.can": nfsfmt.can(cam),
        "3" + stem + ".hrz": nfsfmt.hrz(*spec["sky"]),
        "speedsf.bin": bytes([150]) * n,
        stem + "0.qfs": nfsfmt.fsh(build_textures(spec)),
    }
    total = 0
    for name, data in files.items():
        with open(os.path.join(out_dir, name), "wb") as fh:
            fh.write(data)
        total += len(data)
    min_radius = 1.0 / np.abs(curv).max()
    print("track %s %-13s %4d positions, %4.0f m lap, %2d blocks, %3d trees, %2d signs, min radius %3.0f m, height %+.0f..%+.0f m, %.1f MB" % (
        track_id, spec["name"], n, n * seg, n_blocks, n_trees, n_signs, min_radius, pos[:, 1].min(), pos[:, 1].max(), total / 1e6))
    return dict(id=track_id, name=spec["name"], blurb=spec["blurb"], length_m=int(round(n * seg)), positions=n)


def _shifted(board_tuple, offset):
    pts, name, uv = board_tuple
    return [(p[0] + offset[0], p[1] + offset[1], p[2] + offset[2]) for p in pts], name, uv


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "D:/n64work/opennfs/clean/resources/NFS_3/gamedata/tracks"
    for tid in TRACKS:
        generate(tid, os.path.join(root, tid))
