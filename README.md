# ✦ StoryForge: low poly 3D "how it works" videos

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/bokaling/Projectgeming/blob/main/notebooks/StoryForge_Colab.ipynb)

Type a topic (*how cow poop becomes electricity*) or paste your own script, press **🚀 Make the video**,
and get a finished **low poly 3D explainer**: one 3D world, a camera that flies between the parts,
machines that move, liquids that fill, gas that flows, lights that turn on, numbers that count up,
keyword captions at the top, labels next to the objects, a voiceover, soft music and sound effects.
Plus the thumbnail, title, description, hashtags and YouTube chapters. **Everything is free.**

- 🎬 **Short** (~60 s, 9:16, 1080×1920) or **Long** (~10 min, 16:9, 1920×1080, with chapters)
- 🧊 **The look:** simple shapes, flat colors, soft shadows, a dark teal background and a glowing grid floor
- 🎥 **Camera:** every shot is framed automatically: the thing the line talks about fills the picture, fully
  visible, between the captions (top 15 %) and the app buttons (bottom 20 %). Orbit, push in, follow, low angle,
  close up, cutaway (cut open a tank), x-ray (see through walls), zoom into tiny things like bacteria
- 🏗️ **Real places, not floating objects:** every area gets a ground pad, fences or railings, lamps with warm light,
  hay bales, buckets, barrels, crates, cars and people, automatically
- 🪝 **A close, funny hook** (the demo starts with a cow dropping a 50 kg poop) and an **ending overview** of the
  whole system that flies back to the first shot, so the Short loops. ("Part X" end cards are only for story series.)
- 🧐 **Self-review:** after the render you get `contact_sheet.jpg` (one frame per shot); empty or badly framed shots
  are fixed and only those are rendered again
- ⏱ **In sync:** every shot lasts exactly as long as its voice line, and actions start on the spoken word
  ("the agitator **spins**" → it spins on "spins")
- 🔑 **Keyword captions** at the top, colored by meaning: 🔴 red = problem, 🟠 orange = part name,
  ⚪ white = number
- 🧱 **126 low poly objects** built in code: animals, people, buildings, factories, vehicles, pumps, gears,
  engines, turbines, tanks, pipes, fire, smoke, electricity, cells, bacteria, viruses, molecules, atoms, DNA,
  planets, tools, money, charts, arrows, glass containers and cross sections. Size, color and count can change.
- 🔧 **Fix a shot by typing** ("make the tank bigger", "show the gas flowing"): only that shot is rendered again
- 🔍 **Automatic quality check:** one still per shot is checked before the render (subject in the picture,
  camera not inside a wall, labels apart) and, with a free Gemini key, Gemini looks at every still too
- 🩺 **Script doctor** scores your script for retention and **✨ Improve** rewrites it (you pick)
- 🗣️ One male narrator (Kokoro, 1.1× speed); backups keep the same voice; Farsi works too
- 🎵 A soft "explainer" music bed and sound design that follows the 3D action: machines hum, liquid pours,
  bubbles bubble, sparks zap, vehicles rumble, lights click on, a low whoosh on every camera flight
- 📚 **Batch:** several scripts (or topics) separated by a line of `=====`
- 💻 Works on a **T4 GPU** and also on a **free CPU runtime** (no GPU, no compute units, just slower)

---

## 🚀 Start (5 steps)

1. Click **Open in Colab** above. *(Private repository? In Colab use **File → Open notebook → GitHub**,
   tick **Include private repos**, and pick `notebooks/StoryForge_Colab.ipynb`.)*
2. **Runtime → Change runtime type** → **T4 GPU** (fast) or **CPU** (free, slower) → **Save**.
3. Press ▶ on **1️⃣ Setup**. Allow Google Drive access. Wait 1-3 minutes.
4. Press ▶ on **2️⃣ Start StoryForge** and click **👉 OPEN STORYFORGE**. Keep the Colab tab open.
5. In the app, type a topic and press **✍️ Write the script**, or paste your own script. Then press
   **🚀 Make the video**. First time? Press **⚡ Quick test** (the cow demo, 3 shots, 720p).

When you're done: **Runtime → Disconnect and delete runtime**. A connected GPU keeps using units.

---

## 📝 Script format

```text
[TITLE] How Cow Poop Becomes Electricity
[STYLE] clean low poly farm, warm light          (optional)
[SCENE] wide shot of a dairy barn full of cows
NARRATOR: This farm runs 150 homes on cow poop.
[SCENE] close on the cows, manure piles up in the alley
NARRATOR: Its 2,000 cows make 130 tons of manure. Every single day.
```

- One `[SCENE]` line (what we see) + one `NARRATOR:` line (what is said) = one shot.
- No `[SCENE]` lines? The text is split into shots for you.
- A Short needs about **150 words**, a Long about **1500**. The app counts them for you.
- `[CHAPTER] The digester` (optional) starts a YouTube chapter in long videos.
- Several scripts in one box: put a line of `=====` between them. They're made one after another,
  and one failure doesn't stop the rest.
