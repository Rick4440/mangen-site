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


def load_post(path):
    source = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", source, re.S)
    if not match:
        raise ValueError(f"Missing YAML front matter: {path}")
    metadata = yaml.safe_load(match.group(1))
    slug = path.stem
    if not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError(f"Invalid slug: {path}")
    published = metadata.get("date")
    if isinstance(published, (date, datetime)):
        published = published.isoformat()[:10]
    return metadata, slug, str(published), render_markdown(match.group(2), path)


PER_PAGE = 12
FEED_LIMIT = 50
JST = timezone(timedelta(hours=9))
FEATURED_MIN = 3
FEATURED_MAX = 5
FEATURED_WINDOW_DAYS = 14
# Chinese homepage: one lead plus four compact rows, separate from the journal's editor picks.
HOME_GUIDE_LIMIT = 5
HOME_GUIDE_START = "<!-- home-guides:start -->"
HOME_GUIDE_END = "<!-- home-guides:end -->"
# First row of the desktop guide grid. Auto picks avoid these newest posts when other candidates exist.
LATEST_ABOVE_FOLD = 3
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
    return {"slug": slug, "url": f"/blog/{slug}", "title": title, "excerpt": excerpt,
            "date": published, "updated": modified,
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
            "search": plain(title + " " + excerpt + " " + body)}


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


def rotation_rank(slug, day):
    return hashlib.sha256(f"{day.isoformat()}:{slug}".encode()).hexdigest()


def _active_pin(post, today):
    if not post.get("featured"):
        return False
    until = post.get("featured_until") or ""
    return not until or until >= today.isoformat()


def _region(post):
    places = post.get("destinations") or []
    return places[0] if places else ""


def _take_diverse(pool, need, chosen, day, newest_first=False):
    """Fill slots from pool. Prefer a new topic and a new region; relax only when that cannot fill the slots."""
    if need <= 0:
        return []
    used = {post["slug"] for post in chosen}
    topics = {post["topic"] for post in chosen}
    regions = {_region(post) for post in chosen if _region(post)}
    ordered = list(pool)
    if newest_first:
        ordered.sort(key=lambda post: (post["date"], post["slug"]), reverse=True)
    else:
        ordered.sort(key=lambda post: rotation_rank(post["slug"], day))
    selected = []

    def acceptable(post, mode):
        if post["slug"] in used:
            return False
        topic_free = post["topic"] not in topics
        region = _region(post)
        region_free = not region or region not in regions
        if mode == "strict":
            return topic_free and region_free
        if mode == "topic":
            return topic_free
        if mode == "region":
            return region_free
        return True

    for mode in ("strict", "topic", "region", "any"):
        for post in ordered:
            if len(selected) >= need:
                return selected
            if acceptable(post, mode):
                selected.append(post)
                used.add(post["slug"])
                topics.add(post["topic"])
                if _region(post):
                    regions.add(_region(post))
    return selected


def select_editor_picks(records, today):
    """Choose 3–5 editor's picks. Manual pins come first; the rest rotate by date.

    records may be in any order. The result is the lead card followed by smaller cards.
    Fewer than three published articles returns every article.
    """
    ordered = sorted(records, key=lambda post: (post["date"], post["slug"]), reverse=True)
    target = min(FEATURED_MAX, len(ordered))
    if not ordered:
        return []
    pins = [post for post in ordered if _active_pin(post, today)]
    pins.sort(key=lambda post: (post.get("featured_order") is None, post.get("featured_order") or 0))
    chosen = pins[:FEATURED_MAX]
    chosen_slugs = {post["slug"] for post in chosen}
    if len(chosen) >= target:
        return chosen[:target]
    start = (today - timedelta(days=FEATURED_WINDOW_DAYS)).isoformat()
    above_fold = {post["slug"] for post in ordered[:LATEST_ABOVE_FOLD]}
    recent = [post for post in ordered if post["date"] >= start and post["slug"] not in chosen_slugs]
    preferred = [post for post in recent if post["slug"] not in above_fold]
    overlap = [post for post in recent if post["slug"] in above_fold]
    need = target - len(chosen)
    chosen.extend(_take_diverse(preferred, need, chosen, today))
    if len(chosen) < target:
        chosen.extend(_take_diverse(overlap, target - len(chosen), chosen, today))
    if len(chosen) < target:
        fallback = [post for post in ordered if post["slug"] not in {item["slug"] for item in chosen}]
        chosen.extend(_take_diverse(fallback, target - len(chosen), chosen, today, newest_first=True))
    return chosen[:target]


