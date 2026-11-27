"""Free ready-made low poly models (CC0 only): everyday things are loaded, machines are still built by us.

Packs (all CC0 1.0: free for commercial use, no credit needed; listed in LICENSES/assets.md):
* KayKit (Kay Lousberg) on GitHub: Furniture Bits, Restaurant Bits (a whole kitchen + food), City Builder Bits.
* Kenney on GitHub (starter kits): small buildings, trees, trucks, a motorcycle.
* Kenney zips from kenney.nl, Quaternius packs and Poly Haven models: any pack folder you (or `fetch_url`/
  `fetch_polyhaven` on Colab) put in `StoryForge/library/models/<pack>/` with a LICENSE that says CC0 is read too
  (`scan_folders`): every model in it becomes an object `<pack>_<file name>`.

Things that need cutaways and moving insides (engines, elevators, fridges with a compressor) stay our own machines.

How a model is made to fit our look (`to_model`): the pack's palette texture is sampled once per triangle (flat
colours, like the rest of the library), triangles of one colour become one part, colours are pulled a little toward
our palette, metal-looking greys get the metal material, the model stands on y = 0 centred on x/z and is scaled to its
real size, front = +z (our machines' front). Files are downloaded once and kept on Drive (library/models), so the
next session needs no network. Without the files (no network, tests) the old procedural object is used instead.
"""

from __future__ import annotations

import base64
import json
import re
import struct
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from . import mesh as M

GITHUB_RAW = "https://raw.githubusercontent.com/{repo}/{ref}/{path}"
CC0 = "CC0 1.0 Universal (public domain): free for commercial use, no attribution required"

PACKS = {
    "kaykit_furniture": {"repo": "KayKit-Game-Assets/KayKit-Furniture-Bits-1.0", "ref": "main",
                         "dir": "addons/kaykit_furniture_bits/Assets/gltf", "author": "Kay Lousberg (KayKit)",
                         "home": "https://kaylousberg.itch.io/furniture-bits"},
    "kaykit_restaurant": {"repo": "KayKit-Game-Assets/KayKit-Restaurant-Bits-1.0", "ref": "main",
                          "dir": "addons/kaykit_restaurant_bits/Assets/gltf", "author": "Kay Lousberg (KayKit)",
                          "home": "https://kaylousberg.itch.io/restaurant-bits"},
    "kaykit_city": {"repo": "KayKit-Game-Assets/KayKit-City-Builder-Bits-1.0", "ref": "main",
                    "dir": "addons/kaykit_city_builder_bits/Assets/gltf", "author": "Kay Lousberg (KayKit)",
                    "home": "https://kaylousberg.itch.io/city-builder-bits"},
    "kenney_city": {"repo": "KenneyNL/Starter-Kit-City-Builder", "ref": "main", "dir": "models",
                    "author": "Kenney (kenney.nl)", "home": "https://github.com/KenneyNL/Starter-Kit-City-Builder"},
    "kenney_racing": {"repo": "KenneyNL/Starter-Kit-Racing", "ref": "main", "dir": "models",
                      "author": "Kenney (kenney.nl)", "home": "https://github.com/KenneyNL/Starter-Kit-Racing"},
}


@dataclass
class Item:
    """One curated model: our name, where it comes from, its real size and how the planner finds it."""
    name: str
    pack: str
    file: str
    about: str
    size: tuple  # ("h", 0.9) = 0.9 m tall, ("l", 4.4) = 4.4 m long (longest side on the ground), ("w", 2.0) = wide
    tags: list = field(default_factory=list)
    aliases: list = field(default_factory=list)
    place: str = "floor"  # floor, counter (on a worktop), wall (against a wall), table, street
    replaces: str = ""  # an old procedural object this one stands in for (same name, old one = fallback)
    dims: tuple = ()  # real (width x, height y, depth z) in m: toy proportions are pulled toward it
    fit: float = 0.3  # how far (±) each axis may be stretched toward `dims`


def _i(name, pack, file, about, size, tags=(), aliases=(), place="floor", replaces="", dims=(), fit=0.3):
    return Item(name, pack, file, about, size, list(tags), list(aliases), place, replaces, tuple(dims), fit)


