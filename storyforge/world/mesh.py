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
    """Triangles: pos (N*3, 3). Normals are flat (low poly look) unless `nrm` holds smooth per-corner normals
    (CAD parts: fillets and round parts look smooth, no visible facets)."""

    pos: np.ndarray
    nrm: np.ndarray | None = None

    @property
    def tris(self) -> int:
        return len(self.pos) // 3

    def normals(self) -> np.ndarray:
        if self.nrm is not None and len(self.nrm) == len(self.pos):
            return self.nrm.astype(np.float32)
        t = self.pos.reshape(-1, 3, 3)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        ln = np.linalg.norm(n, axis=1, keepdims=True)
        n = n / np.where(ln < 1e-12, 1, ln)
        return np.repeat(n, 3, axis=0).astype(np.float32)

    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        if not len(self.pos):
            return np.zeros(3, np.float32), np.zeros(3, np.float32)
        return self.pos.min(0), self.pos.max(0)

    def closed(self) -> bool:
        """True when every edge belongs to an even number of triangles: a solid (a cut shows a flat cap),
        not an open surface like a tube wall without thickness."""
        c = getattr(self, "_closed", None)
        if c is None:
            if not len(self.pos):
                c = False
            else:
                q = np.round(self.pos.astype(np.float64) * 2000).astype(np.int64).reshape(-1, 3, 3)
                a = np.concatenate([q[:, 0], q[:, 1], q[:, 2]])
                b = np.concatenate([q[:, 1], q[:, 2], q[:, 0]])
                ab = np.concatenate([a, b], 1)
                ba = np.concatenate([b, a], 1)
                first = (np.sign(a - b) @ np.array([4, 2, 1])) <= 0  # a <= b in (x, y, z) order
                key = np.where(first[:, None], ab, ba)
                _, counts = np.unique(key, axis=0, return_counts=True)
                c = bool(np.all(counts % 2 == 0))
            self._closed = c
        return c


def geo(tris) -> Geo:
    a = np.asarray(tris, np.float32).reshape(-1, 3)
    return Geo(a)


def merge(*gs: Geo) -> Geo:
    gs = [g for g in gs if g is not None and len(g.pos)]
    if not gs:
        return Geo(np.zeros((0, 3), np.float32))
    pos = np.concatenate([g.pos for g in gs]).astype(np.float32)
    if any(g.nrm is not None for g in gs):  # keep smooth normals (flat ones for the flat pieces)
        return Geo(pos, np.concatenate([g.normals() for g in gs]).astype(np.float32))
    return Geo(pos)


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
    n = None
    if g.nrm is not None:  # smooth normals turn with the shape (inverse transpose of the scale)
        n = g.nrm / np.where(np.asarray(s, np.float32) == 0, 1, np.asarray(s, np.float32))
        if any(r):
            n = n @ rot_matrix(*r).T
        n = n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)
    if np.prod(np.sign(np.asarray(s, np.float32) * np.ones(3))) < 0:  # mirrored: keep faces pointing out
        p = p.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
        if n is not None:
            n = n.reshape(-1, 3, 3)[:, ::-1].reshape(-1, 3)
    return Geo(p.astype(np.float32), None if n is None else n.astype(np.float32))


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
    for k in range(teeth):  # teeth around the rim, in the same plane as the disc (XZ before the swap)
        a = 360 * k / teeth
        parts.append(xf(xf(box(tooth * 1.1, depth, tooth * 1.4), (0, 0, r - tooth * 0.2)), r=(0, a, 0)))
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
    boxes: list = field(default_factory=list)  # boxes of the pieces merged into this part (for "camera inside" checks)
    motion: object = None  # how a working part moves (dict or list of dicts, see motion.py): pistons, doors, ropes…
    material: str = ""  # metal, paint, glass, plastic, rubber, water: how shiny it looks
    hollow: float = 0.0  # wall thickness (m) of a hollow solid (a capsule, a tank): a hero cut shows a thin rim


@dataclass
class Model:
    parts: list[Part] = field(default_factory=list)
    anchors: dict = field(default_factory=dict)  # named points: "top", "inlet", "outlet", "label"
    paths: dict = field(default_factory=dict)  # named polylines (pipes: flow goes along them)
    tour: list = field(default_factory=list)  # [(part, what it does in one plain sentence)], in working order

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


