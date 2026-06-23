"""
市场服务 - Agent 包打包/解包
"""
from __future__ import annotations

import json
import tarfile
from pathlib import Path
from fastapi.responses import StreamingResponse


def pack_agent(pkg_dir, output_path=None):
    pkg_dir = Path(pkg_dir)
    if not (pkg_dir / "agent.json").exists():
        raise FileNotFoundError(f"Agent 目录缺少 agent.json")
    with open(pkg_dir / "agent.json", encoding="utf-8") as f:
        config = json.load(f)
    name = config.get("identity", {}).get("name", pkg_dir.name)
    version = config.get("identity", {}).get("version", "1.0.0")
    output_path = Path(output_path or f"{name}-v{version}.tar.gz")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(pkg_dir, arcname=pkg_dir.name)
    return output_path


def unpack_agent(package_path, target_dir):
    package_path = Path(package_path)
    target_dir = Path(target_dir)
    if package_path.name.endswith(".tar.gz"):
        with tarfile.open(package_path, "r:gz") as tar:
            tar.extractall(path=target_dir)
    elif package_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(path=target_dir)
    else:
        raise ValueError(f"不支持的包格式: {package_path.suffix}")
    extracted = list(target_dir.iterdir())
    if len(extracted) == 1 and extracted[0].is_dir():
        return extracted[0]
    return target_dir


def extract_metadata(package_path):
    package_path = Path(package_path)
    if package_path.name.endswith(".tar.gz"):
        with tarfile.open(package_path, "r:gz") as tar:
            for m in tar.getmembers():
                # Only match top-level agent.json (e.g., "pkg-name/agent.json"),
                # not nested ones like "pkg-name/templates/full-agent.json"
                parts = m.name.split("/")
                if len(parts) == 2 and parts[1] == "agent.json":
                    f = tar.extractfile(m)
                    if f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 agent.json")
    elif package_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(package_path, "r") as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) == 2 and parts[1] == "agent.json":
                    with zf.open(name) as f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 agent.json")
    else:
        raise ValueError(f"不支持的包格式")


def extract_team_metadata(package_path):
    """从 tar.gz 或 zip 包中提取 team.json 元数据"""
    package_path = Path(package_path)
    if package_path.name.endswith(".tar.gz"):
        import tarfile
        with tarfile.open(package_path, "r:gz") as tar:
            for m in tar.getmembers():
                parts = m.name.split("/")
                if len(parts) == 2 and parts[1] == "team.json":
                    f = tar.extractfile(m)
                    if f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 team.json")
    elif package_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(package_path, "r") as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) == 2 and parts[1] == "team.json":
                    with zf.open(name) as f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 team.json")
    else:
        raise ValueError(f"不支持的包格式: {package_path.suffix}")


def extract_workflow_metadata(package_path):
    """从 tar.gz 或 zip 包中提取 workflow.json 元数据"""
    package_path = Path(package_path)
    if package_path.name.endswith(".tar.gz"):
        import tarfile
        with tarfile.open(package_path, "r:gz") as tar:
            for m in tar.getmembers():
                parts = m.name.split("/")
                if len(parts) == 2 and parts[1] == "workflow.json":
                    f = tar.extractfile(m)
                    if f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 workflow.json")
    elif package_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(package_path, "r") as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) == 2 and parts[1] == "workflow.json":
                    with zf.open(name) as f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 workflow.json")
    else:
        raise ValueError(f"不支持的包格式: {package_path.suffix}")


def detect_package_type(package_path):
    """检测包类型：agent / team / workflow / unknown"""
    package_path = Path(package_path)
    if package_path.name.endswith(".tar.gz"):
        import tarfile
        with tarfile.open(package_path, "r:gz") as tar:
            for m in tar.getmembers():
                parts = m.name.split("/")
                if len(parts) == 2:
                    if parts[1] == "agent.json":
                        return "agent"
                    if parts[1] == "team.json":
                        return "team"
                    if parts[1] == "workflow.json":
                        return "workflow"
    return "unknown"


