"""
市场服务 - 本地缓存管理
========================
管理本地 Agent 包的缓存、索引和安装状态。
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# ============================================================
# 默认路径
# ============================================================

DEFAULT_MARKET_DIR = Path.home() / ".pilotdeck" / "market"
DEFAULT_CACHE_DIR = DEFAULT_MARKET_DIR / "cache"
DEFAULT_INSTALLED_DIR = DEFAULT_MARKET_DIR / "installed"
DEFAULT_INDEX_FILE = DEFAULT_MARKET_DIR / "index.json"
DEFAULT_CONFIG_FILE = DEFAULT_MARKET_DIR / "config.json"

DEFAULT_CONFIG = {
    "server_url": "http://localhost:8321",
    "proxy": "",
    "max_cache_size_mb": 5120,
    "cache_ttl_hours": 168,
    "auto_update": False,
    "verify_on_install": True,
    "installed_dir": str(DEFAULT_INSTALLED_DIR),
    "cache_dir": str(DEFAULT_CACHE_DIR),
}


# ============================================================
# 目录管理
# ============================================================

def ensure_cache_dirs(market_dir: Path = None):
    """确保缓存目录结构存在

    创建:
    - ~/.pilotdeck/market/
    - ~/.pilotdeck/market/cache/
    - ~/.pilotdeck/market/installed/
    """
    market_dir = market_dir or DEFAULT_MARKET_DIR
    (market_dir / "cache").mkdir(parents=True, exist_ok=True)
    (market_dir / "installed").mkdir(parents=True, exist_ok=True)


# ============================================================
# 索引管理
# ============================================================

def load_index(index_path: str | Path = None) -> dict:
    """加载本地缓存索引

    返回:
        索引字典，如果文件不存在则返回默认结构
    """
    index_path = Path(index_path or DEFAULT_INDEX_FILE)
    if not index_path.exists():
        return {
            "version": 1,
            "last_sync": "",
            "server_url": "http://localhost:8321",
            "agents": {},
        }

    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_index(index: dict, index_path: str | Path = None):
    """保存本地缓存索引"""
    index_path = Path(index_path or DEFAULT_INDEX_FILE)
    index_path.parent.mkdir(parents=True, exist_ok=True)

    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, indent=2, ensure_ascii=False)


# ============================================================
# 配置管理
# ============================================================

def load_config(config_path: str | Path = None) -> dict:
    """加载市场配置"""
    config_path = Path(config_path or DEFAULT_CONFIG_FILE)
    if not config_path.exists():
        return dict(DEFAULT_CONFIG)

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    # 合并默认值
    merged = dict(DEFAULT_CONFIG)
    merged.update(config)
    return merged


def save_config(config: dict, config_path: str | Path = None):
    """保存市场配置"""
    config_path = Path(config_path or DEFAULT_CONFIG_FILE)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


# ============================================================
# 缓存操作
# ============================================================

def get_cached_agent(agent_id: str, cache_dir: str | Path = None) -> Path | None:
    """获取缓存的 Agent 目录路径

    参数:
        agent_id: Agent ID
        cache_dir: 缓存目录（默认 ~/.pilotdeck/market/cache）

    返回:
        如果已缓存则返回目录路径，否则返回 None
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    agent_cache_dir = cache_dir / agent_id

    if agent_cache_dir.exists() and (agent_cache_dir / "agent.json").exists():
        return agent_cache_dir
    return None


