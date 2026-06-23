# 市场服务实现计划

> 基于 `市场服务开发文档.md` 的实现计划
> 创建日期：2026-06-01

---

## 1. 文件结构

根据开发文档，将创建以下新文件（现有文件为扩展修改）：

```text
src/market/
├── __init__.py          # 包初始化
├── database.py          # SQLite 数据库初始化与管理 (agents/skills/mcp_servers/关联表)
├── models.py            # Pydantic 数据模型 (含 SkillInfo/MCPInfo)
├── server.py            # FastAPI 服务（主入口，含 Skills/MCP Routes）
├── auth.py              # API Key 认证中间件
├── package.py           # tar.gz/zip 打包与解包
├── search.py            # 搜索+过滤+分页
├── ratings.py           # 评分系统
├── client.py            # MarketClient 客户端类
├── cache.py             # 本地缓存管理
├── verify.py            # 包完整性验证 (含 skills/mcp 校验)
├── skills_mcp.py        # Skills & MCP 信息提取与归一化
├── discovery.py         # Agent 发现协议 (含 skills/mcp 能力)
├── rate_limit.py        # 速率限制
└── skill_compat.py      # SKILL.md 兼容包装

src/cli/
├── __init__.py          # CLI 入口
└── market.py            # market 子命令组

tests/
└── test_market_server.py   # 服务端测试
└── test_market_client.py   # 客户端测试
└── test_package.py         # 包操作测试
└── test_skills_mcp.py      # Skills & MCP 测试 (19 cases, 100% pass)
```

**扩展的现有文件：**
- `src/agents/__init__.py` — 为 `MainAgent` 增加 `load_from_market()`, `publish_to_market()`, `search_market()`, `list_installed()` 方法
- `src/schemas.py` — 新增 `MarketListing`, `MarketAgentDetail` 等 Pydantic/数据模型

---

## 2. 实施步骤（按 Phase 分组）

### Phase 1: 核心市场服务（服务端）

#### Step 1: 创建 `src/market/` 包结构

**文件：`src/market/__init__.py`**
- 包标识与版本声明

#### Step 2: 数据库初始化 — `src/market/database.py`

**实现内容：**
- 读取开发文档第2节所有 SQL 建表语句
- 实现 `MarketDatabase` 类，封装：
  - `__init__(db_path)` — 初始化连接（使用 aiosqlite）
  - `initialize()` — 创建所有表与索引
  - `get_agent(agent_id)` — 查询单个 Agent
  - `list_agents(filters, sort, page, page_size)` — 分页列表
  - `insert_agent(data)` — 新增 Agent
  - `update_agent(agent_id, data)` — 更新 Agent
  - `delete_agent(agent_id)` — 删除 Agent
  - `increment_download(agent_id, client_ip, user_agent)` — 下载计数+记录
  - 评分相关的 `add_rating()`, `get_ratings()`, `get_agent_rating_avg()`
  - API Key 相关的 `create_api_key()`, `get_api_key()`, `list_api_keys()`, `revoke_api_key()`
  - `health_stats()` — 统计计数

**依赖：** `aiosqlite`（异步 SQLite 驱动）

#### Step 3: 数据模型 — `src/market/models.py`

**实现内容：**
- 基于开发文档第3节所有的 JSON 请求/响应格式，定义 Pydantic 模型：
  - `AgentRegisterRequest` — 注册请求（multipart 文件上传）
  - `AgentResponse` — Agent 详情响应
  - `AgentListItem` — 列表项（精简版）
  - `AgentListResponse` — 分页列表包装
  - `BatchAgentResponse` — 批量查询
  - `RatingCreateRequest` — 评分请求
  - `RatingResponse` — 评分响应
  - `RatingListResponse` — 评分列表
  - `HealthResponse` — 健康检查
  - `ApiKeyCreateRequest` — API Key 创建请求
  - `ApiKeyResponse` — API Key 响应
  - `ErrorResponse` — 统一错误格式
- 枚举类型：`AgentCategory`, `AgentType`, `PackageFormat`

