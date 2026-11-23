// GET /setup — one-time setup page. The blog owner sets the blog password
// here himself; only its SHA-256 hash is stored (D1 blog_settings).
// Once a hash exists, this route returns 404.
const HTML = `<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>设置博客密码 · 开发日志</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:"PingFang SC","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;color:#f0ead9;min-height:100vh;background:#0a0a0a;display:flex;align-items:center;justify-content:center;padding:20px}
.box{width:100%;max-width:400px;border-radius:18px;padding:30px 26px;background:linear-gradient(135deg,rgba(255,255,255,.06),rgba(255,255,255,.02) 55%,rgba(201,169,106,.05));border:1px solid rgba(201,169,106,.4);box-shadow:0 14px 34px rgba(0,0,0,.5)}
h1{font-family:"Songti SC","Noto Serif SC",serif;font-size:24px;letter-spacing:.04em;background:linear-gradient(180deg,#f7ead0,#d3ab66);-webkit-background-clip:text;background-clip:text;color:transparent}
p{margin-top:10px;color:#9aa294;font-size:13.5px;line-height:1.7}
label{display:block;font-size:12.5px;letter-spacing:.12em;color:#c9a962;margin:18px 0 8px}
input{width:100%;font:inherit;font-size:15px;color:#f0ead9;background:rgba(0,0,0,.4);border:1px solid rgba(255,255,255,.18);border-radius:10px;padding:11px 14px;outline:none}
input:focus{border-color:rgba(201,169,106,.65)}
button{width:100%;margin-top:22px;font:inherit;font-size:15px;font-weight:700;color:#2a1e08;cursor:pointer;background:linear-gradient(180deg,#ecd096,#c49a58);border:none;border-radius:999px;padding:12px}
.err{display:none;margin-top:14px;font-size:13.5px;color:#e08a7a}
.err.show{display:block}
</style></head>
<body><div class="box">
<h1>设置博客密码</h1>
<p>这是首次设置：设一个博客密码，之后全站都凭它进入。只存密码的 SHA-256 摘要，不存明文；忘记密码只能清空数据库里的摘要重设。</p>
<label for="pw">新密码（至少 8 位）</label>
<input id="pw" type="password" autocomplete="new-password" autofocus>
<label for="pw2">再输一次</label>
<input id="pw2" type="password" autocomplete="new-password">
<div class="err" id="err"></div>
<button id="go" type="button">设置并进入</button>
</div>
<script>
var pw=document.getElementById('pw'),pw2=document.getElementById('pw2'),err=document.getElementById('err');
function fail(m){err.textContent=m;err.classList.add('show');}
async function setup(){
  err.classList.remove('show');
  if(pw.value.length<8){fail('密码至少 8 位。');return;}
  if(pw.value!==pw2.value){fail('两次输入不一致。');return;}
  var r=await fetch('/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:pw.value})});
  if(r.ok){location.href='/';return;}
  fail(r.status===404 ? '密码已设置过，本页已失效。' : '设置失败，请重试。');
}
document.getElementById('go').addEventListener('click',setup);
pw2.addEventListener('keydown',function(e){if(e.key==='Enter')setup();});
</script></body></html>`;

export async function onRequestGet(context) {
  try {
    if (context.env.DB) {
      const row = await context.env.DB.prepare(
        "SELECT value FROM blog_settings WHERE key = 'password_hash'",
      ).first();
      if (row) return new Response("Not Found", { status: 404 });
    }
  } catch (e) {
    return new Response("Not Found", { status: 404 });
  }
  return new Response(HTML, { headers: { "Content-Type": "text/html; charset=utf-8" } });
}
