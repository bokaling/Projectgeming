# 📋 Scene plan cheatsheet

Write a plan by hand (📋 Paste plan in the app, or `python -m storyforge.make --plan`). Every plan is checked and repaired (closest names, real sizes, missing targets). Use the EXACT part names below for `obj.part` (camera targets, actions, labels, mounts). Regenerate: `python -m storyforge.world.cheatsheet`.

## Plan shape

```
Areas: {id, setting, micro?}. Objects: {id, asset, area, pos [x, z], y?, rot?, count?, layout?, spacing?, params?, color?, hidden?, from?/to? (pipes: 'tank1.outlet'), mount? ('car1.engine_bay'), about? (new assets: what it is + its working parts)}. Scenes: {camera {move, target ('obj' or 'obj.part'), angle?, height?}, actions [{do, target ('obj' or 'obj.part'), at, to?, path?, color?, color2?, keep?, speed?}], labels [{target, text, kind, at, from?, to?}], keywords [{text, kind, at}], look?, cut?, stat? {big, small} (documentary card: '700 M' / 'UNDERGROUND'), map? {lat, lon, place} (a small map with a marker)}.
Looks (per area or shot): studio_light (clean light studio), outdoor_day (sunny sky, grass), macro_dark (dark, glowing), documentary (dark cinematic). cut: true = hard cut (big change of place or time).
Camera moves: orbit = circle slowly around the target; push_in = move closer to the target; pull_out = move back to reveal more; fly_over = glide over the target from one side to the other; top_down = look down from above; close_up = very close on the target; low_angle = low, looking up (big and dramatic); follow = follow a moving target; zoom_into = dive into the target (then the next scene is inside it); cutaway = orbit while it is cut open; static = almost still; reveal = start close and pull far back; hero = HERO PART CUTAWAY: target 'obj.part' (one piston, one valve): that ONE part alone, big, cut in half (cut faces in deep red), inside its machine (shown as a faint ghost) on its floor; macro = extreme close-up on a dark background with glow and shallow depth of field (the most dramatic moment: add glow / sparks / flow).
Actions: appear = pop in; disappear = shrink away; grow = grow (from → to size); move = move to a place; spin = run the machine: engines, motors, compressors, pumps, fans and wheels move (speed 0.3-2); fill = liquid level rises (from → to); drain = liquid level falls; flow = particles flow from the target to 'to' (REQUIRED: the object id it goes into, or a pipe id); bubbles = bubbles rise from it; smoke = smoke puffs rise; sparks = electric sparks travel from the target to 'to' (REQUIRED: an object id); light_on = lights/windows/screens turn on; light_off = lights turn off; glow = pulse with light; alarm = pulse red (danger); shake = shake; cutaway = cut it open to show the inside; xray = make the outside see-through; float = gently bob and turn (micro world, space); show_part = make a hidden part appear (e.g. 'crust'); hide_part = hide a part; count_up = a number counts up; drop = fall from above and land with a plop (a poop, a box, a coin…); 'from' = height in m; open = open the machine's doors / lid / valve / flapper (whole object, or one part: 'fridge1.door'); close = close them again; snap = a rope/cable SNAPS (target 'lift1.ropes'): it breaks, the loose ends whip back, the car drops a little and the safety brakes clamp onto the rails with sparks; clamp = brakes clamp shut with a shower of sparks (target 'lift1.safety_brakes'); lift = move the machine's lifting part to a level: 'to': 1 = top, 0 = bottom (an elevator car rises, its counterweight goes down, the ropes and pulley follow).
Label/keyword kinds: problem (red), part (names of parts: small white labels), number (white), info (teal), wow (yellow: the big wow fact).
Layouts for count > 1: row, column, grid, circle, scatter.
```

Areas: `{id, setting, look?, micro?}`. Settings: studio, kitchen, bathroom, laundry, hangar, garage, street, living_room, office, lab, factory, outdoors, farm, desk, table, site, town.
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
- `hero`: HERO PART CUTAWAY: target 'obj.part' (one piston, one valve): that ONE part alone, big, cut in half (cut faces in deep red), inside its machine (shown as a faint ghost) on its floor
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

## Mechanism kit (in a new object's recipe: {"kit": piece, "name", "pos", "size", "axis": x/y/z/-x/-y/-z}; also objects kit_<piece>)

gear_train, piston_crank, valve, pump, fan, turbine, belt_drive, chain_drive, pulley_cable, hydraulic_cylinder, spring, lever, wheel_axle, motor, battery_wire, heating_coil, tank_pipe, drum, light, emitter

## Machines: real part names, ports, paths

