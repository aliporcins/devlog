// POST /api/logout — deletes the session row and clears the cookie.
import { parseCookies, clearSessionCookie, json } from "./_shared.js";

export async function onRequestPost(context) {
  try {
    const token = parseCookies(context.request.headers.get("Cookie")).blog_session;
    if (token && context.env.DB) {
      await context.env.DB.prepare(
        "DELETE FROM blog_sessions WHERE token = ?",
      ).bind(token).run();
    }
  } catch (e) { /* still clear the cookie */ }
  return json({ ok: true }, 200, { "Set-Cookie": clearSessionCookie() });
}
