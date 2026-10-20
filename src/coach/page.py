# ruff: noqa: E501  (inline CSS/JS)
"""The coach chat page (mobile-first). The conversation lives in this page only: reloading
starts over, and nothing is stored on the server."""

PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><meta name="robots" content="noindex">
<title>Coach · Recovery Lab</title>
<style>
:root{--bg:#f3f4f6;--card:#fff;--ink:#111827;--ink2:#374151;--muted:#6b7280;--line:#e5e7eb;--me:#111827;--meink:#fff;
--accent:#2563eb;--ok:#0f9d58;--bad:#d03b3b}
@media (prefers-color-scheme:dark){:root{--bg:#0f1115;--card:#171a21;--ink:#e5e7eb;--ink2:#c9cdd4;--muted:#9aa1ac;
--line:#2a2f3a;--me:#e5e7eb;--meink:#111827;--accent:#7aa2ff;--ok:#4cc38a;--bad:#f07171}}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}
.app{max-width:640px;margin:0 auto;height:100%;display:flex;flex-direction:column}
header{padding:16px 16px 8px}.brand{font-size:13px;font-weight:700;letter-spacing:.08em}
.sub{font-size:13px;color:var(--muted)}
#log{flex:1;overflow-y:auto;padding:8px 16px 16px}
.msg{max-width:88%;margin:10px 0;padding:10px 14px;border-radius:16px;white-space:pre-wrap;word-wrap:break-word}
.bot{background:var(--card);border:1px solid var(--line);border-top-left-radius:6px}
.me{background:var(--me);color:var(--meink);margin-left:auto;border-top-right-radius:6px}
.meta{font-size:12px;color:var(--muted);margin:-4px 0 6px 4px}.meta a{color:var(--muted)}
.prop{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:8px 0;max-width:88%}
.prop b{display:block}.prop .why{font-size:13px;color:var(--muted);margin-top:2px}
button{font:inherit;cursor:pointer}
.add{margin-top:10px;background:var(--ink);color:var(--bg);border:0;border-radius:10px;padding:8px 14px;font-weight:600}
.link{background:none;border:0;color:var(--muted);text-decoration:underline;padding:0;margin-left:10px;font-size:13px}
.status{font-size:13px;margin-top:8px}.status.ok{color:var(--ok)}.status.no{color:var(--bad)}
.chips{display:flex;gap:8px;flex-wrap:wrap;padding:0 16px 8px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:14px;color:var(--ink2)}
form{display:flex;gap:8px;padding:10px 16px calc(10px + env(safe-area-inset-bottom));border-top:1px solid var(--line);
background:var(--bg)}
textarea{flex:1;resize:none;border:1px solid var(--line);border-radius:12px;padding:10px 12px;font:inherit;
background:var(--card);color:var(--ink);max-height:120px}
.send{background:var(--ink);color:var(--bg);border:0;border-radius:12px;padding:0 16px;font-weight:600}
.send:disabled{opacity:.5}
.typing{color:var(--muted);font-size:14px;margin:8px 0}
</style></head><body><div class="app">
<header><div class="brand">RECOVERY LAB · COACH</div>
<div class="sub">Tell me what you want to improve. I look at your data and free time and can put a plan on your
calendar. Not medical advice.</div></header>
<div id="log"></div>
<div class="chips" id="chips">
<button class="chip">I want to fall asleep earlier</button>
<button class="chip">Fit a workout in this week</button>
<button class="chip">Why has my recovery been low?</button>
<button class="chip">Does golf affect my sleep?</button></div>
<form id="f"><textarea id="t" rows="1" placeholder="Message the coach" maxlength="1000"></textarea>
<button class="send" id="s">Send</button></form></div>
<script>
var base = location.pathname.replace(/\\/$/, ''), history_ = [], busy = false;
var log = document.getElementById('log'), t = document.getElementById('t'), s = document.getElementById('s');
function el(tag, cls, text){var e=document.createElement(tag); if(cls) e.className=cls; if(text!=null) e.textContent=text; return e;}
function scroll(){log.scrollTop = log.scrollHeight;}
function post(path, body){return fetch(base + path, {method:'POST', headers:{'Content-Type':'application/json'},
  body: JSON.stringify(body)}).then(function(r){return r.json();});}
function proposal(p){
  var box = el('div','prop'); box.appendChild(el('b', null, p.day + ' · ' + p.start + '-' + p.end));
  box.appendChild(el('div', null, p.title)); if(p.why) box.appendChild(el('div','why', p.why));
  var add = el('button','add','Add to calendar'), st = el('div','status'); box.appendChild(add); box.appendChild(st);
  add.onclick = function(){ add.disabled = true; st.textContent = 'Adding…'; st.className = 'status';
    post('/add', {token: p.token}).then(function(r){
      st.textContent = r.message; st.className = 'status ' + (r.ok ? 'ok' : 'no');
      if(r.ok){ add.remove(); var u = el('button','link','Undo'); st.appendChild(u);
        u.onclick = function(){ post('/undo', {token: r.undo}).then(function(x){ st.textContent = x.message;
          st.className = 'status ' + (x.ok ? 'ok' : 'no'); }); }; }
      else add.disabled = false; }).catch(function(){ st.textContent = 'Network error. Try again.'; add.disabled = false; }); };
  log.appendChild(box);
}
function remembered(m){
  var box = el('div','meta', 'Saved to memory: ' + m.text + ' '); var f = el('button','link','Forget');
  box.appendChild(f); f.onclick = function(){ post('/forget', {token: m.token}).then(function(r){
    box.textContent = r.ok ? 'Forgotten: ' + m.text : r.message; }); };
  log.appendChild(box);
}
function send(text){
  text = text.trim(); if(!text || busy) return; busy = true; s.disabled = true;
  document.getElementById('chips').style.display = 'none';
  log.appendChild(el('div','msg me', text)); history_.push({role:'user', content:text}); t.value = '';
  var typing = el('div','typing','Looking at your data…'); log.appendChild(typing); scroll();
  post('/message', {history: history_}).then(function(r){
    typing.remove();
    if(r.error){ log.appendChild(el('div','msg bot', r.error)); history_.pop(); return; }
    log.appendChild(el('div','msg bot', r.reply)); history_.push({role:'assistant', content:r.reply});
    var notes = [];
    if(r.tools_used && r.tools_used.length) notes.push('checked: ' + Array.from(new Set(r.tools_used)).join(', ').replace(/_/g,' '));
    if(!r.checked) notes.push('some numbers could not be verified against your data');
    if(notes.length) log.appendChild(el('div','meta', notes.join(' · ')));
    if(r.sources && r.sources.length){
      var src = el('div','meta','Sources: ');
      r.sources.forEach(function(s, i){
        if(i) src.appendChild(document.createTextNode(' · '));
        var a = el(s.url ? 'a' : 'span', null, s.title + ' (' + s.source + ')');
        if(s.url){ a.href = s.url; a.target = '_blank'; a.rel = 'noopener'; }
        src.appendChild(a);
      });
      log.appendChild(src);
    }
    (r.remembered || []).forEach(remembered);
    (r.proposals || []).forEach(proposal);
  }).catch(function(){ typing.remove(); log.appendChild(el('div','msg bot','Network error. Try again.')); history_.pop(); })
  .finally(function(){ busy = false; s.disabled = false; scroll(); t.focus(); });
}
document.getElementById('f').onsubmit = function(e){ e.preventDefault(); send(t.value); };
t.addEventListener('keydown', function(e){ if(e.key === 'Enter' && !e.shiftKey){ e.preventDefault(); send(t.value); } });
document.querySelectorAll('.chip').forEach(function(c){ c.onclick = function(){ send(c.textContent); }; });
</script></body></html>"""
