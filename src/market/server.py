"""
市场服务 - FastAPI 服务主入口
==============================
提供完整的 RESTful API，包括 Agent CRUD、搜索、下载、评分等功能。
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from .auth import generate_api_key, hash_api_key, verify_api_key, make_api_key_dependency, make_admin_key_dependency
from .verify import verify_package, verify_tar_safety, compute_sha256
from .database import MarketDatabase
from .models import (
    AgentListResponse, AgentListItem, AgentRegisterResponse,
    AgentResponse, BatchAgentResponse,
    RatingCreateRequest, RatingResponse, RatingListResponse,
    HealthResponse, ApiKeyCreateRequest, ApiKeyResponse,
    ErrorResponse,
    SkillInfo, MCPInfo,
    SkillCreateRequest, SkillMarketItem, SkillMarketListResponse, SkillDetailResponse,
    MCPServerCreateRequest, MCPServerMarketItem, MCPServerMarketListResponse, MCPServerDetailResponse,
    ResyncResponse,
    TeamResponse, TeamListItem, TeamListResponse, TeamRegisterResponse,
    WorkflowResponse, WorkflowListItem, WorkflowListResponse, WorkflowRegisterResponse,
    UnifiedSearchResponse,
    VersionInfo, VersionListResponse, VersionDetailResponse,
)
from .package import (pack_agent, unpack_agent, extract_metadata, extract_team_metadata,
    extract_workflow_metadata, detect_package_type, create_package_stream, get_package_size)
from .search import build_search_params
from .skills_mcp import extract_skills_info, extract_mcp_info
from .discovery import discover_agents

# ============================================================
# 全局状态
# ============================================================

app = FastAPI(
    title="PilotDeck Market Service",
    description="Agent 市场服务 - 注册、搜索、下载、评分 Agent 包 (v3.1)",
    version="1.1.0",
)

# CORS 中间件 — 使用具体 origin 避免与反向代理重复添加 header
# 如果 nginx/CDN 已配置 CORS，可注释掉此中间件，避免 Access-Control-Allow-Origin 重复
app.add_middleware(
    CORSMiddleware,
)

# 禁用浏览器缓存（开发阶段），确保每次刷新都获取最新文件
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class NoCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # 对所有 HTML / JS / CSS 响应禁用缓存
        ct = response.headers.get("content-type", "")
        if "text/html" in ct or "text/css" in ct or "javascript" in ct:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response

app.add_middleware(NoCacheMiddleware)

# 服务状态
_server_start_time = time.time()
_db: MarketDatabase | None = None
_data_dir: str = "./data/market"
_packages_dir: str = "./data/market/packages"
_static_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
_frontend_dir: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

# 静态文件服务（前端 SPA）
if os.path.isdir(_frontend_dir):
    app.mount("/app", StaticFiles(directory=_frontend_dir, html=True), name="frontend")

# 根路径重定向到前端
@app.get("/")
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/app/")


# ============================================================
# 依赖注入
# ============================================================

def get_db() -> MarketDatabase:
    """获取数据库实例"""
    if _db is None:
        raise HTTPException(status_code=503, detail="数据库未初始化")
    return _db


# 认证依赖
verify_publisher = make_api_key_dependency(get_db)
verify_admin = make_admin_key_dependency(get_db)


# ============================================================
# 启动/关闭事件
# ============================================================

@app.on_event("startup")
async def startup():
    """服务启动时初始化数据库"""
    global _db
    db_path = os.path.join(_data_dir, "market.db")
    _db = MarketDatabase(db_path)
    await _db.connect()
    await _db.initialize()

    # 确保包存储目录存在
    os.makedirs(_packages_dir, exist_ok=True)


@app.on_event("shutdown")
async def shutdown():
    """服务关闭时关闭数据库连接"""
    global _db
    if _db:
        await _db.close()


# ============================================================
# API 端点
# ============================================================

# ─── 前端入口 ───

@app.get("/")
async def root():
    """前端入口页面"""
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(
            index_path,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"message": "PilotDeck Market Service", "docs": "/docs"}

# ─── 健康检查 ───

@app.get("/api/v1/health", response_model=HealthResponse)
async def health_check():
    """健康检查"""
    db = get_db()
    stats = await db.health_stats()
    return HealthResponse(
        status="ok",
        version="1.1.0",
        agents_count=stats["agents_count"],
        teams_count=stats.get("teams_count", 0),
        workflows_count=stats.get("workflows_count", 0),
        uptime=time.time() - _server_start_time,
    )


# ─── Agent 发现 ───

@app.get("/api/v1/discover")
async def discover(
    capability: Optional[str] = Query(None, description="按能力筛选"),
    category: Optional[str] = Query(None, description="按分类筛选"),
    format: Optional[str] = Query(None, alias="format", description="按格式筛选"),
    skill: Optional[str] = Query(None, description="按 Skill 名称筛选"),
    mcp_server: Optional[str] = Query(None, description="按 MCP Server 名称筛选"),
    has_skill: Optional[str] = Query(None, description="过滤有 Skill 的 Agent"),
    has_mcp: Optional[str] = Query(None, description="过滤有 MCP 依赖的 Agent"),
):
    """Agent 发现协议 - 发现市场上的可用 Agent 及其能力"""
    db = get_db()
    return await discover_agents(
        db,
        capability=capability,
        category=category,
        fmt=format,
        skill=skill,
        mcp_server=mcp_server,
        has_skill=has_skill,
        has_mcp=has_mcp,
    )


# ─── Agent 注册 ───

@app.post("/api/v1/agents", status_code=201, response_model=AgentRegisterResponse)
async def register_agent(
    file: UploadFile = File(...),
    force: bool = Form(False),
    auth: dict = Depends(verify_publisher),
):
    """注册（发布）新 Agent 包

    上传 tar.gz 或 zip 包文件，解析 agent.json 并注册到市场。
    """
    db = get_db()

    # 验证文件格式
    filename = file.filename or ""
    if not (filename.endswith(".tar.gz") or filename.endswith(".zip")):
        raise HTTPException(
            status_code=400,
            detail="包格式无效，仅支持 .tar.gz 或 .zip 格式",
        )

    # 保存上传文件到临时目录
    with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Tar.gz safety check (path traversal, symlinks)
        ok, safety_errors = verify_tar_safety(Path(tmp_path))
        if not ok:
            raise HTTPException(
                status_code=400,
                detail=f"包安全检查失败: {'; '.join(safety_errors)}",
            )

        # 提取元数据
        try:
            metadata = extract_metadata(tmp_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HTTPException(
                status_code=400,
                detail=f"包格式无效或agent.json缺失: {e}",
            )

        # Validate agent.json structure and quality
        # Extract to temp dir for full validation and skills/mcp extraction
        import tempfile as tmpfilemod
        import tarfile
        with tmpfilemod.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(extract_path)
            ok, verify_errors = verify_package(extract_path)
            if not ok:
                raise HTTPException(
                    status_code=400,
                    detail=f"Agent 校验失败: {'; '.join(verify_errors)}",
                )

            # 找到解压后的 Agent 目录（tar.gz 通常包一层目录）
            extracted_dirs = [d for d in extract_path.iterdir() if d.is_dir()]
            agent_extract_dir = extracted_dirs[0] if len(extracted_dirs) == 1 else extract_path

            # 提取 skills 和 MCP 信息（传入解压目录以支持文件系统格式）
            skills = extract_skills_info(metadata, agent_extract_dir)
            mcp_list = extract_mcp_info(metadata, agent_extract_dir)

        identity = metadata.get("identity", {})
        agent_name = identity.get("name", "")
        agent_version = identity.get("version", "1.0.0")
        agent_id = agent_name  # 使用 name 作为 id

        # 检查是否已存在
        existing = await db.get_agent(agent_id)
        if existing:
            if existing["version"] == agent_version and not force:
                raise HTTPException(
                    status_code=409,
                    detail=f"Agent '{agent_id}' 版本 {agent_version} 已存在。使用 force=true 覆盖",
                )

        # 将包文件复制到包存储目录
        package_filename = f"{agent_name}-v{agent_version}.tar.gz"
        if filename.endswith(".zip"):
            package_filename = f"{agent_name}-v{agent_version}.zip"

        target_path = os.path.join(_packages_dir, package_filename)
        shutil.copy2(tmp_path, target_path)

        # Compute SHA-256 digest for download integrity verification
        sha256 = compute_sha256(Path(target_path))

        # 解析 tags 和 dependencies
        tags = []
        if "tags" in metadata:
            tags = metadata["tags"]
        # 也尝试从 .market.yml 读取，但简单起见从 metadata 读取

        deps = metadata.get("dependencies", {})

        # 构建 agent data
        agent_data = {
            "id": agent_id,
            "name": agent_name,
            "display_name": metadata.get("display_name", metadata.get("identity", {}).get("display_name", agent_name)),
            "version": agent_version,
            "description": identity.get("description", ""),
            "author": identity.get("author", ""),
            "category": metadata.get("category", "general"),
            "type": metadata.get("type", "agent"),
            "tags": tags,
            "package_path": target_path,
            "package_size": os.path.getsize(target_path),
            "package_format": "tar.gz" if filename.endswith(".tar.gz") else "zip",
            "package_sha256": sha256,
            "json_content": json.dumps(metadata, ensure_ascii=False),
            "dependencies": deps,
            "homepage_url": metadata.get("homepage_url", ""),
            "source_url": metadata.get("source_url", ""),
            "license": metadata.get("license", "MIT"),
            "readme": metadata.get("readme", ""),
        }

        if existing:
            # 更新
            await db.update_agent(agent_id, agent_data)
        else:
            # 插入
            await db.insert_agent(agent_data)

        # 记录版本历史
        await db.record_version("agent", agent_id, agent_data)

        # 同步 skills 和 MCP 到独立表
        for skill in skills:
            await db.upsert_skill(skill)
        await db.sync_agent_skills(agent_id, [s["id"] for s in skills])

        for mcp in mcp_list:
            await db.upsert_mcp_server(mcp)
        await db.sync_agent_mcp_servers(agent_id, [m["id"] for m in mcp_list])

        return AgentRegisterResponse(
            id=agent_id,
            name=agent_name,
            version=agent_version,
            package_size=agent_data["package_size"],
            package_format=agent_data["package_format"],
            created_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

    finally:
        # 清理临时文件
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.post("/api/v1/agents/resync", response_model=ResyncResponse)
async def resync_agents_skills_mcp(
    auth: dict = Depends(verify_admin),
):
    """重新同步所有 Agent 的 skills 和 MCP 数据

    从现有 agents 表的 json_content 中重新提取 skills 和 MCP server 信息，
    并同步到独立的 skills/mcp_servers 表和关联表中。
    用于从旧版本市场迁移或数据修复场景。
    """
    db = get_db()
    result = await db.resync_skills_mcp()
    return ResyncResponse(**result)


# ─── 批量查询（必须放在 /agents/{agent_id} 之前） ───

@app.get("/api/v1/agents/batch", response_model=BatchAgentResponse)
async def batch_get_agents(
    ids: str = Query(..., description="逗号分隔的 Agent ID 列表"),
):
    """批量查询 Agent（CLI 优化）"""
    db = get_db()
    agent_ids = [i.strip() for i in ids.split(",") if i.strip()]
    if not agent_ids:
        raise HTTPException(status_code=400, detail="ids 参数不能为空")

    agents = await db.batch_get_agents(agent_ids)
    result = {}
    for agent_id, agent_data in agents.items():
        if agent_data:
            result[agent_id] = AgentResponse(**agent_data)
        else:
            result[agent_id] = None

    return BatchAgentResponse(agents=result)


# ─── Agent 详情 ───

@app.get("/api/v1/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: str):
    """获取 Agent 详情"""
    db = get_db()
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    # 从关联表加载 skills 和 MCP 信息
    agent["skills_info"] = await db.get_agent_skills(agent_id)
    agent["mcp_info"] = await db.get_agent_mcp_servers(agent_id)
    return AgentResponse(**agent)


# ─── Agent 搜索/列表 ───

@app.get("/api/v1/agents", response_model=AgentListResponse)
async def list_agents(
    q: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    type: str = Query("", alias="type", description="类型过滤"),
    tags: str = Query("", description="标签过滤（逗号分隔）"),
    skill: str = Query("", description="按 Skill 名称筛选"),
    mcp: str = Query("", description="按 MCP Server 名称筛选"),
    sort: str = Query("downloads", description="排序字段: downloads, rating, created, name"),
    order: str = Query("desc", description="排序方向: asc, desc"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """搜索 Agent 列表"""
    db = get_db()

    search_params = build_search_params(
        q=q, category=category, agent_type=type,
        tags=tags, sort=sort, order=order,
        page=page, page_size=page_size,
    )

    total, items = await db.list_agents(
        q=search_params["q"],
        category=search_params["category"],
        agent_type=search_params["agent_type"],
        tags=search_params["tags"],
        sort=search_params["sort"],
        order=search_params["order"],
        page=search_params["page"],
        page_size=search_params["page_size"],
        skill=skill if skill else None,
        mcp=mcp if mcp else None,
    )

    # 附加 skill_count 和 mcp_server_count
    result_items = []
    for item in items:
        agent_id = item["id"]
        item["skill_count"] = len(await db.get_agent_skills(agent_id))
        item["mcp_server_count"] = len(await db.get_agent_mcp_servers(agent_id))
        result_items.append(AgentListItem(**item))

    return AgentListResponse(
        total=total,
        page=search_params["page"],
        page_size=search_params["page_size"],
        items=result_items,
    )


# ─── 下载 Agent ───

@app.get("/api/v1/agents/{agent_id}/download")
async def download_agent(
    agent_id: str,
    x_forwarded_for: str = Header(None, alias="X-Forwarded-For"),
    user_agent: str = Header(None),
):
    """下载 Agent 包文件"""
    db = get_db()
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    package_path = agent.get("package_path", "")
    if not package_path or not os.path.exists(package_path):
        raise HTTPException(status_code=404, detail="Agent 包文件未找到")

    # 记录下载
    client_ip = x_forwarded_for or ""
    await db.increment_download(agent_id, client_ip, user_agent or "")

    # 生成下载流，携带 SHA-256 Digest 头
    filename = f"{agent_id}-v{agent['version']}.{agent['package_format']}"
    sha256 = agent.get("package_sha256", "")
    response = create_package_stream(package_path, filename)
    if sha256:
        response.headers["Digest"] = f"sha-256={sha256}"
        response.headers["X-Content-SHA256"] = sha256
    return response


# ─── 删除 Agent ───

@app.delete("/api/v1/agents/{agent_id}", status_code=204)
async def delete_agent(
    agent_id: str,
    auth: dict = Depends(verify_admin),
):
    """删除 Agent"""
    db = get_db()
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    # 删除包文件
    package_path = agent.get("package_path", "")
    if package_path and os.path.exists(package_path):
        os.unlink(package_path)

    # 删除数据库记录
    await db.delete_agent(agent_id)


# ─── 评分 ───

@app.post("/api/v1/agents/{agent_id}/ratings", status_code=201, response_model=RatingResponse)
async def rate_agent(
    agent_id: str,
    rating: RatingCreateRequest,
    auth: dict = Depends(verify_publisher),
):
    """为 Agent 评分"""
    db = get_db()

    # 检查 Agent 是否存在
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    # 使用 API Key 的 owner 作为 user_id
    user_id = auth.get("owner", "anonymous")

    result = await db.add_rating(agent_id, user_id, rating.score, rating.comment)
    return RatingResponse(**result)


@app.get("/api/v1/agents/{agent_id}/ratings", response_model=RatingListResponse)
async def get_agent_ratings(
    agent_id: str,
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=50, description="每页条数"),
):
    """获取 Agent 评分列表"""
    db = get_db()

    # 检查 Agent 是否存在
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    total, average, items = await db.get_ratings(agent_id, page, page_size)

    return RatingListResponse(
        total=total,
        average=average,
        page=page,
        page_size=page_size,
        items=[RatingResponse(**item) for item in items],
    )


# ─── 弃用 Agent ───

@app.post("/api/v1/agents/{agent_id}/deprecate")
async def deprecate_agent(
    agent_id: str,
    message: str = Form(...),
    replaced_by: str = Form(""),
    auth: dict = Depends(verify_publisher),
):
    """将 Agent 标记为已弃用"""
    db = get_db()
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    await db._conn.execute(
        "UPDATE agents SET status='deprecated', deprecated_at=?, deprecation_message=?, replaced_by=? WHERE id=?",
        (now, message, replaced_by, agent_id)
    )
    await db._conn.commit()

    return {"ok": True, "agent_id": agent_id, "status": "deprecated", "message": message}


# ─── API Key 管理 ───

@app.post("/api/v1/api-keys", status_code=201, response_model=ApiKeyResponse)
async def create_api_key(
    req: ApiKeyCreateRequest,
    authorization: str = Header(None),
):
    """创建新的 API Key（需要 Master Key 或已有 Admin Key）"""
    db = get_db()
    master_key = os.environ.get("MARKET_MASTER_KEY", "")

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
        # 验证是否是 master key
        if master_key and token == master_key:
            pass  # master key 通过
        else:
            # 验证 API Key (hash-based)
            key_info = await verify_api_key(authorization, db)
            if key_info is None:
                raise HTTPException(status_code=401, detail="无效的 API Key")
            if key_info.get("role") != "admin":
                raise HTTPException(status_code=403, detail="需要 admin 权限")
    elif master_key:
        raise HTTPException(status_code=401, detail="缺少 Authorization header")
    else:
        # 未设置 master key 时，允许首次创建
        existing_keys = await db.list_api_keys()
        if existing_keys:
            raise HTTPException(status_code=401, detail="需要 Authorization header")

    # 生成 Key — 返回明文 Key 一次，存储哈希
    new_key = generate_api_key()
    key_hash = hash_api_key(new_key)
    result = await db.create_api_key(new_key, key_hash, req.owner, req.role.value)
    return ApiKeyResponse(key=new_key, owner=result["owner"], role=result["role"], created_at=result["created_at"])


@app.get("/api/v1/api-keys", response_model=list[ApiKeyResponse])
async def list_api_keys(
    auth: dict = Depends(verify_admin),
):
    """列出所有 API Keys"""
    db = get_db()
    keys = await db.list_api_keys()
    return [
        ApiKeyResponse(key=k.get("key", k.get("key_hash", ""))[:16] + "...", owner=k["owner"], role=k["role"], created_at=k["created_at"])
        for k in keys
        for k in keys if k["enabled"]
    ]


@app.delete("/api/v1/api-keys/{key}", status_code=204)
async def revoke_api_key(
    key: str,
    auth: dict = Depends(verify_admin),
):
    """撤销 API Key"""
    db = get_db()
    success = await db.revoke_api_key(key)
    if not success:
        raise HTTPException(status_code=404, detail="API Key 未找到")


# ============================================================
# Skills & MCP Servers 市场级管理
# ============================================================

# ─── Skills ───

@app.get("/api/v1/skills", response_model=SkillMarketListResponse)
async def list_skills(
    q: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """列出全市场所有 Skills"""
    db = get_db()
    total, items = await db.list_skills(q=q, category=category, page=page, page_size=page_size)
    return SkillMarketListResponse(
        total=total, page=page, page_size=page_size,
        skills=[SkillMarketItem(**item) for item in items],
    )


@app.get("/api/v1/skills/{skill_id}", response_model=SkillDetailResponse)
async def get_skill_detail(skill_id: str):
    """获取 Skill 详情 + 关联 Agent 列表"""
    db = get_db()
    skill = await db.get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 未找到")
    agents = await db.get_skill_agents(skill_id)
    return SkillDetailResponse(**skill, agents=agents)


@app.post("/api/v1/skills", status_code=201)
async def register_skill(
    data: SkillCreateRequest,
    auth: dict = Depends(verify_publisher),
):
    """独立注册 Skill"""
    db = get_db()
    skill_dict = data.model_dump()
    await db.upsert_skill(skill_dict)
    return {"ok": True, "id": skill_dict["id"]}


@app.post("/api/v1/skills/upload", status_code=201)
async def upload_skill(
    file: UploadFile = File(...),
    force: bool = Form(False),
    auth: dict = Depends(verify_publisher),
):
    """上传 Skill 包（v3.1 新增）

    上传 tar.gz 或 zip 包文件，解析 skill.json 并注册到市场。
    """
    db = get_db()
    filename = file.filename or ""
    if not (filename.endswith(".tar.gz") or filename.endswith(".zip")):
        raise HTTPException(status_code=400, detail="包格式无效，仅支持 .tar.gz 或 .zip 格式")

    with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from .package import extract_skill_metadata
        from .verify import verify_skill_package

        ok, safety_errors = verify_tar_safety(Path(tmp_path))
        if not ok:
            raise HTTPException(status_code=400, detail=f"包安全检查失败: {'; '.join(safety_errors)}")

        try:
            metadata = extract_skill_metadata(tmp_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"包格式无效或 skill.json 缺失: {e}")

        import tempfile as tmpfilemod
        import tarfile
        with tmpfilemod.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(extract_path)
            ok, verify_errors = verify_skill_package(extract_path)
            if not ok:
                raise HTTPException(status_code=400, detail=f"Skill 校验失败: {'; '.join(verify_errors)}")

        identity = metadata.get("identity", {})
        skill_name = identity.get("name", "")
        skill_version = identity.get("version", "1.0.0")
        skill_id = skill_name

        existing = await db.get_skill(skill_id)
        if existing:
            if existing["version"] == skill_version and not force:
                raise HTTPException(status_code=409, detail=f"Skill '{skill_id}' 版本 {skill_version} 已存在。使用 force=true 覆盖")

        package_filename = f"{skill_name}-v{skill_version}.tar.gz"
        if filename.endswith(".zip"):
            package_filename = f"{skill_name}-v{skill_version}.zip"

        target_path = os.path.join(_packages_dir, package_filename)
        shutil.copy2(tmp_path, target_path)

        sha256 = compute_sha256(Path(target_path))
        tags = metadata.get("tags", [])

        # 读取 SKILL.md 内容（如果 content.source == "file"）
        skill_content = ""
        content_cfg = metadata.get("content", {})
        if content_cfg.get("source") == "file":
            skill_file = content_cfg.get("file", "SKILL.md")
            # 从临时解压目录读取
            with tmpfilemod.TemporaryDirectory() as extract_dir:
                extract_path = Path(extract_dir)
                with tarfile.open(tmp_path, "r:gz") as tar:
                    tar.extractall(extract_path)
                extracted_dirs = [d for d in extract_path.iterdir() if d.is_dir()]
                skill_dir = extracted_dirs[0] if len(extracted_dirs) == 1 else extract_path
                skill_md_path = skill_dir / skill_file
                if skill_md_path.exists():
                    with open(skill_md_path, encoding="utf-8") as f:
                        skill_content = f.read()

        skill_data = {
            "id": skill_id,
            "original_name": skill_name,
            "display_name": identity.get("display_name", skill_name),
            "description": identity.get("description", ""),
            "version": skill_version,
            "category": metadata.get("identity", {}).get("category", "general"),
            "icon": metadata.get("identity", {}).get("icon", ""),
            "package_path": os.path.abspath(target_path),
            "package_size": os.path.getsize(target_path),
            "package_format": "tar.gz" if filename.endswith(".tar.gz") else "zip",
            "content_format": content_cfg.get("format", "markdown"),
            "content_source": content_cfg.get("source", "inline"),
            "content": skill_content,
        }

        if existing:
            await db.upsert_skill(skill_data)
        else:
            await db.upsert_skill(skill_data)

        return {
            "id": skill_id,
            "name": skill_name,
            "version": skill_version,
            "package_size": skill_data["package_size"],
            "package_format": skill_data["package_format"],
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/api/v1/skills/{skill_id}/download")
async def download_skill(skill_id: str):
    """下载 Skill 包文件（v3.1 新增）"""
    db = get_db()
    skill = await db.get_skill(skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 未找到")
    package_path = skill.get("package_path", "")
    if not package_path or not os.path.exists(package_path):
        raise HTTPException(status_code=404, detail="Skill 包文件未找到")
    filename = f"{skill_id}-v{skill['version']}.{skill.get('package_format', 'tar.gz')}"
    return create_package_stream(package_path, filename)


@app.delete("/api/v1/skills/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str,
    auth: dict = Depends(verify_admin),
):
    """删除 Skill"""
    db = get_db()
    if not await db.delete_skill(skill_id):
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' 未找到")


# ─── MCP Servers ───

@app.get("/api/v1/mcp-servers", response_model=MCPServerMarketListResponse)
async def list_mcp_servers(
    q: str = Query("", description="搜索关键词"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
):
    """列出全市场所有 MCP Servers"""
    db = get_db()
    total, items = await db.list_mcp_servers(q=q, page=page, page_size=page_size)
    return MCPServerMarketListResponse(
        total=total, page=page, page_size=page_size,
        servers=[MCPServerMarketItem(**item) for item in items],
    )


@app.get("/api/v1/mcp-servers/{server_id}", response_model=MCPServerDetailResponse)
async def get_mcp_server_detail(server_id: str):
    """获取 MCP Server 详情 + 关联 Agent 列表"""
    db = get_db()
    mcp = await db.get_mcp_server(server_id)
    if mcp is None:
        raise HTTPException(status_code=404, detail=f"MCP Server '{server_id}' 未找到")
    agents = await db.get_mcp_server_agents(server_id)
    return MCPServerDetailResponse(**mcp, agents=agents)


@app.post("/api/v1/mcp-servers", status_code=201)
async def register_mcp_server(
    data: MCPServerCreateRequest,
    auth: dict = Depends(verify_publisher),
):
    """独立注册 MCP Server"""
    db = get_db()
    mcp_dict = data.model_dump()
    await db.upsert_mcp_server(mcp_dict)
    return {"ok": True, "id": mcp_dict["id"]}


@app.post("/api/v1/mcp-servers/upload", status_code=201)
async def upload_mcp_server(
    file: UploadFile = File(...),
    force: bool = Form(False),
    auth: dict = Depends(verify_publisher),
):
    """上传 MCP Server 包（v3.1 新增）

    上传 tar.gz 或 zip 包文件，解析 mcp-server.json 并注册到市场。
    """
    db = get_db()
    filename = file.filename or ""
    if not (filename.endswith(".tar.gz") or filename.endswith(".zip")):
        raise HTTPException(status_code=400, detail="包格式无效，仅支持 .tar.gz 或 .zip 格式")

    with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from .package import extract_mcp_metadata
        from .verify import verify_mcp_package

        ok, safety_errors = verify_tar_safety(Path(tmp_path))
        if not ok:
            raise HTTPException(status_code=400, detail=f"包安全检查失败: {'; '.join(safety_errors)}")

        try:
            metadata = extract_mcp_metadata(tmp_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"包格式无效或 mcp-server.json 缺失: {e}")

        import tempfile as tmpfilemod
        import tarfile
        with tmpfilemod.TemporaryDirectory() as extract_dir:
            extract_path = Path(extract_dir)
            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(extract_path)
            ok, verify_errors = verify_mcp_package(extract_path)
            if not ok:
                raise HTTPException(status_code=400, detail=f"MCP Server 校验失败: {'; '.join(verify_errors)}")

        identity = metadata.get("identity", {})
        mcp_name = identity.get("name", "")
        mcp_version = identity.get("version", "1.0.0")
        mcp_id = mcp_name

        existing = await db.get_mcp_server(mcp_id)
        if existing:
            if existing["version"] == mcp_version and not force:
                raise HTTPException(status_code=409, detail=f"MCP Server '{mcp_id}' 版本 {mcp_version} 已存在。使用 force=true 覆盖")

        package_filename = f"{mcp_name}-v{mcp_version}.tar.gz"
        if filename.endswith(".zip"):
            package_filename = f"{mcp_name}-v{mcp_version}.zip"

        target_path = os.path.join(_packages_dir, package_filename)
        shutil.copy2(tmp_path, target_path)

        # 读取 mcp-config.json 内容
        config_content = ""
        config_cfg = metadata.get("config", {})
        if config_cfg.get("source") == "file":
            config_file = config_cfg.get("file", "mcp-config.json")
            with tmpfilemod.TemporaryDirectory() as extract_dir:
                extract_path = Path(extract_dir)
                with tarfile.open(tmp_path, "r:gz") as tar:
                    tar.extractall(extract_path)
                extracted_dirs = [d for d in extract_path.iterdir() if d.is_dir()]
                mcp_dir = extracted_dirs[0] if len(extracted_dirs) == 1 else extract_path
                config_path = mcp_dir / config_file
                if config_path.exists():
                    with open(config_path, encoding="utf-8") as f:
                        config_content = f.read()

        mcp_data = {
            "id": mcp_id,
            "original_name": mcp_name,
            "description": identity.get("description", ""),
            "version": mcp_version,
            "command": "",
            "args": [],
            "package": identity.get("package", ""),
            "tools": metadata.get("tools", []),
            "required_env": metadata.get("required_env", []),
            "package_path": os.path.abspath(target_path),
            "package_size": os.path.getsize(target_path),
            "package_format": "tar.gz" if filename.endswith(".tar.gz") else "zip",
            "config_content": config_content,
        }

        await db.upsert_mcp_server(mcp_data)

        return {
            "id": mcp_id,
            "name": mcp_name,
            "version": mcp_version,
            "package_size": mcp_data["package_size"],
            "package_format": mcp_data["package_format"],
            "created_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/api/v1/mcp-servers/{server_id}/download")
async def download_mcp_server(server_id: str):
    """下载 MCP Server 包文件（v3.1 新增）"""
    db = get_db()
    mcp = await db.get_mcp_server(server_id)
    if mcp is None:
        raise HTTPException(status_code=404, detail=f"MCP Server '{server_id}' 未找到")
    package_path = mcp.get("package_path", "")
    if not package_path or not os.path.exists(package_path):
        raise HTTPException(status_code=404, detail="MCP Server 包文件未找到")
    filename = f"{server_id}-v{mcp['version']}.{mcp.get('package_format', 'tar.gz')}"
    return create_package_stream(package_path, filename)


@app.delete("/api/v1/mcp-servers/{server_id}", status_code=204)
async def delete_mcp_server(
    server_id: str,
    auth: dict = Depends(verify_admin),
):
    """删除 MCP Server"""
    db = get_db()
    if not await db.delete_mcp_server(server_id):
        raise HTTPException(status_code=404, detail=f"MCP Server '{server_id}' 未找到")


# ============================================================
# Team API
# ============================================================

@app.post("/api/v1/teams", status_code=201, response_model=TeamRegisterResponse)
async def register_team(
    file: UploadFile = File(...),
    force: bool = Form(False),
    auth: dict = Depends(verify_publisher),
):
    """注册（发布）新 Team 包"""
    db = get_db()
    filename = file.filename or ""
    if not (filename.endswith(".tar.gz") or filename.endswith(".zip")):
        raise HTTPException(status_code=400, detail="包格式无效，仅支持 .tar.gz 或 .zip 格式")

    with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        ok, safety_errors = verify_tar_safety(Path(tmp_path))
        if not ok:
            raise HTTPException(status_code=400, detail=f"包安全检查失败: {'; '.join(safety_errors)}")

        try:
            metadata = extract_team_metadata(tmp_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"包格式无效或 team.json 缺失: {e}")

        identity = metadata.get("identity", {})
        team_name = identity.get("name", "")
        team_version = identity.get("version", "1.0.0")
        team_id = team_name

        existing = await db.get_team(team_id)
        if existing:
            if existing["version"] == team_version and not force:
                raise HTTPException(status_code=409, detail=f"Team '{team_id}' 版本 {team_version} 已存在。使用 force=true 覆盖")

        package_filename = f"{team_name}-v{team_version}.tar.gz"
        if filename.endswith(".zip"):
            package_filename = f"{team_name}-v{team_version}.zip"

        target_path = os.path.join(_packages_dir, package_filename)
        shutil.copy2(tmp_path, target_path)

        sha256 = compute_sha256(Path(target_path))
        tags = metadata.get("tags", [])
        deps = metadata.get("dependencies", {})

        team_data = {
            "id": team_id, "name": team_name, "version": team_version,
            "display_name": identity.get("display_name", team_name),
            "description": identity.get("description", ""),
            "author": identity.get("author", ""),
            "category": metadata.get("category", "general"),
            "type": metadata.get("type", "team"),
            "tags": tags, "package_path": target_path,
            "package_size": os.path.getsize(target_path),
            "package_format": "tar.gz" if filename.endswith(".tar.gz") else "zip",
            "package_sha256": sha256,
            "json_content": json.dumps(metadata, ensure_ascii=False),
            "dependencies": deps,
            "homepage_url": identity.get("homepage_url", ""),
            "source_url": identity.get("source_url", ""),
            "license": identity.get("license", "MIT"),
            "readme": metadata.get("readme", ""),
        }

        if existing:
            await db.update_team(team_id, team_data)
        else:
            await db.insert_team(team_data)

        # 记录版本历史
        await db.record_version("team", team_id, team_data)

        return TeamRegisterResponse(
            id=team_id, name=team_name, version=team_version,
            package_size=team_data["package_size"],
            package_format=team_data["package_format"],
            created_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/api/v1/teams/{team_id}", response_model=TeamResponse)
async def get_team(team_id: str):
    """获取 Team 详情"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    return TeamResponse(**team)


