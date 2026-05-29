"""voice MCP server — exposes voice.transcribe.

Backend selection (and therefore the privacy guarantee) comes from the pure
core; the live whisper/cloud backends are built lazily. `mcp` imported lazily.
"""

from __future__ import annotations

import os
from typing import Any

from . import backends, core


def transcribe(path: str, language: str | None = None) -> dict[str, Any]:
    """Transcribe an audio file per the configured backend policy."""
    model = os.environ.get("VOICE_WHISPER_MODEL") or core.DEFAULT_MODEL
    names = core.select_backends(
        cloud_mode=os.environ.get("VOICE_CLOUD_MODE"),
        cloud_fallback=os.environ.get("VOICE_CLOUD_FALLBACK") == "1",
        has_openai_key=bool(os.environ.get("OPENAI_API_KEY")),
    )
    return core.run_transcription(path, language, names,
                                  builder=lambda n: backends.build_backend(n, model))


def main() -> int:
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("voice")

    @server.tool()
    def voice_transcribe(path: str, language: str | None = None) -> dict:
        """Transcribe a local audio file. Returns {text, language, duration_seconds, backend}."""
        return transcribe(path, language)

    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
