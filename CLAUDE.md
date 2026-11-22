# StoryForge: plan and rules

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
2. **Scene plan** (`world/planner.py`): Gemini (`strong=True`) turns the script into a strict JSON plan
   (areas, objects with asset + params, and per shot: camera, actions, labels, keywords). `world/plan.py`
   validates it and auto-fixes everything (closest asset name, missing targets, number clamps, one shot per
   script scene, keywords ≤4 words, ≤4 labels) and lists the fixes. `plan.md` shows it in plain words.
   No AI → `offline_plan` (finds known objects in the words). The cow demo script → the hand-made example plan.
3. **Voice** (made in a thread at the same time as the plan): Kokoro am_fenrir at 1.1x; word timings.
4. **Timeline** (`Pipeline.timeline`): every shot lasts exactly its voice line + a short breath (whole frames).
5. **3D render** (`world/video.py`): one clip per shot, encoded ONCE at final quality with the keyword
   captions burned in (NVENC or x264 `stitchable=1`), saved to Drive with a fingerprint (resume).
6. Music + sound design → clips joined with `-c copy` + audio → thumbnail (a still of the best shot),
   title, description, hashtags, chapters (long) → ⏱ timing report.

* **Short** = ~60 s (~150 words), 9:16, 1080×1920. **Long** = ~10 min (~1500 words), 16:9, 1920×1080,
  YouTube chapters in the description.
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
* **Asset library** (`assets.py` + `assets_more.py`, 135 objects + 16 recipes): `@asset(name, about, tags, aliases)` functions
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
| Script, scene plan, Farsi, titles | Gemini Flash (free key; `strong=True` for script + plan) | Groq → OpenRouter `:free` → Pollinations (no key) → small local model on GPU → built-in template / offline planner |
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
  world/builder.py   object builder: recipes → models, AI design, Drive library
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

### Verified only on CPU (needs a real Colab run)
NVIDIA EGL rendering on a T4/L4, NVENC, Kokoro (torch), Edge TTS, Gemini/Groq calls (script + plan),
wav2vec2 alignment, the Colab port link (`serve_kernel_port_as_window`). Every one of these has a tested fallback.

### Lessons learned (keep these)
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
