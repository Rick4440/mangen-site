"""Regression checks for the shared site branding and company qualifications.

Run with: python -m unittest discover -s tests -v
"""
from html.parser import HTMLParser
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
HOME_PAGES = ("index.html", "zh.html", "en.html")
SITE_PAGES = (*HOME_PAGES, "blog/index.html", "scripts/journal-header.html")


class PageContent(HTMLParser):
    """Collect relevant content and its section from the actual page markup."""

    def __init__(self, source):
        super().__init__()
        self.in_footer = False
        self.in_company = False
        self.in_brand = False
        self.brand_text = []
        self.footer_links = []
        self.footer_link = None
        self.qualifications = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "footer":
            self.in_footer = True
        if tag == "section" and attrs.get("id") == "company":
            self.in_company = True
        if tag == "a" and "brand" in attrs.get("class", "").split():
            self.in_brand = True
        if tag == "a" and self.in_footer:
            self.footer_link = [attrs.get("href"), ""]
        binding = attrs.get("data-bind")
        if binding in ("license-1", "license-2"):
            self.qualifications.append((binding, self.in_footer, self.in_company))

    def handle_endtag(self, tag):
        if tag == "footer":
            self.in_footer = False
        if tag == "section":
            self.in_company = False
        if tag == "a":
            self.in_brand = False
            if self.footer_link is not None:
                self.footer_links.append(tuple(self.footer_link))
                self.footer_link = None

    def handle_data(self, data):
        if self.footer_link is not None:
            self.footer_link[1] += data
        if self.in_brand:
            self.brand_text.append(data)


def read_page(name):
    return PageContent((ROOT / name).read_text(encoding="utf-8"))


class SiteContentTests(unittest.TestCase):
    def test_chinese_home_footer_uses_agreed_labels_and_preserves_destinations(self):
        # Reverting either short label or changing/adding a destination must fail.
        links = read_page("zh.html").footer_links
        self.assertEqual([item for item in links if not item[0].startswith("mailto:")], [
            ("/blog/", "旅行指南"),
            ("#services", "用车服务"),
            ("#company", "公司介绍"),
        ])
        self.assertIn(("mailto:info@mangen.jp", "info@mangen.jp"), links)

    def test_authorized_article_corrections_remove_unsupported_promises(self):
        for name, claims in {
            "first-trip-japan-2026": ["最优解", "轻松游览 4～5 个", "全程不用搬", "往往与反复打车", "包车更稳妥", "随停随走", "都可以放进后备箱"],
            "osaka-kyoto-nara-3days": ["性价比最高", "17:00 前送您回", "约 ¥160K", "约 ¥80K", "60%", "✅ 随时", "也完全可以"],
        }.items():
            source = (ROOT / "content/posts" / f"{name}.md").read_text(encoding="utf-8")
            with self.subTest(article=name):
                for claim in claims:
                    self.assertNotIn(claim, source)
                self.assertIn("确认", source)
                self.assertIn("报价", source)
        etiquette = (ROOT / "content/posts/japan-travel-etiquette.md").read_text(encoding="utf-8")
        self.assertIn("万源的司机都会中文", etiquette)
        self.assertIn("2026 年 11 月 1 日起购买", etiquette)

    def test_footers_do_not_repeat_company_qualifications(self):
        # Restoring a footer's license bindings must fail this test.
        for name in SITE_PAGES:
            with self.subTest(page=name):
                self.assertEqual(
                    [binding for binding, footer, _ in read_page(name).qualifications if footer],
                    [],
                )

    def test_each_homepage_keeps_both_qualifications_once_in_company_section(self):
        # Removing or duplicating a company qualification must fail this test.
        for name in HOME_PAGES:
            with self.subTest(page=name):
                self.assertCountEqual(
                    read_page(name).qualifications,
                    [("license-1", False, True), ("license-2", False, True)],
                )

    def test_brand_has_company_names_without_literal_newline_escape(self):
        # Reintroducing a literal backslash-n between brand spans must fail.
        for name in SITE_PAGES:
            with self.subTest(page=name):
                brand_text = "".join(read_page(name).brand_text)
                self.assertNotIn(r"\n", brand_text)
                self.assertIn("株式会社万源", brand_text)
                if name == "en.html":
                    self.assertIn("Mangen Co., Ltd.", brand_text)
                else:
                    self.assertIn("MANGEN CO., LTD.", brand_text)


if __name__ == "__main__":
    unittest.main()
