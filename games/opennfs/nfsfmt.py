"""Writers for the classic PC racer file formats that LibOpenNFS parses.

Everything here is written from the parser source (LibOpenNFS, MIT): no retail file is read.
Formats: FSH/QFS (uncompressed SHPI), FRD + COL + CAN + HRZ (track), FCE + FEDATA + CARP + VIV (car).
All track coordinates passed in are *raw file space* (x mirrored relative to the engine world).
"""
import struct

import numpy as np


# --------------------------------------------------------------------------- FSH
def fsh(images, names=None):
    """images: list of HxWx4 uint8 RGBA arrays -> bytes of an uncompressed SHPI archive (32-bit ARGB)."""
    n = len(images)
    names = names or ["%04d" % i for i in range(n)]
    head = 16 + 8 * n
    blobs, offsets, pos = [], [], head
    for img in images:
        h, w = img.shape[:2]
        bgra = np.ascontiguousarray(img[:, :, [2, 1, 0, 3]])
        blob = struct.pack("<ihh4h", 0x7D, w, h, 0, 0, 0, 0) + bgra.tobytes()
        offsets.append(pos)
        blobs.append(blob)
        pos += len(blob)
    out = [struct.pack("<4sii4s", b"SHPI", pos, n, b"GIMX")]
    for name, off in zip(names, offsets):
        out.append(struct.pack("<4si", name.encode("ascii")[:4].ljust(4, b"\0"), off))
    return b"".join(out + blobs)


def fsh16(images, names=None):
    """images: list of HxWx4 uint8 RGBA arrays -> uncompressed SHPI archive, 16-bit ARGB 1:5:5:5."""
    n = len(images)
    names = names or ["%04d" % i for i in range(n)]
    head = 16 + 8 * n
    blobs, offsets, pos = [], [], head
    for img in images:
        h, w = img.shape[:2]
        v = img.astype(np.uint16)
        px = ((v[:, :, 3] >= 128).astype(np.uint16) << 15) | ((v[:, :, 0] >> 3) << 10) | ((v[:, :, 1] >> 3) << 5) | (v[:, :, 2] >> 3)
        blob = struct.pack("<ihh4h", 0x7E, w, h, 0, 0, 0, 0) + px.astype("<u2").tobytes()
        offsets.append(pos)
        blobs.append(blob)
        pos += len(blob)
    out = [struct.pack("<4sii4s", b"SHPI", pos, n, b"GIMX")]
    for name, off in zip(names, offsets):
        out.append(struct.pack("<4si", name.encode("ascii")[:4].ljust(4, b"\0"), off))
    return b"".join(out + blobs)


# --------------------------------------------------------------------------- FRD
def polygon(v, tex, flags=0, hs_texflags=0):
    return struct.pack("<4HHHBB", v[0], v[1], v[2], v[3], tex, hs_texflags, flags, 0xF9)


def texblock(width, height, corners, qfs_index, is_lane=False):
    return struct.pack("<HHI8fIBH", width, height, 0, *corners, 0, 1 if is_lane else 0, qfs_index)


def fixed(p):
    return [int(round(float(c) * 65536.0)) for c in p]


class Block:
    """One track block. verts: (N,3) float raw coords; shading: N uint32 ARGB."""

    def __init__(self):
        self.verts = []
        self.shading = []
        self.road_polys = []  # (v4, tex, flags) -> polygon chunk 4 (high detail road + terrain)
        self.row_of_poly = []  # block-local position index per road poly
        self.objects = []  # list of [ (v4, tex, flags) ] -> polygon objects (block vertices)
        self.xobjs = []  # dict(ref=(x,y,z), verts=[], shading=[], polys=[(v4,tex,flags)])
        self.lights = []  # (pos, type)
        self.sounds = []
        self.centre = (0.0, 0.0, 0.0)
        self.neighbours = []
        self.start_pos = 0
        self.n_positions = 8
        self.vroad = []  # (normal3, forward3) per position
        self.polys_per_row = 0

    def add_vert(self, p, shade=0xFFFFFFFF):
        self.verts.append((float(p[0]), float(p[1]), float(p[2])))
        self.shading.append(shade & 0xFFFFFFFF)
        return len(self.verts) - 1


