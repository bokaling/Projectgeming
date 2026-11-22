"""T4 test round 5: model files on Google Drive, voices, keys, word count, quiet log."""
import json
import struct
import warnings

import numpy as np
import pytest

from storyforge import config, doctor, models, paste, pipeline, project
from storyforge.audio import tts
from storyforge.messages import Reporter


def _safetensors(path, n_bytes=16):
    header = json.dumps({"w": {"dtype": "F32", "shape": [n_bytes // 4], "data_offsets": [0, n_bytes]}}).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(struct.pack("<Q", len(header)) + header + b"\1" * n_bytes)


REPO_FILES = ["model_index.json", "transformer/diffusion_pytorch_model.safetensors", "vae/diffusion_pytorch_model.safetensors",
              "text_encoder/model.safetensors"]


def _old_drive_cache(cache, repo):
    """The old Hugging Face cache after a Colab reconnect: blobs are fine, every snapshot 'file' is a 79-byte stub."""
    base = cache / ("models--" + repo.replace("/", "--"))
    blobs, snap = base / "blobs", base / "snapshots" / ("c" * 40)
    blobs.mkdir(parents=True)
    for k, rel in enumerate(REPO_FILES):
        sha = f"{k:x}" * 64
        blob = blobs / sha[:64]
        if rel.endswith(".safetensors"):
            _safetensors(blob, 64)
        else:
            blob.write_text('{"_class_name": "Flux2KleinPipeline"}')
        stub = snap / rel
        stub.parent.mkdir(parents=True, exist_ok=True)
        depth = rel.count("/") + 2
        stub.write_text("../" * depth + "blobs/" + sha[:64])  # what Google Drive keeps instead of the symlink
    return snap


@pytest.fixture()
def fake_hub(monkeypatch):
    import huggingface_hub

    calls = {"snapshot": 0, "files": []}

    def snapshot_download(repo, local_dir=None, allow_patterns=None, ignore_patterns=None, token=None, **kw):
        calls["snapshot"] += 1
        from pathlib import Path

        for rel in REPO_FILES:  # only what is missing is "downloaded"
            p = Path(local_dir) / rel
            if not p.is_file():
                calls["files"].append(rel)
                _safetensors(p, 64) if rel.endswith(".safetensors") else p.write_text("{}")
        return local_dir

    def hf_hub_download(repo, filename, local_dir=None, force_download=False, token=None, **kw):
        from pathlib import Path

        calls["files"].append(filename)
        p = Path(local_dir) / filename
        _safetensors(p, 64)
        return str(p)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", snapshot_download)
    monkeypatch.setattr(huggingface_hub, "hf_hub_download", hf_hub_download)
    monkeypatch.setattr(models, "_expected_sizes", lambda repo: {})
    monkeypatch.setattr(models, "_ignore_patterns", lambda key, repo: None)  # no network in tests
    return calls


def test_79_byte_stub_is_a_link_not_a_broken_file(tmp_path):
    blob = tmp_path / "blobs" / ("a" * 64)
    _safetensors(blob, 64)
    stub = tmp_path / "snap" / "text_encoder" / "model.safetensors"
    stub.parent.mkdir(parents=True)
    stub.write_text("../../blobs/" + "a" * 64)
    assert stub.stat().st_size < 100
    assert models.stub_target(stub) == blob.resolve()
    assert models.real_file(stub) == blob.resolve()
    assert models.safetensors_problem(stub) == ""  # the real blob behind it is fine
    assert "link" in models.file_problem(stub)  # but loaders need a real file there
    link = tmp_path / "snap" / "vae.safetensors"
    link.symlink_to(blob)
    assert models.safetensors_problem(link, expected_size=blob.stat().st_size) == ""  # follows the symlink


def test_old_drive_cache_is_moved_not_downloaded_and_next_time_no_internet(sf_root, fake_hub):
    repo = config.MODELS["image"]
    cache = config.get().big_model_cache
    _old_drive_cache(cache, repo)
    rep = Reporter(echo=False)
    folder = models.ensure_model("image", rep)
    assert fake_hub["files"] == []  # nothing downloaded again
    from pathlib import Path

    for rel in REPO_FILES:
        f = Path(folder) / rel
        assert f.is_file() and not f.is_symlink() and f.stat().st_size > 100 or rel.endswith(".json")
    assert "Moved 4 model file(s)" in rep.text() and "broken" not in rep.text()
    assert not (cache / ("models--" + repo.replace("/", "--"))).exists()  # old cache removed
    # next session: verified files are used without asking the internet at all
    fake_hub["snapshot"] = 0
    assert models.ensure_model("image", Reporter(echo=False)) == folder
    assert fake_hub["snapshot"] == 0 and fake_hub["files"] == []


def test_only_a_really_broken_file_is_downloaded_again(sf_root, fake_hub):
    from pathlib import Path

    folder = Path(models.ensure_model("image"))
    fake_hub["files"].clear()
    bad = folder / "vae" / "diffusion_pytorch_model.safetensors"
    bad.write_bytes(bad.read_bytes()[:-20])  # cut off (e.g. a disconnect while copying)
    rep = Reporter(echo=False)
    models.ensure_model("image", rep)
    assert fake_hub["files"] == ["vae/diffusion_pytorch_model.safetensors"]
    assert "Repaired 1" in rep.text() and models.file_problem(bad) == ""


def test_hf_token_is_used(sf_root, monkeypatch, fake_hub):
    import huggingface_hub

    seen = {}
    real = huggingface_hub.snapshot_download

    def spy(repo, **kw):
        seen["token"] = kw.get("token")
        return real(repo, **kw)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", spy)
    monkeypatch.setenv("HF_TOKEN", "hf_test_token")
    models.ensure_model("depth")
    assert seen["token"] == "hf_test_token"


# ---------------------------------------------------------------- voices
def test_real_kokoro_error_is_shown_and_backup_keeps_gender(sf_root, monkeypatch):
    def broken_kokoro(text, voice, speed=1.0):
        raise RuntimeError("PytorchStreamReader failed reading zip archive")

    monkeypatch.setattr(tts, "kokoro", broken_kokoro)
    monkeypatch.setattr(tts, "edge", lambda text, voice, speed=1.0: (np.ones(tts.SR, np.float32) * 0.1, []))
    rep = Reporter(echo=False)
    eng, voice = tts.resolve("en", {"engine": "kokoro", "voice": "am_fenrir", "speed": 1.1}, rep)
    assert eng == "edge" and tts.voice_gender(eng, voice) == "male"
    assert "Kokoro (am_fenrir) didn't work: RuntimeError: PytorchStreamReader failed" in rep.text()


def test_edge_retries_each_piece_3_times_with_short_waits(sf_root, monkeypatch, tmp_path):
    waits, tries = [], {"n": 0}
    monkeypatch.setattr(tts.time, "sleep", lambda s: waits.append(s))

    def flaky_edge(text, voice, speed=1.0):
        tries["n"] += 1
        if tries["n"] < 3:
            raise RuntimeError("NoAudioReceived")
        return np.ones(tts.SR, np.float32) * 0.1, []

    monkeypatch.setattr(tts, "edge", flaky_edge)
    tts._resolved[("en", "edge", "en-US-AndrewMultilingualNeural")] = ("edge", "en-US-AndrewMultilingualNeural")
    rep = Reporter(echo=False)
    tts.speak("It works.", "en", {"engine": "edge", "voice": "en-US-AndrewMultilingualNeural"}, tmp_path / "a.wav", rep)
    assert tries["n"] == 3 and waits == [2.0, 4.0] and "try 2/3" in rep.text()


def test_voice_that_breaks_halfway_switches_the_whole_video(offline, monkeypatch):
    monkeypatch.setattr(tts.time, "sleep", lambda s: None)
    count = {"n": 0}

    def edge_then_dies(text, voice, speed=1.0):
        count["n"] += 1
        if count["n"] > 3:
            raise RuntimeError("503 Service Unavailable")
        return np.ones(int(tts.SR * 0.6), np.float32) * 0.1, []

    monkeypatch.setattr(tts, "edge", edge_then_dies)
    series = project.Series.create("Voices")
    series.data["voices"] = {"en": "edge:en-US-AndrewMultilingualNeural"}
    series.save()
    ep = series.episode(1)
    opts = project.EpisodeOptions(length="short", resolution="480p")
    from storyforge import script

    script.script_from_text(series, ep, opts, "NARRATOR: One. Two.\n[SCENE] x\nNARRATOR: Three.\n[SCENE] y\n"
                            "NARRATOR: Four.", Reporter(echo=False))
    rep = Reporter(echo=False)
    pipeline.Pipeline(series, ep, rep, opts).voices("en")
    text = rep.text(200)
    assert "Switching the whole video to the backup voice" in text
    engines = {project.read_json(ep.audio_dir("en") / f"{s['id']}.json")["engine"] for s in ep.load_script()["scenes"]}
    assert len(engines) == 1 and "Edge" not in next(iter(engines))  # one voice for the whole video


def test_punctuation_only_pieces_are_skipped(sf_root, monkeypatch, tmp_path):
    said = []
    monkeypatch.setattr(tts, "kokoro", lambda text, voice, speed=1.0: (said.append(text) or (np.ones(tts.SR // 2, np.float32), [])))
    choice = {"engine": "kokoro", "voice": "am_fenrir"}
    tts.speak_lines([("Hello there.", choice), ("…", choice, 0.4), ("—", choice)], "en", tmp_path / "x.wav")
    assert said[-1] == "Hello there." and "…" not in said


# ---------------------------------------------------------------- keys
def test_key_report_says_what_each_key_turns_on(monkeypatch):
    for name in config.SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setitem(config._SECRET_STATUS, "HF_TOKEN", "no_access")
    rep = {n: (st, what) for n, st, what in config.key_report()}
    assert rep["GEMINI_API_KEY"][0] == "found" and "Improve script" in rep["GEMINI_API_KEY"][1]
    assert rep["HF_TOKEN"][0] == "no_access" and "downloads" in rep["HF_TOKEN"][1]
    lines = "\n".join(config.key_lines())
    assert "✅ GEMINI_API_KEY → Gemini" in lines and "Notebook access' is OFF" in lines
    assert "x" not in lines.replace("x", "", 0).split("→")[0].replace("GEMINI_API_KEY", "")  # never prints a key


def test_gemini_key_is_first_and_improve_prefers_the_bigger_free_model(monkeypatch):
    from storyforge import llm

    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert [n for n, _ in llm.providers(allow_local=False)][0] == "Gemini"
    monkeypatch.setitem(llm._model_cache, "gemini", ["gemini-3-flash-lite", "gemini-3-flash"])
    used = []
    monkeypatch.setattr(llm, "_openai_chat", lambda base, key, model, *a: used.append(model) or '{"ok": 1}')
    dict(llm.providers(allow_local=False, strong=True))["Gemini"]([], True, 0.5, 100)
    dict(llm.providers(allow_local=False))["Gemini"]([], True, 0.5, 100)
    assert used == ["gemini-3-flash", "gemini-3-flash-lite"]


# ---------------------------------------------------------------- word count
SCRIPT = '''[TITLE] Count me
[CHARACTER] MIRA: woman
NARRATOR: "Don't open it," she whispered—then stopped.
MIRA (whispering): Who's there?
**NARRATOR:** It was 3:15 a.m. when the radio... spoke.
"I know your name," said the voice.
Dr. Shaw: Run!
Dr. Shaw: Now, Mira!
NARRATOR: Wait...what?
'''


def test_word_count_counts_every_spoken_line():
    assert paste.count_words("whispered—then Wait...what don't 3:15 …") == 6
    parsed = paste.parse_lines(SCRIPT)
    lines = [ln for b in parsed["blocks"] for ln in b["lines"]]
    assert [ln["speaker"] for ln in lines] == ["NARRATOR", "MIRA", "NARRATOR", "NARRATOR", "DR. SHAW", "DR. SHAW",
                                              "NARRATOR"]
    assert lines[1]["text"] == "Who's there?" and lines[2]["text"].startswith("It was 3:15")  # labels not read aloud
    spoken = "Don't open it she whispered then stopped Who's there It was 3:15 a.m. when the radio spoke " \
             "I know your name said the voice Run Now Mira Wait what"
    r = doctor.score(SCRIPT)
    assert r.words == len(spoken.split()) == 29 and r.lines == 7
    assert "29 spoken words in 7 lines" in doctor.report_html(r)
    assert "29 words" in paste.length_warning(SCRIPT, "short")


# ---------------------------------------------------------------- quiet log
def test_harmless_warnings_are_hidden(sf_root):
    config.quiet_warnings()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("default")
        config.quiet_warnings()
        warnings.warn("old thing", FutureWarning)
        warnings.warn("torchao: Skipping import of cpp extensions", UserWarning)
        warnings.warn_explicit("TypedStorage is deprecated", UserWarning, "x.py", 1, module="torch.storage")
        warnings.warn("a real problem", RuntimeWarning)
    assert [str(w.message) for w in caught] == ["a real problem"]


def test_flux_single_file_is_skipped_only_if_transformer_folder_exists(monkeypatch):
    import huggingface_hub

    class Api:
        def __init__(self, token=None):
            pass

        def list_repo_files(self, repo):
            return self.files

    Api.files = ["flux-2-klein-4b.safetensors", "transformer/diffusion_pytorch_model.safetensors", "vae/x.safetensors"]
    monkeypatch.setattr(huggingface_hub, "HfApi", Api)
    assert "flux-2-klein-4b.safetensors" in models._ignore_patterns("image", "r")
    Api.files = ["flux-2-klein-4b.safetensors", "vae/x.safetensors"]  # no transformer folder: keep it
    assert "flux-2-klein-4b.safetensors" not in (models._ignore_patterns("image", "r") or [])
