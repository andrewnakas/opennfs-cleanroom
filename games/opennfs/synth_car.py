"""Original generic cars written in the FCE/VIV car format. No real make, badge or livery; no retail data.

Design space is the engine's chassis frame (metres, y up, z forward, +x = left). The file stores raw
coordinates: the loader multiplies by (-1.2, 1.2, 1.2).
"""
import math
import os

import numpy as np

import nfsfmt

SCALE = np.array([-1.2, 1.2, 1.2])

# texture atlas: flat swatches, 4x4 cells. Alpha encodes the role for the car shader:
# 128 = tinted by the body colour, 255 = drawn as is.
SWATCH = {
    "paint": (0, 0, (236, 236, 236), 128), "paint_dark": (1, 0, (178, 178, 178), 128), "glass": (2, 0, (26, 38, 52), 255),
    "black": (3, 0, (14, 14, 16), 255), "head": (0, 1, (250, 246, 220), 255), "tail": (1, 1, (200, 20, 20), 255),
    "tyre": (2, 1, (24, 24, 26), 255), "rim": (3, 1, (188, 192, 198), 255), "under": (0, 2, (8, 8, 9), 255),
    "grille": (1, 2, (30, 32, 36), 255), "amber": (2, 2, (240, 150, 20), 255), "chrome": (3, 2, (210, 214, 220), 255),
}
ATLAS = 64


def atlas_image():
    img = np.zeros((ATLAS, ATLAS, 4), np.uint8)
    cell = ATLAS // 4
    for cx, cy, rgb, a in SWATCH.values():
        img[cy * cell:(cy + 1) * cell, cx * cell:(cx + 1) * cell, :3] = rgb
        img[cy * cell:(cy + 1) * cell, cx * cell:(cx + 1) * cell, 3] = a
    img[3 * cell:, :, :3] = 128
    img[3 * cell:, :, 3] = 255
    return img


def swatch_uv(name):
    cx, cy, _, _ = SWATCH[name]
    return ((cx + 0.5) / 4.0, (cy + 0.5) / 4.0)


class Mesh:
    """Triangle soup with per-material smoothing (vertices welded by position within a material)."""

    def __init__(self):
        self.verts, self.index, self.tris = [], {}, []

    def _v(self, p, mat):
        key = (round(float(p[0]), 4), round(float(p[1]), 4), round(float(p[2]), 4), mat)
        if key not in self.index:
            self.index[key] = len(self.verts)
            self.verts.append(np.array(p, dtype=np.float64))
        return self.index[key]

    def tri(self, a, b, c, mat):
        ia, ib, ic = self._v(a, mat), self._v(b, mat), self._v(c, mat)
        if len({ia, ib, ic}) == 3:
            self.tris.append((ia, ib, ic, mat))

    def quad(self, a, b, c, d, mat):
        self.tri(a, b, c, mat)
        self.tri(a, c, d, mat)

    def normals(self, origin=(0.0, 0.0, 0.0)):
        verts = np.array(self.verts)
        normals = np.zeros_like(verts)
        origin = np.asarray(origin)
        for i0, i1, i2, _ in self.tris:
            n = np.cross(verts[i1] - verts[i0], verts[i2] - verts[i0])
            # orient each face away from the part's axis so welded vertices get consistent normals
            centre = (verts[i0] + verts[i1] + verts[i2]) / 3.0 - origin
            if np.dot(n, centre) < 0:
                n = -n
            for i in (i0, i1, i2):
                normals[i] += n
        length = np.linalg.norm(normals, axis=1)
        return normals / np.where(length < 1e-9, 1.0, length)[:, None]

    def part(self, name, centre):
        verts = np.array(self.verts)
        normals = self.normals()
        tris = []
        for i0, i1, i2, mat in self.tris:
            u, v = swatch_uv(mat)
            tris.append((i0, i1, i2, 0, (u, u, u, 1.0 - v, 1.0 - v, 1.0 - v)))
        return dict(name=name, centre=tuple(np.array(centre) / SCALE), verts=verts / SCALE,
                    normals=normals * np.array([-1.0, 1.0, 1.0]), tris=tris)


