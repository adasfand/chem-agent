"""Exercise real local MCP stdio discovery and calls without a model service."""

import asyncio

from chem_agent.mcp_registry import ToolRegistry


def test_real_mcp_registry_and_deterministic_tools(tmp_path):
    directory = tmp_path / "data" / "knowledge"
    directory.mkdir(parents=True)
    (directory / "heat.md").write_text(
        "# 显热公式\n来源：测试来源\n\n## 公式\nQ=mcpΔT", encoding="utf-8"
    )

    async def check():
        registry = ToolRegistry(tmp_path)
        catalog = await registry.describe()
        assert catalog["state"] == "connected", catalog
        assert len([tool for tool in catalog["tools"] if tool["source"] == "mcp"]) == 3
        assert all(
            tool["invocation"] == "manual" for tool in catalog["tools"] if tool["source"] == "mcp"
        )
        units = await registry.invoke(
            "inspect_unit_compatibility", {"from_unit": "kg/h", "to_unit": "kg/s"}
        )
        assert units["status"] == "succeeded"
        assert units["output"]["compatible"] is True
        assert units["source"] == "manual" and units["latency_ms"] >= 0
        mismatch = await registry.invoke(
            "inspect_unit_compatibility", {"from_unit": "K", "to_unit": "delta_K"}
        )
        assert mismatch["output"]["compatible"] is False
        balanced = await registry.invoke(
            "check_mass_flow_closure", {"inlet_flows_kg_h": [100, 400], "outlet_flows_kg_h": [500]}
        )
        assert balanced["output"]["balanced"] is True
        unbalanced = await registry.invoke(
            "check_mass_flow_closure", {"inlet_flows_kg_h": [100, 400], "outlet_flows_kg_h": [480]}
        )
        assert unbalanced["output"]["balanced"] is False
        assert unbalanced["output"]["residual_kg_h"] == 20
        invalid = await registry.invoke(
            "check_mass_flow_closure", {"inlet_flows_kg_h": [True], "outlet_flows_kg_h": [0]}
        )
        assert invalid["status"] == "failed"
        assert invalid["output"] is None
        unknown = await registry._exchange(
            "check_mass_flow_closure",
            {"inlet_flows_kg_h": [100], "outlet_flows_kg_h": [90], "accumulation_kg_h": 10},
        )
        assert unknown.isError is True
        sources = await registry.invoke("find_knowledge_sources", {"query": "显热", "limit": 5})
        assert sources["output"]["matched_count"] == 1
        assert sources["output"]["documents"][0]["source"] == "测试来源"

    asyncio.run(check())
