import pytest


@pytest.mark.asyncio
async def test_mcp_exposes_only_readonly_public_tools():
    from app.mcp.server import build_server

    tools = await build_server().list_tools()
    assert {tool.name for tool in tools} == {
        "search_foods", "nutrition_lookup", "search_evidence"
    }


@pytest.mark.asyncio
async def test_mcp_tool_adapter_returns_structured_result(monkeypatch):
    from app.mcp import server as module

    async def fake_search(query, limit):
        return {"matches": [{"food_id": 7, "name": query}], "limit": limit}

    monkeypatch.setattr(module, "search_foods_data", fake_search)
    result = await module.call_readonly_tool("search_foods", {"query": "현미", "limit": 3})
    assert result["matches"][0] == {"food_id": 7, "name": "현미"}


@pytest.mark.asyncio
async def test_mcp_sdk_call_tool_returns_structured_content(monkeypatch):
    from app.mcp import server as module

    async def fake_search(query, limit):
        return {"matches": [{"food_id": 1, "name": query}], "limit": limit}

    monkeypatch.setattr(module, "search_foods_data", fake_search)
    result = await module.build_server().call_tool("search_foods", {"query": "현미", "limit": 1})
    structured = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    assert structured["matches"][0]["name"] == "현미"


@pytest.mark.asyncio
async def test_mcp_rejects_unknown_or_write_tool():
    from app.mcp.server import call_readonly_tool

    with pytest.raises(ValueError, match="not_allowed"):
        await call_readonly_tool("save_meal", {})
