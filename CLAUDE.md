# StoryForge Free: plan and rules

A 100% free AI story video maker for serialized episodes (recurring characters,
hook at the start, cliffhanger at the end). It runs on **Google Colab free (main)**
or **Kaggle (backup)** and shows a dark, neon, mobile-friendly web app (Gradio)
that opens in a new browser tab. Source of truth for model and service choices:
`research.md` (November 2026).

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

1. **100% free.** No paid APIs, no trials, no credit card. API keys are optional and free to get;
   the app must fully work with zero keys.
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
