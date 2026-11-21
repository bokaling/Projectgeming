"""Runs all the steps in order and skips work that is already finished.

Order (research.md section 11, one big model on the GPU at a time):
script → character pictures → scene pictures (klein) → hero clips (Wan) →
depth → voices → scene clips → music/SFX mix → captions → final videos →
thumbnail + title/description/hashtags.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from . import captions, characters, config, images, publish, render, script
from .audio import music, tts
from .messages import FriendlyError, Reporter, Timer
from .paste import NARRATOR
from .motion import clip as clip_mod
from .motion import depth as depth_mod
from .motion import i2v
from .project import (UPLOAD_VIDEO_EXT, Episode, EpisodeOptions, Series, dims, fingerprint, read_json,
                      write_json)

LEAD, TAIL, LAST_TAIL, MIN_SCENE = 0.15, 0.35, 1.4, 2.2


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
        n = script.hero_target(self.opts)  # your number, or auto (T4: 1-2, L4: 3-6, A100: 5-10)
        if n <= 0:
            return []
        return [sc for sc in self.script["scenes"] if sc.get("hero") and not self.ep.upload_path(sc["id"])][:n]

    def hero_minutes(self) -> float:
        return self.opts.hero_minutes or config.gpu_profile().hero_minutes

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
        self.rep.step(f"🎬 Real-motion hero clips with Wan 2.2 ({len(heroes)}, up to {self.hero_minutes():.0f} min each)")
        made = 0
        for k, sc in enumerate(heroes, 1):
            self.rep.check_stop()
            src = self.ep.scene_source_image(sc["id"], fmt, self.opts.formats)
            if src is None:
                continue
            key = f"hero:{sc['id']}:{fmt}"
            fp = fingerprint(file_sig(src), i2v.hero_prompt(sc), self.hero_minutes(), self.scene_seed(sc))
            if self.ep.state.fresh(key, fp):
                made += int(bool(self.ep.state.info(key).get("ok")))
                continue
            with Timer() as t:
                ok, msg = i2v.make_hero_clip(src, sc, self.ep.hero_path(sc["id"], fmt), fmt, self.hero_minutes(),
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

    def narrator_value(self, lang: str) -> str:
        v = self.series.data.get("voices", {}).get(lang)
        return v if isinstance(v, str) and v else f"{tts.DEFAULT_VOICE[lang]['engine']}:{tts.DEFAULT_VOICE[lang]['voice']}"

    def voice_for(self, speaker: str, lang: str) -> dict:
        if speaker in (None, "", NARRATOR):
            return self.voice_choice(lang)
        return characters.voice_for(self.series, speaker, lang, self.narrator_value(lang))

    def scene_speech(self, sc: dict, lang: str) -> list[tuple[str, dict]]:
        """What is said in a scene, and by which voice: [(text, voice), ...]."""
        if lang == self.script.get("language", "en") and sc.get("lines"):
            groups: list[list[str]] = []
            for ln in sc["lines"]:  # consecutive lines by the same speaker are spoken in one go
                if groups and groups[-1][0] == ln["speaker"]:
                    groups[-1][1] += " " + ln["text"]
                else:
                    groups.append([ln["speaker"], ln["text"]])
            return [(text, self.voice_for(speaker, lang)) for speaker, text in groups if text.strip()]
        text = sc["narration"] if lang == "en" else sc.get("narration_fa", "")
        return [(text, self.voice_choice(lang))] if text.strip() else []

    def voices(self, lang: str) -> None:
        sc_all = self.script["scenes"]
        choice = self.voice_choice(lang)
        speech = []
        for i, sc in enumerate(sc_all, 1):
            parts = self.scene_speech(sc, lang)
            if not parts:
                raise FriendlyError(f"Scene {i} has no {'Farsi ' if lang == 'fa' else 'English '}text.",
                                    f"Add it on the Script step (line '{'Farsi' if lang == 'fa' else 'English'}:'), "
                                    "or turn that language off.")
            speech.append(parts)
        texts = [" ".join(t for t, _ in parts) for parts in speech]
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
        # Decide the engine for every voice ONCE, so the whole video sounds the same.
        tts.reset_resolved()
        resolved = {}
        for parts in speech:
            for _, ch in parts:
                key = (ch.get("engine"), ch.get("voice"))
                if key not in resolved:
                    resolved[key] = tts.resolve(lang, ch, self.rep)

        def fp_of(parts):
            return fingerprint([(t, resolved[(c.get("engine"), c.get("voice"))]) for t, c in parts])

        todo = [(i, sc, parts) for i, (sc, parts) in enumerate(zip(sc_all, speech), 1)
                if not self.ep.state.fresh(f"voice:{lang}:{sc['id']}", fp_of(parts), [adir / f"{sc['id']}.wav"])]
        if not todo:
            return
        voices_used = sorted({tts.label(*v) for v in resolved.values()})
        self.rep.step(f"🗣️ Voiceover ({'Farsi' if lang == 'fa' else 'English'}, {len(todo)} scenes, "
                      f"{len(voices_used)} voice{'s' if len(voices_used) > 1 else ''})")
        if any(v[0] == "edge" for v in resolved.values()) and lang == "fa":
            self.rep.info("ℹ️ " + tts.EDGE_WARNING)
        engines = set()
        for i, sc, parts in todo:
            self.rep.check_stop()
            with Timer() as t:
                used, words = tts.speak_lines(parts, lang, adir / f"{sc['id']}.wav", self.rep)
            write_json(adir / f"{sc['id']}.json", {"words": words, "engine": ", ".join(used)})
            self.ep.state.done(f"voice:{lang}:{sc['id']}", fp_of(parts), engine=", ".join(used))
            engines.update(used)
            if i == 1 or i % 10 == 0 or i == len(sc_all):
                self.rep.ok(f"Scene {i}/{len(sc_all)} voice ({', '.join(used)}, {t.label})")
        robotic = any(e.startswith("espeak") for e in engines)
        self.rep.record("warn" if robotic else "ok", f"Voice ({lang})", ", ".join(sorted(engines)))
        if robotic:
            self.rep.warn("The emergency robot voice was used. Check the internet and press Generate again later.")

    def timeline(self, lang: str) -> dict:
        adir = self.ep.audio_dir(lang)
        scenes, words, t = [], [], 0.0
        sc_all = self.script["scenes"]
        for i, sc in enumerate(sc_all):
            wav = adir / f"{sc['id']}.wav"
            x, sr = tts.read_wav(wav)
            vlen = len(x) / sr
            dur = render.snap(max(MIN_SCENE, LEAD + vlen + (LAST_TAIL if i == len(sc_all) - 1 else TAIL)))
            scenes.append({"id": sc["id"], "start": round(t, 3), "dur": round(dur, 3), "voice": round(vlen, 3)})
            for w in (read_json(adir / f"{sc['id']}.json", {}) or {}).get("words", []):
                words.append({"w": w["w"], "s": round(t + LEAD + w["s"], 3), "e": round(t + LEAD + w["e"], 3)})
            t += dur
        tl = {"scenes": scenes, "words": words, "total": round(t + render.TRANSITION, 3)}
        write_json(adir / "timeline.json", tl)
        return tl

    def scene_clips(self, lang: str, fmt: str, tl: dict, progress=(0.0, 1.0)) -> list[Path]:
        size = self.out_size(fmt)
        out_paths, jobs = [], []
        sc_all = self.script["scenes"]
        for i, (sc, info) in enumerate(zip(sc_all, tl["scenes"])):
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
            out_paths.append(out)
            if self.ep.state.fresh(f"clip:{sid}:{fmt}:{lang}", fp, [out]):
                continue
            jobs.append({"i": i, "key": f"clip:{sid}:{fmt}:{lang}", "fp": fp, "out": str(out), "size": list(size),
                         "seconds": seconds, "fps": render.FPS, "video": str(video) if video else "",
                         "image": str(src) if src else "", "depth": str(dpath) if dpath and dpath.exists() else "",
                         "camera": sc["camera"], "fx": sc.get("effects") or [], "seed": self.scene_seed(sc),
                         "shake": shake, "strength": strength, "extras": self.opts.effects})
        if not jobs:
            return out_paths
        from .motion import gpu  # noqa: PLC0415

        prof = config.gpu_profile()
        workers = 1 if gpu.available() else prof.workers
        how_label = "GPU" if gpu.available() else (f"{workers} CPU cores" if workers > 1 else "CPU")
        self.rep.step(f"🎞️ Scene motion ({fmt.replace('x', ':')}, {'Farsi' if lang == 'fa' else 'English'}, "
                      f"{len(jobs)} scenes, {how_label})")
        a, b = progress

        def finished(k, job, how, secs):
            self.ep.state.done(job["key"], job["fp"], method=how)
            sc = sc_all[job["i"]]
            if k == 1 or k % 10 == 0 or k == len(jobs):
                self.rep.ok(f"Scene {job['i'] + 1}/{len(sc_all)}: "
                            f"{script.CAMERA_LABELS.get(sc['camera'], sc['camera'])}, {how} ({secs})")
            self.rep.progress(a + (b - a) * k / len(jobs), f"Scene motion {k}/{len(jobs)}")

        if workers > 1 and len(jobs) > 1:  # several scenes at once, each in its own small Python process
            import concurrent.futures  # noqa: PLC0415

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(clip_mod.run_in_subprocess, job): job for job in jobs}
                for k, fut in enumerate(concurrent.futures.as_completed(futures), 1):
                    if self.rep.stop_requested:
                        for f in futures:
                            f.cancel()
                        self.rep.check_stop()
                    finished(k, futures[fut], fut.result(), "parallel")
        else:
            for k, job in enumerate(jobs, 1):
                self.rep.check_stop()
                with Timer() as t:
                    how = clip_mod.render_job(job)
                finished(k, job, how, t.label)
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
            clips = self.scene_clips(lang, fmt, tl, progress=(base, base + span * 0.7))
            mix_path, credits, music_name = self.audio_mix(lang, tl)
            size = self.out_size(fmt)
            ass = None
            if self.opts.captions:
                ass = captions.write_ass(self.ep.captions_dir() / f"{lang}_{fmt}.ass", tl["words"], size, fmt, lang,
                                         self.opts.caption_style, self.series.data.get("caption_accent", "yellow"),
                                         total=tl["total"])
            ass_text = ass.read_text(encoding="utf-8") if ass else ""
            out = self.ep.video_path(lang, fmt)
            n = len(sc["scenes"])
            trans = [render.transition_for(s, i, n) for i, s in enumerate(sc["scenes"])]
            durs = [s["dur"] for s in tl["scenes"]]
            ranges = render.chunk_ranges(n)
            chunk_paths, start, made = [], 0.0, 0
            label = f"{fmt.replace('x', ':')}, {'Farsi' if lang == 'fa' else 'English'}"
            for k, (a, b) in enumerate(ranges):
                self.rep.check_stop()
                path = self.ep.dir / "render" / f"{lang}_{fmt}_{k:03d}.mp4"
                last = k == len(ranges) - 1
                fp = fingerprint([file_sig(c) for c in clips[a:b]], durs[a:b], trans[a:b], ass_text, round(start, 4),
                                 size, last)
                key = f"chunk:{lang}:{fmt}:{k:03d}"
                if not self.ep.state.fresh(key, fp, [path]):
                    if made == 0:
                        self.rep.step(f"🎬 Final video {label}: {len(ranges)} part{'s' if len(ranges) > 1 else ''}")
                    with Timer() as t:
                        render.render_chunk(clips[a:b], durs[a:b], trans[a:b], ass, start, path, size, last)
                    self.ep.state.done(key, fp)
                    made += 1
                    self.rep.ok(f"Part {k + 1}/{len(ranges)} saved to Drive ({t.label})")
                chunk_paths.append(path)
                start += sum(durs[a:b])
                self.rep.progress(base + span * (0.7 + 0.25 * (k + 1) / len(ranges)))
            fp = fingerprint([file_sig(c) for c in chunk_paths], file_sig(mix_path))
            key = f"video:{lang}:{fmt}"
            if not self.ep.state.fresh(key, fp, [out]):
                title = sc.get("title_fa") if lang == "fa" and sc.get("title_fa") else sc.get("title", "")
                render.mux(chunk_paths, mix_path, out, tl["total"], title)
                self.ep.state.done(key, fp, credits=credits, music=music_name)
                self.rep.ok(f"{out.name} ({_mmss(tl['total'])} video)")
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
        chapters = {}
        if self.opts.length == "long":
            for lang in self.opts.languages:
                tl = read_json(self.ep.audio_dir(lang) / "timeline.json", None)
                if tl:
                    chapters[lang] = publish.make_chapters(sc, tl, lang)
        meta = publish.write_metadata(self.series, self.ep, sc, self.opts.languages, credits, self.opts.creator_note,
                                      self.rep, warnings=warnings, chapters=chapters)
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
    def make_video(self, final: bool = True) -> dict:
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
        prof = config.gpu_profile()
        units = round(total.seconds / 3600 * prof.cu_per_hour, 2)
        result = {"videos": [str(v) for v in videos], "thumbnails": [str(t) for t in extra["thumbnails"]],
                  "metadata": str(self.ep.export_dir / "metadata.md"), "minutes": round(total.seconds / 60, 1),
                  "gpu": prof.name, "units": units, "length": self.opts.length}
        write_json(self.ep.export_dir / "result.json", result)
        log_video_usage(self.series.name, self.ep.number, self.opts.length, prof.name, total.seconds, units)
        msg = (f"Done in {total.label} on {prof.name} (≈{units} compute units). "
               f"Your videos are in Google Drive: {self.ep.export_dir}")
        if final:
            rep.done(result, msg)
        else:
            rep.ok(msg)
        return result


# ---------------------------------------------------------------------------
# One click: your script (or several, separated by =====) → finished videos
# ---------------------------------------------------------------------------


def _mmss(sec: float) -> str:
    sec = int(round(sec))
    return f"{sec // 60}:{sec % 60:02d}"


def log_video_usage(series: str, number: int, length: str, gpu: str, seconds: float, units: float) -> None:
    """Remember time and compute units per video (StoryForge/usage_videos.json) to plan your month."""
    path = config.get().root / "usage_videos.json"
    data = read_json(path, []) or []
    data.append({"series": series, "episode": number, "length": length, "gpu": gpu,
                 "minutes": round(seconds / 60, 1), "units": units, "date": time.strftime("%Y-%m-%d")})
    write_json(path, data[-500:])


def generate(series: Series, opts: EpisodeOptions, text: str, rep: Reporter, number: int | None = None) -> dict:
    """Everything after you press Generate: read script, plan, pictures, motion, voice, captions, music, export."""
    from . import paste  # noqa: PLC0415

    texts = paste.split_scripts(text) if opts.source == "paste" else [""]
    if opts.source == "paste" and not texts:
        raise FriendlyError("The script box is empty.", "Paste your script, then press Generate.")
    if len(texts) > 1:
        return run_batch(series, opts, texts, rep, number)
    ep = series.episode(number or series.next_episode_number())
    set_current_episode(series, ep)
    ep.save_options(opts)
    pipe = Pipeline(series, ep, rep, opts)
    if opts.source == "paste":
        script.script_from_text(series, ep, opts, texts[0], rep)
    else:
        pipe.write_script()
    return pipe.make_video()


def run_batch(series: Series, opts: EpisodeOptions, texts: list[str], rep: Reporter, number: int | None = None) -> dict:
    """Batch mode: make every script one after another. One failure doesn't stop the others."""
    import copy  # noqa: PLC0415

    rep.step(f"📚 Batch: {len(texts)} scripts, one after another")
    done, failed = [], []
    for k, text in enumerate(texts, 1):
        rep.check_stop()
        ep = series.episode((number + k - 1) if number else series.next_episode_number())
        rep.step(f"📚 Script {k}/{len(texts)} → episode {ep.number}")
        set_current_episode(series, ep)
        o = copy.deepcopy(opts)
        ep.save_options(o)
        try:
            script.script_from_text(series, ep, o, text, rep)
            res = Pipeline(series, ep, rep, o).make_video(final=False)
            done.append({"episode": ep.number, **res})
        except Exception as exc:  # noqa: BLE001
            from .messages import StopRequested, explain  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            what, todo = explain(exc)
            rep.error(f"Script {k} (episode {ep.number}) failed: {what}", todo)
            failed.append(ep.number)
    summary = {"videos": [v for d in done for v in d["videos"]], "thumbnails": [t for d in done for t in d["thumbnails"]],
               "episodes": [d["episode"] for d in done], "failed": failed,
               "units": round(sum(d.get("units", 0) for d in done), 2)}
    rep.record("ok" if not failed else "warn", "Batch", f"{len(done)} done, {len(failed)} failed")
    rep.done(summary, f"Batch finished: {len(done)} of {len(texts)} videos made (≈{summary['units']} compute units)."
             + (f" Failed: episodes {failed}. Press Generate again to retry them." if failed else ""))
    return summary


