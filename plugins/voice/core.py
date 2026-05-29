"""Pure core for voice — no whisper/ffmpeg/openai, no network.

Holds the privacy boundary (backend selection) and the deterministic plumbing
(ffmpeg/whisper argv, model paths, whisper-json parsing). Fully unit-testable.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from shutil import which
from typing import Any

SUPPORTED_FORMATS = frozenset({".ogg", ".m4a", ".mp3", ".wav", ".flac", ".opus", ".aac"})
DEFAULT_MODEL = "base"
_WHISPER_BINARIES = ("whisper-cli", "whisper-cpp")

# whisper.cpp ggml models, published under ggerganov/whisper.cpp on HuggingFace.
KNOWN_MODELS = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v1", "large-v2", "large-v3", "large-v3-turbo",
})
_MODEL_BASE_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main"


# ---- privacy boundary: which backends, in what order ----


def select_backends(cloud_mode: str | None, cloud_fallback: bool, has_openai_key: bool) -> list[str]:
    """Decide the ordered backend list. The cloud backend is included ONLY when
    explicitly opted in (VOICE_CLOUD_FALLBACK=1 + OPENAI_API_KEY + mode in
    {primary,fallback}). Otherwise local-only — no audio leaves the machine.
    """
    mode = (cloud_mode or "off").lower()
    cloud_enabled = cloud_fallback and has_openai_key and mode in ("primary", "fallback")
    if not cloud_enabled:
        return ["local"]
    if mode == "primary":
        return ["cloud", "local"]
    return ["local", "cloud"]  # fallback: local first, cloud if local fails


def cloud_allowed(cloud_mode: str | None, cloud_fallback: bool, has_openai_key: bool) -> bool:
    return "cloud" in select_backends(cloud_mode, cloud_fallback, has_openai_key)


# ---- format support ----


def is_supported(path: str) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_FORMATS


# ---- dependency discovery (fail-soft per Decision 18) ----


def whisper_binary() -> str | None:
    for name in _WHISPER_BINARIES:
        found = which(name)
        if found:
            return found
    return None


def ffmpeg_binary() -> str | None:
    return which("ffmpeg")


# ---- model path ----


def model_dir() -> Path:
    return Path(os.path.expanduser("~/.cache/hermes/whisper"))


def model_path(model: str | None = None) -> Path:
    return model_dir() / f"ggml-{model or DEFAULT_MODEL}.bin"


def model_url(model: str | None = None) -> str:
    """HuggingFace download URL for a ggml whisper model.

    Validates against KNOWN_MODELS so an env-supplied name can't escape the
    fixed repo path (no traversal / arbitrary URL).
    """
    name = model or DEFAULT_MODEL
    if name not in KNOWN_MODELS:
        raise ValueError(f"unknown whisper model {name!r}; expected one of {sorted(KNOWN_MODELS)}")
    return f"{_MODEL_BASE_URL}/ggml-{name}.bin"


# ---- argv construction (deterministic) ----


def ffmpeg_args(src: str, dst_wav: str) -> list[str]:
    """Convert any supported input to 16kHz mono WAV for whisper.cpp."""
    return ["ffmpeg", "-y", "-i", src, "-ar", "16000", "-ac", "1", "-f", "wav", dst_wav]


def whisper_args(binary: str, model: str, wav: str, language: str | None,
                 out_prefix: str) -> list[str]:
    """whisper.cpp invocation that emits JSON to <out_prefix>.json."""
    args = [binary, "-m", model, "-f", wav, "-oj", "-of", out_prefix]
    if language:
        args += ["-l", language]
    return args


# ---- whisper json parsing ----


def parse_whisper_json(text: str) -> dict[str, Any]:
    """Parse whisper.cpp -oj output into {text, language}."""
    data = json.loads(text)
    segments = data.get("transcription", []) or []
    body = "".join(seg.get("text", "") for seg in segments).strip()
    lang = (data.get("result", {}) or {}).get("language")
    return {"text": body, "language": lang}


# ---- orchestration (pure given an injected backend builder) ----


def run_transcription(path: str, language: str | None, backend_names: list[str],
                      builder: Any) -> dict[str, Any]:
    """Try each backend in order; return the first success, else an error.

    `builder(name)` returns a Transcriber (or raises, e.g. MissingDependency).
    A Transcriber's `.transcribe(path, language)` returns
    {text, language, duration_seconds}.
    """
    if not is_supported(path):
        return {"ok": False, "error": "unsupported_format",
                "detail": f"{Path(path).suffix} not in {sorted(SUPPORTED_FORMATS)}"}
    errors: list[str] = []
    for name in backend_names:
        try:
            backend = builder(name)
            result = backend.transcribe(path, language)
            return {"ok": True, "backend": name, **result}
        except Exception as exc:  # noqa: BLE001 — surface as structured error
            errors.append(f"{name}: {exc}")
    return {"ok": False, "error": "transcription_failed", "detail": "; ".join(errors)}
