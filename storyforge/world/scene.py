"""One continuous 3D world, evaluated at any time T: objects, animations, particles, labels, camera.

Everything is a pure function of time, so any scene can be rendered on its own (resume after a
disconnect, or re-render one fixed scene) and the camera still flies in from where the previous
scene ended.
"""

from __future__ import annotations

import hashlib
import json
import math
import zlib
from dataclasses import dataclass, field

import numpy as np

from . import assets
from .gl import Draw, Frame, Label, hex_rgb, project_points
from .mesh import rot_matrix

SAFE_TOP, SAFE_BOTTOM = 0.15, 0.20  # keep the top 15 % for captions and the bottom 20 % clear for app buttons
FILL = 0.78  # the subject fills this much of the safe area (its larger side)
FILL_MOVES = {"close_up": 1.0, "fly_over": 0.7, "pull_out": 0.78, "top_down": 0.8}
END_OVERVIEW = 3.6  # explainers end on an overview of the whole system, then fly back to the first shot (loop)
PERSIST = {"appear", "disappear", "grow", "move", "spin", "fill", "drain", "light_on", "light_off", "float", "drop",
           "show_part", "hide_part"}
DEFAULT_DUR = {"drop": 0.6, "appear": 0.45, "disappear": 0.4, "grow": 1.2, "fill": 1.6, "drain": 1.6, "light_on": 0.35,
               "light_off": 0.3, "shake": 0.7, "cutaway": 0.8, "xray": 0.5, "show_part": 0.5, "hide_part": 0.4}
STAGGER = {"appear": 0.16, "disappear": 0.12, "light_on": 0.28, "grow": 0.1, "light_off": 0.15, "show_part": 0.1}
FLOW_COLORS = {"flow": (0.42, 0.29, 0.17), "bubbles": (0.75, 0.95, 0.6), "smoke": (0.72, 0.76, 0.8),
               "sparks": (1.0, 0.85, 0.35)}


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def pop(x: float) -> float:
    """0 → overshoot 1.12 → 1."""
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3 + 0.35 * math.sin(math.pi * x) * (1 - x)


def word_norm(w: str) -> str:
    return "".join(ch for ch in str(w).lower() if ch.isalnum())


@dataclass
class Inst:
    oid: str
    index: int
    asset: str
    model: object
    keys: list
    pos: np.ndarray
    rot: float
    scale: float
    area: str
    radius: float
    lo: np.ndarray
    hi: np.ndarray


@dataclass
class Event:
    do: str
    oid: str
    part: str
    start: float
    dur: float
    end: float  # effect ends (persistent states: inf)
    scene: int
    params: dict = field(default_factory=dict)


