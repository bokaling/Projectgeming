# 📋 Scene plan cheatsheet

Write a plan by hand (📋 Paste plan in the app, or `python -m storyforge.make --plan`). Every plan is checked and repaired (closest names, real sizes, missing targets). Use the EXACT part names below for `obj.part` (camera targets, actions, labels, mounts). Regenerate: `python -m storyforge.world.cheatsheet`.

## Plan shape

```
Areas: {id, setting, micro?}. Objects: {id, asset, area, pos [x, z], y?, rot?, count?, layout?, spacing?, params?, color?, hidden?, from?/to? (pipes: 'tank1.outlet'), mount? ('car1.engine_bay'), about? (new assets: what it is + its working parts)}. Scenes: {camera {move, target ('obj' or 'obj.part'), angle?, height?}, actions [{do, target ('obj' or 'obj.part'), at, to?, path?, color?, color2?, keep?, speed?}], labels [{target, text, kind, at, from?, to?}], keywords [{text, kind, at}], look?, cut?}.
Looks (per area or shot): studio_light (clean light studio), outdoor_day (sunny sky, grass), macro_dark (dark, glowing), documentary (dark cinematic). cut: true = hard cut (big change of place or time).
Camera moves: orbit = circle slowly around the target; push_in = move closer to the target; pull_out = move back to reveal more; fly_over = glide over the target from one side to the other; top_down = look down from above; close_up = very close on the target; low_angle = low, looking up (big and dramatic); follow = follow a moving target; zoom_into = dive into the target (then the next scene is inside it); cutaway = orbit while it is cut open; static = almost still; reveal = start close and pull far back; hero = HERO PART CUTAWAY: target 'obj.part' (one piston, one valve): that ONE part alone, big, cut in half (cut faces in our pink), clean light studio, nothing else in frame; macro = extreme close-up on a dark background with glow and shallow depth of field (the most dramatic moment: add glow / sparks / flow).
Actions: appear = pop in; disappear = shrink away; grow = grow (from → to size); move = move to a place; spin = run the machine: engines, motors, compressors, pumps, fans and wheels move (speed 0.3-2); fill = liquid level rises (from → to); drain = liquid level falls; flow = particles flow from the target to 'to' (REQUIRED: the object id it goes into, or a pipe id); bubbles = bubbles rise from it; smoke = smoke puffs rise; sparks = electric sparks travel from the target to 'to' (REQUIRED: an object id); light_on = lights/windows/screens turn on; light_off = lights turn off; glow = pulse with light; alarm = pulse red (danger); shake = shake; cutaway = cut it open to show the inside; xray = make the outside see-through; float = gently bob and turn (micro world, space); show_part = make a hidden part appear (e.g. 'crust'); hide_part = hide a part; count_up = a number counts up; drop = fall from above and land with a plop (a poop, a box, a coin…); 'from' = height in m; open = open the machine's doors / lid / valve / flapper (whole object, or one part: 'fridge1.door'); close = close them again; snap = a rope/cable SNAPS (target 'lift1.ropes'): it breaks, the loose ends whip back, the car drops a little and the safety brakes clamp onto the rails with sparks; clamp = brakes clamp shut with a shower of sparks (target 'lift1.safety_brakes'); lift = move the machine's lifting part to a level: 'to': 1 = top, 0 = bottom (an elevator car rises, its counterweight goes down, the ropes and pulley follow).
Label/keyword kinds: problem (red), part (names of parts: small white labels), number (white), info (teal), wow (yellow: the big wow fact).
Layouts for count > 1: row, column, grid, circle, scatter.
```

Areas: `{id, setting, look?, micro?}`. Settings: studio, kitchen, bathroom, garage, street, living_room, office, lab, factory, outdoors, farm, desk, table, site, town.
Presets (whole world): studio, farm, city, house_interior, factory, lab, hospital, space, planet_surface, ocean, body, desert, forest, snow, ancient, battlefield, highway, school, office. Looks (area or shot): studio_light, outdoor_day, macro_dark, documentary, underwater, space.

## Camera moves

