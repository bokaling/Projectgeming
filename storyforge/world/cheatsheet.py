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


def _wrap(head: str, items: list[str], width: int) -> list[str]:
    """Items joined with commas, a new line when one gets longer than width (the first line starts with head)."""
    out, row = [], head
    for x in items:
        if len(row) + len(x) > width and row.strip() != head.strip():
            out.append(row.rstrip(", "))
            row = "  "
        row += x + ", "
    out.append(row.rstrip(", "))
    return out


def build() -> str:
    from . import assets, kit, plan as P, presets, settings  # noqa: PLC0415

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
              ". Keywords: 0-1 per shot, only for a wow fact.", "",
              "## Mechanism kit (in a new object's recipe: {\"kit\": piece, \"name\", \"pos\", \"size\", \"axis\": "
              "x/y/z/-x/-y/-z}; also objects kit_<piece>)", "", ", ".join(kit.KIT), "",
              "## Machines: real part names, ports, paths", ""]
    from . import cad, imported  # noqa: PLC0415

    simple = []
    for info in sorted(assets.REGISTRY.values(), key=lambda i: i.name):
        if "set" in info.tags or "kit" in info.tags or "imported" in info.tags:
            continue
        names, anchors, paths = assets.part_list(info.name) if {"machine", "cutaway"} & set(info.tags) else ([], [], [])
        if names:
            extra = (f" · ports: {', '.join(anchors[:10])}" if anchors else "") + \
                    (f" · paths: {', '.join(paths)}" if paths else "")
            lines.append(f"- **{info.name}**: {', '.join(names)}{extra}")
        else:
            simple.append(info.name + (f" ({assets.REAL_SIZE[info.name]} m)" if info.name in assets.REAL_SIZE else ""))
    lines += ["", "## Free CC0 models (ready-made everyday things: use them by name; files load once from Drive)", ""]
    where: dict[str, list[str]] = {}
    for it in imported.CATALOG:
        where.setdefault(it.place, []).append(f"`{it.name}` {it.size[1]} m")
    for place, items in where.items():
        lines += _wrap(f"On the {place}: ", items, 150)
    lines += ["", "Licenses: LICENSES/assets.md (all CC0). Other CC0 packs copied to Drive library/models/<pack>/ "
              "become `<pack>_<file>`.", "",
              "## CAD shapes for new objects' recipes (a part with \"cad\": shape; build123d + bd_warehouse)", ""]
    lines += [f"- `{k}`: {v}" for k, v in cad.SHAPES.items()]
    lines += ["- modifiers: " + cad.MODIFIERS]
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