F, R, CI, KC, KR = "kaykit_furniture", "kaykit_restaurant", "kaykit_city", "kenney_city", "kenney_racing"
CATALOG = [
    # living room, bedroom, office
    _i("sofa", F, "couch_pillows.gltf", "a sofa with cushions", ("l", 2.1), ["furniture", "home"], ["couch", "settee"],
       "wall", replaces="sofa"),
    _i("armchair", F, "armchair_pillows.gltf", "an armchair", ("h", 0.95), ["furniture", "home"], ["easy_chair"]),
    _i("chair", F, "chair_A.gltf", "a chair", ("h", 0.95), ["furniture", "home", "office"], ["chairs"]),
    _i("footstool", F, "chair_stool.gltf", "a footstool", ("w", 0.5), ["furniture"], ["ottoman"]),
    _i("bed", F, "bed_double_A.gltf", "a double bed", ("l", 2.1), ["furniture", "home"], ["double_bed"], "wall"),
    _i("dining_table", F, "table_medium_long.gltf", "a dining table", ("l", 1.8), ["furniture", "home"],
       ["dinner_table"], dims=(1.8, 0.75, 1.0)),
    _i("coffee_table", F, "table_low.gltf", "a low coffee table", ("l", 1.1), ["furniture", "home"], [], dims=(1.1, 0.42, 0.6)),
    _i("bookshelf", F, "shelf_B_large_decorated.gltf", "a bookshelf with books", ("l", 1.8), ["furniture", "home",
       "office"], ["bookcase", "books_shelf"], "wall", dims=(1.8, 1.2, 0.4)),
    _i("cabinet", F, "cabinet_medium_decorated.gltf", "a cabinet with drawers", ("h", 0.9), ["furniture", "home"],
       ["dresser"], "wall"),
    _i("floor_lamp", F, "lamp_standing.gltf", "a standing lamp", ("h", 1.6), ["furniture", "home", "light"],
       ["standing_lamp"]),
    _i("table_lamp", F, "lamp_table.gltf", "a table lamp", ("h", 0.45), ["furniture", "home", "light"], ["desk_lamp"],
       "table"),
    _i("cactus", F, "cactus_medium_A.gltf", "a cactus in a pot", ("h", 0.6), ["plant", "home"], ["cacti"]),
    _i("rug", F, "rug_rectangle_stripes_A.gltf", "a striped rug", ("l", 2.0), ["home"], ["carpet_rug"]),
    _i("picture_frame", F, "pictureframe_large_A.gltf", "a framed picture", ("h", 0.7), ["home"], ["picture"], "wall"),
    _i("books", F, "book_set.gltf", "a row of books", ("h", 0.25), ["home", "school"], [], "table"),
    # kitchen (KayKit Restaurant Bits)
    _i("stove", R, "stove_single.gltf", "a kitchen stove with an oven", ("h", 0.92), ["kitchen", "appliance"],
       ["cooker", "kitchen_stove"], "wall", dims=(0.62, 0.92, 0.62), fit=0.55),
    _i("oven", R, "oven.gltf", "an oven", ("h", 0.92), ["kitchen", "appliance"], ["baking_oven"], "wall", dims=(0.6, 0.92, 0.62), fit=0.4),
    _i("kitchen_cabinet", R, "kitchencabinet.gltf", "a wall cabinet", ("h", 0.7), ["kitchen"], ["wall_cabinet"],
       "wall"),
    _i("worktop", R, "kitchencounter_straight_A_backsplash.gltf", "a kitchen counter with drawers", ("h", 0.92),
       ["kitchen"], ["countertop", "counter_top"], "wall", dims=(1.0, 0.92, 0.62), fit=0.5),
    _i("kitchen_sink", R, "kitchencounter_sink_backsplash.gltf", "a kitchen counter with a sink", ("h", 0.92),
       ["kitchen"], ["kitchen_sinks"], "wall", dims=(1.0, 0.92, 0.62), fit=0.4),
    _i("extractor_hood", R, "extractorhood.gltf", "a cooker hood", ("w", 0.9), ["kitchen"], ["range_hood"], "wall", dims=(0.9, 0.7, 0.5)),
    _i("kitchen_table", R, "kitchentable_A.gltf", "a kitchen work table", ("l", 1.4), ["kitchen"], [], dims=(1.4, 0.9, 0.8), fit=0.4),
    _i("cutting_board", R, "cuttingboard.gltf", "a cutting board", ("l", 0.4), ["kitchen"], ["chopping_board"],
       "counter"),
    _i("knife", R, "knife.gltf", "a kitchen knife", ("max", 0.28), ["kitchen", "tool"], [], "counter"),
    _i("frying_pan", R, "pan_A.gltf", "a frying pan", ("l", 0.45), ["kitchen"], ["skillet"], "counter"),
    _i("cooking_pot", R, "pot_A.gltf", "a cooking pot", ("l", 0.38), ["kitchen"], ["saucepan"], "counter"),
    _i("plate", R, "plate.gltf", "a plate", ("l", 0.26), ["kitchen", "food"], ["plates"], "table"),
    _i("bowl", R, "bowl.gltf", "a bowl", ("l", 0.18), ["kitchen", "food"], ["bowls"], "table"),
    _i("jar", R, "jar_A_medium.gltf", "a glass jar", ("h", 0.18), ["kitchen"], ["jars"], "counter"),
    _i("ketchup", R, "ketchup.gltf", "a ketchup bottle", ("h", 0.2), ["kitchen", "food"], ["sauce_bottle"], "table"),
    _i("paper_towel", R, "papertowel.gltf", "a kitchen paper roll", ("h", 0.26), ["kitchen"], ["kitchen_roll"],
       "counter"),
    _i("dish_rack", R, "dishrack_plates.gltf", "a dish rack with plates", ("l", 0.45), ["kitchen"], [], "counter"),
    _i("burger", R, "food_burger.gltf", "a burger", ("l", 0.12), ["food"], ["hamburger", "cheeseburger"], "table"),
    _i("carrot", R, "food_ingredient_carrot.gltf", "a carrot", ("max", 0.18), ["food", "vegetable"], ["carrots"],
       "table"),
    _i("tomato", R, "food_ingredient_tomato.gltf", "a tomato", ("l", 0.08), ["food", "vegetable"], ["tomatoes"],
       "table"),
    _i("onion", R, "food_ingredient_onion.gltf", "an onion", ("l", 0.08), ["food", "vegetable"], ["onions"], "table"),
    _i("potato", R, "food_ingredient_potato.gltf", "a potato", ("l", 0.09), ["food", "vegetable"], ["potatoes"],
       "table"),
    _i("cheese", R, "food_ingredient_cheese.gltf", "a block of cheese", ("l", 0.12), ["food"], [], "table"),
    _i("lettuce", R, "food_ingredient_lettuce.gltf", "a lettuce", ("l", 0.16), ["food", "vegetable"], [],
       "table"),
    _i("steak", R, "food_ingredient_steak.gltf", "a raw steak", ("l", 0.2), ["food", "meat"], [], "table"),
    _i("stew", R, "food_stew.gltf", "a bowl of stew", ("l", 0.18), ["food"], [], "table"),
    _i("vegetable_crate", R, "crate_carrots.gltf", "a crate of carrots", ("l", 0.6), ["food", "farm"], ["veg_box"]),
    # street and town (KayKit City Builder Bits, Kenney)
    _i("taxi", CI, "car_taxi.gltf", "a taxi", ("l", 4.5), ["vehicle", "city"], [], "street", dims=(1.8, 1.5, 4.5)),
    _i("police_car", CI, "car_police.gltf", "a police car", ("l", 4.6), ["vehicle", "city"], [], "street", dims=(1.85, 1.55, 4.6)),
    _i("hatchback", CI, "car_hatchback.gltf", "a small hatchback car", ("l", 4.0), ["vehicle", "city"], ["small_car"],
       "street", dims=(1.75, 1.5, 4.0)),
    _i("station_wagon", CI, "car_stationwagon.gltf", "an estate car", ("l", 4.7), ["vehicle", "city"], ["estate_car"],
       "street", dims=(1.85, 1.55, 4.7)),
    _i("lamp_post", CI, "streetlight.gltf", "a street light", ("h", 4.5), ["city", "light"], ["streetlight",
       "street_light", "street_lamp"], "street", replaces="lamp_post"),
    _i("traffic_light", CI, "trafficlight_A.gltf", "a traffic light", ("h", 3.6), ["city"], ["traffic_signal"],
       "street"),
    _i("fire_hydrant", CI, "firehydrant.gltf", "a fire hydrant", ("h", 0.75), ["city"], ["hydrant"], "street"),
    _i("dumpster", CI, "dumpster.gltf", "a dumpster", ("h", 1.3), ["city"], ["skip_bin", "garbage_container"],
       "street"),
    _i("bench", CI, "bench.gltf", "a park bench", ("l", 1.8), ["city", "park"], ["park_bench"], "street"),
    _i("bush", CI, "bush.gltf", "a bush", ("h", 0.9), ["plant", "nature", "city"], ["shrub", "bushes"]),
    _i("trash_bag", CI, "trash_A.gltf", "a pile of trash bags", ("l", 1.0), ["city"], ["garbage_bags"], "street"),
    _i("apartment_building", CI, "building_D_withoutBase.gltf", "an apartment building", ("h", 14.0), ["city",
       "building"], ["apartments", "block_of_flats"]),
    _i("shop_building", CI, "building_A_withoutBase.gltf", "a corner shop building", ("h", 8.0), ["city", "building"],
       ["shop_front"]),
    _i("small_building", KC, "building-small-a.glb", "a small town building", ("h", 6.0), ["city", "building"],
       ["small_house_building"]),
    _i("garage_building", KC, "building-garage.glb", "a garage building", ("h", 4.0), ["city", "building"], []),
    _i("fountain", KC, "pavement-fountain.glb", "a fountain on a square", ("l", 6.0), ["city", "park"],
       ["town_fountain"]),
    _i("pickup_truck", KR, "vehicle-truck-red.glb", "a pickup truck", ("l", 5.5), ["vehicle"], ["pickup"],
       "street", dims=(2.0, 1.9, 5.5)),
    _i("motorcycle", KR, "vehicle-motorcycle.glb", "a motorcycle", ("l", 2.1), ["vehicle"], ["motorbike"],
       "street"),
]
BY_NAME = {it.name: it for it in CATALOG}


