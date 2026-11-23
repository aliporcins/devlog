// notepad-worker.test.mjs — 记事本 Worker 的本地测试。
//
// 本文件只用测试值，绝不用任何真实密码：
//   TEST_PASSWORD = 'test-only-do-not-use'（仅测试用，禁止换成真实密码）
// 该值通过 env 注入 Worker，Worker 源码里没有任何密码；测试跑完即丢弃。
// 运行：node --test notepad-worker.test.mjs
// 要求：Node 18+（Request/Response、crypto.subtle、node:test 均为内置）。

import test from 'node:test';
import assert from 'node:assert/strict';
import worker from './notepad-worker.mjs';

// 仅测试用，禁止换成真实密码。
const TEST_PASSWORD = 'test-only-do-not-use';
const BLOG_ORIGIN = 'https://blog.hench.cc.cd';

// ---------- 内存版 D1（只实现 Worker 实际用到的语句） ----------

class MockStmt {
  constructor(db, sql) {
    this.db = db;
    this.sql = sql;
    this.params = [];
  }
  bind(...params) {
    this.params = params;
    return this;
  }
  async run() {
    return this.db.exec(this.sql, this.params, 'run');
  }
  async all() {
    return this.db.exec(this.sql, this.params, 'all');
  }
  async first() {
    return this.db.exec(this.sql, this.params, 'first');
  }
}

class MockDB {
  constructor() {
    this.notes = [];
    this.sessions = new Map(); // token -> expires_at
    this.nextId = 1;
  }
  prepare(sql) {
    return new MockStmt(this, sql);
  }
  exec(sql, p, mode) {
    if (sql.startsWith('DELETE FROM sessions WHERE expires_at')) {
      let n = 0;
      for (const [t, exp] of this.sessions) {
        if (exp <= p[0]) {
          this.sessions.delete(t);
          n++;
        }
      }
      return { meta: { changes: n } };
    }
    if (sql.startsWith('SELECT token, expires_at FROM sessions')) {
      const exp = this.sessions.get(p[0]);
      const row = exp === undefined ? null : { token: p[0], expires_at: exp };
      return mode === 'first' ? row : { results: row ? [row] : [] };
    }
    if (sql.startsWith('INSERT INTO sessions')) {
      this.sessions.set(p[0], p[1]);
      return { meta: { changes: 1 } };
    }
    if (sql.startsWith('DELETE FROM sessions WHERE token')) {
      const had = this.sessions.delete(p[0]);
      return { meta: { changes: had ? 1 : 0 } };
    }
    if (sql.startsWith('SELECT id, title, body, updated_at FROM notes ORDER BY')) {
      const rows = [...this.notes].sort(
        (a, b) => (b.updated_at - a.updated_at) || (b.id - a.id),
      );
      return { results: rows };
    }
    if (sql.startsWith('UPDATE notes SET')) {
      const row = this.notes.find((n) => n.id === p[3]);
      if (!row) return { meta: { changes: 0 } };
      row.title = p[0];
      row.body = p[1];
      row.updated_at = p[2];
      return { meta: { changes: 1 } };
    }
    if (sql.startsWith('SELECT id, title, body, updated_at FROM notes WHERE id')) {
      const row = this.notes.find((n) => n.id === p[0]) || null;
      return mode === 'first' ? row : { results: row ? [row] : [] };
    }
    if (sql.startsWith('INSERT INTO notes')) {
      const row = { id: this.nextId++, title: p[0], body: p[1], updated_at: p[2] };
      this.notes.push(row);
      return { meta: { changes: 1, last_row_id: row.id } };
    }
    if (sql.startsWith('DELETE FROM notes WHERE id')) {
      const i = this.notes.findIndex((n) => n.id === p[0]);
      if (i === -1) return { meta: { changes: 0 } };
      this.notes.splice(i, 1);
      return { meta: { changes: 1 } };
    }
    throw new Error(`mock 不支持的语句: ${sql}`);
  }
}

// ---------- 调用辅助 ----------

function makeEnv(secret) {
  const env = { DB: new MockDB() };
  if (secret !== undefined) env.NOTEPAD_PASSWORD = secret;
  return env;
}

async function call(env, path, { method = 'GET', body = null, cookie = null, origin = null } = {}) {
  const headers = {};
  if (body !== null) headers['Content-Type'] = 'application/json';
  if (cookie) headers['Cookie'] = cookie;
  if (origin) headers['Origin'] = origin;
  const req = new Request(`https://worker.test${path}`, {
    method,
    headers,
    body: body !== null ? JSON.stringify(body) : undefined,
  });
  const res = await worker.fetch(req, env);
  const text = await res.text();
  let data = null;
  try {
    data = JSON.parse(text);
  } catch {
    /* 非 JSON（如 204）保持 null */
  }
  return { res, data, text };
}

function sessionCookieFrom(res) {
  const setCookie = res.headers.get('set-cookie') || '';
  const m = setCookie.match(/notepad_session=([^;]*)/);
  return m ? { header: setCookie, token: m[1] } : null;
}

async function loginCookie(env, password = TEST_PASSWORD) {
  const { res } = await call(env, '/api/login', { method: 'POST', body: { password } });
  assert.equal(res.status, 200);
  const c = sessionCookieFrom(res);
  assert.ok(c && c.token, '登录应下发会话 Cookie');
  return `notepad_session=${c.token}`;
}

