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

from . import assets, motion
from .gl import Draw, Frame, Label, hex_rgb, project_points
from . import mesh as M
from .mesh import rot_matrix, section

NO_SHADOW = {"wall", "tool_wall", "city_block"}
FLOORS = {"pad", "ground_plate", "ground", "rail", "fence", "railing", "pipe_stand", "slab", "floor_tiles", "planks",
          "street_road", "turntable"}  # never "in front of" the subject: they are under it  # a room's walls don't throw big shadows over the machine
SHINE = {"metal": 0.85, "paint": 0.55, "glass": 0.9, "plastic": 0.3, "water": 0.7, "rubber": 0.05, "ceramic": 0.45}

SAFE_TOP, SAFE_BOTTOM = 0.15, 0.20  # keep the top 15 % for captions and the bottom 20 % clear for app buttons


def label_floor(W: int, H: int) -> float:
    """Pixels at the bottom a label must stay above: the app buttons plus the line of subtitles over them
    (captions.two_layer_header: margin 21.5 % / 7.5 % of the height, font 6 % / 4.5 % of the short side)."""
    if H >= W:
        return 0.215 * H + 1.4 * 0.06 * W
    return 0.075 * H + 1.4 * 0.045 * H


FILL = 0.78  # how big the subject is (1 = as big as allowed): see W_DIV / H_DIV
W_DIV = 0.68 / FILL  # a normal shot: the subject's box is 68 % of the frame width (the rule: 60-75 %)
H_DIV = 0.92 / FILL  # …but never more than 92 % of the safe height (captions on top, app buttons below)
FILL_MOVES = {"close_up": 1.0, "fly_over": 0.7, "pull_out": 0.78, "top_down": 0.8, "hero": 0.95, "macro": 1.0}
END_OVERVIEW = 3.6  # explainers end on an overview of the whole system, then fly back to the first shot (loop)
HERO_COLOR = "#9e2a35"  # cut faces of a hero part: a deep, calm red (the classic cutaway colour; was candy pink)
HERO_FLOORS = {"floor_tiles", "planks", "slab", "pad", "turntable", "ground", "ground_plate", "terrain"}
CALM_FLIGHT = 1.8  # seconds: explainers fly smoothly from shot to shot (stories cut faster)
FINISH_IN_SHOT = {"open", "close", "lift", "fill", "drain", "appear", "drop", "grow", "show_part", "hide_part",
                  "light_on", "light_off", "cutaway"}
PERSIST = {"snap", "appear", "disappear", "grow", "move", "spin", "fill", "drain", "light_on", "light_off", "float", "drop",
           "show_part", "hide_part", "lift", "open", "close"}
DEFAULT_DUR = {"snap": 0.6, "clamp": 0.4, "drop": 0.6, "appear": 0.45, "disappear": 0.4, "grow": 1.2, "fill": 1.6, "drain": 1.6, "light_on": 0.6,
               "light_off": 0.5, "shake": 0.7, "cutaway": 1.4, "xray": 0.6, "show_part": 0.5, "hide_part": 0.4,
               "lift": 2.6, "open": 0.8, "close": 0.7}
STAGGER = {"appear": 0.16, "disappear": 0.12, "light_on": 0.28, "grow": 0.1, "light_off": 0.15, "show_part": 0.1}
FLOW_COLORS = {"flow": (0.42, 0.29, 0.17), "bubbles": (0.82, 0.94, 1.0), "smoke": (0.72, 0.76, 0.8),
               "sparks": (1.0, 0.85, 0.35)}


FADE_OUT = 0.4  # seconds a glow or alarm takes to fade away after its shot


def slow_pulse(t: float, hz: float) -> float:
    """0 → 1 → 0, smooth (a cosine), at most 2 times a second, starting from 0 (no jump when it begins)."""
    return 0.5 - 0.5 * math.cos(2 * math.pi * min(hz, 2.0) * max(t, 0.0))


def soft_ramp(t: float, T: float, end: float, rise: float = 0.4) -> float:
    """An effect fades in over `rise` seconds and out over FADE_OUT after its end."""
    k = ease(t / rise)
    if end != math.inf:
        k *= 1.0 - ease((T - end) / FADE_OUT)
    return k


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def smoother(x: float) -> float:
    """Quintic ease in/out: starts and stops even more gently (calm camera flights)."""
    x = min(1.0, max(0.0, x))
    return x * x * x * (x * (x * 6 - 15) + 10)


def ease_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


def pop(x: float) -> float:
    """0 → overshoot 1.12 → 1."""
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3 + 0.35 * math.sin(math.pi * x) * (1 - x)


def word_norm(w: str) -> str:
    return "".join(ch for ch in str(w).lower() if ch.isalnum())