# ---------------------------------------------------------------------------------------------------------------
# Where the files live (Drive) and how they get there
# ---------------------------------------------------------------------------------------------------------------

def models_dir() -> Path:
    from .. import config  # noqa: PLC0415

    return config.get().library_dir / "models"


def _fetch(url: str, dest: Path) -> None:
    """One file from the internet (tests replace this: they never touch the network)."""
    from .. import net  # noqa: PLC0415

    net.download(url, dest, timeout=60, retries=1)


def _gltf_deps(path: Path) -> list[str]:
    """The .bin buffers and textures a .gltf file refers to (relative file names)."""
    try:
        g = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for key in ("buffers", "images"):
        for b in g.get(key, []) or []:
            uri = b.get("uri", "")
            if uri and not uri.startswith("data:"):
                out.append(uri)
    return out


def fetch_item(item: Item) -> Path:
    """The model file on Drive (downloaded once with its buffers and textures). Raises on failure."""
    pack = PACKS[item.pack]
    folder = models_dir() / item.pack
    path = folder / item.file
    want = [item.file]
    if not path.exists():
        _fetch(GITHUB_RAW.format(repo=pack["repo"], ref=pack["ref"], path=f"{pack['dir']}/{item.file}"), path)
    if path.suffix == ".gltf":
        want += _gltf_deps(path)
    for dep in want[1:]:
        if not (folder / dep).exists():
            _fetch(GITHUB_RAW.format(repo=pack["repo"], ref=pack["ref"], path=f"{pack['dir']}/{dep}"), folder / dep)
    lic = folder / "LICENSE.txt"
    if not lic.exists():
        lic.write_text(f"{pack['author']}: {CC0}\nSource: {pack['home']} (GitHub {pack['repo']})\n", encoding="utf-8")
    if path.suffix == ".glb":  # Kenney starter kits keep the palette texture next to the models
        tex = folder / "Textures" / "colormap.png"
        if not tex.exists():
            try:
                _fetch(GITHUB_RAW.format(repo=pack["repo"], ref=pack["ref"], path=f"{pack['dir']}/Textures/colormap.png"),
                       tex)
            except Exception:  # noqa: BLE001  (some GLBs carry their texture inside)
                pass
    return path


