"""Physical sense check: does a built object hold together like the real thing? (No AI, runs everywhere.)

The object designer first writes a BLUEPRINT (how the real thing is built: its parts, real sizes, what sits inside
the casing, what connects to what, which way things face, which parts share an axis and how they move). After the
recipe is built, `check(model, blueprint)` compares the model with it and with plain physics:

* nothing floats: every part touches the rest (a part inside a casing must touch a wall, a floor, a shaft or
  another part, not hang in the middle of the box), the object stands on y = 0;
* spinning parts spin about the axis the blueprint says, and parts that share an axis (a drum and its pulley, a
  fan and its motor shaft, a turbine's stages) are really on ONE line;
* parts face the way they work (the door at the front, the chimney on top), parts that belong inside the casing are
  inside it, nothing important is missing, moving parts have a motion;
* the whole object and each part have their real size (±25 % / ±45 %).

Each problem is one plain sentence the designer can act on ("drum_pulley is not on the drum's axis (off by 4 cm)").
"""

from __future__ import annotations

import numpy as np

SIDES = {"front": (2, 1), "back": (2, -1), "right": (0, 1), "left": (0, -1), "top": (1, 1), "bottom": (1, -1),
         "+z": (2, 1), "-z": (2, -1), "+x": (0, 1), "-x": (0, -1), "+y": (1, 1), "-y": (1, -1), "up": (1, 1),
         "down": (1, -1)}
AXES = {"x": 0, "y": 1, "z": 2, "-x": 0, "-y": 1, "-z": 2}


def _box(p) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = p.geo.bounds()
    return np.asarray(lo, np.float64), np.asarray(hi, np.float64)


def _parts_named(model, name: str) -> list[int]:
    n = str(name or "").lower()
    exact = [k for k, p in enumerate(model.parts) if p.name == n]
    if exact:
        return exact
    return [k for k, p in enumerate(model.parts) if p.name.startswith(n + "_") or
            (p.name.startswith(n) and p.name[len(n):].isdigit())]


def _group_box(model, ks: list[int]):
    bs = [_box(model.parts[k]) for k in ks]
    return np.min([b[0] for b in bs], 0), np.max([b[1] for b in bs], 0)


def _motions(p) -> list[dict]:
    mo = p.motion
    return [m for m in (mo if isinstance(mo, list) else [mo] if mo else []) if isinstance(m, dict)]


def _spin_axis(p) -> str | None:
    for m in _motions(p):
        if m.get("type") == "spin":
            return str(m.get("axis", p.axis))
    if p.kind in ("blade", "wheel"):
        return p.axis
    return None


def _surface_points(p, spacing: float, most: int = 2500) -> np.ndarray:
    """Points spread over a part's surface (corners + points inside big triangles), for distance tests."""
    t = np.asarray(p.geo.pos, np.float64).reshape(-1, 3, 3)
    area = np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1) / 2
    pts = [t.reshape(-1, 3), t.mean(1)]
    n = np.minimum(np.ceil(area / max(spacing * spacing, 1e-10)).astype(int), 40)
    rng = np.random.default_rng(7)
    for k in np.nonzero(n > 1)[0][:most]:
        u = rng.random((n[k], 2))
        flip = u.sum(1) > 1
        u[flip] = 1 - u[flip]
        pts.append(t[k, 0] + u[:, :1] * (t[k, 1] - t[k, 0]) + u[:, 1:] * (t[k, 2] - t[k, 0]))
    out = np.concatenate(pts)
    if len(out) > most * 4:
        out = out[np.random.default_rng(3).choice(len(out), most * 4, replace=False)]
    return out


def _really_touch(a, b, tol: float) -> bool:
    """Do two parts' surfaces come within tol of each other (not just their boxes)?"""
    from scipy.spatial import cKDTree  # noqa: PLC0415

    sp = max(tol, 1e-4)
    pa, pb = _surface_points(a, sp), _surface_points(b, sp)
    d, _ = cKDTree(pb).query(pa, k=1)
    return bool(float(np.min(d)) <= tol * 1.6 + sp * 0.75)


