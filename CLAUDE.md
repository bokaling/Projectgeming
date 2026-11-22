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
* **Asset library** (`assets.py`): `@asset(name, about, tags, aliases)` functions with parameters (size, color,
  level…). `resolve()` maps any name the AI uses (aliases, plurals, last word, difflib) and falls back to
  `crate`. `catalog()` is what the planner AI sees. Part kinds the world animates: `liquid` (fill),
  `crust`, `blade` (spin), `light` (light_on), `glow`.
* **World** (`scene.py`): ONE continuous world per video. Areas laid out along +x, the micro world at z=−90.
  Everything is a pure function of time T (so resume and single-shot renders work). Events: persistent
  (appear, disappear, grow, move, spin, fill, drain, light_on/off, float, show_part, hide_part) and shot-only
  (flow, bubbles, smoke, sparks, glow, alarm, shake, cutaway, xray); groups stagger; `at` = a spoken word,
  a fraction 0-1, or seconds. Cameras: orbit, push_in, pull_out, reveal, fly_over, top_down, close_up,
  low_angle, follow, cutaway, zoom_into, static; distance fits the object; eased flights with a lift between
  shots; a fade instead of a flight into/out of the micro world or after zoom_into; shell objects that block
  the view turn x-ray automatically.
* **Keyword captions** (`captions.keyword_header/keyword_events`): top of the screen, one at a time, colored
  by kind: problem red, part orange, number white, info teal.

## Architecture

| Step | Main | Fallbacks (automatic) |
|---|---|---|
| Script, scene plan, Farsi, titles | Gemini Flash (free key; `strong=True` for script + plan) | Groq → OpenRouter `:free` → Pollinations (no key) → small local model on GPU → built-in template / offline planner |
| 3D render | moderngl on the GPU (EGL) | moderngl on the CPU (Mesa llvmpipe, 2/3 size + upscale) |
| English voice | Kokoro (GPU/CPU) | Kokoro ONNX (same voices, CPU, from GitHub) → Edge TTS → Piper → espeak-ng |
| Farsi voice | Own recording or Edge TTS fa-IR (warn: no commercial grant) | Piper fa_IR |
| Word timing | Kokoro / Edge word timestamps; own voice: CTC forced alignment | Proportional timing by word length |
| Captions | ASS keyword captions, libass `shaping=complex`, Vazirmatn for Farsi | n/a |
| Music + SFX | Generated beds + mechanical SFX (hum, pour, bubbles, zap, click, pop, alarm hum), all < 8 kHz | User library on Drive with `licenses.csv`; Freesound CC0 (optional key) |
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
  world/assets.py  the procedural asset library (add new objects here)
  world/plan.py    scene plan schema, validate + auto-fix, readable summary
  world/planner.py AI planner (Gemini) + offline planner + example match
  world/scene.py   World: layout, events, camera, labels, frame(T)
  world/gl.py      moderngl renderer (shaders, shadows, bloom, labels)
  world/labels.py  label pills and the end card picture
  world/video.py   frames → FFmpeg clip, stills
  world/examples.py  the cow poop demo script + plan
  audio/tts.py     Kokoro, Kokoro ONNX, Edge TTS, Piper, espeak, own voice; word timings
  audio/align.py   CTC forced alignment + proportional fallback
  audio/music.py   music beds, sound design, ducking, loudness
  captions.py      ASS builder: keyword captions, Farsi RTL rules
  render.py        FFmpeg join (copy) + audio mux
  publish.py       thumbnail, title, description, hashtags, chapters, platform checklist
  pipeline.py      runs the steps in order, skips finished work, batch, quick test
  install.py       Colab/Kaggle setup (packages, OpenGL/EGL drivers)
  forms.py         backup mode without the web app
  ui/theme.py      custom Gradio theme + CSS (dark, neon pink/purple)
  ui/app.py        the 4-step web app
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
- [ ] Phase 2: bigger asset library, long videos (chunked planning), 🔧 fix one shot by instruction
      (`Pipeline.fix_scene`), auto quality check (stills + local checks + Gemini vision)
- [ ] Phase 3: polish (camera, lighting, captions, sound), final report

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
