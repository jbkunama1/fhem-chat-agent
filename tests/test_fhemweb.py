from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.tooling import FhemWebClient


@pytest.mark.asyncio
async def test_raw_command_encoded_and_basic_auth(monkeypatch, tmp_path):
    captured = {}

    async def fake_get(self, url):
        captured["url"] = url
        captured["auth"] = self._auth
        return httpx.Response(200, text="ok")

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    settings = Settings(
        app_username="u",
        app_password="p",
        db_path=str(tmp_path / "db.sqlite"),
        openai_api_key="k",
        fhem_url="https://fhem.local/fhem",
        fhem_username="user",
        fhem_password="pass",
    )
    client = FhemWebClient(settings)
    result = await client.call({"cmd": "list TYPE=switch"})

    assert result.ok
    assert "cmd=list+TYPE%3Dswitch" in captured["url"]
    assert "XHR=1" in captured["url"]
    assert "fwcsrf" not in captured["url"].lower()
    assert captured["auth"] is not None


@pytest.mark.asyncio
async def test_timeout_no_retry(monkeypatch, tmp_path):
    calls = {"n": 0}

    async def timeout_get(self, url):
        calls["n"] += 1
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(httpx.AsyncClient, "get", timeout_get)
    settings = Settings(
        app_username="u",
        app_password="p",
        db_path=str(tmp_path / "db.sqlite"),
        openai_api_key="k",
        fhem_url="https://fhem.local/fhem",
    )
    client = FhemWebClient(settings)
    result = await client.call({"cmd": "set lamp on"})

    assert not result.ok
    assert result.uncertain
    assert "keine automatische wiederholung" in result.content.lower()
    assert calls["n"] == 1