- `orbit`: circle slowly around the target
- `push_in`: move closer to the target
- `pull_out`: move back to reveal more
- `fly_over`: glide over the target from one side to the other
- `top_down`: look down from above
- `close_up`: very close on the target
- `low_angle`: low, looking up (big and dramatic)
- `follow`: follow a moving target
- `zoom_into`: dive into the target (then the next scene is inside it)
- `cutaway`: orbit while it is cut open
- `static`: almost still
- `reveal`: start close and pull far back
- `hero`: HERO PART CUTAWAY: target 'obj.part' (one piston, one valve): that ONE part alone, big, cut in half (cut faces in our pink), clean light studio, nothing else in frame
- `macro`: extreme close-up on a dark background with glow and shallow depth of field (the most dramatic moment: add glow / sparks / flow)

## Actions (`at`: a spoken word, 0-1 of the shot, or seconds)

`appear` pop in; `disappear` shrink away; `grow` grow; `move` move to a place
`spin` run the machine; `fill` liquid level rises; `drain` liquid level falls; `flow` particles flow from the target to 'to'
`bubbles` bubbles rise from it; `smoke` smoke puffs rise; `sparks` electric sparks travel from the target to 'to'; `light_on` lights/windows/screens turn on
`light_off` lights turn off; `glow` pulse with light; `alarm` pulse red; `shake` shake
`cutaway` cut it open to show the inside; `xray` make the outside see-through; `float` gently bob and turn; `show_part` make a hidden part appear
`hide_part` hide a part; `count_up` a number counts up; `drop` fall from above and land with a plop; `open` open the machine's doors / lid / valve / flapper
`close` close them again; `snap` a rope/cable SNAPS; `clamp` brakes clamp shut with a shower of sparks; `lift` move the machine's lifting part to a level

Label / keyword kinds: `problem` (red), `part` (orange), `number` (white), `info` (teal), `wow` (yellow). Keywords: 0-1 per shot, only for a wow fact.

## Machines: real part names, ports, paths

- **agitator**: motor, shaft, blades · ports: top
- **boiler**: water, pipe, tank, firebox, fire · ports: outlet, top
- **car_engine**: exhaust, intake, timing_belt, plug, coil, intake_plenum, fuel_rail, block, head, cam_cover, oil_pan, oil, liner, piston, rings, rod, gas, spark, intake_valves, exhaust_valves, crankshaft, pulley, flywheel, intake_cam, intake_cam_pulley, exhaust_cam, exhaust_cam_pulley, throttle · ports: intake, exhaust, inside, spark, piston, cylinder, crankshaft, inlet, outlet, top · paths: intake, exhaust, fuel, flow
- **conveyor**: belt, leg, box, roller · ports: top · paths: flow
- **electric_motor**: fin, coil, feet, body, shaft · ports: top
- **elevator**: car, landing, shaft, back_wall, pit, shaft_back, guide_rails, buffers, motor, brake, bedplate, governor_rope, controller, floors, roof, side_wall, front_glass, shaft_side, landing_wall, lobby_door, floor_light, landing_door, car_floor, car_back, car_walls, car_ceiling, car_frame, safety_brakes · ports: inside, car, sheave, motor, counterweight, power, top · paths: power
- **fan**: stand, blades · ports: top
- **fridge**: floor, shelf, milk, milk_cap, apples, cheese, bottle, vegetables, ice, thermostat, thermostat_dial, evaporator, suction_pipe, condenser_wires, capillary, back_wall, side_wall, top, base, foam, door, door_handle, light, compressor, compressor_piston, compressor_motor, fan · ports: power, top · paths: loop, heat, cold
- **gauge**: face, rim, red_zone, needle · ports: top
- **gear**: axle, gear · ports: top
- **generator**: skid, body, alternator, grille, exhaust, panel, fan, screen · ports: exhaust, inlet, outlet, top
- **piston_pump**: base, motor, pipe_in, cylinder, water, piston, rod, crank_wheel, inlet_valve, outlet_valve · ports: inlet, outlet, power, top · paths: water
- **pump**: base, motor, pipe_in, housing, impeller · ports: inlet, outlet, top
- **robot_arm**: base, arm · ports: top
- **scraper**: blade, frame, shoe · ports: blade, blade_half, top
- **seesaw**: stand, plank, left_seat · ports: left_seat, right_seat, top
- **stomach**: food_pipe, wall, acid · ports: inlet, outlet, top
- **submarine**: periscope, dive_planes, front_ballast, hull, tower, propeller, window, water · ports: vent, inlet, outlet, top
- **toilet**: seat, siphon, flush_valve, chain, fill_valve, supply_pipe, pedestal, bowl, rim, lid, bowl_water, tank, tank_lid, tank_water, flapper, handle, lever_arm, float · ports: inlet, outlet, top · paths: rinse, siphon, refill
- **turbine**: stand, casing, rotor · ports: inlet, outlet, top