#### Step 4: API Key 认证 — `src/market/auth.py`

**实现内容：**
- `verify_api_key(authorization: str, db: MarketDatabase) -> dict | None` — 验证 Bearer token
- `require_publisher` / `require_admin` 的 FastAPI 依赖注入函数
- API Key 生成函数 `generate_api_key() -> str` — 格式 `pd_mkt_xxxxxxxxxxxxxxxx`

#### Step 5: 包打包/解包 — `src/market/package.py`

**实现内容：**
- `pack_agent(pkg_dir: str | Path, output_path: str | Path = None) -> Path` — 将目录打包为 tar.gz
  - 验证目录中包含 agent.json
  - 生成 `{name}-v{version}.tar.gz`
- `unpack_agent(package_path: str | Path, target_dir: str | Path) -> Path` — 解包到目标目录
- `extract_metadata(package_path: str | Path) -> dict` — 从包中提取 agent.json 内容
- `create_package_stream(package_path: str | Path) -> StreamingResponse` — 生成文件下载流

#### Step 6: 搜索功能 — `src/market/search.py`

**实现内容：**
- `build_search_query(q, category, type, tags, sort, order)` — 构建 SQL 查询
- 支持全文搜索（name, display_name, description LIKE 匹配）
- 标签过滤（AND 逻辑，JSON 数组匹配）
- 分页处理（LIMIT/OFFSET）

#### Step 7: 评分系统 — `src/market/ratings.py`

**实现内容：**
- `add_rating(agent_id, user_id, score, comment)` — 添加/更新评分
- `get_agent_ratings(agent_id, page, page_size)` — 分页获取评分
- `update_agent_rating_aggregate(agent_id)` — 更新 agents 表中的 rating 和 review_count

#### Step 8: 包完整性验证 — `src/market/verify.py`

**实现内容：**
- `verify_package(pkg_path: Path) -> tuple[bool, list[str]]` — 按文档第7.3节实现完整验证流程
  - 检查必需文件 agent.json
  - 验证 agent.json JSON 格式与内容
  - 检查子Agent文件是否存在
  - 检查包总大小限制

#### Step 9: FastAPI 服务主入口 — `src/market/server.py`

**实现内容：**
- 创建 FastAPI 应用实例
- 实现文档第3节 所有 REST API 端点：
  - `POST /api/v1/agents` — 注册 Agent（multipart 文件上传）
  - `GET /api/v1/agents/{agent_id}` — Agent 详情
  - `GET /api/v1/agents` — 搜索/列表
  - `GET /api/v1/agents/{agent_id}/download` — 下载包文件
  - `DELETE /api/v1/agents/{agent_id}` — 删除 Agent
  - `POST /api/v1/agents/{agent_id}/ratings` — 评分
  - `GET /api/v1/agents/{agent_id}/ratings` — 获取评分
  - `GET /api/v1/health` — 健康检查
  - `GET /api/v1/agents/batch?ids=...` — 批量查询
  - `POST /api/v1/api-keys` — 创建 API Key
- 启动入口 `if __name__ == "__main__"`: 使用 uvicorn.run()
- CORS 中间件
- 全局异常处理器

---

### Phase 2: 客户端工具

#### Step 10: 本地缓存管理 — `src/market/cache.py`

**实现内容：**
- `ensure_cache_dirs()` — 确保缓存目录结构（`~/.pilotdeck/market/{cache,installed}`）
- `load_index() / save_index(index)` — 读写 index.json
- `get_cached_agent(agent_id)` — 检查本地缓存
- `store_to_cache(agent_id, pkg_path)` — 存入缓存并解压
- `remove_from_cache(agent_id)` — 移除缓存
- `is_installed(agent_id)` — 检查是否已安装
- `list_cached_agents()` — 列出缓存中所有 Agent
- `cache_size_info()` — 缓存大小信息
- `clean_cache(max_age_days=7)` — 清理过期缓存
- `clean_lru_cache(target_size_mb=5120)` — LRU 清理

#### Step 11: MarketClient 类 — `src/market/client.py`