def fetch_all(rep=None) -> tuple[int, list[str]]:
    """Download every curated model now (once; 8 at a time). → (how many ok, failures). Never raises."""
    import concurrent.futures  # noqa: PLC0415

    ok, bad = 0, []
    todo = [it for it in CATALOG if not available(it.name)]

    def one(it):
        try:
            fetch_item(it)
            return None
        except Exception as exc:  # noqa: BLE001
            return f"{it.name}: {type(exc).__name__}"

    ok = len(CATALOG) - len(todo)
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for res in pool.map(one, todo):
                if res is None:
                    ok += 1
                else:
                    bad.append(res)
    if rep is not None:
        rep.info(f"📦 Free CC0 models: {ok} ready" + (f", {len(bad)} not downloaded" if bad else ""))
    return ok, bad


# ---------------------------------------------------------------------------------------------------------------
# Reading glTF / GLB / OBJ (just what low poly models use: triangles, transforms, a palette texture)
# ---------------------------------------------------------------------------------------------------------------
_CT = {5120: np.int8, 5121: np.uint8, 5122: np.int16, 5123: np.uint16, 5125: np.uint32, 5126: np.float32}
_NC = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}


def _quat_matrix(q) -> np.ndarray:
    x, y, z, w = (float(v) for v in q)
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])


def _node_matrix(n: dict) -> np.ndarray:
    m = np.eye(4)
    if "matrix" in n:
        return np.asarray(n["matrix"], np.float64).reshape(4, 4).T  # glTF is column-major
    if "scale" in n:
        m = np.diag([*n["scale"], 1.0]) @ m
    if "rotation" in n:
        r = np.eye(4)
        r[:3, :3] = _quat_matrix(n["rotation"])
        m = r @ m
    if "translation" in n:
        t = np.eye(4)
        t[:3, 3] = n["translation"]
        m = t @ m
    return m