- Farsi works the same way (`راوی:` for the narrator).

**Topic → script:** with a free Gemini key the AI writes the script with retention rules: a shocking first line,
something new every 5 seconds, real numbers, a satisfying payoff and a cliffhanger. Without a key you get a
simple starter script to edit.

---

## 🎬 The 4 steps in the app

| Step | What it's for |
|---|---|
| **1 · 💡 Topic & Script** | Type a topic or paste a script. 🩺 Script doctor score + ✨ Improve. Short/Long, language, quality. **🚀 Make the video**, or **🧭 Plan first** to see every shot before the render. |
| **2 · 🧭 Scene plan** | The 3D plan in plain words: the world, and for each shot the camera move, what moves, the labels and the keywords, with one still frame per shot. You can edit the plan JSON and press **💾 Check and save the plan** (mistakes are fixed for you). Under every shot: type what to change ("make the tank bigger", "show the gas flowing", "cut it open", "from above") and press **🔧 Fix this shot**. Only the shots that show the change are rendered again. |
| **3 · 🎙️ Voice & Sound** | Narrator voice with 🔊 preview, your own recording, music mood and volume, sound effects on/off. |
| **4 · 🎬 Export** | Your video, thumbnail, title, description (with chapters), hashtags, and the ⏱ timing report. |

**How it works inside:** script → **scene plan** (Gemini writes a strict JSON plan: objects, positions,
animations, camera, labels, keywords; the app checks it and fixes mistakes by itself; long videos are planned
14 shots at a time in one shared world) → **voice** (made at the same time) → **🔍 quality check** (one small
still per shot, broken shots fixed) → **3D render** (one clip per shot, encoded once at final quality) → music
and sound design → the clips are joined without re-encoding → thumbnail and texts.

**Colab disconnected?** Run cells 1️⃣ and 2️⃣ again and press the button again. The plan, voices and finished
3D clips are saved on Drive and reused, so only the missing shots are rendered.

---

## ⚡ Speed (and why this renderer)

I tested three free renderers on the same low poly scene at 1080×1920:

| Renderer | Speed (CPU, 4 cores) | Why / why not |
|---|---|---|
| **moderngl (OpenGL 3.3)** ✅ | **7.3 frames/s** with soft shadows + anti-aliasing | Pure Python package, a few MB. Uses the GPU on Colab (through EGL, no screen needed) and still works on a CPU runtime (Mesa). |
| Three.js in headless Chrome | 2.0 frames/s | Taking each frame out of the browser is the slow part (~0.5 s per frame). |
| Blender (Eevee) | not usable | ~350 MB download every session, and Blender's Python module doesn't match Colab's Python version. |

So StoryForge draws everything itself with **moderngl**: flat-shaded low poly, sun + sky light, soft shadow
map, soft contact shading where things touch the floor, fog that melts into the teal background (no horizon
line), a glowing grid floor, bloom (soft glow), a gentle colour grade, cutaways and x-ray.

| Runtime | 60 s Short | Compute units |
|---|---|---|
| **CPU** (measured: 4 cores, drawn at 720p and scaled to 1080p) | **3 min 14 s** for a 52 s Short (with the quality check) | ~0.01 |
| Colab **CPU** runtime (2 cores) | ~5-7 min (estimate) | 0 on the free plan, ~0.01 with compute units |
| Colab **T4** | ~1.5-2.5 min (estimate, full 1080p) | ~0.05 |
| Colab **L4** | ~1-2 min (estimate) | ~0.05 |

