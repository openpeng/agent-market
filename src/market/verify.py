"""市场服务 - Agent 包安全与完整性验证"""
from __future__ import annotations

import json
import hashlib
import re
import tarfile
from pathlib import Path

MAX_PACKAGE_SIZE = 50 * 1024 * 1024  # 50MB hard limit
MIN_INSTRUCTIONS_LENGTH = 50  # Minimum character count for instructions


def verify_package(pkg_path: Path):
    """
    全面验证 Agent 包的安全性和完整性。

    返回 (is_valid: bool, errors: list[str])
    """
    errors = []

    # ---- Size check ----
    total = sum(f.stat().st_size for f in pkg_path.rglob("*") if f.is_file())
    if total > MAX_PACKAGE_SIZE:
        errors.append(f"包体积过大: {total/1024/1024:.1f}MB (最大 {MAX_PACKAGE_SIZE/1024/1024:.0f}MB)")

    # ---- agent.json existence + parse ----
    agent_json = pkg_path / "agent.json"
    if not agent_json.exists():
        errors.append("缺少必需文件: agent.json")
        return False, errors

    try:
        with open(agent_json, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"agent.json 格式错误: {e}")
        return False, errors

    # ---- Required fields ----
    identity = config.get("identity", {})
    if not identity.get("name"):
        errors.append("agent.json 缺少 identity.name")
    if not identity.get("version"):
        errors.append("agent.json 缺少 identity.version")
    if not identity.get("description"):
        errors.append("agent.json 缺少 identity.description")
    if not identity.get("author"):
        errors.append("agent.json 缺少 identity.author")

    # ---- Instructions quality check ----
    schema = config.get("schema_version", "2.0")
    if schema == "2.0":
        instructions = config.get("instructions", "")
        if isinstance(instructions, dict):
            content = instructions.get("content", "")
            content_len = len(content) if content else 0
        elif isinstance(instructions, str):
            content_len = len(instructions)
        else:
            content_len = 0
        if content_len < MIN_INSTRUCTIONS_LENGTH:
            errors.append(f"agent.json 指令内容过短 ({content_len} 字符，要求 >= {MIN_INSTRUCTIONS_LENGTH})")

    # ---- Entry + subagent reference integrity ----
    if config.get("entry", {}).get("main_subagent"):
        main = config["entry"]["main_subagent"]
        subagent_names = [sa.get("name") for sa in config.get("subagents", [])]
        if main not in subagent_names:
            errors.append(f"entry.main_subagent '{main}' 不在 subagents 中: {subagent_names}")

        for sa in config.get("subagents", []):
            p = sa.get("path", "")
            if p and not (pkg_path / p).exists():
                errors.append(f"子Agent文件不存在: {p}")

    # ---- Skills 校验 ----
    skills = config.get("skills", [])
    for i, skill in enumerate(skills):
        if not skill.get("name"):
            errors.append(f"skills[{i}] 缺少 name")
        elif not re.match(r'^[a-zA-Z0-9_\-]+$', skill.get("name", "")):
            errors.append(f"skills[{i}].name 格式无效: {skill['name']}（仅允许字母数字下划线连字符）")

    # ---- MCP Servers 校验 (agent.json 中的声明式配置) ----
    mcp_config = config.get("mcp", {})
    mcp_servers = config.get("mcp_servers", [])
    all_mcp = list(mcp_config.get("required_servers", []) or []) + list(mcp_servers)
    mcp_names = []
    for i, srv in enumerate(all_mcp):
        if not srv.get("name"):
            errors.append(f"mcp_servers[{i}] 缺少 name")
        else:
            if srv["name"] in mcp_names:
                errors.append(f"mcp_servers 名称重复: {srv['name']}")
            mcp_names.append(srv["name"])

    # ---- mcp/config.json 校验 (文件系统中的 MCP 配置) ----
    mcp_config_file = pkg_path / "mcp" / "config.json"
    if mcp_config_file.exists():
        try:
            mcp_cfg = json.loads(mcp_config_file.read_text(encoding="utf-8"))
            servers = mcp_cfg.get("mcpServers", {})
            if not isinstance(servers, dict):
                errors.append("mcp/config.json: mcpServers 应为对象")
            else:
                for name, srv in servers.items():
                    if not isinstance(srv, dict):
                        errors.append(f"mcp/config.json 中 server '{name}' 格式无效")
                    elif not srv.get("command"):
                        errors.append(f"mcp/config.json 中 server '{name}' 缺少 command")
        except json.JSONDecodeError:
            errors.append("mcp/config.json 不是有效的 JSON")

    return len(errors) == 0, errors


def _resolve_pkg_root(pkg_path: Path) -> Path:
    """如果 pkg_path 下只有一个子目录，返回该子目录；否则返回 pkg_path 本身。
    用于处理 tar.gz 包顶层带目录的情况。"""
    if pkg_path.is_dir():
        subdirs = [d for d in pkg_path.iterdir() if d.is_dir()]
        if len(subdirs) == 1 and not any(f.is_file() for f in pkg_path.iterdir()):
            return subdirs[0]
    return pkg_path


