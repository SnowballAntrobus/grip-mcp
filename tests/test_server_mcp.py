"""MCP wiring smoke (DESIGN §6): the server builds, registers all 19 tools
with the versioned descriptions, and answers a tool call over the SDK
layer. Deep behavior lives in test_service.py — this pins the wiring."""

import asyncio
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

pytest.importorskip("mcp")

from grip_mcp import descriptions as D
from grip_mcp.server import build_server


def test_server_registers_all_tools(tmp_path):
    server = build_server(tmp_path)
    tools = asyncio.run(server.list_tools())
    by_name = {t.name: t for t in tools}
    assert set(by_name) == set(D.TOOL_DESCRIPTIONS)
    for name, tool in by_name.items():
        assert tool.description == D.TOOL_DESCRIPTIONS[name]


def test_server_instructions_wired(tmp_path):
    server = build_server(tmp_path)
    assert server.instructions == D.SERVER_INSTRUCTIONS


def _payload(result) -> dict:
    """Unwrap call_tool output across SDK shapes (list of content, or
    (content, structured) tuple)."""
    if isinstance(result, tuple):
        content, structured = result
        if isinstance(structured, dict):
            inner = structured.get("result", structured)
            if isinstance(inner, dict):
                return inner
        result = content
    return json.loads(result[0].text)


def test_tool_call_roundtrip(tmp_path):
    server = build_server(tmp_path)
    r = asyncio.run(
        server.call_tool("set_project", {"name": "song", "create": True})
    )
    payload = _payload(r)
    assert payload["created"] is True and payload["project"] == "song"


def test_identify_over_the_wire(tmp_path):
    server = build_server(tmp_path)

    async def run():
        await server.call_tool("set_project",
                               {"name": "song", "create": True})
        return await server.call_tool(
            "identify",
            {"strings": [2, 2, 2, None, None, None],
             "context_key": "e-minor"},
        )

    payload = _payload(asyncio.run(run()))
    assert payload["top"] == "F#q4"
    assert payload["candidates"][1]["name"] == "Bsus4/F#"
