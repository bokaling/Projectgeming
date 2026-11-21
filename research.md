# StoryForge Free: The Best Zero Cost AI Story Video Maker You Can Build With Claude Code (November 2026)

The best zero cost design is a **Kaggle first, Colab second** notebook that runs FLUX.2 [klein] 4B for consistent character images, Depth Anything V2 Small plus FFmpeg for 2.5D motion on every scene, Wan 2.2 image to video only for 2 or 3 "hero" shots per episode, Kokoro (English) and Edge TTS or your own recorded voice (Farsi) for narration, and libass ASS subtitles for word by word captions, with free LLM APIs (Gemini Flash-Lite, Groq) writing the script. The biggest risk is not cost or quality: it is the 2026 platform rules. Snap's Newsroom post "Rewarding Authentic Creativity on Spotlight" (July 31, 2026) says wholly AI-generated videos are no longer eligible for recommendation on Spotlight, and YouTube, Meta and TikTok all demonetize templated, mass-produced content. Your app must therefore build in human authorship (your own voice, edits, recurring story world) rather than just "press button, upload".

## TL;DR

* **Build it as a Kaggle notebook (2× T4 16 GB, 29 GB RAM, 12 hour sessions) with Google Colab free as a backup.** Kaggle's docs give the weekly GPU quota as "30 hours or sometimes higher depending on demand and resources", and Kaggle staff confirmed that one hour on T4 x2 uses one hour of quota even though you get two GPUs. Use only Apache 2.0 or similarly permissive models: FLUX.2 [klein] 4B (images plus multi-reference character consistency), Depth Anything V2 Small (parallax), Wan 2.2 (real image to video for a few shots), Kokoro (English voice), Whisper / forced alignment (timestamps), FFmpeg + libass (captions and render).
* **Realistic output at zero cost: about 1 polished serialized episode per day** (one 60 to 90 second vertical cut plus one 16:9 cut), taking roughly 20 to 30 minutes of GPU time without real image to video, or about 1 hour with 2 or 3 Wan 2.2 hero clips. Free LLM limits will never be the bottleneck; GPU hours and platform originality rules are.
* **To stay monetizable, the app must not be a slop factory**: human-in-the-loop script editing, your own voice (at least for Farsi), recurring characters and story arcs, AI disclosure toggles, and a "variation checker" so episodes never look templated. Treat Snapchat Spotlight as a promo channel only. Snap's Newsroom post "Rewarding Authentic Creativity on Spotlight" (July 31, 2026) says "wholly AI-generated videos will no longer be eligible for recommendation on Spotlight". Only content "enhanced or edited using Snapchat's AI creative tools" stays eligible.

## Key Findings

* **Free GPU reality, late 2026**
  * Kaggle is now the more predictable free GPU. GPU T4 x2 has been the only free GPU option since Kaggle retired the P100 on 15 September 2026; the Kaggle staff announcement "Sunsetting the NVIDIA Tesla P100 GPU on September 15, 2026" says P100 notebooks were moved to T4 x2 automatically. You get 16 GB per card, 4 CPU cores, 29 GB RAM, a weekly quota of "30 hours or sometimes higher" (one hour on T4 x2 counts as one hour, per Kaggle staff), 12 hour sessions and 20 GB of auto-saved disk in /kaggle/working. A phone-verified account is required.
  * Google Colab free does not publish limits. Its FAQ says free notebooks "can run for at most 12 hours, depending on availability and your usage patterns", GPU access is not guaranteed, and sessions drop after roughly 90 minutes idle.\[1\]\[2\] Users measured roughly 12 GB of system RAM in 2026, which is the real limit for offloading big video models.\[3\]
  * Colab's FAQ warns that free users "commonly experience runtime terminations when attempting to bypass the notebook UI and using a web UI on a Colab managed runtime for content generation".\[2\] So **no ComfyUI, Gradio or tunnels on Colab free**: everything must run as plain Python inside notebook cells.
* **Free LLM APIs shrank in 2026**
  * Gemini: an AI Studio reading on October 21, 2026 showed Gemini 3.8 Flash at 5 RPM and only 20 requests a day, Gemini 3.5 and 3.1 Flash-Lite at 15 RPM and 500 a day, Gemma 4 at 30 RPM and 14,400 a day, and Pro models at 0. Limits apply per project, not per key, and reset at midnight Pacific.\[4\] Google itself says free limits are not guaranteed.\[5\]
  * Groq (no card): the rate-limits page (console.groq.com/docs/rate-limits) lists gpt-oss-120b and Qwen3.8 27B at 30 RPM, 1,000 requests a day, 8,000 tokens a minute and 200,000 tokens a day, "applied at the organization level". Llama 3.1 8B Instant gets 14,400 requests a day and Whisper Large v3 gets 2,000 requests a day.
  * OpenRouter `:free` models: 20 requests a minute and only 50 a day unless you have bought $10 of credits\[6\]\[7\] (which you must not do under your rules).
  * Pollinations: the keyless Classic API is free, but limited to one image at a time at least 45 seconds apart per IP. Keyed access runs on "Pollen" credits, and the free hourly Pollen refill was ended on 2026-07-10.\[8\]\[9\]
  * Hugging Face Inference Providers: officially $0.10 a month of credits for free users, "subject to change". One October 2026 tutorial claims free credits were removed entirely, so treat HF inference as unreliable.\[10\]\[11\]
* **Licenses decide your model choices**
  * FLUX.2 [klein] 4B and 4B Base are Apache 2.0; klein 9B and FLUX.2 [dev] are under the FLUX Non-Commercial License.\[12\]\[13\]\[14\]\[15\] FLUX.1 [dev] is also non-commercial.
  * Wan 2.2 is Apache 2.0.\[16\] LTX-2.x weights use the LTX-2.x Community License: free commercial use for entities under $10 million in annual revenue, which covers you, but it is not OSI open source.\[17\]\[18\]
  * Depth Anything V2 Small is Apache 2.0; Base, Large and Giant are CC-BY-NC-4.0 (non-commercial).\[19\]\[20\] Use Small only.
  * Kokoro is Apache 2.0.\[21\] Edge TTS has **no published Microsoft commercial grant**, and Kokoro has **no Persian voice**.\[22\]\[23\]\[24\]
* **Farsi is solvable but needs care**
  * Edge TTS has natural fa-IR-DilaraNeural (female) and fa-IR-FaridNeural (male) voices.\[25\]\[26\]\[27\] Since edge-tts 7.2.0 the default is `SentenceBoundary`, so you must request `boundary="WordBoundary"` and stream (not `save()`) to get per-word timings.\[28\]\[29\]
  * Stock Whisper is weak on Persian (roughly 17 to 50% WER depending on the test set), so do not transcribe; **force-align your known script** instead.\[30\]\[31\] WhisperX ships a Persian alignment model (`jonatasgrosman/wav2vec2-large-xlsr-53-persian`).\[32\]
  * For burned-in Farsi captions, use FFmpeg's `ass` filter with `shaping=complex` (HarfBuzz), a Persian font like Vazirmatn, Unicode RTL embedding marks around each line, and letter spacing 0.\[33\]\[34\]\[35\]