def read_gltf(path) -> list[dict]:
    """Triangles of a .gltf/.glb: [{tris (T,3,3), uv (T,3,2) or None, color (4,), texture path/bytes, metal}]."""
    path = Path(path)
    data = path.read_bytes()
    bin_chunk = None
    if data[:4] == b"glTF":
        length = struct.unpack_from("<I", data, 8)[0]
        off, g = 12, None
        while off < length:
            clen, ctype = struct.unpack_from("<II", data, off)
            chunk = data[off + 8:off + 8 + clen]
            if ctype == 0x4E4F534A:
                g = json.loads(chunk.decode("utf-8"))
            elif ctype == 0x004E4942:
                bin_chunk = chunk
            off += 8 + clen
    else:
        g = json.loads(data.decode("utf-8"))
    buffers = []
    for b in g.get("buffers", []):
        uri = b.get("uri")
        if uri is None:
            buffers.append(bin_chunk or b"")
        elif uri.startswith("data:"):
            buffers.append(base64.b64decode(uri.split(",", 1)[1]))
        else:
            buffers.append((path.parent / uri).read_bytes())

    def view_bytes(vi: int) -> bytes:
        v = g["bufferViews"][vi]
        b = buffers[v["buffer"]]
        o = v.get("byteOffset", 0)
        return b[o:o + v["byteLength"]]

    def accessor(ai: int) -> np.ndarray:
        a = g["accessors"][ai]
        n, comps, dt = a["count"], _NC[a["type"]], _CT[a["componentType"]]
        v = g["bufferViews"][a["bufferView"]]
        raw = view_bytes(a["bufferView"])
        stride = v.get("byteStride") or comps * np.dtype(dt).itemsize
        off = a.get("byteOffset", 0)
        if stride == comps * np.dtype(dt).itemsize:
            arr = np.frombuffer(raw, dt, count=n * comps, offset=off).reshape(n, comps)
        else:
            rows = [np.frombuffer(raw, dt, count=comps, offset=off + k * stride) for k in range(n)]
            arr = np.stack(rows)
        if a.get("normalized") and dt != np.float32:
            arr = arr.astype(np.float32) / float(np.iinfo(dt).max)
        return arr.astype(np.float32) if dt == np.float32 else arr

    textures = {}
    for ti, t in enumerate(g.get("textures", [])):
        img = g.get("images", [])[t.get("source", 0)] if g.get("images") else None
        if img is None:
            continue
        if "uri" in img and not img["uri"].startswith("data:"):
            textures[ti] = path.parent / img["uri"]
        elif "uri" in img:
            textures[ti] = base64.b64decode(img["uri"].split(",", 1)[1])
        elif "bufferView" in img:
            textures[ti] = view_bytes(img["bufferView"])
    out = []

    def walk(ni: int, parent: np.ndarray) -> None:
        n = g["nodes"][ni]
        m = parent @ _node_matrix(n)
        if "mesh" in n:
            for prim in g["meshes"][n["mesh"]]["primitives"]:
                if prim.get("mode", 4) != 4 or "POSITION" not in prim["attributes"]:
                    continue
                pos = accessor(prim["attributes"]["POSITION"]).astype(np.float64)
                pos = (np.hstack([pos, np.ones((len(pos), 1))]) @ m.T)[:, :3]
                idx = accessor(prim["indices"]).reshape(-1) if "indices" in prim else np.arange(len(pos))
                idx = idx.astype(np.int64)[: len(idx) // 3 * 3]
                uv = accessor(prim["attributes"]["TEXCOORD_0"]) if "TEXCOORD_0" in prim["attributes"] else None
                vcol = accessor(prim["attributes"]["COLOR_0"]) if "COLOR_0" in prim["attributes"] else None
                mat = g.get("materials", [{}])[prim["material"]] if "material" in prim else {}
                pbr = mat.get("pbrMetallicRoughness", {})
                tex = textures.get(pbr.get("baseColorTexture", {}).get("index", -1))
                tris = pos[idx].reshape(-1, 3, 3)
                if np.linalg.det(m[:3, :3]) < 0:  # mirrored node: keep the faces facing out
                    tris = tris[:, ::-1]
                out.append({"tris": tris, "uv": uv[idx].reshape(-1, 3, 2) if uv is not None else None,
                            "vcol": vcol[idx].reshape(-1, 3, vcol.shape[1])[:, :, :3] if vcol is not None else None,
                            "color": np.asarray(pbr.get("baseColorFactor", [1, 1, 1, 1]), np.float64),
                            "texture": tex, "metal": float(pbr.get("metallicFactor", 0.0)),
                            "name": mat.get("name", ""), "alpha": mat.get("alphaMode", "OPAQUE")})
        for c in n.get("children", []):
            walk(c, m)

    scene = g.get("scenes", [{}])[g.get("scene", 0)] if g.get("scenes") else {"nodes": list(range(len(g["nodes"])))}
    for ni in scene.get("nodes", []):
        walk(ni, np.eye(4))
    return out


def read_obj(path) -> list[dict]:
    """Triangles of a Wavefront .obj with its .mtl colours (Kd) and texture (map_Kd)."""
    path = Path(path)
    vs, vts, groups, mats, cur = [], [], {}, {}, ""
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            vs.append([float(x) for x in p[1:4]])
        elif p[0] == "vt":
            vts.append([float(x) for x in p[1:3]])
        elif p[0] == "usemtl":
            cur = p[1] if len(p) > 1 else ""
        elif p[0] == "mtllib" and len(p) > 1:
            mtl = path.parent / " ".join(p[1:])
            name = ""
            if mtl.exists():
                for ml in mtl.read_text(encoding="utf-8", errors="ignore").splitlines():
                    q = ml.split()
                    if not q:
                        continue
                    if q[0] == "newmtl":
                        name = q[1] if len(q) > 1 else ""
                        mats[name] = {"Kd": [0.8, 0.8, 0.8], "map": None}
                    elif q[0] == "Kd" and name:
                        mats[name]["Kd"] = [float(x) for x in q[1:4]]
                    elif q[0] == "map_Kd" and name:
                        mats[name]["map"] = path.parent / q[-1]
        elif p[0] == "f":
            ids = [x.split("/") for x in p[1:]]
            for k in range(1, len(ids) - 1):  # fan triangulation
                groups.setdefault(cur, []).append((ids[0], ids[k], ids[k + 1]))
    V = np.asarray(vs, np.float64)
    VT = np.asarray(vts, np.float64) if vts else None
    out = []
    for name, faces in groups.items():
        def vi(s, n):
            i = int(s)
            return i - 1 if i > 0 else n + i
        tris = np.array([[V[vi(c[0], len(V))] for c in f] for f in faces])
        uv = None
        if VT is not None and all(len(c) > 1 and c[1] for f in faces for c in f):
            uv = np.array([[VT[vi(c[1], len(VT))] for c in f] for f in faces])
        m = mats.get(name, {"Kd": [0.8, 0.8, 0.8], "map": None})
        out.append({"tris": tris, "uv": uv, "vcol": None, "color": np.array([*m["Kd"], 1.0]), "texture": m["map"],
                    "metal": 0.0, "name": name, "alpha": "OPAQUE"})
    return out


def read_model(path) -> list[dict]:
    return read_obj(path) if str(path).lower().endswith(".obj") else read_gltf(path)


# ---------------------------------------------------------------------------------------------------------------
# Into our look: flat colours per part, our palette, real size, standing on the floor, front = +z
# ---------------------------------------------------------------------------------------------------------------

def _texture_colors(tex, uv: np.ndarray) -> np.ndarray:
    """The palette texture's colour at each triangle's centre (flat colours, like our own models)."""
    import io  # noqa: PLC0415

    from PIL import Image  # noqa: PLC0415

    img = Image.open(io.BytesIO(tex) if isinstance(tex, (bytes, bytearray)) else tex).convert("RGB")
    a = np.asarray(img, np.float64) / 255.0
    h, w = a.shape[:2]
    c = uv.mean(1)
    x = np.clip((c[:, 0] % 1.0) * w, 0, w - 1).astype(int)
    y = np.clip((c[:, 1] % 1.0) * h, 0, h - 1).astype(int)  # glTF: v = 0 at the top of the image
    return a[y, x]


def _srgb_hex(rgb) -> str:
    r, g, b = (int(round(min(1.0, max(0.0, float(v))) * 255)) for v in rgb[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _palette() -> np.ndarray:
    from .assets import C  # noqa: PLC0415
    from .gl import hex_rgb  # noqa: PLC0415

    return np.array([hex_rgb(v) for v in C.values()], np.float64)


def _to_our_palette(rgb: np.ndarray) -> np.ndarray:
    """A little toward the nearest library colour, a little calmer: imported things sit with our own objects."""
    pal = _palette()
    near = pal[np.argmin(((pal - rgb) ** 2).sum(1))]
    out = rgb * 0.8 + near * 0.2
    lum = float(out @ np.array([0.2126, 0.7152, 0.0722]))
    out = lum + (out - lum) * 0.92
    return np.clip(out, 0.04, 0.96)


def _material_of(rgb: np.ndarray, metal: float, name: str) -> str:
    n = name.lower()
    if metal > 0.5 or re.search(r"metal|steel|chrome|iron", n):
        return "metal"
    if re.search(r"glass|window", n):
        return "glass"
    sat = float(rgb.max() - rgb.min())
    lum = float(rgb.mean())
    if sat < 0.06 and 0.45 < lum < 0.85:
        return "metal"  # light neutral greys in these packs are appliances, taps, pans
    if sat > 0.35:
        return "paint"
    return "plastic" if lum > 0.75 else ""


def _color_groups(Cc: np.ndarray, tol: float = 0.075, most: int = 10) -> np.ndarray:
    """Group triangle colours: shades of one colour (soft gradients in palette textures) become one flat part."""
    q = np.round(Cc * 48) / 48
    uniq, inv, counts = np.unique(q, axis=0, return_inverse=True, return_counts=True)
    inv = inv.reshape(-1)
    centers, members = [], {}
    for u in np.argsort(-counts):
        d = [float(np.max(np.abs(uniq[u] - c))) for c in centers]
        if d and (min(d) < tol or len(centers) >= most):
            members[u] = int(np.argmin(d))
        else:
            members[u] = len(centers)
            centers.append(uniq[u])
    return np.array([members[u] for u in inv])


def to_model(prims: list[dict], size: tuple = ("h", 1.0), name: str = "model", max_tris: int = 6000,
             dims: tuple = (), fit: float = 0.3) -> M.Model:
    """Our Model from read triangles: one part per colour, real size, on the floor, centred."""
    tris, cols, metals, mnames = [], [], [], []
    for p in prims:
        t = np.asarray(p["tris"], np.float64)
        if not len(t):
            continue
        base = np.asarray(p["color"][:3], np.float64)
        if p.get("texture") is not None and p.get("uv") is not None:
            try:
                c = _texture_colors(p["texture"], p["uv"]) * base
            except (OSError, ValueError):
                c = np.tile(base, (len(t), 1))
        elif p.get("vcol") is not None:
            c = p["vcol"].mean(1) * base
        else:
            c = np.tile(base, (len(t), 1))
        tris.append(t)
        cols.append(c)
        metals += [p.get("metal", 0.0)] * len(t)
        mnames += [p.get("name", "")] * len(t)
    if not tris:
        raise ValueError(f"{name}: no triangles")
    T = np.concatenate(tris)
    Cc = np.concatenate(cols)
    area = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1)
    keep = area > 1e-12
    T, Cc = T[keep], Cc[keep]
    metals = np.asarray(metals)[keep]
    mnames = [n for n, k in zip(mnames, keep) if k]
    if len(T) > max_tris:
        T, Cc, metals, mnames = _decimate(T, Cc, metals, mnames, max_tris)
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    kind, value = size
    ext = hi - lo
    ref = {"h": ext[1], "l": max(ext[0], ext[2]), "w": ext[0], "d": ext[2], "max": max(ext)}.get(kind, ext[1])
    s = float(value) / max(float(ref), 1e-6)
    T = (T - np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])) * s
    if dims:  # toy proportions (a chunky car, a 1 m deep counter): pulled toward the real ones, at most ±30 %
        ext = np.maximum(ext * s, 1e-6)
        k3 = np.clip(np.asarray(dims, np.float64) / ext, 1.0 - fit, 1.0 + fit)
        T = T * k3
    inv = _color_groups(Cc)
    keys = np.unique(inv)
    order = sorted(keys, key=lambda k: -(inv == k).sum())
    m = M.Model()
    for rank, k in enumerate(order):
        sel = inv == k
        rgb = _to_our_palette(Cc[sel].mean(0))
        mat = _material_of(Cc[sel].mean(0), float(metals[sel].mean()), mnames[int(np.nonzero(sel)[0][0])])
        part_name = "body" if rank == 0 else f"detail{rank}"
        m.add(part_name, M.Geo(T[sel].reshape(-1, 3).astype(np.float32)), _srgb_hex(rgb), material=mat)
    return m


