"""Build the patched engine tree for the web port.

pristine OpenNFS clone  --(overlay files + patch list + literal scrub)-->  port tree

Only files whose final content changed are rewritten, so ninja rebuilds stay incremental.
Usage: python ports/opennfs/prepare.py [pristine] [port]
"""
import codecs
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PRISTINE = sys.argv[1] if len(sys.argv) > 1 else "D:/n64work/opennfs/OpenNFS"
PORT = sys.argv[2] if len(sys.argv) > 2 else "D:/n64work/opennfs/port"
OVERLAY = os.path.join(HERE, "overlay")

sys.path.insert(0, HERE)
from patches import PATCHES, REMOVED  # noqa: E402

CODE_EXT = (".cpp", ".h", ".hpp")


def walk(root, sub):
    base = os.path.join(root, sub)
    for d, _, files in os.walk(base):
        for f in files:
            full = os.path.join(d, f)
            yield os.path.relpath(full, root).replace("\\", "/"), full


LITERAL = re.compile(r'"(?:[^"\\\n]|\\.)*"')
# (patterns are stored encoded, rot13 then reversed, so that this file does not contain the titles itself)
def _d(text):
    return codecs.decode(text[::-1], "rot13")


SCRUB = [
    (re.compile(_d("frznt qrrcF ebs qrrA")), "supported game folders"),
    (re.compile(_d("qrrcF ebs qrrA")), "game"),
    (re.compile(" ?(" + _d("abvgvqR ynvprcF|ravyaB lgvP ebgbZ|frxngF utvU|gvhfehC gbU") + ")"), ""),
    (re.compile(r"\b" + _d("FSA") + r" ?([1-6])(?![_0-9A-Za-z])"), r"Gen\1"),
    (re.compile(r"\b" + _d("FSA") + r"(?![_0-9A-Za-z])"), "game"),
]


def scrub_literals(text):
    """Remove retail game titles from C++ string literals (log and assert messages end up in the binary).
    Identifiers, enum names (NFS_3 ...) and #include paths are left alone."""
    count = 0

    def fix(match):
        nonlocal count
        lit = match.group(0)
        for rx, repl in SCRUB:
            lit, n = rx.subn(repl, lit)
            count += n
        return lit

    out = []
    for line in text.split("\n"):
        if '"' in line and "#include" not in line:
            line = LITERAL.sub(fix, line)
        out.append(line)
    return "\n".join(out), count


def main():
    tree = {}
    for sub in ("src", "shaders", "lib/LibOpenNFS"):
        for rel, full in walk(PRISTINE, sub):
            if rel.startswith("shaders/vk/") or rel in REMOVED:
                continue
            if sub.startswith("lib/") and (rel.startswith("lib/LibOpenNFS/lib/glm/") or "/Test/" in rel or "/.git" in rel
                                           or not rel.endswith(CODE_EXT)):
                continue
            with open(full, "rb") as fh:
                tree[rel] = fh.read()
    n_overlay = 0
    for rel, full in walk(OVERLAY, "."):
        rel = rel[2:] if rel.startswith("./") else rel
        with open(full, "rb") as fh:
            tree[rel] = fh.read()
        n_overlay += 1

    failed = []
    applied = 0
    for rel, edits in PATCHES.items():
        if rel not in tree:
            failed.append((rel, "missing file"))
            continue
        text = tree[rel].decode("utf-8").replace("\r\n", "\n")
        for i, edit in enumerate(edits):
            old, new = edit[0], edit[1]
            count = edit[2] if len(edit) > 2 else 1
            found = text.count(old)
            if found == 0 or (count and found != count):
                failed.append((rel, "edit %d: found %d, wanted %d: %r" % (i, found, count, old[:60])))
                continue
            text = text.replace(old, new)
            applied += 1
        tree[rel] = text.encode("utf-8")

    scrubbed = 0
    for rel, data in tree.items():
        if rel.endswith(CODE_EXT) and "/lib/magic_enum/" not in rel:
            text, n = scrub_literals(data.decode("utf-8", errors="surrogateescape"))
            if n:
                tree[rel] = text.encode("utf-8", errors="surrogateescape")
                scrubbed += n

    written = 0
    for rel, data in tree.items():
        out = os.path.join(PORT, rel)
        if os.path.exists(out):
            with open(out, "rb") as fh:
                if fh.read() == data:
                    continue
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "wb") as fh:
            fh.write(data)
        written += 1
    # glm lives inside the parser library (its nested submodule): keep one copy next to the patched sources so
    # every header is seen through a single path
    glm_rel = "lib/LibOpenNFS/lib/glm"
    if not os.path.isdir(os.path.join(PORT, glm_rel, "glm")):
        import shutil
        shutil.copytree(os.path.join(PRISTINE, glm_rel, "glm"), os.path.join(PORT, glm_rel, "glm"))
    # drop files that no longer belong to the tree
    stale = 0
    for sub in ("src", "shaders", "shim", "lib"):
        for rel, full in list(walk(PORT, sub)):
            if rel.startswith(glm_rel + "/"):
                continue
            if rel not in tree:
                os.remove(full)
                stale += 1

    print("port tree: %d files (%d overlay), %d edits applied, %d title mentions scrubbed, %d written, %d stale removed" % (
        len(tree), n_overlay, applied, scrubbed, written, stale))
    for rel, why in failed:
        print("  PATCH FAILED %s: %s" % (rel, why))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
