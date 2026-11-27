"""Приведение выдачи разных акторов Apify к единой строке таблицы.

Акторы (и сами Ad Library) меняют имена полей, поэтому ищем значения по нескольким
путям, сравнивая ключи без учёта регистра и подчёркиваний: start_date == startDate.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any, Iterable

COLUMNS = [
    "creative_id", "platform", "competitor", "advertiser", "first_seen", "last_seen",
    "is_active", "days_running", "is_new_this_week", "reach", "impressions_lower",
    "impressions_upper", "variations", "placements", "countries", "format",
    "headline", "ad_text", "cta", "landing_url", "media_url", "thumbnail_url",
    "library_url", "score", "rank", "drive_media_url", "drive_frames_folder",
]


def _k(key: str) -> str:
    return re.sub(r"[_\-\s]", "", str(key)).lower()


def get(d: Any, *paths: str, default=None):
    """get(item, "snapshot.videos.0.video_hd_url", "videoUrl") -> первое непустое значение."""
    for path in paths:
        cur = d
        ok = True
        for part in path.split("."):
            if isinstance(cur, list):
                if part.isdigit() and int(part) < len(cur):
                    cur = cur[int(part)]
                    continue
                ok = False
                break
            if not isinstance(cur, dict):
                ok = False
                break
            wanted = _k(part)
            match = next((v for k, v in cur.items() if _k(k) == wanted), None)
            if match is None:
                ok = False
                break
            cur = match
        if ok and cur not in (None, "", [], {}):
            return cur
    return default


def find_url(d: Any, patterns: Iterable[str]) -> str | None:
    """Рекурсивно ищет первую строку-URL, где встречается один из паттернов (.mp4, video …)."""
    pats = [re.compile(p, re.I) for p in patterns]

    def walk(x, key=""):
        if isinstance(x, dict):
            for k, v in x.items():
                r = walk(v, k)
                if r:
                    return r
        elif isinstance(x, list):
            for v in x:
                r = walk(v, key)
                if r:
                    return r
        elif isinstance(x, str) and x.startswith("http"):
            if any(p.search(x) or p.search(key) for p in pats):
                return x
        return None

    return walk(d)


def parse_date(v) -> dt.date | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        n = float(v)
        if n > 1e12:
            n /= 1000
        return dt.datetime.utcfromtimestamp(n).date()
    s = str(v).strip()
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)  # ISO, в т.ч. с временем
    if m:
        return dt.date(int(m[1]), int(m[2]), int(m[3]))
    for fmt in ("%d/%m/%Y", "%b %d, %Y", "%d %b %Y", "%B %d, %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def to_num(v) -> float | None:
    if v in (None, ""):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, dict):  # {"lower_bound": 1000, "upper_bound": 5000}
        lo = to_num(get(v, "lowerBound", "lower", "min"))
        hi = to_num(get(v, "upperBound", "upper", "max"))
        vals = [x for x in (lo, hi) if x is not None]
        return sum(vals) / len(vals) if vals else None
    s = str(v).replace(",", "").replace(" ", "").upper()
    m = re.match(r"^([\d.]+)([KM]?)", s)
    if not m:
        return None
    n = float(m[1])
    return n * {"K": 1e3, "M": 1e6}.get(m[2], 1)


def _text(v) -> str:
    if isinstance(v, dict):
        v = get(v, "text", "markup.html", "body")
    if isinstance(v, list):
        v = " ".join(_text(x) for x in v)
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return "" if re.fullmatch(r"(\{\{[^}]*\}\}\s*)+", s) else s  # шаблоны каталожных объявлений


def _list(v, limit: int = 15) -> str:
    if isinstance(v, (list, tuple)):
        return ", ".join(str(x.get("name", x)) if isinstance(x, dict) else str(x) for x in v[:limit])
    return str(v or "")


def normalize_facebook(item: dict, competitor: str, today: dt.date) -> dict:
    snap = get(item, "snapshot") or {}
    ad_id = str(get(item, "adArchiveID", "adArchiveId", "adId", "id") or "")
    first = parse_date(get(item, "startDate", "startDateFormatted", "adDeliveryStartTime", "firstShown"))
    last = parse_date(get(item, "endDate", "endDateFormatted", "adDeliveryStopTime", "lastShown"))
    active = bool(get(item, "isActive", "active", default=last is None or last >= today))
    video = get(snap, "videos.0.videoHdUrl", "videos.0.videoSdUrl", "cards.0.videoHdUrl",
                "cards.0.videoSdUrl") or find_url(snap, [r"\.mp4", r"video"])
    image = get(snap, "images.0.originalImageUrl", "images.0.resizedImageUrl",
                "cards.0.originalImageUrl", "cards.0.resizedImageUrl")
    thumb = get(snap, "videos.0.videoPreviewImageUrl", "cards.0.videoPreviewImageUrl") or image
    reach = to_num(get(item, "euTotalReach", "aaaInfo.euTotalReach", "reachEstimate",
                       "totalReach", "reach"))
    imp = get(item, "impressionsWithIndex", "impressions") or {}
    return {
        "creative_id": f"fb_{ad_id}",
        "page_id": str(get(item, "pageID", "pageId", "snapshot.pageId") or ""),
        "platform": "facebook",
        "competitor": competitor,
        "advertiser": _text(get(item, "pageName", "snapshot.pageName", "advertiserName")),
        "first_seen": first,
        "last_seen": last,
        "is_active": active,
        "reach": reach,
        "impressions_lower": to_num(get(imp, "lowerBound", "impressionsText")),
        "impressions_upper": to_num(get(imp, "upperBound")),
        "variations": to_num(get(item, "collationCount", "collation_count", "adsCount")) or 1,
        "placements": _list(get(item, "publisherPlatform", "publisherPlatforms")),
        "countries": _list(get(item, "targetedOrReachedCountries", "aaaInfo.targetLocations", "countries")),
        "format": "video" if video else ("image" if image else _text(get(snap, "displayFormat"))),
        "headline": _text(get(snap, "title", "cards.0.title")),
        "ad_text": _text(get(snap, "body", "cards.0.body"))[:1500],
        "cta": _text(get(snap, "ctaText", "cards.0.ctaText")),
        "landing_url": get(snap, "linkUrl", "cards.0.linkUrl") or "",
        "media_url": video or image or "",
        "thumbnail_url": thumb or "",
        "library_url": f"https://www.facebook.com/ads/library/?id={ad_id}" if ad_id else "",
    }


def _band(v) -> float | None:
    """'1M-10M' -> среднее границ."""
    if not v:
        return None
    parts = [to_num(x) for x in re.split(r"\s*[-–]\s*", str(v)) if x]
    parts = [x for x in parts if x is not None]
    return sum(parts) / len(parts) if parts else None


def normalize_tiktok(item: dict, competitor: str, today: dt.date) -> dict:
    """Поля lexis-solutions/tiktok-ads-scraper (adId, adStartDate…) и запасные имена других акторов."""
    ad_id = str(get(item, "adId", "ad_id", "id") or "")
    first = parse_date(get(item, "adStartDate", "firstShownDate", "firstShown", "startDate"))
    last = parse_date(get(item, "adEndDate", "lastShownDate", "lastShown", "endDate"))
    images = get(item, "adImageUrls", "imageUrls") or []
    video = (get(item, "adVideoUrl", "videoUrls.0", "videoUrl", "video.url")
             or find_url({k: v for k, v in item.items() if "cover" not in k.lower()}, [r"\.mp4", r"video_mp4"]))
    image = (images[0] if isinstance(images, list) and images else None) or get(item, "imageUrl")
    cover = get(item, "adVideoCover", "coverUrl", "videoCover") or image
    lo, hi = to_num(get(item, "estimatedAudienceMin")), to_num(get(item, "estimatedAudienceMax"))
    reach = ((lo + hi) / 2 if lo is not None and hi is not None
             else _band(get(item, "adEstimatedAudience", "estimatedAudience", "adImpressions")))
    by_loc = get(item, "targetingByLocation")
    if isinstance(by_loc, list):
        countries = [x.get("region") for x in by_loc if isinstance(x, dict) and x.get("region")]
    elif isinstance(get(item, "impressionsByCountry"), dict):
        countries = list(get(item, "impressionsByCountry").keys())
    else:
        countries = get(item, "regions", "countries")
    ad_type = str(get(item, "adType") or "")
    return {
        "creative_id": f"tt_{ad_id}",
        "advertiser_id": str(get(item, "advertiserId") or ""),
        "unavailable": str(get(item, "status") or "").lower() == "unavailable",
        "platform": "tiktok",
        "competitor": competitor,
        "advertiser": _text(get(item, "advertiserName", "advertiserPaidForBy", "paidForBy", "accountUsername",
                                "advertiserTtUserId.display_name")),
        "first_seen": first,
        "last_seen": last,
        "is_active": last is None or last >= today - dt.timedelta(days=2),
        "reach": reach,
        "impressions_lower": None,
        "impressions_upper": None,
        "variations": 1,
        "placements": "tiktok",
        "countries": _list(countries),
        "format": "video" if video or ad_type == "2" else ("image" if image or ad_type == "3" else ""),
        "headline": "",
        "ad_text": _text(get(item, "adTitle", "adText", "caption"))[:1500],
        "cta": _text(get(item, "callToAction", "cta")),
        "landing_url": get(item, "adLandingUrl", "externalUrl", "landingPageUrl") or "",
        "media_url": video or image or "",
        "thumbnail_url": cover or "",
        "library_url": get(item, "adUrl") or (f"https://library.tiktok.com/ads/detail/?ad_id={ad_id}" if ad_id else ""),
    }
