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
    def test_section_headings_match_nav_labels(self):
        # Nav wording is the source of truth for each in-page anchor.
        anchors = ("services", "fleet", "contact", "company")
        stale = ("服务内容", "车型介绍", "关于我们", "サービス内容", "車両ラインナップ")
        for name in HOME_PAGES:
            source = (ROOT / name).read_text(encoding="utf-8")
            nav = source.split("<nav>", 1)[1].split("</nav>", 1)[0]
            with self.subTest(page=name):
                for anchor in anchors:
                    label = re.search(rf'href="#{anchor}">([^<]+)</a>', nav).group(1)
                    section = source.split(f'id="{anchor}"', 1)[1].split("</section>", 1)[0]
                    heading = re.search(r"<h2>([^<]+)</h2>", section).group(1)
                    self.assertEqual(heading, label)
                checked = source
                if name == "zh.html" and "<!-- home-guides:start -->" in source:
                    checked = source.split("<!-- home-guides:start -->", 1)[0] + source.split("<!-- home-guides:end -->", 1)[1]
                for phrase in stale:
                    self.assertNotIn(phrase, checked)
                if name == "zh.html":
                    self.assertIn('href="/blog/">旅行指南</a>', nav)
                    self.assertNotIn('href="#guides"', nav)
                    guide = source.split('id="guides"', 1)[1].split("</section>", 1)[0]
                    self.assertIn("<h2>旅行指南</h2>", guide)
                    self.assertIn('href="/blog/">查看全部 →</a>', guide)
                    self.assertNotIn("查看全部旅行指南", guide)
                    self.assertNotIn("home-guides-more", guide)
                    self.assertEqual(guide.count("home-guide--lead"), 1)
                    self.assertEqual(guide.count("home-guide--row"), 4)
                    self.assertLess(source.index('id="fleet"'), source.index('id="guides"'))
                    self.assertLess(source.index('id="guides"'), source.index('id="contact"'))
                    self.assertLess(source.index('id="guides"'), source.index('id="company"'))
                else:
                    self.assertNotIn('id="guides"', source)
                    self.assertNotIn("查看全部旅行指南", source)
                    self.assertIn('href="/blog/"', nav)
        for name in ("scripts/journal-header.html", "assets/js/main.js", "assets/js/journal.js"):
            source = (ROOT / name).read_text(encoding="utf-8")
            for phrase in stale:
                self.assertNotIn(phrase, source)

    def test_reasons_sit_inside_the_company_section(self):
        # The old standalone why-choose section must not return.
        expected = {
            "index.html": ("万源が選ばれる理由", ("真心", "熱意", "忍耐", "責任感")),
            "zh.html": ("选择万源的理由", ("真心", "热心", "耐心", "责任心")),
            "en.html": ("Why Mangen", ("Sincerity", "Passion", "Patience", "Responsibility")),
        }
        for name, (heading, words) in expected.items():
            source = (ROOT / name).read_text(encoding="utf-8")
            company = source.split('id="company"', 1)[1].split("</section>", 1)[0]
            with self.subTest(page=name):
                self.assertNotIn('<section class="sec" id="quality">', source)
                self.assertNotIn("<h2>選ばれる理由</h2>", source)
                self.assertNotIn("<h2>选择万源的理由</h2>", source)
                self.assertNotIn("<h2>Why Choose Us</h2>", source)
                self.assertIn(f'id="quality"', company)
                self.assertIn(f"<h3>{heading}</h3>", company)
                self.assertLess(company.index('data-bind="company-desc"'), company.index("<h3>"))
                self.assertLess(company.index("<h3>"), company.index('data-bind="company-info"'))
                self.assertLess(company.index('data-bind="company-info"'), company.index('data-bind="license-1"'))
                for word in words:
                    self.assertIn(f"<span class=\"zh\">{word}</span>", company)

    def test_booking_steps_sit_inside_the_contact_section(self):
        # The old standalone booking section must not return.
        expected = {
            "index.html": ("ご予約の流れ", ("ご予約", "お見積り確認", "ご出発")),
            "zh.html": ("预约流程", ("预约", "确认报价", "出行")),
            "en.html": ("How to Book", ("Request", "Confirm the quote", "Travel")),
        }
        for name, (heading, steps) in expected.items():
            source = (ROOT / name).read_text(encoding="utf-8")
            contact = source.split('id="contact"', 1)[1].split("</section>", 1)[0]
            with self.subTest(page=name):
                self.assertNotIn('<section class="sec" id="flow">', source)
                self.assertNotIn('<section class="sec alt" id="flow">', source)
                self.assertNotIn("<h2>ご利用の流れ</h2>", source)
                self.assertNotIn("<h2>预约流程</h2>", source)
                self.assertNotIn("<h2>How it works</h2>", source)
                self.assertIn('id="flow"', contact)
                self.assertIn(f"<h3>{heading}</h3>", contact)
                self.assertLess(contact.index("<h2>"), contact.index("<h3>"))
                self.assertLess(contact.index("<h3>"), contact.index('data-bind="phones"'))
                self.assertLess(contact.index('data-bind="phones"'), contact.index('data-form="contact"'))
                for step in steps:
                    self.assertIn(f"<span>{step}</span>", contact)

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

    def test_fleet_cards_show_luggage_and_use_in_the_existing_order(self):
        # Dropping a luggage line, a use line, or reordering the vehicles must fail.
        fleet = json.loads((ROOT / "content/fleet/fleet.json").read_text(encoding="utf-8"))
        self.assertEqual([item["id"] for item in fleet["items"]], ["alphard", "hiace", "coaster", "vclass", "sclass"])
        notes = {
            "index.html": "荷物は28インチのスーツケースで数えています。乗車人数が多い場合、積める荷物は少なくなります。",
            "zh.html": "行李以 28 寸箱计，乘客较多时可放行李会相应减少。",
            "en.html": "Luggage is counted as 28-inch suitcases. Capacity decreases when more passengers are traveling.",
        }
        lang = {"index.html": "ja", "zh.html": "zh", "en.html": "en"}
        renderer = (ROOT / "assets/js/main.js").read_text(encoding="utf-8")
        self.assertIn('class="luggage"', renderer)
        self.assertIn('class="use"', renderer)
        self.assertIn("luggage_i18n", renderer)
        self.assertIn("use_i18n", renderer)
        for name in HOME_PAGES:
            source = (ROOT / name).read_text(encoding="utf-8")
            section = source.split('id="fleet"', 1)[1].split("</section>", 1)[0]
            code = lang[name]
            cards = section.split('class="card"')[1:]
            with self.subTest(page=name):
                self.assertIn(notes[name], section)
                self.assertEqual(len(cards), len(fleet["items"]))
                for card, item in zip(cards, fleet["items"]):
                    for field in ("name_i18n", "seats_i18n", "luggage_i18n", "use_i18n"):
                        self.assertIn(item[field][code], card)

    def test_language_switchers_use_short_codes_with_descriptive_names(self):
        # Visible labels are JA / ZH / EN. The accessible name stays the language's own name.
        expected = (
            'hreflang="ja" lang="ja" aria-label="日本語">JA</a>',
            'hreflang="zh-CN" lang="zh-CN" aria-label="中文">ZH</a>',
            'hreflang="en" lang="en" aria-label="English">EN</a>',
        )
        for name in ("index.html", "zh.html", "en.html", "scripts/journal-header.html"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                for snippet in expected:
                    self.assertIn(snippet, source)
                self.assertIn('href="/"', source)
                self.assertIn('href="/zh"', source)
                self.assertIn('href="/en"', source)
                self.assertNotIn("日本語首页", source)
                self.assertNotIn("英语首页", source)
                self.assertNotIn("English 首页", source)
                self.assertNotIn(">日本語</a>", source)
                self.assertNotIn(">中文</a>", source)
                self.assertNotIn(">English</a>", source)
        cluster = (
            '<link rel="alternate" hreflang="ja" href="https://mangen.jp/">',
            '<link rel="alternate" hreflang="zh-CN" href="https://mangen.jp/zh">',
            '<link rel="alternate" hreflang="en" href="https://mangen.jp/en">',
            '<link rel="alternate" hreflang="x-default" href="https://mangen.jp/">',
        )
        for name in ("index.html", "zh.html", "en.html"):
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(hreflang=name):
                for snippet in cluster:
                    self.assertIn(snippet, source)

    def test_not_found_page_names_each_home_in_its_own_language(self):
        source = (ROOT / "404.html").read_text(encoding="utf-8")
        self.assertIn('href="/" hreflang="ja" lang="ja">日本語トップ</a>', source)
        self.assertIn('href="/zh" hreflang="zh-CN" lang="zh-CN">中文首页</a>', source)
        self.assertIn('href="/en" hreflang="en" lang="en">English Home</a>', source)
        self.assertNotIn("日本語首页", source)
        self.assertNotIn("English home", source)
        self.assertIn('path.indexOf("/zh/")', source)
        self.assertIn('path.indexOf("/en/")', source)

    def test_company_hours_are_not_published(self):
        company = json.loads((ROOT / "content/settings/company.json").read_text(encoding="utf-8"))
        self.assertNotIn("openingHours", company["schema"])
        for rows in company["info_rows_i18n"].values():
            labels = [row["label"] for row in rows]
            self.assertNotIn("営業時間", labels)
            self.assertNotIn("营业时间", labels)
            self.assertNotIn("Hours", labels)
        for name in HOME_PAGES:
            source = (ROOT / name).read_text(encoding="utf-8")
            with self.subTest(page=name):
                self.assertNotIn("openingHours", source)
                self.assertNotIn("24時間", source)
                self.assertNotIn("24 小时", source)
                self.assertNotIn(">24h<", source)
                self.assertNotIn("Hours:", source)

    def test_founding_date_follows_the_company_name(self):
        company = json.loads((ROOT / "content/settings/company.json").read_text(encoding="utf-8"))
        self.assertEqual(company["schema"]["foundingDate"], "2020-08")
        expected = {
            "ja": ("設立", "2020年8月"),
            "zh": ("成立时间", "2020年8月"),
            "en": ("Established", "August 2020"),
        }
        representatives = {
            "ja": ("代表者", "代表取締役 梁超"),
            "zh": ("代表人", "代表董事 梁超"),
            "en": ("Representative", "Chao Liang, Representative Director"),
        }
        self.assertNotIn("founder", company["schema"])
        for lang, row in expected.items():
            rows = company["info_rows_i18n"][lang]
            self.assertEqual((rows[1]["label"], rows[1]["value"]), row)
            self.assertEqual((rows[2]["label"], rows[2]["value"]), representatives[lang])
            self.assertIn(rows[0]["label"], ("会社名", "公司名称", "Company"))
        pages = {
            "index.html": (
                "<tr><td>設立</td><td>2020年8月</td></tr>",
                "<tr><td>代表者</td><td>代表取締役 梁超</td></tr>",
            ),
            "zh.html": (
                "<tr><td>成立时间</td><td>2020年8月</td></tr>",
                "<tr><td>代表人</td><td>代表董事 梁超</td></tr>",
            ),
            "en.html": (
                "<tr><td>Established</td><td>August 2020</td></tr>",
                "<tr><td>Representative</td><td>Chao Liang, Representative Director</td></tr>",
            ),
        }
        for name, (founded, representative) in pages.items():
            source = (ROOT / name).read_text(encoding="utf-8")
            table = source.split('data-bind="company-info"', 1)[1].split("</tbody>", 1)[0]
            schema = json.loads(re.search(
                r'<script id="business-schema" type="application/ld\+json">(.*?)</script>',
                source,
            ).group(1))
            with self.subTest(page=name):
                self.assertLess(table.index(founded), table.index(representative))
                self.assertLess(table.index(representative), table.index("1147-33"))
                self.assertEqual(schema["foundingDate"], "2020-08")
                self.assertNotIn("founder", schema)

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
