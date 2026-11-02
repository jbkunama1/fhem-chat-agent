from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from .config import Settings
from .db import Database, PendingAction
from .tooling import DiscoveredTool, FhemWebClient, MCPToolClient, ToolPolicy, ToolResult, validate_tool_arguments


@dataclass
class AgentResponse:
    text: str
    pending: PendingAction | None = None


class ChatAgent:
    def __init__(self, settings: Settings, db: Database, mcp_client: MCPToolClient, fhem_client: FhemWebClient) -> None:
        self.settings = settings
        self.db = db
        self.mcp_client = mcp_client
        self.fhem_client = fhem_client
        self.policy = ToolPolicy(settings)
        self.llm = (
            AsyncOpenAI(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                timeout=settings.openai_timeout_seconds,
            )
            if settings.openai_api_key
            else None
        )

    async def _discover_tools(self) -> dict[str, DiscoveredTool]:
        tools = []
        try:
            tools = await self.mcp_client.list_tools()
        except Exception:
            tools = []
        filtered = self.policy.filter_fhem_tools(tools)
        mapped = {tool.name: tool for tool in filtered}
        mapped[self.fhem_client.TOOL_NAME] = DiscoveredTool(
            name=self.fhem_client.TOOL_NAME,
            description="Direkter FHEMWEB Rohbefehl (immer genehmigungspflichtig)",
            input_schema=self.fhem_client.schema(),
            source="fhemweb",
        )
        return mapped

    def _to_openai_tools(self, tools: dict[str, DiscoveredTool]) -> list[dict[str, Any]]:
        out = []
        for tool in tools.values():
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.input_schema,
                    },
                }
            )
        return out

    async def _execute_tool(self, tool: DiscoveredTool, args: dict[str, Any]) -> ToolResult:
        if tool.source == "fhemweb":
            return await self.fhem_client.call(args)
        return await self.mcp_client.call_tool(tool.name, args)

    async def handle_user_message(self, conversation_id: str, owner: str) -> AgentResponse:
        self.db.ensure_conversation(conversation_id, owner)
        if self.llm is None:
            text = "OPENAI_API_KEY fehlt. Chat-Antworten können aktuell nicht erzeugt werden."
            self.db.add_message(conversation_id, "assistant", text)
            self.db.add_audit(conversation_id, owner, "missing_openai_config", {})
            return AgentResponse(text=text)
        tools = await self._discover_tools()
        messages = self.db.get_messages(conversation_id)

        for _ in range(self.settings.max_tool_iterations):
            completion = await self.llm.chat.completions.create(
                model=self.settings.model,
                messages=messages,
                tools=self._to_openai_tools(tools),
                tool_choice="auto",
            )
            msg = completion.choices[0].message
            if not msg.tool_calls:
                text = msg.content or ""
                self.db.add_message(conversation_id, "assistant", text)
                self.db.add_audit(conversation_id, owner, "assistant_reply", {"text": text})
                return AgentResponse(text=text)

            tool_call = msg.tool_calls[0]
            tool_name = tool_call.function.name
            tool = tools.get(tool_name)
            if not tool:
                text = f"Tool {tool_name} ist nicht erlaubt."
                self.db.add_message(conversation_id, "assistant", text)
                self.db.add_audit(conversation_id, owner, "blocked_tool", {"tool": tool_name})
                return AgentResponse(text=text)

            args = json.loads(tool_call.function.arguments or "{}")
            validate_tool_arguments(tool.input_schema, args)

            if self.policy.requires_approval(tool):
                pending = self.db.add_pending_action(
                    conversation_id=conversation_id,
                    owner=owner,
                    tool_name=tool.name,
                    tool_args=args,
                    destination=self.settings.fhem_url if tool.source == "fhemweb" else self.settings.mcp_server_url,
                    transport=tool.source,
                    ttl_seconds=self.settings.approval_ttl_seconds,
                )
                self.db.add_audit(
                    conversation_id,
                    owner,
                    "approval_requested",
                    {
                        "action_id": pending.id,
                        "tool": tool.name,
                        "args": args,
                        "destination": pending.destination,
                        "transport": pending.transport,
                    },
                )
                text = (
                    "Aktion wartet auf Freigabe. "
                    f"Tool: {tool.name}, Ziel: {pending.destination}, Argumente: {pending.tool_args_json}"
                )
                self.db.add_message(conversation_id, "assistant", text)
                return AgentResponse(text=text, pending=pending)

            result = await self._execute_tool(tool, args)
            tool_text = result.content
            self.db.add_audit(
                conversation_id,
                owner,
                "tool_executed",
                {"tool": tool.name, "args": args, "ok": result.ok, "uncertain": result.uncertain, "result": tool_text},
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": tool.name,
                    "content": tool_text,
                }
            )
            self.db.add_message(conversation_id, "tool", f"{tool.name}: {tool_text}")

        text = "Maximale Tool-Iterationen erreicht. Ergebnis ist ggf. unvollständig."
        self.db.add_message(conversation_id, "assistant", text)
        return AgentResponse(text=text)

    async def continue_after_approval(self, pending: PendingAction, owner: str, approved: bool) -> AgentResponse:
        if not approved:
            self.db.add_audit(
                pending.conversation_id,
                owner,
                "approval_rejected",
                {"action_id": pending.id, "tool": pending.tool_name},
            )
            self.db.add_message(pending.conversation_id, "tool", f"{pending.tool_name}: Vom Benutzer abgelehnt")
            self.db.add_message(pending.conversation_id, "assistant", "Ausführung wurde abgelehnt.")
            return AgentResponse(text="Ausführung wurde abgelehnt.")

        tools = await self._discover_tools()
        tool = tools.get(pending.tool_name)
        if not tool:
            text = "Tool ist nicht mehr verfügbar."
            self.db.add_message(pending.conversation_id, "assistant", text)
            return AgentResponse(text=text)
        args = json.loads(pending.tool_args_json)
        validate_tool_arguments(tool.input_schema, args)

        result = await self._execute_tool(tool, args)
        self.db.add_audit(
            pending.conversation_id,
            owner,
            "approval_executed",
            {
                "action_id": pending.id,
                "tool": tool.name,
                "args": args,
                "ok": result.ok,
                "uncertain": result.uncertain,
            },
        )
        self.db.add_message(pending.conversation_id, "tool", f"{tool.name}: {result.content}")
        if not result.ok:
            note = "Ergebnis unsicher." if result.uncertain else "Tool meldete einen Fehler."
            self.db.add_message(pending.conversation_id, "assistant", f"{note} {result.content}")
            return AgentResponse(text=f"{note} {result.content}")
        return await self.handle_user_message(pending.conversation_id, owner)
