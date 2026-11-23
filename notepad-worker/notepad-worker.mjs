// notepad-worker.mjs — 博客私密记事本 API（Cloudflare Module Worker）。
//
// 安全要点（本文件里没有任何密码、哈希或密文）：
// - 唯一凭证是环境密文 env.NOTEPAD_PASSWORD，由用户本人在 Cloudflare 面板里
//   设为 Worker Secret；本文件不读、不写、不返回、不记录它。
// - 密码比对是恒时比较：先对两边做 SHA-256，再对 32 字节摘要逐字节异或累加，
//   避免因长度或提前返回泄露信息。
// - 密文未设置时登录一律失败（fail closed），且与密码错误的返回完全一致，
//   不给调用方留“密文是否存在”的预言机。
// - 笔记接口只认 D1 里未过期的会话；会话 Cookie 为 HttpOnly + Secure +
//   SameSite=None（跨站 fetch 必须用 None 才能带上 Cookie），Path=/，30 天过期。
// - CORS 只放行博客域名 https://blog.hench.cc.cd；其它来源拿不到 CORS 头，
//   浏览器侧直接拦截。写接口要求 JSON Content-Type，跨站简单请求打不到。
// - 本文件不做限流；如需防暴力猜解，后续可在 Cloudflare 侧给该 Worker 加
//   Rate Limiting（不在本次范围）。

const BLOG_ORIGIN = 'https://blog.hench.cc.cd';
const SESSION_COOKIE = 'notepad_session';
const SESSION_TTL_SECONDS = 30 * 24 * 3600; // 30 天
const MAX_TITLE = 200;
const MAX_BODY = 100000;

function nowSeconds() {
  return Math.floor(Date.now() / 1000);
}

function corsHeaders(request) {
  // 只放行博客域名；其它来源一律不给 Allow-Origin。
  if (request.headers.get('Origin') === BLOG_ORIGIN) {
    return {
      'Access-Control-Allow-Origin': BLOG_ORIGIN,
      'Access-Control-Allow-Credentials': 'true',
      'Vary': 'Origin',
    };
  }
  return { 'Vary': 'Origin' };
}

function jsonResponse(request, data, status = 200, extra = {}) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...corsHeaders(request), ...extra },
  });
}

async function sha256Bytes(text) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return new Uint8Array(digest);
}

async function constantTimeEqual(a, b) {
  const da = await sha256Bytes(a);
  const db = await sha256Bytes(b);
  let diff = 0;
  for (let i = 0; i < da.length; i++) diff |= da[i] ^ db[i];
  return diff === 0;
}

function parseCookies(header) {
  const out = {};
  if (!header) return out;
  for (const part of header.split(';')) {
    const idx = part.indexOf('=');
    if (idx === -1) continue;
    out[part.slice(0, idx).trim()] = part.slice(idx + 1).trim();
  }
  return out;
}

function base64url(bytes) {
  let s = '';
  for (const b of bytes) s += String.fromCharCode(b);
  return btoa(s).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}

function newSessionToken() {
  return base64url(crypto.getRandomValues(new Uint8Array(32)));
}

function sessionCookieHeader(token, maxAge) {
  return `${SESSION_COOKIE}=${token}; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=${maxAge}`;
}

function clearSessionCookieHeader() {
  return `${SESSION_COOKIE}=; HttpOnly; Secure; SameSite=None; Path=/; Max-Age=0`;
}

async function requireBlogSession(env, request) {
  // 博客登录态：blog_session Cookie 对应 D1 blog_sessions 表（与博客门共用同一库）。
  // 博客会话 Cookie 带 Domain=.hench.cc.cd，会发给本 Worker 的自定义域名
  // notepad.hench.cc.cd；有效即视为已登录（当次请求放行，不另发 notepad_session）。
  const token = parseCookies(request.headers.get('Cookie')).blog_session;
  if (!token) return null;
  try {
    const row = await env.DB.prepare(
      'SELECT token FROM blog_sessions WHERE token = ? AND expires_at > ?',
    ).bind(token, nowSeconds()).first();
    return row || null;
  } catch (e) {
    return null;
  }
}

async function requireSession(env, request) {
  const token = parseCookies(request.headers.get('Cookie'))[SESSION_COOKIE];
  if (token) {
    // 顺手清理过期会话（失败也不影响本次鉴权）。
    try {
      await env.DB.prepare('DELETE FROM sessions WHERE expires_at <= ?').bind(nowSeconds()).run();
    } catch (e) { /* ignore */ }
    const row = await env.DB.prepare(
      'SELECT token, expires_at FROM sessions WHERE token = ?',
    ).bind(token).first();
    if (row && row.expires_at > nowSeconds()) return row;
  }
  // 记事本会话无效或缺失时，退到博客登录态。
  const blog = await requireBlogSession(env, request);
  if (blog) return { blog_session: true, token: blog.token };
  return null;
}