class World:
    def __init__(self, plan: dict, timeline: dict, size: tuple[int, int], lang: str = "en"):
        import copy  # noqa: PLC0415

        from . import logic  # noqa: PLC0415

        from . import presets  # noqa: PLC0415

        plan = copy.deepcopy(plan)  # the world may add links (auto-connected pipes): never change the caller's plan
        self.plan, self.tl, self.size, self.lang = plan, timeline, size, lang
        self.preset = presets.resolve(plan.get("preset")) or "studio"
        self.look = presets.PRESETS[self.preset]
        self.style = {**presets.style_of(self.preset), "fog": float(self.look.get("fog", 1.0))}
        self.fov = 40.0 if size[0] < size[1] else 34.0
        self.models: dict = {}
        self.insts: list[Inst] = []
        self.groups: dict[str, list[Inst]] = {}
        self.obj = {o["id"]: o for o in plan["objects"]}
        self._areas()
        self._build()
        self.notes = logic.ground_everything(self)  # nothing floats without support
        self.notes += logic.auto_connect(self)  # pipes/cables without ends get connected to the nearest ports
        self.notes += logic.build_connections(self)  # routed pipes, cables, chains between ports
        self._build_env()
        self._timing()
        self._events()
        self._add_env(logic.assemblies(self))  # complete machines (scraper rail, chain, motor)
        self.push = logic.push_links(self)  # blades push piles
        self.notes += logic.arrival_clamps(self)  # lights start when the flow arrives
        self.events.sort(key=lambda e: e.start)
        for evs in self.events_of.values():
            evs.sort(key=lambda e: e.start)
        self.ending = "overview" if (timeline.get("end") or {}).get("kind") == "overview" else "hold"
        self._focus = [self.focus_ids(i) for i in range(len(self.scenes))]
        self._cams = [self._cam_spec(i) for i in range(len(self.scenes))]

    # ------------------------------------------------------------------ building
    def _model(self, asset: str, params: dict):
        key = asset + ":" + hashlib.md5(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:8]
        if key not in self.models:
            self.models[key] = assets.build(asset, **params)
        return key, self.models[key]

    def _areas(self) -> None:
        objs = self.plan["objects"]
        ext = {}
        for a in self.plan["areas"]:
            r = 4.0
            for o in objs:
                if o["area"] != a["id"]:
                    continue
                _, m = self._model(o["asset"], o["params"])
                lo, hi = m.bounds()
                rad = float(max(hi[0] - lo[0], hi[2] - lo[2])) / 2 * o["scale"]
                spread = o["spacing"] * (o["count"] - 1) / 2 if o["count"] > 1 else 0
                r = max(r, math.hypot(*o["pos"]) + rad + spread)
            ext[a["id"]] = r
        self.area_xz, self.area_r = {}, ext
        right, prev = None, None  # the right edge of the areas placed so far
        for a in self.plan["areas"]:
            if "x" in a:  # a frozen position (saved with the plan, so a fix never moves other areas)
                self.area_xz[a["id"]] = (a["x"], a["z"])
                if not a.get("micro"):
                    right = max(right if right is not None else -1e9, a["x"] + ext[a["id"]])
                    prev = a["id"]
                continue
            if a.get("micro"):
                base = self.area_xz.get(prev, (0.0, 0.0))
                self.area_xz[a["id"]] = (base[0], -90.0)
                continue
            x = 0.0 if right is None else right + 4 + ext[a["id"]]
            self.area_xz[a["id"]] = (x, 0.0)
            right, prev = x + ext[a["id"]], a["id"]

    def _layout(self, o: dict, width: float) -> list[tuple[float, float, float]]:
        n = o["count"]
        sp = o["spacing"] or width * 1.35
        if n == 1:
            return [(0.0, 0.0, 0.0)]
        rng = np.random.default_rng(len(o["id"]) * 7 + n)
        if o["layout"] == "column":
            return [(0.0, (i - (n - 1) / 2) * sp, 0.0) for i in range(n)]
        if o["layout"] == "grid":
            cols = math.ceil(math.sqrt(n))
            rows = math.ceil(n / cols)
            return [((i % cols - (cols - 1) / 2) * sp, (i // cols - (rows - 1) / 2) * sp, 0.0) for i in range(n)]
        if o["layout"] == "circle":
            r = max(sp * n / (2 * math.pi), sp)
            return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), -360 * i / n) for i in range(n)]
        if o["layout"] == "scatter":
            r = sp * math.sqrt(n) * 0.6
            pts = []
            for i in range(n):
                for _ in range(30):
                    p = rng.uniform(-r, r, 2)
                    if all(np.hypot(*(p - q[:2])) > sp * 0.8 for q in pts):
                        break
                pts.append((float(p[0]), float(p[1]), float(rng.uniform(-35, 35))))
            return pts
        return [((i - (n - 1) / 2) * sp, 0.0, 0.0) for i in range(n)]

    @staticmethod
    def solid_bounds(m) -> tuple[np.ndarray, np.ndarray]:
        """The box of the parts you actually see (thin cables, chains and rods don't make an object 'bigger')."""
        bs = []
        for p in m.parts:
            if not p.geo.tris or p.opacity < 0.3:
                continue
            lo, hi = p.geo.bounds()
            if sorted(hi - lo)[1] > 0.15:  # at least two sides thicker than 15 cm
                bs.append((lo, hi))
        if not bs:
            return m.bounds()
        return np.min([b[0] for b in bs], 0), np.max([b[1] for b in bs], 0)

    def _build(self) -> None:
        for o in self.plan["objects"]:
            key, m = self._model(o["asset"], o["params"])
            lo, hi = self.solid_bounds(m)
            width = float(max(hi[0] - lo[0], hi[2] - lo[2])) * o["scale"]
            ax, az = self.area_xz.get(o["area"], (0.0, 0.0))
            group = []
            for i, (dx, dz, dr) in enumerate(self._layout(o, width)):
                pos = np.array([ax + o["pos"][0] + dx, o["y"], az + o["pos"][1] + dz], np.float32)
                keys = [f"{key}:{k}" for k in range(len(m.parts))]
                inst = Inst(o["id"], i, o["asset"], m, keys, pos, o["rot"] + dr, o["scale"], o["area"],
                            float(np.linalg.norm(hi - lo)) / 2 * o["scale"], lo, hi)
                group.append(inst)
                self.insts.append(inst)
            self.groups[o["id"]] = group

    def _build_env(self) -> None:
        """The set dressing around every area (pads, props, people, lamps, pipe stands): see decor.py."""
        from . import decor  # noqa: PLC0415

        self.env_ids = set()
        self._add_env(decor.dress(self))

    def _add_env(self, items: list) -> None:
        for o in items:
            k = len(self.env_ids)
            key, m = self._model(o["asset"], o.get("params", {}))
            lo, hi = self.solid_bounds(m)
            oid = f"_env{k}"
            inst = Inst(oid, 0, o["asset"], m, [f"{key}:{j}" for j in range(len(m.parts))], np.asarray(o["at"], np.float32),
                        float(o.get("rot", 0.0)), 1.0, o["area"], float(np.linalg.norm(hi - lo)) / 2, lo, hi)
            self.insts.append(inst)
            self.groups[oid] = [inst]
            self.env_ids.add(oid)

    def upload(self, renderer) -> None:
        renderer.style = {**renderer.style, **self.style}  # the preset's background, floor, light and fog
        for key, m in self.models.items():
            for k, p in enumerate(m.parts):
                renderer.upload(f"{key}:{k}", p.geo)

    # ------------------------------------------------------------------ timing
    def _timing(self) -> None:
        self.scenes = []
        words = self.tl.get("words", [])
        for i, s in enumerate(self.plan["scenes"]):
            info = self.tl["scenes"][i] if i < len(self.tl["scenes"]) else {"start": i * 4.0, "dur": 4.0}
            st, du = float(info["start"]), float(info["dur"])
            ws = [w for w in words if st - 0.01 <= w["s"] < st + du]
            self.scenes.append({"plan": s, "start": st, "dur": du, "end": st + du, "words": ws})
        self.total = float(self.tl.get("total") or (self.scenes[-1]["end"] if self.scenes else 1.0))

    def at_time(self, i: int, at, default_frac: float = 0.1) -> float:
        """'at' (a spoken word, a fraction 0-1, or seconds) → seconds from the scene start."""
        sc = self.scenes[i]
        du = sc["dur"]
        if isinstance(at, (int, float)):
            return float(at) * du if 0 <= at <= 1 else min(du * 0.95, max(0.0, float(at)))
        if isinstance(at, str) and at.strip():
            target = [word_norm(w) for w in at.split() if word_norm(w)]
            ws = sc["words"]
            norm = [word_norm(w["w"]) for w in ws]
            for k in range(len(norm)):
                if target and norm[k:k + len(target)] == target:
                    return ws[k]["s"] - sc["start"]
            for k, n in enumerate(norm):  # "manure" matches "manure," / "methane" matches "methane."
                if target and n and (n.startswith(target[0]) or target[0].startswith(n)) and len(n) > 2:
                    return ws[k]["s"] - sc["start"]
        return du * default_frac

    def _events(self) -> None:
        self.events: list[Event] = []
        for i, sc in enumerate(self.scenes):
            for a in sc["plan"]["actions"]:
                oid, _, part = a["target"].partition(".")
                if oid not in self.groups:
                    continue
                do = a["do"]
                t0 = sc["start"] + self.at_time(i, a.get("at"), 0.0 if do in ("spin", "float", "flow", "bubbles",
                                                                              "smoke", "sparks", "glow") else 0.12)
                if do == "move":
                    dur = a.get("dur") or max(1.0, sc["end"] - t0 - 0.25)
                else:
                    dur = a.get("dur") or DEFAULT_DUR.get(do, 0.6)
                keep = bool(a.get("keep")) or do in PERSIST
                end = math.inf if keep else sc["end"] + (0.0 if do not in ("flow", "sparks") else 0.0)
                self.events.append(Event(do, oid, part, t0, float(dur), end, i, dict(a)))
        self.events.sort(key=lambda e: e.start)
        self.events_of: dict[str, list] = {}  # per object (long videos have hundreds of events)
        for e in self.events:
            self.events_of.setdefault(e.oid, []).append(e)
        # things that appear (or parts that are shown) later start hidden
        self.hidden_at_start = {o["id"] for o in self.plan["objects"] if o.get("hidden")}
        first = {}
        for e in self.events:
            if e.do in ("appear", "disappear", "drop") and e.oid not in first:
                first[e.oid] = "appear" if e.do == "drop" else e.do
        self.hidden_at_start |= {k for k, v in first.items() if v == "appear"}
        self.hidden_parts = {(e.oid, e.part) for e in self.events if e.do == "show_part"}
        if (self.tl.get("end") or {}).get("kind") == "overview" and self.scenes:  # the ending: everything working
            last, t_end = len(self.scenes) - 1, self.scenes[-1]["end"]
            seen = set()
            for e in list(self.events):
                if e.do in ("flow", "sparks", "bubbles") and (e.oid, e.do) not in seen:
                    seen.add((e.oid, e.do))
                    self.events.append(Event(e.do, e.oid, e.part, t_end, e.dur, math.inf, last, dict(e.params)))
            self.events.sort(key=lambda e: e.start)
            self.events_of = {}
            for e in self.events:
                self.events_of.setdefault(e.oid, []).append(e)

    # ------------------------------------------------------------------ state of one object at time T
    def state(self, inst: Inst, T: float) -> dict:
        st = {"vis": 0.0 if inst.oid in self.hidden_at_start else 1.0, "scale": 1.0, "pos": inst.pos.copy(),
              "yaw": inst.rot, "spin": 0.0, "spin_on": False, "fill": 1.0, "light": 0.0, "glow": 0.0, "alarm": 0.0,
              "shake": np.zeros(3), "drop": 0.0, "cut": 0.0, "cut_dir": None, "xray": False, "parts": {}, "travel": 0.0, "bob": 0.0}
        for part in [p for (o, p) in self.hidden_parts if o == inst.oid]:
            st["parts"][part] = 0.0
        n_group = len(self.groups[inst.oid])
        for e in self.events_of.get(inst.oid, ()):
            if e.start > T:
                break  # sorted by start time
            stagger = e.params.get("stagger", STAGGER.get(e.do, 0.0))
            t = T - e.start - stagger * inst.index * (1 if n_group > 1 else 0)
            if t < 0:
                continue
            active = T < e.end
            p = t / max(e.dur, 1e-3)
            if e.do == "appear":
                st["vis"] = pop(p)
            elif e.do == "drop":  # falls from above, lands with a small squash ("plop")
                st["vis"] = 1.0
                h = float(e.params.get("from", 2.2))
                st["drop"] = h * (1 - min(1.0, p) ** 2)
                if p >= 1:
                    q = (t - e.dur) / 0.35
                    st["scale"] = 1.0 + (0.18 * math.sin(q * math.pi) * (1 - q) if q < 1 else 0.0)
            elif e.do == "disappear":
                st["vis"] = 1 - ease(p)
            elif e.do == "grow":
                a, b = e.params.get("from", 0.2), e.params.get("to_value", 1.0)
                st["scale"] = a + (b - a) * ease_out(p)
            elif e.do == "move":
                start = st["pos"].copy()
                dest = self._dest(inst, e)
                u = ease(p)
                st["pos"] = start + (dest - start) * u
                d = dest - start
                if np.hypot(d[0], d[2]) > 0.3 and self._faces_travel(inst):
                    st["yaw"] = math.degrees(math.atan2(-d[2], d[0]))
                st["travel"] += float(np.linalg.norm(d)) * u
            elif e.do == "spin" and active:
                st["spin_on"] = True
                st["spin"] += 2 * math.pi * e.params.get("speed", 1.2) * t
            elif e.do in ("fill", "drain"):
                a = e.params.get("from", st["fill"] if e.do == "fill" else 1.0)
                b = e.params.get("to_value", 1.0 if e.do == "fill" else 0.25)
                if e.do == "fill" and "from" not in e.params and st["fill"] >= 0.99:
                    a = 0.15
                st["fill"] = a + (b - a) * ease(p)
            elif e.do == "light_on":
                st["light"] = ease(p)
            elif e.do == "light_off":
                st["light"] = 1 - ease(p)
            elif e.do == "glow" and active:
                st["glow"] = 0.12 + 0.12 * math.sin(t * 5.0)
            elif e.do == "alarm" and active:
                st["alarm"] = 0.5 + 0.5 * math.sin(t * 7.0)
            elif e.do == "shake" and p < 1:
                k = (1 - p) * 0.08 * max(1.0, inst.radius * 0.3)
                st["shake"] = np.array([math.sin(t * 61), math.sin(t * 47) * 0.4, math.sin(t * 53)]) * k
            elif e.do == "cutaway" and active:
                st["cut"] = ease(p)
                st["cut_dir"] = e.scene
            elif e.do == "xray" and active:
                st["xray"] = True
            elif e.do == "float":
                ph = inst.index * 1.7
                st["bob"] = 0.18 * math.sin(t * 1.6 + ph)
                st["yaw"] = inst.rot + 12 * math.sin(t * 0.5 + ph)
            elif e.do == "show_part":
                st["parts"][e.part] = pop(p)
            elif e.do == "hide_part":
                st["parts"][e.part] = 1 - ease(p)
        if getattr(self, "push", None) and (inst.oid, inst.index) in self.push:
            from .logic import pushed_state  # noqa: PLC0415

            pushed_state(self, inst, st, T)
        return st

    def _faces_travel(self, inst: Inst) -> bool:
        return any(p.kind == "wheel" for p in inst.model.parts) or inst.asset in ("cow", "person", "scraper")

    def _dest(self, inst: Inst, e: Event) -> np.ndarray:
        to = e.params.get("to")
        y = float(e.params["y"]) if isinstance(e.params.get("y"), (int, float)) else inst.pos[1]  # dive, climb, rise
        if isinstance(to, list):  # a group keeps its formation (each member keeps its offset from the first)
            ax, az = self.area_xz.get(inst.area, (0, 0))
            g = self.groups.get(inst.oid) or [inst]
            off = inst.pos - g[0].pos
            yy = y + off[1] if "y" in e.params else inst.pos[1]
            return np.array([ax + to[0] + off[0], yy, az + to[1] + off[2]], np.float32)
        if isinstance(to, str) and to.split(".")[0] in self.groups:
            other = self.groups[to.split(".")[0]][0]
            c = other.pos
            d = inst.pos - c
            d[1] = 0
            n = float(np.linalg.norm(d)) or 1.0
            return (c + d / n * (other.radius * 0.8 + inst.radius * 0.9)).astype(np.float32)
        return inst.pos

    # ------------------------------------------------------------------ geometry helpers
    def inst_matrix(self, inst: Inst, st: dict) -> np.ndarray:
        m = np.eye(4, dtype=np.float32)
        s = inst.scale * st["scale"] * max(0.0, st["vis"])
        m[:3, :3] = rot_matrix(0, st["yaw"], 0) * s
        m[:3, 3] = st["pos"] + st["shake"] + np.array([0, st["bob"] + st.get("drop", 0.0), 0])
        return m

    def group_box(self, oid: str, T: float | None = None, insts=None) -> tuple[np.ndarray, np.ndarray]:
        from .decor import inst_box  # noqa: PLC0415

        los, his = [], []
        for inst in (insts if insts is not None else self.groups.get(oid, [])):
            if T is None:
                lo, hi = inst_box(inst)
            else:
                st = self.state(inst, T)
                lo, hi = inst_box(inst, st["pos"], st["yaw"], st["scale"])
                lo, hi = lo + [0, st.get("drop", 0.0), 0], hi + [0, st.get("drop", 0.0), 0]
            los.append(lo)
            his.append(hi)
        if not los:
            return np.zeros(3), np.ones(3)
        return np.min(los, 0), np.max(his, 0)

    def _sub_box(self, oid: str, T: float) -> tuple[np.ndarray, np.ndarray]:
        """A long group (a row of 10 cows) is framed by its middle 3: the row runs out of the picture, like a real shot."""
        insts = self.groups.get(oid, [])
        if len(insts) > 3:  # the 3 closest to the middle (rows, grids and scatters alike)
            mid = np.mean([i.pos for i in insts], 0)
            insts = sorted(insts, key=lambda i: float(np.linalg.norm(i.pos - mid)))[:3]
        return self.group_box(oid, T, insts)

    def focus_ids(self, i: int) -> list[str]:
        """What shot i is about: the camera's subject + the things its line acts on or labels nearby."""
        sc = self.scenes[i]
        tgt = self._target(i)
        ids = [tgt]
        T = sc["start"] + sc["dur"] * 0.6
        lo, hi = self._sub_box(tgt, T)
        c = (lo + hi) / 2
        for a in sc["plan"]["actions"] + sc["plan"]["labels"]:
            oid = a["target"].split(".")[0]
            if oid in ids or oid not in self.groups or oid in getattr(self, "env_ids", ()):
                continue
            if self.groups[oid][0].area != self.groups[tgt][0].area:
                continue
            l2, h2 = self._sub_box(oid, T)
            if np.linalg.norm((l2 + h2) / 2 - c) > 9.0 or a.get("do") in ("flow", "sparks", "move"):
                continue
            u_lo, u_hi = np.minimum(lo, l2), np.maximum(hi, h2)  # only if the subject stays big in the picture
            if float((u_hi - u_lo)[[0, 2]].max()) <= 1.5 * max(float((hi - lo)[[0, 2]].max()), 1.0):
                ids.append(oid)
                lo, hi = u_lo, u_hi
        return ids

    def focus_box(self, i: int, T: float) -> tuple[np.ndarray, np.ndarray]:
        boxes = [self._sub_box(oid, T) for oid in self._focus[i]]
        return np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)

    def _target(self, i: int) -> str:
        t = self.scenes[i]["plan"]["camera"]["target"]
        return t if t in self.groups else next(iter(self.groups))

    def fit(self, lo, hi, az: float, el: float, fov: float, fill: float) -> tuple[np.ndarray, np.ndarray]:
        """(eye, look-at) so the box fills `fill` of the safe area and sits in its middle, seen from (az, el)."""
        W, H = self.size
        c = (np.asarray(lo, np.float64) + np.asarray(hi, np.float64)) / 2
        corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])], np.float64)
        ra, re = math.radians(az), math.radians(el)
        v = np.array([math.sin(ra) * math.cos(re), math.sin(re), math.cos(ra) * math.cos(re)])
        fwd = -v
        right = np.cross(fwd, [0.0, 1.0, 0.0])
        right /= max(np.linalg.norm(right), 1e-9)
        up = np.cross(right, fwd)
        tv = math.tan(math.radians(fov) / 2)
        th = tv * W / H
        rel = corners - c
        rx, ry, rz = rel @ right, rel @ up, rel @ fwd
        half_h = 1 - SAFE_TOP - SAFE_BOTTOM  # usable half height in screen units (-1..1)
        y_mid = 1 - 2 * (SAFE_TOP + half_h / 2)

        def size(d):
            depth = d + rz
            x, y = rx / (depth * th), ry / (depth * tv)
            return max((x.max() - x.min()) / 2 / 0.94, (y.max() - y.min()) / 2 / half_h), x, y

        a, b = float(max(-rz.min(), 0.0) + 0.3), 600.0
        for _ in range(40):  # bigger distance = smaller subject
            m = (a + b) / 2
            if size(m)[0] > fill:
                a = m
            else:
                b = m
        d = b
        _, x, y = size(d)
        shift = right * ((x.max() + x.min()) / 2) * d * th + up * ((y.max() + y.min()) / 2 - y_mid) * d * tv
        return c + v * d + shift, c + shift

    def anchor(self, oid: str, name: str, T: float) -> np.ndarray:
        insts = self.groups.get(oid, [])
        if not insts:
            return np.zeros(3)
        if len(insts) > 1 and name == "label":
            lo, hi = self.group_box(oid, T)
            return np.array([(lo[0] + hi[0]) / 2, hi[1] + 0.5, (lo[2] + hi[2]) / 2])
        inst = insts[0]
        st = self.state(inst, T)
        a = np.asarray(inst.model.anchors.get(name, inst.model.anchors.get("center", (0, 1, 0))), np.float32)
        return (self.inst_matrix(inst, {**st, "vis": 1.0}) @ np.append(a, 1.0))[:3]

    def path_world(self, oid: str, T: float) -> list | None:
        inst = self.groups[oid][0]
        path = inst.model.paths.get("flow")
        if not path:
            return None
        m = self.inst_matrix(inst, {**self.state(inst, T), "vis": 1.0})
        return [(m @ np.append(np.asarray(p, np.float32), 1.0))[:3] for p in path]

    # ------------------------------------------------------------------ camera
    def _cam_spec(self, i: int) -> dict:
        sc = self.scenes[i]
        cam = sc["plan"]["camera"]
        tgt = self._target(i)
        lo, hi = self.focus_box(i, sc["start"] + sc["dur"] * 0.6)
        az = cam.get("angle", 25.0 + 15 * ((i * 7) % 5 - 2))
        el = cam.get("height", 22.0)
        ext = hi - lo
        tags = set(getattr(assets.REGISTRY.get(self.groups[tgt][0].asset), "tags", []))
        if tags & {"animal", "people"}:
            el = min(max(el, 6.0), 20.0)  # animals and people: from the side or 3/4, never from above
        elif "vehicle" in tags:
            el = min(el, 30.0)
        elif self.size[1] > self.size[0] and max(ext[0], ext[2]) > 2.2 * max(ext[1], 0.5):
            el = max(el, 36.0)  # a wide, low subject in a tall frame: look down more, so the place fills the picture
        keys = [sc["start"] + self.at_time(i, k.get("at"), 0.2) for k in sc["plan"]["keywords"]]
        area = self.groups[tgt][0].area
        micro = any(a.get("micro") and a["id"] == area for a in self.plan["areas"])
        fill = FILL_MOVES.get(cam["move"], FILL) * min(1.25, max(0.8, cam.get("zoom", 1.0) ** 0.5))
        return {"move": cam["move"], "target": tgt, "lo": lo, "hi": hi, "c": (lo + hi) / 2,
                "r": max(1.2, float(np.linalg.norm(hi - lo)) / 2), "az": az, "el": el, "to_az": cam.get("to_angle"),
                "fov": cam.get("fov", self.fov), "keys": keys, "micro": micro, "fill": min(1.0, fill)}

    def _cam_path(self, i: int, t: float) -> tuple[np.ndarray, np.ndarray, float]:
        """Every move is framed from the subject's box (fit), then moves a little: every shot has motion."""
        sp = self._cams[i]
        du = self.scenes[i]["dur"]
        u = min(1.0, max(0.0, t / max(du, 1e-3)))
        mv = sp["move"]
        lo, hi = sp["lo"], sp["hi"]
        az, el, k = sp["az"], sp["el"], 1.0  # k > 1 = further than the fit, < 1 = closer
        if mv == "orbit":
            az = az + ((sp["to_az"] - sp["az"]) if sp["to_az"] is not None else 32) * ease(u)
        elif mv == "push_in":
            k = 1.2 - 0.3 * ease_out(u)
            az += 8 * u
        elif mv == "pull_out":
            k = 0.78 + 0.32 * ease(u)
            az -= 12 * u
        elif mv == "reveal":
            k = 0.8 + 0.35 * ease(u)
            el = 6 + (el - 6) * ease(u)
        elif mv == "fly_over":
            az = az - 35 + 70 * ease(u)
            el = 40
        elif mv == "top_down":
            el = 66
            az += 22 * u
        elif mv == "close_up":
            k = 1.05 - 0.12 * ease_out(u)
            el = min(el, 16)
            az += 14 * u
        elif mv == "low_angle":
            el = 7
            k = 1.0 - 0.1 * u
        elif mv == "follow":
            lo, hi = self.focus_box(i, self.scenes[i]["start"] + t)
            az += 10 * u
        elif mv == "cutaway":
            az += 24 * u
            el = 24
        elif mv == "static":
            k = 1.0 - 0.06 * u
            az += 5 * u
        for tk in sp["keys"]:  # punch-in on key words
            dt = self.scenes[i]["start"] + t - tk
            if 0 <= dt < 1.2:
                k *= 1 - 0.05 * math.sin(min(1.0, dt / 0.15) * math.pi / 2) * math.exp(-dt * 2.2)
        eye, tgt = self.fit(lo, hi, az, el, sp["fov"], sp["fill"])
        eye = tgt + (eye - tgt) * k
        if mv == "zoom_into":  # dive into the cut-open tank at the end of the shot (fades out at 82 %)
            q = max(0.0, (u - 0.62) / 0.38)
            inside = self.anchor(sp["target"], "inside", self.scenes[i]["start"] + t)
            tgt2 = tgt + (inside - tgt) * ease(q)
            eye = tgt2 + (eye - tgt) * (1.0 - 0.85 * (q * q * (3 - 2 * q)))
            tgt = tgt2
        eye[1] = max(eye[1], 0.35)
        return eye, tgt, sp["fov"]

    def _overview(self) -> tuple[np.ndarray, np.ndarray]:
        """The whole system, all normal areas at once (for the ending)."""
        micro = {a["id"] for a in self.plan["areas"] if a.get("micro")}
        ids = [o["id"] for o in self.plan["objects"] if o["area"] not in micro and o["id"] in self.groups]
        boxes = [self.group_box(o, self.total) for o in ids] or [(np.zeros(3), np.ones(3))]
        lo, hi = np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)
        long_x = (hi[0] - lo[0]) > (hi[2] - lo[2])
        tall = self.size[1] > self.size[0]
        az = (-90.0 if long_x else 0.0) if tall else (20.0 if long_x else -70.0)  # along the chain in a tall frame
        return self.fit(lo, hi, az, 20.0 if tall else 32.0, self.fov, 1.9 if tall else 1.0)

    def camera(self, i: int, t: float) -> tuple[np.ndarray, np.ndarray, float, float]:
        """(eye, target, fov, fade) for scene i at local time t, flying in from the previous scene.

        A very small, slow drift (like a camera operator breathing) keeps even still shots alive. It follows the
        clock of the whole video, so it never jumps from one shot to the next."""
        eye, tgt, fov, fade = self._camera(i, t)
        T = self.scenes[i]["start"] + t
        d = float(np.linalg.norm(np.asarray(eye) - np.asarray(tgt)))
        k = 0.011 * d
        drift = np.array([math.sin(T * 0.61), 0.6 * math.sin(T * 0.47 + 1.3), math.sin(T * 0.53 + 2.1)]) * k
        look = np.array([math.sin(T * 0.43 + 0.7), 0.5 * math.sin(T * 0.37 + 2.4), math.sin(T * 0.51 + 1.1)]) * k * 0.35
        return np.asarray(eye) + drift, np.asarray(tgt) + look, fov, fade

    def _camera(self, i: int, t: float) -> tuple[np.ndarray, np.ndarray, float, float]:
        du_i = self.scenes[i]["dur"]
        if i == len(self.scenes) - 1 and t > du_i and self.ending == "overview":
            return self._ending_camera(t - du_i)
        eye, tgt, fov = self._cam_path(i, t)
        fade = 0.0
        du = self.scenes[i]["dur"]
        if self._cams[i]["move"] == "zoom_into" and t > du * 0.82:  # fade before the camera is inside
            fade = ease((t - du * 0.82) / (du * 0.15))
        if i == 0:
            return eye, tgt, fov, fade
        prev = self._cams[i - 1]
        hard = prev["move"] == "zoom_into" or prev["micro"] != self._cams[i]["micro"]
        if hard:  # into / out of the micro world: fade instead of flying
            return eye, tgt, fov, max(fade, 1 - min(1.0, t / 0.35))
        tr = min(1.1, 0.4 * du)
        if t < tr:
            pe, pt, pf = self._cam_path(i - 1, self.scenes[i - 1]["dur"])
            ne, nt, nf = self._cam_path(i, tr)
            w = ease(t / tr)
            lift = 0.22 * float(np.linalg.norm(ne - pe)) * math.sin(math.pi * w)
            eye = pe + (ne - pe) * w + np.array([0, lift, 0])
            tgt = pt + (nt - pt) * w
            fov = pf + (nf - pf) * w
        return eye, tgt, fov, fade

    def _ending_camera(self, t: float):
        n = len(self.scenes) - 1
        e0, t0, f0 = self._cam_path(n, self.scenes[n]["dur"])
        oe, ot = self._overview()
        fe, ft, ff = self._cam_path(0, 0.0)
        end = self.tl.get("end", {}).get("dur", END_OVERVIEW)
        a, b = min(1.3, end * 0.36), max(min(1.3, end * 0.36) + 0.1, end - 1.2)
        if t < a:  # up and out to the overview
            w = ease(t / a)
            lift = 0.18 * float(np.linalg.norm(oe - e0)) * math.sin(math.pi * w)
            return e0 + (oe - e0) * w + np.array([0, lift, 0]), t0 + (ot - t0) * w, f0 + (self.fov - f0) * w, 0.0
        if t < b:  # the whole system working, slowly turning
            ang = math.radians(8 * (t - a) / max(b - a, 1e-3))
            rel = oe - ot
            rel = np.array([rel[0] * math.cos(ang) - rel[2] * math.sin(ang), rel[1],
                            rel[0] * math.sin(ang) + rel[2] * math.cos(ang)])
            return ot + rel, ot, self.fov, 0.0
        w = ease(min(1.0, (t - b) / max(end - b, 1e-3)))  # back down to the first shot: the video loops
        ang = math.radians(8)
        rel = oe - ot
        oe2 = ot + np.array([rel[0] * math.cos(ang) - rel[2] * math.sin(ang), rel[1],
                             rel[0] * math.sin(ang) + rel[2] * math.cos(ang)])
        return oe2 + (fe - oe2) * w, ot + (ft - ot) * w, self.fov + (ff - self.fov) * w, 0.0

    def sun(self, eye, tgt) -> tuple:
        d = np.asarray(eye) - np.asarray(tgt)
        az = math.atan2(d[0], d[2]) - math.radians(40)
        el = math.radians(52)
        return (math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el))

    # ------------------------------------------------------------------ one frame
    def scene_at(self, T: float) -> int:
        for i, sc in enumerate(self.scenes):
            if T < sc["end"] - 1e-6:
                return i
        return len(self.scenes) - 1

    def frame(self, T: float, label_tex=None) -> Frame:
        i = self.scene_at(T)
        sc = self.scenes[i]
        t = T - sc["start"] if (self.ending == "overview" and i == len(self.scenes) - 1) else min(T - sc["start"], sc["dur"])
        eye, tgt, fov, fade = self.camera(i, t)
        draws = []
        self._aim_i = i
        cam_dir = np.asarray(eye) - np.asarray(tgt)
        focus_id = self._cams[i]["target"]
        flying = i > 0 and t < min(1.1, 0.4 * sc["dur"]) + 0.3
        prev_id = self._cams[i - 1]["target"] if i > 0 else None
        fwd = np.asarray(tgt, np.float64) - np.asarray(eye, np.float64)
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        half = math.radians(fov) / 2 * max(1.0, self.size[0] / self.size[1]) * 1.25  # a little wider than the view
        for inst in self.insts:
            rel = inst.pos - eye  # skip what is behind the camera or far outside the picture (much faster)
            dist = float(np.linalg.norm(rel))
            if dist > 260 or (dist > inst.radius * 1.5 and float(np.dot(rel, fwd)) / dist <
                                    math.cos(min(math.pi / 2, half + math.asin(min(1.0, inst.radius * 1.5 / dist))))):
                if inst.oid not in self.groups or not self.events_of.get(inst.oid):
                    continue
            st = self.state(inst, T)
            if st["vis"] <= 0.01:
                continue
            if np.linalg.norm(st["pos"] - eye) > 260:
                continue
            if inst.oid in self.env_ids and self._in_front_of_subject(inst, st, eye, tgt, fov, i):
                continue  # a prop drawn over the subject: leave it out (clean composition)
            hidden_parts = set()
            if inst.oid not in self._focus[i] and not (flying and inst.oid == prev_id) and \
                    inst.asset not in ("pad", "ground", "terrain", "ground_plate") and self._blocks(inst, st, eye, tgt):
                if inst.oid in self.env_ids:
                    continue  # a prop in front of the subject: leave it out
                if any(p.shell for p in inst.model.parts):  # a roof or wall in the way: leave out exactly the
                    hidden_parts = self._blocking_parts(inst, st, eye, tgt)  # parts that block (no ghost lines)
            if inst.oid not in self._focus[i] and any(p.shell for p in inst.model.parts):
                hidden_parts |= self._shell_parts_over_subject(inst, st, eye, tgt, fov, i)
            m0 = self.inst_matrix(inst, st)
            clip = None
            if st["cut"] > 0:
                n = cam_dir.copy()
                n[1] = 0
                n /= max(np.linalg.norm(n), 1e-6)
                c = st["pos"]  # remove the half that faces the camera
                clip = (*n, float(np.dot(n, c) + inst.radius * (1 - st["cut"]) * 1.2 - 0.02))
            for k, part in enumerate(inst.model.parts):
                vis = st["parts"].get(part.name, 1.0)
                if vis <= 0.01 or k in hidden_parts:
                    continue
                m = m0
                local = np.eye(4, dtype=np.float32)
                if part.kind in ("blade", "wheel") and st["spin_on"] or (part.kind == "wheel" and st["travel"]):
                    ang = st["spin"] if part.kind == "blade" else (st["travel"] / 0.6 + st["spin"])
                    axis = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[part.axis]
                    deg = math.degrees(ang) * (-1 if part.kind == "wheel" else 1)
                    r = rot_matrix(*(np.array(axis) * deg))
                    pv = np.asarray(part.pivot, np.float32)
                    local[:3, :3] = r
                    local[:3, 3] = pv - r @ pv
                if part.kind == "piston" and st["spin_on"]:  # engines: pistons go up and down in turn
                    local[1, 3] += 0.22 * math.sin(st["spin"] * 2.0 + k * 1.9)
                if part.kind == "rocker" and st["spin_on"]:  # pumpjacks, arms, wings, needles: swing back and forth
                    axis = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[part.axis]
                    r = rot_matrix(*(np.array(axis) * 18.0 * math.sin(st["spin"])))
                    pv = np.asarray(part.pivot, np.float32)
                    local[:3, :3] = r
                    local[:3, 3] = pv - r @ pv
                if part.kind == "flame":  # fire flickers all the time (a pure function of T)
                    lo, hi = part.geo.bounds()
                    f = 1.0 + 0.14 * math.sin(T * 11.0 + k * 1.7) + 0.06 * math.sin(T * 23.0 + k)
                    sm = np.eye(4, dtype=np.float32)
                    sm[1, 1] = f
                    sm[1, 3] = float(lo[1]) * (1 - f)
                    local = local @ sm
                if part.kind == "liquid" and st["fill"] != 1.0:  # the level drops inside its own container
                    lo, hi = part.geo.bounds()
                    f = max(0.02, st["fill"])
                    sm = np.diag([1, f, 1, 1]).astype(np.float32)
                    sm[1, 3] = float(lo[1]) * (1 - f)
                    local = local @ sm
                if part.kind == "crust" and st["fill"] != 1.0:
                    lo, hi = part.geo.bounds()
                    local[1, 3] += (st["fill"] - 1) * float(lo[1])
                if vis < 0.999:
                    lo, hi = part.geo.bounds()
                    pc = (lo + hi) / 2
                    sm = np.eye(4, dtype=np.float32)
                    sm[:3, :3] *= vis
                    sm[:3, 3] = pc - pc * vis
                    local = local @ sm
                if not np.allclose(local, np.eye(4)):
                    m = m0 @ local
                color = hex_rgb(part.color)
                emi = part.emissive
                if part.kind == "light":
                    emi = max(emi, st["light"])
                    if st["light"] > 0:
                        lamp = (1.0, 0.85, 0.42)
                        color = tuple(a + (b - a) * st["light"] for a, b in zip(color, lamp))
                emi += st["glow"]
                if st["alarm"]:
                    color = tuple(a + (b - a) * (0.55 + 0.35 * st["alarm"]) for a, b in zip(color, (0.95, 0.12, 0.08)))
                    emi += 0.25 + 0.35 * st["alarm"]
                inner = tuple(max(0.05, x * 0.45) for x in color)
                xr = st["xray"] and part.shell
                draws.append(Draw(inst.keys[k], m, color, emi, part.opacity, clip, inner, xr,
                                  shadow=part.opacity > 0.5))
        parts = self.particles(i, T)
        draws += self.puffs(i, T)
        c = np.asarray(tgt, np.float64)
        dist = float(np.linalg.norm(np.asarray(eye) - c))
        labels = self.labels(i, T, eye, tgt, fov, label_tex) if label_tex and t <= sc["dur"] else []
        return Frame(eye=tuple(eye), target=tuple(tgt), fov=fov, draws=draws, particles=parts, labels=labels,
                     focus=tuple(c), focus_radius=max(8.0, dist * 0.62), grid_center=(c[0], c[2]),
                     fade=fade, sun=self.sun(eye, tgt), bloom=0.6, lights=self._lights(c, T))

    def _lights(self, c, T: float) -> list:
        """Warm point lights: lamps (always on) and windows that are lit, nearest to what we look at (max 4)."""
        found = []
        for inst in self.insts:
            if float(np.linalg.norm(inst.pos - c)) > 45:
                continue
            kinds = {p.kind for p in inst.model.parts}
            if not kinds & {"lamp", "light"}:
                continue
            st = self.state(inst, T)
            if st["vis"] < 0.5:
                continue
            m = self.inst_matrix(inst, st)
            for p in inst.model.parts:
                on = p.kind == "lamp" or (p.kind == "light" and st["light"] > 0.5 and inst.asset in ("house", "factory",
                                                                                                   "skyscraper"))
                if not on:
                    continue
                lo, hi = p.geo.bounds()
                pos = (m @ np.append((lo + hi) / 2, 1.0))[:3]
                found.append((float(np.linalg.norm(pos - c)), tuple(pos), (1.0, 0.72, 0.4), 6.0 if p.kind == "lamp" else 4.0))
        found.sort(key=lambda x: x[0])
        return [(p, col, r) for _, p, col, r in found[:4]]

    # ------------------------------------------------------------------ particles
    def particles(self, i: int, T: float) -> np.ndarray | None:
        out = self._air(i, T)
        for e in self.events:
            if e.do not in ("flow", "bubbles", "smoke", "sparks", "cutaway") or not (e.start <= T < e.end):
                continue
            if abs(e.scene - i) > 1:
                continue
            t = T - e.start
            color = hex_rgb(e.params["color"]) if e.params.get("color") else FLOW_COLORS.get(e.do, (0.45, 0.86, 0.36))
            fade = min(1.0, t / 0.4)
            rng = np.random.default_rng(zlib.crc32(f"{e.oid}/{e.do}/{e.scene}".encode()))
            if e.do in ("flow", "sparks"):
                path = self._flow_path(e, T)
                if path is None:
                    continue
                n = int(e.params.get("count", 18 if e.do == "flow" else 14))
                lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
                total = float(lengths.sum()) or 1.0
                speed = e.params.get("speed", 2.2 if e.do == "flow" else 7.0)
                ph = rng.random(n)
                for k in range(n):
                    s = ((ph[k] + speed * t / total) % 1.0) * total
                    if s > speed * t:  # particles start at the beginning (no pop-in in the middle)
                        continue
                    p = _along(path, lengths, s)
                    if e.do == "sparks":
                        p = p + rng.normal(0, 0.05, 3)
                    size = (0.16 if e.do == "flow" else 0.1) * fade
                    out.append([*p, size, *color, 0.5 if e.do == "flow" else 1.2])
            elif e.do == "cutaway":  # the cut-open tank shows what lives inside: drifting bacteria
                inst = self.groups[e.oid][0]
                lo, hi = self.group_box(e.oid, T)
                c = (lo + hi) / 2
                surf = self.anchor(e.oid, "surface", T) if "surface" in inst.model.anchors else \
                    self.anchor(e.oid, "inside", T) * np.array([1, 2.0, 1])
                r = min(hi[0] - lo[0], hi[2] - lo[2]) * 0.4
                for k in range(46):
                    a, rr, h = rng.random() * 6.283, math.sqrt(rng.random()) * r, rng.random()
                    y = float(lo[1]) + 0.3 + h * max(0.5, float(surf[1]) - float(lo[1]) - 0.5)
                    wob = 0.15 * math.sin(t * 1.7 + k)
                    out.append([c[0] + rr * math.cos(a) + wob, y + 0.1 * math.sin(t * 2.1 + k * 0.7),
                                c[2] + rr * math.sin(a), 0.11 * min(1.0, t / 0.6), 0.45, 0.86, 0.36, 0.4])
            elif e.do == "bubbles":
                inst = self.groups[e.oid][0]
                lo, hi = self.group_box(e.oid, T)
                c = (lo + hi) / 2
                surf = self.anchor(e.oid, "surface", T) if "surface" in inst.model.anchors else np.array([c[0], hi[1], c[2]])
                r = min(hi[0] - lo[0], hi[2] - lo[2]) * 0.35
                for k in range(int(e.params.get("count", 26))):
                    a, rr, ph = rng.random() * 6.283, math.sqrt(rng.random()) * r, rng.random()
                    h = ((ph + t * 0.45) % 1.0)
                    y = float(lo[1]) + 0.3 + h * (float(surf[1]) - float(lo[1]) + 1.2)
                    out.append([c[0] + rr * math.cos(a), y, c[2] + rr * math.sin(a), 0.1 + 0.08 * h, *color, 0.35])
        return np.asarray(out, np.float32) if out else None

    def _air(self, i: int, T: float) -> list:
        """Ambient particles of the place: bubbles under water, dust, snow, stars, blood cells."""
        kind = self.look.get("air")
        if not kind:
            return []
        c = np.asarray(self._cams[i]["c"], np.float64)
        r = max(8.0, self._cams[i]["r"] * 3)
        rng = np.random.default_rng(zlib.crc32(f"air/{kind}".encode()))
        n = {"stars": 160, "snow": 110, "bubbles": 80, "dust": 70, "cells": 36}[kind]
        base = rng.random((n, 3))
        eye = np.asarray(self.camera(i, T - self.scenes[i]["start"])[0], np.float64) if i < len(self.scenes) else c
        near = max(2.0, 0.45 * float(np.linalg.norm(eye - c)))  # nothing big and blurry right in front of the lens
        out = []
        for k in range(n):
            x, y, z = (base[k] - 0.5) * 2 * r
            if kind == "stars":
                d = np.array([x, abs(y) + r * 0.3, z])
                p = c + d / max(np.linalg.norm(d), 1e-6) * r * 6
                out.append([*p, 0.35 * (0.5 + base[k][0]), 1.0, 1.0, 1.0, 1.5])
                continue
            h = 2 * r
            if kind == "bubbles":
                y = (base[k][1] * h + T * 0.9) % h - r * 0.2
                col, size, emi = (0.75, 0.92, 1.0), 0.07 + 0.05 * base[k][2], 0.5
            elif kind == "snow":
                y = h - (base[k][1] * h + T * 0.7) % h
                col, size, emi = (1.0, 1.0, 1.0), 0.06, 0.4
            elif kind == "cells":
                y = abs(y) * 0.5 + 0.5 + 0.3 * np.sin(T * 0.8 + k)
                x += np.sin(T * 0.3 + k) * 0.8
                col, size, emi = (0.82, 0.12, 0.16), 0.16 + 0.1 * base[k][2], 0.1
            else:  # dust
                y = abs(y) * 0.4 + 0.3 + 0.2 * np.sin(T * 0.5 + k)
                x += T * 0.25 % (2 * r)
                col, size, emi = (0.95, 0.85, 0.65), 0.04, 0.2
            if np.linalg.norm(np.array([c[0] + x, y, c[2] + z]) - eye) < near:
                continue
            out.append([c[0] + x, y, c[2] + z, size, *col, emi])
        return out

    def puffs(self, i: int, T: float) -> list:
        """Smoke: soft see-through puffs that rise, grow and fade."""
        out = []
        for e in self.events:
            if e.do != "smoke" or not (e.start <= T < e.end) or abs(e.scene - i) > 1:
                continue
            t = T - e.start
            src = self.anchor(e.oid, "exhaust" if "exhaust" in self.groups[e.oid][0].model.anchors else "top", T)
            color = hex_rgb(e.params["color"]) if e.params.get("color") else FLOW_COLORS["smoke"]
            for k in range(8):
                h = (k / 8 + t * 0.32) % 1.0
                if h > t * 0.32 + 0.02:
                    continue
                drift = np.array([0.9 * h + 0.2 * math.sin(k * 2.1 + t), 3.2 * h, 0.35 * math.sin(k * 1.3)])
                s = 0.25 + 0.75 * h
                m = np.eye(4, dtype=np.float32)
                m[:3, :3] *= s
                m[:3, 3] = src + drift
                out.append(Draw("__puff", m, color, 0.0, 0.55 * (1 - h) ** 0.7, shadow=False))
        return out

    def _blocking_parts(self, inst: Inst, st: dict, eye, tgt) -> set:
        """Indexes of the shell parts (walls, posts, roofs) that are between the camera and the subject."""
        m = self.inst_matrix(inst, {**st, "vis": 1.0})
        try:
            inv = np.linalg.inv(m.astype(np.float64))
        except np.linalg.LinAlgError:
            return set()
        e = (inv @ np.append(np.asarray(eye, np.float64), 1.0))[:3]
        out = set()
        for k, part in enumerate(inst.model.parts):
            if not part.shell:
                continue
            for tp in self._aim_points(tgt):
                t = (inv @ np.append(tp, 1.0))[:3]
                if any(_seg_box(e, t, a, b) for a, b in (part.boxes or [part.geo.bounds()])):
                    out.add(k)
                    break
        return out

    def _in_front_of_subject(self, inst: Inst, st: dict, eye, tgt, fov, i: int) -> bool:
        """A prop that is nearer than the subject and overlaps it on screen."""
        if inst.asset in ("pad", "ground_plate", "ground", "rail", "fence", "railing", "pipe_stand"):
            return False
        from .decor import inst_box  # noqa: PLC0415

        lo, hi = inst_box(inst, st["pos"], st["yaw"], st["scale"])
        slo, shi = self._cams[i]["lo"], self._cams[i]["hi"]
        e = np.asarray(eye, np.float64)
        if np.linalg.norm((lo + hi) / 2 - e) >= np.linalg.norm((slo + shi) / 2 - e):
            return False
        def rect(a, b):  # noqa: E306
            c = np.array([[x, y, z] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])])
            p = project_points(eye, tgt, fov, self.size, c)
            return p[:, 0].min(), p[:, 0].max(), p[:, 1].min(), p[:, 1].max(), (p[:, 2] > 0).all()
        px0, px1, py0, py1, ok1 = rect(lo, hi)
        sx0, sx1, sy0, sy1, ok2 = rect(slo, shi)
        return bool(ok1 and ok2 and px0 < sx1 and px1 > sx0 and py0 < sy1 and py1 > sy0)

    def _shell_parts_over_subject(self, inst: Inst, st: dict, eye, tgt, fov, i: int) -> set:
        """Posts, walls and roof parts that are nearer than the subject and cover it on screen."""
        m = self.inst_matrix(inst, {**st, "vis": 1.0})
        slo, shi = self._cams[i]["lo"], self._cams[i]["hi"]
        e = np.asarray(eye, np.float64)
        ds = float(np.linalg.norm((slo + shi) / 2 - e))
        sc = np.array([[x, y, z] for x in (slo[0], shi[0]) for y in (slo[1], shi[1]) for z in (slo[2], shi[2])])
        sp = project_points(eye, tgt, fov, self.size, sc)
        if not (sp[:, 2] > 0).all():
            return set()
        sx0, sx1, sy0, sy1 = sp[:, 0].min(), sp[:, 0].max(), sp[:, 1].min(), sp[:, 1].max()
        out = set()
        for k, part in enumerate(inst.model.parts):
            if not part.shell:
                continue
            for a, b in (part.boxes or [part.geo.bounds()]):
                if sorted(np.asarray(b) - np.asarray(a))[1] > 0.5:
                    continue  # only thin posts and beams; walls and domes stay (no hollow tanks)
                c = np.array([[x, y, z, 1.0] for x in (a[0], b[0]) for y in (a[1], b[1]) for z in (a[2], b[2])])
                w = (c @ m.T.astype(np.float64))[:, :3]
                if float(np.linalg.norm(w.mean(0) - e)) >= ds * 0.92:
                    continue
                p = project_points(eye, tgt, fov, self.size, w)
                if (p[:, 2] > 0).all() and p[:, 0].min() < sx1 and p[:, 0].max() > sx0 and \
                        p[:, 1].min() < sy1 and p[:, 1].max() > sy0:
                    out.add(k)
                    break
        return out

    def _aim_points(self, tgt) -> list:
        """The look-at point and the top corners of the subject: if any of them is hidden, the thing blocks."""
        i = getattr(self, "_aim_i", None)
        pts = [np.asarray(tgt, np.float64)]
        if i is not None:
            lo, hi = self._cams[i]["lo"], self._cams[i]["hi"]
            pts += [np.array([x, hi[1] * 0.8 + lo[1] * 0.2, z]) for x in (lo[0], hi[0]) for z in (lo[2], hi[2])]
        return pts

    def _blocks(self, inst: Inst, st: dict, eye, tgt) -> bool:
        """Does this object stand between the camera and what it looks at? (rays vs box)"""
        from .decor import inst_box  # noqa: PLC0415

        lo, hi = inst_box(inst, st["pos"], st["yaw"], st["scale"])
        return any(_seg_box(np.asarray(eye, np.float64), tp, lo, hi) for tp in self._aim_points(tgt))

    def _blocks_old(self, inst: Inst, st: dict, eye, tgt) -> bool:
        s = inst.scale * st["scale"]
        lo, hi = st["pos"] + inst.lo * s, st["pos"] + inst.hi * s
        e, d = np.asarray(eye, np.float64), np.asarray(tgt, np.float64) - np.asarray(eye, np.float64)
        dist = float(np.linalg.norm(d))
        if dist < 1e-6:
            return False
        tmin, tmax = 0.0, 0.92  # only between the camera and (almost) the target
        for a in range(3):
            if abs(d[a]) < 1e-9:
                if e[a] < lo[a] or e[a] > hi[a]:
                    return False
                continue
            t1, t2 = (lo[a] - e[a]) / d[a], (hi[a] - e[a]) / d[a]
            tmin, tmax = max(tmin, min(t1, t2)), min(tmax, max(t1, t2))
            if tmin > tmax:
                return False
        return True

    def _flow_path(self, e: Event, T: float):
        own = self.path_world(e.oid, T)
        if own is not None and not e.params.get("to"):
            return np.asarray(own)
        a = self.anchor(e.oid, "outlet" if "outlet" in self.groups[e.oid][0].model.anchors else "top", T)
        to = e.params.get("to")
        if isinstance(to, str) and to.split(".")[0] in self.groups:
            oid = to.split(".")[0]
            other = self.path_world(oid, T)
            if other is not None:
                return np.asarray(other)
            names = self.groups[oid][0].model.anchors
            b = self.anchor(oid, "inlet" if "inlet" in names else ("wire" if "wire" in names else "top"), T)
        elif isinstance(to, list):
            ax, az = self.area_xz.get(self.groups[e.oid][0].area, (0, 0))
            b = np.array([ax + to[0], 1.0, az + to[1]])
        else:
            b = a + np.array([0, 3.0, 0])
        mid = (a + b) / 2 + np.array([0, 0.25 * float(np.linalg.norm(b - a)), 0])
        return np.asarray([a + (mid - a) * k / 6 for k in range(6)] + [mid + (b - mid) * k / 6 for k in range(7)])

    # ------------------------------------------------------------------ labels
    def labels(self, i: int, T: float, eye, tgt, fov, label_tex) -> list:
        sc = self.scenes[i]
        t = T - sc["start"]
        W, H = self.size
        out = []
        for lb in sc["plan"]["labels"]:
            t0 = self.at_time(i, lb.get("at"), 0.15)
            if t < t0 or lb["target"] not in self.groups:
                continue
            p = self.anchor(lb["target"], "label", T)
            x, y, w = project_points(eye, tgt, fov, self.size, [p])[0]
            if w <= 0.1:
                continue
            text = lb["text"]
            if lb.get("count"):
                a, b = lb["count"]
                v = a + (b - a) * ease_out(min(1.0, (t - t0) / max(0.8, sc["dur"] - t0 - 0.4)))
                num = f"{int(round(v)):,}"
                text = text.replace("{n}", num) if "{n}" in text else f"{num} {text}"
            img, key = label_tex(text, lb["kind"])
            k = min(1.0, (t - t0) / 0.22)
            out_fade = min(1.0, (sc["dur"] - t) / 0.2)
            x = min(max(x, img.shape[1] * 0.5 + 12), W - img.shape[1] * 0.5 - 12)
            y = min(max(y, img.shape[0] + 0.14 * H), H - 0.08 * H)
            out.append(Label(key, img, float(x), float(y), scale=pop(k) * 0.98 + 0.02, alpha=min(k * 1.5, out_fade)))
        out.sort(key=lambda lb: lb.y)  # push overlapping labels apart
        for a in range(1, len(out)):
            for b in range(a):
                la, lb2 = out[a], out[b]
                if abs(la.x - lb2.x) < (la.image.shape[1] + lb2.image.shape[1]) / 2 and \
                        abs(la.y - lb2.y) < la.image.shape[0] * 1.05:
                    la.y = lb2.y + la.image.shape[0] * 1.08
        return out