def section(tris: np.ndarray, n, d: float) -> np.ndarray | None:
    """The flat cut face where the plane dot(n, p) = d slices a solid: triangles (K*3, 3) of the convex outline
    of the cut (low poly parts are convex enough), or None. tris: (T*3, 3) world positions."""
    t = np.asarray(tris, np.float64).reshape(-1, 3, 3)
    n = np.asarray(n, np.float64)
    s = t @ n - d  # (T, 3) signed distances
    pts = []
    for a, b in ((0, 1), (1, 2), (2, 0)):
        sa, sb = s[:, a], s[:, b]
        m = (sa * sb) < 0
        if np.any(m):
            u = (sa[m] / (sa[m] - sb[m]))[:, None]
            pts.append(t[m, a] + (t[m, b] - t[m, a]) * u)
    if not pts:
        return None
    P = np.concatenate(pts)
    if len(P) < 3:
        return None
    ax = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(n, ax)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(n, e1)
    q = np.stack([P @ e1, P @ e2], 1)
    order = np.lexsort((q[:, 1], q[:, 0]))
    q, P = q[order], P[order]

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for k in range(len(q)):  # monotone chain convex hull
        while len(lower) >= 2 and cross(q[lower[-2]], q[lower[-1]], q[k]) <= 1e-12:
            lower.pop()
        lower.append(k)
    for k in range(len(q) - 1, -1, -1):
        while len(upper) >= 2 and cross(q[upper[-2]], q[upper[-1]], q[k]) <= 1e-12:
            upper.pop()
        upper.append(k)
    hull = lower[:-1] + upper[:-1]
    if len(hull) < 3:
        return None
    c = P[hull].mean(0)
    out = []
    for k in range(len(hull)):
        a, b = P[hull[k]], P[hull[(k + 1) % len(hull)]]
        out += [c, a, b] if np.dot(np.cross(a - c, b - c), n) > 0 else [c, b, a]
    return np.asarray(out, np.float32)