def floating_parts(model, tol: float | None = None, precise: bool = False) -> list[str]:
    """Parts (or groups of parts) that don't touch the rest of the object. precise=True also checks that the
    surfaces really meet (a shade hanging next to the end of an arm has overlapping boxes but floats)."""
    parts = [p for p in model.parts if p.geo.tris]
    if len(parts) < 2:
        return []
    lo, hi = model.bounds()
    size = float(np.max(hi - lo)) or 1.0
    tol = tol if tol is not None else max(0.003, size * 0.012)
    boxes = [_box(p) for p in parts]
    n = len(parts)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def contains(b, a):  # a's box well inside b's box (b is a casing around a)
        return bool(np.all(a[0] > b[0] + tol) and np.all(a[1] < b[1] - tol))

    def touches(a, b):
        return bool(np.all(a[0] <= b[1] + tol) and np.all(b[0] <= a[1] + tol))

    for i in range(n):
        for j in range(i + 1, n):
            a, b = boxes[i], boxes[j]
            if not touches(a, b):
                continue
            # a part fully inside a hollow casing must touch one of its walls, not just sit in its box
            if parts[j].shell and contains(b, a) and not _near_wall(a, b, tol):
                continue
            if parts[i].shell and contains(a, b) and not _near_wall(b, a, tol):
                continue
            if precise and not parts[i].shell and not parts[j].shell and not _really_touch(parts[i], parts[j], tol):
                continue
            parent[find(i)] = find(j)
    on_ground = [i for i in range(n) if boxes[i][0][1] <= float(lo[1]) + tol]  # the floor holds what stands on it
    for i in on_ground[1:]:
        parent[find(i)] = find(on_ground[0])
    roots = {}
    for i in range(n):
        roots.setdefault(find(i), []).append(i)
    if len(roots) <= 1:
        return []
    groups = sorted(roots.values(), key=lambda g: -sum(float(np.prod(boxes[k][1] - boxes[k][0] + 1e-6)) for k in g))
    out = []
    for g in groups[1:]:
        names = sorted({parts[k].name for k in g})
        out.append(", ".join(names[:4]) + (" …" if len(names) > 4 else ""))
    return out


def _near_wall(a, b, tol) -> bool:
    """Does box a touch one of the walls of box b from the inside (mounted on the floor, a side, the roof)?"""
    gap = np.concatenate([a[0] - b[0], b[1] - a[1]])
    return bool(np.min(gap) <= tol * 2.5)


def check(model, blueprint: dict | None = None, precise: bool = True) -> list[str]:
    """Plain-English problems (empty = it makes physical sense)."""
    problems = []
    lo, hi = model.bounds()
    ext = hi - lo
    size = float(np.max(ext)) or 1.0
    if lo[1] < -0.02 * size - 0.005:
        problems.append(f"part of it is under the floor (lowest point {lo[1]:.2f} m): it must stand on y = 0")
    elif lo[1] > 0.03 * size + 0.01 and not (blueprint or {}).get("sits_on") in ("wall", "ceiling"):
        problems.append(f"it floats {lo[1]:.2f} m above the floor: its feet/base must touch y = 0")
    for f in floating_parts(model, precise=precise):
        problems.append(f"{f} float(s) in the air: connect it to the part it is mounted on (real things are held)")
    bp = blueprint or {}
    real = bp.get("size_m")
    if isinstance(real, (list, tuple)) and len(real) == 3:
        r = np.asarray([float(x) for x in real], np.float64)
        for k, axis in enumerate(("width", "height", "depth")):
            if r[k] > 0.01 and not (0.75 * r[k] <= ext[k] <= 1.25 * r[k]):
                problems.append(f"its {axis} is {ext[k]:.2f} m, the real thing is about {r[k]:.2f} m")
    shared = [g for g in (bp.get("shared_axes") or []) if isinstance(g, (list, tuple)) and len(g) >= 2]
    for p in bp.get("parts") or []:
        if not isinstance(p, dict) or not p.get("name"):
            continue
        name = str(p["name"]).lower()
        ks = _parts_named(model, name)
        if not ks:
            if str(p.get("importance", "key")) != "minor":
                problems.append(f"{name} is missing (the real thing has it)")
            continue
        plo, phi = _group_box(model, ks)
        b0 = _box(model.parts[ks[0]])
        ps = p.get("size_m")
        if isinstance(ps, (list, tuple)) and len(ps) == 3:  # one piece (a spring of two) or the whole set (5 blades)
            want = max(float(x) for x in ps)
            haves = [float(np.max(phi - plo)), float(np.max(b0[1] - b0[0]))]
            if want > 0.005 and not any(0.55 * want <= h <= 1.45 * want for h in haves):
                problems.append(f"{name} is {haves[0]:.2f} m long, it should be about {want:.2f} m")
        side = str(p.get("faces") or "").lower()
        if side in SIDES:
            ax, sign = SIDES[side]
            c = (plo[ax] + phi[ax]) / 2 - (lo[ax] + hi[ax]) / 2
            if sign * c < 0.12 * ext[ax]:
                problems.append(f"{name} should be on the {side} of the object (it faces/works {side})")
        inside = str(p.get("inside") or "").lower()
        if inside and inside not in ("null", "none"):
            cs = _parts_named(model, inside)
            if cs:
                clo, chi = _group_box(model, cs)
                g = 0.03 * size
                if np.any(plo < clo - g) or np.any(phi > chi + g):
                    problems.append(f"{name} sticks out of the {inside}: it belongs inside it")
        moves = str(p.get("moves") or "").lower()
        if moves in ("spins", "slides", "swings", "opens", "turns", "rotates"):
            kinds = {m.get("type") for k in ks for m in _motions(model.parts[k])} | \
                    {model.parts[k].kind for k in ks}
            if not kinds - {"", None}:
                problems.append(f"{name} {moves} in the real thing but has no motion")
        axis = str(p.get("axis") or "").lower()
        if axis in AXES and moves in ("spins", "turns", "rotates"):
            got = next((_spin_axis(model.parts[k]) for k in ks if _spin_axis(model.parts[k])), None)
            if got and got.strip("-") != axis.strip("-"):
                problems.append(f"{name} spins about {got} but should spin about {axis}")
    for g in shared:
        lines = []
        for name in g:
            ks = _parts_named(model, str(name).lower())
            if not ks:
                continue
            p = model.parts[ks[0]]
            ax = _spin_axis(p) or p.axis
            plo, phi = _group_box(model, ks)
            piv = np.asarray(p.pivot if any(p.pivot) else (plo + phi) / 2, np.float64)
            lines.append((str(name), ax.strip("-"), piv))
        for nm, ax, piv in lines[1:]:
            nm0, ax0, piv0 = lines[0]
            if ax != ax0:
                problems.append(f"{nm} and {nm0} must turn about the same axis ({ax0}), {nm} uses {ax}")
                continue
            k = AXES[ax0]
            off = np.delete(piv - piv0, k)
            if float(np.linalg.norm(off)) > max(0.01, 0.02 * size):
                problems.append(f"{nm} is not on the {nm0}'s axis (off by {float(np.linalg.norm(off)) * 100:.0f} cm)")
    return problems