- **agitator**: motor, shaft, blades · ports: top
- **bicycle**: front, rear, frame, fork, seat_post, stem, handlebar, grips, saddle, bottom_bracket, chain, front_wheel_tire, front_wheel_rim, front_wheel_hub, front_wheel_spokes, rear_wheel_tire, rear_wheel_rim, rear_wheel_hub, rear_wheel_spokes, chainring, rear_cog, cranks · ports: key, top · paths: chain
- **boiler**: water, pipe, tank, firebox, fire · ports: outlet, top
- **car_engine**: exhaust, intake, timing_belt, plug, coil, intake_plenum, intake_runners, fuel_rail, mounts, block, head, cam_cover, oil_pan, oil, liner, piston, rings, rod, gas, spark, intake_valves, exhaust_valves, crankshaft, pulley, flywheel, intake_cam, intake_cam_pulley, exhaust_cam, exhaust_cam_pulley, throttle, throttle_plate, exhaust_manifold · ports: intake, exhaust, inside, spark, piston, cylinder, crankshaft, inlet, outlet, top · paths: intake, exhaust, fuel, flow
- **ceiling_fan**: pull, canopy, downrod, motor_housing, switch_housing, light_kit, pull_chain, pull_bead, rotor, blade_irons, blades, bulb · ports: key, top · paths: air
- **conveyor**: belt, leg, box, roller · ports: top · paths: flow
- **cordless_drill**: battery, battery_latch, handle, clutch_collar, trigger, direction_switch, barrel, motor, motor_shaft, gearbox, chuck, bit, led_light · ports: key, top · paths: power
- **dishwasher**: drain, inlet, lower, upper, wash, sump, filter, wash_pump, pump_motor, wash_tube, drain_pump, drain_hose, inlet_valve, inlet_hose, lower_rack, lower_rack_rails, upper_rack, upper_rack_rails, plates, cabinet, door, control_strip, buttons, door_handle, detergent_dispenser, toe_kick, water, lower_arm_hub, lower_spray_arm, upper_spray_arm, heater · ports: inlet, outlet, power, key, top · paths: water, spray, drain
- **electric_motor**: fin, coil, feet, body, shaft · ports: top
- **elevator**: car, landing, passenger, shaft, back_wall, pit, shaft_back, guide_rails, buffers, motor, brake, bedplate, governor_rope, controller, floors, roof, side_wall, front_glass, shaft_side, landing_wall, lobby_door, floor_light, landing_door, car_floor, car_back, car_walls, car_ceiling, car_frame, safety_brakes, handrail, car_panel, car_light, car_door, car_buttons, passenger_leg, passenger_shoe, passenger_torso, passenger_hand, passenger_eye, passenger_brow, passenger_mouth, passenger_hair, counterweight, ropes, cw_ropes, sheave, motor_shaft, governor, controller_lights · ports: inside, car, sheave, motor, counterweight, power, top · paths: power
- **fan**: stand, ring, blades · ports: top
- **fridge**: floor, freezer_floor, shelf, milk, milk_cap, apples, cheese, bottle, vegetables, ice, thermostat, thermostat_dial, evaporator, suction_pipe, discharge_pipe, condenser, condenser_wires, capillary, fan_mount, back_wall, side_wall, top, base, foam, door, door_handle, light, compressor, compressor_piston, compressor_motor, fan · ports: power, top · paths: loop, heat, cold
- **gauge**: face, rim, red_zone, post, needle · ports: top
- **gear**: axle, stand, gear · ports: top
- **generator**: skid, body, alternator, grille, exhaust, panel, fan_mount, fan, screen · ports: exhaust, inlet, outlet, top
- **jet_engine**: hp, pylon, struts, combustor, fuel_nozzles, exhaust_cone, cone_struts, stand_frame, stand, stand_wheels, nacelle, core_casing, fan, spinner, compressor, hp_compressor, flame, hp_turbine, turbine, lp_shaft, hp_shaft · ports: intake, exhaust, fuel, key, top · paths: air, bypass, fuel
- **microwave**: fan, chassis, cavity, cavity_rails, control_panel, display, buttons, start_button, turntable_motor, magnetron, magnetron_fins, magnetron_antenna, waveguide, magnetron_bracket, transformer, transformer_coil, capacitor, fan_frame, fan_bracket, feet, casing, door, door_window, door_handle, turntable, roller_ring, turntable_coupler, food, food_soup, light, cooling_fan · ports: power, key, top · paths: waves, heat
- **piston_pump**: crank, pipe, base, frame, motor, pipe_in, pipe_out, pipe_flanges, frame_foot, bolts, shaft_bearing, frame_arm, cylinder, water, piston, rod, crank_wheel, inlet_valve, outlet_valve, crank_shaft · ports: inlet, outlet, power, top · paths: water
- **pump**: pipe, base, motor, pipe_in, pipe_out, motor_mount, housing, impeller · ports: inlet, outlet, top
- **rescue_capsule**: stripes, stripe_blue, top, bottom, wheels, door, cable, body · ports: top, inside
- **robot_arm**: base, arm · ports: top
- **scraper**: blade, frame, shoe · ports: blade, blade_half, top
- **seesaw**: stand, plank, left_seat, right_seat · ports: left_seat, right_seat, top
- **stomach**: food_pipe, exit, wall, acid · ports: inlet, outlet, top
- **submarine**: periscope, dive_planes, rudder, front_ballast, rear_ballast, hull, tower, propeller, window, water · ports: vent, inlet, outlet, top
- **toaster**: base, crumb_tray, lever_slot, browning_knob, cancel_button, cord, feet, body, bread, heating_elements, carriage, lever · ports: power, key, top · paths: heat
- **toilet**: seat, siphon, flush_valve, overflow_tube, chain, fill_valve, supply_pipe, shutoff_valve, pedestal, bowl, rim, lid, bowl_water, tank, tank_lid, tank_water, flapper, handle, lever_arm, float · ports: inlet, outlet, top · paths: rinse, siphon, refill
- **turbine**: stand, casing, rotor · ports: inlet, outlet, top
- **washing_machine**: drain, drawer, inlet, control_panel, dial, display, buttons, detergent_drawer, drawer_handle, tub, tub_back, bellow, motor, drum_bearing, motor_bracket, bracket_bolts, belt, springs, dampers, base_plate, drain_pump, pump_filter_cap, sump_hose, drain_hose, inlet_valve, inlet_valve_coil, inlet_hose, drawer_chute, feet, cabinet, door, door_glass, door_handle, drum, drum_paddle, drum_shaft, drum_pulley, motor_pulley, motor_shaft, heater, water · ports: inlet, outlet, power, key, top · paths: water, drain

