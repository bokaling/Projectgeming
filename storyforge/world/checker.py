"""🔍 Automatic quality check of every shot, before the video is rendered.

1. Local checks (instant, no internet): is the camera's subject in the picture and big enough, is the camera
   inside a wall or under the floor, do labels overlap or fall off the screen, is the still frame empty?
   Problems are fixed in the plan right away (camera closer / further / higher, fewer labels).
2. With a free Gemini key: Gemini looks at one still per shot (vision) together with the narration and says
   which shots are broken or don't match the words. Those shots are fixed with the shot fixer.
"""

from __future__ import annotations

import copy
import io

import numpy as np

from .gl import project_points
from .scene import SAFE_BOTTOM, SAFE_TOP

MIN_FILL = 0.30  # the main object must fill at least 30 % of the frame (width or height)
MIN_COVERAGE = 0.30  # at least 30 % of the picture shows things (not just floor and sky)


def coverage(world, i: int, T: float, eye, tgt, fov, grid=(18, 32)) -> float:
    """How much of the picture is covered by objects (projected boxes on a coarse grid; pads don't count)."""
    from .decor import inst_box  # noqa: PLC0415

    W, H = world.size
    gx, gy = grid if W < H else grid[::-1]
    cover = np.zeros((gy, gx), bool)
    for inst in world.insts:
        if inst.asset in ("pad", "ground", "terrain", "ground_plate"):
            continue
        st = world.state(inst, T)
        if st["vis"] < 0.5:
            continue
        lo, hi = inst_box(inst, st["pos"], st["yaw"], st["scale"])
        c = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
        p = project_points(eye, tgt, fov, (W, H), c)
        if (p[:, 2] <= 0.05).any():
            continue
        x0, x1 = int(np.clip(p[:, 0].min() / W * gx, 0, gx)), int(np.clip(np.ceil(p[:, 0].max() / W * gx), 0, gx))
        y0, y1 = int(np.clip(p[:, 1].min() / H * gy, 0, gy)), int(np.clip(np.ceil(p[:, 1].max() / H * gy), 0, gy))
        cover[y0:y1, x0:x1] = True
    return float(cover.mean())

VISION_SYSTEM = """You check still frames of a low poly 3D "how it works" explainer video (dark teal studio, glowing grid floor).
For each shot you get the narration and one still frame from the middle of the shot.
A shot is NOT ok only if something is clearly broken: the main object is missing, tiny (under 30 % of the frame) or
cut off, it sits under the captions (top 15 %) or the app buttons (bottom 20 %), the camera is inside an object or wall,
the frame is empty or mostly floor and sky, labels overlap, the first shot is a far-away wide shot instead of a close,
funny or shocking hook, or the picture clearly doesn't fit the narration.
Simple low poly shapes are the style: they are fine. For every bad shot give ONE short fix instruction in plain words,
like "camera further away", "show the gas flowing in the pipe", "make the tank bigger", "remove the labels".
Reply with JSON only: {"shots": [{"n": 1, "ok": true}, {"n": 2, "ok": false, "problem": "…", "fix": "…"}]}"""


