"""Build crawlable article pages and index from the Decap Markdown sources."""
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
import hashlib
import json
import re
import math
import xml.etree.ElementTree as ET

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "content/posts"
BLOG = ROOT / "blog"
BASE = "https://mangen.jp"
CATEGORY_LABELS = {
    "a": "包车指南",
    "b": "旅行指南",
    "c": "知识科普",
    "d": "线路规划",
    "e": "公司动态",
}


def text(value):
    return escape(str(value or ""), quote=True)


def normalize_markdown_body(source):
    """Repair common CMS paste/list issues before rendering Markdown."""
    source = source.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")

    # Decap users sometimes put a bold list label and its full-width colon text
    # in separate paragraphs. Keep them in one list item so markers do not leak.
    source = re.sub(
        r"(?m)^[*+-]\s+\*\*([^*\n]+)\*\*\s*\n\s*\n[ \t]*：\s*([^\n]+)",
        lambda match: f"- **{match.group(1).rstrip('：:')}：** {match.group(2).strip()}",
        source,
    )

    # Python-Markdown requires a blank line between a normal paragraph and a
    # following list. The CMS preview is more forgiving, so normalize the gap.
    lines = source.split("\n")
    normalized = []
    bullet = re.compile(r"^\s*[-*+]\s+")
    for line in lines:
        if bullet.match(line) and normalized and normalized[-1].strip() and not bullet.match(normalized[-1]):
            normalized.append("")
        normalized.append(line)
    return "\n".join(normalized).strip() + "\n"


def render_markdown(source, path):
    normalized = normalize_markdown_body(source)
    if re.search(r"(?m)^\s*[：。；，]\s*(?:$|\*\*)", normalized):
        raise ValueError(f"孤立的中文标点，请在 CMS 中合并到上一行: {path}")
    rendered = markdown.markdown(normalized, extensions=["tables", "fenced_code", "sane_lists", "toc"])
    if re.search(r"<p>\s*[-*+]\s+(?:<strong>|\S)", rendered):
        raise ValueError(f"列表符号被渲染成正文，请检查列表格式: {path}")
    return rendered


_REVIEW_PREFIX = re.compile(r"^(资料核对日期|资料核对|信息核查日期|信息核验日期|信息核验)[：:]\s*")
_REVIEW_KEEP = re.compile(r"本文|不代表|不构成|不是|不宣称|仅为|非实时|不把|并不|本次补充")
_REVIEW_GENERIC = re.compile(r"请再核对|官方|为准|可能调整|可能变化|可能变动|路线为规划建议")
EDITORIAL_LASTMOD = "2026-10-26T00:00:00+09:00"
SERVICE_AREAS = {"东京・关东", "大阪・关西"}


def _review_date(stamp):
    """The Japan-time calendar date written in a source note. No date is invented."""
    matched = re.search(r"日本时间为\s*(\d{4})年(\d{1,2})月(\d{1,2})日", stamp)
    if matched:
        return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3))).isoformat()
    matched = re.search(r"日本时间为\s*(\d{1,2})月(\d{1,2})日", stamp)
    if matched:
        year = re.search(r"(\d{4})-\d{2}-\d{2}", stamp)
        if not year:
            return ""
        return date(int(year.group(1)), int(matched.group(1)), int(matched.group(2))).isoformat()
    matched = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", stamp)
    if matched:
        return date(int(matched.group(1)), int(matched.group(2)), int(matched.group(3))).isoformat()
    matched = re.search(r"(\d{4}-\d{2}-\d{2})", stamp)
    return matched.group(1) if matched else ""


def detach_review_boilerplate(source):
    """Lift one repeated closing note out of an article. Source links and specific caveats stay."""
    stripped = source.replace("\r\n", "\n").strip("\n")
    if not stripped:
        return source, ""
    parts = re.split(r"\n\s*\n", stripped)
    last = parts[-1].strip()
    if not _REVIEW_PREFIX.match(last):
        return source, ""
    stamp, _separator, rest = last.partition("。")
    reviewed = _review_date(stamp)
    if not reviewed:
        return source, ""
    kept = []
    for sentence in [item.strip() for item in rest.split("。") if item.strip()]:
        if _REVIEW_KEEP.search(sentence) or re.search(r"\d", sentence):
            kept.append(sentence)
        elif _REVIEW_GENERIC.search(sentence):
            continue
        else:
            kept.append(sentence)
    if kept:
        parts[-1] = "。".join(kept) + "。"
    else:
        parts.pop()
    return "\n\n".join(parts).strip() + "\n", reviewed


def render_review_note(reviewed):
    if not reviewed:
        return ""
    shown = text(reviewed)
    return (
        '<aside class="source-note"><p>资料核对：'
        f'<time datetime="{shown}">{shown}</time>'
        "（日本时间）。营业、交通、商品及现场规则可能调整，出行前请再核对文中官方来源。</p></aside>"
    )


def render_service_block(post):
    """Existing homepage copy, only for guides whose region is Tokyo/Kanto or Osaka/Kansai."""
    if not set(post.get("regions") or []) & SERVICE_AREAS:
        return ""
    return (
        '<aside class="guide-service" aria-label="用车服务">'
        "<h2>用车服务</h2><ul>"
        '<li><a href="/zh#services">用车服务</a><p>为访日旅客与商务人士提供在日出行用车。</p></li>'
        '<li><a href="/zh#fleet">车型阵容</a><p>按人数与用途挑选合适的车型。</p></li>'
        '<li><a href="/zh#contact">联系我们</a></li>'
        "</ul></aside>"
    )


def load_post(path):
    source = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", source, re.S)
    if not match:
        raise ValueError(f"Missing YAML front matter: {path}")
    metadata = yaml.safe_load(match.group(1)) or {}
    slug = path.stem
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError(f"Invalid slug: {path}")
    published = metadata.get("date")
    if isinstance(published, (date, datetime)):
        published = published.isoformat()[:10]
    body, reviewed = detach_review_boilerplate(match.group(2))
    stated = str(metadata.get("reviewed") or "")[:10]
    if stated:
        date.fromisoformat(stated)
    if reviewed and stated and reviewed != stated:
        raise ValueError(f"Review date disagrees with the closing note in {slug}: {stated} / {reviewed}")
    metadata["reviewed"] = stated or reviewed
    return metadata, slug, str(published), render_markdown(body, path)