## Other assets

airplane (37.0 m), arrow, atom, bacteria, balance_scale, ball, bar_chart, barn, barrel, battery (0.3 m), beaker (0.22 m)
bird (0.3 m), blood_cell, blood_vessel, bolt, bottle (0.3 m), bridge, bucket, bus (12.0 m), car, cash (0.16 m)
cell, check_mark, chicken (0.45 m), clock, cloud, coin (0.025 m), coin_stack (0.04 m), cooling_tower, counter
cow, crane, crate, crops, cross_mark, crystal, cutaway_wall, cylinder_block, dam, digester, dna, dog (0.9 m), drill
excavator, explosion, factory, fat_cell, fence, fire, fish (0.4 m), furnace, glass_box, glucose, gold_bar (0.25 m)
grass_patch, greenhouse, ground, ground_layers, ground_plate, hammer (0.33 m), hay_bale, heart, helicopter (13.0 m)
hill, horse, house, house_cutaway, human_hair (0.05 m), insulin, intestine, lamp_post, laptop (0.35 m), lightbulb (0.12 m)
lighthouse, lightning_strike, magnifier, manure, methane, molecule, money_bag (0.5 m), moon, mountain, neuron
pad, palm_tree, pancreas, person, phone (0.15 m), pig, pipe, pipe_stand, pit, planet, platform, power_line, power_pole
power_station, puddle, pumpjack, pyramid, question_mark, rail, railing, ramp, reed_boat, rock, rocket, ruler (0.3 m)
satellite, sea_surface, sheep, ship, shot_glass (0.06 m), sign_number, silo, skyscraper, sled, smoke_cloud, solar_panel
stone_block, sugar_cube (0.016 m), sun, tank, terrain, thermometer (0.35 m), tractor, train, transformer, tree
truck (9.0 m), valve (0.4 m), virus, volcano, warehouse, warning_sign, water, water_drop (0.005 m), water_tower
wind_turbine, wire, wrench (0.25 m)

## Small example

```json
{"title": "How a toilet flushes", "preset": "studio", "areas": [{"id": "bath", "setting": "bathroom"}, {"id": "compare", "setting": "table"}], "objects": [{"id": "wc1", "asset": "toilet", "area": "bath", "pos": [0, 0]}, {"id": "bottle1", "asset": "bottle", "area": "compare", "pos": [-0.1, 0]}, {"id": "glass1", "asset": "shot_glass", "area": "compare", "pos": [0.1, 0]}], "scenes": [{"camera": {"move": "close_up", "target": "wc1.handle"}, "actions": [{"do": "open", "target": "wc1.flapper", "at": "press"}], "labels": [], "keywords": []}, {"camera": {"move": "hero", "target": "wc1.flapper"}, "actions": [{"do": "drain", "target": "wc1.tank_water", "at": "rushes"}], "labels": [{"target": "wc1.flapper", "text": "flapper", "kind": "part", "at": "flapper"}], "keywords": [{"text": "6 LITERS", "kind": "number", "at": "six"}]}, {"camera": {"move": "push_in", "target": "bottle1"}, "cut": true, "actions": [], "labels": [], "keywords": [{"text": "4 BOTTLES", "kind": "wow", "at": "bottles"}]}]}
```