def get_package_size(package_path):
    return Path(package_path).stat().st_size


def pack_skill(pkg_dir, output_path=None):
    """打包 Skill 目录为 tar.gz

    输入: Skill 目录（含 skill.json + SKILL.md）
    输出: {name}-v{version}.tar.gz
    """
    pkg_dir = Path(pkg_dir)
    if not (pkg_dir / "skill.json").exists():
        raise FileNotFoundError(f"Skill 目录缺少 skill.json: {pkg_dir}")
    with open(pkg_dir / "skill.json", encoding="utf-8") as f:
        config = json.load(f)
    name = config.get("identity", {}).get("name", pkg_dir.name)
    version = config.get("identity", {}).get("version", "1.0.0")
    output_path = Path(output_path or f"{name}-v{version}.tar.gz")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(pkg_dir, arcname=pkg_dir.name)
    return output_path


def pack_mcp_server(pkg_dir, output_path=None):
    """打包 MCP Server 目录为 tar.gz

    输入: MCP Server 目录（含 mcp-server.json + mcp-config.json）
    输出: {name}-v{version}.tar.gz
    """
    pkg_dir = Path(pkg_dir)
    if not (pkg_dir / "mcp-server.json").exists():
        raise FileNotFoundError(f"MCP Server 目录缺少 mcp-server.json: {pkg_dir}")
    with open(pkg_dir / "mcp-server.json", encoding="utf-8") as f:
        config = json.load(f)
    name = config.get("identity", {}).get("name", pkg_dir.name)
    version = config.get("identity", {}).get("version", "1.0.0")
    output_path = Path(output_path or f"{name}-v{version}.tar.gz")
    with tarfile.open(output_path, "w:gz") as tar:
        tar.add(pkg_dir, arcname=pkg_dir.name)
    return output_path


def extract_skill_metadata(package_path):
    """从 tar.gz 或 zip 包中提取 skill.json 元数据"""
    package_path = Path(package_path)
    if package_path.name.endswith(".tar.gz"):
        with tarfile.open(package_path, "r:gz") as tar:
            for m in tar.getmembers():
                parts = m.name.split("/")
                if len(parts) == 2 and parts[1] == "skill.json":
                    f = tar.extractfile(m)
                    if f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 skill.json")
    elif package_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(package_path, "r") as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) == 2 and parts[1] == "skill.json":
                    with zf.open(name) as f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 skill.json")
    else:
        raise ValueError(f"不支持的包格式: {package_path.suffix}")


def extract_mcp_metadata(package_path):
    """从 tar.gz 或 zip 包中提取 mcp-server.json 元数据"""
    package_path = Path(package_path)
    if package_path.name.endswith(".tar.gz"):
        with tarfile.open(package_path, "r:gz") as tar:
            for m in tar.getmembers():
                parts = m.name.split("/")
                if len(parts) == 2 and parts[1] == "mcp-server.json":
                    f = tar.extractfile(m)
                    if f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 mcp-server.json")
    elif package_path.suffix == ".zip":
        import zipfile
        with zipfile.ZipFile(package_path, "r") as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) == 2 and parts[1] == "mcp-server.json":
                    with zf.open(name) as f:
                        return json.loads(f.read().decode("utf-8"))
            raise FileNotFoundError("包中未找到 mcp-server.json")
    else:
        raise ValueError(f"不支持的包格式: {package_path.suffix}")


def create_package_stream(package_path, filename=None):
    """创建包文件下载流"""
    package_path = Path(package_path)
    if not package_path.exists():
        raise FileNotFoundError(f"包文件不存在: {package_path}")
    filename = filename or package_path.name

    def iter_file():
        with open(package_path, "rb") as f:
            yield from f

    return StreamingResponse(
        iter_file(), media_type="application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{filename}"',
                 "Content-Length": str(package_path.stat().st_size)})