NO_VIS = (False, frozenset(), frozenset())  # nothing left out


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
        self.fmt = str(plan.get("format") or "how_it_works")
        self.calm = self.fmt != "story"  # explainers + documentaries: slow eased moves, no fast shakes
        self.fov = 40.0 if size[0] < size[1] else 34.0
        self.models: dict = {}
        self.insts: list[Inst] = []
        self.groups: dict[str, list[Inst]] = {}
        self.obj = {o["id"]: o for o in plan["objects"]}
        self._areas()
        self._build()
        self.notes = logic.place_on_surfaces(self)  # a microwave on the counter, a ceiling fan on the ceiling
        self.notes += logic.ground_everything(self)  # nothing floats without support
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
        self._looks = [self.look_of(i) for i in range(len(self.scenes))]
        self._cams = [self._cam_spec(i) for i in range(len(self.scenes))]

    # ------------------------------------------------------------------ looks (per shot)
    def look_of(self, i: int) -> tuple[str, dict]:
        """(name, renderer style) of shot i: the shot's own look, else hero → clean light studio, macro → dark with
        glow, a comparison table → light studio, an outdoor place → sunny sky; else the world preset's colours."""
        from . import presets  # noqa: PLC0415

        sc = self.scenes[i]["plan"]
        cam = sc["camera"]
        name = presets.look(sc.get("look"))
        if not name and cam["move"] == "hero":
            name = "studio_light"
        if not name and cam["move"] == "macro":
            name = "macro_dark"
        area = next((a for a in self.plan["areas"] if self.groups.get(self._target(i)) and
                     a["id"] == self.groups[self._target(i)][0].area), {})
        if not name:
            name = presets.look(area.get("look"))
        if not name and area.get("setting") == "table":
            name = "studio_light"
        if not name and self.fmt == "documentary" and not area.get("micro"):
            name = "documentary"  # a true story: dark and cinematic everywhere (headlamps, dust, warm vs cold)
        if not name and area.get("setting") in presets.OUTDOOR_SETTINGS and not area.get("micro") and \
                self.preset not in ("ocean", "space", "body", "planet_surface"):
            name = "outdoor_day"
        if not name:
            return self.preset, dict(self.style)
        return name, {**presets.LOOKS[name]}

    def isolated(self, i: int) -> str:
        """'' = the whole world; 'hero' = one part alone; 'macro' = one part and what touches it, on black;
        'subject' = only the filmed machine; 'area' = only its area."""
        mv = self.scenes[i]["plan"]["camera"]["move"]
        if mv == "hero" and self._cam_part(i):
            return "hero"
        if mv == "macro" and self._cam_part(i):
            return "macro"
        if mv == "macro" or self._looks[i][1].get("env") is False:
            return "subject"
        area = next((a for a in self.plan["areas"] if a["id"] == self.groups[self._target(i)][0].area), {})
        return "area" if area.get("setting") == "table" else ""

    def hero_parts(self, i: int, T: float) -> tuple[str, set, np.ndarray, np.ndarray] | None:
        """The ONE part a hero shot is about (piston1 of four) + what sits inside it, and their box."""
        oid, name = self._target(i), self._cam_part(i)
        insts = self.groups.get(oid)
        if not insts or not name:
            return None
        model = insts[0].model
        ks = self.part_names(model, name)
        if not ks:
            return None
        sc = self.scenes[i]
        inst = insts[0]
        k0 = ks[0]  # 'piston1' (or the first of four parts all called 'liner'): one cylinder, not the whole engine
        boxes = [self._part_k_box(inst, k0, sc["start"] + sc["dur"] * f) for f in (0.1, 0.35, 0.6, 0.85)]
        lo, hi = np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)  # all the way it travels
        first = model.parts[k0].name
        num = first[len(first.rstrip("0123456789")):]
        size = float(np.max(hi - lo))
        grow = np.maximum((hi - lo) * 0.3, 0.01)
        keep = {k0}
        cand = []
        for k, p in enumerate(model.parts):  # what sits in it or right at it (rings, rod, gas, the cylinder wall)
            if k == k0 or (p.shell and not p.name.startswith(name)) or p.opacity < 0.2 or \
                    (p.kind == "liquid" and not p.name.startswith(name)):
                continue  # (water around a heating element is not part of the hero)
            pn = p.name[len(p.name.rstrip("0123456789")):]
            if num and pn and pn != num:
                continue
            b = self._part_k_box(inst, k, T)
            if float(np.max(b[1] - b[0])) > size * 2.2:
                continue
            if np.all(b[1] >= lo - grow) and np.all(b[0] <= hi + grow):
                cand.append((k, b))
        for k, b in cand:
            keep.add(k)
        assembly = [k for k, p in enumerate(model.parts) if k not in keep and p.name.startswith(name + "_")
                    and not num]  # a kit assembly ("compressor", "compressor_stage2"…): all its stages together
        if cand:  # frame the part with what is right at it, but never wider than twice the part
            blo = np.minimum(lo, np.min([b[0] for _, b in cand], 0))
            bhi = np.maximum(hi, np.max([b[1] for _, b in cand], 0))
            c, half = (lo + hi) / 2, (hi - lo) / 2
            lo, hi = np.maximum(blo, c - 2 * half - 0.01), np.minimum(bhi, c + 2 * half + 0.01)
        if 0 < len(assembly) <= 14:
            for k in assembly:
                b = self._part_k_box(inst, k, T)
                keep.add(k)
                lo, hi = np.minimum(lo, b[0]), np.maximum(hi, b[1])
        return oid, keep, lo, hi

    def _part_k_box(self, inst: Inst, k: int, T: float) -> tuple[np.ndarray, np.ndarray]:
        """World box of ONE part (by index) where it is now."""
        st = self.state(inst, T)
        m0 = self.inst_matrix(inst, {**st, "vis": 1.0})
        p = inst.model.parts[k]
        local, _, _ = self.part_local(p, k, st, T)
        pts = np.hstack([p.geo.pos, np.ones((len(p.geo.pos), 1), np.float32)]) @ (m0 @ local).T
        return pts[:, :3].min(0), pts[:, :3].max(0)

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
        """The box of the parts you actually see (thin cables, chains and rods don't make an object 'bigger').
        Machines: the box of 94 % of their visible surface, so a flywheel or a manifold sticking out doesn't
        make the whole engine small in the picture."""
        bs, cs, ws = [], [], []
        for p in m.parts:
            if not p.geo.tris or p.opacity < 0.3 or p.kind == "beam":
                continue
            lo, hi = p.geo.bounds()
            if sorted(hi - lo)[1] > 0.15 or float(np.max(hi - lo)) < 1.5:  # thick, or a small machine's part
                bs.append((lo, hi))
                t = p.geo.pos.reshape(-1, 3, 3).astype(np.float64)
                cs.append(t.mean(1))
                ws.append(0.5 * np.linalg.norm(np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0]), axis=1))
        if not bs:
            return m.bounds()
        lo, hi = np.min([b[0] for b in bs], 0), np.max([b[1] for b in bs], 0)
        if len(m.parts) >= 12 and cs:  # a machine: trim the 3 % of surface furthest out on each side
            c, w = np.concatenate(cs), np.concatenate(ws)
            if w.sum() > 0:
                tl, th = [], []
                for ax in range(3):
                    o = np.argsort(c[:, ax])
                    cw = np.cumsum(w[o]) / w.sum()
                    tl.append(c[o][np.searchsorted(cw, 0.03), ax])
                    th.append(c[o][min(len(o) - 1, np.searchsorted(cw, 0.97)), ax])
                tl, th = np.array(tl), np.array(th)
                pad = (th - tl) * 0.06
                lo, hi = np.maximum(lo, tl - pad), np.minimum(hi, th + pad)
        return lo.astype(np.float32), hi.astype(np.float32)

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
        self.mounts = {}
        for o in self.plan["objects"]:  # sits on / inside another object: at its anchor point ("car1.engine_bay")
            if not o.get("mount"):
                continue
            base, _, anchor = o["mount"].partition(".")
            if base not in self.groups or o["id"] not in self.groups:
                continue
            parent = self.groups[base][0]
            a = assets.part_center(parent.model, anchor or "top")  # an anchor point, or the top of a real part
            if a is None:
                a = np.asarray(parent.model.anchors.get("top", (0.0, 0.0, 0.0)), np.float32)
            self.mounts[o["id"]] = (parent, a)
            m = self.inst_matrix(parent, {"pos": parent.pos, "yaw": parent.rot, "scale": 1.0, "vis": 1.0,
                                          "shake": np.zeros(3), "bob": 0.0})
            grp = self.groups[o["id"]]
            mid = np.mean([g.pos for g in grp], 0)  # a group (33 miners) stands AROUND the anchor, not beside it
            mid[1] = grp[0].pos[1]
            for inst in grp:
                inst.pos = ((m @ np.append(a, 1.0))[:3] + (inst.pos - mid)).astype(np.float32)
                inst.rot = parent.rot + o["rot"]

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
                    if do in FINISH_IN_SHOT:  # said on the last word: start a bit earlier, so it is SEEN finishing
                        t0 = max(sc["start"], min(t0, sc["end"] - dur - 0.35))
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
              "shake": np.zeros(3), "drop": 0.0, "cut": 0.0, "cut_dir": None, "xray": False, "parts": {}, "travel": 0.0, "bob": 0.0,
              "lift": 0.0, "open": 0.0, "opens": {}, "fills": {}}
        for part in [p for (o, p) in self.hidden_parts if o == inst.oid]:
            st["parts"][part] = 0.0
        if any(par is inst for par, _ in getattr(self, "mounts", {}).values()) and \
                any(p.name == "hood" for p in inst.model.parts):
            st["opens"]["hood"] = 1.0  # an engine sits in the bay: the hood is open so we can see it
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
                now = st["fills"].get(e.part, st["fill"]) if e.part else st["fill"]
                a = e.params.get("from", now if e.do == "fill" else 1.0)
                b = e.params.get("to_value", 1.0 if e.do == "fill" else 0.25)
                if e.do == "fill" and "from" not in e.params and now >= 0.99:
                    a = 0.15
                if e.do == "drain" and "from" not in e.params:
                    a = now
                level = a + (b - a) * ease(p)
                if e.part:  # one liquid of the machine (the toilet's tank, not its bowl)
                    st["fills"][e.part] = level
                else:
                    st["fill"] = level
            elif e.do == "lift":  # the machine's lifting part: 0 = bottom, 1 = top (elevator car, counterweight…)
                a = e.params.get("from", st["lift"])
                b = e.params.get("to_value", 0.0 if st["lift"] > 0.5 else 1.0)
                st["lift"] = a + (b - a) * ease(p)
            elif e.do in ("open", "close"):
                u = ease(p) if e.do == "open" else 1 - ease(p)
                if e.part:
                    st["opens"][e.part] = u
                else:
                    st["open"] = u
            elif e.do == "light_on":
                st["light"] = ease(p)
            elif e.do == "light_off":
                st["light"] = 1 - ease(p)
            elif e.do == "glow" and (active or T < e.end + FADE_OUT):
                k = soft_ramp(t, T, e.end)  # glows fade in and out, and pulse slowly (under 1 per second)
                g = k * ((0.06 + 0.12 * slow_pulse(t, 0.7)) if not e.part else (0.4 + 0.3 * slow_pulse(t, 0.6)))
                if e.part:  # one part glows (hot coils, a heating element), not the whole machine
                    st.setdefault("glows", {})[e.part] = g
                else:
                    st["glow"] = g
            elif e.do == "alarm" and (active or T < e.end + FADE_OUT):
                part = e.part or self._scene_part(e.scene, inst.oid)
                a_k = soft_ramp(t, T, e.end) * (0.25 + 0.75 * slow_pulse(t, 0.8))  # a slow red pulse, soft fades
                if part:  # a huge machine: only the part in the picture turns red (the ropes, not the building)
                    st.setdefault("alarms", {})[part] = a_k
                else:
                    st["alarm"] = a_k
            elif e.do == "shake" and p < 1:
                env = (1 - p) * min(1.0, t / 0.12)
                if self.fmt == "story":  # stories keep a real jolt
                    k = env * 0.08 * max(1.0, inst.radius * 0.3)
                    st["shake"] = np.array([math.sin(t * 61), math.sin(t * 47) * 0.4, math.sin(t * 53)]) * k
                else:  # explainers and documentaries: a slow rock (a fast shake of a big object reads as flicker)
                    k = env * 0.03 * max(1.0, inst.radius * 0.15)
                    st["shake"] = np.array([math.sin(t * 13.0), math.sin(t * 11.0) * 0.4, math.sin(t * 12.0)]) * k
            elif e.do == "cutaway" and active:
                st["cut"] = ease(p)
                st["cut_dir"] = e.scene
            elif e.do == "xray" and active:
                st["xray"] = max(float(st["xray"]), ease(p))  # the shell turns see-through gradually
            elif e.do == "snap":  # a rope breaks: it whips back, the car drops until the safety brakes clamp
                st.setdefault("snaps", {})[e.part or "ropes"] = t
                st["sag"] = 0.55 * ease(min(1.0, t / 0.5))
            elif e.do == "float":
                ph = inst.index * 1.7
                st["bob"] = 0.18 * math.sin(t * 1.6 + ph)
                st["yaw"] = inst.rot + 12 * math.sin(t * 0.5 + ph)
            elif e.do == "show_part":
                st["parts"][e.part] = pop(p)
            elif e.do == "hide_part":
                st["parts"][e.part] = 1 - ease(p)
        if inst.oid in getattr(self, "mounts", {}):  # riding on its parent (an engine in a car that drives away)
            parent, a = self.mounts[inst.oid]
            pst = self.state(parent, T)
            if np.linalg.norm(pst["pos"] - parent.pos) > 1e-4 or abs(pst["yaw"] - parent.rot) > 1e-3:
                pm = self.inst_matrix(parent, {**pst, "vis": 1.0, "scale": 1.0})
                st["pos"] = (pm @ np.append(a, 1.0))[:3].astype(np.float32)
                st["yaw"] = pst["yaw"] + (inst.rot - parent.rot)
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
        if "y" in e.params:  # straight up or down (a capsule rising up its shaft, a sub diving)
            return np.array([inst.pos[0], y, inst.pos[2]], np.float32)
        return inst.pos

    # ------------------------------------------------------------------ geometry helpers
    def part_local(self, part, k: int, st: dict, T: float) -> tuple[np.ndarray, float, tuple | None]:
        """How one part moves inside its object right now: (local 4x4, extra glow, colour override)."""
        local = np.eye(4, dtype=np.float32)
        extra_glow, recolor = 0.0, None
        if part.motion:  # real working parts: pistons, rods, valves, doors, ropes, floats…
            for mo in (part.motion if isinstance(part.motion, list) else [part.motion]):
                mat, g, c2 = motion.evaluate(part, st, T, mo)
                if mat is not None:
                    local = mat @ local
                extra_glow += g
                recolor = c2 or recolor
        for name, ts in st.get("snaps", {}).items():  # the snapped rope: its loose end whips back up
            if part.name == name or part.name.startswith(name + "_") or (part.name.startswith(name) and
                                                                          part.name[len(name):].isdigit()):
                lo, hi = part.geo.bounds()
                pv = np.asarray(part.pivot if any(part.pivot) else ((lo + hi) / 2 * [1, 0, 1] + [0, hi[1], 0]),
                                np.float32)
                k = 1.0 - 0.6 * ease(min(1.0, ts / 0.9))  # the loose end springs back (smooth, readable)
                sm = np.eye(4, dtype=np.float32)
                sm[1, 1] = k
                sm[1, 3] = float(pv[1]) * (1 - k)
                ang = 12.0 * math.exp(-1.6 * ts) * math.sin(5.0 * ts) * min(1.0, ts / 0.25)  # a slow sway
                r = np.eye(4, dtype=np.float32)
                r[:3, :3] = rot_matrix(0, 0, ang)
                r[:3, 3] = pv - r[:3, :3] @ pv
                local = r @ sm @ local
                extra_glow += 0.3 * min(1.0, ts / 0.25) * math.exp(-1.8 * max(0.0, ts - 0.25))  # a soft glow, no flash
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
        level = st["fills"].get(part.name, st["fill"])
        if part.kind == "liquid" and level != 1.0:  # the level drops inside its own container
            lo, hi = part.geo.bounds()
            f = max(0.02, level)
            sm = np.diag([1, f, 1, 1]).astype(np.float32)
            sm[1, 3] = float(lo[1]) * (1 - f)
            local = local @ sm
        if part.kind == "crust" and st["fill"] != 1.0:
            lo, hi = part.geo.bounds()
            local[1, 3] += (st["fill"] - 1) * float(lo[1])
        return local, extra_glow, recolor

    @staticmethod
    def part_names(model, name: str) -> list[int]:
        """The parts a name means: 'piston' → piston1..piston4, 'car' → car_floor, car_walls, car_door…
        An exact name wins ('governor' is the wheel, not also the 16 m governor_rope)."""
        exact = [k for k, p in enumerate(model.parts) if p.name == name]
        if exact:
            return exact
        out = []
        for k, p in enumerate(model.parts):
            n = p.name
            if n.startswith(name + "_") or (n.startswith(name) and n[len(name):].isdigit()):
                out.append(k)
        return out

    def part_box(self, oid: str, name: str, T: float, margin: bool = True) -> tuple[np.ndarray, np.ndarray] | None:
        """World box of a machine's part (where it is NOW, moving parts included) or of a named anchor point."""
        insts = self.groups.get(oid)
        if not insts:
            return None
        inst = insts[0]
        st = self.state(inst, T)
        m0 = self.inst_matrix(inst, {**st, "vis": 1.0})
        pts, hang = [], None
        for k in self.part_names(inst.model, name):
            p = inst.model.parts[k]
            local, _, _ = self.part_local(p, k, st, T)
            tri = p.geo.pos.reshape(-1, 3, 3)
            tri = tri[:: max(1, len(tri) // 400)].reshape(-1, 3).astype(np.float64)  # whole triangles (a sample)
            pts.append(np.hstack([tri, np.ones((len(tri), 1))]) @ (m0 @ local).T.astype(np.float64))
            mos = p.motion if isinstance(p.motion, list) else [p.motion] if p.motion else []
            if any(mo.get("type") == "stretch" for mo in mos):  # a hanging rope: its pivot end is fixed
                hang = (m0 @ np.append(np.asarray(p.pivot, np.float32), 1.0))[:3]
        if pts:
            P = np.concatenate(pts)[:, :3]
            lo, hi = P.min(0), P.max(0)
            ext = hi - lo
            ax = int(np.argmax(ext))
            rest = max(float(np.sort(ext)[1]), 0.3)
            spans = P[:, ax].reshape(-1, 3)  # each triangle covers [min, max] along the long axis
            bins = np.linspace(float(lo[ax]), float(hi[ax]) + 1e-6, 25)
            mid = (bins[:-1] + bins[1:]) / 2
            covered = ((spans.min(1)[None, :] <= mid[:, None]) & (spans.max(1)[None, :] >= mid[:, None])).any(1)
            solid_along = float(covered.mean())  # a rope fills its length; two brake blocks 2 m apart don't
            if margin and ext[ax] > 3.5 * rest and solid_along > 0.6:  # a long rope / rail / cable: frame a piece
                win = max(3.0 * rest, 0.18 * float(ext[ax]))
                if hang is not None:  # the end that holds the load (the car), away from the fixed end
                    c0 = lo[ax] + win / 2 if abs(hang[ax] - hi[ax]) < abs(hang[ax] - lo[ax]) else hi[ax] - win / 2
                else:
                    c0 = (lo[ax] + hi[ax]) / 2
                if hang is not None or ax == 1:  # ropes and cables hang: a piece; a shaft or a rail: all of it
                    lo, hi = lo.copy(), hi.copy()
                    lo[ax], hi[ax] = c0 - win / 2, c0 + win / 2
        elif name in inst.model.anchors:
            a = self.anchor(oid, name, T)
            r = max(0.08, inst.radius * 0.18)
            lo, hi = a - r, a + r
        else:
            return None
        if not margin:
            return lo, hi
        c, half = (lo + hi) / 2, (hi - lo) / 2  # room around it: the part and what it works with stay readable
        floor = min(inst.radius * 0.22, 0.35 + 0.6 * float(np.max(half)))  # thin parts get some context, not a whole wall
        half = np.maximum(half * 1.6, max(0.06, floor))
        return c - half, c + half

    def label_point(self, i: int, lb: dict, T: float) -> np.ndarray:
        """Where a label points: at its part (named in the label, or the part the camera is on), else the object."""
        oid = lb["target"]
        insts = self.groups.get(oid)
        part = lb.get("part", "")
        if insts and not part:
            model = insts[0].model
            words = {w.lower().rstrip("s") for w in str(lb.get("text", "")).replace("-", " ").split() if len(w) > 2}
            for p in model.parts:  # "Sheave" → the sheave, "Spark plug" → spark1
                stem = p.name.rstrip("0123456789").lower()
                if stem and (stem in words or stem.rstrip("s") in words or stem.split("_")[0] in words):
                    part = stem
                    break
            if not part and self._target(i) == oid and self._cam_part(i):
                part = self._cam_part(i)
        if part and insts:
            box = self.part_box(oid, part, T, margin=False)
            if box is not None:
                lo, hi = box
                return np.array([(lo[0] + hi[0]) / 2, hi[1] + max(0.03, 0.06 * float(np.max(hi - lo))), (lo[2] + hi[2]) / 2])
        return self.anchor(oid, "label", T)

    def _cam_part(self, i: int) -> str:
        return str(self.scenes[i]["plan"]["camera"].get("part") or "")

    def _scene_part(self, i: int, oid: str) -> str:
        """The part shot i's camera is on, if it looks at this object."""
        if not 0 <= i < len(self.scenes):
            return ""
        cam = self.scenes[i]["plan"]["camera"]
        return str(cam.get("part") or "") if cam.get("target") == oid else ""

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
        """What shot i is about: the camera's subject + the things its line acts on or labels nearby.
        A comparison table: everything on it, side by side."""
        sc = self.scenes[i]
        tgt = self._target(i)
        ids = [tgt]
        area = next((a for a in self.plan["areas"] if a["id"] == self.groups[tgt][0].area), {})
        if area.get("setting") == "table":
            return [o["id"] for o in self.plan["objects"] if o["area"] == area["id"] and o["id"] in self.groups]
        if self._cam_part(i):
            return ids
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
        part = self._cam_part(i)
        if part:  # the camera looks at one part of the machine (the car of an elevator, a piston, the sheave)
            box = self.part_box(self._target(i), part, T)
            if box is not None:
                return box
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

        def size(d):  # at fill = FILL: 68 % of the width (60-75 %), at most 92 % of the safe height
            depth = d + rz
            x, y = rx / (depth * th), ry / (depth * tv)
            return max((x.max() - x.min()) / 2 / W_DIV, (y.max() - y.min()) / 2 / (half_h * H_DIV)), x, y

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

    def path_world(self, oid: str, T: float, name: str = "flow") -> list | None:
        inst = self.groups[oid][0]
        path = inst.model.paths.get(name)
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
        if cam["move"] == "hero":
            hp = self.hero_parts(i, sc["start"] + sc["dur"] * 0.6)
            if hp is not None:
                lo, hi = hp[2], hp[3]
        elif cam["move"] == "macro" and self._cam_part(i):  # ONE spark, not all four across the engine
            model = self.groups[tgt][0].model
            ks = self.part_names(model, self._cam_part(i))
            # framed as it is when the shot starts (a rope that snaps later whips OUT of this box: we watch it go)
            b = self.part_box(tgt, model.parts[ks[0]].name, sc["start"] + sc["dur"] * 0.1, margin=False) if ks else None
            if b is not None:
                mlo, mhi = model.bounds()
                g = max(0.05, 0.12 * float(np.max(mhi - mlo)) * self.groups[tgt][0].scale)
                ext = b[1] - b[0]
                if float(np.max(ext)) > 6 * max(float(np.min(ext)), 1e-3):  # a rope: its lower (load) end only
                    k = int(np.argmax(ext))
                    b = (b[0].copy(), b[1].copy())
                    b[1][k] = b[0][k] + max(0.6, 4 * float(np.sort(ext)[1]))
                c = (b[0] + b[1]) / 2
                half = np.maximum((b[1] - b[0]) / 2, min(g / 2, 0.04 + 0.25 * float(np.max(b[1] - b[0]))))
                lo, hi = c - half, c + half
        az = cam.get("angle", 25.0 + 15 * ((i * 7) % 5 - 2))
        el = cam.get("height", 22.0)
        ext = hi - lo
        tags = set(getattr(assets.REGISTRY.get(self.groups[tgt][0].asset), "tags", []))
        if "cutaway" in tags and "angle" not in cam:  # a machine is designed to be seen (and cut) from its front
            az += self.groups[tgt][0].rot
        if "symbol" in tags and not self._cam_part(i):  # counters, signs, scales, charts: read them face-on
            az = cam.get("angle", 8.0 + 6 * ((i % 3) - 1)) + self.groups[tgt][0].rot
            el = min(cam.get("height", 12.0), 16.0)
        if tags & {"animal", "people"}:
            el = min(max(el, 6.0), 20.0)  # animals and people: from the side or 3/4, never from above
        elif "vehicle" in tags:
            el = min(el, 30.0)
        elif self.size[1] > self.size[0] and max(ext[0], ext[2]) > 2.2 * max(ext[1], 0.5):
            el = max(el, 36.0)  # a wide, low subject in a tall frame: look down more, so the place fills the picture
        keys = [sc["start"] + self.at_time(i, k.get("at"), 0.2) for k in sc["plan"]["keywords"]]
        area = self.groups[tgt][0].area
        area_of = next((a for a in self.plan["areas"] if a["id"] == area), {})
        micro = any(a.get("micro") and a["id"] == area for a in self.plan["areas"])
        fill = FILL_MOVES.get(cam["move"], FILL) * min(1.25, max(0.8, cam.get("zoom", 1.0) ** 0.5))
        if cam["move"] in ("hero", "macro"):
            el = min(el, 18.0)
        part = self._cam_part(i)
        if part and "angle" not in cam:  # a wheel / pulley / governor: look at its face, not its edge
            model = self.groups[tgt][0].model
            ks = self.part_names(model, part)
            mos = [mo for k in ks[:1] for mo in (model.parts[k].motion if isinstance(model.parts[k].motion, list)
                                                  else [model.parts[k].motion] if model.parts[k].motion else [])]
            if any(mo.get("type") == "spin" for mo in mos) or (ks and model.parts[ks[0]].kind in ("wheel", "blade")):
                axis = next((mo.get("axis") for mo in mos if mo.get("type") == "spin"), model.parts[ks[0]].axis)
                if axis == "x":
                    az = self.groups[tgt][0].rot + 58.0
                elif axis == "z":
                    az = self.groups[tgt][0].rot + 18.0
        room = area_of.get("setting") in ("kitchen", "bathroom", "garage", "living_room", "office", "lab", "laundry")
        if part and "angle" not in cam and cam["move"] not in ("hero", "macro"):  # film the part from its clear side
            az = self._clear_side(i, tgt, part, lo, hi, az, el, cam.get("fov", self.fov), min(1.0, fill), room)
        prev_look = self._looks[i - 1][0] if i > 0 else self._looks[i][0]
        cut = bool(sc["plan"].get("cut")) or (i > 0 and (prev_look != self._looks[i][0] or self.isolated(i) or
                                                        self.isolated(i - 1)))
        return {"move": cam["move"], "target": tgt, "lo": lo, "hi": hi, "c": (lo + hi) / 2, "cut": cut, "room": room,
                "r": max(1.2, float(np.linalg.norm(hi - lo)) / 2), "az": az, "el": el, "to_az": cam.get("to_angle"),
                "fov": cam.get("fov", self.fov), "keys": keys, "micro": micro, "fill": min(1.0, fill)}

    def _clear_side(self, i: int, tgt: str, part: str, lo, hi, az0: float, el: float, fov: float, fill: float,
                    room: bool) -> float:
        """The camera angle near az0 from which the fewest of the machine's own solid parts stand in front of the
        part this shot is about. It moves only when that clearly shows more of the part: a motor under a washer's
        tub is filmed from the side, not through the drum and the drain pump."""
        inst = self.groups[tgt][0]
        sc = self.scenes[i]
        T = sc["start"] + 0.5 * sc["dur"]
        st = self.state(inst, T)
        try:
            inv = np.linalg.inv(self.inst_matrix(inst, {**st, "vis": 1.0}).astype(np.float64))
        except np.linalg.LinAlgError:
            return az0
        keep = set(self.part_names(inst.model, part))
        solid = [p for k, p in enumerate(inst.model.parts)
                 if k not in keep and not p.shell and p.kind != "liquid" and p.opacity >= 0.6]
        box = self.part_box(tgt, part, T, margin=False) or (lo, hi)
        c, half = (np.asarray(box[0], np.float64) + box[1]) / 2, (np.asarray(box[1], np.float64) - box[0]) / 2 * 0.7
        pts = [c] + [c + half * np.array([sx, sy, sz]) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        pts = [(inv @ np.append(q, 1.0))[:3] for q in pts]
        if not solid:
            return az0
        tris = np.concatenate([p.geo.pos.reshape(-1, 3, 3) for p in solid]).astype(np.float64)  # real triangles:
        # a bent hose's box covers half the machine, its triangles don't

        def blocked(a: float) -> float:
            eye, _ = self.fit(lo, hi, a, el, fov, fill)
            e = (inv @ np.append(eye, 1.0))[:3]
            return sum(_seg_hits(e, q, tris) for q in pts) / len(pts)

        def norm(a: float) -> float:
            a = (a + 180.0) % 360.0 - 180.0
            return min(95.0, max(-5.0, a)) if room else a

        start = norm(az0)
        here = blocked(start)
        if here < 0.3:
            return az0
        best, best_s = start, here
        for d in (25, -25, 50, -50, 75, -75, 100, -100, 130, -130, 180):
            a = (az0 + d + 180.0) % 360.0 - 180.0
            if room and not -5.0 <= a <= 95.0:
                continue
            s = blocked(a)
            if s < best_s - 0.05:
                best, best_s = a, s
        return best if here - best_s >= 0.25 else az0

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
            span = 40 if self.calm else 70
            az = az - span / 2 + span * ease(u)
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
        elif mv == "hero":  # one part alone, cut in half: a slow turn and a gentle push in
            k = 1.08 - 0.1 * ease(u)
            az += 18 * ease(u)
        elif mv == "macro":  # extreme close-up: almost still, a slow creep in
            k = 0.95 - 0.12 * ease(u)
            az += 6 * u
        punch = 0.025 if self.calm else 0.05
        for tk in sp["keys"]:  # punch-in on key words (gentle in explainers)
            dt = self.scenes[i]["start"] + t - tk
            if 0 <= dt < 1.2:
                k *= 1 - punch * math.sin(min(1.0, dt / 0.25) * math.pi / 2) * math.exp(-dt * 1.6)
        if sp.get("room"):  # a room set is open at the front and the right: never film it from behind a wall
            a = (az + 180.0) % 360.0 - 180.0
            az = min(95.0, max(-5.0, a))
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
        micro = {a["id"] for a in self.plan["areas"] if a.get("micro") or a.get("setting") == "table"}
        ids = [o["id"] for o in self.plan["objects"] if o["area"] not in micro and o["id"] in self.groups]
        real = [o for o in ids if "symbol" not in getattr(assets.REGISTRY.get(self.groups[o][0].asset), "tags", [])]
        ids = real or ids  # counters, scales and arrows are not "the system"
        shots = [self._target(k) for k in range(len(self.scenes))]
        main = [o for o in ids if shots.count(o) >= max(2, len(shots) // 4)]
        if main and all(o in self.mounts for o in main):
            ids = main  # the engine the video is about, not the whole car it sits in
        elif len(main) > 1 and len({self.groups[o][0].asset for o in main}) == 1:
            # the same machine twice (in the car and on a stand): the one shot 1 films (the video loops back to it),
            # else the one filmed most
            best = shots[0] if shots and shots[0] in main else max(main, key=shots.count)
            ids = [o for o in ids if self.groups[o][0].area == self.groups[best][0].area]
        boxes = [self.group_box(o, self.total) for o in ids] or [(np.zeros(3), np.ones(3))]
        lo, hi = np.min([b[0] for b in boxes], 0), np.max([b[1] for b in boxes], 0)
        if any("cross_section" in getattr(assets.REGISTRY.get(self.groups[o][0].asset), "tags", []) for o in ids):
            return self.fit(lo, hi, 12.0, 14.0, self.fov, 0.95)  # a cut-open mountain: from the front, like a cake
        if len({self.groups[o][0].area for o in ids}) <= 1:  # one machine: the whole of it, working, 3/4 view
            az = float(self._cams[-1]["az"]) + 25.0 if self._cams else 30.0
            return self.fit(lo, hi, az, 24.0, self.fov, 0.9)
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
        if self._cams[i]["cut"]:  # a big change of place, time or look: a clean hard cut
            return eye, tgt, fov, fade
        tr = self.flight(i)
        if t < tr:
            pe, pt, pf = self._cam_path(i - 1, self.scenes[i - 1]["dur"])
            ne, nt, nf = self._cam_path(i, tr)
            w = smoother(t / tr) if self.calm else ease(t / tr)
            lift = 0.22 * float(np.linalg.norm(ne - pe)) * math.sin(math.pi * w)
            eye = pe + (ne - pe) * w + np.array([0, lift, 0])
            tgt = pt + (nt - pt) * w
            fov = pf + (nf - pf) * w
        return eye, tgt, fov, fade

    def flight(self, i: int) -> float:
        """Seconds the camera flies from shot i-1 into shot i (0 = a hard cut)."""
        if i == 0 or self._cams[i]["cut"]:
            return 0.0
        du = self.scenes[i]["dur"]
        return min(CALM_FLIGHT, 0.35 * du) if self.calm else min(1.1, 0.4 * du)

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

    def _shot_light(self, i: int) -> tuple:
        """The sun and the shadow box of shot i: FIXED for the whole shot (sun from the upper left of the shot's main
        view, sharp shadow map around its subject). Only the camera moves, so shadows don't swim or crawl."""
        cache = self.__dict__.setdefault("_light_cache", {})
        if i not in cache:
            sp = self._cams[i]
            du = self.scenes[i]["dur"]
            tr = self.flight(i)
            eye, tgt, fov = self._cam_path(i, tr + 0.5 * max(du - tr, 0.0))
            dist = float(np.linalg.norm(np.asarray(eye) - np.asarray(tgt)))
            r0 = max(float(sp["r"]) * 1.35, dist * math.tan(math.radians(fov) / 2) * 1.25, 0.12)
            if self.isolated(i) in ("hero", "macro"):
                r0 = max(float(np.linalg.norm(sp["hi"] - sp["lo"])) * 0.75, 0.08)
            cache[i] = (np.asarray(self.sun(eye, tgt), np.float64), np.asarray(sp["c"], np.float64), r0,
                        max(r0 * 4.0, dist * 1.6, 6.0))
        return cache[i]

    def _overview_light(self) -> tuple:
        oe, ot = self._overview()
        dist = float(np.linalg.norm(oe - ot))
        r0 = max(dist * 0.5, 1.0)
        return np.asarray(self.sun(oe, ot), np.float64), np.asarray(ot, np.float64), r0, max(r0 * 4.0, dist * 1.6)

    @staticmethod
    def _blend_light(a: tuple, b: tuple, w: float) -> tuple:
        sun = a[0] + (b[0] - a[0]) * w
        sun /= max(np.linalg.norm(sun), 1e-9)
        lr = lambda x, y: math.exp(math.log(x) + (math.log(y) - math.log(x)) * w)  # noqa: E731
        return sun, a[1] + (b[1] - a[1]) * w, lr(a[2], b[2]), lr(a[3], b[3])

    def light_at(self, i: int, t: float) -> tuple:
        """(sun, shadow centre, sharp radius, wide radius) at local time t of shot i: the shot's own light, blended
        from the previous shot's only while the camera flies in (and over the ending's overview)."""
        cur = self._shot_light(i)
        du = self.scenes[i]["dur"]
        if i == len(self.scenes) - 1 and t > du and self.ending == "overview":
            tt = t - du
            end = self.tl.get("end", {}).get("dur", END_OVERVIEW)
            a, b = min(1.3, end * 0.36), max(min(1.3, end * 0.36) + 0.1, end - 1.2)
            ov = self._overview_light()
            if tt < a:
                return self._blend_light(cur, ov, ease(tt / a))
            if tt < b:
                return ov
            return self._blend_light(ov, self._shot_light(0), ease(min(1.0, (tt - b) / max(end - b, 1e-3))))
        tr = self.flight(i)
        if i > 0 and t < tr and not self._cams[i]["cut"]:
            w = smoother(t / tr) if self.calm else ease(t / tr)
            return self._blend_light(self._shot_light(i - 1), cur, w)
        return cur

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

    def camera_at(self, T: float) -> tuple:
        """(eye, target, fov, fade) at video time T."""
        i = self.scene_at(T)
        sc = self.scenes[i]
        t = T - sc["start"] if (self.ending == "overview" and i == len(self.scenes) - 1) else min(T - sc["start"], sc["dur"])
        return self.camera(i, t)

    def frame(self, T: float, label_tex=None, cam: tuple | None = None) -> Frame:
        """Everything to draw at time T. cam = (eye, target, fov, fade) films the world at T from another camera
        (the flicker check holds the camera still to see what changes in the world itself)."""
        i = self.scene_at(T)
        sc = self.scenes[i]
        t = T - sc["start"] if (self.ending == "overview" and i == len(self.scenes) - 1) else min(T - sc["start"], sc["dur"])
        eye, tgt, fov, fade = cam if cam is not None else self.camera(i, t)
        draws = []
        dyn = []  # cut faces made for this frame (hero shots)
        door_shot = {a["target"].split(".")[0] for a in sc["plan"]["actions"] if a["do"] in ("open", "close")}
        self._aim_i = i
        cam_dir = np.asarray(eye) - np.asarray(tgt)
        focus_id = self._cams[i]["target"]
        ending = self.ending == "overview" and i == len(self.scenes) - 1 and t > sc["dur"]
        iso = "" if ending else self.isolated(i)
        hero = self.hero_parts(i, T) if iso == "hero" else None
        if iso == "hero" and hero is None:
            iso = "subject"
        near_box = None
        if iso == "macro":  # only the parts near the filmed one (no building walls behind it)
            sp = self._cams[i]
            g = np.maximum((sp["hi"] - sp["lo"]) * 0.9, 0.1)
            near_box = (sp["lo"] - g, sp["hi"] + g)
        own_area = self.groups[focus_id][0].area if focus_id in self.groups else None
        mount_parents = {self.mounts[f][0].oid for f in self._focus[i] if f in self.mounts}
        fwd = np.asarray(tgt, np.float64) - np.asarray(eye, np.float64)
        fwd /= max(np.linalg.norm(fwd), 1e-9)
        half = math.radians(fov) / 2 * max(1.0, self.size[0] / self.size[1]) * 1.25  # a little wider than the view
        far_cut = max(260.0, 2.5 * float(np.linalg.norm(np.asarray(eye) - np.asarray(tgt))))  # huge cross-sections
        vis_now, vis_prev, vw = self._shot_vis(i), None, 1.0
        vis_fly, dip = {}, 0.0
        if ending:  # the overview: everything comes back while the camera flies out, then shot 1's choices
            end = self.tl.get("end", {}).get("dur", END_OVERVIEW)
            tt = t - sc["dur"]
            a_, b_ = min(1.3, end * 0.36), max(min(1.3, end * 0.36) + 0.1, end - 1.2)
            ov = self._ending_vis()
            if tt < a_:
                vis_now, vis_prev, vw = ov, vis_now, ease(tt / a_)
            elif tt < b_:
                vis_now = ov
            else:
                vis_now, vis_prev, vw = self._shot_vis(0), ov, ease(min(1.0, (tt - b_) / max(end - b_, 1e-3)))
        elif i > 0 and not self._cams[i]["cut"] and t < self.flight(i):
            vis_prev = self._shot_vis(i - 1)
            u_fl = t / self.flight(i)
            vw = smoother(u_fl) if self.calm else ease(u_fl)
            vis_fly = self._flight_vis(i)  # whatever blocks the way while flying: out early, back in at the end
            dip = smoother(u_fl / 0.45) * (1.0 - smoother((u_fl - 0.55) / 0.45))
        sun, s_c, s_r0, s_r1 = self.light_at(i, t)
        no_cast = self._no_cast()
        for inst in self.insts:
            if iso == "hero" and inst.oid != hero[0] and inst.asset not in HERO_FLOORS:
                continue  # a hero shot: ONE part, its machine as a faint ghost around it, on its floor
            if iso in ("subject", "macro") and inst.oid not in self._focus[i] and inst.oid not in mount_parents:
                continue  # a macro shot: only the subject on a dark background
            if iso == "area" and inst.area != own_area:
                continue  # a comparison on its own plain table
            rel = inst.pos - eye  # skip what is behind the camera or far outside the picture (much faster)
            dist = float(np.linalg.norm(rel))
            shadow_only = False
            if dist > far_cut or (dist > inst.radius * 1.5 and float(np.dot(rel, fwd)) / dist <
                                    math.cos(min(math.pi / 2, half + math.asin(min(1.0, inst.radius * 1.5 / dist))))):
                if inst.oid not in self.groups or not self.events_of.get(inst.oid):
                    if iso or float(np.linalg.norm(inst.pos - s_c)) > s_r1 + inst.radius:
                        continue
                    shadow_only = True  # just outside the picture: its shadow still falls into it (no shadow pop)
            st = self.state(inst, T)
            if st["vis"] <= 0.01:
                continue
            if np.linalg.norm(st["pos"] - eye) > far_cut:
                continue
            # what is left out / see-through is decided once per shot (no part pops away mid-shot); while the
            # camera flies in from the last shot, parts fade between the two shots' choices
            skip_a, hid_a, see_a = vis_now.get(inst.oid, NO_VIS)
            if vis_prev is not None:
                skip_b, hid_b, see_b = vis_prev.get(inst.oid, NO_VIS)
            else:
                skip_b, hid_b, see_b = skip_a, hid_a, see_a
            skip_f, hid_f, see_f = vis_fly.get(inst.oid, NO_VIS)
            inst_k = (0.0 if skip_a else 1.0) * vw + (0.0 if skip_b else 1.0) * (1.0 - vw)
            if skip_f:
                inst_k = min(inst_k, 1.0 - dip)
            if inst_k <= 0.01:
                continue
            hidden_parts, fade_k = set(), {}
            for k in hid_a | hid_b | see_a | see_b | hid_f | see_f:
                fa = 0.0 if k in hid_a else (0.3 if k in see_a else 1.0)
                fb = 0.0 if k in hid_b else (0.3 if k in see_b else 1.0)
                fk = fa * vw + fb * (1.0 - vw)
                if k in hid_f or k in see_f:
                    fk = min(fk, 1.0 - dip * (1.0 if k in hid_f else 0.7))
                if fk <= 0.01:
                    hidden_parts.add(k)
                else:
                    fade_k[k] = fk
            m0 = self.inst_matrix(inst, st)
            clip = None
            if st["cut"] > 0:
                n = cam_dir.copy()
                n[1] = 0
                n /= max(np.linalg.norm(n), 1e-6)
                c = st["pos"]  # remove the half that faces the camera
                if "key" in inst.model.anchors:  # a designed machine: cut right through its most important part
                    c = (m0 @ np.append(np.asarray(inst.model.anchors["key"], np.float32), 1.0))[:3]
                if inst.oid == focus_id and self._cam_part(i):  # filming one part: cut right through THAT part
                    pb = self.part_box(inst.oid, self._cam_part(i), T, margin=False)
                    if pb is not None:
                        c = (pb[0] + pb[1]) / 2
                clip = (*n, float(np.dot(n, c) + inst.radius * (1 - st["cut"]) * 1.2 - 0.02))  # sweeps in gently
            has_shell = clip is not None and any(p.shell for p in inst.model.parts)
            own_cut = {}  # a shell part the camera films (a compressor's dome): cut through ITS centre, not removed
            if clip is not None and inst.oid == focus_id and self._cam_part(i):
                for k in self.part_names(inst.model, self._cam_part(i)):
                    if inst.model.parts[k].shell:
                        plo, phi = inst.model.parts[k].geo.bounds()
                        pc = (m0 @ np.append((plo + phi) / 2, 1.0))[:3]
                        own_cut[k] = (clip[0], clip[1], clip[2],  # sweeps in with the cutaway (no one-frame hole)
                                      float(np.dot(clip[:3], pc)) + inst.radius * (1 - st["cut"]) * 1.2)
            hero_clip = None
            if hero is not None:  # cut the hero part through its middle, turned 55° so we see the cut AND the outside
                n = self._hero_normal(i)  # fixed for the shot (the cut doesn't turn with the camera)
                hc = (hero[2] + hero[3]) / 2
                hero_clip = (*n, float(np.dot(n, hc)))
            near_keep = None
            if near_box is not None and inst.oid == focus_id:
                near_keep = set(self.part_names(inst.model, self._cam_part(i)))  # the filmed part, however long
                for k, part in enumerate(inst.model.parts):
                    lo, hi = part.geo.bounds()
                    w = (m0 @ np.array([[lo[0], lo[1], lo[2], 1], [hi[0], hi[1], hi[2], 1]], np.float32).T).T[:, :3]
                    blo, bhi = np.minimum(w[0], w[1]), np.maximum(w[0], w[1])
                    if np.all(bhi >= near_box[0]) and np.all(blo <= near_box[1]) and \
                            float(np.max(bhi - blo)) < 3.0 * float(np.max(near_box[1] - near_box[0])):
                        near_keep.add(k)
            beam_ok = None
            for k, part in enumerate(inst.model.parts):
                vis = st["parts"].get(part.name, 1.0)
                ghost = hero is not None and inst.oid == hero[0] and k not in hero[1]
                if vis <= 0.01 or k in hidden_parts or (ghost and (part.opacity < 0.5 or part.kind == "beam")):
                    continue
                if part.kind == "beam":  # headlamp beams: only a few, never right at the lens (no white-out)
                    if beam_ok is None:  # fades out as the camera comes close (no on/off pop)
                        d_eye = float(np.linalg.norm(st["pos"] - np.asarray(eye)))
                        beam_ok = min(1.0, max(0.0, (d_eye - 4.0 - inst.radius) / 2.5)) if inst.index < 6 else 0.0
                    if beam_ok <= 0.01:
                        continue
                if near_keep is not None and k not in near_keep:
                    continue  # macro: walls and far parts stay dark
                m = m0
                local, extra_glow, recolor = self.part_local(part, k, st, T)
                if vis < 0.999:
                    lo, hi = part.geo.bounds()
                    pc = (lo + hi) / 2
                    sm = np.eye(4, dtype=np.float32)
                    sm[:3, :3] *= vis
                    sm[:3, 3] = pc - pc * vis
                    local = local @ sm
                if not np.allclose(local, np.eye(4)):
                    m = m0 @ local
                color = recolor or hex_rgb(part.color)
                emi = part.emissive + extra_glow
                if part.kind == "light":
                    emi = max(emi, st["light"])
                    if st["light"] > 0:
                        lamp = (1.0, 0.85, 0.42)
                        color = tuple(a + (b - a) * st["light"] for a, b in zip(color, lamp))
                elif part.kind == "heater":  # a heating coil glows orange when it is turned on (light_on)
                    hot = st["light"]
                    if hot > 0:
                        emi = max(emi, 0.9 * hot)
                        color = tuple(a + (b - a) * hot for a, b in zip(color, (1.0, 0.36, 0.1)))
                emi += st["glow"]
                for name, g in st.get("glows", {}).items():
                    if part.name == name or part.name.startswith(name + "_") or (
                            part.name.startswith(name) and part.name[len(name):].isdigit()):
                        emi += g
                al = st["alarm"]
                for name, g in st.get("alarms", {}).items():
                    if k in self.part_names(inst.model, name):
                        al = max(al, g)
                if al:
                    color = tuple(a + (b - a) * (0.55 + 0.35 * al) for a, b in zip(color, (0.95, 0.12, 0.08)))
                    emi += 0.25 + 0.35 * al
                inner = tuple(max(0.05, x * 0.45) for x in color)
                xr = float(st["xray"]) if part.shell else 0.0  # (a car around a filmed engine: near side left out)
                part_clip = clip if (part.shell or not has_shell) else None  # cut the outside, keep the works whole
                if part_clip is not None and inst.oid in door_shot and _opens(part):
                    part_clip = None  # "the door closes": the door stays in the picture, it isn't cut away
                part_clip = own_cut.get(k, part_clip)
                op = part.opacity * inst_k * (beam_ok if part.kind == "beam" else 1.0)
                if k in fade_k and fade_k[k] < 0.999:  # fading out (left out / see-through here) or back in
                    op = min(op, fade_k[k])
                if ghost:  # the rest of the machine: a faint ghost, so the hero part is clearly IN its machine
                    draws.append(Draw(inst.keys[k], m, tuple(0.35 + 0.5 * c for c in color), 0.0, 0.3, None,
                                      inner, 0.8, shadow=False, shine=0.0))
                    continue
                if hero is not None and inst.oid == hero[0] and hero_clip is not None and op > 0.6 and \
                        part.kind not in ("chamber", "flame", "light") and self._hero_cut(inst, k, part, m, hero_clip, color,
                                                                                          emi, dyn):
                    continue  # cut exactly (manifold3d): the body and its cut face are in `dyn`
                if hero is not None and inst.oid == hero[0]:  # every piece cut in half, the cut faces in the cut colour
                    part_clip, inner, xr = hero_clip, hex_rgb(HERO_COLOR), 0.0
                    op = max(op, 0.35) if part.kind == "liquid" or part.opacity < 0.6 else op
                closed = hero is not None and inst.oid == hero[0] and op > 0.6 and part.kind not in ("chamber", "flame", "light") and \
                    not part.shell and part.geo.closed()  # a hollow shell (a capsule's skin) shows a rim, not a slab
                draws.append(Draw(inst.keys[k], m, color, emi, op, part_clip, inner, xr,
                                  shadow=part.opacity > 0.5 and inst.asset not in NO_SHADOW and inst.oid not in
                                  no_cast[0] and (inst.oid, k) not in no_cast[1],
                                  visible=not shadow_only,
                                  shine=SHINE.get(part.material, 0.0),
                                  cap=2 if hero is not None and inst.oid == hero[0] and op > 0.6 and not closed else 0,
                                  additive=part.kind == "beam"))  # headlamp beams: light added on top
                if shadow_only:
                    continue
                if closed and hero_clip is not None:  # the flat cut face of a solid piece, in the signature colour
                    wp = (np.hstack([part.geo.pos, np.ones((len(part.geo.pos), 1), np.float32)]) @ m.T)[:, :3]
                    face = section(wp, hero_clip[:3], hero_clip[3] - 1e-4)
                    if face is not None:
                        dyn.append((face, hex_rgb(HERO_COLOR), 0.22))
        parts = self.particles(i, T)
        near = 0.3 * float(np.linalg.norm(np.asarray(eye) - np.asarray(tgt)))  # right in front of the lens: big blobs
        if parts is not None and len(parts):
            parts = parts[np.linalg.norm(parts[:, :3] - np.asarray(eye, np.float32), axis=1) > near]
            cam_d = float(np.linalg.norm(np.asarray(eye) - np.asarray(tgt)))
            parts[:, 3] = np.minimum(parts[:, 3], 0.012 * cam_d)  # close-ups: small dots, never big balls
            if hero is not None:  # only what happens inside the hero part
                g = np.maximum((hero[3] - hero[2]) * 0.25, 0.05)
                inside = np.all((parts[:, :3] >= hero[2] - g) & (parts[:, :3] <= hero[3] + g), axis=1)
                parts = parts[inside]
        draws += self.puffs(i, T)
        draws += [d for d in self.arrows(i, T) if float(np.linalg.norm(d.model[:3, 3] - np.asarray(eye))) > near]
        c = np.asarray(tgt, np.float64)
        dist = float(np.linalg.norm(np.asarray(eye) - c))
        labels = self.labels(i, T, eye, tgt, fov, label_tex) if label_tex and t <= sc["dur"] else []
        look_name, style = self._looks[i] if not ending else (self._looks[0][0], self._looks[-1][1])
        mv = self._cams[i]["move"]
        dof = 0.0 if ending else {"macro": 0.45, "close_up": 0.25, "hero": 0.0}.get(mv, 0.0) * \
            float(style.get("dof", 1.0) if mv != "macro" else 1.0)
        if dof and i > 0 and not self._cams[i]["cut"]:  # the blur comes in softly after the flight (no pop)
            dof *= ease((t - self.flight(i)) / 0.6)
        if hero is not None:
            focus_d = float(np.linalg.norm(np.asarray(eye) - (hero[2] + hero[3]) / 2))
        else:
            focus_d = dist
        return Frame(eye=tuple(eye), target=tuple(tgt), fov=fov, draws=draws, particles=parts, labels=labels,
                     focus=tuple(float(x) for x in s_c), focus_radius=float(s_r0), far_radius=float(s_r1),
                     grid_center=(c[0], c[2]), fade=fade, sun=tuple(float(x) for x in sun),
                     bloom=0.9 if look_name == "macro_dark" else 0.6, lights=self._lights(c, T), style=style,
                     dof=dof, focus_dist=focus_d, time=float(T), dyn=dyn)

    def _vis_of(self, i: int, inst: Inst, st: dict, eye, tgt, fov: float) -> tuple:
        """(leave the whole object out?, parts left out, parts made see-through) for camera (eye, tgt) in shot i."""
        focus_id = self._cams[i]["target"]
        if inst.oid in self.env_ids and self._in_front_of_subject(inst, st, eye, tgt, fov, i):
            return True, set(), set()  # a prop drawn over the subject: leave it out (clean composition)
        hidden_parts = set()
        if inst.oid not in self._focus[i] and \
                inst.asset not in ("pad", "ground", "terrain", "ground_plate") and self._blocks(inst, st, eye, tgt):
            if inst.oid in self.env_ids:
                return True, set(), set()  # a prop in front of the subject: leave it out
            if any(p.shell for p in inst.model.parts):  # a roof or wall in the way: leave out exactly the
                hidden_parts = self._blocking_parts(inst, st, eye, tgt)  # parts that block (no ghost lines)
        if inst.oid not in self._focus[i] and inst.asset not in ("pad", "ground", "terrain", "ground_plate"):
            near = self._near_lens_parts(inst, st, eye, tgt, fov)  # a post sweeping past right in front of the lens
            if near and inst.oid in self.env_ids:
                return True, set(), set()
            hidden_parts |= {k for k in near if not _works(inst.model.parts[k])}
        see_through = set()
        if inst.oid == focus_id and self._cam_part(i):  # its own walls/panels in front of the part we film
            keep = set(self.part_names(inst.model, self._cam_part(i)))
            blocking = self._blocking_parts(inst, st, eye, tgt, any_part=True, liquids=True) - keep
            see_through = {k for k in blocking if inst.model.parts[k].kind == "liquid" or  # water: see through it
                           not inst.model.parts[k].shell}  # a working part in front: glass, never missing
            hidden_parts |= blocking - see_through
        parent_of_focus = any(self.mounts.get(f, (None,))[0] is inst for f in self._focus[i]) and \
            float(np.linalg.norm(np.asarray(eye) - np.asarray(tgt))) < inst.radius * 1.15
        # the car around its engine is a ghost only when the camera is close on the engine; wide shots and
        # shots of the car show the real car with its hood open
        if parent_of_focus:  # an engine inside its car: the car is a ghost, nothing of it in front of the engine
            hidden_parts |= self._shell_parts_over_subject(inst, st, eye, tgt, fov, i, any_size=True, any_part=True)
            hidden_parts |= self._blocking_parts(inst, st, eye, tgt, any_part=True)
        elif inst.oid not in self._focus[i] and any(p.shell for p in inst.model.parts):
            hidden_parts |= self._shell_parts_over_subject(inst, st, eye, tgt, fov, i)
        return False, hidden_parts, see_through - hidden_parts

    def _shot_vis(self, i: int) -> dict:
        """What shot i leaves out, decided ONCE for the whole shot from a few camera positions after the flight in
        (a union): a panel never vanishes in one frame in the middle of a shot (that was a visible pop)."""
        cache = self.__dict__.setdefault("_vis_cache", {})
        if i in cache:
            return cache[i]
        sc = self.scenes[i]
        du, tr = sc["dur"], self.flight(i)
        out: dict = {}
        old_aim = getattr(self, "_aim_i", None)
        self._aim_i = i
        n_s = max(4, min(14, int((du - tr) / 0.4) + 2))  # every ~0.4 s: a post the camera passes is caught too
        for f in [k / (n_s - 1) for k in range(n_s)]:
            t = tr + (du - tr) * f
            T = sc["start"] + min(t, du - 1e-3)
            eye, tgt, fov, _ = self._camera(i, min(t, du))
            for inst in self.insts:
                st = self.state(inst, T)
                if st["vis"] <= 0.01:
                    continue
                skip, hid, see = self._vis_of(i, inst, st, eye, tgt, fov)
                if not (skip or hid or see):
                    continue
                o = out.setdefault(inst.oid, [False, set(), set()])
                o[0] = o[0] or skip
                o[1] |= hid
                o[2] |= see
        self._aim_i = old_aim
        res = {oid: (sk, hid, see - hid) for oid, (sk, hid, see) in out.items()}
        cache[i] = res
        return res

    def _hero_normal(self, i: int) -> np.ndarray:
        cache = self.__dict__.setdefault("_hero_n", {})
        if i not in cache:
            du, tr = self.scenes[i]["dur"], self.flight(i)
            eye, tgt, _ = self._cam_path(i, tr + 0.5 * max(du - tr, 0.0))
            n = np.asarray(eye, np.float64) - np.asarray(tgt, np.float64)
            n[1] = 0
            n /= max(np.linalg.norm(n), 1e-6)
            ca, sa = math.cos(math.radians(55)), math.sin(math.radians(55))
            cache[i] = np.array([n[0] * ca - n[2] * sa, 0.0, n[0] * sa + n[2] * ca])
        return cache[i]

    def _hero_cut(self, inst, k: int, part, m, plane, color, emi: float, dyn: list) -> bool:
        """Cut one hero part exactly with manifold3d: its body + a cut face in HERO_COLOR, piece by piece (12 blades
        get 12 small faces, not a comb), hollow parts as a thin rim. False = not a closed solid (clip it instead)."""
        from . import cad  # noqa: PLC0415

        if not cad.manifold_available():
            return False
        key = (inst.oid, k, np.round(m, 5).tobytes(), tuple(round(float(x), 5) for x in plane))
        cache = self.__dict__.setdefault("_cut_cache", {})
        if key not in cache:
            if len(cache) > 600:
                cache.clear()
            wp = (np.hstack([part.geo.pos, np.ones((len(part.geo.pos), 1), np.float32)]) @ m.T)[:, :3]
            try:
                kept, caps, loose = cad.cut(wp, plane[:3], plane[3], hollow=float(getattr(part, "hollow", 0.0) or 0.0))
            except Exception:  # noqa: BLE001
                kept, caps, loose = None, None, None
            if kept is None or len(loose) or (not len(kept) and not len(caps)):
                cache[key] = None
            else:
                smooth = part.geo.nrm is not None
                cache[key] = (kept.reshape(-1, 3), M.smooth_normals(kept.reshape(-1, 3)) if smooth else None,
                              caps.reshape(-1, 3))
        res = cache[key]
        if res is None:
            return False
        kept, knrm, caps = res
        if len(kept):
            dyn.append((kept, color, emi, SHINE.get(part.material, 0.0), knrm))
        if len(caps):
            dyn.append((caps, hex_rgb(HERO_COLOR), 0.03, 0.0, None))
        return True

    def _near_lens_parts(self, inst: Inst, st: dict, eye, tgt, fov: float) -> set:
        """Parts of another object that come within a third of the subject distance of the lens, inside the picture:
        they would fill the frame with a big blurry shape (a barn post, a stall wall) while the camera passes."""
        eye = np.asarray(eye, np.float64)
        fwd = np.asarray(tgt, np.float64) - eye
        dist = float(np.linalg.norm(fwd))
        if dist < 1e-6:
            return set()
        fwd /= dist
        reach = 0.33 * dist
        if float(np.linalg.norm(st["pos"] - eye)) > inst.radius * max(1.0, inst.scale * st["scale"]) * 1.2 + reach:
            return set()
        m = self.inst_matrix(inst, {**st, "vis": 1.0})
        try:
            inv = np.linalg.inv(m.astype(np.float64))
        except np.linalg.LinAlgError:
            return set()
        e = (inv @ np.append(eye, 1.0))[:3]
        cos_half = math.cos(math.radians(fov) / 2 * max(1.0, self.size[0] / self.size[1]) * 1.3)
        out = set()
        for k, part in enumerate(inst.model.parts):
            for a, b in (part.boxes or [part.geo.bounds()]):
                q = np.clip(e, a, b)  # the closest point of the part's box to the lens
                w = (m @ np.append(q, 1.0))[:3]
                d = w - eye
                dl = float(np.linalg.norm(d))
                if dl < reach and (dl < 1e-6 or float(np.dot(d, fwd)) / dl > cos_half * 0.6):
                    out.add(k)
                    break
        return out

    def _flight_vis(self, i: int) -> dict:
        """What blocks the view anywhere along the camera's flight into shot i (sampled), like a short shot of its own."""
        cache = self.__dict__.setdefault("_vis_cache", {})
        key = ("fly", i)
        if key not in cache:
            sc = self.scenes[i]
            tr = self.flight(i)
            out: dict = {}
            old_aim = getattr(self, "_aim_i", None)
            self._aim_i = i
            n_f = max(5, min(12, int(tr / 0.15)))  # every ~0.15 s of the flight
            for f in [0.08 + 0.84 * k / (n_f - 1) for k in range(n_f)]:
                eye, tgt, fov, _ = self._camera(i, tr * f)
                T = sc["start"] + tr * f
                for inst in self.insts:
                    st = self.state(inst, T)
                    if st["vis"] <= 0.01:
                        continue
                    skip, hid, see = self._vis_of(i, inst, st, eye, tgt, fov)
                    if skip or hid or see:
                        o = out.setdefault(inst.oid, [False, set(), set()])
                        o[0], o[1], o[2] = o[0] or skip, o[1] | hid, o[2] | see
            self._aim_i = old_aim
            cache[key] = {oid: (sk, hid, see - hid) for oid, (sk, hid, see) in out.items()}
        return cache[key]

    def _no_cast(self) -> tuple:
        """(objects, (object, part) pairs) that never cast a shadow in this video: whatever any shot leaves out,
        makes see-through or turns x-ray. Their shadow can't fade with them, so it is never there: no shadow pops."""
        cache = self.__dict__.setdefault("_vis_cache", {})
        if "no_cast" not in cache:
            objs, parts = set(), set()
            flights = [self._flight_vis(k) for k in range(1, len(self.scenes)) if self.flight(k) > 0]
            for vis in [self._shot_vis(k) for k in range(len(self.scenes))] + flights + \
                    ([self._ending_vis()] if self.ending == "overview" else []):
                for oid, (skip, hid, see) in vis.items():
                    if skip:
                        objs.add(oid)
                    parts |= {(oid, k) for k in hid | see}
            for e in self.events:
                if e.do == "xray" and e.oid in self.groups:
                    for inst in self.groups[e.oid]:
                        parts |= {(inst.oid, k) for k, p in enumerate(inst.model.parts) if p.shell}
            cache["no_cast"] = (objs, parts)
        return cache["no_cast"]

    def _ending_vis(self) -> dict:
        """What the ending's overview leaves out (a wall between the overview camera and the machine)."""
        cache = self.__dict__.setdefault("_vis_cache", {})
        if "end" not in cache:
            last = len(self.scenes) - 1
            oe, ot = self._overview()
            out = {}
            old_aim = getattr(self, "_aim_i", None)
            self._aim_i = last
            for inst in self.insts:
                st = self.state(inst, self.total)
                if st["vis"] <= 0.01:
                    continue
                skip, hid, see = self._vis_of(last, inst, st, oe, ot, self.fov)
                if skip or hid:
                    out[inst.oid] = (skip, hid, set())
            self._aim_i = old_aim
            cache["end"] = out
        return cache["end"]

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
        for e in self.events:  # a snapped rope / a clamp: the brakes grip the rails with a shower of sparks
            if e.do not in ("snap", "clamp") or abs(e.scene - i) > 1 or not (e.start + 0.25 <= T < e.start + 2.2):
                continue
            brake = (e.part or "safety_brakes") if e.do == "clamp" else "safety_brakes"
            box = self.part_box(e.oid, brake, T, margin=False) if e.oid in self.groups else None
            if box is None:
                continue
            t = T - e.start - 0.25
            rng = np.random.default_rng(zlib.crc32(f"{e.oid}/brake/{e.scene}".encode()))
            lo, hi = box
            for side in (lo[0], hi[0]):
                for k in range(34):
                    ph = rng.random()
                    age = (ph * 0.6 + t) % 0.6
                    v = rng.normal(0, 1, 3) * np.array([1.4, 0.6, 1.4]) + np.array([0, 1.8, 0])
                    p = np.array([side, lo[1] + 0.1, (lo[2] + hi[2]) / 2]) + v * age - np.array([0, 4.9 * age * age, 0])
                    fade = min(1.0, t / 0.3) * max(0.0, 1.0 - t / 2.0)  # the shower builds up and dies down
                    out.append([*p, 0.03 * fade, 1.0, 0.78 - 0.4 * age, 0.25, 1.5 * fade])
        for e in self.events:
            if e.do not in ("flow", "bubbles", "smoke", "sparks", "cutaway") or not (e.start <= T < e.end):
                continue
            if abs(e.scene - i) > 1:
                continue
            t = T - e.start
            color = hex_rgb(e.params["color"]) if e.params.get("color") else FLOW_COLORS.get(e.do, (0.45, 0.86, 0.36))
            fade = min(1.0, t / 0.4) * (min(1.0, max(0.0, (e.end - T) / 0.35)) if e.end != math.inf else 1.0)
            rng = np.random.default_rng(zlib.crc32(f"{e.oid}/{e.do}/{e.scene}".encode()))
            if e.do in ("flow", "sparks"):
                path = self._flow_path(e, T)
                if path is None:
                    continue
                lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
                total = float(lengths.sum()) or 1.0
                k_size = self._flow_scale(e)  # small machines get small particles (an engine is 0.6 m)
                n = int(e.params.get("count", max(18, min(60, int(total / (0.55 * k_size)))) if e.do == "flow" else 14))
                speed = e.params.get("speed", (2.2 if e.do == "flow" else 7.0) * max(0.25, k_size))
                c2 = hex_rgb(e.params["color2"]) if e.params.get("color2") else None
                ph = rng.random(n)
                for k in range(n):
                    s = ((ph[k] + speed * t / total) % 1.0) * total
                    if s > speed * t:  # particles start at the beginning (no pop-in in the middle)
                        continue
                    p = _along(path, lengths, s)
                    if e.do == "sparks":
                        p = p + rng.normal(0, 0.05 * k_size, 3)
                    ends = min(1.0, s / (0.06 * total), (total - s) / (0.06 * total))  # shrink in/out at the path ends
                    size = (0.16 if e.do == "flow" else 0.1) * fade * k_size * max(0.0, ends)
                    col = color if c2 is None else tuple(a + (b - a) * (s / total) for a, b in zip(color, c2))
                    out.append([*p, size, *col, 0.5 if e.do == "flow" else 1.2])
            elif e.do == "cutaway":  # the cut-open tank shows what lives inside: drifting bacteria
                inst = self.groups[e.oid][0]
                if inst.asset not in ("tank", "digester") and not e.params.get("bacteria"):
                    continue  # a machine cut open shows its own working parts, not germs
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
                                c[2] + rr * math.sin(a), 0.11 * min(1.0, t / 0.6) * fade, 0.45, 0.86, 0.36, 0.4])
            elif e.do == "bubbles":
                inst = self.groups[e.oid][0]
                lo, hi = self.group_box(e.oid, T)
                c = (lo + hi) / 2
                surf = self.anchor(e.oid, "surface", T) if "surface" in inst.model.anchors else np.array([c[0], hi[1], c[2]])
                r = min(hi[0] - lo[0], hi[2] - lo[2]) * 0.35
                kb = float(min(1.0, max(0.08, inst.radius / 4.0)))  # bubbles in a toilet bowl are small
                for k in range(int(e.params.get("count", 26))):
                    a, rr, ph = rng.random() * 6.283, math.sqrt(rng.random()) * r, rng.random()
                    h = ((ph + t * 0.45) % 1.0)
                    y = float(lo[1]) + 0.3 * kb + h * (float(surf[1]) - float(lo[1]) + 1.2 * kb)
                    wrap = min(1.0, h / 0.1, (1.0 - h) / 0.1)  # grow at the bottom, fade at the top (no pop)
                    out.append([c[0] + rr * math.cos(a), y, c[2] + rr * math.sin(a), (0.1 + 0.08 * h) * kb * fade * wrap,
                                *color, 0.35])
        return np.asarray(out, np.float32) if out else None

    def _flow_scale(self, e: Event) -> float:
        """Particle size for a flow: 1 for big plants (tanks, pipes), smaller for small machines."""
        inst = self.groups[e.oid][0]
        r = inst.radius
        if inst.asset in ("pipe", "wire", "cable", "chain") and e.params.get("to"):
            to = str(e.params["to"]).split(".")[0]
            r = self.groups[to][0].radius if to in self.groups else r
        return float(min(1.0, max(0.1, r / 4.0)))

    def arrows(self, i: int, T: float) -> list:
        """Glowing arrows that travel along every flow: the viewer sees where things go."""
        out = []
        for e in self.events:
            if e.do not in ("flow", "sparks") or not (e.start <= T < e.end) or abs(e.scene - i) > 0:
                continue
            if e.params.get("arrows") is False:
                continue
            path = self._flow_path(e, T)
            if path is None or len(path) < 2:
                continue
            lengths = np.linalg.norm(np.diff(path, axis=0), axis=1)
            total = float(lengths.sum())
            k = self._flow_scale(e)
            if total < 1.5 * k:
                continue
            t = T - e.start
            color = hex_rgb(e.params["color"]) if e.params.get("color") else FLOW_COLORS.get(e.do, (0.45, 0.86, 0.36))
            c2 = hex_rgb(e.params["color2"]) if e.params.get("color2") else None
            n = max(1, min(4, int(total / (2.2 * k))))
            speed = 0.6 * max(0.25, k) * (2.0 if e.do == "sparks" else 1.0)
            for a in range(n):
                s = ((a / n + speed * t / total) % 1.0) * total
                p = _along(path, lengths, s)
                q = _along(path, lengths, min(total, s + 0.05 * total))
                d = q - p
                if float(np.linalg.norm(d)) < 1e-6:
                    continue
                d /= np.linalg.norm(d)
                yaw = math.degrees(math.atan2(-d[2], d[0]))
                pitch = math.degrees(math.asin(max(-1.0, min(1.0, d[1]))))
                m = np.eye(4, dtype=np.float32)
                m[:3, :3] = rot_matrix(0, yaw, pitch) * (0.45 * k)
                m[:3, 3] = p
                col = color if c2 is None else tuple(x + (y - x) * (s / total) for x, y in zip(color, c2))
                fade = min(1.0, t / 0.4) * min(1.0, s / (0.3 * k + 1e-6), (total - s) / (0.3 * k + 1e-6))
                out.append(Draw("__arrow", m, tuple(min(1.0, c * 1.1 + 0.08) for c in col), 0.9, 0.95 * fade,
                                shadow=False))
        return out

    def _air(self, i: int, T: float) -> list:
        """Ambient particles of the place: bubbles under water, dust, snow, stars, blood cells. Each shot has its own
        cloud around its subject; while the camera flies in, the old cloud fades out and the new one fades in."""
        kind = self.look.get("air")
        if not kind:
            return []
        eye = np.asarray(self.camera(i, T - self.scenes[i]["start"])[0], np.float64) if i < len(self.scenes) else None
        t = T - self.scenes[i]["start"]
        tr = self.flight(i)
        if i > 0 and t < tr and not self._cams[i]["cut"]:
            w = smoother(t / tr) if self.calm else ease(t / tr)
            return self._air_field(i - 1, T, eye, kind, 1.0 - w) + self._air_field(i, T, eye, kind, w)
        return self._air_field(i, T, eye, kind, 1.0)

    def _air_field(self, i: int, T: float, eye, kind: str, k_all: float) -> list:
        if k_all <= 0.01:
            return []
        c = np.asarray(self._cams[i]["c"], np.float64)
        r = max(8.0, self._cams[i]["r"] * 3)
        rng = np.random.default_rng(zlib.crc32(f"air/{kind}".encode()))
        n = {"stars": 160, "snow": 110, "bubbles": 80, "dust": 70, "cells": 36}[kind]
        base = rng.random((n, 3))
        eye = c if eye is None else eye
        near = max(2.0, 0.45 * float(np.linalg.norm(eye - c)))  # nothing big and blurry right in front of the lens
        out = []
        for k in range(n):
            x, y, z = (base[k] - 0.5) * 2 * r
            if kind == "stars":
                d = np.array([x, abs(y) + r * 0.3, z])
                p = c + d / max(np.linalg.norm(d), 1e-6) * r * 6
                out.append([*p, 0.35 * (0.5 + base[k][0]) * k_all, 1.0, 1.0, 1.0, 1.5])
                continue
            h = 2 * r
            edge = 1.0  # particles fade where they wrap around (no pop at the top / bottom / side)
            if kind == "bubbles":
                u = (base[k][1] * h + T * 0.9) % h
                y = u - r * 0.2
                edge = min(1.0, u / (0.08 * h), (h - u) / (0.08 * h))
                col, size, emi = (0.75, 0.92, 1.0), 0.07 + 0.05 * base[k][2], 0.5
            elif kind == "snow":
                u = (base[k][1] * h + T * 0.7) % h
                y = h - u
                edge = min(1.0, u / (0.08 * h), (h - u) / (0.08 * h))
                col, size, emi = (1.0, 1.0, 1.0), 0.06, 0.4
            elif kind == "cells":
                y = abs(y) * 0.5 + 0.5 + 0.3 * np.sin(T * 0.8 + k)
                x += np.sin(T * 0.3 + k) * 0.8
                col, size, emi = (0.82, 0.12, 0.16), 0.16 + 0.1 * base[k][2], 0.1
            else:  # dust
                y = abs(y) * 0.4 + 0.3 + 0.2 * np.sin(T * 0.5 + k)
                u = (x + r + T * 0.25) % (2 * r)
                x = u - r
                edge = min(1.0, u / (0.1 * r), (2 * r - u) / (0.1 * r))
                col, size, emi = (0.95, 0.85, 0.65), 0.04, 0.2
            dist = float(np.linalg.norm(np.array([c[0] + x, y, c[2] + z]) - eye))
            lens = min(1.0, max(0.0, (dist - near) / (0.4 * near)))  # near the lens: shrinks away smoothly
            kk = k_all * edge * lens
            if kk <= 0.01:
                continue
            out.append([c[0] + x, y, c[2] + z, size * kk, *col, emi])
        return out

    def puffs(self, i: int, T: float) -> list:
        """Smoke: soft see-through puffs that rise, grow and fade."""
        out = []
        for e in self.events:
            if e.do != "smoke" or not (e.start <= T < e.end) or abs(e.scene - i) > 1:
                continue
            t = T - e.start
            src = self.anchor(e.oid, "exhaust" if "exhaust" in self.groups[e.oid][0].model.anchors else "top", T)
            part = self._scene_part(e.scene, e.oid)
            if part and "exhaust" not in self.groups[e.oid][0].model.anchors:  # mist from the opened door, steam
                box = self.part_box(e.oid, part, T, margin=False)  # from the valve: where the shot is
                if box is not None:
                    src = (box[0] + box[1]) / 2
            color = hex_rgb(e.params["color"]) if e.params.get("color") else FLOW_COLORS["smoke"]
            for k in range(8):
                h = (k / 8 + t * 0.32) % 1.0
                if h > t * 0.32 + 0.02:
                    continue
                kk = float(min(1.0, max(0.15, self.groups[e.oid][0].radius / 3.0)))  # a fridge's mist is small
                drift = np.array([0.9 * h + 0.2 * math.sin(k * 2.1 + t), 3.2 * h, 0.35 * math.sin(k * 1.3)]) * kk
                s = (0.25 + 0.75 * h) * kk
                m = np.eye(4, dtype=np.float32)
                m[:3, :3] *= s
                m[:3, 3] = src + drift
                end_k = min(1.0, max(0.0, (e.end - T) / 0.4)) if e.end != math.inf else 1.0
                out.append(Draw("__puff", m, color, 0.0, 0.55 * (1 - h) ** 0.7 * min(1.0, h / 0.08) * end_k, shadow=False))
        return out

    def _blocking_parts(self, inst: Inst, st: dict, eye, tgt, any_part: bool = False, liquids: bool = False) -> set:
        """Indexes of the shell parts (walls, posts, roofs) that are between the camera and the subject."""
        m = self.inst_matrix(inst, {**st, "vis": 1.0})
        try:
            inv = np.linalg.inv(m.astype(np.float64))
        except np.linalg.LinAlgError:
            return set()
        e = (inv @ np.append(np.asarray(eye, np.float64), 1.0))[:3]
        out = set()
        for k, part in enumerate(inst.model.parts):
            if not part.shell and not any_part:
                continue
            if any_part and not part.shell and _works(part) and not (liquids and part.kind == "liquid"):
                continue  # never hide a working part (pistons, gears, valves: what the viewer should see)
            for tp in self._aim_points(tgt):
                t = (inv @ np.append(tp, 1.0))[:3]
                if any(_seg_box(e, t, a, b) for a, b in (part.boxes or [part.geo.bounds()])):
                    out.add(k)
                    break
        return out

    def _in_front_of_subject(self, inst: Inst, st: dict, eye, tgt, fov, i: int) -> bool:
        """A prop that is nearer than the subject and overlaps it on screen."""
        if inst.asset in FLOORS:
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
        W, H = self.size
        if not ok1:  # nearer than the subject and partly behind the lens: it wraps around the camera
            return True
        big = (min(px1, W) - max(px0, 0)) * (min(py1, H) - max(py0, 0)) > 0.12 * W * H  # a big blob up front
        return bool(ok2 and (px0 < sx1 and px1 > sx0 and py0 < sy1 and py1 > sy0 or big))

    def _shell_parts_over_subject(self, inst: Inst, st: dict, eye, tgt, fov, i: int, any_size: bool = False,
                                  any_part: bool = False) -> set:
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
            if not part.shell and not any_part:
                continue
            for a, b in (part.boxes or [part.geo.bounds()]):
                if sorted(np.asarray(b) - np.asarray(a))[1] > 0.5 and not any_size:
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
        if e.params.get("path"):  # one of the machine's own paths (intake, exhaust, refrigerant loop…)
            own = self.path_world(e.oid, T, e.params["path"])
            if own is not None:
                return np.asarray(own)
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
            p = self.label_point(i, lb, T)
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
            y = min(max(y, img.shape[0] + 0.14 * H), H - label_floor(W, H))
            out.append(Label(key, img, float(x), float(y), scale=pop(k) * 0.98 + 0.02, alpha=min(k * 1.5, out_fade)))
        out.sort(key=lambda lb: lb.y)  # push overlapping labels apart
        for a in range(1, len(out)):
            for b in range(a):
                la, lb2 = out[a], out[b]
                if abs(la.x - lb2.x) < (la.image.shape[1] + lb2.image.shape[1]) / 2 and \
                        abs(la.y - lb2.y) < la.image.shape[0] * 1.05:
                    la.y = lb2.y + la.image.shape[0] * 1.08
        out += self.overlays(i, T, label_tex)
        for lb in out:  # never cut off at the frame edge: shrink a too-wide label, keep it inside the picture
            if getattr(lb, "anchor", "") == "center":
                continue  # stat cards and map insets are placed by overlays()
            w, h = lb.image.shape[1], lb.image.shape[0]
            fit = min(1.0, (W * 0.92) / max(w, 1))
            lb.scale *= fit
            half = w * lb.scale / 2
            lb.x = min(max(lb.x, half + 0.03 * W), W - half - 0.03 * W)
            lb.y = min(max(lb.y, h * lb.scale + 0.14 * H), H - label_floor(W, H))  # above the subtitles + buttons
        return out


    def overlays(self, i: int, T: float, label_tex) -> list:
        """Documentary cards: a stat card at the bottom (700 M / UNDERGROUND, DAY 17) and a small map with a
        location marker at the top, both sliding in and out."""
        sc = self.scenes[i]
        p = sc["plan"]
        t = T - sc["start"]
        W, H = self.size
        out = []
        if not hasattr(label_tex, "stat_card"):
            return out
        k_in = min(1.0, max(0.0, (t - 0.35) / 0.35))
        k_out = min(1.0, max(0.0, (sc["dur"] - t) / 0.3))
        a = ease(k_in) * k_out
        if a > 0.01 and p.get("stat"):
            img, key = label_tex.stat_card(p["stat"].get("big", ""), p["stat"].get("small", ""))
            y = H * (0.70 if H > W else 0.80) + (1 - ease(k_in)) * H * 0.03
            out.append(Label(key, img, W / 2, float(y), scale=1.0, alpha=a, anchor="center"))
        if a > 0.01 and p.get("map"):
            pulse = 0.5 + 0.5 * math.sin(t * 5.0)
            img, key = label_tex.map_inset(p["map"].get("lat", 0.0), p["map"].get("lon", 0.0), p["map"].get("place", ""),
                                           p["map"].get("region", ""), round(pulse * 4) / 4)
            y = H * (0.2 if H > W else 0.22) + img.shape[0] / 2 + (1 - ease(k_in)) * -H * 0.02
            out.append(Label(key, img, W - img.shape[1] / 2 - W * 0.05, float(y), scale=1.0, alpha=a, anchor="center"))
        return out


WORKS = {"spin", "slide", "rod", "valve", "swing", "pulse", "chamber", "level", "stretch"}


def _opens(part) -> bool:
    mos = part.motion if isinstance(part.motion, list) else [part.motion] if part.motion else []
    return any(m.get("type") == "open" or m.get("drive") == "open" for m in mos)


def _works(part) -> bool:
    mos = part.motion if isinstance(part.motion, list) else [part.motion] if part.motion else []
    return any(m.get("type") in WORKS for m in mos) or part.kind in ("blade", "piston", "rocker", "liquid")


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


def _seg_hits(a, b, tris: np.ndarray, t0: float = 0.02, t1: float = 0.94) -> bool:
    """Does the segment a→b (between 2 % and 94 % of the way) pass through any of the triangles (n, 3, 3)?"""
    d = np.asarray(b, np.float64) - np.asarray(a, np.float64)
    v0, e1, e2 = tris[:, 0], tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]
    pv = np.cross(d, e2)
    det = np.einsum("ij,ij->i", e1, pv)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    tv = np.asarray(a, np.float64) - v0
    u = np.einsum("ij,ij->i", tv, pv) * inv
    qv = np.cross(tv, e1)
    v = (qv @ d) * inv
    t = np.einsum("ij,ij->i", e2, qv) * inv
    return bool(np.any(ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > t0) & (t < t1)))


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