// ---------- 测试 ----------

test('登录成功：测试密码通过，下发 HttpOnly + Secure + SameSite=None 会话 Cookie', async () => {
  const env = makeEnv(TEST_PASSWORD);
  const { res, data } = await call(env, '/api/login', {
    method: 'POST',
    body: { password: TEST_PASSWORD },
  });
  assert.equal(res.status, 200);
  assert.deepEqual(data, { ok: true });
  const c = sessionCookieFrom(res);
  assert.ok(c, '应有 Set-Cookie');
  assert.match(c.header, /HttpOnly/);
  assert.match(c.header, /Secure/);
  assert.match(c.header, /SameSite=None/);
  assert.ok(env.DB.sessions.has(c.token), '会话应写入 D1');
});

test('登录失败：错密码拒绝，且不下发会话', async () => {
  const env = makeEnv(TEST_PASSWORD);
  const { res } = await call(env, '/api/login', {
    method: 'POST',
    body: { password: 'wrong-password' },
  });
  assert.equal(res.status, 401);
  assert.equal(sessionCookieFrom(res), null);
  assert.equal(env.DB.sessions.size, 0);
});

test('fail closed：密文未设置时登录一律失败', async () => {
  for (const env of [makeEnv(undefined), makeEnv('')]) {
    const { res } = await call(env, '/api/login', {
      method: 'POST',
      body: { password: TEST_PASSWORD },
    });
    assert.equal(res.status, 401);
  }
});

test('未登录时笔记接口一律拒绝', async () => {
  const env = makeEnv(TEST_PASSWORD);
  for (const args of [
    ['/api/notes', {}],
    ['/api/notes', { method: 'POST', body: { title: 't', body: 'b' } }],
    ['/api/notes/1', { method: 'DELETE' }],
  ]) {
    const { res } = await call(env, ...args);
    assert.equal(res.status, 401);
  }
});

test('会话有效时笔记增删改查全通', async () => {
  const env = makeEnv(TEST_PASSWORD);
  const cookie = await loginCookie(env);

  let r = await call(env, '/api/notes', { cookie });
  assert.equal(r.res.status, 200);
  assert.deepEqual(r.data.notes, []);

  r = await call(env, '/api/notes', {
    method: 'POST',
    cookie,
    body: { title: '第一条', body: '内容 A' },
  });
  assert.equal(r.res.status, 200);
  const id = r.data.note.id;
  assert.ok(Number.isInteger(id));

  r = await call(env, '/api/notes', { cookie });
  assert.equal(r.data.notes.length, 1);
  assert.equal(r.data.notes[0].title, '第一条');

  r = await call(env, '/api/notes', {
    method: 'POST',
    cookie,
    body: { id, title: '改后', body: '内容 B' },
  });
  assert.equal(r.res.status, 200);
  assert.equal(r.data.note.title, '改后');
  assert.equal(r.data.note.body, '内容 B');

  r = await call(env, '/api/notes/999999', { method: 'DELETE', cookie });
  assert.equal(r.res.status, 404);

  r = await call(env, `/api/notes/${id}`, { method: 'DELETE', cookie });
  assert.equal(r.res.status, 200);

  r = await call(env, '/api/notes', { cookie });
  assert.deepEqual(r.data.notes, []);

  r = await call(env, '/api/notes', {
    method: 'POST',
    cookie,
    body: { title: 123, body: 'x' },
  });
  assert.equal(r.res.status, 400);
});

test('过期会话被拒绝', async () => {
  const env = makeEnv(TEST_PASSWORD);
  env.DB.sessions.set('expired-token', Math.floor(Date.now() / 1000) - 10);
  const { res } = await call(env, '/api/notes', { cookie: 'notepad_session=expired-token' });
  assert.equal(res.status, 401);
});

test('CORS：只放行博客域名，其它来源拿不到 Allow-Origin', async () => {
  const env = makeEnv(TEST_PASSWORD);
  const cookie = await loginCookie(env);

  let r = await call(env, '/api/notes', { cookie, origin: BLOG_ORIGIN });
  assert.equal(r.res.headers.get('access-control-allow-origin'), BLOG_ORIGIN);
  assert.equal(r.res.headers.get('access-control-allow-credentials'), 'true');

  r = await call(env, '/api/notes', { cookie, origin: 'https://evil.example' });
  assert.equal(r.res.headers.get('access-control-allow-origin'), null);

  r = await call(env, '/api/notes', { method: 'OPTIONS', origin: BLOG_ORIGIN });
  assert.equal(r.res.status, 204);
  assert.match(r.res.headers.get('access-control-allow-methods') || '', /POST/);

  r = await call(env, '/api/notes', { method: 'OPTIONS', origin: 'https://evil.example' });
  assert.equal(r.res.status, 204);
  assert.equal(r.res.headers.get('access-control-allow-methods'), null);
});

test('登出：清 Cookie、删会话，旧会话随即失效', async () => {
  const env = makeEnv(TEST_PASSWORD);
  const cookie = await loginCookie(env);

  const { res } = await call(env, '/api/logout', { method: 'POST', cookie });
  assert.equal(res.status, 200);
  assert.match(res.headers.get('set-cookie') || '', /Max-Age=0/);
  assert.equal(env.DB.sessions.size, 0);

  const r = await call(env, '/api/notes', { cookie });
  assert.equal(r.res.status, 401);
});
