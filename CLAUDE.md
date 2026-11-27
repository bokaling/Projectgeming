# StoryForge: plan and rules

## CODE MAP (read this first, then open only the files you need)

**Which files for which task**
* Rendering / look / shadows / flicker: `world/gl.py` (shaders, shadow map, SSAO, bloom, grade), `world/scene.py`
  (`World.frame` builds a `gl.Frame`: draws, lights, flash/fade, shadow focus), `world/video.py` (frames → FFmpeg).
* Objects / machines: `world/mesh.py` (shapes), `world/assets.py` + `world/assets_more.py` (library), `world/machines.py`
  (engine, car, elevator), `world/kit.py` (mechanism kit), `world/builder.py` (JSON recipes, AI design, self check),
  `world/cad.py` (build123d / bd_warehouse parts, manifold3d cuts), `world/imported.py` (CC0 glTF/OBJ models),
  `world/recipes/*.json`, `world/sense.py` (physical sense check), `world/motion.py` (how parts move).
* Planner (script → plan): `world/planner.py` (AI + offline), `world/plan.py` (validate/auto-fix), `world/examples.py`,
  `world/presets.py`, `world/settings.py` (rooms), `world/decor.py`, `world/logic.py` (ports, pipes, grounding),
  `world/checker.py` (quality check), `world/fixer.py` (fix one shot), `world/cheatsheet.py` → `docs/PLAN_CHEATSHEET.md`.
* Audio: `audio/tts.py` (voices), `audio/align.py` (word times), `audio/music.py` (music beds, SFX, mix, loudness),
  `pipeline.audio_mix` (which sounds go where, SFX level).
* Captions: `captions.py` (ASS: keyword, two-layer, karaoke, Farsi RTL), `pipeline.keyword_items`.
* App UI: `ui/app.py` (4-step Gradio app), `ui/status.py` (progress panel), `ui/theme.py`, `ui/jobs.py`.
* Colab notebook / setup: `notebooks/StoryForge_Colab.ipynb` (2 cells), `install.py` (packages, EGL, CAD tools),
  `forms.py` (backup forms mode), `config.py` (paths, GPU, secrets).
* Whole pipeline / resume: `pipeline.py` (`Pipeline`: scene_plan → timeline → render_clips → audio_mix → final_videos),
  `project.py` (series, episodes, `state.json`, `EpisodeOptions`), `make.py` (CLI).

**Files (key functions)**
| File | What it does |
|---|---|
| `config.py` | settings, Drive paths, Colab/Kaggle detection, GPU profiles, secrets (`secret`, `key_lines`), `encoder_args` |
| `project.py` | `Series`, `Episode`, `State` (resume), `EpisodeOptions` (all user options incl. `sfx`), atomic `write_json` |
| `pipeline.py` | `Pipeline`: `scene_plan`, `save_plan`, `timeline`, `scene_fp`, `render_clips`, `audio_mix`, `final_videos`, `make_video`, `quality_check`, `self_review`, `fix_scene`; `auto_series`, `use_plan` |
| `make.py` | CLI: `python -m storyforge.make --script s.txt [--plan p.json] --res 720p --out v.mp4 [--sfx subtle]` |
| `messages.py` / `net.py` / `llm.py` | progress + friendly errors / HTTP retries / Gemini→Flash-Lite→Groq→OpenRouter chain, `generate_json`, `vision_json` |
| `paste.py` / `script.py` | read a pasted script (tags, batch, timing) / topic → script, templates |
| `doctor.py`, `beats.py` | script doctor score + improve / hooks, reveals, music mood |
| `formats.py` | 6 formats (rules, captions, ending, music mood), `detect` |
| `captions.py` | ASS captions (`keyword_events`, `subtitle_events`, `karaoke_events`, Farsi) |
| `publish.py`, `videos.py` | thumbnail, metadata, chapters / "StoryForge Videos" folder on Drive |
| `render.py`, `media.py` | FFmpeg join (`-c copy`) + mux / ffprobe helpers |
| `audio/music.py` | `generate_music`, `make_sfx` (short one-shots), `mix` (voice + ducked music + SFX), `loudnorm` |
| `audio/tts.py`, `audio/align.py` | Kokoro → Kokoro ONNX → Edge → Piper → espeak / CTC + proportional word times |
| `world/gl.py` | `Renderer.render(Frame)`: stable shadow map (`shadow_box`, texel snap), PCF, SSAO, bloom, DOF, ACES grade |
| `world/scene.py` | `World`: layout, events (`state`), cameras (`camera`, `fit`, `flight`), `frame(T)`, labels, particles, hero/macro |
| `world/video.py` | `make_renderer`, `render_span` (one clip), `render_still`, `RENDER_VERSION` |
| `world/mesh.py` | `Geo`, shapes (box, cylinder, lathe, gear…), `Part`, `Model`, `section` (cut face) |
| `world/assets.py` | `@asset` registry, `build`, `resolve`, `catalog`, `part_list`, `snap_part`, `REAL_SIZE`, core objects |
| `world/assets_more.py` | the rest of the library (animals, vehicles, buildings, machines, science, tools) |
| `world/machines.py` | `car_engine`, `car`, `elevator`, `counter`, `balance_scale` (real working parts) |
| `world/kit.py` | 20 mechanism pieces (`expand`, `compose` templates) |
| `world/builder.py` | recipes → models (`model_from_recipe`), `design` (AI, description first), `self_check` (3 views), `ensure_objects` |
| `world/cad.py` | build123d shapes (fillet, loft, sweep, revolve, holes) + bd_warehouse gears/bearings/bolts/flanges → `Geo`; manifold3d cuts |
| `world/imported.py` | CC0 model packs: download once to Drive, load glTF/GLB/OBJ, rescale, recolour to our palette, register as assets |
| `world/sense.py` | physical sense check (floating parts, shared axes, facing, proportions, real size) |
| `world/motion.py` | part motions (spin, slide, rod, valve, open, lift, stretch, level) as pure functions of T |
| `world/plan.py` | `validate` (auto-fix + list of fixes), `summary` (plan.md), `literal_problems`, `relevant_objects` |
| `world/planner.py` | `visual_ideas`, `ai_plan` (chunks of 14), `make_plan`, `offline_plan` |
| `world/presets.py` / `world/settings.py` / `world/decor.py` | 19 world presets + looks / rooms around a machine (kitchen…) / set dressing |
| `world/logic.py` | ports, routed pipes/cables, assemblies, pushing, `ground_everything`, `place_on_surfaces` |
| `world/checker.py` / `world/fixer.py` | quality check (local + vision) / fix one shot (AI + rules) |
| `world/labels.py` | label pills, stat cards, map insets, end card picture |
| `world/examples.py` | demo scripts + hand-made plans (cow, submarine, sugar, pyramids) |
| `ui/app.py` | the 4-step app (`build_app`, `launch`); `ui/status.py` progress panel; `ui/theme.py` CSS |
| `forms.py` | backup Colab forms (no web app) |
| `install.py` | Colab/Kaggle setup: packages, OpenGL/EGL, optional CAD tools (`setup_cad`) |
| `docs/PLAN_CHEATSHEET.md` | generated list of assets with exact part names (`python -m storyforge.world.cheatsheet`) |
| `LICENSES/assets.md` | every downloaded model pack with its license (CC0 only) |
| `.claude/skills/build123d` | the rawwerks build123d skill (read before writing CAD code) |
| `tests/` | CPU-only tests (`python -m pytest -q`); `tests/test_part14.py` = shadows, flicker, SFX, CAD, imports |

A **low poly 3D "how it works" explainer video maker** (how things work, what happens if, how things are
made, inside machines, science, engineering, history of inventions). Example: how a dairy farm turns cow
manure into electricity. **All software and APIs are 100% free.** It runs on **Google Colab** (main; the
owner has Google AI Plus: 50 compute units a month, T4 / L4 / A100, High-RAM), on a **free Colab CPU
runtime** (slower, 0 units) or **Kaggle** (free backup), and shows a dark, neon, mobile-friendly web app
(Gradio) that opens in a new browser tab. The old picture version is kept on the branch `legacy-images`.