PER_PAGE = 12
FEED_LIMIT = 50
JST = timezone(timedelta(hours=9))
# Shared by the Chinese homepage and /blog/ editor's picks: one lead plus four rows.
GUIDE_PICK_COUNT = 5
HOME_GUIDE_START = "<!-- home-guides:start -->"
HOME_GUIDE_END = "<!-- home-guides:end -->"
RELATED_MIN = 3
RELATED_MAX = 5
_THUMB_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif"}
_BODY_LINK = re.compile(r"(?:\]\(|https://mangen\.jp)/blog/([a-z0-9-]+)")
TOPICS = ["行程路线", "交通接送", "住宿美食", "购物退税", "季节活动", "礼仪与生活"]
# Older labels still publish into the six topics, so a batch written with the previous names does not break the build.
TOPIC_ALIASES = {
    "景点行程": "行程路线", "目的地攻略": "行程路线",
    "交通与接送": "交通接送", "交通出行": "交通接送", "机场与出入境": "交通接送",
    "旅行实用": "礼仪与生活", "万源动态": "礼仪与生活",
}
DESTINATIONS = ["东京", "京都", "大阪", "奈良", "富士山", "箱根", "北海道", "札幌", "小樽", "函馆", "二世古", "名古屋", "福冈", "冲绳", "那霸", "神户", "广岛", "宫岛", "镰仓", "江之岛", "横滨", "宇治", "川越", "金泽", "高山", "日光", "松本", "姬路", "仙台", "长崎", "静冈", "熊本", "长野", "滋贺", "和歌山", "高松", "松山", "热海", "尾道", "鸟取", "青森", "鹿儿岛", "别府", "新潟", "富山", "福井", "盛冈", "德岛", "松江", "高知", "弘前", "秋田", "山形", "上高地", "长瀞", "足利", "箕面", "高尾山", "冈山", "仓敷", "羽田", "成田", "三重", "三重・伊势"]
# Visible guide filters. Membership follows where the articles actually are; empty groups are omitted.
REGION_GROUPS = [
    ("东京・关东", ("东京", "横滨", "镰仓", "江之岛", "川越", "箱根", "富士山", "日光", "高尾山", "长瀞", "足利", "热海", "羽田", "成田")),
    ("大阪・关西", ("大阪", "神户", "奈良", "姬路", "和歌山", "滋贺", "箕面")),
    ("京都", ("京都", "宇治")),
    ("北海道", ("北海道", "札幌", "小樽", "函馆", "二世古")),
    ("冲绳", ("冲绳", "那霸")),
]
OTHER_REGION = "其他"
# Public hub URLs. Slugs stay in ASCII; the visible name is the taxonomy label.
TOPIC_SLUGS = {
    "行程路线": "routes",
    "交通接送": "transfers",
    "住宿美食": "food-and-stay",
    "购物退税": "tax-free-shopping",
    "季节活动": "seasons",
    "礼仪与生活": "etiquette",
}
REGION_SLUGS = {
    "东京・关东": "tokyo-kanto",
    "大阪・关西": "osaka-kansai",
    "京都": "kyoto",
    "北海道": "hokkaido",
    "冲绳": "okinawa",
    "其他": "other",
}
REGION_CHIP_LIMIT = 6
_GROUPED_PLACES = {place for _, places in REGION_GROUPS for place in places}
if _GROUPED_PLACES - set(DESTINATIONS):
    raise ValueError(f"Region places missing from DESTINATIONS: {sorted(_GROUPED_PLACES - set(DESTINATIONS))}")
TOPIC_FALLBACK = {"a": "交通接送", "b": "礼仪与生活", "c": "交通接送", "d": "行程路线", "e": "礼仪与生活"}
# Longer aliases first. A mention used only as a return/transfer point is not the article's region.
PLACE_RULES = [("伊势神宫", "三重・伊势"), ("名花之里", "三重"), ("河口湖", "富士山"), ("山中湖", "富士山"), ("高尾山", "高尾山"), ("二世古", "二世古"), ("函馆", "函馆"), ("小樽", "小樽"), ("札幌", "札幌"), ("镰仓", "镰仓"), ("江之岛", "江之岛"), ("宫岛", "宫岛"), ("广岛", "广岛"), ("神户", "神户"), ("横滨", "横滨"), ("宇治", "宇治"), ("川越", "川越"), ("金泽", "金泽"), ("高山", "高山"), ("日光", "日光"), ("松本", "松本"), ("姬路", "姬路"), ("仙台", "仙台"), ("长崎", "长崎"), ("静冈", "静冈"), ("熊本", "熊本"), ("长野", "长野"), ("滋贺", "滋贺"), ("和歌山", "和歌山"), ("高松", "高松"), ("松山", "松山"), ("热海", "热海"), ("尾道", "尾道"), ("鸟取", "鸟取"), ("青森", "青森"), ("鹿儿岛", "鹿儿岛"), ("别府", "别府"), ("新潟", "新潟"), ("富山", "富山"), ("福井", "福井"), ("盛冈", "盛冈"), ("德岛", "德岛"), ("松江", "松江"), ("高知", "高知"), ("弘前", "弘前"), ("秋田", "秋田"), ("山形", "山形"), ("上高地", "上高地"), ("长瀞", "长瀞"), ("足利", "足利"), ("箕面", "箕面"), ("那霸", "那霸"), ("USJ", "大阪"), ("迪士尼", "东京"), ("冈山", "冈山"), ("仓敷", "仓敷"), ("羽田", "羽田"), ("成田", "成田"), ("富士山", "富士山"), ("箱根", "箱根"), ("名古屋", "名古屋"), ("冲绳", "冲绳"), ("福冈", "福冈"), ("奈良", "奈良"), ("京都", "京都"), ("大阪", "大阪"), ("东京", "东京"), ("北海道", "北海道")]


def canonical_topic(raw, category):
    topic = raw or TOPIC_FALLBACK.get(category, "礼仪与生活")
    topic = TOPIC_ALIASES.get(topic, topic)
    return topic


def place_mentioned(title, alias):
    if alias not in title:
        return False
    cleaned = title
    for phrase in (f"{alias}往返", f"往返{alias}", f"回{alias}", f"从{alias}", f"{alias}出发"):
        cleaned = cleaned.replace(phrase, "")
    return alias in cleaned


