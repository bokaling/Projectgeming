# Asset licenses

Every ready-made 3D model StoryForge downloads is **CC0 1.0 Universal** (public domain dedication): free for
commercial use, changes allowed, **no attribution required** (we still name the authors here as a thank-you).
Only CC0 packs are allowed. Never add PartNet-Mobility (non-commercial license) or anything with NC/ND/SA terms.
Files are downloaded once into `MyDrive/StoryForge/library/models/<pack>/` (each folder gets a LICENSE.txt).

| Pack (folder) | Author | Source | License |
|---|---|---|---|
| `kaykit_furniture` | Kay Lousberg (KayKit) | https://github.com/KayKit-Game-Assets/KayKit-Furniture-Bits-1.0 (https://kaylousberg.itch.io/furniture-bits) | CC0 1.0 |
| `kaykit_restaurant` | Kay Lousberg (KayKit) | https://github.com/KayKit-Game-Assets/KayKit-Restaurant-Bits-1.0 (https://kaylousberg.itch.io/restaurant-bits) | CC0 1.0 |
| `kaykit_city` | Kay Lousberg (KayKit) | https://github.com/KayKit-Game-Assets/KayKit-City-Builder-Bits-1.0 (https://kaylousberg.itch.io/city-builder-bits) | CC0 1.0 |
| `kenney_city` | Kenney (kenney.nl) | https://github.com/KenneyNL/Starter-Kit-City-Builder (https://github.com/KenneyNL/Starter-Kit-City-Builder) | CC0 1.0 |
| `kenney_racing` | Kenney (kenney.nl) | https://github.com/KenneyNL/Starter-Kit-Racing (https://github.com/KenneyNL/Starter-Kit-Racing) | CC0 1.0 |
| `polyhaven` (optional, `imported.fetch_polyhaven(id)`) | Poly Haven contributors | https://polyhaven.com/models | CC0 1.0 |
| `<any>` Kenney zips from kenney.nl, Quaternius packs (`imported.fetch_url` or copied by hand) | Kenney, Quaternius | https://kenney.nl/assets, https://quaternius.com | CC0 1.0 (a pack folder without a CC0 LICENSE file is ignored) |

## Models used by name

| Object | Pack | File |
|---|---|---|
| sofa | kaykit_furniture | couch_pillows.gltf |
| armchair | kaykit_furniture | armchair_pillows.gltf |
| chair | kaykit_furniture | chair_A.gltf |
| footstool | kaykit_furniture | chair_stool.gltf |
| bed | kaykit_furniture | bed_double_A.gltf |
| dining_table | kaykit_furniture | table_medium_long.gltf |
| coffee_table | kaykit_furniture | table_low.gltf |
| bookshelf | kaykit_furniture | shelf_B_large_decorated.gltf |
| cabinet | kaykit_furniture | cabinet_medium_decorated.gltf |
| floor_lamp | kaykit_furniture | lamp_standing.gltf |
| table_lamp | kaykit_furniture | lamp_table.gltf |
| cactus | kaykit_furniture | cactus_medium_A.gltf |
| rug | kaykit_furniture | rug_rectangle_stripes_A.gltf |
| picture_frame | kaykit_furniture | pictureframe_large_A.gltf |
| books | kaykit_furniture | book_set.gltf |
| stove | kaykit_restaurant | stove_single.gltf |
| oven | kaykit_restaurant | oven.gltf |
| kitchen_cabinet | kaykit_restaurant | kitchencabinet.gltf |
| worktop | kaykit_restaurant | kitchencounter_straight_A_backsplash.gltf |
| kitchen_sink | kaykit_restaurant | kitchencounter_sink_backsplash.gltf |
| extractor_hood | kaykit_restaurant | extractorhood.gltf |
| kitchen_table | kaykit_restaurant | kitchentable_A.gltf |
| cutting_board | kaykit_restaurant | cuttingboard.gltf |
| knife | kaykit_restaurant | knife.gltf |
| frying_pan | kaykit_restaurant | pan_A.gltf |
| cooking_pot | kaykit_restaurant | pot_A.gltf |
| plate | kaykit_restaurant | plate.gltf |
| bowl | kaykit_restaurant | bowl.gltf |
| jar | kaykit_restaurant | jar_A_medium.gltf |
| ketchup | kaykit_restaurant | ketchup.gltf |
| paper_towel | kaykit_restaurant | papertowel.gltf |
| dish_rack | kaykit_restaurant | dishrack_plates.gltf |
| burger | kaykit_restaurant | food_burger.gltf |
| carrot | kaykit_restaurant | food_ingredient_carrot.gltf |
| tomato | kaykit_restaurant | food_ingredient_tomato.gltf |
| onion | kaykit_restaurant | food_ingredient_onion.gltf |
| potato | kaykit_restaurant | food_ingredient_potato.gltf |
| cheese | kaykit_restaurant | food_ingredient_cheese.gltf |
| lettuce | kaykit_restaurant | food_ingredient_lettuce.gltf |
| steak | kaykit_restaurant | food_ingredient_steak.gltf |
| stew | kaykit_restaurant | food_stew.gltf |
| vegetable_crate | kaykit_restaurant | crate_carrots.gltf |
| taxi | kaykit_city | car_taxi.gltf |
| police_car | kaykit_city | car_police.gltf |
| hatchback | kaykit_city | car_hatchback.gltf |
| station_wagon | kaykit_city | car_stationwagon.gltf |
| lamp_post | kaykit_city | streetlight.gltf |
| traffic_light | kaykit_city | trafficlight_A.gltf |
| fire_hydrant | kaykit_city | firehydrant.gltf |
| dumpster | kaykit_city | dumpster.gltf |
| bench | kaykit_city | bench.gltf |
| bush | kaykit_city | bush.gltf |
| trash_bag | kaykit_city | trash_A.gltf |
| apartment_building | kaykit_city | building_D_withoutBase.gltf |
| shop_building | kaykit_city | building_A_withoutBase.gltf |
| small_building | kenney_city | building-small-a.glb |
| garage_building | kenney_city | building-garage.glb |
| fountain | kenney_city | pavement-fountain.glb |
| pickup_truck | kenney_racing | vehicle-truck-red.glb |
| motorcycle | kenney_racing | vehicle-motorcycle.glb |

## Code libraries for objects

| Library | Use | License |
|---|---|---|
| build123d (gumyr) | CAD shapes for machine parts (fillets, chamfers, lofts, sweeps, revolves, holes) | Apache 2.0 |
| bd_warehouse (gumyr) | gears, bearings, fasteners, flanges, pipes, sprockets, threads | Apache 2.0 |
| OCP / cadquery-ocp (OpenCascade) | the CAD kernel under build123d | LGPL 2.1 with exception (dynamic linking, unchanged) |
| manifold3d | exact boolean cuts (clean halves, rims, holes) | Apache 2.0 |
| VibeCAD build123d skill (rawwerks) | instructions for Claude in `.claude/skills/build123d` | MIT |

Fonts: see `assets/fonts/OFL-*.txt` (SIL Open Font License).
