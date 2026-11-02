from __future__ import annotations

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from .agent import ChatAgent
from .config import Settings, load_settings
from .db import Database
from .tooling import FhemWebClient, MCPToolClient


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    message: str = Field(min_length=1, max_length=8000)


class ApprovalRequest(BaseModel):
    conversation_id: str
    nonce: str


security = HTTPBasic(auto_error=False)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.db_path)
    db.cancel_pending_on_startup()
    mcp_client = MCPToolClient(settings)
    fhem_client = FhemWebClient(settings)
    agent = ChatAgent(settings=settings, db=db, mcp_client=mcp_client, fhem_client=fhem_client)

    app = FastAPI(title="FHEM Chat Agent")

    def get_user(credentials: HTTPBasicCredentials | None = Depends(security)) -> str:
        if credentials is None:
            raise HTTPException(status_code=401, detail="Authentication required", headers={"WWW-Authenticate": "Basic"})
        if credentials.username != settings.app_username or credentials.password != settings.app_password:
            raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
        return credentials.username

    @app.middleware("http")
    async def request_limits(request: Request, call_next):
        length = request.headers.get("content-length")
        if length and int(length) > settings.max_request_bytes:
            return JSONResponse(status_code=413, content={"detail": "Request too large"})
        if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "DELETE", "PATCH"}:
            origin = request.headers.get("origin")
            referer = request.headers.get("referer")
            base = str(request.base_url).rstrip("/")
            if not origin and not referer:
                return JSONResponse(status_code=403, content={"detail": "Origin/Referer erforderlich"})
            if origin and origin.rstrip("/") != base:
                return JSONResponse(status_code=403, content={"detail": "Origin not allowed"})
            if not origin and referer and not referer.startswith(base):
                return JSONResponse(status_code=403, content={"detail": "Referer not allowed"})
        return await call_next(request)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/ready")
    async def ready():
        return {
            "status": "ok",
            "config": {
                "openai_configured": bool(settings.openai_api_key),
                "mcp_configured": bool(settings.mcp_server_url),
                "fhemweb_configured": bool(settings.fhem_url),
                "telegram_configured": bool(settings.telegram_bot_token),
                "mcp_transport": settings.mcp_transport,
            },
            "notes": [
                "App startet ohne externe Endpunkte, meldet aber fehlende Konfigurationen.",
                "OPENAI_BASE_URL muss i.d.R. auf .../v1 enden.",
            ],
        }

    @app.get("/", response_class=HTMLResponse)
    async def index(user: str = Depends(get_user)):
        return HTMLResponse(
            """
<!doctype html><html lang='de'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>
<title>FHEM Chat Agent</title><style>body{font-family:sans-serif;max-width:860px;margin:0 auto;padding:1rem}#chat{border:1px solid #ddd;border-radius:8px;padding:1rem;min-height:40vh} .m{margin:.4rem 0;white-space:pre-wrap}</style></head>
<body><h1>FHEM Chat Agent</h1><div id='chat'></div><form id='f'><input id='i' style='width:80%'><button>Senden</button></form>
<script>
let cid=null;const chat=document.getElementById('chat');
function add(r,c){const d=document.createElement('div');d.className='m';d.textContent=`${r}: ${c}`;chat.appendChild(d);} // textContent => no XSS
async function send(msg){const res=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({conversation_id:cid,message:msg})});const j=await res.json();if(j.conversation_id)cid=j.conversation_id;add('assistant',j.reply);if(j.pending_action){add('system',`Freigabe nötig: ${j.pending_action.tool_name} -> ${j.pending_action.destination} args=${j.pending_action.tool_args_json}`)}}
document.getElementById('f').addEventListener('submit',async(e)=>{e.preventDefault();const i=document.getElementById('i');const t=i.value;i.value='';add('du',t);await send(t);});
</script></body></html>
"""
        )

    @app.get("/api/conversations")
    async def conversations(user: str = Depends(get_user)):
        return {"items": db.list_conversations(user)}

    @app.get("/api/conversations/{conversation_id}/messages")
    async def messages(conversation_id: str, user: str = Depends(get_user)):
        db.ensure_conversation(conversation_id, user)
        return {"items": db.get_messages(conversation_id)}

    @app.post("/api/chat")
    async def chat(payload: ChatRequest, user: str = Depends(get_user)):
        conversation_id = payload.conversation_id or db.create_conversation(user)
        db.ensure_conversation(conversation_id, user)
        db.add_message(conversation_id, "user", payload.message)
        db.add_audit(conversation_id, user, "user_message", {"text": payload.message})

        reply = await agent.handle_user_message(conversation_id=conversation_id, owner=user)
        return {
            "conversation_id": conversation_id,
            "reply": reply.text,
            "pending_action": None
            if not reply.pending
            else {
                "id": reply.pending.id,
                "conversation_id": reply.pending.conversation_id,
                "owner": reply.pending.owner,
                "tool_name": reply.pending.tool_name,
                "tool_args_json": reply.pending.tool_args_json,
                "destination": reply.pending.destination,
                "transport": reply.pending.transport,
                "nonce": reply.pending.nonce,
                "expires_at": reply.pending.expires_at,
            },
        }

    @app.post("/api/approvals/{action_id}/approve")
    async def approve(action_id: str, payload: ApprovalRequest, user: str = Depends(get_user)):
        pending = db.consume_pending(action_id, user, payload.conversation_id, payload.nonce, "approved")
        response = await agent.continue_after_approval(pending, owner=user, approved=True)
        return {"reply": response.text}

    @app.post("/api/approvals/{action_id}/reject")
    async def reject(action_id: str, payload: ApprovalRequest, user: str = Depends(get_user)):
        pending = db.consume_pending(action_id, user, payload.conversation_id, payload.nonce, "rejected")
        response = await agent.continue_after_approval(pending, owner=user, approved=False)
        return {"reply": response.text}

    @app.post("/telegram/webhook")
    async def telegram_webhook(request: Request, user: str = Depends(get_user)):
        # Telegram is optional and should normally run via long polling worker.
        update = await request.json()
        allowed_ids = set(settings.telegram_allowed_user_ids)
        sender = (update.get("message") or {}).get("from", {}).get("id") or (update.get("callback_query") or {}).get("from", {}).get("id")
        chat = (update.get("message") or {}).get("chat", {}) or (update.get("callback_query") or {}).get("message", {}).get("chat", {})
        if not allowed_ids or sender not in allowed_ids or chat.get("type") != "private" or chat.get("id") != sender:
            raise HTTPException(status_code=403, detail="Telegram update rejected")
        return {"status": "accepted"}

    return app


try:
    app = create_app()
except Exception as exc:  # pragma: no cover
    app = FastAPI(title="FHEM Chat Agent (config error)")

    @app.get("/health")
    async def _health_config_error():
        return {"status": "error", "detail": f"Startup-Konfiguration fehlt/ungültig: {type(exc).__name__}"}