## Details

### 1. Free cloud GPU comparison

| Platform | GPU / VRAM | System RAM | Session | Weekly / daily limit | Background run | Key rules |
|---|---|---|---|---|---|---|
| **Kaggle (recommended main)** | 2× T4, 16 GB each (P100 retired 15 Sep 2026) | 29 GB | 12 h GPU | ~30 h/week, "sometimes higher" | Yes (Save Version runs with tab closed) | Phone verification; idle sessions still burn quota; stop sessions manually |
| **Google Colab free (backup / interactive)** | Usually T4 16 GB, not guaranteed | ~12 GB measured | Max 12 h, ~90 min idle timeout | Unpublished, dynamic | No | No web UIs for content generation, no SSH/remote desktop; account switching to dodge limits is against the terms |
| Hugging Face ZeroGPU Spaces | Shared, short bursts | n/a | Seconds to minutes | Small daily quota | n/a | Good only as an emergency image backup\[36\] |

* **Why Kaggle first:** 29 GB RAM lets you offload big models (Wan 2.2 14B GGUF, FLUX text encoders) that crash Colab's ~12 GB, and Kaggle publishes a real weekly quota and can run a whole episode with your browser closed.\[3\]\[37\]
* **Why keep Colab:** it mounts Google Drive natively, is better for the interactive "edit the script" step, and gives extra GPU hours when Kaggle's week runs out.
* **T4 gotcha:** the T4 is a Turing GPU with no native bf16 or FP8, so load models in fp16 or GGUF quantization. Many 2026 tutorials assume RTX 40/50 cards; their timings will be 3× to 10× faster than what you will see.

### 2. Script writing (free LLMs)

| Option | Free limit (late 2026) | Quality for story scripts | Role |
|---|---|---|---|
| Gemini 3.5 / 3.1 Flash-Lite | 15 RPM, 500/day | Good, long context | **Main** |
| Gemini 3.8 Flash | 5 RPM, 20/day | Best Gemini free | "Polish pass" only |
| Groq gpt-oss-120b or Qwen3.8 27B | 30 RPM, 1,000/day, 8K tokens/min, 200K tokens/day (Groq rate-limits docs) | Good, very fast | **Backup 1** |
| Gemma 4 via Gemini API | 30 RPM, 14,400/day | Decent | Backup 2 / titles, hashtags |
| OpenRouter `:free` | 20 RPM, 50/day | Varies | Backup 3 |
| Pollinations keyless text | 1 request per 30 s per IP | Varies | Last resort |
| Local small model on GPU (e.g. a 7B to 9B instruct model in 4-bit) | Unlimited | Fair | Offline fallback, uses GPU time |

* One episode needs only about 5 to 10 LLM calls (outline, script, scene breakdown with image prompts, Farsi translation, metadata). **Even the tightest tier covers dozens of episodes a day**, so the LLM step is never your bottleneck.
* Gemini free tier data may be used to improve Google products: do not paste anything private.\[38\]
* Make the LLM output **strict JSON** (scenes, narration per scene, visual prompt, characters present, camera move, SFX tags) so the rest of the pipeline is deterministic.

### 3. Image generation

| Option | License (commercial) | VRAM | Speed on T4 (estimate) | Character consistency | Verdict |
|---|---|---|---|---|---|
| **FLUX.2 [klein] 4B** | Apache 2.0 ✅ | ~13 GB per BFL (fits 16 GB T4 in fp16 or quantized) | Roughly 10 to 25 s per 1024 px image at 4 steps (my estimate; BFL benchmarks are on RTX 5080/5090) | Built-in multi-reference editing | **Main**\[12\] |
| SDXL (+ IP-Adapter) | CreativeML Open RAIL++-M, commercial allowed | ~8 to 10 GB | ~30 s per 1024 px image at 25 steps | IP-Adapter / LoRA | Backup on GPU\[36\] |
| FLUX.1 [schnell] | Apache 2.0 ✅ | GGUF fits T4 | 4 steps, moderate | No native reference | Backup\[39\] |
| FLUX.2 [klein] 9B, FLUX.2 [dev], FLUX.1 [dev] | Non-commercial ❌ | | | | **Do not use**\[40\] |
| Pollinations keyless (Flux) | Check terms per output | Cloud | 1 image per 45 s per IP | Seed only | Online backup when no GPU |
| HF Inference Providers | $0.10/month, may be removed | Cloud | n/a | n/a | Not reliable |

* Klein 4B's big advantage for you is **multi-reference editing**: feed each scene the character sheet images, so the same faces and outfits carry across scenes and episodes without training anything.

### 4. Character consistency (scenes and episodes)

Use these layers together, in this order of value:

1. **Character bible (JSON on Drive):** for each recurring character, a fixed name, a fixed 40 to 60 word visual description (age, face, hair, clothing, color palette) and a style string. The LLM must copy it verbatim into every prompt.
2. **Reference sheet per character:** generated once (front, three-quarter, side, full body), hand-picked by you, and saved to `characters/<name>/ref_*.png`.
3. **Reference conditioning:** pass 1 to 3 reference images into FLUX.2 klein 4B's multi-reference mode for every scene where that character appears.
4. **Fixed seeds per character and per location**, plus a fixed style string, to reduce drift.
5. **Optional LoRA** on klein 4B Base (Apache 2.0) for your 2 or 3 main characters once the series takes off.\[41\]\[42\] On a T4 this is slow and fiddly, so treat it as a later upgrade, not version 1.
6. **Auto check:** compute face/CLIP similarity between each scene image and the reference sheet, and regenerate anything below a threshold (max 2 retries).

* Avoid InstantID or anything built on insightface's pretrained face models in a monetized pipeline: those face models are widely reported as non-commercial (verify before use).

### 5. Image to video on free GPUs

