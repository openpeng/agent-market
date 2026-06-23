# agent-market — Agent Hub Market 服务

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Framework](https://img.shields.io/badge/framework-FastAPI-009688.svg)](https://fastapi.tiangolo.com)

一个轻量级的 AI Agent 市场服务，支持 Agent 包的注册、发布、搜索、下载、评分，内置完整的安全扫描机制。

## 功能特性

- **Agent 注册与发布** — 上传 `.tar.gz` / `.zip` 格式的 Agent 包，自动解析元数据
- **语义搜索** — 基于关键词、分类、标签的多维度过滤查询
- **下载与缓存** — 流式下载，SHA-256 完整性校验，客户端缓存 + LRU 清理
- **评分与评论** — 1-5 星评分系统，支持评论
- **API Key 认证** — Bearer Token 认证，SHA-256 哈希存储，支持 publisher / admin 两种角色
- **安全扫描** — 上传包自动检测路径遍历、符号链接、大小限制，拒绝恶意包
- **Rate Limiting** — 分层限流（上传 20次/小时，下载 100次/分钟，Key创建 5次/小时）
- **Agent 发现** — 按能力/格式的智能 Agent 匹配服务
- **生命周期管理** — Agent 弃用/下架机制
- **REST API** — 完整的 RESTful API，FastAPI 自动生成 Swagger 文档
- **CLI 客户端** — 命令行工具，支持搜索、安装、发布等操作
- **Web 管理后台** — 内建 SPA 前端界面
- **Docker 部署** — 提供 Dockerfile + docker-compose.yml

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
python -m uvicorn src.market.server:app --reload --port 8321
```

### 3. 打开浏览器

```
http://localhost:8321
```

访问 `/docs` 查看 API 文档。

## 架构概览

```
src/market/
├── server.py        # FastAPI 服务入口
├── models.py        # Pydantic 数据模型
├── database.py      # SQLite 异步数据库层 (aiosqlite + WAL)
├── auth.py          # API Key 认证 (SHA-256 哈希)
├── package.py       # 打包/解包 (tar.gz, zip)
├── search.py        # 搜索参数构建
├── client.py        # MarketClient HTTP 客户端
├── cache.py         # 本地缓存管理 (LRU)
├── verify.py        # 包完整性验证 (SHA-256 + 路径遍历检测)
├── discovery.py     # Agent 发现服务 (按能力匹配)
├── rate_limit.py    # 分层限流中间件
├── ratings.py       # 评分系统
├── skill_compat.py  # 旧版 SKILL.md 兼容包装
└── static/          # Web 前端 SPA
```

## API 端点

| Method | Path | 说明 | 认证 |
|--------|------|------|------|
| `GET` | `/api/v1/health` | 健康检查 | 无 |
| `GET` | `/api/v1/agents` | 搜索/列出 Agent | 无 |
| `GET` | `/api/v1/agents/batch` | 批量查询 | 无 |
| `GET` | `/api/v1/agents/{id}` | Agent 详情 | 无 |
| `POST` | `/api/v1/agents` | 注册 Agent（含安全扫描） | publisher |
| `GET` | `/api/v1/agents/{id}/download` | 下载 Agent 包（SHA-256 校验） | 无 |
| `DELETE` | `/api/v1/agents/{id}` | 删除 Agent | admin |
| `POST` | `/api/v1/agents/{id}/deprecate` | 弃用 Agent | publisher |
| `POST` | `/api/v1/agents/{id}/ratings` | 评分 | publisher |
| `GET` | `/api/v1/agents/{id}/ratings` | 查看评分 | 无 |
| `GET` | `/api/v1/discover` | Agent 发现（按能力匹配） | 无 |
| `POST` | `/api/v1/api-keys` | 创建 API Key | master/admin |
| `GET` | `/api/v1/api-keys` | 列出 API Keys | admin |
| `DELETE` | `/api/v1/api-keys/{key}` | 撤销 API Key | admin |

## CLI 用法

```bash
# 健康检查
python src/cli/market.py status

# 搜索 Agent
python src/cli/market.py search "keyword"

# 安装 Agent
python src/cli/market.py install agent-id

# 发布 Agent 包
python src/cli/market.py publish ./path/to/agent --api-key YOUR_KEY

# 管理缓存
python src/cli/market.py cache status
python src/cli/market.py cache clean --max-age 30

# 管理 API Key
python src/cli/market.py key create --owner my-team --role publisher
python src/cli/market.py key list --api-key YOUR_ADMIN_KEY
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MARKET_MASTER_KEY` | 主 API Key，用于创建其他 Key | 无 |
| `MARKET_DB_PATH` | SQLite 数据库路径 | `data/market/market.db` |
| `MARKET_PACKAGES_DIR` | Agent 包存储目录 | `data/market/packages` |

## 安全特性

| 特性 | 说明 |
|------|------|
| API Key 哈希存储 | SHA-256 哈希，永不保存明文 |
| 上传扫描 | 路径遍历/符号链接/大小检测，拒绝恶意包 |
| 下载校验 | HTTP `Digest: sha-256=...` 响应头 + 客户端校验 |
| Rate Limiting | 上传 20次/小时，下载 100次/分钟，Key创建 5次/小时 |
| 常量时间比对 | API Key 验证防时序攻击 |
| Docker 部署 | Dockerfile + docker-compose.yml 一键部署 |

## 文档

### 项目文档
- [完整文档索引](docs/README.md) — 查看所有文档
- [市场服务实现计划](docs/market-service-implementation.md) — 架构和实现
- [前端开发计划](docs/market-frontend.md) — Web UI 规划

### 技能文档
- [Market Helper 技能](skills/market-helper/SKILL.md) — Market API 助手
- [Market Tutorial 技能](skills/market-tutorial/SKILL.md) — Market 使用教程

### 相关项目
- [agent-deploy](https://github.com/openpeng/agent-deploy) — Agent 部署工具，与 Market 完整集成

## 许可证

[MIT](LICENSE) © 2025 Peng Xiao
