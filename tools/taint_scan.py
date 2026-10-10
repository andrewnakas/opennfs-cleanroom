"""Taint scan for the clean asset tree. Must print "0 failing" before anything is published.

    python tools/taint_scan.py [--clean D:/n64work/opennfs/clean] [--work D:/n64work/opennfs]

Checks
  1. every file under <clean>/resources is listed in <clean>/MANIFEST.json with the same sha1
     (so the tree is exactly what the generators wrote; nothing was dropped in by hand)
  2. no clean file is byte-identical to a reference file
  3. no clean image looks like a reference image (normalised 16x16 thumbnail correlation)
  4. kept-geometry circuits: every regenerated texture is compared with the retail texture it replaces.
     Both are reduced to what the scope does NOT keep (detail left after removing the 4x4 colour grid);
     that detail must be uncorrelated.
Reference files = the art bundled with the upstream engine repository (never used) plus, when the
owner has supplied them, every file of the dirty room (retail game folders under <work>).
Files marked KEPT in the manifest (track geometry, collision, camera path, AI speed table) are the
owner's kept facts: they are counted and reported, and exempt from the identity check.
"""
import argparse
import hashlib
import io
import json
import os
import struct
import sys

import numpy as np
from PIL import Image

IMAGE_EXT = (".bmp", ".tga", ".png", ".jpg", ".jpeg")
KNOWN_WORK_DIRS = {"openNFS", "opennfs", "port", "build", "clean", "site", "shots", "side", "pages", "spec", "public_repo", "clean_retail_test"}
GAME_HINTS = ("gamedata", "fedata", "NFS_2", "NFS_3", "NFS_4", "NFS_5", "data")


def sha1(path):
    h = hashlib.sha1()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def thumb(img):
    g = np.asarray(img.convert("L").resize((16, 16), Image.BILINEAR), np.float32).ravel()
    g = g - g.mean()
    n = np.linalg.norm(g)
    return g / n if n > 1e-3 else None


def shpi_images(data):
    """Images of an uncompressed 32-bit SHPI archive (the only kind the generators write)."""
    if data[:4] != b"SHPI":
        return []
    count = struct.unpack_from("<i", data, 8)[0]
    out = []
    for i in range(count):
        off = struct.unpack_from("<i", data, 16 + 8 * i + 4)[0]
        code, w, h = struct.unpack_from("<ihh", data, off)
        if w <= 0 or h <= 0:
            continue
        if code & 0xFF == 0x7D:
            px = np.frombuffer(data, np.uint8, w * h * 4, off + 16).reshape(h, w, 4)
            out.append(Image.fromarray(px[:, :, [2, 1, 0]].copy(), "RGB"))
        elif code & 0xFF == 0x7E:
            v = np.frombuffer(data, "<u2", w * h, off + 16).reshape(h, w).astype(np.uint32)
            rgb = np.dstack([((v >> 10) & 31) << 3, ((v >> 5) & 31) << 3, (v & 31) << 3]).astype(np.uint8)
            out.append(Image.fromarray(rgb, "RGB"))
    return out


def images_of(path):
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in IMAGE_EXT:
            with Image.open(path) as im:
                return [im.convert("RGB")]
        if ext in (".qfs", ".fsh"):
            with open(path, "rb") as fh:
                return shpi_images(fh.read())
        if ext == ".viv":  # the generated car archive carries one TGA
            with open(path, "rb") as fh:
                data = fh.read()
            i = data.find(b"car00.tga\0")
            if i > 0:
                pos, size = struct.unpack_from(">II", data, i - 8)
                with Image.open(io.BytesIO(data[pos:pos + size])) as im:
                    return [im.convert("RGB")]
    except Exception:
        return []
    return []


def detail_residual(rgba):
    """Luminance detail that the 4x4 colour grid does not explain, over opaque texels. -> (residual, mask)"""
    h, w = rgba.shape[:2]
    lum = rgba[:, :, :3].astype(np.float32) @ np.array([0.299, 0.587, 0.114], np.float32)
    mask = rgba[:, :, 3] >= 128
    coarse = np.zeros((4, 4), np.float32)
    overall = float(lum[mask].mean()) if mask.any() else 0.0
    for gy in range(4):
        y0, y1 = gy * h // 4, max((gy + 1) * h // 4, gy * h // 4 + 1)
        for gx in range(4):
            x0, x1 = gx * w // 4, max((gx + 1) * w // 4, gx * w // 4 + 1)
            m = mask[y0:y1, x0:x1]
            coarse[gy, gx] = float(lum[y0:y1, x0:x1][m].mean()) if m.any() else overall
    up = np.asarray(Image.fromarray(coarse, "F").resize((w, h), Image.BICUBIC), np.float32)
    return (lum - up) * mask, mask


