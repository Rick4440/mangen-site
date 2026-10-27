"""One CMS-owned set of localized links for site headers and footers."""
from html import escape
from pathlib import Path
import json
import re

HOMES = {'zh': '/zh', 'ja': '/', 'en': '/en'}
TARGETS = {'services', 'fleet', 'blog', 'contact', 'company', 'faq'}


def localized(data, key, lang):
    value = (data.get(key) or {}).get(lang)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Missing navigation text: {key}.{lang}')
    return escape(value.strip(), quote=True)


def links(data, lang, faq_visible, active=False):
    items = []
    seen = set()
    for item in data.get('items') or []:
        target = item.get('target')
        if target not in TARGETS or target in seen:
            raise ValueError(f'Invalid or duplicate navigation target: {target}')
        seen.add(target)
        if target == 'faq' and not faq_visible:
            continue
        href = '/blog/' if target == 'blog' else HOMES[lang] + '#' + target
        selected = ' class="active"' if active and target == 'blog' else ''
        items.append(f'<li><a{selected} href="{href}">{localized(item, "label_i18n", lang)}</a></li>')
    return ''.join(items)


def footer(data, company, lang, faq_visible):
    name = escape(company.get('company_name_i18n', {}).get(lang) or company['company_name'])
    rows = company.get('info_rows_i18n', {}).get(lang, [])
    address = next((row['value'] for row in rows if row['label'] in ('地址','所在地','Address')), '')
    phones = ''.join('<li>' + escape(p.get('city_i18n', {}).get(lang) or p.get('city', '')) + ': '
                     + escape(p.get('display') or p.get('number', '')) + '</li>' for p in company.get('phones', []))
    email = next((channel['value'] for channel in company.get('channels', [])
                  if not channel.get('pending') and '@' in channel.get('value', '')), '')
    return ('<footer class="site-footer"><div class="inner">'
            f'<div><h4>{name}</h4><p>{localized(data,"footer_tagline_i18n",lang)}</p><p>{escape(address)}</p></div>'
            f'<div><h4>{localized(data,"contact_heading_i18n",lang)}</h4><ul data-bind="footer-phones">{phones}</ul>'
            f'<p><a href="mailto:{escape(email, quote=True)}">{escape(email)}</a></p></div>'
            f'<nav class="footer-links" aria-label="{localized(data,"footer_heading_i18n",lang)}">'
            f'<h4>{localized(data,"footer_heading_i18n",lang)}</h4><ul class="footer-navigation">'
            + links(data, lang, faq_visible) + '</ul></nav></div>'
            f'<div class="copy" data-bind="copyright">© 2026 {name}. All Rights Reserved.</div></footer>')


def update_site_navigation(root):
    root = Path(root)
    config = root/'content/settings/navigation.json'
    if not config.exists():
        return
    data = json.loads(config.read_text(encoding='utf-8'))
    company = json.loads((root/'content/settings/company.json').read_text(encoding='utf-8'))
    faq_path = root/'content/settings/faq.json'
    faq = json.loads(faq_path.read_text(encoding='utf-8')) if faq_path.exists() else {}
    visible = faq.get('enabled', True) and any(not item.get('hidden') for item in faq.get('items') or [])
    paths = [root/name for name in ('index.html','zh.html','en.html','404.html') if (root/name).exists()]
    for folder in ('blog','editorial','pages','scripts'):
        paths.extend(sorted((root/folder).rglob('*.html')))
    for path in paths:
        original = path.read_text(encoding='utf-8')
        language = re.search(r'<html[^>]*lang="([^"]+)"', original)
        lang = language.group(1).split('-')[0] if language else 'zh'
        if lang not in HOMES:
            continue
        menu = links(data, lang, visible, active='/blog/' in '/' + str(path.relative_to(root)) or path.name == 'journal-header.html')
        def replace_header(match):
            return re.sub(r'(<nav\b[^>]*>).*?(</nav>)', lambda nav: nav.group(1) + '<ul>' + menu + '</ul>' + nav.group(2), match.group(0), count=1, flags=re.S)
        updated = re.sub(r'<header\b[^>]*class="[^"]*site-header[^\"]*"[^>]*>.*?</header>', replace_header, original, count=1, flags=re.S)
        updated = re.sub(r'<footer\b[^>]*class="(?:site-footer|journal-footer)"[^>]*>.*?</footer>', lambda _: footer(data, company, lang, visible), updated, count=1, flags=re.S)
        if updated != original:
            path.write_text(updated, encoding='utf-8')
