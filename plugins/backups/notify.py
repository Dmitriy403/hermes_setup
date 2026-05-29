"""Failure notification routing.

Which channels fire is a pure function of the environment (mac always;
Telegram when BACKUP_ALERT_CHAT_ID is set). The actual send is a live edge.
"""

from __future__ import annotations

import os
import subprocess
from typing import Callable

Notifier = Callable[[str, str], None]


def notifier_names(env: dict[str, str]) -> list[str]:
    """Pure: which notification channels apply for this environment."""
    names = ["mac"]
    if env.get("BACKUP_ALERT_CHAT_ID") and env.get("TELEGRAM_BOT_TOKEN"):
        names.append("telegram")
    return names


def mac_notify(title: str, message: str) -> None:
    t = title.replace('"', '\\"')
    m = message.replace('"', '\\"')
    subprocess.run(["osascript", "-e", f'display notification "{m}" with title "{t}"'],
                   capture_output=True, timeout=15)


def telegram_notify(title: str, message: str) -> None:
    chat_id = int(os.environ["BACKUP_ALERT_CHAT_ID"])
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    import asyncio

    from telegram import Bot
    asyncio.run(Bot(token).send_message(chat_id=chat_id, text=f"{title}\n{message}"))


def build_notifiers(env: dict[str, str]) -> dict[str, Notifier]:
    impls: dict[str, Notifier] = {"mac": mac_notify, "telegram": telegram_notify}
    return {name: impls[name] for name in notifier_names(env) if name in impls}


def notify_failure(title: str, summary: str, notifiers: dict[str, Notifier]) -> dict[str, str]:
    """Fire every notifier; never raise (best-effort alerting). Returns per-channel status."""
    status: dict[str, str] = {}
    for name, fn in notifiers.items():
        try:
            fn(title, summary)
            status[name] = "sent"
        except Exception as exc:  # noqa: BLE001
            status[name] = f"failed: {str(exc)[:120]}"
    return status
