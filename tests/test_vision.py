"""Tests for the vision skill helper (manifest/skills/vision/files/run.py).

Covers the pure logic — prompt building, media-type detection, message
assembly, arg handling. The live Claude API call is not exercised in CI.

    PYTHONPATH=src python3 tests/test_vision.py
"""

from __future__ import annotations

import base64
import importlib.util
import sys
import tempfile
from pathlib import Path

_RUN = (Path(__file__).resolve().parents[1]
        / "manifest" / "skills" / "vision" / "files" / "run.py")
_spec = importlib.util.spec_from_file_location("vision_run", _RUN)
run = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run)


def test_media_type_detection():
    assert run.media_type("/x/a.png") == "image/png"
    assert run.media_type("/x/a.JPG") == "image/jpeg"
    assert run.media_type("/x/a.jpeg") == "image/jpeg"
    assert run.media_type("/x/a.webp") == "image/webp"
    assert run.media_type("/x/a.unknown") == "image/jpeg"  # fallback


def test_build_prompt_describe():
    assert "describe" in run.build_prompt("describe").lower()
    assert "what is the error" in run.build_prompt("describe", prompt="what is the error").lower()


def test_build_prompt_ocr_is_commentary_free():
    p = run.build_prompt("ocr").lower()
    assert "only" in p and "no commentary" in p


def test_build_prompt_extract_includes_schema_and_null_rule():
    schema = '{"vendor": "string", "total": "number"}'
    p = run.build_prompt("extract", schema=schema)
    assert schema in p
    assert "null" in p.lower()
    assert "json" in p.lower()


def test_build_prompt_unknown_mode_raises():
    try:
        run.build_prompt("hallucinate")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown mode")


def test_build_messages_has_image_and_text_blocks():
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "x.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n fake")
        msgs = run.build_messages(str(img), "describe", None, None)
        assert len(msgs) == 1
        content = msgs[0]["content"]
        kinds = [b["type"] for b in content]
        assert kinds == ["image", "text"]
        # image is base64 of the file bytes
        assert content[0]["source"]["media_type"] == "image/png"
        assert content[0]["source"]["data"] == base64.standard_b64encode(img.read_bytes()).decode()


def test_main_missing_image_returns_2():
    assert run.main(["/no/such/image.png"]) == 2


def test_main_extract_without_schema_returns_64():
    with tempfile.TemporaryDirectory() as d:
        img = Path(d) / "x.png"
        img.write_bytes(b"fake")
        assert run.main([str(img), "--mode", "extract"]) == 64


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
