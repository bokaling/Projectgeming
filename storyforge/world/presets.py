"""World presets: the kind of place a video happens in (its ground, props, light, background and air).

The plan names a preset ("preset": "ocean"); without one it is guessed from the words of the script.
Each preset sets the renderer colours (background gradient, floor, grid or no grid, sky and sun light),
the ground under the site, the pads and props of the set dressing, and ambient particles in the air.
"""

from __future__ import annotations

import re

# colours: background (top), horizon (bottom of the sky), floor (far ground), grid (None = no grid),
# sky / ground_light (soft light from above / below), sun; base = ground under the site (None = no ground: space);
# natural = open ground (sand, sea floor, flesh…): no pads, ground plate, roads or pipe stands, the floor IS the ground
PRESETS = {
    "studio": dict(background="#cfd9e1", horizon="#f3f6f8", floor="#e4e9ed", grid=None, sky="#ffffff",
                   ground_light="#b9c4cc", sun="#fff6ea", base="#d5dce1", pad="concrete", look="studio_light",
                   props=["barrel", "crate", "bucket"], air=None),
    "farm": dict(background="#4f9be0", horizon="#d4ebf8", floor="#76b957", grid=None, sky="#d6ecff",
                 ground_light="#5f7f4c", sun="#fff3dc", base="#76b957", pad="dirt", look="outdoor_day",
                 props=["hay_bale", "bucket", "hay_bale", "crate"], air=None),
    "city": dict(background="#4f9be0", horizon="#d4ebf8", floor="#8a9198", grid=None, sky="#d6ecff",
                 ground_light="#6b7178", sun="#fff3dc", base="#7d858c", pad="concrete", look="outdoor_day",
                 props=["car", "lamp_post", "bus", "car"], air=None),
    "house_interior": dict(background="#c9bfb4", horizon="#f3ede6", floor="#d8cbbb", grid=None, sky="#ffe8cf",
                           ground_light="#5a4335", sun="#ffe2b8", base="#9c7a55", pad="#b38a5e",
                           props=["laptop", "bottle", "phone", "bucket"], air=None),
    "factory": dict(background="#9aa7b1", horizon="#dfe5e9", floor="#a8afb5", grid=None, sky="#f2f5f7",
                    ground_light="#8a939a", sun="#fff4e0", base="#9aa1a7", pad="concrete",
                    props=["barrel", "crate", "railing", "barrel"], air=None),
    "lab": dict(background="#a9c3d1", horizon="#e3eef3", floor="#cfdde4", grid="#7fb6d0", sky="#ffffff",
                ground_light="#b9c6cc", sun="#ffffff", base="#dfe8ec", pad="#eef3f5",
                props=["beaker", "glass_box", "laptop", "beaker"], air=None),
    "hospital": dict(background="#a7c9d6", horizon="#e6f2f5", floor="#d5e6ea", grid=None, sky="#ffffff",
                     ground_light="#c0d0d4", sun="#ffffff", base="#e6eff1", pad="#f3f7f8",
                     props=["glass_box", "beaker", "laptop"], air=None),
    "space": dict(background="#03040c", horizon="#0b1236", floor="#03040c", grid=None, sky="#9fb4ff",
                  ground_light="#1a1f3a", sun="#fff8e8", base=None, pad=None, props=[], air="stars"),
    "planet_surface": dict(background="#2b0f12", horizon="#8a3b22", floor="#5a2416", grid=None, sky="#ffc9a8",
                           ground_light="#6b3020", sun="#ffe0c0", base="#a5502f", pad="#b9643c",
                           props=["rock", "crystal", "rock"], air="dust", people=[], fence=None, lamps=False, natural=True),
    "ocean": dict(background="#022a40", horizon="#0a5b7a", floor="#0b3d52", grid=None, sky="#8fdcff",
                  ground_light="#1d5566", sun="#d8f6ff", base="#b9a06a", pad="#c8b27c",
                  props=["rock", "grass_patch", "rock", "fish"], air="bubbles", fog=0.45, people=[], fence=None, lamps=False, natural=True),
    "body": dict(background="#2a0710", horizon="#6e1a2c", floor="#4a1020", grid=None, sky="#ffc2cc",
                 ground_light="#6b2233", sun="#ffe0e4", base="#a63d55", pad="#b9506a",
                 props=["blood_cell", "blood_cell", "cell"], air="cells", fog=0.55, people=[], fence=None, lamps=False, natural=True),
    "desert": dict(background="#c97a45", horizon="#f0c88a", floor="#cfa468", grid=None, sky="#ead6b4",
                   ground_light="#977048", sun="#ffe9c0", base="#cfa86a", pad="#d8b47a",
                   props=["rock", "rock", "crate"], air="dust", fence=None, lamps=False, natural=True),
    "forest": dict(background="#4f9be0", horizon="#d4ebf8", floor="#5f9e45", grid=None, sky="#d8f0c8",
                   ground_light="#4d6e3e", sun="#fff4d6", base="#5f9e45", pad="dirt", look="outdoor_day",
                   props=["tree", "rock", "grass_patch", "tree"], air=None, lamps=False, natural=True),
    "snow": dict(background="#7f9bb3", horizon="#e3edf5", floor="#c9d8e4", grid=None, sky="#ffffff",
                 ground_light="#b8c8d6", sun="#ffffff", base="#f2f6f9", pad="#e6eef4",
                 props=["tree", "rock", "tree"], air="snow", lamps=False, natural=True),
    "ancient": dict(background="#b9713d", horizon="#f0c88a", floor="#c99d62", grid=None, sky="#e6cfa8",
                    ground_light="#8f6a42", sun="#ffe6b8", base="#c79e62", pad="#d2ad72",
                    props=["stone_block", "rock", "stone_block", "palm_tree"], air="dust", fence=None, lamps=False,
                    people=[{"shirt": "#efe6d2", "pants": "#efe6d2", "hair": "#2a1f18"},
                            {"shirt": "#d9c9a3", "pants": "#8a5a2e", "hair": "#1d1612"}], natural=True),
    "battlefield": dict(background="#34322d", horizon="#6b6457", floor="#3f3a32", grid=None, sky="#d8d0c0",
                        ground_light="#4a4236", sun="#ffe6c8", base="#6b5a43", pad="dirt",
                        props=["crate", "barrel", "rock", "smoke_cloud"], air="dust", natural=True),
    "highway": dict(background="#4f9be0", horizon="#d4ebf8", floor="#76b957", grid=None, sky="#d6ecff",
                    ground_light="#5f7f4c", sun="#fff3dc", base="#76b957", pad="gravel", look="outdoor_day",
                    props=["car", "lamp_post", "bus", "car"], air=None),
    "school": dict(background="#b9c7d3", horizon="#eef2f5", floor="#d9cdb8", grid=None, sky="#fff4e2",
                   ground_light="#5a4a3a", sun="#ffeccc", base="#c9a87a", pad="#d6b88c",
                   props=["laptop", "bucket", "bottle"], air=None),
    "office": dict(background="#b9c4ce", horizon="#eef1f4", floor="#c9ced3", grid=None, sky="#f0f4ff",
                   ground_light="#4a5260", sun="#fff6e8", base="#8b8f96", pad="#a2a7ae",
                   props=["laptop", "phone", "glass_box"], air=None),
}
ALIASES = {"interior": "house_interior", "home": "house_interior", "kitchen": "house_interior", "underwater": "ocean",
           "sea": "ocean", "human_body": "body", "inside_the_body": "body", "mars": "planet_surface",
           "moon": "planet_surface", "egypt": "ancient", "rome": "ancient", "war": "battlefield", "road": "highway",
           "classroom": "school", "industry": "factory", "laboratory": "lab", "default": "studio"}
