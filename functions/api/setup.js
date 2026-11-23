// POST /api/setup — one-time only. Stores only the SHA-256 hash of the
// password the owner sets himself, then issues a session. After setup,
// both /setup and /api/setup return 404.
import { sha256Hex, newSessionToken, sessionCookie, json } from "./_shared.js";

export async function onRequestPost(context) {
  try {
    const existing = await context.env.DB.prepare(
      "SELECT value FROM blog_settings WHERE key = 'password_hash'",
    ).first();
    if (existing) return json({ error: "not found" }, 404);
    const body = await context.request.json().catch(() => null);
    const password = body && typeof body.password === "string" ? body.password : "";
    if (password.length < 8) return json({ error: "password too short" }, 400);
    await context.env.DB.prepare(
      "INSERT INTO blog_settings (key, value) VALUES ('password_hash', ?)",
    ).bind(await sha256Hex(password)).run();
    const token = newSessionToken();
    const expiresAt = Math.floor(Date.now() / 1000) + 7 * 24 * 3600;
    await context.env.DB.prepare(
      "INSERT INTO blog_sessions (token, expires_at) VALUES (?, ?)",
    ).bind(token, expiresAt).run();
    return json({ ok: true }, 200, { "Set-Cookie": sessionCookie(token, 7 * 24 * 3600) });
  } catch (e) {
    return json({ error: "server error" }, 500);
  }
}
