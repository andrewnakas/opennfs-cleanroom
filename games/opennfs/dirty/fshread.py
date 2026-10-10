"""DIRTY ROOM. Reads retail texture archives (QFS/FSH). Only extract_spec.py may import this module, and
only coarse facts computed from what it returns may leave the dirty room.

Written from the open-source parser (LibOpenNFS: QfsCompression.cpp, FshArchive.cpp, FshTexture.cpp).
"""
import struct

import numpy as np

BITMAP_CODES = {0x78, 0x7B, 0x7D, 0x7E, 0x7F, 0x6D, 0x60, 0x61, 0x40, 0x41}
PALETTE_CODES = {0x22, 0x23, 0x24, 0x29, 0x2A, 0x2D}


def refpack_decompress(data):
    """QFS / RefPack decompression."""
    if len(data) < 5 or (data[0] & 0xFE) != 0x10 or data[1] != 0xFB:
        return data
    out_size = (data[2] << 16) | (data[3] << 8) | data[4]
    out = bytearray(out_size)
    pos = 8 if data[0] & 1 else 5
    o = 0
    n = len(data)
    while pos < n and data[pos] < 0xFC:
        code = data[pos]
        if not code & 0x80:
            b1 = data[pos + 1]
            lit = code & 3
            out[o:o + lit] = data[pos + 2:pos + 2 + lit]
            pos += lit + 2
            o += lit
            length = ((code & 0x1C) >> 2) + 3
            offset = ((code >> 5) << 8) + b1 + 1
        elif not code & 0x40:
            b1, b2 = data[pos + 1], data[pos + 2]
            lit = (b1 >> 6) & 3
            out[o:o + lit] = data[pos + 3:pos + 3 + lit]
            pos += lit + 3
            o += lit
            length = (code & 0x3F) + 4
            offset = (b1 & 0x3F) * 256 + b2 + 1
        elif not code & 0x20:
            b1, b2, b3 = data[pos + 1], data[pos + 2], data[pos + 3]
            lit = code & 3
            out[o:o + lit] = data[pos + 4:pos + 4 + lit]
            pos += lit + 4
            o += lit
            length = ((code >> 2) & 3) * 256 + b3 + 5
            offset = ((code & 0x10) << 12) + 256 * b1 + b2 + 1
        else:
            lit = (code & 0x1F) * 4 + 4
            out[o:o + lit] = data[pos + 1:pos + 1 + lit]
            pos += lit + 1
            o += lit
            continue
        src = o - offset
        if offset >= length:
            out[o:o + length] = out[src:src + length]
        else:
            for k in range(length):
                out[o + k] = out[src + k]
        o += length
    if pos < n and o < out_size:
        lit = data[pos] & 3
        out[o:o + lit] = data[pos + 1:pos + 1 + lit]
    return bytes(out)


def _palette(data, offset):
    code, count = data[offset], struct.unpack_from("<h", data, offset + 4)[0]
    raw = data[offset + 16:]
    pal = np.zeros((256, 4), np.uint8)
    pal[:, 3] = 255
    count = max(0, min(count, 256))
    if code == 0x24:
        a = np.frombuffer(raw, np.uint8, count * 3).reshape(count, 3)
        pal[:count, :3] = a
    elif code == 0x22:
        a = np.frombuffer(raw, np.uint8, count * 3).reshape(count, 3)
        pal[:count, :3] = (a.astype(np.uint16) << 2).astype(np.uint8)
    elif code == 0x2A:
        a = np.frombuffer(raw, np.uint8, count * 4).reshape(count, 4)
        pal[:count] = a[:, [2, 1, 0, 3]]
    elif code in (0x2D, 0x29, 0x23):
        v = np.frombuffer(raw, "<u2", count).astype(np.uint32)
        if code == 0x2D:
            pal[:count, 0], pal[:count, 1], pal[:count, 2] = ((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3
            pal[:count, 3] = np.where(v & 0x8000, 255, 0)
        elif code == 0x29:
            pal[:count, 0], pal[:count, 1], pal[:count, 2] = ((v >> 11) & 31) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3
        else:
            r, g, b = (v & 31) * 255 // 31, ((v >> 5) & 31) * 255 // 31, ((v >> 10) & 31) * 255 // 31
            pal[:count, 0], pal[:count, 1], pal[:count, 2] = r, g, b
            pal[:count, 3] = np.where(((v & 0x8000) == 0) & (r == 0) & (g == 0) & (b == 0), 0, 255)
    return pal


def read_archive(path):
    """-> list of dict(name, code, width, height, rgba (h, w, 4 uint8) or None when the format is not decoded)."""
    with open(path, "rb") as fh:
        data = refpack_decompress(fh.read())
    if data[:4] not in (b"SHPI", b"SHPP"):
        raise ValueError("not an FSH archive: " + path)
    file_size, count = struct.unpack_from("<ii", data, 4)
    directory = [(data[16 + 8 * i:20 + 8 * i], struct.unpack_from("<i", data, 20 + 8 * i)[0]) for i in range(count)]
    global_pal = None
    for name, off in directory:
        if name == b"!pal":
            global_pal = _palette(data, off)
            break
    if global_pal is None:
        for name, off in directory:
            if off + 16 <= len(data) and data[off] in PALETTE_CODES:
                global_pal = _palette(data, off)
                break
    out = []
    for name, off in directory:
        if off + 16 > len(data):
            continue
        code_full, w, h = struct.unpack_from("<ihh", data, off)
        code = code_full & 0x7F
        if code not in BITMAP_CODES:
            continue
        entry = dict(name=name.decode("latin-1"), code=code, width=w, height=h, rgba=None)
        px = off + 16
        n = w * h
        try:
            if code == 0x7D:
                a = np.frombuffer(data, np.uint8, n * 4, px).reshape(h, w, 4)
                entry["rgba"] = a[:, :, [2, 1, 0, 3]].copy()
            elif code == 0x7F:
                a = np.frombuffer(data, np.uint8, n * 3, px).reshape(h, w, 3)
                entry["rgba"] = np.dstack([a[:, :, [2, 1, 0]], np.full((h, w), 255, np.uint8)])
            elif code in (0x7E, 0x78, 0x6D):
                v = np.frombuffer(data, "<u2", n, px).astype(np.uint32).reshape(h, w)
                if code == 0x7E:
                    rgba = np.dstack([((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3, np.where(v & 0x8000, 255, 0)])
                elif code == 0x78:
                    rgba = np.dstack([((v >> 11) & 31) << 3, ((v >> 5) & 63) << 2, (v & 31) << 3, np.full((h, w), 255)])
                else:
                    rgba = np.dstack([((v >> 8) & 15) * 17, ((v >> 4) & 15) * 17, (v & 15) * 17, ((v >> 12) & 15) * 17])
                entry["rgba"] = rgba.astype(np.uint8)
            elif code in (0x7B, 0x41):
                idx = np.frombuffer(data, np.uint8, n, px).reshape(h, w)
                pal = None
                att, hdr = off, code_full
                while (hdr >> 8) > 0:  # attachments chained after the bitmap
                    att += hdr >> 8
                    if att + 16 > len(data):
                        break
                    hdr = struct.unpack_from("<i", data, att)[0]
                    if (hdr & 0xFF) in PALETTE_CODES:
                        pal = _palette(data, att)
                if global_pal is not None:
                    pal = global_pal
                if pal is not None:
                    entry["rgba"] = pal[idx]
        except ValueError:
            entry["rgba"] = None
        out.append(entry)
    return out
