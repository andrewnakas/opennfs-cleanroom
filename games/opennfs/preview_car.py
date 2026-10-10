"""Offline preview of the generated car meshes (one contact sheet), for quick shape iteration.
Usage: python games/opennfs/preview_car.py out.png
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

import synth_car as sc  # noqa: E402

VIEWS = [("front 3/4", 18, 35), ("rear 3/4", 18, 150), ("side", 4, 90), ("top", 80, 90)]
TINT = np.array([0.80, 0.10, 0.08])
SUN = np.array([0.45, 0.72, 0.52]) / np.linalg.norm([0.45, 0.72, 0.52])


def main(path):
    fig = plt.figure(figsize=(16, 3.6 * len(sc.CARS)), dpi=70)
    for row, cid in enumerate(sc.CARS):
        tris, cols = [], []
        for mesh, centre, _ in sc.build_meshes(cid):
            offset = np.array(centre)
            verts = np.array(mesh.verts) + offset
            for i0, i1, i2, mat in mesh.tris:
                p = verts[[i0, i1, i2]]
                n = np.cross(p[1] - p[0], p[2] - p[0])
                ln = np.linalg.norm(n)
                if ln < 1e-9:
                    continue
                n /= ln
                if np.dot(n, p.mean(axis=0) - offset) < 0:
                    n = -n
                _, _, rgb, alpha = sc.SWATCH[mat]
                col = np.array(rgb) / 255.0
                if alpha < 200:
                    col = col * TINT
                shade = 0.45 + 0.55 * max(np.dot(n, SUN), 0.0)
                tris.append(p[:, [2, 0, 1]])  # plot with z (forward) along the x axis, y up
                cols.append(np.clip(col * shade, 0, 1))
        for k, (name, elev, azim) in enumerate(VIEWS):
            ax = fig.add_subplot(len(sc.CARS), len(VIEWS), row * len(VIEWS) + k + 1, projection="3d")
            ax.add_collection3d(Poly3DCollection(tris, facecolors=cols, edgecolors="none"))
            ax.set_xlim(-2.4, 2.4)
            ax.set_ylim(-2.4, 2.4)
            ax.set_zlim(-1.6, 1.6)
            ax.set_box_aspect((4.8, 4.8, 3.2))
            ax.view_init(elev=elev, azim=azim)
            ax.set_axis_off()
            ax.set_title("%s: %s" % (cid, name), fontsize=10)
    fig.subplots_adjust(left=0, right=1, top=0.96, bottom=0, wspace=0, hspace=0)
    fig.savefig(path)
    print("preview ->", path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "car_preview.png")
