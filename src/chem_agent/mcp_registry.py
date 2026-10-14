"""Fixed local MCP client: browsers can neither register commands nor remote servers."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from datetime import timedelta
from pathlib import Path

from chem_agent.tool_catalog import AGENT_TOOLS
from chem_agent.tools import DESCRIPTIONS, BusinessTool
from chem_agent.trace import utc_now

MCP_TOOLS = {
    "inspect_unit_compatibility": {
        "title": "单位量纲检查",
        "example": {"from_unit": "kg/h", "to_unit": "kg/s"},
    },
    "check_mass_flow_closure": {
        "title": "质量流量闭合检查",
        "example": {"inlet_flows_kg_h": [100, 400], "outlet_flows_kg_h": [500]},
    },
    "find_knowledge_sources": {
        "title": "知识资料来源查询",
        "example": {"query": "显热", "limit": 5},
    },
}


class ToolRegistry:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self._lock = asyncio.Lock()
        self._cached: dict | None = None
        self._cached_at = 0.0

    async def _exchange(self, name: str | None = None, arguments: dict | None = None):
        # Import on demand so an older installation can still serve its existing APIs.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        safe_env = {
            key: value
            for key, value in os.environ.items()
            if key.upper() in {"PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME"}
        }
        safe_env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        safe_env["PYTHONIOENCODING"] = "utf-8"
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "chem_agent.mcp_server", "--root", str(self.root)],
            env=safe_env,
        )
        async with asyncio.timeout(10):
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(
                    reader, writer, read_timeout_seconds=timedelta(seconds=7)
                ) as session:
                    await session.initialize()
                    if name is None:
                        return await session.list_tools()
                    return await session.call_tool(name, arguments or {})

    async def describe(self, *, refresh: bool = False) -> dict:
        async with self._lock:
            if not refresh and self._cached and time.monotonic() - self._cached_at < 60:
                return self._cached
            agent_tools = [
                {
                    **tool,
                    "description": DESCRIPTIONS[tool["name"]],
                    "source": "agent",
                    "invocation": "model",
                    "input_schema": {
                        "type": "object",
                        "properties": BusinessTool.inputs,
                        "required": list(BusinessTool.inputs),
                        "additionalProperties": False,
                    },
                }
                for tool in AGENT_TOOLS
            ]
            try:
                discovered = await self._exchange()
                tools = [
                    {
                        "name": tool.name,
                        "title": MCP_TOOLS[tool.name]["title"],
                        "description": tool.description or "",
                        "input_schema": tool.inputSchema,
                        "output_schema": tool.outputSchema,
                        "example": MCP_TOOLS[tool.name]["example"],
                        "source": "mcp",
                        "invocation": "manual",
                    }
                    for tool in discovered.tools
                    if tool.name in MCP_TOOLS
                ]
                result = {
                    "server": "chem-audit",
                    "transport": "stdio",
                    "state": "connected",
                    "checked_at": utc_now(),
                    "tools": agent_tools + tools,
                }
            except Exception:
                result = {
                    "server": "chem-audit",
                    "transport": "stdio",
                    "state": "unavailable",
                    "checked_at": utc_now(),
                    "tools": agent_tools,
                    "message": "MCP 服务未连接，请安装项目依赖并重启后端。",
                }
            self._cached, self._cached_at = result, time.monotonic()
            return result

    async def invoke(self, name: str, arguments: dict) -> dict:
        if name not in MCP_TOOLS:
            raise KeyError(name)
        async with self._lock:
            started_at, started = utc_now(), time.perf_counter()
            try:
                result = await self._exchange(name, arguments)
            except Exception:
                raise RuntimeError("MCP connection unavailable") from None
            return {
                "tool_name": name,
                "source": "manual",
                "server": "chem-audit",
                "status": "failed" if result.isError else "succeeded",
                "started_at": started_at,
                "finished_at": utc_now(),
                "latency_ms": round((time.perf_counter() - started) * 1000, 3),
                "arguments": arguments,
                "output": result.structuredContent if not result.isError else None,
                "error": "参数校验或工具执行失败，请核对参数类型、单位和数值范围。"
                if result.isError
                else None,
            }