def _light_parts(m: M.Model) -> None:
    """Street lights and lamps: their brightest warm part is the bulb (kind lamp: a warm point light at night)."""
    from .gl import hex_rgb  # noqa: PLC0415

    best, score = None, 0.0
    for p in m.parts:
        r, g, b = hex_rgb(p.color)
        sc = (r + g) / 2 - b * 0.6 + (r + g + b) / 3
        if sc > score and (r + g + b) / 3 > 0.6:
            best, score = p, sc
    if best is not None:
        best.kind, best.emissive = "lamp", max(best.emissive, 0.6)


def _decimate(T, Cc, metals, mnames, max_tris):
    """Vertex clustering: snap corners to a grid until few enough triangles are left (for dense scans)."""
    lo, hi = T.reshape(-1, 3).min(0), T.reshape(-1, 3).max(0)
    span = float(np.max(hi - lo))
    cells = 64
    while True:
        q = np.round((T - lo) / span * cells)
        P = q / cells * span + lo
        ok = ~(np.all(q[:, 0] == q[:, 1], 1) | np.all(q[:, 1] == q[:, 2], 1) | np.all(q[:, 0] == q[:, 2], 1))
        if ok.sum() <= max_tris or cells <= 8:
            return P[ok], Cc[ok], metals[ok], [n for n, k in zip(mnames, ok) if k]
        cells = int(cells * 0.75)