def infer_places(title):
    found = []
    for alias, label in PLACE_RULES:
        if place_mentioned(title, alias):
            found.append((title.find(alias), label))
    places = []
    for _, label in sorted(found):
        if label not in places:
            places.append(label)
    return places


def resolve_destinations(raw, title):
    """Drop the retired 全日本 label. Empty metadata falls back to places named in the title."""
    places = [place for place in (raw or []) if place != "全日本"]
    if raw and places:
        return places
    return infer_places(title)


def jst_timestamp(value):
    """ISO 8601 with +09:00. A calendar date is midnight in Japan, not the build clock."""
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=JST)
        return moment.astimezone(JST).isoformat(timespec="seconds")
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=JST).isoformat(timespec="seconds")
    text_value = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text_value):
        return f"{text_value}T00:00:00+09:00"
    match = re.fullmatch(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2})(?::(\d{2}))?(Z|[+-]\d{2}:\d{2})?", text_value)
    if not match:
        raise ValueError(f"Unusable timestamp: {value}")
    day, hm, sec, zone = match.groups()
    sec = sec or "00"
    if not zone:
        return f"{day}T{hm}:{sec}+09:00"
    if zone == "Z":
        zone = "+00:00"
    moment = datetime.fromisoformat(f"{day}T{hm}:{sec}{zone}")
    return moment.astimezone(JST).isoformat(timespec="seconds")


def plain(source):
    from html import unescape
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(source or "")))).strip()


def post_record(post):
    data, slug, published, body = post
    title = data.get("title_i18n", {}).get("zh") or data.get("title") or slug
    excerpt = plain(data.get("excerpt_i18n", {}).get("zh") or data.get("excerpt") or "")
    topic = canonical_topic(data.get("topic"), data.get("category"))
    if topic not in TOPICS:
        raise ValueError(f"Unsupported topic in {slug}: {topic}")
    destinations = resolve_destinations(data.get("destinations"), title)
    if not isinstance(destinations, list) or any(place not in DESTINATIONS for place in destinations):
        raise ValueError(f"Unsupported destinations in {slug}: {destinations}")
    destinations = list(dict.fromkeys(destinations))
    cover = data.get("cover_image") or ""
    if cover and (not cover.startswith("/assets/uploads/") or ".." in cover.split("/") or any(c in cover for c in '?#\\')):
        raise ValueError(f"Invalid cover image path: {slug}")
    source = data.get("cover_source") or ""
    if source and not re.match(r"^https?://[^\s]+$", source):
        raise ValueError(f"Invalid cover source URL: {slug}")
    for field in ("cover_creator_url", "cover_license_url"):
        value = data.get(field) or ""
        if value and not re.match(r"^https?://[^\s]+$", value):
            raise ValueError(f"Invalid {field} URL: {slug}")
    modified = str(data.get("updated") or published)[:10]
    # Do not invent update dates from a build or deployment date.
    date.fromisoformat(published)
    date.fromisoformat(modified)
    if modified < published:
        raise ValueError(f"Update date precedes publication: {slug}")
    featured_until = str(data.get("featured_until") or "")[:10]
    if featured_until:
        date.fromisoformat(featured_until)
    featured_order = data.get("featured_order")
    if featured_order in (None, ""):
        featured_order = None
    elif isinstance(featured_order, bool) or not isinstance(featured_order, (int, float)) or int(featured_order) != featured_order:
        raise ValueError(f"Invalid featured_order in {slug}: {featured_order}")
    else:
        featured_order = int(featured_order)
    reviewed = str(data.get("reviewed") or "")[:10]
    if reviewed:
        date.fromisoformat(reviewed)
    raw_tags = data.get("tags") or []
    if isinstance(raw_tags, str):
        raw_tags = [part.strip() for part in re.split(r"[,，]", raw_tags) if part.strip()]
    elif isinstance(raw_tags, list):
        raw_tags = [str(part).strip() for part in raw_tags if str(part).strip()]
    else:
        raw_tags = []
    return {"slug": slug, "url": f"/blog/{slug}", "title": title, "excerpt": excerpt,
            "date": published, "updated": modified, "reviewed": reviewed,
            "published_at": jst_timestamp(data.get("date") or published),
            "updated_at": jst_timestamp(data.get("updated") or data.get("date") or published),
            "category": CATEGORY_LABELS.get(data.get("category"), "旅行指南"),
            "topic": topic, "destinations": destinations, "regions": regions_for(destinations),
            "featured": bool(data.get("featured")),
            "featured_order": featured_order, "featured_until": featured_until,
            "cover": cover, "coverAlt": data.get("cover_alt") or title,
            "coverCredit": data.get("cover_credit") or "", "coverSource": source,
            "coverLicense": data.get("cover_license") or "", "coverLicenseUrl": data.get("cover_license_url") or "",
            "coverCreatorUrl": data.get("cover_creator_url") or "", "coverCaption": data.get("cover_caption") or "",
            "coverChanges": data.get("cover_changes") or "",
            "tags": list(dict.fromkeys(raw_tags)),
            "search": plain(title + " " + excerpt + " " + body),
            "body_links": list(dict.fromkeys(_BODY_LINK.findall(body)))}


def page_url(number):
    return "/blog/" if number == 1 else f"/blog/page/{number}/"


def render_template(template, values):
    # One pass prevents user metadata containing {{TOKENS}} from being interpreted.
    return re.sub(r"\{\{([A-Z_]+)\}\}", lambda m: str(values.get(m[1], m[0])), template)


def render_credit(post):
    if not post["cover"]:
        return ""
    blob = " ".join(part for part in (post["coverCredit"], post["coverLicense"], post["coverCaption"], post["coverChanges"]) if part)
    third_party = bool(post["coverSource"] or post["coverLicenseUrl"] or post["coverCreatorUrl"])
    if not third_party and ("AI" in blob or "原创图示" in blob or "原创示意" in blob):
        return "示意图（AI 辅助制作），非实景，仅供参考。"
    parts = []
    if post["coverCaption"]: parts.append(text(post["coverCaption"]))
    for label, url in [(post["coverCredit"], post["coverCreatorUrl"]), ("来源" if post["coverSource"] else "", post["coverSource"]), (post["coverLicense"], post["coverLicenseUrl"])]:
        if label:
            parts.append(f'<a href="{text(url)}" rel="noopener noreferrer">{text(label)}</a>' if url else text(label))
    if post["coverChanges"]: parts.append(text(post["coverChanges"]))
    return ' · '.join(parts)


