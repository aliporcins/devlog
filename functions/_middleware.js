// Site-wide password gate for the devlog blog (Pages Functions middleware).
// Every route requires a valid blog_session cookie, except the routes the
// login/setup flow itself needs. The login and setup pages are fully
// self-contained (inline CSS/JS), so no static asset needs exempting.
// Sessions live in D1 table blog_sessions; the password hash lives in
// blog_settings under key "password_hash". Fail closed: any DB problem
// sends the visitor to /login instead of letting them through.

const EXEMPT = new Set([
  "/login",
  "/setup",
  "/api/login",
  "/api/setup",
  "/api/logout",
  "/logout",
  "/favicon.ico",
]);

function parseCookies(header) {
  const out = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    out[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }
  return out;
}

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

export async function onRequest(context) {
  const url = new URL(context.request.url);
  if (EXEMPT.has(url.pathname)) return context.next();
  try {
    if (!context.env.DB) throw new Error("DB binding missing");
    const token = parseCookies(context.request.headers.get("Cookie")).blog_session;
    if (token) {
      const row = await context.env.DB.prepare(
        "SELECT token FROM blog_sessions WHERE token = ? AND expires_at > ?",
      ).bind(token, nowSeconds()).first();
      if (row) return context.next();
    }
  } catch (e) {
    // Fail closed: fall through to the login redirect below.
  }
  return Response.redirect(new URL("/login", url.origin).toString(), 302);
}
