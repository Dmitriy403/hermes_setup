"""Transcriber backends (live edge).

LocalWhisper shells ffmpeg + whisper.cpp; CloudWhisper calls the OpenAI
Whisper API. Both are built lazily by `build_backend`, which fails soft with
MissingDependency when a required binary/SDK is absent (Decision 18).
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Protocol

from . import core


class MissingDependency(Exception):
    """A backend's dependency (whisper-cpp/ffmpeg/openai) is unavailable."""


def ensure_model(model: str | None = None) -> Path:
    """Return the local path to the ggml model, downloading it if absent.

    Fetches `ggml-<model>.bin` into `~/.cache/hermes/whisper/` on first use.
    Downloads to a temp file in the same dir and atomically renames, so an
    interrupted fetch never leaves a half-written model in place.
    """
    dest = core.model_path(model)
    if dest.exists():
        return dest
    url = core.model_url(model)  # validates the model name
    dest.parent.mkdir(parents=True, exist_ok=True)
    import urllib.error
    import urllib.request
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as fh:
            while chunk := resp.read(1 << 20):
                fh.write(chunk)
        tmp.replace(dest)
    except (urllib.error.URLError, OSError) as exc:
        tmp.unlink(missing_ok=True)
        raise MissingDependency(
            f"failed to download whisper model from {url}: {exc} — "
            f"fetch it manually into {core.model_dir()}") from exc
    return dest


class Transcriber(Protocol):
    def transcribe(self, path: str, language: str | None) -> dict[str, Any]:
        """Return {text, language, duration_seconds}."""
        ...


def _audio_duration(path: str) -> int | None:
    ffprobe = __import__("shutil").which("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=30)
        return int(float(out.stdout.strip()))
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


class LocalWhisper:
    def __init__(self, model: str | None = None):
        self.binary = core.whisper_binary()
        self.ffmpeg = core.ffmpeg_binary()
        if not self.binary:
            raise MissingDependency("whisper-cpp not found — `brew install whisper-cpp`")
        if not self.ffmpeg:
            raise MissingDependency("ffmpeg not found — `brew install ffmpeg`")
        self.model = str(ensure_model(model))

    def transcribe(self, path: str, language: str | None) -> dict[str, Any]:
        with tempfile.TemporaryDirectory() as d:
            wav = str(Path(d) / "a.wav")
            subprocess.run(core.ffmpeg_args(path, wav), capture_output=True, check=True, timeout=300)
            out_prefix = str(Path(d) / "out")
            subprocess.run(core.whisper_args(self.binary, self.model, wav, language, out_prefix),
                           capture_output=True, check=True, timeout=600)
            parsed = core.parse_whisper_json(Path(out_prefix + ".json").read_text())
        return {"text": parsed["text"], "language": parsed["language"] or language,
                "duration_seconds": _audio_duration(path)}


class CloudWhisper:
    def __init__(self):
        if not os.environ.get("OPENAI_API_KEY"):
            raise MissingDependency("OPENAI_API_KEY not set")
        try:
            import openai  # noqa: F401
        except ImportError as exc:
            raise MissingDependency("openai SDK not installed — `pip install openai`") from exc

    def transcribe(self, path: str, language: str | None) -> dict[str, Any]:
        import openai
        client = openai.OpenAI()
        with open(path, "rb") as fh:
            kwargs = {"model": "whisper-1", "file": fh}
            if language:
                kwargs["language"] = language
            resp = client.audio.transcriptions.create(**kwargs)
        return {"text": resp.text, "language": language, "duration_seconds": _audio_duration(path)}


def build_backend(name: str, model: str | None = None) -> Transcriber:
    if name == "local":
        return LocalWhisper(model)
    if name == "cloud":
        return CloudWhisper()
    raise MissingDependency(f"unknown backend: {name}")
