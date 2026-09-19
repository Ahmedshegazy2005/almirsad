#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
المرصد — سكربت التحديث اليومي
يجيب أخبار حقيقية من مصادر RSS مباشرة (من غير أي خدمة وسيطة)،
يصنّفها لفئات، ويعمل ملف index.html جاهز للنشر على GitHub Pages.
يشتغل تلقائيًا كل يوم عن طريق GitHub Actions (شوف .github/workflows/update.yml)
"""

import json
import re
import html
from datetime import datetime, timezone

try:
    import feedparser
except ImportError:
    raise SystemExit("Missing dependency 'feedparser'. Install with: pip install feedparser")

MAX_PER_CATEGORY = 10

# ---------------------------------------------------------------------------
# FEEDS — عدّل هنا لو حبيت تضيف أو تشيل مصادر
# forced_category: لو محدد، كل الأخبار من الفيد ده هتتحط في الفئة دي مباشرة
# لو مش محدد، هيتصنف تلقائيًا حسب كلمات مفتاحية في العنوان/الملخص
# ---------------------------------------------------------------------------
FEEDS_EN = [
    {"source": "BBC World",        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",              "forced_category": None},
    {"source": "NPR World",        "url": "https://feeds.npr.org/1004/rss.xml",                        "forced_category": None},
    {"source": "Al Jazeera",       "url": "https://www.aljazeera.com/xml/rss/all.xml",                 "forced_category": None},
    {"source": "BBC Business",     "url": "https://feeds.bbci.co.uk/news/business/rss.xml",             "forced_category": "business"},
    {"source": "CNBC Markets",     "url": "https://www.cnbc.com/id/10001147/device/rss/rss.html",       "forced_category": "business"},
    {"source": "TechCrunch AI",    "url": "https://techcrunch.com/category/artificial-intelligence/feed/", "forced_category": "ai"},
    {"source": "The Verge AI",     "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "forced_category": "ai"},
    {"source": "BBC Sport",        "url": "https://feeds.bbci.co.uk/sport/rss.xml",                     "forced_category": "sports"},
    {"source": "ESPN",             "url": "https://www.espn.com/espn/rss/news",                         "forced_category": "sports"},
]

FEEDS_AR = [
    {"source": "BBC عربي",         "url": "https://feeds.bbci.co.uk/arabic/rss.xml",                    "forced_category": None},
    {"source": "الجزيرة",          "url": "https://www.aljazeera.net/rss/all.xml",                      "forced_category": None},
]

# فئات وكلمات مفتاحية للتصنيف التلقائي (لما مفيش forced_category)
CATEGORY_KEYWORDS = {
    "military": {
        "en": ["military", "army", "troops", "missile", "weapon", "defen", "navy", "air force",
               "airstrike", "air strike", "warplane", "warship", "soldier", "combat"],
        "ar": ["عسكري", "جيش", "صاروخ", "سلاح", "دفاع", "قوات", "غارة", "قصف", "طائرة حربية"],
    },
    "cooperation": {
        "en": ["agreement", "partnership", "cooperation", "treaty", "memorandum", "mou",
               "deal signed", "sign a deal", "strategic partnership", "trade deal"],
        "ar": ["اتفاقية", "تعاون", "شراكة", "مذكرة تفاهم", "توقيع اتفاق"],
    },
    "politics": {
        "en": ["president", "prime minister", "election", "parliament", "government",
               "sanctions", "diplomat", "minister", "vote", "congress", "senate"],
        "ar": ["رئيس", "وزير", "انتخابات", "برلمان", "حكومة", "عقوبات", "دبلوماسي", "مجلس النواب"],
    },
}

CATEGORY_ORDER = ["politics", "military", "cooperation", "ai", "business", "sports", "world"]

# دول للتصنيف حسب الاسم (يُستخدم لتحديد أولوية الظهور حسب اختيار المستخدم)
COUNTRIES = [
    {"code": "EG", "ar": "مصر", "en": "Egypt", "kw": ["egypt", "مصر", "cairo", "القاهرة"]},
    {"code": "SA", "ar": "السعودية", "en": "Saudi Arabia", "kw": ["saudi", "السعودية", "riyadh", "الرياض"]},
    {"code": "AE", "ar": "الإمارات", "en": "UAE", "kw": ["uae", "emirates", "الإمارات", "dubai", "abu dhabi"]},
    {"code": "US", "ar": "الولايات المتحدة", "en": "United States", "kw": ["united states", " u.s.", "washington", "أمريكا", "الولايات المتحدة", "واشنطن"]},
    {"code": "GB", "ar": "بريطانيا", "en": "United Kingdom", "kw": ["britain", "uk ", "united kingdom", "london", "بريطانيا", "لندن"]},
    {"code": "FR", "ar": "فرنسا", "en": "France", "kw": ["france", "paris", "فرنسا", "باريس"]},
    {"code": "DE", "ar": "ألمانيا", "en": "Germany", "kw": ["germany", "berlin", "ألمانيا", "برلين"]},
    {"code": "RU", "ar": "روسيا", "en": "Russia", "kw": ["russia", "moscow", "روسيا", "موسكو"]},
    {"code": "UA", "ar": "أوكرانيا", "en": "Ukraine", "kw": ["ukraine", "kyiv", "أوكرانيا"]},
    {"code": "CN", "ar": "الصين", "en": "China", "kw": ["china", "beijing", "الصين"]},
    {"code": "JP", "ar": "اليابان", "en": "Japan", "kw": ["japan", "tokyo", "اليابان"]},
    {"code": "IN", "ar": "الهند", "en": "India", "kw": ["india", "الهند"]},
    {"code": "TR", "ar": "تركيا", "en": "Turkiye", "kw": ["turkey", "turkiye", "تركيا"]},
    {"code": "IR", "ar": "إيران", "en": "Iran", "kw": ["iran", "tehran", "إيران", "طهران"]},
    {"code": "IL", "ar": "إسرائيل", "en": "Israel", "kw": ["israel", "إسرائيل"]},
    {"code": "PS", "ar": "فلسطين", "en": "Palestine", "kw": ["palestin", "gaza", "فلسطين", "غزة"]},
    {"code": "YE", "ar": "اليمن", "en": "Yemen", "kw": ["yemen", "houthi", "اليمن", "الحوثي"]},
]

# ---------------------------------------------------------------------------


def strip_html(text):
    text = html.unescape(text or "")
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def classify(title, desc, forced_category):
    if forced_category:
        return forced_category
    blob = (title + " " + desc).lower()
    for cat in ("military", "cooperation", "politics"):
        kws = CATEGORY_KEYWORDS[cat]["en"] + CATEGORY_KEYWORDS[cat]["ar"]
        if any(kw in blob for kw in kws):
            return cat
    return "world"


def tag_countries(title, desc):
    blob = (title + " " + desc).lower()
    hits = []
    for c in COUNTRIES:
        if any(kw.lower() in blob for kw in c["kw"]):
            hits.append(c["code"])
    return hits


def fetch_lang(feeds, lang):
    grouped = {cat: [] for cat in CATEGORY_ORDER}
    for feed in feeds:
        try:
            parsed = feedparser.parse(feed["url"])
            if parsed.bozo and not parsed.entries:
                print(f"[warn] failed feed ({lang}): {feed['source']} -> {parsed.bozo_exception}")
                continue
            for entry in parsed.entries[:20]:
                title = strip_html(entry.get("title", ""))
                desc = strip_html(entry.get("summary", entry.get("description", "")))[:240]
                link = entry.get("link", "")
                if not title or not link:
                    continue
                cat = classify(title, desc, feed.get("forced_category"))
                countries = tag_countries(title, desc)
                grouped[cat].append({
                    "title": title,
                    "desc": desc,
                    "source": feed["source"],
                    "link": link,
                    "countries": countries,
                })
        except Exception as e:
            print(f"[warn] error fetching {feed['source']} ({lang}): {e}")

    for cat in grouped:
        grouped[cat] = grouped[cat][:MAX_PER_CATEGORY]
    return grouped


def main():
    print("Fetching English feeds...")
    articles_en = fetch_lang(FEEDS_EN, "en")
    print("Fetching Arabic feeds...")
    articles_ar = fetch_lang(FEEDS_AR, "ar")

    total_en = sum(len(v) for v in articles_en.values())
    total_ar = sum(len(v) for v in articles_ar.values())
    print(f"Collected {total_en} EN items, {total_ar} AR items")

    articles_json = json.dumps({"en": articles_en, "ar": articles_ar}, ensure_ascii=False)
    countries_json = json.dumps(
        [{"code": c["code"], "ar": c["ar"], "en": c["en"]} for c in COUNTRIES],
        ensure_ascii=False,
    )
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with open("template.html", "r", encoding="utf-8") as f:
        template = f.read()

    output = template.replace("__ARTICLES_JSON__", articles_json)
    output = output.replace("__COUNTRIES_JSON__", countries_json)
    output = output.replace("__UPDATED_AT__", updated_at)

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(output)

    print("Wrote index.html")


if __name__ == "__main__":
    main()
