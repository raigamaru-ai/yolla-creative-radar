from __future__ import annotations

import datetime as dt
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Week:
    run_date: dt.date      # день запуска (пятница)
    start: dt.date         # первый день окна
    end: dt.date           # последний день окна (включительно)

    @property
    def label(self) -> str:
        return f"{self.run_date.isoformat()} (окно {self.start:%d.%m}–{self.end:%d.%m.%Y})"

    @property
    def workdir(self) -> Path:
        return ROOT / "work" / self.run_date.isoformat()


def load_config(path: str | None = None) -> dict:
    with open(path or ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    env_folder = os.environ.get("DRIVE_ROOT_FOLDER_ID")
    if env_folder:
        cfg["google_drive"]["root_folder_id"] = env_folder
    return cfg


def make_week(cfg: dict, run_date: str | None = None) -> Week:
    d = dt.date.fromisoformat(run_date) if run_date else dt.date.today()
    end = d - dt.timedelta(days=1)
    start = d - dt.timedelta(days=int(cfg.get("window_days", 7)))
    return Week(run_date=d, start=start, end=end)
