"""Write docs/PLAN_CHEATSHEET.md from the real library (exact part names), so it never goes stale.

    python -m storyforge.world.cheatsheet
"""

from __future__ import annotations

import json
from pathlib import Path

EXAMPLE = {
    "title": "How a toilet flushes", "preset": "studio",
    "areas": [{"id": "bath", "setting": "bathroom"}, {"id": "compare", "setting": "table"}],
    "objects": [{"id": "wc1", "asset": "toilet", "area": "bath", "pos": [0, 0]},
                {"id": "bottle1", "asset": "bottle", "area": "compare", "pos": [-0.1, 0]},
                {"id": "glass1", "asset": "shot_glass", "area": "compare", "pos": [0.1, 0]}],
    "scenes": [
        {"camera": {"move": "close_up", "target": "wc1.handle"},
         "actions": [{"do": "open", "target": "wc1.flapper", "at": "press"}], "labels": [], "keywords": []},
        {"camera": {"move": "hero", "target": "wc1.flapper"}, "actions": [{"do": "drain", "target": "wc1.tank_water",
                                                                           "at": "rushes"}],
         "labels": [{"target": "wc1.flapper", "text": "flapper", "kind": "part", "at": "flapper"}],
         "keywords": [{"text": "6 LITERS", "kind": "number", "at": "six"}]},
        {"camera": {"move": "push_in", "target": "bottle1"}, "cut": True, "actions": [], "labels": [],
         "keywords": [{"text": "4 BOTTLES", "kind": "wow", "at": "bottles"}]},
    ]}


def build() -> str:
    from . import assets, plan as P, presets, settings  # noqa: PLC0415

    lines = ["# 📋 Scene plan cheatsheet", "",
             "Write a plan by hand (📋 Paste plan in the app, or `python -m storyforge.make --plan`). Every plan is "
             "checked and repaired (closest names, real sizes, missing targets). Use the EXACT part names below for "
             "`obj.part` (camera targets, actions, labels, mounts). Regenerate: `python -m storyforge.world.cheatsheet`.",
             "", "## Plan shape", "", "```", P.schema_text(), "```", "",
             "Areas: `{id, setting, look?, micro?}`. Settings: " + ", ".join(settings.SETTINGS) + ".",
             "Presets (whole world): " + ", ".join(presets.PRESETS) + ". Looks (area or shot): " +
             ", ".join(presets.LOOKS) + ".", "",
             "## Camera moves", ""]
    lines += [f"- `{k}`: {v}" for k, v in P.CAMERA_MOVES.items()]
    lines += ["", "## Actions (`at`: a spoken word, 0-1 of the shot, or seconds)", ""]
    lines += ["; ".join(f"`{k}` {v.split('(')[0].split(':')[0].strip()}" for k, v in list(P.ACTIONS.items())[i:i + 4])
              for i in range(0, len(P.ACTIONS), 4)]
    lines += ["", "Label / keyword kinds: " + ", ".join(f"`{k}` ({v})" for k, v in P.KINDS.items()) +
              ". Keywords: 0-1 per shot, only for a wow fact.", "", "## Machines: real part names, ports, paths", ""]
    simple = []
    for info in sorted(assets.REGISTRY.values(), key=lambda i: i.name):
        if "set" in info.tags:
            continue
        names, anchors, paths = assets.part_list(info.name) if {"machine", "cutaway"} & set(info.tags) else ([], [], [])
        if names:
            extra = (f" · ports: {', '.join(anchors[:10])}" if anchors else "") + \
                    (f" · paths: {', '.join(paths)}" if paths else "")
            lines.append(f"- **{info.name}**: {', '.join(names[:28])}{extra}")
        else:
            simple.append(info.name + (f" ({assets.REAL_SIZE[info.name]} m)" if info.name in assets.REAL_SIZE else ""))
    lines += ["", "## Other assets", ""]
    row = []
    for name in simple:
        row.append(name)
        if sum(len(x) + 2 for x in row) > 110:
            lines.append(", ".join(row))
            row = []
    if row:
        lines.append(", ".join(row))
    lines += ["", "## Small example", "", "```json", json.dumps(EXAMPLE, indent=None), "```", ""]
    return "\n".join(lines)


def write(path: Path | None = None) -> Path:
    path = Path(path or Path(__file__).resolve().parents[2] / "docs" / "PLAN_CHEATSHEET.md")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(), encoding="utf-8")
    return path


if __name__ == "__main__":
    p = write()
    print(f"{p} ({len(p.read_text(encoding='utf-8').splitlines())} lines)")