def _trkblock(b):
    v = np.asarray(b.verts, dtype="<f4")
    lo, hi = v.min(axis=0), v.max(axis=0)
    bounding = [(lo[0], b.centre[1], lo[2]), (hi[0], b.centre[1], lo[2]), (hi[0], b.centre[1], hi[2]), (lo[0], b.centre[1], hi[2])]
    n = len(b.verts)
    out = [struct.pack("<3f", *b.centre)]
    for p in bounding:
        out.append(struct.pack("<3f", *p))
    # nVertices, nHiResVert, nLoResVert, nMedResVert, nVerticesDup, nObjectVert
    out.append(struct.pack("<6I", n, n, n, n, n, n))
    out.append(v.tobytes())
    out.append(np.asarray(b.shading, dtype="<u4").tobytes())
    nbd = [(-1, 0)] * 0x12C
    for i, blk in enumerate(b.neighbours):
        nbd[i] = (blk, 0)
    out.append(b"".join(struct.pack("<hh", *e) for e in nbd))
    n_poly = len(b.road_polys)
    out.append(struct.pack("<8I", b.start_pos, b.n_positions, n_poly, len(b.vroad), len(b.xobjs), 0, len(b.sounds), len(b.lights)))
    for row in range(b.n_positions):  # PositionData
        out.append(struct.pack("<HBbhh", row * b.polys_per_row, min(b.polys_per_row, 255), 0, -1, -1))
    for row in b.row_of_poly:  # PolyVRoadData
        out.append(struct.pack("<BB6B", row, 0, 0, 0, 0, 0, 0, 0))
    for normal, forward in b.vroad:  # VRoadData
        vals = [int(round(c * 32767.0)) & 0xFFFF for c in (*normal, *forward)]
        out.append(struct.pack("<6H", *vals))
    for i, x in enumerate(b.xobjs):  # RefExtraObject
        out.append(struct.pack("<3iHHHbb", *fixed(x["ref"]), 0, i, 0, 0, 0))
    for pos, kind in b.sounds:
        out.append(struct.pack("<3iI", *fixed(pos), kind))
    for pos, kind in b.lights:
        out.append(struct.pack("<3iI", *fixed(pos), kind))
    return b"".join(out)


def _polyblock(b):
    out = []
    for chunk in range(7):
        polys = b.road_polys if chunk == 4 else []
        out.append(struct.pack("<I", len(polys)))
        if polys:
            out.append(struct.pack("<I", len(polys)))
            out.extend(polygon(*p) for p in polys)
    for chunk in range(4):
        objs = b.objects if chunk == 0 else []
        total = sum(len(o) for o in objs)
        out.append(struct.pack("<I", total))
        if total:
            out.append(struct.pack("<I", len(objs)))
            for o in objs:
                out.append(struct.pack("<II", 1, len(o)))
                out.extend(polygon(*p) for p in o)
    return b"".join(out)


def _xobjblock(xobjs):
    out = [struct.pack("<I", len(xobjs))]
    for i, x in enumerate(xobjs):
        out.append(struct.pack("<III", 4, i, 0))
        out.append(struct.pack("<3fI", *x["ref"], 0))
        out.append(struct.pack("<I", len(x["verts"])))
        out.append(np.asarray(x["verts"], dtype="<f4").tobytes())
        out.append(np.asarray(x["shading"], dtype="<u4").tobytes())
        out.append(struct.pack("<I", len(x["polys"])))
        out.extend(polygon(*p) for p in x["polys"])
    return b"".join(out)


def frd(blocks, texblocks):
    n = len(blocks)
    out = [b"\0" * 28, struct.pack("<I", n - 1)]
    out.extend(_trkblock(b) for b in blocks)
    out.extend(_polyblock(b) for b in blocks)
    # 4 extra-object blocks per track block (+1 global); the engine reads blocks 4b..4b+4 for block b,
    # so objects live in 4b+1 to appear exactly once.
    for b in blocks:
        out.append(_xobjblock([]))
        out.append(_xobjblock(b.xobjs))
        out.append(_xobjblock([]))
        out.append(_xobjblock([]))
    out.append(_xobjblock([]))
    out.append(struct.pack("<I", len(texblocks)))
    out.extend(texblocks)
    return b"".join(out)


