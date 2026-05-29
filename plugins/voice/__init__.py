"""voice — MCP server that transcribes audio via local whisper.cpp (default)
or an opt-in cloud Whisper backend.

Pure core (backend selection, ffmpeg/whisper argv, output parsing) +
injected Transcriber boundary. The privacy guarantee — no audio leaves the
machine unless the operator opts in — lives in `select_backends`.
"""
