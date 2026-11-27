"""Восстановление рабочей папки недели из Google Drive — без повторного сбора в Apify.

Берёт из папки недели таблицу «00 Таблица креативов», медиа из «01 Креативы конкурентов»,
заново вырезает кадры локально (имена совпадают с исходными) и пересобирает manifest.json
со ссылками на уже загруженные в Drive файлы. Ничего не загружает повторно.
"""
from __future__ import annotations

import csv
import json
import re

from . import download
from .config import Week
from .drive import FOLDER, SHEET


def run(cfg: dict, week: Week, drive) -> None:
    root = cfg["google_drive"]["root_folder_id"]
    week_folder = drive.find(week.label, root, FOLDER)
    if not week_folder:
        raise SystemExit(f"В Drive нет папки недели «{week.label}»: эту неделю придётся собирать заново (prep)")
    print(f"Папка недели: {drive.link(week_folder)}")
    wd = week.workdir
    (wd / "media").mkdir(parents=True, exist_ok=True)

    sheet = drive.find(f"00 Таблица креативов — {week.run_date}", week_folder, SHEET)
    if not sheet:
        raise SystemExit("В папке недели нет таблицы «00 Таблица креативов»")
    drive.download(sheet, wd / "creatives.csv", export_mime="text/csv")
    with open(wd / "creatives.csv", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    print(f"✓ таблица: {len(rows)} креативов")

    media_folder = drive.find("01 Креативы конкурентов", week_folder, FOLDER)
    media = {f["name"]: f for f in drive.list(media_folder)} if media_folder else {}
    for name, f in media.items():
        dest = wd / "media" / name
        if not dest.exists():
            drive.download(f["id"], dest)
    print(f"✓ медиа из Drive: {len(media)} файлов")

    # Берём ровно те креативы, что были скачаны в исходном прогоне: остальные ссылки на CDN уже протухли
    have = {n.rsplit(".", 1)[0] for n in media}
    for r in rows:
        r["rank"] = int(float(r["rank"]))
    def base(r: dict) -> str:  # то же имя, что даёт download.run
        return f"{r['rank']:03d}_" + re.sub(r"\W+", "", r["competitor"]) + f"_{r['creative_id']}"

    picked = [r for r in rows if base(r) in have]
    for r in picked:
        r["media_url"] = r.get("media_url") or "drive"
    sel = cfg["selection"]
    cfg = {**cfg, "selection": {**sel, "download_top_overall": len(picked) or 1, "download_top_per_competitor": 0}}
    download.run(picked, cfg, week, drive=None)

    frames_folder = drive.find("02 Кадры-референсы", week_folder, FOLDER)
    frame_links = {f["name"]: f["webViewLink"] for f in drive.list(frames_folder)} if frames_folder else {}
    mf_path = wd / "manifest.json"
    mf = json.loads(mf_path.read_text())
    mf["drive_week_folder_id"] = week_folder
    by_id = {r["creative_id"]: r for r in rows}
    for c in mf["creatives"]:
        name = c["local_media"].split("/", 1)[-1]
        if name in media:
            c["drive_media_url"] = media[name]["webViewLink"]
        c["frame_links"] = {p: frame_links[p.split("/", 1)[-1]] for p in c["frames"]
                            if p.split("/", 1)[-1] in frame_links}
        c["drive_media_url"] = c.get("drive_media_url") or by_id.get(c["creative_id"], {}).get("drive_media_url")
    mf["restored_from_drive"] = True
    mf_path.write_text(json.dumps(mf, ensure_ascii=False, indent=1, default=str))
    print(f"✓ manifest.json восстановлен: {len(mf['creatives'])} креативов, "
          f"ссылок на кадры в Drive: {sum(len(c['frame_links']) for c in mf['creatives'])}")
    print(f"Рабочая папка: {wd}. Дальше — шаги 3–6 из SKILL.md (prep не запускать).")
