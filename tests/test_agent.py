from __future__ import annotations

import json

import pytest

from app.agent import ChatAgent
from app.config import Settings
from app.db import Database
from app.tooling import DiscoveredTool, ToolResult


class _Msg:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []


class _Choice:
    def __init__(self, msg):
        self.message = msg


class _Completion:
    def __init__(self, msg):
        self.choices = [_Choice(msg)]


class _ToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})


class FakeLLM:
    def __init__(self, messages):
        self._messages = messages
        self.chat = type("Chat", (), {"completions": self})

    async def create(self, **kwargs):
        msg = self._messages.pop(0)
        return _Completion(msg)


class FakeMCPClient:
    def __init__(self, tools, result=None):
        self.tools = tools
        self.result = result or ToolResult(ok=True, content="ok")
        self.calls = 0

    async def list_tools(self):
        return self.tools

    async def call_tool(self, tool_name, args):
        self.calls += 1
        return self.result


class FakeFhemClient:
    TOOL_NAME = "fhemweb_raw_command"

    def __init__(self):
        self.calls = 0

    def schema(self):
        return {
            "type": "object",
            "properties": {"cmd": {"type": "string"}},
            "required": ["cmd"],
            "additionalProperties": False,
        }

    async def call(self, args):
        self.calls += 1
        return ToolResult(ok=True, content="direct-ok")


def _settings(tmp_path):
    return Settings(
        app_username="u",
        app_password="p",
        db_path=str(tmp_path / "db.sqlite"),
        openai_api_key="k",
        fhem_url="https://fhem.local/fhem",
    )


@pytest.mark.asyncio
async def test_discovery_filtering_and_write_requires_approval(tmp_path):
    settings = _settings(tmp_path)
    db = Database(settings.db_path)
    mcp = FakeMCPClient(
        [
            DiscoveredTool("calendar_list", "", {"type": "object"}, "mcp"),
            DiscoveredTool("fhem_list_devices", "", {"type": "object"}, "mcp"),
            DiscoveredTool("fhem_set", "", {"type": "object"}, "mcp"),
        ]
    )
    fhem = FakeFhemClient()
    agent = ChatAgent(settings, db, mcp, fhem)
    agent.llm = FakeLLM([_Msg(tool_calls=[_ToolCall("1", "fhem_set", "{}")])])

    cid = db.create_conversation("u")
    db.add_message(cid, "user", "mach etwas")

    response = await agent.handle_user_message(cid, "u")

    assert response.pending is not None
    assert response.pending.tool_name == "fhem_set"
    assert mcp.calls == 0


@pytest.mark.asyncio
async def test_approval_continues_conversation(tmp_path):
    settings = _settings(tmp_path)
    db = Database(settings.db_path)
    mcp = FakeMCPClient([DiscoveredTool("fhem_set", "", {"type": "object"}, "mcp")])
    fhem = FakeFhemClient()
    agent = ChatAgent(settings, db, mcp, fhem)
    agent.llm = FakeLLM([
        _Msg(tool_calls=[_ToolCall("1", "fhem_set", json.dumps({"x": 1}))]),
        _Msg(content="Fertig ausgeführt"),
    ])

    cid = db.create_conversation("u")
    db.add_message(cid, "user", "setze")
    pending = (await agent.handle_user_message(cid, "u")).pending
    assert pending is not None

    consumed = db.consume_pending(pending.id, "u", cid, pending.nonce, "approved")
    result = await agent.continue_after_approval(consumed, "u", approved=True)

    assert mcp.calls == 1
    assert "Fertig" in result.text


@pytest.mark.asyncio
async def test_rejected_approval_stops_execution(tmp_path):
    settings = _settings(tmp_path)
    db = Database(settings.db_path)
    mcp = FakeMCPClient([DiscoveredTool("fhem_set", "", {"type": "object"}, "mcp")])
    fhem = FakeFhemClient()
    agent = ChatAgent(settings, db, mcp, fhem)
    agent.llm = FakeLLM([_Msg(tool_calls=[_ToolCall("1", "fhem_set", "{}")])])

    cid = db.create_conversation("u")
    db.add_message(cid, "user", "setze")
    pending = (await agent.handle_user_message(cid, "u")).pending
    assert pending is not None

    consumed = db.consume_pending(pending.id, "u", cid, pending.nonce, "rejected")
    result = await agent.continue_after_approval(consumed, "u", approved=False)

    assert "abgelehnt" in result.text.lower()
    assert mcp.calls == 0