def interpolate_profile(stations, z):
    """Side profile at z -> (y_bottom, y_belt, y_top, half_width, roof_half_width or None)."""
    st = sorted(stations, key=lambda t: -t[0])
    if z >= st[0][0]:
        return st[0][1:]
    if z <= st[-1][0]:
        return st[-1][1:]
    for a, b in zip(st[:-1], st[1:]):
        if a[0] >= z >= b[0]:
            t = (a[0] - z) / (a[0] - b[0]) if a[0] != b[0] else 0.0
            vals = [a[i] + (b[i] - a[i]) * t for i in range(1, 5)]
            ra, rb = a[5], b[5]
            if ra is None and rb is None:
                roof = None
            else:  # pillar: the glass edge runs from the body shoulder to the roof edge
                ra = a[4] * 0.88 if ra is None else ra
                rb = b[4] * 0.88 if rb is None else rb
                roof = ra + (rb - ra) * t
            return (*vals, roof)
    return st[-1][1:]


def box(m, centre, half, mat):
    cx, cy, cz = centre
    hx, hy, hz = half
    c = [np.array([cx + sx * hx, cy + sy * hy, cz + sz * hz]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    for a, b, d, e in ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4), (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5)):
        m.quad(c[a], c[b], c[d], c[e], mat)


def loft_body(stations, axles, wheel_y, wheel_radius):
    """stations: (z, y_bottom, y_belt, y_top, half_width, roof_half_width or None), front first.
    axles: z of the front and rear axle. Wheel arches are cut into the lower body around them."""
    m = Mesh()
    arch_r = wheel_radius * 1.22
    tall = [s[0] for s in stations if s[5] is not None]
    roof_front, roof_rear = max(tall), min(tall)
    order = [s[0] for s in stations]
    glass_front = order[order.index(roof_front) - 1]  # base of the windscreen
    glass_rear = order[order.index(roof_rear) + 1]  # base of the rear window
    zs = {round(s[0], 4) for s in stations}
    for za in axles:
        for k in (-1.0, -0.82, -0.5, 0.0, 0.5, 0.82, 1.0):
            zs.add(round(za + arch_r * k, 4))
    z_front, z_rear = stations[0][0], stations[-1][0]
    zs = sorted((z for z in zs if z_rear <= z <= z_front), reverse=True)

    def arch_lift(z):
        for za in axles:
            dz = abs(z - za)
            if dz <= arch_r + 1e-6:
                return wheel_y + math.sqrt(max(arch_r * arch_r - dz * dz, 0.0))
        return None

    def ring(z):
        yb, ybelt, yt, hw, rhw = interpolate_profile(stations, z)
        top_hw = rhw if rhw is not None else hw * 0.88
        crown = 0.03 if rhw is not None else 0.02
        lift = arch_lift(z)
        xin = hw * 0.60
        arch = lift is not None and lift > yb + 0.02
        if arch:
            lift = min(lift, ybelt - 0.03)  # never above the shoulder of the body
            c, d = np.array([xin, lift, z]), np.array([hw, lift, z])
        else:
            c, d = np.array([hw * 0.93, yb, z]), np.array([hw, yb + 0.10, z])
        y_mid = min(max(d[1] + 0.02, (yb + 0.10 + ybelt) / 2.0), ybelt - 0.01)
        pts = [np.array([0.0, yb, z]), np.array([xin, yb, z]), c, d, np.array([hw * 1.012, y_mid, z]), np.array([hw * 0.985, ybelt, z]),
               np.array([top_hw, yt, z]), np.array([0.0, yt + crown, z])]
        return pts, arch

    rings = [ring(z) for z in zs]
    for sign in (1.0, -1.0):
        mirror = np.array([sign, 1.0, 1.0])
        for (ra, arch_a), (rb, arch_b), za, zb in zip(rings[:-1], rings[1:], zs[:-1], zs[1:]):
            arch = arch_a or arch_b
            mid = (za + zb) / 2.0
            glazed = glass_rear < mid < glass_front
            roof = roof_rear < mid < roof_front
            mats = ["under", "black" if arch else "under", "black" if arch else "under", "paint_dark", "paint",
                    "glass" if glazed else "paint", "paint" if (roof or not glazed) else "glass"]
            for k, mat in enumerate(mats):
                m.quad(ra[k] * mirror, ra[k + 1] * mirror, rb[k + 1] * mirror, rb[k] * mirror, mat)
        for (r, _), z, is_front in ((rings[0], zs[0], True), (rings[-1], zs[-1], False)):  # end caps
            yb, ybelt, yt, hw, _ = interpolate_profile(stations, z)
            mid = np.array([0.0, (yb + yt) / 2.0, z])
            for k in range(7):
                m.tri(mid, r[k] * mirror, r[k + 1] * mirror, "paint_dark" if k < 4 else "paint")
            # lamps and grille sit just proud of the cap
            zc = z + (0.012 if is_front else -0.012)
            y_lamp = yt - 0.10
            x0, x1 = hw * 0.40, hw * 0.93
            m.quad(np.array([x0, y_lamp - 0.055, zc]) * mirror, np.array([x1, y_lamp - 0.04, zc]) * mirror,
                   np.array([x1, y_lamp + 0.045, zc]) * mirror, np.array([x0, y_lamp + 0.055, zc]) * mirror, "head" if is_front else "tail")
            gy0, gy1 = yb + 0.03, yb + (0.13 if is_front else 0.09)
            m.quad(np.array([0.0, gy0, zc]) * mirror, np.array([hw * 0.55, gy0, zc]) * mirror,
                   np.array([hw * 0.55, gy1, zc]) * mirror, np.array([0.0, gy1, zc]) * mirror, "grille" if is_front else "black")
        # door mirror
        _, ybelt, _, hw, _ = interpolate_profile(stations, glass_front)
        box(m, np.array([sign * (hw + 0.07), ybelt + 0.06, glass_front - 0.12]), (0.07, 0.045, 0.05), "paint")
    return m


