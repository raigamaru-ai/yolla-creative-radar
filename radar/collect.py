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


def _run_actor(actor: str, run_input: dict, max_items: int) -> list[dict]:
    from apify_client import ApifyClient

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        raise SystemExit("APIFY_TOKEN не задан")
    client = ApifyClient(token)
    try:  # max_items — потолок оплачиваемых результатов на стороне Apify
        run = client.actor(actor).call(run_input=run_input, max_items=max_items, timeout_secs=1800)
    except TypeError:
        run = client.actor(actor).call(run_input=run_input, timeout_secs=1800)
    if not run or run.get("status") != "SUCCEEDED":
        print(f"  ! {actor}: статус {run and run.get('status')}")
    return list(client.dataset(run["defaultDatasetId"]).iterate_items()) if run else []


def fetch(cfg: dict, week: Week, fixtures: Path | None = None) -> list[dict]:
    raw_dir = week.workdir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    today = week.run_date
    rows: list[dict] = []
    discovered: dict[str, dict] = {}
    # «Impressions by date» в Ad Library: объявления, у которых были показы в окне
    dates = {"start_date": week.start.isoformat(), "end_date": week.end.isoformat()}

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
                        targets.append(acfg["url_by_page"].format(page_id=pid, **dates))
                    if not targets:
                        targets.append(acfg["url_by_query"].format(query=urllib.parse.quote(pcfg["query"]), **dates))
                else:
                    targets.append(None)
                for url in targets:
                    values = {
                        "url": url, "query": pcfg.get("query", name), "max_items": int(acfg["max_items"]),
                        "start_date": week.start.isoformat(), "end_date": week.end.isoformat(),
                    }
                    print(f"→ {platform} / {name}: {url or values['query']}")
                    try:
                        run_input = _fill(copy.deepcopy(acfg["input"]), values)
                        advertisers = pcfg.get("advertisers") or []
                        if platform == "tiktok" and advertisers:  # точный поиск по аккаунтам рекламодателя
                            run_input.pop("advertiserName", None)
                            run_input["advertisers"] = [{"id": str(a["id"]), "name": a["name"]} for a in advertisers]
                        cap = int(acfg["max_items"]) * (len(advertisers) if platform == "tiktok" and advertisers else 1)
                        items += _run_actor(acfg["actor"], run_input, cap)
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
                if r.get("unavailable"):
                    continue  # объявление удалено из библиотеки
                if pats and r["advertiser"] and not any(p.search(r["advertiser"]) for p in pats):
                    continue  # чужой рекламодатель, попавший в поиск по ключевому слову
                rows.append(r)
                kept += 1
                if r.get("page_id") and platform == "facebook":
                    discovered.setdefault(name, {})[r["page_id"]] = r["advertiser"]
            print(f"  {platform}/{name}: получено {len(items)}, оставлено {kept}")
    if discovered:
        (week.workdir / "discovered_page_ids.json").write_text(json.dumps(discovered, ensure_ascii=False, indent=1))
        print("ID страниц конкурентов в Facebook (впишите в config.yaml → page_ids):")
        for comp, pages in discovered.items():
            print(f"  {comp}: " + ", ".join(f"{pid} ({pn})" for pid, pn in pages.items()))
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


def probe(cfg: dict, only: str | None = None, days: int = 90, max_items: int = 40) -> None:
    """Разведка: под какими страницами FB и аккаунтами TikTok рекламируются конкуренты.

    Ищет широко (любой порядок слов, последние `days` дней), ничего не пишет в Drive.
    Печатает рекламодателей с числом объявлений: нужные ID вписать в config.yaml
    (facebook.page_ids, tiktok.advertisers) и сузить match.
    """
    import collections

    end = dt.date.today()
    start = end - dt.timedelta(days=days)
    fb = cfg["apify"]["facebook"]
    tt = cfg["apify"]["tiktok"]
    for comp in cfg["competitors"]:
        if only and comp["name"].lower() != only.lower():
            continue
        q = (comp.get("facebook") or {}).get("query", comp["name"])
        pats = [re.compile(p, re.I) for p in comp.get("match", [])]
        print(f"\n=== {comp['name']} (запрос «{q}», {start} … {end})")

        url = ("https://www.facebook.com/ads/library/?active_status=all&ad_type=all&country=ALL&media_type=all"
               f"&q={urllib.parse.quote(q)}&search_type=keyword_unordered"
               "&sort_data[mode]=total_impressions&sort_data[direction]=desc"
               f"&start_date[min]={start}&start_date[max]={end}")
        try:
            items = _run_actor(fb["actor"], {**_fill(copy.deepcopy(fb["input"]), {"url": url, "max_items": max_items})},
                               max_items)
        except Exception as e:
            items = []
            print(f"  ! facebook: {e}")
        pages = collections.Counter()
        sample = {}
        for it in items:
            try:
                r = normalize_facebook(it, comp["name"], end)
            except Exception:
                continue
            key = (r["page_id"], r["advertiser"])
            pages[key] += 1
            sample.setdefault(key, (r["ad_text"] or r["headline"])[:90])
        print(f"  Facebook: {len(items)} объявлений, страниц: {len(pages)}")
        for (pid, name), n in pages.most_common(15):
            ok = "✓" if pats and any(p.search(name or "") for p in pats) else " "
            print(f"   {ok} page_id {pid or '—'} · {name or '—'} · {n} объявл. · {sample[(pid, name)]}")

        tq = (comp.get("tiktok") or {}).get("query", comp["name"])
        run_input = _fill(copy.deepcopy(tt["input"]), {"query": tq, "start_date": start.isoformat(),
                                                       "end_date": end.isoformat()})
        try:
            items = _run_actor(tt["actor"], run_input, max_items)
        except Exception as e:
            items = []
            print(f"  ! tiktok: {e}")
        accs = collections.Counter()
        for it in items:
            try:
                r = normalize_tiktok(it, comp["name"], end)
            except Exception:
                continue
            accs[(r.get("advertiser_id") or "", r["advertiser"])] += 1
        print(f"  TikTok (EU): {len(items)} объявлений, рекламодателей: {len(accs)}")
        for (aid, name), n in accs.most_common(15):
            ok = "✓" if pats and any(p.search(name or "") for p in pats) else " "
            print(f"   {ok} advertiser {{id: \"{aid}\", name: \"{name}\"}} · {n} объявл.")
