import asyncio, contextlib, json, os, secrets, time
from contextlib import asynccontextmanager
import httpx
from fastapi import Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from jsonschema import validate
import app as core
from menu import TEMPLATES, make_prompt

app = core.app
core.MCP_URL = os.environ.get("MCP_SERVER_URL", "").strip()
core.SYSTEM["content"] += " Bei Beschreibungen statt exakten Namen zuerst reale Geräte suchen. Berücksichtige alias, room, group und TYPE. Bei mehreren plausiblen Treffern konkrete Auswahl erfragen, besonders vor Schreibzugriffen. Keine Namen erfinden."
cache = {"expires": 0, "devices": []}
cache_lock = asyncio.Lock()
choices = {}


def unpack(value):
    if isinstance(value, dict):
        if isinstance(value.get("Results"), list):
            return value["Results"]
        for key in ("devices", "results", "data"):
            if isinstance(value.get(key), (dict, list)):
                return unpack(value[key])
        if value and all(isinstance(v, dict) for v in value.values()):
            return [dict(v, Name=k) for k, v in value.items()]
    if isinstance(value, list):
        return value
    raise ValueError("Unbekanntes Geräteformat")


def normalize(rows):
    result = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        internals = item.get("Internals", {})
        attrs = item.get("Attributes", item.get("attributes", {}))
        if not isinstance(internals, dict) or not isinstance(attrs, dict):
            continue
        name = item.get("Name") or item.get("name") or internals.get("NAME")
        if not isinstance(name, str) or not name or len(name) > 200:
            continue
        result[name] = {"name": name, "alias": str(attrs.get("alias", item.get("alias", name)))[:200],
                        "room": str(attrs.get("room", item.get("room", "")))[:300],
                        "group": str(attrs.get("group", ""))[:300],
                        "type": str(internals.get("TYPE", item.get("type", "")))[:100]}
    return list(result.values())


async def devices():
    async with cache_lock:
        if cache["expires"] > time.monotonic():
            return cache["devices"]
        if not core.MCP_URL:
            raise ValueError("MCP_SERVER_URL fehlt")
        tools = await core.discover()
        tool = tools.get("fhem_list_devices")
        if not tool or not core.readonly("fhem_list_devices"):
            raise ValueError("FHEM-Geräteliste nicht verfügbar")
        validate({}, tool["function"]["parameters"])
        async with asyncio.timeout(25):
            async with core.mcp_session() as session:
                response = await session.call_tool("fhem_list_devices", {})
        if getattr(response, "isError", False):
            raise ValueError("FHEM-Geräteabfrage fehlgeschlagen")
        structured = getattr(response, "structuredContent", None)
        if structured is not None:
            rows = unpack(structured)
        else:
            texts = [part.text for part in response.content if getattr(part, "type", "") == "text"]
            rows = unpack(json.loads("\n".join(texts)))
        result = normalize(rows)
        cache.update(devices=result, expires=time.monotonic() + 30)
        return result


def search(rows, query):
    words = query.casefold().split()
    return [d for d in rows if all(w in " ".join(d.values()).casefold() for w in words)]


@app.get("/api/devices")
async def find_devices(q: str = Query(default="", max_length=120), owner=Depends(core.auth)):
    try:
        matches = search(await devices(), q)
        return {"devices": matches[:30], "total": len(matches), "cache_seconds": 30}
    except Exception:
        raise HTTPException(503, "Gerätesuche nicht verfügbar. MCP-Konfiguration, Tool und Antwortformat prüfen.")


@app.get("/api/menu")
async def menu(owner=Depends(core.auth)):
    return {"templates": TEMPLATES}