def _along(path: np.ndarray, lengths: np.ndarray, s: float) -> np.ndarray:
    for k, ln in enumerate(lengths):
        if s <= ln or k == len(lengths) - 1:
            u = s / ln if ln > 0 else 0
            return path[k] + (path[k + 1] - path[k]) * min(1.0, u)
        s -= ln
    return path[-1]


def area_layout(plan: dict) -> dict:
    """Where every area goes (x, z), without building the whole world."""
    w = World.__new__(World)
    w.plan, w.models = plan, {}
    w._areas()
    return {k: (round(float(x), 2), round(float(z), 2)) for k, (x, z) in w.area_xz.items()}


def freeze_layout(plan: dict) -> dict:
    """Write the area positions into the plan, so a later fix (a bigger tank) doesn't move every other area."""
    pos = area_layout(plan)
    for a in plan["areas"]:
        if "x" not in a and a["id"] in pos:
            a["x"], a["z"] = pos[a["id"]]
    return plan


def _seg_box(a, b, lo, hi, t0: float = 0.02, t1: float = 0.94) -> bool:
    """Does the segment a→b (between 2 % and 94 % of the way) pass through the box?"""
    d = np.asarray(b, np.float64) - np.asarray(a, np.float64)
    tmin, tmax = t0, t1
    for k in range(3):
        if abs(d[k]) < 1e-9:
            if a[k] < lo[k] or a[k] > hi[k]:
                return False
            continue
        u, v = (lo[k] - a[k]) / d[k], (hi[k] - a[k]) / d[k]
        tmin, tmax = max(tmin, min(u, v)), min(tmax, max(u, v))
        if tmin > tmax:
            return False
    return True
