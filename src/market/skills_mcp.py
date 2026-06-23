"""
市场服务 - Skills & MCP 信息提取
================================
从 agent.json 和文件系统归一化提取 skills 和 MCP server 信息。
支持 3 种 skills 格式 + 3 种 MCP 格式，统一归一化为带 agent 前缀的 id。
"""
from __future__ import annotations

import json
from pathlib import Path


def extract_skills_info(metadata: dict, extract_dir: Path | None = None) -> list[dict]:
    """从 agent.json 和文件系统归一化提取 skills 信息（v3.1 更新）

    支持格式：
    - 格式 A: agent.json 顶层 skills 数组（source: "local"/"market"）
    - 格式 B: skills/*.yaml 文件（Runtime 文件系统加载）
    - 格式 C: skills/ 目录下的 skill.json 文件（v3.1 推荐）

    返回格式：
    [
        {
            "id": "agent-name/skill-name",    # qualified id
            "original_name": "skill-name",    # 原始 name
            "display_name": "显示名称",
            "description": "...",
            "version": "1.0.0",
            "category": "nlp",
            "icon": "💬",
            "content": "...",                  # v3.1 新增: SKILL.md 内容
            "capabilities": ["..."],           # v3.1 新增: 能力列表
        }
    ]
    """
    agent_name = metadata.get("identity", {}).get("name", "")
    skills = []

    # 格式 A: agent.json 顶层 skills 数组（v3.1 推荐）
    for skill in metadata.get("skills", []):
        raw_name = skill.get("name", "")
        if not raw_name:
            continue
        skills.append({
            "id": f"{agent_name}/{raw_name}" if agent_name else raw_name,
            "original_name": raw_name,
            "display_name": skill.get("display_name", raw_name),
            "description": skill.get("description", ""),
            "version": skill.get("version", ""),
            "category": skill.get("category", ""),
            "icon": skill.get("icon", ""),
            "content": skill.get("content", ""),
            "capabilities": skill.get("capabilities", []),
        })

    # 格式 B: skills/*.yaml 文件（Runtime 文件系统加载）
    seen_names = {s["original_name"] for s in skills}
    if extract_dir:
        skills_dir = extract_dir / "skills"
        if skills_dir.is_dir():
            for yaml_file in skills_dir.glob("*.yaml"):
                raw_name = yaml_file.stem
                if raw_name in seen_names:
                    continue
                skills.append({
                    "id": f"{agent_name}/{raw_name}",
                    "original_name": raw_name,
                    "display_name": raw_name,
                    "description": f"Skill from {yaml_file.name}",
                    "version": metadata.get("identity", {}).get("version", ""),
                    "category": "",
                    "icon": "",
                    "content": "",
                    "capabilities": [],
                })
                seen_names.add(raw_name)

    # 格式 C: skills/ 目录下的 skill.json 文件（v3.1 推荐）
    if extract_dir:
        skills_dir = extract_dir / "skills"
        if skills_dir.is_dir():
            for skill_json_file in skills_dir.rglob("skill.json"):
                skill_dir = skill_json_file.parent
                raw_name = skill_dir.name
                if raw_name in seen_names:
                    continue
                try:
                    with open(skill_json_file, encoding="utf-8") as f:
                        skill_cfg = json.load(f)
                    identity = skill_cfg.get("identity", {})
                    content_cfg = skill_cfg.get("content", {})
                    content = ""
                    if content_cfg.get("source") == "file":
                        skill_md = skill_dir / content_cfg.get("file", "SKILL.md")
                        if skill_md.exists():
                            with open(skill_md, encoding="utf-8") as f:
                                content = f.read()
                    elif content_cfg.get("source") == "inline":
                        content = content_cfg.get("content", "")
                    skills.append({
                        "id": f"{agent_name}/{raw_name}" if agent_name else raw_name,
                        "original_name": raw_name,
                        "display_name": identity.get("display_name", raw_name),
                        "description": identity.get("description", ""),
                        "version": identity.get("version", ""),
                        "category": identity.get("category", ""),
                        "icon": identity.get("icon", ""),
                        "content": content,
                        "capabilities": skill_cfg.get("capabilities", []),
                    })
                    seen_names.add(raw_name)
                except (json.JSONDecodeError, OSError):
                    pass  # 解析失败则忽略

    # 向后兼容: v3.0 subagents 中 type: "skill" 的项（deprecated）
    for sa in metadata.get("subagents", []):
        if sa.get("type") != "skill":
            continue
        raw_name = sa.get("name", "")
        if not raw_name or raw_name in seen_names:
            continue
        skills.append({
            "id": f"{agent_name}/{raw_name}",
            "original_name": raw_name,
            "display_name": sa.get("display_name", raw_name),
            "description": sa.get("description", ""),
            "version": metadata.get("identity", {}).get("version", ""),
            "category": "",
            "icon": "",
            "content": "",
            "capabilities": [],
            "deprecated": True,  # 标记为 deprecated
        })
        seen_names.add(raw_name)

    return skills


