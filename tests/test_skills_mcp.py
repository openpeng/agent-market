"""Skills & MCP 提取与数据库测试"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path

import pytest

# Set up test environment
os.environ["MARKET_MASTER_KEY"] = "test-master-key"


# ============================================================
# 提取函数单元测试
# ============================================================

from src.market.skills_mcp import extract_skills_info, extract_mcp_info


def test_extract_skills_format_b_agent_builder():
    """格式 B: agent.json 顶层 skills 数组"""
    meta = {
        "identity": {"name": "test-agent", "version": "1.0.0"},
        "skills": [
            {"name": "skill-a", "display_name": "Skill A", "description": "desc", "version": "1.0.0",
             "icon": "💬", "category": "test"},
        ]
    }
    result = extract_skills_info(meta)
    assert len(result) == 1
    assert result[0]["id"] == "test-agent/skill-a"
    assert result[0]["original_name"] == "skill-a"
    assert result[0]["display_name"] == "Skill A"


def test_extract_skills_format_a_v3_subagent():
    """格式 A: subagents 中 type: "skill" 的项"""
    meta = {
        "identity": {"name": "my-agent", "version": "2.0.0"},
        "subagents": [
            {"name": "orchestrator", "path": "orchestrator.yaml"},
            {"name": "text-summarizer", "path": "skills/text-summarizer/worker.yaml", "type": "skill"},
        ]
    }
    result = extract_skills_info(meta)
    assert len(result) == 1
    assert result[0]["id"] == "my-agent/text-summarizer"
    assert result[0]["original_name"] == "text-summarizer"
    assert result[0]["version"] == "2.0.0"


def test_extract_skills_format_c_filesystem(tmp_path):
    """格式 C: skills/*.yaml 文件系统"""
    skills_dir = tmp_path / "skills"
    skills_dir.mkdir()
    (skills_dir / "my-skill.yaml").write_text("name: my-skill")
    (skills_dir / "another.yaml").write_text("name: another")

    meta = {"identity": {"name": "fs-agent", "version": "1.0.0"}}
    result = extract_skills_info(meta, tmp_path)
    assert len(result) == 2
    names = {s["original_name"] for s in result}
    assert names == {"my-skill", "another"}
    for s in result:
        assert s["id"].startswith("fs-agent/")


def test_extract_skills_dedup_same_name():
    """同一 Agent 内同名 skill 去重"""
    meta = {
        "identity": {"name": "test-agent", "version": "1.0.0"},
        "skills": [{"name": "shared-skill", "display_name": "from skills array"}],
        "subagents": [{"name": "shared-skill", "path": "s.yaml", "type": "skill"}],
    }
    result = extract_skills_info(meta)
    assert len(result) == 1
    # skills 数组的优先级高于 subagents（先提取先占）
    assert result[0]["display_name"] == "from skills array"


def test_extract_skills_no_skills():
    """没有 skills 的旧 Agent"""
    meta = {"identity": {"name": "old-agent", "version": "1.0.0"}}
    result = extract_skills_info(meta)
    assert result == []


def test_extract_mcp_format_a1_agent_builder():
    """格式 A1: agent.json 顶层 mcp_servers 数组"""
    meta = {
        "identity": {"name": "test-agent", "version": "1.0.0"},
        "mcp_servers": [
            {"name": "tapd", "description": "TAPD MCP", "command": "npx",
             "args": ["-y", "@scope/mcp-tapd"],
             "env": {"TAPD_KEY": "${KEY}", "TAPD_WS": "${WS}"}},
        ]
    }
    result = extract_mcp_info(meta)
    assert len(result) == 1
    assert result[0]["id"] == "test-agent/tapd"
    assert result[0]["original_name"] == "tapd"
    assert result[0]["command"] == "npx"
    assert result[0]["required_env"] == ["TAPD_KEY", "TAPD_WS"]


def test_extract_mcp_format_a2_v3():
    """格式 A2: mcp.required_servers（v3 规范）"""
    meta = {
        "identity": {"name": "test-agent", "version": "1.0.0"},
        "mcp": {
            "config_path": "./mcp/servers.json",
            "required_servers": [
                {"name": "tapd", "description": "TAPD", "package": "@openpeng/mcp-tapd",
                 "tools": ["tapd_create", "tapd_list"], "required_env": ["TAPD_KEY"]},
            ]
        }
    }
    result = extract_mcp_info(meta)
    assert len(result) == 1
    assert result[0]["id"] == "test-agent/tapd"
    assert result[0]["package"] == "@openpeng/mcp-tapd"
    assert result[0]["tools"] == ["tapd_create", "tapd_list"]
    assert result[0]["required_env"] == ["TAPD_KEY"]


def test_extract_mcp_format_b_config_json(tmp_path):
    """格式 B: mcp/config.json Claude Desktop 格式"""
    mcp_dir = tmp_path / "mcp"
    mcp_dir.mkdir()
    config = {
        "mcpServers": {
            "aliyun-log": {
                "type": "stdio",
                "command": "npx",
                "args": ["-y", "@openpeng/alilog-mcp"],
                "env": {"CRED_SOURCE": "consul"},
            }
        }
    }
    (mcp_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")

    meta = {"identity": {"name": "log-agent", "version": "1.0.0"}}
    result = extract_mcp_info(meta, tmp_path)
    assert len(result) == 1
    assert result[0]["id"] == "log-agent/aliyun-log"
    assert result[0]["command"] == "npx"
    assert result[0]["required_env"] == ["CRED_SOURCE"]


def test_extract_mcp_dedup():
    """Agent 内同名 MCP 去重"""
    meta = {
        "identity": {"name": "test-agent", "version": "1.0.0"},
        "mcp_servers": [{"name": "tapd", "command": "npx", "args": ["a"]}],
        "mcp": {"required_servers": [{"name": "tapd", "package": "pkg"}]},
    }
    result = extract_mcp_info(meta)
    assert len(result) == 1
    # mcp_servers 优先级高于 mcp.required_servers
    assert result[0]["command"] == "npx"


def test_extract_mcp_no_mcp():
    """没有 MCP 依赖的旧 Agent"""
    meta = {"identity": {"name": "simple-agent", "version": "1.0.0"}}
    result = extract_mcp_info(meta)
    assert result == []


# ============================================================
# 数据库集成测试（使用 asyncio.run 避免 async fixture 兼容问题）
# ============================================================

from src.market.database import MarketDatabase


def _create_db():
    """创建临时测试数据库"""
    db_path = "./data/test_market_skills.db"
    if os.path.exists(db_path):
        os.unlink(db_path)
    return db_path


async def _setup_db(db_path):
    database = MarketDatabase(db_path)
    await database.connect()
    await database.initialize()
    return database


async def _cleanup_db(database, db_path):
    await database.close()
    if os.path.exists(db_path):
        os.unlink(db_path)


async def _insert_test_agent(db, agent_id="test-agent"):
    now = "2026-01-01T00:00:00Z"
    await db._conn.execute(
        "INSERT INTO agents (id,name,display_name,version,description,author,created_at,updated_at,published_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (agent_id, agent_id, "Test Agent", "1.0.0", "test", "test", now, now, now)
    )
    await db._conn.commit()


def test_upsert_and_get_skill():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            skill = {"id": "test-agent/my-skill", "original_name": "my-skill",
                     "display_name": "My Skill", "description": "A test skill",
                     "version": "1.0.0", "category": "test", "icon": "🧪"}
            await db.upsert_skill(skill)
            result = await db.get_skill("test-agent/my-skill")
            assert result is not None
            assert result["id"] == "test-agent/my-skill"
            assert result["original_name"] == "my-skill"
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_upsert_skill_idempotent():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            skill = {"id": "test-agent/my-skill", "original_name": "my-skill", "display_name": "V1"}
            await db.upsert_skill(skill)
            skill["display_name"] = "V2"
            await db.upsert_skill(skill)
            result = await db.get_skill("test-agent/my-skill")
            assert result["display_name"] == "V2"
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_list_skills():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await db.upsert_skill({"id": "a/s1", "original_name": "s1", "display_name": "Skill 1", "category": "cat"})
            await db.upsert_skill({"id": "b/s2", "original_name": "s2", "display_name": "Skill 2", "category": "cat"})
            total, items = await db.list_skills(category="cat")
            assert total == 2

            total, items = await db.list_skills(q="Skill 2")
            assert total == 1
            assert items[0]["id"] == "b/s2"
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_delete_skill():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await db.upsert_skill({"id": "test-agent/my-skill", "original_name": "my-skill"})
            assert await db.get_skill("test-agent/my-skill") is not None
            await db.delete_skill("test-agent/my-skill")
            assert await db.get_skill("test-agent/my-skill") is None
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_agent_skill_association():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await _insert_test_agent(db)
            s1 = {"id": "test-agent/s1", "original_name": "s1", "display_name": "Skill 1"}
            s2 = {"id": "test-agent/s2", "original_name": "s2", "display_name": "Skill 2"}
            await db.upsert_skill(s1)
            await db.upsert_skill(s2)
            await db.sync_agent_skills("test-agent", ["test-agent/s1", "test-agent/s2"])

            skills = await db.get_agent_skills("test-agent")
            assert len(skills) == 2
            assert {s["id"] for s in skills} == {"test-agent/s1", "test-agent/s2"}

            agents = await db.get_skill_agents("test-agent/s1")
            assert len(agents) == 1
            assert agents[0]["id"] == "test-agent"

            # 更新关联
            await db.sync_agent_skills("test-agent", ["test-agent/s1"])
            skills = await db.get_agent_skills("test-agent")
            assert len(skills) == 1
            assert skills[0]["id"] == "test-agent/s1"
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_agent_mcp_association():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await _insert_test_agent(db)
            mcp = {"id": "test-agent/tapd", "original_name": "tapd", "description": "TAPD MCP",
                   "command": "npx", "args": ["-y", "pkg"], "required_env": ["TAPD_KEY"]}
            await db.upsert_mcp_server(mcp)
            await db.sync_agent_mcp_servers("test-agent", ["test-agent/tapd"])

            servers = await db.get_agent_mcp_servers("test-agent")
            assert len(servers) == 1
            assert servers[0]["id"] == "test-agent/tapd"
            assert servers[0]["args"] == ["-y", "pkg"]
            assert servers[0]["required_env"] == ["TAPD_KEY"]

            agents = await db.get_mcp_server_agents("test-agent/tapd")
            assert len(agents) == 1
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_cascade_delete():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await _insert_test_agent(db, "cascade-agent")
            await db.upsert_skill({"id": "cascade-agent/s1", "original_name": "s1", "display_name": "Skill"})
            await db.sync_agent_skills("cascade-agent", ["cascade-agent/s1"])

            assert await db.get_agent("cascade-agent") is not None
            assert len(await db.get_agent_skills("cascade-agent")) == 1

            await db.delete_agent("cascade-agent")
            assert await db.get_agent("cascade-agent") is None
            # Skill 本身保留
            assert await db.get_skill("cascade-agent/s1") is not None
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_list_agents_with_skill_filter():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await _insert_test_agent(db, "agent-a")
            await _insert_test_agent(db, "agent-b")

            await db.upsert_skill({"id": "agent-a/s1", "original_name": "s1", "display_name": "Skill 1"})
            await db.upsert_skill({"id": "agent-b/s2", "original_name": "s2", "display_name": "Skill 2"})
            await db.sync_agent_skills("agent-a", ["agent-a/s1"])
            await db.sync_agent_skills("agent-b", ["agent-b/s2"])

            total, items = await db.list_agents(skill="s1")
            assert total == 1
            assert items[0]["id"] == "agent-a"

            total, items = await db.list_agents(skill="nonexistent")
            assert total == 0
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())


def test_mcp_server_list():
    db_path = _create_db()
    async def run():
        db = await _setup_db(db_path)
        try:
            await db.upsert_mcp_server({"id": "a/tapd", "original_name": "tapd", "description": "TAPD MCP",
                                        "command": "npx", "args": ["-y", "pkg"]})
            await db.upsert_mcp_server({"id": "b/wecom", "original_name": "wecom", "description": "WeCom MCP"})

            total, items = await db.list_mcp_servers()
            assert total == 2

            total, items = await db.list_mcp_servers(q="tapd")
            assert total == 1
            assert items[0]["original_name"] == "tapd"
            assert items[0]["agent_count"] == 0
        finally:
            await _cleanup_db(db, db_path)
    asyncio.run(run())