The owner is a beginner coder. Explain things simply, in short sentences.

## Main flow: topic or script → one click → finished video

1. **Topic → script** (`script.write_from_topic`): the free Gemini key writes a script with the retention rules
   (shocking first line ≤10 words, something new every 5 s, specific numbers, satisfying payoff, cliffhanger).
   Or the owner pastes a script: `[TITLE]`, `[STYLE]` (optional), `[SCENE] what we see`, `NARRATOR: line`,
   `[CHAPTER] name` (optional). Several scripts (or topics) separated by `=====` = batch mode.
2. **Scene plan** (`world/planner.py`), in TWO steps: (a) `visual_ideas`: Gemini says per line what the viewer
   must SEE (subject, machine part, setting, number visual, inside or not), (b) `ai_plan` turns lines + ideas into
   a strict JSON plan (areas with a `setting`, objects with asset + params, per shot: camera (target can be
   `obj.part`), actions, labels, keywords). `builder.ensure_objects` designs missing machines with their working
   parts. `plan.literal_problems` rejects shots whose camera subject is not the idea's subject: one AI retry
   with the reasons (`_second_try`), then `fix_literal` aims the camera at the matching object/part locally.
   `world/plan.py` validates it and auto-fixes everything (closest asset name, missing targets, number clamps,
   real size, flows without a target, auto cutaway of machines, one shot per script scene, keywords ≤4 words,
   ≤4 labels) and lists the fixes. `plan.md` shows it in plain words. No AI → `offline_plan` (finds known objects
   and machine parts in the words, runs/lifts/opens machines by their motions). The cow demo script → the
   hand-made example plan. The planner sees `examples.MACHINE_EXAMPLE_PLAN` as its example.
3. **Voice** (made in a thread at the same time as the plan): Kokoro am_fenrir at 1.0x (stories 1.1x); word timings;
   `[PAUSE]` = 0.75 s of silence.
4. **Timeline** (`Pipeline.timeline`): every shot lasts exactly its voice line + a breath (3D formats 0.5 s, min 3 s;
   stories 0.22 s), whole frames.
5. **3D render** (`world/video.py`): one clip per shot, encoded ONCE at final quality with the keyword
   captions burned in (NVENC or x264 `stitchable=1`), saved to Drive with a fingerprint (resume).
6. Music + sound design → clips joined with `-c copy` + audio → thumbnail (a still of the best shot),
   title, description, hashtags, chapters (long) → ⏱ timing report.

* **Short** = vertical 9:16, 1080×1920, 30 s - 3 min (How it works 80 s, documentary ~150 s by default), 150 words a
  minute. **Long** = 8-10 min (~1300-1500 words), 16:9, 1920×1080, YouTube chapters in the description.
* **Script doctor** (`doctor.py`, `beats.py`): instant offline score + weak lines; "✨ Improve" via the LLM chain
  keeps [TITLE]/[STYLE]/[SCENE] and speaker names; old vs new side by side, the user picks.
* **Speed target:** a 60 s Short in under 5 min on a T4. Every video ends with a ⏱ timing report and logs
  minutes and units in `StoryForge/usage_videos.json`.

## The 3D engine (`storyforge/world/`)

* **Renderer: moderngl** (OpenGL 3.3 core, headless EGL). Benchmarked at 1080×1920 on a 4-core CPU:
  moderngl 7.3 fps (MSAA4 + PCF shadows), Three.js in headless Chrome 2.0 fps (frame capture ~0.5 s),
  Blender rejected (~350 MB per session, bpy doesn't match Colab's Python). GPU: NVIDIA EGL
  (`install.setup_opengl` writes `/usr/share/glvnd/egl_vendor.d/10_nvidia.json`). CPU: Mesa llvmpipe; draws
  at 2/3 size with MSAA2 and FFmpeg lanczos upscales to 1080p.
* **Look** (`gl.py`): flat-shaded low poly, sun + hemisphere light, 3×3 PCF shadow map, fog into a dark teal
  gradient, procedural glowing grid floor, HDR + bloom, vignette, fade/flash. Cutaway = clip plane (back faces
  get the darker inner color). X-ray = translucent shell parts with a rim. Particles = small octahedra;
  smoke = translucent puff spheres. Labels = screen-space textured pills made with Pillow (`labels.py`).
* **Shapes** (`mesh.py`): box, cylinder, cone, lathe, icosphere, torus, capsule, tube, extrude, roof, gear,
  plane, arrow, bolt; `Part(name, geo, color, emissive, opacity, shell, pivot, axis, kind)`, `Model(parts,
  anchors, paths)`.
* **Asset library** (`assets.py` + `assets_more.py` + `machines.py` + `kit.py`, ~200 objects + 19 recipes): `@asset(name, about, tags, aliases)` functions
  with parameters (size, color, level…). `resolve()` maps any name the AI uses (aliases, plurals, last word,
  difflib) and falls back to `crate`. `catalog()` is what the planner AI sees. Part kinds the world animates:
  `liquid` (fill/drain), `crust`, `blade` (spin), `wheel` (rolls when moving), `piston` and `rocker` (while
  spinning), `flame` (always flickers), `light` (light_on). Aliases must be concrete nouns (the offline planner
  turns every alias it finds in the text into an object: no "time", "data", "no").
* **World** (`scene.py`): ONE continuous world per video. Areas laid out along +x, the micro world at z=−90.
  Everything is a pure function of time T (so resume and single-shot renders work). Events: persistent
  (appear, disappear, grow, move, spin, fill, drain, light_on/off, float, show_part, hide_part) and shot-only
  (flow, bubbles, smoke, sparks, glow, alarm, shake, cutaway, xray); groups stagger; `at` = a spoken word,
  a fraction 0-1, or seconds. Cameras: orbit, push_in, pull_out, reveal, fly_over, top_down, close_up,
  low_angle, follow, cutaway, zoom_into, static; distance fits the object; eased flights with a lift between
  shots; a fade instead of a flight into/out of the micro world or after zoom_into; shell objects that block
  the view turn x-ray automatically.
* **World presets (phase 5 B, `world/presets.py`):** 19 places (studio, farm, city, house_interior, factory, lab,
  hospital, space, planet_surface, ocean, body, desert, forest, snow, ancient, battlefield, highway, school, office).
  Each sets the renderer colours (`style_of`: background, horizon, floor, grid or none = black lines, sky, sun), the
  ground (`base`, None = space), pad colour, props, people (`[]` = none), fence, lamps, `air` particles (stars, snow,
  bubbles, dust, cells; never within 45 % of the camera distance of the lens) and `fog`. `natural=True` = open ground
  (sea floor, sand, flesh): no pads, ground plate, roads or pipe stands, the floor colour IS the ground. The plan has
  `"preset"`; without it `presets.guess` counts keyword hits (plurals too) in the title + lines (most hits wins).
* **Object builder (phase 5 B, `world/builder.py`):** objects as JSON recipes of basic shapes (box, cylinder, cone,
  sphere, capsule, torus, wedge, tube, extrude; kinds, pivots, shell, opacity, ports, paths). `model_from_recipe`
  checks and builds (clamps sizes, refuses > 120 m, stands it on the ground), `register` adds it to the library.
  Built-in recipes: `world/recipes/*.json` (loaded when `assets` is imported). `planner.make_plan` calls
  `builder.ensure_objects`: unknown assets are designed by Gemini (`strong=True`) and saved to
  `StoryForge/library/objects/`; without AI the closest asset is used. Objects with a `flow` path (blood vessel,
  intestine) carry flows without a `to`. A see-through surface is a `shell` part, so it is left out when it blocks.
* **Formats (phase 5 B, `storyforge/formats.py`):** how_it_works, what_if, how_made, history, top_list, story
  (`EpisodeOptions.video_format`, "auto" = `formats.detect(title)`). Each has script rules (sent to the writer),
  captions (`keywords` or `words` = one big word, red accents), ending (`overview` or `card` = "Part X") and a music
  mood. People have `mood` (neutral, happy, sad, angry, surprised, scared).
