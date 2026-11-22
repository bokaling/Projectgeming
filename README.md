# ✦ StoryForge: AI story videos from your script

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/bokaling/Projectgeming/blob/main/notebooks/StoryForge_Colab.ipynb)

Paste your story script, press **🚀 Generate**, and get a finished video for YouTube, Shorts,
TikTok, Reels and Snapchat, in **English and Farsi**: pictures, motion, voiceover, word-by-word
captions, music, thumbnail, title, description and hashtags. All software and APIs are **free**.
It runs on Google Colab's GPUs (free T4, or L4/A100 with your Google AI Plus compute units).

- 📝 **Your script, your story.** The AI writer is optional.
- 🩺 **Script doctor:** scores your script for retention (hook, stakes, twists, cliffhanger) and can rewrite it.
  You pick your version or the improved one, side by side.
- ✂️ **Edited like a real Short:** a 1 s cold open, a hard cut every ~2 s, punch-in zooms, white flashes on
  reveals, big pop-up captions, hook text at the top, and "Part 2 👀" at the end
- 🎞️ **Short** (~60 s, 9:16, 1080×1920) or **Long** (~10 min, 16:9, 1920×1080, with YouTube chapters)
- 📚 **Batch:** paste several scripts separated by `=====`, and they're made one after another
- 🧑‍🎨 Characters keep the same face in every scene and episode, with varied shots (close-ups, wide
  shots, details, empty places…), lighting and colors
- 🎬 Real image-to-video for "hero" scenes (more on stronger GPUs); 2.5D motion for all other scenes
- 🗣️ One natural male narrator (Kokoro, 1.1× speed, a short pause before each reveal). Characters who speak
  get their own voice
- 🎵 Gentle music that builds tension and drops out right before a reveal; soft, low editing sounds

---

## 🚀 Start (5 steps)

1. Click **Open in Colab** above. *(Private repository? In Colab use **File → Open notebook → GitHub**,
   tick **Include private repos**, and pick `notebooks/StoryForge_Colab.ipynb`.)*
2. **Runtime → Change runtime type** → choose a GPU → **Save**. See "Which GPU?" below.
3. Press ▶ on **1️⃣ Setup**. Allow Google Drive access. Wait 2-4 minutes.
4. Press ▶ on **2️⃣ Start StoryForge** and click **👉 OPEN STORYFORGE**. Keep the Colab tab open.
5. In the app, paste your script, choose **Short** or **Long**, and press **🚀 Generate video**.
   First time? Press **⚡ Quick test** (3 scenes, ~3-8 min) to check that everything works.

When you're done: **Runtime → Disconnect and delete runtime**. A connected GPU keeps using units.

---

## 📝 Script format

```text
[TITLE] The Night Radio
[CHARACTER] MIRA: woman, 30s, short silver hair, yellow raincoat
[STYLE] night, heavy rain, yellow taxi, green radio glow, horror thriller
[SCENE] a yellow taxi parked in the rain at 3 a.m., neon signs
NARRATOR: The radio crackled at exactly three in the morning.
MIRA: Who's there?
[SCENE] the dashboard radio glowing red
NARRATOR: A voice answered with her own name.
```

- `[CHARACTER] NIKOLA: man, 40s, short dark hair, lab coat` fixes how a character looks. That description goes
  into every picture where he appears (and decides his voice: man or woman).
- `[STYLE] night, rain, dark lab, green glow, horror` is the **mood lock**: it goes into every picture prompt, so
  every scene keeps the same time of day, light and colors. No `[STYLE]` line? The app makes one from your
  script and shows it to you (the Script doctor has a button to add it to your script).
- `[SCENE]` is optional. Your `[SCENE]` text is the main picture prompt; the shot type is only added after it.
  Without it, the text is split into scenes and the picture prompts are written for you.
- **One picture every ~5 s** (short, about 12 pictures) or ~10 s (long). The fast cuts in between (every
  1.5-2.5 s, or 3-5 s in long videos) are zooms and crops into different parts of the same picture.
