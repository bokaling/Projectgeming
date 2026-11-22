# StoryForge: plan and rules

An AI story video maker for serialized episodes (recurring characters, hook at the
start, cliffhanger at the end). **All software and APIs are 100% free.** It runs on
**Google Colab** (main; the owner has Google AI Plus: 50 compute units a month, T4 / L4 /
A100, High-RAM) or **Kaggle** (free backup) and shows a dark, neon, mobile-friendly web app
(Gradio) that opens in a new browser tab. Source of truth for model and service choices:
`research.md` (November 2026).

## Main mode (update 2): paste your script → one click → finished videos

* The owner pastes a full script: `[TITLE]`, `[SCENE] what we see` (optional), `NARRATOR: line`,
  `NAME: line` (a character speaking). No `[SCENE]` lines → split automatically (~14 words per
  scene for shorts, ~24 for long). `[CHAPTER] name` is optional. Several scripts separated by a
  line of `=====` = batch mode (made one after another; one failure doesn't stop the rest).
* After **Generate** everything is automatic: read script, plan scenes, pictures, motion, voices,
  captions, music, export, thumbnail, title, description, hashtags. The AI script writer is an
  option (off by default).
* **Short** = ~60 s (~150 words), 9:16, 1080×1920. **Long** = ~10 min (~1500 words), 16:9, 1920×1080,
  YouTube chapters in the description. Every scene clip is encoded ONCE (final quality, captions burned in,
  NVENC if it works) and saved to Drive; the video = clips joined without re-encoding + audio.
* **Script doctor** (`doctor.py`, `beats.py`): instant offline score (hook 2 s, stakes, new every 5 s,
  curiosity, payoff, cliffhanger) + weak lines; "✨ Improve" via the LLM chain keeps [TITLE]/[CHARACTER]/
  [STYLE]/[SCENE] and speaker names (light polish if no AI); old vs new side by side, the user picks.
* **Editing** (`motion/cuts.py`): 1 s cold open (most dramatic picture, flash), hard cuts every 1.5-2.5 s
  (short) / 3-5 s (long) made from crops of ONE picture per ~5 s / ~10 s, cuts on word starts, punch-in on
  hook words, shake on scary words, white flash + low boom on reveals; pop captions 1-3 words with the key
  word highlighted; hook text at the top for 3 s; end card "Part X 👀" / "The End" (checkboxes).
* **Mood lock**: `[STYLE]` line (or made from the script) goes into every FLUX/Gemini prompt; per-shot lighting
  only changes direction, never colors; faces get an expression from the line, never smiling unless written.
* **Pictures:** 8 rotating shot types (wide, medium, detail insert, close-up, empty environment,
  over-the-shoulder, top-down, low angle); the main character appears in about half; composition,
  lighting and color change every scene (never all sepia); face from the reference picture, new
  pose/angle/setting.
* **Audio:** gentle cinematic music only (no bells, hats, ticks, arpeggios), lowpassed at 8 kHz,
  quiet and ducked under the voice; it builds tension, drops out right before reveals and comes back
  with a soft hit. Editing sounds ON by default (toggle): low whoosh on picture changes, low boom on
  reveals, soft riser before the cliffhanger, all lowpassed and ducked; −14 LUFS, true peak ≤ −1.5 dB.
* **Voices:** ONE male narrator by default (Kokoro am_fenrir; Farsi: Edge Farid) at 1.1x speed with a
  0.4 s pause before reveal sentences (word times include it). Each voice's
  engine is chosen once per video; backups keep the same gender; a voice never switches mid-video.
  Characters who speak get their own voice (dropdown + preview on the Characters step).
* **GPU profiles** (`config.gpu_profile`): T4 fp16 / L4 bf16 / A100 bf16; picture size, prompt
  reader kept loaded on L4/A100, Wan 2.2 size/steps, auto hero scenes (Shorts 0 unless chosen; long: T4 2,
  L4 6, A100 10), compute-unit rate. Motion renders on the GPU (PyTorch), 2-3 clips at a time.
* **Speed:** voice is made in a thread while the pictures are made; Gemini mode loads no image model at all
  (no FLUX, no depth); FLUX/depth stay loaded for the next video unless Wan needs the GPU; a working voice
  engine is remembered for the session (forgotten if it fails); every video ends with a ⏱ timing report.
* Session timer + compute-unit estimate in the app; every video logs minutes and units in
  `StoryForge/usage_videos.json`. Big models are kept on Drive automatically when it has 45+ GB free.

The owner is a beginner coder. Explain things simply, in short sentences.

## What the app does (the 6 steps in the UI)

1. **Idea**: series name, episode number, story idea, language (English, Farsi, both), quality.
2. **Script**: AI writes an episode as JSON (3 second hook, 8 to 14 scenes, cliffhanger).
   The user edits it before anything else runs (this is the "human authorship" step).
3. **Characters**: character bible (fixed look text, seed) plus a reference image per character,
   saved per series so every episode reuses them.
4. **Scenes**: one AI image per scene. Preview, Regenerate, or Replace (upload own image or video
   clip). Pick camera move, mark up to 3 "hero" scenes for real image-to-video.
5. **Voice & Captions**: voice per language, upload own recording, caption style preview.
6. **Export**: 9:16 and 16:9 MP4s, thumbnail, title, description, hashtags, AI disclosure checklist.

## Architecture (from research.md, adapted to "Colab main")

| Step | Main | Fallbacks (automatic) |
|---|---|---|
| Script + Farsi translation | Gemini Flash-Lite (free key) | Groq (free key) → OpenRouter `:free` (free key) → Pollinations (no key) → small local model on GPU → built-in template |
| Images | FLUX.2 [klein] 4B on GPU, fp16, multi-reference for consistency | Pollinations (no key) → AI Horde (no key) → placeholder card (user replaces) |
| Motion, every scene | Depth Anything V2 Small depth → 2.5D parallax, Ken Burns, particles, light leaks, grain, shake | Ken Burns only (no depth model) |
| Real image-to-video | Wan 2.2 TI2V 5B for up to 3 hero scenes, with a time budget | Parallax (automatic if no GPU, out of time, or out of memory) |
| English voice | Kokoro (CPU or GPU) | Edge TTS → Piper |
| Farsi voice | Own recording or Edge TTS fa-IR (warn: no commercial grant) | Piper fa_IR |
| Word timing | Kokoro / Edge word timestamps; own voice: CTC forced alignment of the known script | Proportional timing by word length |
| Captions | ASS file, word-by-word highlight, libass `shaping=complex`, Vazirmatn for Farsi | Plain per-line captions |
| Music + SFX | Built-in generated music beds and SFX (no license issues), user's own library on Drive with `licenses.csv` | Freesound CC0 (optional free key); no music |
| Render | FFmpeg (NVENC if available, else libx264), 30 fps, −14 LUFS | n/a |

### Colab specifics
* Drive mounted at `/content/drive`. Everything lives in `MyDrive/StoryForge/`.
* Free Drive is 15 GB. Small models (Kokoro, Depth Small, aligners, Piper voices, fonts) are cached on
  Drive. Big models (klein ~16 GB, Wan ~20 GB) download to `/content` each session unless the user turns
  on `CACHE_BIG_MODELS_ON_DRIVE` and has the space (we check free space first).
* T4 has no bf16: load in fp16. Colab RAM is ~12 GB: load one model at a time, load straight to GPU,
  encode all prompts with the text encoder, unload it, then load the image transformer.
* The web app is served through Colab's own port link (no outside tunnel). Optional public Gradio link
  for using the app on a phone while Colab runs on the PC (warn: research says Colab free may stop
  runtimes that serve web UIs for content generation; resume makes this safe).
* Kaggle backup: storage in `/kaggle/working/StoryForge`, keys from Kaggle Secrets, public Gradio link.

## Folder layout on Drive

```
MyDrive/StoryForge/
  models/                     small model cache (HF_HOME for small models)
  library/music/<mood>/       user's own music, with licenses.csv
  library/sfx/
  series/<series_slug>/
    series.json               characters, style, voices, seeds (shared by all episodes)
    characters/<name>/ref.png
    episodes/ep01/
      state.json              finished steps, so a reconnect resumes
      script.json, script.md
      scenes/s01/image.png, depth.png, motion.mp4, upload.*
      audio/en/..., audio/fa/...
      captions/*.ass
      export/ep01_9x16_en.mp4, ep01_16x9_en.mp4, thumbnail.png, metadata.md
```

## Repo files

```
README.md                    beginner guide + "Open in Colab" badge
CLAUDE.md                    this file
requirements.txt             Python packages installed by the setup cell
notebooks/StoryForge_Colab.ipynb   2 cells: Setup, Launch
notebooks/StoryForge_Kaggle.ipynb  backup, same 2 cells
storyforge/
  config.py        settings, paths, Colab/Kaggle/local detection, secrets, GPU check
  project.py       series + episode folders, state.json, resume, step skipping
  messages.py      progress messages and friendly errors ("what to do next")
  net.py           HTTP helper: retries, backoff, provider fallback, usage log
  llm.py           LLM providers and fallback chain, JSON repair
  script.py        prompts, idea -> episode JSON, editable markdown, Farsi translation
  characters.py    character bible + reference sheets
  images.py        FLUX.2 klein 4B (GPU) + online fallbacks + placeholder
  gemini.py        Gemini images mode: prompts.txt, your uploaded pictures, matching, cropping
  motion/depth.py  Depth Anything V2 Small (+ fake depth fallback)
  motion/effects.py  Ken Burns, parallax, particles, light leaks, grain, vignette, shake
  motion/i2v.py    Wan 2.2 TI2V 5B hero shots with time budget
  motion/clip.py   render one scene clip (any motion or the user's own video)
  audio/tts.py     Kokoro, Edge TTS, Piper, own voice; returns audio + word timings
  audio/align.py   CTC forced alignment (numpy) + proportional fallback
  audio/music.py   generated music beds + SFX, user library, ducking, loudness
  captions.py      ASS builder: TikTok word highlight, Farsi RTL rules
  render.py        FFmpeg final assembly for 9:16 and 16:9
  publish.py       thumbnail, title, description, hashtags, credits, platform checklist
  pipeline.py      runs the steps in order, skips finished work
  ui/theme.py      custom Gradio theme + CSS (dark, neon pink/purple)
  ui/app.py        the 6-step web app
assets/fonts/      Vazirmatn, Anton, Montserrat (SIL OFL, licenses included)
tests/             CPU-only tests, network calls mocked
```

## Rules

1. **Software and APIs 100% free.** No paid APIs, no trials, no credit card. API keys are optional
   and free to get; the app must fully work with zero keys. **Paid Colab GPU runtimes are allowed**
   (the owner's Google AI Plus plan: 50 compute units/month, L4 and A100, High-RAM), but the app
   must still work on a free T4 and on Kaggle.
2. **Licenses.** Only permissive models (Apache 2.0, MIT, OFL, CC0). Never use: FLUX.2 klein 9B,
   FLUX.2 dev, FLUX.1 dev, Depth Anything V2 Base/Large/Giant, MMS forced aligner, XTTS fine-tunes,
   InstantID/insightface. Edge TTS is allowed but always shown with a warning.
3. **Secrets.** Keys come only from Colab Secrets, Kaggle Secrets, or environment variables.
   Never hardcode, print, log or save keys to Drive.
4. **Resume.** Every step writes its result to the episode folder and marks it in `state.json`.
   Re-running skips finished work. Writes are atomic (temp file then rename).
5. **Never dead-end.** Every external call has a fallback. If everything fails, show a friendly
   message that says what happened and what to do, and keep the rest of the project intact.
6. **GPU memory.** One big model on the GPU at a time. Unload (`del`, `gc.collect()`,
   `torch.cuda.empty_cache()`) before loading the next. fp16 on T4.
7. **Imports.** Heavy libraries (torch, diffusers, kokoro, gradio) are imported inside functions,
   so the package imports fast and tests run on a weak CPU machine.
8. **Farsi captions.** Logical-order Unicode, wrap each RTL line in U+202B … U+202C, Vazirmatn font,
   `Spacing: 0`, burn with FFmpeg `ass` filter and `shaping=complex`. Never use arabic-reshaper for
   libass output (it is fine for Pillow text if Pillow has no raqm).
9. **Notebook stays tiny.** Cell 1 installs and mounts Drive, cell 2 launches the app. All logic is
   in `storyforge/`.
10. **Messages.** Simple English with step numbers and emoji, e.g. `🖼️ Scene 4/12 image ✅ (14 s)`.
    Errors: one line of what went wrong, one line of what to do.
11. **UI.** Dark background, neon pink/purple accents, rounded cards, big buttons, works on a phone
    (single column under 768 px).
12. **Tests.** `python -m pytest -q` must pass before every commit. Tests are CPU-only and never
    touch the network (mock it).
13. **Monetization safety** (research.md section 12): keep the script edit step, a "creator note"
    field, own-voice option, AI disclosure checklist at export, and a simple variation warning.
14. **Git.** Work on branch `claude/nice-noether-0u7lld`. Small commits with clear messages.
    Only merge into `main` after the owner has tested the branch on a real Colab T4
    (notebook Setup cell: `BRANCH = "claude/nice-noether-0u7lld"`).

## Status

- [x] Core: config, project/state, messages, net
- [x] Script: LLM chain, writer, editor round-trip, Farsi translation
- [x] Characters + images
- [x] Motion engine + i2v
- [x] Audio: TTS, alignment, music/SFX
- [x] Captions (English + Farsi tested with a real render)
- [x] Render + publish
- [x] Web app UI (desktop + phone screenshots checked)
- [x] Notebooks + README + backup forms mode
- [x] Update 2: paste-script mode, shot variety, gentle audio, one narrator + character voices,
      short/long + chunked render + chapters + batch, GPU profiles + GPU motion + cost meter
- [x] Gemini images mode (`gemini.py`, tab "🍌 My images"): numbered standalone prompts (character sheets C1.. first),
      upload/Drive folder `episodes/epNN/my_images/`, match by number or order, crop to fill, replace/swap,
      missing → ask (FLUX or nearest). `EpisodeOptions.image_source = "mine"` skips FLUX; Generate sets it back to "flux".
- [x] Round 5 fixes: models as real files on Drive (no re-download), real voice errors + whole-video backup,
      keys report, word counter, quiet log.
- [x] Update 4 (viral): script doctor, mood lock + expressions, cold open, fast cuts from crops, pop captions,
      hook text, end card, tension music + editing sounds, 1.1x narrator + reveal pauses, parallel voice,
      single encode + copy join, timing report; uploads ordered by File.lastModified (JS) / Drive mtime,
      C sheets first, .jfif/.heic/.avif → PNG.

### Verified only on CPU (needs a real Colab GPU run)
FLUX.2 klein loading/generation, Depth Anything download, Wan 2.2 hero clips, Kokoro, Edge TTS,
wav2vec2 forced alignment, Pollinations/AI Horde/Gemini/Groq calls, the Colab port link
(`serve_kernel_port_as_window`). Every one of these has a tested fallback.

### Lessons learned (keep these)
* libass needs `Encoding: -1` in the Farsi style, or Persian word order comes out mirrored whenever a
  word is highlighted (verified against a Pillow+raqm reference; regression test in test_captions.py).
* Gradio 6: theme/css/head go to `launch()`; `elem_classes` lands on two nested elements; Tabs keep a
  hidden measuring copy; the tab container itself is the scrolling `tablist`. Use `.input` (not
  `.change`) for "save settings", or programmatic updates trigger saves.
* Don't wait 46 s for Pollinations after a failed connection: circuit breaker in images.py.
* Never save a placeholder as a character reference: it would steer klein later.
* Run `pytest` and check ITS exit code before committing (not a piped `tail`).
* T4 feedback (round 3): `[CHARACTER] NAME: look` is always used for that character; your `[SCENE]` text is the
  main prompt (shot type only appended, never replacing it, and no protagonist is added to it); every prompt ends
  with "No text, no letters, no watermark."; blank/blurry GPU pictures are redone with a new seed (2 more tries);
  a new picture every ~2.5-3 s via several shots per scene (scenes stay whole sentences so the voice sounds
  natural); stronger motion (MOTION_BOOST) + zoom punch on the hook; length warning.
* With a GPU, image errors are SHOWN (FriendlyError), never hidden behind the online queue. Online picture
  services are only used when there is no GPU.
* Model files are checked before loading (`models.ensure_model`: safetensors header + size); broken files
  (e.g. "header too large" from a cut-off Drive copy) are downloaded again.
* Never use `str.replace` with a slice that can be empty: it inserts the text between every character.
* Never use a `spawn`/`forkserver` process pool from the app: children re-run `__main__` (the app or the
  notebook). Run helpers as `python -m storyforge.motion.clip job.json` subprocesses instead.
* Default arguments are bound at definition time (`size=CHUNK_SCENES` ignored later changes).
* Dataclass fields that depend on others need `__post_init__` (formats follow length).
* The old offline English backup voice (Piper lessac) was female: backups must keep the gender.
* Joining clips with `-c copy` needs every clip encoded with the SAME settings (`config.encoder_args("final")`,
  x264 `stitchable=1`), including your own videos and the end card.
* The browser is the only place that knows a file's real time: `theme.HEAD` stores `File.lastModified` on
  change/drop, and the upload event's `js=` passes it to Python as an extra input.
* Remembered things (voice engines, focus points, end card PNG) must be keyed so they can't go stale:
  a failing voice is forgotten; the end card PNG name contains a hash of its text.
* Google Drive can't keep symlinks: after a reconnect, every Hugging Face cache "file" is a 79-byte text stub
  ("../../blobs/<sha>"). Models now live as REAL files in `models/files/<org>--<name>/` (`snapshot_download(local_dir=…)`),
  old caches are migrated by renaming blobs (no download), and `.storyforge_verified.json` lets the next session
  skip the network entirely. Never check sizes on the snapshot path; check the real file (`models.file_problem`).
* Show the real engine error (`tts.error_text`) whenever a voice falls back; a voice that dies mid-video is
  marked broken and the WHOLE video is redone with the backup (`tts.VoiceFailed`).
* Speaker labels can carry notes or markdown: `MIRA (whispering):`, `**NARRATOR:**`, `Dr. Shaw:` (Title Case
  names count when used twice). Count words with `paste.count_words` (dashes and "..." split words).
* Colab secrets are read only when cell 2 starts (main thread); `config.key_lines()` says which keys were found.
