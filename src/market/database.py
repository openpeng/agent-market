"""
市场服务 - SQLite 数据库层
===========================
异步 SQLite 数据库管理，提供完整的 CRUD 操作。
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import aiosqlite


class MarketDatabase:
    """市场数据库管理器"""

    def __init__(self, db_path: str = "./data/market/market.db"):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")

    async def close(self):
        if self._conn:
            await self._conn.close()
            self._conn = None

    async def initialize(self):
        if not self._conn:
            await self.connect()
        await self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS agents (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, display_name TEXT NOT NULL,
                version TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '', category TEXT NOT NULL DEFAULT 'general',
                type TEXT NOT NULL DEFAULT 'agent', tags TEXT NOT NULL DEFAULT '[]',
                package_path TEXT NOT NULL DEFAULT '', package_size INTEGER NOT NULL DEFAULT 0,
                package_format TEXT NOT NULL DEFAULT 'tar.gz',
                package_sha256 TEXT NOT NULL DEFAULT '',
                json_content TEXT NOT NULL DEFAULT '{}',
                download_count INTEGER NOT NULL DEFAULT 0, rating REAL NOT NULL DEFAULT 0.0,
                review_count INTEGER NOT NULL DEFAULT 0, dependencies TEXT NOT NULL DEFAULT '{}',
                homepage_url TEXT NOT NULL DEFAULT '', source_url TEXT NOT NULL DEFAULT '',
                license TEXT NOT NULL DEFAULT 'MIT', readme TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                deprecated_at TEXT,
                deprecation_message TEXT NOT NULL DEFAULT '',
                replaced_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')), published_at TEXT
            );
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                user_id TEXT NOT NULL, score INTEGER NOT NULL CHECK(score>=1 AND score<=5),
                comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(agent_id, user_id)
            );
            CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                client_ip TEXT NOT NULL DEFAULT '', user_agent TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key_hash TEXT NOT NULL,
                owner TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'publisher',
                enabled INTEGER NOT NULL DEFAULT 1,
                expires_at TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_agents_name ON agents(name);
            CREATE INDEX IF NOT EXISTS idx_agents_category ON agents(category);
            CREATE INDEX IF NOT EXISTS idx_agents_rating ON agents(rating);
            CREATE INDEX IF NOT EXISTS idx_agents_download_count ON agents(download_count);
            CREATE INDEX IF NOT EXISTS idx_agents_created_at ON agents(created_at);
            CREATE TABLE IF NOT EXISTS skills (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '',
                icon TEXT NOT NULL DEFAULT '',
                package_path TEXT DEFAULT '',
                package_size INTEGER DEFAULT 0,
                package_format TEXT DEFAULT 'tar.gz',
                content_format TEXT DEFAULT 'markdown',
                content_source TEXT DEFAULT 'inline',
                content TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS mcp_servers (
                id TEXT PRIMARY KEY,
                original_name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '',
                command TEXT NOT NULL DEFAULT '',
                args TEXT NOT NULL DEFAULT '[]',
                package TEXT NOT NULL DEFAULT '',
                tools TEXT NOT NULL DEFAULT '[]',
                required_env TEXT NOT NULL DEFAULT '[]',
                package_path TEXT DEFAULT '',
                package_size INTEGER DEFAULT 0,
                package_format TEXT DEFAULT 'tar.gz',
                config_content TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS agent_skills (
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                skill_id TEXT NOT NULL REFERENCES skills(id) ON DELETE CASCADE,
                PRIMARY KEY (agent_id, skill_id)
            );
            CREATE TABLE IF NOT EXISTS agent_mcp_servers (
                agent_id TEXT NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
                mcp_server_id TEXT NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
                PRIMARY KEY (agent_id, mcp_server_id)
            );
            CREATE INDEX IF NOT EXISTS idx_skills_original_name ON skills(original_name);
            CREATE INDEX IF NOT EXISTS idx_mcp_servers_original_name ON mcp_servers(original_name);
            CREATE INDEX IF NOT EXISTS idx_agent_skills_skill_id ON agent_skills(skill_id);
            CREATE INDEX IF NOT EXISTS idx_agent_mcp_servers_server_id ON agent_mcp_servers(mcp_server_id);

            -- ─── Schema migrations ───
            # Ensure config_content column exists on mcp_servers (added in v1.1)
            cursor = await self._conn.execute("PRAGMA table_info(mcp_servers)")
            existing_cols = {row[1] for row in await cursor.fetchall()}
            if "config_content" not in existing_cols:
                await self._conn.execute("ALTER TABLE mcp_servers ADD COLUMN config_content TEXT DEFAULT ''")
            if "package_format" not in existing_cols:
                await self._conn.execute("ALTER TABLE mcp_servers ADD COLUMN package_format TEXT DEFAULT 'tar.gz'")

            -- ─── Teams 表 ───
            CREATE TABLE IF NOT EXISTS teams (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                version TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                type TEXT NOT NULL DEFAULT 'team',
                tags TEXT NOT NULL DEFAULT '[]',
                package_path TEXT NOT NULL DEFAULT '',
                package_size INTEGER NOT NULL DEFAULT 0,
                package_format TEXT NOT NULL DEFAULT 'tar.gz',
                package_sha256 TEXT NOT NULL DEFAULT '',
                json_content TEXT NOT NULL DEFAULT '{}',
                download_count INTEGER NOT NULL DEFAULT 0,
                rating REAL NOT NULL DEFAULT 0.0,
                review_count INTEGER NOT NULL DEFAULT 0,
                dependencies TEXT NOT NULL DEFAULT '{}',
                homepage_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                license TEXT NOT NULL DEFAULT 'MIT',
                readme TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                deprecated_at TEXT,
                deprecation_message TEXT NOT NULL DEFAULT '',
                replaced_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                published_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_teams_name ON teams(name);
            CREATE INDEX IF NOT EXISTS idx_teams_category ON teams(category);
            CREATE INDEX IF NOT EXISTS idx_teams_rating ON teams(rating);
            CREATE INDEX IF NOT EXISTS idx_teams_download_count ON teams(download_count);

            -- ─── Workflows 表 ───
            CREATE TABLE IF NOT EXISTS workflows (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                version TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT 'general',
                type TEXT NOT NULL DEFAULT 'workflow',
                tags TEXT NOT NULL DEFAULT '[]',
                package_path TEXT NOT NULL DEFAULT '',
                package_size INTEGER NOT NULL DEFAULT 0,
                package_format TEXT NOT NULL DEFAULT 'tar.gz',
                package_sha256 TEXT NOT NULL DEFAULT '',
                json_content TEXT NOT NULL DEFAULT '{}',
                download_count INTEGER NOT NULL DEFAULT 0,
                rating REAL NOT NULL DEFAULT 0.0,
                review_count INTEGER NOT NULL DEFAULT 0,
                dependencies TEXT NOT NULL DEFAULT '{}',
                homepage_url TEXT NOT NULL DEFAULT '',
                source_url TEXT NOT NULL DEFAULT '',
                license TEXT NOT NULL DEFAULT 'MIT',
                readme TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'active',
                deprecated_at TEXT,
                deprecation_message TEXT NOT NULL DEFAULT '',
                replaced_by TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                published_at TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_workflows_name ON workflows(name);
            CREATE INDEX IF NOT EXISTS idx_workflows_category ON workflows(category);
            CREATE INDEX IF NOT EXISTS idx_workflows_rating ON workflows(rating);
            CREATE INDEX IF NOT EXISTS idx_workflows_download_count ON workflows(download_count);

            -- ─── 版本历史表（Agent/Team/Workflow 共用） ───
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entity_type TEXT NOT NULL CHECK(entity_type IN ('agent', 'team', 'workflow')),
                entity_id TEXT NOT NULL,
                version TEXT NOT NULL,
                changelog TEXT NOT NULL DEFAULT '',
                package_path TEXT NOT NULL DEFAULT '',
                package_size INTEGER NOT NULL DEFAULT 0,
                package_format TEXT NOT NULL DEFAULT 'tar.gz',
                package_sha256 TEXT NOT NULL DEFAULT '',
                author TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE(entity_type, entity_id, version)
            );
            CREATE INDEX IF NOT EXISTS idx_versions_entity ON versions(entity_type, entity_id);
            CREATE INDEX IF NOT EXISTS idx_versions_entity_version ON versions(entity_type, entity_id, version);
        """)
        await self._conn.commit()

    async def insert_agent(self, data: dict) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)
        deps = data.get("dependencies", "{}")
        if isinstance(deps, dict):
            deps = json.dumps(deps, ensure_ascii=False)
        await self._conn.execute(
            "INSERT INTO agents (id,name,display_name,version,description,author,category,type,tags,package_path,package_size,package_format,json_content,dependencies,homepage_url,source_url,license,readme,created_at,updated_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data["id"], data["name"], data.get("display_name", data["name"]), data["version"],
             data.get("description", ""), data.get("author", ""), data.get("category", "general"),
             data.get("type", "agent"), tags_json, data.get("package_path", ""),
             data.get("package_size", 0), data.get("package_format", "tar.gz"),
             data.get("json_content", "{}"), deps, data.get("homepage_url", ""),
             data.get("source_url", ""), data.get("license", "MIT"), data.get("readme", ""),
             now, now, now)
        )
        await self._conn.commit()
        return data["id"]

    async def get_agent(self, agent_id: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        try:
            d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else {}
        except (json.JSONDecodeError, TypeError):
            d["dependencies"] = {}
        return d

    async def update_agent(self, agent_id: str, data: dict) -> bool:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        fields, values = [], []
        for key in ("description","display_name","category","type","package_path","package_size","package_format","homepage_url","source_url","license","readme","author","version"):
            if key in data:
                fields.append(f"{key}=?")
                values.append(data[key])
        if "tags" in data:
            fields.append("tags=?")
            values.append(json.dumps(data["tags"], ensure_ascii=False))
        if not fields:
            return False
        fields.append("updated_at=?")
        values.append(now)
        values.append(agent_id)
        await self._conn.execute(f"UPDATE agents SET {','.join(fields)} WHERE id=?", values)
        await self._conn.commit()
        return True

    async def delete_agent(self, agent_id: str) -> bool:
        cursor = await self._conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_agents(self, q="", category="", agent_type="", tags=None, sort="downloads", order="desc", page=1, page_size=20, skill=None, mcp=None):
        conditions, params = [], []
        if q:
            conditions.append("(name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if category:
            conditions.append("category=?")
            params.append(category)
        if agent_type:
            conditions.append("type=?")
            params.append(agent_type)
        if tags:
            for t in tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{t}"%')
        # 按 Skill 筛选：通过关联表 JOIN
        if skill:
            conditions.append("id IN (SELECT agent_id FROM agent_skills WHERE skill_id LIKE ?)")
            params.append(f"%/{skill}")
        # 按 MCP server 筛选：通过关联表 JOIN
        if mcp:
            conditions.append("id IN (SELECT agent_id FROM agent_mcp_servers WHERE mcp_server_id LIKE ?)")
            params.append(f"%/{mcp}")
        where = " AND ".join(conditions) if conditions else "1=1"
        sort_map = {"downloads":"download_count","rating":"rating","created":"created_at","name":"name"}
        sort_col = sort_map.get(sort,"download_count")
        order_dir = "DESC" if order=="desc" else "ASC"
        cursor = await self._conn.execute(f"SELECT COUNT(*) FROM agents WHERE {where}", params)
        total = (await cursor.fetchone())[0]
        offset = (page-1)*page_size
        cursor = await self._conn.execute(f"SELECT * FROM agents WHERE {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?", params+[page_size, offset])
        rows = await cursor.fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            items.append(d)
        return total, items

    async def batch_get_agents(self, ids):
        if not ids:
            return {}
        placeholders = ",".join("?" for _ in ids)
        cursor = await self._conn.execute(f"SELECT * FROM agents WHERE id IN ({placeholders})", ids)
        rows = await cursor.fetchall()
        result = {}
        for row in rows:
            d = dict(row)
            try:
                d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            try:
                d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else {}
            except (json.JSONDecodeError, TypeError):
                d["dependencies"] = {}
            result[d["id"]] = d
        for aid in ids:
            if aid not in result:
                result[aid] = None
        return result

    async def increment_download(self, agent_id, client_ip="", user_agent=""):
        try:
            await self._conn.execute("UPDATE agents SET download_count=download_count+1 WHERE id=?", (agent_id,))
            await self._conn.execute("INSERT INTO downloads (agent_id,client_ip,user_agent) VALUES (?,?,?)", (agent_id, client_ip, user_agent))
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def add_rating(self, agent_id, user_id, score, comment=""):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._conn.execute(
            "INSERT OR REPLACE INTO ratings (agent_id,user_id,score,comment,created_at) VALUES (?,?,?,?,COALESCE((SELECT created_at FROM ratings WHERE agent_id=? AND user_id=?),?))",
            (agent_id, user_id, score, comment, agent_id, user_id, now))
        await self._conn.commit()
        await self._update_rating_aggregate(agent_id)
        cursor = await self._conn.execute("SELECT id,agent_id,score,comment,created_at FROM ratings WHERE agent_id=? AND user_id=?", (agent_id, user_id))
        r = await cursor.fetchone()
        return {"id":r[0],"agent_id":r[1],"score":r[2],"comment":r[3],"created_at":r[4]}

    async def get_ratings(self, agent_id, page=1, page_size=10):
        cursor = await self._conn.execute("SELECT AVG(score),COUNT(*) FROM ratings WHERE agent_id=?", (agent_id,))
        row = await cursor.fetchone()
        avg = round(row[0], 1) if row and row[0] else 0.0
        total = row[1] if row else 0
        offset = (page-1)*page_size
        cursor = await self._conn.execute("SELECT id,agent_id,score,comment,created_at FROM ratings WHERE agent_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?", (agent_id, page_size, offset))
        rows = await cursor.fetchall()
        items = [{"id":r[0],"agent_id":r[1],"score":r[2],"comment":r[3],"created_at":r[4]} for r in rows]
        return total, avg, items

    async def _update_rating_aggregate(self, agent_id):
        cursor = await self._conn.execute("SELECT AVG(score),COUNT(*) FROM ratings WHERE agent_id=?", (agent_id,))
        row = await cursor.fetchone()
        avg = round(row[0], 1) if row and row[0] else 0.0
        cnt = row[1] if row else 0
        await self._conn.execute("UPDATE agents SET rating=?, review_count=? WHERE id=?", (avg, cnt, agent_id))
        await self._conn.commit()

    async def create_api_key(self, key, key_hash, owner, role, expires_at=None):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._conn.execute(
            "INSERT INTO api_keys (key_hash,owner,role,expires_at) VALUES (?,?,?,?)",
            (key_hash, owner, role, expires_at)
        )
        await self._conn.commit()
        return {"key": key, "key_hash": key_hash, "owner": owner, "role": role, "expires_at": expires_at, "created_at": now}

    async def get_all_enabled_api_keys(self):
        """Get all enabled, non-expired API keys for verification."""
        cursor = await self._conn.execute(
            "SELECT * FROM api_keys WHERE enabled=1"
        )
        rows = await cursor.fetchall()
        result = []
        for row in rows:
            result.append({
                "id": row[0], "key_hash": row[1], "owner": row[2], "role": row[3],
                "enabled": bool(row[4]), "expires_at": row[5], "created_at": row[6]
            })
        return result

    async def get_api_key_by_id(self, key_id):
        """Get API key info by ID (for admin)."""
        cursor = await self._conn.execute("SELECT * FROM api_keys WHERE id=?", (key_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        return {"id": row[0], "key_hash": row[1], "owner": row[2], "role": row[3],
                "enabled": bool(row[4]), "expires_at": row[5], "created_at": row[6]}

    async def list_api_keys(self):
        cursor = await self._conn.execute("SELECT * FROM api_keys ORDER BY created_at DESC")
        rows = await cursor.fetchall()
        return [{"id":r[0],"key":r[1],"owner":r[2],"role":r[3],"enabled":bool(r[4]),"created_at":r[6]} for r in rows]

    async def revoke_api_key(self, key):
        cursor = await self._conn.execute("UPDATE api_keys SET enabled=0 WHERE key=?", (key,))
        await self._conn.commit()
        return cursor.rowcount > 0

    # ================================================================
    # Skill & MCP Server 管理
    # ================================================================

    async def upsert_skill(self, skill_data: dict):
        """INSERT OR REPLACE 技能定义（v3.1 扩展：支持独立包）"""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._conn.execute(
            "INSERT OR REPLACE INTO skills (id, original_name, display_name, description, version, category, icon, "
            "package_path, package_size, package_format, content_format, content_source, content, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (skill_data["id"], skill_data.get("original_name", ""),
             skill_data.get("display_name", ""), skill_data.get("description", ""),
             skill_data.get("version", ""), skill_data.get("category", ""),
             skill_data.get("icon", ""),
             skill_data.get("package_path", ""),
             skill_data.get("package_size", 0),
             skill_data.get("package_format", "tar.gz"),
             skill_data.get("content_format", "markdown"),
             skill_data.get("content_source", "inline"),
             skill_data.get("content", ""),
             now)
        )
        await self._conn.commit()

    async def get_skill(self, skill_id: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM skills WHERE id=?", (skill_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def list_skills(self, q="", category="", page=1, page_size=20):
        conditions, params = [], []
        if q:
            conditions.append("(s.original_name LIKE ? OR s.display_name LIKE ? OR s.description LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if category:
            conditions.append("s.category=?")
            params.append(category)
        where = " AND ".join(conditions) if conditions else "1=1"
        cursor = await self._conn.execute(
            f"SELECT s.*, COUNT(a_s.agent_id) as agent_count "
            f"FROM skills s LEFT JOIN agent_skills a_s ON s.id = a_s.skill_id "
            f"WHERE {where} GROUP BY s.id ORDER BY s.display_name LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size]
        )
        rows = await cursor.fetchall()
        cursor = await self._conn.execute(
            f"SELECT COUNT(*) FROM skills s WHERE {where}", params
        )
        total = (await cursor.fetchone())[0]
        return total, [dict(r) for r in rows]

    async def delete_skill(self, skill_id: str) -> bool:
        cursor = await self._conn.execute("DELETE FROM skills WHERE id=?", (skill_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_skill_agents(self, skill_id: str) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT a.id, a.display_name AS name, a.version FROM agents a "
            "JOIN agent_skills a_s ON a.id = a_s.agent_id WHERE a_s.skill_id=?",
            (skill_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def upsert_mcp_server(self, mcp_data: dict):
        """INSERT OR REPLACE MCP 服务定义（v3.1 扩展：支持独立包）"""
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        args_json = json.dumps(mcp_data.get("args", []), ensure_ascii=False)
        tools_json = json.dumps(mcp_data.get("tools", []), ensure_ascii=False)
        env_json = json.dumps(mcp_data.get("required_env", []), ensure_ascii=False)
        await self._conn.execute(
            "INSERT OR REPLACE INTO mcp_servers (id, original_name, description, version, command, args, package, tools, required_env, "
            "package_path, package_size, package_format, config_content, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (mcp_data["id"], mcp_data.get("original_name", ""),
             mcp_data.get("description", ""), mcp_data.get("version", ""),
             mcp_data.get("command", ""),
             args_json, mcp_data.get("package", ""),
             tools_json, env_json,
             mcp_data.get("package_path", ""),
             mcp_data.get("package_size", 0),
             mcp_data.get("package_format", "tar.gz"),
             mcp_data.get("config_content", ""),
             now)
        )
        await self._conn.commit()

    async def get_mcp_server(self, mcp_id: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM mcp_servers WHERE id=?", (mcp_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("args", "tools", "required_env"):
            try:
                d[key] = json.loads(d[key]) if d[key] else []
            except (json.JSONDecodeError, TypeError):
                d[key] = []
        return d

    async def list_mcp_servers(self, q="", page=1, page_size=20):
        conditions, params = [], []
        if q:
            conditions.append("(m.original_name LIKE ? OR m.description LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like])
        where = " AND ".join(conditions) if conditions else "1=1"
        cursor = await self._conn.execute(
            f"SELECT m.*, COUNT(a_m.agent_id) as agent_count "
            f"FROM mcp_servers m LEFT JOIN agent_mcp_servers a_m ON m.id = a_m.mcp_server_id "
            f"WHERE {where} GROUP BY m.id ORDER BY m.original_name LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size]
        )
        rows = await cursor.fetchall()
        cursor = await self._conn.execute(
            f"SELECT COUNT(*) FROM mcp_servers m WHERE {where}", params
        )
        total = (await cursor.fetchone())[0]
        items = []
        for r in rows:
            d = dict(r)
            for key in ("args", "tools", "required_env"):
                try:
                    d[key] = json.loads(d[key]) if d[key] else []
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
            items.append(d)
        return total, items

    async def delete_mcp_server(self, mcp_id: str) -> bool:
        cursor = await self._conn.execute("DELETE FROM mcp_servers WHERE id=?", (mcp_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def get_mcp_server_agents(self, mcp_id: str) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT a.id, a.display_name AS name, a.version FROM agents a "
            "JOIN agent_mcp_servers a_m ON a.id = a_m.agent_id WHERE a_m.mcp_server_id=?",
            (mcp_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]

    # ---- 关联表操作 ----

    async def sync_agent_skills(self, agent_id: str, skill_ids: list[str]):
        """替换 Agent 的 skill 关联关系（先删后插）"""
        await self._conn.execute("DELETE FROM agent_skills WHERE agent_id=?", (agent_id,))
        for skill_id in skill_ids:
            await self._conn.execute(
                "INSERT OR IGNORE INTO agent_skills (agent_id, skill_id) VALUES (?, ?)",
                (agent_id, skill_id)
            )
        await self._conn.commit()

    async def sync_agent_mcp_servers(self, agent_id: str, mcp_ids: list[str]):
        """替换 Agent 的 MCP server 关联关系（先删后插）"""
        await self._conn.execute("DELETE FROM agent_mcp_servers WHERE agent_id=?", (agent_id,))
        for mcp_id in mcp_ids:
            await self._conn.execute(
                "INSERT OR IGNORE INTO agent_mcp_servers (agent_id, mcp_server_id) VALUES (?, ?)",
                (agent_id, mcp_id)
            )
        await self._conn.commit()

    async def get_agent_skills(self, agent_id: str) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT s.* FROM skills s JOIN agent_skills a_s ON s.id = a_s.skill_id WHERE a_s.agent_id=?",
            (agent_id,)
        )
        return [dict(r) for r in await cursor.fetchall()]

    async def get_agent_mcp_servers(self, agent_id: str) -> list[dict]:
        cursor = await self._conn.execute(
            "SELECT m.* FROM mcp_servers m JOIN agent_mcp_servers a_m ON m.id = a_m.mcp_server_id WHERE a_m.agent_id=?",
            (agent_id,)
        )
        items = []
        for r in await cursor.fetchall():
            d = dict(r)
            for key in ("args", "tools", "required_env"):
                try:
                    d[key] = json.loads(d[key]) if d[key] else []
                except (json.JSONDecodeError, TypeError):
                    d[key] = []
            items.append(d)
        return items

    async def resync_skills_mcp(self) -> dict:
        """从现有 agents 的 json_content 中重新提取 skills 和 MCP 并同步到独立表

        用于从旧版本市场迁移数据时，补全 skills/mcp_servers 表的内容。"""
        # 优先用相对导入（兼容不同部署方式），失败则退回到绝对导入
        try:
            from .skills_mcp import extract_skills_info, extract_mcp_info
        except ImportError:
            from market.skills_mcp import extract_skills_info, extract_mcp_info

        cursor = await self._conn.execute("SELECT id, json_content FROM agents")
        rows = await cursor.fetchall()

        agent_count = 0
        total_skills = 0
        total_mcp = 0
        errors = []

        for row in rows:
            agent_id = row[0]
            json_content = row[1]

            try:
                metadata = json.loads(json_content) if json_content else {}
            except (json.JSONDecodeError, TypeError):
                errors.append({"agent_id": agent_id, "error": "json_content 解析失败"})
                continue

            try:
                # 从 json_content 提取 skills 和 MCP（不含 extract_dir 因为无法访问包文件）
                skills = extract_skills_info(metadata, extract_dir=None)
                mcp_list = extract_mcp_info(metadata, extract_dir=None)

                # 同步到独立表
                for skill in skills:
                    await self.upsert_skill(skill)
                await self.sync_agent_skills(agent_id, [s["id"] for s in skills])

                for mcp in mcp_list:
                    await self.upsert_mcp_server(mcp)
                await self.sync_agent_mcp_servers(agent_id, [m["id"] for m in mcp_list])

                agent_count += 1
                total_skills += len(skills)
                total_mcp += len(mcp_list)
            except Exception as e:
                errors.append({"agent_id": agent_id, "error": str(e)})

        return {
            "agents_processed": agent_count,
            "skills_extracted": total_skills,
            "mcp_servers_extracted": total_mcp,
            "total_agents": len(rows),
            "errors": errors,
        }

    async def health_stats(self):
        c1 = await self._conn.execute("SELECT COUNT(*) FROM agents")
        agents_count = (await c1.fetchone())[0]
        c2 = await self._conn.execute("SELECT COUNT(*) FROM api_keys WHERE enabled=1")
        api_keys_count = (await c2.fetchone())[0]
        c3 = await self._conn.execute("SELECT COUNT(*) FROM teams")
        teams_count = (await c3.fetchone())[0]
        c4 = await self._conn.execute("SELECT COUNT(*) FROM workflows")
        workflows_count = (await c4.fetchone())[0]
        return {"agents_count": agents_count, "api_keys_count": api_keys_count,
                "teams_count": teams_count, "workflows_count": workflows_count}

    # ============================================================
    # Team 管理
    # ============================================================

    async def insert_team(self, data: dict) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)
        deps = data.get("dependencies", "{}")
        if isinstance(deps, dict):
            deps = json.dumps(deps, ensure_ascii=False)
        await self._conn.execute(
            "INSERT INTO teams (id,name,display_name,version,description,author,category,type,tags,package_path,package_size,package_format,json_content,dependencies,homepage_url,source_url,license,readme,created_at,updated_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data["id"], data["name"], data.get("display_name", data["name"]), data["version"],
             data.get("description", ""), data.get("author", ""), data.get("category", "general"),
             data.get("type", "team"), tags_json, data.get("package_path", ""),
             data.get("package_size", 0), data.get("package_format", "tar.gz"),
             data.get("json_content", "{}"), deps, data.get("homepage_url", ""),
             data.get("source_url", ""), data.get("license", "MIT"), data.get("readme", ""),
             now, now, now)
        )
        await self._conn.commit()
        return data["id"]

    async def get_team(self, team_id: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        try:
            d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else {}
        except (json.JSONDecodeError, TypeError):
            d["dependencies"] = {}
        return d

    async def update_team(self, team_id: str, data: dict) -> bool:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        fields, values = [], []
        for key in ("description", "display_name", "version", "category", "package_path",
                    "package_size", "package_format", "homepage_url", "source_url", "license", "readme", "author"):
            if key in data:
                fields.append(f"{key}=?")
                values.append(data[key])
        if "tags" in data:
            fields.append("tags=?")
            values.append(json.dumps(data["tags"], ensure_ascii=False))
        if not fields:
            return False
        fields.append("updated_at=?")
        values.append(now)
        values.append(team_id)
        await self._conn.execute(f"UPDATE teams SET {','.join(fields)} WHERE id=?", values)
        await self._conn.commit()
        return True

    async def delete_team(self, team_id: str) -> bool:
        cursor = await self._conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_teams(self, q="", category="", team_type="", tags=None,
                          sort="downloads", order="desc", page=1, page_size=20):
        conditions, params = [], []
        if q:
            conditions.append("(name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if category:
            conditions.append("category=?")
            params.append(category)
        if tags:
            for t in tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{t}"%')
        where = " AND ".join(conditions) if conditions else "1=1"
        sort_map = {"downloads": "download_count", "rating": "rating", "created": "created_at", "name": "name"}
        sort_col = sort_map.get(sort, "download_count")
        order_dir = "DESC" if order == "desc" else "ASC"
        cursor = await self._conn.execute(f"SELECT COUNT(*) FROM teams WHERE {where}", params)
        total = (await cursor.fetchone())[0]
        cursor = await self._conn.execute(
            f"SELECT * FROM teams WHERE {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size]
        )
        rows = await cursor.fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            items.append(d)
        return total, items

    async def increment_download_team(self, team_id, client_ip="", user_agent=""):
        try:
            await self._conn.execute("UPDATE teams SET download_count=download_count+1 WHERE id=?", (team_id,))
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def add_team_rating(self, team_id, user_id, score, comment=""):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        # 使用独立的 ratings 表，但添加实体类型区分
        await self._conn.execute(
            "INSERT OR REPLACE INTO ratings (agent_id, user_id, score, comment, created_at) VALUES (?,?,?,?, COALESCE((SELECT created_at FROM ratings WHERE agent_id=? AND user_id=?), ?))",
            (team_id, user_id, score, comment, team_id, user_id, now)
        )
        await self._conn.commit()
        await self._update_team_rating_aggregate(team_id)
        cursor = await self._conn.execute("SELECT id, agent_id as team_id, score, comment, created_at FROM ratings WHERE agent_id=? AND user_id=?", (team_id, user_id))
        r = await cursor.fetchone()
        return {"id": r[0], "team_id": r[1], "score": r[2], "comment": r[3], "created_at": r[4]}

    async def _update_team_rating_aggregate(self, team_id):
        cursor = await self._conn.execute("SELECT AVG(score), COUNT(*) FROM ratings WHERE agent_id=?", (team_id,))
        row = await cursor.fetchone()
        avg = round(row[0], 1) if row and row[0] else 0.0
        cnt = row[1] if row else 0
        await self._conn.execute("UPDATE teams SET rating=?, review_count=? WHERE id=?", (avg, cnt, team_id))
        await self._conn.commit()

    async def get_team_ratings(self, team_id, page=1, page_size=10):
        cursor = await self._conn.execute("SELECT AVG(score),COUNT(*) FROM ratings WHERE agent_id=?", (team_id,))
        row = await cursor.fetchone()
        avg = round(row[0], 1) if row and row[0] else 0.0
        total = row[1] if row else 0
        offset = (page - 1) * page_size
        cursor = await self._conn.execute(
            "SELECT id, agent_id as team_id, score, comment, created_at FROM ratings WHERE agent_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (team_id, page_size, offset)
        )
        rows = await cursor.fetchall()
        items = [{"id": r[0], "team_id": r[1], "score": r[2], "comment": r[3], "created_at": r[4]} for r in rows]
        return total, avg, items

    # ============================================================
    # Workflow 管理
    # ============================================================

    async def insert_workflow(self, data: dict) -> str:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        tags_json = json.dumps(data.get("tags", []), ensure_ascii=False)
        deps = data.get("dependencies", "{}")
        if isinstance(deps, dict):
            deps = json.dumps(deps, ensure_ascii=False)
        await self._conn.execute(
            "INSERT INTO workflows (id,name,display_name,version,description,author,category,type,tags,package_path,package_size,package_format,json_content,dependencies,homepage_url,source_url,license,readme,created_at,updated_at,published_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (data["id"], data["name"], data.get("display_name", data["name"]), data["version"],
             data.get("description", ""), data.get("author", ""), data.get("category", "general"),
             data.get("type", "workflow"), tags_json, data.get("package_path", ""),
             data.get("package_size", 0), data.get("package_format", "tar.gz"),
             data.get("json_content", "{}"), deps, data.get("homepage_url", ""),
             data.get("source_url", ""), data.get("license", "MIT"), data.get("readme", ""),
             now, now, now)
        )
        await self._conn.commit()
        return data["id"]

    async def get_workflow(self, workflow_id: str) -> dict | None:
        cursor = await self._conn.execute("SELECT * FROM workflows WHERE id = ?", (workflow_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        d = dict(row)
        try:
            d["tags"] = json.loads(d["tags"]) if d["tags"] else []
        except (json.JSONDecodeError, TypeError):
            d["tags"] = []
        try:
            d["dependencies"] = json.loads(d["dependencies"]) if d["dependencies"] else {}
        except (json.JSONDecodeError, TypeError):
            d["dependencies"] = {}
        return d

    async def update_workflow(self, workflow_id: str, data: dict) -> bool:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        fields, values = [], []
        for key in ("description", "display_name", "version", "category", "package_path",
                    "package_size", "package_format", "homepage_url", "source_url", "license", "readme", "author"):
            if key in data:
                fields.append(f"{key}=?")
                values.append(data[key])
        if "tags" in data:
            fields.append("tags=?")
            values.append(json.dumps(data["tags"], ensure_ascii=False))
        if not fields:
            return False
        fields.append("updated_at=?")
        values.append(now)
        values.append(workflow_id)
        await self._conn.execute(f"UPDATE workflows SET {','.join(fields)} WHERE id=?", values)
        await self._conn.commit()
        return True

    async def delete_workflow(self, workflow_id: str) -> bool:
        cursor = await self._conn.execute("DELETE FROM workflows WHERE id=?", (workflow_id,))
        await self._conn.commit()
        return cursor.rowcount > 0

    async def list_workflows(self, q="", category="", workflow_type="", tags=None,
                              sort="downloads", order="desc", page=1, page_size=20):
        conditions, params = [], []
        if q:
            conditions.append("(name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
            like = f"%{q}%"
            params.extend([like, like, like])
        if category:
            conditions.append("category=?")
            params.append(category)
        if tags:
            for t in tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{t}"%')
        where = " AND ".join(conditions) if conditions else "1=1"
        sort_map = {"downloads": "download_count", "rating": "rating", "created": "created_at", "name": "name"}
        sort_col = sort_map.get(sort, "download_count")
        order_dir = "DESC" if order == "desc" else "ASC"
        cursor = await self._conn.execute(f"SELECT COUNT(*) FROM workflows WHERE {where}", params)
        total = (await cursor.fetchone())[0]
        cursor = await self._conn.execute(
            f"SELECT * FROM workflows WHERE {where} ORDER BY {sort_col} {order_dir} LIMIT ? OFFSET ?",
            params + [page_size, (page - 1) * page_size]
        )
        rows = await cursor.fetchall()
        items = []
        for r in rows:
            d = dict(r)
            try:
                d["tags"] = json.loads(d["tags"]) if d["tags"] else []
            except (json.JSONDecodeError, TypeError):
                d["tags"] = []
            items.append(d)
        return total, items

    async def increment_download_workflow(self, workflow_id, client_ip="", user_agent=""):
        try:
            await self._conn.execute("UPDATE workflows SET download_count=download_count+1 WHERE id=?", (workflow_id,))
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def add_workflow_rating(self, workflow_id, user_id, score, comment=""):
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._conn.execute(
            "INSERT OR REPLACE INTO ratings (agent_id, user_id, score, comment, created_at) VALUES (?,?,?,?, COALESCE((SELECT created_at FROM ratings WHERE agent_id=? AND user_id=?), ?))",
            (workflow_id, user_id, score, comment, workflow_id, user_id, now)
        )
        await self._conn.commit()
        await self._update_workflow_rating_aggregate(workflow_id)
        cursor = await self._conn.execute("SELECT id, agent_id as workflow_id, score, comment, created_at FROM ratings WHERE agent_id=? AND user_id=?", (workflow_id, user_id))
        r = await cursor.fetchone()
        return {"id": r[0], "workflow_id": r[1], "score": r[2], "comment": r[3], "created_at": r[4]}

    async def _update_workflow_rating_aggregate(self, workflow_id):
        cursor = await self._conn.execute("SELECT AVG(score), COUNT(*) FROM ratings WHERE agent_id=?", (workflow_id,))
        row = await cursor.fetchone()
        avg = round(row[0], 1) if row and row[0] else 0.0
        cnt = row[1] if row else 0
        await self._conn.execute("UPDATE workflows SET rating=?, review_count=? WHERE id=?", (avg, cnt, workflow_id))
        await self._conn.commit()

    async def get_workflow_ratings(self, workflow_id, page=1, page_size=10):
        cursor = await self._conn.execute("SELECT AVG(score),COUNT(*) FROM ratings WHERE agent_id=?", (workflow_id,))
        row = await cursor.fetchone()
        avg = round(row[0], 1) if row and row[0] else 0.0
        total = row[1] if row else 0
        offset = (page - 1) * page_size
        cursor = await self._conn.execute(
            "SELECT id, agent_id as workflow_id, score, comment, created_at FROM ratings WHERE agent_id=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (workflow_id, page_size, offset)
        )
        rows = await cursor.fetchall()
        items = [{"id": r[0], "workflow_id": r[1], "score": r[2], "comment": r[3], "created_at": r[4]} for r in rows]
        return total, avg, items

    # ============================================================
    # 版本历史管理
    # ============================================================

    async def record_version(self, entity_type: str, entity_id: str, data: dict, changelog: str = ""):
        """记录一个新版本到 versions 表

        entity_type: 'agent' | 'team' | 'workflow'
        data: 包含 version, package_path, package_size, package_format, package_sha256, author 等字段
        """
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        await self._conn.execute(
            "INSERT OR IGNORE INTO versions "
            "(entity_type, entity_id, version, changelog, package_path, package_size, package_format, package_sha256, author, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (entity_type, entity_id, data.get("version", ""),
             changelog, data.get("package_path", ""), data.get("package_size", 0),
             data.get("package_format", "tar.gz"), data.get("package_sha256", ""),
             data.get("author", ""), now)
        )
        await self._conn.commit()

    async def list_versions(self, entity_type: str, entity_id: str) -> list[dict]:
        """列出某个实体的所有版本，按 created_at DESC 排序"""
        cursor = await self._conn.execute(
            "SELECT version, changelog, package_size, package_sha256, author, created_at "
            "FROM versions WHERE entity_type=? AND entity_id=? ORDER BY created_at DESC",
            (entity_type, entity_id)
        )
        rows = await cursor.fetchall()
        return [
            {
                "version": r[0],
                "changelog": r[1] or "",
                "package_size": r[2],
                "package_sha256": r[3] or "",
                "author": r[4] or "",
                "created_at": r[5],
            }
            for r in rows
        ]

    async def get_version(self, entity_type: str, entity_id: str, version: str) -> dict | None:
        """获取某个实体的特定版本详情"""
        cursor = await self._conn.execute(
            "SELECT version, changelog, package_size, package_sha256, package_format, package_path, author, created_at "
            "FROM versions WHERE entity_type=? AND entity_id=? AND version=?",
            (entity_type, entity_id, version)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return {
            "version": row[0],
            "changelog": row[1] or "",
            "package_size": row[2],
            "package_sha256": row[3] or "",
            "package_format": row[4] or "tar.gz",
            "package_path": row[5] or "",
            "author": row[6] or "",
            "created_at": row[7],
        }