# voice

An MCP server that transcribes audio to text. Local `whisper.cpp` by default;
an optional cloud Whisper backend is strictly opt-in.

## Tool

`voice.transcribe(path, language?)` → `{text, language, duration_seconds, backend}`

Supported formats: `.ogg` (Telegram voice notes), `.m4a`, `.mp3`, `.wav`,
`.flac`, `.opus`, `.aac`. `language` is an optional ISO 639-1 hint; omit to
auto-detect.

## Privacy — cloud is opt-in

By default **no audio leaves the machine**. The cloud backend is used only when
**all** of these are set: `VOICE_CLOUD_MODE` ∈ {`primary`, `fallback`},
`VOICE_CLOUD_FALLBACK=1`, and `OPENAI_API_KEY`. Otherwise transcription is
local-only and the cloud backend is never even constructed.

## Env

- `VOICE_WHISPER_MODEL` — `base` (default) | `small` | `medium` | `large` (per-machine knob, not a secret)
- `VOICE_CLOUD_MODE` — `off` (default) | `fallback` | `primary`
- `VOICE_CLOUD_FALLBACK` — `1` to allow cloud
- `OPENAI_API_KEY` — required only for the cloud backend (secrets.env)

## Dependencies (lazy / brew)

- `whisper-cpp` and `ffmpeg` — `brew install whisper-cpp ffmpeg`. If absent,
  `voice.transcribe` returns `{ok:false, error:"missing_dependency", how_to_fix:…}`.
- A whisper model at `~/.cache/hermes/whisper/ggml-<model>.bin`. Downloaded
  automatically from HuggingFace on first transcription (the `VOICE_WHISPER_MODEL`
  size, default `base`); no manual step needed if the host has network access.
- `openai` SDK only for the cloud backend (`pip install openai`).

## Smoke test

`hermes-voice` is the MCP server. With whisper-cpp + a model installed,
`voice.transcribe("/path/to/clip.ogg")` should return the spoken text.