@app.get("/api/v1/teams", response_model=TeamListResponse)
async def list_teams(
    q: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    tags: str = Query("", description="标签过滤（逗号分隔）"),
    sort: str = Query("downloads", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    """搜索 Team 列表"""
    db = get_db()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    total, items = await db.list_teams(q=q, category=category, tags=tag_list,
                                        sort=sort, order=order, page=page, page_size=page_size)
    return TeamListResponse(total=total, page=page, page_size=page_size,
                            items=[TeamListItem(**item) for item in items])


@app.get("/api/v1/teams/{team_id}/download")
async def download_team(team_id: str,
    x_forwarded_for: str = Header(None), user_agent: str = Header(None),
):
    """下载 Team 包文件"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    package_path = team.get("package_path", "")
    if not package_path or not os.path.exists(package_path):
        raise HTTPException(status_code=404, detail="Team 包文件未找到")
    await db.increment_download_team(team_id, x_forwarded_for or "", user_agent or "")
    filename = f"{team_id}-v{team['version']}.{team['package_format']}"
    sha256 = team.get("package_sha256", "")
    response = create_package_stream(package_path, filename)
    if sha256:
        response.headers["Digest"] = f"sha-256={sha256}"
        response.headers["X-Content-SHA256"] = sha256
    return response


@app.delete("/api/v1/teams/{team_id}", status_code=204)
async def delete_team(team_id: str, auth: dict = Depends(verify_admin)):
    """删除 Team"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    package_path = team.get("package_path", "")
    if package_path and os.path.exists(package_path):
        os.unlink(package_path)
    await db.delete_team(team_id)


@app.post("/api/v1/teams/{team_id}/ratings", status_code=201, response_model=RatingResponse)
async def rate_team(team_id: str, rating: RatingCreateRequest, auth: dict = Depends(verify_publisher)):
    """为 Team 评分"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    user_id = auth.get("owner", "anonymous")
    result = await db.add_team_rating(team_id, user_id, rating.score, rating.comment)
    return RatingResponse(**result)


@app.get("/api/v1/teams/{team_id}/ratings", response_model=RatingListResponse)
async def get_team_ratings(team_id: str, page: int = 1, page_size: int = 10):
    """获取 Team 评分列表"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    total, average, items = await db.get_team_ratings(team_id, page, page_size)
    return RatingListResponse(total=total, average=average, page=page,
                              page_size=page_size, items=[RatingResponse(**item) for item in items])


# ============================================================
# Workflow API
# ============================================================

@app.post("/api/v1/workflows", status_code=201, response_model=WorkflowRegisterResponse)
async def register_workflow(
    file: UploadFile = File(...),
    force: bool = Form(False),
    auth: dict = Depends(verify_publisher),
):
    """注册（发布）新 Workflow 包"""
    db = get_db()
    filename = file.filename or ""
    if not (filename.endswith(".tar.gz") or filename.endswith(".zip")):
        raise HTTPException(status_code=400, detail="包格式无效，仅支持 .tar.gz 或 .zip 格式")

    with tempfile.NamedTemporaryFile(delete=False, suffix=filename) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        ok, safety_errors = verify_tar_safety(Path(tmp_path))
        if not ok:
            raise HTTPException(status_code=400, detail=f"包安全检查失败: {'; '.join(safety_errors)}")

        try:
            metadata = extract_workflow_metadata(tmp_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            raise HTTPException(status_code=400, detail=f"包格式无效或 workflow.json 缺失: {e}")

        identity = metadata.get("identity", {})
        workflow_name = identity.get("name", "")
        workflow_version = identity.get("version", "1.0.0")
        workflow_id = workflow_name

        existing = await db.get_workflow(workflow_id)
        if existing:
            if existing["version"] == workflow_version and not force:
                raise HTTPException(status_code=409, detail=f"Workflow '{workflow_id}' 版本 {workflow_version} 已存在。使用 force=true 覆盖")

        package_filename = f"{workflow_name}-v{workflow_version}.tar.gz"
        if filename.endswith(".zip"):
            package_filename = f"{workflow_name}-v{workflow_version}.zip"

        target_path = os.path.join(_packages_dir, package_filename)
        shutil.copy2(tmp_path, target_path)

        sha256 = compute_sha256(Path(target_path))
        tags = metadata.get("tags", [])
        deps = metadata.get("dependencies", {})

        workflow_data = {
            "id": workflow_id, "name": workflow_name, "version": workflow_version,
            "display_name": identity.get("display_name", workflow_name),
            "description": identity.get("description", ""),
            "author": identity.get("author", ""),
            "category": metadata.get("category", "general"),
            "type": metadata.get("type", "workflow"),
            "tags": tags, "package_path": target_path,
            "package_size": os.path.getsize(target_path),
            "package_format": "tar.gz" if filename.endswith(".tar.gz") else "zip",
            "package_sha256": sha256,
            "json_content": json.dumps(metadata, ensure_ascii=False),
            "dependencies": deps,
            "homepage_url": identity.get("homepage_url", ""),
            "source_url": identity.get("source_url", ""),
            "license": identity.get("license", "MIT"),
            "readme": metadata.get("readme", ""),
        }

        if existing:
            await db.update_workflow(workflow_id, workflow_data)
        else:
            await db.insert_workflow(workflow_data)

        # 记录版本历史
        await db.record_version("workflow", workflow_id, workflow_data)

        return WorkflowRegisterResponse(
            id=workflow_id, name=workflow_name, version=workflow_version,
            package_size=workflow_data["package_size"],
            package_format=workflow_data["package_format"],
            created_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


@app.get("/api/v1/workflows/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(workflow_id: str):
    """获取 Workflow 详情"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    return WorkflowResponse(**workflow)


@app.get("/api/v1/workflows", response_model=WorkflowListResponse)
async def list_workflows(
    q: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    tags: str = Query("", description="标签过滤（逗号分隔）"),
    sort: str = Query("downloads", description="排序字段"),
    order: str = Query("desc", description="排序方向"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    """搜索 Workflow 列表"""
    db = get_db()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None
    total, items = await db.list_workflows(q=q, category=category, tags=tag_list,
                                            sort=sort, order=order, page=page, page_size=page_size)
    return WorkflowListResponse(total=total, page=page, page_size=page_size,
                                items=[WorkflowListItem(**item) for item in items])


@app.get("/api/v1/workflows/{workflow_id}/download")
async def download_workflow(workflow_id: str,
    x_forwarded_for: str = Header(None), user_agent: str = Header(None),
):
    """下载 Workflow 包文件"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    package_path = workflow.get("package_path", "")
    if not package_path or not os.path.exists(package_path):
        raise HTTPException(status_code=404, detail="Workflow 包文件未找到")
    await db.increment_download_workflow(workflow_id, x_forwarded_for or "", user_agent or "")
    filename = f"{workflow_id}-v{workflow['version']}.{workflow['package_format']}"
    sha256 = workflow.get("package_sha256", "")
    response = create_package_stream(package_path, filename)
    if sha256:
        response.headers["Digest"] = f"sha-256={sha256}"
        response.headers["X-Content-SHA256"] = sha256
    return response


@app.delete("/api/v1/workflows/{workflow_id}", status_code=204)
async def delete_workflow(workflow_id: str, auth: dict = Depends(verify_admin)):
    """删除 Workflow"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    package_path = workflow.get("package_path", "")
    if package_path and os.path.exists(package_path):
        os.unlink(package_path)
    await db.delete_workflow(workflow_id)


@app.post("/api/v1/workflows/{workflow_id}/ratings", status_code=201, response_model=RatingResponse)
async def rate_workflow(workflow_id: str, rating: RatingCreateRequest, auth: dict = Depends(verify_publisher)):
    """为 Workflow 评分"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    user_id = auth.get("owner", "anonymous")
    result = await db.add_workflow_rating(workflow_id, user_id, rating.score, rating.comment)
    return RatingResponse(**result)


@app.get("/api/v1/workflows/{workflow_id}/ratings", response_model=RatingListResponse)
async def get_workflow_ratings(workflow_id: str, page: int = 1, page_size: int = 10):
    """获取 Workflow 评分列表"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    total, average, items = await db.get_workflow_ratings(workflow_id, page, page_size)
    return RatingListResponse(total=total, average=average, page=page,
                              page_size=page_size, items=[RatingResponse(**item) for item in items])


# ============================================================
# 版本管理 API
# ============================================================

# ─── Agent 版本 ───

@app.get("/api/v1/agents/{agent_id}/versions", response_model=VersionListResponse)
async def list_agent_versions(agent_id: str):
    """列出 Agent 的所有版本"""
    db = get_db()
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")
    versions = await db.list_versions("agent", agent_id)
    return VersionListResponse(versions=[VersionInfo(**v) for v in versions])


@app.get("/api/v1/agents/{agent_id}/versions/{version}", response_model=VersionDetailResponse)
async def get_agent_version(agent_id: str, version: str):
    """获取 Agent 的特定版本详情"""
    db = get_db()
    agent = await db.get_agent(agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 未找到")
    ver = await db.get_version("agent", agent_id, version)
    if ver is None:
        raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' 版本 '{version}' 未找到")
    return VersionDetailResponse(**ver)


# ─── Team 版本 ───

@app.get("/api/v1/teams/{team_id}/versions", response_model=VersionListResponse)
async def list_team_versions(team_id: str):
    """列出 Team 的所有版本"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    versions = await db.list_versions("team", team_id)
    return VersionListResponse(versions=[VersionInfo(**v) for v in versions])


@app.get("/api/v1/teams/{team_id}/versions/{version}", response_model=VersionDetailResponse)
async def get_team_version(team_id: str, version: str):
    """获取 Team 的特定版本详情"""
    db = get_db()
    team = await db.get_team(team_id)
    if team is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 未找到")
    ver = await db.get_version("team", team_id, version)
    if ver is None:
        raise HTTPException(status_code=404, detail=f"Team '{team_id}' 版本 '{version}' 未找到")
    return VersionDetailResponse(**ver)


# ─── Workflow 版本 ───

@app.get("/api/v1/workflows/{workflow_id}/versions", response_model=VersionListResponse)
async def list_workflow_versions(workflow_id: str):
    """列出 Workflow 的所有版本"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    versions = await db.list_versions("workflow", workflow_id)
    return VersionListResponse(versions=[VersionInfo(**v) for v in versions])


@app.get("/api/v1/workflows/{workflow_id}/versions/{version}", response_model=VersionDetailResponse)
async def get_workflow_version(workflow_id: str, version: str):
    """获取 Workflow 的特定版本详情"""
    db = get_db()
    workflow = await db.get_workflow(workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 未找到")
    ver = await db.get_version("workflow", workflow_id, version)
    if ver is None:
        raise HTTPException(status_code=404, detail=f"Workflow '{workflow_id}' 版本 '{version}' 未找到")
    return VersionDetailResponse(**ver)


# ============================================================
# 统一搜索入口
# ============================================================

@app.get("/api/v1/search", response_model=UnifiedSearchResponse)
async def unified_search(
    q: str = Query("", description="搜索关键词"),
    category: str = Query("", description="分类过滤"),
    entity_type: str = Query("", alias="type", description="类型过滤：agent/team/workflow/空=全"),
    tags: str = Query("", description="标签过滤"),
    sort: str = Query("downloads"), order: str = Query("desc"),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    """统一搜索接口，返回 Agents + Teams + Workflows 的混合搜索结果"""
    db = get_db()
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    agents: list[dict] = []
    teams: list[dict] = []
    workflows: list[dict] = []
    total_agents = total_teams = total_workflows = 0

    if entity_type in ("", "agent"):
        total_agents, agents = await db.list_agents(q=q, category=category, tags=tag_list,
                                                     sort=sort, order=order, page=page, page_size=page_size)
    if entity_type in ("", "team"):
        total_teams, teams = await db.list_teams(q=q, category=category, tags=tag_list,
                                                   sort=sort, order=order, page=page, page_size=page_size)
    if entity_type in ("", "workflow"):
        total_workflows, workflows = await db.list_workflows(q=q, category=category, tags=tag_list,
                                                              sort=sort, order=order, page=page, page_size=page_size)

    return UnifiedSearchResponse(
        agents=agents, teams=teams, workflows=workflows,
        total_agents=total_agents, total_teams=total_teams, total_workflows=total_workflows,
    )


# ============================================================
# 启动入口
# ============================================================

def run_server(port: int = 8321, data_dir: str = "./data/market",
               host: str = "0.0.0.0", daemon: bool = False):
    """启动市场服务

    参数:
        port: 监听端口（默认 8321）
        data_dir: 数据目录
        host: 监听地址
        daemon: 是否以守护进程方式启动
    """
    import uvicorn

    global _data_dir, _packages_dir
    _data_dir = data_dir
    _packages_dir = os.path.join(data_dir, "packages")

    if daemon:
        import subprocess
        import sys

        log_file = os.path.join(data_dir, "market.log")
        os.makedirs(os.path.dirname(log_file), exist_ok=True)

        cmd = [
            sys.executable, "-m", "uvicorn",
            "market.server:app",
            "--host", host,
            "--port", str(port),
            "--log-level", "info",
        ]
        with open(log_file, "a") as f:
            proc = subprocess.Popen(
                cmd,
                stdout=f,
                stderr=f,
                start_new_session=True,
            )
        print(f"市场服务已启动 (PID: {proc.pid}), 端口: {port}")
        print(f"日志文件: {log_file}")
        return proc.pid
    else:
        print(f"市场服务启动中... 端口: {port}, 数据目录: {data_dir}")
        uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PilotDeck 市场服务")
    parser.add_argument("--port", type=int, default=8321, help="监听端口")
    parser.add_argument("--data-dir", default="./data/market", help="数据目录")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--daemon", action="store_true", help="以守护进程方式启动")

    args = parser.parse_args()
    run_server(port=args.port, data_dir=args.data_dir,
               host=args.host, daemon=args.daemon)
