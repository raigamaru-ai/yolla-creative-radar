"""Публикация: таблица креативов → Google Sheet, анализ + сценарии → Google Doc в папке недели."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import markdown

from .config import Week
from .drive import DOC, SHEET

CSS = """
body{font-family:Arial,sans-serif;font-size:11pt;line-height:1.45;color:#1f2328}
h1{font-size:22pt;color:#0b5cff} h2{font-size:16pt;color:#0b5cff;margin-top:24pt}
h3{font-size:13pt;margin-top:16pt} table{border-collapse:collapse}
td,th{border:1px solid #c9ced6;padding:4pt 6pt;vertical-align:top} th{background:#eef3ff}
code,pre{font-family:'Roboto Mono',monospace;font-size:9.5pt;background:#f5f7fa}
pre{padding:8pt;white-space:pre-wrap} blockquote{color:#57606a;border-left:3pt solid #c9ced6;padding-left:8pt}
img{max-width:220px}
"""


def _embed_images(html: str, week: Week, links: dict[str, str]) -> str:
    """Локальные кадры → base64 (Docs импортирует их как картинки) + ссылка на файл в Drive."""
    def repl(m):
        src = m.group(2)
        p = (week.workdir / src).resolve()
        if not p.exists() or week.workdir.resolve() not in p.parents:
            return m.group(0)
        data = base64.b64encode(p.read_bytes()).decode()
        img = f'<img{m.group(1)}src="data:image/jpeg;base64,{data}"{m.group(3)}>'
        link = links.get(src)
        return img + (f'<br><a href="{link}">открыть кадр в Drive</a>' if link else "")
    return re.sub(r'<img([^>]*?)src="([^"]+)"([^>]*)>', repl, html)


def build_html(week: Week) -> str:
    parts = []
    for name in ("scenarios.md", "analysis.md"):
        f = week.workdir / name
        if not f.exists():
            raise SystemExit(f"Нет {f}: сначала выполните модули 3–4 (см. SKILL.md)")
        parts.append(f.read_text(encoding="utf-8"))
    from .kling import report_markdown
    gen = report_markdown(week)
    if gen:
        parts.insert(1, gen)
    md = "\n\n---\n\n".join(parts)
    html = markdown.markdown(md, extensions=["tables", "fenced_code", "sane_lists"])
    links: dict[str, str] = {}
    mf = week.workdir / "manifest.json"
    if mf.exists():
        for c in json.loads(mf.read_text())["creatives"]:
            links.update(c.get("frame_links") or {})
    html = _embed_images(html, week, links)
    return f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{html}</body></html>"


def run(cfg: dict, week: Week, drive=None) -> dict:
    html_path = week.workdir / "report.html"
    html_path.write_text(build_html(week), encoding="utf-8")
    print(f"✓ локальная версия отчёта: {html_path}")
    if not drive:
        return {"report_html": str(html_path)}

    mf = json.loads((week.workdir / "manifest.json").read_text())
    folder = mf.get("drive_week_folder_id") or drive.folder(week.label, cfg["google_drive"]["root_folder_id"])
    sheet = drive.upload(week.workdir / "creatives.csv", folder, name=f"00 Таблица креативов — {week.run_date}",
                         convert_to=SHEET, mime="text/csv")
    doc = drive.upload(html_path, folder, name=f"Yolla — сценарии и промпты — {week.run_date}",
                       convert_to=DOC, mime="text/html")
    out = {"folder": drive.link(folder), "sheet": sheet["webViewLink"], "doc": doc["webViewLink"]}
    (week.workdir / "links.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return out
