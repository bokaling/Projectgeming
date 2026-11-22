"""More low poly objects for the library (phase 2): animals, buildings, vehicles, machines, nature,
fire, science, space, tools, money, symbols, containers and cross-section helpers.

Same rules as assets.py: every object is a function with parameters, decorated with @asset, made of
named parts. Moving parts have a kind: "blade" (spins), "wheel" (rolls when moving), "piston" (goes
up and down while the machine runs), "rocker" (swings while it runs), "flame" (flickers),
"liquid" (fill / drain), "light" (turns on). Shell parts can be cut open or seen through (x-ray).
"""

from __future__ import annotations

import math

import numpy as np

from . import mesh as M
from .assets import C, asset, col
from .mesh import Model

def _floor(g):
    """Nothing below the floor (jittered rocks and hills can poke through it)."""
    p = g.pos.copy()
    p[:, 1] = np.maximum(p[:, 1], 0.0)
    return M.Geo(p)


# ---------------------------------------------------------------------------
# Animals
# ---------------------------------------------------------------------------


def _quadruped(m: Model, body, length, height, color, legs_color, head_color=None, leg=0.55, neck=0.0):
    m.add("body", M.xf(M.box(length, height, length * 0.45, base=True), (0, leg, 0)), color)
    for x in (-length * 0.36, length * 0.36):
        for z in (-length * 0.15, length * 0.15):
            m.add("leg", M.xf(M.box(0.14 * body, leg, 0.14 * body, base=True), (x, 0, z)), legs_color)
    hc = head_color or color
    m.add("head", M.xf(M.box(0.42 * body, 0.38 * body, 0.36 * body, base=True),
                       (length / 2 + 0.16 * body, leg + height * 0.55 + neck, 0)), hc)
    return m


@asset("pig", "a pink pig", ["animal", "farm"], aliases=["pigs", "hog", "swine", "piglet"])
def pig(color="pink"):
    c = col(color, C["pink"])
    m = _quadruped(Model(), 1.0, 1.3, 0.62, c, c, leg=0.35)
    m.add("snout", M.xf(M.cylinder(0.13, 0.12, 8, base=False), (0.98, 0.72, 0), (0, 0, 90)), "#e88a9e")
    return m


@asset("sheep", "a fluffy white sheep", ["animal", "farm"], aliases=["lamb", "ram"])
def sheep(color="white", seed=4):
    m = Model()
    wool = M.merge(*[M.xf(M.sphere(0.33, 0), (x, 0.82, z)) for x in (-0.35, 0, 0.35) for z in (-0.15, 0.15)])
    m.add("wool", M.jitter(wool, 0.03, seed), col(color, C["white"]))
    for x in (-0.35, 0.35):
        for z in (-0.15, 0.15):
            m.add("leg", M.xf(M.box(0.1, 0.55, 0.1, base=True), (x, 0, z)), C["black"])
    m.add("head", M.xf(M.box(0.3, 0.3, 0.26, base=True), (0.68, 0.8, 0)), C["black"])
    return m


@asset("chicken", "a chicken / hen", ["animal", "farm"], aliases=["hen", "rooster", "chick", "poultry"])
def chicken(color="white"):
    m = Model()
    m.add("body", M.xf(M.sphere(0.3, 1), (0, 0.45, 0), s=(1.2, 1.0, 0.9)), col(color, C["white"]))
    m.add("head", M.xf(M.sphere(0.15, 1), (0.3, 0.8, 0)), col(color, C["white"]))
    m.add("comb", M.xf(M.box(0.12, 0.1, 0.04, base=True), (0.3, 0.92, 0)), C["red"])
    m.add("beak", M.xf(M.cone(0.05, 0.14, 6), (0.45, 0.8, 0), (0, 0, -90)), C["orange"])
    for z in (-0.1, 0.1):
        m.add("leg", M.xf(M.cylinder(0.03, 0.2, 5), (0, 0, z)), C["orange"])
    return m


@asset("horse", "a brown horse", ["animal", "farm"], aliases=["pony", "donkey"])
def horse(color="#8b5a2b"):
    c = col(color, "#8b5a2b")
    m = _quadruped(Model(), 1.3, 1.8, 0.75, c, "#5a3a1c", leg=1.0, neck=0.45)
    m.add("neck", M.xf(M.box(0.35, 0.8, 0.3, base=True), (1.0, 1.4, 0), (0, 0, -25)), c)
    return m


@asset("fish", "a fish (swims with 'float' or 'move')", ["animal", "water"], aliases=["fishes", "salmon", "tuna"])
def fish(color="#f28c28"):
    c = col(color, C["orange"])
    m = Model().add("body", M.xf(M.sphere(0.4, 1), (0, 0.5, 0), s=(1.6, 0.8, 0.5)), c)
    m.add("tail", M.xf(M.extrude([(0, 0), (-0.45, 0.3), (-0.45, -0.3)], 0.06), (-0.55, 0.5, 0)), c)
    m.add("eye", M.xf(M.sphere(0.06, 0), (0.45, 0.6, 0.17)), C["black"])
    return m


@asset("bird", "a small bird (flies with 'move' or 'float')", ["animal", "nature"], aliases=["birds", "pigeon", "seagull"])
def bird(color="#3d8fd6"):
    c = col(color, C["blue"])
    m = Model().add("body", M.xf(M.sphere(0.22, 1), (0, 0.4, 0), s=(1.5, 0.9, 0.9)), c)
    for z in (-1, 1):
        m.add("wing", M.xf(M.box(0.3, 0.04, 0.5), (0, 0.48, z * 0.3), (z * 15, 0, 0)), c, kind="rocker", axis="x",
              pivot=(0, 0.48, 0))
    m.add("beak", M.xf(M.cone(0.05, 0.14, 6), (0.33, 0.42, 0), (0, 0, -90)), C["yellow"])
    return m


@asset("dog", "a dog", ["animal", "city"], aliases=["dogs", "puppy"])
def dog(color="#c98d4b"):
    c = col(color, "#c98d4b")
    m = _quadruped(Model(), 0.8, 1.0, 0.45, c, c, leg=0.4, neck=0.15)
    m.add("tail", M.xf(M.box(0.06, 0.35, 0.06, base=True), (-0.52, 0.75, 0), (0, 0, 35)), c)
    return m


# ---------------------------------------------------------------------------
# Buildings and big structures
# ---------------------------------------------------------------------------


def _windows(m: Model, w, d, floors, h, y0=0.4, per=4, color="#2b3a4a"):
    for f in range(floors):
        y = y0 + f * h
        for k in range(per):
            x = -w / 2 + w * (k + 0.5) / per
            m.add("window", M.xf(M.box(w / per * 0.55, h * 0.45, 0.06), (x, y + h * 0.3, d / 2 + 0.02)), color,
                  kind="light")


@asset("factory", "a factory with a sawtooth roof, a tall chimney (smoke comes out) and windows that light up",
       ["industry", "building"], aliases=["mill", "workshop", "refinery", "manufacturing", "factories"])
def factory(w=10.0, d=6.0, h=4.0, color="#c9b79c", chimney=True):
    m = Model()
    m.add("walls", M.box(w, h, d, base=True), col(color, "#c9b79c"), shell=True)
    teeth = 4
    for k in range(teeth):
        x0 = -w / 2 + w * k / teeth
        m.add("roof", M.xf(M.extrude([(0, 0), (w / teeth, 0), (w / teeth, 1.3)], d), (x0, h, 0)), "#7d8a96", shell=True)
    _windows(m, w, d, 1, h * 0.6, y0=0.6, per=6)
    if chimney:
        m.add("chimney", M.xf(M.cylinder(0.55, h * 2.2, 12, r_top=0.45), (w * 0.35, 0, -d * 0.25)), "#b04a3c")
        m.add("stripe", M.xf(M.cylinder(0.5, 0.4, 12), (w * 0.35, h * 1.8, -d * 0.25)), C["white"])
        m.anchors["exhaust"] = (w * 0.35, h * 2.25, -d * 0.25)
    m.add("door", M.xf(M.box(1.8, 2.2, 0.08, base=True), (-w * 0.3, 0, d / 2 + 0.03)), "#5b6672")
    m.anchors["label"] = (0.0, h * 2.4 if chimney else h + 2.2, 0.0)
    return m


@asset("skyscraper", "a tall office tower with many lit windows", ["city", "building"],
       aliases=["tower", "office", "office_building", "building", "apartment", "high_rise"])
def skyscraper(floors=12, w=4.0, color="#6f8aa3"):
    floors = max(2, int(floors))
    h = floors * 1.1
    m = Model().add("tower", M.box(w, h, w, base=True), col(color, "#6f8aa3"), shell=True)
    _windows(m, w, w, floors, 1.1, y0=0.2, per=3, color="#24323f")
    m.add("top", M.xf(M.box(w * 0.6, 0.6, w * 0.6, base=True), (0, h, 0)), "#4b5a68")
    m.anchors["label"] = (0.0, h + 1.4, 0.0)
    return m


@asset("warehouse", "a big warehouse / storage hall with a curved roof", ["industry", "building"],
       aliases=["hall", "depot", "hangar", "storage_building"])
def warehouse(w=12.0, d=7.0, h=3.5, color="#9fb3c2"):
    m = Model().add("walls", M.box(w, h, d, base=True), col(color, "#9fb3c2"), shell=True)
    arc = [(math.cos(a) * d / 2, h + math.sin(a) * 1.6) for a in np.linspace(0, math.pi, 9)]
    roof = M.extrude(arc, w)
    m.add("roof", M.xf(roof, (0, 0, 0), (0, 90, 0)), "#7d8a96", shell=True)
    m.add("door", M.xf(M.box(3.0, 2.6, 0.08, base=True), (0, 0, d / 2 + 0.03)), "#5b6672")
    return m


@asset("silo", "a tall round farm silo (grain, feed) with a dome", ["farm", "building", "container"],
       aliases=["grain_silo", "feed_silo"])
def silo(r=1.6, h=8.0, color="#c7cfd6"):
    m = Model().add("wall", M.cylinder(r, h, 18), col(color, "#c7cfd6"), shell=True)
    for y in np.arange(1.0, h, 1.4):
        m.add("ring", M.xf(M.torus(r * 1.01, 0.04, 18, 4), (0, float(y), 0)), C["dark_steel"], shell=True)
    m.add("dome", M.xf(M.lathe([(r, 0), (r * 0.7, r * 0.45), (0, r * 0.6)], 18, close_bottom=False), (0, h, 0)),
          "#9aa7b3", shell=True)
    m.add("grain", M.cylinder(r * 0.95, h * 0.6, 18), C["sand"], kind="liquid")
    return m


