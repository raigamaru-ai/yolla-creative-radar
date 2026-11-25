"""Модуль 2: скачивание лучших креативов, ключевые кадры, транскрипт, загрузка в Google Drive."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import requests

from .config import Week

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"}


def ffmpeg_bin() -> str | None:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def select(rows: list[dict], cfg: dict) -> list[dict]:
    s = cfg["selection"]
    with_media = [r for r in rows if r.get("media_url")]
    chosen = {r["creative_id"]: r for r in with_media[: int(s["download_top_overall"])]}
    for comp in {r["competitor"] for r in with_media}:
        for r in [x for x in with_media if x["competitor"] == comp][: int(s["download_top_per_competitor"])]:
            chosen.setdefault(r["creative_id"], r)
    return sorted(chosen.values(), key=lambda r: int(r["rank"]))


def _download(url: str, dest: Path, max_mb: int) -> bool:
    try:
        with requests.get(url, headers=UA, stream=True, timeout=60) as resp:
            resp.raise_for_status()
            size = 0
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(1 << 20):
                    size += len(chunk)
                    if size > max_mb * 2**20:
                        raise ValueError(f"больше {max_mb} МБ")
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"  ! не скачал {dest.name}: {e}")
        dest.unlink(missing_ok=True)
        return False


def _duration(ff: str, video: Path) -> float:
    out = subprocess.run([ff, "-i", str(video)], capture_output=True, text=True).stderr
    m = re.search(r"Duration: (\d+):(\d+):([\d.]+)", out)
    return int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3]) if m else 0.0


def extract_frames(ff: str, video: Path, out_dir: Path, n: int) -> tuple[list[Path], float]:
    """Кадры с упором на хук: 0.5с, 1.5с, 3с, дальше равномерно до конца."""
    dur = _duration(ff, video)
    if dur <= 0:
        return [], 0.0
    times = [t for t in (0.5, 1.5, 3.0) if t < dur]
    rest = max(n - len(times), 0)
    times += [3.0 + (dur - 3.5) * (i + 1) / (rest + 1) for i in range(rest)] if dur > 4 else []
    frames = []
    for i, t in enumerate(sorted(set(round(x, 1) for x in times))[:n]):
        dest = out_dir / f"{video.stem}_f{i + 1}_{t:.1f}s.jpg"
        subprocess.run([ff, "-y", "-loglevel", "error", "-ss", f"{t}", "-i", str(video), "-frames:v", "1",
                        "-vf", "scale=720:-2", "-q:v", "4", str(dest)], check=False)
        if dest.exists():
            frames.append(dest)
    return frames, dur


_whisper = None


def transcribe(video: Path) -> tuple[str, str]:
    global _whisper
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return "", ""
    if _whisper is None:
        _whisper = WhisperModel("base", device="cpu", compute_type="int8")
    try:
        segments, info = _whisper.transcribe(str(video), vad_filter=True)
        text = " ".join(f"[{s.start:.0f}s] {s.text.strip()}" for s in segments)
        return text, info.language
    except Exception as e:
        print(f"  ! транскрипт {video.name}: {e}")
        return "", ""


def run(rows: list[dict], cfg: dict, week: Week, drive=None) -> list[dict]:
    s = cfg["selection"]
    media_dir = week.workdir / "media"
    frames_dir = week.workdir / "frames"
    media_dir.mkdir(parents=True, exist_ok=True)
    frames_dir.mkdir(parents=True, exist_ok=True)
    ff = ffmpeg_bin()
    if not ff:
        print("! ffmpeg не найден: кадры не будут извлечены (pip install imageio-ffmpeg)")

    week_folder = media_folder = frames_folder = None
    if drive:
        week_folder = drive.folder(week.label, cfg["google_drive"]["root_folder_id"])
        media_folder = drive.folder("01 Креативы конкурентов", week_folder)
        frames_folder = drive.folder("02 Кадры-референсы", week_folder)

    manifest = []
    for r in select(rows, cfg):
        comp = re.sub(r"\W+", "", r["competitor"])
        base = f"{int(r['rank']):03d}_{comp}_{r['creative_id']}"
        is_video = r["format"] == "video"
        ext = ".mp4" if is_video else ".jpg"
        dest = media_dir / (base + ext)
        print(f"↓ #{r['rank']} {r['competitor']} {r['platform']} score={r['score']}")
        if not dest.exists() and not _download(r["media_url"], dest, int(s["max_video_mb"])):
            continue
        entry = {k: r[k] for k in ("creative_id", "rank", "score", "competitor", "platform", "format",
                                   "first_seen", "days_running", "is_new_this_week", "reach",
                                   "variations", "headline", "ad_text", "cta", "library_url")}
        entry["local_media"] = str(dest.relative_to(week.workdir))
        frames, dur = ([], 0.0)
        if is_video and ff:
            frames, dur = extract_frames(ff, dest, frames_dir, int(s["frames_per_video"]))
            if s.get("transcribe_audio"):
                entry["transcript"], entry["language"] = transcribe(dest)
        elif not is_video:
            frames = [dest]
        entry["duration_s"] = round(dur, 1)
        entry["frames"] = [str(p.relative_to(week.workdir)) for p in frames]

        if drive:
            up = drive.upload(dest, media_folder)
            r["drive_media_url"] = entry["drive_media_url"] = up["webViewLink"]
            entry["frame_links"] = {}
            for p in frames if is_video else []:
                entry["frame_links"][str(p.relative_to(week.workdir))] = drive.upload(p, frames_folder)["webViewLink"]
            r["drive_frames_folder"] = drive.link(frames_folder)
        manifest.append(entry)

    (week.workdir / "manifest.json").write_text(json.dumps(
        {"week": week.label, "window_start": str(week.start), "window_end": str(week.end),
         "drive_week_folder_id": week_folder, "creatives": manifest},
        ensure_ascii=False, indent=1, default=str))
    print(f"✓ скачано {len(manifest)} креативов → manifest.json")
    return rows
