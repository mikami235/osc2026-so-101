"""Allowlisted client for the local voice skill MCP server."""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from .router import SKILL_TARGETS


async def _call_skill(skill: str, target: str) -> str:
    if skill not in SKILL_TARGETS or SKILL_TARGETS[skill] != target:
        raise ValueError("Requested MCP tool is not allowlisted")
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError("Install the voice extra with: uv sync --extra voice") from exc

    server_path = Path(__file__).with_name("mcp_server.py")
    params = StdioServerParameters(command=sys.executable, args=[str(server_path)])
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            available = await session.list_tools()
            names = {tool.name for tool in available.tools}
            if skill not in names:
                raise RuntimeError(f"MCP skill is not registered: {skill}")
            result = await session.call_tool(skill, arguments={"target": target})
            if result.isError:
                raise RuntimeError(f"MCP skill failed: {skill}")
            structured: Any = getattr(result, "structuredContent", None)
            if structured is None:
                for item in result.content:
                    text = getattr(item, "text", None)
                    if text:
                        try:
                            structured = json.loads(text)
                            break
                        except json.JSONDecodeError:
                            continue
            if not isinstance(structured, dict) or structured.get("result") != "MOCK_SUCCESS":
                raise RuntimeError(f"MCP skill returned an invalid result: {skill}")
            return str(structured["result"])


def call_skill(skill: str, target: str) -> str:
    try:
        return asyncio.run(_call_skill(skill, target))
    except BaseExceptionGroup as exc:
        leaf: BaseException = exc
        while isinstance(leaf, BaseExceptionGroup) and len(leaf.exceptions) == 1:
            leaf = leaf.exceptions[0]
        if isinstance(leaf, Exception):
            raise leaf from exc
        raise RuntimeError("Local MCP server communication failed") from exc