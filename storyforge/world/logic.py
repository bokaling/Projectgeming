"""How things connect and work (for every topic): ports, routed pipes and cables, assemblies, pushing, grounding.

* Ports: named points on machines and containers ("tank1.outlet", "dig1.gas_out", "gen1.inlet", "pole1.wire").
  A pipe, cable, chain or belt with "from" and "to" is routed between two ports: pipes leave the port, drop to
  stand height, run with right-angle bends and climb into the other port; cables hang between their ends.
  Flows (liquid, gas, electricity) travel along that exact route.
* Assemblies: a scraper gets its guide rail, chain and drive motor; machines are complete working units.
* Cause and effect: a moving blade (scraper, tractor bucket) pushes the piles in its way; they ride in front of
  it and drop into a pit or tank they reach. Lights and machines downstream of a flow start when it arrives.
* Grounding: things rest on the ground or on something; only gas, particles, tiny things and things in the sky
  or space may float.
"""

from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .mesh import Model

CONNECTORS = {"pipe", "wire", "cable", "chain", "belt", "conveyor", "power_line"}
PUSHABLE = {"manure", "crate", "rock", "hay_bale", "barrel", "ball", "coin", "cash"}
PITS = {"pit", "tank", "digester", "conveyor", "silo", "beaker", "glass_box"}
FLOAT_TAGS = {"micro", "space", "sky", "water", "body"}
FLOAT_ASSETS = {"cloud", "sun", "bird", "airplane", "helicopter", "methane", "molecule", "atom", "smoke_cloud",
                "explosion", "lightning_strike", "satellite", "moon", "planet", "fish", "bacteria", "virus"}
PORT_ALIASES = {"out": "outlet", "output": "outlet", "in": "inlet", "input": "inlet", "gas": "gas_out",
                "power": "power", "electric": "power", "cable": "wire", "top": "top"}


def split_ref(ref) -> tuple[str, str]:
    ref = str(ref or "")
    oid, _, port = ref.partition(".")
    return oid, port


def port(world, ref: str, toward=None) -> tuple[np.ndarray, np.ndarray]:
    """World position and outward direction (xz) of a port like 'tank1.outlet' (or the best side of the object)."""
    oid, name = split_ref(ref)
    inst = world.groups[oid][0]
    anchors = inst.model.anchors
    name = PORT_ALIASES.get(name, name)
    if name == "power" and "power" not in anchors and "wire" in anchors:
        name = "wire"
    if name == "wire" and "wire" not in anchors and "power" in anchors:
        name = "power"
    m = world.inst_matrix(inst, {"pos": inst.pos, "yaw": inst.rot, "scale": 1.0, "vis": 1.0, "shake": np.zeros(3),
                                 "bob": 0.0})
    center = (m @ np.append(np.asarray(anchors.get("center", (0, 1, 0)), np.float32), 1.0))[:3]
    if name in anchors:
        p = (m @ np.append(np.asarray(anchors[name], np.float32), 1.0))[:3]
    else:  # no such port: the side of the object that faces the other end, at 40 % of its height
        lo, hi = world.solid_bounds(inst.model)
        t = np.asarray(toward if toward is not None else center + [1, 0, 0], np.float64)
        d = t - center
        d[1] = 0
        d /= max(np.linalg.norm(d), 1e-6)
        r = float(max(hi[0] - lo[0], hi[2] - lo[2])) / 2 * inst.scale
        p = center + d * r
        p[1] = inst.pos[1] + (lo[1] + (hi[1] - lo[1]) * 0.4) * inst.scale
    n = p - center
    n[1] = 0
    if np.linalg.norm(n) < 1e-3:
        n = (np.asarray(toward, np.float64) - p) if toward is not None else np.array([1.0, 0, 0])
        n[1] = 0
    return np.asarray(p, np.float64), n / max(np.linalg.norm(n), 1e-6)


def route_pipe(a, na, b, nb, h: float = 0.8) -> list:
    """Right-angle route: out of port a, to stand height, across (x then z), up/down into port b."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    p1 = a + np.asarray(na) * 0.9
    q1 = b + np.asarray(nb) * 0.9
    pts = [a, p1]
    if abs(p1[1] - h) > 0.05:
        pts.append(np.array([p1[0], h, p1[2]]))
    pts.append(np.array([q1[0], h, p1[2]]))
    pts.append(np.array([q1[0], h, q1[2]]))
    if abs(q1[1] - h) > 0.05:
        pts.append(np.array([q1[0], q1[1], q1[2]]))
    pts += [q1, b]
    out = [pts[0]]
    for p in pts[1:]:
        if np.linalg.norm(p - out[-1]) > 0.05:
            out.append(p)
    return [tuple(map(float, p)) for p in out]


def route_cable(a, b, sag: float | None = None) -> list:
    """A cable hangs between its two ends."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    d = float(np.linalg.norm(b - a))
    s = d * 0.05 if sag is None else sag
    return [tuple(map(float, a + (b - a) * u - np.array([0, s * math.sin(math.pi * u), 0]))) for u in np.linspace(0, 1, 13)]