def place_region(place):
    for label, places in REGION_GROUPS:
        if place in places:
            return label
    return OTHER_REGION


def regions_for(destinations):
    labels = []
    for label, places in REGION_GROUPS:
        if any(place in places for place in destinations):
            labels.append(label)
    if any(place not in _GROUPED_PLACES for place in destinations):
        labels.append(OTHER_REGION)
    return labels


def visible_region_chips(records):
    """At most six regions that have articles. Ties keep the geographic order above."""
    counts = {label: 0 for label, _ in REGION_GROUPS}
    counts[OTHER_REGION] = 0
    for post in records:
        for label in regions_for(post["destinations"]):
            counts[label] += 1
    ranked = [(counts[label], index, label) for index, (label, _) in enumerate(REGION_GROUPS) if counts[label]]
    if counts[OTHER_REGION]:
        ranked.append((counts[OTHER_REGION], len(REGION_GROUPS), OTHER_REGION))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    chosen = {label for _, _, label in ranked[:REGION_CHIP_LIMIT]}
    ordered = [label for label, _ in REGION_GROUPS if label in chosen]
    if OTHER_REGION in chosen:
        ordered.append(OTHER_REGION)
    return ordered


def taxonomy_html(post):
    topic = text(post["topic"])
    place = post["destinations"][0] if post["destinations"] else ""
    if not place:
        return topic
    return f'{text(place)}<span> · </span>{topic}'


def render_card(post):
    cover = (f'<div class="guide-image"><img src="{text(post["cover"])}" alt="{text(post["coverAlt"])}" loading="lazy" decoding="async" width="900" height="600"></div>' if post["cover"] else "")
    return (f'<article class="guide-entry"><a class="guide-card{ " guide-card--text" if not cover else ""}" href="{text(post["url"])}">{cover}'
            f'<div class="guide-copy"><div class="guide-taxonomy">{taxonomy_html(post)}</div>'
            f'<h3>{text(post["title"])}</h3><p>{text(post["excerpt"])}</p>'
            f'<time datetime="{text(post["date"])}">{text(post["date"].replace("-", "."))}</time></div></a>' +
            (f'<p class="image-credit">{render_credit(post)}</p>' if cover else '') + '</article>')


def journal_today():
    """Calendar day in Japan, so a rebuild on the same date keeps the same picks."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Asia/Tokyo")).date()
    except Exception:
        return datetime.now(timezone(timedelta(hours=9))).date()


def usable_thumbnail(post):
    """Raster cover shipped with the site. Empty covers and vector placeholders are not cards."""
    cover = post.get("cover") or ""
    return cover.startswith("/assets/") and ".." not in cover.split("/") and Path(cover).suffix.lower() in _THUMB_EXT


def related_posts(records, post, limit=3):
    """Same related-reading order the article pages emit. Date then slug breaks ties."""
    others = sorted((item for item in records if item["slug"] != post["slug"]),
                    key=lambda item: (item["date"], item["slug"]), reverse=True)
    return sorted(others, key=lambda item: (
        bool(set(item.get("destinations") or []) & set(post.get("destinations") or []) - {"全日本"}),
        item.get("topic") == post.get("topic"),
        bool(item.get("featured"))), reverse=True)[:limit]


def inbound_link_counts(records, day):
    """How many already-published articles link here, via the body or related reading.

    The rotating picks are not counted: those links are what this ranking is choosing.
    The latest-article index links every article once, so it does not change the order.
    """
    iso = day.isoformat() if isinstance(day, date) else str(day)
    visible = [post for post in records if post.get("date", "") <= iso]
    counts = {post["slug"]: 0 for post in visible}
    for post in visible:
        targets = {slug for slug in (post.get("body_links") or []) if slug in counts and slug != post["slug"]}
        for item in related_posts(visible, post):
            targets.add(item["slug"])
        for slug in targets:
            counts[slug] += 1
    return counts


def _ranked_guides(records, day):
    counts = inbound_link_counts(records, day)
    pool = [post for post in records if post.get("date", "") <= day.isoformat() and usable_thumbnail(post)]
    pool.sort(key=lambda post: (counts.get(post["slug"], 0), post["date"], post["slug"]))
    return pool


def _guide_window(ranked, day):
    if not ranked:
        return []
    count = min(GUIDE_PICK_COUNT, len(ranked))
    if len(ranked) <= GUIDE_PICK_COUNT:
        return ranked[:count]
    start = (day.toordinal() * GUIDE_PICK_COUNT) % len(ranked)
    return [ranked[(start + offset) % len(ranked)] for offset in range(count)]


def select_daily_guides(records, day):
    """Five articles shared by the homepage block and the blog editor's picks.

    `day` is an Asia/Tokyo calendar date. The same date always returns the same
    five articles in the same order. The list walks articles that already have
    fewer internal links, oldest first, so the extra links move through the
    archive instead of staying on the newest posts. Articles without a usable
    thumbnail are left out. When more than five articles qualify, the five
    slugs are not the previous date's five.
    """
    if isinstance(day, str):
        day = date.fromisoformat(day[:10])
    ranked = _ranked_guides(records, day)
    chosen = _guide_window(ranked, day)
    if len(ranked) <= GUIDE_PICK_COUNT:
        return chosen
    previous = {post["slug"] for post in _guide_window(_ranked_guides(records, day - timedelta(days=1)), day - timedelta(days=1))}
    if {post["slug"] for post in chosen} == previous:
        start = ((day.toordinal() * GUIDE_PICK_COUNT) + 1) % len(ranked)
        chosen = [ranked[(start + offset) % len(ranked)] for offset in range(GUIDE_PICK_COUNT)]
    return chosen


def render_home_guide_card(post, lead=False):
    width, height = ("960", "540") if lead else ("96", "72")
    cover = ""
    if post["cover"]:
        cover = (f'<img src="{text(post["cover"])}" alt="{text(post["coverAlt"] or post["title"])}" '
                 f'loading="lazy" decoding="async" width="{width}" height="{height}">')
    topic = f'<p class="home-guide-topic">{text(post["topic"])}</p>'
    title = f'<h3>{text(post["title"])}</h3>'
    when = f'<time datetime="{text(post["date"])}">{text(post["date"].replace("-", "."))}</time>'
    if lead:
        credit = render_credit(post)
        credit_html = f'<p class="home-guide-credit">{credit}</p>' if credit else ""
        return (f'<article class="home-guide home-guide--lead"><a href="{text(post["url"])}">{cover}'
                f'<div class="home-guide-copy">{topic}{title}'
                f'<p class="home-guide-excerpt">{text(post["excerpt"])}</p>{when}</div></a>'
                f'{credit_html}</article>')
    return (f'<article class="home-guide home-guide--row"><a href="{text(post["url"])}">{cover}'
            f'<div class="home-guide-copy">{topic}{title}{when}</div></a></article>')


def render_home_guides(records, day):
    posts = select_daily_guides(records, day)
    lead = render_home_guide_card(posts[0], True) if posts else ""
    rows = "\n".join(render_home_guide_card(post) for post in posts[1:])
    listing = f'    <div class="home-guide-list">\n{rows}\n    </div>' if rows else ""
    return (
        f'{HOME_GUIDE_START}\n'
        f'<section class="sec" id="guides" data-guide-date="{day.isoformat()}">\n'
        '  <div class="wrap">\n'
        '    <div class="home-guides-head">\n'
        '      <h2>旅行指南</h2>\n'
        '      <a class="home-guides-all" href="/blog/">查看全部 →</a>\n'
        '    </div>\n'
        f'    <div class="home-guides">\n{lead}\n{listing}\n    </div>\n'
        '  </div>\n'
        '</section>\n'
        f'{HOME_GUIDE_END}'
    )


def update_chinese_homepage(records, day):
    path = ROOT / "zh.html"
    if not path.exists():
        return
    page = path.read_text(encoding="utf-8")
    start = page.find(HOME_GUIDE_START)
    end = page.find(HOME_GUIDE_END)
    if start < 0 or end < start:
        raise ValueError("zh.html is missing home guide markers")
    end += len(HOME_GUIDE_END)
    updated = page[:start] + render_home_guides(records, day) + page[end:]
    if updated != page:
        path.write_text(updated, encoding="utf-8")


def render_featured(posts, day):
    """Blog editor's picks use the same lead-plus-four markup as the homepage block."""
    if not posts:
        return ""
    lead = render_home_guide_card(posts[0], True)
    rows = "".join(render_home_guide_card(post) for post in posts[1:])
    listing = f'<div class="home-guide-list">{rows}</div>' if rows else ""
    return (f'<section class="featured-section" id="featured-section" data-guide-date="{day.isoformat()}" aria-labelledby="featured-title">'
            f'<div class="home-guides-head"><h2 id="featured-title">编辑精选</h2></div>'
            f'<div class="home-guides">{lead}{listing}</div></section>')


