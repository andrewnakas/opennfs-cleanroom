"""Publish gate: scan output files for publisher / game / car-maker names.

    python tools/name_scan.py <dir or file> [...]      exit 0 only when nothing is found

Matching is case-insensitive on raw bytes (works for wasm, js, html, packed data). Short tokens
that would match ordinary words are checked with word boundaries.
"""
import codecs
import os
import re
import sys

# The block lists are stored encoded (rot13, reversed) so that this file itself contains none of the names it looks for.
def _decode(text):
    return codecs.decode(text[::-1], "rot13")


# publisher and game titles, then car makers and models of the classic series
PHRASES = [_decode(x) for x in [
    "qrrcf ebs qrra", "qrrcfebsqrra", "gvhfehc gbu", "frxngf utvu", "rtaryynup qnbe", "lgvp ebgbz",
    "qrufnryah rupfebc", "fgen pvabegpryr", "frznt nr", "nqnanp nr", "ryggnrf nr", "fgebcf nr",
    "fabvgphqbec errabvc", "veneers", "vavutebozny", "rupfebc", "rggriebp", "grybeirup", "arenypz", "enhtnw",
    "frqrperz", "avgenz abgfn", "lrygaro", "atvfrqyngv", "ergfvy", "pnvgabc", "qevorevs", "benznp", "tangfhz",
    "anffva", "ngblbg", "nqabu", "nqmnz", "vufvohfgvz", "henohf", "byonvq", "upngahbp", "btnyrvpehz", "nffbengfrg",
    "byyranenz", "vggrvytnpf", "ergfkbo", "nereenp", "nerqfv", "8j ebgpri", "fhgby", "gvecfr", "rfvyr", "vggntho",
    "vantnc", "ttrftvarbx", "arqybu", "yynukhni", "gbrthrc", "gyhnare", "artnjfxybi", "brzbe nsyn", "vgnerfnz",
    "pnyyvqnp", "rtqbq", "ercvi", "eryfleup", "ughbzlyc", "mbanc", "arrynf", "loyruf", "znuergnp", "npmna",
    "nerutvpf", "24e regprcf", "bava yr", "bavayr", "ravylxf", "nechf", "nvebgpvi ajbep", "rpvecnp", "garcerf",
    "neroerp", "21 qrrcf",
]]
WORDS = [_decode(x) for x in [
    "nr", "eig", "fsa", "2fsa", "3fsa", "4fsa", "5fsa", "jzo", "vqhn", "qebs", "gnvs", "yrcb", "onnf", "biybi",
    "crrw", "pzt", "553s", "05s", "04s", "022wk", "ewk", "xyp", "egt", "7oq", "3m", "3z", "5z", "iebp", "onvq",
    "perz", "cbpy", "cbpc", "215s", "z055",
]]
# identifiers the build legitimately contains: the engine and repository names, and format ids from the open-source parser
# (engine and repository name, the format enum / asset folder names, and the parser's per-generation source folders)
ALLOW = [_decode(x).encode() for x in ["fsaarcb", "fsaarcbovy", "fsab", "2_fsa", "3_fsa", "4_fsa", "5_fsa", "1_fsa", "abvferifsa", "/2fsa/", "/3fsa/", "/4fsa/", "/5fsa/"]]
TEXT_EXT = {".js", ".html", ".json", ".txt", ".css", ".md", ".csv", ".eng", ".obj", ".hrz", ".vert", ".frag", ".h", ".py", ".sh", ".cpp", ".hpp"}


def scan_bytes(data, ext, generated=False):
    """Phrases are searched everywhere. Short words only in text files and in the string runs of a wasm
    (pixel and sample data would match two-letter words by chance)."""
    low = data.lower()
    hits, context = {}, {}
    for p in PHRASES:
        n = low.count(p.encode())
        if n:
            hits[p] = n
            i = low.find(p.encode())
            context[p] = data[max(0, i - 40):i + 50]
    if ext == ".wasm":
        # readable strings only: runs of text characters that are mostly letters (skips compressed tables)
        runs = re.findall(rb"[\x20-\x7e]{8,}", low)
        masked = b"\n".join(r for r in runs if sum(97 <= c <= 122 or c in (32, 47, 95) for c in r) >= 0.8 * len(r))
    elif ext in TEXT_EXT and not generated:
        masked = low
    else:
        return hits, context
    for a in ALLOW:
        masked = masked.replace(a, b"\x00" * len(a))
    for w in WORDS:
        found = list(re.finditer(rb"(?<![a-z0-9_])" + re.escape(w.encode()) + rb"(?![a-z0-9_])", masked))
        if found:
            hits[w] = len(found)
            i = found[0].start()
            context[w] = masked[max(0, i - 40):i + 50]
    return hits, context


def main():
    targets = sys.argv[1:]
    verbose = "-v" in targets
    targets = [t for t in targets if t != "-v"]
    total, files = 0, 0
    for target in targets:
        paths = [target] if os.path.isfile(target) else [os.path.join(d, f) for d, _, fs in os.walk(target) for f in fs]
        for path in paths:
            if "/.git/" in path.replace("\\", "/"):
                continue
            with open(path, "rb") as fh:
                data = fh.read()
            if data[:2] == b"\x1f\x8b":  # gzip container (the shipped asset pack): scan what is inside
                import gzip
                data = gzip.decompress(data)
            files += 1
            # emscripten's minified glue uses two-letter import names; only phrases are meaningful there
            generated = os.path.basename(path) in ("opennfs.js", "assets.js")
            hits, context = scan_bytes(data, os.path.splitext(path)[1].lower(), generated)
            if hits:
                total += sum(hits.values())
                print("%s: %s" % (os.path.relpath(path, target if os.path.isdir(target) else os.path.dirname(target)),
                                  ", ".join("%s x%d" % kv for kv in sorted(hits.items(), key=lambda kv: -kv[1])[:12])))
                if verbose:
                    for term in list(hits)[:8]:
                        print("    %s: ...%r..." % (term, context.get(term, b"")))
    print("name scan: %d files, %d hits" % (files, total))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main())
