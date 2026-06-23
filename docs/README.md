# Agent Market Documentation

## 文档索引

### Market 实现文档

- **[市场服务实现计划](./market-service-implementation.md)** — 后端架构和实现方案
- **[前端开发计划](./market-frontend.md)** — Web UI 开发规划

### 主项目文档

- **[快速开始](../../docs/QUICK_START.md)** — 5 分钟上手指南
- **[Agent 开发指南](../../docs/AGENT_DEV_GUIDE.md)** — 从零创建 Agent
- **[Market API](../../docs/API.md)** — 完整的 REST API 参考
- **[安全模型](../../docs/SECURITY.md)** — 安全策略与沙箱机制
- **[排错手册](../../docs/TROUBLESHOOTING.md)** — 常见问题与解决方案
- **[架构设计](../../ARCHITECTURE.md)** — Agent Gateway 架构详解

---

## 核心概念

### Agent Package

Agent 包是包含 agent.json v3 + worker.yaml 及相关文件的压缩包（.tar.gz），用于在 Market 中分发。

**基本结构**:
```
my-agent/
├── agent.json          # 必需：Agent 元数据 (v3 schema)
├── worker.yaml         # 必需：Pipeline 工作流定义
├── skills/             # 可选：内置 Skills（*.yaml WorkerYaml 定义）
├── mcp/                # 可选：MCP Server 配置 (config.json/servers.json)
├── README.md           # 推荐：使用说明
└── resources/          # 可选：资源文件
```

### Market API

Market 提供 RESTful API，支持：
- 搜索和发现 Agent（语义搜索 + 能力匹配）
- 上传和下载 Agent 包（安全扫描 + SHA-256 校验）
- **Skills 市场：全市场 Skills 浏览、搜索、独立注册**
- **MCP Servers 市场：全市场 MCP 浏览、搜索、独立注册**
- 评分和评论（1-5 星）
- Agent 生命周期管理（弃用/下架）
- API Key 管理（SHA-256 哈希存储）
- **Agent 发现协议：按 skill/mcp_server/has_skill/has_mcp 维度发现**

### 角色权限

| 角色 | 搜索 | 下载 | 上传 | 评分 | 删除 | 管理 Key |
|------|------|------|------|------|------|----------|
| anonymous | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ |
| publisher | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ |
| admin | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| master | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |

---

## 相关项目

- **[agent-hub](https://github.com/openpeng/agent-hub)** — Agent Hub 主项目
  - Market: Agent 注册、搜索、下载、评分
  - Deploy: agent.json → 9 AI 工具格式
  - Runtime: Pipeline 引擎 + 9 内置工具 + 子Agent 编排

---

**最后更新**: 2026-06-12