def render_destination_filters(records):
    """One row of main regions, plus a single 更多 menu for every specific place."""
    chips = visible_region_chips(records)
    buttons = '<button type="button" data-filter="destination" value="" aria-pressed="true">全部</button>'
    buttons += ''.join(
        f'<button type="button" data-filter="destination" value="region:{text(label)}" aria-pressed="false">{text(label)}</button>'
        for label in chips)
    used = [place for place in DESTINATIONS if any(place in post["destinations"] for post in records)]
    groups = []
    for label, _ in REGION_GROUPS:
        places = [place for place in used if place_region(place) == label]
        if places:
            groups.append((label, places))
    other = [place for place in used if place_region(place) == OTHER_REGION]
    if other:
        groups.append((OTHER_REGION, other))
    options = ''.join(
        f'<optgroup label="{text(label)}">' + ''.join(f'<option value="{text(place)}">{text(place)}</option>' for place in places) + '</optgroup>'
        for label, places in groups)
    more = (f'<label class="filter-more"><span class="sr-only">更多目的地</span>'
            f'<select data-select="destination" aria-label="更多目的地"><option value="">更多</option>{options}</select></label>')
    mobile_options = ''.join(f'<option value="region:{text(label)}">{text(label)}</option>' for label in chips)
    mobile_options += options
    mobile = (f'<label class="mobile-filter"><span class="sr-only">目的地</span>'
              f'<select data-select="destination" aria-label="目的地"><option value="">目的地 · 全部</option>{mobile_options}</select></label>')
    return (f'<div class="filter-row filter-row--regions filter-row--line"><span class="filter-label">目的地</span>'
            f'<div class="filter-options" role="group" aria-label="目的地">{buttons}</div>{more}</div>{mobile}')


def render_filters(records, key, label, order):
    used = set(value for post in records for value in (post[key] if isinstance(post[key], list) else [post[key]]))
    options = [option for option in order if option in used]
    filter_name = "destination" if key == "destinations" else "topic"
    buttons = '<button type="button" data-filter="'+filter_name+'" value="" aria-pressed="true">全部</button>'
    buttons += ''.join(f'<button type="button" data-filter="{filter_name}" value="{text(option)}" aria-pressed="false">{text(option)}</button>' for option in options)
    select = f'<label class="mobile-filter"><span class="sr-only">{label}</span><select data-select="{filter_name}" aria-label="{label}"><option value="">{label} · 全部</option>'
    select += ''.join(f'<option value="{text(option)}">{text(option)}</option>' for option in options) + '</select></label>'
    return f'<div class="filter-row filter-row--line"><span class="filter-label">{label}</span><div class="filter-options" role="group" aria-label="{label}">{buttons}</div></div>{select}'


def render_pagination(current, total, url_for=None):
    url_for = url_for or page_url
    if total <= 1:
        return '<span class="page-summary">已显示全部指南</span>'
    items = [f'<a href="{url_for(current-1)}" rel="prev">上一页</a>' if current > 1 else '<span aria-disabled="true">上一页</span>']
    visible = sorted({1, total, *range(max(1, current-2), min(total, current+2)+1)})
    previous = 0
    for number in visible:
        if previous and number > previous + 1:
            items.append('<span class="page-gap" aria-hidden="true">…</span>')
        items.append(f'<a href="{url_for(number)}" aria-label="第 {number} 页"'+(' aria-current="page"' if number==current else '')+f'>{number}</a>')
        previous = number
    items.append(f'<a href="{url_for(current+1)}" rel="next">下一页</a>' if current < total else '<span aria-disabled="true">下一页</span>')
    return ''.join(items)


