---
name: vision
description: Analyze a local image — describe it, OCR its text, or extract structured data. Use when given an image path (from Telegram, a screenshot, or the filesystem) and asked what's in it, to read its text, or to pull fields out of it.
---

# vision

Analyze an image at a local filesystem path using Claude's native vision. The
image source is irrelevant — it works for Telegram photos (`tg_get_photo`),
macOS screenshots (`screenshot_*`), or any user-provided path.

There is **no third-party vision model** — Claude looks at the image directly.

## Modes

### describe (default)
Give a detailed natural-language description of the image, addressing the
user's prompt if one was given.

> Read the image and describe what you see. If the user asked a specific
> question about the image, answer that question using what's visible.

### ocr
Transcribe all visible text, verbatim, with **no commentary or formatting**.

> Read the image and output only the text you can read in it. Do not add
> explanations, headings, or markdown. Preserve reading order.

### extract
Return structured JSON matching a caller-provided schema.

> Read the image and produce a single JSON object matching the requested
> schema. Use `null` for any field that is not present in the image. Output
> ONLY the JSON — no prose, no code fences.

## How to use it interactively

When you (Claude) are asked to analyze an image and you have the path:
1. Use the `Read` tool on the image path (you are multimodal — you can see it).
2. Apply the instructions for the requested `mode` above.
3. For `extract`, echo back valid JSON only.

## Headless / programmatic use

For non-interactive pipelines (e.g. the Telegram bot analyzing an incoming
photo without a live Claude session), use the bundled helper:

```sh
python3 run.py /tmp/photo.jpg --mode describe --prompt "what's the error?"
python3 run.py /tmp/doc.png  --mode ocr
python3 run.py /tmp/receipt.jpg --mode extract \
    --schema '{"vendor": "string", "total": "number", "date": "string"}'
```

The helper sends the image to Claude (via the `anthropic` SDK if available,
else the `claude` CLI). It requires `ANTHROPIC_API_KEY` for the SDK path.
