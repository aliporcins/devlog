// GET /logout — clears the session (row + cookie) and sends the
// visitor back to the login page.
import { parseCookies, clearSessionCookie } from "./api/_shared.js";

export async function onRequestGet(context) {
  try {
    const token = parseCookies(context.request.headers.get("Cookie")).blog_session;
    if (token && context.env.DB) {
      await context.env.DB.prepare(
        "DELETE FROM blog_sessions WHERE token = ?",
      ).bind(token).run();
    }
  } catch (e) { /* still clear the cookie */ }
  return new Response(null, {
    status: 302,
    headers: {
      Location: new URL("/login", context.request.url).toString(),
      "Set-Cookie": clearSessionCookie(),
    },
  });
}