def topic_hub_path(topic, page=1):
    slug = TOPIC_SLUGS[topic]
    return f"/blog/topic/{slug}/" if page == 1 else f"/blog/topic/{slug}/page/{page}/"


def region_hub_path(region, page=1):
    slug = REGION_SLUGS[region]
    return f"/blog/region/{slug}/" if page == 1 else f"/blog/region/{slug}/page/{page}/"


def topic_intro(topic):
    return f"收录主题为{topic}的旅行指南。"


def region_intro(region):
    if region == OTHER_REGION:
        names = "、".join(label for label, _ in REGION_GROUPS)
        return f"收录目的地属于{region}的旅行指南。{region}指未归入{names}的目的地。"
    places = dict(REGION_GROUPS)[region]
    return f"收录目的地属于{region}的旅行指南。{region}包含：" + "、".join(places) + "。"


def topic_hub_link(post):
    return f'<a href="{text(topic_hub_path(post["topic"]))}">{text(post["topic"])}</a>'


def destination_hub_links(post):
    if not post["destinations"]:
        return ""
    parts = [f'<a href="{text(region_hub_path(place_region(place)))}">{text(place)}</a>' for place in post["destinations"]]
    return " · " + " / ".join(parts)


def render_hub_nav(records):
    topics = [topic for topic in TOPICS if any(post["topic"] == topic for post in records)]
    regions = [label for label, _ in REGION_GROUPS if any(label in post["regions"] for post in records)]
    if any(OTHER_REGION in post["regions"] for post in records):
        regions.append(OTHER_REGION)
    topic_links = "".join(f'<li><a href="{text(topic_hub_path(topic))}">{text(topic)}</a></li>' for topic in topics)
    region_links = "".join(f'<li><a href="{text(region_hub_path(region))}">{text(region)}</a></li>' for region in regions)
    return ('<nav class="guide-hubs" aria-label="主题与地区">'
            f'<p>主题</p><ul>{topic_links}</ul><p>地区</p><ul>{region_links}</ul></nav>')


def hub_schema(name, description, canonical, posts, start):
    items = [{"@type": "ListItem", "position": index, "url": BASE + post["url"], "name": post["title"]}
             for index, post in enumerate(posts, start)]
    return {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "BreadcrumbList", "itemListElement": [
                {"@type": "ListItem", "position": 1, "name": "首页", "item": BASE + "/zh"},
                {"@type": "ListItem", "position": 2, "name": "旅行指南", "item": BASE + "/blog/"},
                {"@type": "ListItem", "position": 3, "name": name, "item": canonical},
            ]},
            {"@type": "CollectionPage", "name": name, "description": description, "url": canonical,
             "inLanguage": "zh-CN", "mainEntity": {"@type": "ItemList", "numberOfItems": len(items), "itemListElement": items}},
        ],
    }


def write_hub_pages(records, header):
    """One crawlable index per topic and per region that has articles."""
    template = (ROOT / "scripts/hub-template.html").read_text(encoding="utf-8")
    groups = [("topic", topic, topic_intro, topic_hub_path) for topic in TOPICS]
    groups += [("region", label, region_intro, region_hub_path) for label, _ in REGION_GROUPS]
    groups.append(("region", OTHER_REGION, region_intro, region_hub_path))
    written = set()
    dates = {}
    for _kind, name, intro_for, path_for in groups:
        if _kind == "topic":
            members = [post for post in records if post["topic"] == name]
        else:
            members = [post for post in records if name in post["regions"]]
        if not members:
            continue
        intro = intro_for(name)
        page_count = math.ceil(len(members) / PER_PAGE)
        for number in range(1, page_count + 1):
            chunk = members[(number - 1) * PER_PAGE:number * PER_PAGE]
            url = path_for(name, number)
            description = intro if number == 1 else f"{intro}第 {number} 页。"
            title = name if number == 1 else f"{name} · 第 {number} 页"
            canonical = BASE + url
            head = ""
            if number > 1:
                head += f'<link rel="prev" href="{text(BASE + path_for(name, number - 1))}">'
            if number < page_count:
                head += f'<link rel="next" href="{text(BASE + path_for(name, number + 1))}">'
            schema = json.dumps(hub_schema(name, description, canonical, chunk, (number - 1) * PER_PAGE + 1), ensure_ascii=False).replace("<", "\\u003c")
            html = render_template(template, {
                "HEADER": header, "TITLE": text(title), "NAME": text(name), "DESCRIPTION": text(description),
                "CANONICAL": text(canonical), "INTRO": text(intro), "TOTAL": len(members),
                "CARDS": "\n".join(render_card(post) for post in chunk),
                "PAGINATION": render_pagination(number, page_count, lambda page, name=name, path_for=path_for: path_for(name, page)),
                "PAGINATION_HEAD": head, "SCHEMA": schema,
            })
            output = BLOG.joinpath(*url.strip("/").split("/")[1:]) / "index.html"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(html, encoding="utf-8")
            written.add(output)
            dates[url] = f"{max(post['updated'] for post in chunk)}T00:00:00+09:00"
    for kind in ("topic", "region"):
        root = BLOG / kind
        if not root.exists():
            continue
        for page in root.rglob("index.html"):
            if page not in written:
                page.unlink()
        for child in sorted(root.rglob("*"), reverse=True):
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()
        if root.exists() and not any(root.iterdir()):
            root.rmdir()
    return dates


_ASSET_REF = re.compile(r'(?P<path>/assets/[A-Za-z0-9_./-]+\.(?:css|js))(?:\?[^"\'\s>]*)?')
_ASSET_HASH_LEN = 12


def version_asset_refs(html):
    """Append a short content hash so edge caches drop stale stylesheets and scripts."""
    versions = {}

    def version(url_path):
        if url_path not in versions:
            file_path = ROOT / url_path.lstrip("/")
            if file_path.is_file():
                versions[url_path] = hashlib.sha256(file_path.read_bytes()).hexdigest()[:_ASSET_HASH_LEN]
            else:
                versions[url_path] = None
        return versions[url_path]

    def replace(match):
        digest = version(match.group("path"))
        if not digest:
            return match.group(0)
        return f'{match.group("path")}?v={digest}'

    return _ASSET_REF.sub(replace, html)


