"""Модуль 5: генерация креативов в Kling по промптам из сценариев.

Claude пишет work/<дата>/kling_jobs.json, скрипт проверяет задания по ограничениям из config.yaml → kling,
отправляет их в официальный Kling API, ждёт результат, скачивает и кладёт в Drive.

Видео — Kling 3.0 text-to-video (720p, 3–15 с, 16:9 / 9:16 / 1:1).
Статика — Kling Image 4.0 (минимум 2K), плюс копия, уменьшенная до 720p.
Документация: https://kling.ai/document-api (ключ API — заголовок Authorization: Bearer <KLING_API_KEY>).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path

import requests

from .config import Week
from .download import ffmpeg_bin

DONE, FAILED = "succeeded", "failed"


class KlingError(RuntimeError):
    pass


class Kling:
    def __init__(self, cfg: dict, api_key: str | None = None):
        self.cfg = cfg
        self.base = cfg["base_url"].rstrip("/")
        key = api_key or os.environ.get("KLING_API_KEY")
        if not key:
            raise SystemExit("KLING_API_KEY не задан (переменная облачного окружения)")
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {key}", "Content-Type": "application/json"})

    def _call(self, method: str, path: str, **kw) -> dict:
        delay = 2.0
        for _ in range(8):
            r = self.s.request(method, self.base + path, timeout=60, **kw)
            try:
                body = r.json()
            except ValueError:
                raise KlingError(f"HTTP {r.status_code}: {r.text[:300]}")
            if body.get("code") == 1303:  # превышен лимит параллельных задач пакета — ждём и повторяем
                print(f"  … лимит параллельных задач, жду {delay:.0f} с")
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            if r.status_code >= 400 or body.get("code") not in (0, None):
                raise KlingError(f"HTTP {r.status_code}, code {body.get('code')}: {body.get('message')}")
            return body
        raise KlingError("лимит параллельных задач не освободился")

    def submit(self, job: dict) -> str:
        options = {"external_task_id": job["external_id"], "watermark_info": {"enabled": False}}
        if job["kind"] == "video":
            v = self.cfg["video"]
            body = {"prompt": job["prompt"], "options": options, "settings": {
                "resolution": v["resolution"], "duration": job["duration"], "aspect_ratio": job["aspect_ratio"],
                "audio": job.get("audio", v["audio"]), "multi_shot": bool(job.get("multi_shot", True))}}
            path = v["endpoint"]
        else:
            i = self.cfg["image"]
            body = {"contents": [{"type": "prompt", "text": job["prompt"]}], "options": options, "settings": {
                "result_type": "single", "n": 1, "resolution": i["resolution"], "aspect_ratio": job["aspect_ratio"]}}
            path = i["endpoint"]
        return self._call("POST", path, json=body)["data"]["id"]

    def status(self, task_ids: list[str]) -> list[dict]:
        return self._call("GET", "/tasks", params={"task_ids": ",".join(task_ids)})["data"]


def _slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", s).strip("_")[:60] or "job"


def validate(jobs: list[dict], cfg: dict) -> tuple[list[dict], list[str]]:
    """Отсекает задания вне ограничений и сверх лимитов. Возвращает (годные, предупреждения)."""
    v, i = cfg["video"], cfg["image"]
    ok, warn, units = [], [], 0.0
    n_video = n_image = 0
    for j in jobs:
        jid = _slug(str(j.get("id") or f"job{len(ok) + 1}"))
        kind = j.get("kind")
        ar = j.get("aspect_ratio")
        if kind not in ("video", "image"):
            warn.append(f"{jid}: kind должен быть video или image")
            continue
        if not (j.get("prompt") or "").strip():
            warn.append(f"{jid}: пустой промпт")
            continue
        if ar not in cfg["aspect_ratios"]:
            warn.append(f"{jid}: формат {ar} не разрешён (можно {', '.join(cfg['aspect_ratios'])})")
            continue
        job = {**j, "id": jid, "prompt": j["prompt"].strip()[:3000]}
        if kind == "video":
            dur = int(j.get("duration") or v["max_duration"])
            if not v["min_duration"] <= dur <= v["max_duration"]:
                warn.append(f"{jid}: длительность {dur} с вне {v['min_duration']}–{v['max_duration']} с, урезал")
                dur = max(v["min_duration"], min(dur, v["max_duration"]))
            audio = j.get("audio", v["audio"])
            cost = dur * (v["units_per_second_audio"] if audio == "native" else v["units_per_second"])
            if n_video >= v["max_per_run"] or units + cost > v["max_units_per_run"]:
                warn.append(f"{jid}: пропущено — лимит видео за прогон ({v['max_per_run']} шт / {v['max_units_per_run']} units)")
                continue
            job.update(duration=dur, audio=audio, est_units=cost)
            units += cost
            n_video += 1
        else:
            if n_image >= i["max_per_run"]:
                warn.append(f"{jid}: пропущено — лимит картинок за прогон ({i['max_per_run']})")
                continue
            n_image += 1
        ok.append(job)
    return ok, warn


def _download(url: str, dest: Path) -> None:
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)


def _to_720p(ff: str | None, src: Path) -> Path | None:
    """Копия картинки с короткой стороной 720 px (Image 4.0 отдаёт минимум 2K)."""
    if not ff:
        return None
    dest = src.with_name(src.stem + "_720p.jpg")
    vf = "scale='if(gt(iw,ih),-2,720)':'if(gt(iw,ih),720,-2)'"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(src), "-vf", vf, "-q:v", "3", str(dest)], check=False)
    return dest if dest.exists() else None


def _poster(ff: str | None, video: Path) -> Path | None:
    if not ff:
        return None
    dest = video.with_suffix(".jpg")
    subprocess.run([ff, "-y", "-loglevel", "error", "-ss", "1", "-i", str(video), "-frames:v", "1",
                    "-vf", "scale=480:-2", "-q:v", "4", str(dest)], check=False)
    return dest if dest.exists() else None


def run(cfg_all: dict, week: Week, drive=None, dry_run: bool = False) -> list[dict]:
    cfg = cfg_all["kling"]
    jobs_file = week.workdir / "kling_jobs.json"
    if not jobs_file.exists():
        raise SystemExit(f"Нет {jobs_file}: Claude пишет его после сценариев (SKILL.md, шаг 4б)")
    raw = json.loads(jobs_file.read_text(encoding="utf-8"))
    jobs, warn = validate(raw.get("jobs", raw) if isinstance(raw, dict) else raw, cfg)
    for w in warn:
        print("! " + w)
    est = sum(j.get("est_units", 0) for j in jobs)
    print(f"Заданий: {len(jobs)} (видео {sum(j['kind'] == 'video' for j in jobs)}, "
          f"статика {sum(j['kind'] == 'image' for j in jobs)}); видео ≈ {est:.1f} units "
          f"(≈ ${est * cfg['usd_per_unit']:.2f})")
    if dry_run or not jobs:
        return jobs

    out_dir = week.workdir / "generated"
    out_dir.mkdir(exist_ok=True)
    api = Kling(cfg)
    stamp = week.run_date.strftime("%Y%m%d")
    for j in jobs:
        j["external_id"] = f"yolla-radar-{stamp}-{j['id']}-{int(time.time())}"
        try:
            j["task_id"] = api.submit(j)
            print(f"→ {j['id']}: задача {j['task_id']}")
        except Exception as e:
            j["error"] = str(e)
            print(f"  ! {j['id']}: не отправлено — {e}")

    pending = {j["task_id"]: j for j in jobs if j.get("task_id")}
    deadline = time.time() + cfg["timeout_minutes"] * 60
    while pending and time.time() < deadline:
        time.sleep(cfg["poll_seconds"])
        try:
            states = api.status(list(pending))
        except Exception as e:
            print(f"  ! опрос статуса: {e}")
            continue
        for st in states:
            j = pending.get(st.get("id"))
            if not j or st.get("status") not in (DONE, FAILED):
                continue
            pending.pop(st["id"])
            if st["status"] == FAILED:
                j["error"] = st.get("message") or "failed"
                print(f"  ! {j['id']}: Kling вернул ошибку — {j['error']}")
                continue
            want = "video" if j["kind"] == "video" else "image"
            urls = [o["url"] for o in st.get("outputs") or [] if o.get("type") == want and o.get("url")]
            if not urls:
                j["error"] = "в ответе нет ссылки на результат"
                continue
            dest = out_dir / f"{j['id']}_{j['aspect_ratio'].replace(':', 'x')}{'.mp4' if want == 'video' else '.png'}"
            try:
                _download(urls[0], dest)
                j["local"] = str(dest.relative_to(week.workdir))
                print(f"✓ {j['id']} → {j['local']}")
            except Exception as e:
                j["error"] = f"не скачал результат: {e}"
    for j in pending.values():
        j["error"] = f"не дождался за {cfg['timeout_minutes']} мин (задача {j['task_id']} в Kling)"

    ff = ffmpeg_bin()
    folder = None
    if drive and any(j.get("local") for j in jobs):
        mf = week.workdir / "manifest.json"
        week_folder = (json.loads(mf.read_text()).get("drive_week_folder_id") if mf.exists() else None) \
            or drive.folder(week.label, cfg_all["google_drive"]["root_folder_id"])
        folder = drive.folder("03 Сгенерировано в Kling", week_folder)
    for j in jobs:
        if not j.get("local"):
            continue
        src = week.workdir / j["local"]
        preview = _poster(ff, src) if j["kind"] == "video" else _to_720p(ff, src)
        if preview:
            j["preview"] = str(preview.relative_to(week.workdir))
        if folder:
            j["drive_url"] = drive.upload(src, folder)["webViewLink"]
            if j["kind"] == "image" and preview:
                j["drive_720p_url"] = drive.upload(preview, folder)["webViewLink"]
    if folder:
        print(f"✓ Drive: {drive.link(folder)}")

    (week.workdir / "generated.json").write_text(json.dumps(
        {"jobs": jobs, "warnings": warn}, ensure_ascii=False, indent=1, default=str))
    ok = sum(bool(j.get("local")) for j in jobs)
    print(f"✓ сгенерировано {ok} из {len(jobs)} → generated.json")
    return jobs


def report_markdown(week: Week) -> str:
    """Раздел для документа: что сгенерировано, с превью и ссылками."""
    f = week.workdir / "generated.json"
    if not f.exists():
        return ""
    data = json.loads(f.read_text(encoding="utf-8"))
    lines = ["## Сгенерировано в Kling", "",
             "| Задание | Сценарий | Тип | Формат | Длит. | Результат |", "|---|---|---|---|---|---|"]
    previews = []
    for j in data["jobs"]:
        if j.get("drive_url"):
            res = f"[открыть в Drive]({j['drive_url']})"
            if j.get("drive_720p_url"):
                res += f" · [720p]({j['drive_720p_url']})"
        elif j.get("local"):
            res = j["local"]
        else:
            res = "✗ " + (j.get("error") or "не сгенерировано")
        dur = f"{j['duration']} с" if j["kind"] == "video" else "—"
        kind = "видео" if j["kind"] == "video" else "статика"
        lines.append(f"| {j['id']} | {j.get('scenario', '')} | {kind} | {j['aspect_ratio']} | {dur} | {res} |")
        if j.get("preview"):
            previews.append(f"**{j['id']}**\n\n![{j['id']}]({j['preview']})\n")
    if data.get("warnings"):
        lines += ["", "**Не отправлено:** " + "; ".join(data["warnings"])]
    return "\n".join(lines + [""] + previews)