## Free CC0 models (ready-made everyday things: use them by name; files load once from Drive)

On the wall: `sofa` 2.1 m, `bed` 2.1 m, `bookshelf` 1.8 m, `cabinet` 0.9 m, `picture_frame` 0.7 m, `stove` 0.92 m, `oven` 0.92 m
  `kitchen_cabinet` 0.7 m, `worktop` 0.92 m, `kitchen_sink` 0.92 m, `extractor_hood` 0.9 m
On the floor: `armchair` 0.95 m, `chair` 0.95 m, `footstool` 0.5 m, `dining_table` 1.8 m, `coffee_table` 1.1 m, `floor_lamp` 1.6 m, `cactus` 0.6 m
  `rug` 2.0 m, `kitchen_table` 1.4 m, `vegetable_crate` 0.6 m, `bush` 0.9 m, `apartment_building` 14.0 m, `shop_building` 8.0 m
  `small_building` 6.0 m, `garage_building` 4.0 m, `fountain` 6.0 m
On the table: `table_lamp` 0.45 m, `books` 0.25 m, `plate` 0.26 m, `bowl` 0.18 m, `ketchup` 0.2 m, `burger` 0.12 m, `carrot` 0.18 m, `tomato` 0.08 m
  `onion` 0.08 m, `potato` 0.09 m, `cheese` 0.12 m, `lettuce` 0.16 m, `steak` 0.2 m, `stew` 0.18 m
On the counter: `cutting_board` 0.4 m, `knife` 0.28 m, `frying_pan` 0.45 m, `cooking_pot` 0.38 m, `jar` 0.18 m, `paper_towel` 0.26 m
  `dish_rack` 0.45 m
On the street: `taxi` 4.5 m, `police_car` 4.6 m, `hatchback` 4.0 m, `station_wagon` 4.7 m, `lamp_post` 4.5 m, `traffic_light` 3.6 m
  `fire_hydrant` 0.75 m, `dumpster` 1.3 m, `bench` 1.8 m, `trash_bag` 1.0 m, `pickup_truck` 5.5 m, `motorcycle` 2.1 m

Licenses: LICENSES/assets.md (all CC0). Other CC0 packs copied to Drive library/models/<pack>/ become `<pack>_<file>`.

## CAD shapes for new objects' recipes (a part with "cad": shape; build123d + bd_warehouse)

