#!/usr/bin/env python3
"""Headless vision helper for the `vision` skill.

Sends a local image to Claude (native vision) and prints the analysis. Used by
non-interactive pipelines (e.g. the Telegram bot). No third-party vision model
— the only external call is to Claude.

    python3 run.py IMAGE [--mode describe|ocr|extract] [--prompt P] [--schema S] [--model M]
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp",
}
DEFAULT_MODEL = "claude-opus-4-7"


def media_type(path: str) -> str:
    return _MEDIA_TYPES.get(Path(path).suffix.lower(), "image/jpeg")


def build_prompt(mode: str, prompt: str | None = None, schema: str | None = None) -> str:
    if mode == "ocr":
        return ("Transcribe all text visible in this image. Output only the "
                "recognized text, preserving reading order, with no commentary, "
                "headings, or markdown.")
    if mode == "extract":
        return ("Extract structured data from this image matching this JSON schema:\n"
                f"{schema}\n"
                "Output ONLY a single valid JSON object. Use null for any field "
                "not present in the image. No prose, no code fences.")
    if mode != "describe":
        raise ValueError(f"unknown mode: {mode}")
    base = "Describe this image in detail."
    return f"{base} {prompt}" if prompt else base


def build_messages(image_path: str, mode: str, prompt: str | None, schema: str | None) -> list[dict]:
    data = base64.standard_b64encode(Path(image_path).read_bytes()).decode("ascii")
    return [{
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": media_type(image_path), "data": data}},
            {"type": "text", "text": build_prompt(mode, prompt, schema)},
        ],
    }]


def analyze(image_path: str, mode: str, prompt: str | None, schema: str | None, model: str) -> str:
    try:
        import anthropic
    except ImportError:
        raise SystemExit(
            "the 'anthropic' SDK is required for headless vision; "
            "install it (pip install anthropic) or run vision interactively in Claude."
        )
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=build_messages(image_path, mode, prompt, schema),
    )
    return "".join(block.text for block in resp.content if getattr(block, "type", None) == "text")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="vision", description="Analyze an image with Claude.")
    p.add_argument("image", help="path to the image file")
    p.add_argument("--mode", choices=["describe", "ocr", "extract"], default="describe")
    p.add_argument("--prompt", help="extra instruction for describe mode")
    p.add_argument("--schema", help="JSON schema hint for extract mode")
    p.add_argument("--model", default=DEFAULT_MODEL)
    args = p.parse_args(argv)

    if not Path(args.image).is_file():
        print(f"no such image: {args.image}", file=sys.stderr)
        return 2
    if args.mode == "extract" and not args.schema:
        print("extract mode requires --schema", file=sys.stderr)
        return 64

    print(analyze(args.image, args.mode, args.prompt, args.schema, args.model))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
