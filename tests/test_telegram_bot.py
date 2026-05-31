"""Tests for telegram-bot — core (allowlist, ring buffer, normalization),
tool allowlist enforcement (via a fake client), and launchd plist.

No python-telegram-bot / mcp needed (those are the live edge).

    PYTHONPATH=src python3 tests/test_telegram_bot.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# telegram_bot is a package under plugins/ with relative imports → import as pkg
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins"))

from telegram_bot import core  # noqa: E402
from telegram_bot.tools import TelegramTools  # noqa: E402


class FakeClient:
    def __init__(self):
        self.sent: list[tuple] = []

    def download(self, file_id: str) -> str:
        return f"/tmp/fake-{file_id}.bin"

    def send_text(self, chat_id, text):
        self.sent.append(("text", chat_id, text))

    def send_photo(self, chat_id, path, caption=None):
        self.sent.append(("photo", chat_id, path))

    def send_document(self, chat_id, path, caption=None):
        self.sent.append(("document", chat_id, path))


# ---- core: allowlist + config ----

def test_parse_allowlist():
    assert core.parse_allowlist("1, 2 ,,x,3") == {1, 2, 3}
    assert core.parse_allowlist("") == set()
    assert core.parse_allowlist(None) == set()


def test_validate_config_refuses_empty_allowlist():
    try:
        core.validate_config("tok", set())
    except core.ConfigError as e:
        assert "TELEGRAM_ALLOWED_CHAT_IDS" in str(e)
    else:
        raise AssertionError("expected ConfigError on empty allowlist")


def test_validate_config_refuses_missing_token():
    try:
        core.validate_config(None, {1})
    except core.ConfigError as e:
        assert "TELEGRAM_BOT_TOKEN" in str(e)
    else:
        raise AssertionError("expected ConfigError on missing token")


def test_validate_config_ok():
    core.validate_config("tok", {123})  # no raise


# ---- core: ring buffer ----

def _msg(mid, text="hi", chat=1):
    return core.Message(mid, chat, "u", "2026-01-01T00:00:00+00:00", "text", text)


def test_ring_buffer_evicts_and_indexes():
    b = core.MessageBuffer(maxlen=3)
    for i in range(1, 6):
        b.add(_msg(i))
    assert len(b) == 3
    assert [m.message_id for m in b.latest(10)] == [5, 4, 3]   # newest first
    assert b.get(5) is not None
    assert b.get(1) is None  # evicted → dropped from index


def test_ring_buffer_latest_limit():
    b = core.MessageBuffer(maxlen=10)
    for i in range(1, 6):
        b.add(_msg(i))
    assert [m.message_id for m in b.latest(2)] == [5, 4]
    assert b.latest(0) == []


# ---- core: normalization ----

def test_normalize_text():
    m = core.normalize_update({"message": {"message_id": 7, "chat": {"id": 1},
                                           "from": {"username": "dt"}, "date": 1700000000, "text": "yo"}})
    assert m.type == "text" and m.content == "yo" and m.sender == "dt" and m.chat_id == 1


def test_normalize_voice_photo_document():
    v = core.normalize_update({"message": {"message_id": 1, "chat": {"id": 1}, "date": 0,
                                           "voice": {"file_id": "VID", "duration": 5, "mime_type": "audio/ogg"}}})
    assert v.type == "voice" and v.file_id == "VID" and v.duration_seconds == 5
    p = core.normalize_update({"message": {"message_id": 2, "chat": {"id": 1}, "date": 0,
                                           "photo": [{"file_id": "small"}, {"file_id": "big"}]}})
    assert p.type == "photo" and p.file_id == "big"   # largest
    d = core.normalize_update({"message": {"message_id": 3, "chat": {"id": 1}, "date": 0,
                                           "document": {"file_id": "DID", "file_name": "x.pdf"}}})
    assert d.type == "document" and d.file_id == "DID" and d.file_name == "x.pdf"


def test_normalize_ignores_non_message():
    assert core.normalize_update({"edited_message": {}}) is None
    assert core.normalize_update({"message": {"chat": {"id": 1}, "date": 0}}) is None  # no content


# ---- tools: inbound + outbound allowlist enforcement ----

def _tools(allowed={1}):
    b = core.MessageBuffer(maxlen=50)
    b.add(core.Message(10, 1, "u", "t", "voice", "[voice]", file_id="VID", mime_type="audio/ogg", duration_seconds=5))
    b.add(core.Message(11, 1, "u", "t", "text", "hello"))
    return TelegramTools(b, FakeClient(), set(allowed)), b


def test_get_latest_and_voice():
    t, _ = _tools()
    latest = t.get_latest_messages(10)
    assert latest["ok"] and len(latest["messages"]) == 2
    v = t.get_voice(10)
    assert v["ok"] and v["path"] == "/tmp/fake-VID.bin" and v["duration_seconds"] == 5


def test_get_voice_wrong_type_and_missing():
    t, _ = _tools()
    assert t.get_voice(11)["error"] == "wrong_type"   # 11 is text
    assert t.get_voice(999)["error"] == "not_found"


def test_send_text_allowed():
    t, _ = _tools(allowed={1})
    r = t.send_text(1, "hi")
    assert r["ok"] and r["sent_to"] == 1
    assert t.client.sent == [("text", 1, "hi")]


def test_send_to_non_allowlisted_refused_and_not_sent():
    t, _ = _tools(allowed={1})
    r = t.send_text(999, "leak?")
    assert r["ok"] is False and r["error"] == "chat_not_allowed"
    assert t.client.sent == []   # CRITICAL: nothing sent
    r2 = t.send_photo(999, "/x.png")
    assert r2["error"] == "chat_not_allowed" and t.client.sent == []


# ---- launchd ----

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
