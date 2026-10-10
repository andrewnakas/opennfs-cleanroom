"""Assemble the static site: engine (js/wasm) + packaged clean assets + page.

Usage: python tools/make_site.py [--out D:/n64work/opennfs/site] [--assets D:/n64work/opennfs/clean]
Prints a one-screen summary.
"""
import argparse
import os
import shutil
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = "D:/n64work/opennfs"
EMS = "D:/n64work/emsdk/upstream/emscripten"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=WORK + "/site")
    ap.add_argument("--assets", default=WORK + "/clean")
    ap.add_argument("--build", default=WORK + "/build")
    ap.add_argument("--port", default=WORK + "/port")
    ap.add_argument("--release", action="store_true", help="strip function names from the wasm (publish builds)")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    for name in ("opennfs.js", "opennfs.wasm"):
        shutil.copy2(os.path.join(a.build, name), os.path.join(a.out, name))
    if a.release:
        wasm = os.path.join(a.out, "opennfs.wasm")
        # drop the function-name and producers sections (plain section removal: the code is not rewritten)
        r = subprocess.run(["D:/n64work/emsdk/upstream/bin/llvm-objcopy.exe", "--remove-section=name", "--remove-section=producers", wasm],
                           capture_output=True, text=True)
        if r.returncode:
            print(r.stderr[-1500:])
            return 1
    env = dict(os.environ, EM_CONFIG="D:/n64work/emsdk/.emscripten")
    cmd = [sys.executable, EMS + "/tools/file_packager.py", os.path.join(a.out, "assets.data"),
           "--preload", a.assets + "/resources@/game/resources", a.port + "/shaders@/game/shaders",
           "--exclude", "*/gamedata/tracks/*",
           "--js-output=" + os.path.join(a.out, "assets.js"), "--no-node"]
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if r.returncode:
        print(r.stderr[-2000:])
        return 1
    # ship the pack gzip-compressed; the page inflates it and hands it to the packager's loader
    import gzip
    data_path = os.path.join(a.out, "assets.data")
    with open(data_path, "rb") as fh:
        raw = fh.read()
    with open(os.path.join(a.out, "assets.bin"), "wb") as fh:
        fh.write(gzip.compress(raw, 9, mtime=0))
    os.remove(data_path)
    # one pack per track, fetched when the track is first raced
    import struct
    tracks_src = os.path.join(a.assets, "resources", "NFS_3", "gamedata", "tracks")
    tracks_out = os.path.join(a.out, "tracks")
    shutil.rmtree(tracks_out, ignore_errors=True)
    os.makedirs(tracks_out)
    pack_sizes = []
    for track_id in sorted(os.listdir(tracks_src)):
        names = sorted(os.listdir(os.path.join(tracks_src, track_id)))
        blob = [b"ORPK", struct.pack("<I", len(names))]
        for name in names:
            with open(os.path.join(tracks_src, track_id, name), "rb") as fh:
                data = fh.read()
            encoded = name.encode("utf-8")
            blob += [struct.pack("<H", len(encoded)), encoded, struct.pack("<I", len(data)), data]
        packed = gzip.compress(b"".join(blob), 9, mtime=0)
        with open(os.path.join(tracks_out, track_id + ".bin"), "wb") as fh:
            fh.write(packed)
        pack_sizes.append(len(packed))
    print("track packs: %d, %.1f MB total, largest %.1f MB" % (len(pack_sizes), sum(pack_sizes) / 1e6, max(pack_sizes) / 1e6))
    web = os.path.join(REPO, "ports", "opennfs", "web")
    for name in os.listdir(web):
        src = os.path.join(web, name)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(a.out, name), dirs_exist_ok=True)
        else:
            shutil.copy2(src, os.path.join(a.out, name))
    page_data = os.path.join(a.assets, "page")
    if os.path.isdir(page_data):
        shutil.copytree(page_data, a.out, dirs_exist_ok=True)
    total = 0
    for d, _, files in os.walk(a.out):
        for f in files:
            total += os.path.getsize(os.path.join(d, f))
    sizes = ", ".join("%s %.1f MB" % (n, os.path.getsize(os.path.join(a.out, n)) / 1e6) for n in ("opennfs.wasm", "assets.bin"))
    print("site: %s (%.1f MB total; %s)" % (a.out, total / 1e6, sizes))
    return 0


if __name__ == "__main__":
    sys.exit(main())