def summary(problems: list[str]) -> str:
    return "makes physical sense" if not problems else "; ".join(problems[:6])


def floating_groups(model, tol: float | None = None) -> list[list[int]]:
    """Indexes of the parts in each group that doesn't touch the main body (largest group first is NOT included)."""
    parts = model.parts
    lo, hi = model.bounds()
    size = float(np.max(hi - lo)) or 1.0
    tol = tol if tol is not None else max(0.003, size * 0.012)
    idx = [k for k, p in enumerate(parts) if p.geo.tris]
    boxes = {k: _box(parts[k]) for k in idx}
    parent = {k: k for k in idx}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def contains(b, a):
        return bool(np.all(a[0] > b[0] + tol) and np.all(a[1] < b[1] - tol))

    for x, i in enumerate(idx):
        for j in idx[x + 1:]:
            a, b = boxes[i], boxes[j]
            if not (np.all(a[0] <= b[1] + tol) and np.all(b[0] <= a[1] + tol)):
                continue
            if parts[j].shell and contains(b, a) and not _near_wall(a, b, tol):
                continue
            if parts[i].shell and contains(a, b) and not _near_wall(b, a, tol):
                continue
            parent[find(i)] = find(j)
    ground = [k for k in idx if boxes[k][0][1] <= float(lo[1]) + tol]
    for k in ground[1:]:
        parent[find(k)] = find(ground[0])
    groups = {}
    for k in idx:
        groups.setdefault(find(k), []).append(k)
    gs = sorted(groups.values(), key=lambda g: -sum(float(np.prod(boxes[k][1] - boxes[k][0] + 1e-6)) for k in g))
    return gs[1:]


def add_supports(model) -> list[str]:
    """Give every floating group a support: a strut straight down to the part below it (a casing floor, a frame) or
    to the floor, like the brackets real machines have. Returns notes. Changes the model in place."""
    from . import mesh as M  # noqa: PLC0415

    notes = []
    done = set()
    for _ in range(4):
        groups = [g for g in floating_groups(model) if tuple(g) not in done]
        if not groups:
            break
        g = groups[0]
        done.add(tuple(g))
        main = [k for k in range(len(model.parts)) if k not in g and model.parts[k].geo.tris]
        glo = np.min([_box(model.parts[k])[0] for k in g], 0)
        ghi = np.max([_box(model.parts[k])[1] for k in g], 0)
        c = (glo + ghi) / 2
        base = 0.0  # what is right below the group's centre: the top of a part, a casing's floor, or the ground
        for k in main:
            blo, bhi = _box(model.parts[k])
            if blo[0] <= c[0] <= bhi[0] and blo[2] <= c[2] <= bhi[2] and bhi[1] <= glo[1] + 1e-6:
                base = max(base, float(bhi[1]))
            elif model.parts[k].shell and np.all(blo <= glo) and np.all(bhi >= ghi):
                base = max(base, float(blo[1]))  # inside a casing: down to its floor
        h = float(glo[1]) - base
        w = float(max(0.01, 0.18 * min(ghi[0] - glo[0], ghi[2] - glo[2])))
        name = model.parts[g[0]].name.split("_")[0] + "_mount"
        if h <= 0.002:
            continue  # already at the level of what holds it (the floor, a shelf): nothing to add
        geo = M.xf(M.box(w, h + 0.002, w), (float(c[0]), base + h / 2, float(c[2])))
        model.parts.append(M.Part(name, geo, "#5b636b", material="metal"))
        notes.append(f"{name}: a {max(h, 0.01):.2f} m support under {model.parts[g[0]].name}")
    return notes
