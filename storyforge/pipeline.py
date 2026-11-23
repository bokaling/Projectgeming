"""Runs every step in order and skips work that is already finished (resume after a disconnect).

script → (scene plan ∥ voiceover) → timing → 3D render of every scene (keyword captions burned in)
→ music + sound design → join without re-encoding → thumbnail + title/description/hashtags/chapters.
"""

from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path

from . import beats, captions, characters, config, formats, paste, publish, render, script
from .audio import music, tts
from .messages import FriendlyError, Reporter, Timer
from .paste import NARRATOR
from .project import Episode, EpisodeOptions, Series, dims, fingerprint, read_json, write_json

LEAD, TAIL, LAST_TAIL, MIN_SCENE = 0.08, 0.22, 0.6, 1.6  # seconds: short gaps between scenes
END_CARD, END_HOLD = 1.6, 0.8
QUALITY_CHECK_READY = True  # the automatic quality check (step 🔍) is on
SPEAKER_GAP, REVEAL_PAUSE = 0.2, 0.4  # pause between speakers / before a reveal
CHARACTER_SPEED = 1.05


def split_for_pauses(text: str) -> list[str]:
    """Split before sentences with a reveal, so a short dramatic pause can go there."""
    sents = [x for x in re.split(r"(?<=[.!?؟…])\s+", (text or "").strip()) if x.strip()]
    out: list[str] = []
    for k, s in enumerate(sents):
        if out and k > 0 and beats.has_any(s, beats.STRONG_REVEAL):
            out.append(s)
        elif out:
            out[-1] += " " + s
        else:
            out.append(s)
    return out or [text]


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
            raise FriendlyError("This episode has no script yet.", "Paste a script or type a topic on step 1.")
        return sc

    def out_size(self, fmt: str) -> tuple[int, int]:
        return dims(fmt, self.opts.resolution)

    def voice_choice(self, lang: str) -> dict:
        """The narrator: about 1.1x speed (more energy). Word times come from the engine, so captions stay in sync."""
        c = tts.parse_voice(self.series.data.get("voices", {}).get(lang), lang)
        c["speed"] = paste.NARRATOR_SPEED if c.get("engine") != "own" else 1.0
        return c

    def narrator_value(self, lang: str) -> str:
        v = self.series.data.get("voices", {}).get(lang)
        return v if isinstance(v, str) and v else f"{tts.DEFAULT_VOICE[lang]['engine']}:{tts.DEFAULT_VOICE[lang]['voice']}"

    def voice_for(self, speaker: str, lang: str) -> dict:
        if speaker in (None, "", NARRATOR):
            return self.voice_choice(lang)
        c = dict(characters.voice_for(self.series, speaker, lang, self.narrator_value(lang)))
        c["speed"] = CHARACTER_SPEED
        return c

    def scene_speech(self, sc: dict, lang: str) -> list[tuple[str, dict, float]]:
        """What is said in a scene, by which voice, and the pause before it: [(text, voice, pause), ...].

        A short dramatic pause comes before a sentence with a reveal ("that's when…", "it was never…").
        """
        if lang == self.script.get("language", "en") and sc.get("lines"):
            groups: list[list[str]] = []
            for ln in sc["lines"]:  # consecutive lines by the same speaker are spoken in one go
                if groups and groups[-1][0] == ln["speaker"]:
                    groups[-1][1] += " " + ln["text"]
                else:
                    groups.append([ln["speaker"], ln["text"]])
            items = [(text, self.voice_for(speaker, lang)) for speaker, text in groups if text.strip()]
        else:
            text = sc["narration"] if lang == "en" else sc.get("narration_fa", "")
            items = [(text, self.voice_choice(lang))] if text.strip() else []
        out = []
        for text, voice in items:
            for k, piece in enumerate(split_for_pauses(text)):
                out.append((piece, voice, REVEAL_PAUSE if k else SPEAKER_GAP))
        return out

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
        texts = [" ".join(t for t, _, _ in parts) for parts in speech]
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
        for attempt in range(3):
            try:
                return self._tts_voices(lang, sc_all, speech, adir)
            except tts.VoiceFailed as exc:  # a voice broke halfway: the WHOLE video switches to the backup voice
                if attempt == 2:
                    raise
                self.rep.warn(f"{exc.what} Switching the whole video to the backup voice (same gender), so the "
                              "voice never changes in the middle.")

    def _tts_voices(self, lang: str, sc_all: list, speech: list, adir: Path) -> None:
        # Decide the engine for every voice ONCE, so the whole video sounds the same.
        tts.reset_resolved()
        resolved = {}
        for parts in speech:
            for _, ch, _ in parts:
                key = (ch.get("engine"), ch.get("voice"))
                if key not in resolved:
                    resolved[key] = tts.resolve(lang, ch, self.rep)

        def fp_of(parts):
            return fingerprint([(t, resolved[(c.get("engine"), c.get("voice"))], c.get("speed"), round(g, 2))
                                for t, c, g in parts])

        todo = [(i, sc, parts) for i, (sc, parts) in enumerate(zip(sc_all, speech), 1)
                if not self.ep.state.fresh(f"voice:{lang}:{sc['id']}", fp_of(parts), [adir / f"{sc['id']}.wav"])]
        if not todo:
            return
        voices_used = sorted({tts.label(*v) for v in resolved.values()})
        self.rep.step(f"🗣️ Voiceover ({'Farsi' if lang == 'fa' else 'English'}, {len(todo)} scenes, "
                      f"{len(voices_used)} voice{'s' if len(voices_used) > 1 else ''}, narrator "
                      f"{paste.NARRATOR_SPEED:g}x speed)")
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

    def all_voices(self) -> None:
        for lang in self.opts.languages:
            self.voices(lang)

    # ------------------------------------------------------------------ the 3D scene plan
    def scene_plan(self, force: bool = False) -> dict:
        """Script → scene plan (AI, checked and repaired). Saved as plan.json; reused while the script is the same."""
        from .world import plan as P  # noqa: PLC0415
        from .world import planner  # noqa: PLC0415
        from .world.scene import freeze_layout  # noqa: PLC0415

        sc = self.script
        texts = [s["narration"] for s in sc["scenes"]]
        fp = fingerprint(texts, [s.get("visual", "") for s in sc["scenes"]], self.opts.length, "plan-1")
        plan = self.ep.load_plan()
        if plan and not force and self.ep.state.fresh("plan", fp, [self.ep.plan_path]):
            return plan
        self.rep.step("🧭 Scene plan (the 3D world and every shot)")
        with Timer() as t:
            plan, provider, fixes = planner.make_plan(sc, self.opts.length, self.rep)
        freeze_layout(plan)
        self.ep.save_plan(plan)
        (self.ep.dir / "plan.md").write_text(P.summary(plan), encoding="utf-8")
        self.ep.state.done("plan", fp, provider=provider, fixes=fixes)
        n_obj = sum(o["count"] for o in plan["objects"])
        self.rep.ok(f"Plan by {provider}: {len(plan['areas'])} areas, {n_obj} objects, {len(plan['scenes'])} shots "
                    f"({t.label})")
        if fixes:
            self.rep.info(f"🔧 Auto-fixed {len(fixes)} thing(s) in the plan: " + "; ".join(fixes[:4])
                          + (" …" if len(fixes) > 4 else ""))
        self.rep.record("ok" if "no AI" not in provider else "warn", "Scene plan", provider)
        return plan

    def save_plan(self, plan: dict) -> dict:
        """Your edited plan (or a fixed scene): checked, saved, kept until the script changes."""
        from .world import plan as P  # noqa: PLC0415
        from .world.scene import freeze_layout  # noqa: PLC0415

        sc = self.script
        plan, fixes = P.validate(plan, [s["narration"] for s in sc["scenes"]])
        freeze_layout(plan)  # new areas get a fixed place too
        self.ep.save_plan(plan)
        (self.ep.dir / "plan.md").write_text(P.summary(plan), encoding="utf-8")
        fp = fingerprint([s["narration"] for s in sc["scenes"]], [s.get("visual", "") for s in sc["scenes"]],
                         self.opts.length, "plan-1")
        self.ep.state.done("plan", fp, provider="edited", fixes=fixes)
        return plan

    # ------------------------------------------------------------------ timing
    def timeline(self, lang: str) -> dict:
        """Every scene lasts exactly as long as its voice (plus a short breath)."""
        adir = self.ep.audio_dir(lang)
        scenes, words, t = [], [], 0.0
        sc_all = self.script["scenes"]
        for i, sc in enumerate(sc_all):
            x, sr = tts.read_wav(adir / f"{sc['id']}.wav")
            vlen = len(x) / sr
            tail = LAST_TAIL if i == len(sc_all) - 1 else TAIL
            dur = render.snap(max(MIN_SCENE, LEAD + vlen + tail))
            scenes.append({"id": sc["id"], "start": round(t, 3), "dur": round(dur, 3), "voice": round(vlen, 3)})
            for w in (read_json(adir / f"{sc['id']}.json", {}) or {}).get("words", []):
                words.append({"w": w["w"], "s": round(t + LEAD + w["s"], 3), "e": round(t + LEAD + w["e"], 3)})
            t += dur
        from .world.scene import END_OVERVIEW  # noqa: PLC0415

        # explainers end on an overview of the whole system that flies back to shot 1 (the video loops);
        # "Part X" end cards are only for story series (option)
        card = self.opts.end_card or formats.get(self.video_format())["ending"] == "card"  # story series: "Part X"
        end = render.snap(END_CARD if card else END_OVERVIEW)
        total = round(t + end, 3)
        tl = {"scenes": scenes, "words": words, "total": total,
              "end": {"start": round(t, 3), "dur": end, "kind": "card" if card else "overview"},
              "beats": beats.find_beats(words, total, self.opts.length)}
        write_json(adir / "timeline.json", tl)
        return tl

    # ------------------------------------------------------------------ 3D render
    def keyword_items(self, world) -> list[dict]:
        items = []
        for i, sc in enumerate(world.scenes):
            for k in sc["plan"]["keywords"]:
                st = sc["start"] + world.at_time(i, k.get("at"), 0.15)
                items.append({"text": k["text"], "kind": k["kind"], "start": st, "end": sc["end"]})
        return items

    def scene_fp(self, plan: dict, tl: dict, i: int, size, extra="") -> str:
        """What a scene clip depends on: the objects it can show (their areas, earlier lasting changes and when they
        first appear), this shot's actions, labels and keywords, this camera and the one before, and the timing.
        So fixing one shot re-renders that shot (and the ones that really show the change), not the whole video."""
        from .world.plan import relevant_objects  # noqa: PLC0415
        from .world.scene import PERSIST  # noqa: PLC0415
        from .world.video import RENDER_VERSION  # noqa: PLC0415

        sc = plan["scenes"]
        rel = relevant_objects(plan, i)
        objs = [o for o in plan["objects"] if o["id"] in rel]
        areas = [a for a in plan["areas"] if a["id"] in {o["area"] for o in objs}]
        lasting = [a for s in sc[:i] for a in s["actions"] if a["do"] in PERSIST and a["target"].split(".")[0] in rel]
        first_seen = {}  # an object that 'appears' later is hidden until then, even in earlier shots
        for s in sc:
            for a in s["actions"]:
                oid = a["target"].split(".")[0]
                if oid in rel and (a["do"] in ("appear", "disappear") and oid not in first_seen or a["do"] == "show_part"):
                    first_seen.setdefault(a["target"] if a["do"] == "show_part" else oid, a["do"])
        return fingerprint(areas, objs, lasting, sorted(first_seen.items()), sc[i]["actions"],
                           [s["camera"] for s in sc[max(0, i - 1): i + 1]], sc[i]["labels"], sc[i]["keywords"],
                           tl["scenes"][max(0, i - 1): i + 1], [w for w in tl["words"]
                                                                if tl["scenes"][i]["start"] <= w["s"] < tl["scenes"][i]["start"]
                                                                + tl["scenes"][i]["dur"]],
                           size, self.opts.captions, RENDER_VERSION, extra)

    def render_clips(self, lang: str, fmt: str, tl: dict, plan: dict, only: list[int] | None = None,
                     progress=(0.0, 1.0)) -> list[Path]:
        from .world import video  # noqa: PLC0415
        from .world.labels import LabelMaker  # noqa: PLC0415
        from .world.scene import World  # noqa: PLC0415

        size = self.out_size(fmt)
        lang_plan = plan
        world = World(lang_plan, tl, size, lang)
        n = len(world.scenes)
        items = [("end", tl["end"]["start"], tl["end"]["start"] + tl["end"]["dur"])]
        items = [(s["id"], world.scenes[k]["start"], world.scenes[k]["end"]) for k, s in enumerate(self.script["scenes"])] + items
        events = []
        words_mode = formats.get(self.video_format())["captions"] == "words"
        if self.opts.captions and words_mode:  # story: single big words, red key words
            events = captions.caption_events(tl["words"], size, fmt, lang, style="pop", accent="red", total=tl["total"],
                                             single=True)
        elif self.opts.captions:
            events = captions.keyword_events(self.keyword_items(world), lang, tl["total"])
        head = captions.header(size, fmt, lang, style="pop", accent="red") if words_mode else \
            captions.keyword_header(size, fmt, lang)
        outs, todo = [], []
        for k, (cid, t0, t1) in enumerate(items):
            out = self.ep.clip_path(cid, fmt, lang)
            outs.append(out)
            ev = captions.slice_events(events, t0, t1) if cid != "end" else []
            ass_text = captions.to_text(head, ev) if ev else ""
            card = self.end_card_text(lang) if cid == "end" else ""
            fp = (self.scene_fp(plan, tl, k, size, ass_text) if cid != "end"
                  else fingerprint(plan, tl["end"], tl["scenes"][-1], size, card, video.RENDER_VERSION))
            key = f"clip:{cid}:{fmt}:{lang}"
            if only is not None and k not in only and self.ep.state.fresh(key, None, [out]):
                continue
            if self.ep.state.fresh(key, fp, [out]):
                continue
            todo.append((k, cid, t0, t1, out, ass_text, card, key, fp))
        if not todo:
            return outs
        renderer, rsize, how = video.make_renderer(size)
        try:
            if tuple(rsize) != tuple(size):  # drawn smaller on a CPU: labels must be placed in the pixels drawn
                world = World(lang_plan, tl, rsize, lang)
            world.upload(renderer)
            labels = LabelMaker((renderer.W, renderer.H), lang)
            self.rep.step(f"🎬 3D render ({fmt.replace('x', ':')}, {len(todo)} clip(s), {how}, encoder "
                          f"{config.video_encoder()})")
            a, b = progress
            frames = 0
            for j, (k, cid, t0, t1, out, ass_text, card, key, fp) in enumerate(todo, 1):
                self.rep.check_stop()
                vf = ""
                if ass_text:
                    ass = self.ep.captions_dir() / f"{lang}_{fmt}_{cid}.ass"
                    ass.write_text(ass_text, encoding="utf-8")
                    vf = captions.ass_filter(ass)
                with Timer() as tm:
                    frames += video.render_span(world, renderer, labels, t0, t1, out, size, vf,
                                                card={"text": card, "lang": lang} if card else None,
                                                stop=lambda: self.rep.stop_requested)
                self.ep.state.done(key, fp, frames=int(round((t1 - t0) * video.FPS)))
                label = ("End card" if card else "Overview of the whole system") if cid == "end" else f"Scene {k + 1}/{n}"
                self.rep.ok(f"{label} ({t1 - t0:.1f} s video, {tm.label})")
                self.rep.progress(a + (b - a) * j / len(todo), f"3D render {j}/{len(todo)}")
            self.rep.record("ok", "3D render", how)
        finally:
            renderer.release()
        return outs

    def end_card_text(self, lang: str) -> str:
        card = self.opts.end_card or formats.get(self.video_format())["ending"] == "card"
        return publish.end_card_text(self.ep.number, lang, self.opts.final_episode) if card else ""

    def video_format(self) -> str:
        """The format of this video (the user's choice, or guessed from the title and the first lines)."""
        sc = self.script or {}
        text = " ".join([sc.get("title", "")] + [s.get("narration", "") for s in sc.get("scenes", [])[:2]])
        return formats.resolve(self.opts.video_format, text)

    def stills(self, fmt: str, lang: str, tl: dict, plan: dict, at: float = 0.6, only=None) -> list[Path]:
        """One still frame per scene (for the app, the quality check and the thumbnail). only = these shots."""
        from .world import video  # noqa: PLC0415
        from .world.labels import LabelMaker  # noqa: PLC0415
        from .world.scene import World  # noqa: PLC0415

        size = self.out_size(fmt)
        renderer, rsize, how = video.make_renderer(size)
        world = World(plan, tl, rsize, lang)  # the size actually drawn (smaller on a CPU)
        try:
            world.upload(renderer)
            labels = LabelMaker((renderer.W, renderer.H), lang)
            outs = []
            for i, sc in enumerate(world.scenes):
                out = self.ep.still_path(self.script["scenes"][i]["id"], fmt)
                if only is None or i in only:
                    video.render_still(world, renderer, labels, sc["start"] + sc["dur"] * at, out)
                outs.append(out)
            return outs
        finally:
            renderer.release()

    # ------------------------------------------------------------------ sound
    def audio_mix(self, lang: str, tl: dict, plan: dict | None = None) -> tuple[Path, list[str], str]:
        """Voice + music that builds and drops before reveals + soft sounds (whoosh on camera flights,
        machine hums, bubbling, sparks, booms on reveals). Nothing above 8 kHz, -14 LUFS."""
        sc = self.script
        plan = plan or {"scenes": []}
        fmood = formats.get(self.video_format())["mood"]
        mood = self.opts.music_mood if self.opts.music_mood != "auto" else (
            fmood if fmood != "auto" and sc.get("music_mood", "explainer") == "explainer" else sc.get("music_mood", "explainer"))
        seed = characters.stable_seed(f"{self.series.slug}/{self.ep.number}/music")
        prev = [p.get("music", "") for p in self.series.previous_summaries(self.ep.number, 3)]
        pick = music.choose_music(mood, seed, avoid=prev)
        reveals = list(tl.get("beats", {}).get("reveal", []))
        events_spec = []
        if self.opts.sfx:
            for k, info in enumerate(tl["scenes"][1:], 1):  # the camera flies to the next shot
                if all(abs(info["start"] - r) > 0.6 for r in reveals):
                    events_spec.append((round(max(0.0, info["start"] - 0.25), 3), "low_whoosh", 0))
            for r in reveals:
                events_spec.append((round(max(0.0, r - 0.02), 3), "boom", 0))
            from .world.scene import World  # noqa: PLC0415

            if plan.get("scenes"):
                world = World(plan, tl, (1080, 1920), lang)
                looping = set()
                for e in world.events:
                    snd = {"spin": "hum", "flow": "pour", "fill": "pour", "drain": "pour", "bubbles": "bubbles",
                           "sparks": "zap", "light_on": "click", "appear": "pop", "alarm": "alarm_hum",
                           "smoke": "steam", "shake": "rumble", "cutaway": "low_whoosh", "drop": "pop"}.get(e.do)
                    if e.do == "move" and any(p.kind == "wheel" for p in world.groups[e.oid][0].model.parts):
                        snd = "rumble"  # a vehicle drives
                    if not snd:
                        continue
                    if snd in music.LOOPED:  # one loop of each kind per shot is enough (5 houses ≠ 5 hums)
                        if (snd, e.scene) in looping:
                            continue
                        looping.add((snd, e.scene))
                    end = min(e.end, world.scenes[e.scene]["end"])
                    length = max(0.0, end - e.start) if snd in music.LOOPED else 0
                    if snd in ("pop", "click") and any(abs(e.start - t0) < 0.25 for t0, n, _ in events_spec if n == snd):
                        continue
                    events_spec.append((round(e.start, 3), snd, round(length, 3)))
            if len(tl["scenes"]) > 1:
                events_spec.append((round(max(0.0, tl["scenes"][-1]["start"] - 2.55), 3), "soft_riser", 0))
            if tl.get("end", {}).get("kind") == "overview":  # up to the overview, and back down to shot 1
                events_spec.append((round(tl["end"]["start"], 3), "low_whoosh", 0))
                events_spec.append((round(tl["total"] - 1.0, 3), "low_whoosh", 0))
        mix_path = self.ep.audio_dir(lang) / "mix.wav"
        fp = fingerprint(tl, pick.get("name"), events_spec, self.opts.music_volume, self.opts.sfx, reveals, "sound-3d-3",
                         [file_sig(self.ep.audio_dir(lang) / f"{s['id']}.wav") for s in sc["scenes"]])
        credits = [pick["credit"]] if pick.get("credit") else []
        if self.ep.state.fresh(f"mix:{lang}", fp, [mix_path]):
            info = self.ep.state.info(f"mix:{lang}")
            return mix_path, info.get("credits", credits), pick["name"]
        self.rep.step("🎵 Music and sound design")
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
        env, hits = music.tension_envelope(tl["total"], reveals, hits=not self.opts.sfx)
        events = []
        for at, name, max_sec in events_spec:
            audio, credit = music.get_sfx(name, seed)
            if credit and credit not in credits:
                credits.append(credit)
            events.append((at, audio, music.SFX_GAIN.get(name, 0.3), max_sec))
        for h in hits:
            events.append((h, music.make_sfx("boom", seed), 0.22, 0))
        mixed = music.mix(voice, tl["total"], bed, self.opts.music_volume, events, music_env=env)
        raw = self.ep.audio_dir(lang) / "mix_raw.wav"
        music.write_stereo(raw, mixed)
        music.loudnorm(raw, mix_path)
        raw.unlink(missing_ok=True)
        self.ep.state.done(f"mix:{lang}", fp, credits=credits, music=pick["name"])
        self.rep.ok(f"Mixed: voice + music + {len(events)} sound(s), loudness -14 LUFS")
        self.rep.record("ok", "Music & sound", pick["name"])
        return mix_path, credits, pick["name"]

    # ------------------------------------------------------------------ final video
    def final_videos(self, plan: dict) -> list[Path]:
        sc = self.script
        outs = []
        jobs = [(lang, fmt) for lang in self.opts.languages for fmt in self.opts.formats]
        for j, (lang, fmt) in enumerate(jobs):
            base = 0.4 + 0.5 * j / len(jobs)
            span = 0.5 / len(jobs)
            self.rep.check_stop()
            tl = self.timeline(lang)
            label = f"{fmt.replace('x', ':')}, {'Farsi' if lang == 'fa' else 'English'}"
            with self.rep.timed(f"🎬 3D render ({label})"):
                clips = self.render_clips(lang, fmt, tl, plan, progress=(base, base + span * 0.85))
            with self.rep.timed(f"🎵 Music & sound ({'Farsi' if lang == 'fa' else 'English'})"):
                mix_path, credits, music_name = self.audio_mix(lang, tl, plan)
            out = self.ep.video_path(lang, fmt)
            fp = fingerprint([file_sig(c) for c in clips], file_sig(mix_path))
            key = f"video:{lang}:{fmt}"
            if not self.ep.state.fresh(key, fp, [out]):
                title = sc.get("title", "")
                with self.rep.timed(f"🔗 Join, no re-encoding ({label})"):
                    render.mux(clips, mix_path, out, tl["total"], title)
                self.ep.state.done(key, fp, credits=credits, music=music_name)
                self.rep.ok(f"{out.name} ({_mmss(tl['total'])} video, {len(clips)} clips joined without re-encoding)")
            outs.append(out)
            self.rep.progress(base + span)
        self.rep.record("ok", "Final video", f"{len(outs)} file(s)")
        return outs

    def thumbnails_and_text(self, plan: dict) -> dict:
        sc = self.script
        self.rep.step("🖼️ Thumbnail, titles, description, hashtags")
        thumbs = []
        best = max(range(len(plan["scenes"])), key=lambda i: len(plan["scenes"][i]["actions"])
                   + 2 * len(plan["scenes"][i]["labels"]) - (3 if i == 0 else 0)) if plan.get("scenes") else 0
        for lang in self.opts.languages:
            tl = read_json(self.ep.audio_dir(lang) / "timeline.json", None)
            if not tl:
                continue
            for fmt in self.opts.formats:
                try:
                    from .world import video  # noqa: PLC0415
                    from .world.labels import LabelMaker  # noqa: PLC0415
                    from .world.scene import World  # noqa: PLC0415

                    size = (1280, 720) if fmt == "16x9" else (1080, 1920)
                    renderer, rsize, _ = video.make_renderer(size)
                    world = World(plan, tl, rsize, lang)
                    try:
                        world.upload(renderer)
                        s = world.scenes[best]
                        still = self.ep.dir / "stills" / f"thumb_{fmt}_{lang}.jpg"
                        video.render_still(world, renderer, LabelMaker((renderer.W, renderer.H), lang),
                                           s["start"] + s["dur"] * 0.7, still)
                    finally:
                        renderer.release()
                    out = self.ep.export_dir / f"thumbnail_{lang}_{fmt}.jpg"
                    publish.make_thumbnail(still, sc.get("thumbnail_text", ""), lang, size, out, badge=f"EP {self.ep.number}")
                    thumbs.append(out)
                except Exception as exc:  # noqa: BLE001 - a thumbnail must never stop the video
                    self.rep.warn(f"No thumbnail this time ({type(exc).__name__}). The video is fine.")
        credits, music_name = [], ""
        for key in self.ep.state.keys("mix:"):
            info = self.ep.state.info(key)
            credits += [c for c in info.get("credits", []) if c not in credits]
            music_name = info.get("music", music_name)
        cams = [(s.get("camera") or {}).get("move", "") for s in plan.get("scenes", [])]
        warnings = publish.variation_warnings(self.series, self.ep, sc, music_name, cams)
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
        self.series.remember_episode(self.ep.number, title=sc.get("title", ""), summary=sc.get("summary", ""),
                                     cliffhanger=sc.get("cliffhanger", ""), music=music_name,
                                     cameras=cams)
        self.rep.ok("metadata.md is ready in the export folder")
        self.rep.record("ok", "Thumbnail & text", ", ".join({m["provider"] for m in meta["languages"].values()}))
        return {"thumbnails": thumbs, "metadata": meta}

    # ------------------------------------------------------------------ all together
    def make_video(self, final: bool = True) -> dict:
        """Everything after the script. The voiceover is made at the same time as the scene plan."""
        import concurrent.futures  # noqa: PLC0415

        rep = self.rep
        rep.timings.clear()
        with Timer() as total:
            rep.progress(0.03, "Plan + voice")
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                t_voice = time.time()
                voice_job = pool.submit(self.all_voices)
                try:
                    with rep.timed("🧭 Scene plan"):
                        plan = self.scene_plan()
                finally:
                    voice_job.result()
                with rep.timed_lock():
                    rep.timings.append(("🗣️ Voice (made at the same time)", time.time() - t_voice))
            if self.opts.quality_check and QUALITY_CHECK_READY:
                with rep.timed("🔍 Quality check"):
                    plan = self.quality_check(plan)
            videos = self.final_videos(plan)
            with rep.timed("🧐 Self-review"):
                plan, videos = self.self_review(plan, videos)
            rep.progress(0.95, "Thumbnail")
            with rep.timed("🖼️ Thumbnail & text"):
                extra = self.thumbnails_and_text(plan)
        prof = config.gpu_profile()
        units = round(total.seconds / 3600 * prof.cu_per_hour, 2)
        report = [(n, round(sec, 1)) for n, sec in rep.timings if sec >= 0.05]
        rep.info("")
        rep.info("⏱ Timing report:")
        for line in rep.timing_report(total.seconds):
            rep.info("   " + line)
        result = {"videos": [str(v) for v in videos], "thumbnails": [str(t) for t in extra["thumbnails"]],
                  "metadata": str(self.ep.export_dir / "metadata.md"), "minutes": round(total.seconds / 60, 1),
                  "gpu": prof.name, "units": units, "length": self.opts.length, "timings": report}
        write_json(self.ep.export_dir / "result.json", result)
        log_video_usage(self.series.name, self.ep.number, self.opts.length, prof.name, total.seconds, units)
        msg = (f"Done in {total.label} on {prof.name} (≈{units} compute units). "
               f"Your videos are in Google Drive: {self.ep.export_dir}")
        if final:
            rep.done(result, msg)
        else:
            rep.ok(msg)
        return result

    def quality_check(self, plan: dict) -> dict:
        """🔍 Before rendering: one still per shot, local checks (subject in frame, camera not inside a wall, labels
        on screen and apart, nothing empty) and, with a free Gemini key, Gemini vision. Broken shots are fixed."""
        from .world import checker, video  # noqa: PLC0415
        from .world.labels import LabelMaker  # noqa: PLC0415
        from .world.scene import World  # noqa: PLC0415

        lang, fmt = self.opts.languages[0], self.opts.formats[0]
        tl = self.timeline(lang)
        fp = fingerprint(plan, tl, fmt, "qc-1", bool(config.secret("GEMINI_API_KEY")))
        if self.ep.state.fresh("qc", fp):
            return plan
        self.rep.step("🔍 Quality check (one still per shot)")
        size = self.out_size(fmt)
        small = (size[0] // 3 // 2 * 2, size[1] // 3 // 2 * 2)  # small stills are enough to judge a shot
        renderer = None
        try:
            renderer, rsize, _ = video.make_renderer(small)
            labels = LabelMaker((renderer.W, renderer.H), lang)
            texts = [s["narration"] for s in self.script["scenes"]]

            def make_world(p):
                w = World(p, tl, (renderer.W, renderer.H), lang)
                w.upload(renderer)
                w.label_tex = labels
                return w

            def still(w, i):
                sc = w.scenes[i]
                return renderer.render(w.frame(sc["start"] + sc["dur"] * 0.6, labels))

            with Timer() as t:
                new, report, _ = checker.check(plan, make_world, still, texts, self.rep)
                for note in make_world(new).notes[:8]:  # how things were connected and grounded
                    self.rep.info("🔗 " + note)
        except Exception as exc:  # noqa: BLE001  (never stop a video because the check broke)
            from .messages import StopRequested  # noqa: PLC0415

            if isinstance(exc, StopRequested):
                raise
            self.rep.warn(f"The quality check didn't work ({type(exc).__name__}), so the plan is used as it is.")
            return plan
        finally:
            if renderer is not None:
                renderer.release()
        if report:
            new = self.save_plan(new)
            for line in report[:12]:
                self.rep.info("🔧 " + line)
        ai = "with Gemini vision" if config.secret("GEMINI_API_KEY") else "local checks (add a free GEMINI_API_KEY for Gemini vision)"
        self.rep.ok(f"{len(plan['scenes'])} shots checked, {len(report)} fixed ({ai}, {t.label})")
        self.rep.record("ok" if not report else "warn", "Quality check", f"{len(report)} fixed")
        self.ep.state.done("qc", fingerprint(new, tl, fmt, "qc-1", bool(config.secret("GEMINI_API_KEY"))))
        return new

    def contact_sheet(self, video: Path, tl: dict, cols: int = 7) -> tuple[Path, list]:
        """One frame per shot (60 % into it) + the ending, from the finished video → export/contact_sheet.jpg."""
        import subprocess  # noqa: PLC0415

        import numpy as np  # noqa: PLC0415
        from PIL import Image, ImageDraw  # noqa: PLC0415

        times = [s["start"] + s["dur"] * 0.6 for s in tl["scenes"]] + [tl["end"]["start"] + tl["end"]["dur"] * 0.55]
        frames = []
        for t in times:
            p = subprocess.run([config.ffmpeg_path(), "-v", "error", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
                                "-vf", "scale=270:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
            w = 270
            h = len(p.stdout) // (w * 3)
            frames.append(np.frombuffer(p.stdout[: w * h * 3], np.uint8).reshape(h, w, 3) if h else
                          np.zeros((480, 270, 3), np.uint8))
        h = max(f.shape[0] for f in frames)
        rows = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 270, rows * h), (8, 20, 24))
        draw = ImageDraw.Draw(sheet)
        for k, f in enumerate(frames):
            x, y = (k % cols) * 270, (k // cols) * h
            sheet.paste(Image.fromarray(f), (x, y))
            draw.text((x + 6, y + 4), f"{k + 1}" if k < len(tl["scenes"]) else "end", fill=(255, 255, 255))
        out = self.ep.export_dir / "contact_sheet.jpg"
        sheet.save(out, quality=85)
        return out, frames

    def self_review(self, plan: dict, videos: list) -> tuple[dict, list]:
        """🧐 After rendering: a contact sheet of every shot, checked on the real pixels (and by Gemini vision with a
        free key). Bad shots are fixed in the plan and only those are rendered again (one round)."""
        from .world import checker, fixer  # noqa: PLC0415

        if not videos:
            return plan, videos
        lang = self.opts.languages[0]
        tl = read_json(self.ep.audio_dir(lang) / "timeline.json", None)
        if not tl:
            return plan, videos
        self.rep.step("🧐 Self-review (a contact sheet of every shot)")
        sheet, frames = self.contact_sheet(Path(videos[0]), tl)
        texts = [s["narration"] for s in self.script["scenes"]]
        n = len(texts)
        fp = fingerprint(file_sig(Path(videos[0])), "review-1")
        if self.ep.state.fresh("review", fp):
            self.rep.ok(f"Contact sheet: {sheet.name} (already reviewed)")
            return plan, videos
        bad: dict[int, list] = {}
        for i in range(n):
            if checker.content_fraction(frames[i]) < 0.3:
                bad.setdefault(i, []).append("mostly_empty")
        from .world.scene import World  # noqa: PLC0415

        world = World(plan, tl, (270, 480), lang)  # the logic check: connected, touching, nothing in the way
        for i in range(n):
            logic = checker.logic_problems(world, i)
            if logic:
                bad.setdefault(i, []).extend(logic)
                self.rep.info(f"🧩 Shot {i + 1}: " + ", ".join(x.replace("_", " ") for x in logic))
        seen = checker.ask_vision(frames[:n], texts, self.rep)  # {} without a free Gemini key
        new = json.loads(json.dumps(plan))
        report = []
        for i, probs in bad.items():
            done = checker.fix_local(new, i, probs)
            report += [f"Shot {i + 1}: {', '.join(done)}"] if done else []
        for i, info in seen.items():
            try:
                new, changes, _ = fixer.fix(new, i, info["fix"], texts[i], self.rep)
                report.append(f"Shot {i + 1} (Gemini: {info['problem'] or 'looked wrong'}): {', '.join(changes)}")
            except ValueError:
                report.append(f"Shot {i + 1}: Gemini saw a problem ({info['problem']}); check it on step 2.")
        if report and new != plan:
            for line in report[:10]:
                self.rep.info("🔧 " + line)
            plan = self.save_plan(new)
            videos = self.final_videos(plan)  # only the fixed shots are rendered again
            sheet, _ = self.contact_sheet(Path(videos[0]), tl)
        ai = "Gemini vision + pixel checks" if config.secret("GEMINI_API_KEY") else "pixel checks"
        self.rep.ok(f"{n} shots reviewed ({ai}), {len(report)} fixed. Contact sheet: {sheet.name}")
        self.ep.state.done("review", fingerprint(file_sig(Path(videos[0])), "review-1"))
        return plan, videos

    def fix_scene(self, i: int, instruction: str) -> dict:
        """🔧 Change one shot by typing what you want. Only the shots that show the change are rendered again."""
        from .world import fixer  # noqa: PLC0415

        rep = self.rep
        plan = self.ep.load_plan()
        if not plan:
            raise FriendlyError("There is no scene plan yet.", "Press 🧭 Plan first (or 🚀 Make the video) first.")
        if not 0 <= i < len(plan["scenes"]):
            raise FriendlyError(f"There is no shot {i + 1}.", f"Pick a shot from 1 to {len(plan['scenes'])}.")
        instruction = (instruction or "").strip()
        if not instruction:
            raise FriendlyError("Type what to change first.", "For example: make the tank bigger.")
        text = self.script["scenes"][i]["narration"]
        rep.step(f"🔧 Fixing shot {i + 1}: “{instruction}”")
        try:
            new, changes, provider = fixer.fix(plan, i, instruction, text, rep)
        except ValueError:
            raise FriendlyError("I couldn't understand that change without AI.",
                                "Try: bigger · smaller · closer · further · from above · show the gas flowing · cut it open"
                                " · spin · light up · add a pump · label \"38 °C\" · remove labels. A free GEMINI_API_KEY "
                                "understands anything.") from None
        plan = self.save_plan(new)
        rep.ok(f"Shot {i + 1} changed ({provider}): " + "; ".join(changes))
        lang, fmt = self.opts.languages[0], self.opts.formats[0]
        tl = read_json(self.ep.audio_dir(lang) / "timeline.json", None)
        made_video = any(k.startswith("clip:") for k in self.ep.state.data.get("steps", {}))
        if made_video:  # re-render only the shots that changed, then join again (fast)
            return self.make_video()
        if tl:
            self.stills(fmt, lang, tl, plan, only=[i])
            rep.ok(f"New still frame for shot {i + 1}")
        rep.done({"episode": self.ep.number}, f"Shot {i + 1} is fixed. Press 🚀 when all shots look good.")
        return {"episode": self.ep.number, "changes": changes}


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


def auto_series(opts: EpisodeOptions, text: str = "") -> Series:
    """No series picked: one per video format ("How it works"), so a new topic never lands in an old story series.
    A story gets its own series named after its topic/title. Voices are copied from the series used last."""
    topic = (opts.idea or "").split("=====")[0].strip()
    if not topic:
        topic = (paste.parse_lines(text or opts.script_text or "").get("title") or "").strip()
    key = formats.resolve(opts.video_format, topic)
    name = (topic[:60] or "My story") if key == "story" else formats.get(key)["label"]
    last = read_json(config.get().root / "app.json", {}) or {}
    s = Series.create(name)
    if not s.data.get("voices") and last.get("series") and last["series"] != s.slug:
        old = Series(last["series"])
        if old.path.exists() and old.data.get("voices"):
            s.data["voices"] = dict(old.data["voices"])
            s.save()
    return s


def episode_number(series: Series, number: int | None, opts: EpisodeOptions) -> int | None:
    """The episode to make. A number that already holds a DIFFERENT video is never overwritten: the next free one."""
    if not number or number not in series.episode_numbers():
        return number or None
    old = series.episode(number).load_options()
    if (opts.script_text or "").strip():
        same = (old.script_text or "").strip() == opts.script_text.strip()
    else:  # a topic: the AI writes the script
        same = bool((opts.idea or "").strip()) and (old.idea or "").strip() == opts.idea.strip()
    return number if same else None


def generate(series: Series, opts: EpisodeOptions, text: str, rep: Reporter, number: int | None = None) -> dict:
    """Everything after you press Generate: (topic → script), plan, voice, 3D render, sound, export."""
    texts = paste.split_scripts(text) if opts.source == "paste" else []
    if opts.source == "ai":
        topics = [t.strip() for t in re.split(r"\n\s*={5,}\s*\n", opts.idea or "") if t.strip()]
        if not topics:
            raise FriendlyError("Type a topic first.", "For example: how cow poop becomes electricity.")
        texts = []
        for tp in topics:
            rep.step(f"✍️ Writing the script: {tp}")
            txt, provider = script.write_from_topic(tp, opts.length, (opts.languages or ["en"])[0], opts.creator_note, rep,
                                                    opts.video_format)
            rep.ok(f"Script written by {provider}")
            texts.append(txt)
        opts.source = "paste"
    if not texts:
        raise FriendlyError("The script box is empty.", "Paste your script (or type a topic), then press Generate.")
    if len(texts) > 1:
        return run_batch(series, opts, texts, rep, number)
    ep = series.episode(number or series.next_episode_number())
    set_current_episode(series, ep)
    opts.script_text = texts[0]
    ep.save_options(opts)
    script.script_from_text(series, ep, opts, texts[0], rep)
    return Pipeline(series, ep, rep, opts).make_video()


def prepare(series: Series, opts: EpisodeOptions, text: str, rep: Reporter, number: int | None = None) -> dict:
    """🧭 Plan first: script → scene plan + voice + one still frame per shot (fast), to check the shots before rendering."""
    import concurrent.futures  # noqa: PLC0415

    if opts.source == "ai" or not (text or "").strip():
        topic = (opts.idea or "").split("=====")[0].strip()
        rep.step(f"✍️ Writing the script: {topic}")
        text, provider = script.write_from_topic(topic, opts.length, (opts.languages or ["en"])[0], opts.creator_note, rep,
                                                 opts.video_format)
        rep.ok(f"Script written by {provider}")
        opts.source = "paste"
    first = (paste.split_scripts(text) or [""])[0]
    if len(paste.split_scripts(text)) > 1:
        rep.warn("🧭 Plan first works on one script at a time: using the first one (before the first =====).")
    ep = series.episode(number or series.next_episode_number())
    set_current_episode(series, ep)
    opts.script_text = first
    ep.save_options(opts)
    script.script_from_text(series, ep, opts, first, rep)
    pipe = Pipeline(series, ep, rep, opts)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        voice_job = pool.submit(pipe.all_voices)
        try:
            plan = pipe.scene_plan()
        finally:
            voice_job.result()
    lang, fmt = opts.languages[0], opts.formats[0]
    tl = pipe.timeline(lang)
    if opts.quality_check and QUALITY_CHECK_READY:
        plan = pipe.quality_check(plan)
    rep.step("🖼️ One still frame per shot")
    with Timer() as t:
        stills = pipe.stills(fmt, lang, tl, plan)
    rep.ok(f"{len(stills)} still frames ({t.label})")
    rep.done({"episode": ep.number, "stills": [str(p) for p in stills]},
             f"The plan is ready: {len(plan['scenes'])} shots. Check them on step 2, fix any shot, then press 🚀.")
    return {"episode": ep.number}


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
        o.script_text = text
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
# Quick test: the built-in demo (or the first 3 scenes of your script), 720p
# ---------------------------------------------------------------------------


def quick_test(rep: Reporter, text: str = "", languages=("en",), length: str = "short") -> dict:
    """The first 3 scenes of your script (or of the built-in demo), 720p: checks voice, 3D render and sound."""
    from .world import examples  # noqa: PLC0415

    s = config.get()
    prof = config.gpu_profile()
    rep.step("⚡ Quick test: 3 scenes, 720p")
    rep.info(f"Computer: {s.gpu.label} → {prof.label}. Saving to: {s.root}")
    first = (paste.split_scripts(text) or [""])[0] or examples.COW_POOP_SCRIPT
    parsed = paste.parse_lines(first)
    scenes = paste.to_scenes(parsed, length)[:3]
    body = "\n".join(([f"[TITLE] {parsed['title']}"] if parsed["title"] else []) + [
        line for sc in scenes for line in [f"[SCENE] {sc['visual']}".rstrip()] + [f"{ln['speaker']}: {ln['text']}"
                                                                                 for ln in sc["lines"]]])
    series = Series.create("Quick test")
    ep_dir = series.dir / "episodes" / "ep01"
    if ep_dir.exists():
        shutil.rmtree(ep_dir, ignore_errors=True)
    series.data["episodes"] = {}
    series.save()
    ep = series.episode(1)
    opts = EpisodeOptions.from_dict({"script_text": body, "languages": list(languages) or ["en"], "length": length,
                                     "resolution": "720p", "quick_test": True, "source": "paste",
                                     "quality_check": False})
    ep.save_options(opts)
    set_current_episode(series, ep)
    script.script_from_text(series, ep, opts, body, rep)
    result = Pipeline(series, ep, rep, opts).make_video()
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
    return json.dumps({"plan": count("plan"), "voices": count("voice:"), "clips": count("clip:"),
                       "videos": count("video:")})
