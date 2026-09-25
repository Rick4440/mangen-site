"""Build crawlable article pages and index from the Decap Markdown sources."""
from datetime import date, datetime
from html import escape
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

import markdown
import yaml

ROOT = Path(__file__).resolve().parents[1]
POSTS = ROOT / "content/posts"
BLOG = ROOT / "blog"
BASE = "https://mangen.jp"


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
    rendered = markdown.markdown(normalized, extensions=["tables", "fenced_code", "sane_lists"])
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
    source_slug = str(metadata.get("slug") or slug)
    dated_slug = rf"\d{{8}}-{re.escape(source_slug)}(?:-\d+)?"
    if not re.fullmatch(r"[a-z0-9-]+", slug) or (source_slug != slug and not re.fullmatch(dated_slug, slug)):
        raise ValueError(f"Invalid slug: {path}")
    published = metadata.get("date")
    if isinstance(published, (date, datetime)):
        published = published.isoformat()[:10]
    return metadata, slug, str(published), render_markdown(match.group(2), path)


def main():
    posts = [post for path in POSTS.glob("*.md") if not (post := load_post(path))[0].get("draft", False)]
    posts.sort(key=lambda item: (item[2], item[1]), reverse=True)
    if not posts:
        raise ValueError("No articles found in content/posts")
    # Article template is kept separately, since generated pages are overwritten on every build.
    template = (ROOT / "scripts/article-template.html").read_text(encoding="utf-8")
    for data, slug, published, body in posts:
        related = [item for item in posts if item[1] != slug][:3]
        related_links = "\n".join(
            f'<li><a href="/blog/{other_slug}">{text(other_data.get("title_i18n", {}).get("zh") or other_data.get("title") or other_slug)}</a></li>'
            for other_data, other_slug, _, _ in related
        )
        title = data.get("title_i18n", {}).get("zh") or data.get("title") or slug
        excerpt = data.get("excerpt_i18n", {}).get("zh") or data.get("excerpt") or ""
        cover = data.get("cover_image") or ""
        if cover and (not cover.startswith("/assets/uploads/") or ".." in cover.split("/")):
            raise ValueError(f"Invalid cover image path: {slug}")
        category = data.get("category") or "旅行指南"
        schema = {"@context": "https://schema.org", "@type": "Article", "headline": title,
                  "description": excerpt, "inLanguage": "zh-CN",
                  "mainEntityOfPage": f"{BASE}/blog/{slug}",
                  "datePublished": published, "dateModified": published, "author": {"@type": "Organization", "name": "株式会社万源"},
                  "publisher": {"@type": "Organization", "name": "株式会社万源"}}
        if cover:
            schema["image"] = BASE + cover
        page = template
        for key, value in {"TITLE": text(title), "DESCRIPTION": text(excerpt), "DATE": text(published),
                           "BODY": body, "URL": f"{BASE}/blog/{slug}", "RELATED": related_links,
                           "CATEGORY": text(category),
                           "COVER": f'<figure class="article-cover"><img src="{text(cover)}" alt="{text(title)}" loading="eager"></figure>' if cover else "",
                           "OG_IMAGE": text(BASE + cover if cover else BASE + "/assets/img/logo.png"),
                           "SCHEMA": json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")}.items():
            page = page.replace("{{" + key + "}}", value)
        (BLOG / f"{slug}.html").write_text(page, encoding="utf-8")

    # Generated article pages are disposable: remove pages for deleted or unpublished posts.
    active = {f"{slug}.html" for _, slug, _, _ in posts}
    for page in BLOG.glob("*.html"):
        if page.name != "index.html" and page.name not in active:
            page.unlink()

    cards = []
    for data, slug, published, _ in posts:
        title = data.get("title_i18n", {}).get("zh") or data.get("title") or slug
        excerpt = data.get("excerpt_i18n", {}).get("zh") or data.get("excerpt") or ""
        category = data.get("category") or "旅行指南"
        cards.append(f'<a class="blog-card" href="/blog/{slug}"><time datetime="{text(published)}">{text(published)}</time><span>{text(category)}</span><h3>{text(title)}</h3><p>{text(excerpt)}</p></a>')
    index_path = BLOG / "index.html"
    index = index_path.read_text(encoding="utf-8")
    index = re.sub(r'<div class="blog-list"(?: data-bind="blog-list")?>.*?</div>\s*</section>',
                   '<div class="blog-list">' + "\n".join(cards) + '</div>\n</section>', index, flags=re.S)
    index_path.write_text(index, encoding="utf-8")

    ET.register_namespace("", "http://www.sitemaps.org/schemas/sitemap/0.9")
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    urls = ET.Element(ns + "urlset")
    for path in ["/", "/zh", "/en", "/blog/", *(f"/blog/{p[1]}" for p in posts)]:
        entry = ET.SubElement(urls, ns + "url")
        ET.SubElement(entry, ns + "loc").text = BASE + path
        if path.startswith("/blog/") and path != "/blog/":
            post_date = next((p[2] for p in posts if path == f"/blog/{p[1]}"), None)
            if post_date:
                ET.SubElement(entry, ns + "lastmod").text = post_date
    ET.ElementTree(urls).write(ROOT / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    print(f"Built {len(posts)} articles, index and sitemap")


if __name__ == "__main__":
    main()
