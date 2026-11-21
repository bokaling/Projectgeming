# ✦ StoryForge: a 100% free AI story video maker

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/bokaling/Projectgeming/blob/main/notebooks/StoryForge_Colab.ipynb)

Make serialized AI story episodes (recurring characters, a hook at the start, a cliffhanger at the end)
for YouTube, Shorts, TikTok, Reels and Snapchat, in **English and Farsi**. It runs on **Google Colab's
free GPU**, so your own computer can be slow. No paid APIs, no trials, no credit card.

**What it makes for each episode**

- ✍️ A script you can edit, with a hook and a cliffhanger
- 🧑‍🎨 Characters that look the same in every scene and every episode
- 🖼️ One AI picture per scene (preview it, regenerate it, or replace it with your own picture or video)
- 🎞️ Motion in every scene: 2.5D parallax, Ken Burns, particles, light, camera shake, plus real
  image-to-video for 0 to 3 "hero" scenes
- 🗣️ A natural voiceover in English and Farsi (or your own recorded voice)
- 💬 Word-by-word TikTok-style captions, with correct Farsi
- 🎵 Music and sound effects that are safe to monetize
- 🎬 9:16 and 16:9 videos, thumbnails, titles, descriptions and hashtags

---

## 🚀 Start (5 steps)

1. Click the **Open in Colab** badge above.
   *Your repository is private?* Then in Colab use **File → Open notebook → GitHub**, tick
   **Include private repos**, sign in to GitHub, and pick `notebooks/StoryForge_Colab.ipynb`.
2. In Colab: **Runtime → Change runtime type → T4 GPU → Save**.
3. Press ▶ on **1️⃣ Setup**. Allow Google Drive access when asked. Wait 2 to 4 minutes.
4. Press ▶ on **2️⃣ Start StoryForge**. Click the **👉 OPEN STORYFORGE** link that appears.
   The app opens in a new tab. **Keep the Colab tab open.**
5. In the app, press **⚡ Quick test** first (step 1, "Idea"). In about 3 to 8 minutes you get a short
   3-scene video plus a checklist that shows which parts worked.

> **On your phone:** tick **PUBLIC_LINK** in cell 2️⃣ before running it. You then also get a
> `gradio.live` link that works on any device. Don't share that link.

---

## 🎬 Make an episode (the 6 steps in the app)

| Step | What you do |
|---|---|
| **1 · Idea** | Name your series, type a 1-2 sentence idea, choose languages, formats, the number of scenes and hero scenes (0 to 3, default 2). Press **✨ Write my script**. |
| **2 · Script** | Read and edit the script. This is where the story becomes *yours*. Press **💾 Save my edits**. For Farsi, press **🌍 Translate to Farsi** or type the `Farsi:` lines yourself. |
| **3 · Characters** | Check each character's fixed look. Press **🎨 New picture** until you like it, or **📤 My picture** to use your own. The same look is reused in every episode of the series. |
| **4 · Scenes** | Press **🖼️ Make all pictures**. For any scene: **🔄 Regenerate**, **📤 Replace** (your picture or video clip), change the camera move, or tick ⭐ Hero. |
| **5 · Voice & Captions** | Pick the voices (saved for the whole series), or upload your own recording. Choose a caption style and color, then press **👀 Preview captions**. Set the music mood and volume. |
| **6 · Export** | Press **🎬 Make my video**. When it's done you can watch, download and copy the titles, description and hashtags. |

**Next episode:** on step 1 choose your series, and the episode number goes up by itself. Type what
happens next, or leave it empty to continue from the last cliffhanger.

**Colab disconnected?** Run cells 1️⃣ and 2️⃣ again. The app reopens your episode, and pressing the
button again continues: finished pictures, voices and clips are **not** made again.

---

## 🔑 Optional free keys (better scripts)

Everything works **without keys**. With a free key, scripts and translations come from stronger AI models.