@asset("cooling_tower", "a power-plant cooling tower (curved concrete, steam comes out of the top)",
       ["energy", "industry"], aliases=["cooling_towers", "nuclear_plant", "nuclear_tower"])
def cooling_tower(r=4.0, h=10.0, color="#d7d4cc"):
    prof = [(r, 0), (r * 0.82, h * 0.35), (r * 0.66, h * 0.7), (r * 0.7, h * 0.9), (r * 0.76, h)]
    m = Model().add("shell", M.lathe(prof, 24, close_bottom=False, close_top=False), col(color, "#d7d4cc"), shell=True)
    m.add("legs", M.merge(*[M.xf(M.box(0.25, 0.8, 0.25, base=True),
                                 (r * 0.97 * math.cos(a), 0, r * 0.97 * math.sin(a)))
                            for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)]), "#9a978f")
    m.anchors["exhaust"] = (0.0, h, 0.0)
    return m


@asset("power_station", "a power station: a building, a cooling tower and a chimney", ["energy", "industry"],
       aliases=["power_plant", "powerplant", "power_house", "coal_plant", "gas_plant"])
def power_station(color="#b9c3cc"):
    m = Model().add("hall", M.box(8, 4, 5, base=True), col(color, "#b9c3cc"), shell=True)
    m.add("roof", M.xf(M.box(8.2, 0.3, 5.2, base=True), (0, 4, 0)), "#7d8a96")
    _windows(m, 8, 5, 1, 2.6, y0=0.8, per=5)
    tower = cooling_tower(3.0, 8.0)
    for p in tower.parts:
        m.add("tower_" + p.name, M.xf(p.geo, (-7.0, 0, 0)), p.color, shell=p.shell)
    m.add("chimney", M.xf(M.cylinder(0.45, 10, 10, r_top=0.35), (3.0, 0, -1.5)), "#b04a3c")
    m.anchors["exhaust"] = (3.0, 10.2, -1.5)
    m.anchors["steam"] = (-7.0, 8.0, 0.0)
    m.anchors["label"] = (0.0, 11.0, 0.0)
    m.anchors["outlet"] = (4.0, 3.0, 0.0)
    return m


@asset("wind_turbine", "a wind turbine: tall white tower, nacelle and 3 blades that spin", ["energy"],
       aliases=["windmill", "wind_mill", "wind_farm", "wind_generator"])
def wind_turbine(h=14.0, blade=5.5, color="white"):
    c = col(color, C["white"])
    m = Model().add("tower", M.cylinder(0.45, h, 12, r_top=0.25), c)
    m.add("nacelle", M.xf(M.box(1.6, 0.8, 0.8), (0, h + 0.2, -0.2)), c)
    hub = (0.0, h + 0.2, 0.35)
    blades = [M.xf(M.extrude([(-0.18, 0), (0.22, 0), (0.06, blade), (-0.04, blade)], 0.08), hub, (0, 0, a))
              for a in (0, 120, 240)]
    m.add("blades", M.merge(M.xf(M.sphere(0.32, 1), hub), *blades), c, kind="blade", axis="z", pivot=hub)
    m.anchors["label"] = (0.0, h + blade + 0.8, 0.0)
    m.anchors["outlet"] = (0.0, 1.0, 0.0)
    return m


@asset("solar_panel", "a solar panel on a stand (glows when the sun hits it: light_on)", ["energy"],
       aliases=["solar_panels", "solar", "pv_panel", "solar_farm"])
def solar_panel(w=2.4, d=1.4, color="#1d3f72"):
    m = Model().add("stand", M.xf(M.box(0.12, 1.0, 0.12, base=True), (0, 0, 0)), C["steel"])
    panel = M.xf(M.box(w, 0.08, d), (0, 1.15, 0), (-28, 0, 0))
    m.add("panel", panel, col(color, "#1d3f72"), kind="light")
    for k in range(1, 4):
        m.add("line", M.xf(M.box(0.03, 0.09, d), (-w / 2 + w * k / 4, 1.16, 0), (-28, 0, 0)), "#a9c4e8")
    return m


@asset("dam", "a concrete dam holding back a lake (water flows through the turbines below)", ["energy", "water"],
       aliases=["hydro_dam", "hydroelectric_dam", "hydro", "reservoir"])
def dam(w=16.0, h=8.0, color="#c4c0b6", water="#3aa6d9"):
    m = Model()
    wall = M.extrude([(-1.5, 0), (1.5, 0), (0.6, h), (-0.6, h)], w)
    m.add("wall", M.xf(wall, r=(0, 90, 0)), col(color, "#c4c0b6"), shell=True)
    m.add("lake", M.xf(M.box(w, h * 0.85, w * 0.8, base=True), (0, 0, -w * 0.4 - 1.4)), col(water, C["water"]),
          opacity=0.75, kind="liquid")
    m.add("outlet_pipe", M.xf(M.cylinder(0.6, 2.5, 10, base=False), (0, 1.0, 2.2), (90, 0, 0)), C["dark_steel"])
    m.anchors["inlet"] = (0.0, h * 0.6, -1.6)
    m.anchors["outlet"] = (0.0, 1.0, 3.5)
    m.anchors["label"] = (0.0, h + 1.2, 0.0)
    return m


@asset("bridge", "a simple bridge with towers and cables", ["city", "transport"], aliases=["overpass", "viaduct"])
def bridge(length=20.0, color="#d9534f"):
    c = col(color, C["red"])
    m = Model().add("deck", M.xf(M.box(length, 0.5, 3.0, base=True), (0, 3.0, 0)), "#7d8a96")
    for x in (-length * 0.3, length * 0.3):
        for z in (-1.4, 1.4):
            m.add("tower", M.xf(M.box(0.5, 9.0, 0.5, base=True), (x, 0, z)), c)
    for z in (-1.4, 1.4):
        pts = [(-length / 2, 3.5, z)] + [(float(x), 3.5 + 5.5 * (x / (length * 0.3)) ** 2, z)
                                         for x in np.linspace(-length * 0.3, length * 0.3, 9)] + [(length / 2, 3.5, z)]
        m.add("cable", M.tube(pts, 0.08, 5, joints=False), c)
    return m


@asset("lighthouse", "a lighthouse with a lamp on top (light_on)", ["building", "water"], aliases=["beacon"])
def lighthouse(h=9.0):
    m = Model().add("tower", M.cylinder(1.2, h, 12, r_top=0.8), C["white"], shell=True)
    for y in (h * 0.25, h * 0.6):
        m.add("stripe", M.xf(M.cylinder(1.1, h * 0.15, 12, r_top=1.0), (0, y, 0)), C["red"], shell=True)
    m.add("lamp", M.xf(M.cylinder(0.7, 1.0, 10), (0, h, 0)), C["glass"], kind="light")
    m.add("cap", M.xf(M.cone(0.95, 0.9, 10), (0, h + 1.0, 0)), C["red"])
    return m


@asset("water_tower", "a water tower (tank on legs)", ["city", "water", "container"], aliases=["water_tank"])
def water_tower(h=7.0, color="#7cc6ea"):
    m = Model()
    for a in (45, 135, 225, 315):
        m.add("leg", M.xf(M.box(0.25, h, 0.25, base=True), (1.3 * math.cos(math.radians(a)), 0,
                                                              1.3 * math.sin(math.radians(a)))), C["steel"])
    m.add("tank", M.xf(M.cylinder(2.0, 2.4, 16), (0, h, 0)), col(color, C["sky_blue"]), shell=True)
    m.add("water", M.xf(M.cylinder(1.9, 2.1, 16), (0, h + 0.1, 0)), C["water"], kind="liquid")
    m.add("roof", M.xf(M.cone(2.2, 1.0, 16), (0, h + 2.4, 0)), "#4b5a68")
    return m


@asset("greenhouse", "a glass greenhouse with plants inside", ["farm", "building"], aliases=["glasshouse"])
def greenhouse(w=8.0, d=4.0):
    m = Model().add("glass", M.box(w, 2.4, d, base=True), C["glass"], opacity=0.35, shell=True)
    m.add("roof", M.xf(M.prism_roof(d, w, 1.4), (0, 2.4, 0), (0, 90, 0)), C["glass"], opacity=0.35, shell=True)
    for x in np.linspace(-w / 2 + 0.6, w / 2 - 0.6, 6):
        m.add("plant", M.xf(M.sphere(0.35, 0), (float(x), 0.45, 0)), C["tree"])
    return m


# ---------------------------------------------------------------------------
# Vehicles
# ---------------------------------------------------------------------------


def _wheels(m: Model, xs, z, r=0.35, y=None):
    for x in xs:
        for zz in (-z, z):
            c = (x, r if y is None else y, zz)
            m.add("wheel", M.xf(M.cylinder(r, 0.25, 10, base=False), c, (90, 0, 0)), C["black"], kind="wheel", axis="z",
                  pivot=c)


@asset("car", "a small car", ["vehicle", "city"], aliases=["cars", "auto", "taxi", "sedan", "electric_car"])
def car(color="#d9534f"):
    m = Model().add("body", M.xf(M.box(2.6, 0.6, 1.3, base=True), (0, 0.3, 0)), col(color, C["red"]))
    m.add("cabin", M.xf(M.box(1.4, 0.55, 1.2, base=True), (-0.15, 0.9, 0)), C["glass"])
    _wheels(m, (-0.85, 0.85), 0.62)
    return m


@asset("bus", "a city bus", ["vehicle", "city"], aliases=["coach", "school_bus"])
def bus(color="#f4c430"):
    m = Model().add("body", M.xf(M.box(6.0, 1.9, 2.0, base=True), (0, 0.35, 0)), col(color, C["yellow"]))
    for k in range(5):
        m.add("window", M.xf(M.box(0.8, 0.6, 2.02), (-2.2 + k * 1.1, 1.75, 0)), "#2b3a4a", kind="light")
    _wheels(m, (-2.0, 2.0), 0.95, 0.42)
    return m


@asset("train", "a train: locomotive + wagons (wheels roll when it moves)", ["vehicle", "transport"],
       aliases=["locomotive", "railway", "rail", "subway", "metro", "tram"])
