from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def _settings(tmp_path):
    return Settings(
        app_username="user",
        app_password="pass",
        db_path=str(tmp_path / "db.sqlite"),
        openai_api_key="k",
        telegram_allowed_user_ids=(42,),
    )


def _auth():
    import base64

    token = base64.b64encode(b"user:pass").decode()
    return {"Authorization": f"Basic {token}"}


def test_auth_required(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    res = client.get("/api/conversations")
    assert res.status_code == 401


def test_telegram_allowlist_and_private_chat(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app)

    ok = {
        "message": {
            "chat": {"id": 42, "type": "private"},
            "from": {"id": 42},
            "text": "hi",
        }
    }
    bad = {
        "message": {
            "chat": {"id": 99, "type": "group"},
            "from": {"id": 99},
            "text": "hi",
        }
    }

    assert client.post("/telegram/webhook", headers=_auth(), json=ok).status_code == 200
    assert client.post("/telegram/webhook", headers=_auth(), json=bad).status_code == 403


def test_api_post_requires_same_origin_headers(tmp_path):
    app = create_app(_settings(tmp_path))
    client = TestClient(app)
    res = client.post("/api/chat", headers=_auth(), json={"message": "hallo"})
    assert res.status_code == 403