def add_spoiler(m, z, y, half_width):
    box(m, np.array([0.0, y + 0.17, z]), (half_width, 0.018, 0.12), "paint_dark")
    for sx in (-1, 1):
        box(m, np.array([sx * half_width * 0.72, y + 0.08, z]), (0.025, 0.08, 0.06), "black")


def wheel(radius, width, segments=16):
    m = Mesh()
    hw = width / 2.0
    rim = radius * 0.64
    for k in range(segments):
        a0, a1 = 2 * math.pi * k / segments, 2 * math.pi * (k + 1) / segments
        c0, s0, c1, s1 = math.cos(a0), math.sin(a0), math.cos(a1), math.sin(a1)

        def p(x, r, c, s):
            return np.array([x, r * s, r * c])
        m.quad(p(-hw, radius, c0, s0), p(hw, radius, c0, s0), p(hw, radius, c1, s1), p(-hw, radius, c1, s1), "tyre")
        for x in (-hw, hw):
            m.quad(p(x, radius, c0, s0), p(x, radius, c1, s1), p(x, rim, c1, s1), p(x, rim, c0, s0), "tyre")
            spoke = "rim" if (k % 4) < 3 else "grille"
            m.tri(np.array([x * 0.86, 0.0, 0.0]), p(x * 0.86, rim, c0, s0), p(x * 0.86, rim, c1, s1), spoke)
    return m