- Faces show the feeling of the line (scared, shocked, angry, sad…), never smiling unless your script says so.
- About **150 words** for a Short, **1500** for a long video. You get a warning if it's much shorter.
- `NARRATOR:` (or plain text without a name) is the narrator. `MIRA:` is a character speaking.
- `[CHAPTER] The road` (optional) sets YouTube chapters for long videos. Without it, there's one about every 90 seconds.
- Farsi works the same way (`راوی:` for the narrator). The language is detected automatically.
- **Batch:** put a line of `=====` between scripts. Each one becomes the next episode of the series.

---

## 🩺 Script doctor (step 1, right under your script)

As soon as you paste, you see a score out of 100 and six bars:
🪝 hook in the first 2 seconds · ⚠️ stakes · ⚡ something new every 5 seconds · ❓ curiosity gaps ·
🎁 payoff and twists · 🧗 cliffhanger. Weak lines are listed with the line number, the reason and what to do.
**Your script is never changed by itself.**

Press **✨ Improve script** and the free AI rewrites it for retention: a shocking first line (max 10 words),
no slow intro, short punchy sentences, a twist about every 15 seconds, specific details, a cliffhanger
(long videos: a mini cliffhanger every ~2 minutes). It keeps your `[TITLE]`, `[CHARACTER]`, `[STYLE]` and
`[SCENE]` lines and your speaker names. You see **yours and the improved one side by side** with both scores.
Press **✅ Use the improved script** or **↩️ Keep my original**. The one you pick is the one Generate and the
Gemini prompts use. (No AI available? You get a light polish only and a note saying so.)

---

## 🍌 Make the pictures yourself in Gemini (no FLUX)

Like the pictures from the Gemini app (Nano Banana) better? Use this mode. FLUX is skipped completely,
so there is no big download and the video is made much faster.

1. **Step 1 · Script:** paste your script, choose **Short** or **Long**, and press
   **📝 Make Gemini prompts**. The app opens the **🍌 My images** tab.
2. **Copy the prompts:** you get one numbered prompt per picture. Each prompt has the full character
   look, the shot type, lighting, mood and the size (vertical 9:16 or horizontal 16:9).
   - Make **C1, C2…** (character sheets) first. Give that picture to Gemini together with the scene
     prompts, so the face stays the same.
   - Use the 📋 button on each prompt, the copy button on the big box ("copy all"), or **⬇️ Download prompts.txt**.
     `prompts.txt` is also saved on Drive in the episode folder.
3. **Upload your pictures:** drop them all at once into **Drop your images here**.
   - **No renaming needed.** Pictures are put in the order you made them (the oldest first): character sheets
     C1, C2… first, then scenes 1, 2, 3… The app reads each file's time from your browser. If your browser
     doesn't share it, it uses the order you selected them in and tells you.
   - A number in the name always wins: `1.png`, `03_taxi.jpg`, `scene_02.jpg`, `C1.png`.
   - Any picture type works: PNG, JPG, **JFIF** (what Gemini downloads), WEBP, HEIC (iPhone) and AVIF.
     They are turned into PNG automatically.
   - From your phone: put them in Google Drive in `StoryForge/series/<series>/episodes/ep01/my_images/`,
     then press **🔄 Check my Drive folder**.
   - Every picture is cropped to fill the frame (no black bars). Each card shows ✅ or **missing**.
   - After the upload the grid shows every picture with its number. Wrong picture? **📤 Replace** on its card.
     Wrong order? ⬆️ / ⬇️ swap it with its neighbour (C1 comes right before scene 1).
   - The Drive folder follows the same rules, using the files' times in Google Drive.
4. **Press 🚀 Make video with my images.** If pictures are missing, the app asks you:
   **🎨 Make the missing ones with FLUX**, or **🔁 Reuse the nearest image**.

The normal **🚀 Generate video** button still uses FLUX, as before. In Gemini mode no image model is loaded at
all (no FLUX, no depth model), so it is the fastest way to make a video.

---

## 🎬 The 6 steps in the app

