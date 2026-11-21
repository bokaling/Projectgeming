"""Runs all the steps in order and skips work that is already finished.

Order (research.md section 11, one big model on the GPU at a time):
script → character pictures → scene pictures (klein) → hero clips (Wan) →
depth → voices → scene clips → music/SFX mix → captions → final videos →
thumbnail + title/description/hashtags.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from . import captions, characters, config, images, publish, render, script
from .audio import music, tts
from .messages import FriendlyError, Reporter, Timer
from .motion import clip as clip_mod
from .motion import depth as depth_mod
from .motion import i2v
from .project import (UPLOAD_VIDEO_EXT, Episode, EpisodeOptions, Series, dims, fingerprint, read_json,
                      write_json)

LEAD, TAIL, LAST_TAIL, MIN_SCENE = 0.15, 0.35, 1.4, 2.2
QUICK_IDEA = "A lighthouse keeper gets a radio message from her future self, warning her about tonight's storm."


def file_sig(path: Path | None) -> str:
    if not path or not Path(path).exists():
        return ""
    st = Path(path).stat()
    return f"{st.st_size}-{int(st.st_mtime)}"


class Pipeline:
    def __init__(self, series: Series, episode: Episode, rep: Reporter, opts: EpisodeOptions | None = None):
        self.series, self.ep, self.rep = series, episode, rep
        self.opts = opts or episode.load_options()

    # ------------------------------------------------------------------ basics
    @property
    def script(self) -> dict:
        sc = self.ep.load_script()
        if not sc or not sc.get("scenes"):
            raise FriendlyError("This episode has no script yet.", "Go to the Script step and press 'Write script'.")
        return sc

    def scene_seed(self, sc: dict) -> int:
        return characters.stable_seed(f"{self.series.slug}/{self.ep.number}/{sc['id']}") + 7919 * int(sc.get("regen", 0))

    def out_size(self, fmt: str) -> tuple[int, int]:
        return dims(fmt, self.opts.resolution)

    def image_formats(self) -> list[str]:
        fmts = [self.opts.primary_format]
        mode = self.opts.second_format_images
        if mode == "generate" or (mode == "auto" and images.KleinEngine.usable()):
            fmts += [f for f in self.opts.formats if f not in fmts]
        return fmts

    def voice_choice(self, lang: str) -> dict:
        return tts.parse_voice(self.series.data.get("voices", {}).get(lang), lang)

    def upload_video(self, sid: str) -> Path | None:
        up = self.ep.upload_path(sid)
        return up if up and up.suffix.lower() in UPLOAD_VIDEO_EXT else None

    def hero_scenes(self) -> list[dict]:
        if self.opts.hero_count <= 0:
            return []
        return [sc for sc in self.script["scenes"] if sc.get("hero") and not self.ep.upload_path(sc["id"])][: self.opts.hero_count]

    def hero_clip(self, sid: str, fmt: str) -> Path | None:
        if fmt != self.opts.primary_format:
            return None  # hero clips are made for the main format; the other format uses parallax
        info = self.ep.state.info(f"hero:{sid}:{fmt}")
        path = self.ep.hero_path(sid, fmt)
        return path if info.get("ok") and path.exists() else None

    # ------------------------------------------------------------------ steps
    def write_script(self) -> dict:
        return script.write_script(self.series, self.ep, self.opts, self.rep)

    def character_pictures(self, force=()) -> None:
        names = sorted({n for sc in self.script["scenes"] for n in sc.get("characters", [])})
        characters.ensure_references(self.series, names, self.rep, force=list(force))

    def scene_pictures(self, only: list[str] | None = None, force: bool = False, keep_loaded: bool = False) -> dict:
        sc_all = self.script["scenes"]
        jobs = []
        use_refs = images.KleinEngine.usable()
        for i, sc in enumerate(sc_all, 1):
            if only and sc["id"] not in only:
                continue
            if self.ep.upload_path(sc["id"]) and not force:
                continue
            prompt, refs = characters.scene_prompt(self.series, sc, with_refs=use_refs)
            seed = self.scene_seed(sc)
            for fmt in self.image_formats():
                out = self.ep.image_path(sc["id"], fmt)
                fp = fingerprint(prompt, seed, fmt, [file_sig(r) for r in refs])
                key = f"image:{sc['id']}:{fmt}"
                if not force and self.ep.state.fresh(key, fp, [out]):
                    continue
                jobs.append(images.ImageJob(prompt, out, dims(fmt, "1080p"), seed, refs, key, fp,
                                            label=f"Scene {i} ({fmt.replace('x', ':')})"))
        if not jobs:
            self.rep.ok("All scene pictures are already done")
            return {}
        self.rep.step(f"🖼️ Scene pictures ({len(jobs)})")

        def saved(job, provider):
            self.ep.state.done(job.key, job.fp, provider=provider)
            sid = job.key.split(":")[1]
            self.ep.state.forget(f"hero:{sid}")
            self.ep.state.forget(f"clip:{sid}")

        with Timer() as t:
            counts = images.generate_batch(jobs, self.rep, on_done=saved, span=(0.08, 0.35))
        if not keep_loaded:
            images.unload()
        summary = ", ".join(f"{n} × {k}" for k, n in counts.items())
        status = "warn" if "Placeholder" in counts else "ok"
        self.rep.record(status, "Pictures", summary)
        if "Placeholder" in counts:
            self.rep.warn("Some pictures are placeholders (no picture service worked). Regenerate or replace them on the Scenes step.")
        self.rep.ok(f"Pictures done in {t.label}: {summary}")
        return counts

    def regenerate(self, sid: str, keep_loaded: bool = True) -> None:
        sc = self.script
        for s in sc["scenes"]:
            if s["id"] == sid:
                s["regen"] = int(s.get("regen", 0)) + 1
        script.save_script(self.ep, sc)
        self.ep.clear_upload(sid)
        self.scene_pictures(only=[sid], force=True, keep_loaded=keep_loaded)

    def hero_clips(self) -> None:
        heroes = self.hero_scenes()
        if not heroes:
            return
        fmt = self.opts.primary_format
        if not i2v.WanEngine.usable():
            why = i2v.WanEngine.failed_reason or "they need a free GPU with 15 GB"
            self.rep.info(f"🎬 Real-motion hero clips skipped ({why}). Those scenes get 2.5D motion instead.")
            self.rep.record("warn" if config.get().gpu.available else "ok", "Hero clips", "motion effects instead")
            return
        self.rep.step(f"🎬 Real-motion hero clips with Wan 2.2 ({len(heroes)}, up to {self.opts.hero_minutes:.0f} min each)")
        made = 0
        for k, sc in enumerate(heroes, 1):
            self.rep.check_stop()
            src = self.ep.scene_source_image(sc["id"], fmt, self.opts.formats)
            if src is None:
                continue
            key = f"hero:{sc['id']}:{fmt}"
            fp = fingerprint(file_sig(src), i2v.hero_prompt(sc), self.opts.hero_minutes, self.scene_seed(sc))
            if self.ep.state.fresh(key, fp):
                made += int(bool(self.ep.state.info(key).get("ok")))
                continue
            with Timer() as t:
                ok, msg = i2v.make_hero_clip(src, sc, self.ep.hero_path(sc["id"], fmt), fmt, self.opts.hero_minutes,
                                             self.scene_seed(sc), self.rep)
            self.ep.state.done(key, fp, ok=ok, msg=msg)
            self.ep.state.forget(f"clip:{sc['id']}")
            if ok:
                made += 1
                self.rep.ok(f"Hero clip {k}/{len(heroes)} ({t.label})")
            else:
                self.rep.warn(f"Hero clip {k}/{len(heroes)} skipped: {msg}. Using 2.5D motion instead.")
        i2v.unload()
        self.rep.record("ok" if made == len(heroes) else "warn", "Hero clips", f"{made}/{len(heroes)} made")

    def depth_maps(self) -> None:
        todo = []
        for sc in self.script["scenes"]:
            if self.upload_video(sc["id"]):
                continue
            for fmt in self.opts.formats:
                if self.hero_clip(sc["id"], fmt):
                    continue
                src = self.ep.scene_source_image(sc["id"], fmt, self.opts.formats)
                if src is None:
                    continue
                out = self.depth_for(src)
                if not self.ep.state.fresh(f"depth:{sc['id']}:{src.stem}", file_sig(src), [out]):
                    todo.append((sc["id"], src, out))
        todo = list({str(s): (sid, s, o) for sid, s, o in todo}.values())
        if not todo:
            return
        self.rep.step(f"🌄 Depth maps for 2.5D motion ({len(todo)})")
        method = ""
        for sid, src, out in todo:
            self.rep.check_stop()
            method = depth_mod.make_depth(src, out)
            self.ep.state.done(f"depth:{sid}:{src.stem}", file_sig(src), method=method)
        depth_mod.unload()
        self.rep.ok(f"Depth maps ready ({method})")
        self.rep.record("ok" if "Anything" in method else "warn", "Depth (2.5D)", method)

    def depth_for(self, src: Path) -> Path:
        return src.with_name(f"depth_{src.stem}.png")

    def voices(self, lang: str) -> None:
        sc_all = self.script["scenes"]
        choice = self.voice_choice(lang)
        texts = []
        for i, sc in enumerate(sc_all, 1):
            text = sc["narration"] if lang == "en" else sc.get("narration_fa", "")
            if not text.strip():
                raise FriendlyError(f"Scene {i} has no {'Farsi ' if lang == 'fa' else ''}narration.",
                                    "Add it on the Script step (line 'Farsi:'), then press the button again.")
            texts.append(text)
        adir = self.ep.audio_dir(lang)
        if choice["engine"] == "own":
            rec = self.ep.own_voice_path(lang)
            if rec is None:
                raise FriendlyError("You chose your own voice but no recording is uploaded.",
                                    "Upload it on the Voice step (one file for the whole episode), or put it in "
                                    f"Google Drive as {adir / 'own_voice.m4a'}.")
            fp = fingerprint(texts, file_sig(rec))
            if all(self.ep.state.fresh(f"voice:{lang}:{sc['id']}", fp, [adir / f"{sc['id']}.wav"]) for sc in sc_all):
                return
            self.rep.step("🎙️ Cutting your recording into scenes")
            method, parts = tts.split_own_recording(rec, texts, lang, adir)
            for sc, (wav, words) in zip(sc_all, parts):
                shutil.move(str(wav), adir / f"{sc['id']}.wav")
                write_json(adir / f"{sc['id']}.json", {"words": words, "engine": "your voice"})
                self.ep.state.done(f"voice:{lang}:{sc['id']}", fp, engine="your voice")
            self.rep.ok(f"Your recording is split into {len(parts)} scenes ({method})")
            self.rep.record("ok", f"Voice ({lang})", f"your voice, {method}")
            return
        todo = [(i, sc, t) for i, (sc, t) in enumerate(zip(sc_all, texts), 1)
                if not self.ep.state.fresh(f"voice:{lang}:{sc['id']}", fingerprint(t, choice), [adir / f"{sc['id']}.wav"])]
        if not todo:
            return
        self.rep.step(f"🗣️ Voiceover ({'Farsi' if lang == 'fa' else 'English'}, {len(todo)} scenes)")
        if lang == "fa" and choice["engine"] == "edge":
            self.rep.info("ℹ️ " + tts.EDGE_WARNING)
        engines = set()
        for i, sc, text in todo:
            self.rep.check_stop()
            with Timer() as t:
                engine, words = tts.speak(text, lang, choice, adir / f"{sc['id']}.wav", self.rep)
            write_json(adir / f"{sc['id']}.json", {"words": words, "engine": engine})
            self.ep.state.done(f"voice:{lang}:{sc['id']}", fingerprint(text, choice), engine=engine)
            engines.add(engine)
            self.rep.ok(f"Scene {i}/{len(sc_all)} voice ({engine}, {t.label})")
        robotic = any(e.startswith("espeak") for e in engines)
        self.rep.record("warn" if robotic else "ok", f"Voice ({lang})", ", ".join(sorted(engines)))
        if robotic:
            self.rep.warn("The emergency robot voice was used. Check the internet and redo the voice later.")

    def timeline(self, lang: str) -> dict:
        adir = self.ep.audio_dir(lang)
        scenes, words, t = [], [], 0.0
        sc_all = self.script["scenes"]
        for i, sc in enumerate(sc_all):
            wav = adir / f"{sc['id']}.wav"
            x, sr = tts.read_wav(wav)
            vlen = len(x) / sr
            dur = max(MIN_SCENE, LEAD + vlen + (LAST_TAIL if i == len(sc_all) - 1 else TAIL))
            scenes.append({"id": sc["id"], "start": round(t, 3), "dur": round(dur, 3), "voice": round(vlen, 3)})
            for w in (read_json(adir / f"{sc['id']}.json", {}) or {}).get("words", []):
                words.append({"w": w["w"], "s": round(t + LEAD + w["s"], 3), "e": round(t + LEAD + w["e"], 3)})
            t += dur
        tl = {"scenes": scenes, "words": words, "total": round(t + render.TRANSITION, 3)}
        write_json(adir / "timeline.json", tl)
        return tl

    def scene_clips(self, lang: str, fmt: str, tl: dict, progress=(0.0, 1.0)) -> list[Path]:
        size = self.out_size(fmt)
        out_paths = []
        sc_all = self.script["scenes"]
        todo_count = 0
        for i, (sc, info) in enumerate(zip(sc_all, tl["scenes"])):
            self.rep.check_stop()
            sid = sc["id"]
            seconds = info["dur"] + render.TRANSITION
            out = self.ep.clip_path(sid, fmt, lang)
            video = self.upload_video(sid) or self.hero_clip(sid, fmt)
            src = None if video else self.ep.scene_source_image(sid, fmt, self.opts.formats)
            if video is None and src is None:
                raise FriendlyError(f"Scene {i + 1} has no picture.", "Make the pictures on the Scenes step first.")
            shake = [0.12] if set(sc.get("sfx", [])) & {"impact", "thunder"} else []
            strength = 1.25 if sc.get("kind") == "hook" else 1.0
            dpath = self.depth_for(src) if src is not None else None
            fp = fingerprint(file_sig(video or src), file_sig(dpath), sc["camera"], sc.get("effects"), round(seconds, 3),
                             size, self.opts.effects, shake, strength, render.FPS)
            key = f"clip:{sid}:{fmt}:{lang}"
            if self.ep.state.fresh(key, fp, [out]):
                out_paths.append(out)
                continue
            if todo_count == 0:
                self.rep.step(f"🎞️ Scene motion ({fmt.replace('x', ':')}, {'Farsi' if lang == 'fa' else 'English'})")
            todo_count += 1
            with Timer() as t:
                if video is not None:
                    how = clip_mod.from_video(video, out, size, seconds, render.FPS)
                else:
                    how = clip_mod.from_image(src, dpath if dpath and dpath.exists() else None, out, size, seconds,
                                              render.FPS, sc["camera"], sc.get("effects"), self.scene_seed(sc),
                                              shake, strength, extras=self.opts.effects)
            self.ep.state.done(key, fp, method=how)
            self.rep.ok(f"Scene {i + 1}/{len(sc_all)}: {script.CAMERA_LABELS.get(sc['camera'], sc['camera'])}, {how} ({t.label})")
            a, b = progress
            self.rep.progress(a + (b - a) * (i + 1) / len(sc_all))
            out_paths.append(out)
        return out_paths

    def audio_mix(self, lang: str, tl: dict) -> tuple[Path, list[str], str]:
        sc = self.script
        mood = self.opts.music_mood if self.opts.music_mood != "auto" else sc.get("music_mood", "tense")
        seed = characters.stable_seed(f"{self.series.slug}/{self.ep.number}/music")
        prev = [p.get("music", "") for p in self.series.previous_summaries(self.ep.number, 3)]
        pick = music.choose_music(mood, seed, avoid=prev)
        sfx_on = self.opts.sfx
        events_spec = []
        if sfx_on:
            for s, info in zip(sc["scenes"], tl["scenes"]):
                for name in s.get("sfx", []):
                    t0 = info["start"]
                    at = {"whoosh": t0 - 0.3, "impact": t0 + 0.05, "riser": t0 - 2.4, "thunder": t0 + 0.25}.get(name, t0 + 0.1)
                    max_sec = info["dur"] if name in music.AMBIENT else 0
                    events_spec.append((round(max(0.0, at), 3), name, max_sec))
            last = tl["scenes"][-1]
            if not any(n == "sting" for _, n, _ in events_spec):  # end on a sting for the cliffhanger
                events_spec.append((round(last["start"] + LEAD + last["voice"] + 0.05, 3), "sting", 0))
        mix_path = self.ep.audio_dir(lang) / "mix.wav"
        fp = fingerprint(tl, pick.get("name"), events_spec, self.opts.music_volume, sfx_on,
                         [file_sig(self.ep.audio_dir(lang) / f"{s['id']}.wav") for s in sc["scenes"]])
        credits = [pick["credit"]] if pick.get("credit") else []
        if self.ep.state.fresh(f"mix:{lang}", fp, [mix_path]):
            info = self.ep.state.info(f"mix:{lang}")
            return mix_path, info.get("credits", credits), pick["name"]
        self.rep.step("🎵 Music and sound effects")
        n = int(tl["total"] * tts.SR)
        import numpy as np  # noqa: PLC0415

        voice = np.zeros(n, np.float32)
        for s, info in zip(sc["scenes"], tl["scenes"]):
            x, _ = tts.read_wav(self.ep.audio_dir(lang) / f"{s['id']}.wav")
            i0 = int((info["start"] + LEAD) * tts.SR)
            voice[i0: i0 + len(x)] += x[: max(0, n - i0)]
        if pick["kind"] == "library":
            bed = music.load_audio(Path(pick["path"]))
            self.rep.ok(f"Music: {pick['name']} (your library)")
        else:
            bed = music.generate_music(mood, tl["total"], seed)
            self.rep.ok(f"Music: generated '{mood}' track (yours to use, no license needed)")
        events = []
        for at, name, max_sec in events_spec:
            audio, credit = music.get_sfx(name, seed)
            if credit and credit not in credits:
                credits.append(credit)
            events.append((at, audio, music.SFX_GAIN.get(name, 0.5), max_sec))
        mixed = music.mix(voice, tl["total"], bed, self.opts.music_volume, events)
        raw = self.ep.audio_dir(lang) / "mix_raw.wav"
        music.write_stereo(raw, mixed)
        music.loudnorm(raw, mix_path)
        raw.unlink(missing_ok=True)
        self.ep.state.done(f"mix:{lang}", fp, credits=credits, music=pick["name"])
        self.rep.ok(f"Mixed: voice + music + {len(events)} sound effects, loudness -14 LUFS")
        self.rep.record("ok", "Music & SFX", pick["name"])
        return mix_path, credits, pick["name"]

    def final_videos(self) -> list[Path]:
        sc = self.script
        outs = []
        langs, fmts = self.opts.languages, self.opts.formats
        jobs = [(lang, fmt) for lang in langs for fmt in fmts]
        for j, (lang, fmt) in enumerate(jobs):
            base = 0.55 + 0.4 * j / len(jobs)
            span = 0.4 / len(jobs)
            self.rep.check_stop()
            tl = self.timeline(lang)
            clips = self.scene_clips(lang, fmt, tl, progress=(base, base + span * 0.75))
            mix_path, credits, music_name = self.audio_mix(lang, tl)
            size = self.out_size(fmt)
            ass = None
            if self.opts.captions:
                ass = captions.write_ass(self.ep.captions_dir() / f"{lang}_{fmt}.ass", tl["words"], size, fmt, lang,
                                         self.opts.caption_style, self.series.data.get("caption_accent", "yellow"),
                                         total=tl["total"])
            out = self.ep.video_path(lang, fmt)
            trans = [render.transition_for(s, i, len(sc["scenes"])) for i, s in enumerate(sc["scenes"])]
            fp = fingerprint([file_sig(c) for c in clips], file_sig(mix_path), ass.read_text(encoding="utf-8") if ass else "",
                             trans, size)
            key = f"video:{lang}:{fmt}"
            if not self.ep.state.fresh(key, fp, [out]):
                self.rep.step(f"🎬 Final video {fmt.replace('x', ':')} ({'Farsi' if lang == 'fa' else 'English'})")
                with Timer() as t:
                    title = sc.get("title_fa") if lang == "fa" and sc.get("title_fa") else sc.get("title", "")
                    render.assemble(clips, [s["dur"] for s in tl["scenes"]], trans, mix_path, ass, out, size, title)
                self.ep.state.done(key, fp, credits=credits, music=music_name)
                self.rep.ok(f"{out.name} ({tl['total']:.0f} s video, made in {t.label})")
            outs.append(out)
            self.rep.progress(base + span)
        self.rep.record("ok", "Final video", f"{len(outs)} file(s)")
        return outs

    def thumbnails_and_text(self) -> dict:
        sc = self.script
        self.rep.step("🖼️ Thumbnail, titles, description, hashtags")
        first = next((s for s in sc["scenes"] if self.ep.scene_source_image(s["id"], self.opts.primary_format, self.opts.formats)), None)
        thumbs = []
        if first:
            for lang in self.opts.languages:
                text = sc.get("thumbnail_text_fa") if lang == "fa" and sc.get("thumbnail_text_fa") else sc.get("thumbnail_text", "")
                for fmt in self.opts.formats:
                    src = self.ep.scene_source_image(first["id"], fmt, self.opts.formats)
                    size = (1280, 720) if fmt == "16x9" else (1080, 1920)
                    out = self.ep.export_dir / f"thumbnail_{lang}_{fmt}.jpg"
                    publish.make_thumbnail(src, text, lang, size, out, badge=f"EP {self.ep.number}")
                    thumbs.append(out)
        credits, music_name = [], ""
        for key in self.ep.state.keys("mix:"):
            info = self.ep.state.info(key)
            credits += [c for c in info.get("credits", []) if c not in credits]
            music_name = info.get("music", music_name)
        warnings = publish.variation_warnings(self.series, self.ep, sc, music_name)
        meta = publish.write_metadata(self.series, self.ep, sc, self.opts.languages, credits, self.opts.creator_note,
                                      self.rep, warnings=warnings)
        for w in warnings:
            self.rep.warn(w)
        self.series.remember_episode(
            self.ep.number, title=sc.get("title", ""), summary=sc.get("summary", ""), cliffhanger=sc.get("cliffhanger", ""),
            music=music_name, cameras=[s["camera"] for s in sc["scenes"]],
        )
        self.rep.ok("metadata.md is ready in the export folder")
        self.rep.record("ok", "Thumbnail & text", ", ".join({m["provider"] for m in meta["languages"].values()}))
        return {"thumbnails": thumbs, "metadata": meta}

    # ------------------------------------------------------------------ all together
    def make_video(self) -> dict:
        rep = self.rep
        with Timer() as total:
            rep.progress(0.02, "Characters")
            self.character_pictures()
            rep.progress(0.08, "Pictures")
            self.scene_pictures()
            rep.progress(0.35, "Hero clips")
            self.hero_clips()
            rep.progress(0.45, "Depth")
            self.depth_maps()
            rep.progress(0.5, "Voices")
            for lang in self.opts.languages:
                self.voices(lang)
            videos = self.final_videos()
            rep.progress(0.96, "Thumbnail")
            extra = self.thumbnails_and_text()
        result = {"videos": [str(v) for v in videos], "thumbnails": [str(t) for t in extra["thumbnails"]],
                  "metadata": str(self.ep.export_dir / "metadata.md"), "minutes": round(total.seconds / 60, 1)}
        write_json(self.ep.export_dir / "result.json", result)
        rep.done(result, f"Done in {total.label}! Your videos are in Google Drive: {self.ep.export_dir}")
        return result


# ---------------------------------------------------------------------------
# Quick test: 3 scenes, motion effects only, 720p, main format
# ---------------------------------------------------------------------------


def quick_test(rep: Reporter, idea: str = "", languages=("en",), fmt: str = "9x16") -> dict:
    s = config.get()
    rep.step("⚡ Quick test: 3 scenes, motion effects only (no hero clips), 720p")
    rep.info(f"Computer: {s.gpu.label}. Saving to: {s.root}")
    series = Series.create("Quick test")
    ep_dir = series.dir / "episodes" / "ep01"
    if ep_dir.exists():
        shutil.rmtree(ep_dir, ignore_errors=True)
    series.data["episodes"] = {}
    series.save()
    ep = series.episode(1)
    opts = EpisodeOptions(idea=idea.strip() or QUICK_IDEA, languages=list(languages) or ["en"], formats=[fmt],
                          resolution="720p", scene_count=3, hero_count=0, quick_test=True)
    ep.save_options(opts)
    pipe = Pipeline(series, ep, rep, opts)
    sc = pipe.write_script()
    if "fa" in opts.languages and not all(s.get("narration_fa") for s in sc["scenes"]):
        opts.languages = [lang for lang in opts.languages if lang != "fa"] or ["en"]
        if opts.languages == ["en"] and "en" not in languages:
            rep.warn("No Farsi text (the AI translator is busy), so the test uses English.")
        else:
            rep.warn("Farsi skipped in this test: no translation available right now.")
        rep.record("warn", "Farsi", "skipped (no translation)")
        ep.save_options(opts)
    rep.progress(0.05)
    result = pipe.make_video()
    lines = ["", "📋 Quick test results:"]
    icons = {"ok": "✅", "warn": "⚠️", "fail": "❌"}
    for status, part, detail in rep.summary:
        lines.append(f"   {icons.get(status, '•')} {part}: {detail}")
    for ln in lines:
        rep.info(ln)
    return result


def load_result(ep: Episode) -> dict | None:
    return read_json(ep.export_dir / "result.json", None)


def describe_state(ep: Episode) -> str:
    """Short status for the UI: what's done in this episode."""
    st = ep.state.data.get("steps", {})
    count = lambda p: sum(1 for k in st if k.startswith(p))  # noqa: E731
    return json.dumps({"pictures": count("image:"), "voices": count("voice:"), "clips": count("clip:"),
                       "videos": count("video:")})
