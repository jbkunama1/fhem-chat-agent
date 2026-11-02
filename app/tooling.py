from __future__ import annotations

import json
import urllib.parse
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
from jsonschema import ValidationError, validate

from .config import MUTATION_KEYWORDS, READ_ONLY_ALLOWLIST, Settings

try:
    from mcp import ClientSession
    from mcp.client.sse import sse_client
    from mcp.client.streamable_http import streamablehttp_client
except Exception:  # pragma: no cover
    ClientSession = None
    sse_client = None
    streamablehttp_client = None


@dataclass
class DiscoveredTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    source: str


@dataclass
class ToolResult:
    ok: bool
    content: str
    uncertain: bool = False


class MCPToolClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _headers(self) -> dict[str, str]:
        if not self.settings.mcp_api_key:
            return {}
        if self.settings.mcp_auth_scheme:
            value = f"{self.settings.mcp_auth_scheme} {self.settings.mcp_api_key}".strip()
        else:
            value = self.settings.mcp_api_key
        return {self.settings.mcp_auth_header: value}

    @asynccontextmanager
    async def _session(self):
        if ClientSession is None:
            raise RuntimeError("MCP SDK nicht installiert")
        headers = self._headers()
        if self.settings.mcp_transport == "sse":
            async with sse_client(self.settings.mcp_server_url, headers=headers) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    yield session
        else:
            async with streamablehttp_client(self.settings.mcp_server_url, headers=headers) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    yield session

    async def list_tools(self) -> list[DiscoveredTool]:
        out: list[DiscoveredTool] = []
        cursor = None
        async with self._session() as session:
            while True:
                result = await session.list_tools(cursor=cursor)
                for tool in result.tools:
                    out.append(
                        DiscoveredTool(
                            name=tool.name,
                            description=tool.description or "",
                            input_schema=tool.inputSchema or {"type": "object"},
                            source="mcp",
                        )
                    )
                cursor = getattr(result, "nextCursor", None)
                if not cursor:
                    break
        return out

    async def call_tool(self, tool_name: str, args: dict[str, Any]) -> ToolResult:
        async with self._session() as session:
            result = await session.call_tool(tool_name, args)
            text_chunks = []
            for item in getattr(result, "content", []) or []:
                text = getattr(item, "text", None)
                if text:
                    text_chunks.append(text)
            is_error = bool(getattr(result, "isError", False))
            text = "\n".join(text_chunks) if text_chunks else json.dumps(args, ensure_ascii=False)
            if is_error:
                return ToolResult(ok=False, content=f"MCP-Fehler: {text}", uncertain=False)
            return ToolResult(ok=True, content=text)


class FhemWebClient:
    TOOL_NAME = "fhemweb_raw_command"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"cmd": {"type": "string", "minLength": 1}},
            "required": ["cmd"],
            "additionalProperties": False,
        }

    async def call(self, args: dict[str, Any]) -> ToolResult:
        if not self.settings.fhem_url:
            return ToolResult(ok=False, content="FHEM_URL ist nicht konfiguriert.", uncertain=True)
        cmd = args.get("cmd", "")
        query = urllib.parse.urlencode({"cmd": cmd, "XHR": "1"})
        url = f"{self.settings.fhem_url}?{query}"
        auth = None
        if self.settings.fhem_username and self.settings.fhem_password:
            auth = (self.settings.fhem_username, self.settings.fhem_password)
        timeout = httpx.Timeout(20.0)
        async with httpx.AsyncClient(timeout=timeout, verify=self.settings.fhem_verify_tls, auth=auth) as client:
            try:
                resp = await client.get(url)
            except httpx.TimeoutException:
                return ToolResult(ok=False, content="FHEMWEB Timeout (keine automatische Wiederholung).", uncertain=True)
            except Exception as exc:
                return ToolResult(ok=False, content=f"FHEMWEB Fehler: {type(exc).__name__}", uncertain=True)
        text = resp.text
        if resp.status_code >= 400:
            return ToolResult(ok=False, content=f"FHEMWEB HTTP {resp.status_code}: {text}", uncertain=False)
        if "csrf" in text.lower() or "forbidden" in text.lower():
            return ToolResult(ok=False, content=f"FHEMWEB hat Anfrage abgelehnt (möglicherweise CSRF): {text}", uncertain=False)
        if "error" in text.lower():
            return ToolResult(ok=False, content=f"FHEMWEB meldet Fehler: {text}", uncertain=False)
        return ToolResult(ok=True, content=text)


class ToolPolicy:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def is_fhem_tool(name: str) -> bool:
        lowered = name.lower()
        return lowered.startswith("fhem")

    @staticmethod
    def is_mutation_tool(name: str) -> bool:
        lowered = name.lower()
        return any(word in lowered for word in MUTATION_KEYWORDS)

    def requires_approval(self, tool: DiscoveredTool) -> bool:
        if tool.name == FhemWebClient.TOOL_NAME:
            return True
        if tool.name in READ_ONLY_ALLOWLIST:
            return False
        return True

    def filter_fhem_tools(self, tools: list[DiscoveredTool]) -> list[DiscoveredTool]:
        return [tool for tool in tools if self.is_fhem_tool(tool.name)]


def validate_tool_arguments(schema: dict[str, Any], args: dict[str, Any]) -> None:
    try:
        validate(instance=args, schema=schema)
    except ValidationError as exc:
        raise ValueError(f"Ungültige Tool-Argumente: {exc.message}") from exc
