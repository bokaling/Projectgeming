"""Built-in example: "How cow poop becomes electricity" (script + scene plan).

It is (1) the demo video, (2) the example the AI sees when it writes a new scene plan, and (3) a test.
"""

from __future__ import annotations

COW_POOP_SCRIPT = """[TITLE] How Cow Poop Becomes Electricity
[STYLE] clean low poly farm, dark teal studio, glowing grid floor
[SCENE] close up: a cow drops a huge poop
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
    "areas": [{"id": "barn"}, {"id": "storage"}, {"id": "digester"}, {"id": "micro", "micro": True}, {"id": "power"},
              {"id": "town"}],
    "objects": [
        {"id": "barn1", "asset": "barn", "area": "barn", "pos": [0, 0], "params": {"length": 18, "width": 11}},
        {"id": "cows", "asset": "cow", "area": "barn", "pos": [0, -1.7], "rot": 90, "count": 10, "layout": "row",
         "spacing": 1.65},
        {"id": "hero", "asset": "cow", "area": "barn", "pos": [12.5, 2.5], "rot": 20, "params": {"seed": 7}},
        {"id": "poop", "asset": "manure", "area": "barn", "pos": [11.3, 2.95], "params": {"size": 1.5}, "hidden": True},
        {"id": "piles", "asset": "manure", "area": "barn", "pos": [0.8, 0.7], "count": 5, "layout": "row",
         "spacing": 3.3, "hidden": True},
        {"id": "bigpile", "asset": "manure", "area": "barn", "pos": [8.0, 0.7], "params": {"size": 1.6}, "hidden": True},
        {"id": "scraper1", "asset": "scraper", "area": "barn", "pos": [-8.0, 0.7]},
        {"id": "tractor1", "asset": "tractor", "area": "barn", "pos": [12.0, 7.6]},
        {"id": "tank1", "asset": "tank", "area": "storage", "pos": [0, 0],
         "params": {"r": 4.5, "h": 3.0, "crust": True, "level": 0.75}},
        {"id": "mixer1", "asset": "agitator", "area": "storage", "pos": [-1.6, 0.6], "params": {"h": 3.8}},
        {"id": "pipe1", "asset": "pipe", "area": "storage", "pos": [4.6, 0],
         "params": {"length": 7.0, "rise": 0.0, "height": 0.6}},
        {"id": "dig1", "asset": "digester", "area": "digester", "pos": [0, 0], "params": {"r": 4.5, "h": 4.0}},
        {"id": "gaspipe", "asset": "pipe", "area": "digester", "pos": [5.7, 0],
         "params": {"length": 6.0, "rise": -6.0, "height": 7.4, "color": "yellow"}},
        {"id": "germs", "asset": "bacteria", "area": "micro", "pos": [0, 0], "y": 1.0, "count": 5, "layout": "scatter",
         "spacing": 2.2, "params": {"color": "#7bdc66"}},
        {"id": "germs2", "asset": "bacteria", "area": "micro", "pos": [1.0, -1.5], "y": 2.0, "count": 3,
         "layout": "scatter", "spacing": 2.5, "params": {"color": "#c68cf2"}},
        {"id": "ch4", "asset": "methane", "area": "micro", "pos": [0, 0.5], "y": 2.0, "count": 6, "layout": "scatter",
         "spacing": 1.8, "hidden": True},
        {"id": "gen1", "asset": "generator", "area": "power", "pos": [0, 0]},
        {"id": "pole1", "asset": "power_pole", "area": "power", "pos": [4.5, 0]},
        {"id": "wire1", "asset": "wire", "area": "power", "pos": [1.8, 0],
         "params": {"length": 2.7, "h1": 1.3, "h2": 5.9, "sag": 0.2}},
        {"id": "wire2", "asset": "wire", "area": "power", "pos": [4.5, 0],
         "params": {"length": 9.0, "h1": 5.9, "h2": 5.9, "sag": 0.6}},
        {"id": "pole2", "asset": "power_pole", "area": "town", "pos": [-8.5, 0]},
        {"id": "wire3", "asset": "wire", "area": "town", "pos": [-8.5, -0.4],
         "params": {"length": 6.0, "h1": 5.9, "h2": 2.4, "sag": 0.4}},
        {"id": "homes", "asset": "house", "area": "town", "pos": [2.5, 1.6], "count": 4, "layout": "row", "spacing": 6.2},
        {"id": "trees", "asset": "tree", "area": "town", "pos": [2.0, -5.6], "count": 5, "layout": "scatter",
         "spacing": 3.0},
    ],
    "scenes": [
        {"camera": {"move": "close_up", "target": "hero", "angle": 150, "height": 14},
         "actions": [{"do": "drop", "target": "poop", "at": "poop", "from": 1.2}],
         "labels": [{"target": "poop", "text": "50 kg", "kind": "number", "at": "poop"}],
         "keywords": [{"text": "150 homes", "kind": "number", "at": "150"},
                      {"text": "on cow poop", "kind": "problem", "at": "poop"}]},
        {"camera": {"move": "push_in", "target": "cows", "angle": -20, "height": 14},
         "actions": [{"do": "appear", "target": "piles", "at": "manure"},
                     {"do": "grow", "target": "piles", "at": "manure", "from": 0.3, "to": 1.0, "dur": 1.6}],
         "labels": [{"target": "piles", "text": "Manure", "kind": "part", "at": "manure"}],
         "keywords": [{"text": "2,000 cows", "kind": "number", "at": "2,000"},
                      {"text": "130 tons a day", "kind": "number", "at": "130"}]},
        {"camera": {"move": "follow", "target": "scraper1", "angle": 20, "height": 26},
         "actions": [{"do": "move", "target": "scraper1", "to": [6.0, 0.7], "at": 0.05},
                     {"do": "disappear", "target": "piles", "at": 0.25, "stagger": 0.45},
                     {"do": "appear", "target": "bigpile", "at": 0.8}],
         "labels": [{"target": "scraper1", "text": "Scraper", "kind": "part", "at": "scraper"}],
         "keywords": [{"text": "the scraper", "kind": "part", "at": "scraper"}]},
        {"camera": {"move": "follow", "target": "tractor1", "angle": 35, "height": 22},
         "actions": [{"do": "disappear", "target": "bigpile", "at": 0.0},
                     {"do": "move", "target": "tractor1", "to": "tank1", "at": 0.1}],
         "labels": [{"target": "tractor1", "text": "Tractor", "kind": "part", "at": "tractor"}],
         "keywords": [{"text": "storage tank", "kind": "part", "at": "storage"}]},
        {"camera": {"move": "orbit", "target": "tank1", "angle": 25, "to_angle": 60, "height": 42},
         "actions": [{"do": "show_part", "target": "tank1.crust", "at": "crust"},
                     {"do": "shake", "target": "tank1", "at": "trapped"}],
         "labels": [{"target": "tank1", "text": "Hard crust", "kind": "problem", "at": "crust"}],
         "keywords": [{"text": "a hard crust", "kind": "problem", "at": "crust"},
                      {"text": "gas trapped", "kind": "problem", "at": "trapped"}]},
        {"camera": {"move": "close_up", "target": "mixer1", "angle": 40, "height": 30},
         "actions": [{"do": "spin", "target": "mixer1", "at": "spins", "speed": 1.6},
                     {"do": "bubbles", "target": "tank1", "at": "spins"},
                     {"do": "hide_part", "target": "tank1.crust", "at": "mixed"}],
         "labels": [{"target": "mixer1", "text": "Agitator", "kind": "part", "at": "agitator"}],
         "keywords": [{"text": "the agitator", "kind": "part", "at": "agitator"},
                      {"text": "non-stop", "kind": "info", "at": "non-stop"}]},
        {"camera": {"move": "orbit", "target": "dig1", "angle": -45, "to_angle": 0, "height": 20},
         "actions": [{"do": "flow", "target": "pipe1", "at": 0.0, "color": "#6e4a2c"},
                     {"do": "glow", "target": "dig1", "at": "38"}],
         "labels": [{"target": "dig1", "text": "Digester", "kind": "part", "at": "digester"}],
         "keywords": [{"text": "no oxygen", "kind": "info", "at": "oxygen"},
                      {"text": "38 °C", "kind": "number", "at": "38"}]},
        {"camera": {"move": "zoom_into", "target": "dig1", "angle": 15, "height": 18},
         "actions": [{"do": "cutaway", "target": "dig1", "at": 0.0},
                     {"do": "bubbles", "target": "dig1", "at": 0.1}],
         "labels": [{"target": "dig1", "text": "Bacteria inside", "kind": "info", "at": "bacteria"}],
         "keywords": [{"text": "21 days", "kind": "number", "at": "21"}]},
        {"camera": {"move": "orbit", "target": "germs", "angle": 10, "to_angle": 50, "height": 14, "zoom": 1.6},
         "actions": [{"do": "float", "target": "germs", "at": 0.0}, {"do": "float", "target": "germs2", "at": 0.0},
                     {"do": "appear", "target": "ch4", "at": "burp"}, {"do": "float", "target": "ch4", "at": "burp"},
                     {"do": "bubbles", "target": "germs", "at": 0.0, "color": "#c9a46a"}],
         "labels": [{"target": "ch4", "text": "Methane CH4", "kind": "part", "at": "methane"}],
         "keywords": [{"text": "methane", "kind": "part", "at": "methane"}]},
        {"camera": {"move": "pull_out", "target": "dig1", "angle": 55, "height": 22},
         "actions": [{"do": "glow", "target": "dig1", "at": "swells"},
                     {"do": "flow", "target": "gaspipe", "at": "rushes", "color": "#9fe870", "speed": 5}],
         "labels": [{"target": "gaspipe", "text": "Gas pipe", "kind": "part", "at": "pipe"}],
         "keywords": [{"text": "biogas", "kind": "part", "at": "gas"}]},
        {"camera": {"move": "push_in", "target": "gen1", "angle": 35, "height": 18},
         "actions": [{"do": "spin", "target": "gen1", "at": "burns", "speed": 3},
                     {"do": "smoke", "target": "gen1", "at": "burns"},
                     {"do": "light_on", "target": "gen1", "at": "generator"},
                     {"do": "sparks", "target": "wire1", "at": "generator"},
                     {"do": "sparks", "target": "wire2", "at": "generator"}],
         "labels": [{"target": "gen1", "text": "Generator", "kind": "part", "at": "generator"}],
         "keywords": [{"text": "burns the gas", "kind": "info", "at": "burns"}]},
        {"camera": {"move": "orbit", "target": "homes", "angle": 15, "to_angle": -15, "height": 50, "zoom": 1.5},
         "actions": [{"do": "sparks", "target": "wire3", "at": 0.0},
                     {"do": "light_on", "target": "homes", "at": "light"}],
         "labels": [{"target": "homes", "text": "{n} homes", "kind": "number", "at": "light", "from": 0, "to": 150}],
         "keywords": [{"text": "4,000 kWh a day", "kind": "number", "at": "4,000"}]},
        {"camera": {"move": "push_in", "target": "dig1", "angle": 25, "height": 24},
         "actions": [{"do": "alarm", "target": "dig1", "at": "second"}],
         "labels": [{"target": "dig1", "text": "H2S gas", "kind": "problem", "at": "gas"}],
         "keywords": [{"text": "a deadly gas", "kind": "problem", "at": "kill"}]},
    ],
}
