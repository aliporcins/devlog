// Shared helpers for the blog gate API routes. No secrets live here:
// only hashes and random session tokens are handled, never passwords
// in stored form (the password hash is computed here, in memory only).
export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export function newSessionToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  let s = "";
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

export function sessionCookie(token, maxAge) {
  return `blog_session=${token}; HttpOnly; Secure; SameSite=Lax; Domain=.hench.cc.cd; Path=/; Max-Age=${maxAge}`;
}

export function clearSessionCookie() {
  return "blog_session=; HttpOnly; Secure; SameSite=Lax; Domain=.hench.cc.cd; Path=/; Max-Age=0";
}

export function parseCookies(header) {
  const out = {};
  if (!header) return out;
  for (const part of header.split(";")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    out[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }
  return out;
}

export function json(data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", ...extra },
  });
}
