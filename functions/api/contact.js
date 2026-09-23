// Cloudflare Pages Function — 接收表单提交
//
// 用法：fetch('/api/contact', { method: 'POST', body: JSON.stringify(...) })
// 环境变量（Pages Settings → Environment variables）：
//   FORMSPREE_ENDPOINT  — 例如 https://formspree.io/f/xxxxxxxx
//   或直接转发到 Zoho SMTP（推荐后续切换到 Resend/Brevo）
//
// 当前实现：转发到 Formspree（免费 50/月）。后续可改为 Resend。

export async function onRequestPost({ request, env }) {
  let data;
  try {
    data = await request.json();
  } catch (e) {
    return new Response(JSON.stringify({ error: 'invalid json' }), {
      status: 400, headers: { 'Content-Type': 'application/json' }
    });
  }

  // 简易校验
  if (!data.name || !data.contact) {
    return new Response(JSON.stringify({ error: 'missing fields' }), {
      status: 400, headers: { 'Content-Type': 'application/json' }
    });
  }

  // 转发到 Formspree（设置 env.FORMSPREE_ENDPOINT 后生效）
  const endpoint = env.FORMSPREE_ENDPOINT;
  if (!endpoint) {
    return new Response(JSON.stringify({ error: 'contact service unavailable' }), {
      status: 503, headers: { 'Content-Type': 'application/json' }
    });
  }

  const r = await fetch(endpoint, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body: JSON.stringify({
      name: data.name,
      contact: data.contact,
      date: data.date,
      pax: data.pax,
      message: data.message,
      _subject: `【万源网站】新咨询 - ${data.name}`,
      _language: data._language || 'ja'
    })
  });

  if (!r.ok) {
    return new Response(JSON.stringify({ error: 'forward failed', status: r.status }), {
      status: 502, headers: { 'Content-Type': 'application/json' }
    });
  }
  const out = await r.json().catch(() => ({}));
  return new Response(JSON.stringify({ ok: true, upstream: out }), {
    headers: { 'Content-Type': 'application/json' }
  });
}

export async function onRequest({ request }) {
  return new Response(JSON.stringify({
    hint: 'POST JSON to /api/contact with {name, contact, date, pax, message}'
  }), { headers: { 'Content-Type': 'application/json' } });
}
