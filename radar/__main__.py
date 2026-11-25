"""CLI.

python -m radar prep     [--date 2026-11-27] [--no-drive] [--fixtures tests/fixtures]   # модули 1–2
python -m radar publish  [--date ...] [--no-drive]                                     # выгрузка документа
python -m radar doctor                                                                 # проверка ключей и доступа
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from . import collect, download, publish
from .config import load_config, make_week


def main():
    ap = argparse.ArgumentParser(prog="radar")
    ap.add_argument("command", choices=["prep", "publish", "doctor"])
    ap.add_argument("--date", help="день запуска YYYY-MM-DD (по умолчанию сегодня); окно = 7 дней до него")
    ap.add_argument("--no-drive", action="store_true", help="ничего не загружать в Google Drive")
    ap.add_argument("--fixtures", type=Path, help="читать выдачу Apify из папки вместо запуска акторов")
    a = ap.parse_args()

    cfg = load_config()
    week = make_week(cfg, a.date)
    week.workdir.mkdir(parents=True, exist_ok=True)
    drive = None
    if not a.no_drive and a.command != "doctor":
        from .drive import Drive
        drive = Drive()

    if a.command == "doctor":
        ok = True
        for var in ("APIFY_TOKEN", "GOOGLE_SERVICE_ACCOUNT_JSON"):
            print(f"{'✓' if os.environ.get(var) else '✗'} {var}")
            ok &= bool(os.environ.get(var))
        print(f"{'✓' if download.ffmpeg_bin() else '✗'} ffmpeg")
        folder = cfg["google_drive"]["root_folder_id"]
        if os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
            from .drive import Drive
            try:
                print("✓ Drive папка:", Drive().link(folder))
            except Exception as e:
                ok = False
                print("✗ Drive папка недоступна сервисному аккаунту:", e)
        print(f"Окно анализа: {week.start} … {week.end}")
        raise SystemExit(0 if ok else 1)

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
