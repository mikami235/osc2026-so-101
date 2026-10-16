"""Local stdio MCP server exposing only dry-run pen-placement tools."""

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("so101-voice-mock-skills")


@mcp.tool()
def place_pen_right(target: str = "right") -> dict[str, str]:
    """Dry-run placing a pen in the right-side pen holder."""
    if target != "right":
        raise ValueError("place_pen_right only accepts target='right'")
    return {"skill": "place_pen_right", "target": target, "mode": "DRY-RUN", "result": "MOCK_SUCCESS"}


@mcp.tool()
def place_pen_left(target: str = "left") -> dict[str, str]:
    """Dry-run placing a pen in the left-side pen holder."""
    if target != "left":
        raise ValueError("place_pen_left only accepts target='left'")
    return {"skill": "place_pen_left", "target": target, "mode": "DRY-RUN", "result": "MOCK_SUCCESS"}


if __name__ == "__main__":
    mcp.run(transport="stdio")