# --------------------------------------------------------------------------- COL
def col(n_textures, vroad):
    """vroad: list of dict(pos, normal, forward, right, left_wall, right_wall) in raw space."""
    tex = b"".join(struct.pack("<4H", i, 0, 0, 0) for i in range(n_textures))
    tex_block = struct.pack("<IHH", 8 + len(tex), 2, n_textures) + tex

    def i8(v):
        return [max(-127, min(127, int(round(c * 127.0)))) for c in v] + [0]

    recs = []
    for v in vroad:
        recs.append(struct.pack("<3iI4b4b4bII", *fixed(v["pos"]), 0, *i8(v["normal"]), *i8(v["forward"]), *i8(v["right"]),
                                int(v["left_wall"] * 65536), int(v["right_wall"] * 65536)))
    vr = b"".join(recs)
    vr_block = struct.pack("<IHH", 8 + len(vr), 15, len(vroad)) + vr
    head_len = 16 + 8
    table = struct.pack("<II", head_len, head_len + len(tex_block))
    total = head_len + len(tex_block) + len(vr_block)
    return b"COLL" + struct.pack("<III", 11, total, 2) + table + tex_block + vr_block


# --------------------------------------------------------------------------- CAN / HRZ
def can(points):
    """points: list of (pos3 raw, quat4 floats in -1..1)."""
    body = b"".join(struct.pack("<3i4h", *fixed(p), *[int(round(q * 32767)) for q in quat]) for p, quat in points)
    return struct.pack("<HBBHH", 8 + len(body), 3, 0, len(points), 0) + body


def hrz(top, bottom):
    return ("/* horizon description for a synthetic track */\r\n"
            "/* r,g,b value at top of Gourad shaded SKY area */\r\n%d,%d,%d,\r\n"
            "/* r,g,b values for base of Gourad shaded SKY area */\r\n%d,%d,%d,\r\n" % (*top, *bottom)).encode("ascii")


# --------------------------------------------------------------------------- VIV
def viv(files):
    """files: list of (name, bytes) -> BIGF archive."""
    dir_len = 16 + sum(8 + len(n) + 1 for n, _ in files)
    pos, entries = dir_len, []
    for name, data in files:
        entries.append(struct.pack(">II", pos, len(data)) + name.encode("ascii") + b"\0")
        pos += len(data)
    return b"BIGF" + struct.pack(">III", pos, len(files), dir_len) + b"".join(entries) + b"".join(d for _, d in files)


