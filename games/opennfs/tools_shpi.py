"""Reader for the uncompressed 32-bit SHPI archives written by nfsfmt.fsh (clean files only)."""
import struct

import numpy as np


def read(data):
    """-> list of (h, w, 4) uint8 RGBA arrays."""
    if data[:4] != b"SHPI":
        raise ValueError("not an archive written by nfsfmt.fsh")
    count = struct.unpack_from("<i", data, 8)[0]
    out = []
    for i in range(count):
        off = struct.unpack_from("<i", data, 16 + 8 * i + 4)[0]
        code, w, h = struct.unpack_from("<ihh", data, off)
        if code & 0xFF == 0x7D:
            px = np.frombuffer(data, np.uint8, w * h * 4, off + 16).reshape(h, w, 4)
            out.append(px[:, :, [2, 1, 0, 3]].copy())
        elif code & 0xFF == 0x7E:
            v = np.frombuffer(data, "<u2", w * h, off + 16).reshape(h, w).astype(np.uint32)
            out.append(np.dstack([((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3,
                                  np.where(v & 0x8000, 255, 0)]).astype(np.uint8))
        else:
            raise ValueError("unexpected pixel format")
    return out