@app.post("/api/diagnostics")
async def diagnostics(owner=Depends(core.auth)):
    async def mcp_check():
        if not core.MCP_URL:
            return {"status": "missing", "message": "MCP_SERVER_URL fehlt"}
        try:
            async with asyncio.timeout(12):
                tools = await core.discover()
            return {"status": "ok" if tools else "error", "fhem_tools": len(tools)}
        except Exception:
            return {"status": "error", "message": "MCP-Verbindung oder Authentifizierung fehlgeschlagen"}
    async def fhem_check():
        try:
            async with asyncio.timeout(15):
                rows = await devices()
            return {"status": "ok", "devices": len(rows), "message": "MCP-Lesezugriff, Cache maximal 30 Sekunden"}
        except Exception:
            return {"status": "error", "message": "FHEM-Geräteliste nicht lesbar"}
    async def llm_check():
        if not os.environ.get("OPENAI_API_KEY"):
            return {"status": "missing", "message": "OPENAI_API_KEY fehlt"}
        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
                r = await client.get(os.environ.get("OPENAI_BASE_URL", "https://9router.arbeitermili.eu/v1").rstrip("/") + "/models", headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
            return {"status": "ok" if r.is_success else "error", "http_status": r.status_code, "message": "Nur Modellliste geprüft, kein Generierungs- oder Tool-Calling-Test"}
        except Exception:
            return {"status": "error", "message": "LLM-Modellliste nicht erreichbar"}
    mcp, fhem, llm = await asyncio.gather(mcp_check(), fhem_check(), llm_check())
    return {"app": {"status": "ok"}, "mcp": mcp, "fhem_via_mcp": fhem, "llm": llm,
            "direct_fhem": {"status": "not_tested", "message": "Direkter FHEMWEB-Zugang wird nicht automatisch aufgerufen"}}


PAGE = r"""<!doctype html><html lang="de"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>hAI.FHEMChatAgent</title>
<style>body{margin:0;background:#0b1020;color:#f0f5ff;font:16px/1.5 system-ui}main{max-width:980px;margin:auto;padding:20px}section{background:#151d33;border:1px solid #344568;border-radius:18px;padding:18px;margin:16px 0}h1{color:#78e8cc}input,textarea,button,select{font:inherit;border-radius:9px;padding:10px;margin:5px 0;max-width:100%;box-sizing:border-box}textarea,input{width:100%;background:#0e172a;color:white;border:1px solid #8299ff}button{background:#78e8cc;color:#102334;border:0;cursor:pointer}button:disabled{opacity:.5}button:focus-visible,input:focus-visible,textarea:focus-visible{outline:3px solid #ffbc78}pre,.msg{white-space:pre-wrap;overflow-wrap:anywhere}.msg{padding:12px;background:#24314d;border-radius:12px;margin:10px 0}.user{background:#284c60}.device{display:block;text-align:left;width:100%}small{color:#b7c7e2}#error{color:#ffbc78}#approval{border:2px solid #ffbc78}#log{max-height:55vh;overflow:auto}</style>
<main><h1>hAI.FHEMChatAgent</h1><p>Einfach fragen. Gerätenamen musst du nicht kennen.</p>
<section><div id="log" aria-live="polite"></div><div id="approval" hidden><h2>Auftrag einzeln freigeben</h2><pre id="proposal"></pre><p id="expires"></p><button id="yes">Genau so ausführen</button> <button id="no">Abbrechen</button></div><p id="error" role="alert"></p><form id="chat"><label for="text">Deine Nachricht</label><textarea id="text" required maxlength="8000" placeholder="Welche Heizungen gibt es im Wohnzimmer?"></textarea><button id="send">Senden</button></form><button id="reset">Neuer Chat</button></section>
<section><h2>Geräte finden – optional</h2><form id="search"><label for="query">Raum, Alias, Name oder Gerätetyp</label><input id="query" maxlength="120" placeholder="z. B. Wohnzimmer"><button>Suchen</button></form><label for="template">Abfrage für ausgewähltes Gerät</label> <select id="template"></select><p id="count"></p><div id="results"></div><small>Auswahl bereitet nur eine Nachricht vor. Du sendest sie selbst.</small></section>
<section><h2>Verbindungen</h2><button id="check">Jetzt prüfen</button><pre id="diagnostics">Noch nicht geprüft. Keine automatische KI-Generierung.</pre></section></main>
<script>
const $=id=>document.getElementById(id);let pending=null,busy=false,templates=[];
async function api(path,data){const r=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-FHEM-Chat':'1'},body:JSON.stringify(data)});const s=await r.json();if(!r.ok)throw Error(typeof s.detail==='string'?s.detail:'Anfrage fehlgeschlagen');return s}
function controls(){for(const id of ['send','yes','no','reset'])$(id).disabled=busy; $('send').disabled=busy||!!pending}
function render(s){$('log').replaceChildren();for(const m of s.messages){if(!m.content)continue;const a=document.createElement(m.role==='tool'?'details':'article');if(m.role==='tool'){const title=document.createElement('summary');title.textContent='Werkzeugantwort';const pre=document.createElement('pre');pre.textContent=m.content;a.append(title,pre)}else{a.className='msg '+m.role;a.textContent=(m.role==='user'?'Du: ':'Assistent: ')+m.content}$('log').append(a)}pending=s.pending;$('approval').hidden=!pending;if(pending){$('proposal').textContent=JSON.stringify(pending.action,null,2);$('expires').textContent='Gültig bis '+new Date(pending.expires*1000).toLocaleTimeString()}controls();$('log').scrollTop=$('log').scrollHeight}
async function action(path,data){if(busy)return;busy=true;controls();$('error').textContent='';try{render(await api(path,data));return true}catch(e){$('error').textContent=e.message}finally{busy=false;controls()}}
$('chat').onsubmit=async e=>{e.preventDefault();if(pending)return;if(await action('/api/chat',{text:$('text').value}))$('text').value=''};
$('yes').onclick=()=>pending&&action('/api/decision',{id:pending.id,approve:true});$('no').onclick=()=>pending&&action('/api/decision',{id:pending.id,approve:false});$('reset').onclick=()=>confirm('Verlauf und offene Freigabe verwerfen?')&&action('/api/reset',{});
$('search').onsubmit=async e=>{e.preventDefault();$('results').replaceChildren();$('count').textContent='Suche …';try{const s=await api('/api/devices?q='+encodeURIComponent($('query').value));$('count').textContent=s.total+' Treffer; maximal 30 angezeigt. Suche bei Bedarf eingrenzen.';for(const d of s.devices){const b=document.createElement('button');b.className='device';b.textContent=d.alias+' · '+d.name+' · '+(d.room||'ohne Raum');b.onclick=()=>{const t=templates.find(t=>t.id===$('template').value);$('text').value=t.text.replace('{device}',JSON.stringify(d.name));$('text').focus()};$('results').append(b)}}catch(e){$('count').textContent=e.message}};
$('check').onclick=async()=>{$('check').disabled=true;try{$('diagnostics').textContent=JSON.stringify(await api('/api/diagnostics',{}),null,2)}catch(e){$('diagnostics').textContent=e.message}finally{$('check').disabled=false}};
(async()=>{try{render(await api('/api/state'));templates=(await api('/api/menu')).templates.filter(t=>t.id!=='devices');for(const t of templates){const o=document.createElement('option');o.value=t.id;o.textContent=t.label;$('template').append(o)}}catch(e){$('error').textContent=e.message}})();
</script></html>"""

# Replace only the existing HTML route; core chat and approval routes stay intact.
app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/"]
@app.get("/", response_class=HTMLResponse)
async def index(owner=Depends(core.auth)):
    return PAGE


async def send_state(uid, state, start):
    for message in state["messages"][start:]:
        if message["role"] == "assistant" and message.get("content"):
            for i in range(0, len(message["content"]), 3500):
                await core.tg("sendMessage", {"chat_id": uid, "text": message["content"][i:i+3500]})
    p = state["pending"]
    if p:
        text = json.dumps(p["action"], ensure_ascii=False, indent=2)
        for i in range(0, len(text), 3500):
            await core.tg("sendMessage", {"chat_id": uid, "text": text[i:i+3500]})
        await core.tg("sendMessage", {"chat_id": uid, "text": "Diesen Auftrag einmalig freigeben?", "reply_markup": {"inline_keyboard": [[{"text": "Ausführen", "callback_data": "y:"+p["id"]}, {"text": "Abbrechen", "callback_data": "n:"+p["id"]}]]}})


async def handle(update):
    cb = update.get("callback_query")
    msg = cb.get("message", {}) if cb else update.get("message", {})
    uid = (cb or msg).get("from", {}).get("id")
    if uid not in core.ALLOWED or msg.get("chat", {}).get("type") != "private" or msg.get("chat", {}).get("id") != uid:
        return
    owner = "tg:"+str(uid)
    start = len(core.store.load(owner))
    if cb:
        await core.tg("answerCallbackQuery", {"callback_query_id": cb["id"]})
        data = cb.get("data", "")
        if data.startswith(("y:", "n:")):
            state = await core.decide(owner, data[2:], data.startswith("y:"))
            await send_state(uid, state, start)
        elif data.startswith("d:"):
            selection = choices.pop(data[2:], None)
            if not selection or selection[0] != uid or selection[2] < time.monotonic():
                await core.tg("sendMessage", {"chat_id": uid, "text": "Auswahl abgelaufen. Bitte /devices Suchbegriff erneut senden."})
                return
            if core.store.pending(owner):
                await core.tg("sendMessage", {"chat_id": uid, "text": "Zuerst offenen Auftrag freigeben oder abbrechen."})
                return
            await send_state(uid, await core.chat(owner, make_prompt("status", selection[1])), start)
        return
    text = msg.get("text", "").strip()
    if not text or len(text) > 8000:
        return
    if text in ("/start", "/menu", "/help"):
        await core.tg("sendMessage", {"chat_id": uid, "text": "Schreibe direkt, z. B.: Welche Heizungen gibt es im Wohnzimmer?\n/devices Wohnzimmer sucht echte Geräte zur Auswahl. Keine exakten Namen nötig. Schreibaktionen brauchen eine eigene Freigabe."})
        return
    if text == "/devices" or text.startswith("/devices "):
        if core.store.pending(owner):
            await core.tg("sendMessage", {"chat_id": uid, "text": "Zuerst offenen Auftrag freigeben oder abbrechen."})
            return
        q = text.partition(" ")[2][:120]
        found = search(await devices(), q)
        now = time.monotonic()
        for key in list(choices):
            if choices[key][2] < now or choices[key][0] == uid:
                choices.pop(key, None)
        if len(choices) > 2000:
            raise ValueError("Auswahllimit erreicht")
        buttons = []
        for d in found[:20]:
            token = secrets.token_hex(12)
            choices[token] = (uid, d["name"], now+300)
            buttons.append([{"text": (d["alias"]+" · "+d["name"]+" · "+d["room"])[:100], "callback_data": "d:"+token}])
        await core.tg("sendMessage", {"chat_id": uid, "text": str(len(found))+" Treffer, maximal 20 angezeigt. Bei Bedarf Suchbegriff eingrenzen. Auswahl liest nur den Status.", "reply_markup": {"inline_keyboard": buttons}})
        return
    await send_state(uid, await core.chat(owner, text), start)


async def telegram():
    offset = 0
    while True:
        try:
            updates = await core.tg("getUpdates", {"offset": offset, "timeout": 25, "allowed_updates": ["message", "callback_query"]})
            for update in updates:
                offset = update["update_id"]+1
                try:
                    await handle(update)
                except Exception:
                    cb = update.get("callback_query")
                    uid = (cb or update.get("message", {})).get("from", {}).get("id")
                    if uid in core.ALLOWED:
                        with contextlib.suppress(Exception):
                            await core.tg("sendMessage", {"chat_id": uid, "text": "Anfrage fehlgeschlagen. Nicht automatisch wiederholt. MCP-Konfiguration oder Freigabe prüfen."})
        except Exception:
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(telegram()) if core.BOT and core.ALLOWED else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

app.router.lifespan_context = lifespan