def verify_skill_package(pkg_path: Path):
    """
    验证 Skill 包的安全性和完整性（v3.1 新增）。

    返回 (is_valid: bool, errors: list[str])
    """
    errors = []
    MAX_SKILL_SIZE = 10 * 1024 * 1024  # 10MB

    # 处理 tar.gz 包顶层带目录的情况
    pkg_path = _resolve_pkg_root(pkg_path)

    # ---- Size check ----
    total = sum(f.stat().st_size for f in pkg_path.rglob("*") if f.is_file())
    if total > MAX_SKILL_SIZE:
        errors.append(f"Skill 包体积过大: {total/1024/1024:.1f}MB (最大 {MAX_SKILL_SIZE/1024/1024:.0f}MB)")

    # ---- skill.json existence + parse ----
    skill_json = pkg_path / "skill.json"
    if not skill_json.exists():
        errors.append("缺少必需文件: skill.json")
        return False, errors

    try:
        with open(skill_json, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"skill.json 格式错误: {e}")
        return False, errors

    # ---- Required fields ----
    identity = config.get("identity", {})
    if not identity.get("name"):
        errors.append("skill.json 缺少 identity.name")
    if not identity.get("version"):
        errors.append("skill.json 缺少 identity.version")

    # ---- Content check ----
    content_cfg = config.get("content", {})
    if content_cfg.get("source") == "file":
        skill_file = content_cfg.get("file", "SKILL.md")
        skill_md = pkg_path / skill_file
        if not skill_md.exists():
            errors.append(f"SKILL.md 文件不存在: {skill_file}")

    # ---- Scripts check (optional) ----
    scripts_dir = pkg_path / "scripts"
    if scripts_dir.exists():
        for script in scripts_dir.iterdir():
            if script.is_file() and not script.stat().st_mode & 0o111:
                errors.append(f"脚本文件不可执行: {script.name}")

    return len(errors) == 0, errors


def verify_mcp_package(pkg_path: Path):
    """
    验证 MCP Server 包的安全性和完整性（v3.1 新增）。

    返回 (is_valid: bool, errors: list[str])
    """
    errors = []
    MAX_MCP_SIZE = 10 * 1024 * 1024  # 10MB

    # 处理 tar.gz 包顶层带目录的情况
    pkg_path = _resolve_pkg_root(pkg_path)

    # ---- Size check ----
    total = sum(f.stat().st_size for f in pkg_path.rglob("*") if f.is_file())
    if total > MAX_MCP_SIZE:
        errors.append(f"MCP Server 包体积过大: {total/1024/1024:.1f}MB (最大 {MAX_MCP_SIZE/1024/1024:.0f}MB)")

    # ---- mcp-server.json existence + parse ----
    mcp_json = pkg_path / "mcp-server.json"
    if not mcp_json.exists():
        errors.append("缺少必需文件: mcp-server.json")
        return False, errors

    try:
        with open(mcp_json, encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as e:
        errors.append(f"mcp-server.json 格式错误: {e}")
        return False, errors

    # ---- Required fields ----
    identity = config.get("identity", {})
    if not identity.get("name"):
        errors.append("mcp-server.json 缺少 identity.name")
    if not identity.get("version"):
        errors.append("mcp-server.json 缺少 identity.version")

    # ---- mcp-config.json check ----
    config_cfg = config.get("config", {})
    if config_cfg.get("source") == "file":
        config_file = config_cfg.get("file", "mcp-config.json")
        mcp_config = pkg_path / config_file
        if not mcp_config.exists():
            errors.append(f"mcp-config.json 文件不存在: {config_file}")
        else:
            try:
                with open(mcp_config, encoding="utf-8") as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                errors.append(f"mcp-config.json 格式错误: {e}")

    return len(errors) == 0, errors


def verify_tar_safety(tar_path: Path):
    """
    Tar.gz 包安全性检查 — 路径遍历、符号链接、大文件。

    返回 (is_safe: bool, errors: list[str])
    """
    errors = []
    total_size = 0

    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                # Path traversal check
                name = member.name
                if name.startswith("/") or ".." in name.split("/"):
                    errors.append(f"禁止的路径: {name}")

                # Symlink check
                if member.issym() or member.islnk():
                    errors.append(f"禁止的符号链接: {name}")

                total_size += member.size
    except tarfile.TarError as e:
        errors.append(f"Tar 包解析错误: {e}")
    except Exception as e:
        errors.append(f"包读取错误: {e}")

    if total_size > MAX_PACKAGE_SIZE:
        errors.append(f"压缩包解压后体积过大: {total_size/1024/1024:.1f}MB")

    return len(errors) == 0, errors


def compute_sha256(file_path: Path) -> str:
    """计算文件的 SHA-256 哈希"""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()