def local_problems(world, i: int, at: float = 0.6, label_tex=None) -> list[str]:
    """What's wrong with shot i, judged from the 3D world alone (no picture needed)."""
    sc = world.scenes[i]
    t = sc["dur"] * at
    T = sc["start"] + t
    eye, tgt, fov, fade = world.camera(i, t)
    if fade > 0.5:  # fading into / out of the tiny world: nothing to judge
        return []
    W, H = world.size
    out = []
    if eye[1] < 0.3:
        out.append("under_floor")
    spec = world._cams[i]
    iso = world.isolated(i) if hasattr(world, "isolated") else ""
    if iso in ("hero", "macro"):  # ONE part alone (one piston of four): judge the box this shot really frames
        lo, hi = spec["lo"], spec["hi"]
    else:
        lo, hi = world.focus_box(i, T)  # what the line talks about (the same box the camera frames)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    pts = project_points(eye, tgt, fov, (W, H), corners)
    front = pts[pts[:, 2] > 0.05]
    if len(front) < 8:
        out.append("target_behind")
    else:
        x0, x1 = front[:, 0].min(), front[:, 0].max()
        y0, y1 = front[:, 1].min(), front[:, 1].max()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (0.0 < cx < W and 0.0 < cy < H):
            out.append("target_off_screen")
        size = max((x1 - x0) / W, (y1 - y0) / H)  # how much of the frame the subject fills
        if size < MIN_FILL:
            out.append("target_too_small")
        elif spec["move"] not in ("zoom_into", "close_up", "macro") and (
                x0 < -0.02 * W or x1 > 1.02 * W or y0 < (SAFE_TOP - 0.03) * H or y1 > (1 - SAFE_BOTTOM + 0.03) * H):
            out.append("cut_off")  # not fully visible, or under the captions / the app buttons
        if (x1 - x0) > W * 2.6 and (y1 - y0) > H * 2.6 and spec["move"] not in ("zoom_into", "close_up"):
            out.append("target_too_big")
        if not iso and coverage(world, i, T, eye, tgt, fov) < MIN_COVERAGE:  # (a hero part is alone on purpose)
            out.append("mostly_empty")
    for inst in world.insts:  # the camera inside something solid
        if iso in ("hero", "macro", "subject"):
            break  # only the subject is drawn in these shots: nothing else can be in the way
        st = world.state(inst, T)
        if st["vis"] < 0.5 or st["cut"] > 0 or st["xray"]:
            continue
        solid = [p for p in inst.model.parts if p.opacity > 0.9 and p.geo.tris]
        if not solid or float(np.linalg.norm(np.asarray(eye) - st["pos"])) > inst.radius * 1.5 + 1:
            continue
        m = world.inst_matrix(inst, {**st, "vis": 1.0})  # the eye in the object's own space, then part by part
        local = np.linalg.solve(m, np.append(np.asarray(eye, np.float64), 1.0))[:3]
        inside = False
        for p in solid:  # an open barn is fine to stand in; its floor, posts and rails are not
            for a, b in (p.boxes or [p.geo.bounds()]):
                if np.all(local > a + 0.05) and np.all(local < b - 0.05):
                    inside = True
                    break
            if inside:
                break
        if inside and spec["move"] != "zoom_into":
            out.append(f"camera_inside:{inst.oid}")
            break
    if label_tex is not None and sc["plan"]["labels"]:
        e2, t2, f2, _ = world.camera(i, sc["dur"] - 0.25)
        labels = world.labels(i, sc["start"] + sc["dur"] - 0.25, e2, t2, f2, label_tex)
        for lb in labels:
            h = lb.image.shape[0]
            if lb.y > H - 0.04 * H or lb.y - h < 0:
                out.append("label_off_screen")
                break
        for a_ in range(len(labels)):
            for b_ in range(a_):
                la, lb2 = labels[a_], labels[b_]
                if abs(la.x - lb2.x) < (la.image.shape[1] + lb2.image.shape[1]) / 2 - 2 and \
                        abs(la.y - lb2.y) < la.image.shape[0] * 0.9:
                    out.append("labels_overlap")
                    break
            if "labels_overlap" in out:
                break
    return out


def content_fraction(img: np.ndarray) -> float:
    """How much of a finished frame shows things, not just the dark teal background and the faint grid."""
    a = img[::4, ::4].astype(np.float32)
    teal = np.array([16.0, 55.0, 62.0])
    dark_teal = np.linalg.norm(a - teal, axis=2) < 38
    grid = (a[..., 1] > a[..., 0] + 40) & (a[..., 2] > a[..., 0] + 30) & (a[..., 0] < 90)  # cyan lines
    return float(1.0 - (dark_teal | grid).mean())


def empty_picture(img: np.ndarray) -> bool:
    """A still with (almost) nothing in it: only the background and grid."""
    small = img[::8, ::8].astype(np.float32)
    return float(small.std()) < 9.0


