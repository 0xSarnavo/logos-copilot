"""Thin human-facing playground (Starlette). Reuses the same retrieval/freshness/feedback as MCP.

A discovery + trust + feedback surface: search box → cited results stamped with how fresh the
knowledge is, a coverage badge, and 👍/👎 feedback. Binds loopback by default (config.mcp_host);
front it with an authenticating proxy to expose publicly.
"""
from __future__ import annotations

from contextlib import closing

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from .config import is_loopback, settings
from .db import connect
from .feedback import submit_feedback
from .refresh import freshness
from .retrieve import citation, search

PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Logos Copilot</title>
<style>
:root{--bg:#0d1117;--card:#161b22;--bd:#30363d;--fg:#e6edf3;--mut:#8b949e;--ac:#58a6ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);
font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:820px;margin:0 auto;padding:28px 18px}
h1{font-size:22px;margin:0 0 2px}.sub{color:var(--mut);margin:0 0 18px;font-size:13px}
.bar{display:flex;gap:8px;margin-bottom:8px}
input,select,button{background:var(--card);color:var(--fg);border:1px solid var(--bd);
border-radius:8px;padding:10px 12px;font-size:14px}
input{flex:1}button{cursor:pointer}button:hover{border-color:var(--ac)}
#fresh{color:var(--mut);font-size:12px;margin-bottom:18px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:10px;padding:14px;margin:10px 0}
.cite{color:var(--mut);font-size:12px;margin-top:8px;display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.cite a{color:var(--ac);text-decoration:none}.kind{background:#1f2937;border-radius:4px;padding:1px 6px;font-size:11px}
pre{white-space:pre-wrap;word-break:break-word;margin:0;font:12.5px/1.5 ui-monospace,Menlo,monospace}
.vote{margin-left:auto}.vote button{padding:2px 8px;font-size:13px}
.empty{color:var(--mut);padding:20px 0}
</style></head><body><div class=wrap>
<h1>Logos Copilot</h1><p class=sub>Cited, version-pinned, freshness-stamped knowledge for building on Logos.</p>
<div class=bar>
<input id=q placeholder="Ask: how do I upload data to Codex and share the CID over Waku?" autofocus>
<select id=kind><option value="">any kind</option><option>doc</option><option>code</option>
<option>spec</option><option>sdk</option><option>guide</option><option>recipe</option><option>openapi</option></select>
<button onclick=go()>Search</button></div>
<div id=fresh></div><div id=out class=empty>Type a question and hit Search.</div>
<script>
async function fresh(){try{let r=await (await fetch('/api/freshness')).json();
let n=r.by_component.reduce((a,c)=>a+c.n,0);
document.getElementById('fresh').textContent=`Knowledge base: ${r.active_repos} active repos across ${r.by_component.length} components`+(r.retired_repos?` · ${r.retired_repos} retired`:'');}catch(e){}}
async function go(){let q=document.getElementById('q').value.trim();if(!q)return;window.__q=q;
let kind=document.getElementById('kind').value;let out=document.getElementById('out');
out.className='';out.textContent='Searching…';
let u='/api/search?q='+encodeURIComponent(q)+(kind?'&kind='+encodeURIComponent(kind):'');
let r=await (await fetch(u)).json();
if(!r.results||!r.results.length){out.className='empty';out.textContent='No results.';return;}
out.innerHTML=r.results.map(x=>{let c=x.citation;
let loc=esc(c.repo+'/'+c.path+(c.lines&&c.lines[0]?` L${c.lines[0]}-${c.lines[1]}`:''));
let url=c.url?esc(safeUrl(c.url)):'';
return `<div class=card><pre>${esc(x.content)}</pre><div class=cite>
<span class=kind>${esc(c.kind)}</span>
${url?`<a href="${url}" target=_blank rel=noopener>${loc}</a>`:loc}
<span>indexed ${esc((''+c.indexed_at).slice(0,16))}</span>
<span class=vote><button class=v data-r=up data-u="${url}">👍</button>
<button class=v data-r=down data-u="${url}">👎</button></span>
</div></div>`}).join('');}
function esc(s){return (''+s).replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]))}
function safeUrl(u){try{var p=new URL(u,location.href);return(p.protocol==='https:'||p.protocol==='http:')?u:''}catch(e){return''}}
document.getElementById('out').addEventListener('click',e=>{let b=e.target.closest('button.v');if(!b)return;
fetch('/api/feedback',{method:'POST',headers:{'content-type':'application/json'},
body:JSON.stringify({rating:b.dataset.r,query:window.__q||'',source_url:b.dataset.u||''})});b.textContent='✓'});
document.getElementById('q').addEventListener('keydown',e=>{if(e.key==='Enter')go()});
fresh();
</script></div></body></html>"""


MAX_QUERY = 512
MAX_BODY = 16384


def _do_search(q, component, kind):
    rows = search(q, component=component, kind=kind, top_k=8)
    from .querylog import log_query
    with closing(connect()) as conn:
        log_query(conn, q, kind, component, len(rows))
    return {"query": q, "count": len(rows),
            "results": [{"content": r["content"][:900], "citation": citation(r)} for r in rows]}


def _do_freshness():
    with closing(connect()) as conn:
        return freshness(conn)


def _do_feedback(query, rating, source_url, comment):
    with closing(connect()) as conn:
        submit_feedback(conn, query=query, rating=rating, source_url=source_url, comment=comment)


async def index(request):
    return HTMLResponse(PAGE)


async def api_search(request):
    q = (request.query_params.get("q") or "").strip()[:MAX_QUERY]
    if not q:
        return JSONResponse({"error": "empty query"}, status_code=400)
    kind = request.query_params.get("kind") or None
    component = request.query_params.get("component") or None
    try:                                       # blocking pg8000 work off the event loop
        return JSONResponse(await run_in_threadpool(_do_search, q, component, kind))
    except Exception:
        return JSONResponse({"error": "service unavailable"}, status_code=503)


async def api_freshness(request):
    try:
        return JSONResponse(await run_in_threadpool(_do_freshness))
    except Exception:
        return JSONResponse({"error": "service unavailable"}, status_code=503)


async def api_feedback(request):
    if int(request.headers.get("content-length") or 0) > MAX_BODY:
        return JSONResponse({"error": "body too large"}, status_code=413)
    try:
        data = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid json"}, status_code=400)
    if not isinstance(data, dict) or data.get("rating") not in ("up", "down"):
        return JSONResponse({"error": "rating must be 'up' or 'down'"}, status_code=400)
    try:
        await run_in_threadpool(_do_feedback, str(data.get("query", ""))[:1000], data["rating"],
                                (data.get("source_url") or None), (data.get("comment") or None))
    except Exception:
        return JSONResponse({"error": "service unavailable"}, status_code=503)
    return JSONResponse({"received": True})


app = Starlette(routes=[
    Route("/", index),
    Route("/api/search", api_search),
    Route("/api/freshness", api_freshness),
    Route("/api/feedback", api_feedback, methods=["POST"]),
])


def main() -> None:
    import uvicorn

    # The web API is unauthenticated; don't bind it to a public host without an auth proxy.
    if not is_loopback(settings.web_host) and not settings.auth_token:
        raise SystemExit(
            f"Refusing to bind WEB_HOST={settings.web_host} without auth. Use 127.0.0.1 behind an "
            f"authenticating proxy, or set AUTH_TOKEN.")
    uvicorn.run(app, host=settings.web_host, port=settings.web_port)


if __name__ == "__main__":
    main()
