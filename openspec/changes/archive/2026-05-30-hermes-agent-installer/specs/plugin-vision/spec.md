## ADDED Requirements

### Requirement: Vision pipeline accepts images from any local source
The system SHALL provide a vision pipeline (delivered as a Claude Code skill named `vision`) that analyzes an image file given a local filesystem path. The image source is irrelevant to the pipeline — it MUST work with images from Telegram (via `tg_get_photo`), the macOS screenshot tool, or arbitrary user-provided paths.

#### Scenario: Pipeline analyzes a Telegram photo
- **WHEN** Claude has called `tg_get_photo` and received a local path `/tmp/abc.jpg`
- **AND** the `vision` skill is invoked with that path and a prompt
- **THEN** the skill returns a textual analysis of the image addressing the prompt

### Requirement: Pipeline supports description, OCR, and structured extraction modes
The skill SHALL accept a `mode` parameter with values `describe` (default), `ocr`, and `extract` (the latter taking a JSON-schema hint and returning matching structured data).

#### Scenario: OCR mode returns text only
- **WHEN** the skill runs with `mode=ocr` on an image of a document
- **THEN** the output is the recognized text with no commentary

#### Scenario: Extract mode returns JSON matching schema
- **WHEN** the skill runs with `mode=extract` and a schema describing `{vendor, total, date}` on a photo of a receipt
- **THEN** the output is a JSON object whose fields match the schema or whose missing fields are `null`

### Requirement: Vision uses Claude's native vision, no external model
The skill MUST use Claude's built-in vision via the Claude API/CLI. It MUST NOT require, install, or call any third-party vision model or cloud service.

#### Scenario: No third-party model dependency
- **WHEN** the user inspects the skill's dependencies
- **THEN** no package references a vision-specific model (e.g., `clip`, `blip`, `gpt-4-vision`)
- **AND** the only external call is to Claude