The GPU numbers are estimates until the first real run: every video ends with a **⏱ timing report**
(each step's time) and `StoryForge/usage_videos.json` keeps the real numbers.
No big AI models are downloaded at all: the voice model is ~350 MB once, kept on Drive.

---

## 🔑 Optional free keys (much better plans and scripts)

Everything works **without keys**. With a free key, the AI parts are much better. In Colab click
**🔑 Secrets** (left bar) → add the name → paste the key → switch **Notebook access** ON → run cell 2️⃣ again
(Colab only shares secrets when that cell starts). Cell 2️⃣ prints which keys it found, and the app shows
them in step 1 under **🔑 Free keys**.

| Name | Where (free, no card) | What it turns on |
|---|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key | Topic → script, the 3D scene plan, 🔧 fixing shots in your own words, 🔍 Gemini vision quality check, ✨ Improve script, titles and descriptions, Farsi translation |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (a "Read" token) | Faster, more reliable downloads of the Kokoro voice |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys | Backup AI writer when Gemini is busy |
| `FREESOUND_API_KEY` | [freesound.org](https://freesound.org/apiv2/apply) | Extra CC0 sound effects |

Without a Gemini key, the scene plan is made by a simple built-in planner from the words of your script
(it finds known objects like *cow, tank, pipe, generator, house*). The cow demo has a hand-made plan built in.

---

## 🧪 Test this update before it goes live

This update is on the branch `claude/nice-noether-0u7lld` and is **not on `main` yet**. (The old picture
version is saved on the branch `legacy-images`.) To test it:

1. In Colab **File → Open notebook → GitHub**, paste `https://github.com/bokaling/Projectgeming`, choose the
   branch `claude/nice-noether-0u7lld`, and open `notebooks/StoryForge_Colab.ipynb`.
2. Runtime → **T4 GPU**. In cell 1️⃣ set **BRANCH** to `claude/nice-noether-0u7lld`, then run 1️⃣ and 2️⃣.
   Cell 1️⃣ prints which 3D renderer it found (a line with `GL_RENDERER`: on a T4 it should say NVIDIA).
3. Press **⚡ Quick test**, then paste the cow script (or type the topic) and press **🚀 Make the video**.
4. Read the **⏱ timing report** at the end of the log, and send it to Claude with what you liked or didn't.
5. Optional: try the same on **Runtime → CPU** (free) and compare the timing.

---

## 🆘 If something goes wrong

| Problem | What to do |
|---|---|
| "Couldn't download StoryForge" | Check the BRANCH name. Private repo: make it public, or add a `GITHUB_TOKEN` secret. |
| The app link doesn't open / Colab stops the session | Use the **🧰 Backup mode** cell (paste your script or a topic there, no web app needed). |
| "The 3D renderer couldn't start" | Run cell 1️⃣ again (it installs the OpenGL drivers), then cell 2️⃣. |
| The plan looks simple | Add a free `GEMINI_API_KEY`: the built-in planner only knows the words in your script. |
| Robot voice | The voice services were unreachable. Press the button again later: only the voice is redone, and the whole video gets the same voice. The log shows the real reason with a 🔧 line. |
| A shot looks wrong | Step 2 → type what to change under that shot → **🔧 Fix this shot**. Without a Gemini key the fixer understands simple words: bigger, smaller, closer, further, from above, low angle, spin, flow, cut open, x-ray, light up, smoke, a color, add a pump, label "38 °C", remove labels. |
| "I couldn't understand that change" | Use one of the simple words above, or add a free `GEMINI_API_KEY` (it understands anything). |

---

## 📁 Your files on Google Drive

```text
MyDrive/StoryForge/
  series/<series>/series.json            voices, episode list
    episodes/ep01/
      script.json, script.md             your script
      plan.json, plan.md                 the 3D scene plan (and its readable version)
      audio/en/                          voice per shot, timeline (word times)
      stills/                            one still frame per shot
      render/                            the 3D clip of every shot (final quality)
      export/                            ⭐ final video, thumbnails, metadata.md
  library/music/<mood>/                  your own music (+ licenses.csv for automatic credits)
  usage_videos.json                      minutes and compute units per video
  models/                                the voice models, kept on Drive
```

---

## 💰 Staying monetizable (2026 rules)

- Your topic, your script edits and your creator note are the human authorship platforms look for.
  Recording your own voice is even stronger.
- `metadata.md` includes an AI disclosure line and a per-platform checklist. Low poly 3D doesn't look
  realistic, so YouTube's "altered or synthetic content" label is usually not needed.
- **Edge TTS** (the default Farsi voice) has no published commercial license. Your own recording is the
  safe choice.
- Music and sound effects are generated by the app (no copyright claims), or come from your own library
  with credits.

---

## 📜 What's inside (all free, commercial use allowed)

| Part | Tool | License |
|---|---|---|
| 3D renderer | moderngl (OpenGL 3.3, EGL on the GPU, Mesa on the CPU) | MIT |
| 3D objects | Built-in procedural low poly library, 126 objects (`storyforge/world/assets.py`, `assets_more.py`) | Yours |
| Voices | Kokoro 82M (+ Kokoro ONNX backup), Edge TTS / Piper (Farsi), your voice | Apache 2.0 / see above |
| Captions | FFmpeg + libass, Vazirmatn / Montserrat / Anton | LGPL / SIL OFL |
| Music & SFX | Generated in code | Yours |
| Script, scene plan, titles | Gemini / Groq / OpenRouter free tiers, Pollinations, built-in fallback | Free tiers |

Based on [`research.md`](research.md). The plan and rules are in [`CLAUDE.md`](CLAUDE.md).

## 👩‍💻 For developers

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest -q
```

The tests run on a normal CPU without internet (AI services are faked). They draw real 3D frames with Mesa
(skipped if OpenGL can't start), build real videos with FFmpeg, and check the sounds stay soft (nothing above
8 kHz). Adding a 3D object: write a function with `@asset("name", "what it is", tags, aliases)` in
`storyforge/world/assets_more.py` that returns a `Model` made of shapes from `storyforge/world/mesh.py`. Give moving
parts a `kind` (`blade` spins, `wheel` rolls, `piston` goes up and down, `rocker` swings, `flame` flickers,
`liquid` fills, `light` turns on) and it animates by itself.