def editorial_header(filename, home):
    html = (ROOT / filename).read_text(encoding="utf-8")
    start = html.index("<header")
    header = html[start:html.index("</header>") + len("</header>")]
    header = re.sub(r'href="#([^"]*)"', lambda match: f'href="{home}#{match.group(1)}"', header)
    header = re.sub(r'href="[^"]*"([^>]*?hreflang="ja")', 'href="/editorial/"\\1', header)
    header = re.sub(r'href="[^"]*"([^>]*?hreflang="zh-CN")', 'href="/editorial/zh/"\\1', header)
    header = re.sub(r'href="[^"]*"([^>]*?hreflang="en")', 'href="/editorial/en/"\\1', header)
    return header


def write_editorial_pages():
    pages = (
        ("index.html", "/", "scripts/editorial-ja.html", ROOT / "editorial" / "index.html"),
        ("zh.html", "/zh", "scripts/editorial-zh.html", ROOT / "editorial" / "zh" / "index.html"),
        ("en.html", "/en", "scripts/editorial-en.html", ROOT / "editorial" / "en" / "index.html"),
    )
    for filename, home, template_name, output in pages:
        template = (ROOT / template_name).read_text(encoding="utf-8")
        output.parent.mkdir(parents=True, exist_ok=True)
        page = render_template(template, {"HEADER": editorial_header(filename, home)})
        page = page.replace('<meta name="robots" content="noindex">', '<meta name="robots" content="index,follow">', 1)
        output.write_text(page, encoding="utf-8")


def write_feed(records):
    latest = records[:FEED_LIMIT]
    if not latest:
        return
    updated = max(post["updated_at"] for post in latest)

    def entry(post):
        return (
            "<entry>"
            f"<title>{text(post['title'])}</title>"
            f'<link href="{text(BASE + post["url"])}"/>'
            f"<id>{text(BASE + post['url'])}</id>"
            f"<published>{text(post['published_at'])}</published>"
            f"<updated>{text(post['updated_at'])}</updated>"
            f"<summary>{text(post['excerpt'])}</summary>"
            "</entry>"
        )

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<feed xmlns="http://www.w3.org/2005/Atom">'
        "<title>日本旅行指南</title>"
        f'<link href="{BASE}/blog/feed.xml" rel="self"/>'
        f'<link href="{BASE}/blog/" rel="alternate" type="text/html"/>'
        f"<id>{BASE}/blog/feed.xml</id>"
        f"<updated>{updated}</updated>"
        "<author><name>株式会社万源</name></author>"
        + "".join(entry(post) for post in latest)
        + "</feed>\n"
    )
    (BLOG / "feed.xml").write_text(xml, encoding="utf-8")


def _post_regions(post):
    if post.get("regions"):
        return set(post["regions"])
    return set(regions_for(post.get("destinations") or []))


def _post_tags(post):
    return {str(tag) for tag in (post.get("tags") or []) if str(tag).strip()}


def related_tier(source, candidate):
    """2 shares a topic or tag and a region; 1 is the same topic or tag; 0 is region only.

    The CMS category letter is a coarse bucket (many topics share 旅行指南), so it is
    not a match signal. Topic is the published category.
    """
    if candidate["slug"] == source["slug"]:
        return None
    topical = (bool(source.get("topic")) and source.get("topic") == candidate.get("topic")
               or bool(_post_tags(source) & _post_tags(candidate)))
    same_region = bool(_post_regions(source) & _post_regions(candidate))
    if topical and same_region:
        return 2
    if topical:
        return 1
    if same_region:
        return 0
    return None


def select_related_map(records):
    """3–5 related articles per page. Newer pages give their links to older matches first."""
    sources = sorted(records, key=lambda post: (post.get("date") or "", post["slug"]), reverse=True)
    inbound = {post["slug"]: 0 for post in records}
    chosen = {}
    for source in sources:
        bands = {2: [], 1: [], 0: []}
        for candidate in records:
            tier = related_tier(source, candidate)
            if tier is not None:
                bands[tier].append(candidate)
        selected = []
        seen = set()
        for tier in (2, 1, 0):
            if len(selected) >= RELATED_MAX:
                break
            if tier < 2 and len(selected) >= RELATED_MIN:
                break
            band = [item for item in bands[tier] if item["slug"] not in seen]
            band.sort(key=lambda item: (inbound[item["slug"]], item.get("date") or "", item["slug"]))
            selected.extend(band[:RELATED_MAX - len(selected)])
            seen.update(item["slug"] for item in selected)
        for item in selected:
            inbound[item["slug"]] += 1
        chosen[source["slug"]] = selected
    return chosen


def render_related_section(posts):
    if not posts:
        return ""
    items = []
    for post in posts:
        if post.get("cover"):
            thumb = (f'<img src="{text(post["cover"])}" alt="{text(post.get("coverAlt") or post["title"])}" '
                     f'loading="lazy" decoding="async" width="320" height="240">')
        else:
            thumb = '<span class="related-thumb" aria-hidden="true"></span>'
        shown = text(str(post.get("date") or "").replace("-", "."))
        items.append(
            f'<li><a href="{text(post["url"])}">{thumb}<span class="related-copy">'
            f'<span class="related-title">{text(post["title"])}</span>'
            f'<time datetime="{text(post.get("date") or "")}">{shown}</time></span></a></li>'
        )
    return ('<section class="related-reading" aria-label="相关阅读"><h2>相关阅读</h2><ul>'
            + "".join(items) + "</ul></section>")