def fix_local(plan: dict, i: int, problems: list[str]) -> list[str]:
    """Repair a shot's plan for the problems found. Returns what changed (in plain words)."""
    sc = plan["scenes"][i]
    cam = sc["camera"]
    done = []
    for p in problems:
        if p in ("target_too_small", "empty_picture", "mostly_empty"):
            cam["zoom"] = round(min(2.5, max(1.0, float(cam.get("zoom", 1.0))) * 1.4), 2)
            cam.pop("distance", None)
            if cam.get("move") in ("fly_over", "pull_out", "top_down", "reveal"):
                cam["move"] = "push_in"
            if p == "mostly_empty":  # a wide subject in a tall frame: look down more, so the place fills the picture
                cam["height"] = min(60.0, float(cam.get("height", 24.0)) + 14)
            done.append("camera closer")
        elif p == "cut_off":
            cam["zoom"] = round(max(0.5, min(1.0, float(cam.get("zoom", 1.0))) * 0.8), 2)
            cam.pop("distance", None)
            done.append("whole object in the safe area")
        elif p == "target_too_big":
            cam["zoom"] = round(max(0.2, float(cam.get("zoom", 1.0)) / 1.5), 2)
            done.append("camera further away")
        elif p.startswith("camera_inside") or p == "under_floor":
            cam["zoom"] = round(max(0.2, float(cam.get("zoom", 1.0)) / 1.6), 2)
            cam["height"] = min(70.0, float(cam.get("height", 24.0)) + 12)
            cam.pop("distance", None)
            done.append("camera moved out and up")
        elif p in ("target_off_screen", "target_behind"):
            cam["move"] = "orbit"
            for k in ("distance", "fov"):
                cam.pop(k, None)
            done.append("camera aimed at the subject again")
        elif p == "labels_overlap":
            sc["labels"] = sc["labels"][:2]
            if len(sc["labels"]) == 2:
                sc["labels"][1]["at"] = 0.55  # the second one comes later
            done.append("fewer labels")
        elif p.startswith("subject_blocked"):
            cam["angle"] = float(cam.get("angle", 25.0)) + 55.0
            done.append("camera moved round so nothing hides the subject")
        elif p == "label_off_screen":
            sc["labels"] = sc["labels"][:1]
            done.append("label kept on screen")
    return list(dict.fromkeys(done))


def _jpeg(img: np.ndarray, width: int = 384) -> bytes:
    from PIL import Image  # noqa: PLC0415

    im = Image.fromarray(img)
    h = int(im.height * width / im.width)
    buf = io.BytesIO()
    im.resize((width, h)).save(buf, "JPEG", quality=80)
    return buf.getvalue()


def ask_vision(stills: list[np.ndarray], texts: list[str], rep=None, batch: int = 8) -> dict[int, dict]:
    """Gemini looks at the stills. Returns {shot index: {"problem", "fix"}} for the bad ones ({} without a key)."""
    from .. import llm  # noqa: PLC0415

    bad: dict[int, dict] = {}
    if llm.gemini_busy():  # Gemini was busy a moment ago: don't wait on it again for an extra
        if rep is not None:
            rep.info("⏭️ Gemini is busy, so the picture check uses the local checks only.")
        return bad
    for a in range(0, len(stills), batch):
        idx = list(range(a, min(len(stills), a + batch)))
        text = "\n".join(f"Shot {k + 1}: {texts[k]}" for k in idx) + \
            f"\n\nThe {len(idx)} pictures below are shots {idx[0] + 1} to {idx[-1] + 1}, in order."
        reply = llm.vision_json(VISION_SYSTEM, text, [_jpeg(stills[k]) for k in idx], rep=rep)
        if reply is None:
            return bad  # no key or no answer: the local checks are enough
        for item in (reply.get("shots") if isinstance(reply, dict) else None) or []:
            try:
                n = int(item.get("n")) - 1
            except (TypeError, ValueError):
                continue
            if n in idx and item.get("ok") is False and str(item.get("fix") or "").strip():
                bad[n] = {"problem": str(item.get("problem") or "")[:120], "fix": str(item["fix"])[:160]}
    return bad


def check(plan: dict, make_world, render_still, texts: list[str], rep=None, use_ai: bool = True,
          rounds: int = 2) -> tuple[dict, list[str], list]:
    """Check every shot, fix what's broken. make_world(plan) → World; render_still(world, i) → image (HxWx3).

    Returns (plan, report lines, stills of the final plan)."""
    from . import fixer  # noqa: PLC0415

    plan = copy.deepcopy(plan)
    report: list[str] = []
    world = make_world(plan)
    stills = [render_still(world, i) for i in range(len(world.scenes))]
    for _ in range(rounds):
        changed = set()
        for i in range(len(world.scenes)):
            probs = local_problems(world, i, label_tex=getattr(world, "label_tex", None)) + logic_problems(world, i)
            if empty_picture(stills[i]):
                probs.append("empty_picture")
            fixes = fix_local(plan, i, probs)
            if fixes:
                changed.add(i)
                report.append(f"Shot {i + 1}: " + ", ".join(fixes))
        if not changed:
            break
        world = make_world(plan)
        for i in changed:
            stills[i] = render_still(world, i)
    if use_ai:
        import time  # noqa: PLC0415

        from .. import llm  # noqa: PLC0415

        bad = ask_vision(stills, texts, rep)
        changed = set()
        t0 = time.time()
        for i, info in sorted(bad.items()):
            try:  # the light Gemini model, at most 2 minutes, nothing when Gemini is busy
                plan, changes, _ = fixer.fix(plan, i, info["fix"], texts[i], rep, quick=True,
                                             use_ai=time.time() - t0 < 120 and not llm.gemini_busy())
            except ValueError:
                report.append(f"Shot {i + 1}: Gemini saw a problem ({info['problem'] or info['fix']}), "
                              "but I couldn't fix it automatically. Check it on step 2.")
                continue
            changed.add(i)
            report.append(f"Shot {i + 1} (Gemini: {info['problem'] or 'looked wrong'}): " + ", ".join(changes))
        if changed:
            from . import plan as P  # noqa: PLC0415

            plan, _ = P.validate(plan, texts)
            world = make_world(plan)
            for i in changed:
                stills[i] = render_still(world, i)
    return plan, report, stills