| Key name | Where to get it (free, no card) |
|---|---|
| `GEMINI_API_KEY` | [aistudio.google.com](https://aistudio.google.com) → Get API key |
| `GROQ_API_KEY` | [console.groq.com](https://console.groq.com) → API Keys |
| `OPENROUTER_API_KEY` | [openrouter.ai](https://openrouter.ai) (only free models are used) |
| `HF_TOKEN` | [huggingface.co](https://huggingface.co/settings/tokens): faster, more reliable model downloads |
| `FREESOUND_API_KEY` | [freesound.org](https://freesound.org/apiv2/apply): extra CC0 sound effects |

In Colab click **🔑 (Secrets)** on the left → **Add new secret** → type the name and paste the key →
turn **Notebook access** ON. Keys are never saved in your project or printed.

---

## 🎙️ Your own voice, pictures and music

- **Own voice (best for Farsi and for monetization):** record the whole episode on your phone, reading
  the narration lines in order, then upload one file on step 5. StoryForge cuts it into scenes and
  times the captions.
- **Own picture or clip for a scene:** step 4 → **📤 Replace**.
- **Own music:** put tracks in Google Drive at `StoryForge/library/music/<mood>/` (moods: tense,
  mysterious, sad, hopeful, epic, calm, dark, action, romantic, playful). Add a line to
  `StoryForge/library/music/licenses.csv` and the credit is added to your descriptions automatically.
  Without your own music, StoryForge **generates** music and sound effects itself, so there are no
  copyright claims.

---

## 🆘 If something goes wrong

| Problem | What to do |
|---|---|
| "Couldn't download StoryForge" in Setup | Your repo is private. Make it public (GitHub → Settings → General → Danger Zone → Change visibility), or add a free GitHub token as the Colab secret `GITHUB_TOKEN`. |
| The 👉 OPEN STORYFORGE link doesn't open, or Colab stops the session | Use the **🧰 Backup mode** cell at the bottom of the notebook (plain Colab forms, no web app). |
| "The GPU ran out of memory" | **Runtime → Restart session**, then run cell 2️⃣ again. Your finished work is kept. |
| "No GPU" in the app | Colab didn't give you a GPU today. The app still works, using free online pictures (slower). Or try the **Kaggle** notebook. |
| Placeholder pictures (abstract hills) | No picture service worked at that moment. Press **🔄 Regenerate** later, or upload your own picture. |
| Robotic voice | The internet voices were unreachable. Press **🎬 Make my video** again later: only the voice is redone. |
| Farsi lines missing | Step 2: press **🌍 Translate to Farsi**, or type the `Farsi:` lines yourself. |

Every message in the app tells you what happened and what to do. The full log is under **Show details (log)**.

---

## 🧪 What to test in Colab (first time)

1. **Setup** finishes and prints ✅ for FFmpeg and the core packages.
2. **Start** prints `GPU: Tesla T4` and `Saving to Google Drive`, and the link opens the dark app.
3. **⚡ Quick test** (English) finishes. In the checklist you want: Script ✅, Pictures ✅
   (`FLUX.2 klein (GPU)`), Depth ✅ (`Depth Anything V2 Small`), Voice ✅ (`Kokoro`), Final video ✅.
   Watch the video: does it move, are the captions in sync?
4. Quick test again with **Farsi** ticked: check the Farsi captions read right-to-left and the
   highlighted word moves from right to left.
5. A real episode with **2 hero scenes**: the log shows how long each Wan 2.2 clip took. If a clip
   takes too long, it automatically falls back to motion effects, so you lose nothing.
6. Close the app tab, reopen the link: your episode is still there.

If a ⚠️ shows up in the checklist, the log says why. Share the last 20 lines of the log if you need help.

---

## 🗂️ Where your files are (Google Drive)

```
MyDrive/StoryForge/
  series/<your-series>/series.json          characters, style, voices (shared by all episodes)
  series/<your-series>/characters/<name>/   reference pictures
  series/<your-series>/episodes/ep01/
      script.md                             your script (you can also edit it here)
      scenes/s01/                           picture, depth map, hero clip, your uploads
      export/                               ⭐ final videos, thumbnails, metadata.md
  library/music/<mood>/                     your own music (+ licenses.csv)
  models/                                   small AI models (so they don't download every time)
```

The big AI models (~16 GB image model, ~20 GB video model) are too big for free Drive (15 GB), so
they download into Colab each session (a few minutes). If you have more Drive space, tick
**KEEP_BIG_MODELS_ON_DRIVE** in cell 2️⃣.

---

## 💰 Staying monetizable (2026 rules)

AI videos *can* earn money, but platforms punish copy-paste "slop". StoryForge helps you stay original:

- Always edit the script (step 2) and add a **creator note**. Your own voice is the strongest signal.
- Recurring characters and a real story arc make it a *series*, not a template.
- `metadata.md` adds an **AI disclosure** line and a checklist per platform (YouTube altered content,
  TikTok AI label, Meta AI info).
- **Snapchat:** since July 2026, fully AI-generated videos are not recommended on Spotlight. Add real
  footage (like a filmed intro) or use Snapchat only to promote the series.
- **Edge TTS** voices (the default Farsi voice) are free, but Microsoft hasn't published a commercial
  license for them. Recording your own voice is the safe choice.

---

## 🧰 Backup options

- **Backup mode (no web app):** the last cell of the Colab notebook. Pick an ACTION
  (⚡ Quick test → 1. Write script → 2. Make pictures → 3. Make video), run it, then pick the next one.
- **Kaggle:** `notebooks/StoryForge_Kaggle.ipynb` (GPU T4 x2, about 30 free GPU hours a week, needs a
  phone-verified account). Download your videos before stopping, because Kaggle deletes files unless
  you *Save Version*.

---

## 📜 What's inside (all free, commercial use allowed)

| Part | Tool | License |
|---|---|---|
| Pictures | FLUX.2 [klein] 4B (GPU) → Pollinations → AI Horde | Apache 2.0 |
| Depth (2.5D) | Depth Anything V2 **Small** | Apache 2.0 |
| Hero clips | Wan 2.2 TI2V 5B | Apache 2.0 |
| English voice | Kokoro 82M | Apache 2.0 |
| Farsi voice | Edge TTS (⚠️ see above) / Piper / your voice | LGPL tool, no voice grant |
| Captions | FFmpeg + libass, Vazirmatn / Montserrat / Anton fonts | LGPL / SIL OFL |
| Music & SFX | Generated in code | Yours |
| Script | Gemini / Groq / OpenRouter free tiers, Pollinations, or a local model | Free tiers |

Based on the research in [`research.md`](research.md). The plan and rules are in [`CLAUDE.md`](CLAUDE.md).

## 👩‍💻 For developers

```bash
pip install -r requirements-dev.txt
```

```bash
python -m pytest -q
```

The tests run on a normal CPU without internet (AI services are faked) and build real videos with FFmpeg.