def connector_model(kind: str, pts: list, color: str = "", r: float | None = None) -> Model:
    """The 3D shape of a routed connection (in world coordinates) with its flow path."""
    m = Model()
    if kind in ("wire", "cable", "power_line"):
        m.add("cable", M.tube(pts, r or 0.05, 5, joints=False), color or "#1f2428")
    elif kind in ("chain", "belt"):
        m.add("chain", M.tube(pts, r or 0.06, 5, joints=False), color or "#8f9ba8")
    else:
        rr = r or 0.22
        m.add("pipe", M.tube(pts, rr, 10), color or "#f4c430", shell=True)
        for p in (pts[0], pts[-1]):
            m.add("flange", M.xf(M.sphere(rr * 1.45, 1), p), "#5b6672")
    m.paths["flow"] = [tuple(map(float, p)) for p in pts]
    m.anchors["start"], m.anchors["end"] = tuple(pts[0]), tuple(pts[-1])
    mid = pts[len(pts) // 2]
    m.anchors["label"] = (mid[0], mid[1] + 0.9, mid[2])
    return m


def build_connections(world) -> list[str]:
    """Route every plan object that has "from" and "to". Returns notes for the log."""
    notes = []
    for o in world.plan["objects"]:
        if not (o.get("from") and o.get("to")):
            continue
        a_id, b_id = split_ref(o["from"])[0], split_ref(o["to"])[0]
        if a_id not in world.groups or b_id not in world.groups or o["id"] not in world.groups:
            continue
        b_pos = world.groups[b_id][0].pos
        a_pos = world.groups[a_id][0].pos
        pa, na = port(world, o["from"], toward=b_pos)
        pb, nb = port(world, o["to"], toward=a_pos)
        kind = o["asset"]
        if kind in ("wire", "cable", "power_line"):
            pts = route_cable(pa, pb)
        elif kind in ("chain", "belt", "conveyor"):
            pts = [tuple(pa), tuple(pb)]
        else:
            pts = route_pipe(pa, na, pb, nb, h=float(o.get("params", {}).get("height", 0.8)))
        model = connector_model(kind, pts, str(o.get("params", {}).get("color") or o.get("color") or ""),
                                o.get("params", {}).get("r"))
        key = f"route:{o['id']}"
        world.models[key] = model
        lo, hi = model.bounds()
        inst = world.groups[o["id"]][0]
        inst.model, inst.keys = model, [f"{key}:{k}" for k in range(len(model.parts))]
        inst.pos, inst.rot, inst.scale = np.zeros(3, np.float32), 0.0, 1.0
        inst.lo, inst.hi, inst.radius = lo, hi, float(np.linalg.norm(hi - lo)) / 2
        world.groups[o["id"]] = [inst]
        notes.append(f"{o['id']}: {o['from']} → {o['to']}")
    return notes


def assemblies(world) -> list[dict]:
    """Extra parts that make machines complete (set dressing format: asset, area, at, rot, params)."""
    out = []
    for inst in list(world.insts):
        if inst.asset != "scraper" or inst.oid.startswith("_env"):
            continue
        moves = [e for e in world.events_of.get(inst.oid, []) if e.do == "move"]
        a = inst.pos.astype(np.float64)
        b = world._dest(inst, moves[0]).astype(np.float64) if moves else a + np.array([10.0, 0, 0])
        d = b - a
        d[1] = 0
        n = float(np.linalg.norm(d)) or 1.0
        u = d / n
        start, end = a - u * 1.2, b + u * 1.6
        mid = (start + end) / 2
        yaw = math.degrees(math.atan2(-u[2], u[0]))
        length = float(np.linalg.norm(end - start))
        out.append({"asset": "rail", "area": inst.area, "at": (float(mid[0]), 0.0, float(mid[2])), "rot": yaw,
                    "params": {"length": round(length, 2)}})
        motor = end + u * 0.6
        out.append({"asset": "electric_motor", "area": inst.area, "at": (float(motor[0]), 0.0, float(motor[2])),
                    "rot": yaw + 90, "params": {}})
    return out


def push_links(world) -> dict:
    """Which piles each moving blade pushes: {pile inst id: [(event, start, dir, contact_s, lateral, pit_s)]}."""
    links: dict = {}
    pits = [i for i in world.insts if i.asset in PITS and not i.oid.startswith("_env")]
    for inst in world.insts:
        if "blade" not in inst.model.anchors:
            continue
        for e in world.events_of.get(inst.oid, []):
            if e.do != "move":
                continue
            S = world.state(inst, e.start)["pos"].astype(np.float64)
            D = world._dest(inst, e).astype(np.float64)
            d = D - S
            d[1] = 0
            dist = float(np.linalg.norm(d))
            if dist < 0.5:
                continue
            u = d / dist
            blade = float(inst.model.anchors["blade"][0]) * inst.scale
            half = float(inst.model.anchors.get("blade_half", (0.8, 0, 0))[0]) * inst.scale
            stack = 0
            for p in sorted((p for p in world.insts if p.asset in PUSHABLE and p.area == inst.area
                             and not p.oid.startswith("_env")), key=lambda p: float(np.dot(p.pos - S, u))):
                rel = p.pos - S
                along = float(np.dot(rel, u))
                lateral = float(rel[0] * -u[2] + rel[2] * u[0])
                if not (blade < along < dist + blade + 0.5) or abs(lateral) > half + p.radius * 0.4:
                    continue
                contact = along - blade - p.radius * 0.6
                pit_s = None
                for s in np.linspace(contact, dist, 40):
                    q = S + u * (s + blade + p.radius * 0.6 + stack * 0.35)
                    for pit in pits:
                        lo, hi = world.group_box(pit.oid)
                        if lo[0] < q[0] < hi[0] and lo[2] < q[2] < hi[2]:
                            pit_s = float(s)
                            break
                    if pit_s is not None:
                        break
                links.setdefault((p.oid, p.index), []).append((e, S, u, contact, lateral, pit_s, stack, blade))
                stack += 1
    return links


def pushed_state(world, inst, st: dict, T: float) -> None:
    """Move a pile with the blade that pushes it (and let it drop into a pit or tank)."""
    for e, S, u, contact, lateral, pit_s, stack, blade in world.push.get((inst.oid, inst.index), []):
        if T < e.start:
            continue
        pusher = world.groups[e.oid][0]
        s = float(np.dot(world.state(pusher, T)["pos"].astype(np.float64) - S, u))
        if s < contact:
            continue
        side = np.array([-u[2], 0, u[0]])
        pos = S + u * (s + blade + inst.radius * 0.6 + stack * 0.35) + side * lateral * 0.5
        st["pos"] = np.array([pos[0], st["pos"][1], pos[2]], np.float32)
        if pit_s is not None and s >= pit_s:
            k = min(1.0, (s - pit_s) / 0.6)
            st["drop"] = st.get("drop", 0.0) - 0.9 * k
            st["vis"] = min(st["vis"], 1.0 - k)


def floats_ok(world, inst) -> bool:
    from . import assets  # noqa: PLC0415

    info = assets.REGISTRY.get(inst.asset)
    tags = set(info.tags) if info else set()
    area_micro = any(a.get("micro") and a["id"] == inst.area for a in world.plan["areas"])
    floating_event = any(a.get("do") in ("float", "drop") and str(a.get("target", "")).split(".")[0] == inst.oid
                         for sc in world.plan["scenes"] for a in sc.get("actions", []))
    return area_micro or floating_event or inst.asset in FLOAT_ASSETS or bool(tags & FLOAT_TAGS) or \
        inst.asset in CONNECTORS or inst.asset in ("power_pole",)


ROOMS = {"kitchen", "bathroom", "laundry", "office", "living_room", "lab", "garage"}


def place_on_surfaces(world) -> list[str]:
    """Things sit where they belong in real life: a microwave or a toaster ON the kitchen counter, a lamp on the desk,
    a ceiling fan hanging from the ceiling (the setting then builds the counter, desk or ceiling panel around it).
    Only in rooms; the plan's own "y" and mounts win. Marks inst.support."""
    from . import assets  # noqa: PLC0415
    from .decor import inst_box  # noqa: PLC0415

    notes = []
    settings = {a["id"]: a.get("setting", "") for a in world.plan.get("areas", [])}
    for inst in world.insts:
        if inst.oid.startswith("_env") or inst.oid in getattr(world, "mounts", {}):
            continue
        o = world.obj.get(inst.oid, {})
        if o.get("y") not in (None, 0, 0.0) or settings.get(inst.area) not in ROOMS:
            continue
        where = assets.placement(inst.asset)
        if where in assets.SURFACE_Y:
            inst.pos[1] = assets.SURFACE_Y[where]
        elif where == "ceiling":
            lo, hi = inst_box(inst)
            inst.pos[1] = assets.CEILING_Y - float(hi[1] - lo[1]) - 0.01
        else:
            continue
        inst.support = where
        notes.append(f"{inst.oid} stands on the {where}" if where != "ceiling" else f"{inst.oid} hangs from the ceiling")
    return notes


def ground_everything(world) -> list[str]:
    """Things that hang in the air without support are put on the ground (only gas, sky and tiny things float)."""
    from .decor import inst_box  # noqa: PLC0415

    notes = []
    plan_insts = [i for i in world.insts if not i.oid.startswith("_env")]
    boxes = {id(i): inst_box(i) for i in plan_insts}
    for inst in plan_insts:
        if inst.pos[1] <= 0.05 or floats_ok(world, inst) or inst.oid in getattr(world, "mounts", {}) or \
                getattr(inst, "support", ""):
            continue
        lo, hi = boxes[id(inst)]
        bottom = lo[1]
        supported = False
        for other in plan_insts:
            if other is inst:
                continue
            l2, h2 = boxes[id(other)]
            if -0.35 < bottom - h2[1] < 0.15 and lo[0] < h2[0] and hi[0] > l2[0] and lo[2] < h2[2] and hi[2] > l2[2]:
                supported = True
                break
        if not supported:
            inst.pos[1] = 0.0
            if inst.oid not in notes:
                notes.append(inst.oid)
    return [f"{oid} was floating: put on the ground" for oid in notes]


def arrival_clamps(world) -> list[str]:
    """Lights and machines at the end of a flow start only when the flow reaches them."""
    notes = []
    for o in world.plan["objects"]:
        if not (o.get("from") and o.get("to")) or o["id"] not in world.groups:
            continue
        path = world.groups[o["id"]][0].model.paths.get("flow")
        if not path:
            continue
        length = float(sum(np.linalg.norm(np.subtract(b, a)) for a, b in zip(path[:-1], path[1:])))
        dest = split_ref(o["to"])[0]
        for e in world.events_of.get(o["id"], []):
            if e.do not in ("flow", "sparks"):
                continue
            speed = float(e.params.get("speed", 2.2 if e.do == "flow" else 7.0))
            arrive = e.start + length / max(speed, 0.1)
            for d in world.events_of.get(dest, []):
                if d.do in ("light_on", "spin", "glow") and e.start - 0.01 <= d.start < arrive:
                    d.start = arrive
                    notes.append(f"{dest} starts when the {e.do} from {o['id']} arrives")
    return notes


PORT_NAMES = ("outlet", "inlet", "gas_out", "wire", "power")


def auto_connect(world) -> list[str]:
    """A pipe or cable that the plan left loose is connected to the nearest ports at its two ends."""
    notes = []
    candidates = [i for i in world.insts if not i.oid.startswith("_env") and i.asset not in CONNECTORS
                  and any(p in i.model.anchors for p in PORT_NAMES)]
    for o in world.plan["objects"]:
        if o["asset"] not in ("pipe", "wire") or (o.get("from") and o.get("to")) or o["id"] not in world.groups:
            continue
        inst = world.groups[o["id"]][0]
        local = inst.model.paths.get("flow")
        if not local or len(candidates) < 2:
            continue
        m = world.inst_matrix(inst, {"pos": inst.pos, "yaw": inst.rot, "scale": 1.0, "vis": 1.0, "shake": np.zeros(3),
                                     "bob": 0.0})
        path = [(m @ np.append(np.asarray(q, np.float32), 1.0))[:3] for q in local]
        ends = []
        for end in (path[0], path[-1]):
            best = None
            for c in candidates:
                if any(c.oid == e[0] for e in ends):
                    continue
                for name in PORT_NAMES:
                    if name not in c.model.anchors:
                        continue
                    p, _ = port(world, f"{c.oid}.{name}")
                    d = float(np.linalg.norm(p - np.asarray(end)))
                    if best is None or d < best[2]:
                        best = (c.oid, name, d)
            if best and best[2] < 16:
                ends.append(best)
        if len(ends) == 2:
            o["from"], o["to"] = f"{ends[0][0]}.{ends[0][1]}", f"{ends[1][0]}.{ends[1][1]}"
            notes.append(f"{o['id']} was loose: connected {o['from']} → {o['to']}")
    return notes