def logic_problems(world, i: int) -> list[str]:
    """Does shot i make sense? Pipes connected at both ends, moving tools touch what they move, nothing solid
    blocks the subject. (Floating things are grounded and loose pipes connected when the world is built.)"""
    from .logic import CONNECTORS, PUSHABLE  # noqa: PLC0415

    out = []
    sc = world.scenes[i]
    names = {a["target"].split(".")[0] for a in sc["plan"]["actions"]} | {sc["plan"]["camera"]["target"]}
    objs = {o["id"]: o for o in world.plan["objects"]}
    for oid in names:
        o = objs.get(oid)
        if o and o["asset"] in CONNECTORS and not (o.get("from") and o.get("to")):
            out.append(f"open_pipe:{oid}")
    for a in sc["plan"]["actions"]:
        oid = a["target"].split(".")[0]
        if a["do"] != "move" or oid not in world.groups:
            continue
        inst = world.groups[oid][0]
        if "blade" in inst.model.anchors:  # a pile right next to the blade's path that it misses = a logic mistake
            ev = next((e for e in world.events_of.get(oid, []) if e.do == "move" and e.scene == i), None)
            if ev is None:
                continue
            S = world.state(inst, ev.start)["pos"].astype(float)
            D = world._dest(inst, ev).astype(float)
            d = D - S
            d[1] = 0
            L = float(np.linalg.norm(d)) or 1.0
            u = d / L
            linked = {k for k, links in world.push.items() if any(x[0] is ev for x in links)}
            for p in world.insts:
                if p.asset not in PUSHABLE or p.oid.startswith("_env") or (p.oid, p.index) in linked:
                    continue
                rel = p.pos - S
                along, lateral = float(np.dot(rel, u)), abs(float(rel[0] * -u[2] + rel[2] * u[0]))
                if 0 < along < L and lateral < 1.6:
                    out.append(f"tool_not_touching:{oid}")
                    break
    T = sc["start"] + sc["dur"] * 0.6
    eye, tgt, fov, fade = world.camera(i, sc["dur"] * 0.6)
    iso = world.isolated(i) if hasattr(world, "isolated") else ""
    parents = {world.mounts[f][0].oid for f in world._focus[i] if f in getattr(world, "mounts", {})}
    if fade < 0.5 and iso not in ("hero", "macro", "subject"):  # isolated shots draw only the subject
        world._aim_i = i
        for inst in world.insts:
            if inst.oid.startswith("_env") or inst.oid in world._focus[i] or inst.asset in CONNECTORS:
                continue
            if inst.oid in parents:
                continue  # the thing it sits in (a car around its engine, a mine around its shelter): its parts in
                # the way are left out when the picture is drawn
            if any(p.shell for p in inst.model.parts):
                continue  # walls and roofs in the way are left out automatically
            st = world.state(inst, T)
            if st["vis"] > 0.5 and world._blocks(inst, st, eye, tgt):
                out.append(f"subject_blocked:{inst.oid}")
                break
    return out


# ---------------------------------------------------------------------------------------------------------------
# Brightness jumps (Part 14): no flash, pop or flicker between two frames, except at a hard cut
# ---------------------------------------------------------------------------------------------------------------
JUMP_LIMIT = 0.15  # a change of more than 15 % between two frames (whole picture or one ninth of it) is a jump


