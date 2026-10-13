"""Read-only and deterministic auxiliary tools exposed through local MCP stdio."""

from __future__ import annotations

import argparse
import math
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from chem_agent.calculations import _UNITS, _finite_number, _resolve_unit
from chem_agent.knowledge import KnowledgeBase

Number = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Flows = Annotated[list[Number], Field(min_length=1, max_length=32)]
Text = Annotated[str, Field(strict=True, min_length=1, max_length=64)]
Query = Annotated[str, Field(strict=True, max_length=200)]


class StrictToolServer(FastMCP):
    """Reject extra parameters at the protocol boundary, including direct MCP clients."""

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            tool.inputSchema["additionalProperties"] = False
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        tool = next((tool for tool in await self.list_tools() if tool.name == name), None)
        if tool and set(arguments) - set(tool.inputSchema.get("properties", {})):
            raise ValueError("工具参数包含未支持的字段，请按参数规范填写。")
        return await super().call_tool(name, arguments)


def create_server(root: Path) -> FastMCP:
    server = StrictToolServer("chem-audit", log_level="ERROR")

    @server.tool(structured_output=True)
    def inspect_unit_compatibility(from_unit: Text, to_unit: Text) -> dict[str, Any]:
        """检查两个常用单位的量纲和换算兼容性，区分绝对温度与温差。"""
        source_group, source = _resolve_unit(from_unit, "from_unit")
        target_group, target = _resolve_unit(to_unit, "to_unit")
        return {
            "compatible": source_group == target_group,
            "from_unit": from_unit,
            "to_unit": to_unit,
            "from_quantity": source_group,
            "to_quantity": target_group,
            "from_dimension": str(_UNITS.Unit(source).dimensionality),
            "to_dimension": str(_UNITS.Unit(target).dimensionality),
        }

    @server.tool(structured_output=True)
    def check_mass_flow_closure(
        inlet_flows_kg_h: Flows,
        outlet_flows_kg_h: Flows,
        absolute_tolerance_kg_h: Number = 0.001,
        relative_tolerance: Annotated[float, Field(strict=True, ge=0, le=1)] = 1e-6,
    ) -> dict[str, Any]:
        """核对稳态、无质量积累的总质量流量闭合；所有流量单位为 kg/h。"""
        inlet = _finite_number(math.fsum(inlet_flows_kg_h), "入口总流量")
        outlet = _finite_number(math.fsum(outlet_flows_kg_h), "出口总流量")
        residual = inlet - outlet
        scale = max(inlet, outlet)
        tolerance = max(absolute_tolerance_kg_h, relative_tolerance * scale)
        return {
            "balanced": abs(residual) <= tolerance,
            "inlet_total_kg_h": inlet,
            "outlet_total_kg_h": outlet,
            "residual_kg_h": residual,
            "relative_residual": abs(residual) / scale if scale else 0.0,
            "allowed_residual_kg_h": tolerance,
            "assumption": "稳态、无总质量积累；核对总质量流量。",
        }

    @lru_cache(maxsize=1)
    def knowledge() -> KnowledgeBase:
        return KnowledgeBase(root / "data" / "knowledge")

    @server.tool(structured_output=True)
    def find_knowledge_sources(
        query: Query = "", limit: Annotated[int, Field(strict=True, ge=1, le=20)] = 5
    ) -> dict[str, Any]:
        """按标题和来源筛选本地知识资料目录，返回来源信息；空查询列出目录。"""
        needle = query.strip().casefold()
        matches = [
            {key: item[key] for key in ("doc_id", "title", "source", "chunk_count")}
            for item in knowledge().inventory()
            if not needle or needle in f"{item['title']} {item['source']}".casefold()
        ]
        return {"query": query, "matched_count": len(matches), "documents": matches[:limit]}

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    create_server(args.root.resolve()).run(transport="stdio")


if __name__ == "__main__":
    main()
