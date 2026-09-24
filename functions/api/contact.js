// Cloudflare Pages Function — 接收表单提交
//
// 用法：fetch('/api/contact', { method: 'POST', body: JSON.stringify(...) })
// 环境变量（Pages Settings → Environment variables）：
//   FORMSPREE_ENDPOINT  — 例如 https://formspree.io/f/xxxxxxxx
//   或直接转发到 Zoho SMTP（推荐后续切换到 Resend/Brevo）
//
// 当前实现：服务端转发到 Formspree，终端访客只访问本站接口。

const json = (body, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }
});

export async function onRequestPost({ request, env }) {
  if (request.headers.get('content-type')?.split(';')[0].trim() !== 'application/json') {
    return json({ error: 'invalid content type' }, 415);
  }
  if (Number(request.headers.get('content-length')) > 10000) {
    return json({ error: 'request too large' }, 413);
  }
  let data;
  try {
    data = await request.json();
  } catch {
    return json({ error: 'invalid json' }, 400);
  }

  if (!data || typeof data !== 'object' || Array.isArray(data)) {
    return json({ error: 'invalid fields' }, 400);
  }

  // 蜜罐字段：自动填写的垃圾提交不发送通知。
  if (data.website) return json({ ok: true });
  const name = String(data.name || '').trim();
  const contact = String(data.contact || '').trim();
  if (!name || !contact || name.length > 120 || contact.length > 240 ||
      String(data.message || '').length > 3000) {
    return json({ error: 'invalid fields' }, 400);
  }

  // Cloudflare Pages 的生产环境变量；请勿把 Formspree 地址放进前端脚本。
  const endpoint = env.FORMSPREE_ENDPOINT;
  if (!/^https:\/\/formspree\.io\/f\/[a-zA-Z0-9]+$/.test(endpoint || '')) {
    return json({ error: 'contact service unavailable' }, 503);
  }

  let r;
  try {
    r = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
      body: JSON.stringify({
        name, contact,
        date: String(data.date || '').slice(0, 30),
        pax: String(data.pax || '').slice(0, 120),
        message: String(data.message || ''),
        _subject: `【万源网站】新咨询 - ${name}`,
        _language: String(data._language || 'ja').slice(0, 10)
      })
    });
  } catch {
    return json({ error: 'delivery unavailable' }, 502);
  }

  if (!r.ok) {
    return json({ error: r.status === 429 ? 'rate limited' : 'delivery failed' }, r.status === 429 ? 429 : 502);
  }
  return json({ ok: true });
}

export async function onRequest({ request }) {
  return new Response(JSON.stringify({
    hint: 'POST JSON to /api/contact with {name, contact, date, pax, message}'
  }), { headers: { 'Content-Type': 'application/json' } });
}
