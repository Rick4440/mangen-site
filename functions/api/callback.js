function popup(status, payload) {
  // Serialize twice: the outer string is Decap's message, the inner JSON is its data.
  const message = `authorization:github:${status}:${JSON.stringify(payload)}`;
  return new Response(`<!doctype html><html><head><meta charset="utf-8"><title>GitHub login</title></head><body><script>
    if (window.opener) {
      window.opener.postMessage('authorizing:github', 'https://mangen.jp');
      window.addEventListener('message', function(event) {
        if (event.origin !== 'https://mangen.jp' || event.data !== 'authorizing:github') return;
        window.opener.postMessage(${JSON.stringify(message)}, 'https://mangen.jp');
        window.close();
      });
    } else { document.body.textContent = 'Please return to the CMS and try again.'; }
  </script></body></html>`, {
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'", "Set-Cookie": "cms_oauth_state=; HttpOnly; Secure; SameSite=Lax; Path=/api/callback; Max-Age=0" },
  });
}

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  if (url.origin !== "https://mangen.jp" || !env.GITHUB_CLIENT_ID || !env.GITHUB_CLIENT_SECRET) {
    return new Response("CMS authentication is not configured", { status: 503 });
  }
  const state = url.searchParams.get("state");
  const cookie = request.headers.get("Cookie")?.match(/(?:^|;\s*)cms_oauth_state=([0-9a-f-]+)/)?.[1];
  if (!state || !cookie || state !== cookie || !url.searchParams.get("code")) {
    return popup("error", { message: "Invalid or expired login. Please try again." });
  }
  try {
    const response = await fetch("https://github.com/login/oauth/access_token", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ client_id: env.GITHUB_CLIENT_ID, client_secret: env.GITHUB_CLIENT_SECRET,
        code: url.searchParams.get("code"), redirect_uri: url.origin + "/api/callback", state }),
    });
    const result = await response.json();
    if (!response.ok || !result.access_token) return popup("error", { message: "GitHub authorization failed" });
    return popup("success", { token: result.access_token, provider: "github" });
  } catch {
    return popup("error", { message: "GitHub is temporarily unavailable" });
  }
}
