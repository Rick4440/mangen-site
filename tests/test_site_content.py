"""Regression checks for the shared site branding and company qualifications.

Run with: python -m unittest discover -s tests -v
"""
from html.parser import HTMLParser
from pathlib import Path
import json
import re
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

    def test_service_area_names_tokyo_and_kanto_before_osaka_and_kansai(self):
        # Reverting the owner order (Tokyo / Kanto first) must fail.
        company = json.loads((ROOT / "content/settings/company.json").read_text(encoding="utf-8"))
        areas = {lang: next(row["value"] for row in rows if row["label"] in ("対応エリア", "服务区域", "Area"))
                 for lang, rows in company["info_rows_i18n"].items()}
        self.assertEqual(areas["ja"], "関東・関西中心（その他地域はご相談ください）")
        self.assertEqual(areas["zh"], "以关东、关西为主（其他地区可咨询）")
        self.assertEqual(areas["en"], "Mainly Kanto & Kansai (other areas on request)")
        self.assertEqual(company["schema"]["description"], "東京・大阪の空港送迎・貸切ハイヤー。日中英対応ドライバー。")
        self.assertEqual(
            [area["name"] for area in company["schema"]["areaServed"]],
            ["Tokyo Metropolis", "Osaka Prefecture", "Kanto", "Kansai"],
        )
        # Headquarters stays Osaka, so the phone list stays Osaka then Tokyo.
        self.assertEqual([phone["city"] for phone in company["phones"]], ["大阪", "東京"])

        stale = (
            "大阪・東京", "関西・関東", "大阪・东京", "关西、关东",
            "Osaka and Tokyo", "Kansai and Kanto", "Kansai &amp; Kanto", "Kansai & Kanto",
            "in Osaka, Tokyo",
        )
        expected = {
            "index.html": ("東京・大阪の空港送迎・貸切ハイヤー", "関東・関西を中心に"),
            "zh.html": ("东京・大阪机场接送与包车服务", "以关东、关西为主", "东京（关东）、大阪（关西）"),
            "en.html": ("in Tokyo and Osaka", "Kanto and Kansai", "Kanto &amp; Kansai", "in Tokyo, Osaka"),
        }
        for name, phrases in expected.items():
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                for phrase in phrases:
                    self.assertIn(phrase, source)
                for phrase in stale:
                    self.assertNotIn(phrase, source)
                schema = json.loads(re.search(
                    r'<script id="business-schema" type="application/ld\+json">(.*?)</script>',
                    source,
                ).group(1))
                self.assertEqual(schema["description"], company["schema"]["description"])
                self.assertEqual(schema["areaServed"], company["schema"]["areaServed"])
                self.assertLess(source.index("072-275-4665"), source.index("042-649-9057"))

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