def train(wagons=2, color="#3d8fd6"):
    c = col(color, C["blue"])
    m = Model().add("engine", M.xf(M.box(4.0, 2.2, 2.0, base=True), (0, 0.4, 0)), c)
    m.add("nose", M.xf(M.box(0.6, 1.2, 1.8, base=True), (2.3, 0.4, 0)), "#2b3a4a")
    _wheels(m, (-1.2, 1.2), 0.9, 0.4)
    for k in range(int(wagons)):
        x = -4.5 * (k + 1)
        m.add("wagon", M.xf(M.box(4.0, 2.0, 2.0, base=True), (x, 0.4, 0)), C["gray"])
        _wheels(m, (x - 1.2, x + 1.2), 0.9, 0.4)
    m.add("rail", M.xf(M.box(4.5 * (int(wagons) + 1) + 2, 0.08, 1.6, base=True), (-2.25 * int(wagons), 0, 0)),
          C["dark_steel"])
    return m


@asset("ship", "a cargo ship with containers", ["vehicle", "water", "transport"], aliases=["boat", "cargo_ship", "tanker_ship", "ferry"])
def ship(length=12.0, color="#d9534f"):
    m = Model()
    hull = M.extrude([(-length / 2, 0.4), (length / 2 - 1.5, 0.4), (length / 2, 2.0), (-length / 2, 2.0)], 3.2)
    m.add("hull", hull, col(color, C["red"]), shell=True)
    m.add("deck", M.xf(M.box(length - 1.5, 0.2, 3.0, base=True), (-0.75, 2.0, 0)), "#5b6672")
    m.add("bridge", M.xf(M.box(1.8, 2.0, 2.6, base=True), (-length / 2 + 1.2, 2.2, 0)), C["white"])
    cols = [C["blue"], C["orange"], C["green"], C["yellow"]]
    for k in range(int(length // 2.2) - 1):
        m.add("container", M.xf(M.box(1.9, 1.0, 2.4, base=True), (-length / 2 + 3.2 + k * 2.1, 2.2, 0)), cols[k % 4])
    return m


@asset("airplane", "a passenger airplane", ["vehicle", "transport"], aliases=["plane", "jet", "aircraft", "airliner"])
def airplane(color="white"):
    c = col(color, C["white"])
    m = Model().add("body", M.xf(M.capsule(0.55, 7.0, 12), (0, 2.0, 0)), c)
    m.add("wing", M.xf(M.extrude([(-1.0, -4.5), (1.0, -0.5), (1.0, 0.5), (-1.0, 4.5)], 0.15, axis="y"), (0.3, 1.8, 0)),
          C["gray"])
    m.add("tail", M.xf(M.extrude([(0, 0), (1.2, 0), (0.2, 1.6)], 0.12), (-4.2, 2.3, 0)), C["red"])
    for z in (-2.0, 2.0):
        m.add("engine", M.xf(M.cylinder(0.32, 1.0, 10, base=False), (0.8, 1.45, z), (0, 0, 90)), C["dark_steel"])
    return m


@asset("rocket", "a space rocket (smoke/fire at the bottom when it launches)", ["vehicle", "space"],
       aliases=["spaceship", "space_rocket", "missile", "launch_vehicle"])
def rocket(h=8.0, color="white"):
    c = col(color, C["white"])
    y0 = 1.6  # stands on a launch pad, the flame goes down to it
    m = Model().add("pad", M.box(3.0, 0.4, 3.0, base=True), C["dark_steel"])
    m.add("body", M.xf(M.cylinder(0.7, h * 0.75, 14), (0, y0, 0)), c)
    m.add("nose", M.xf(M.cone(0.7, h * 0.2, 14), (0, y0 + h * 0.75, 0)), C["red"])
    for a in (0, 120, 240):
        fin = M.extrude([(0, 0), (1.0, 0), (0, 1.8)], 0.1)
        m.add("fin", M.xf(fin, (0.6 * math.cos(math.radians(a)), y0, 0.6 * math.sin(math.radians(a))), (0, -a, 0)),
              C["red"])
    m.add("window", M.xf(M.sphere(0.25, 1), (0, y0 + h * 0.5, 0.62)), C["glass"], kind="light")
    m.add("flame", M.xf(M.cone(0.5, 1.2, 10), (0, y0 + 0.05, 0), (180, 0, 0)), C["fire"], emissive=0.9, kind="flame")
    m.anchors["exhaust"] = (0.0, 0.5, 0.0)
    return m


@asset("helicopter", "a helicopter with spinning rotors", ["vehicle"], aliases=["chopper"])
def helicopter(color="#3d8fd6"):
    c = col(color, C["blue"])
    m = Model().add("body", M.xf(M.sphere(1.0, 1), (0, 1.4, 0), s=(1.5, 1.0, 1.0)), c)
    m.add("tail", M.xf(M.box(3.0, 0.3, 0.3), (-2.4, 1.6, 0)), c)
    m.add("skids", M.merge(M.xf(M.box(3.0, 0.1, 0.1), (0, 0.2, 0.7)), M.xf(M.box(3.0, 0.1, 0.1), (0, 0.2, -0.7))),
          C["dark_steel"])
    rotor = M.merge(M.xf(M.box(6.5, 0.06, 0.3), (0, 2.6, 0)), M.xf(M.box(0.3, 0.06, 6.5), (0, 2.6, 0)))
    m.add("rotor", rotor, C["black"], kind="blade", axis="y")
    return m


@asset("crane", "a construction tower crane", ["industry", "building"], aliases=["tower_crane", "construction"])
def crane(h=12.0, color="yellow"):
    c = col(color, C["yellow"])
    m = Model().add("mast", M.box(0.8, h, 0.8, base=True), c)
    m.add("jib", M.xf(M.box(12.0, 0.6, 0.6), (3.0, h + 0.3, 0)), c, kind="blade", axis="y")
    m.add("cab", M.xf(M.box(1.2, 1.0, 1.0, base=True), (0.9, h - 1.0, 0)), C["white"])
    m.add("hook", M.xf(M.box(0.08, 4.0, 0.08, base=True), (7.5, h - 4.0, 0)), C["black"], kind="blade", axis="y")
    return m


@asset("excavator", "a digger / excavator", ["vehicle", "industry"], aliases=["digger", "bulldozer", "backhoe"])
def excavator(color="yellow"):
    c = col(color, C["yellow"])
    m = Model().add("tracks", M.box(3.0, 0.7, 2.2, base=True), C["black"])
    m.add("body", M.xf(M.box(2.4, 1.4, 1.8, base=True), (-0.2, 0.7, 0)), c)
    m.add("cab", M.xf(M.box(1.0, 1.2, 1.0, base=True), (0.5, 2.1, 0.4)), C["glass"])
    m.add("arm", M.tube([(0.8, 1.8, -0.4), (2.6, 3.2, -0.4), (3.6, 1.2, -0.4)], 0.18, 6), c, kind="rocker", axis="z",
          pivot=(0.8, 1.8, -0.4))
    return m


# ---------------------------------------------------------------------------
# Machines and parts
# ---------------------------------------------------------------------------


@asset("pump", "a pump: motor + pump housing with pipes in and out (the impeller spins inside)",
       ["machine", "industry", "water"], aliases=["pumps", "water_pump", "pumping_station"])
def pump(color="#3d8fd6"):
    c = col(color, C["blue"])
    m = Model().add("base", M.box(2.6, 0.2, 1.0, base=True), C["dark_steel"])
    m.add("motor", M.xf(M.cylinder(0.45, 1.3, 12, base=False), (-0.6, 0.7, 0), (0, 0, 90)), c)
    m.add("housing", M.xf(M.cylinder(0.6, 0.5, 14, base=False), (0.6, 0.75, 0), (0, 0, 90)), C["steel"], shell=True)
    hub = (0.6, 0.75, 0.0)
    m.add("impeller", M.merge(*[M.xf(M.box(0.08, 0.9, 0.12), hub, (a, 0, 0)) for a in (0, 60, 120)]),
          C["orange"], kind="blade", axis="x", pivot=hub)
    m.add("pipe_in", M.tube([(0.6, 0.75, 0.0), (2.0, 0.75, 0.0)], 0.2, 8, joints=False), C["steel"])
    m.add("pipe_out", M.tube([(0.6, 0.75, 0.0), (0.6, 2.0, 0.0)], 0.2, 8, joints=False), C["steel"])
    m.anchors["inlet"] = (2.0, 0.75, 0.0)
    m.anchors["outlet"] = (0.6, 2.0, 0.0)
    return m


@asset("gear", "a gear wheel that spins (use count + row layout for a gear train)", ["machine"],
       aliases=["gears", "cog", "cogwheel", "sprocket"])
def gear(r=1.0, teeth=12, color="#9aa3ab"):
    c = (0.0, r + 0.2, 0.0)
    m = Model().add("gear", M.xf(M.gear(r, int(teeth), 0.3, r * 0.2, 0.0), c), col(color, C["gray"]), kind="blade",
                    axis="z", pivot=c)
    m.add("axle", M.xf(M.cylinder(r * 0.15, 0.5, 8, base=False), c, (90, 0, 0)), C["dark_steel"])
    m.add("stand", M.box(0.2, r + 0.2, 0.2, base=True), C["dark_steel"])
    return m


@asset("engine", "a car engine block with pistons that move up and down (cutaway shows them)",
       ["machine", "vehicle"], aliases=["motor_engine", "combustion_engine", "piston_engine", "v8"])
def engine(cylinders=4, color="#8f9ba8"):
    n = max(1, int(cylinders))
    w = n * 0.8 + 0.4
    m = Model().add("block", M.box(w, 1.6, 1.2, base=True), col(color, C["steel"]), shell=True)
    m.add("head", M.xf(M.box(w, 0.4, 1.0, base=True), (0, 1.6, 0)), C["dark_steel"], shell=True)
    for k in range(n):
        x = -w / 2 + 0.6 + k * 0.8
        m.add("piston", M.xf(M.cylinder(0.3, 0.45, 10), (x, 0.9, 0)), "#d4dadd", kind="piston")
        m.add("spark", M.xf(M.sphere(0.08, 0), (x, 1.5, 0)), C["lamp"], kind="light")
    m.add("crank", M.xf(M.cylinder(0.12, w, 8, base=False), (0, 0.35, 0), (0, 0, 90)), C["dark_steel"], kind="blade",
          axis="x", pivot=(0, 0.35, 0))
    m.anchors["exhaust"] = (w / 2, 1.8, 0.0)
    return m


@asset("electric_motor", "an electric motor with a spinning shaft", ["machine", "energy"], aliases=["motor", "e_motor"])
def electric_motor(color="#2cc7b8"):
    c = col(color, C["teal"])
    m = Model().add("body", M.xf(M.cylinder(0.6, 1.6, 14, base=False), (0, 0.7, 0), (0, 0, 90)), c, shell=True)
    for k in range(6):
        m.add("fin", M.xf(M.torus(0.62, 0.04, 14, 4), (-0.6 + k * 0.24, 0.7, 0), (0, 0, 90)), "#1f8f85")
    m.add("coil", M.xf(M.cylinder(0.45, 1.2, 10, base=False), (0, 0.7, 0), (0, 0, 90)), C["copper"])
    m.add("shaft", M.xf(M.cylinder(0.08, 2.6, 8, base=False), (0.4, 0.7, 0), (0, 0, 90)), C["steel"], kind="blade",
          axis="x", pivot=(0, 0.7, 0))
    m.add("feet", M.box(1.4, 0.15, 1.0, base=True), C["dark_steel"])
    return m


@asset("turbine", "a turbine: a casing with rotor blades inside that spin (steam, gas or water turns it)",
       ["energy", "machine"], aliases=["steam_turbine", "gas_turbine", "water_turbine", "rotor"])
def turbine(length=4.0, r=1.0, color="#8f9ba8"):
    m = Model().add("casing", M.xf(M.cylinder(r, length, 18, r_top=r * 0.7, base=False), (0, r + 0.3, 0), (0, 0, 90)),
                    col(color, C["steel"]), shell=True)
    hub = (0.0, r + 0.3, 0.0)
    rotor = [M.xf(M.cylinder(0.15, length * 0.95, 8, base=False), hub, (0, 0, 90))]
    for x in np.linspace(-length * 0.35, length * 0.35, 4):
        for a in range(0, 360, 45):
            blade = M.xf(M.box(0.25, r * 0.7, 0.08), (0, r * 0.42, 0), (0, 20, 0))  # one blade, pointing up
            rotor.append(M.xf(blade, (float(x) + hub[0], hub[1], hub[2]), (a, 0, 0)))
    m.add("rotor", M.merge(*rotor), C["gold"], kind="blade", axis="x", pivot=hub)
    m.add("stand", M.box(length * 0.6, 0.3, r * 1.4, base=True), C["dark_steel"])
    m.anchors["inlet"] = (-length / 2, r + 0.3, 0.0)
    m.anchors["outlet"] = (length / 2, r + 0.3, 0.0)
    return m


@asset("boiler", "a boiler: a horizontal tank over a fire box (fire glows, steam goes out)", ["energy", "machine"],
       aliases=["steam_boiler", "heater", "water_heater"])
def boiler(color="#b04a3c"):
    m = Model().add("tank", M.xf(M.cylinder(1.0, 4.0, 16, base=False), (0, 1.9, 0), (0, 0, 90)), col(color, "#b04a3c"),
                    shell=True)
    m.add("water", M.xf(M.cylinder(0.92, 3.8, 16, base=False), (0, 1.9, 0), (0, 0, 90), s=(1, 1, 1)), C["water"],
          opacity=0.85)
    m.add("firebox", M.box(3.6, 0.9, 1.6, base=True), C["dark_steel"], shell=True)
    m.add("fire", M.merge(*[M.xf(M.cone(0.25, 0.6, 6), (x, 0.2, 0)) for x in (-1.2, -0.4, 0.4, 1.2)]), C["fire"],
          emissive=0.9, kind="flame")
    m.add("pipe", M.tube([(1.2, 2.8, 0), (1.2, 3.6, 0), (2.6, 3.6, 0)], 0.15, 8), C["steel"])
    m.anchors["outlet"] = (2.6, 3.6, 0.0)
    return m


@asset("furnace", "a furnace / kiln with a glowing hot mouth", ["industry", "fire"], aliases=["kiln", "oven", "blast_furnace", "smelter"])
def furnace(color="#5b6672"):
    m = Model().add("body", M.cylinder(1.6, 4.0, 12, r_top=1.0), col(color, C["dark_steel"]), shell=True)
    m.add("mouth", M.xf(M.box(1.2, 1.0, 0.1), (0, 1.0, 1.52)), C["fire"], emissive=1.0, kind="flame")
    m.add("chimney", M.xf(M.cylinder(0.4, 2.5, 8), (0, 4.0, 0)), C["black"])
    m.anchors["exhaust"] = (0.0, 6.6, 0.0)
    return m


@asset("conveyor", "a conveyor belt with rollers and boxes riding on it (things flow along it)",
       ["industry", "machine"], aliases=["conveyor_belt", "belt", "assembly_line", "production_line"])
def conveyor(length=8.0, color="#2a2a2e", items=4):
    m = Model().add("belt", M.xf(M.box(length, 0.15, 1.2, base=True), (0, 0.9, 0)), col(color, C["black"]))
    for x in np.linspace(-length / 2 + 0.3, length / 2 - 0.3, max(2, int(length))):
        c = (float(x), 0.82, 0.0)
        m.add("roller", M.xf(M.cylinder(0.12, 1.3, 8, base=False), c, (90, 0, 0)), C["steel"], kind="blade", axis="z",
              pivot=c)
    for x in (-length / 2 + 0.4, length / 2 - 0.4):
        m.add("leg", M.xf(M.box(0.15, 0.85, 1.0, base=True), (x, 0, 0)), C["dark_steel"])
    for k in range(int(items)):
        m.add("box", M.xf(M.box(0.6, 0.5, 0.6, base=True), (-length / 2 + 1 + k * length / max(1, int(items)), 1.05, 0)),
              "#c69c6d")
    m.paths["flow"] = [(-length / 2, 1.3, 0.0), (length / 2, 1.3, 0.0)]
    return m


@asset("valve", "a pipe valve with a hand wheel (turns with spin)", ["industry", "water"], aliases=["tap", "faucet", "gate_valve"])
def valve(color="#d9534f"):
    m = Model().add("pipe", M.xf(M.cylinder(0.2, 2.0, 10, base=False), (0, 0.5, 0), (0, 0, 90)), C["steel"])
    m.add("body", M.xf(M.sphere(0.35, 1), (0, 0.5, 0)), C["dark_steel"])
    m.add("stem", M.xf(M.cylinder(0.05, 0.7, 6), (0, 0.8, 0)), C["steel"])
    m.add("wheel", M.xf(M.torus(0.35, 0.05, 12, 4), (0, 1.5, 0)), col(color, C["red"]), kind="blade", axis="y")
    m.paths["flow"] = [(-1.0, 0.5, 0.0), (1.0, 0.5, 0.0)]
    return m


@asset("fan", "a big fan / ventilator with spinning blades", ["machine"], aliases=["ventilator", "propeller_fan", "air_fan"])
def fan(r=1.2, color="#9aa3ab"):
    hub = (0.0, r + 0.4, 0.0)
    m = Model().add("stand", M.box(0.2, r + 0.4, 0.2, base=True), C["dark_steel"])
    m.add("blades", M.merge(M.xf(M.sphere(0.2, 0), hub),
                            *[M.xf(M.xf(M.box(0.3, r, 0.04, base=True), r=(0, 15, a)), hub) for a in (0, 120, 240)]),
          col(color, C["gray"]), kind="blade", axis="z", pivot=hub)
    m.add("ring", M.xf(M.torus(r * 1.1, 0.05, 20, 4), hub, (90, 0, 0)), C["dark_steel"])
    return m


@asset("battery", "a battery with a charge level (fill = charging, drain = using power)", ["energy", "electricity"],
       aliases=["batteries", "battery_pack", "accumulator", "power_bank", "cell_battery"])
def battery(h=2.0, color="#2a2a2e", level=0.6):
    m = Model().add("case", M.box(1.2, h, 0.8, base=True), col(color, C["black"]), opacity=0.55, shell=True)
    m.add("charge", M.xf(M.box(1.0, (h - 0.2) * float(level), 0.6, base=True), (0, 0.1, 0)), "#7bdc66", emissive=0.35,
          kind="liquid")
    m.add("cap", M.xf(M.box(0.4, 0.2, 0.3, base=True), (0, h, 0)), C["gray"])
    return m


@asset("transformer", "an electrical transformer box with cooling fins and insulators", ["energy", "electricity"],
       aliases=["substation", "transformer_box", "power_substation"])
def transformer(color="#7d8a96"):
    m = Model().add("tank", M.box(2.2, 2.0, 1.4, base=True), col(color, "#7d8a96"), shell=True)
    for k in range(6):
        m.add("fin", M.xf(M.box(0.06, 1.6, 0.4, base=True), (-0.9 + k * 0.36, 0.2, 0.9)), C["dark_steel"])
    for x in (-0.6, 0, 0.6):
        m.add("bushing", M.xf(M.cylinder(0.1, 0.8, 8), (x, 2.0, 0)), "#8fd3e8")
    m.add("coil", M.xf(M.cylinder(0.45, 1.4, 10), (0, 0.3, 0)), C["copper"])
    m.anchors["wire"] = (0.0, 2.8, 0.0)
    return m


@asset("robot_arm", "an industrial robot arm (it swings while it works)", ["industry", "machine"],
       aliases=["robot", "robotic_arm", "industrial_robot"])
def robot_arm(color="orange"):
    c = col(color, C["orange"])
    m = Model().add("base", M.cylinder(0.7, 0.5, 12), C["dark_steel"])
    m.add("arm", M.merge(M.xf(M.box(0.4, 2.0, 0.4, base=True), (0, 0.5, 0)),
                         M.xf(M.box(2.0, 0.35, 0.35), (0.9, 2.5, 0)),
                         M.xf(M.sphere(0.3, 0), (0, 2.5, 0)),
                         M.xf(M.box(0.25, 0.6, 0.25), (1.9, 2.2, 0))), c, kind="rocker", axis="y")
    return m


@asset("pumpjack", "an oil pumpjack (the horse head nods up and down)", ["energy", "industry"],
       aliases=["oil_well", "oil_pump", "nodding_donkey", "oil_rig", "oil"])
def pumpjack(color="#3b3f46"):
    c = col(color, "#3b3f46")
    m = Model().add("base", M.box(5.0, 0.3, 1.4, base=True), C["dark_steel"])
    m.add("post", M.xf(M.extrude([(-0.8, 0), (0.8, 0), (0.1, 3.0), (-0.1, 3.0)], 0.5), (0, 0.3, 0)), c)
    pivot = (0.0, 3.3, 0.0)
    beam = M.merge(M.xf(M.box(4.6, 0.3, 0.35), pivot), M.xf(M.box(0.6, 1.4, 0.4), (2.3, 2.9, 0)))
    m.add("beam", beam, C["orange"], kind="rocker", axis="z", pivot=pivot)
    m.add("well", M.xf(M.cylinder(0.25, 0.8, 8), (2.4, 0, 0)), C["steel"])
    return m


@asset("drill", "a drill / drilling rig tower", ["industry", "tool"], aliases=["drilling_rig", "derrick", "power_drill"])
def drill(h=10.0, color="#d9534f"):
    c = col(color, C["red"])
    m = Model()
    for x in (-1, 1):
        for z in (-1, 1):
            m.add("leg", M.tube([(x * 1.5, 0, z * 1.5), (x * 0.3, h, z * 0.3)], 0.1, 5, joints=False), c)
    m.add("bit", M.xf(M.cylinder(0.15, h * 0.8, 8), (0, -1.0, 0)), C["steel"], kind="blade", axis="y")
    m.add("floor", M.xf(M.box(3.4, 0.2, 3.4, base=True), (0, 1.5, 0)), C["dark_steel"])
    return m


# ---------------------------------------------------------------------------
# Nature and terrain
# ---------------------------------------------------------------------------


@asset("hill", "a grassy low poly hill", ["nature", "terrain"], aliases=["hills", "mound", "slope"])
def hill(r=6.0, h=3.0, color="grass", seed=3):
    g = _floor(M.jitter(M.xf(M.sphere(1.0, 1), (0, 0, 0), s=(r, h, r)), 0.12 * h, int(seed)))
    return Model().add("hill", g, col(color, C["grass"]))


@asset("mountain", "a rocky mountain with a snow cap", ["nature", "terrain"], aliases=["mountains", "peak"])
def mountain(r=8.0, h=10.0, color="#7d7a76", seed=5):
    m = Model().add("rock", _floor(M.jitter(M.cone(r, h, 9), 0.35, int(seed))), col(color, "#7d7a76"))
    m.add("snow", M.xf(M.jitter(M.cone(r * 0.32, h * 0.33, 9), 0.08, int(seed) + 1), (0, h * 0.68, 0)), C["white"])
    return m


@asset("volcano", "a volcano with glowing lava in the crater", ["nature", "terrain", "fire"], aliases=["lava", "eruption"])
def volcano(r=8.0, h=7.0, seed=7):
    m = Model().add("cone", _floor(M.jitter(M.cylinder(r, h, 12, r_top=r * 0.25), 0.3, int(seed))), "#5a4a42", shell=True)
    m.add("lava", M.xf(M.cylinder(r * 0.22, 0.3, 12), (0, h - 0.2, 0)), C["fire"], emissive=1.0, kind="flame")
    m.anchors["exhaust"] = (0.0, h + 0.3, 0.0)
    return m


@asset("rock", "a low poly rock / stone / boulder", ["nature"], aliases=["rocks", "stone", "stones", "boulder", "ore", "coal"])
def rock(size=1.0, color="#8d8a85", seed=2):
    g = M.jitter(M.sphere(0.6 * size, 1), 0.1 * size, int(seed))
    return Model().add("rock", M.xf(g, (0, 0.4 * size, 0), s=(1.2, 0.75, 1.0)), col(color, "#8d8a85"))


@asset("cloud", "a fluffy white cloud (use y for height; float makes it drift)", ["nature", "sky"], aliases=["clouds"])
def cloud(size=1.0, color="white", seed=1):
    rng = np.random.default_rng(int(seed))
    g = M.merge(*[M.xf(M.sphere(rng.uniform(0.5, 0.9) * size, 1), (float(x) * size, (1.0 + rng.uniform(-0.1, 0.2)) * size, 0))
                  for x in (-0.9, -0.3, 0.3, 0.9)])
    return Model().add("cloud", g, col(color, C["white"]), opacity=0.92)


@asset("sun", "the sun / a star (glowing ball with rays, use y for height)", ["space", "sky", "energy"],
       aliases=["star", "sunlight"])
def sun(r=2.0, color="#ffd76b"):
    c = (0.0, r * 1.8, 0.0)
    m = Model().add("sun", M.xf(M.sphere(r, 2), c), col(color, C["lamp"]), emissive=1.0)
    rays = [M.xf(M.xf(M.cone(0.2 * r, 0.6 * r, 5), (0, r * 1.08, 0)), c, (0, 0, a)) for a in range(0, 360, 30)]
    m.add("rays", M.merge(*rays), C["lamp"], emissive=0.8, kind="blade", axis="z", pivot=c)
    return m


@asset("water", "a flat area of water: lake, pond, sea or pool (see-through)", ["nature", "water", "liquid"],
       aliases=["lake", "pond", "sea", "ocean", "river", "pool_water", "swimming_pool"])
def water(w=12.0, d=8.0, depth=1.0, color="#3aa6d9"):
    m = Model().add("water", M.box(w, depth, d, base=True), col(color, C["water"]), opacity=0.72, kind="liquid")
    m.add("bed", M.xf(M.box(w + 0.4, 0.1, d + 0.4, base=True), (0, -0.1, 0)), "#5b6f63")
    return m


@asset("terrain", "rolling low poly ground with small hills (a landscape)", ["nature", "terrain"],
       aliases=["landscape", "land", "countryside", "valley"])
def terrain(w=30.0, d=30.0, color="grass", seed=9):
    n = 10
    rng = np.random.default_rng(int(seed))
    hgt = rng.uniform(0, 1.2, (n + 1, n + 1))
    hgt[0, :] = hgt[-1, :] = hgt[:, 0] = hgt[:, -1] = 0
    tris = []
    for i in range(n):
        for j in range(n):
            p = [(-w / 2 + w * (i + a) / n, hgt[i + a, j + b], -d / 2 + d * (j + b) / n) for a, b in ((0, 0), (1, 0), (1, 1), (0, 1))]
            tris += [p[0], p[3], p[2], p[0], p[2], p[1]]
    return Model().add("ground", M.geo(tris), col(color, C["grass"]))


@asset("crops", "a field of crops in rows (wheat, corn, vegetables)", ["farm", "nature"],
       aliases=["field_crops", "wheat", "corn", "crop", "farm_field", "plants"])
def crops(rows=6, length=8.0, color="#c9b23a"):
    m = Model().add("soil", M.box(length + 0.6, 0.1, rows * 0.8 + 0.4, base=True), "#6e4a2c")
    for r in range(int(rows)):
        z = -rows * 0.4 + 0.4 + r * 0.8
        m.add("row", M.merge(*[M.xf(M.cone(0.18, 0.9, 5), (float(x), 0.1, z)) for x in np.linspace(-length / 2, length / 2, 10)]),
              col(color, "#c9b23a"))
    return m


@asset("grass_patch", "a patch of grass tufts", ["nature"], aliases=["grass_tufts", "bushes", "shrub"])
def grass_patch(r=1.5, color="#4aa564", seed=4):
    rng = np.random.default_rng(int(seed))
    g = M.merge(*[M.xf(M.cone(0.12, rng.uniform(0.3, 0.6), 4), (rng.uniform(-r, r), 0, rng.uniform(-r, r)))
                  for _ in range(18)])
    return Model().add("grass", g, col(color, C["green"]))


# ---------------------------------------------------------------------------
# Fire, smoke, electricity, explosions
# ---------------------------------------------------------------------------


@asset("fire", "a campfire / flames that flicker (logs + glowing flames)", ["fire"],
       aliases=["flames", "flame", "campfire", "burning", "blaze", "bonfire"])
def fire(size=1.0, color="#ff7a1a"):
    m = Model().add("logs", M.merge(*[M.xf(M.cylinder(0.1 * size, 1.2 * size, 6, base=False), (0, 0.12 * size, 0),
                                           (90, a, 0)) for a in (0, 60, 120)]), C["trunk"])
    m.add("flame", M.xf(M.cone(0.45 * size, 1.4 * size, 7), (0, 0.15 * size, 0)), col(color, C["fire"]), emissive=0.9,
          kind="flame")
    m.add("flame", M.xf(M.cone(0.25 * size, 0.9 * size, 6), (0.15 * size, 0.15 * size, 0.1 * size)), C["lamp"],
          emissive=1.0, kind="flame")
    m.anchors["exhaust"] = (0.0, 1.6 * size, 0.0)
    return m


@asset("smoke_cloud", "a still puff of smoke or steam (use the smoke action for moving smoke)", ["fire", "sky"],
       aliases=["steam", "smoke", "fog", "exhaust_cloud", "pollution", "co2_cloud"])
def smoke_cloud(size=1.0, color="#b9c2c9", seed=6):
    m = cloud(size, color, seed)
    m.parts[0].opacity = 0.6
    return m


@asset("explosion", "an explosion / blast: a glowing spiky ball", ["fire"], aliases=["blast", "explosions"])
def explosion(size=1.0, color="#ff7a1a"):
    spikes = [M.xf(M.cone(0.35 * size, 1.4 * size, 5), (0, 0, 0), (a, b, 0))
              for a in range(0, 360, 60) for b in (0, 45, 90)]
    m = Model().add("core", M.xf(M.sphere(0.9 * size, 1), (0, 1.6 * size, 0)), C["lamp"], emissive=1.0)
    m.add("spikes", M.xf(M.merge(*spikes), (0, 1.6 * size, 0)), col(color, C["fire"]), emissive=0.9, kind="flame")
    return m


@asset("power_line", "a long power line: several poles with cables between them (sparks travel along)",
       ["energy", "electricity"], aliases=["power_lines", "transmission_line", "grid", "electric_grid", "pylon", "pylons"])
def power_line(length=24.0, poles=4, h=8.0):
    n = max(2, int(poles))
    m = Model()
    xs = np.linspace(-length / 2, length / 2, n)
    for x in xs:
        m.add("pylon", M.xf(M.cylinder(0.6, h, 4, r_top=0.12), (float(x), 0, 0)), C["steel"])
        m.add("arm", M.xf(M.box(0.2, 0.2, 3.0), (float(x), h - 0.6, 0)), C["steel"])
    pts = []
    for a, b in zip(xs[:-1], xs[1:]):
        for k in range(8):
            u = k / 8
            pts.append((float(a + (b - a) * u), h - 0.7 - 0.8 * math.sin(math.pi * u), 1.3))
    pts.append((float(xs[-1]), h - 0.7, 1.3))
    m.add("cable", M.tube(pts, 0.09, 5, joints=False), "#1f2428")
    m.add("cable", M.xf(M.tube(pts, 0.09, 5, joints=False), (0, 0, -2.6)), "#1f2428")
    m.paths["flow"] = pts
    return m


# ---------------------------------------------------------------------------
# Science: cells, viruses, molecules, atoms, DNA
# ---------------------------------------------------------------------------


@asset("cell", "a living cell (see-through membrane, nucleus, mitochondria; cutaway shows inside)",
       ["micro", "biology"], aliases=["cells", "animal_cell", "plant_cell", "human_cell"])
def cell(r=2.0, color="#f2a7b5", seed=3):
    rng = np.random.default_rng(int(seed))
    m = Model().add("membrane", M.xf(M.jitter(M.sphere(r, 2), 0.05 * r, int(seed)), (0, r * 1.15, 0)), col(color, C["pink"]),
                    opacity=0.45, shell=True)
    m.add("nucleus", M.xf(M.sphere(r * 0.35, 1), (0.2 * r, r, 0)), C["purple"])
    for _ in range(4):
        p = (rng.uniform(-0.5, 0.5) * r, r + rng.uniform(-0.4, 0.4) * r, rng.uniform(-0.5, 0.5) * r)
        m.add("mitochondria", M.xf(M.capsule(0.12 * r, 0.35 * r, 8), p, (0, rng.uniform(0, 180), 0)), C["orange"])
    m.anchors["inside"] = (0.0, r, 0.0)
    return m


@asset("virus", "a virus particle with spikes", ["micro", "biology"], aliases=["viruses", "coronavirus", "pathogen"])
def virus(r=1.0, color="#d9534f"):
    c = (0.0, r * 1.4, 0.0)
    m = Model().add("body", M.xf(M.sphere(r, 1), c), col(color, C["red"]))
    v, _ = M._icosahedron()
    spikes = []
    for d in v:
        p = np.asarray(c) + d * r * 1.15
        spikes.append(M.xf(M.sphere(0.13 * r, 0), tuple(p)))
        spikes.append(M.tube([tuple(np.asarray(c) + d * r * 0.9), tuple(p)], 0.04 * r, 4, joints=False))
    m.add("spikes", M.merge(*spikes), "#f6c445")
    return m


ATOM_COLORS = {"H": "#f4f1ea", "C": "#3b3f46", "O": "#d9534f", "N": "#3d8fd6", "S": "#f4c430", "Cl": "#4aa564",
               "Na": "#9a6ad6", "Fe": "#c8763c"}
MOLECULES = {  # atom list: (element, x, y, z) in units of one bond
    "H2O": [("O", 0, 0, 0), ("H", 0.8, 0.6, 0), ("H", -0.8, 0.6, 0)],
    "CO2": [("C", 0, 0, 0), ("O", 1.1, 0, 0), ("O", -1.1, 0, 0)],
    "O2": [("O", 0.55, 0, 0), ("O", -0.55, 0, 0)],
    "N2": [("N", 0.55, 0, 0), ("N", -0.55, 0, 0)],
    "H2": [("H", 0.4, 0, 0), ("H", -0.4, 0, 0)],
    "NH3": [("N", 0, 0, 0), ("H", 0.9, -0.4, 0), ("H", -0.45, -0.4, 0.78), ("H", -0.45, -0.4, -0.78)],
    "H2S": [("S", 0, 0, 0), ("H", 0.9, 0.6, 0), ("H", -0.9, 0.6, 0)],
    "NaCl": [("Na", 0.6, 0, 0), ("Cl", -0.6, 0, 0)],
    "CO": [("C", 0.55, 0, 0), ("O", -0.55, 0, 0)],
}


@asset("molecule", "a molecule from its formula: H2O, CO2, O2, N2, H2, NH3, H2S, NaCl, CO (use methane for CH4)",
       ["micro", "chemistry"], aliases=["molecules", "h2o", "co2", "oxygen", "water_molecule", "carbon_dioxide",
                                        "hydrogen", "nitrogen", "ammonia", "salt"])
def molecule(formula="H2O", scale=1.0):
    atoms = MOLECULES.get(str(formula).replace(" ", ""), MOLECULES["H2O"])
    m = Model()
    y = 1.0 * scale
    for el, x, yy, z in atoms:
        r = (0.22 if el == "H" else 0.34) * scale
        p = (x * 0.75 * scale, y + yy * 0.75 * scale, z * 0.75 * scale)
        m.add(el, M.xf(M.sphere(r, 1), p), ATOM_COLORS.get(el, C["gray"]))
        if (el, x, yy, z) != atoms[0] and len(atoms) > 2:
            m.add("bond", M.tube([(0, y, 0), p], 0.06 * scale, 6, joints=False), "#cfd6dc")
    if len(atoms) == 2:
        a, b = atoms
        m.add("bond", M.tube([(a[1] * 0.75 * scale, y, 0), (b[1] * 0.75 * scale, y, 0)], 0.08 * scale, 6, joints=False),
              "#cfd6dc")
    return m


@asset("atom", "an atom: nucleus with electrons on orbits that spin", ["micro", "chemistry", "physics"],
       aliases=["atoms", "nucleus", "electron", "proton", "neutron"])
def atom(r=1.6, color="#d9534f"):
    c = (0.0, r + 0.4, 0.0)
    nuc = [M.xf(M.sphere(0.2, 1), tuple(np.asarray(c) + d * 0.18)) for d in M._icosahedron()[0][:8]]
    m = Model().add("nucleus", M.merge(*nuc), col(color, C["red"]))
    for tilt, pos, axis in (((0, 0, 0), (r, 0, 0), "y"), ((90, 0, 0), (0, r, 0), "z"), ((0, 0, 90), (0, 0, r), "x")):
        m.add("orbit", M.xf(M.torus(r, 0.025, 28, 4), c, tilt), "#7df0ff", emissive=0.4, opacity=0.6)
        m.add("electron", M.xf(M.sphere(0.12, 1), tuple(np.asarray(c) + np.asarray(pos))), "#7df0ff", emissive=0.8,
              kind="blade", axis=axis, pivot=c)
    return m


@asset("dna", "a DNA double helix (spins)", ["micro", "biology"], aliases=["gene", "genes", "double_helix", "chromosome"])
def dna(h=6.0, color="#3d8fd6"):
    pts_a, pts_b, rungs = [], [], []
    for k in range(25):
        y = 0.3 + h * k / 24
        a = k * 0.55
        pa, pb = (math.cos(a), y, math.sin(a)), (-math.cos(a), y, -math.sin(a))
        pts_a.append(pa)
        pts_b.append(pb)
        if k % 2 == 0:
            rungs.append(M.tube([pa, pb], 0.06, 4, joints=False))
    m = Model().add("strand", M.merge(M.tube(pts_a, 0.12, 6), M.tube(pts_b, 0.12, 6)), col(color, C["blue"]),
                    kind="blade", axis="y")
    m.add("rungs", M.merge(*rungs), C["orange"], kind="blade", axis="y")
    return m


@asset("blood_cell", "red blood cells (flat discs with a dip in the middle)", ["micro", "biology"],
       aliases=["blood_cells", "red_blood_cell", "blood", "platelet"])
def blood_cell(r=0.8, color="#c0392b"):
    prof = [(0.0, 0.25), (r * 0.5, 0.18), (r * 0.9, 0.3), (r, 0.0), (r * 0.9, -0.3), (r * 0.5, -0.18), (0.0, -0.25)]
    g = M.lathe([(x, y) for x, y in prof], 16, close_bottom=False, close_top=False)
    return Model().add("cell", M.xf(g, (0, r + 0.2, 0), (90, 0, 0)), col(color, "#c0392b"))


@asset("neuron", "a nerve cell with branches (signals travel along it as sparks)", ["micro", "biology"],
       aliases=["nerve", "brain_cell", "neurons"])
def neuron(color="#9a6ad6", seed=8):
    rng = np.random.default_rng(int(seed))
    m = Model().add("body", M.xf(M.sphere(0.5, 1), (0, 1.0, 0)), col(color, C["purple"]), emissive=0.2)
    branches = []
    for k in range(6):
        a = k * 1.05
        pts = [(0, 1.0, 0), (math.cos(a) * 1.0, 1.0 + rng.uniform(-0.4, 0.4), math.sin(a) * 1.0),
               (math.cos(a + 0.3) * 1.8, 1.0 + rng.uniform(-0.8, 0.8), math.sin(a + 0.3) * 1.8)]
        branches.append(M.tube(pts, 0.06, 5, joints=False))
    axon = [(0, 1.0, 0), (2.0, 1.0, 0), (4.0, 1.2, 0), (6.0, 1.0, 0)]
    m.add("branches", M.merge(*branches, M.tube(axon, 0.1, 6)), col(color, C["purple"]))
    m.paths["flow"] = axon
    return m


@asset("crystal", "a crystal / gem / salt cube", ["chemistry", "nature"], aliases=["gem", "diamond", "crystals", "quartz", "ice"])
def crystal(size=1.0, color="#8fd3e8"):
    g = M.merge(M.xf(M.cylinder(0.4 * size, 1.0 * size, 6, r_top=0.4 * size), (0, 0, 0)),
                M.xf(M.cone(0.4 * size, 0.6 * size, 6), (0, 1.0 * size, 0)))
    return Model().add("crystal", g, col(color, "#8fd3e8"), opacity=0.8, emissive=0.15)


@asset("planet", "a planet (color and an optional ring like Saturn)", ["space"],
       aliases=["planets", "earth", "mars", "jupiter", "saturn", "globe"])
def planet(r=3.0, color="#3d8fd6", ring=False, land="#4aa564"):
    c = (0.0, r + 0.5, 0.0)
    m = Model().add("planet", M.xf(M.sphere(r, 2), c), col(color, C["blue"]))
    if land:
        rng = np.random.default_rng(3)
        patches = []
        for _ in range(6):
            d = rng.normal(0, 1, 3)
            d /= np.linalg.norm(d)
            patches.append(M.xf(M.sphere(r * 0.28, 1), tuple(np.asarray(c) + d * r * 0.86), s=(1.0, 0.6, 1.0)))
        m.add("land", M.merge(*patches), col(land, C["green"]))
    if ring:
        m.add("ring", M.xf(M.torus(r * 1.7, r * 0.12, 32, 4), c, (20, 0, 10), s=(1, 0.2, 1)), C["sand"])
    m.parts[0].kind = "blade"
    m.parts[0].pivot = c
    return m


@asset("moon", "a gray moon with craters", ["space"], aliases=["moons", "asteroid", "meteor", "comet"])
def moon(r=1.5, color="#b8b5ae", seed=5):
    c = (0.0, r + 0.3, 0.0)
    m = Model().add("moon", M.xf(M.jitter(M.sphere(r, 1), 0.06 * r, int(seed)), c), col(color, "#b8b5ae"))
    rng = np.random.default_rng(int(seed))
    craters = []
    for _ in range(5):
        d = rng.normal(0, 1, 3)
        d /= np.linalg.norm(d)
        craters.append(M.xf(M.sphere(r * 0.18, 0), tuple(np.asarray(c) + d * r * 0.95), s=(1, 0.4, 1)))
    m.add("crater", M.merge(*craters), "#8e8b85")
    return m


@asset("satellite", "a satellite with solar wings", ["space"], aliases=["satellites", "space_station", "probe"])
def satellite(color="#f6c445"):
    m = Model().add("body", M.xf(M.box(1.0, 1.0, 1.0), (0, 1.5, 0)), col(color, C["gold"]))
    for x in (-1.6, 1.6):
        m.add("wing", M.xf(M.box(2.0, 0.05, 0.9), (x, 1.5, 0)), "#1d3f72", kind="light")
    m.add("dish", M.xf(M.cone(0.45, 0.3, 10), (0, 2.1, 0), (180, 0, 0)), C["white"])
    return m


# ---------------------------------------------------------------------------
# Tools, everyday things, money
# ---------------------------------------------------------------------------


@asset("hammer", "a hammer", ["tool"], aliases=["mallet"])
def hammer(color="#a0703f"):
    m = Model().add("handle", M.xf(M.box(0.12, 1.4, 0.12, base=True), (0, 0, 0)), col(color, C["wood"]))
    m.add("head", M.xf(M.box(0.7, 0.25, 0.25), (0, 1.45, 0)), C["dark_steel"])
    return m


@asset("wrench", "a wrench / spanner", ["tool"], aliases=["spanner", "tools", "toolbox"])
def wrench(color="#8f9ba8"):
    c = col(color, C["steel"])
    m = Model().add("handle", M.xf(M.box(0.18, 1.5, 0.08, base=True), (0, 0.2, 0)), c)
    m.add("jaw", M.xf(M.torus(0.22, 0.08, 10, 4), (0, 1.85, 0), (90, 0, 0)), c)
    return m


@asset("magnifier", "a magnifying glass (look closer)", ["tool", "symbol"], aliases=["magnifying_glass"])
def magnifier(size=1.0):
    c = (0.0, 1.6 * size, 0.0)
    m = Model().add("rim", M.xf(M.torus(0.6 * size, 0.08 * size, 20, 4), c, (90, 0, 0)), C["black"])
    m.add("glass", M.xf(M.cylinder(0.56 * size, 0.04, 20, base=False), c, (90, 0, 0)), C["glass"], opacity=0.4)
    m.add("handle", M.xf(M.box(0.14 * size, 1.0 * size, 0.14 * size, base=True), (0, 0, 0)), C["wood"])
    return m


@asset("thermometer", "a thermometer (the red column rises with fill)", ["science", "symbol"],
       aliases=["temperature", "degrees", "temperature_gauge"])
def thermometer(h=3.0, level=0.5):
    m = Model().add("tube", M.xf(M.cylinder(0.18, h, 10), (0, 0.3, 0)), C["glass"], opacity=0.4, shell=True)
    m.add("bulb", M.xf(M.sphere(0.32, 1), (0, 0.3, 0)), C["red"], emissive=0.3)
    m.add("column", M.cylinder(0.1, 0.3 + h * float(level), 8), C["red"], emissive=0.3, kind="liquid")
    return m


@asset("gauge", "a pressure gauge / meter with a needle that swings", ["machine", "symbol"],
       aliases=["meter", "dial", "pressure_gauge", "speedometer", "power_meter"])
def gauge(r=1.0, color="#f4f1ea"):
    c = (0.0, r + 0.3, 0.0)
    m = Model().add("face", M.xf(M.cylinder(r, 0.12, 20, base=False), c, (90, 0, 0)), col(color, C["white"]))
    m.add("rim", M.xf(M.torus(r, 0.07, 20, 4), c, (90, 0, 0)), C["dark_steel"])
    m.add("red_zone", M.xf(M.box(0.35 * r, 0.12, 0.05), (0.6 * r, r + 0.3 + 0.45 * r, 0.07), (0, 0, -40)), C["red"])
    m.add("needle", M.xf(M.box(0.06, 0.8 * r, 0.04, base=True), (c[0], c[1], 0.09)), C["red"], kind="rocker", axis="z",
          pivot=c)
    m.add("post", M.box(0.12, r + 0.3, 0.12, base=True), C["dark_steel"])
    return m


@asset("clock", "a clock / timer with hands that turn", ["symbol", "time"], aliases=["timer", "watch", "stopwatch", "clocks"])
def clock(r=1.0):
    c = (0.0, r + 0.2, 0.0)
    m = Model().add("face", M.xf(M.cylinder(r, 0.15, 24, base=False), c, (90, 0, 0)), C["white"])
    m.add("rim", M.xf(M.torus(r, 0.08, 24, 4), c, (90, 0, 0)), C["dark_steel"])
    m.add("hand", M.xf(M.box(0.06, 0.8 * r, 0.04, base=True), (c[0], c[1], 0.1)), C["black"], kind="blade", axis="z",
          pivot=c)
    m.add("hand2", M.xf(M.box(0.08, 0.55 * r, 0.04, base=True), (c[0], c[1], 0.12), (0, 0, 120)), C["black"])
    return m


@asset("phone", "a smartphone with a screen that lights up", ["everyday", "electricity"],
       aliases=["smartphone", "mobile", "cellphone", "tablet"])
def phone(color="#2a2a2e"):
    m = Model().add("body", M.xf(M.box(0.8, 1.6, 0.1, base=True), (0, 0.1, 0)), col(color, C["black"]))
    m.add("screen", M.xf(M.box(0.7, 1.4, 0.02, base=True), (0, 0.2, 0.06)), "#2b3a4a", kind="light")
    return m


@asset("laptop", "a laptop / computer with a screen", ["everyday", "electricity"],
       aliases=["computer", "pc", "monitor", "server", "data_center"])
def laptop(color="#9aa3ab"):
    c = col(color, C["gray"])
    m = Model().add("base", M.box(1.6, 0.08, 1.1, base=True), c)
    m.add("lid", M.xf(M.box(1.6, 1.0, 0.06, base=True), (0, 0.08, -0.52), (-12, 0, 0)), c)
    m.add("screen", M.xf(M.box(1.45, 0.85, 0.02, base=True), (0, 0.15, -0.48), (-12, 0, 0)), "#2b3a4a", kind="light")
    return m


@asset("coin", "a gold coin (money)", ["money"], aliases=["coins", "money", "cent", "penny", "bitcoin"])
def coin(r=0.6, color="gold"):
    c = (0.0, r + 0.05, 0.0)
    m = Model().add("coin", M.xf(M.cylinder(r, 0.12, 18, base=False), c, (90, 0, 0)), col(color, C["gold"]),
                    kind="blade", axis="y", pivot=c)
    m.add("rim", M.xf(M.torus(r * 0.85, 0.04, 18, 4), c, (90, 0, 0)), "#d9a520")
    return m


@asset("coin_stack", "a stack of coins (count = how many)", ["money"], aliases=["coin_stacks", "savings", "profit"])
def coin_stack(coins=8, r=0.5, color="gold"):
    g = M.merge(*[M.xf(M.cylinder(r, 0.1, 16), (0.02 * math.sin(k), k * 0.11, 0.02 * math.cos(k))) for k in range(int(coins))])
    return Model().add("coins", g, col(color, C["gold"]))


@asset("cash", "a stack of green banknotes (cash)", ["money"], aliases=["banknotes", "dollars", "bills", "cash_stack", "euro"])
def cash(stacks=1, color="#6fbf73"):
    m = Model()
    for k in range(int(stacks)):
        m.add("notes", M.xf(M.box(1.4, 0.4, 0.7, base=True), (k * 1.6, 0, 0)), col(color, "#6fbf73"))
        m.add("band", M.xf(M.box(0.25, 0.42, 0.72, base=True), (k * 1.6, 0, 0)), C["white"])
    return m


@asset("money_bag", "a money bag with a $ sign", ["money"], aliases=["bag_of_money", "sack", "loot"])
def money_bag(color="#c9a66b"):
    m = Model().add("bag", M.lathe([(0.0, 0), (0.7, 0.2), (0.8, 0.7), (0.5, 1.3), (0.25, 1.45), (0.35, 1.7), (0.0, 1.75)],
                                   12), col(color, "#c9a66b"))
    m.add("sign", M.xf(M.box(0.1, 0.6, 0.05), (0, 0.8, 0.78)), C["dark_green"])
    m.add("sign", M.xf(M.torus(0.18, 0.05, 10, 4), (0, 0.8, 0.78), (90, 0, 0)), C["dark_green"])
    return m


@asset("gold_bar", "gold bars / ingots", ["money"], aliases=["gold", "gold_bars", "ingot", "treasure"])
def gold_bar(bars=3):
    m = Model()
    for k in range(int(bars)):
        m.add("bar", M.xf(M.cylinder(0.55, 0.35, 4, r_top=0.4), (k * 0.8 - (bars - 1) * 0.4, 0, 0), (0, 45, 0),
                          s=(1.4, 1, 0.7)), C["gold"], emissive=0.1)
    return m


# ---------------------------------------------------------------------------
# Symbols, charts and helpers
# ---------------------------------------------------------------------------


@asset("bar_chart", "a 3D bar chart (values = bar heights; grow makes them rise)", ["symbol", "data"],
       aliases=["chart", "graph", "statistics", "bars"])
def bar_chart(values=(2, 4, 3, 6), color="#2cc7b8"):
    vals = [float(v) for v in (values if isinstance(values, (list, tuple)) else [values])][:8] or [1.0]
    top = max(vals) or 1.0
    m = Model().add("base", M.box(len(vals) * 1.2 + 0.4, 0.12, 1.2, base=True), C["dark_steel"])
    for k, v in enumerate(vals):
        h = 4.0 * v / top
        m.add("bar", M.xf(M.box(0.8, max(0.1, h), 0.8, base=True), (-(len(vals) - 1) * 0.6 + k * 1.2, 0.12, 0)),
              col(color, C["teal"]) if k < len(vals) - 1 else C["orange"], emissive=0.15)
    return m


@asset("check_mark", "a green check mark (yes / correct / solved)", ["symbol"], aliases=["tick", "checkmark"])
def check_mark(size=1.0, color="#4aa564"):
    g = M.merge(M.xf(M.box(0.3, 0.8, 0.2), (-0.25, 0.4, 0), (0, 0, 40)), M.xf(M.box(0.3, 1.6, 0.2), (0.3, 0.85, 0), (0, 0, -30)))
    return Model().add("check", M.xf(g, (0, 0.6 * size, 0), s=size), col(color, C["green"]), emissive=0.3)


@asset("cross_mark", "a red X (no / wrong / problem)", ["symbol"], aliases=["x_mark", "forbidden"])
def cross_mark(size=1.0, color="#d9534f"):
    g = M.merge(M.xf(M.box(0.3, 1.8, 0.2), (0, 0, 0), (0, 0, 45)), M.xf(M.box(0.3, 1.8, 0.2), (0, 0, 0), (0, 0, -45)))
    return Model().add("cross", M.xf(g, (0, 1.2 * size, 0), s=size), col(color, C["red"]), emissive=0.3)


@asset("warning_sign", "a yellow warning triangle (danger)", ["symbol"], aliases=["warning", "danger", "hazard", "caution", "alert"])
def warning_sign(size=1.0):
    tri = M.extrude([(-0.9, 0), (0.9, 0), (0, 1.6)], 0.12)
    m = Model().add("sign", M.xf(tri, (0, 1.2 * size, 0), s=size), C["yellow"], emissive=0.2)
    m.add("mark", M.xf(M.box(0.16, 0.6, 0.14), (0, (1.2 + 0.75) * size, 0.02), s=size), C["black"])
    m.add("dot", M.xf(M.box(0.16, 0.16, 0.14), (0, (1.2 + 0.25) * size, 0.02), s=size), C["black"])
    m.add("post", M.box(0.1, 1.2 * size, 0.1, base=True), C["steel"])
    return m


@asset("heart", "a red heart (health, love, the heart muscle as a symbol)", ["symbol", "biology"], aliases=["hearts"])
def heart(size=1.0, color="#d9534f"):
    c = 1.4 * size
    g = M.merge(M.xf(M.sphere(0.5 * size, 1), (-0.36 * size, c + 0.15 * size, 0)),
                M.xf(M.sphere(0.5 * size, 1), (0.36 * size, c + 0.15 * size, 0)),
                M.xf(M.cone(0.8 * size, 1.15 * size, 8), (0, c + 0.12 * size, 0), (180, 0, 0)))
    return Model().add("heart", g, col(color, C["red"]), emissive=0.2)


@asset("question_mark", "a big question mark (mystery)", ["symbol"], aliases=["question"])
def question_mark(size=1.0, color="#f4c430"):
    pts = [(-0.45, 2.0), (-0.3, 2.35), (0.1, 2.45), (0.45, 2.2), (0.4, 1.8), (0.0, 1.5), (0.0, 1.1)]
    g = M.tube([(x * size, y * size, 0) for x, y in pts], 0.14 * size, 8)
    m = Model().add("curve", g, col(color, C["yellow"]), emissive=0.3)
    m.add("dot", M.xf(M.sphere(0.17 * size, 1), (0, 0.6 * size, 0)), col(color, C["yellow"]), emissive=0.3)
    return m


@asset("lightning_strike", "a lightning bolt from a cloud", ["energy", "sky", "electricity"], aliases=["thunder", "storm", "thunderstorm"])
def lightning_strike(h=6.0):
    m = cloud(1.6, "#6b7480", 2)
    for p in m.parts:
        p.geo = M.xf(p.geo, (0, h, 0))
    m.add("bolt", M.xf(M.bolt(h * 0.8, 1.2, 0.2), (0, h * 0.1, 0)), C["lamp"], emissive=1.0, kind="light")
    return m


# ---------------------------------------------------------------------------
# Containers, liquids and cross-section helpers
# ---------------------------------------------------------------------------


@asset("beaker", "a glass lab beaker / flask with liquid (fill / drain)", ["chemistry", "container", "liquid"],
       aliases=["flask", "test_tube", "laboratory", "jar"])
def beaker(r=0.8, h=1.8, liquid="#2cc7b8", level=0.6):
    m = Model().add("glass", M.cylinder(r, h, 16, caps=False), C["glass"], opacity=0.35, shell=True)
    m.add("bottom", M.cylinder(r, 0.05, 16), C["glass"], opacity=0.5)
    m.add("liquid", M.cylinder(r * 0.92, h * float(level), 16), col(liquid, C["teal"]), opacity=0.85, kind="liquid",
          emissive=0.1)
    m.anchors["surface"] = (0.0, h * float(level), 0.0)
    return m


@asset("barrel", "an oil drum / barrel", ["container", "industry"], aliases=["barrels", "drum", "oil_drum", "keg"])
def barrel(color="#3d8fd6"):
    m = Model().add("drum", M.cylinder(0.55, 1.4, 14), col(color, C["blue"]))
    for y in (0.35, 1.05):
        m.add("ring", M.xf(M.torus(0.56, 0.04, 14, 4), (0, y, 0)), C["dark_steel"])
    return m


@asset("bottle", "a bottle (plastic or glass)", ["container", "everyday"], aliases=["bottles", "plastic_bottle"])
def bottle(color="#7cc6ea", liquid="#3aa6d9"):
    prof = [(0.35, 0), (0.38, 0.9), (0.2, 1.25), (0.12, 1.45), (0.12, 1.6)]
    m = Model().add("bottle", M.lathe(prof, 12), col(color, C["sky_blue"]), opacity=0.45, shell=True)
    m.add("liquid", M.cylinder(0.32, 0.8, 12), col(liquid, C["water"]), kind="liquid")
    m.add("cap", M.xf(M.cylinder(0.14, 0.15, 10), (0, 1.6, 0)), C["red"])
    return m


@asset("glass_box", "a see-through box / container with liquid inside (good for showing what's inside)",
       ["container", "helper"], aliases=["aquarium", "chamber", "glass_tank", "box_tank"])
def glass_box(w=3.0, h=2.0, d=2.0, liquid="#3aa6d9", level=0.6):
    m = Model().add("glass", M.box(w, h, d, base=True), C["glass"], opacity=0.3, shell=True)
    if liquid:
        m.add("liquid", M.box(w * 0.95, h * float(level), d * 0.95, base=True), col(liquid, C["water"]), opacity=0.8,
              kind="liquid")
    m.anchors["surface"] = (0.0, h * float(level), 0.0)
    return m


@asset("ground_layers", "a cross section of the ground: soil, clay, rock and water layers (for underground scenes)",
       ["helper", "terrain", "cross_section"], aliases=["underground", "soil_layers", "earth_layers", "cross_section",
                                                       "geology", "aquifer", "bedrock"])
def ground_layers(w=10.0, d=4.0, depth=6.0):
    """A slab standing on the floor, like a cake cut open: rock at the bottom, grass on top."""
    layers = [("#6f6a66", 0.25), ("#3aa6d9", 0.12), ("#b08a5a", 0.25), ("#7a5232", 0.3), ("#6cbf4f", 0.08)]
    m = Model()
    y = 0.0
    for (color, frac), name in zip(layers, ("bedrock", "groundwater", "clay", "soil", "grass")):
        hgt = depth * frac
        m.add(name, M.xf(M.box(w, hgt, d, base=True), (0, y, 0)), color, opacity=0.9 if name == "groundwater" else 1.0)
        y += hgt
    m.anchors["label"] = (0.0, depth + 0.8, 0.0)
    m.anchors["inside"] = (0.0, depth * 0.3, 0.0)
    return m


@asset("puddle", "a puddle / spill of liquid on the ground", ["liquid", "water"], aliases=["spill", "leak", "oil_spill"])
def puddle(r=1.5, color="#3aa6d9", seed=2):
    g = _floor(M.jitter(M.cylinder(r, 0.05, 12), 0.03 * r, int(seed)))
    return Model().add("liquid", M.xf(g, s=(1.0, 1.0, 0.7)), col(color, C["water"]), opacity=0.8)


@asset("water_drop", "a water drop (rain, sweat, a leak)", ["liquid", "water"], aliases=["droplet", "raindrop", "water_drops"])
def water_drop(size=1.0, color="#3aa6d9"):
    prof = [(0.0, 0), (0.35 * size, 0.15 * size), (0.45 * size, 0.45 * size), (0.3 * size, 0.85 * size), (0.0, 1.3 * size)]
    return Model().add("drop", M.xf(M.lathe(prof, 14), (0, 0.1, 0)), col(color, C["water"]), opacity=0.85, emissive=0.1)


@asset("cutaway_wall", "a wall section cut open to show inside layers (insulation, pipes, wires)", ["helper", "building"],
       aliases=["wall_section", "insulation"])
def cutaway_wall(w=4.0, h=3.0):
    m = Model().add("brick", M.xf(M.box(w, h, 0.3, base=True), (0, 0, -0.35)), "#c0443e")
    m.add("insulation", M.box(w, h, 0.4, base=True), "#f2d36b")
    m.add("board", M.xf(M.box(w, h, 0.08, base=True), (0, 0, 0.25)), C["white"])
    m.add("pipe", M.tube([(-w / 2, 0.6, 0.05), (w / 2, 0.6, 0.05)], 0.08, 6, joints=False), C["copper"])
    m.add("wire", M.tube([(-w / 2, h - 0.5, 0.05), (w / 2, h - 0.5, 0.05)], 0.04, 4, joints=False), C["red"])
    return m


@asset("house_cutaway", "a house cut in half: rooms, floors, stairs and lamps inside", ["city", "building", "helper"],
       aliases=["dollhouse", "inside_house", "home_inside", "rooms"])
def house_cutaway(w=6.0, d=4.0, color="#f3e3c3"):
    c = col(color, "#f3e3c3")
    m = Model().add("back", M.xf(M.box(w, 5.0, 0.2, base=True), (0, 0, -d / 2)), c)
    for x in (-w / 2, w / 2):
        m.add("side", M.xf(M.box(0.2, 5.0, d, base=True), (x, 0, 0)), c)
    m.add("floor", M.box(w, 0.2, d, base=True), "#a0703f")
    m.add("floor2", M.xf(M.box(w, 0.2, d, base=True), (0, 2.5, 0)), "#a0703f")
    m.add("roof", M.xf(M.prism_roof(w + 0.4, d + 0.4, 1.6), (0, 5.0, 0)), "#b5523b")
    for x, y in ((-1.5, 2.2), (1.5, 2.2), (-1.5, 4.7), (1.5, 4.7)):
        m.add("lamp", M.xf(M.sphere(0.2, 1), (x, y, 0)), C["lamp"], kind="light")
    m.add("stairs", M.merge(*[M.xf(M.box(0.8, 0.3, 0.5, base=True), (w / 2 - 0.6, 0.2 + k * 0.3, -d / 2 + 0.4 + k * 0.33))
                              for k in range(8)]), "#7a5232")
    return m
