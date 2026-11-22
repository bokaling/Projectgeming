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

VISION_SYSTEM = """You check still frames of a low poly 3D "how it works" explainer video (dark teal studio, glowing grid floor).
For each shot you get the narration and one still frame from the middle of the shot.
A shot is NOT ok only if something is clearly broken: the main object is missing or cut off, the camera is inside an
object or wall, the frame is empty or almost empty, labels overlap, or the picture clearly doesn't fit the narration.
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
    lo, hi = world.group_box(spec["target"], T)
    corners = np.array([[x, y, z] for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    pts = project_points(eye, tgt, fov, (W, H), corners)
    front = pts[pts[:, 2] > 0.05]
    if len(front) < 4:
        out.append("target_behind")
    else:
        x0, x1 = front[:, 0].min(), front[:, 0].max()
        y0, y1 = front[:, 1].min(), front[:, 1].max()
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        if not (0.0 < cx < W and 0.0 < cy < H):
            out.append("target_off_screen")
        size = max((x1 - x0) / W, (y1 - y0) / H)  # how much of the frame the subject fills
        if size < 0.22 and spec["move"] not in ("fly_over", "pull_out", "reveal"):
            out.append("target_too_small")
        if (x1 - x0) > W * 2.6 and (y1 - y0) > H * 2.6 and spec["move"] not in ("zoom_into", "close_up"):
            out.append("target_too_big")
    for inst in world.insts:  # the camera inside something solid
        st = world.state(inst, T)
        if st["vis"] < 0.5 or st["cut"] > 0 or st["xray"]:
            continue
        if not any(p.opacity > 0.9 and not p.shell for p in inst.model.parts):
            continue
        s = inst.scale * st["scale"]
        a, b = st["pos"] + inst.lo * s, st["pos"] + inst.hi * s
        if np.all(np.asarray(eye) > a + 0.05) and np.all(np.asarray(eye) < b - 0.05):
            if spec["move"] != "zoom_into":
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
        if p in ("target_too_small", "empty_picture"):
            cam["zoom"] = round(min(5.0, float(cam.get("zoom", 1.0)) * 1.5), 2)
            cam.pop("distance", None)
            done.append("camera closer")
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
            probs = local_problems(world, i, label_tex=getattr(world, "label_tex", None))
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
        bad = ask_vision(stills, texts, rep)
        changed = set()
        for i, info in sorted(bad.items()):
            try:
                plan, changes, _ = fixer.fix(plan, i, info["fix"], texts[i], rep)
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

