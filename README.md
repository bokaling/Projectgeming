# ✦ StoryForge: AI story videos from your script

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/bokaling/Projectgeming/blob/main/notebooks/StoryForge_Colab.ipynb)

Paste your story script, press **🚀 Generate**, and get a finished video for YouTube, Shorts,
TikTok, Reels and Snapchat, in **English and Farsi**: pictures, motion, voiceover, word-by-word
captions, music, thumbnail, title, description and hashtags. All software and APIs are **free**.
It runs on Google Colab's GPUs (free T4, or L4/A100 with your Google AI Plus compute units).

- 📝 **Your script, your story.** The AI writer is optional.
- 🎞️ **Short** (~60 s, 9:16, 1080×1920) or **Long** (~10 min, 16:9, 1920×1080, with YouTube chapters)
- 📚 **Batch:** paste several scripts separated by `=====`, and they're made one after another
- 🧑‍🎨 Characters keep the same face in every scene and episode, with varied shots (close-ups, wide
  shots, details, empty places…), lighting and colors
- 🎬 Real image-to-video for "hero" scenes (more on stronger GPUs); 2.5D motion for all other scenes
- 🗣️ One natural male narrator (Kokoro). Characters who speak get their own voice
- 🎵 Gentle cinematic music (no sharp sounds), quietly ducked under the voice; sound effects optional

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
[SCENE] a yellow taxi parked in the rain at 3 a.m., neon signs
NARRATOR: The radio crackled at exactly three in the morning.
MIRA: Who's there?
[SCENE] the dashboard radio glowing red
NARRATOR: A voice answered with her own name.
```

- `[CHARACTER] NIKOLA: man, 40s, short dark hair, lab coat` fixes how a character looks. That description goes
  into every picture where he appears (and decides his voice: man or woman).
- `[SCENE]` is optional. Your `[SCENE]` text is the main picture prompt; the shot type is only added after it.
  Without it, the text is split into scenes and the picture prompts are written for you.
- A new picture every ~2.5 s (short) or ~3 s (long): each scene gets several shots of the same moment.
  You get a warning if the script is shorter than the target length (~150 words for a Short).
- `NARRATOR:` (or plain text without a name) is the narrator. `MIRA:` is a character speaking.
- `[CHAPTER] The road` (optional) sets YouTube chapters for long videos. Without it, there's one about every 90 seconds.
- Farsi works the same way (`راوی:` for the narrator). The language is detected automatically.
- **Batch:** put a line of `=====` between scripts. Each one becomes the next episode of the series.

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
   - Name them with their number (`1.png`, `scene_02.jpg`, `C1.png`). Without numbers, they are used in upload order.
   - From your phone: put them in Google Drive in `StoryForge/series/<series>/episodes/ep01/my_images/`,
     then press **🔄 Check my Drive folder**.
   - Every picture is cropped to fill the frame (no black bars). Each card shows ✅ or **missing**.
   - Wrong picture? **📤 Replace** on its card. Wrong order? ⬆️ / ⬇️ swap it with its neighbour.
4. **Press 🚀 Make video with my images.** If pictures are missing, the app asks you:
   **🎨 Make the missing ones with FLUX**, or **🔁 Reuse the nearest image**.

The normal **🚀 Generate video** button still uses FLUX, as before.

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

Estimated units per video. These are **my estimates** and haven't been measured on a real GPU yet;
the app logs the real numbers, so check them after your first week:

| Video | T4 (fp16) | L4 (bf16, ~2× faster) |
|---|---|---|
| Short, no hero clips | ~8 min · **0.15** | ~5 min · **0.15** |
| Short, 1 hero clip | ~23 min · **0.45** | ~12 min · **0.35** |
| Short, auto heroes (T4 1 / L4 3) | ~23 min · **0.45** | ~22 min · **0.6** |
| Long (10 min), no hero clips | ~40 min · **0.8** | ~21 min · **0.6** |
| Long, 2 hero clips | ~67 min · **1.35** | ~33 min · **0.95** |
| Long, auto heroes (T4 2 / L4 6) | ~67 min · **1.35** | ~53 min · **1.5** |

Plus ~5 minutes per session for setup and loading the models (less with big models kept on Drive).

**Your goal: 30 shorts + 4-5 long videos a month, within 50 units**

- **Cheapest:** **L4**, hero scenes set to **1** for shorts and **2** for long videos, and **batches**
  of 5-10 shorts per session so the models load only once. That's ≈ 30 × 0.35 + 5 × 0.95 + ~2
  (setup) ≈ **17 units**.
- **Best looking within budget:** L4 with **Auto** heroes (3 per short, 6 per long) ≈ 30 × 0.6 + 5 × 1.5
  + ~2 ≈ **28 units**, leaving ~20 for re-dos.
- **Free extra:** long videos on **Kaggle** (free T4 x2, ~30 GPU hours a week) cost 0 units.
- **Avoid the A100** for this: it uses 3-4× the units for a small speed gain.
- **L4 is usually cheaper per video than T4**, because it finishes GPU work about twice as fast for
  only ~1.4× the rate.

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
3. Press **⚡ Quick test** (leave the script box empty, which uses a sample with a narrator and a character).
   In the checklist you want ✅ for: Script, Pictures (`FLUX.2 klein (GPU)`), Depth (`Depth Anything`),
   Voice (`Kokoro`), Final video. Listen: one male narrator, a different voice for MIRA, soft music.
4. Paste one real short script → **🚀 Generate**. Check that scenes look different (close-ups, wide shots,
   empty places), that captions are in sync, and look at the units shown on the Export step.
5. Optional: one **Long** script, then disconnect halfway, reconnect and press Generate again.
   Only the missing parts should be made.
6. All good? Tell Claude, and the update is merged into `main`.

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
      scenes/s01/                        picture, depth, hero clip, your uploads, scene clips
      render/                            finished video parts (for resume)
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