* **Machines (round 6, `world/machines.py`, `world/motion.py`):** real working parts at real size. A part's
  `motion` (dict or list): spin, slide (pistons, exact crank+rod motion with `len`), rod (connecting rods), valve
  (cam timing), swing, pulse (sparks), chamber (the gas above a piston: squeezed, coloured by stroke), open (doors,
  lids, flappers; `drive: open` for levers), lift (elevator car, negative = counterweight), stretch (ropes: the
  pivot end stays), level (a float on a named liquid). States: `spin` runs, `lift` (to 0-1), `open`/`close`,
  fill/drain/glow/alarm on one part (`toilet1.tank_water`). `car_engine` (inline 4, 0.6 m), `car` (4.5 m, engine
  bay anchor), `elevator` (4-floor building, shaft, car, counterweight, ropes, sheave, motor, governor), `counter`,
  `balance_scale`; built-in recipes `piston_pump` (the design example), `fridge`, `toilet`. Part `material`
  (metal, paint, glass, plastic, rubber, ceramic, water) = specular highlight + sky reflection (`u_shine`).
  A cutaway (and `xray`) cuts only the SHELL; the works inside stay whole. Objects with `"mount": "car1.engine_bay"`
  sit at another object's anchor (and ride along); never grounded. Flows can follow a model `path` ("intake",
  "loop") with `color2` (hot → cold) and draw glowing arrows along the way; particle size follows the machine size.
* **Camera on a part:** `camera.target = "lift1.car"` frames that part where it is NOW (a follow shot rides the
  rising car); exact part names win over prefixes (`governor` ≠ `governor_rope`), long thin parts (ropes) are
  cropped to the load end, the machine's own walls/panels between the camera and the part are left out, labels
  point at their part (`World.label_point`), alarms on a huge machine only colour the part in the picture.
* **Settings (round 6, `world/settings.py`):** per area: studio (dark grid + a turntable under one machine),
  kitchen, bathroom, garage, street, living_room, office, lab, factory, outdoors, desk; farm/site/town = the old
  pads with props. Rooms are open dollhouse corners (floor, back + left wall, furniture) sized and placed from the
  machine's box, walls don't cast shadows; guessed from object names (×3) + the shot words.
* **Real size:** `assets.REAL_SIZE` (objects drawn far from life size: bottle, phone, coin…) → `plan.validate` sets
  the scale (kept within 0.6-1.6× real); not in micro areas, symbols, the body or space worlds.
* **Framing:** a normal shot puts the subject's box at 68 % of the width (`W_DIV`), at most 92 % of the safe
  height (`H_DIV`).
* **Moves:** `move` takes `"y"` (dive, climb a ramp, rise); a group keeps its formation (offsets from its first
  member). Liquid parts fill/drain from their own bottom (a ballast tank high in a hull drains in place).
* **Keyword captions** (`captions.keyword_header/keyword_events`): top of the screen, one at a time, colored
  by kind: problem red, part orange, number white, info teal.
* **Framing (phase 4):** every shot is framed from the box of what the line talks about (`World.focus_ids`: the
  camera target + nearby action/label targets, only if the subject stays big; groups use their 3 members closest to
  the middle; boxes use `solid_bounds`, so thin chains/cables don't count). `World.fit` solves the distance so the box
  fills `FILL` (0.78) of the SAFE AREA (top 15 % captions, bottom 20 % app buttons) and shifts the camera so it sits
  in its middle. Moves only change angle/elevation and a distance factor k around that fit: every shot moves.
  Wide, low subjects in a tall frame get el ≥ 36. The first shot is never a wide move (`plan.WIDE_MOVES` → close_up).
* **Set dressing** (`world/decor.py`): every area gets a pad (dirt/concrete/grass), props on its edges (hay, buckets,
  barrels, crates, cars), people, a fence or railing, lamp posts (warm point lights, max 4 per frame), stands under
  low pipes; the micro world gets a muddy floor and floating food bits. Env instances are `_env*` ids, not in the plan.
* **Models:** blocky cows (patches, ears, pink muzzle and udder, tail), original blocky people (face, hair/hat),
  steel-frame barn (trusses, stalls, feed rail, lamps, x-ray when it blocks), tractor with glass cab, banded white
  tank with walkway, banded digester, blue genset, bigger houses. `assets._merge_static` merges plain parts of the
  same look into one mesh (cow 40 → 6 draws); `frame()` skips objects outside the view.
* **Ending:** explainers end on `END_OVERVIEW` (3.6 s): fly up to an overview of the whole system working (flows and
  sparks keep running), then back down to shot 1's camera so the video loops. "Part X" end cards are opt-in (story).
* **🧐 Self-review** (`Pipeline.self_review`, after the render): `export/contact_sheet.jpg` (one frame per shot +
  the ending), pixel check (`checker.content_fraction` ≥ 0.3) + Gemini vision with the framing rules; fixes the plan
  and re-renders only the stale clips (one round).
* **Things work (phase 5 A, `world/logic.py`):** ports are model anchors (inlet, outlet, gas_out, wire, power…).
  Objects with `"from": "tank1.outlet", "to": "dig1.inlet"` are routed (pipes: out of the port, down to stand height,
  right-angle bends, into the other port, on `pipe_stand`s; cables hang between ends); flows follow the route.
  Loose pipes are auto-connected to the nearest ports; floating objects are grounded (only gas, sky, micro and
  space things float); `arrival_clamps` start lights/machines when the flow arrives. Assemblies: a moving scraper
  gets a rail + chain + motor; the tractor has a front bucket with a `load` part. Blades (`blade` anchor) push
  `PUSHABLE` piles (`push_links`/`pushed_state`) and piles drop into pits/tanks they reach. Composition: props in
  front of the subject and shell parts in the way are LEFT OUT (no x-ray ghosts); thin posts/beams over the subject
  too. One ground plate under the whole site + gravel roads between areas. Animals/people are filmed from the side
  (el ≤ 20). `checker.logic_problems` (open pipe, tool not touching, subject blocked) runs in the QC and the review.
* **Frozen layout:** after planning, each area's x/z is written into the plan (`scene.freeze_layout`), so a fix
  (bigger tank) never moves other areas. `Pipeline.scene_fp` covers only `plan.relevant_objects(plan, i)` (the
  areas shot i and the shot before look at + what its actions/labels name), so a fix re-renders only the shots
  that show it.
* **Long videos:** `planner.ai_plan` plans 14 shots per request (`CHUNK`); later requests get `world_so_far`
  and must reuse ids; `merge_part` renames clashing ids and pads missing shots; a failing part (not the first)
  uses the offline planner with prefixed ids.
* **🔧 Fix a shot** (`world/fixer.py`, `Pipeline.fix_scene`): Gemini edits that shot's JSON (+ changed/new
  objects); without AI `rule_fix` understands simple words. After a video exists, `make_video()` re-renders only
  stale clips and joins again.
* **🔍 Quality check** (`world/checker.py`, `Pipeline.quality_check`, before the render): small stills, local
  checks (subject in frame and ≥22% of it, camera not inside a solid object or under the floor, labels on screen
  and apart, frame not empty) fixed by camera/label changes; then Gemini vision (`llm.vision_json`, batches of
  8 stills, free key only) → `fixer.fix`. Saved as state "qc", so resume skips it.

## Architecture