**实现内容（按文档 7.2 节）：**
- `__init__(server_url, api_key)` — 初始化
- `search(query, **kwargs)` — 搜索
- `get_agent(agent_id)` — 获取详情
- `download(agent_id, version)` — 下载到缓存
- `publish(pkg_dir, force)` — 发布
- `ensure_installed(agent_id, version)` — 确保安装
- `install(agent_id, version, output_dir)` — 安装流程
- `uninstall(agent_id)` — 卸载
- `list_installed()` — 已安装列表
- `check_updates(agent_id)` — 检查更新
- `cache_info()` — 缓存状态
- `clean_cache(max_age_days)` — 清理缓存
- `load_config() / save_config(config)` — 配置读写

#### Step 12: CLI 市场命令 — `src/cli/market.py`

**实现内容（按文档第4节）：**

命令组 `pilotdeck market`：
- `market serve` — 启动市场服务
- `market stop` — 停止服务
- `market status` — 服务状态
- `market publish <path>` — 发布 Agent
- `market search <query>` — 搜索
- `market install <agent_id>` — 安装
- `market list` — 列出已安装
- `market uninstall <agent_id>` — 卸载
- `market update [agent_id]` — 更新
- `market pack <path>` — 打包
- `market unpack <path>` — 解包预览
- `market cache status` — 缓存状态
- `market cache clean` — 清理缓存
- `market key create` — 创建 API Key
- `market key list` — 列出 API Keys
- `market key revoke <key>` — 撤销 API Key

**文件：`src/cli/__init__.py` — CLI 入口路由**

#### Step 13: MainAgent 集成 — 扩展 `src/agents/__init__.py`

**实现内容（按文档 7.1 节）：**
在 `MainAgent` 类中新增方法：
- `load_from_market(agent_id, market_url)` — 从市场安装并加载
- `publish_to_market(pkg_path, api_key)` — 发布到市场
- `search_market(query, **kwargs)` — 搜索市场
- `list_installed()` — 列出已安装

#### Step 14: 扩展 `src/schemas.py`

新增：
- `MarketListing` dataclass — 市场列表项
- `MarketAgentDetail` dataclass — 市场 Agent 详情

---

### Phase 3: 完善与兼容

#### Step 15: SKILL.md 兼容 — `src/market/skill_compat.py`

**实现内容（按文档 5.4 节）：**
- `wrap_skill_directory(skill_dir: Path) -> dict` — 自动包装 SKILL.md 为 agent.json
- 使用现有的 `SkillAutoWrap.detect_and_wrap()` 复用能力
- 标记 `is_wrapped: true`

#### Step 16: 测试文件

- `tests/test_market_server.py` — 服务端端点测试（用 FastAPI TestClient）
- `tests/test_market_client.py` — 客户端集成测试
- `tests/test_package.py` — 打包/解包/验证测试

---

## 3. 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 数据库驱动 | aiosqlite | 异步、零配置、嵌入式 |
| API 框架 | FastAPI | 异步原生、自动文档、类型安全 |
| 包格式 | tar.gz | 通用、压缩率高、Python 原生支持 |
| API Key 前缀 | `pd_mkt_` | 清晰标识、可配置 |
| 缓存策略 | LRU + 延迟清理 | 简单有效，默认 5GB 上限 |
| 服务端口 | 8321 | 如文档指定 |

## 4. 依赖项

需要安装的 Python 包：
```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
aiosqlite>=0.19.0
python-multipart>=0.0.6
pyyaml>=6.0
```

## 5. 文件创建顺序

