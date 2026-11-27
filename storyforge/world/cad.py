"""Real CAD shapes for machine parts (build123d + bd_warehouse) and exact cuts (manifold3d).

A recipe part with "cad" is built as a CAD solid, then turned into a clean triangle mesh with smooth normals
(rounded edges look round, no visible facets) and a sensible number of triangles:

    {"name": "drum", "cad": "revolve", "profile": [[0.24, 0.0], [0.26, 0.02], [0.26, 0.5], [0.24, 0.52]],
     "hollow": 0.004, "holes": [{"at": [0, 0.26, 0.25], "r": 0.006, "axis": "z", "grid": [12, 6, 0.04]}]}

Shapes (sizes in metres, our axes: y up, front +z):
  box       size [x, y, z]; fillet r (round edges) or chamfer c
  cylinder  size [r, h] along `axis` (x/y/z, default y); fillet/chamfer on the rims; bore r (a thick tube)
  revolve   profile [[radius, height], …] spun around y (drums, bowls, nozzles, domes, bottles, cones)
  loft      sections [{"y": h, "size": [w, d]} or {"y": h, "r": r}, …] joined smoothly (cowlings, hoods, casings)
  sweep     path [[x, y, z], …] with r (hoses, bent pipes, handles, cables), bore r (hollow), bend radius
  extrude   poly [[x, y], …] (as seen from the front) pushed back by size [depth] (brackets, plates, levers)
  gear      module m (tooth size), teeth n, thickness t, bore r (bd_warehouse involute spur gear, spins about z)
  sprocket  teeth n, pitch p (chain sprocket), thickness, bore r (bd_warehouse)
  bearing   od (outside diameter) and width: a real ball bearing (inner ring, outer ring, balls) (bd_warehouse)
  bolt      d (thread diameter), length: a hex head bolt (bd_warehouse ISO 4014)
  nut       d: a hex nut (ISO 4032); washer: d (ISO 7089)
  flange    nps ("2", "4" …), kind slip_on / weld_neck / blind (bd_warehouse ASME flanges, real size)
  pipe      nps, path [[x, y, z], …] (bd_warehouse schedule 40 steel pipe along the path)
Modifiers on any shape: holes [{"at", "r", "axis", "depth"?, "grid": [nx, ny, spacing]?}], windows [{"at", "size"}]
(rectangular openings), hollow t (a shell with walls t thick: a cut shows a thin rim, not a solid slab),
open "top"/"front"/… (which face the hollow shell leaves open).

Without build123d (CPU tests, Kaggle, a failed install) the same spec is approximated with our own mesh shapes
(chamfered boxes, lathes, tubes, gears) and holes are cut with manifold3d when it is there: nothing breaks.
Every mesh is cached by its spec (built-in parts in the repo: world/cad_meshes/, new ones on Drive: library/cad/),
so a shape is built once; videos never wait for the CAD kernel twice.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from . import mesh as M

CAD_VERSION = "cad-2"
REPO_CACHE = Path(__file__).resolve().parent / "cad_meshes"
SHAPES = {
    "box": "size [x, y, z]; fillet r (round edges) or chamfer c",
    "cylinder": "size [r, h] along axis x/y/z (default y); fillet/chamfer on the rims; bore r = a thick tube",
    "revolve": "profile [[radius, height], …] spun around y: drums, bowls, nozzles, domes, bottles, cones; ring: true = "
               "the profile is a closed loop away from the axis (a hollow cowling, a nacelle, a tyre)",
    "loft": "sections [{y, size [w, d]} or {y, r}, …] joined smoothly: cowlings, hoods, casings",
    "sweep": "path [[x, y, z], …] with r: hoses, bent pipes, handles, cables; bore r = hollow",
    "extrude": "poly [[x, y], …] (front view) pushed back by size [depth] along z: brackets, plates, levers; fillet",
    "gear": "module m, teeth n, thickness t, bore r: a real involute spur gear (spins about z)",
    "sprocket": "teeth n, pitch p, thickness t, bore r: a chain sprocket (spins about z)",
    "bearing": "od, width: a real ball bearing (rings + balls), axis z",
    "bolt": "d, length: a hex head bolt (along y, head on top)",
    "nut": "d: a hex nut", "washer": "d: a flat washer",
    "flange": "nps ('2', '4'…), kind slip_on / weld_neck / blind: a pipe flange (real size)",
    "pipe": "nps, path [[x, y, z], …]: a steel pipe along the path (real size)",
}
MODIFIERS = ("holes [{at, r, axis, depth?, grid [nx, ny, spacing]?}], windows [{at, size}], hollow t (walls t thick), "
             "open top/front/… (the side a hollow shell leaves open)")
_STATE: dict = {}
_MEM: dict = {}  # meshes already built or loaded in this session


def available() -> bool:
    """Is build123d (the CAD kernel) installed? Checked once."""
    if "ok" not in _STATE:
        try:
            import build123d  # noqa: F401,PLC0415

            _STATE["ok"] = True
        except Exception:  # noqa: BLE001
            _STATE["ok"] = False
    return _STATE["ok"]


def manifold_available() -> bool:
    if "mf" not in _STATE:
        try:
            import manifold3d  # noqa: F401,PLC0415

            _STATE["mf"] = True
        except Exception:  # noqa: BLE001
            _STATE["mf"] = False
    return _STATE["mf"]


def _key(spec: dict) -> str:
    keep = {k: v for k, v in spec.items() if k not in ("name", "color", "material", "kind", "motion", "pivot", "axis_spin",
                                                     "pos", "rot", "shell", "opacity", "emissive")}
    ver = CAD_VERSION + ("-centred" if spec.get("cad") in ("bearing", "flange") else "")  # were off-centre before
    return hashlib.sha1((ver + json.dumps(keep, sort_keys=True, default=str)).encode()).hexdigest()[:16]


def _drive_cache() -> Path | None:
    try:
        from .. import config  # noqa: PLC0415

        return config.get().library_dir / "cad"
    except Exception:  # noqa: BLE001
        return None


def _load(key: str) -> M.Geo | None:
    for folder in (REPO_CACHE, _drive_cache()):
        if folder is None:
            continue
        f = folder / f"{key}.npz"
        if f.exists():
            try:
                z = np.load(f)
                v, t, n = z["v"].astype(np.float32), z["t"].astype(np.int64), z["n"].astype(np.float32)
                return M.Geo(v[t.reshape(-1)], n[t.reshape(-1)])
            except Exception:  # noqa: BLE001
                continue
    return None


def _save(key: str, geo: M.Geo, folder: Path | None) -> None:
    if folder is None:
        return
    try:
        folder.mkdir(parents=True, exist_ok=True)
        pos, nrm = geo.pos.astype(np.float32), geo.normals().astype(np.float32)
        keys = np.round(np.hstack([pos, nrm]) * 1e5).astype(np.int64)  # shared corners stored once
        _, first, inv = np.unique(keys, axis=0, return_index=True, return_inverse=True)
        t = inv.reshape(-1).astype(np.uint32 if len(first) > 65535 else np.uint16)
        tmp = folder / f"{key}.tmp.npz"
        np.savez_compressed(tmp, v=pos[first], n=nrm[first], t=t)
        tmp.replace(folder / f"{key}.npz")
    except Exception:  # noqa: BLE001
        pass


def shape(spec: dict, builtin: bool = False) -> M.Geo:
    """The part's mesh in its own frame (y up, centred like our primitives), from the cache, build123d or the
    mesh fallback. builtin=True also stores it in the repo cache (for the library's own parts)."""
    key = _key(spec)
    if key in _MEM:
        g = _MEM[key]
        return M.Geo(g.pos.copy(), None if g.nrm is None else g.nrm.copy())
    g = _load(key)
    if g is not None:
        _MEM[key] = g
        return M.Geo(g.pos.copy(), None if g.nrm is None else g.nrm.copy())
    g = None
    if available():
        try:
            g = _build_cad(spec)
        except Exception:  # noqa: BLE001  (a spec the kernel can't make: the mesh version)
            g = None
    if g is None:
        return fallback(spec)
    _save(key, g, REPO_CACHE if builtin else _drive_cache())
    _MEM[key] = g
    return M.Geo(g.pos.copy(), g.nrm.copy())


# ---------------------------------------------------------------------------------------------------------------
# build123d (millimetres inside: the kernel's tolerances suit mm; our axes: y up → build123d z up)
# ---------------------------------------------------------------------------------------------------------------

def _mm(v) -> float:
    return float(v) * 1000.0


def _vec(v, n=3, d=0.0):
    v = list(v or [])[:n]
    return [float(x) if isinstance(x, (int, float)) else d for x in v] + [d] * (n - len(v))


def _to_b(p):
    """Our (x, y, z) metres → build123d (x, -z, y) millimetres."""
    x, y, z = _vec(p)
    return (_mm(x), -_mm(z), _mm(y))


def _axis_b(a: str):
    from build123d import Axis  # noqa: PLC0415

    return {"x": Axis.X, "y": Axis.Z, "z": Axis.Y}.get(str(a or "y").lower(), Axis.Z)


def _build_cad(spec: dict) -> M.Geo:
    import build123d as bd  # noqa: PLC0415

    kind = str(spec.get("cad", "box")).lower()
    size = [float(x) for x in (spec.get("size") or [0.1])] if isinstance(spec.get("size"), (list, tuple)) else \
        [float(spec.get("size", 0.1))]
    while len(size) < 3:
        size.append(size[-1])
    part = None
    if kind == "box":
        part = bd.Box(_mm(size[0]), _mm(size[2]), _mm(size[1]))
    elif kind == "cylinder":
        r, h = size[0], size[1]
        part = bd.Cylinder(_mm(r), _mm(h))
        if spec.get("bore"):
            part = part - bd.Cylinder(_mm(min(float(spec["bore"]), r * 0.97)), _mm(h) * 1.2)
        ax = str(spec.get("axis", "y")).lower()
        if ax == "x":
            part = bd.Rot(0, 90, 0) * part
        elif ax == "z":
            part = bd.Rot(90, 0, 0) * part
    elif kind == "revolve":
        prof = [(max(0.0, _mm(a)), _mm(b)) for a, b in (spec.get("profile") or [])][:40]
        if len(prof) < 2:
            raise ValueError("revolve needs a profile")
        if spec.get("ring"):  # a closed loop away from the axis: a hollow ring (a cowling, a tyre, a pipe flange)
            pts = list(prof)
        else:  # an outline from the axis out and back: a solid of revolution
            pts = [(0.0, prof[0][1])] if prof[0][0] > 1e-6 else []
            pts += prof
            if prof[-1][0] > 1e-6:
                pts.append((0.0, prof[-1][1]))
        face = bd.Plane.XZ * bd.Polygon(*pts, align=None)
        part = bd.revolve(face, bd.Axis.Z)
    elif kind == "loft":
        secs = []
        for s in (spec.get("sections") or [])[:12]:
            y = _mm(s.get("y", 0.0))
            if s.get("r") is not None:
                sk = bd.Circle(_mm(s["r"]))
            else:
                w, d = _vec(s.get("size"), 2, 0.1)
                rr = min(_mm(s.get("round", 0.0)), _mm(min(w, d)) * 0.45)
                sk = bd.RectangleRounded(_mm(w), _mm(d), rr) if rr > 0.01 else bd.Rectangle(_mm(w), _mm(d))
            secs.append(bd.Plane.XY.offset(y) * sk)
        if len(secs) < 2:
            raise ValueError("loft needs 2+ sections")
        part = bd.loft(secs)
    elif kind == "sweep":
        pts = [_to_b(p) for p in (spec.get("path") or [])][:40]
        if len(pts) < 2:
            raise ValueError("sweep needs a path")
        r = _mm(spec.get("r", 0.01))
        bend = _mm(spec.get("bend", float(spec.get("r", 0.01)) * 2.5))
        path = bd.FilletPolyline(*pts, radius=bend) if len(pts) > 2 else bd.Polyline(*pts)
        prof = bd.Plane(path @ 0, z_dir=path % 0) * bd.Circle(r)
        if spec.get("bore"):
            prof = prof - bd.Plane(path @ 0, z_dir=path % 0) * bd.Circle(min(_mm(spec["bore"]), r * 0.95))
        part = bd.sweep(prof, path, transition=bd.Transition.ROUND)
    elif kind == "extrude":
        poly = [(_mm(x), _mm(y)) for x, y in (spec.get("poly") or [])][:40]  # our XY plane, depth along z
        if len(poly) < 3:
            raise ValueError("extrude needs a polygon")
        part = bd.extrude(bd.Plane.XZ * bd.Polygon(*poly, align=None), _mm(size[0]))
        part = bd.Pos(0, _mm(size[0]) / 2, 0) * part
    elif kind in ("gear", "sprocket", "bearing", "bolt", "nut", "washer", "flange", "pipe"):
        part = _warehouse(kind, spec)
    else:
        raise ValueError(f"unknown cad shape {kind}")
    if kind in ("box", "cylinder", "extrude", "loft") and (spec.get("fillet") or spec.get("chamfer")):
        edges = part.edges()
        try:
            if spec.get("fillet"):
                part = bd.fillet(edges, min(_mm(spec["fillet"]), _mm(min(size[:3])) * 0.45))
            else:
                part = bd.chamfer(edges, min(_mm(spec["chamfer"]), _mm(min(size[:3])) * 0.45))
        except Exception:  # noqa: BLE001  (a radius too big for a small edge: keep the sharp shape)
            pass
    if spec.get("hollow"):
        t = _mm(spec["hollow"])
        side = str(spec.get("open", "")).lower()
        dirs = {"top": bd.Axis.Z, "bottom": bd.Axis.Z, "front": bd.Axis.Y, "back": bd.Axis.Y, "left": bd.Axis.X,
                "right": bd.Axis.X}
        openings = None
        if side in dirs:
            faces = part.faces().sort_by(dirs[side])
            openings = [faces[-1] if side in ("top", "back", "right") else faces[0]]
            if side == "front":
                openings = [faces[0]]
        try:
            if openings:
                part = bd.offset(part, amount=-t, openings=openings)
            else:  # closed and hollow: the solid minus a slightly smaller copy of itself (a box with walls)
                part = part - bd.offset(part, amount=-t)
        except Exception:  # noqa: BLE001
            pass
    for h in (spec.get("holes") or [])[:24]:
        try:
            r = _mm(h.get("r", 0.005))
            depth = _mm(h.get("depth", 2.0))
            ax = str(h.get("axis", "y")).lower()
            nx, ny, gap = (list(h.get("grid") or [1, 1, 0]) + [1, 1, 0])[:3]
            for i in range(max(1, min(int(nx), 24))):
                for j in range(max(1, min(int(ny), 24))):
                    at = list(_vec(h.get("at")))
                    off = [(i - (int(nx) - 1) / 2) * float(gap), (j - (int(ny) - 1) / 2) * float(gap)]
                    if ax == "z":
                        at[0] += off[0]
                        at[1] += off[1]
                    elif ax == "x":
                        at[2] += off[0]
                        at[1] += off[1]
                    else:
                        at[0] += off[0]
                        at[2] += off[1]
                    cyl = bd.Cylinder(r, depth)
                    if ax == "x":
                        cyl = bd.Rot(0, 90, 0) * cyl
                    elif ax == "z":
                        cyl = bd.Rot(90, 0, 0) * cyl
                    part = part - bd.Pos(*_to_b(at)) * cyl
        except Exception:  # noqa: BLE001
            continue
    for w in (spec.get("windows") or [])[:8]:
        try:
            sx, sy, sz = _vec(w.get("size"), 3, 0.05)
            part = part - bd.Pos(*_to_b(w.get("at"))) * bd.Box(_mm(sx), _mm(sz), _mm(sy))
        except Exception:  # noqa: BLE001
            continue
    return _mesh(part, spec)


def _warehouse(kind: str, spec: dict):
    import build123d as bd  # noqa: PLC0415

    if kind == "gear":
        from bd_warehouse.gear import SpurGear  # noqa: PLC0415

        m = max(0.3, _mm(spec.get("module", 0.002)))
        n = int(min(150, max(6, spec.get("teeth", 20))))
        t = _mm(spec.get("thickness", 0.01))
        g = SpurGear(module=m, tooth_count=n, pressure_angle=20.0, thickness=t, root_fillet=m * 0.2)
        g = bd.Pos(0, 0, -t / 2) * g if abs(g.bounding_box().min.Z) < 1e-6 else g
        if spec.get("bore"):
            g = g - bd.Cylinder(_mm(spec["bore"]), t * 3)
        return bd.Rot(90, 0, 0) * g  # build123d z (the gear axis) → our z (it spins about z)
    if kind == "sprocket":
        from bd_warehouse.sprocket import Sprocket  # noqa: PLC0415

        p = _mm(spec.get("pitch", 0.0127))
        s = Sprocket(num_teeth=int(min(80, max(8, spec.get("teeth", 18)))), chain_pitch=p, roller_diameter=p * 0.625,
                     thickness=_mm(spec.get("thickness", 0.004)), bore_diameter=_mm(spec.get("bore", 0.0)) * 2)
        return bd.Rot(90, 0, 0) * s
    if kind == "bearing":
        from bd_warehouse.bearing import SingleRowDeepGrooveBallBearing  # noqa: PLC0415

        od = _mm(spec.get("od", 0.022))
        best = min(SingleRowDeepGrooveBallBearing.sizes("SKT"), key=lambda s: abs(float(s.split("-")[1]) - od))
        b = SingleRowDeepGrooveBallBearing(size=best)
        bb = b.bounding_box()
        b = bd.Pos(0, 0, -(bb.min.Z + bb.max.Z) / 2) * b  # centred on its own width, like every other part
        k = od / float(best.split("-")[1])
        return bd.Rot(90, 0, 0) * bd.scale(b, k) if abs(k - 1) > 1e-3 else bd.Rot(90, 0, 0) * b
    if kind in ("bolt", "nut", "washer"):
        from bd_warehouse.fastener import HexHeadScrew, HexNut, PlainWasher  # noqa: PLC0415

        d = _mm(spec.get("d", 0.008))
        sizes = HexHeadScrew.sizes("iso4014")
        best = min(sizes, key=lambda s: abs(float(s.split("-")[0][1:]) - d))
        if kind == "bolt":
            ln = _mm(spec.get("length", 0.03))
            return HexHeadScrew(size=best, length=ln, fastener_type="iso4014", simple=True)
        if kind == "nut":
            return HexNut(size=best, fastener_type="iso4032", simple=True)
        return PlainWasher(size=best.split("-")[0], fastener_type="iso7089")
    if kind == "flange":
        from bd_warehouse.flange import BlindFlange, SlipOnFlange, WeldNeckFlange  # noqa: PLC0415

        cls = {"weld_neck": WeldNeckFlange, "blind": BlindFlange}.get(str(spec.get("kind", "slip_on")), SlipOnFlange)
        f = cls(nps=str(spec.get("nps", "4")), flange_class=150)
        bb = f.bounding_box()
        return bd.Pos(0, 0, -(bb.min.Z + bb.max.Z) / 2) * f  # centred on its own thickness
    if kind == "pipe":
        from bd_warehouse.pipe import Pipe  # noqa: PLC0415

        pts = [_to_b(p) for p in (spec.get("path") or [])][:30]
        if len(pts) < 2:
            raise ValueError("pipe needs a path")
        path = bd.FilletPolyline(*pts, radius=_mm(spec.get("bend", 0.1))) if len(pts) > 2 else bd.Polyline(*pts)
        for mat, ident in (("stainless", "40S"), ("iron", "STD"), ("pvc", "40")):  # names differ between versions
            try:
                return Pipe(nps=str(spec.get("nps", "2")), material=mat, identifier=ident, path=path)
            except Exception:  # noqa: BLE001
                continue
        raise ValueError("no pipe material")
    raise ValueError(kind)


def _mesh(part, spec: dict) -> M.Geo:
    """A clean triangle mesh: smooth normals inside each CAD face (fillets look round), sharp between faces."""
    bb = part.bounding_box()
    size = max(bb.max.X - bb.min.X, bb.max.Y - bb.min.Y, bb.max.Z - bb.min.Z)
    tris, nrms = _tessellate(part, max(0.08, size * 0.004), 0.35)  # mm: about 250 steps across the part
    if sum(len(t) for t in tris) > 8000:  # holes, balls, threads: coarser, so a part stays light to draw
        try:
            from OCP.BRepTools import BRepTools  # noqa: PLC0415

            BRepTools.Clean_s(part.wrapped)  # forget the fine mesh (OpenCascade only ever refines a mesh)
        except Exception:  # noqa: BLE001
            pass
        tris, nrms = _tessellate(part, max(0.25, size * 0.015), 0.8)
    if not tris:
        raise ValueError("empty CAD mesh")
    P = np.concatenate(tris)
    N = np.concatenate(nrms)
    # build123d (x, y, z) mm → our (x, z, -y) metres; y up
    P = np.stack([P[..., 0], P[..., 2], -P[..., 1]], -1) / 1000.0
    N = np.stack([N[..., 0], N[..., 2], -N[..., 1]], -1)
    geo_n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    flip = np.einsum("ij,ij->i", geo_n, N.mean(1)) < 0  # winding agrees with the smooth normals
    P[flip] = P[flip][:, ::-1]
    N[flip] = N[flip][:, ::-1]
    return M.Geo(P.reshape(-1, 3).astype(np.float32), N.reshape(-1, 3).astype(np.float32))


def _tessellate(part, tol: float, ang: float):
    tris, nrms = [], []
    for face in part.faces():
        vs, ts = face.tessellate(tol, ang)
        if not ts:
            continue
        V = np.array([[v.X, v.Y, v.Z] for v in vs], np.float64)
        T = np.array(ts, np.int64)
        fn = np.cross(V[T[:, 1]] - V[T[:, 0]], V[T[:, 2]] - V[T[:, 0]])
        vn = np.zeros_like(V)
        for k in range(3):
            np.add.at(vn, T[:, k], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        tris.append(V[T])
        nrms.append(vn[T])
    return tris, nrms


# ---------------------------------------------------------------------------------------------------------------
# Without the CAD kernel: the same shapes from our own mesh pieces
# ---------------------------------------------------------------------------------------------------------------

def rounded_box(w: float, h: float, d: float, r: float) -> M.Geo:
    """A box with bevelled edges (a chamfer the size of the fillet): close to a filleted box in low poly."""
    r = min(r, w * 0.45, h * 0.45, d * 0.45)
    if r <= 1e-5:
        return M.box(w, h, d)
    parts = [M.box(w, h - 2 * r, d - 2 * r), M.box(w - 2 * r, h, d - 2 * r), M.box(w - 2 * r, h - 2 * r, d)]
    pts = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            for sz in (-1, 1):
                pts.append((sx * (w / 2 - r), sy * (h / 2 - r), sz * (d / 2 - r)))
    corner = M.sphere(r, 1)
    for p in pts:
        parts.append(M.xf(corner, p))
    for ax in range(3):  # edge cylinders
        for s1 in (-1, 1):
            for s2 in (-1, 1):
                if ax == 0:
                    parts.append(M.xf(M.cylinder(r, w - 2 * r, 8, base=False), (0, s1 * (h / 2 - r), s2 * (d / 2 - r)), (0, 0, 90)))
                elif ax == 1:
                    parts.append(M.xf(M.cylinder(r, h - 2 * r, 8, base=False), (s1 * (w / 2 - r), 0, s2 * (d / 2 - r))))
                else:
                    parts.append(M.xf(M.cylinder(r, d - 2 * r, 8, base=False), (s1 * (w / 2 - r), s2 * (h / 2 - r), 0), (90, 0, 0)))
    return M.merge(*parts)


def fallback(spec: dict) -> M.Geo:
    kind = str(spec.get("cad", "box")).lower()
    size = [float(x) for x in (spec.get("size") or [0.1])] if isinstance(spec.get("size"), (list, tuple)) else \
        [float(spec.get("size", 0.1))]
    while len(size) < 3:
        size.append(size[-1])
    if kind == "box":
        g = rounded_box(size[0], size[1], size[2], float(spec.get("fillet") or spec.get("chamfer") or 0.0))
    elif kind == "cylinder":
        r, h = size[0], size[1]
        g = M.cylinder(r, h, 24, base=False) if not spec.get("bore") else \
            M.lathe([(float(spec["bore"]), -h / 2), (r, -h / 2), (r, h / 2), (float(spec["bore"]), h / 2),
                     (float(spec["bore"]), -h / 2)], 24, close_bottom=False, close_top=False)
        ax = str(spec.get("axis", "y")).lower()
        if ax == "x":
            g = M.xf(g, (0, 0, 0), (0, 0, 90))
        elif ax == "z":
            g = M.xf(g, (0, 0, 0), (90, 0, 0))
    elif kind == "revolve":
        prof = [(max(0.0, float(a)), float(b)) for a, b in (spec.get("profile") or [])][:40]
        ring = bool(spec.get("ring"))
        if ring and len(prof) >= 3:
            prof = prof + [prof[0]]
        g = M.lathe(prof, 24, close_bottom=not ring and prof[0][0] > 0, close_top=not ring and prof[-1][0] > 0) \
            if len(prof) >= 2 else M.box(0.1, 0.1, 0.1)
    elif kind == "loft":
        secs = spec.get("sections") or []
        prof = [(float(s.get("r", max(_vec(s.get("size"), 2, 0.1)) / 2)), float(s.get("y", 0.0))) for s in secs]
        g = M.lathe(prof, 20) if len(prof) >= 2 else M.box(0.1, 0.1, 0.1)
    elif kind in ("sweep", "pipe"):
        pts = [tuple(_vec(p)) for p in (spec.get("path") or [])][:40]
        r = float(spec.get("r", {"pipe": 0.03}.get(kind, 0.01)))
        g = M.tube(pts, r, 10) if len(pts) >= 2 else M.box(0.1, 0.1, 0.1)
    elif kind == "extrude":
        poly = [tuple(_vec(q, 2)) for q in (spec.get("poly") or [])][:40]
        g = M.extrude(poly, size[0]) if len(poly) >= 3 else M.box(0.1, 0.1, 0.1)  # same as the recipe extrude
    elif kind in ("gear", "sprocket"):
        n = int(spec.get("teeth", 20))
        m = float(spec.get("module", float(spec.get("pitch", 0.0127)) / math.pi))
        r = m * n / 2
        g = M.gear(r, n, float(spec.get("thickness", 0.01)), tooth=m * 1.1)
    elif kind == "bearing":
        od = float(spec.get("od", 0.022))
        w = float(spec.get("width", od * 0.3))
        ring = lambda ro, ri: M.lathe([(ri, -w / 2), (ro, -w / 2), (ro, w / 2), (ri, w / 2), (ri, -w / 2)], 24,  # noqa: E731
                                      close_bottom=False, close_top=False)
        g = M.merge(M.xf(ring(od / 2, od * 0.38), (0, 0, 0), (90, 0, 0)), M.xf(ring(od * 0.27, od * 0.18), (0, 0, 0),
                                                                                   (90, 0, 0)))
    elif kind in ("bolt", "nut", "washer"):
        d = float(spec.get("d", 0.008))
        if kind == "bolt":
            ln = float(spec.get("length", 0.03))
            g = M.merge(M.xf(M.cylinder(d * 0.9, d * 0.65, 6), (0, 0, 0)), M.xf(M.cylinder(d / 2, ln, 12), (0, -ln, 0)))
        elif kind == "nut":
            g = M.cylinder(d * 0.9, d * 0.8, 6, base=False)
        else:
            g = M.cylinder(d * 1.0, d * 0.18, 16, base=False)
    elif kind == "flange":
        g = M.cylinder(0.11, 0.025, 24, base=False)
    else:
        g = M.box(*size[:3])
    if manifold_available() and (spec.get("holes") or spec.get("windows")):
        try:
            g = _holes_manifold(g, spec)
        except Exception:  # noqa: BLE001
            pass
    return g


# ---------------------------------------------------------------------------------------------------------------
# manifold3d: exact booleans on meshes (holes without CAD, clean cuts for hero shots)
# ---------------------------------------------------------------------------------------------------------------

def _weld(tris: np.ndarray, digits: int = 6):
    q = np.round(np.asarray(tris, np.float64).reshape(-1, 3), digits)
    uniq, inv = np.unique(q, axis=0, return_inverse=True)
    return uniq, inv.reshape(-1, 3)


def to_manifold(pos: np.ndarray):
    """A manifold3d solid from a triangle soup, or None (an open surface, crossing pieces)."""
    import manifold3d as mf  # noqa: PLC0415

    v, f = _weld(pos)
    keep = (f[:, 0] != f[:, 1]) & (f[:, 1] != f[:, 2]) & (f[:, 0] != f[:, 2])
    mesh = mf.Mesh(vert_properties=v.astype(np.float32), tri_verts=f[keep].astype(np.uint32))
    m = mf.Manifold(mesh)
    if m.status() != mf.Error.NoError or m.is_empty():
        return None
    return m


def _from_manifold(m) -> np.ndarray:
    mesh = m.to_mesh()
    v = np.asarray(mesh.vert_properties, np.float64)[:, :3]
    f = np.asarray(mesh.tri_verts, np.int64)
    return v[f]


def components(pos: np.ndarray) -> list[np.ndarray]:
    """Split a triangle soup into its connected pieces (a part made of several boxes → each box)."""
    v, f = _weld(pos)
    parent = np.arange(len(v))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for a, b, c in f:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra
        parent[find(rc)] = ra
    roots = np.array([find(a) for a in f[:, 0]])
    tri = np.asarray(pos, np.float64).reshape(-1, 3, 3)
    return [tri[roots == r] for r in np.unique(roots)]


def cut(pos: np.ndarray, n, d: float, hollow: float = 0.0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cut a part (world triangles) with the plane dot(n, p) = d, keeping dot(n, p) <= d.
    → (kept triangles, cap triangles on the cut, pieces that are not closed solids: draw those with a clip plane).
    Each connected piece is cut on its own, so 12 blades get 12 small caps (not one big 'comb'); hollow > 0 (wall
    thickness) cuts the piece as a shell: the cap is a thin rim."""
    n = np.asarray(n, np.float64)
    n = n / max(float(np.linalg.norm(n)), 1e-12)
    kept, caps, loose = [], [], []
    for comp in components(pos):
        m = to_manifold(comp)
        if m is None:
            loose.append(comp)
            continue
        if hollow > 0:
            lo, hi = comp.reshape(-1, 3).min(0), comp.reshape(-1, 3).max(0)
            ext = np.maximum(hi - lo, 1e-6)
            k = np.clip(1.0 - 2.0 * hollow / ext, 0.05, 0.98)
            c = (lo + hi) / 2
            inner = m.translate(tuple(-c)).scale(tuple(k)).translate(tuple(c))
            m = m - inner
        t = m.trim_by_plane(tuple(-n), float(-d))  # keeps dot(-n, p) >= -d, i.e. dot(n, p) <= d
        if t.is_empty():
            continue
        tri = _from_manifold(t)
        on = np.abs(tri @ n - d).max(1) < max(1e-6, 1e-5 * float(np.abs(tri).max()))
        fn = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        cap = on & (np.einsum("ij,j->i", fn, n) > 0)
        kept.append(tri[~cap])
        caps.append(tri[cap])
    cat = lambda xs: np.concatenate(xs) if xs else np.zeros((0, 3, 3))  # noqa: E731
    return cat(kept), cat(caps), cat(loose)


def _holes_manifold(g: M.Geo, spec: dict) -> M.Geo:
    import manifold3d as mf  # noqa: PLC0415

    m = to_manifold(g.pos)
    if m is None:
        return g
    for h in (spec.get("holes") or [])[:24]:
        r, depth = float(h.get("r", 0.005)), float(h.get("depth", 2.0))
        cyl = mf.Manifold.cylinder(depth, r, r, 16, True)  # along z
        ax = str(h.get("axis", "y")).lower()
        if ax == "y":
            cyl = cyl.rotate((90, 0, 0))
        elif ax == "x":
            cyl = cyl.rotate((0, 90, 0))
        nx, ny, gap = (list(h.get("grid") or [1, 1, 0]) + [1, 1, 0])[:3]
        for i in range(max(1, min(int(nx), 24))):
            for j in range(max(1, min(int(ny), 24))):
                at = list(_vec(h.get("at")))
                off = [(i - (int(nx) - 1) / 2) * float(gap), (j - (int(ny) - 1) / 2) * float(gap)]
                if ax == "z":
                    at[0] += off[0]
                    at[1] += off[1]
                elif ax == "x":
                    at[2] += off[0]
                    at[1] += off[1]
                else:
                    at[0] += off[0]
                    at[2] += off[1]
                m = m - cyl.translate(tuple(at))
    for w in (spec.get("windows") or [])[:8]:
        sx, sy, sz = _vec(w.get("size"), 3, 0.05)
        m = m - mf.Manifold.cube((sx, sy, sz), True).translate(tuple(_vec(w.get("at"))))
    return M.Geo(_from_manifold(m).reshape(-1, 3).astype(np.float32))


def describe() -> str:
    """For the designer prompt and the cheatsheet."""
    return "; ".join(f"{k}: {v}" for k, v in SHAPES.items()) + ". Modifiers: " + MODIFIERS
