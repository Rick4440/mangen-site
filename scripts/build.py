"""Build crawlable article pages and index from the Decap Markdown sources."""
from datetime import date, datetime
from html import escape
from pathlib import Path
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
TOPICS = ["行程路线", "交通与接送", "目的地攻略", "住宿美食", "季节活动", "旅行实用", "万源动态"]
DESTINATIONS = ["全日本", "东京", "京都", "大阪", "奈良", "富士山", "箱根", "北海道", "冲绳", "名古屋", "福冈"]
TOPIC_FALLBACK = {"a": "交通与接送", "b": "旅行实用", "c": "旅行实用", "d": "行程路线", "e": "万源动态"}


def plain(source):
    from html import unescape
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", str(source or "")))).strip()


def post_record(post):
    data, slug, published, body = post
    title = data.get("title_i18n", {}).get("zh") or data.get("title") or slug
    excerpt = plain(data.get("excerpt_i18n", {}).get("zh") or data.get("excerpt") or "")
    topic = data.get("topic") or TOPIC_FALLBACK.get(data.get("category"), "旅行实用")
    if topic not in TOPICS:
        raise ValueError(f"Unsupported topic in {slug}: {topic}")
    destinations = data.get("destinations")
    if destinations is None or destinations == []:
        # Broad articles mention many places; a title is the conservative fallback.
        destinations = [place for place in DESTINATIONS[1:] if place in title] or ["全日本"]
    if not isinstance(destinations, list) or any(place not in DESTINATIONS for place in destinations):
        raise ValueError(f"Unsupported destinations in {slug}")
    destinations = list(dict.fromkeys(destinations)) or ["全日本"]
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
    return {"slug": slug, "url": f"/blog/{slug}", "title": title, "excerpt": excerpt,
            "date": published, "updated": modified, "category": CATEGORY_LABELS.get(data.get("category"), "旅行指南"),
            "topic": topic, "destinations": destinations, "featured": bool(data.get("featured")),
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
    parts = []
    if post["coverCaption"]: parts.append(text(post["coverCaption"]))
    for label, url in [(post["coverCredit"], post["coverCreatorUrl"]), ("来源" if post["coverSource"] else "", post["coverSource"]), (post["coverLicense"], post["coverLicenseUrl"])]:
        if label:
            parts.append(f'<a href="{text(url)}" rel="noopener noreferrer">{text(label)}</a>' if url else text(label))
    if post["coverChanges"]: parts.append(text(post["coverChanges"]))
    return ' · '.join(parts)


def render_card(post):
    cover = (f'<div class="guide-image"><img src="{text(post["cover"])}" alt="{text(post["coverAlt"])}" loading="lazy" decoding="async" width="900" height="600"></div>' if post["cover"] else "")
    return (f'<article class="guide-entry"><a class="guide-card{ " guide-card--text" if not cover else ""}" href="{text(post["url"])}">{cover}'
            f'<div class="guide-copy"><div class="guide-taxonomy">{text(" / ".join(post["destinations"]))}<span> · </span>{text(post["topic"])}</div>'
            f'<h3>{text(post["title"])}</h3><p>{text(post["excerpt"])}</p>'
            f'<time datetime="{text(post["date"])}">{text(post["date"].replace("-", "."))}</time></div></a>' +
            (f'<p class="image-credit">{render_credit(post)}</p>' if cover else '') + '</article>')


def render_featured(post):
    cover = (f'<a class="featured-image" href="{text(post["url"])}" tabindex="-1" aria-hidden="true"><img src="{text(post["cover"])}" alt="" loading="eager" fetchpriority="high" width="1200" height="800"></a>' if post["cover"] else "")
    return (f'<section class="featured-section" aria-labelledby="featured-title" id="featured-section"><h2 id="featured-title">编辑精选</h2>'
            f'<div class="featured{ " featured--text" if not cover else ""}">{cover}<div class="featured-copy">'
            f'<div class="guide-taxonomy">{text(" / ".join(post["destinations"]))} · {text(post["topic"])}</div>'
            f'<h3><a href="{text(post["url"])}">{text(post["title"])}</a></h3><p>{text(post["excerpt"])}</p>'
            f'<a class="text-link" href="{text(post["url"])}">阅读指南</a></div></div>' +
            (f'<p class="image-credit">{render_credit(post)}</p>' if cover else '') + '</section>')


def render_filters(records, key, label, order):
    used = set(value for post in records for value in (post[key] if isinstance(post[key], list) else [post[key]]))
    options = [option for option in order if option in used]
    filter_name = "destination" if key == "destinations" else "topic"
    buttons = '<button type="button" data-filter="'+filter_name+'" value="" aria-pressed="true">全部</button>'
    buttons += ''.join(f'<button type="button" data-filter="{filter_name}" value="{text(option)}" aria-pressed="false">{text(option)}</button>' for option in options)
    select = f'<label class="mobile-filter"><span class="sr-only">{label}</span><select data-select="{filter_name}" aria-label="{label}"><option value="">{label} · 全部</option>'
    select += ''.join(f'<option value="{text(option)}">{text(option)}</option>' for option in options) + '</select></label>'
    return f'<div class="filter-row"><span class="filter-label">{label}</span><div class="filter-options" role="group" aria-label="{label}">{buttons}</div></div>{select}'


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
            "CATEGORY": text(post["topic"]), "DESTINATIONS": text(" / ".join(post["destinations"])), "COVER": cover, "TOC": toc,
            "OG_IMAGE": text(BASE + (post["cover"] or "/assets/img/logo.png")), "SCHEMA": json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")})
        (BLOG / f"{slug}.html").write_text(page, encoding="utf-8")
    active = {f"{post['slug']}.html" for post in records}
    for page in BLOG.glob("*.html"):
        if page.name != "index.html" and page.name not in active:
            page.unlink()

    index_template = (ROOT / "scripts/blog-index-template.html").read_text(encoding="utf-8")
    page_count = math.ceil(len(records) / PER_PAGE)
    # Existing editorial route guide is the fallback, not a fabricated popularity claim.
    featured = next((p for p in records if p["featured"]), next((p for p in records if p["topic"] == "行程路线"), records[0]))
    for number in range(1, page_count + 1):
        output = BLOG / "index.html" if number == 1 else BLOG / "page" / str(number) / "index.html"
        output.parent.mkdir(parents=True, exist_ok=True)
        values = {"HEADER": header, "PAGE_TITLE": "日本旅行指南" + (f" · 第 {number} 页" if number > 1 else ""),
            "CANONICAL": BASE + page_url(number), "PAGE": number, "TOTAL": len(records), "PAGE_COUNT": page_count,
            "DESTINATION_FILTER": render_filters(records, "destinations", "目的地", DESTINATIONS),
            "TOPIC_FILTER": render_filters(records, "topic", "旅行主题", TOPICS),
            "FEATURED": render_featured(featured) if number == 1 else render_featured(featured).replace('<section ', '<section hidden ', 1),
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
    (BLOG / "articles.json").write_text(json.dumps({"perPage": PER_PAGE, "posts": records}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls = ET.Element(ns + "urlset")
    dates = {post["url"]: post["updated"] for post in records}
    for path in ["/", "/zh", "/en", *(page_url(i) for i in range(1, page_count+1)), *dates]:
        entry = ET.SubElement(urls, ns + "url")
        ET.SubElement(entry, ns + "loc").text = BASE + path
        if path in dates: ET.SubElement(entry, ns + "lastmod").text = dates[path]
    ET.ElementTree(urls).write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    print(f"Built {len(posts)} articles, {page_count} index page(s), search catalog and sitemap")


if __name__ == "__main__":
    main()