| Model | License | Fits free T4? | Time per ~5 s clip on T4 | Quality | Verdict |
|---|---|---|---|---|---|
| **Wan 2.2 14B I2V (GGUF Q4/Q5 + offload)** | Apache 2.0 ✅ | Yes with GGUF and CPU offload (needs Kaggle's 29 GB RAM) | 18 min for GGUF Q4 on a free Colab T4 per the Agathas Web UK "ComfyUI on Google Colab" guide (May 2026), which also says to expect 12–25 minutes per 4-second clip; up to 40 to 50 min at full step counts | Best open i2v | **Hero shots only (2 to 3 per episode)** |
| Wan 2.2 TI2V 5B | Apache 2.0 ✅ | Yes (reported to fit 8 GB) | Faster than 14B; several minutes at 480p (estimate) | Good | **Main i2v option**\[43\] |
| LTX-2.3 / LTX-2.5 (GGUF) | LTX-2.x Community License, free under $10M revenue | Q3/Q4 GGUF reported around 12 GB with offload | Fastest family on modern GPUs; T4 untested by sources | Very good, has audio | Optional; check the gated license\[16\]\[43\] |
| LTX-Video 0.9.x | LTX license (older) | Yes (~12 GB) | Fast | Fair | Fallback\[43\] |
| CogVideoX, SVD, AnimateDiff | Mixed licenses (SVD under Stability's community license; verify) | Yes | Slow to moderate | Dated in 2026 | Not recommended |

* **Honest verdict:** a 90 second Short with 12 scenes would need 12 clips; at 5 to 18 minutes each on a T4, that is 1 to 4 hours of GPU per episode, which burns Kaggle's 30 h/week in a few days. So use **real i2v for the hook shot, the cliffhanger shot and one action beat**, and 2.5D motion for everything else.
* Online i2v "free tiers" in 2026 are almost all credit trials, so they break your rule. There is no reliable forever-free online i2v backup; the backup is the motion engine below.

### 6. Motion effects engine (the workhorse)

* **2.5D parallax:** Depth Anything V2 Small (Apache 2.0, 24.8M parameters, ~95 MB) builds a depth map in under a second on GPU.\[44\] Split the image into 3 to 4 depth layers, inpaint the background behind the foreground (OpenCV `inpaint` or a quick klein edit), then move layers at different speeds with a virtual dolly or orbit.
* **Ken Burns:** upscale the image 1.3× first, then crop with smooth float positions (avoid FFmpeg `zoompan` jitter by rendering frames in Python or using high internal resolution).
* **Overlays:** particles (dust, rain, snow, embers), light leaks, god rays, vignette, film grain, subtle camera shake timed to SFX hits. Generate them procedurally in NumPy so there are no license questions.
* **Variety rule:** the LLM assigns a different camera move per scene (push in, pull out, pan, orbit, tilt, shake), and the renderer never repeats the same move twice in a row. This directly helps against "templated" detection.

### 7. Voices

| Voice | License / terms | English | Farsi | Word timestamps | Runs where | Verdict |
|---|---|---|---|---|---|---|
| **Kokoro (82M)** | Apache 2.0 ✅ | Excellent, 50+ voices | ❌ none | Yes for English via its pipeline, or align | CPU or GPU | **English main**\[21\]\[45\] |
| **Edge TTS (fa-IR Dilara / Farid)** | edge-tts is LGPL-3.0; Microsoft publishes no commercial grant for Read Aloud voices ⚠️ | Excellent | Excellent | Yes, with `boundary="WordBoundary"` | Online, free, no key | **Farsi main (accepting risk) / English backup**\[25\]\[46\] |
| **Your own recorded voice** | You own it ✅ | ✅ | ✅ | Forced alignment | Phone mic | **Best for Farsi and for monetization** |
| Piper (fa_IR voices) | Per-voice licenses, check each model card | OK | OK, robotic | Via alignment | CPU, offline | Offline Farsi fallback |
| ParsVoice XTTS-v2 fine-tune | Built on Coqui XTTS-v2, whose model license is non-commercial ⚠️ | n/a | Good (MOS 3.6/5) | Via alignment | GPU | Personal testing only\[47\] |

* On 29 September 2026 a volunteer MVP moderator on Microsoft Q&A wrote that "Microsoft does not currently publish documentation that explicitly grants commercial redistribution rights for audio generated through Edge Read Aloud or edge-tts". He named Azure AI Speech as "the appropriate Microsoft service for a commercial application". The edge-tts maintainer also says the library "is meant for personal use". It is an unofficial endpoint that can break (versions below 7.0 are already rejected with HTTP 403). **Recommendation:** use Kokoro for English, record your Farsi narration yourself (or at least the hook), and keep Edge TTS as a convenience option with a clear warning in the notebook.

### 8. Word by word captions (including Farsi)

* **Timing method (best to worst):**
  1. Your script is already known, so **forced alignment** of known text to audio is more accurate than transcription. Use WhisperX alignment (Persian model `jonatasgrosman/wav2vec2-large-xlsr-53-persian`, self-reported CV WER 30.1%, CER 7.4%)\[32\]\[48\] or `ctc-forced-aligner` with a permissively licensed wav2vec2 model.
  2. Edge TTS WordBoundary events (offsets in 100 ns ticks) when you use Edge.\[49\]
  3. Kokoro's own English token timestamps.
  4. faster-whisper or Groq Whisper (2,000 requests/day) word timestamps,\[50\] English only in practice.
* **Do not use** `MahmoudAshraf/mms-300m-1130-forced-aligner` (the ctc-forced-aligner default) for monetized videos: it is CC-BY-NC-4.0.\[51\]\[52\]
* **Whisper on Persian is weak out of the box.** The givia/whisper-large-v3-turbo-persian model card reports stock large-v3 at 17.3 to 37.3% WER across Persian test sets. The MohammadGholizadeh/whisper-large-v3-turbo-persian card measured stock large-v3-turbo at 50.2% WER on the Common Voice 17 fa test set (10,558 clips), against 19.4% after fine-tuning. Only use Whisper for Farsi if you have no script.
* **Rendering (TikTok style):** generate an `.ass` file. Use either one event per line with `\kf` karaoke fills, or one event per word with the active word recolored and scaled to ~112% (the "highlight" style, which is more robust for RTL).\[53\]
* **Farsi rendering checklist:**
  * Burn with `-vf "ass=captions.ass:shaping=complex:fontsdir=fonts"` (the `subtitles` filter's simple shaper breaks letters such as لا into boxes).\[33\]\[34\]
  * Use logical-order Unicode and let libass (HarfBuzz + FriBidi) shape it. **Do not** pre-process with arabic-reshaper/python-bidi for libass output.\[54\]
  * Wrap each RTL line in U+202B … U+202C so punctuation and numbers stay on the correct side.\[55\]
  * Keep `Spacing: 0` in the style; non-zero letter spacing reverses Persian glyph order in libass.\[56\]
  * Bundle Vazirmatn (OFL) for Farsi and a bold display font (e.g. Anton or Montserrat, OFL) for English.
  * Test RTL karaoke early: per-word events are the safe fallback if `\k` sweeps look wrong on RTL lines.\[57\]

### 9. Music and sound effects (monetization safe)

| Source | License | YouTube monetization | TikTok / IG / Snap | Notes |
|---|---|---|---|---|
| **YouTube Audio Library** | YouTube's terms | ✅ "won't be claimed" via Content ID | ⚠️ Not covered; treat as YouTube only unless the track is Creative Commons | Credit CC tracks in the description\[58\]\[59\] |
| **Freesound (filter CC0 only)** | CC0 | ✅ | ✅ | Avoid CC BY-NC (ad revenue counts as commercial)\[60\] |
| **Incompetech / Kevin MacLeod** | CC BY 4.0 | ✅ with credit | ✅ with credit | Tracks are in Content ID; claims are released within 72 hours if the credit is in the description\[61\]\[62\] |
| Pixabay Music / SFX | Pixabay license | ⚠️ Some tracks get Content ID claims from contributors | ⚠️ same | Save the license certificate per track\[63\]\[64\] |
| Procedural SFX (generated in code) | Yours | ✅ | ✅ | Whooshes, hits, risers, ambience |

* Build a **local, tagged library on Drive** (`music/tense/…`, `sfx/whoosh/…`) with a `licenses.csv` that records source, URL, license and credit text. The app auto-writes the required credits into the description.
* Duck music under the voice (FFmpeg `sidechaincompress`) and normalize loudness to about −14 LUFS.

### 10. Beginner-friendly notebook design

* **One form cell** (Colab `#@param` / Kaggle top-of-notebook config): story idea, series name, episode number, language (English / Farsi / both), formats (9:16, 16:9), quality (Fast = parallax only, Best = parallax + 3 i2v hero shots), voice choice.
* **Two buttons, not one:** "1. Write script" stops and shows the script as an editable text block (or `script.json` on Drive you can edit on your phone); "2. Make video" runs the rest. This pause is your legal "human authorship" step, so keep it.
* **Progress messages** with emoji and step numbers ("🖼️ Scene 4/12 image ✅ 14 s"), and one friendly error message per failure with what to do next.
* **Projects on Drive:** `MyDrive/StoryForge/series/<series>/ep<NN>/` with `state.json` recording each finished step. Re-running skips done steps, so a disconnect only loses the current scene.
* **GPU check at start:** if `torch.cuda.is_available()` is false, switch automatically to: Pollinations keyless images (45 s spacing), CPU Kokoro, CPU parallax with smaller resolution, and skip i2v, while telling you clearly that this is a slower fallback.

### 11. Speed and limit management

* **Model caching:** free Google Drive has only 15 GB shared, so do **not** cache 10 GB+ models there. Cache small things on Drive (Kokoro ~330 MB, Depth Anything Small ~95 MB, fonts, LoRAs, character refs). On Kaggle, store big weights as a private Kaggle Dataset or attach Kaggle Models so they mount instantly; on Colab, download from Hugging Face each session (usually a few minutes) into `/content`.
* **Pipeline order to minimize VRAM swaps:** load klein → all images → unload; load depth → all depth maps → unload; load Wan → hero clips → unload; then CPU work (TTS, alignment, render) while nothing else is on the GPU.
* **Parallel steps:** run TTS and caption alignment on CPU threads while the GPU renders images; on Kaggle use GPU 0 for images and GPU 1 for depth or i2v.
* **Retries and rotation:** every external call goes through one `call_with_fallback()` helper with exponential backoff on HTTP 429/402/5xx, then moves to the next provider in the list (Gemini Flash-Lite → Groq → Gemma → OpenRouter → Pollinations → local). Log quota use per day to `usage.json`.
* **Stay inside the rules:** rotate between different services, never between multiple accounts of the same service (Colab's terms forbid account switching; Gemini and Groq limits are per project/organization anyway).\[4\]\[65\]\[66\]

### 12. Platform rules in 2026 and what the app must do

| Platform | 2026 rule | Impact for you |
|---|---|---|
| **YouTube** | Policy update on July 16, 2026 split "inauthentic content" into three non-monetizable types: generic/repetitive/template-based, off-putting or distressing, and AI personas on sensitive topics. Using AI alone is not disqualifying.\[67\]\[68\] | Fine for a real serialized story with your own voice and writing; fatal for templated mass uploads |
| **TikTok** | Must label realistic AI content; unoriginal content is ineligible for Creator Rewards (originality page refreshed Sep 26, 2026). Creator Rewards pays only for videos over 1 minute and runs in only 8 countries.\[69\]\[70\]\[71\] | Turn on the AI label; a UAE creator likely cannot join Creator Rewards (check in app) |
| **Meta (Instagram / Facebook)** | March 12, 2026 originality guidelines; unoriginal accounts become non-recommendable and lose monetization; AI info labels for photorealistic AI. Instagram enforcement extended to all formats on April 30, 2026.\[72\]\[73\] | Facebook content monetization is available in the UAE; Instagram ad revenue is not\[74\] |
| **Snapchat** | Snap's Newsroom post "Rewarding Authentic Creativity on Spotlight" (July 31, 2026): "As of this month and going forward, wholly AI-generated videos will no longer be eligible for recommendation on Spotlight"; content "enhanced or edited using Snapchat's AI creative tools will continue to be eligible". AI use must be disclosed. Monetization is invite-only, available in the UAE.\[75\]\[76\] | Pure AI episodes will not be pushed on Spotlight; add real camera footage or a filmed host intro, or treat Snap as promo only |

**App features that protect monetization:**

* Mandatory script review/edit step and a "creator note" field (your commentary, recap, or question to viewers) included in each video.
* Your own voice option (record on phone, drop into the episode folder) and a short filmed intro/outro clip for Snapchat and Meta.
* Variation checker: compares new episode metadata, camera moves, music and thumbnail layout to the last 10 episodes and warns if too similar.
* AI disclosure reminders per platform at export time, plus C2PA-friendly metadata left intact.
* Hard cap of 1 to 2 uploads per day per platform by default.

### 13. Existing open source projects to learn from

| Project | What it does | Pros | Cons |
|---|---|---|---|
| MoneyPrinterTurbo (MIT) | Topic → LLM script → stock footage → Edge TTS → subtitles | Mature pipeline, multi-LLM | Stock footage, not consistent AI characters; "faceless slop" format at risk under 2026 rules |
| ShortGPT | Automated short video editing framework | Good editing engine ideas | Less active; not story focused |
| ffmpeg-word-captions | Whisper JSON → karaoke/highlight/reveal/pop ASS captions burned with FFmpeg\[53\] | Exactly the caption styles you want | Node.js; port the logic to Python |
| rtl-burn | Burns Persian/Arabic subtitles with FFmpeg using RTL embedding marks\[55\] | Solves Farsi punctuation/bidi | SRT focused, not karaoke |
| Atlansub | Offline Persian subtitles (faster-whisper + libass, Vazirmatn)\[56\] | Real Farsi lessons (Spacing 0 bug) | Desktop tool, not a pipeline |
| NarratoFlow | Narration video pipeline with ASS RTL caption work\[54\]\[57\] | Documents RTL karaoke tests | Early stage |
| BFL `flux2` repo, Wan 2.2 repo, Depth-Anything-V2 repo | Official inference code | Correct, licensed | Need T4 adaptation |

* Do not fork a giant project. Have Claude Code build a small, clean pipeline and borrow ideas (caption styles, RTL fixes, provider fallbacks) from these.

### 14. License check summary

| Component | License | Monetized videos OK? |
|---|---|---|
| FLUX.2 [klein] 4B / 4B Base | Apache 2.0 | ✅\[12\]\[15\]\[21\]\[77\]\[78\]\[79\] |
| FLUX.2 [klein] 9B, FLUX.2 [dev], FLUX.1 [dev] | FLUX Non-Commercial | ❌ avoid\[13\]\[15\] |
| FLUX.1 [schnell] | Apache 2.0 | ✅ |
| SDXL base | CreativeML Open RAIL++-M | ✅ (use restrictions apply) |
| Wan 2.2 | Apache 2.0 | ✅ |
| LTX-2.x | Community License, free under $10M revenue | ✅ for you, read the gated terms\[80\] |
| Depth Anything V2 Small | Apache 2.0 | ✅ |
| Depth Anything V2 Base/Large/Giant | CC-BY-NC-4.0 | ❌\[81\] |
| Kokoro | Apache 2.0 | ✅\[23\] |
| Edge TTS voices | No published grant; tool is LGPL-3.0 | ⚠️ risk\[24\]\[82\] |
| Coqui XTTS-v2 fine-tunes | Non-commercial model license | ❌ |
| Whisper / faster-whisper | MIT | ✅ |
| MMS forced aligner default | CC-BY-NC-4.0 | ❌\[51\]\[52\] |
| Vazirmatn, Noto, Anton, Montserrat fonts | SIL OFL | ✅ |
| FFmpeg / libass | LGPL/GPL tools (outputs unaffected) | ✅ |

## Recommendations

### Recommended final free architecture

| Step | Main (free forever) | Backup 1 | Backup 2 |
|---|---|---|---|
| Compute | Kaggle T4 x2 | Colab free T4 | CPU-only mode |
| Storage | Google Drive project folders (+ Kaggle Dataset for weights) | Kaggle /kaggle/working (20 GB) | Local download |
| Script + Farsi translation | Gemini Flash-Lite (500/day) | Groq gpt-oss-120b / Qwen3.8 27B (1,000/day) | Gemma 4 API → OpenRouter :free → local 4-bit LLM |
| Images | FLUX.2 [klein] 4B + multi-reference on GPU | FLUX.1 schnell or SDXL + IP-Adapter on GPU | Pollinations keyless (1 per 45 s) |
| Consistency | Character bible + reference sheets + seeds + similarity check | Klein 4B Base LoRA (later) | Manual regenerate |
| Real motion | Wan 2.2 TI2V 5B for 2–3 hero shots | Wan 2.2 14B GGUF on Kaggle (best quality) | LTX-2.x GGUF |
| Other motion | Depth Anything V2 Small parallax + Ken Burns + particles/light/shake | Ken Burns only | Static with zoom |
| English voice | Kokoro | Edge TTS (en voices) | Piper |
| Farsi voice | Your own recording | Edge TTS Dilara/Farid (accepting risk) | Piper fa_IR |
| Word timing | Forced alignment of known script (WhisperX / wav2vec2 Persian) | Edge WordBoundary / Kokoro timestamps | Groq Whisper / faster-whisper |
| Captions | ASS + libass `shaping=complex`, Vazirmatn | Per-word ASS events | Plain SRT |
| Music / SFX | YouTube Audio Library (YouTube), Freesound CC0, Incompetech CC BY | Procedural SFX | No music |
| Render | FFmpeg (NVENC on GPU if available, else libx264) | MoviePy for compositing only | n/a |
| Thumbnail + metadata | Klein 4B thumbnail with your character + Pillow text; LLM titles/hashtags | Best scene frame + text | n/a |

### How many videos at zero cost

| Mode | GPU time per episode (both 9:16 and 16:9 cuts, estimates) | Per week on Kaggle (~30 h) | Per day realistic |
|---|---|---|---|
| Fast (parallax only, 12 scenes) | ~20–30 min | ~60 episodes | GPU is not the limit; your editing is |
| Best (parallax + 3 Wan 2.2 5B hero shots) | ~45–75 min | ~25–35 episodes | **1 to 2 episodes** |
| Max (Wan 2.2 14B GGUF hero shots) | ~1.5–2 h | ~15 episodes | 1 episode |

* Colab free adds unpredictable extra hours on top.
* The LLM limits (500 to 1,000 requests/day) support far more than you will ever use.
* The practical and safest target given platform rules is **1 episode per day, posted as one vertical cut (to Shorts, TikTok, Reels, Spotlight) and one 16:9 cut (YouTube)**.

### Expected quality

* Images: near-commercial quality stills with stable characters if you curate reference sheets well. Expect occasional hand and text errors; the notebook should let you regenerate one scene with one click.
* Motion: parallax scenes look like premium "motion comic" style; Wan 2.2 hero shots give real character movement. It will not match paid Kling/Veo-level video, and you should not promise viewers that.
* Voice: Kokoro English is close to paid TTS. Edge Farsi is natural; your own voice beats both for engagement and policy safety.

### Step by step build plan for Claude Code

**Repo structure**

```
storyforge/
  README.md                  # beginner instructions with screenshots
  notebooks/
    StoryForge_Kaggle.ipynb  # main: config cell + 2 run cells
    StoryForge_Colab.ipynb   # same, with Drive mount + forms
  storyforge/
    config.py                # dataclass of all settings + paths
    state.py                 # state.json load/save, step skipping
    providers/
      llm.py                 # Gemini, Groq, Gemma, OpenRouter, Pollinations, local
      fallback.py            # call_with_fallback, backoff, usage.json
    script/
      prompts.py             # hook + cliffhanger templates, JSON schema
      writer.py              # outline -> script -> scenes JSON
      translate.py           # English -> Farsi
    characters/
      bible.py               # character bible + reference sheet builder
      consistency.py         # similarity check + retry
    images/
      klein.py               # FLUX.2 klein 4B fp16 / quantized loader
      fallback_online.py     # Pollinations keyless with 45 s spacing
    motion/
      depth.py               # Depth Anything V2 Small
      parallax.py            # layered 2.5D renderer
      kenburns.py, overlays.py, shake.py
      i2v_wan.py             # Wan 2.2 TI2V 5B / 14B GGUF hero shots
    audio/
      tts_kokoro.py, tts_edge.py, tts_piper.py, own_voice.py
      align.py               # WhisperX / wav2vec2 forced alignment
      music.py               # library picker, ducking, loudness
    captions/
      ass_builder.py         # karaoke + highlight styles, RTL rules
    render/
      compose.py             # FFmpeg graph, 9:16 and 16:9
      thumbnail.py
    publish/
      metadata.py            # titles, descriptions, hashtags, credits
      policy_check.py        # variation checker + disclosure reminders
  assets/fonts/ (Vazirmatn, Anton, Montserrat)  assets/sfx/  assets/music/licenses.csv
  tests/ (tiny smoke tests for each module)
```

**Prompts to give Claude Code, in order** (one per session, test each before moving on):

1. "Create the repo structure above. Write `config.py` and `state.py`: a project folder per episode on Google Drive (or /kaggle/working), `state.json` tracking finished steps, and a `run_step(name, fn)` helper that skips completed steps. Write a beginner README."
2. "Write `providers/fallback.py` and `providers/llm.py`: one `generate_json(prompt, schema)` function that tries Gemini Flash-Lite, then Groq, then Gemma, then OpenRouter `:free`, then Pollinations, with exponential backoff on 429/402/5xx, JSON validation and repair, and daily usage logging. API keys come from Colab Secrets / Kaggle Secrets, never hard coded."
3. "Write `script/writer.py`: from a story idea, series bible and previous episode summary, produce an episode JSON with a 3 second hook, 10 to 14 scenes (narration, visual prompt, characters, location, camera move, SFX tags, mood), and a cliffhanger. Save `script.md` that I can edit; when I re-run, parse my edits back into JSON. Add Farsi translation that keeps names consistent."
4. "Write `characters/bible.py` and `images/klein.py`: load FLUX.2 [klein] 4B in fp16 (T4 has no bf16), generate a 4-view reference sheet per new character, and generate each scene with multi-reference conditioning, fixed seeds, 9:16 (1080×1920 via 768×1344 + upscale) and 16:9 versions. Add `consistency.py` that scores similarity to the refs and retries twice."
5. "Write `motion/`: Depth Anything V2 Small depth maps, a 3-layer parallax renderer with inpainted background, Ken Burns with smooth float cropping, procedural particles, light leaks, grain and SFX-synced shake. Each scene gets its camera move from the JSON; never repeat the same move twice in a row."
6. "Write `motion/i2v_wan.py`: Wan 2.2 TI2V 5B image to video for scenes flagged `hero: true` (max 3), with a time budget; if out of time or VRAM, fall back to parallax automatically. Add an optional Wan 2.2 14B GGUF path for Kaggle only."
7. "Write `audio/`: Kokoro for English, Edge TTS for Farsi using `boundary='WordBoundary'` and streaming, Piper fallback, and an own-voice option that picks up `voice_fa.wav` from the episode folder. Then `align.py` that force-aligns the known script to the audio (WhisperX Persian/English align models) and outputs word timings JSON."
8. "Write `captions/ass_builder.py`: TikTok style captions, 2 to 4 words per line, active word highlighted and scaled 112%, safe zones for 9:16 and 16:9. For Farsi: logical Unicode, U+202B/U+202C wrapping, Vazirmatn, Spacing 0, burned with the `ass` filter and `shaping=complex`. Create a test video with Farsi containing لا, numbers and punctuation."
9. "Write `audio/music.py` and `render/compose.py`: pick music by mood from my local library, duck under voice, add SFX, normalize to −14 LUFS, and render both formats with FFmpeg (h264_nvenc if available, else libx264), 30 fps, YouTube/TikTok compatible settings."
10. "Write `render/thumbnail.py` and `publish/metadata.py`: thumbnail with the main character, bold title text (English and Farsi), titles, descriptions with automatic music credits and AI disclosure line, and hashtags per platform."
11. "Write `publish/policy_check.py`: compare the new episode to the last 10 (camera moves, music, thumbnail layout, title pattern) and warn if too similar; print a per-platform checklist (TikTok AI label, Meta AI info, YouTube altered content disclosure, Snapchat disclosure)."
12. "Build the two notebooks: a form/config cell, a 'Write script' cell that stops for editing, and a 'Make video' cell with clear emoji progress messages, GPU detection with CPU/online fallback, resume from `state.json`, and auto-save to Drive. Test end to end on Kaggle, then on Colab."

## Caveats

* **Free limits change constantly.** The Gemini figures above come from third-party AI Studio readings (Google publishes no fixed free numbers), and sources disagree sharply (some still quote 1,500 requests/day).\[83\]\[84\] Always check your own AI Studio and Groq console limits pages.
* **Timing figures for T4 are partly estimates.** The Wan 2.2 14B figure of 18 min per clip (GGUF Q4, free T4) comes from the Agathas Web UK "ComfyUI on Google Colab" guide (May 2026), which also says to expect 12–25 minutes per 4-second clip. Other sources report 40 to 50 minutes at full step counts. Klein 4B timing on T4 is my extrapolation. Benchmark on your own first run and let the notebook auto-adjust the number of hero shots.
* **Hugging Face free credits are in conflict:** official docs say $0.10/month "subject to change", while one source says they were removed in October 2026.\[10\]\[11\]
* **Edge TTS is the main legal grey area.** It is widely used, but Microsoft has not granted commercial rights and could block the endpoint.\[24\]\[85\] Your own Farsi voice is the safest path.
* **Monetization depends on country and policy interpretation.** Snapchat has not defined "wholly AI-generated",\[71\]\[86\] TikTok Creator Rewards likely is not available in the UAE, and UAE law requires an advertiser permit if you publish paid promotions.\[75\] None of the platforms guarantees monetization for AI story channels.
* The GitHub projects listed were not all re-verified for late 2026 activity; check commit dates before borrowing code.

## Sources

1. [Top Google Colab Alternatives (November 2026): Pricing, Limits, and Availability](https://www.thundercompute.com/blog/colab-alternatives-for-cheap-deep-learning-in-2025)
2. [Google Colab](https://research.google.com/colaboratory/faq.html)
3. [Kaggle vs Colab in 2026: Free GPUs, Session Limits and Which to Use](https://fastero.com/blog/kaggle-vs-colab)
4. [Gemini API Free Tier Limits: 20 Requests a Day on Gemini 3.8 Flash](https://imisofts.com/blog/gemini-api-free-tier-limits/)
5. [Gemini API Free Tier in 2026: What Is Free and What to Check - Free models, rate limits by model, and daily quota](https://www.aifreeapi.com/en/posts/google-gemini-api-free-tier)
6. [OpenRouter free models: limits, expiry and fallbacks](https://www.requesty.ai/blog/openrouter-free-models)
7. [OpenRouter Free Models: Full List and Limits (Oct 2026)](https://danishsofi.in/blog/openrouter-free-models)
8. [Pollinations.AI Free Tier 2026: Limits, Pricing & What Changed](https://agentdeals.dev/vendor/pollinations-ai)
9. [Pollinations Classic API](https://raw.githubusercontent.com/pollinations/pollinations/master/APIDOCS.md)
10. [Pricing and Billing](https://huggingface.co/buckets/hf-doc-build/doc-dev/resolve/inference-providers/pr_1805/en/pricing.html?download=true)
11. [Hugging Face API Tutorial 2026: Free Tier & Python Code](https://freeapihub.com/blog/hugging-face-api-tutorial-free-ai-models)
12. [FLUX.2 \[klein\]: Towards Interactive Visual Intelligence](https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence)
13. [How does FLUX licensing work?](https://help.bfl.ai/articles/9272590838-self-serve-dev-license-overview-pricing)
14. [FLUX open weights and commercial licences](https://wiki.licenseware.io/wiki/black-forest-labs-flux-open-weights-and-commercial-licenses/)
15. [GitHub - black-forest-labs/flux2: Official inference repo for FLUX.2 models · GitHub](https://github.com/black-forest-labs/flux2)
16. [Best Local AI Video Model 2026: LTX vs WAN vs Hunyuan](https://www.earngenix.com/workflows/best-local-ai-video-model-2026)
17. [LTX-2 Review: LTX-2.5, API Pricing & License](https://www.therundown.ai/tools/ltx-2)
18. [LTX-2.5 can generate a 10-second AI video from an image in just 6.8 seconds on Nvidia superchips — and it's open weights](https://venturebeat.com/technology/ltx-2-5-can-generate-a-10-second-ai-video-from-an-image-in-just-6-8-seconds-on-nvidia-superchips-and-its-open-weights)
19. [GitHub - rafaelperez/Depth-Anything-for-Nuke: \[CVPR 2024\] Depth Anything: Unleashing the Power of Large-Scale Unlabeled Data. Foundation Model for Monocular Depth Estimation · GitHub](https://github.com/rafaelperez/Depth-Anything-for-Nuke)
20. [Depth-Anything-V1 / README\_Github.md](https://huggingface.co/spaces/zino36/Depth-Anything-V1/blob/6ceac94614402ad16e7f12aa2044c61162611fd3/README_Github.md)
21. [Kokoro TTS: Advanced AI Text-to-Speech Model with 82M parameters](https://kokorottsai.com/)
22. [Kokoro-82M TTS on Android — ONNX Runtime + APK](https://soniqo.audio/guides/kokoro/android)
23. [Full List of 54 Voices (Free, In-Browser) - Kokoro TTS](https://kokoroweb.app/voices)
24. [Commercial use of Microsoft Edge Text-to-Speech via edge-tts - Microsoft Q&A](https://learn.microsoft.com/en-us/answers/questions/6007729/commercial-use-of-microsoft-edge-text-to-speech-vi?page=1#answer-12979213)
25. [Edge TTS Voice Samples - 322 Neural Voices Preview](https://www.oceanz.site/en/explore/edge-tts)
26. [Edge‐TTS‐Voices · FoloToy/folotoy-server-self-hosting Wiki · GitHub](https://github.com/FoloToy/folotoy-server-self-hosting/wiki/Edge%E2%80%90TTS%E2%80%90Voices)
27. [Available Voices - COVAS:NEXT](https://ratherrude.github.io/Elite-Dangerous-AI-Integration/40_edgeTTSVoices/)
28. [Restore word-boundary timing in the narration pipeline · Issue #35 · youirepo/visentia · GitHub](https://github.com/youirepo/visentia/issues/35)
29. [fix(tts): 显式请求词边界（edge-tts 7.2.0+ 默认不给）；空音频自动重试 by Vincentwei1021 · Pull Request #3 · Vincentwei1021/anything2explainer · GitHub](https://github.com/Vincentwei1021/anything2explainer/pull/3)
30. [MohammadGholizadeh/whisper-large-v3-turbo-persian · Hugging Face](https://huggingface.co/MohammadGholizadeh/whisper-large-v3-turbo-persian)
31. [givia/whisper-large-v3-turbo-persian · Hugging Face](https://huggingface.co/givia/whisper-large-v3-turbo-persian)
32. [whisperX/whisperx/alignment.py at main · m-bain/whisperX · GitHub](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py)
33. [Fix Arabic text rendering by using complex shaping in libass by EngDawood · Pull Request #13 · EngDawood/video-caption · GitHub](https://github.com/EngDawood/video-caption/pull/13)
34. [Fix squares in Arabic subtitles and add subtitle styles by FAJU85 · Pull Request #19 · FAJU85/vid-translate- · GitHub](https://github.com/FAJU85/vid-translate-/pull/19)
35. [Arabic RTL Fix — Free Subtitle Fixer Guide (Hebrew & Persian Too)](https://videodubbing.com/blog/post/fix-arabic-hebrew-subtitles-rtl-fixer-guide-2026/)
36. [ComfyUI on Google Colab: Free AI Image & Video Generation Guide](https://uk.agathasweb.com/blog/comfyui-google-colab-gerar-imagens-videos-ia)
37. [Kaggle’s Free GPUs for AI Experiments: What You Actually Get](https://medium.com/@hari12.nhk/kaggles-free-gpus-for-ai-experiments-what-you-actually-get-abff5684a53c)
38. [Gemini API Pricing 2026: Free Tier & Per-Model Rates](https://creditforstartups.com/pricing/gemini-api-pricing)
39. [FLUX by Black Forest Labs: Versions & EU Availability](https://innfactory.ai/en/ai-models/flux/)
40. [Open Source Image Models: The License Matrix Everyone Gets Wrong (August 2026)](https://invideo.io/blog/open-source-image-models-licenses/)
41. [Floyo](https://www.floyo.ai/models/flux-2-klein)
42. [FLUX.2 Klein: Fast Open-Weight 4B & 9B Models](https://www.flux3.org/models/flux-2-klein)
43. [Local AI Video Generation: Wan 2.2 vs LTX-2 vs HunyuanVideo](https://localaimaster.com/blog/local-ai-video-generation)
44. [Download depth\_anything\_v2\_vitl.pth, vitb and vits](https://www.rizwanai.com/model-weights/depth-anything-v2)
45. [Best Open-Source Text to Speech in 2026: 10 Free Models Ranked](https://texttolab.com/blog/open-source-text-to-speech)
46. [feat(tts): add Persian character detection and dynamic voice selection for Edge TTS by w0l4i · Pull Request #150669 · NousResearch/hermes-agent · GitHub](https://github.com/NousResearch/hermes-agent/pull/150669)
47. [MohammadJRanjbar/ParsVoice-XTTS · Hugging Face](https://huggingface.co/MohammadJRanjbar/ParsVoice-XTTS)
48. [jonatasgrosman/wav2vec2-large-xlsr-53-persian · Hugging Face](https://huggingface.co/jonatasgrosman/wav2vec2-large-xlsr-53-persian)
49. [GitHub - andresayac/edge-tts: Edge TTS is a Node or Bun package that allows access to the online text-to-speech service used by Microsoft Edge without the need for Microsoft Edge, Windows, or an API key. · GitHub](https://github.com/andresayac/edge-tts)
50. [Groq Free Caps 2026: Plan Around Per-Model Limits](https://ampm-aiops.com/en/guides/groq-special-2026/)
51. [README.md · MahmoudAshraf/mms-300m-1130-forced-aligner at main](https://huggingface.co/MahmoudAshraf/mms-300m-1130-forced-aligner/blob/main/README.md)
52. [deskpai/ctc\_forced\_aligner · Hugging Face](https://huggingface.co/deskpai/ctc_forced_aligner)
53. [GitHub - CosLynxAI/ffmpeg-word-captions: Word-by-word karaoke, highlight, reveal and pop captions from a Whisper transcript, burned in with ffmpeg. · GitHub](https://github.com/CosLynxAI/ffmpeg-word-captions)
54. [ASS captions in logical-order Unicode (Amiri / Montserrat) · Issue #19 · eaitbrahim/NarratoFlow · GitHub](https://github.com/eaitbrahim/NarratoFlow/issues/19)
55. [GitHub - mohammadhadijavidi/rtl-burn: Burn Persian, Arabic, Urdu & Hebrew subtitles into video with ffmpeg — no broken punctuation or reordered words. · GitHub](https://github.com/mohammadhadijavidi/rtl-burn)
56. [GitHub - alimc98/Atlansub: Offline Persian (Farsi) subtitle generator with a local web UI - Premiere-safe SRT and transparent ProRes 4444 overlay. · GitHub](https://github.com/alimc98/Atlansub)
57. [Spike: RTL karaoke highlighting in libass · Issue #26 · eaitbrahim/NarratoFlow · GitHub](https://github.com/eaitbrahim/NarratoFlow/issues/26)
58. [Copyright Free Music YouTube Audio Library: 2026 Guide - Foxi Blog](https://www.foximusic.com/blog/copyright-free-music-youtube-audio-library-guide/)
59. [Can you use YouTube Audio Library music outside YouTube? — Faceless Desk](https://facelessdesk.com/youtube-audio-library-outside-youtube/)
60. [Freesound - Forums - "Legal" help and Attribution questions - New to THIS...Could use some insight on usages.](https://freesound.org/forum/legal-help-and-attribution-questions/43120/)
61. [Free Music Download: What Each Licence Lets You Do](https://mubert.com/blog/free-music-download-licences-explained)
62. [YouTube Content ID](https://incompetech.com/music/royalty-free/youtube-contentid.html)
63. [Pixabay Music and Sound Effects Alternatives in 2026 (Licenses Compared)](https://sonilo.com/blog/comparisons/pixabay-music-sound-effects-alternatives-2026)
64. [Free Music for YouTube: How Monetization and Content ID Affect Your Licenses](https://www.archyde.com/free-music-for-youtube-how-monetization-and-content-id-affect-your-licenses/)
65. [Free Cloud GPUs in 2026: What Works and What Closed - Blog](https://gpuperhour.com/blog/free-cloud-gpus-and-credits)
66. [Groq pricing in 2026: every model, free tier, and hidden discounts explained](https://www.eesel.ai/blog/groq-pricing)
67. [YouTube clarifies policies around AI slop and upsetting videos](https://techcrunch.com/2026/07/20/youtube-clarifies-policies-around-ai-slop-and-upsetting-videos/)
68. [YouTube's 2026 inauthentic content policy — Deeporax AI](https://deeporax.com/blog/youtube-inauthentic-content-policy-2026)
69. [AI Video Monetization on TikTok: Eligibility and Originality](https://noobclaw.com/blog/monetize-ai-generated-videos-tiktok-2026/)
70. [How to Monetize AI Videos in 2026 Without Getting Demonetized](https://clippie.ai/blog/make-money-ai-generated-shorts-2026)
71. [Can AI Videos Make Money? Every Platform's 2026 Rules](https://www.clip-short.com/guides/make-money-with-ai-videos)
72. [Facebook Monetization for AI Videos: The 2026 Rules](https://falconvid.ai/blog/facebook-monetization-for-ai-videos)
73. [What Counts as Original Content in 2026 (Meta Finally Spelled](https://noobclaw.com/blog/what-counts-as-original-content-instagram-facebook-2026/)
74. [Creator Monetization 2026: Saudi Arabia, UAE, Kuwait, Qatar](https://www.clip-short.com/guides/creator-monetization-saudi-arabia-uae-kuwait-qatar)
75. [Snapchat creators in 2026: earnings, paid partnership rules and Gulf programmes](https://wiro.ae/articles/snapchat-creators-2026)
76. [How Snapchat Pays Creators in 2026: Requirements](https://www.clip-short.com/guides/snapchat-monetization)
77. [Flux (text-to-image model)](<https://en.wikipedia.org/wiki/Flux_(text-to-image_model)>)
78. [AI Video Generation PC 2026: GPU, VRAM, and Models (Wan, LTX, Hunyuan)](https://www.radiancesystems.eu/en/blogs/intelligence-artificielle-et-llm-local/pc-pour-generation-video-ia)
79. [Depth Anything V2: predict and validate monocular depth](https://www.libreyolo.com/docs/models/depth-anything-v2)
80. [LTX-2.5: 22B Open-Weights Video AI, Fast & Free 2026](https://hokai.io/hub/models/ltx-2.5)
81. [Depth-Anything-V2-Base license · Issue #162 · DepthAnything/Depth-Anything-V2 · GitHub](https://github.com/DepthAnything/Depth-Anything-V2/issues/162)
82. [Voxa/NOTICE.md at main · akshinmrv/Voxa · GitHub](https://github.com/akshinmrv/Voxa/blob/main/NOTICE.md)
83. [Gemini API free tier limits: Google docs, September 2026](https://www.memetik.ai/guides/gemini-api-free-tier-limits)
84. [Gemini API Free Tier 2026: 1,500 Req/Day, 1M TPM — No Card - TokenMix Blog](https://tokenmix.ai/blog/gemini-api-free-tier-limits)
85. [GitHub - ganapap1/TTS\_NO\_API: Free Text-to-Speech Application - Edge TTS + Piper TTS · GitHub](https://github.com/ganapap1/TTS_NO_API)
86. [Can You Monetize AI Content? Snapchat Just Made It Much Harder](https://www.dreampixelforge.com/blog/can-you-monetize-ai-content)