def luma_grid(img: np.ndarray, grid: int = 3) -> np.ndarray:
    """Mean brightness (0..1) of the whole frame and of a grid x grid split: (1 + grid*grid,)."""
    a = np.asarray(img, np.float32)
    lum = (a[..., 0] * 0.2126 + a[..., 1] * 0.7152 + a[..., 2] * 0.0722) / 255.0
    H, W = lum.shape
    cells = [lum[H * y // grid:H * (y + 1) // grid, W * x // grid:W * (x + 1) // grid].mean()
             for y in range(grid) for x in range(grid)]
    return np.array([lum.mean(), *cells], np.float32)


def cut_times(world) -> list[float]:
    """Where the picture is ALLOWED to change at once: hard cuts and jumps into/out of the micro world."""
    out = []
    for i in range(1, len(world.scenes)):
        prev, cur = world._cams[i - 1], world._cams[i]
        if cur["cut"] or prev["move"] == "zoom_into" or prev["micro"] != cur["micro"]:
            out.append(float(world.scenes[i]["start"]))
    return out


def brightness_jumps(lumas: np.ndarray, fps: float, cuts: list[float], limit: float = JUMP_LIMIT,
                     held: np.ndarray | None = None) -> list[dict]:
    """Problems between frames (a hard cut, ±1 frame, may change everything):
    * jump: the whole picture gets brighter/darker by more than `limit` from one frame to the next;
    * pop: with the camera held still (`held[k]` = frame k filmed from frame k-1's camera), one ninth of the picture
      changes by more than `limit`: a flash, a part popping in/out, a colour snapping. Camera moves don't count;
    * strobe: one ninth of the picture flickers up and down 4+ times within a second (steps over 6 %), measured
      with the camera held still when `held` is given (a fence sliding past is motion, not flicker).
    Returns [{t, kind, change}]."""
    L = np.asarray(lumas, np.float32)
    n = len(L)
    if n < 3:
        return []
    near_cut = np.zeros(n, bool)
    for c in cuts:
        k = int(round(c * fps))
        near_cut[max(0, k - 1):min(n, k + 2)] = True
    d = L[1:] - L[:-1]  # change into frame k+1
    rel = np.abs(d) / np.maximum(np.maximum(L[1:], L[:-1]), 0.08)
    out = []
    for k in range(1, n):
        if near_cut[k] or near_cut[k - 1]:
            continue
        t = round(k / fps, 3)
        if rel[k - 1, 0] > limit:
            out.append({"t": t, "kind": "jump", "change": round(float(rel[k - 1, 0]), 3)})
            continue
        if held is not None:
            h = np.abs(held[k] - L[k - 1]) / np.maximum(np.maximum(held[k], L[k - 1]), 0.08)
            if float(h.max()) > limit:
                out.append({"t": t, "kind": "pop", "change": round(float(h.max()), 3)})
    win = int(round(fps))
    if held is not None:  # strobing is the world blinking (lights, glows), not the camera passing a fence
        d = np.asarray(held, np.float32)[1:] - L[:-1]
        rel = np.abs(d) / np.maximum(np.maximum(np.asarray(held, np.float32)[1:], L[:-1]), 0.08)
    for c in range(L.shape[1]):  # strobing: many quick up/down steps in one second
        steps = np.where(rel[:, c] > 0.06, np.sign(d[:, c]), 0.0)
        for k0 in range(0, n - 1 - win, win // 2):
            seg = steps[k0:k0 + win]
            seg = seg[seg != 0]
            if len(seg) >= 5 and int(np.sum(seg[1:] != seg[:-1])) >= 4 and not near_cut[k0:k0 + win + 1].any():
                out.append({"t": round(k0 / fps, 3), "kind": "strobe", "change": round(float(rel[k0:k0 + win, c].max()), 3)})
                break
    out.sort(key=lambda x: x["t"])
    return out


def scan_video(world, renderer, fps: float = 30.0, t0: float = 0.0, t1: float | None = None) -> tuple:
    """Every frame of [t0, t1) drawn (small is fine), plus the same moment filmed from the previous frame's camera.
    Returns (luma grids, held luma grids) for brightness_jumps. Labels are left out (they are overlays)."""
    t1 = world.total if t1 is None else t1
    n = int(round((t1 - t0) * fps))
    L, held, prev = [], [], None
    for k in range(n):
        T = t0 + k / fps
        cam = world.camera_at(T)
        L.append(luma_grid(renderer.render(world.frame(T, cam=cam))))
        held.append(luma_grid(renderer.render(world.frame(T, cam=prev))) if prev is not None else L[-1])
        prev = cam
    return np.stack(L), np.stack(held)