KEYWORDS = [  # (pattern, preset): checked on the title and scene texts, the first match wins
    (r"\b(submarine|ocean|sea|underwater|whale|shark|coral|deep sea|diver|fish)\b", "ocean"),
    (r"\b(body|blood|stomach|intestine|liver|pancreas|insulin|cell|heart|brain|sugar)\b", "body"),
    (r"\b(pyramid|pharaoh|egypt|roman|rome|ancient|temple|colosseum)\b", "ancient"),
    (r"\b(outer space|into space|in space|space station|spacecraft|spaceship|rocket|orbit|satellite|astronaut|galaxy|"
     r"star)\b", "space"),  # not "a tiny space" inside an engine
    (r"\b(mars|moon surface|planet surface|crater)\b", "planet_surface"),
    (r"\b(desert|sand|dune|camel)\b", "desert"),
    (r"\b(snow|ice|arctic|glacier|polar)\b", "snow"),
    (r"\b(forest|jungle|tree|wood|rainforest)\b", "forest"),
    (r"\b(war|battle|soldier|tank battle|army|cannon)\b", "battlefield"),
    (r"\b(hospital|doctor|surgery|patient|vaccine)\b", "hospital"),
    (r"\b(lab|laboratory|chemistry|experiment|molecule|atom)\b", "lab"),
    (r"\b(factory|assembly|manufactur|plant|steel|mill)\b", "factory"),
    (r"\b(highway|traffic|road|car crash|motorway)\b", "highway"),
    (r"\b(school|classroom|student|teacher)\b", "school"),
    (r"\b(office|meeting|computer|email)\b", "office"),
    (r"\b(kitchen|house|home|fridge|microwave|toilet)\b", "house_interior"),
    (r"\b(city|street|building|skyscraper|subway)\b", "city"),
    (r"\b(farm|cow|barn|tractor|manure|crop)\b", "farm"),
]


