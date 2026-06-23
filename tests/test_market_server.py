"""市场服务 - 服务端 API 测试"""
from __future__ import annotations

import json
import os
import tarfile
import io
import asyncio
import pytest
from fastapi.testclient import TestClient

os.environ["MARKET_MASTER_KEY"] = "test-master-key"
from market.server import app
from market.database import MarketDatabase

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    db_path = "./data/test_market.db"
    if os.path.exists(db_path):
        os.unlink(db_path)
    import market.server as sm
    db = MarketDatabase(db_path)
    asyncio.run(db.connect())
    asyncio.run(db.initialize())
    sm._db = db
    os.makedirs(sm._packages_dir, exist_ok=True)
    yield
    asyncio.run(db.close())
    if os.path.exists(db_path):
        os.unlink(db_path)


def create_test_package():
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        agent = json.dumps({
            "identity": {"name": "test-agent", "version": "1.0.0", "description": "test", "author": "test"},
            "entry": {"main_subagent": "worker", "max_retries": 2},
            "subagents": [{"name": "worker", "path": "worker.yaml"}],
        })
        info = tarfile.TarInfo(name="agent.json")
        info.size = len(agent.encode())
        tar.addfile(info, io.BytesIO(agent.encode()))
        worker = "name: worker\ntools:\n  - name: bash\n    type: builtin\npipeline:\n  - step: echo\n    tool: bash\n    args:\n      command: echo hello\n"
        info2 = tarfile.TarInfo(name="worker.yaml")
        info2.size = len(worker.encode())
        tar.addfile(info2, io.BytesIO(worker.encode()))
    return buf.getvalue()


def test_health():
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    assert r.status_code == 201
    key = r.json()["key"]
    data = create_test_package()
    r = client.post("/api/v1/agents", files={"file":("test.tar.gz",data,"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    assert r.status_code == 201
    assert r.json()["id"] == "test-agent"


def test_register_no_auth():
    data = create_test_package()
    r = client.post("/api/v1/agents", files={"file":("test.tar.gz",data,"application/gzip")}, data={"force":"false"})
    assert r.status_code == 401


def test_get_agent():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    key = r.json()["key"]
    client.post("/api/v1/agents", files={"file":("test.tar.gz",create_test_package(),"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    r = client.get("/api/v1/agents/test-agent")
    assert r.status_code == 200
    assert r.json()["id"] == "test-agent"


def test_get_agent_not_found():
    r = client.get("/api/v1/agents/nonexist")
    assert r.status_code == 404


def test_search():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    key = r.json()["key"]
    client.post("/api/v1/agents", files={"file":("test.tar.gz",create_test_package(),"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    r = client.get("/api/v1/agents")
    assert r.status_code == 200
    assert r.json()["total"] >= 1


def test_download():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    key = r.json()["key"]
    client.post("/api/v1/agents", files={"file":("test.tar.gz",create_test_package(),"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    r = client.get("/api/v1/agents/test-agent/download")
    assert r.status_code == 200
    assert "Content-Disposition" in r.headers


def test_ratings():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    key = r.json()["key"]
    client.post("/api/v1/agents", files={"file":("test.tar.gz",create_test_package(),"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    r = client.post("/api/v1/agents/test-agent/ratings", json={"score":5,"comment":"Great!"}, headers={"Authorization":f"Bearer {key}"})
    assert r.status_code == 201
    r = client.get("/api/v1/agents/test-agent/ratings")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert r.json()["average"] == 5.0


def test_delete():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    key = r.json()["key"]
    client.post("/api/v1/agents", files={"file":("test.tar.gz",create_test_package(),"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    r = client.delete("/api/v1/agents/test-agent", headers={"Authorization":f"Bearer {key}"})
    assert r.status_code == 204
    r = client.get("/api/v1/agents/test-agent")
    assert r.status_code == 404


def test_batch():
    r = client.post("/api/v1/api-keys", json={"owner":"tester","role":"admin"}, headers={"Authorization":"Bearer test-master-key"})
    key = r.json()["key"]
    client.post("/api/v1/agents", files={"file":("test.tar.gz",create_test_package(),"application/gzip")}, data={"force":"false"}, headers={"Authorization":f"Bearer {key}"})
    r = client.get("/api/v1/agents/batch?ids=test-agent,nonexist")
    assert r.status_code == 200
    data = r.json()["agents"]
    assert data["test-agent"] is not None
    assert data["nonexist"] is None