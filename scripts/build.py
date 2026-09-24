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


def load_post(path):
    source = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", source, re.S)
    if not match:
        raise ValueError(f"Missing YAML front matter: {path}")
    metadata = yaml.safe_load(match.group(1))
    slug = path.stem
    if metadata.get("slug", slug) != slug or not re.fullmatch(r"[a-z0-9-]+", slug):
        raise ValueError(f"Invalid slug: {path}")
    published = metadata.get("date")
    if isinstance(published, (date, datetime)):
        published = published.isoformat()[:10]
    return metadata, slug, str(published), markdown.markdown(match.group(2), extensions=["tables", "fenced_code"])


def main():
    posts = [load_post(path) for path in POSTS.glob("*.md")]
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
        schema = {"@context": "https://schema.org", "@type": "Article", "headline": title,
                  "description": excerpt, "inLanguage": "zh-CN",
                  "mainEntityOfPage": f"{BASE}/blog/{slug}",
                  "datePublished": published, "dateModified": published, "author": {"@type": "Organization", "name": "株式会社万源"},
                  "publisher": {"@type": "Organization", "name": "株式会社万源"}}
        page = template
        for key, value in {"TITLE": text(title), "DESCRIPTION": text(excerpt), "DATE": text(published),
                           "BODY": body, "URL": f"{BASE}/blog/{slug}", "RELATED": related_links,
                           "SCHEMA": json.dumps(schema, ensure_ascii=False).replace("<", "\\u003c")}.items():
            page = page.replace("{{" + key + "}}", value)
        (BLOG / f"{slug}.html").write_text(page, encoding="utf-8")

    cards = []
    for data, slug, published, _ in posts:
        title = data.get("title_i18n", {}).get("zh") or data.get("title") or slug
        excerpt = data.get("excerpt_i18n", {}).get("zh") or data.get("excerpt") or ""
        cards.append(f'<a class="blog-card" href="/blog/{slug}"><time datetime="{text(published)}">{text(published)}</time><h3>{text(title)}</h3><p>{text(excerpt)}</p></a>')
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
