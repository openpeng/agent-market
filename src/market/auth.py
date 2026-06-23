"""
市场服务 - API Key 认证
========================
提供 API Key 生成、验证和 FastAPI 依赖注入。
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Optional

from fastapi import Header, HTTPException, Depends
from .database import MarketDatabase


def generate_api_key() -> str:
    """生成新 API Key，格式: pd_mkt_xxxxxxxxxxxxxxxx"""
    random_bytes = secrets.token_hex(16)
    return f"pd_mkt_{random_bytes}"


def hash_api_key(key: str) -> str:
    """SHA-256 哈希 API Key，用于安全存储"""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def verify_api_key_hash(key: str, stored_hash: str) -> bool:
    """Constant-time 比较 API Key 哈希，防时序攻击"""
    computed = hash_api_key(key)
    return hmac.compare_digest(computed, stored_hash)


async def verify_api_key(
    authorization: str,
    db: MarketDatabase,
) -> dict | None:
    """验证 Authorization header 中的 API Key

    支持格式: Authorization: Bearer pd_mkt_xxxxxxxxxxxxxxxx
    返回 API Key 信息或 None
    """
    if not authorization:
        return None

    if not authorization.startswith("Bearer "):
        return None

    key = authorization[7:].strip()
    if not key:
        return None

    # Get all enabled keys and compare hashes (constant-time)
    key_hash = hash_api_key(key)
    all_keys = await db.get_all_enabled_api_keys()
    for key_info in all_keys:
        if hash_api_key(key) == key_info.get("key_hash", ""):
            # Double-check with constant-time comparison
            if hmac.compare_digest(key_hash, key_info.get("key_hash", "")):
                # Check expiration
                expires_at = key_info.get("expires_at")
                if expires_at:
                    from datetime import datetime, timezone
                    try:
                        expiry = datetime.fromisoformat(expires_at)
                        if datetime.now(timezone.utc) > expiry:
                            return None
                    except (ValueError, TypeError):
                        pass
                return key_info
    return None


async def require_publisher(
    authorization: str = Header(None),
) -> dict:
    """FastAPI 依赖注入：需要发布者或管理员权限"""
    # 这个 dep 在 server 中被调用时会被注入 db 实例
    # 返回一个占位符，实际在路由中处理
    return {"authorization": authorization}


async def require_admin(
    authorization: str = Header(None),
) -> dict:
    """FastAPI 依赖注入：需要管理员权限"""
    return {"authorization": authorization}


def make_api_key_dependency(db_provider):
    """创建带 db 实例的认证依赖

    用法:
        verify_publisher = make_api_key_dependency(lambda: db)
    """

    async def verify_publisher(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="缺少 Authorization header")

        db = db_provider()
        key_info = await verify_api_key(authorization, db)
        if key_info is None:
            raise HTTPException(status_code=401, detail="无效的 API Key")

        role = key_info.get("role", "publisher")
        if role not in ("publisher", "admin"):
            raise HTTPException(status_code=403, detail="权限不足，需要 publisher 或 admin 角色")

        return key_info

    return verify_publisher


def make_admin_key_dependency(db_provider):
    """创建带 db 实例的管理员认证依赖"""

    async def verify_admin(authorization: str = Header(None)):
        if not authorization:
            raise HTTPException(status_code=401, detail="缺少 Authorization header")

        db = db_provider()
        key_info = await verify_api_key(authorization, db)
        if key_info is None:
            raise HTTPException(status_code=401, detail="无效的 API Key")

        if key_info.get("role") != "admin":
            raise HTTPException(status_code=403, detail="权限不足，需要 admin 角色")

        return key_info

    return verify_admin