| Step | Main | Fallbacks (automatic) |
|---|---|---|
| Script, scene plan, Farsi, titles | Gemini Flash (free key; `strong=True`: 3 retries, waits 5/15/30 s, "Gemini busy, retrying…") | Gemini Flash-Lite → Groq → OpenRouter `:free` (optional keys) → built-in planner (plans) / "Gemini is busy, try again" (scripts with a key) / template (no key). No Pollinations, no local LLM for scripts or plans |
| 3D render | moderngl on the GPU (EGL) | moderngl on the CPU (Mesa llvmpipe, 2/3 size + upscale) |
| English voice | Kokoro (GPU/CPU) | Kokoro ONNX (same voices, CPU, from GitHub) → Edge TTS → Piper → espeak-ng |
| Farsi voice | Own recording or Edge TTS fa-IR (warn: no commercial grant) | Piper fa_IR |
| Word timing | Kokoro / Edge word timestamps; own voice: CTC forced alignment | Proportional timing by word length |
| Captions | ASS keyword captions, libass `shaping=complex`, Vazirmatn for Farsi | n/a |
| Music + SFX | Generated beds ("explainer" by default) + mechanical SFX (hum, pour, bubbles, zap, click, pop, alarm hum, rumble, steam), all < 8 kHz | User library on Drive with `licenses.csv`; Freesound CC0 (optional key) |
| Render | FFmpeg (NVENC if available, else libx264), 30 fps, −14 LUFS, true peak ≤ −1.5 dB | n/a |

### Colab specifics
* Drive mounted at `/content/drive`. Everything lives in `MyDrive/StoryForge/`.
* No big model downloads. Small models (Kokoro, Kokoro ONNX ~350 MB, aligners, Piper voices, fonts) are kept
  on Drive as real files.
* Colab RAM is ~12 GB: one model at a time on the GPU.
* The web app is served through Colab's own port link (no outside tunnel). Optional public Gradio link.
* Kaggle backup: storage in `/kaggle/working/StoryForge`, keys from Kaggle Secrets, public Gradio link.

## Folder layout on Drive

```
MyDrive/StoryForge/
  models/                     small model cache (real files, no symlinks)
  library/music/<mood>/       user's own music, with licenses.csv
  library/sfx/
  series/<series_slug>/
    series.json               voices, episodes (shared by all episodes)
    episodes/ep01/
      state.json              finished steps + fingerprints, so a reconnect resumes
      script.json, script.md
      plan.json, plan.md      the 3D scene plan
      audio/en/s01.wav, s01.json (word times), timeline.json
      stills/s01_9x16.jpg     one still per shot
      render/s01_9x16_en.mp4  the shot clips (final quality, captions burned in)
      export/<slug>_ep01_en_9x16.mp4, thumbnail, metadata.md, metadata.json
```

## Repo files

```
README.md                    beginner guide + "Open in Colab" badge
CLAUDE.md                    this file
requirements.txt             Python packages installed by the setup cell
notebooks/StoryForge_Colab.ipynb   2 cells: Setup, Launch (+ backup forms cell)
notebooks/StoryForge_Kaggle.ipynb  backup, same cells
storyforge/
  config.py        settings, paths, Colab/Kaggle/local detection, secrets, GPU check + profiles
  project.py       series + episode folders, state.json, resume, EpisodeOptions
  messages.py      progress messages, friendly errors, timing report
  net.py           HTTP helper: retries, backoff, provider fallback, usage log
  llm.py           LLM providers and fallback chain, JSON repair
  paste.py         read a pasted script (tags, speakers, batch, word counts)
  script.py        topic → script (retention rules), script → scenes
  doctor.py, beats.py  script doctor, story beats, music mood
  characters.py    speakers and their voices
  models.py        small model downloads checked by size (HF + GitHub files)
  world/mesh.py    low poly shapes, Part, Model
  world/assets.py  the procedural asset library (core objects, registry, palette)
  world/assets_more.py  the rest of the library (add new objects here)
  world/plan.py    scene plan schema, validate + auto-fix, readable summary
  world/planner.py AI planner (Gemini, long videos in parts) + offline planner + example match
  world/fixer.py   🔧 fix one shot: AI edit or simple rules
  world/checker.py 🔍 quality check: local checks + Gemini vision
  world/scene.py   World: layout, events, camera, labels, frame(T)
  world/gl.py      moderngl renderer (shaders, shadows, bloom, labels)
  world/labels.py  label pills and the end card picture
  world/video.py   frames → FFmpeg clip, stills
  world/examples.py  4 demo scripts + hand-made plans (cow/farm, submarine/ocean, sugar/body, pyramids/ancient)
  world/presets.py   the 19 world presets (colours, ground, props, people, air) + guess from the words
  world/builder.py   object builder: recipes (with motions, materials, paths) → models, AI design, Drive library
  world/machines.py  machines with real working parts (engine, car, elevator) + number visuals (counter, scale)
  world/motion.py    how working parts move (crank, rods, valves, doors, lifts, ropes, floats), pure functions of T
  world/settings.py  the place around a machine per area (kitchen, bathroom, garage, street…) + set pieces
  world/recipes/     built-in object recipes (JSON)
  audio/tts.py     Kokoro, Kokoro ONNX, Edge TTS, Piper, espeak, own voice; word timings
  audio/align.py   CTC forced alignment + proportional fallback
  audio/music.py   music beds, sound design, ducking, loudness
  captions.py      ASS builder: keyword captions, Farsi RTL rules
  render.py        FFmpeg join (copy) + audio mux
  publish.py       thumbnail, title, description, hashtags, chapters, platform checklist
  formats.py       the 6 video formats (rules, captions, ending, music mood) + detect from the title
  pipeline.py      runs the steps in order, skips finished work, batch, quick test
  install.py       Colab/Kaggle setup (packages, OpenGL/EGL drivers)
  forms.py         backup mode without the web app
  ui/theme.py      custom Gradio theme + CSS (dark, neon pink/purple)
  ui/app.py        the 4-step web app
  ui/status.py     live progress panel, step checklist, clean mini log, badges, toasts (pure functions)
assets/fonts/      Vazirmatn, Anton, Montserrat (SIL OFL, licenses included)
tests/             CPU-only tests, network calls mocked; 3D tests draw with Mesa (skip without OpenGL)
```

## Rules

