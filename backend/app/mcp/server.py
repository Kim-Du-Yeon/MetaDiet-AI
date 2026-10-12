"""Read-only MCP surface for food, nutrition and guideline evidence."""
import argparse
from typing import Any

from mcp.server import MCPServer


async def search_foods_data(query: str, limit: int = 10) -> dict[str, Any]:
    from app.tools.food_catalog import default_catalog
    return {'matches': await default_catalog().search(query, limit), 'limit': limit}


async def nutrition_lookup_data(food_id: str | int, quantity_g: float) -> dict[str, Any]:
    from app.tools.food_catalog import default_catalog
    return await default_catalog().lookup(food_id, quantity_g)


async def search_evidence_data(query: str, k: int = 4) -> dict[str, Any]:
    if not query.strip() or len(query) > 1000 or not 1 <= k <= 8:
        raise ValueError("invalid_arguments")
    from app.rag.retriever import retrieve

    result = await retrieve(query, k=k)
    evidence = []
    for doc in result.get("docs", []) if result.get("grounded") else []:
        evidence.append({"source": doc.metadata.get("source_file", "unknown"),
                         "page": str(doc.metadata.get("pdf_page", doc.metadata.get("page", "unknown"))),
                         "excerpt": doc.page_content,
                         "source_url": doc.metadata.get("source_url"),
                         "edition": doc.metadata.get("edition"),
                         "population": doc.metadata.get("population"),
                         "document_sha256": doc.metadata.get("document_sha256")})
    return {"grounded": bool(result.get("grounded")), "evidence": evidence}


async def call_readonly_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name not in {"search_foods", "nutrition_lookup", "search_evidence"}:
        raise ValueError("tool_not_allowed")
    result = await build_server().call_tool(name, arguments)
    if getattr(result, "isError", False) or getattr(result, "is_error", False):
        raise RuntimeError("mcp_tool_failed")
    structured = (getattr(result, "structuredContent", None)
                  or getattr(result, "structured_content", None))
    if not isinstance(structured, dict):
        raise RuntimeError("mcp_invalid_result")
    return structured


def build_server() -> MCPServer:
    server = MCPServer("metadiet-readonly", instructions=(
        "Read-only nutrition and evidence tools. No user records or writes are exposed."))

    @server.tool(description="국가 식품성분표에서 음식 후보를 조회합니다.", structured_output=True)
    async def search_foods(query: str, limit: int = 10) -> dict[str, Any]:
        return await search_foods_data(query, limit)

    @server.tool(description="식품 ID와 확인된 양으로 영양값을 계산합니다.", structured_output=True)
    async def nutrition_lookup(food_id: str | int, quantity_g: float) -> dict[str, Any]:
        return await nutrition_lookup_data(food_id, quantity_g)

    @server.tool(description="색인된 공식 영양 지침에서 근거를 조회합니다.", structured_output=True)
    async def search_evidence(query: str, k: int = 4) -> dict[str, Any]:
        return await search_evidence_data(query, k)

    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8090)
    args = parser.parse_args()
    build_server().run(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