```
1.  src/market/__init__.py        (包标识)
2.  src/market/models.py          (先定义数据模型)
3.  src/market/database.py        (数据库层)
4.  src/market/auth.py            (认证层)
5.  src/market/package.py         (包操作)
6.  src/market/search.py          (搜索逻辑)
7.  src/market/ratings.py         (评分逻辑)
8.  src/market/verify.py          (验证逻辑)
9.  src/market/server.py          (API 服务 - 核心)
10. src/market/cache.py           (缓存管理)
11. src/market/client.py          (客户端)
12. src/market/skill_compat.py    (兼容层)
13. src/cli/__init__.py           (CLI 入口)
14. src/cli/market.py             (CLI 命令)
15. 扩展 src/schemas.py           (新增模型)
16. 扩展 src/agents/__init__.py   (MainAgent 集成)
17. tests/test_market_server.py
18. tests/test_market_client.py
19. tests/test_package.py
```

---

## 6. 风险与注意事项

- **现有代码兼容**：MarketClient 的 `publish` 方法调用 `server.py` 的 API，需确保服务端先启动
- **异步一致性**：数据库操作使用 aiosqlite 的异步接口，需注意 FastAPI 端点的 async/await 一致性
- **包路径安全**：下载/解包操作需防止 path traversal 攻击
- **数据目录创建**：服务启动时自动创建数据目录（`./data/market/packages/`）
- **测试数据**：可复用现有的 `test_collab/` 和 `test_web_scraper/` 作为测试用 Agent 包

---
## 7. Skills & MCP 支持 (Phase 9)

### 7.1 数据库扩展

新增 4 张表，实现多对多关系：

```
agents ──< agent_skills >── skills
agents ──< agent_mcp_servers >── mcp_servers
```

| 表 | 主键 | 关键字段 |
|---|---|---|
| `skills` | id (qualified: "agent/skill-name") | original_name, display_name, description, category |
| `mcp_servers` | id (qualified: "agent/server-name") | original_name, description, command, args, required_env |
| `agent_skills` | (agent_id, skill_id) PK | 关联 Agent ↔ Skill，ON DELETE CASCADE |
| `agent_mcp_servers` | (agent_id, mcp_server_id) PK | 关联 Agent ↔ MCP，ON DELETE CASCADE |

### 7.2 Skills & MCP 提取

`skills_mcp.py` 支持 3 种 skills 格式 + 3 种 MCP 格式的归一化提取：

- **Skills 格式 A**: subagents 中 `type: "skill"`（v3 协议）
- **Skills 格式 B**: agent.json 顶层 `skills[]` 数组（agent-builder）
- **Skills 格式 C**: `skills/*.yaml` 文件系统（Runtime Loader）
- **MCP 格式 A1**: agent.json 顶层 `mcp_servers[]` 数组（agent-builder）
- **MCP 格式 A2**: `mcp.required_servers[]`（v3 协议）
- **MCP 格式 B**: `mcp/config.json` Claude Desktop 格式（Runtime Loader）

所有格式统一归一化为 `agent-name/original-name` 命名空间前缀，保证全局唯一。

### 7.3 API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/v1/skills` | 全市场 Skills 列表 |
| `GET` | `/api/v1/skills/{id}` | Skill 详情 + 关联 Agent |
| `POST` | `/api/v1/skills` | 独立注册 Skill |
| `DELETE` | `/api/v1/skills/{id}` | 删除 Skill |
| `GET` | `/api/v1/mcp-servers` | 全市场 MCP 列表 |
| `GET` | `/api/v1/mcp-servers/{id}` | MCP 详情 + 关联 Agent |
| `POST` | `/api/v1/mcp-servers` | 独立注册 MCP Server |
| `DELETE` | `/api/v1/mcp-servers/{id}` | 删除 MCP Server |

### 7.4 Agent 注册同步流程

Agent 上传时自动提取 skills/mcp 并同步到独立表：

```
register_agent()
  ├── verify_package()    → 校验 agent.json + skills/mcp 格式
  ├── extract_skills_info() → 从 3 种格式归一化
  ├── upsert_skill() × N   → INSERT OR REPLACE 到 skills 表
  ├── sync_agent_skills()  → 重建 agent_skills 关联
  ├── extract_mcp_info()   → 从 3 种格式归一化
  ├── upsert_mcp_server() × N → INSERT OR REPLACE 到 mcp_servers 表
  └── sync_agent_mcp_servers() → 重建 agent_mcp_servers 关联
```
