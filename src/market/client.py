"""市场服务 - MarketClient 客户端类"""
from __future__ import annotations

import json
import os
import tempfile
import datetime
from pathlib import Path

import httpx

from .cache import (
    ensure_cache_dirs, load_index, save_index, load_config,
    get_cached_agent, store_to_cache,
    is_installed, install_agent, uninstall_agent,
    list_cached_agents, list_installed_agents,
    cache_size_info, clean_cache,
    DEFAULT_CACHE_DIR, DEFAULT_INSTALLED_DIR,
)
from .package import pack_agent
from .verify import verify_package


class MarketClient:
    """市场客户端 - 负责与市场服务交互"""

    def __init__(self, server_url=None, api_key=None):
        config = load_config()
        self.server_url = (server_url or config.get("server_url", "http://localhost:8321")).rstrip("/")
        self.api_key = api_key or ""
        self.cache_dir = DEFAULT_CACHE_DIR
        self.installed_dir = DEFAULT_INSTALLED_DIR
        self.config = config
        ensure_cache_dirs()
        self._client = httpx.Client(base_url=self.server_url, timeout=30.0, follow_redirects=True)

    def _api_url(self, path):
        return f"{self.server_url}/api/v1{path}"

    def _headers(self):
        h = {"User-Agent": "PilotDeck-MarketClient/1.0"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def search(self, query="", **kwargs):
        params = {"q": query}
        for k in ("category", "type", "tags", "sort", "order", "page", "page_size"):
            if k in kwargs:
                params[k] = str(kwargs[k])
        r = self._client.get(self._api_url("/agents"), params=params, headers=self._headers())
        r.raise_for_status()
        return r.json().get("items", [])

    def get_agent(self, agent_id):
        r = self._client.get(self._api_url(f"/agents/{agent_id}"), headers=self._headers())
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def download(self, agent_id, version=None, target_dir=None):
        target_dir = Path(target_dir or self.cache_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
            r = self._client.get(self._api_url(f"/agents/{agent_id}/download"), headers=self._headers())
            r.raise_for_status()
            tmp.write(r.content)
            tmp_path = tmp.name
        try:
            return store_to_cache(agent_id, tmp_path, target_dir)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def publish(self, pkg_dir, force=False):
        pkg_dir = Path(pkg_dir)
        if pkg_dir.is_dir():
            with tempfile.NamedTemporaryFile(delete=False, suffix=".tar.gz") as tmp:
                tmp_path = tmp.name
            try:
                pack_agent(pkg_dir, tmp_path)
                pkg_path = tmp_path
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise
        else:
            pkg_path = str(pkg_dir)
        try:
            with open(pkg_path, "rb") as f:
                files = {"file": (os.path.basename(pkg_path), f, "application/gzip")}
                data = {"force": "true" if force else "false"}
                r = self._client.post(self._api_url("/agents"), files=files, data=data, headers=self._headers())
                r.raise_for_status()
                return r.json()
        finally:
            if pkg_path != str(pkg_dir):
                os.unlink(pkg_path)

    def api_health(self):
        r = self._client.get(self._api_url("/health"), headers=self._headers())
        r.raise_for_status()
        return r.json()

    def ensure_installed(self, agent_id, version=None):
        if is_installed(agent_id, self.installed_dir):
            return self.installed_dir / agent_id
        cached = get_cached_agent(agent_id, self.cache_dir)
        if cached is None:
            cached = self.download(agent_id, version)
        install_agent(agent_id, self.cache_dir, self.installed_dir)
        self._update_index(agent_id, version)
        return self.installed_dir / agent_id

    def install(self, agent_id, version=None, output_dir=None, verify=False):
        cache_dir = self.cache_dir
        installed_dir = Path(output_dir) if output_dir else self.installed_dir
        info = self.get_agent(agent_id)
        if info is None:
            raise ValueError(f"市场未找到 Agent '{agent_id}'")
        cached = self.download(agent_id, version, cache_dir)
        install_agent(agent_id, cache_dir, installed_dir)
        if verify:
            valid, errors = verify_package(cached)
            if not valid:
                raise ValueError(f"Agent '{agent_id}' 验证失败:\n"+"\n".join(f"  - {e}" for e in errors))
        self._update_index(agent_id, version or info.get("version"))
        return installed_dir / agent_id

    def uninstall(self, agent_id):
        ok = uninstall_agent(agent_id, self.installed_dir)
        if ok:
            idx = load_index()
            if agent_id in idx.get("agents", {}):
                idx["agents"][agent_id]["installed"] = False
            save_index(idx)
        return ok

    def list_installed(self):
        return list_installed_agents(self.installed_dir)

    def list_cached(self):
        return list_cached_agents(self.cache_dir)

    def check_updates(self, agent_id=None):
        idx = load_index()
        agents = idx.get("agents", {})
        results = {}
        if agent_id:
            if agent_id not in agents:
                return {agent_id: {"error": "未安装"}}
            info = self.get_agent(agent_id)
            if info:
                cur, lat = agents[agent_id].get("version", ""), info.get("version", "")
                results[agent_id] = {"has_update": cur != lat and cur != "", "current": cur, "latest": lat}
            else:
                results[agent_id] = {"has_update": False, "current": agents[agent_id].get("version", ""), "latest": ""}
        else:
            for aid, info in agents.items():
                if info.get("installed"):
                    ag = self.get_agent(aid)
                    if ag:
                        cur, lat = info.get("version", ""), ag.get("version", "")
                        results[aid] = {"has_update": cur != lat and cur != "", "current": cur, "latest": lat}
        return results

    def cache_info(self):
        return cache_size_info(self.cache_dir)

    def clean_cache(self, max_age_days=7):
        return clean_cache(self.cache_dir, max_age_days, self.installed_dir)

    def resync(self):
        """重新同步所有 Agent 的 skills 和 MCP 数据（需要 admin 权限）"""
        r = self._client.post(self._api_url("/agents/resync"), headers=self._headers())
        r.raise_for_status()
        return r.json()

    def _update_index(self, agent_id, version=None):
        idx = load_index()
        if "agents" not in idx:
            idx["agents"] = {}
        now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        if agent_id not in idx["agents"]:
            idx["agents"][agent_id] = {}
        idx["agents"][agent_id].update({"id": agent_id, "version": version or "", "installed": True, "cached": True, "installed_at": now, "last_checked": now})
        idx["last_sync"] = now
        save_index(idx)

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()