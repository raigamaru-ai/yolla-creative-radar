"""Модуль 6: короткий отчёт о прогоне в Telegram.

Переменные окружения:
  TELEGRAM_BOT_TOKEN — токен бота от @BotFather (секрет);
  TELEGRAM_CHAT_IDS  — ID чатов через запятую: группа (обычно отрицательное число) и/или личные чаты.
Сбой отправки не роняет прогон: печатается предупреждение.
"""
from __future__ import annotations

import json
import os

import requests

from .config import Week

API = "https://api.telegram.org/bot{token}/{method}"
LIMIT = 4000  # у Telegram лимит 4096 символов на сообщение


def _creds() -> tuple[str | None, list[str]]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chats = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_IDS", "").replace(";", ",").split(",") if c.strip()]
    return token, chats


def _call(token: str, method: str, **params) -> dict:
    r = requests.post(API.format(token=token, method=method), json=params, timeout=30)
    body = r.json()
    if not body.get("ok"):
        raise RuntimeError(f"{method}: {body.get('description')}")
    return body["result"]


def _chunks(text: str) -> list[str]:
    out, cur = [], ""
    for para in text.split("\n"):
        while len(para) > LIMIT:
            out.append(para[:LIMIT])
            para = para[LIMIT:]
        if len(cur) + len(para) + 1 > LIMIT:
            out.append(cur)
            cur = ""
        cur += para + "\n"
    if cur.strip():
        out.append(cur)
    return out


def default_text(week: Week) -> str:
    """Запасной текст, если Claude не написал telegram.md: только ссылки."""
    lines = [f"Yolla Creative Radar — {week.start:%d.%m} … {week.end:%d.%m.%Y}"]
    f = week.workdir / "links.json"
    if f.exists():
        links = json.loads(f.read_text())
        lines += [f"Папка недели: {links.get('folder')}", f"Документ: {links.get('doc')}", f"Таблица: {links.get('sheet')}"]
    else:
        lines.append("Отчёт не опубликован — подробности в логе облачного прогона.")
    return "\n".join(lines)


def send(text: str) -> bool:
    token, chats = _creds()
    if not token or not chats:
        print("⚠ Telegram не настроен (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_IDS) — отчёт не отправлен")
        return False
    ok = True
    for chat in chats:
        try:
            for part in _chunks(text):
                _call(token, "sendMessage", chat_id=chat, text=part, disable_web_page_preview=True)
            print(f"✓ Telegram: отправлено в чат {chat}")
        except Exception as e:
            ok = False
            print(f"⚠ Telegram, чат {chat}: {e}")
    return ok


def run(week: Week, text: str | None = None) -> bool:
    if text is None:
        f = week.workdir / "telegram.md"
        text = f.read_text(encoding="utf-8") if f.exists() else default_text(week)
    return send(text)


def list_chats() -> None:
    """Помогает узнать ID чатов: напишите боту (или в группу с ботом), затем запустите эту команду."""
    token, _ = _creds()
    if not token:
        raise SystemExit("Задайте TELEGRAM_BOT_TOKEN в окружении")
    me = _call(token, "getMe")
    print(f"Бот: @{me['username']}")
    seen = {}
    for u in _call(token, "getUpdates"):
        msg = u.get("message") or u.get("my_chat_member") or u.get("channel_post") or {}
        chat = msg.get("chat")
        if chat:
            seen[chat["id"]] = chat.get("title") or " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")])) \
                or chat.get("username") or ""
    if not seen:
        print("Сообщений нет: напишите боту /start (или любое сообщение в группе с ботом) и повторите.")
    for cid, name in seen.items():
        print(f"{cid}\t{name}")
    if seen:
        print("Эти ID через запятую — в TELEGRAM_CHAT_IDS облачного окружения.")