| Step | What it's for |
|---|---|
| **1 · Script** | Paste your script, choose Short/Long, then **🚀 Generate**. Optional: let the AI write a script from an idea. |
| **2 · Edit** | Change any line, picture prompt, shot type or camera move, then press Generate again (finished parts are reused). |
| **3 · Characters** | Each character's fixed look and reference picture (**📤 My picture** for the best face match), plus **the voice when they speak** with 🔊 preview. |
| **4 · Scenes** | Preview every picture: **🔄 Regenerate**, **📤 Replace** (your picture or video clip), shot type, ⭐ hero. |
| **5 · Voice & Captions** | Narrator voice (male by default), your own recording, caption style, music mood/volume, sound effects on/off. |
| **6 · Export** | Your video, thumbnail, title, description (with chapters), hashtags, downloads, and how many compute units it used. |

**Colab disconnected?** Run cells 1️⃣ and 2️⃣ again and press Generate. Finished pictures, voices,
scene clips and video parts are saved on Drive and reused, even halfway through a 10-minute video.

---

## 💳 Which GPU? (compute units)

The app shows a live **⏱ session timer and compute-unit estimate** at the top, and after each video
it shows how long that video took and about how many units it used. Rates are unofficial
user measurements: T4 ≈ 1.2 units/hour, L4 ≈ 1.7, A100 40 GB ≈ 5.4, A100 80 GB ≈ 7-9.

