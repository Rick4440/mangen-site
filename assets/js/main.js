/* Mangen 静态站 - 客户端数据加载与渲染
 *
 * 数据源（Decap CMS 管理）：
 *   /content/settings/company.json  - 全局公司信息（电话、地址、资质、邮箱）
 *   /content/fleet/fleet.json      - 车型数据（5 项）
 *   /content/posts/*.md            - 博客文章 frontmatter + body
 *
 * 占位约定：HTML 中需要动态填充的元素用 id 或 data-content 标记。
 * main.js 在 DOMContentLoaded 时按页面需求加载对应数据并渲染。
 */
(function () {
  'use strict';

  const LANG = (document.documentElement.lang || 'ja').toLowerCase();
  const BASE = window.location.origin;
  const $ = (sel, root) => (root || document).querySelector(sel);
  const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

  /* --------------------------------------------------------------------
   * 数据加载
   * ------------------------------------------------------------------ */

  async function fetchJSON(path) {
    const r = await fetch(BASE + path, { cache: 'no-store' });
    if (!r.ok) throw new Error('fetch failed: ' + path);
    return r.json();
  }

  async function fetchText(path) {
    const r = await fetch(BASE + path, { cache: 'no-store' });
    if (!r.ok) throw new Error('fetch failed: ' + path);
    return r.text();
  }

  async function fetchIndex() {
    try { return await fetchJSON('/content/posts/_index.json'); }
    catch (e) { return null; }
  }

  /* --------------------------------------------------------------------
   * 全局 header / footer 数据渲染（公司信息、资质、联系）
   * ------------------------------------------------------------------ */

  async function loadGlobal() {
    const data = await fetchJSON('/content/settings/company.json');

    // 公司名（多语言）
    const cn = data.company_name_i18n || {};
    const companyName = cn[LANG] || cn.ja || data.company_name || '株式会社万源';

    // header brand
    const brandName = $('.site-header .brand .name');
    if (brandName) brandName.textContent = companyName;

    // 资质（footer + contact area）
    const lic = data.license || {};
    const lic1 = lic[1] || {};
    const lic2 = lic[2] || {};
    $$('[data-bind="license-1"]').forEach(el => {
      el.innerHTML = `<small>${escapeHTML(lic1.zh || '運輸局免許')}</small><b>${escapeHTML(lic1.value || '—')}</b>`;
    });
    $$('[data-bind="license-2"]').forEach(el => {
      el.innerHTML = `<small>${escapeHTML(lic2.zh || '大阪府登録')}</small><b>${escapeHTML(lic2.value || '—')}</b>`;
    });

    // 联系信息（telbig）
    const phones = data.phones || [];
    const telbox = $('[data-bind="phones"]');
    if (telbox) {
      telbox.innerHTML = phones.map(p => `
        <a class="telbig" href="tel:+${(p.intl || p.number).replace(/[^0-9]/g, '')}">
          <div><small>${escapeHTML(p.city_i18n?.[LANG] || p.city || '')}</small>
               <b>${escapeHTML(p.display || p.number)}</b></div>
        </a>
      `).join('');
    }

    // 渠道徽章
    const channels = data.channels || [];
    const chbox = $('[data-bind="channels"]');
    if (chbox) {
      chbox.innerHTML = channels.map(c => {
        const label = c.label_i18n?.[LANG] || c.label || '';
        const value = c.value || '';
        if (!value || value.includes('準備中')) return '';
        if (label === 'Mail' || label === 'メール' || label === '邮箱' || label === 'Email') {
          return `<a class="ch" href="mailto:${escapeAttr(value)}">${escapeHTML(label)}: ${escapeHTML(value)}</a>`;
        }
        return `<span class="ch">${escapeHTML(label)}: ${escapeHTML(value)}</span>`;
      }).join('');
    }

    // 公司信息表
    const info = $('[data-bind="company-info"]');
    if (info) {
      const rows = data.info_rows_i18n?.[LANG] || data.info_rows || [];
      info.innerHTML = rows.map(r => `
        <tr><td>${escapeHTML(r.label)}</td><td>${escapeHTML(r.value)}</td></tr>
      `).join('');
    }

    // 公司介绍段落
    const desc = $('[data-bind="company-desc"]');
    if (desc && data.desc_i18n) {
      desc.textContent = data.desc_i18n[LANG] || data.desc_i18n.ja || '';
    }

    // Footer copyright
    const cp = $('[data-bind="copyright"]');
    if (cp) cp.textContent = `© ${new Date().getFullYear()} ${companyName}. All Rights Reserved.`;

    // Footer contact list
    const fphones = $('[data-bind="footer-phones"]');
    if (fphones) {
      fphones.innerHTML = phones.map(p => `<li>${escapeHTML(p.city_i18n?.[LANG] || p.city || '')}: ${escapeHTML(p.display || p.number)}</li>`).join('');
    }

    // LocalBusiness Schema
    if (data.schema) {
      const ld = document.createElement('script');
      ld.type = 'application/ld+json';
      ld.textContent = JSON.stringify(data.schema);
      document.head.appendChild(ld);
    }
  }

  /* --------------------------------------------------------------------
   * 车型列表渲染
   * ------------------------------------------------------------------ */

  async function loadFleet() {
    const data = await fetchJSON('/content/fleet/fleet.json');
    const items = (data.items || []).slice().sort((a, b) => (a.order || 0) - (b.order || 0));
    const box = $('[data-bind="fleet"]');
    if (!box) return;
    box.innerHTML = items.map(it => {
      const name = it.name_i18n?.[LANG] || it.name || '';
      const seats = it.seats_i18n?.[LANG] || it.seats || '';
      const img = it.image || '';
      return `
        <div class="card">
          <div class="body"><img src="${escapeAttr(img)}" alt="${escapeAttr(name)}" loading="lazy"></div>
          <div class="info">
            <p class="name">${escapeHTML(name)}</p>
            <p class="seats">${escapeHTML(seats)}</p>
          </div>
        </div>
      `;
    }).join('');
  }

  /* --------------------------------------------------------------------
   * 博客列表
   * ------------------------------------------------------------------ */

  async function loadBlogIndex() {
    const list = $('[data-bind="blog-list"]');
    if (!list) return;
    let idx = await fetchIndex();
    if (!idx) {
      // 降级：硬编码三个文章（首版部署时 Decap 未启用）
      idx = [
        { slug: 'green-plate-guide',      title_i18n: { zh: '日本旅行用车｜绿牌白牌一字之差', ja: '緑ナンバーと白ナンバー', en: 'Green vs White Plate in Japan' }, date: '2026-09-22' },
        { slug: 'japan-travel-etiquette', title_i18n: { zh: '访日旅游礼仪与注意事项', ja: '訪日マナー', en: 'Japan Travel Etiquette' }, date: '2026-09-22' },
        { slug: 'osaka-kyoto-nara-3days', title_i18n: { zh: '大阪・京都・奈良 3 日包车路线', ja: '大阪・京都・奈良 3 日コース', en: 'Osaka-Kyoto-Nara 3 Days' }, date: '2026-09-22' }
      ];
    }
    list.innerHTML = idx.map(p => {
      const title = p.title_i18n?.[LANG] || p.title || p.slug;
      const excerpt = p.excerpt_i18n?.[LANG] || p.excerpt || '';
      return `
        <a class="blog-card" href="/blog/${p.slug}">
          <time>${escapeHTML(p.date || '')}</time>
          <h3>${escapeHTML(title)}</h3>
          <p>${escapeHTML(excerpt)}</p>
        </a>
      `;
    }).join('');
  }

  /* --------------------------------------------------------------------
   * 单篇博客（页面级模板）
   * ------------------------------------------------------------------ */

  async function loadSinglePost() {
    const article = $('[data-bind="article"]');
    if (!article) return;
    const slug = article.dataset.slug + '.md';
    let md;
    try {
      md = await fetchText('/content/posts/' + slug);
    } catch (e) {
      // 文件未生成：降级静态导航
      return;
    }
    const { fm, body } = parseFrontmatter(md);
    const title = fm.title_i18n?.[LANG] || fm.title || '';
    const date = fm.date || '';
    article.querySelector('[data-bind="post-title"]').textContent = title;
    article.querySelector('[data-bind="post-date"]').textContent = date;
    article.querySelector('[data-bind="post-body"]').innerHTML = renderMarkdown(body);

    // Article schema
    const ld = document.createElement('script');
    ld.type = 'application/ld+json';
    ld.textContent = JSON.stringify({
      '@context': 'https://schema.org',
      '@type': 'Article',
      'headline': title,
      'datePublished': date,
      'author': { '@type': 'Organization', 'name': '株式会社万源' },
      'publisher': { '@type': 'Organization', 'name': '株式会社万源' }
    });
    document.head.appendChild(ld);
  }

  /* --------------------------------------------------------------------
   * Frontmatter / Markdown 解析（极简版，足够用）
   * ------------------------------------------------------------------ */

  function parseFrontmatter(md) {
    if (!md.startsWith('---')) return { fm: {}, body: md };
    const end = md.indexOf('\n---', 3);
    if (end < 0) return { fm: {}, body: md };
    const raw = md.slice(3, end).trim();
    const body = md.slice(end + 4).trim();
    const fm = {};
    raw.split('\n').forEach(line => {
      const m = line.match(/^(\w+):\s*(.*)$/);
      if (!m) return;
      let v = m[2].trim();
      if (v.startsWith('"') && v.endsWith('"')) v = v.slice(1, -1);
      fm[m[1]] = v;
    });
    return { fm, body };
  }

  function renderMarkdown(md) {
    // 极简 Markdown → HTML（够博客文章用：# ## ### - * ** > | 段落）
    const lines = md.split('\n');
    let html = '';
    let inList = false;
    let inQuote = false;
    for (let line of lines) {
      line = line.trimEnd();
      if (!line) {
        if (inList) { html += '</ul>'; inList = false; }
        if (inQuote) { html += '</blockquote>'; inQuote = false; }
        html += '';
        continue;
      }
      if (/^### /.test(line)) {
        if (inList) html += '</ul>';
        if (inQuote) html += '</blockquote>';
        html += `<h3>${inline(line.slice(4))}</h3>`;
      } else if (/^## /.test(line)) {
        if (inList) html += '</ul>';
        if (inQuote) html += '</blockquote>';
        html += `<h2>${inline(line.slice(3))}</h2>`;
      } else if (/^# /.test(line)) {
        if (inList) html += '</ul>';
        if (inQuote) html += '</blockquote>';
        html += `<h2>${inline(line.slice(2))}</h2>`;
      } else if (/^[-*] /.test(line)) {
        if (!inList) html += '<ul>';
        inList = true;
        html += `<li>${inline(line.slice(2))}</li>`;
      } else if (/^> /.test(line)) {
        if (!inQuote) html += '<blockquote style="border-left:3px solid var(--accent);padding:8px 14px;color:var(--sub);margin:14px 0">';
        inQuote = true;
        html += `<p>${inline(line.slice(2))}</p>`;
      } else {
        if (inList) html += '</ul>';
        if (inQuote) html += '</blockquote>';
        html += `<p>${inline(line)}</p>`;
      }
    }
    if (inList) html += '</ul>';
    if (inQuote) html += '</blockquote>';
    return html;
  }

  function inline(s) {
    return escapeHTML(s)
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`(.+?)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2">$1</a>');
  }

  function escapeHTML(s) {
    return String(s || '').replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;' }[c]));
  }
  function escapeAttr(s) { return escapeHTML(s); }

  /* --------------------------------------------------------------------
   * 表单提交（Formspree 占位 + Cloudflare Worker 备选）
   * ------------------------------------------------------------------ */

  function bindForm() {
    const form = $('[data-form="contact"]');
    if (!form) return;
    form.addEventListener('submit', async e => {
      e.preventDefault();
      const btn = form.querySelector('button');
      const status = form.querySelector('.status');
      btn.disabled = true;
      status.className = 'status'; status.textContent = '';
      try {
        const data = Object.fromEntries(new FormData(form));
        if (data.website) return;
        delete data.website;
        data.subject = '【万源网站】新咨询 - ' + data.name;
        data.from_name = '株式会社万源 官网';
        data.botcheck = false;
        if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.contact)) data.email = data.contact;
        const r = await fetch('https://api.web3forms.com/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
          body: JSON.stringify(data)
        });
        if (!r.ok) throw new Error(r.status === 429 ? 'rate-limited' : 'submit-failed');
        if ((await r.json()).success !== true) throw new Error('submit-failed');
        status.classList.add('success');
        status.textContent = (window.I18N_FORM_SUCCESS || '送信が完了しました。担当者より折り返しご連絡いたします。');
        form.reset();
      } catch (err) {
        status.classList.add('error');
        const lang = document.documentElement.lang;
        status.textContent = err.message === 'rate-limited'
          ? (lang === 'en' ? 'Too many requests. Please try again later.' : lang === 'ja' ? '送信回数が多すぎます。時間をおいて再試行してください。' : '提交过于频繁，请稍后重试。') + ' '
          : (window.I18N_FORM_ERROR || '送信できませんでした。メールでお問い合わせください。') + ' ';
        const mail = document.createElement('a');
        const details = Object.fromEntries([...new FormData(form)].filter(([key]) => key !== 'website'));
        mail.href = 'mailto:mangeninc@gmail.com?subject=' + encodeURIComponent('万源网站咨询') + '&body=' + encodeURIComponent(Object.entries(details).map(([key, value]) => key + ': ' + value).join('\n'));
        mail.textContent = document.documentElement.lang === 'en' ? 'Open email draft' : document.documentElement.lang === 'ja' ? 'メールで問い合わせる' : '打开邮件草稿';
        status.appendChild(mail);
      } finally {
        btn.disabled = false;
      }
    });
  }

  /* --------------------------------------------------------------------
   * 语言切换（基于路径前缀）
   * ------------------------------------------------------------------ */

  function bindLangSwitch() {
    $$('.lang-switch a').forEach(a => {
      const href = a.getAttribute('href');
      const target = href.replace(BASE, '').replace(/^\//, '');
      const cur = location.pathname.replace(/^\//, '');
      if (target === cur || (target === 'index.html' && cur === '')) {
        a.classList.add('active');
      }
    });
  }

  function bindMobileMenu() {
    const btn = $('.menu-btn');
    const nav = $('.site-header nav');
    if (!btn || !nav) return;
    btn.addEventListener('click', () => nav.classList.toggle('open'));
  }

  /* --------------------------------------------------------------------
   * 启动
   * ------------------------------------------------------------------ */

  document.addEventListener('DOMContentLoaded', async () => {
    bindLangSwitch();
    bindMobileMenu();
    bindForm();
    try {
      await loadGlobal();
      await Promise.all([loadFleet(), loadBlogIndex(), loadSinglePost()]);
    } catch (e) {
      console.warn('[mgn] data load partial failure:', e);
    }
  });
})();