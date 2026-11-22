"""Set dressing: every area becomes a real place (ground pad, fences, lamps, props, people), automatically.

The plan only names the important objects. Here we add the small things around them, like a set designer:
a concrete, dirt or grass pad under the area, props along its edges (never on top of the main objects),
a person or two, lamp posts with warm light, and stands under pipes. Everything is placed from the plan
alone (seeded with zlib.crc32), so a frame still depends only on the plan and the time.
"""

from __future__ import annotations

import math
import zlib

import numpy as np

from . import assets

FARM = {"cow", "pig", "sheep", "chicken", "horse", "barn", "manure", "tractor", "scraper", "hay_bale", "crops", "silo"}
TOWN = {"house", "skyscraper", "tree", "car", "bus"}
NO_PAD = {"pad", "ground", "terrain", "water", "platform", "wire", "power_line", "cloud", "sun", "planet", "pipe",
          "cable", "chain", "belt"}
PROPS = {
    "farm": [("hay_bale", {}), ("bucket", {}), ("hay_bale", {}), ("bucket", {"color": "#d9534f"}), ("crate", {})],
    "industry": [("barrel", {}), ("crate", {}), ("barrel", {"color": "#f28c28"}), ("bucket", {"color": "#f4c430"})],
    "town": [("car", {}), ("bucket", {"color": "#4aa564"}), ("car", {"color": "#3d8fd6"})],
}
PEOPLE = {
    "farm": [{"shirt": "#c0443e", "pants": "#2f5fa8", "hat": "#d9bb62", "overalls": True, "stripes": True}],
    "industry": [{"shirt": "#f28c28", "pants": "#3a4450", "hat": "#f4c430"}],
    "town": [{"shirt": "#4aa564", "pants": "#3a4450", "hair": "#2a2a2e"}, {"shirt": "#9a6ad6", "pants": "#2f5fa8"}],
}


def _rng(*parts) -> np.random.Generator:
    return np.random.default_rng(zlib.crc32("/".join(map(str, parts)).encode()))


def inst_box(inst, pos=None, yaw=None, scale=1.0) -> tuple[np.ndarray, np.ndarray]:
    """World box of one placed object, rotation included."""
    pos = inst.pos if pos is None else pos
    yaw = inst.rot if yaw is None else yaw
    s = inst.scale * scale
    lo, hi = inst.lo * s, inst.hi * s
    a = math.radians(yaw)
    ca, sa = math.cos(a), math.sin(a)
    xs, zs = [], []
    for x in (lo[0], hi[0]):
        for z in (lo[2], hi[2]):
            xs.append(x * ca + z * sa)
            zs.append(-x * sa + z * ca)
    return (np.array([pos[0] + min(xs), pos[1] + lo[1], pos[2] + min(zs)]),
            np.array([pos[0] + max(xs), pos[1] + hi[1], pos[2] + max(zs)]))


