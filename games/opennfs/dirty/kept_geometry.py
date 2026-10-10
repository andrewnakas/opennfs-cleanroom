"""DIRTY ROOM. Turns a retail track's geometry files into kept-fact files.

The owner's scope keeps geometry, collision and road/AI spline data. A track geometry file also carries a
colour for every vertex (baked lighting), which is art, not geometry. This module walks the file layout
(known from the open-source parser) and replaces those colours with a coarse version: ONE average colour
per track block (and per scenery object), blended between neighbouring blocks so no seams show.
Vertex alpha is reduced to 2 bits. Everything else is copied unchanged.
"""
import struct

import numpy as np


def _coarse_alpha(shading):
    a = (shading >> 24) & 0xFF
    return (np.round(a.astype(np.float32) / 85.0).astype(np.uint32) * 85) << 24


def _mean_rgb(shading):
    if len(shading) == 0:
        return np.array([255.0, 255.0, 255.0])
    return np.array([((shading >> 16) & 0xFF).mean(), ((shading >> 8) & 0xFF).mean(), (shading & 0xFF).mean()])


def _pack(rgb, alpha_bits):
    rgb = np.clip(np.round(rgb), 0, 255).astype(np.uint32)
    return alpha_bits | (rgb[..., 0] << 16) | (rgb[..., 1] << 8) | rgb[..., 2]


def coarsen_frd(data):
    """-> (new bytes, facts dict). facts: number of blocks, vertex/polygon counts."""
    out = bytearray(data)
    pos = 28
    n_blocks = struct.unpack_from("<I", data, pos)[0] + 1
    pos += 4
    blocks = []  # (centre xyz, vert offset, shading offset, n vertices)
    n_poly_total = 0
    for _ in range(n_blocks):
        centre = struct.unpack_from("<3f", data, pos)
        pos += 12 + 48
        n_vert = struct.unpack_from("<I", data, pos)[0]
        pos += 24
        vert_off = pos
        pos += n_vert * 12
        shade_off = pos
        pos += n_vert * 4
        pos += 0x12C * 4
        n_start, n_positions, n_polygons, n_vroad, n_xobj, n_polyobj, n_sound, n_light = struct.unpack_from("<8I", data, pos)
        pos += 32
        pos += n_positions * 8 + n_polygons * 8 + n_vroad * 12 + n_xobj * 20 + n_polyobj * 20 + n_sound * 16 + n_light * 16
        blocks.append((np.array(centre), vert_off, shade_off, n_vert))
        n_poly_total += n_polygons
    for _ in range(n_blocks):  # polygon blocks: no colours, just skip
        for _chunk in range(7):
            sz = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            if sz:
                pos += 4 + sz * 14
        for _chunk in range(4):
            n1 = struct.unpack_from("<I", data, pos)[0]
            pos += 4
            if n1:
                n2 = struct.unpack_from("<I", data, pos)[0]
                pos += 4
                for _k in range(n2):
                    kind = struct.unpack_from("<I", data, pos)[0]
                    pos += 4
                    if kind == 1:
                        numpoly = struct.unpack_from("<I", data, pos)[0]
                        pos += 4 + numpoly * 14
    n_xobj_total = 0
    for _ in range(4 * n_blocks + 1):  # extra object blocks: one average colour per object
        nobj = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        for _k in range(nobj):
            crosstype = struct.unpack_from("<I", data, pos)[0]
            pos += 12
            if crosstype == 4:
                pos += 16
            elif crosstype == 3:
                pos += 18 + 2
                n_anim = struct.unpack_from("<H", data, pos)[0]
                pos += 4 + n_anim * 20
            else:
                raise ValueError("unknown extra object type %d" % crosstype)
            n_vert = struct.unpack_from("<I", data, pos)[0]
            pos += 4 + n_vert * 12
            shading = np.frombuffer(data, "<u4", n_vert, pos)
            new = _pack(np.tile(_mean_rgb(shading), (n_vert, 1)), _coarse_alpha(shading))
            out[pos:pos + n_vert * 4] = new.astype("<u4").tobytes()
            pos += n_vert * 4
            n_poly = struct.unpack_from("<I", data, pos)[0]
            pos += 4 + n_poly * 14
            n_xobj_total += 1
    n_tex = struct.unpack_from("<I", data, pos)[0]
    pos += 4 + n_tex * 47
    if pos != len(data):
        raise ValueError("layout walk ended at %d of %d bytes" % (pos, len(data)))

    # track blocks: one mean colour per block, blended along the track by distance to the block centres
    means = np.array([_mean_rgb(np.frombuffer(data, "<u4", n, s)) for (_, _, s, n) in blocks])
    centres = np.array([c for (c, _, _, _) in blocks])
    for b, (centre, vert_off, shade_off, n_vert) in enumerate(blocks):
        if n_vert == 0:
            continue
        verts = np.frombuffer(data, "<f4", n_vert * 3, vert_off).reshape(n_vert, 3)
        near = [(b - 1) % n_blocks, b, (b + 1) % n_blocks]
        d = np.stack([np.linalg.norm(verts - centres[k], axis=1) for k in near], axis=1)
        w = 1.0 / np.maximum(d, 1.0) ** 2
        w /= w.sum(axis=1, keepdims=True)
        rgb = w @ means[near]
        shading = np.frombuffer(data, "<u4", n_vert, shade_off)
        out[shade_off:shade_off + n_vert * 4] = _pack(rgb, _coarse_alpha(shading)).astype("<u4").tobytes()
    return bytes(out), dict(blocks=n_blocks, polygons=n_poly_total, extra_objects=n_xobj_total, textures=n_tex)


def coarsen_col(data):
    """-> (new bytes, facts dict with the lap length in metres from the virtual road)."""
    out = bytearray(data)
    if data[:4] != b"COLL":
        raise ValueError("not a COL file")
    n_blocks = struct.unpack_from("<I", data, 12)[0]
    pos = 16 + 4 * n_blocks
    size, xbid, nrec = struct.unpack_from("<IHH", data, pos)  # texture table
    pos += size
    n_struct = 0
    if n_blocks >= 4:
        block_start = pos
        size, xbid, nrec = struct.unpack_from("<IHH", data, pos)  # 3D structures
        p = pos + 8
        for _ in range(nrec):
            rec_size, n_vert, n_poly = struct.unpack_from("<IHH", data, p)
            v = p + 8
            shading = np.array([struct.unpack_from("<I", data, v + 16 * k + 12)[0] for k in range(n_vert)], dtype=np.uint32)
            new = _pack(np.tile(_mean_rgb(shading), (n_vert, 1)), _coarse_alpha(shading)) if n_vert else shading
            for k in range(n_vert):
                struct.pack_into("<I", out, v + 16 * k + 12, int(new[k]))
            p += rec_size
            n_struct += 1
        pos = block_start + size
        size, xbid, nrec = struct.unpack_from("<IHH", data, pos)  # objects
        pos += size
    if n_blocks == 5:
        size, xbid, nrec = struct.unpack_from("<IHH", data, pos)  # animated objects
        pos += size
    size, xbid, nrec = struct.unpack_from("<IHH", data, pos)  # virtual road
    if xbid != 15:
        raise ValueError("virtual road block not found")
    pts = np.array([struct.unpack_from("<3i", data, pos + 8 + 36 * k) for k in range(nrec)], dtype=np.float64) / 65536.0
    lap = float(np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1).sum()) if nrec > 1 else 0.0
    return bytes(out), dict(positions=nrec, lap_m=lap, structures=n_struct)
