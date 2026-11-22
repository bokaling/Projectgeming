"""Built-in example: "How cow poop becomes electricity" (script + scene plan).

It is (1) the demo video, (2) the example the AI sees when it writes a new scene plan, and (3) a test.
"""

from __future__ import annotations

COW_POOP_SCRIPT = """[TITLE] How Cow Poop Becomes Electricity
[STYLE] clean low poly farm, dark teal studio, glowing grid floor
[SCENE] wide shot of a dairy barn full of cows
NARRATOR: This farm runs 150 homes on cow poop.
[SCENE] close on the cows, manure piles up in the alley
NARRATOR: Its 2,000 cows make 130 tons of manure. Every single day.
[SCENE] a scraper drags the manure down the barn alley
NARRATOR: A scraper drags it down the alley,
[SCENE] a tractor hauls the manure to the storage tank
NARRATOR: and a tractor hauls it to a giant storage tank.
[SCENE] the storage tank from above, a hard crust forms on top
NARRATOR: Left alone, a hard crust forms on top, and the gas gets trapped underneath.
[SCENE] the agitator spins and breaks up the crust
NARRATOR: So an agitator spins non-stop to keep it mixed.
[SCENE] slurry flows through a pipe into the sealed digester
NARRATOR: Then it's pumped into a sealed digester. No oxygen, a steady 38 degrees, like a giant stomach.
[SCENE] cutaway of the digester, the camera dives into the liquid
NARRATOR: Inside, trillions of bacteria feast on the manure for 21 days.
[SCENE] zoomed in: bacteria release methane molecules
NARRATOR: And as they eat, they burp out methane, the same gas in your kitchen stove.
[SCENE] the gas dome swells, gas rushes down the yellow pipe
NARRATOR: The gas swells the dome, then rushes down a pipe
[SCENE] the generator burns the gas, sparks run along the wires
NARRATOR: into a big engine that burns it and spins a generator.
[SCENE] the houses light up one by one
NARRATOR: 4,000 kilowatt hours a day. Enough to light up 150 homes.
[SCENE] back at the digester, the dome glows red
NARRATOR: But that dome hides a second gas. One breath of it can kill you.
"""