def store_to_cache(agent_id: str, pkg_path: str | Path,
                   cache_dir: str | Path = None) -> Path:
    """将解压后的 Agent 包存入缓存

    参数:
        agent_id: Agent ID
        pkg_path: 解压后的 Agent 目录路径
        cache_dir: 缓存目录

    返回:
        缓存中的 Agent 目录路径
    """
    from .package import unpack_agent

    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    target_dir = cache_dir / agent_id

    # 清理已存在的缓存
    if target_dir.exists():
        shutil.rmtree(target_dir)

    # 解包到缓存目录
    pkg_path = Path(pkg_path)
    if pkg_path.is_file():
        # 包文件，需要解压
        unpacked = unpack_agent(pkg_path, target_dir)
        # unpack_agent 可能在 target_dir 下创建了单层包装目录，需要展平
        if unpacked != target_dir and unpacked.is_dir():
            # 把嵌套目录里的内容移到 target_dir
            for item in unpacked.iterdir():
                shutil.move(str(item), str(target_dir / item.name))
            unpacked.rmdir()
    elif pkg_path.is_dir():
        # 已经是目录，直接复制
        shutil.copytree(pkg_path, target_dir)

    return target_dir


def remove_from_cache(agent_id: str, cache_dir: str | Path = None) -> bool:
    """从缓存中移除 Agent

    参数:
        agent_id: Agent ID
        cache_dir: 缓存目录

    返回:
        是否成功移除
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    agent_cache_dir = cache_dir / agent_id

    if agent_cache_dir.exists():
        shutil.rmtree(agent_cache_dir)
        return True
    return False


# ============================================================
# 安装管理
# ============================================================

def is_installed(agent_id: str, installed_dir: str | Path = None) -> bool:
    """检查 Agent 是否已安装"""
    installed_dir = Path(installed_dir or DEFAULT_INSTALLED_DIR)
    link_path = installed_dir / agent_id
    return link_path.exists() or link_path.is_symlink()


def install_agent(agent_id: str, cache_dir: str | Path = None,
                   installed_dir: str | Path = None) -> Path:
    """安装 Agent（创建符号链接）

    参数:
        agent_id: Agent ID
        cache_dir: 缓存目录
        installed_dir: 安装目录

    返回:
        安装后的路径
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    installed_dir = Path(installed_dir or DEFAULT_INSTALLED_DIR)

    cache_path = cache_dir / agent_id
    if not cache_path.exists():
        raise FileNotFoundError(f"Agent '{agent_id}' 未在缓存中找到")

    installed_path = installed_dir / agent_id

    # 移除旧的符号链接
    if installed_path.exists() or installed_path.is_symlink():
        installed_path.unlink()

    # 创建符号链接
    installed_path.symlink_to(cache_path, target_is_directory=True)
    return installed_path


def uninstall_agent(agent_id: str, installed_dir: str | Path = None) -> bool:
    """卸载 Agent（移除符号链接，保留缓存）

    参数:
        agent_id: Agent ID
        installed_dir: 安装目录

    返回:
        是否成功卸载
    """
    installed_dir = Path(installed_dir or DEFAULT_INSTALLED_DIR)
    installed_path = installed_dir / agent_id

    if installed_path.exists() or installed_path.is_symlink():
        installed_path.unlink()
        return True
    return False


# ============================================================
# 列表查询
# ============================================================