def select_home_guides(records, limit=HOME_GUIDE_LIMIT):
    """Newest articles for the Chinese homepage.

    The large card is always the newest article. The other cards continue in
    date order, preferring a topic that is not already in the row. This stays
    off the journal front, which leads with the manual pin and then rotates
    posts from outside the newest row.
    """
    ordered = sorted(records, key=lambda post: (post["date"], post["slug"]), reverse=True)
    if not ordered:
        return []
    chosen = [ordered[0]]
    chosen.extend(_take_diverse(ordered[1:], limit - 1, chosen, date.min, newest_first=True))
    return chosen[:limit]


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


def render_home_guides(records):
    posts = select_home_guides(records)
    lead = render_home_guide_card(posts[0], True) if posts else ""
    rows = "\n".join(render_home_guide_card(post) for post in posts[1:])
    listing = f'    <div class="home-guide-list">\n{rows}\n    </div>' if rows else ""
    return (
        f'{HOME_GUIDE_START}\n'
        '<section class="sec" id="guides">\n'
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


def update_chinese_homepage(records):
    path = ROOT / "zh.html"
    if not path.exists():
        return
    page = path.read_text(encoding="utf-8")
    start = page.find(HOME_GUIDE_START)
    end = page.find(HOME_GUIDE_END)
    if start < 0 or end < start:
        raise ValueError("zh.html is missing home guide markers")
    end += len(HOME_GUIDE_END)
    updated = page[:start] + render_home_guides(records) + page[end:]
    if updated != page:
        path.write_text(updated, encoding="utf-8")


def render_featured(posts):
    if not posts:
        return ""

    def cover_link(post, lead):
        if not post["cover"]:
            return ""
        loading = 'loading="eager" fetchpriority="high"' if lead else 'loading="lazy" decoding="async"'
        image = (f'<img src="{text(post["cover"])}" alt="" {loading} width="1200" height="800">')
        if lead:
            return f'<a class="featured-image" href="{text(post["url"])}" tabindex="-1" aria-hidden="true">{image}</a>'
        return f'<span class="featured-mini-image">{image}</span>'

    def taxonomy(post):
        return taxonomy_html(post).replace("<span> · </span>", " · ")

    lead = posts[0]
    lead_cover = cover_link(lead, True)
    lead_html = (f'<article class="featured-lead{" featured-lead--text" if not lead_cover else ""}">{lead_cover}'
                 f'<div class="featured-copy"><div class="guide-taxonomy">{taxonomy(lead)}</div>'
                 f'<h3><a href="{text(lead["url"])}">{text(lead["title"])}</a></h3><p>{text(lead["excerpt"])}</p>'
                 f'<a class="text-link" href="{text(lead["url"])}">阅读指南</a></div>'
                 + (f'<p class="image-credit">{render_credit(lead)}</p>' if lead_cover else "") + "</article>")
    minis = []
    for post in posts[1:]:
        thumb = cover_link(post, False)
        minis.append(f'<article class="featured-mini"><a href="{text(post["url"])}">{thumb}'
                     f'<span class="featured-mini-copy"><span class="guide-taxonomy">{taxonomy(post)}</span>'
                     f'<h3>{text(post["title"])}</h3></span></a></article>')
    side = f'<div class="featured-side">{"".join(minis)}</div>' if minis else ""
    count = len(posts)
    return (f'<section class="featured-section" aria-labelledby="featured-title" id="featured-section">'
            f'<h2 id="featured-title">编辑精选</h2>'
            f'<div class="featured-layout featured-layout--{count}">{lead_html}{side}</div></section>')


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


def render_pagination(current, total):
    if total <= 1:
        return '<span class="page-summary">已显示全部指南</span>'
    items = [f'<a href="{page_url(current-1)}" rel="prev">上一页</a>' if current > 1 else '<span aria-disabled="true">上一页</span>']
    visible = sorted({1, total, *range(max(1, current-2), min(total, current+2)+1)})
    previous = 0
    for number in visible:
        if previous and number > previous + 1:
            items.append('<span class="page-gap" aria-hidden="true">…</span>')
        items.append(f'<a href="{page_url(number)}" aria-label="第 {number} 页"'+(' aria-current="page"' if number==current else '')+f'>{number}</a>')
        previous = number
    items.append(f'<a href="{page_url(current+1)}" rel="next">下一页</a>' if current < total else '<span aria-disabled="true">下一页</span>')
    return ''.join(items)


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


def stamp_html_assets():
    paths = []
    for name in (
        "index.html", "zh.html", "en.html", "404.html", "quote.html",
        "scripts/journal-header.html", "scripts/article-template.html", "scripts/blog-index-template.html",
    ):
        path = ROOT / name
        if path.is_file():
            paths.append(path)
    if BLOG.is_dir():
        paths.extend(sorted(BLOG.rglob("*.html")))
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
    BLOG.mkdir(parents=True, exist_ok=True)
    header = (ROOT / "scripts/journal-header.html").read_text(encoding="utf-8")
    template = (ROOT / "scripts/article-template.html").read_text(encoding="utf-8")
    for (data, slug, published, body), post in zip(posts, records):
        # Rank by explicit content metadata; stable input order breaks ties.
        related = sorted([p for p in records if p["slug"] != slug], key=lambda p: (
            bool(set(p["destinations"]) & set(post["destinations"]) - {"全日本"}),
            p["topic"] == post["topic"], p["featured"]), reverse=True)[:3]
        related_links = '\n'.join(f'<li><a href="{text(p["url"])}"><span class="guide-taxonomy">{text(p["topic"])}</span>{text(p["title"])}</a></li>' for p in related)
        schema = {"@context": "https://schema.org", "@type": "Article", "headline": post["title"],
                  "description": post["excerpt"], "inLanguage": "zh-CN", "mainEntityOfPage": BASE + post["url"],
                  "datePublished": published, "dateModified": post["updated"],
                  "author": {"@type": "Organization", "name": "株式会社万源"}, "publisher": {"@type": "Organization", "name": "株式会社万源"}}
        cover = ""
        if post["cover"]:
            schema["image"] = BASE + post["cover"]
            caption = f'<figcaption>{render_credit(post)}</figcaption>' if render_credit(post) else ""
            cover = f'<figure class="article-cover"><img src="{text(post["cover"])}" alt="{text(post["coverAlt"])}" loading="eager" width="1200" height="800">{caption}</figure>'
        headings = re.findall(r'<h([23]) id="([^"]+)">(.*?)</h\1>', body, re.S)
        toc = '<details class="article-toc"><summary>本文目录</summary><nav aria-label="本文目录"><ol>'+''.join(f'<li class="toc-level-{level}"><a href="#{text(anchor)}">{text(plain(label))}</a></li>' for level, anchor, label in headings)+'</ol></nav></details>' if headings else ""
        updated = f' · 更新于 <time datetime="{text(post["updated"])}">{text(post["updated"])}</time>' if post["updated"] != published else ""
        page = render_template(template, {"HEADER": header, "TITLE": text(post["title"]), "DESCRIPTION": text(post["excerpt"]),
            "DATE": text(published), "UPDATED": updated, "BODY": body, "URL": BASE + post["url"], "RELATED": related_links,
            "CATEGORY": text(post["topic"]), "DESTINATIONS": (" · " + text(" / ".join(post["destinations"]))) if post["destinations"] else "", "COVER": cover, "TOC": toc,
            "OG_IMAGE": text(BASE + (post["cover"] or "/assets/img/logo.png")), "SCHEMA": json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")})
        (BLOG / f"{slug}.html").write_text(page, encoding="utf-8")
    active = {f"{post['slug']}.html" for post in records}
    for page in BLOG.glob("*.html"):
        if page.name != "index.html" and page.name not in active:
            page.unlink()

    index_template = (ROOT / "scripts/blog-index-template.html").read_text(encoding="utf-8")
    page_count = math.ceil(len(records) / PER_PAGE)
    featured_html = render_featured(select_editor_picks(records, journal_today()))
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
    public_records = [{key: value for key, value in post.items() if key not in {"published_at", "updated_at"}} for post in records]
    (BLOG / "articles.json").write_text(json.dumps({"perPage": PER_PAGE, "posts": public_records}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    write_feed(records)

    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls = ET.Element(ns + "urlset")
    dates = {post["url"]: post["updated_at"] for post in records}
    if records:
        dates["/blog/feed.xml"] = max(post["updated_at"] for post in records[:FEED_LIMIT])
    for path in ["/", "/zh", "/en", *(page_url(i) for i in range(1, page_count+1)), *dates]:
        entry = ET.SubElement(urls, ns + "url")
        ET.SubElement(entry, ns + "loc").text = BASE + path
        if path in dates: ET.SubElement(entry, ns + "lastmod").text = dates[path]
    ET.ElementTree(urls).write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    update_chinese_homepage(records)
    stamp_html_assets()
    print(f"Built {len(posts)} articles, {page_count} index page(s), search catalog and sitemap")


if __name__ == "__main__":
    main()
