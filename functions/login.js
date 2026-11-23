// GET /login — self-contained login page (no external assets, so the
// gate middleware does not need any static-asset exemption for it).
const HTML = `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>登录 · 开发日志</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;color:#f0ead9;min-height:100vh;background:#0a0a0a;display:flex;align-items:center;justify-content:center;padding:20px}
.box{width:100%;max-width:380px;border-radius:18px;padding:30px 26px;background:linear-gradient(135deg,rgba(255,255,255,.06),rgba(255,255,255,.02) 55%,rgba(201,169,106,.05));border:1px solid rgba(201,169,106,.4);box-shadow:0 14px 34px rgba(0,0,0,.5)}
h1{font-family:"Songti SC","Noto Serif SC",serif;font-size:26px;letter-spacing:.06em;background:linear-gradient(180deg,#f7ead0,#d3ab66);-webkit-background-clip:text;background-clip:text;color:transparent}
p{margin-top:10px;color:#9aa294;font-size:13.5px;line-height:1.7}
label{display:block;font-size:12.5px;letter-spacing:.12em;color:#c9a962;margin:20px 0 8px}
input{width:100%;font:inherit;font-size:15px;color:#f0ead9;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.18);border-radius:10px;padding:11px 14px;outline:none}
input:focus{border-color:rgba(201,169,106,.65)}
button{width:100%;margin-top:22px;font:inherit;font-size:15px;font-weight:700;color:#2a1e08;cursor:pointer;background:linear-gradient(180deg,#ecd096,#c49a58);border:none;border-radius:999px;padding:12px}
.err{display:none;margin-top:14px;font-size:13.5px;color:#e08a7a}
.err.show{display:block}
.hint{margin-top:16px;font-size:12.5px;color:#6d7466}
.hint a{color:#c9a962}
</style></head>
<body><div class="box">
<h1>开发日志</h1>
<p>本站已上锁。输入博客密码进入。</p>
<label for="pw">博客密码</label>
<input id="pw" type="password" autocomplete="current-password" autofocus>
<div class="err" id="err"></div>
<button id="go" type="button">进入</button>
<p class="hint">还没有设置密码？先去 <a href="/setup">/setup 设置密码</a>。</p>
</div>
<script>
var pw=document.getElementById('pw'),err=document.getElementById('err');
async function login(){
  err.classList.remove('show');
  var r=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw.value})});
  if(r.ok){location.href='/';return;}
  var d={};try{d=await r.json();}catch(e){}
  err.textContent = d.error==='not_configured' ? '尚未设置密码，请先去 /setup 设置。' : '密码不对，请重试。';
  err.classList.add('show');
}
document.getElementById('go').addEventListener('click',login);
pw.addEventListener('keydown',function(e){if(e.key==='Enter')login();});
</script></body></html>`;

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

export async function onRequestGet(context) {
  try {
    const token = parseCookies(context.request.headers.get("Cookie")).blog_session;
    if (token && context.env.DB) {
      const row = await context.env.DB.prepare(
        "SELECT token FROM blog_sessions WHERE token = ? AND expires_at > ?",
      ).bind(token, Math.floor(Date.now() / 1000)).first();
      if (row) return Response.redirect(new URL("/", context.request.url).toString(), 302);
    }
  } catch (e) { /* fall through to the login page */ }
  return new Response(HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}