- `box`: size [x, y, z]; fillet r (round edges) or chamfer c
- `cylinder`: size [r, h] along axis x/y/z (default y); fillet/chamfer on the rims; bore r = a thick tube
- `revolve`: profile [[radius, height], …] spun around y: drums, bowls, nozzles, domes, bottles, cones; ring: true = the profile is a closed loop away from the axis (a hollow cowling, a nacelle, a tyre)
- `loft`: sections [{y, size [w, d]} or {y, r}, …] joined smoothly: cowlings, hoods, casings
- `sweep`: path [[x, y, z], …] with r: hoses, bent pipes, handles, cables; bore r = hollow
- `extrude`: poly [[x, y], …] (front view) pushed back by size [depth] along z: brackets, plates, levers; fillet
- `gear`: module m, teeth n, thickness t, bore r: a real involute spur gear (spins about z)
- `sprocket`: teeth n, pitch p, thickness t, bore r: a chain sprocket (spins about z)
- `bearing`: od, width: a real ball bearing (rings + balls), axis z
- `bolt`: d, length: a hex head bolt (along y, head on top)
- `nut`: d: a hex nut
- `washer`: d: a flat washer
- `flange`: nps ('2', '4'…), kind slip_on / weld_neck / blind: a pipe flange (real size)
- `pipe`: nps, path [[x, y, z], …]: a steel pipe along the path (real size)
- modifiers: holes [{at, r, axis, depth?, grid [nx, ny, spacing]?}], windows [{at, size}], hollow t (walls t thick), open top/front/… (the side a hollow shell leaves open)

## Other assets

airplane (37.0 m), arrow, atom, bacteria, balance_scale, ball, bar_chart, barn, barrel, battery (0.3 m), beaker (0.22 m)
bird (0.3 m), blood_cell, blood_vessel, bolt, bottle (0.3 m), bridge, bucket, bus (12.0 m), car, cash (0.16 m)
cell, check_mark, chicken (0.45 m), clock, cloud, coin (0.025 m), coin_stack (0.04 m), cooling_tower, counter
cow, crane, crate, crops, cross_mark, crystal, cutaway_wall, cylinder_block, dam, desk_lamp, digester, dna, dog (0.9 m)
drill, excavator, explosion, factory, fat_cell, fence, fire, fish (0.4 m), furnace, glass_box, glucose, gold_bar (0.25 m)
grass_patch, greenhouse, ground, ground_layers, ground_plate, hammer (0.33 m), hay_bale, heart, helicopter (13.0 m)
hill, horse, house, house_cutaway, human_hair (0.05 m), insulin, intestine, laptop (0.35 m), lightbulb (0.12 m)
lighthouse, lightning_strike, magnifier, manure, methane, mine, miner, molecule, money_bag (0.5 m), moon, mountain
neuron, pad, palm_tree, pancreas, person, phone (0.15 m), pig, pipe, pipe_stand, pit, planet, platform, power_line
power_pole, power_station, puddle, pumpjack, pyramid, question_mark, rail, railing, ramp, reed_boat, rock, rocket
ruler (0.3 m), satellite, sea_surface, sheep, ship, shot_glass (0.06 m), sign_number, silo, skyscraper, sled, smoke_cloud
solar_panel, stone_block, sugar_cube (0.016 m), sun, tank, terrain, thermometer (0.35 m), tractor, train, transformer
tree, truck (9.0 m), valve (0.4 m), virus, volcano, warehouse, warning_sign, water, water_drop (0.005 m), water_tower
wind_turbine, wire, wrench (0.25 m)

## Small example

```json
{"title": "How a toilet flushes", "preset": "studio", "areas": [{"id": "bath", "setting": "bathroom"}, {"id": "compare", "setting": "table"}], "objects": [{"id": "wc1", "asset": "toilet", "area": "bath", "pos": [0, 0]}, {"id": "bottle1", "asset": "bottle", "area": "compare", "pos": [-0.1, 0]}, {"id": "glass1", "asset": "shot_glass", "area": "compare", "pos": [0.1, 0]}], "scenes": [{"camera": {"move": "close_up", "target": "wc1.handle"}, "actions": [{"do": "open", "target": "wc1.flapper", "at": "press"}], "labels": [], "keywords": []}, {"camera": {"move": "hero", "target": "wc1.flapper"}, "actions": [{"do": "drain", "target": "wc1.tank_water", "at": "rushes"}], "labels": [{"target": "wc1.flapper", "text": "flapper", "kind": "part", "at": "flapper"}], "keywords": [{"text": "6 LITERS", "kind": "number", "at": "six"}]}, {"camera": {"move": "push_in", "target": "bottle1"}, "cut": true, "actions": [], "labels": [], "keywords": [{"text": "4 BOTTLES", "kind": "wow", "at": "bottles"}]}]}
```
