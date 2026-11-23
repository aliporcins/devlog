# 博客私密记事本 — 部署说明（给主聊天复核用，本文件不部署）

## 已完成（本目录）

- `notepad-worker.mjs`：Module Worker，API 全部实现（见下）。
- `metadata.json`：PUT-WORKER 用 metadata，`main_module` 与 D1 绑定（DB →
  blog-notepad，uuid `b0a79ff2-fce4-4599-a06a-154847435efc`）已写好。
  注意：cf.py 的 PUT-WORKER 把模块段固定命名为 `script.js`，因此
  metadata.json 的 `main_module` 必须是 `script.js`（主聊天上传时已修正），
  不是源码文件名；否则报 10021 No such module。
- `notepad-worker.test.mjs`：本地测试（测试密码仅为 `test-only-do-not-use`，
  绝非真实密码；跑完即弃）。
- 页面源码：`../notepad-page.html`，部署产物已拷入 `../site/notepad.html`
  （build.py 不删 site/ 下的未知文件，下次构建仍在；改页面源码后需重拷）。

## API 契约

Base URL：部署后 Worker 的 workers.dev 地址（部署时填入页面 `WORKER_URL`）。
全部请求除登录外都要求会话 Cookie；CORS 只放行 `https://blog.hench.cc.cd`。

| 方法与路径 | 入参 | 成功 | 失败 |
|---|---|---|---|
| POST /api/login | JSON `{password}` | 200 `{ok:true}` + Set-Cookie 会话（HttpOnly、Secure、SameSite=None、30 天） | 401（错密码与密文未设置返回完全一致） |
| POST /api/logout | —（Cookie） | 200 `{ok:true}` + 清 Cookie | 恒 200 |
| GET /api/notes | —（Cookie） | 200 `{notes:[{id,title,body,updated_at}]}`（updated_at 倒序） | 401 未登录/会话过期 |
| POST /api/notes | JSON `{id?, title, body}`（有 id 为更新，无 id 为新建） | 200 `{note:{...}}` | 400 入参非法/超长、401、404 id 不存在 |
| DELETE /api/notes/:id | —（Cookie） | 200 `{ok:true}` | 401、404 |

会话表 `sessions(token, expires_at)`，过期 30 天；每次鉴权顺手清过期行。
笔记表 `notes(id, title, body, updated_at)`，updated_at 为秒级时间戳。

## 部署前唯一缺口：用户设密文

用户本人去 Cloudflare 面板设置（主聊天不要代设、不要问用户要密码）：

**Workers & Pages → 选择 Worker `blog-notepad` → Settings → Variables →
Add secret → Name 填 `NOTEPAD_PASSWORD`，Value 填记事本专用新密码 → 保存。**

注意：是 Secret（加密存储），不是普通 Variable。密文未设置时登录一律 401。

## 部署步骤（主聊天复核后执行）

1. 上传 Worker（模块格式，参考 custom.cloudflare 连接器的 PUT-WORKER 法）：
   `cf.py PUT-WORKER /accounts/56729b24f482638227bbb17f3c47382a/workers/scripts/blog-notepad notepad-worker.mjs metadata.json`
   （脚本名 `blog-notepad`；如与现有 Worker 重名，先确认再覆盖。）
2. 启用 workers.dev 路由（首次上传后）：
   `cf.py POST /accounts/.../workers/scripts/blog-notepad/subdomain '{"enabled":true}'`
   记下实际 workers.dev 地址，填入 `site/notepad.html` 里的 `WORKER_URL`
   （把 `REPLACE-WITH-YOUR-SUBDOMAIN` 换掉），不要改其它内容。
3. 确认用户已按上节设好 `NOTEPAD_PASSWORD` 密文。
4. 跑 `deploy.py` 发布博客（含 `site/notepad.html`），上线后实测：
   登录页 → 输专用密码 → 新建一条 → 刷新后仍在 → 删除 → 退出后笔记接口 401。
5. 可选加固（不在本次范围）：Cloudflare Rate Limiting 防暴力猜解；
   页面故意不进博客导航（只知道地址 + 密码校验双重门）。

## 未验证项（不要对外宣称已验证）

- Worker 未实际上传、未启用 workers.dev，线上联调未做。
- 页面未在真机浏览器里点过（本地只做了 JS 语法检查）。
- 上线后必须按上节第 4 步实测一遍才算交付完成。