CARS = {
    # generic two-door coupe
    "cgt1": dict(
        name="Clean Coupe", maker="Cleanroom Motors", klass=1, mass=1380, top_speed=72.0, brake=11.0,
        stations=[(2.20, -0.36, -0.20, -0.16, 0.70, None), (2.05, -0.50, -0.14, -0.08, 0.86, None), (1.60, -0.55, -0.04, 0.02, 0.92, None),
                  (1.00, -0.55, 0.06, 0.10, 0.925, None), (0.75, -0.55, 0.10, 0.14, 0.925, None), (0.10, -0.55, 0.14, 0.52, 0.925, 0.60),
                  (-0.75, -0.55, 0.16, 0.55, 0.925, 0.60), (-1.50, -0.55, 0.20, 0.24, 0.92, None), (-2.00, -0.50, 0.18, 0.22, 0.88, None),
                  (-2.20, -0.36, 0.10, 0.16, 0.74, None)],
        wheel_radius=0.33, wheel_width=0.24, axle_z=(1.32, -1.30), track=0.80, wheel_y=-0.37),
    # a taller, boxier hatchback
    "hat1": dict(
        name="Clean Hatch", maker="Cleanroom Motors", klass=2, mass=1150, top_speed=58.0, brake=10.0,
        stations=[(1.95, -0.42, -0.22, -0.14, 0.68, None), (1.80, -0.55, -0.14, -0.04, 0.82, None), (1.35, -0.60, -0.02, 0.06, 0.86, None),
                  (0.95, -0.60, 0.04, 0.10, 0.86, None), (0.70, -0.60, 0.08, 0.14, 0.86, None), (0.20, -0.60, 0.12, 0.60, 0.86, 0.62),
                  (-1.30, -0.60, 0.14, 0.62, 0.86, 0.62), (-1.82, -0.58, 0.16, 0.22, 0.84, None), (-1.95, -0.44, 0.08, 0.14, 0.72, None)],
        wheel_radius=0.31, wheel_width=0.21, axle_z=(1.22, -1.20), track=0.75, wheel_y=-0.44),
    # low wedge-shaped sports car
    "wdg1": dict(
        name="Clean Wedge", maker="Cleanroom Motors", klass=0, mass=1250, top_speed=86.0, brake=12.5,
        stations=[(2.25, -0.36, -0.26, -0.22, 0.72, None), (2.05, -0.46, -0.16, -0.10, 0.90, None), (1.55, -0.50, 0.00, 0.05, 0.97, None),
                  (0.95, -0.50, 0.03, 0.07, 0.98, None), (0.70, -0.50, 0.05, 0.09, 0.98, None), (-0.10, -0.50, 0.08, 0.48, 0.98, 0.58),
                  (-0.65, -0.50, 0.10, 0.50, 0.98, 0.58), (-1.45, -0.50, 0.20, 0.26, 0.98, None), (-2.05, -0.46, 0.22, 0.28, 0.94, None),
                  (-2.25, -0.34, 0.14, 0.22, 0.80, None)],
        wheel_radius=0.33, wheel_width=0.28, axle_z=(1.36, -1.32), track=0.84, wheel_y=-0.35, spoiler=True),
}

COLOURS = [  # name, (H, S, B, T) 0..255
    ("Signal Red", (0, 225, 205, 255)), ("Cobalt Blue", (156, 215, 190, 255)), ("Sunflower", (34, 225, 235, 255)),
    ("Pearl White", (0, 0, 240, 255)), ("Graphite", (0, 0, 70, 255)), ("Racing Green", (96, 200, 110, 255)),
    ("Tangerine", (18, 235, 240, 255)), ("Silver", (150, 12, 185, 255)),
]
STATS = {0: (18, 19, 17, 18), 1: (14, 14, 14, 14), 2: (9, 9, 12, 10)}  # accel, speed, handling, brakes per class


def build_meshes(shape_id):
    """-> [(mesh, centre, name)]: body first, then the four wheels (front left, front right, rear left, rear right)."""
    c = CARS[shape_id]
    r = c["wheel_radius"]
    body = loft_body(c["stations"], c["axle_z"], c["wheel_y"], r)
    if c.get("spoiler"):
        rear = c["stations"][-2]
        add_spoiler(body, rear[0] + 0.05, rear[3], rear[4] * 0.9)
    out = [(body, (0.0, 0.0, 0.0), "body")]
    # left is +x in the chassis frame (forward +z, up +y)
    for label, x_sign, z in (("fl", 1, c["axle_z"][0]), ("fr", -1, c["axle_z"][0]), ("rl", 1, c["axle_z"][1]), ("rr", -1, c["axle_z"][1])):
        out.append((wheel(r, c["wheel_width"]), (x_sign * c["track"], c["wheel_y"], z), "wheel_" + label))
    return out


