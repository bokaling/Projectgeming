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

PERSIST = {"appear", "disappear", "grow", "move", "spin", "fill", "drain", "light_on", "light_off", "float",
           "show_part", "hide_part"}
DEFAULT_DUR = {"appear": 0.45, "disappear": 0.4, "grow": 1.2, "fill": 1.6, "drain": 1.6, "light_on": 0.35,
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
        self.plan, self.tl, self.size, self.lang = plan, timeline, size, lang
        self.fov = 40.0 if size[0] < size[1] else 34.0
        self.models: dict = {}
        self.insts: list[Inst] = []
        self.groups: dict[str, list[Inst]] = {}
        self.obj = {o["id"]: o for o in plan["objects"]}
        self._areas()
        self._build()
        self._timing()
        self._events()
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
            x = 0.0 if right is None else right + 7 + ext[a["id"]]
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

    def _build(self) -> None:
        for o in self.plan["objects"]:
            key, m = self._model(o["asset"], o["params"])
            lo, hi = m.bounds()
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

    def upload(self, renderer) -> None:
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
            if e.do in ("appear", "disappear") and e.oid not in first:
                first[e.oid] = e.do
        self.hidden_at_start |= {k for k, v in first.items() if v == "appear"}
        self.hidden_parts = {(e.oid, e.part) for e in self.events if e.do == "show_part"}

    # ------------------------------------------------------------------ state of one object at time T
    def state(self, inst: Inst, T: float) -> dict:
        st = {"vis": 0.0 if inst.oid in self.hidden_at_start else 1.0, "scale": 1.0, "pos": inst.pos.copy(),
              "yaw": inst.rot, "spin": 0.0, "spin_on": False, "fill": 1.0, "light": 0.0, "glow": 0.0, "alarm": 0.0,
              "shake": np.zeros(3), "cut": 0.0, "cut_dir": None, "xray": False, "parts": {}, "travel": 0.0, "bob": 0.0}
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
        return st

    def _faces_travel(self, inst: Inst) -> bool:
        return any(p.kind == "wheel" for p in inst.model.parts) or inst.asset in ("cow", "person", "scraper")

    def _dest(self, inst: Inst, e: Event) -> np.ndarray:
        to = e.params.get("to")
        if isinstance(to, list):
            ax, az = self.area_xz.get(inst.area, (0, 0))
            return np.array([ax + to[0], inst.pos[1], az + to[1]], np.float32)
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
        m[:3, 3] = st["pos"] + st["shake"] + np.array([0, st["bob"], 0])
        return m

    def group_box(self, oid: str, T: float | None = None) -> tuple[np.ndarray, np.ndarray]:
        los, his = [], []
        for inst in self.groups.get(oid, []):
            pos = self.state(inst, T)["pos"] if T is not None else inst.pos
            los.append(pos + inst.lo * inst.scale)
            his.append(pos + inst.hi * inst.scale)
        if not los:
            return np.zeros(3), np.ones(3)
        return np.min(los, 0), np.max(his, 0)

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
        tgt = cam["target"] if cam["target"] in self.groups else next(iter(self.groups))
        lo, hi = self.group_box(tgt, sc["start"] + sc["dur"] * 0.5)
        c = (lo + hi) / 2
        r = max(1.2, float(np.linalg.norm(hi - lo)) / 2)
        W, H = self.size
        vf = math.radians(cam.get("fov", self.fov))
        hf = 2 * math.atan(math.tan(vf / 2) * W / H)
        d = r / math.sin(min(vf, hf) / 2) * 0.92
        if cam.get("distance"):
            d = min(max(cam["distance"], d * 0.35), d * 3)
        d /= cam.get("zoom", 1.0)
        az = cam.get("angle", 25.0 + 15 * ((i * 7) % 5 - 2))
        el = cam.get("height", 24.0)
        keys = [sc["start"] + self.at_time(i, k.get("at"), 0.2) for k in sc["plan"]["keywords"]]
        area = self.groups[tgt][0].area
        micro = any(a.get("micro") and a["id"] == area for a in self.plan["areas"])
        return {"move": cam["move"], "target": tgt, "c": c, "r": r, "d": d, "az": az, "el": el,
                "to_az": cam.get("to_angle"), "fov": cam.get("fov", self.fov), "keys": keys, "micro": micro,
                "lift": (hi[1] - lo[1]) * 0.15}

    def _cam_path(self, i: int, t: float) -> tuple[np.ndarray, np.ndarray, float]:
        sp = self._cams[i]
        du = self.scenes[i]["dur"]
        u = min(1.0, max(0.0, t / max(du, 1e-3)))
        mv = sp["move"]
        c = sp["c"].copy()
        d, az, el = sp["d"], sp["az"], sp["el"]
        if mv == "orbit":
            az = az + ((sp["to_az"] - sp["az"]) if sp["to_az"] is not None else 38) * u
        elif mv == "push_in":
            d *= 1.25 - 0.45 * ease_out(u)
            az += 10 * u
        elif mv == "pull_out":
            d *= 0.8 + 0.5 * ease(u)
            az -= 12 * u
        elif mv == "reveal":
            d *= 0.45 + 1.0 * ease(u)
            el = 40 - 15 * u
        elif mv == "fly_over":
            az = az - 45 + 90 * ease(u)
            el = 42
            d *= 1.05
        elif mv == "top_down":
            el = 72
            az += 25 * u
        elif mv == "close_up":
            d *= 0.55
            az += 16 * u
            c[1] += sp["lift"]
        elif mv == "low_angle":
            el = 7
            d *= 0.95 - 0.1 * u
            c[1] += sp["lift"] * 2
        elif mv == "follow":
            lo, hi = self.group_box(sp["target"], self.scenes[i]["start"] + t)
            c = (lo + hi) / 2
            az += 10 * u
        elif mv == "cutaway":
            az += 28 * u
            el = 26
        elif mv == "zoom_into":
            k = max(0.0, (u - 0.5) / 0.5)
            az += 20 * min(u, 0.5)
            inside = self.anchor(sp["target"], "inside", self.scenes[i]["start"] + t)
            c = c + (inside - c) * ease(k)
            d *= 1.0 - 0.93 * (k ** 2 * (3 - 2 * k))
            el = el * (1 - k) + 8 * k
        elif mv == "static":
            az += 6 * u
        # punch-in on key words
        for tk in sp["keys"]:
            dt = self.scenes[i]["start"] + t - tk
            if 0 <= dt < 1.2:
                d *= 1 - 0.06 * math.sin(min(1.0, dt / 0.15) * math.pi / 2) * math.exp(-dt * 2.2)
        ra, re = math.radians(az), math.radians(el)
        eye = c + d * np.array([math.sin(ra) * math.cos(re), math.sin(re), math.cos(ra) * math.cos(re)])
        eye[1] = max(eye[1], 0.35)
        return eye, c, sp["fov"]

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
        eye, tgt, fov = self._cam_path(i, t)
        fade = 0.0
        du = self.scenes[i]["dur"]
        if self._cams[i]["move"] == "zoom_into" and t > du * 0.72:  # fade before the camera is inside
            fade = ease((t - du * 0.72) / (du * 0.2))
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
        t = min(T - sc["start"], sc["dur"])
        eye, tgt, fov, fade = self.camera(i, t)
        draws = []
        cam_dir = np.asarray(eye) - np.asarray(tgt)
        focus_id = self._cams[i]["target"]
        flying = i > 0 and t < min(1.1, 0.4 * sc["dur"]) + 0.3
        prev_id = self._cams[i - 1]["target"] if i > 0 else None
        for inst in self.insts:
            st = self.state(inst, T)
            if st["vis"] <= 0.01:
                continue
            if np.linalg.norm(st["pos"] - eye) > 260:
                continue
            if inst.oid != focus_id and not (flying and inst.oid == prev_id) and self._blocks(inst, st, eye, tgt):
                st["xray"] = True  # a roof or wall between the camera and the subject: see through it
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
                if vis <= 0.01:
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
                if part.kind == "liquid" and st["fill"] != 1.0:
                    local = local @ np.diag([1, max(0.02, st["fill"]), 1, 1]).astype(np.float32)
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
        lo, hi = self.group_box(self._cams[i]["target"], T)
        c = (lo + hi) / 2
        labels = self.labels(i, T, eye, tgt, fov, label_tex) if label_tex else []
        return Frame(eye=tuple(eye), target=tuple(tgt), fov=fov, draws=draws, particles=parts, labels=labels,
                     focus=tuple(c), focus_radius=max(8.0, self._cams[i]["r"] * 1.8), grid_center=(c[0], c[2]),
                     fade=fade, sun=self.sun(eye, tgt), bloom=0.6)

    # ------------------------------------------------------------------ particles
    def particles(self, i: int, T: float) -> np.ndarray | None:
        out = []
        for e in self.events:
            if e.do not in ("flow", "bubbles", "smoke", "sparks") or not (e.start <= T < e.end):
                continue
            if abs(e.scene - i) > 1:
                continue
            t = T - e.start
            color = hex_rgb(e.params["color"]) if e.params.get("color") else FLOW_COLORS[e.do]
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

    def _blocks(self, inst: Inst, st: dict, eye, tgt) -> bool:
        """Does this object stand between the camera and what it looks at? (ray vs box)"""
        if not any(p.shell for p in inst.model.parts):
            return False
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
