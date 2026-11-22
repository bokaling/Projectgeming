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
    "studio": dict(background="#0b2a30", horizon="#13414a", floor="#0e3238", grid="#2ee6d6", sky="#a8e4ec",
                   ground_light="#24474d", sun="#fff4e0", base="#6d7377", pad="concrete",
                   props=["barrel", "crate", "bucket"], air=None),
    "farm": dict(background="#0b2a30", horizon="#13414a", floor="#0e3238", grid="#2ee6d6", sky="#b8e6ec",
                 ground_light="#3b4d35", sun="#fff1d6", base="#5f7a4c", pad="dirt",
                 props=["hay_bale", "bucket", "hay_bale", "crate"], air=None),
    "city": dict(background="#1b2433", horizon="#3a4a63", floor="#262c35", grid="#5ad1ff", sky="#c9dcf0",
                 ground_light="#3a3f48", sun="#fff3e0", base="#4e545c", pad="concrete",
                 props=["car", "lamp_post", "bus", "car"], air=None),
    "house_interior": dict(background="#2a2230", horizon="#4a3b47", floor="#3a2d2a", grid=None, sky="#ffe8cf",
                           ground_light="#5a4335", sun="#ffe2b8", base="#9c7a55", pad="#b38a5e",
                           props=["laptop", "bottle", "phone", "bucket"], air=None),
    "factory": dict(background="#1d2228", horizon="#3a434d", floor="#22272d", grid="#f5a524", sky="#d6dee6",
                    ground_light="#3d434a", sun="#fff4e0", base="#5b6066", pad="concrete",
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
    "forest": dict(background="#16301f", horizon="#3e6b45", floor="#22402a", grid=None, sky="#d8f0c8",
                   ground_light="#3a5a33", sun="#fff4d6", base="#4f7a3a", pad="dirt",
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
    "highway": dict(background="#1d2633", horizon="#45577a", floor="#262c35", grid=None, sky="#d6e4f5",
                    ground_light="#3a3f48", sun="#fff3e0", base="#3f4347", pad="gravel",
                    props=["car", "lamp_post", "bus", "car"], air=None),
    "school": dict(background="#263241", horizon="#4b5f78", floor="#2d3846", grid=None, sky="#fff4e2",
                   ground_light="#5a4a3a", sun="#ffeccc", base="#c9a87a", pad="#d6b88c",
                   props=["laptop", "bucket", "bottle"], air=None),
    "office": dict(background="#222c38", horizon="#46566a", floor="#2a3340", grid=None, sky="#f0f4ff",
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
    (r"\b(space|rocket|orbit|satellite|astronaut|galaxy|star)\b", "space"),
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


def style_of(preset: str) -> dict:
    """Renderer colours for a preset (gl.STYLE keys)."""
    p = PRESETS.get(preset) or PRESETS["studio"]
    keys = ("background", "horizon", "floor", "sky", "ground_light", "sun")
    out = {k: p[k] for k in keys}
    out["grid"] = p["grid"] or "#000000"  # black lines add nothing: no grid
    if p.get("natural") and p.get("base"):
        out["floor"] = p["base"]
    return out