# ---------------------------------------------------------------------------------------------------------------
# Library objects
# ---------------------------------------------------------------------------------------------------------------
_CACHE: dict = {}


def load(name: str) -> M.Model:
    """The curated model `name` as our Model (downloaded once). Raises if it can't be had."""
    it = BY_NAME[name]
    if name not in _CACHE:
        path = fetch_item(it)
        _CACHE[name] = to_model(read_model(path), it.size, name, dims=it.dims, fit=it.fit)
        if "light" in it.tags:
            _light_parts(_CACHE[name])
    src = _CACHE[name]
    return M.Model([M.Part(p.name, M.Geo(p.geo.pos.copy()), p.color, p.emissive, p.opacity, p.shell, kind=p.kind,
                           material=p.material) for p in src.parts], dict(src.anchors), dict(src.paths))


def _fallback(it: Item):
    from . import assets  # noqa: PLC0415

    old = assets.REGISTRY.get(it.replaces) if it.replaces else None
    if old is not None:
        return old.fn
    stand_in = {"vehicle": "car", "plant": "potted_plant", "food": "ball", "building": "house", "light": "lamp_post",
                "furniture": "crate", "kitchen": "crate", "city": "crate"}
    for t in it.tags:
        if t in stand_in and stand_in[t] in assets.REGISTRY and stand_in[t] != it.name:
            return assets.REGISTRY[stand_in[t]].fn
    return assets.REGISTRY["crate"].fn


