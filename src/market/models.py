"""
市场服务 - Pydantic 数据模型
=============================
定义所�?REST API 的请�?响应模型�?
"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ============================================================
# 枚举类型
# ============================================================

class AgentCategory(str, Enum):
    GENERAL = "general"
    BROWSER = "browser"
    DATA_ANALYSIS = "data_analysis"
    CONTENT_CREATION = "content_creation"
    WEB_SCRAPER = "web_scraper"
    FILE_PROCESSOR = "file_processor"
    AI_CHAT = "ai_chat"
    UTILITY = "utility"
    OTHER = "other"


class AgentType(str, Enum):
    AGENT = "agent"
    SUBAGENT = "subagent"
    SKILL = "skill"
    WORKFLOW = "workflow"


class PackageFormat(str, Enum):
    TAR_GZ = "tar.gz"
    ZIP = "zip"
    DIRECTORY = "directory"


class ApiKeyRole(str, Enum):
    PUBLISHER = "publisher"
    ADMIN = "admin"


# ============================================================
# 请求模型
# ============================================================

class RatingCreateRequest(BaseModel):
    score: int = Field(..., ge=1, le=5, description="评分 1-5")
    comment: str = Field(default="", max_length=500, description="评分评论")


class ApiKeyCreateRequest(BaseModel):
    owner: str = Field(..., min_length=1, max_length=100)
    role: ApiKeyRole = Field(default=ApiKeyRole.PUBLISHER)


# ============================================================
# 响应模型
# ============================================================

class AgentResponse(BaseModel):
    id: str
    name: str
    display_name: str
    version: str
    description: str = ""
    author: str = ""
    category: str = "general"
    type: str = "agent"
    tags: list[str] = Field(default_factory=list)
    package_size: int = 0
    package_format: str = "tar.gz"
    download_count: int = 0
    rating: float = 0.0
    review_count: int = 0
    dependencies: dict = Field(default_factory=dict)
    homepage_url: str = ""
    source_url: str = ""
    license: str = "MIT"
    readme: str = ""
    json_content: str = "{}"
    skills_info: list[SkillInfo] = Field(default_factory=list)
    mcp_info: list[MCPInfo] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    published_at: Optional[str] = None

    class Config:
        from_attributes = True


class AgentListItem(BaseModel):
    id: str
    display_name: str
    version: str
    description: str
    category: str
    tags: list[str] = Field(default_factory=list)
    download_count: int = 0
    rating: float = 0.0
    package_size: int = 0
    skill_count: int = 0
    mcp_server_count: int = 0
    created_at: str = ""


class AgentListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list[AgentListItem] = Field(default_factory=list)


class BatchAgentResponse(BaseModel):
    agents: dict[str, Optional[AgentResponse]] = Field(default_factory=dict)


class AgentRegisterResponse(BaseModel):
    id: str
    name: str
    version: str
    package_size: int
    package_format: str
    created_at: str


class RatingResponse(BaseModel):
    id: int
    agent_id: str
    score: int
    comment: str = ""
    created_at: str = ""


class RatingListResponse(BaseModel):
    total: int = 0
    average: float = 0.0
    page: int = 1
    page_size: int = 10
    items: list[RatingResponse] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
    agents_count: int = 0
    teams_count: int = 0
    workflows_count: int = 0
    uptime: float = 0.0


class ApiKeyResponse(BaseModel):
    key: str
    owner: str
    role: str
    created_at: str = ""


class ApiKeyDetailResponse(BaseModel):
    id: int
    key: str
    owner: str
    role: str
    enabled: bool
    created_at: str = ""


class ErrorResponse(BaseModel):
    detail: str
    error_code: str = ""
    errors: list[str] = Field(default_factory=list)


# ============================================================
# Skill & MCP 模型
# ============================================================

class SkillInfo(BaseModel):
    id: str                         # qualified id: "agent-name/skill-name"
    original_name: str = ""         # 原始 name（不�?agent 前缀�?
    display_name: str = ""
    description: str = ""
    version: str = ""
    category: str = ""
    icon: str = ""


class MCPInfo(BaseModel):
    id: str                         # qualified id: "agent-name/server-name"
    original_name: str = ""         # 原始 name
    description: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    package: str = ""
    tools: list[str] = Field(default_factory=list)
    required_env: list[str] = Field(default_factory=list)


class SkillCreateRequest(BaseModel):
    id: str
    original_name: str = ""
    display_name: str = ""
    description: str = ""
    version: str = ""
    category: str = ""
    icon: str = ""


class MCPServerCreateRequest(BaseModel):
    id: str
    original_name: str = ""
    description: str = ""
    command: str = ""
    args: list[str] = Field(default_factory=list)
    package: str = ""
    tools: list[str] = Field(default_factory=list)
    required_env: list[str] = Field(default_factory=list)


class SkillMarketItem(BaseModel):
    id: str
    original_name: str
    display_name: str
    description: str
    category: str
    agent_count: int = 0


class SkillMarketListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    skills: list[SkillMarketItem] = Field(default_factory=list)


class SkillDetailResponse(BaseModel):
    id: str
    original_name: str
    display_name: str
    description: str
    version: str = ""
    category: str = ""
    agents: list[dict] = Field(default_factory=list)


class MCPServerMarketItem(BaseModel):
    id: str
    original_name: str
    description: str
    command: str = ""
    agent_count: int = 0


class MCPServerMarketListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    servers: list[MCPServerMarketItem] = Field(default_factory=list)


class MCPServerDetailResponse(BaseModel):
    id: str
    original_name: str
    description: str
    command: str = ""
    args: list[str] = Field(default_factory=list)
    required_env: list[str] = Field(default_factory=list)
    agents: list[dict] = Field(default_factory=list)


class ResyncResponse(BaseModel):
    agents_processed: int = 0
    skills_extracted: int = 0
    mcp_servers_extracted: int = 0
    total_agents: int = 0
    errors: list[dict] = Field(default_factory=list)


# ============================================================
# Team 模型
# ============================================================

class TeamResponse(BaseModel):
    id: str
    name: str
    display_name: str
    version: str
    description: str = ""
    author: str = ""
    category: str = "general"
    type: str = "team"
    tags: list[str] = Field(default_factory=list)
    package_size: int = 0
    package_format: str = "tar.gz"
    download_count: int = 0
    rating: float = 0.0
    review_count: int = 0
    dependencies: dict = Field(default_factory=dict)
    homepage_url: str = ""
    source_url: str = ""
    license: str = "MIT"
    readme: str = ""
    json_content: str = "{}"
    created_at: str = ""
    updated_at: str = ""
    published_at: Optional[str] = None

    class Config:
        from_attributes = True


class TeamListItem(BaseModel):
    id: str
    display_name: str
    version: str
    description: str
    category: str
    tags: list[str] = Field(default_factory=list)
    download_count: int = 0
    rating: float = 0.0
    package_size: int = 0
    created_at: str = ""


class TeamListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list[TeamListItem] = Field(default_factory=list)


class TeamRegisterResponse(BaseModel):
    id: str
    name: str
    version: str
    package_size: int
    package_format: str
    created_at: str


# ============================================================
# Workflow 模型
# ============================================================

class WorkflowResponse(BaseModel):
    id: str
    name: str
    display_name: str
    version: str
    description: str = ""
    author: str = ""
    category: str = "general"
    type: str = "workflow"
    tags: list[str] = Field(default_factory=list)
    package_size: int = 0
    package_format: str = "tar.gz"
    download_count: int = 0
    rating: float = 0.0
    review_count: int = 0
    dependencies: dict = Field(default_factory=dict)
    homepage_url: str = ""
    source_url: str = ""
    license: str = "MIT"
    readme: str = ""
    json_content: str = "{}"
    created_at: str = ""
    updated_at: str = ""
    published_at: Optional[str] = None

    class Config:
        from_attributes = True


class WorkflowListItem(BaseModel):
    id: str
    display_name: str
    version: str
    description: str
    category: str
    tags: list[str] = Field(default_factory=list)
    download_count: int = 0
    rating: float = 0.0
    package_size: int = 0
    created_at: str = ""


class WorkflowListResponse(BaseModel):
    total: int = 0
    page: int = 1
    page_size: int = 20
    items: list[WorkflowListItem] = Field(default_factory=list)


class WorkflowRegisterResponse(BaseModel):
    id: str
    name: str
    version: str
    package_size: int
    package_format: str
    created_at: str


# ============================================================
# 统一搜索响应
# ============================================================

class UnifiedSearchResponse(BaseModel):
    agents: list[dict] = Field(default_factory=list)
    teams: list[dict] = Field(default_factory=list)
    workflows: list[dict] = Field(default_factory=list)
    total_agents: int = 0
    total_teams: int = 0
    total_workflows: int = 0


# ============================================================
# 版本管理模型
# ============================================================

class VersionInfo(BaseModel):
    """版本信息（匹配 agent-deploy 的 VersionInfo 接口）"""
    version: str
    created_at: str = ""
    changelog: str = ""
    author: str = ""
    package_size: int = 0
    package_sha256: str = ""

    class Config:
        from_attributes = True


class VersionListResponse(BaseModel):
    """版本列表响应"""
    versions: list[VersionInfo] = Field(default_factory=list)


class VersionDetailResponse(BaseModel):
    """版本详情响应"""
    version: str
    created_at: str = ""
    changelog: str = ""
    author: str = ""
    package_size: int = 0
    package_sha256: str = ""
    package_format: str = "tar.gz"
    package_path: str = ""

    class Config:
        from_attributes = True