def stamp_html_assets():
    paths = []
    for name in (
        "index.html", "zh.html", "en.html", "404.html", "quote.html",
        "editorial/index.html", "editorial/zh/index.html", "editorial/en/index.html",
        "scripts/journal-header.html", "scripts/article-template.html", "scripts/blog-index-template.html",
        "scripts/editorial-ja.html", "scripts/editorial-zh.html", "scripts/editorial-en.html",
        "scripts/hub-template.html",
    ):
        path = ROOT / name
        if path.is_file():
            paths.append(path)
    if BLOG.is_dir():
        paths.extend(sorted(BLOG.rglob("*.html")))
    pages_root = ROOT / "pages"
    if pages_root.is_dir():
        paths.extend(sorted(pages_root.rglob("*.html")))
    for path in paths:
        original = path.read_text(encoding="utf-8")
        updated = version_asset_refs(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")


def main():
    posts = [post for path in POSTS.glob("*.md") if not (post := load_post(path))[0].get("draft", False)]
    posts.sort(key=lambda item: (item[2], item[1]), reverse=True)
    if not posts:
        raise ValueError("No articles found in content/posts")
    records = [post_record(post) for post in posts]
    related_map = select_related_map(records)
    BLOG.mkdir(parents=True, exist_ok=True)
    header = (ROOT / "scripts/journal-header.html").read_text(encoding="utf-8")
    template = (ROOT / "scripts/article-template.html").read_text(encoding="utf-8")
    for (data, slug, published, body), post in zip(posts, records):
        schema = {"@context": "https://schema.org", "@type": "Article", "headline": post["title"],
                  "description": post["excerpt"], "inLanguage": "zh-CN", "mainEntityOfPage": BASE + post["url"],
                  "datePublished": published,
                  "author": {"@type": "Organization", "name": "株式会社万源", "url": BASE + "/editorial/zh/"},
                  "publisher": {"@type": "Organization", "name": "株式会社万源", "url": BASE + "/",
                                "logo": {"@type": "ImageObject", "url": BASE + "/assets/img/logo.png"}}}
        if post["updated"] != published:
            schema["dateModified"] = post["updated"]
        cover = ""
        if post["cover"]:
            schema["image"] = BASE + post["cover"]
            caption = f'<figcaption>{render_credit(post)}</figcaption>' if render_credit(post) else ""
            cover = f'<figure class="article-cover"><img src="{text(post["cover"])}" alt="{text(post["coverAlt"])}" loading="eager" width="1200" height="800">{caption}</figure>'
        headings = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body, re.S)
        toc = '<details class="article-toc"><summary>本文目录</summary><nav aria-label="本文目录"><ol>'+''.join(f'<li class="toc-level-{level}"><a href="#{text(anchor)}">{text(plain(label))}</a></li>' for level, anchor, label in headings)+'</ol></nav></details>' if headings else ""
        updated = f' · 更新于 <time datetime="{text(post["updated"])}">{text(post["updated"])}</time>' if post["updated"] != published else ""
        page = render_template(template, {"HEADER": header, "TITLE": text(post["title"]), "DESCRIPTION": text(post["excerpt"]),
            "DATE": text(published), "UPDATED": updated, "BODY": body, "URL": BASE + post["url"],
            "RELATED": render_related_section(related_map.get(slug, [])),
            "REVIEW_NOTE": render_review_note(post.get("reviewed")), "SERVICE": render_service_block(post),
            "CATEGORY": topic_hub_link(post), "DESTINATIONS": destination_hub_links(post), "COVER": cover, "TOC": toc,
            "OG_IMAGE": text(BASE + (post["cover"] or "/assets/img/logo.png")), "SCHEMA": json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")})
        (BLOG / f"{slug}.html").write_text(page, encoding="utf-8")
    active = {f"{post['slug']}.html" for post in records}
    for page in BLOG.glob("*.html"):
        if page.name != "index.html" and page.name not in active:
            page.unlink()

    index_template = (ROOT / "scripts/blog-index-template.html").read_text(encoding="utf-8")
    page_count = math.ceil(len(records) / PER_PAGE)
    today = journal_today()
    featured_html = render_featured(select_daily_guides(records, today), today)
    for number in range(1, page_count + 1):
        output = BLOG / "index.html" if number == 1 else BLOG / "page" / str(number) / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        guide_description = "从城市漫步到山间温泉，找到适合你的日本旅行灵感。万源整理行程路线、交通接送与实用旅行指南。"
        if number > 1:
            guide_description += f"第 {number} 页。"
        values = {"HEADER": header, "PAGE_TITLE": "日本旅行指南" + (f" · 第 {number} 页" if number > 1 else ""),
            "DESCRIPTION": guide_description,
            "CANONICAL": BASE + page_url(number), "PAGE": number, "TOTAL": len(records), "PAGE_COUNT": page_count,
            "DESTINATION_FILTER": render_destination_filters(records),
            "TOPIC_FILTER": render_filters(records, "topic", "旅行主题", TOPICS),
            "HUB_NAV": render_hub_nav(records),
            "FEATURED": featured_html if number == 1 else "",
            "CARDS": '\n'.join(render_card(p) for p in records[(number-1)*PER_PAGE:number*PER_PAGE]),
            "PAGINATION": render_pagination(number, page_count)}
        output.write_text(render_template(index_template, values), encoding="utf-8")
    if (BLOG / "page").exists():
        for directory in (BLOG / "page").iterdir():
            if directory.is_dir() and directory.name.isdigit() and int(directory.name) not in range(2, page_count + 1):
                # Only remove files owned by this generator; never remove arbitrary content.
                generated = directory / "index.html"
                if generated.exists(): generated.unlink()
                if not any(directory.iterdir()): directory.rmdir()
    hidden = {"published_at", "updated_at", "tags", "body_links", "reviewed"}
    public_records = [{key: value for key, value in post.items() if key not in hidden} for post in records]
    (BLOG / "articles.json").write_text(json.dumps({"perPage": PER_PAGE, "posts": public_records}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_feed(records)
    hub_dates = write_hub_pages(records, header)
    write_editorial_pages()

    from site_pages import update_site_pages
    standalone_urls = update_site_pages(ROOT)

    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls = ET.Element(ns + "urlset")
    dates = {post["url"]: post["updated_at"] for post in records}
    dates.update(hub_dates)
    if records:
        dates["/blog/feed.xml"] = max(post["updated_at"] for post in records[:FEED_LIMIT])
    editorial_paths = ["/editorial/", "/editorial/zh/", "/editorial/en/"]
    for path in ["/", "/zh", "/en", *(page_url(i) for i in range(1, page_count+1)), *editorial_paths, *standalone_urls, *dates]:
        entry = ET.SubElement(urls, ns + "url")
        ET.SubElement(entry, ns + "loc").text = BASE + path
        if path in dates: ET.SubElement(entry, ns + "lastmod").text = dates[path]
        elif path in editorial_paths: ET.SubElement(entry, ns + "lastmod").text = EDITORIAL_LASTMOD
    ET.ElementTree(urls).write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    update_chinese_homepage(records, today)
    stamp_html_assets()
    print(f"Built {len(posts)} articles, {page_count} index page(s), search catalog and sitemap")


if __name__ == "__main__":
    main()
