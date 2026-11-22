"""Low poly building blocks: boxes, cylinders, cones, icospheres, tori, pipes, lathes, extrusions.

Every shape is a list of triangles (numpy, float32) with FLAT normals (one per triangle), which is
what gives the faceted low poly look. Y is up, units are meters, the ground is y = 0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Geo:
    """Triangles: pos (N*3, 3). Normals are computed flat."""

    pos: np.ndarray

    @property
    def tris(self) -> int:
        return len(self.pos) // 3

    def normals(self) -> np.ndarray:
        t = self.pos.reshape(-1, 3, 3)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.where(ln < 1e-12, 1, ln)
        return np.repeat(n, 3, axis=0).astype(np.float32)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if not len(self.pos):
            return np.zeros(3, np.float32), np.zeros(3, np.float32)
        return self.pos.min(0), self.pos.max(0)


def geo(tris) -> Geo:
    a = np.asarray(tris, np.float32).reshape(-1, 3)
    return Geo(a)


def merge(*gs: Geo) -> Geo:
    parts = [g.pos for g in gs if g is not None and len(g.pos)]
    return Geo(np.concatenate(parts).astype(np.float32) if parts else np.zeros((0, 3), np.float32))


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------


def rot_matrix(rx: float = 0, ry: float = 0, rz: float = 0) -> np.ndarray:
    """Rotation (degrees) X then Y then Z."""
    ax, ay, az = (math.radians(v) for v in (rx, ry, rz))
    cx, sx, cy, sy, cz, sz = math.cos(ax), math.sin(ax), math.cos(ay), math.sin(ay), math.cos(az), math.sin(az)
    mx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    my = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    mz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return (mz @ my @ mx).astype(np.float32)


def xf(g: Geo, t=(0, 0, 0), r=(0, 0, 0), s=1.0) -> Geo:
    """Scale, rotate (degrees), then move."""
    p = g.pos * np.asarray(s, np.float32)
    if any(r):
        p = p @ rot_matrix(*r).T
    p = p + np.asarray(t, np.float32)
    if np.prod(np.sign(np.asarray(s, np.float32) * np.ones(3))) < 0:  # mirrored: keep faces pointing out
        p = p.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
    return Geo(p.astype(np.float32))


def jitter(g: Geo, amount: float, seed: int = 0) -> Geo:
    """Move shared corners a little (lumpy rocks, manure, clouds). Same corner = same offset (no cracks)."""
    rng = np.random.default_rng(seed)
    keys = np.round(g.pos * 1000).astype(np.int64)
    uniq, inv = np.unique(keys, axis=0, return_inverse=True)
    off = rng.normal(0, amount, (len(uniq), 3)).astype(np.float32)
    return Geo(g.pos + off[inv.ravel()])


def orient_out(g: Geo, mode: str = "center") -> Geo:
    """Make every triangle face outward (lighting and cutaways need it).

    mode "center": away from the shape's middle (convex shapes); "axis": away from the Y axis at the same
    height (cylinders, lathes); "ring": away from the ring of a torus.
    """
    t = g.pos.reshape(-1, 3, 3).copy()
    if not len(t):
        return g
    n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    c = t.mean(1)
    lo, hi = g.pos.min(0), g.pos.max(0)
    mid = (lo + hi) / 2
    if mode == "axis":
        ref = np.stack([np.zeros(len(c)), np.full(len(c), mid[1]), np.zeros(len(c))], 1)
    elif mode == "ring":
        ang = np.arctan2(c[:, 2], c[:, 0])
        rr = (hi[0] - lo[0]) / 2
        R = rr - (hi[1] - lo[1]) / 2
        ref = np.stack([R * np.cos(ang), np.zeros(len(c)), R * np.sin(ang)], 1)
    else:
        ref = np.broadcast_to(mid, c.shape)
    flip = (n * (c - ref)).sum(1) < 0
    t[flip] = t[flip][:, ::-1]
    return Geo(t.reshape(-1, 3).astype(np.float32))


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------


def _quad(a, b, c, d):
    return [a, b, c, a, c, d]


def box(sx: float = 1, sy: float = 1, sz: float = 1, base: bool = False) -> Geo:
    """A box centred at the origin (base=True: sitting on y = 0)."""
    x, y, z = sx / 2, sy / 2, sz / 2
    p = np.array([[-x, -y, -z], [x, -y, -z], [x, y, -z], [-x, y, -z], [-x, -y, z], [x, -y, z], [x, y, z], [-x, y, z]])
    faces = [(4, 5, 6, 7), (1, 0, 3, 2), (0, 4, 7, 3), (5, 1, 2, 6), (7, 6, 2, 3), (0, 1, 5, 4)]
    tris = []
    for a, b, c, d in faces:
        tris += _quad(p[a], p[b], p[c], p[d])
    g = geo(tris)
    return xf(g, (0, y, 0)) if base else g


def cylinder(r: float = 0.5, h: float = 1, seg: int = 12, r_top: float | None = None, caps: bool = True,
             base: bool = True) -> Geo:
    """Upright cylinder (or cone/frustum with r_top). base=True: from y=0 to y=h, else centred."""
    rt = r if r_top is None else r_top
    y0, y1 = (0.0, h) if base else (-h / 2, h / 2)
    ang = np.linspace(0, 2 * math.pi, seg + 1)
    tris = []
    for i in range(seg):
        a0, a1 = ang[i], ang[i + 1]
        p0 = (r * math.cos(a0), y0, r * math.sin(a0))
        p1 = (r * math.cos(a1), y0, r * math.sin(a1))
        q0 = (rt * math.cos(a0), y1, rt * math.sin(a0))
        q1 = (rt * math.cos(a1), y1, rt * math.sin(a1))
        if rt > 1e-6:
            tris += [p0, q1, p1, p0, q0, q1]
        else:
            tris += [p0, q0, p1]
        if caps:
            tris += [(0, y0, 0), p0, p1]
            if rt > 1e-6:
                tris += [(0, y1, 0), q1, q0]
    return orient_out(geo(tris), "axis")


def cone(r: float = 0.5, h: float = 1, seg: int = 12) -> Geo:
    return cylinder(r, h, seg, r_top=0.0)


def lathe(profile: list[tuple[float, float]], seg: int = 14, close_bottom: bool = True,
          close_top: bool = True) -> Geo:
    """Spin a profile [(radius, y), …] around the Y axis (tanks, domes, bottles)."""
    ang = np.linspace(0, 2 * math.pi, seg + 1)
    tris = []
    for k in range(len(profile) - 1):
        (r0, y0), (r1, y1) = profile[k], profile[k + 1]
        for i in range(seg):
            a0, a1 = ang[i], ang[i + 1]
            p0 = (r0 * math.cos(a0), y0, r0 * math.sin(a0))
            p1 = (r0 * math.cos(a1), y0, r0 * math.sin(a1))
            q0 = (r1 * math.cos(a0), y1, r1 * math.sin(a0))
            q1 = (r1 * math.cos(a1), y1, r1 * math.sin(a1))
            if r0 > 1e-6:
                tris += [p0, q1, p1]
            if r1 > 1e-6:
                tris += [p0, q0, q1]
    if close_bottom and profile[0][0] > 1e-6:
        r, y = profile[0]
        for i in range(seg):
            tris += [(0, y, 0), (r * math.cos(ang[i]), y, r * math.sin(ang[i])),
                     (r * math.cos(ang[i + 1]), y, r * math.sin(ang[i + 1]))]
    if close_top and profile[-1][0] > 1e-6:
        r, y = profile[-1]
        for i in range(seg):
            tris += [(0, y, 0), (r * math.cos(ang[i + 1]), y, r * math.sin(ang[i + 1])),
                     (r * math.cos(ang[i]), y, r * math.sin(ang[i]))]
    return orient_out(geo(tris), "axis")


_ICO = None


def _icosahedron():
    t = (1 + 5 ** 0.5) / 2
    v = np.array([[-1, t, 0], [1, t, 0], [-1, -t, 0], [1, -t, 0], [0, -1, t], [0, 1, t], [0, -1, -t], [0, 1, -t],
                  [t, 0, -1], [t, 0, 1], [-t, 0, -1], [-t, 0, 1]], np.float64)
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    return v, f


def sphere(r: float = 0.5, detail: int = 1) -> Geo:
    """Icosphere: detail 0 = 20 faces (very low poly), 1 = 80, 2 = 320."""
    v, f = _icosahedron()
    verts = list(v)
    faces = list(f)
    for _ in range(detail):
        cache, new = {}, []

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = (verts[a] + verts[b]) / 2
                verts.append(m / np.linalg.norm(m))
                cache[key] = len(verts) - 1
            return cache[key]

        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            new += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = new
    vv = np.array(verts) * r
    return orient_out(geo([vv[i] for tri in faces for i in tri]))


def torus(R: float = 1, r: float = 0.25, seg: int = 16, side: int = 6) -> Geo:
    """Ring lying flat (in the XZ plane)."""
    tris = []
    for i in range(seg):
        a0, a1 = 2 * math.pi * i / seg, 2 * math.pi * (i + 1) / seg
        for j in range(side):
            b0, b1 = 2 * math.pi * j / side, 2 * math.pi * (j + 1) / side

            def pt(a, b):
                return ((R + r * math.cos(b)) * math.cos(a), r * math.sin(b), (R + r * math.cos(b)) * math.sin(a))

            tris += _quad(pt(a0, b0), pt(a0, b1), pt(a1, b1), pt(a1, b0))
    return orient_out(geo(tris), "ring")


def capsule(r: float = 0.3, length: float = 1.0, seg: int = 10) -> Geo:
    """Lying along X (bacteria, pills)."""
    prof = []
    for k in range(5):
        a = -math.pi / 2 + math.pi / 2 * k / 4
        prof.append((r * math.cos(a), -length / 2 + r * math.sin(a)))
    for k in range(5):
        a = math.pi / 2 * k / 4
        prof.append((r * math.cos(a), length / 2 + r * math.sin(a)))
    g = lathe(prof, seg, close_bottom=False, close_top=False)
    return xf(g, r=(0, 0, 90))


def tube(points, r: float = 0.15, seg: int = 8, joints: bool = True) -> Geo:
    """A pipe along a list of 3D points (straight pieces with round joints)."""
    pts = [np.asarray(p, np.float64) for p in points]
    parts = []
    for a, b in zip(pts[:-1], pts[1:]):
        d = b - a
        ln = float(np.linalg.norm(d))
        if ln < 1e-6:
            continue
        c = cylinder(r, ln, seg, base=True, caps=False)
        # rotate the Y axis onto d
        y = np.array([0.0, 1.0, 0.0])
        u = d / ln
        v = np.cross(y, u)
        s, cth = np.linalg.norm(v), float(np.dot(y, u))
        if s < 1e-8:
            m = np.eye(3) if cth > 0 else np.diag([1.0, -1.0, -1.0])
        else:
            vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
            m = np.eye(3) + vx + vx @ vx * ((1 - cth) / (s * s))
        parts.append(Geo((c.pos @ m.T.astype(np.float32) + a.astype(np.float32)).astype(np.float32)))
    if joints:
        for p in pts:
            parts.append(xf(sphere(r * 1.02, 0), p))
    return merge(*parts)


def extrude(poly2d, depth: float = 1.0, axis: str = "z") -> Geo:
    """Extrude a CONVEX-ish 2D polygon [(x, y), …] (counter-clockwise). axis z: polygon in XY, depth along Z."""
    p = [tuple(map(float, q)) for q in poly2d]
    n = len(p)
    d = depth / 2
    tris = []
    for i in range(1, n - 1):  # fan (front and back)
        tris += [(p[0][0], p[0][1], d), (p[i][0], p[i][1], d), (p[i + 1][0], p[i + 1][1], d)]
        tris += [(p[0][0], p[0][1], -d), (p[i + 1][0], p[i + 1][1], -d), (p[i][0], p[i][1], -d)]
    for i in range(n):
        a, b = p[i], p[(i + 1) % n]
        tris += _quad((a[0], a[1], -d), (b[0], b[1], -d), (b[0], b[1], d), (a[0], a[1], d))
    g = orient_out(geo(tris))
    if axis == "y":  # polygon in XZ, depth up
        g = xf(g, r=(90, 0, 0))
    return g


def prism_roof(w: float, d: float, h: float) -> Geo:
    """A gable roof: triangle (w wide, h high) extruded d deep, sitting on y = 0."""
    return extrude([(-w / 2, 0), (w / 2, 0), (0, h)], d)


def gear(r: float = 1.0, teeth: int = 10, depth: float = 0.3, tooth: float = 0.18, hole: float = 0.0) -> Geo:
    """A flat gear in the XY plane (spins around Z)."""
    parts = [cylinder(r - tooth * 0.5, depth, max(12, teeth * 2), base=False)]
    for k in range(teeth):
        a = 360 * k / teeth
        parts.append(xf(box(tooth * 1.1, tooth * 1.4, depth), (0, r - tooth * 0.2, 0), (0, 0, 0)))
        parts[-1] = xf(parts[-1], r=(0, 0, a))
    return _yz_swap(merge(*parts))


def _yz_swap(g: Geo) -> Geo:
    """Cylinders are built around Y; gears/wheels need their axle along Z."""
    return xf(g, r=(90, 0, 0))


def plane(w: float = 1, d: float = 1) -> Geo:
    x, z = w / 2, d / 2
    return geo(_quad((-x, 0, z), (x, 0, z), (x, 0, -z), (-x, 0, -z)))


def arrow2d(length: float = 2.0, width: float = 0.5, head: float = 0.7, thick: float = 0.12) -> Geo:
    """A flat arrow pointing along +X, lying on the ground plane (y = thick/2)."""
    w, h = width / 2, head
    shaft = extrude([(-length / 2, -w / 2), (length / 2 - h, -w / 2), (length / 2 - h, w / 2), (-length / 2, w / 2)],
                    thick)
    tip = extrude([(length / 2 - h, -w * 1.1), (length / 2, 0), (length / 2 - h, w * 1.1)], thick)
    return xf(merge(shaft, tip), (0, thick / 2, 0), (-90, 0, 0))


def bolt(h: float = 2.0, w: float = 0.8, thick: float = 0.15) -> Geo:
    """A lightning bolt (electricity) standing up."""
    pts = [(0.1, 1.0), (-0.35, 0.05), (0.02, 0.05), (-0.15, -1.0), (0.4, 0.15), (0.03, 0.15)]
    tris_a = extrude([(0.1, 1.0), (-0.35, 0.05), (0.02, 0.05)], thick)
    tris_b = extrude([(0.02, 0.05), (-0.35, 0.05), (0.03, 0.15), (0.4, 0.15)], thick)
    tris_c = extrude([(0.03, 0.15), (0.4, 0.15), (-0.15, -1.0)], thick)
    del pts
    return xf(merge(tris_a, tris_b, tris_c), (0, h / 2, 0), s=(w, h / 2, 1))


# ---------------------------------------------------------------------------
# Models made of parts
# ---------------------------------------------------------------------------


@dataclass
class Part:
    name: str
    geo: Geo
    color: str = "#cccccc"
    emissive: float = 0.0  # 0..1 glow (lights, screens, sparks)
    opacity: float = 1.0  # < 1 = glass / water
    shell: bool = False  # cut open in cutaway / x ray views
    pivot: tuple = (0.0, 0.0, 0.0)  # spin / swing around this point
    axis: str = "y"  # spin axis
    kind: str = ""  # "liquid" (fill level), "light" (turns on), "blade" (spins), "screen", …


@dataclass
class Model:
    parts: list[Part] = field(default_factory=list)
    anchors: dict = field(default_factory=dict)  # named points: "top", "inlet", "outlet", "label"
    paths: dict = field(default_factory=dict)  # named polylines (pipes: flow goes along them)

    def add(self, name, g: Geo, color="#cccccc", **kw) -> "Model":
        self.parts.append(Part(name, g, color, **kw))
        return self

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        bs = [p.geo.bounds() for p in self.parts if p.geo.tris]
        if not bs:
            return np.zeros(3, np.float32), np.zeros(3, np.float32)
        return np.min([b[0] for b in bs], 0), np.max([b[1] for b in bs], 0)

    @property
    def tris(self) -> int:
        return sum(p.geo.tris for p in self.parts)