COW_POOP_PLAN = {
    "title": "How Cow Poop Becomes Electricity",
    "areas": [
        {"id": "barn", "x": 0, "z": 0}, {"id": "storage", "x": 26, "z": 0}, {"id": "digester", "x": 44, "z": 0},
        {"id": "micro", "x": 44, "z": -90, "micro": True}, {"id": "power", "x": 60, "z": 0},
        {"id": "town", "x": 80, "z": 0},
    ],
    "objects": [
        {"id": "barn1", "asset": "barn", "area": "barn", "pos": [0, 0], "params": {"length": 14, "width": 9}},
        {"id": "cows", "asset": "cow", "area": "barn", "pos": [0, -2.3], "rot": -90, "count": 5, "layout": "row",
         "spacing": 2.6},
        {"id": "piles", "asset": "manure", "area": "barn", "pos": [0.5, 0.9], "count": 4, "layout": "row",
         "spacing": 3.0, "params": {"size": 0.8}, "hidden": True},
        {"id": "bigpile", "asset": "manure", "area": "barn", "pos": [8.8, 0.9], "params": {"size": 1.6}, "hidden": True},
        {"id": "scraper1", "asset": "scraper", "area": "barn", "pos": [-6.4, 0.9]},
        {"id": "tractor1", "asset": "tractor", "area": "barn", "pos": [10.5, 4.2]},
        {"id": "tank1", "asset": "tank", "area": "storage", "pos": [0, 0],
         "params": {"r": 4.0, "h": 2.6, "crust": True, "level": 0.75}},
        {"id": "mixer1", "asset": "agitator", "area": "storage", "pos": [-1.6, 0.6], "params": {"h": 3.4}},
        {"id": "pipe1", "asset": "pipe", "area": "storage", "pos": [4.1, 0],
         "params": {"length": 9.4, "height": 1.7, "color": "#7d8a93"}},
        {"id": "dig1", "asset": "digester", "area": "digester", "pos": [0, 0], "params": {"r": 4.5, "h": 4.0}},
        {"id": "gaspipe", "asset": "pipe", "area": "digester", "pos": [5.7, 0],
         "params": {"length": 8.7, "height": 8.02, "rise": -6.9, "color": "yellow"}},
        {"id": "germs", "asset": "bacteria", "area": "micro", "pos": [0, 0], "y": 1.0, "count": 5, "layout": "scatter",
         "spacing": 2.6},
        {"id": "germs2", "asset": "bacteria", "area": "micro", "pos": [1.0, -1.5], "y": 2.0, "count": 3,
         "layout": "scatter", "spacing": 2.4, "params": {"color": "#b37be0", "seed": 5}},
        {"id": "ch4", "asset": "methane", "area": "micro", "pos": [0, 0.5], "y": 2.0, "count": 6, "layout": "scatter",
         "spacing": 2.2, "hidden": True},
        {"id": "gen1", "asset": "generator", "area": "power", "pos": [0, 0]},
        {"id": "pole1", "asset": "power_pole", "area": "power", "pos": [4.5, 0]},
        {"id": "wire1", "asset": "wire", "area": "power", "pos": [1.8, 0],
         "params": {"length": 2.7, "h1": 1.2, "h2": 5.95, "sag": 0.2}},
        {"id": "wire2", "asset": "wire", "area": "power", "pos": [4.5, 0],
         "params": {"length": 9.0, "h1": 5.95, "h2": 5.95, "sag": 0.6}},
        {"id": "pole2", "asset": "power_pole", "area": "town", "pos": [-6.5, 0]},
        {"id": "wire3", "asset": "wire", "area": "town", "pos": [-6.5, -0.4],
         "params": {"length": 17.0, "h1": 5.95, "h2": 3.6, "sag": 0.5}},
        {"id": "homes", "asset": "house", "area": "town", "pos": [2.5, 1.6], "count": 5, "layout": "row", "spacing": 4.3},
        {"id": "trees", "asset": "tree", "area": "town", "pos": [2.0, -4.6], "count": 5, "layout": "scatter",
         "spacing": 3.2},
    ],
    "scenes": [
        {"camera": {"move": "orbit", "target": "barn1", "angle": 18, "to_angle": 58, "height": 22},
         "actions": [],
         "labels": [],
         "keywords": [{"text": "150 homes", "kind": "number", "at": "150"},
                      {"text": "cow poop", "kind": "problem", "at": "poop"}]},
        {"camera": {"move": "push_in", "target": "cows", "angle": 12, "height": 16},
         "actions": [{"do": "appear", "target": "piles", "at": "manure"},
                     {"do": "grow", "target": "piles", "at": "manure", "from": 0.3, "to": 1.0, "dur": 1.6}],
         "labels": [{"target": "piles", "text": "Manure", "kind": "part", "at": "manure"}],
         "keywords": [{"text": "2,000 cows", "kind": "number", "at": "2,000"},
                      {"text": "130 tons a day", "kind": "number", "at": "130"}]},
        {"camera": {"move": "follow", "target": "scraper1", "angle": 12, "height": 24, "distance": 13},
         "actions": [{"do": "move", "target": "scraper1", "to": [6.6, 0.9], "at": 0.05},
                     {"do": "disappear", "target": "piles", "at": 0.25, "stagger": 0.45},
                     {"do": "appear", "target": "bigpile", "at": 0.8}],
         "labels": [{"target": "scraper1", "text": "Scraper", "kind": "part", "at": "scraper"}],
         "keywords": []},
        {"camera": {"move": "follow", "target": "tractor1", "angle": 28, "height": 30, "distance": 16},
         "actions": [{"do": "disappear", "target": "bigpile", "at": 0.0},
                     {"do": "move", "target": "tractor1", "to": "tank1", "at": 0.1}],
         "labels": [{"target": "tractor1", "text": "Tractor", "kind": "part", "at": "tractor"}],
         "keywords": [{"text": "storage tank", "kind": "part", "at": "storage"}]},
        {"camera": {"move": "orbit", "target": "tank1", "angle": 25, "to_angle": 65, "height": 50},
         "actions": [{"do": "show_part", "target": "tank1.crust", "at": "crust"},
                     {"do": "shake", "target": "tank1", "at": "trapped"}],
         "labels": [{"target": "tank1", "text": "Hard crust", "kind": "problem", "at": "crust"}],
         "keywords": [{"text": "crust", "kind": "problem", "at": "crust"},
                      {"text": "gas trapped", "kind": "problem", "at": "trapped"}]},
        {"camera": {"move": "push_in", "target": "mixer1", "angle": 40, "height": 38, "distance": 15},
         "actions": [{"do": "spin", "target": "mixer1", "at": "spins", "speed": 1.6},
                     {"do": "bubbles", "target": "tank1", "at": "spins"},
                     {"do": "hide_part", "target": "tank1.crust", "at": "mixed"}],
         "labels": [{"target": "mixer1", "text": "Agitator", "kind": "part", "at": "agitator"}],
         "keywords": [{"text": "non-stop", "kind": "info", "at": "non-stop"}]},
        {"camera": {"move": "orbit", "target": "dig1", "angle": -45, "to_angle": 5, "height": 26, "zoom": 0.8},
         "actions": [{"do": "flow", "target": "pipe1", "at": 0.0, "color": "#6e4a2c"},
                     {"do": "glow", "target": "dig1", "at": "38"}],
         "labels": [{"target": "dig1", "text": "Digester", "kind": "part", "at": "digester"}],
         "keywords": [{"text": "no oxygen", "kind": "info", "at": "oxygen"},
                      {"text": "38 °C", "kind": "number", "at": "38"}]},
        {"camera": {"move": "zoom_into", "target": "dig1", "angle": 15, "height": 22},
         "actions": [{"do": "cutaway", "target": "dig1", "at": 0.0},
                     {"do": "bubbles", "target": "dig1", "at": 0.1}],
         "labels": [{"target": "dig1", "text": "Trillions of bacteria", "kind": "info", "at": "bacteria"}],
         "keywords": [{"text": "21 days", "kind": "number", "at": "21"}]},
        {"camera": {"move": "orbit", "target": "germs", "angle": 10, "to_angle": 50, "height": 14, "zoom": 1.6},
         "actions": [{"do": "float", "target": "germs", "at": 0.0}, {"do": "float", "target": "germs2", "at": 0.0},
                     {"do": "appear", "target": "ch4", "at": "burp"}, {"do": "float", "target": "ch4", "at": "burp"},
                     {"do": "bubbles", "target": "germs", "at": 0.0, "color": "#c9a46a"}],
         "labels": [{"target": "ch4", "text": "Methane CH4", "kind": "part", "at": "methane"}],
         "keywords": [{"text": "methane", "kind": "part", "at": "methane"}]},
        {"camera": {"move": "pull_out", "target": "dig1", "angle": 55, "height": 24},
         "actions": [{"do": "glow", "target": "dig1", "at": "swells"},
                     {"do": "flow", "target": "gaspipe", "at": "rushes", "color": "#9fe870", "speed": 5}],
         "labels": [{"target": "gaspipe", "text": "Gas pipe", "kind": "part", "at": "pipe"}],
         "keywords": [{"text": "biogas", "kind": "part", "at": "gas"}]},
        {"camera": {"move": "push_in", "target": "gen1", "angle": 35, "height": 20, "zoom": 0.75},
         "actions": [{"do": "spin", "target": "gen1", "at": "burns", "speed": 3},
                     {"do": "smoke", "target": "gen1", "at": "burns"},
                     {"do": "light_on", "target": "gen1", "at": "generator"},
                     {"do": "sparks", "target": "wire1", "at": "generator"},
                     {"do": "sparks", "target": "wire2", "at": "generator"}],
         "labels": [{"target": "gen1", "text": "Generator", "kind": "part", "at": "generator"}],
         "keywords": [{"text": "burns the gas", "kind": "info", "at": "burns"}]},
        {"camera": {"move": "fly_over", "target": "homes", "angle": 10},
         "actions": [{"do": "sparks", "target": "wire3", "at": 0.0},
                     {"do": "light_on", "target": "homes", "at": "light"}],
         "labels": [{"target": "homes", "text": "{n} homes", "kind": "number", "at": "light", "from": 0, "to": 150}],
         "keywords": [{"text": "4,000 kWh a day", "kind": "number", "at": "4,000"}]},
        {"camera": {"move": "push_in", "target": "dig1", "angle": 25, "height": 28},
         "actions": [{"do": "alarm", "target": "dig1", "at": "second"}],
         "labels": [{"target": "dig1", "text": "H2S gas", "kind": "problem", "at": "gas"}],
         "keywords": [{"text": "deadly gas", "kind": "problem", "at": "kill"}]},
    ],
}
