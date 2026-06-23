"""市场服务 - 速率限制中间件"""
from __future__ import annotations

import time
from collections import defaultdict
from fastapi import HTTPException, Request


class RateLimiter:
    """简单的内存速率限制器"""

    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def check(self, key: str) -> bool:
        """检查是否允许请求。返回 True=允许, False=超限"""
        now = time.time()
        bucket = self._buckets[key]

        # 清理过期记录
        cutoff = now - self.window_seconds
        self._buckets[key] = [t for t in bucket if t > cutoff]

        if len(self._buckets[key]) >= self.max_requests:
            return False

        self._buckets[key].append(now)
        return True

    def remaining(self, key: str) -> int:
        """返回剩余可用请求数"""
        now = time.time()
        bucket = self._buckets[key]
        cutoff = now - self.window_seconds
        active = len([t for t in bucket if t > cutoff])
        return max(0, self.max_requests - active)


# 全局限流器实例
_upload_limiter = RateLimiter(max_requests=20, window_seconds=3600)    # 20/hour
_download_limiter = RateLimiter(max_requests=100, window_seconds=60)  # 100/minute
_key_create_limiter = RateLimiter(max_requests=5, window_seconds=3600)  # 5/hour


async def check_upload_rate(request: Request, publisher: str):
    """检查上传速率限制"""
    if not _upload_limiter.check(f"upload:{publisher}"):
        raise HTTPException(
            status_code=429,
            detail=f"上传频率超限 (最大 {_upload_limiter.max_requests} 次/小时)，请稍后再试",
            headers={"Retry-After": str(_upload_limiter.window_seconds)}
        )


async def check_download_rate(client_ip: str):
    """检查下载速率限制"""
    if not _download_limiter.check(f"download:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail=f"下载频率超限 (最大 {_download_limiter.max_requests} 次/分钟)，请稍后再试",
            headers={"Retry-After": str(_download_limiter.window_seconds)}
        )


async def check_key_create_rate(client_ip: str):
    """检查 API Key 创建速率限制"""
    if not _key_create_limiter.check(f"keycreate:{client_ip}"):
        raise HTTPException(
            status_code=429,
            detail=f"API Key 创建频率超限 (最大 {_key_create_limiter.max_requests} 次/小时)，请稍后再试",
            headers={"Retry-After": str(_key_create_limiter.window_seconds)}
        )