def _plane_basis(n: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    ax = np.array([1.0, 0.0, 0.0]) if abs(n[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    e1 = np.cross(n, ax)
    e1 /= np.linalg.norm(e1)
    return e1, np.cross(n, e1)


def _inside_any(pts: np.ndarray, tris2d: np.ndarray, shrink: float) -> bool:
    """Is any point strictly inside one of the 2D triangles (by more than `shrink`)?"""
    a, b, c = tris2d[:, 0][None], tris2d[:, 1][None], tris2d[:, 2][None]
    p = pts[:, None, :]

    def side(u, v, w):
        return (v[..., 0] - u[..., 0]) * (w[..., 1] - u[..., 1]) - (v[..., 1] - u[..., 1]) * (w[..., 0] - u[..., 0])

    area = side(a, b, c)
    sgn = np.where(area < 0, -1.0, 1.0)
    s1, s2, s3 = side(a, b, p) * sgn, side(b, c, p) * sgn, side(c, a, p) * sgn
    lens = [np.linalg.norm(v - u, axis=-1) for u, v in ((a, b), (b, c), (c, a))]
    ok = (s1 > shrink * lens[0]) & (s2 > shrink * lens[1]) & (s3 > shrink * lens[2]) & (np.abs(area) > 1e-12)
    return bool(np.any(ok))


def resolve_coplanar(model: "Model", passes: int = 3) -> list[str]:
    """Stop z-fighting (see _coplanar_pass); a moved part can land on a third one (a rim behind the moved tyre),
    so it runs again until nothing is left (at most `passes` times)."""
    notes, total = [], {}
    for _ in range(passes):
        new = _coplanar_pass(model, total)
        notes += new
        if not new:
            break
    return notes


def _coplanar_pass(model: "Model", total: dict | None = None) -> list[str]:
    """Stop z-fighting: two parts with flat faces in the SAME plane facing the SAME way (a tyre cap flush with the
    body side, a door flush with its wall) fight for the same pixels and flicker as the camera moves. The smaller
    of the two is moved out along that face's normal by a few millimetres (the whole part, so it stays closed).
    Returns notes ('tire: 7 mm out of front_side')."""
    parts = [p for p in model.parts if p.geo.tris and p.opacity > 0.05]
    if len(parts) < 2:
        return []
    lo, hi = model.bounds()
    size = float(np.linalg.norm(hi - lo)) or 1.0
    eps = min(0.012, max(0.0008, size * 0.0015))
    tol = max(size * 2e-4, 2e-5)
    info = []
    buckets: dict = {}
    for pi, p in enumerate(parts):
        t = p.geo.pos.astype(np.float64).reshape(-1, 3, 3)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        area = np.linalg.norm(n, axis=1) / 2
        good = area > 1e-10
        n = n / np.where(area[:, None] > 1e-10, 2 * area[:, None], 1.0)
        d = np.einsum("ij,ij->i", n, t[:, 0])
        info.append((t, n, d, area))
        qn = np.round(n * 200).astype(np.int64)
        qd = np.floor(d / tol).astype(np.int64)
        for k in np.nonzero(good)[0]:
            key = (qn[k, 0], qn[k, 1], qn[k, 2], qd[k])
            buckets.setdefault(key, {}).setdefault(pi, []).append(k)
    shifts: dict = {}
    notes = []
    seen = set()
    for key, by_part in buckets.items():
        merged = {pi: list(ks) for pi, ks in by_part.items()}
        for dq in (-1, 1):  # a plane right on a bucket border lands in the next bucket
            for pi, ks in buckets.get((*key[:3], key[3] + dq), {}).items():
                merged.setdefault(pi, []).extend(ks)
        if len(merged) < 2:
            continue
        pis = sorted(merged)
        for x in range(len(pis)):
            for y in range(x + 1, len(pis)):
                a, b = pis[x], pis[y]
                if (a, b, key[:3]) in seen:
                    continue
                ta, tb = info[a][0][merged[a]], info[b][0][merged[b]]
                na = info[a][1][merged[a][0]]
                if abs(float(np.mean(info[a][2][merged[a]]) - np.mean(info[b][2][merged[b]]))) > tol * 1.5:
                    continue
                e1, e2 = _plane_basis(na)
                A = np.stack([ta @ e1, ta @ e2], -1)
                B = np.stack([tb @ e1, tb @ e2], -1)
                if np.any(A.reshape(-1, 2).max(0) <= B.reshape(-1, 2).min(0) + tol) or \
                        np.any(B.reshape(-1, 2).max(0) <= A.reshape(-1, 2).min(0) + tol):
                    continue
                w = np.array([[1 / 3, 1 / 3, 1 / 3], [0.6, 0.2, 0.2], [0.2, 0.6, 0.2], [0.2, 0.2, 0.6]])
                sa = np.einsum("sk,tkd->tsd", w, A).reshape(-1, 2)
                sb = np.einsum("sk,tkd->tsd", w, B).reshape(-1, 2)
                if not (_inside_any(sa, B, tol) or _inside_any(sb, A, tol)):
                    continue
                seen.add((a, b, key[:3]))
                small = a if info[a][3][merged[a]].sum() <= info[b][3][merged[b]].sum() else b
                big = b if small == a else a
                total = {} if total is None else total
                if float(np.dot(total.get(id(parts[small]), np.zeros(3)), na)) < -1e-9:  # would undo an earlier move:
                    small, big = big, small  # move the other one (a curb flush with the road below AND the pavement)
                    if float(np.dot(total.get(id(parts[small]), np.zeros(3)), na)) < -1e-9:
                        continue
                v = shifts.setdefault(small, np.zeros(3))
                if abs(float(np.dot(v, na))) < eps * 0.99:  # already moved along this axis (either way): separated
                    shifts[small] = v + na * eps
                    notes.append(f"{parts[small].name}: {eps * 1000:.0f} mm out of {parts[big].name}")
    for pi, v in shifts.items():
        if float(np.linalg.norm(v)) < 1e-9:
            continue
        p = parts[pi]
        if total is not None:
            total[id(p)] = total.get(id(p), np.zeros(3)) + v
        p.geo = Geo((p.geo.pos.astype(np.float64) + v).astype(np.float32), p.geo.nrm)
        p.pivot = tuple(float(a + b) for a, b in zip(p.pivot, v))
        if p.boxes:
            p.boxes = [(np.asarray(b0) + v, np.asarray(b1) + v) for b0, b1 in p.boxes]
    return notes


def smooth_normals(pos: np.ndarray, crease_deg: float = 35.0) -> np.ndarray:
    """Per-corner normals averaged over the triangles around a corner that bend less than `crease_deg` (round
    surfaces look round, sharp edges stay sharp)."""
    t = np.asarray(pos, np.float64).reshape(-1, 3, 3)
    fn = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
    fl = np.linalg.norm(fn, axis=1, keepdims=True)
    fu = fn / np.maximum(fl, 1e-12)
    keys = np.round(t.reshape(-1, 3), 5)
    _, inv = np.unique(keys, axis=0, return_inverse=True)
    inv = inv.reshape(-1)
    corner_f = np.repeat(np.arange(len(t)), 3)
    acc = np.zeros((inv.max() + 1, 3))
    np.add.at(acc, inv, fn[corner_f])
    avg = acc[inv]
    avg /= np.maximum(np.linalg.norm(avg, axis=1, keepdims=True), 1e-12)
    own = fu[corner_f]
    cos = np.einsum("ij,ij->i", avg, own)
    out = np.where((cos > math.cos(math.radians(crease_deg)))[:, None], avg, own)
    return out.astype(np.float32)


_CHAMFER_CACHE: dict = {}


def chamfer_box(hx: float, hy: float, hz: float, r: float) -> np.ndarray:
    """A box (half sizes) with bevelled edges and corners: 44 triangles, (44, 3, 3) local coordinates."""
    key = (round(hx, 6), round(hy, 6), round(hz, 6), round(r, 6))
    if key in _CHAMFER_CACHE:
        return _CHAMFER_CACHE[key]
    from scipy.spatial import ConvexHull  # noqa: PLC0415

    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                pts += [(sx * hx, sy * (hy - r), sz * (hz - r)), (sx * (hx - r), sy * hy, sz * (hz - r)),
                        (sx * (hx - r), sy * (hy - r), sz * hz)]
    P = np.asarray(pts, np.float64)
    hull = ConvexHull(P)
    tris = P[hull.simplices]
    fn = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    out = np.einsum("ij,ij->i", fn, tris.mean(1)) < 0  # face away from the centre
    tris[out] = tris[out][:, ::-1]
    _CHAMFER_CACHE[key] = tris
    return tris


def _cuboid(tri: np.ndarray):
    """(centre, axes 3x3 rows, half sizes) if 12 triangles form a box (any orientation), else None."""
    v = np.unique(np.round(tri.reshape(-1, 3), 6), axis=0)
    if len(v) != 8:
        return None
    c = v.mean(0)
    v0 = v[0]
    others = v[1:] - v0
    import itertools  # noqa: PLC0415

    for a, b, cc in itertools.combinations(range(7), 3):
        e = others[[a, b, cc]]
        ln = np.linalg.norm(e, axis=1)
        if np.min(ln) < 1e-6:
            continue
        u = e / ln[:, None]
        if abs(u[0] @ u[1]) > 1e-3 or abs(u[0] @ u[2]) > 1e-3 or abs(u[1] @ u[2]) > 1e-3:
            continue
        far = v0 + e.sum(0)
        if np.min(np.linalg.norm(v - far, axis=1)) > 1e-5 * max(1.0, float(ln.max())):
            continue
        return c, u, ln / 2
    return None


def bevel_boxes(model: "Model", rel: float = 0.14, cap: float = 0.025) -> int:
    """Every box in the model gets bevelled edges (a thin highlight along each edge, like real made things).
    Returns how many boxes were bevelled."""
    count = 0
    for p in model.parts:
        if not p.geo.tris or p.kind in ("liquid", "chamber", "flame", "beam") or p.opacity < 0.5 or p.geo.nrm is not None:
            continue
        t = p.geo.pos.astype(np.float64).reshape(-1, 3, 3)
        if len(t) > 20000:
            continue
        keys = np.round(t.reshape(-1, 3), 6)
        _, inv = np.unique(keys, axis=0, return_inverse=True)
        inv = inv.reshape(-1, 3)
        parent = np.arange(inv.max() + 1)

        def find(a):
            while parent[a] != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        for a, b, c in inv:
            ra = find(a)
            parent[find(b)] = ra
            parent[find(c)] = ra
        roots = np.array([find(a) for a in inv[:, 0]])
        new, changed = [], False
        for r_ in np.unique(roots):
            comp = t[roots == r_]
            box = _cuboid(comp) if len(comp) == 12 else None
            if box is None:
                new.append(comp)
                continue
            c, u, h = box
            if np.linalg.det(u) < 0:  # a mirrored frame would turn the new box inside out
                u = u.copy()
                u[2] = -u[2]
            r = min(rel * float(h.min()) * 2, cap)
            if r < 0.0015 or float(h.min()) < 0.004:
                new.append(comp)
                continue
            loc = chamfer_box(float(h[0]), float(h[1]), float(h[2]), r)
            new.append(loc @ u + c)
            changed = True
            count += 1
        if changed:
            p.geo = Geo(np.concatenate(new).reshape(-1, 3).astype(np.float32))
    return count


def smooth_round(model: "Model", crease: float = 40.0) -> None:
    """Round parts (cylinders, spheres, lathes) get smooth normals: no visible facets; box edges stay sharp."""
    for p in model.parts:
        if p.geo.tris and p.geo.nrm is None and p.geo.tris <= 30000:
            n = smooth_normals(p.geo.pos, crease)
            flat = p.geo.normals()
            if float(np.mean(np.einsum("ij,ij->i", n, flat))) < 0.9999:  # something got smoother
                p.geo = Geo(p.geo.pos, n)