def extract_mcp_info(metadata: dict, extract_dir: Path | None = None) -> list[dict]:
    """从 agent.json 和文件系统归一化提取 MCP 信息

    返回格式：
    [
        {
            "id": "agent-name/server-name",   # qualified id
            "original_name": "server-name",   # 原始 name
            "description": "...",
            "command": "npx",
            "args": ["-y", "package-name"],
            "package": "@scope/package",
            "tools": ["tool1", "tool2"],
            "required_env": ["ENV_VAR1", "ENV_VAR2"],
        }
    ]
    """
    agent_name = metadata.get("identity", {}).get("name", "")
    mcp_list = []

    # 格式 A1: agent.json 顶层 mcp_servers 数组（agent-builder 使用）
    for srv in metadata.get("mcp_servers", []):
        raw_name = srv.get("name", "")
        if not raw_name:
            continue
        env_dict = srv.get("env", {})
        required_env = list(env_dict.keys()) if isinstance(env_dict, dict) else []
        mcp_list.append({
            "id": f"{agent_name}/{raw_name}" if agent_name else raw_name,
            "original_name": raw_name,
            "description": srv.get("description", ""),
            "command": srv.get("command", ""),
            "args": srv.get("args", []),
            "package": srv.get("package", ""),
            "tools": srv.get("tools", []),
            "required_env": required_env,
        })

    seen_names = {m["original_name"] for m in mcp_list}

    # 格式 A2: mcp.required_servers（v3 规范）
    mcp_config = metadata.get("mcp", {})
    for srv in mcp_config.get("required_servers", []):
        raw_name = srv.get("name", "")
        if not raw_name or raw_name in seen_names:
            continue
        mcp_list.append({
            "id": f"{agent_name}/{raw_name}",
            "original_name": raw_name,
            "description": srv.get("description", ""),
            "command": "",
            "args": [],
            "package": srv.get("package", ""),
            "tools": srv.get("tools", []),
            "required_env": srv.get("required_env", []),
        })
        seen_names.add(raw_name)

    # 格式 B: mcp/config.json 文件（Runtime 文件系统加载，Claude Desktop 格式）
    if extract_dir:
        for cfg_name in ("config.json", "servers.json"):
            cfg_path = extract_dir / "mcp" / cfg_name
            if not cfg_path.is_file():
                continue
            try:
                with open(cfg_path, encoding="utf-8") as f:
                    mcp_cfg = json.load(f)
                for raw_name, srv_cfg in mcp_cfg.get("mcpServers", {}).items():
                    if raw_name in seen_names:
                        continue
                    env_dict = srv_cfg.get("env", {})
                    required_env = list(env_dict.keys()) if isinstance(env_dict, dict) else []
                    mcp_list.append({
                        "id": f"{agent_name}/{raw_name}",
                        "original_name": raw_name,
                        "description": srv_cfg.get("description", ""),
                        "command": srv_cfg.get("command", ""),
                        "args": srv_cfg.get("args", []),
                        "package": "",
                        "tools": [],
                        "required_env": required_env,
                    })
                    seen_names.add(raw_name)
            except (json.JSONDecodeError, OSError):
                pass  # 解析失败则忽略

    return mcp_list
