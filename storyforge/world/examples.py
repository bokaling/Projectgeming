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
        {"id": "scraper1", "asset": "scraper", "area": "barn", "pos": [-8.0, 0.7]},
        {"id": "pit1", "asset": "pit", "area": "barn", "pos": [7.6, 0.7]},
        {"id": "tractor1", "asset": "tractor", "area": "barn", "pos": [12.0, 7.6]},
        {"id": "tank1", "asset": "tank", "area": "storage", "pos": [0, 0],
         "params": {"r": 4.5, "h": 3.0, "crust": True, "level": 0.75}},
        {"id": "mixer1", "asset": "agitator", "area": "storage", "pos": [-1.6, 0.6], "params": {"h": 3.8}},
        {"id": "pipe1", "asset": "pipe", "area": "storage", "from": "tank1.outlet", "to": "dig1.inlet"},
        {"id": "dig1", "asset": "digester", "area": "digester", "pos": [0, 0], "params": {"r": 4.5, "h": 4.0}},
        {"id": "gaspipe", "asset": "pipe", "area": "digester", "from": "dig1.gas_out", "to": "gen1.inlet",
         "params": {"color": "#f4c430", "height": 1.0}},
        {"id": "germs", "asset": "bacteria", "area": "micro", "pos": [0, 0], "y": 1.0, "count": 5, "layout": "scatter",
         "spacing": 2.2, "params": {"color": "#7bdc66"}},
        {"id": "germs2", "asset": "bacteria", "area": "micro", "pos": [1.0, -1.5], "y": 2.0, "count": 3,
         "layout": "scatter", "spacing": 2.5, "params": {"color": "#c68cf2"}},
        {"id": "ch4", "asset": "methane", "area": "micro", "pos": [0, 0.5], "y": 2.0, "count": 6, "layout": "scatter",
         "spacing": 1.8, "hidden": True},
        {"id": "gen1", "asset": "generator", "area": "power", "pos": [0, 0]},
        {"id": "pole1", "asset": "power_pole", "area": "power", "pos": [4.5, 0]},
        {"id": "wire1", "asset": "wire", "area": "power", "from": "gen1.outlet", "to": "pole1.wire"},
        {"id": "wire2", "asset": "wire", "area": "power", "from": "pole1.wire", "to": "pole2.wire"},
        {"id": "pole2", "asset": "power_pole", "area": "town", "pos": [-8.5, 0]},
        {"id": "wire3", "asset": "wire", "area": "town", "from": "pole2.wire", "to": "homes.power"},
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
         "actions": [{"do": "move", "target": "scraper1", "to": [6.2, 0.7], "at": 0.02}],
         "labels": [{"target": "scraper1", "text": "Scraper", "kind": "part", "at": "scraper"}],
         "keywords": [{"text": "the scraper", "kind": "part", "at": "scraper"}]},
        {"camera": {"move": "follow", "target": "tractor1", "angle": 35, "height": 22},
         "actions": [{"do": "show_part", "target": "tractor1.load", "at": 0.0},
                     {"do": "move", "target": "tractor1", "to": "tank1", "at": 0.05},
                     {"do": "hide_part", "target": "tractor1.load", "at": 0.92},
                     {"do": "flow", "target": "pipe1", "at": 0.95, "color": "#6e4a2c"}],
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
COW_POOP_PLAN["preset"] = "farm"
COW_POOP_PLAN["format"] = "how_it_works"

# ---------------------------------------------------------------------------------------------------------------
# 3 more demos (one per world preset / format): they are also the test videos for presets, recipes and formats.

SUB_SCRIPT = """[TITLE] How a Submarine Dives
[SCENE] close up: a submarine floats at the surface
NARRATOR: This 7,000 ton machine sinks on purpose.
[SCENE] the hull from the side, the ballast tanks inside
NARRATOR: Its secret is a set of huge ballast tanks, inside the hull.
[SCENE] cutaway: the tanks are full of air
NARRATOR: At the surface they are full of air, so the sub floats like an empty bottle.
[SCENE] vents open on top, air blasts out
NARRATOR: To dive, the crew opens vents on top. Air blasts out.
[SCENE] sea water floods into the tanks
NARRATOR: Sea water floods in from below, and the sub gets heavier than the sea around it.
[SCENE] the sub slides down under the waves, lights on
NARRATOR: The dive planes tilt, and it slides under the waves.
[SCENE] deep down, the hull creaks under the pressure
NARRATOR: At 300 meters, the sea presses 300 tons on every square meter of the hull.
[SCENE] the propeller spins, the sub glides past the fish
NARRATOR: A single propeller pushes it along, silent and invisible.
[SCENE] compressed air blows the water out of the tanks
NARRATOR: To come back up, it blasts compressed air into the tanks and pushes the water out.
[SCENE] the sub rises to the surface
NARRATOR: Lighter than the sea again, it rises.
[SCENE] close on the sub, a warning light
NARRATOR: But if one vent jams open, it never comes back up.
"""

SUB_PLAN = {
    "title": "How a Submarine Dives", "preset": "ocean", "format": "how_it_works",
    "areas": [{"id": "sea"}],
    "objects": [
        {"id": "sub1", "asset": "submarine", "area": "sea", "pos": [-6, 0], "y": 7.0},
        {"id": "surface", "asset": "sea_surface", "area": "sea", "pos": [4, 0], "y": 9.9},
        {"id": "fish1", "asset": "fish", "area": "sea", "pos": [9, 3.5], "y": 3.0, "count": 6, "layout": "scatter",
         "spacing": 1.6},
        {"id": "fish2", "asset": "fish", "area": "sea", "pos": [-2, -4], "y": 5.0, "count": 4, "layout": "scatter",
         "spacing": 1.8, "params": {"color": "#f4c430"}},
        {"id": "rocks", "asset": "rock", "area": "sea", "pos": [6, -3.5], "count": 5, "layout": "scatter",
         "spacing": 2.6, "params": {"size": 1.6}},
        {"id": "weed", "asset": "grass_patch", "area": "sea", "pos": [2, 4], "count": 4, "layout": "scatter",
         "spacing": 3.0},
    ],
    "scenes": [
        {"camera": {"move": "close_up", "target": "sub1", "angle": 150, "height": 12},
         "actions": [{"do": "drain", "target": "sub1", "at": 0.0, "from": 0.03, "to": 0.03, "dur": 0.05},
                     {"do": "float", "target": "sub1", "at": 0.0}, {"do": "float", "target": "fish2", "at": 0.0}],
         "labels": [{"target": "sub1", "text": "7,000 tons", "kind": "number", "at": "7,000"}],
         "keywords": [{"text": "7,000 tons", "kind": "number", "at": "7,000"},
                      {"text": "sinks on purpose", "kind": "problem", "at": "sinks"}]},
        {"camera": {"move": "orbit", "target": "sub1", "angle": 20, "to_angle": 50, "height": 14},
         "actions": [{"do": "xray", "target": "sub1", "at": "ballast"}],
         "labels": [{"target": "sub1", "text": "Ballast tanks", "kind": "part", "at": "ballast"}],
         "keywords": [{"text": "ballast tanks", "kind": "part", "at": "ballast"}]},
        {"camera": {"move": "push_in", "target": "sub1", "angle": 10, "height": 12},
         "actions": [{"do": "cutaway", "target": "sub1", "at": 0.0}],
         "labels": [{"target": "sub1", "text": "Full of air", "kind": "info", "at": "air"}],
         "keywords": [{"text": "full of air", "kind": "info", "at": "air"},
                      {"text": "it floats", "kind": "info", "at": "floats"}]},
        {"camera": {"move": "low_angle", "target": "sub1", "angle": 40, "height": 24},
         "actions": [{"do": "bubbles", "target": "sub1", "at": "vents", "color": "#e8f8ff"},
                     {"do": "smoke", "target": "sub1", "at": "blasts", "color": "#e8f8ff"}],
         "labels": [{"target": "sub1", "text": "Vents open", "kind": "part", "at": "vents"}],
         "keywords": [{"text": "vents open", "kind": "part", "at": "vents"},
                      {"text": "air out", "kind": "info", "at": "blasts"}]},
        {"camera": {"move": "orbit", "target": "sub1", "angle": -10, "to_angle": 25, "height": 10},
         "actions": [{"do": "cutaway", "target": "sub1", "at": 0.0},
                     {"do": "fill", "target": "sub1", "at": "floods", "from": 0.03, "to": 1.0, "dur": 3.0}],
         "labels": [{"target": "sub1", "text": "Sea water in", "kind": "info", "at": "floods"}],
         "keywords": [{"text": "sea water floods in", "kind": "info", "at": "floods"},
                      {"text": "heavier", "kind": "problem", "at": "heavier"}]},
        {"camera": {"move": "follow", "target": "sub1", "angle": 30, "height": 10},
         "actions": [{"do": "move", "target": "sub1", "to": [2, 0], "y": 2.2, "at": 0.08},
                     {"do": "light_on", "target": "sub1", "at": "slides"}],
         "labels": [{"target": "sub1", "text": "Dive planes", "kind": "part", "at": "planes"}],
         "keywords": [{"text": "dive planes", "kind": "part", "at": "planes"},
                      {"text": "under the waves", "kind": "info", "at": "waves"}]},
        {"camera": {"move": "low_angle", "target": "sub1", "angle": -30, "height": 8},
         "actions": [{"do": "shake", "target": "sub1", "at": "presses"}],
         "labels": [{"target": "sub1", "text": "300 t per m²", "kind": "number", "at": "300"}],
         "keywords": [{"text": "300 meters", "kind": "number", "at": "300"},
                      {"text": "300 tons a m²", "kind": "problem", "at": "presses"}]},
        {"camera": {"move": "follow", "target": "sub1", "angle": -140, "height": 12},
         "actions": [{"do": "spin", "target": "sub1", "at": "propeller", "speed": 3.0},
                     {"do": "move", "target": "sub1", "to": [10, 0], "y": 2.2, "at": 0.1},
                     {"do": "float", "target": "fish1", "at": 0.0}],
         "labels": [{"target": "sub1", "text": "Propeller", "kind": "part", "at": "propeller"}],
         "keywords": [{"text": "one propeller", "kind": "part", "at": "propeller"},
                      {"text": "silent", "kind": "info", "at": "silent"}]},
        {"camera": {"move": "push_in", "target": "sub1", "angle": 15, "height": 10},
         "actions": [{"do": "cutaway", "target": "sub1", "at": 0.0},
                     {"do": "bubbles", "target": "sub1", "at": "blasts", "color": "#e8f8ff"},
                     {"do": "drain", "target": "sub1", "at": "pushes", "from": 1.0, "to": 0.03, "dur": 2.2}],
         "labels": [{"target": "sub1", "text": "Compressed air", "kind": "part", "at": "compressed"}],
         "keywords": [{"text": "compressed air", "kind": "part", "at": "compressed"},
                      {"text": "water out", "kind": "info", "at": "out"}]},
        {"camera": {"move": "follow", "target": "sub1", "angle": 35, "height": 6},
         "actions": [{"do": "move", "target": "sub1", "to": [14, 0], "y": 7.0, "at": 0.05}],
         "labels": [{"target": "sub1", "text": "Lighter than water", "kind": "info", "at": "Lighter"}],
         "keywords": [{"text": "lighter", "kind": "info", "at": "Lighter"},
                      {"text": "it rises", "kind": "info", "at": "rises"}]},
        {"camera": {"move": "push_in", "target": "sub1", "angle": 160, "height": 14},
         "actions": [{"do": "alarm", "target": "sub1", "at": "jams"}],
         "labels": [{"target": "sub1", "text": "Vent jammed", "kind": "problem", "at": "jams"}],
         "keywords": [{"text": "one jammed vent", "kind": "problem", "at": "jams"}]},
    ],
}

SUGAR_SCRIPT = """[TITLE] What Happens Inside Your Body When You Eat Sugar
[SCENE] close up: sugar cubes drop one after another
NARRATOR: One can of soda dumps 10 sugar cubes into your body.
[SCENE] the sugar slides down into the stomach
NARRATOR: It splashes into your stomach, and in minutes it is squeezed on.
[SCENE] the sugar rushes into the twisting small intestine
NARRATOR: Next stop, your small intestine. 6 meters of twisting tube.
[SCENE] glucose molecules pass into a blood vessel
NARRATOR: Here the sugar is split into glucose and pushed straight into your blood.
[SCENE] glucose floods the bloodstream
NARRATOR: Within 20 minutes, your blood sugar shoots up.
[SCENE] the pancreas lights up and sends out insulin
NARRATOR: Your pancreas notices and fires out insulin.
[SCENE] insulin keys travel to the cells
NARRATOR: Insulin works like a key. It unlocks your cells,
[SCENE] glucose pours into a cell, the cell glows with energy
NARRATOR: so glucose can pour in and turn into energy.
[SCENE] the extra sugar goes into fat cells, they grow
NARRATOR: But cells can only use so much. A lot of the extra gets packed into fat cells.
[SCENE] blood sugar crashes, warning
NARRATOR: Then your blood sugar crashes, and you feel tired and hungry.
[SCENE] another sugar cube drops
NARRATOR: Which is exactly why you reach for another one.
"""

SUGAR_PLAN = {
    "title": "What Happens Inside Your Body When You Eat Sugar", "preset": "body", "format": "what_if",
    "areas": [{"id": "gut"}, {"id": "blood"}, {"id": "pancreas"}, {"id": "cells"}],
    "objects": [
        {"id": "cubes", "asset": "sugar_cube", "area": "gut", "pos": [-7.5, 0.5], "count": 3, "layout": "row",
         "spacing": 1.0, "hidden": True},
        {"id": "cube2", "asset": "sugar_cube", "area": "gut", "pos": [-4.2, 2.4], "hidden": True},
        {"id": "stom", "asset": "stomach", "area": "gut", "pos": [0, 0]},
        {"id": "gut1", "asset": "intestine", "area": "gut", "pos": [8, 0]},
        {"id": "duct", "asset": "pipe", "area": "gut", "from": "stom.outlet", "to": "gut1.inlet",
         "params": {"color": "#d9798b"}},
        {"id": "vessel", "asset": "blood_vessel", "area": "blood", "pos": [0, 0]},
        {"id": "glu", "asset": "glucose", "area": "blood", "pos": [0, 2.6], "y": 1.6, "count": 4, "layout": "row",
         "spacing": 3.4, "hidden": True},
        {"id": "rbc", "asset": "blood_cell", "area": "blood", "pos": [1, -3], "y": 1.5, "count": 5,
         "layout": "scatter", "spacing": 2.2},
        {"id": "panc", "asset": "pancreas", "area": "pancreas", "pos": [0, 0]},
        {"id": "keys", "asset": "insulin", "area": "pancreas", "pos": [3.5, 1.5], "y": 1.4, "count": 3,
         "layout": "row", "spacing": 1.5, "hidden": True},
        {"id": "cell1", "asset": "cell", "area": "cells", "pos": [0, 0], "params": {"r": 2.2}},
        {"id": "glu2", "asset": "glucose", "area": "cells", "pos": [-5, 2.5], "y": 1.6, "count": 2, "layout": "row",
         "spacing": 3.2, "hidden": True},
        {"id": "fat", "asset": "fat_cell", "area": "cells", "pos": [8, 0], "count": 3, "layout": "scatter",
         "spacing": 2.6},
    ],
    "scenes": [
        {"camera": {"move": "close_up", "target": "cubes", "angle": 30, "height": 22, "zoom": 0.6},
         "actions": [{"do": "drop", "target": "cubes", "at": "dumps", "from": 3.0}],
         "labels": [{"target": "cubes", "text": "{n} cubes", "kind": "number", "at": "10", "from": 0, "to": 10}],
         "keywords": [{"text": "1 soda", "kind": "info", "at": "soda"},
                      {"text": "10 sugar cubes", "kind": "number", "at": "10"}]},
        {"camera": {"move": "orbit", "target": "stom", "angle": 20, "to_angle": -10, "height": 14},
         "actions": [{"do": "move", "target": "cubes", "to": "stom", "at": 0.02},
                     {"do": "disappear", "target": "cubes", "at": 0.6},
                     {"do": "bubbles", "target": "stom", "at": "splashes", "color": "#f6e7b0"},
                     {"do": "shake", "target": "stom", "at": "squeezed"}],
         "labels": [{"target": "stom", "text": "Stomach", "kind": "part", "at": "stomach"}],
         "keywords": [{"text": "the stomach", "kind": "part", "at": "stomach"},
                      {"text": "minutes", "kind": "number", "at": "minutes"}]},
        {"camera": {"move": "push_in", "target": "gut1", "angle": 25, "height": 22},
         "actions": [{"do": "flow", "target": "duct", "at": 0.0, "color": "#fff4d0"},
                     {"do": "flow", "target": "gut1", "at": "intestine", "color": "#fff4d0"}],
         "labels": [{"target": "gut1", "text": "Small intestine", "kind": "part", "at": "intestine"}],
         "keywords": [{"text": "small intestine", "kind": "part", "at": "intestine"},
                      {"text": "6 meters", "kind": "number", "at": "6"}]},
        {"camera": {"move": "close_up", "target": "glu", "angle": 20, "height": 16},
         "actions": [{"do": "appear", "target": "glu", "at": "glucose"},
                     {"do": "float", "target": "glu", "at": "glucose"},
                     {"do": "flow", "target": "vessel", "at": "blood", "color": "#ffffff"}],
         "labels": [{"target": "glu", "text": "Glucose", "kind": "part", "at": "glucose"}],
         "keywords": [{"text": "glucose", "kind": "part", "at": "glucose"},
                      {"text": "into your blood", "kind": "info", "at": "blood"}]},
        {"camera": {"move": "orbit", "target": "vessel", "angle": 65, "to_angle": 95, "height": 28},
         "actions": [{"do": "flow", "target": "vessel", "at": 0.0, "color": "#ffffff", "speed": 5},
                     {"do": "float", "target": "glu", "at": 0.0}, {"do": "float", "target": "rbc", "at": 0.0},
                     {"do": "glow", "target": "vessel", "at": "shoots"}],
         "labels": [{"target": "vessel", "text": "Blood sugar up", "kind": "problem", "at": "shoots"}],
         "keywords": [{"text": "20 minutes", "kind": "number", "at": "20"},
                      {"text": "blood sugar spikes", "kind": "problem", "at": "shoots"}]},
        {"camera": {"move": "push_in", "target": "panc", "angle": 30, "height": 18},
         "actions": [{"do": "light_on", "target": "panc", "at": "notices"},
                     {"do": "glow", "target": "panc", "at": "notices"},
                     {"do": "appear", "target": "keys", "at": "insulin"}],
         "labels": [{"target": "panc", "text": "Pancreas", "kind": "part", "at": "pancreas"}],
         "keywords": [{"text": "the pancreas", "kind": "part", "at": "pancreas"},
                      {"text": "insulin", "kind": "part", "at": "insulin"}]},
        {"camera": {"move": "follow", "target": "keys", "angle": 25, "height": 16},
         "actions": [{"do": "move", "target": "keys", "to": [13, 1.5], "y": 1.4, "at": 0.05}],
         "labels": [{"target": "keys", "text": "Insulin = key", "kind": "info", "at": "key"}],
         "keywords": [{"text": "like a key", "kind": "info", "at": "key"},
                      {"text": "unlocks cells", "kind": "part", "at": "unlocks"}]},
        {"camera": {"move": "close_up", "target": "cell1", "angle": 25, "height": 16},
         "actions": [{"do": "appear", "target": "glu2", "at": 0.0},
                     {"do": "move", "target": "glu2", "to": "cell1", "at": "pour"},
                     {"do": "disappear", "target": "glu2", "at": "energy"},
                     {"do": "glow", "target": "cell1", "at": "energy"}],
         "labels": [{"target": "cell1", "text": "Energy", "kind": "info", "at": "energy"}],
         "keywords": [{"text": "glucose in", "kind": "part", "at": "pour"},
                      {"text": "energy", "kind": "info", "at": "energy"}]},
        {"camera": {"move": "push_in", "target": "fat", "angle": 20, "height": 16},
         "actions": [{"do": "grow", "target": "fat", "at": "fat", "from": 1.0, "to": 1.45, "dur": 1.6}],
         "labels": [{"target": "fat", "text": "Fat cells", "kind": "problem", "at": "fat"}],
         "keywords": [{"text": "the extra", "kind": "problem", "at": "extra"},
                      {"text": "into fat cells", "kind": "problem", "at": "fat"}]},
        {"camera": {"move": "pull_out", "target": "vessel", "angle": 80, "height": 32},
         "actions": [{"do": "alarm", "target": "vessel", "at": "crashes"},
                     {"do": "disappear", "target": "glu", "at": "crashes"}],
         "labels": [{"target": "vessel", "text": "Sugar crash", "kind": "problem", "at": "crashes"}],
         "keywords": [{"text": "the crash", "kind": "problem", "at": "crashes"},
                      {"text": "tired + hungry", "kind": "problem", "at": "tired"}]},
        {"camera": {"move": "push_in", "target": "stom", "angle": -25, "height": 18},
         "actions": [{"do": "drop", "target": "cube2", "at": 0.12, "from": 3.0}],
         "labels": [{"target": "cube2", "text": "Again", "kind": "problem", "at": "another"}],
         "keywords": [{"text": "another one", "kind": "problem", "at": "another"}]},
    ],
}

PYRAMID_SCRIPT = """[TITLE] How the Pyramids Were Built
[SCENE] close up: a giant stone block lands next to a sled
NARRATOR: This pyramid is made of 2.3 million stone blocks.
[SCENE] the quarry: workers cut limestone blocks
NARRATOR: Most weigh about 2.5 tons, cut by hand with copper chisels and wooden wedges.
[SCENE] a boat carries a block down the Nile
NARRATOR: The hardest granite came by boat down the Nile, from over 800 kilometers away.
[SCENE] a team drags a block on a wooden sled
NARRATOR: On land, a team of 20 men dragged each block on a wooden sled.
[SCENE] a worker pours water on the sand in front of the sled
NARRATOR: The trick? Pour water on the sand. Wet sand cuts the pulling force in half.
[SCENE] the sled is pulled up a long ramp
NARRATOR: Then they hauled it up long ramps of mud brick and rubble.
[SCENE] the pyramid rises layer by layer
NARRATOR: Layer by layer, the pyramid rose to 146 meters.
[SCENE] the shining capstone goes on top
NARRATOR: On top went a shining capstone.
[SCENE] the finished pyramid, wide
NARRATOR: It took about 20 years, and it stayed the tallest building on Earth for 3,800 years.
[SCENE] cutaway of the pyramid, a hidden room inside
NARRATOR: But deep inside, there is a giant hidden room that nobody has ever entered.
"""

PYRAMID_PLAN = {
    "title": "How the Pyramids Were Built", "preset": "ancient", "format": "how_made",
    "areas": [{"id": "quarry"}, {"id": "river"}, {"id": "site"}],
    "objects": [
        {"id": "blocks", "asset": "stone_block", "area": "quarry", "pos": [0, 0], "count": 4, "layout": "row",
         "spacing": 2.2},
        {"id": "cliff", "asset": "rock", "area": "quarry", "pos": [0, -3.5], "count": 3, "layout": "row",
         "spacing": 3.4, "params": {"size": 2.2, "color": "#b89c6c"}},
        {"id": "cutters", "asset": "person", "area": "quarry", "pos": [0.9, -1.5], "count": 2, "layout": "row",
         "spacing": 4.4, "rot": 90, "params": {"shirt": "#efe6d2", "pants": "#efe6d2", "hair": "#2a1f18"}},
        {"id": "nile", "asset": "water", "area": "river", "pos": [2, 0], "params": {"w": 26.0, "d": 9.0, "depth": 0.5}},
        {"id": "boat", "asset": "reed_boat", "area": "river", "pos": [-6, 0], "y": 0.4},
        {"id": "palms", "asset": "palm_tree", "area": "river", "pos": [2, -6.5], "count": 4, "layout": "row",
         "spacing": 6.0},
        {"id": "sled1", "asset": "sled", "area": "site", "pos": [-24, 4.5]},
        {"id": "team", "asset": "person", "area": "site", "pos": [-19.5, 4.5], "count": 4, "layout": "row",
         "spacing": 1.0, "rot": 0, "params": {"shirt": "#d9c9a3", "pants": "#8a5a2e", "hair": "#1d1612"}},
        {"id": "wet", "asset": "water", "area": "site", "pos": [-17.2, 4.5], "hidden": True,
         "params": {"w": 3.6, "d": 1.8, "depth": 0.04, "color": "#8f6a40"}},
        {"id": "pourer", "asset": "person", "area": "site", "pos": [-17.5, 2.6], "rot": 90,
         "params": {"shirt": "#4aa5c8", "pants": "#efe6d2", "hair": "#1d1612", "mood": "happy"}},
        {"id": "bigblock", "asset": "stone_block", "area": "site", "pos": [-24, 2.6], "hidden": True},
        {"id": "ramp1", "asset": "ramp", "area": "site", "pos": [-4, 4.5]},
        {"id": "pyr", "asset": "pyramid", "area": "site", "pos": [10, 0]},
    ],
    "scenes": [
        {"camera": {"move": "close_up", "target": "sled1", "angle": 150, "height": 24},
         "actions": [{"do": "drop", "target": "bigblock", "at": "blocks", "from": 3.0},
                     {"do": "hide_part", "target": "pyr.layer2", "at": 0.0, "dur": 0.05},
                     {"do": "hide_part", "target": "pyr.layer3", "at": 0.0, "dur": 0.05},
                     {"do": "hide_part", "target": "pyr.layer4", "at": 0.0, "dur": 0.05},
                     {"do": "hide_part", "target": "pyr.layer5", "at": 0.0, "dur": 0.05},
                     {"do": "hide_part", "target": "pyr.layer6", "at": 0.0, "dur": 0.05},
                     {"do": "hide_part", "target": "pyr.cap", "at": 0.0, "dur": 0.05}],
         "labels": [{"target": "bigblock", "text": "{n} blocks", "kind": "number", "at": "2.3", "from": 0,
                     "to": 2300000}],
         "keywords": [{"text": "2.3 million blocks", "kind": "number", "at": "2.3"}]},
        {"camera": {"move": "orbit", "target": "blocks", "angle": 20, "to_angle": 50, "height": 16},
         "actions": [{"do": "shake", "target": "blocks", "at": "chisels"},
                     {"do": "smoke", "target": "blocks", "at": "cut", "color": "#b8a27a"}],
         "labels": [{"target": "blocks", "text": "2.5 tons each", "kind": "number", "at": "2.5"}],
         "keywords": [{"text": "2.5 tons", "kind": "number", "at": "2.5"},
                      {"text": "copper chisels", "kind": "part", "at": "copper"}]},
        {"camera": {"move": "follow", "target": "boat", "angle": 30, "height": 14},
         "actions": [{"do": "move", "target": "boat", "to": [9, 0], "y": 0.4, "at": 0.05}],
         "labels": [{"target": "boat", "text": "Granite", "kind": "part", "at": "granite"}],
         "keywords": [{"text": "down the Nile", "kind": "info", "at": "Nile"},
                      {"text": "800 km", "kind": "number", "at": "800"}]},
        {"camera": {"move": "follow", "target": "team", "angle": 30, "height": 16},
         "actions": [{"do": "move", "target": "sled1", "to": [-20, 4.5], "at": 0.1, "dur": 3.0},
                     {"do": "move", "target": "team", "to": [-15.5, 4.5], "at": 0.1, "dur": 3.0}],
         "labels": [{"target": "team", "text": "20 men", "kind": "number", "at": "20"}],
         "keywords": [{"text": "20 men", "kind": "number", "at": "20"},
                      {"text": "a wooden sled", "kind": "part", "at": "sled"}]},
        {"camera": {"move": "close_up", "target": "sled1", "angle": 50, "height": 16},
         "actions": [{"do": "appear", "target": "wet", "at": "water"},
                     {"do": "grow", "target": "wet", "at": "water", "from": 0.3, "to": 1.0, "dur": 1.2}],
         "labels": [{"target": "wet", "text": "Wet sand", "kind": "info", "at": "Wet"}],
         "keywords": [{"text": "wet sand", "kind": "info", "at": "Wet"},
                      {"text": "half the force", "kind": "number", "at": "half"}]},
        {"camera": {"move": "orbit", "target": "ramp1", "angle": -55, "to_angle": -30, "height": 26},
         "actions": [{"do": "move", "target": "sled1", "to": [-2.5, 4.5], "y": 2.95, "at": 0.05},
                     {"do": "move", "target": "team", "to": [-0.8, 4.5], "y": 3.95, "at": 0.05}],
         "labels": [{"target": "ramp1", "text": "Mud brick ramp", "kind": "part", "at": "ramps"}],
         "keywords": [{"text": "long ramps", "kind": "part", "at": "ramps"}]},
        {"camera": {"move": "orbit", "target": "pyr", "angle": 20, "to_angle": 55, "height": 22},
         "actions": [{"do": "show_part", "target": "pyr.layer2", "at": 0.12},
                     {"do": "show_part", "target": "pyr.layer3", "at": 0.26},
                     {"do": "show_part", "target": "pyr.layer4", "at": 0.4},
                     {"do": "show_part", "target": "pyr.layer5", "at": 0.54},
                     {"do": "show_part", "target": "pyr.layer6", "at": 0.68}],
         "labels": [{"target": "pyr", "text": "{n} m", "kind": "number", "at": "146", "from": 0, "to": 146}],
         "keywords": [{"text": "layer by layer", "kind": "info", "at": "Layer"},
                      {"text": "146 meters", "kind": "number", "at": "146"}]},
        {"camera": {"move": "low_angle", "target": "pyr", "angle": -20, "height": 12},
         "actions": [{"do": "show_part", "target": "pyr.cap", "at": "capstone"},
                     {"do": "glow", "target": "pyr", "at": "shining"}],
         "labels": [{"target": "pyr", "text": "Capstone", "kind": "part", "at": "capstone"}],
         "keywords": [{"text": "a shining capstone", "kind": "part", "at": "capstone"}]},
        {"camera": {"move": "pull_out", "target": "pyr", "angle": 35, "height": 20},
         "actions": [],
         "labels": [{"target": "pyr", "text": "Tallest for 3,800 years", "kind": "number", "at": "3,800"}],
         "keywords": [{"text": "20 years", "kind": "number", "at": "20"},
                      {"text": "3,800 years", "kind": "number", "at": "3,800"}]},
        {"camera": {"move": "push_in", "target": "pyr", "angle": 10, "height": 14},
         "actions": [{"do": "cutaway", "target": "pyr", "at": "inside"},
                     {"do": "alarm", "target": "pyr", "at": "hidden"}],
         "labels": [{"target": "pyr", "text": "Hidden room", "kind": "problem", "at": "hidden"}],
         "keywords": [{"text": "a hidden room", "kind": "problem", "at": "hidden"},
                      {"text": "never entered", "kind": "problem", "at": "never"}]},
    ],
}

EXAMPLES = [(COW_POOP_SCRIPT, COW_POOP_PLAN), (SUB_SCRIPT, SUB_PLAN), (SUGAR_SCRIPT, SUGAR_PLAN),
            (PYRAMID_SCRIPT, PYRAMID_PLAN)]