def build_car(shape_id, out_dir, car_id=None):
    c = CARS[shape_id]
    car_id = car_id or shape_id
    parts = [mesh.part(name, centre) for mesh, centre, name in build_meshes(shape_id)]
    hw = max(s[4] for s in c["stations"])
    front, rear = c["stations"][0], c["stations"][-1]
    dummies = [("HFLO", np.array([0.55, front[3] - 0.1, front[0]]) / SCALE), ("HFRE", np.array([-0.55, front[3] - 0.1, front[0]]) / SCALE),
               ("TRLN", np.array([0.55, rear[3] - 0.1, rear[0]]) / SCALE), ("TRRN", np.array([-0.55, rear[3] - 0.1, rear[0]]) / SCALE)]
    dummies = [(n, tuple(p)) for n, p in dummies]
    half = tuple(np.abs(parts[0]["verts"]).max(axis=0))
    fce = nfsfmt.fce(parts, dummies, [(hsbt, (0, 0, 40, 255)) for _, hsbt in COLOURS], half)
    length = c["stations"][0][0] - c["stations"][-1][0]
    info = dict(manufacturer=c["maker"], model=c["name"], car_name=c["name"], price="n/a", status="Original design",
                weight="%d kg" % c["mass"], weight_distribution="50/50", length="%.2f m" % length, width="%.2f m" % (2 * hw),
                height="1.25 m", engine="Generic", displacement="n/a", horse_power="n/a", torque="n/a", maximum_rpm="7000",
                brakes="Discs", tires="Generic", top_speed="%d km/h" % round(c["top_speed"] * 3.6), zero_to_sixty="n/a",
                zero_to_one_hundred="n/a", transmission="Rear wheel drive", gearbox="6 speed")
    fed = nfsfmt.fedata(car_id, info, ["An original car made for this project."], [n for n, _ in COLOURS], stats=STATS[c["klass"]],
                        vehicle_class=c["klass"])
    carp = nfsfmt.carp([
        ("Serial Number", 0, "1"), ("Car Classification", 1, str(c["klass"])), ("Mass [kg]", 2, "%d" % c["mass"]),
        ("Number of Gears (manual)", 3, "8"), ("Gear shift delay", 4, "6"),
        ("Engine minimum rpm", 12, "900"), ("Engine redline in rpm", 13, "7000"),
        ("Maximum velocity of car [m/s]", 14, "%.1f" % c["top_speed"]), ("Top speed cap [m/s]", 15, "%.1f" % c["top_speed"]),
        ("Maximum braking deceleration [m/s^2]", 18, "%.1f" % c["brake"]), ("Wheel base [m]", 24, "%.2f" % (c["axle_z"][0] - c["axle_z"][1])),
        ("Suspension stiffness", 64, "1.0"),
    ])
    files = [("car.fce", fce), ("fedata.eng", fed), ("carp.txt", carp), ("car00.tga", nfsfmt.tga(atlas_image()))]
    os.makedirs(out_dir, exist_ok=True)
    data = nfsfmt.viv(files)
    with open(os.path.join(out_dir, "car.viv"), "wb") as fh:
        fh.write(data)
    n_tri = sum(len(p["tris"]) for p in parts)
    print("car %s (%s): %d parts, %d triangles, %d bytes" % (car_id, c["name"], len(parts), n_tri, len(data)))


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "D:/n64work/opennfs/clean/resources/NFS_3/gamedata/carmodel"
    for cid in CARS:
        build_car(cid, os.path.join(root, cid))