def dress(world) -> list[dict]:
    """Extra objects (plan format, world coordinates in 'at') for every normal area of the world."""
    out = []
    rects = []  # (cx, cz, w, d, kind) of every area pad: for the ground under everything and the roads between
    micro = {a["id"] for a in world.plan["areas"] if a.get("micro")}
    for area in world.plan["areas"]:
        aid = area["id"]
        if aid in micro:  # inside the liquid: a muddy floor and floating bits of food all around
            insts = [i for i in world.insts if i.area == aid]
            if not insts:
                continue
            c = np.mean([i.pos for i in insts], 0)
            out.append({"asset": "pad", "area": aid, "at": (float(c[0]), 0.0, float(c[2])),
                        "params": {"w": 26.0, "d": 26.0, "color": "#3b2a1c"}})
            rng = _rng(aid, "micro")
            for k in range(34):
                a, r = rng.uniform(0, 2 * math.pi), rng.uniform(2.0, 9.0)
                out.append({"asset": "ball", "area": aid, "rot": float(rng.uniform(0, 360)),
                            "at": (float(c[0] + r * math.cos(a)), float(rng.uniform(0.3, 4.5)), float(c[2] + r * math.sin(a))),
                            "params": {"r": round(float(rng.uniform(0.12, 0.45)), 2),
                                       "color": ["#6b4a2c", "#8a6a3c", "#4f3a22", "#a08050"][k % 4]}})
            continue
        insts = [i for i in world.insts if i.area == aid and i.asset not in NO_PAD]
        if not insts:
            continue
        boxes = [inst_box(i) for i in insts]
        lo = np.min([b[0] for b in boxes], 0)
        hi = np.max([b[1] for b in boxes], 0)
        names = {i.asset for i in insts}
        kind = "farm" if names & FARM else ("town" if names & TOWN else "industry")
        margin = 2.6
        cx, cz = (lo[0] + hi[0]) / 2, (lo[2] + hi[2]) / 2
        w, d = hi[0] - lo[0] + 2 * margin, hi[2] - lo[2] + 2 * margin
        pad_color = {"farm": "dirt", "town": "grass", "industry": "concrete"}[kind]
        out.append({"asset": "pad", "area": aid, "at": (cx, 0.0, cz), "params": {"w": round(w, 2), "d": round(d, 2),
                                                                                 "color": pad_color}})
        rects.append((cx, cz, w, d, kind))
        rng = _rng(aid, kind)

        def free(x, z, r=0.7):
            return all(not (b[0][0] - r < x < b[1][0] + r and b[0][2] - r < z < b[1][2] + r) for b in boxes)

        # spots along the edges of the pad, inside it
        spots = []
        for k in range(18):
            side = k % 4
            u = rng.uniform(-0.45, 0.45)
            if side == 0:
                x, z = cx + u * w, cz - d / 2 + 1.0
            elif side == 1:
                x, z = cx + u * w, cz + d / 2 - 1.0
            elif side == 2:
                x, z = cx - w / 2 + 1.0, cz + u * d
            else:
                x, z = cx + w / 2 - 1.0, cz + u * d
            if free(x, z) and all(math.hypot(x - a, z - b) > 1.6 for a, b in spots):
                spots.append((x, z))
        props = PROPS[kind]
        for k, (x, z) in enumerate(spots[:5]):
            asset, params = props[k % len(props)]
            out.append({"asset": asset, "area": aid, "at": (x, 0.0, z), "rot": float(rng.uniform(0, 360)),
                        "params": params})
        for k, (x, z) in enumerate(spots[5:5 + len(PEOPLE[kind])]):
            yaw = math.degrees(math.atan2(-(cz - z), cx - x))  # look toward the middle of the area
            out.append({"asset": "person", "area": aid, "at": (x, 0.0, z), "rot": yaw,
                        "params": {**PEOPLE[kind][k], "seed": k + 1}})
        if kind != "town":  # a fence or railing along the back, lamps at the back corners
            fence = "fence" if kind == "farm" else "railing"
            n = max(1, int(w // 6))
            for k in range(n):
                x = cx - w / 2 + 3 + k * 6
                if free(x, cz - d / 2 + 0.3, 0.2):
                    out.append({"asset": fence, "area": aid, "at": (x, 0.0, cz - d / 2 + 0.3), "params": {"length": 6.0}})
        for x in (cx - w / 2 + 0.6, cx + w / 2 - 0.6):
            if free(x, cz - d / 2 + 0.6, 0.3):
                out.append({"asset": "lamp_post", "area": aid, "at": (x, 0.0, cz - d / 2 + 0.6), "rot": -90.0,
                            "params": {}})
    if rects:  # one ground under the whole site (no islands in the void) + gravel roads between the places
        x0 = min(r[0] - r[2] / 2 for r in rects) - 10
        x1 = max(r[0] + r[2] / 2 for r in rects) + 10
        z0 = min(r[1] - r[3] / 2 for r in rects) - 10
        z1 = max(r[1] + r[3] / 2 for r in rects) + 10
        kinds = [r[4] for r in rects]
        base = "#5f7a4c" if ("farm" in kinds or "town" in kinds) else "#6d7377"
        out.append({"asset": "ground_plate", "area": world.plan["areas"][0]["id"], "at": ((x0 + x1) / 2, 0.0, (z0 + z1) / 2),
                    "params": {"w": round(x1 - x0, 1), "d": round(z1 - z0, 1), "color": base}})
        order = sorted(rects, key=lambda r: r[0])
        for a, b in zip(order[:-1], order[1:]):
            xa, xb = a[0] + a[2] / 2, b[0] - b[2] / 2
            if xb - xa > 0.2:
                out.append({"asset": "pad", "area": world.plan["areas"][0]["id"],
                            "at": ((xa + xb) / 2, 0.0, (a[1] + b[1]) / 2),
                            "params": {"w": round(xb - xa + 0.4, 2), "d": 3.2, "color": "gravel"}})
    for inst in world.insts:  # stands under pipes that run low over the ground
        path = inst.model.paths.get("flow") if inst.asset == "pipe" and inst.model.parts and \
            inst.model.parts[0].name == "pipe" else None
        if not path:
            continue
        m = world.inst_matrix(inst, {"pos": inst.pos, "yaw": inst.rot, "scale": 1.0, "vis": 1.0, "shake": np.zeros(3),
                                     "bob": 0.0})
        pts = [(m @ np.append(np.asarray(p, np.float32), 1.0))[:3] for p in path]
        for a, b in zip(pts[:-1], pts[1:]):
            seg = float(np.linalg.norm(b - a))
            for k in range(1, int(seg // 2.5) + 1):
                p = a + (b - a) * (k * 2.5 / seg)
                if 0.4 < p[1] < 3.0 and abs(b[1] - a[1]) < 0.3:
                    out.append({"asset": "pipe_stand", "area": inst.area, "at": (float(p[0]), 0.0, float(p[2])),
                                "params": {"h": round(float(p[1]) - 0.2, 2)}})
    return out
