"""Build CMS-owned FAQ blocks and multilingual standalone pages."""
from html import escape
from pathlib import Path
import json
import re

import markdown
import yaml

LANGUAGES = {'zh': ('zh-CN', '/zh', '首页', '联系我们'),
             'ja': ('ja', '/', 'ホーム', 'お問い合わせ'),
             'en': ('en', '/en', 'Home', 'Contact us')}
FAQ_START, FAQ_END = '<!-- faq:start -->', '<!-- faq:end -->'


def localized(data, key, lang, context):
    value = (data.get(key) or {}).get(lang)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'{context}: missing {key}.{lang}')
    return value.strip()


def update_faq(root):
    path = root / 'content/settings/faq.json'
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding='utf-8'))
    sections = {}
    for lang in LANGUAGES:
        entries = []
        if data.get('enabled', True):
            for index, item in enumerate(data.get('items') or []):
                if item.get('hidden', False):
                    continue
                question = escape(localized(item, 'question_i18n', lang, f'FAQ {index + 1}'))
                answer = escape(localized(item, 'answer_i18n', lang, f'FAQ {index + 1}'))
                entries.append(f'<article class="faq-item"><h3><span class="faq-mark" aria-hidden="true">Q</span>{question}</h3>'
                               f'<p><span class="faq-mark" aria-hidden="true">A</span><span>{answer}</span></p></article>')
        sections[lang] = ('<section class="sec faq-section" id="faq" aria-labelledby="faq-title">\n'
                          '<div class="wrap"><h2 id="faq-title">'
                          + escape(localized(data, 'heading_i18n', lang, 'FAQ heading'))
                          + '</h2><div class="faq-list">' + '\n'.join(entries) + '</div></div>\n</section>') if entries else ''
    for lang, filename in [('zh', 'zh.html'), ('ja', 'index.html'), ('en', 'en.html')]:
        page = root / filename
        source = page.read_text(encoding='utf-8')
        block = FAQ_START + '\n' + sections[lang] + '\n' + FAQ_END
        if FAQ_START in source:
            source, count = re.subn(re.escape(FAQ_START) + r'.*?' + re.escape(FAQ_END), lambda _: block, source, flags=re.S)
            if count != 1:
                raise ValueError(f'Duplicate FAQ region in {filename}')
        else:
            if source.count('</main>') != 1:
                raise ValueError(f'Missing main region in {filename}')
            source = source.replace('</main>', block + '\n\n</main>', 1)
        page.write_text(source, encoding='utf-8')


def standalone_html(data, slug, lang):
    code, home, home_label, contact = LANGUAGES[lang]
    title = escape(localized(data, 'title_i18n', lang, slug))
    description = escape(localized(data, 'description_i18n', lang, slug), quote=True)
    body = markdown.markdown(localized(data, 'body_i18n', lang, slug), extensions=['tables', 'fenced_code', 'sane_lists'])
    route = f'/pages/{slug}/' + (f'{lang}/' if lang != 'zh' else '')
    alternates = ''.join(f'<link rel="alternate" hreflang="{code}" href="https://mangen.jp/pages/{slug}/' + (f'{key}/' if key != 'zh' else '') + '">'
                         for key, (code, *_) in LANGUAGES.items())
    switch = ' · '.join(f'<a lang="{code}" href="/pages/{slug}/' + (f'{key}/' if key != 'zh' else '') + f'">{key.upper()}</a>'
                        for key, (code, *_) in LANGUAGES.items())
    return f'''<!DOCTYPE html>
<html lang="{code}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} | 株式会社万源</title><meta name="description" content="{description}">
<link rel="canonical" href="https://mangen.jp{route}">{alternates}
<link rel="stylesheet" href="/assets/css/style.css"><link rel="icon" href="/assets/img/favicon.png"></head>
<body><header class="site-header"><div class="inner"><a class="brand" href="{home}"><span class="brand-ja">株式会社万源</span><span class="brand-en">MANGEN CO., LTD.</span></a><button class="menu-btn" type="button" aria-label="Menu" aria-expanded="false"><span></span><span></span><span></span></button><nav aria-label="Menu"><ul></ul></nav><div class="lang-switch">{switch}</div></div></header>
<main class="wrap cms-page"><nav class="crumb"><a href="{home}">{home_label}</a> / {title}</nav><article><h1>{title}</h1><p class="cms-page-summary">{escape(localized(data, 'description_i18n', lang, slug))}</p><div class="cms-page-body">{body}</div></article><p class="cms-page-contact"><a href="{home}#contact">{contact} →</a></p></main>
<footer class="site-footer"><div class="wrap">© 2026 株式会社万源</div></footer><script src="/assets/js/main.js"></script></body></html>\n'''


def update_pages(root):
    folder = root / 'content/pages'
    output = root / 'pages'
    manifest = output / '_generated.json'
    previous = json.loads(manifest.read_text()) if manifest.exists() else []
    rendered = {}
    for source in sorted(folder.glob('*.md')):
        slug = source.stem
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
            raise ValueError(f'Invalid page ID: {slug}')
        match = re.fullmatch(r'---\s*\n(.*?)\n---\s*\n(.*)', source.read_text(encoding='utf-8'), re.S)
        if not match:
            raise ValueError(f'Missing page metadata: {slug}')
        data = yaml.safe_load(match.group(1)) or {}
        if data.get('draft', False):
            continue
        for lang in LANGUAGES:
            route = f'/pages/{slug}/' + (f'{lang}/' if lang != 'zh' else '')
            rendered[route] = standalone_html(data, slug, lang)
    for route, html in rendered.items():
        path = root / route.strip('/') / 'index.html'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding='utf-8')
    for route in set(previous) - set(rendered):
        if not re.fullmatch(r'/pages/[a-z0-9]+(?:-[a-z0-9]+)*/(?:(?:ja|en)/)?', route):
            raise ValueError('Invalid generated page manifest entry')
        path = root / route.strip('/') / 'index.html'
        path.unlink(missing_ok=True)
    if rendered or manifest.exists():
        output.mkdir(exist_ok=True)
        manifest.write_text(json.dumps(sorted(rendered)), encoding='utf-8')
    return sorted(rendered)


def update_site_pages(root):
    root = Path(root)
    urls = update_pages(root)
    update_faq(root)
    return urls