def fine_detail(lum, mask):
    """Texel-scale detail of a luminance field (difference from a 3x3 mean), over opaque texels."""
    # the local mean only uses opaque texels: the alpha outline is a kept fact and must not count as detail
    weight = mask.astype(np.float32)
    pad_l, pad_w = np.pad(lum * weight, 1, mode="constant"), np.pad(weight, 1, mode="constant")
    h, w = lum.shape
    total = sum(pad_l[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3))
    count = sum(pad_w[dy:dy + h, dx:dx + w] for dy in range(3) for dx in range(3))
    blur = total / np.maximum(count, 1.0)
    return (lum - blur) * mask


def correlation(a, b):
    na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
    return abs(float((a * b).sum()) / (na * nb)) if na > 1e-3 and nb > 1e-3 else 0.0


def kept_track_detail_check(work, clean_res, dirty_roots, failing):
    """-> (pairs compared, highest correlation). Appends failures."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games", "opennfs"))
    from dirty import fshread
    from dirty.extract_spec import find_ci
    import tools_shpi
    pairs, worst = 0, 0.0
    worst_broad = [0.0]
    # textures re-typeset from a brief (signs) are meant to read like signs: they are counted, not correlated
    import json as _json
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "games", "opennfs", "briefs.json")) as fh:
        briefs = _json.load(fh)
    n_briefed = [0]
    tracks = os.path.join(clean_res, "NFS_3", "gamedata", "tracks")
    for root in dirty_roots:
        gamedata = find_ci(root, "gamedata")
        dirty_tracks = find_ci(gamedata, "tracks") if gamedata else None
        if not dirty_tracks:
            continue
        for folder in sorted(os.listdir(dirty_tracks)):
            track_id = folder.lower()
            stem = track_id.replace("k0", "", 1)
            clean_qfs = os.path.join(tracks, track_id, stem + "0.qfs")
            dirty_qfs = find_ci(os.path.join(dirty_tracks, folder), stem + "0.qfs")
            if not os.path.exists(clean_qfs) or not dirty_qfs:
                continue
            retail = fshread.read_archive(dirty_qfs)
            with open(clean_qfs, "rb") as fh:
                regenerated = tools_shpi.read(fh.read())
            if len(retail) != len(regenerated):
                failing.append("texture count differs: " + track_id)
                continue
            for i, (r, c) in enumerate(zip(retail, regenerated)):
                # below 16 texels a side the 4x4 grid is (nearly) the whole texture: there is no detail to leak
                if str(i) in briefs.get(track_id, {}):
                    n_briefed[0] += 1
                    continue
                if r["rgba"] is None or r["rgba"].shape != c.shape or min(c.shape[:2]) < 16:
                    continue
                rd, mask = detail_residual(r["rgba"])
                if mask.sum() < 64 or float(np.linalg.norm(rd)) < 2.0 * np.sqrt(mask.sum()):
                    continue  # the retail texture has no detail beyond the kept grid
                rc, _ = detail_residual(c)
                # two views of "detail": what the grid does not explain (smooth, so only a strong match counts),
                # and texel-scale detail (many independent samples, so even a weak match would be a leak)
                broad = correlation(rd, rc)
                # (taken after removing the grid, so edges that the kept grid itself describes do not count)
                fine = correlation(fine_detail(rd, mask), fine_detail(rc, mask))
                pairs += 1
                worst = max(worst, fine)
                worst_broad[0] = max(worst_broad[0], broad)
                # small textures give few samples: the fine limit is at least 5 standard errors of a chance match
                fine_limit = max(0.25, 5.0 / float(np.sqrt(mask.sum())))
                if fine > fine_limit or broad > 0.75:
                    failing.append("regenerated texture follows retail detail (fine %.2f, broad %.2f): %s texture %d" % (
                        fine, broad, track_id, i))
    return pairs, worst, worst_broad[0], n_briefed[0]


def walk(root):
    for d, _, files in os.walk(root):
        for f in files:
            yield os.path.join(d, f)


def find_dirty(work):
    """Retail game folders the owner dropped into the work dir (anything that is not one of our own folders)."""
    roots = []
    if not os.path.isdir(work):
        return roots
    for name in os.listdir(work):
        full = os.path.join(work, name)
        if not os.path.isdir(full) or name in KNOWN_WORK_DIRS or name == "OpenNFS":
            continue
        if any(os.path.exists(os.path.join(full, hint)) for hint in GAME_HINTS) or name.lower().startswith(("dirty", "game")):
            roots.append(full)
    return roots


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", default="D:/n64work/opennfs/clean")
    ap.add_argument("--work", default="D:/n64work/opennfs")
    a = ap.parse_args()
    res = os.path.join(a.clean, "resources")
    failing = []

    with open(os.path.join(a.clean, "MANIFEST.json")) as fh:
        manifest = json.load(fh)["files"]
    clean_files = sorted(walk(res))
    seen = set()
    for path in clean_files:
        rel = os.path.relpath(path, a.clean).replace("\\", "/")
        seen.add(rel)
        if rel not in manifest:
            failing.append("not in manifest: " + rel)
        elif manifest[rel]["sha1"] != sha1(path):
            failing.append("changed since generation: " + rel)
    for rel in manifest:
        if rel not in seen:
            failing.append("missing: " + rel)

    reference_roots = [os.path.join(a.work, "OpenNFS", "resources")] + find_dirty(a.work)
    dirty_roots = reference_roots[1:]
    ref_hashes, ref_thumbs = {}, []
    n_ref = 0
    for root in reference_roots:
        for path in walk(root):
            n_ref += 1
            ref_hashes[sha1(path)] = path
            for im in images_of(path):
                t = thumb(im)
                if t is not None:
                    ref_thumbs.append((t, path))

    n_img = n_kept = n_kept_identical = 0
    for path in clean_files:
        rel = os.path.relpath(path, a.clean).replace("\\", "/")
        h = manifest.get(rel, {}).get("sha1") or sha1(path)
        if manifest.get(rel, {}).get("source", "").startswith("KEPT"):
            n_kept += 1
            n_kept_identical += 1 if h in ref_hashes else 0
        elif h in ref_hashes:
            failing.append("identical to reference file: %s == %s" % (rel, ref_hashes[h]))
        from_spec = "/tracks/trk0" in rel
        for k, im in enumerate(images_of(path)):
            n_img += 1
            if from_spec:
                continue  # covered by the detail comparison below (the coarse colour grid is a kept fact)
            t = thumb(im)
            if t is None:
                continue
            for rt, rpath in ref_thumbs:
                c = float(np.dot(t, rt))
                if c > 0.97:
                    failing.append("image resembles reference (%.3f): %s[%d] ~ %s" % (c, rel, k, rpath))
                    break

    pairs, worst, worst_broad, n_briefed = kept_track_detail_check(a.work, res, dirty_roots, failing) if dirty_roots else (0, 0.0, 0.0, 0)
    print("dirty room: %s" % (", ".join(dirty_roots) if dirty_roots else "no game files found (step 2 is BLOCKED on game files)"))
    print("kept facts (owner scope: geometry, collision, camera path, AI speeds): %d files, %d of them byte-identical to the game's "
          "(camera paths and AI speed tables; geometry files have their vertex colours coarsened)" % (n_kept, n_kept_identical))
    print("regenerated vs retail texture detail: %d pairs compared, highest correlation fine %.3f (limit 0.25, or 5 sigma on small textures), broad %.3f (limit 0.75)" % (
        pairs, worst, worst_broad))
    print("re-typeset from briefs (generic wording, not correlated): %d textures" % n_briefed)
    print("taint: %d clean files, %d clean images, %d reference files (%d reference images): %d failing" % (
        len(clean_files), n_img, n_ref, len(ref_thumbs), len(failing)))
    for line in failing[:int(os.environ.get("TAINT_SHOW", "20"))]:
        print("  FAIL " + line)
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