# --------------------------------------------------------------------------- FCE (v3)
def fce(parts, dummies, colours, half_size):
    """parts: list of dict(name, centre, verts (N,3), normals (N,3), tris [(i0,i1,i2, flags, (u0,u1,u2,v0,v1,v2))]).
    dummies: list of (name, pos). colours: list of ((H,S,B,T) primary, (H,S,B,T) secondary), 0..255 each."""
    assert len(parts) <= 64 and len(dummies) <= 16 and len(colours) <= 16
    n_vert = sum(len(p["verts"]) for p in parts)
    n_tri = sum(len(p["tris"]) for p in parts)
    vert_off, norm_off, tri_off = 0, n_vert * 12, n_vert * 24
    end = tri_off + n_tri * 56

    def pad_vec(items, count):
        items = list(items) + [(0.0, 0.0, 0.0)] * (count - len(items))
        return b"".join(struct.pack("<3f", *v) for v in items)

    def pad_u32(items, count):
        items = list(items) + [0] * (count - len(items))
        return struct.pack("<%dI" % count, *items)

    def pad_names(names, count):
        names = list(names) + [""] * (count - len(names))
        return b"".join(n.encode("ascii")[:63].ljust(64, b"\0") for n in names)

    first_vert, first_tri, v_acc, t_acc = [], [], 0, 0
    for p in parts:
        first_vert.append(v_acc)
        first_tri.append(t_acc)
        v_acc += len(p["verts"])
        t_acc += len(p["tris"])

    def colour_table(idx):
        rows = [c[idx] for c in colours] + [(0, 0, 0, 0)] * (16 - len(colours))
        return b"".join(struct.pack("<4I", *r) for r in rows)

    head = [
        struct.pack("<10I", 0, n_tri, n_vert, 1, vert_off, norm_off, tri_off, end, end, end),
        struct.pack("<3f", *half_size),
        struct.pack("<I", len(dummies)), pad_vec([d[1] for d in dummies], 16),
        struct.pack("<I", len(parts)), pad_vec([p["centre"] for p in parts], 64),
        pad_u32(first_vert, 64), pad_u32([len(p["verts"]) for p in parts], 64),
        pad_u32(first_tri, 64), pad_u32([len(p["tris"]) for p in parts], 64),
        struct.pack("<I", len(colours)), colour_table(0),
        struct.pack("<I", len(colours)), colour_table(1),
        pad_names([d[0] for d in dummies], 16), pad_names([p["name"] for p in parts], 64),
        pad_u32([], 64),
    ]
    head = b"".join(head)
    assert len(head) == 0x1F04, hex(len(head))
    verts = b"".join(np.asarray(p["verts"], dtype="<f4").tobytes() for p in parts)
    norms = b"".join(np.asarray(p["normals"], dtype="<f4").tobytes() for p in parts)
    tris = []
    for p in parts:
        for i0, i1, i2, flags, uv in p["tris"]:
            tris.append(struct.pack("<I3I6HI6f", 0, i0, i1, i2, 0xFF00, 0xFF00, 0xFF00, 0xFF00, 0xFF00, 0xFF00, flags, *uv))
    return head + verts + norms + b"".join(tris)


# --------------------------------------------------------------------------- FEDATA / CARP
FEDATA_FIELDS = ["manufacturer", "model", "car_name", "price", "status", "weight", "weight_distribution", "length", "width",
                 "height", "engine", "displacement", "horse_power", "torque", "maximum_rpm", "brakes", "tires", "top_speed",
                 "zero_to_sixty", "zero_to_one_hundred", "transmission", "gearbox"]


def fedata(car_id, info, history, colour_names, stats=(10, 10, 10, 10), vehicle_class=0, serial=0):
    strings = [info.get(k, "") for k in FEDATA_FIELDS]
    strings += (list(history) + [""] * 8)[:8]
    strings += (list(colour_names) + [""] * 10)[:10]
    assert len(strings) == 40
    head = car_id.encode("ascii")[:4].ljust(4, b" ")
    # flag count, bonus, ai, class, unknown1, dlc, police, seat, unknown2, unknown3, serial
    head += struct.pack("<11H", 9, 0, 1, vehicle_class, 3, 0, 0, 0, 1, 0, serial)
    head = head.ljust(40, b"\0")
    head += struct.pack("<5BB", stats[0], stats[1], stats[2], stats[3], 5, 40)
    head = head.ljust(47, b"\0")
    pos = 47 + 4 * 40
    table, blob = [], []
    for s in strings:
        data = s.encode("latin-1") + b"\0"
        table.append(struct.pack("<I", pos))
        blob.append(data)
        pos += len(data)
    return head + b"".join(table) + b"".join(blob)


def carp(entries):
    """entries: list of (label, entry number, value string)."""
    return "".join("%s(%d)\r\n%s\r\n" % (label, num, value) for label, num, value in entries).encode("ascii")


# --------------------------------------------------------------------------- TGA
def tga(img):
    """HxWx4 RGBA uint8 -> uncompressed 32-bit TGA (top-left origin)."""
    h, w = img.shape[:2]
    head = struct.pack("<BBBHHBHHHHBB", 0, 0, 2, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    return head + np.ascontiguousarray(img[:, :, [2, 1, 0, 3]]).tobytes()