def register() -> list[str]:
    """Every curated model becomes a library object (an old box-built one of the same name is the fallback)."""
    from . import assets  # noqa: PLC0415

    done = []
    for it in CATALOG:
        fb = _fallback(it)

        def fn(_it=it, _fb=fb, **kw):
            try:
                return load(_it.name)
            except Exception:  # noqa: BLE001  (offline, tests, a broken file: the procedural object)
                import inspect  # noqa: PLC0415

                ok = {k: v for k, v in kw.items() if k in inspect.signature(_fb).parameters}
                return _fb(**ok)

        import inspect  # noqa: PLC0415

        fb_params = {k: v.default for k, v in inspect.signature(fb).parameters.items()
                     if v.default is not inspect.Parameter.empty and k != "_"}
        tags = sorted(set(it.tags) | {"cc0", "imported"} | ({"set"} if it.replaces and "set" in getattr(
            assets.REGISTRY.get(it.replaces), "tags", []) else set()))
        assets.REGISTRY[it.name] = assets.AssetInfo(it.name, fn, f"{it.about} (free CC0 model)", tags, fb_params)
        for a in it.aliases:
            assets.ALIASES.setdefault(a, it.name)
        if it.place in ("counter", "table", "wall"):
            assets.PLACE[it.name] = it.place
        done.append(it.name)
    return done


def available(name: str) -> bool:
    """Is this curated model's file already on Drive (no download needed)?"""
    it = BY_NAME.get(name)
    if it is None:
        return False
    try:
        return (models_dir() / it.pack / it.file).exists()
    except Exception:  # noqa: BLE001
        return False


def scan_folders() -> list[str]:
    """Any other CC0 pack you put in StoryForge/library/models/<pack>/ (Kenney zips, Quaternius, Poly Haven): each
    model becomes `<pack>_<file>` (1 m tall unless the name says otherwise). A pack without a LICENSE file saying
    CC0 is skipped (only CC0 here)."""
    from . import assets  # noqa: PLC0415

    found = []
    try:
        root = models_dir()
    except Exception:  # noqa: BLE001
        return found
    if not root.exists():
        return found
    for pack in sorted(p for p in root.iterdir() if p.is_dir() and p.name not in PACKS):
        lic = " ".join(f.read_text(encoding="utf-8", errors="ignore") for f in pack.glob("LICENSE*"))
        if not re.search(r"CC0|public domain|creative commons zero", lic, re.I):
            continue
        for f in sorted(list(pack.rglob("*.glb")) + list(pack.rglob("*.gltf")) + list(pack.rglob("*.obj")))[:300]:
            nm = re.sub(r"[^a-z0-9]+", "_", f"{pack.name}_{f.stem}".lower()).strip("_")
            if nm in assets.REGISTRY:
                continue

            def fn(_f=f, **kw):
                return to_model(read_model(_f), ("h", 1.0), _f.stem)

            assets.REGISTRY[nm] = assets.AssetInfo(nm, fn, f"{f.stem.replace('_', ' ')} (CC0 model from {pack.name})",
                                                   ["cc0", "imported"], {})
            found.append(nm)
    return found


def fetch_polyhaven(asset_id: str, rep=None) -> Path:
    """A Poly Haven model (CC0) by id, as glTF at 1k, into library/models/polyhaven/<id>/ (Colab: open internet).
    Poly Haven models are realistic scans: to_model reduces them to flat low poly colours (≤ 6000 triangles)."""
    from .. import net  # noqa: PLC0415

    folder = models_dir() / "polyhaven" / asset_id
    files = net.request("GET", f"https://api.polyhaven.com/files/{asset_id}", timeout=30).json()
    gl = files["gltf"]["1k"]["gltf"]
    _fetch(gl["url"], folder / f"{asset_id}.gltf")
    for rel, info in (gl.get("include") or {}).items():
        _fetch(info["url"], folder / rel)
    lic = models_dir() / "polyhaven" / "LICENSE.txt"
    if not lic.exists():
        lic.write_text(f"Poly Haven (polyhaven.com): {CC0}\n", encoding="utf-8")
    return folder / f"{asset_id}.gltf"


def fetch_url(pack: str, url: str, author: str) -> Path:
    """A CC0 zip (a Kenney kit from kenney.nl, a Quaternius pack) unpacked into library/models/<pack>/."""
    import zipfile  # noqa: PLC0415

    folder = models_dir() / re.sub(r"[^a-z0-9_]+", "_", pack.lower())
    z = folder / "pack.zip"
    _fetch(url, z)
    with zipfile.ZipFile(z) as zf:
        for member in zf.namelist():
            target = (folder / member).resolve()
            if folder.resolve() in target.parents and re.search(r"\.(glb|gltf|bin|obj|mtl|png|jpg|txt)$", member, re.I):
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(member))
    (folder / "LICENSE.txt").write_text(f"{author}: {CC0}\nSource: {url}\n", encoding="utf-8")
    z.unlink(missing_ok=True)
    return folder


def placement(name: str) -> str:
    """Where a thing normally stands: floor, counter, wall, table or street (used by the placement rules)."""
    it = BY_NAME.get(name)
    return it.place if it else ""


def catalog_lines() -> list[str]:
    return [f"{it.name} ({it.about}; {it.size[1]} m {'tall' if it.size[0] == 'h' else 'long'}; on the {it.place})"
            for it in CATALOG]