def set_current_episode(series: Series, ep: Episode) -> None:
    write_json(config.get().root / "app.json", {"series": series.slug, "episode": ep.number})


# ---------------------------------------------------------------------------
# Quick test: 3 scenes, motion effects only, 720p, main format
# ---------------------------------------------------------------------------

QUICK_SCRIPT = """[TITLE] The Night Radio
[SCENE] a lonely lighthouse on a cliff at night, storm clouds over the sea
NARRATOR: At exactly three in the morning, the old radio in the lighthouse turned itself on.
[SCENE] an old brass radio glowing on a wooden desk, rain on the window
NARRATOR: A voice came through the static. It was her own voice.
MIRA: Who is this?
[SCENE] a dark wooden door with warm light under it
NARRATOR: The voice whispered one last warning. Do not open the door.
"""


def quick_test(rep: Reporter, text: str = "", languages=("en",), length: str = "short") -> dict:
    """3 scenes from your script (or a sample), motion effects only, 720p."""
    from . import paste  # noqa: PLC0415

    s = config.get()
    prof = config.gpu_profile()
    rep.step("⚡ Quick test: 3 scenes, motion effects only (no hero clips), 720p")
    rep.info(f"Computer: {s.gpu.label} → {prof.label}. Saving to: {s.root}")
    first = (paste.split_scripts(text) or [""])[0]
    if first.strip():
        scenes = paste.to_scenes(paste.parse_lines(first), length)[:3]
        title = paste.parse_lines(first)["title"]
        body = "\n".join(([f"[TITLE] {title}"] if title else []) + [
            line for sc in scenes for line in ([f"[SCENE] {sc['visual']}"] if sc["visual"].strip() else ["[SCENE] "])
            + [f"{ln['speaker']}: {ln['text']}" for ln in sc["lines"]]])
    else:
        body = QUICK_SCRIPT
    series = Series.create("Quick test")
    ep_dir = series.dir / "episodes" / "ep01"
    if ep_dir.exists():
        shutil.rmtree(ep_dir, ignore_errors=True)
    series.data["episodes"] = {}
    series.save()
    ep = series.episode(1)
    opts = EpisodeOptions.from_dict({"script_text": body, "languages": list(languages) or ["en"], "length": length,
                                     "resolution": "720p", "hero_count": 0, "quick_test": True, "source": "paste"})
    ep.save_options(opts)
    set_current_episode(series, ep)
    pipe = Pipeline(series, ep, rep, opts)
    sc = script.script_from_text(series, ep, opts, body, rep)
    other = [x for x in opts.languages if x != sc["language"]]
    if other and not all(x.get("narration_fa" if other[0] == "fa" else "narration") for x in sc["scenes"]):
        opts.languages = [sc["language"]]
        rep.warn("The other language is skipped in this test: no translation available right now.")
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
