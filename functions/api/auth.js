// GitHub OAuth entrypoint for the Decap CMS popup.
export async function onRequestGet({ request, env }) {
  const origin = new URL(request.url).origin;
  if (origin !== "https://mangen.jp" || !env.GITHUB_CLIENT_ID || !env.GITHUB_CLIENT_SECRET) {
    return new Response("CMS authentication is not configured", { status: 503 });
  }
  const state = crypto.randomUUID();
  const authorization = new URL("https://github.com/login/oauth/authorize");
  authorization.searchParams.set("client_id", env.GITHUB_CLIENT_ID);
  authorization.searchParams.set("redirect_uri", origin + "/api/callback");
  authorization.searchParams.set("scope", "public_repo");
  authorization.searchParams.set("state", state);
  return new Response(null, {
    status: 302,
    headers: {
      Location: authorization.toString(),
      "Set-Cookie": `cms_oauth_state=${state}; HttpOnly; Secure; SameSite=Lax; Path=/api/callback; Max-Age=600`,
      "Cache-Control": "no-store",
    },
  });
}