1. **Software and APIs 100% free.** No paid APIs, no trials, no credit card. API keys are optional
   and free to get; the app must fully work with zero keys. **Paid Colab GPU runtimes are allowed**
   (the owner's Google AI Plus plan), but the app must still work on a free T4, a free CPU runtime and Kaggle.
2. **Licenses.** Only permissive models and libraries (Apache 2.0, MIT, BSD, OFL, CC0). Never use
   non-commercial licenses (e.g. MMS forced aligner, XTTS fine-tunes). Edge TTS is allowed but always shown
   with a warning.
3. **Secrets.** Keys come only from Colab Secrets, Kaggle Secrets, or environment variables.
   Never hardcode, print, log or save keys to Drive.
4. **Resume.** Every step writes its result to the episode folder and marks it in `state.json`.
   Re-running skips finished work. Writes are atomic (temp file then rename).
5. **Never dead-end.** Every external call has a fallback. If everything fails, show a friendly
   message that says what happened and what to do, and keep the rest of the project intact.
6. **GPU memory.** One big model on the GPU at a time. Unload (`del`, `gc.collect()`,
   `torch.cuda.empty_cache()`) before loading the next. Release the GL context after rendering.
7. **Imports.** Heavy libraries (torch, moderngl, kokoro, gradio) are imported inside functions,
   so the package imports fast and tests run on a weak CPU machine.
8. **Farsi captions.** Logical-order Unicode, wrap each RTL line in U+202B … U+202C, Vazirmatn font,
   `Spacing: 0`, `Encoding: -1`, burn with FFmpeg `ass` filter and `shaping=complex`. Never use
   arabic-reshaper for libass output (it is fine for Pillow text if Pillow has no raqm).
9. **Notebook stays tiny.** Cell 1 installs and mounts Drive, cell 2 launches the app. All logic is
   in `storyforge/`.
10. **Messages.** Simple English with step numbers and emoji, e.g. `🎬 Scene 4/12 ✅ (3.1 s video, 9 s)`.
    Errors: one line of what went wrong, one line of what to do.
11. **UI.** Dark background, neon pink/purple accents, rounded cards, big buttons, works on a phone
    (single column under 768 px).
12. **Tests.** `python -m pytest -q` must pass before every commit. Tests are CPU-only and never
    touch the network (mock it; the Kokoro ONNX download is blocked in `conftest.py`).
13. **Monetization safety** (research.md section 12): keep the script edit step, a "creator note"
    field, own-voice option, AI disclosure checklist at export, and a simple variation warning.
14. **Git.** Work on branch `claude/nice-noether-0u7lld`. Small commits with clear messages.
    Only merge into `main` after the owner has tested the branch on a real Colab T4
    (notebook Setup cell: `BRANCH = "claude/nice-noether-0u7lld"`).
15. **Determinism.** Random things in the world use `zlib.crc32` seeds (never Python's `hash()`), and a
    frame depends only on T, so a re-rendered shot matches its neighbours.

## Status

- [x] Kept from the picture version: config, project/state, messages, net, LLM chain, script doctor,
      Kokoro + backups, word timing, sound design, captions (Farsi), export/publish, batch, resume, timing report
- [x] Pivot phase 1: 3D engine (moderngl), asset library v1 (28 objects), plan schema + validator, AI/offline
      planner, World (events, cameras, labels, cutaway, x-ray, micro world), keyword captions, mechanical SFX,
      Kokoro ONNX backup, new 4-step UI, notebooks, docs; cow poop Short rendered end to end on CPU
- [x] Phase 2: asset library 126 objects (piston/rocker/flame kinds), long videos planned in parts with one
      shared world, frozen area layout + per-shot fingerprints, 🔧 fix one shot (AI + rules, app + backup form),
      🔍 quality check (local + Gemini vision), see-through liquids drawn correctly
- [x] Round 6 (How it works first): T4 crash (`in_nrm`) fixed (only bind inputs a shader has), flows need a target,
      auto series per format + files named by title, vision QC with real errors; two-step planner (visual ideas →
      plan) + literal check + one AI retry; machines with real working parts (engine, elevator, car, fridge, toilet,
      piston pump), motion system, settings per area, real size, camera on a part, numbers as visuals, fact-safe
      scripts, machine tours for the no-AI script; How it works is the default format. Test loop: 4 topics × 3 loops
      (elevator, car engine, fridge, toilet), all rendered end to end on CPU with the Kokoro ONNX voice
- [x] Phase 5 C (UI): job buttons go purple "Working…" (spinner, disabled) → green ✅ Done / red ❌ Failed (ticker,
      `JOB_BUTTONS`, `job.button`); quick buttons use `sync_click`. Always-visible panel: friendly step ("Rendering
      shot 4 of 13"), bar + %, time passed + left, live checklist ⏳🔄✅❌⏭️, last 10 clean log lines, red error box
      with what to do; full log in an accordion; badges (GPU, Gemini, HF, Drive, units); toasts from log lines;
      Export shows the video big + download button + Drive path + contact sheet + timing report
- [x] Phase 5 A: ports + routed pipes/cables, assemblies, pushing into pits, grounding, flows switch things on,
      clean composition (no ghosts, no props in front), ground + roads, side views of animals, opaque captions,
      logic check in QC + self-review
- [x] Phase 5 B: 19 world presets (ground, props, people, light, air), object builder (Gemini recipes, saved to
      Drive, 16 built-in recipes), 6 formats (story: blocky characters with moods, one-word captions, Part X card),
      3 new demos (submarine/ocean, sugar/body, pyramids/ancient) rendered end to end on CPU
- [x] Phase 4 visual quality: bounding-box framing in the safe area (+ check: ≥ 30 % of the frame, not cut off, not
      mostly empty), set dressing, better cow/person/barn/tractor/tank/digester/generator/house, point lights,
      crisper shadows, fainter grid, close hook with a "drop", overview ending that loops, bigger captions,
      post-render self-review with a contact sheet
- [x] Phase 3 polish: seamless horizon (fog melts into the exact background colour per pixel), contact shading,
      stronger rim light, gentle colour grade, slow camera drift (global clock), bigger keyword captions with a
      soft outline, "explainer" music bed as the default, more action sounds (rumble for vehicles and shaking,
      steam hiss for smoke, pour for fill/drain, whoosh on cutaways), one loop of each kind per shot

- [x] Round 2 (mega prompt, see "Round 2" below): busy-Gemini chain (no Pollinations, no local LLM for plans), real
      part names + snapping, target length (150 words/min), light studio + sunny outdoor look, hero part cutaways (pink
      cut faces), macro shots, comparison tables, two-layer captions, calm pacing (4-8 s shots, flights, hard cuts only
      for big changes), filmic lighting (ACES, SSAO, soft shadows, DOF, grades, grain), elevator/engine/fridge/toilet
      fixes, StoryForge Videos folder, CLI + cheatsheet + paste plan, 3D Documentary format (miners test)

### Round 2 (what changed, how it works)
* **AI chain** (`llm.py`): `providers(strong=True)` = Gemini's newest Flash with 3 retries (waits 5/15/30 s, log
  "⏳ Gemini busy…", `net.request(waits=, on_wait=)`), then 2 Flash-Lite models, then Groq/OpenRouter (only with keys).
  `BUSY["main"]` remembers a busy Gemini: `gemini_busy()` skips vision checks; `all_busy(exc)` makes the planner go
  straight to the built-in planner (no second long wait). Scripts with a key that all fail → `FriendlyError(BUSY_TEXT)`.
  `allow_local` defaults to False everywhere. Pollinations is gone.
* **Length** (`paste.target_seconds/target_words`): `EpisodeOptions.seconds` (0 = format default: How it works 80 s,
  documentary 150 s, long 540 s); 150 words/min at 1.0x; narrator 1.0x (story 1.1x, `paste.narrator_speed`). The
  writer gets a word rule and a too-short reply goes back once with its word count; ≥60 % of the target is kept with a
  warning. `[PAUSE]` = `paste.PAUSE_SECONDS` of silence (`scene_speech`), a trailing one holds the picture. A `[SCENE]`
  under 6 words joins the next (`MIN_SHOT_WORDS`); 3D formats: `TAIL_3D` 0.5 s, `MIN_SCENE_3D` 3 s.
* **Part names** (`assets.part_list/snap_part/part_center`): the catalog shows `[parts: …] [mount/ports: …] [paths: …]`
  with the EXACT names. `plan.validate` snaps unknown mounts/targets (`PART_WORDS` synonyms, singular, shared words,
  difflib), mounts may name a real part (top middle of it), and an object that only stands in for a machine's own part
  ("doors" mounted on "lift1.doors") is folded into that part. Never on the ground.
* **Looks** (`presets.LOOKS`, `World.look_of`): studio_light (default, no teal void, no grid), outdoor_day (blue sky
  by view direction + fbm clouds in the background shader, grass, `sky_mode=1`), macro_dark, documentary, underwater,
  space. Order: shot `look` → hero/macro → area `look` → table → documentary format → outdoor settings → preset.
  `Frame.style` overrides the renderer style per frame. A look change, an isolated shot or `"cut": true` = hard cut.
* **Hero shot** (camera `hero`, target `obj.part`): `World.hero_parts` = the FIRST member of the part group by index
  (`_part_k_box`; four parts all called "liner" are not one box) over its whole travel + what touches it (≤2.2× size),
  framed alone on the light studio. Cut plane through its middle turned 55° (outside AND cut face visible). Closed,
  non-shell solids get a flat cut face built on the CPU (`mesh.section`: slice + convex hull, `Frame.dyn`) in
  `HERO_COLOR` #ff3d9a (our pink); open/shell parts get a pink rim (`FRAG_CAP`, `Draw.cap=2`).
* **Macro** (camera `macro`): one member of the part group, ropes cropped to the load end, only parts near it
  (`near_box`), dark look, bloom 0.9, DOF. **Comparison**: area `setting: "table"` (plain light table, look
  studio_light, only that area drawn, the camera frames everything on the table); real-size clamp is skipped when the
  plan gives an explicit scale there. New assets: shot_glass, human_hair, seesaw, ruler.
* **Camera pacing**: calm formats (not story) fly `CALM_FLIGHT` 1.8 s with quintic easing (`smoother`), gentler
  key-word punch-ins, fly_over ±20°, shakes 1/4 (documentary keeps them). Discs that spin about x/z are filmed
  face-on. Room sets: azimuth clamped to the open front/right (−5…95°). Wide cull distance scales with the shot.
* **Lighting** (`gl.py`, Part 6): 12-tap rotated Poisson PCF (CPU 6 taps, `shadow_taps`), wrap diffuse + floor bounce,
  contact shadow, height fog (`u_hfog` per grade), SSAO from the resolved depth (half size, plane-aware, blurred),
  DOF (half-size blur mixed by CoC; macro 0.45, close_up 0.25), ACES filmic + exposure, `GRADES` (bright, dark,
  documentary, underwater, space: saturation, contrast, lift/gain tint, vignette, grain), glass fresnel, additive
  `beam` parts (headlamps). Benchmark 720×1280 CPU (llvmpipe, 4 cores): old 152 ms/frame → new 177 ms/frame (6 taps;
  12 taps: 282). GPU cost of the extra passes is small (not measured on a T4 yet).
* **Captions**: 3D explainers = two layers (`captions.two_layer_header`, `subtitle_events`: 2-3 white words at the
  bottom above the app buttons + ONE big keyword at the top; `plan.validate` keeps 1 keyword/shot, wow > number >
  problem). Part labels are small white pills with a pink dot (`labels.py`). Documentary = karaoke
  (`karaoke_events`: the line stays, the current word bold white, numbers/keywords in a yellow box).
* **Elevator**: passenger + buttons in the car, `snap` (rope whips back, glow, car sags 0.55 m, `st["sag"]` in
  `motion.lift`), `clamp`/snap → brake sparks. **Car + engine**: the car is never a ghost; close on the engine its near
  panels are left out (cutaway car), the hood opens when an engine is mounted; throttle_plate opens (air!).
  **Toilet/fridge**: lathe bowl/pedestal, compressor dome; builder shapes `lathe` and `dome`. Working parts in front of
  a filmed part become see-through instead of missing; flow particles ≤1.2 % of the camera distance; doors stay (not
  cut) in a shot that opens/closes them. Labels are clamped inside the frame (shrunk if too wide).
* **Documentary** (`formats.documentary`, `assets_more`: miner with helmet/headlamp/beam, rescue_capsule, mine
  cross-section): scene `stat {big, small}` cards and `map {lat, lon, place}` insets (`World.overlays`,
  `LabelMaker.stat_card/map_inset`, coarse continents), dark `documentary` look everywhere, no set dressing around a
  `cross_section` asset, mounted groups centred on the anchor, `move` with only `"y"` goes straight up/down.
* **Videos folder** (`videos.py`): `MyDrive/StoryForge Videos/<date> <title> (Short 9x16).mp4` + `.txt` (YouTube,
  TikTok, Instagram, Facebook) + `.jpg`; same name the same day = replaced; "Posted ✅" moves it to `Posted/`;
  `drive_link()` reads the Drive folder id (xattr `user.drive.id`) for a clickable link. Same topic → same episode
  (`pipeline.same_topic_episode`), no "title very close" warning.
* **Cheaper planning**: `python -m storyforge.make --script --plan --res --out` (whole pipeline), `docs/PLAN_CHEATSHEET.md`
  generated by `python -m storyforge.world.cheatsheet` (real part names), app step 2 "📋 Paste plan (JSON)"
  (`pipeline.use_plan`).
* **Doctor**: `score(..., video_format)` adds explainer checks (myth buster early, unit soup, [PAUSE], comparisons,
  1-3 sentences a shot); `improve` uses `IMPROVE_SYSTEM_3D` for every non-story format.

### Part 13: new topics work like library machines
* **Mechanism kit** (`world/kit.py`): 20 animated building blocks as recipe parts (gear_train, piston_crank, valve,
  pump, fan, turbine, belt_drive, chain_drive, pulley_cable, hydraulic_cylinder, spring, lever, wheel_axle, motor,
  battery_wire, heating_coil, tank_pipe, drum, light, emitter). In a recipe `{"kit": "turbine", "name": "compressor",
  "pos", "size", "axis": x/y/z/-x/-y/-z, "stages"…}` → parts "compressor", "compressor_shaft"… (`kit.expand`: positions,
  pivots and motion axes turned with the piece, paths "<name>_<path>", ports both "<name>_inlet" and plain "inlet").
  Every piece is also a library object `kit_<piece>` (`builder.register_kit`, standing on the floor).
* **Builder** (`builder.py`): new shapes gear (+teeth), spring (+turns), blades (+count, twisted), taper, lathe with
  `"caps": false`, dome; kind `heater` (glows orange on `light_on`); motions `pump` (= slide) and `squash` (springs);
  `key_part` → `anchors["key"]`: a cutaway of the whole object cuts through it (`scene.frame`); a moving part without
  a pivot turns about its own pos. Machines merge static parts only within the same name (`_merge_static(by_name)`), so
  every named part stays targetable ("nozzle" ≠ "fuel_nozzles"). The design prompt lists the kit, asks for real
  proportions/materials, key_part, ports, paths, tour.
* **Self check** (`builder.self_check`, `preview_stills`): 3 views (front 3/4, side, cut open through the key part with
  the works moving) → Gemini vision (`CHECK_SYSTEM`) → if not ok, the designer gets the problems + fix and tries again
  (`design(tries=3)` = up to 2 redesigns). Saved to `StoryForge/library/objects/<name>.json` (+ `<name>_check.jpg`)
  with `"checked": "checked"|"unchecked"`; a design that still fails is used for this video but NOT saved. No AI →
  `builder.compose` (kit templates: washing machine, jet engine, microwave, hair dryer, blender), not saved.
* **Places**: settings `laundry` (tiled room, shelf, basket) and `hangar` (light concrete, yellow lines, tall wall,
  crates, a person for scale), guessed from the words/object names.
* **No-AI planner**: `make_plan` composes the title's machine from the kit first; `offline_plan` starts from the
  machine named in the title, so "the drum" is the washer's drum (not a barrel).

### Part 13 test loop (3 topics with NO library object, CPU 720p, designs + plans written as the prompts ask Gemini)
* "How a washing machine works" (1:08, laundry room), "How a jet engine works" (1:02, hangar), "How a microwave heats
  food" (0:59, kitchen). Designs checked from 3 views (as `self_check` shows them to Gemini vision): the washer's
  drain hose ran outside the cabinet → redesigned once. Found and fixed in the ENGINE: a pasted/CLI plan was checked
  without loading the shared library (the washer became a crate) → `Pipeline` loads it and designs missing objects;
  "nozzle" merged into "fuel_nozzles" (same look) → machines merge by name; parts without a pivot orbited the origin
  → pivot = own pos; a hero of a kit assembly showed one blade disc → the whole assembly; a horizontal shaft was
  cropped like a rope → only hanging ropes are cropped; heaters glowed whenever the machine ran → only on `light_on`;
  hero shots pulled in nearby water; the ending overview included the comparison table.
* Not fixed: hero shots of thin bladed stages read as pink "combs"; a design can put parts on top of each other (the
  washer's spring next to its inlet valve crowds that close-up); an object the plan raises (`"y": 0.9`, a microwave on
  a counter) is grounded to the floor; kit templates exist for 5 machine kinds only (others fall back to the closest
  object without AI).

### Research (round 2, not built)
* **HyperFrames** (github.com/heygen-com/hyperframes, Apache 2.0): HTML + CSS + JS/GSAP compositions rendered to MP4
  by seeking every frame in headless Chrome (Puppeteer); needs Node.js 22+ and FFmpeg (`npx hyperframes init`,
  `npx hyperframes render`). Its README documents NO transparent output (no ProRes 4444 / VP9 alpha / PNG sequence
  flags) and no speed numbers. Our own benchmark of headless-Chrome frame capture was ~0.5 s per 1080×1920 frame
  (Three.js test, phase 1): a 60 s overlay layer would be ~15 min of capture on a CPU, far over the "under 1 min extra"
  rule. Not adopted: the overlay layer (captions via libass, stat cards and map insets via Pillow labels drawn by our
  own renderer) costs ~0 s extra. Revisit only if HyperFrames gains a documented alpha output and a fast path.
* **Blender "🎬 Cinematic"** (desk research, NOT run here: no T4 in this session): the official Linux LTS tarball
  (~300 MB download per Colab session, or ~1 GB unpacked kept on Drive) runs headless (`blender -b -P script.py`)
  with its own Python, so no bpy pip package is needed. A converter would write our plan as a .blend (meshes from
  `mesh.py`, keyframes from `World.state`). Eevee needs a GL/EGL context (NVIDIA EGL works on Colab GPUs); Cycles
  works headless on CUDA/OptiX with the OptiX denoiser. Rough expectation for a T4 at 1080×1920: Eevee ~0.3-1 s/frame,
  Cycles 64 samples + denoise ~3-8 s/frame → a 60 s Short (1,800 frames) ≈ 10-30 min (Eevee) or 1.5-4 h (Cycles),
  i.e. about 0.4-1.2 or 3-8 compute units at ~1.8 units/hour. Measure before building: one 10 s test shot.

### Verified only on CPU (needs a real Colab run)
Round 2 additions: the new lighting passes on NVIDIA (SSAO depth resolve, `FRAG_CAP` variant, 12 shadow taps),
the Gemini retry/Flash-Lite chain and the new prompts with real replies, `videos.drive_link()` (Drive folder id via
xattr), the app's 📋 Paste plan box, 📂 Open my videos and Posted ✅ on a phone.
NVIDIA EGL rendering on a T4/L4 (the `in_nrm` fix is tested with a Mesa program that drops the input, not on
NVIDIA), NVENC, Kokoro (torch), Edge TTS, Gemini/Groq calls (script, visual ideas, plan, object designs, vision QC:
the round-6 test loop used replies written by Claude from the exact prompts, not real Gemini), wav2vec2 alignment,
the Colab port link (`serve_kernel_port_as_window`). Every one of these has a tested fallback.

### Round 6 test loop: problems not fixed (after 3 loops)
* Toilet hook: the plan's first shot is a literal close-up of the flush handle: correct, but not striking. The
  prompt now asks that what the first line says HAPPENS on screen; the engine can't make a dull action exciting.
* After a cutaway, doors and lids on the cut side vanish with the shell; "the door closes" is only visible when that
  shot aims the camera at the door (then the cut runs through the door itself).
* Close-ups of an inner part hide the machine's own parts in the way; around the toilet's S-pipe this can make the
  toilet look taken apart (tank pieces hanging in the air).
* Whole-engine shots frame its full box (manifolds, flywheel, plenum): the visible engine is ~50 % of the width,
  not 60-75 %.
* Flow particles right next to a small part (fridge capillary tube) can still look like big diamonds.
* Recipe shapes are basic: the AI-designed toilet bowl is a cylinder, not a curved bowl.
* Room settings are open on two sides (dollhouse): shots from behind a machine look past the room into the studio.
* The engine runs slowed down (0.5 turns/s) so strokes can be followed; each cylinder's flash is short, so a still
  frame can miss it (the hook adds a glow on the spark).
* Not tested against the real Gemini: its replies may be weaker than the recorded ones; the validator, literal
  check, retry, library machines and the no-AI tours are the safety net.

### Round 2 test loop (CPU, 720p, Kokoro ONNX voice, plans written the way the planner prompt asks)
* "How an elevator works" (1:17) and "How a car engine works" (~1:20) rendered end to end with
  `python -m storyforge.make`; "The 33 miners trapped in Chile" (~2 min, 3D Documentary) the same way. Loop 1 found
  (fixed in the engine/checker, not in single videos): the quality check turned hero/macro shots into orbits (it
  measured all four pistons) → it now judges the box the shot frames and leaves isolated shots alone; a 1.8 s shot
  from a trailing `[PAUSE]` → trailing pauses hold the picture, 3 s minimum; the passenger close-up cut his head off
  (only "passenger" matched) → all pieces are "passenger_…"; "CAR + HALF A LOAD" cut at "+" → symbols don't count as
  words; documentary shots were not dark (outdoor rule first) and headlamp beams blew out close shots; grass in front
  of the underground cut; a 300 m camera culled everything (fixed 260 m cut); mounted groups stood beside the
  shelter. CPU render ≈ 7-9 s of render per second of video at 720p (≈ 9-12 min for an 80 s Short).

### Round 2: known problems (not fixed)
* Hero cut faces are the convex outline of each part: a part made of merged pieces (the counterweight's plate stack,
  the crankshaft) gets one big pink face. Real capping would need a stencil pass (moderngl has no stencil API).
* Macro shots in big machines still show the neighbouring parts lit by the sun; the dark look darkens the background
  only. Engine close-ups show the red panels of the cut-open car around the engine (busy picture).
* Comparisons work at everyday sizes (bottle vs shot glass, seesaw); microscopic ones (a droplet next to a hair) break
  the depth buffer (near/far ratio) and are not usable yet.
* Documentary: the mine is a diagram (a 70 m slab for 700 m; the stat card says the real number), the map inset uses
  coarse hand-made continents, karaoke key-word "boxes" are thick libass outlines (rounded), not rectangles.
* Not run against the real Gemini (scripts, ideas, plans with the new prompts), not on a T4 (GPU time of the new
  lighting passes, NVENC with the new look), the long 8-10 min path was not rendered this round.
* HyperFrames was not prototyped and Blender was not run (research notes above).
* The hero cut of a hollow casing (the rescue capsule) still shows a lot of pink inside; the elevator counterweight
  (a merged plate stack) shows one big pink face.

### Lessons learned (keep these)
* GPU drivers remove shader inputs and uniforms a shader never uses (NVIDIA: `in_nrm` of the grid floor). Bind
  attributes through `Renderer.vertex_array` (padding for missing ones) and set uniforms with `set_uniform`.
* Machines: frame the PART the line is about (`obj.part`), cut through that part, hide the machine's own walls in the
  way (never its working parts), see through water in front of it; a mounted machine's parent becomes a ghost.
* A long thin part (rope) is cropped to its load end, but only if it fills its length (two brake blocks 2 m apart
  are not a rope): measure coverage with triangle spans, not vertices (a cylinder has vertices only at its ends).
* `put(..., y=...)` style helpers must not swallow an asset parameter of the same name (the tool wall's `y`).
* Word matching for the no-AI planner: the longest name wins ("car engine" is not also a car), verb-like aliases
  ("lifts a chain", "to scale") are skipped, and words naming a part of a machine already present stay that part.
* Preset keywords must be unambiguous: "a tiny space" in an engine made the whole video outer space.
* A visible change said on the line's last word must still finish inside the shot (`FINISH_IN_SHOT`).
* libass needs `Encoding: -1` in the Farsi style, or Persian word order comes out mirrored whenever a
  word is highlighted (regression test in test_captions.py).
* Gradio 6: theme/css/head go to `launch()`; `elem_classes` lands on two nested elements; Tabs keep a
  hidden measuring copy; the tab container itself is the scrolling `tablist`. Use `.input` (not
  `.change`) for "save settings", or programmatic updates trigger saves.
* Run `pytest` and check ITS exit code before committing (not a piped `tail`).
* Never use `str.replace` with a slice that can be empty: it inserts the text between every character.
* Never use a `spawn`/`forkserver` process pool from the app: children re-run `__main__` (the app or the
  notebook). Run helpers as `python -m ...` subprocesses instead.
* Default arguments are bound at definition time; dataclass fields that depend on others need `__post_init__`.
* Backup voices must keep the gender (the old Piper lessac backup was female).
* Joining clips with `-c copy` needs every clip encoded with the SAME settings (`config.encoder_args("final")`,
  x264 `stitchable=1`), including the end card.
* Remembered things (voice engines, end card PNG) must be keyed so they can't go stale.
* Google Drive can't keep symlinks: models live as REAL files in `models/files/<org>--<name>/`
  (`snapshot_download(local_dir=…)`), `.storyforge_verified.json` lets the next session skip the network.
  Check sizes on the real file (`models.file_problem`).
* Show the real engine error (`tts.error_text`) whenever a voice falls back; a voice that dies mid-video is
  marked broken and the WHOLE video is redone with the backup (`tts.VoiceFailed`).
* Speaker labels can carry notes or markdown: `MIRA (whispering):`, `**NARRATOR:**`. Count words with
  `paste.count_words` (it counts the whole text; count narration words for timing).
* Colab secrets are read only when cell 2 starts (main thread); `config.key_lines()` says which keys were found.
* 3D: back faces must be drawn (cutaways show the inside), shell parts that block the camera go x-ray, but never
  the object the camera is flying away from (it flickers). Into a tank (zoom_into): fade at 72% of the shot,
  before the camera is inside the wall.
* 3D: python `hash()` changes every run; seeds come from `zlib.crc32`. Looped sounds need a seamless loop
  (`music._loopable`), or each repeat clicks.
* Changing the look (shaders, camera, captions): bump `video.RENDER_VERSION`, or old clips on Drive are reused.
* moderngl: `depth_mask` is a FRAMEBUFFER setting (`fbo.depth_mask`); `ctx.depth_mask = False` silently does
  nothing, and glass then hides the liquid inside it. Thick see-through parts (opacity ≥ 0.6) write depth,
  thin glass and x-ray shells don't.
* Frame by what you SEE: a model's box includes thin chains/cables (the scraper's 3 m chain made its blade tiny);
  use `World.solid_bounds`. A long site seen side-on in a tall frame is a thin line: look ALONG it.
* Presets: never take the FIRST matching keyword (the cow script says "stomach" and became "inside the body"):
  count hits. A big see-through sheet (sea surface) over the subject washes the picture out: make it a shell part.
  Air particles near the lens become huge blurry blocks: skip them near the camera.
* Tests that register objects must restore `assets.REGISTRY`/`ALIASES` (other tests count the library).
* `plan.validate` must be idempotent (numbers always float, label `count` kept): saved plans are checked again
  after every edit, and any drift changes every fingerprint (= the whole video re-renders).
* Checks must judge what the shot really draws: a hero/macro shot frames ONE member of a part group; judging the whole
  group made the quality check "fix" every hero shot into an orbit. Isolated shots skip the "something in the way" test.
* A culling distance must scale with the camera distance (a 60 m cross-section needs a camera 300 m away).
* Additive light beams right at the lens white out the picture: draw only a few, never near the camera.
* A stand-in object for a machine's own part ("doors" on "lift1.doors") must be folded into that part, never grounded.
* GLSL: a local variable may not shadow another (`n` for the tap count clashed with the normal `n`).

### Part 14: clean pictures, quiet sound, real objects (this round)
**Part 1, shadows and shimmer (`world/gl.py`, `world/mesh.py`, `world/scene.py`).** The "dotted dark triangles" on the
red car body were **z-fighting**: the tyre's end cap lay exactly in the plane of the body side (both at z = 0.89 m).
* `mesh.resolve_coplanar(model)` (run by `assets.build` for every object): faces of two parts in the same plane facing
  the same way → the smaller part moves out 0.8-12 mm along that normal (whole part, so it stays closed; up to 3
  passes, never undoing an earlier move). The whole library (203 objects) has no coplanar pairs left (test).
* Shadows: the sun and the shadow box are FIXED per shot (`World._shot_light`, blended only during flights and the
  ending, `light_at`); two maps (`Frame.focus_radius` sharp map around the subject, `far_radius` wide map), texel
  snapped and sized in 2^(1/8) steps (`gl.shadow_box`, `quantize_radius`): no swimming. GPU 4096 + 2048 texels,
  CPU 2048 + 1024. Slope-scaled polygon offset on casters (`ctx.polygon_offset = (2, 4)`), normal offset on the
  receiver (≈ one kernel width, more at grazing angles), faces turned away from the sun count as shadowed
  (`facing`): no acne. PCF = a FIXED grid of hardware-filtered taps (`u_taps` 4×4 GPU, 3×3 CPU), no random rotation.
* SSAO: fixed 4×4 interleaved start angles + a depth-aware 4×4 average (`AO_BLUR_FRAG`) + a soft blur. Film grain
  is off in every grade (it changed every frame). MSAA 4 on the CPU too (measured: not slower on llvmpipe).
* The shadow pass applies the same cut plane as the colour pass (a cutaway no longer drops the shadows of the whole
  object in one frame). `Draw.visible=False` = shadow only: objects just outside the picture still cast into it.
* Proof (`docs/part14/`): the same "piston pushes" frame before/after + 200 % crop; 3 s of that shot: worst frame
  85.7 % → 3.8 % of the area changing, mean frame-to-frame noise 2.5 → 0.48; fine noise on flat surfaces 3-5x lower
  in close-ups of the elevator, farm and submarine.

**Part 2, no flashes or pops (`world/scene.py`, `world/motion.py`, `world/checker.py`).**
* What a shot leaves out (walls in the way, panels of a car around its engine, props in front, posts near the lens:
  `_near_lens_parts`) is decided ONCE per shot from camera samples every ~0.4 s (`_shot_vis`), for every flight from
  samples every ~0.15 s (`_flight_vis`) and for the ending overview (`_ending_vis`). Parts fade between the two shots'
  choices while the camera flies; they never pop in the middle of a shot. Parts any shot leaves out never cast
  shadows (`_no_cast`), so no shadow pops either.
* No white flash anywhere (`Frame.flash` removed). Glows/alarms: `slow_pulse` (≤ 2 per second, cosine, starts at 0)
  × `soft_ramp` (0.4 s fade in, fades out after the shot). Spark plugs: a smooth bell; the gas colour blends into the
  next stroke; rope snap: a slow sway; brake sparks build up; x-ray, DOF, beams, air particles, bubbles, smoke and
  flow particles fade instead of switching; shakes in explainers/documentaries are a slow rock (stories keep a jolt);
  cutaways sweep in over 1.4 s.
* Brightness check: `checker.scan_video` draws every frame twice (moving camera, and the same moment from the previous
  frame's camera) → `brightness_jumps`: jump (whole picture > 15 %), pop (content change > 15 % in a ninth of the
  picture with the camera held still), strobe (4+ blinks a second). Hard cuts (±1 frame) are allowed. Results with the
  test scripts in `docs/test_loop/` (old code → new): car engine 9 → 0 problems (the old flashes at 0:20-0:25 are the
  spark/bang colour snaps), elevator 5 → 0, farm 5 → 0, submarine 2 → 0. The ending overview of the car video showed
  blank frames (camera behind the garage wall) → the overview now frames shot 1's machine and leaves walls out.
* `test_part14.py::test_brightness_has_no_jumps_except_hard_cuts` runs a small world (engine sparks, glow, alarm,
  cutaway, rope snap, flights) through the detector at 54×96.

**Part 3, quiet sound (`pipeline.sound_events`, `audio/music.py`).** The noise under the voice was the machine loops
(a hum looped for every shot where a machine spins, plus pour/steam/alarm loops) and the explainer music's soft kick
on every other beat. Now `EpisodeOptions.sfx` = "off" | "subtle" (default) | "full" (old True → subtle, False → off;
app: radio "Sound effects", Colab/Kaggle forms: `SOUNDS`). subtle = soft music + a gentle low whoosh on camera flights
(none on hard cuts) + ONE short soft sound per big moment (`BIG_MOMENTS`: snap, clamp, thud for drop/shake); full adds
short machine sounds when something starts (`FULL_SOUNDS`), reveal booms and the riser. `music.mix` never loops a
sound and cuts every effect at `MAX_SFX_SECONDS` = 2 s with soft fades; effects are lowpassed at 3.2 kHz (subtle) /
5 kHz (full) and duck 80 % / 60 % under the voice. Music presets explainer/tense/dark have no "pulse" layer.
