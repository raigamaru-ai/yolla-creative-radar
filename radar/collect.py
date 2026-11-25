"""Модуль 1: сбор креативов конкурентов через Apify и таблица метрик."""
from __future__ import annotations

import copy
import csv
import datetime as dt
import json
import math
import os
import re
import urllib.parse
from pathlib import Path

from .config import Week
from .normalize import COLUMNS, normalize_facebook, normalize_tiktok


def _fill(template, values: dict):
    """Подставляет {placeholders} в шаблон ввода актора; числа остаются числами."""
    if isinstance(template, dict):
        return {k: _fill(v, values) for k, v in template.items()}
    if isinstance(template, list):
        return [_fill(v, values) for v in template]
    if isinstance(template, str):
        m = re.fullmatch(r"\{(\w+)\}", template)
        if m and m[1] in values:
            return values[m[1]]
        return template.format(**values) if "{" in template else template
    return template


def _run_actor(actor: str, run_input: dict) -> list[dict]:
    from apify_client import ApifyClient

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN не задан")
    client = ApifyClient(token)
    run = client.actor(actor).call(run_input=run_input, timeout_secs=1800)
    if not run or run.get("status") != "SUCCEEDED":
        print(f"  ! {actor}: статус {run and run.get('status')}")
    return list(client.dataset(run["defaultDatasetId"]).iterate_items()) if run else []


def fetch(cfg: dict, week: Week, fixtures: Path | None = None) -> list[dict]:
    raw_dir = week.workdir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = week.run_date
    tt_start = week.end - dt.timedelta(days=int(cfg.get("lookback_days_tiktok", 90)))
    rows: list[dict] = []

    for comp in cfg["competitors"]:
        name = comp["name"]
        slug = re.sub(r"\W+", "_", name.lower())
        for platform in ("facebook", "tiktok"):
            acfg = cfg["apify"][platform]
            pcfg = comp.get(platform) or {}
            if not pcfg:
                continue
            raw_file = raw_dir / f"{platform}_{slug}.json"
            if fixtures:
                src = fixtures / f"{platform}_{slug}.json"
                items = json.loads(src.read_text()) if src.exists() else []
            else:
                items = []
                targets = []
                if platform == "facebook":
                    for pid in pcfg.get("page_ids") or []:
                        targets.append(acfg["url_by_page"].format(page_id=pid))
                    if not targets:
                        targets.append(acfg["url_by_query"].format(query=urllib.parse.quote(pcfg["query"])))
                else:
                    targets.append(None)
                for url in targets:
                    values = {
                        "url": url, "query": pcfg.get("query", name), "max_items": int(acfg["max_items"]),
                        "start_date": tt_start.isoformat(), "end_date": week.end.isoformat(),
                    }
                    print(f"→ {platform} / {name}: {url or values['query']}")
                    try:
                        items += _run_actor(acfg["actor"], _fill(copy.deepcopy(acfg["input"]), values))
                    except Exception as e:  # один упавший конкурент не должен ронять весь отчёт
                        print(f"  ! ошибка {platform}/{name}: {e}")
            raw_file.write_text(json.dumps(items, ensure_ascii=False, default=str, indent=1))

            norm = normalize_facebook if platform == "facebook" else normalize_tiktok
            pats = [re.compile(p, re.I) for p in comp.get("match", [])]
            kept = 0
            for it in items:
                try:
                    r = norm(it, name, today)
                except Exception as e:
                    print(f"  ! не разобрал объявление: {e}")
                    continue
                if pats and r["advertiser"] and not any(p.search(r["advertiser"]) for p in pats):
                    continue  # чужой рекламодатель, попавший в поиск по ключевому слову
                rows.append(r)
                kept += 1
            print(f"  {platform}/{name}: получено {len(items)}, оставлено {kept}")
    return rows


def _norm(values: list[float | None]) -> list[float | None]:
    present = [v for v in values if v is not None]
    if not present:
        return [None] * len(values)
    lo, hi = min(present), max(present)
    return [None if v is None else (1.0 if hi == lo else (v - lo) / (hi - lo)) for v in values]


def score_and_filter(rows: list[dict], cfg: dict, week: Week) -> list[dict]:
    """Оставляет креативы, которые крутились в окне, и считает score."""
    seen, out = set(), []
    for r in rows:
        if r["creative_id"] in seen or not r["creative_id"].split("_", 1)[1]:
            continue
        seen.add(r["creative_id"])
        first, last = r["first_seen"], r["last_seen"]
        if first is None or first > week.end:
            continue
        effective_last = min(last or week.run_date, week.run_date) if not r["is_active"] else week.run_date
        if effective_last < week.start:
            continue  # закончился до начала окна
        r["days_running"] = max((effective_last - first).days, 1)
        r["is_new_this_week"] = week.start <= first <= week.end
        out.append(r)

    w = cfg["scoring"]
    reach = _norm([math.log10(r["reach"] + 1) if r["reach"] else None for r in out])
    longev = _norm([math.log10(r["days_running"] + 1) for r in out])
    variations = _norm([math.log10((r["variations"] or 1) + 1) for r in out])
    for r, a, b, c in zip(out, reach, longev, variations):
        parts = [(w["longevity"], b), (w["variations"], c)]
        if a is not None:
            parts.append((w["reach"], a))
        total = sum(wt for wt, _ in parts)
        r["score"] = round(100 * sum(wt * (v or 0) for wt, v in parts) / total, 1)
    out.sort(key=lambda r: r["score"], reverse=True)
    for i, r in enumerate(out, 1):
        r["rank"] = i
    return out


def write_table(rows: list[dict], week: Week) -> Path:
    path = week.workdir / "creatives.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        wr = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        wr.writeheader()
        for r in rows:
            wr.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in COLUMNS})
    return path


def read_table(week: Week) -> list[dict]:
    with open(week.workdir / "creatives.csv", encoding="utf-8") as f:
        return list(csv.DictReader(f))
