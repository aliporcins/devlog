// POST /api/login — checks the password hash, issues a 7-day session.
import { sha256Hex, newSessionToken, sessionCookie, json } from "./_shared.js";

export async function onRequestPost(context) {
  try {
    const body = await context.request.json().catch(() => null);
    const password = body && typeof body.password === "string" ? body.password : "";
    if (!password) return json({ error: "invalid credentials" }, 401);
    const row = await context.env.DB.prepare(
      "SELECT value FROM blog_settings WHERE key = 'password_hash'",
    ).first();
    if (!row) return json({ error: "not_configured" }, 400);
    const inputHash = await sha256Hex(password);
    let diff = inputHash.length === row.value.length ? 0 : 1;
    for (let i = 0; i < Math.min(inputHash.length, row.value.length); i++) {
      diff |= inputHash.charCodeAt(i) ^ row.value.charCodeAt(i);
    }
    if (diff !== 0) return json({ error: "invalid credentials" }, 401);
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
