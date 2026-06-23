# Market Frontend 开发计划

## 目标
为 PilotDeck Market Service 开发管理后台的 Web 前端界面，涵盖 Agent 浏览、搜索、上传、评分和 API Key 管理等功能。

## 当前状态分析

### 后端 API 已就绪
- `GET /api/v1/health` — 健康检查
- `GET /api/v1/agents` — 搜索/列出 Agent（支持 q, category, type, tags, sort, order, page, page_size）
- `GET /api/v1/agents/{id}` — Agent 详情
- `GET /api/v1/agents/batch?ids=...` — 批量查询
- `POST /api/v1/agents` — 注册 Agent（上传 tar.gz/zip）
- `GET /api/v1/agents/{id}/download` — 下载
- `DELETE /api/v1/agents/{id}` — 删除（需 admin）
- `POST /api/v1/agents/{id}/ratings` — 评分
- `GET /api/v1/agents/{id}/ratings` — 获取评分列表
- `POST /api/v1/api-keys` — 创建 API Key
- `GET /api/v1/api-keys` — 列出 API Keys（需 admin）
- `DELETE /api/v1/api-keys/{key}` — 撤销 API Key（需 admin）

### 前端当前状态
- 无任何前端文件
- 无 static 目录配置
- CORS 已配置 `allow_origins=["*"]`

## 实现方案

### 架构选择：单一 HTML SPA + 静态文件服务

**方案**：在 `src/market/static/` 目录下创建一个完整的单页应用（SPA），使用原生 HTML/CSS/JS，由 FastAPI 提供静态文件服务。

**优势**：
- 零依赖，无需 npm/webpack 等
- 单文件部署，维护简单
- 与后端同端口运行，无 CORS 跨域问题
- FastAPI 原生支持 `StaticFiles` 挂载

### 文件变更清单

| # | 文件 | 操作 | 说明 |
|---|------|------|------|
| 1 | `src/market/static/index.html` | 新建 | 主 SPA 页面（含 CSS + JS） |
| 2 | `src/market/server.py` | 修改 | 添加 `StaticFiles` 挂载，将 `/` 路由指向 `static/index.html` |

### 前端页面设计（3 个标签页）

#### Tab 1: 市场浏览（Market）
- **搜索栏**：关键词输入 + 分类下拉 + 类型下拉 + 标签过滤
- **Agent 卡片网格**：显示名称、版本、描述、分类、下载数、评分星标
- **分页**：上一页/下一页 + 页码显示
- **点击卡片**：弹出详情模态框
  - 完整描述、作者、许可证、标签、依赖
  - 下载按钮
  - 评分区域：星级评分 + 评论列表
  - 删除按钮（需 admin）

#### Tab 2: 上传 Agent（Upload）
- 文件拖拽/选择区域
- 强制覆盖选项（force）
- 上传进度反馈
- 结果展示

#### Tab 3: API Keys
- 创建 Key 表单（owner + role）
- Keys 列表表格
- 撤销按钮

#### 顶部状态栏
- 服务器连接状态指示器
- API Key 输入框
- 健康统计（Agent 总数、运行时间）

### 技术细节

#### CSS
- 使用 CSS 变量实现主题色
- 响应式网格布局（grid-template-columns: repeat(auto-fill, minmax(320px, 1fr))）
- 模态框使用固定定位 + overlay
- 卡片 hover 效果 + 过渡动画
- 评分星星使用 Unicode 字符 ★ ☆

#### JavaScript
- 使用 fetch API 与后端通信
- 状态管理使用简单的全局对象
- API Key 存储在 localStorage
- 所有 API 请求自动携带 Authorization header（如果设置了 API Key）
- 错误统一处理 + toast 提示

## 实施步骤

1. 创建 `src/market/static/` 目录
2. 创建 `src/market/static/index.html` — 完整的 SPA
3. 修改 `src/market/server.py` — 添加 StaticFiles 挂载和主页路由
4. 重启服务器验证效果
5. 用 curl 验证静态文件可访问

## 验证标准
- [ ] 打开 `http://localhost:8321/` 可见前端界面
- [ ] 无需 API Key 可以浏览 Agent 列表
- [ ] 可以搜索/过滤 Agent
- [ ] 上传功能可以正常使用（需要 API Key）
- [ ] API Key 管理功能正常
- [ ] 评分功能正常
