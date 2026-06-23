"""市场服务 - 客户端测试"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from market.client import MarketClient
from market.cache import load_index, save_index


def test_client_init():
    c = MarketClient(server_url="http://localhost:9999", api_key="my-key")
    assert c.server_url == "http://localhost:9999"
    assert c.api_key == "my-key"


def test_search():
    c = MarketClient()
    with patch.object(c._client, 'get') as mock:
        resp = MagicMock()
        resp.json.return_value = {"total": 1, "items": [{"id": "a1", "display_name": "Agent 1", "version": "1.0.0"}]}
        resp.status_code = 200
        mock.return_value = resp
        results = c.search("test")
        assert len(results) == 1
        assert results[0]["id"] == "a1"


def test_get_agent():
    c = MarketClient()
    with patch.object(c._client, 'get') as mock:
        resp = MagicMock()
        resp.json.return_value = {"id": "test-agent", "name": "test-agent", "version": "1.0.0"}
        resp.status_code = 200
        mock.return_value = resp
        agent = c.get_agent("test-agent")
        assert agent["id"] == "test-agent"


def test_get_agent_not_found():
    c = MarketClient()
    with patch.object(c._client, 'get') as mock:
        resp = MagicMock()
        resp.status_code = 404
        mock.return_value = resp
        assert c.get_agent("nonexist") is None


def test_health():
    c = MarketClient()
    with patch.object(c._client, 'get') as mock:
        resp = MagicMock()
        resp.json.return_value = {"status": "ok", "version": "1.0.0", "agents_count": 5, "uptime": 100}
        resp.status_code = 200
        mock.return_value = resp
        h = c.api_health()
        assert h["status"] == "ok"


def test_publish():
    c = MarketClient()
    with patch.object(c._client, 'post') as mock:
        resp = MagicMock()
        resp.json.return_value = {"id": "test-agent", "name": "test-agent", "version": "1.0.0", "package_size": 1024}
        resp.status_code = 201
        mock.return_value = resp
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "test-agent"
            d.mkdir()
            with open(d / "agent.json", "w") as f:
                json.dump({"identity": {"name": "test-agent", "version": "1.0.0"}, "entry": {"main_subagent": "w"}, "subagents": [{"name": "w", "path": "w.yaml"}]}, f)
            with open(d / "w.yaml", "w") as f:
                f.write("name: w\n")
            result = c.publish(str(d), force=True)
            assert result["id"] == "test-agent"


def test_index():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "idx.json"
        save_index({"version": 1, "agents": {"a": {"id": "a", "version": "1.0.0", "installed": True}}}, p)
        idx = load_index(p)
        assert idx["version"] == 1
        assert "a" in idx["agents"]