async function readJson(request) {
  try {
    return await request.json();
  } catch (e) {
    return null;
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    // 预览请求：只给博客域名放 CORS。
    if (request.method === 'OPTIONS') {
      const headers = { ...corsHeaders(request) };
      if (request.headers.get('Origin') === BLOG_ORIGIN) {
        headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS';
        headers['Access-Control-Allow-Headers'] = 'Content-Type';
        headers['Access-Control-Max-Age'] = '86400';
      }
      return new Response(null, { status: 204, headers });
    }

    // ---- POST /api/login ----
    if (path === '/api/login' && request.method === 'POST') {
      const body = await readJson(request);
      const password = body && typeof body.password === 'string' ? body.password : '';
      const secret = env.NOTEPAD_PASSWORD;
      // Fail closed：密文未设置 => 任何登录都失败；返回与密码错误完全一致。
      if (!secret || !password || !(await constantTimeEqual(password, secret))) {
        return jsonResponse(request, { error: 'invalid credentials' }, 401);
      }
      const token = newSessionToken();
      const expiresAt = nowSeconds() + SESSION_TTL_SECONDS;
      await env.DB.prepare(
        'INSERT INTO sessions (token, expires_at) VALUES (?, ?)',
      ).bind(token, expiresAt).run();
      return jsonResponse(request, { ok: true }, 200, {
        'Set-Cookie': sessionCookieHeader(token, SESSION_TTL_SECONDS),
      });
    }

    // ---- POST /api/logout ----
    if (path === '/api/logout' && request.method === 'POST') {
      const token = parseCookies(request.headers.get('Cookie'))[SESSION_COOKIE];
      if (token) {
        try {
          await env.DB.prepare('DELETE FROM sessions WHERE token = ?').bind(token).run();
        } catch (e) { /* ignore */ }
      }
      return jsonResponse(request, { ok: true }, 200, {
        'Set-Cookie': clearSessionCookieHeader(),
      });
    }

    // ---- 笔记接口：必须先过会话 ----
    if (path === '/api/notes' || path.startsWith('/api/notes/')) {
      const session = await requireSession(env, request);
      if (!session) return jsonResponse(request, { error: 'unauthorized' }, 401);

      if (path === '/api/notes' && request.method === 'GET') {
        const { results } = await env.DB.prepare(
          'SELECT id, title, body, updated_at FROM notes ORDER BY updated_at DESC, id DESC',
        ).all();
        return jsonResponse(request, { notes: results || [] });
      }

      if (path === '/api/notes' && request.method === 'POST') {
        const body = await readJson(request);
        if (!body || typeof body.title !== 'string' || typeof body.body !== 'string') {
          return jsonResponse(request, { error: 'title and body must be strings' }, 400);
        }
        if (body.title.length > MAX_TITLE || body.body.length > MAX_BODY) {
          return jsonResponse(request, { error: 'note too large' }, 400);
        }
        const now = nowSeconds();
        if (body.id !== undefined && body.id !== null) {
          const id = Number(body.id);
          if (!Number.isInteger(id)) return jsonResponse(request, { error: 'bad id' }, 400);
          const res = await env.DB.prepare(
            'UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?',
          ).bind(body.title, body.body, now, id).run();
          if (!res.meta || res.meta.changes === 0) {
            return jsonResponse(request, { error: 'not found' }, 404);
          }
          const note = await env.DB.prepare(
            'SELECT id, title, body, updated_at FROM notes WHERE id = ?',
          ).bind(id).first();
          return jsonResponse(request, { note });
        }
        const res = await env.DB.prepare(
          'INSERT INTO notes (title, body, updated_at) VALUES (?, ?, ?)',
        ).bind(body.title, body.body, now).run();
        const newId = res.meta ? res.meta.last_row_id : null;
        const note = await env.DB.prepare(
          'SELECT id, title, body, updated_at FROM notes WHERE id = ?',
        ).bind(newId).first();
        return jsonResponse(request, { note });
      }

      if (path.startsWith('/api/notes/') && request.method === 'DELETE') {
        const id = Number(path.slice('/api/notes/'.length));
        if (!Number.isInteger(id)) return jsonResponse(request, { error: 'bad id' }, 400);
        const res = await env.DB.prepare('DELETE FROM notes WHERE id = ?').bind(id).run();
        if (!res.meta || res.meta.changes === 0) {
          return jsonResponse(request, { error: 'not found' }, 404);
        }
        return jsonResponse(request, { ok: true });
      }

      return jsonResponse(request, { error: 'method not allowed' }, 405);
    }

    return jsonResponse(request, { error: 'not found' }, 404);
  },
};