Estimated time and units per video (after the first video of a session). These are **my estimates**, not
measured on a real GPU yet. Every video now ends with a **⏱ timing report** (each step's time), and
`StoryForge/usage_videos.json` keeps the real numbers, so check them after a few videos:

| Video | T4 (fp16) | L4 (bf16) |
|---|---|---|
| Short, 🍌 your Gemini pictures | ~1.5-2.5 min · **0.04** | ~1-1.5 min · **0.04** |
| Short, FLUX pictures (no hero clips, the default) | ~4-6 min · **0.1** | ~2.5-3.5 min · **0.09** |
| Long (10 min), 🍌 your Gemini pictures | ~7-10 min · **0.18** | ~5-7 min · **0.17** |
| Long, FLUX pictures, no hero clips | ~15-20 min · **0.35** | ~8-11 min · **0.3** |
| Long, FLUX + auto hero clips (T4 2 / L4 6) | ~30-35 min · **0.65** | ~35-45 min · **1.15** |

Plus ~3-5 minutes per session for setup and the first model download (FLUX is ~16 GB; Gemini mode skips it).

Why it is faster now: one picture per ~5 s instead of per ~2.5 s (the fast cuts are crops), the voice is
made while the pictures are made, every scene clip is encoded only once on the GPU encoder (NVENC) with the
captions already in it, the clips are joined without re-encoding, Shorts have no hero clips unless you pick
them, and models stay loaded for the next video in the same session (on L4/A100).

**Your goal: 30 shorts + 4-5 long videos a month, within 50 units**

- **Cheapest:** your own Gemini pictures on a **T4** or **L4**: ≈ 30 × 0.04 + 5 × 0.18 + ~2 (setup) ≈ **4 units**.
- **All automatic (FLUX) on an L4**, batches of 5-10 shorts per session: ≈ 30 × 0.09 + 5 × 0.3 + ~2 ≈ **6 units**.
- **Best looking:** L4 with FLUX and a few hero clips (pick 1-3 per short) ≈ 15-25 units, still well under 50.
- **Free extra:** long videos on **Kaggle** (free T4 x2, ~30 GPU hours a week) cost 0 units.
- **Avoid the A100** for this: it uses 3-4× the units for a small speed gain.

---

## 🔑 Optional free keys (better picture prompts and titles)

Everything works **without keys**. With a free key, the AI picture prompts, translations and titles
are better. In Colab click **🔑 Secrets** → add the name → paste the key → **Notebook access** ON.

| Name | Where (free, no card) |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys |
| `HF_TOKEN` | [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens): faster model downloads |
| `FREESOUND_API_KEY` | [freesound.org](https://freesound.org/apiv2/apply): extra CC0 sound effects |

---

## 🧪 Test this update on a T4 before it goes live

This update is on the branch `claude/nice-noether-0u7lld` and is **not on `main` yet**. To test it:

1. Open the notebook from that branch: in Colab **File → Open notebook → GitHub**, paste
   `https://github.com/bokaling/Projectgeming`, choose the branch `claude/nice-noether-0u7lld`,
   and open `notebooks/StoryForge_Colab.ipynb`.
2. Runtime → **T4 GPU**. In cell 1️⃣ set **BRANCH** to `claude/nice-noether-0u7lld`, then run 1️⃣ and 2️⃣.
3. Paste a short script. Look at the **🩺 Script doctor** score, press **✨ Improve script**, compare, and pick one.
4. **🍌 Gemini mode first (fastest):** Make Gemini prompts → make the pictures in Gemini → drop all the
   downloaded `.jfif` files at once (no renaming) → check the order in the grid → Make video with my images.
5. Watch the video: 1 s cold open with a flash, hook text at the top for 3 s, a cut every ~2 s, big pop-up
   captions in sync, a white flash and a low boom on the reveal, music dropping out just before it,
   "PART 2 👀" at the end. Then read the **⏱ timing report** at the end of the log.
6. Try **🚀 Generate** (FLUX) with the same script and compare the timing report.
7. All good? Tell Claude, and the update is merged into `main`.

---

## 🆘 If something goes wrong

| Problem | What to do |
|---|---|
| "Couldn't download StoryForge" | Check the BRANCH name. Private repo: make it public, or add a `GITHUB_TOKEN` secret. |
| The app link doesn't open / Colab stops the session | Use the **🧰 Backup mode** cell (paste your script there, no web app needed). |
| "The GPU ran out of memory" | **Runtime → Restart session**, run cell 2️⃣, press Generate again. Finished work is kept. |
| Robot voice | The voice services were unreachable. Press Generate later: only the voice is redone, and the whole video gets the same voice. |
| A picture is wrong | Step 4 → **🔄 Regenerate** or **📤 Replace**, then press Generate again. |
| Placeholder pictures (abstract hills) | No picture service worked at that moment. Regenerate later. |

---

## 🗂️ Where your files are (Google Drive)

```
MyDrive/StoryForge/
  series/<series>/series.json            characters, style, voices (shared by all episodes)
  series/<series>/characters/<name>/     reference pictures
  series/<series>/episodes/ep01/
      script.json, script.md             the planned script (scenes, shots, prompts)
      scenes/s01/                        picture, depth, hero clip, your uploads, scene clip (final quality)
      render/                            cold open, end card, editing plan (edit_*.json)
      my_images/                         🍌 your Gemini pictures (+ originals/)
      export/                            ⭐ final video, thumbnails, metadata.md
  library/music/<mood>/                  your own music (+ licenses.csv for automatic credits)
  usage_videos.json                      minutes and compute units per video
  models/                                AI models kept on Drive
```

---

## 💰 Staying monetizable (2026 rules)

- Your own script and edits are the human authorship platforms look for. Recording your own voice
  is even stronger.
- `metadata.md` includes an AI disclosure line and a per-platform checklist (YouTube altered content,
  TikTok AI label, Meta AI info). **Snapchat** doesn't recommend wholly AI-generated videos on Spotlight
  (since July 2026), so add real footage or use it to promote the series.
- **Edge TTS** (the default Farsi voice) has no published commercial license. Your own recording is the
  safe choice.
- Music and sound effects are generated by the app (no copyright claims), or come from your own library
  with credits.

---

## 📜 What's inside (all free, commercial use allowed)

| Part | Tool | License |
|---|---|---|
| Pictures | FLUX.2 [klein] 4B → Pollinations → AI Horde | Apache 2.0 |
| Depth (2.5D) | Depth Anything V2 Small | Apache 2.0 |
| Hero clips | Wan 2.2 TI2V 5B | Apache 2.0 |
| Voices | Kokoro 82M (English), Edge TTS / Piper (Farsi), your voice | Apache 2.0 / see above |
| Captions | FFmpeg + libass, Vazirmatn / Montserrat / Anton | LGPL / SIL OFL |
| Music & SFX | Generated in code | Yours |
| Picture prompts, titles | Gemini / Groq / OpenRouter free tiers, Pollinations, built-in fallback | Free tiers |

Based on [`research.md`](research.md). The plan and rules are in [`CLAUDE.md`](CLAUDE.md).

## 👩‍💻 For developers

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest -q
```

The tests run on a normal CPU without internet (AI services are faked), build real videos with FFmpeg,
and check the audio stays gentle (no energy above 8 kHz in the music).
