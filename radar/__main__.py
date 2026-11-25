"""CLI.

python -m radar prep     [--date 2026-11-27] [--no-drive] [--fixtures tests/fixtures]   # модули 1–2
python -m radar publish  [--date ...] [--no-drive]                                     # выгрузка документа
python -m radar doctor                                                                 # проверка ключей и доступа
python -m radar auth     [--client-secret client_secret.json] [--share-with-link]       # один раз: вход в личный Google Drive
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import collect, download, publish
from .config import load_config, make_week


def doctor(cfg: dict, week) -> bool:
    import requests
    from .drive import Drive, auth_mode

    ok = True

    def mark(good: bool, text: str):
        nonlocal ok
        ok &= good
        print(("✓ " if good else "✗ ") + text)

    token = os.environ.get("APIFY_TOKEN")
    mark(bool(token), "APIFY_TOKEN задан")
    if token:
        try:
            r = requests.get("https://api.apify.com/v2/users/me", timeout=20,
                             headers={"Authorization": f"Bearer {token}"})
            mark(r.status_code == 200, f"Apify API отвечает (HTTP {r.status_code})"
                 + ("" if r.status_code == 200 else ": проверьте токен и сетевой доступ окружения к api.apify.com"))
        except Exception as e:
            mark(False, f"Apify API недоступен: {e}")
    mark(download.ffmpeg_bin() is not None, "ffmpeg")

    mode = auth_mode()
    mark(mode is not None, f"Google-авторизация: {mode or 'нет GOOGLE_OAUTH_TOKEN_JSON / GOOGLE_SERVICE_ACCOUNT_JSON'}")
    folder = cfg["google_drive"]["root_folder_id"]
    if mode:
        try:
            info = Drive().info(folder)
            mark(True, f"Папка отчётов: {info['name']} — {info['webViewLink']}")
            if mode == "service_account":
                mark(bool(info.get("driveId")), "папка лежит в Shared Drive (сервисный аккаунт не может писать в «Мой диск»)")
        except Exception as e:
            mark(False, f"папка {folder} недоступна: {e}")
    print(f"Окно анализа: {week.start} … {week.end}")
    return ok


def auth(client_secret: str, share_with_link: bool):
    """Один раз на своём компьютере: вход в Google, токен в файл, папка отчётов в «Моём диске»."""
    import re
    from google_auth_oauthlib.flow import InstalledAppFlow
    from .config import ROOT
    from .drive import FOLDER, OAUTH_SCOPES, Drive

    flow = InstalledAppFlow.from_client_secrets_file(client_secret, OAUTH_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    token_file = ROOT / "google-oauth-token.json"
    token_file.write_text(creds.to_json())
    token_file.chmod(0o600)

    drive = Drive(creds)
    folder_id = drive.svc.files().create(body={"name": "Yolla Creative Radar", "mimeType": FOLDER},
                                         fields="id").execute()["id"]
    if share_with_link:
        drive.svc.permissions().create(fileId=folder_id, body={"type": "anyone", "role": "reader"}).execute()
    cfg_path = ROOT / "config.yaml"
    text = cfg_path.read_text(encoding="utf-8")
    cfg_path.write_text(re.sub(r'root_folder_id: "[^"]*"', f'root_folder_id: "{folder_id}"', text), encoding="utf-8")
    print(f"✓ Токен сохранён в {token_file.name}: его содержимое вставьте в GOOGLE_OAUTH_TOKEN_JSON облачного окружения.")
    print(f"✓ Папка отчётов создана: {drive.link(folder_id)}")
    print("✓ config.yaml обновлён (root_folder_id).")


def main():
    ap = argparse.ArgumentParser(prog="radar")
    ap.add_argument("command", choices=["prep", "publish", "doctor", "auth"])
    ap.add_argument("--date", help="день запуска YYYY-MM-DD (по умолчанию сегодня); окно = 7 дней до него")
    ap.add_argument("--no-drive", action="store_true", help="ничего не загружать в Google Drive")
    ap.add_argument("--fixtures", type=Path, help="читать выдачу Apify из папки вместо запуска акторов")
    ap.add_argument("--client-secret", default="client_secret.json", help="для auth: OAuth-клиент (Desktop app)")
    ap.add_argument("--share-with-link", action="store_true",
                    help="для auth: открыть папку отчётов всем, у кого есть ссылка (просмотр)")
    a = ap.parse_args()

    cfg = load_config()
    week = make_week(cfg, a.date)
    week.workdir.mkdir(parents=True, exist_ok=True)
    drive = None
    if not a.no_drive and a.command in ("prep", "publish"):
        from .drive import Drive
        drive = Drive()

    if a.command == "doctor":
        raise SystemExit(0 if doctor(cfg, week) else 1)
    if a.command == "auth":
        auth(a.client_secret, a.share_with_link)
        return

    if a.command == "prep":
        print(f"=== Модуль 1: сбор креативов, окно {week.start} … {week.end}")
        rows = collect.score_and_filter(collect.fetch(cfg, week, a.fixtures), cfg, week)
        collect.write_table(rows, week)
        print(f"✓ в таблице {len(rows)} креативов ({sum(r['is_new_this_week'] for r in rows)} новых за неделю)")
        print("=== Модуль 2: скачивание и загрузка в Drive")
        rows = download.run(rows, cfg, week, drive)
        collect.write_table(rows, week)  # с ссылками на Drive
        print(f"Рабочая папка: {week.workdir}")
    else:
        publish.run(cfg, week, drive)


if __name__ == "__main__":
    main()