def list_cached_agents(cache_dir: str | Path = None) -> list[dict]:
    """列出缓存中的所有 Agent

    返回:
        Agent 信息列表
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    if not cache_dir.exists():
        return []

    agents = []
    for entry in cache_dir.iterdir():
        if entry.is_dir() and (entry / "agent.json").exists():
            try:
                with open(entry / "agent.json", "r", encoding="utf-8") as f:
                    config = json.load(f)
                agents.append({
                    "id": entry.name,
                    "name": config.get("identity", {}).get("name", entry.name),
                    "version": config.get("identity", {}).get("version", ""),
                    "description": config.get("identity", {}).get("description", ""),
                    "cached_at": datetime.fromtimestamp(
                        entry.stat().st_mtime
                    ).strftime("%Y-%m-%dT%H:%M:%SZ"),
                })
            except (json.JSONDecodeError, Exception):
                pass

    return agents


def list_installed_agents(installed_dir: str | Path = None) -> list[dict]:
    """列出已安装的 Agent

    返回:
        Agent 信息列表
    """
    installed_dir = Path(installed_dir or DEFAULT_INSTALLED_DIR)
    if not installed_dir.exists():
        return []

    agents = []
    for entry in installed_dir.iterdir():
        if entry.is_symlink() or entry.is_dir():
            agent_json = entry / "agent.json" if entry.is_dir() else \
                entry.resolve() / "agent.json" if entry.is_symlink() else None

            if agent_json and agent_json.exists():
                try:
                    with open(agent_json, "r", encoding="utf-8") as f:
                        config = json.load(f)
                    agents.append({
                        "id": entry.name,
                        "name": config.get("identity", {}).get("name", entry.name),
                        "version": config.get("identity", {}).get("version", ""),
                        "description": config.get("identity", {}).get("description", ""),
                        "path": str(entry.resolve()),
                    })
                except (json.JSONDecodeError, Exception):
                    pass
            else:
                agents.append({
                    "id": entry.name,
                    "name": entry.name,
                    "version": "",
                    "description": "",
                    "path": str(entry.resolve()),
                })

    return agents


# ============================================================
# 缓存清理
# ============================================================

def cache_size_info(cache_dir: str | Path = None) -> dict:
    """获取缓存大小信息

    返回:
        {"total_size_bytes": ..., "total_size_mb": ..., "agent_count": ...}
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    if not cache_dir.exists():
        return {"total_size_bytes": 0, "total_size_mb": 0, "agent_count": 0}

    total_size = 0
    agent_count = 0

    for entry in cache_dir.iterdir():
        if entry.is_dir():
            agent_count += 1
            for f in entry.rglob("*"):
                if f.is_file():
                    total_size += f.stat().st_size

    return {
        "total_size_bytes": total_size,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "agent_count": agent_count,
    }


def clean_cache(cache_dir: str | Path = None, max_age_days: int = 7,
                installed_dir: str | Path = None) -> int:
    """清理过期缓存（保留已安装的）

    参数:
        cache_dir: 缓存目录
        max_age_days: 最大缓存天数
        installed_dir: 安装目录

    返回:
        清理的 Agent 数量
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    installed_dir = Path(installed_dir or DEFAULT_INSTALLED_DIR)

    if not cache_dir.exists():
        return 0

    now = time.time()
    max_age_seconds = max_age_days * 24 * 3600
    cleaned = 0

    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue

        # 检查是否已安装
        if installed_dir and (installed_dir / entry.name).exists():
            continue

        # 检查是否过期
        mtime = entry.stat().st_mtime
        if now - mtime > max_age_seconds:
            shutil.rmtree(entry)
            cleaned += 1

    return cleaned


def clean_lru_cache(cache_dir: str | Path = None,
                    target_size_mb: int = 5120,
                    installed_dir: str | Path = None) -> int:
    """LRU 清理：当缓存超过目标大小时，清理最近最少使用的缓存

    参数:
        cache_dir: 缓存目录
        target_size_mb: 目标缓存大小上限（MB）
        installed_dir: 安装目录

    返回:
        清理的 Agent 数量
    """
    cache_dir = Path(cache_dir or DEFAULT_CACHE_DIR)
    installed_dir = Path(installed_dir or DEFAULT_INSTALLED_DIR)

    if not cache_dir.exists():
        return 0

    info = cache_size_info(cache_dir)
    if info["total_size_mb"] <= target_size_mb:
        return 0

    # 获取所有缓存目录及其 mtime 和大小
    agents = []
    for entry in cache_dir.iterdir():
        if not entry.is_dir():
            continue

        # 跳过已安装的
        if installed_dir and (installed_dir / entry.name).exists():
            continue

        size = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
        agents.append({
            "path": entry,
            "mtime": entry.stat().st_mtime,
            "size_mb": size / (1024 * 1024),
        })

    # 按 mtime 排序（最旧的在最前）
    agents.sort(key=lambda x: x["mtime"])

    cleaned = 0
    current_size_mb = info["total_size_mb"]

    for agent in agents:
        if current_size_mb <= target_size_mb:
            break
        shutil.rmtree(agent["path"])
        current_size_mb -= agent["size_mb"]
        cleaned += 1

    return cleaned