"""Tests for voice — backend selection (incl. the cloud-off PRIVACY guarantee),
argv construction, whisper-json parsing, and orchestration with fake backends.

No whisper/ffmpeg/openai needed (live edge).

    PYTHONPATH=src python3 tests/test_voice.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from voice import core  # noqa: E402


# ---- PRIVACY: backend selection ----

def test_cloud_off_is_local_only():
    # default / off / unset → local only, regardless of key
    assert core.select_backends(None, False, False) == ["local"]
    assert core.select_backends("off", True, True) == ["local"]


def test_cloud_requires_all_three_opt_ins():
    # missing any of: fallback flag, key, mode → no cloud
    assert core.select_backends("primary", False, True) == ["local"]   # no flag
    assert core.select_backends("primary", True, False) == ["local"]   # no key
    assert core.select_backends("fallback", False, False) == ["local"]


def test_cloud_enabled_ordering():
    assert core.select_backends("primary", True, True) == ["cloud", "local"]
    assert core.select_backends("fallback", True, True) == ["local", "cloud"]


def test_cloud_allowed_helper():
    assert core.cloud_allowed("off", True, True) is False
    assert core.cloud_allowed("fallback", True, True) is True


# ---- format support ----

def test_supported_formats():
    assert core.is_supported("/tmp/v.ogg")
    assert core.is_supported("/tmp/v.M4A")
    assert not core.is_supported("/tmp/v.txt")


# ---- argv ----

def test_ffmpeg_args_16k_mono():
    a = core.ffmpeg_args("/in.ogg", "/out.wav")
    assert a[:1] == ["ffmpeg"] and "-ar" in a and "16000" in a and "-ac" in a and "1" in a
    assert a[-1] == "/out.wav"


def test_whisper_args_with_and_without_language():
    a = core.whisper_args("/bin/whisper", "/m.bin", "/a.wav", "ru", "/out")
    assert "-l" in a and "ru" in a and "-oj" in a and "/m.bin" in a
    b = core.whisper_args("/bin/whisper", "/m.bin", "/a.wav", None, "/out")
    assert "-l" not in b


def test_model_path_default_and_override():
    assert core.model_path().name == "ggml-base.bin"
    assert core.model_path("medium").name == "ggml-medium.bin"


def test_model_url_default_and_override():
    assert core.model_url().endswith("/ggml-base.bin")
    assert core.model_url("large-v3").endswith("/ggml-large-v3.bin")


def test_model_url_rejects_unknown_name():
    # guards against env-supplied names escaping the fixed repo path
    for bad in ("../etc/passwd", "huge", "base.bin"):
        try:
            core.model_url(bad)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {bad!r}")


def test_ensure_model_skips_download_when_present(tmp_path=None):
    import tempfile
    from voice import backends
    with tempfile.TemporaryDirectory() as d:
        from pathlib import Path as _P
        present = _P(d) / "ggml-base.bin"
        present.write_bytes(b"fake-model")
        orig = core.model_dir
        core.model_dir = lambda: _P(d)  # type: ignore[assignment]
        try:
            # would raise on any network attempt; file present means no fetch
            assert backends.ensure_model() == present
        finally:
            core.model_dir = orig  # type: ignore[assignment]


# ---- whisper json parse ----

def test_parse_whisper_json():
    raw = json.dumps({
        "result": {"language": "ru"},
        "transcription": [{"text": " Привет"}, {"text": " мир"}],
    })
    out = core.parse_whisper_json(raw)
    assert out["language"] == "ru"
    assert out["text"] == "Привет мир"


# ---- orchestration (fake backends) ----

class FakeBackend:
    def __init__(self, text, lang):
        self.text, self.lang = text, lang
    def transcribe(self, path, language):
        return {"text": self.text, "language": language or self.lang, "duration_seconds": 3}


def test_run_transcription_success():
    r = core.run_transcription("/tmp/v.ogg", "ru", ["local"],
                               builder=lambda n: FakeBackend("привет", "ru"))
    assert r["ok"] and r["backend"] == "local" and r["text"] == "привет" and r["language"] == "ru"


def test_run_transcription_unsupported_format():
    r = core.run_transcription("/tmp/v.txt", None, ["local"], builder=lambda n: FakeBackend("x", "en"))
    assert r["ok"] is False and r["error"] == "unsupported_format"


def test_run_transcription_falls_through_to_cloud():
    def builder(name):
        if name == "local":
            raise RuntimeError("whisper-cpp missing")
        return FakeBackend("from cloud", "en")
    r = core.run_transcription("/tmp/v.ogg", None, ["local", "cloud"], builder=builder)
    assert r["ok"] and r["backend"] == "cloud" and r["text"] == "from cloud"


def test_run_transcription_all_fail():
    def builder(name):
        raise RuntimeError(f"{name} unavailable")
    r = core.run_transcription("/tmp/v.ogg", None, ["local"], builder=builder)
    assert r["ok"] is False and r["error"] == "transcription_failed" and "local unavailable" in r["detail"]


def _run_standalone() -> int:
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  PASS {fn.__name__}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {fn.__name__}: {exc}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run_standalone())
