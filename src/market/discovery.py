"""
Agent Discovery Protocol endpoint.

Provides a discoverable API for external systems to find available agents
and their capabilities, parameter schemas, and supported formats.
"""
from __future__ import annotations

from typing import Optional


async def discover_agents(
    db,
    capability: Optional[str] = None,
    category: Optional[str] = None,
    fmt: Optional[str] = None,
    skill: Optional[str] = None,
    mcp_server: Optional[str] = None,
    has_skill: Optional[str] = None,
    has_mcp: Optional[str] = None,
):
    """
    Discover available agents in the marketplace.

    Returns a machine-readable listing of agents with their capabilities,
    skills, and MCP server dependencies for automatic integration.
    """
    total, agents = await db.list_agents(
        category=category or "",
        skill=skill,
        mcp=mcp_server,
        page=1,
        page_size=100,
    )

    result = []
    for agent in agents:
        # Filter by capability from tags or category
        if capability:
            tags = agent.get("tags", [])
            agent_capability = tags if isinstance(tags, list) else []
            if capability not in agent_capability and capability != agent.get("category"):
                continue

        # Filter by supported format from agent.json compatibility field
        if fmt:
            compat = agent.get("compatibility", {})
            if fmt not in compat:
                continue

        agent_id = agent.get("id")

        # Load skills and MCP info from junction tables
        skills = await db.get_agent_skills(agent_id)
        mcp_servers_info = await db.get_agent_mcp_servers(agent_id)

        # Filter by has_skill / has_mcp
        if has_skill is not None and has_skill.lower() == "true" and not skills:
            continue
        if has_mcp is not None and has_mcp.lower() == "true" and not mcp_servers_info:
            continue

        result.append({
            "id": agent_id,
            "name": agent.get("name"),
            "version": agent.get("version"),
            "display_name": agent.get("display_name"),
            "description": agent.get("description"),
            "author": agent.get("author"),
            "category": agent.get("category"),
            "type": agent.get("type"),
            "tags": agent.get("tags", []),
            "dependencies": agent.get("dependencies", {}),
            "rating": agent.get("rating", 0),
            "download_count": agent.get("download_count", 0),
            "compatibility": agent.get("compatibility", {}),
            "skills": [
                {"id": s.get("id"), "display_name": s.get("display_name")}
                for s in skills
            ],
            "mcp_servers": [
                {"id": m.get("id"), "description": m.get("description")}
                for m in mcp_servers_info
            ],
        })

    return {
        "total": len(result),
        "agents": result,
    }
