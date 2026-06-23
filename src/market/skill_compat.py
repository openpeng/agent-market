"""
市场服务 - SKILL.md 兼容包装
==============================
将旧格式的 SKILL.md 目录自动包装为市场兼容的 Agent 包格式。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


def wrap_skill_directory(skill_dir: str | Path) -> dict:
    """检测并包装旧 Skill 目录为市场兼容的 Agent 包配置

    当市场遇到旧格式的 SKILL.md 目录时:
    1. 自动调用 SkillAutoWrap.detect_and_wrap() 生成 agent.json
    2. 将生成的 agent.json 写入包中
    3. 原 SKILL.md 保留在包中作为文档
    4. 标记 is_wrapped: true 以便用户知晓

    参数:
        skill_dir: Skill 目录路径

    返回:
        自动生成的 agent.json 配置字典

    抛出:
        ValueError: 目录不是有效的 Skill 目录
    """
    skill_dir = Path(skill_dir)

    if not skill_dir.exists():
        raise ValueError(f"目录不存在: {skill_dir}")

    # 检测 SKILL.md
    skill_files = [
        skill_dir / "SKILL.md",
        skill_dir / "skill.yaml",
        skill_dir / "skill.json",
    ]
    skill_file = None
    for sf in skill_files:
        if sf.exists():
            skill_file = sf
            break

    if not skill_file:
        raise ValueError(
            f"'{skill_dir}' 不是有效的 Skill 目录（缺少 SKILL.md/skill.yaml/skill.json）"
        )

    # 使用现有的 SkillAutoWrap
    try:
        from agents.loader import SkillAutoWrap
        wrapped = SkillAutoWrap.detect_and_wrap(str(skill_dir))
    except ImportError:
        wrapped = _fallback_wrap(skill_dir, skill_file)

    if wrapped is None:
        raise ValueError(f"无法自动包装 Skill 目录: {skill_dir}")

    # 添加市场标记
    wrapped["is_wrapped"] = True

    # 尝试从 .market.yml 读取额外元数据
    market_yml = skill_dir / ".market.yml"
    if market_yml.exists():
        try:
            import yaml
            with open(market_yml, "r", encoding="utf-8") as f:
                market_meta = yaml.safe_load(f) or {}

            # 合并元数据
            if "display_name" in market_meta:
                wrapped["display_name"] = market_meta["display_name"]
            if "category" in market_meta:
                wrapped["category"] = market_meta["category"]
            if "tags" in market_meta:
                wrapped["tags"] = market_meta["tags"]
            if "homepage" in market_meta:
                wrapped["homepage_url"] = market_meta["homepage"]
            if "source" in market_meta:
                wrapped["source_url"] = market_meta["source"]
            if "license" in market_meta:
                wrapped["license"] = market_meta["license"]
        except Exception:
            pass  # .market.yml 解析失败则忽略

    # 写入 agent.json
    agent_json_path = skill_dir / "agent.json"
    with open(agent_json_path, "w", encoding="utf-8") as f:
        json.dump(wrapped, f, indent=2, ensure_ascii=False)

    return wrapped


def _fallback_wrap(skill_dir: Path, skill_file: Path) -> dict | None:
    """兜底的包装函数（SkillAutoWrap 不可用时）"""
    skill_name = skill_dir.name

    # 读取 Skill 描述
    description = ""
    try:
        content = skill_file.read_text(encoding="utf-8")
        for line in content.split("\n"):
            line = line.strip().strip("#").strip()
            if line:
                description = line[:100]
                break
    except Exception:
        description = skill_name

    if not description:
        description = skill_name

    # 生成 agent.json
    return {
        "identity": {
            "name": skill_name,
            "version": "1.0.0",
            "description": f"自动包装自Skill: {skill_name}",
            "author": "auto-wrap",
        },
        "entry": {
            "main_subagent": skill_name,
            "max_retries": 1,
        },
        "subagents": [
            {
                "name": skill_name,
                "path": skill_file.name,
                "description": description,
            }
        ],
        "is_wrapped": True,
    }


def is_skill_directory(path: str | Path) -> bool:
    """检查目录是否是 Skill 目录

    检测条件:
    - 目录下存在 SKILL.md 文件
    - 或目录下存在 skill.yaml / skill.json 文件
    - 且不存在 agent.json（避免重复包装）
    """
    path = Path(path)
    if not path.is_dir():
        return False

    # 已有 agent.json 则不是"旧" Skill 目录
    if (path / "agent.json").exists():
        return False

    return (
        (path / "SKILL.md").exists()
        or (path / "skill.yaml").exists()
        or (path / "skill.json").exists()
    )