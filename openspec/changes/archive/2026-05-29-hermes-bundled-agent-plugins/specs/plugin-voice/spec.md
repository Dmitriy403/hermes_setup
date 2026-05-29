## ADDED Requirements

### Requirement: Voice plugin transcribes audio files via MCP
The repo SHALL contain `plugins/voice/` exposing an MCP server named `voice` that takes a local audio file path and returns its transcription. Supported formats MUST include at least `.ogg` (Telegram voice notes), `.m4a`, `.mp3`, `.wav`, `.flac`.

#### Scenario: Telegram voice note round-trip
- **WHEN** Claude calls `tg_get_voice(message_id=42)` and receives `/tmp/v.ogg`
- **AND** calls `voice.transcribe(path="/tmp/v.ogg")`
- **THEN** the tool returns `{text, language, duration_seconds}` where `text` is the transcribed content

### Requirement: Default backend is local whisper.cpp
The default backend SHALL be local `whisper.cpp` with a configurable model size (default: `base`, configurable to `small`/`medium`/`large` via `VOICE_WHISPER_MODEL` in `secrets.env` despite not being a secret — kept there because it is a per-machine knob, with no leak risk).

#### Scenario: Local backend works offline
- **WHEN** the host machine has no internet connection
- **AND** `voice.transcribe(path=…)` is called on a supported audio file
- **THEN** the call still succeeds

### Requirement: Optional cloud fallback for accuracy
The plugin SHALL support a cloud Whisper backend (OpenAI Whisper API) that is engaged only when both `VOICE_CLOUD_FALLBACK=1` and `OPENAI_API_KEY` are set. The cloud backend MUST be selectable as primary or fallback via `VOICE_CLOUD_MODE=primary|fallback|off`, with the default value `off` so no audio leaves the machine without explicit opt-in.

#### Scenario: Cloud mode off means no network call
- **WHEN** `VOICE_CLOUD_MODE` is `off` or unset
- **THEN** `voice.transcribe` never opens an outbound network connection

### Requirement: Plugin language hint
`voice.transcribe` SHALL accept an optional `language` hint (ISO 639-1 code). When omitted, the backend auto-detects.

#### Scenario: Russian voice note is transcribed
- **WHEN** `voice.transcribe(path="/tmp/v.ogg", language="ru")` is called on a Russian-language voice note
- **THEN** the returned `text` is in Russian and `language` is `"ru"`