def resolve(name) -> str:
    key = re.sub(r"[^a-z_]+", "_", str(name or "").lower()).strip("_")
    key = ALIASES.get(key, key)
    return key if key in PRESETS else ""


def guess(texts: list[str]) -> str:
    """The preset whose words come up most often (ties: the earlier rule), else the studio look."""
    text = " ".join(texts).lower()
    best, hits = "studio", 0
    for pattern, preset in KEYWORDS:
        n = len(re.findall(pattern[:-3] + r")(?:s|es)?\b", text))  # plurals count too ("cows")
        if n > hits:
            best, hits = preset, n
    return best


# Looks a single shot (or area) can have, whatever the world preset is (renderer colours + post effects).
# sky=1: a real sky (blue gradient by view direction, soft clouds); env=False: only the subject is drawn;
# grade: the colour grading (gl.GRADES); dof: depth of field strength (close-ups).
LOOKS = {
    "studio_light": dict(background="#cfd9e1", horizon="#f3f6f8", floor="#e4e9ed", grid="#000000", sky="#ffffff",
                         ground_light="#b9c4cc", sun="#fff6ea", fog=1.0, sky_mode=0, grade="bright"),
    "outdoor_day": dict(background="#3f8fdc", horizon="#d4ebf8", floor="#76b957", grid="#000000", sky="#d6ecff",
                        ground_light="#5f7f4c", sun="#fff3dc", fog=1.6, sky_mode=1, grade="bright"),
    "macro_dark": dict(background="#040608", horizon="#0c1116", floor="#07090c", grid="#000000", sky="#7a8898",
                       ground_light="#0d1115", sun="#ffe6c8", fog=0.8, sky_mode=0, grade="dark", dof=1.0, env=False),
    "documentary": dict(background="#07090d", horizon="#1a2027", floor="#15181c", grid="#000000", sky="#8796a8",
                        ground_light="#1c1a18", sun="#ffd9a8", fog=0.75, sky_mode=0, grade="documentary"),
    "underwater": dict(background="#022a40", horizon="#0a5b7a", floor="#0b3d52", grid="#000000", sky="#8fdcff",
                       ground_light="#1d5566", sun="#d8f6ff", fog=0.45, sky_mode=0, grade="underwater"),
    "space": dict(background="#03040c", horizon="#0b1236", floor="#03040c", grid="#000000", sky="#9fb4ff",
                  ground_light="#1a1f3a", sun="#fff8e8", fog=1.0, sky_mode=0, grade="space"),
}
LOOK_ALIASES = {"light": "studio_light", "studio": "studio_light", "clean": "studio_light", "white": "studio_light",
                "outdoor": "outdoor_day", "outdoors": "outdoor_day", "day": "outdoor_day", "sunny": "outdoor_day",
                "macro": "macro_dark", "dark": "macro_dark", "cinematic": "documentary", "ocean": "underwater"}
OUTDOOR_SETTINGS = {"street", "outdoors", "farm", "site", "town"}
GRADE_OF = {"ocean": "underwater", "space": "space", "planet_surface": "space", "body": "dark", "battlefield": "documentary"}


def look(name) -> str:
    n = str(name or "").strip().lower().replace(" ", "_")
    n = LOOK_ALIASES.get(n, n)
    return n if n in LOOKS else ""


def style_of(preset: str) -> dict:
    """Renderer colours for a preset (gl.STYLE keys)."""
    p = PRESETS.get(preset) or PRESETS["studio"]
    keys = ("background", "horizon", "floor", "sky", "ground_light", "sun")
    out = {k: p[k] for k in keys}
    out["grid"] = p["grid"] or "#000000"  # black lines add nothing: no grid
    if p.get("natural") and p.get("base"):
        out["floor"] = p["base"]
    if p.get("look") in LOOKS:
        out["sky_mode"] = LOOKS[p["look"]].get("sky_mode", 0)
    out["grade"] = GRADE_OF.get(preset, "bright")
    return out
