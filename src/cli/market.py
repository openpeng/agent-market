"""PilotDeck CLI - market 子命令"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def create_market_parser():
    parser = argparse.ArgumentParser(prog="pilotdeck market", description="PilotDeck 市场服务管理命令")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("serve", help="启动市场服务")
    p.add_argument("--port", type=int, default=8321)
    p.add_argument("--data-dir", default="./data/market")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--daemon", action="store_true")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("stop", help="停止市场服务")
    p.set_defaults(func=cmd_stop)

    p = sub.add_parser("status", help="查看市场服务状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("publish", help="发布 Agent")
    p.add_argument("path")
    p.add_argument("--server", default="http://localhost:8321")
    p.add_argument("--api-key", default="")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_publish)

    p = sub.add_parser("search", help="搜索 Agent")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("--server", default="http://localhost:8321")
    p.add_argument("--category", default="")
    p.add_argument("--tags", default="")
    p.add_argument("--sort", default="downloads")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("install", help="安装 Agent")
    p.add_argument("agent_id")
    p.add_argument("--server", default="http://localhost:8321")
    p.add_argument("--api-key", default="")
    p.add_argument("--output-dir", default="")
    p.add_argument("--verify", action="store_true")
    p.set_defaults(func=cmd_install)

    p = sub.add_parser("list", help="列出已安装的 Agent")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("uninstall", help="卸载 Agent")
    p.add_argument("agent_id")
    p.set_defaults(func=cmd_uninstall)

    p = sub.add_parser("update", help="更新 Agent")
    p.add_argument("agent_id", nargs="?", default="")
    p.add_argument("--server", default="http://localhost:8321")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("pack", help="打包 Agent 目录")
    p.add_argument("path")
    p.add_argument("--output", default="")
    p.add_argument("--verify", action="store_true")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("unpack", help="解压 Agent 包")
    p.add_argument("path")
    p.add_argument("--output", default="")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_unpack)

    # cache subcommand
    cp = sub.add_parser("cache", help="管理本地缓存")
    csub = cp.add_subparsers(dest="cache_command")
    cs = csub.add_parser("status", help="查看缓存状态")
    cs.set_defaults(func=cmd_cache_status)
    cc = csub.add_parser("clean", help="清理缓存")
    cc.add_argument("--max-age", type=int, default=7)
    cc.set_defaults(func=cmd_cache_clean)
    cp.set_defaults(func=cmd_cache_help)

    # key subcommand
    kp = sub.add_parser("key", help="管理 API Key")
    ksub = kp.add_subparsers(dest="key_command")
    kc = ksub.add_parser("create", help="创建 API Key")
    kc.add_argument("--owner", required=True)
    kc.add_argument("--role", default="publisher", choices=["publisher","admin"])
    kc.add_argument("--server", default="http://localhost:8321")
    kc.add_argument("--api-key", default="")
    kc.set_defaults(func=cmd_key_create)
    kl = ksub.add_parser("list", help="列出 API Keys")
    kl.add_argument("--server", default="http://localhost:8321")
    kl.add_argument("--api-key", default="")
    kl.set_defaults(func=cmd_key_list)
    kr = ksub.add_parser("revoke", help="撤销 API Key")
    kr.add_argument("key")
    kr.add_argument("--server", default="http://localhost:8321")
    kr.add_argument("--api-key", default="")
    kr.set_defaults(func=cmd_key_revoke)
    kp.set_defaults(func=cmd_key_help)

    # resync subcommand
    p = sub.add_parser("resync", help="重新同步 Skills 和 MCP 数据")
    p.add_argument("--server", default="http://localhost:8321")
    p.add_argument("--api-key", default="")
    p.set_defaults(func=cmd_resync)

    return parser


def _get_client(server_url=None, api_key=None):
    from market.client import MarketClient
    return MarketClient(server_url=server_url, api_key=api_key)


def cmd_serve(args):
    from market.server import run_server
    run_server(port=args.port, data_dir=args.data_dir, host=args.host, daemon=args.daemon)


def cmd_stop(args):
    pid_file = Path("./data/market/market.pid")
    if pid_file.exists():
        pid = int(pid_file.read_text().strip())
        try:
            os.kill(pid, 15)
            pid_file.unlink()
            print(f"✅ 市场服务已停止 (PID: {pid})")
        except ProcessLookupError:
            print("⚠️ 市场服务未运行")
            pid_file.unlink()
        except Exception as e:
            print(f"❌ 停止失败: {e}")
    else:
        print("⚠️ 未找到市场服务 PID 文件")


def cmd_status(args):
    c = _get_client()
    try:
        h = c.api_health()
        print(f"✅ 市场服务运行中\n   版本: {h.get('version','N/A')}\n   Agent 数量: {h.get('agents_count',0)}\n   运行时间: {h.get('uptime',0):.0f}s")
    except Exception:
        print(f"❌ 市场服务未运行\n   服务器: {c.server_url}")


def cmd_publish(args):
    c = _get_client(args.server, args.api_key)
    try:
        r = c.publish(args.path, force=args.force)
        print(f"✅ 发布成功! agent_id: {r.get('id','')}\n   版本: {r.get('version','')}")
    except Exception as e:
        print(f"❌ 发布失败: {e}")
        sys.exit(1)


def cmd_search(args):
    c = _get_client(args.server)
    try:
        results = c.search(query=args.query, category=args.category, tags=args.tags, sort=args.sort)
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        sys.exit(1)
    if not results:
        print("没有找到匹配的 Agent")
        return
    if args.json:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return
    print(f"找到 {len(results)} 个 Agent:\n")
    for r in results:
        stars = f"⭐{r.get('rating',0)}" if r.get('rating',0)>0 else ""
        dl = f"📥{r.get('download_count',0)}"
        print(f"  {r.get('id',''):20s} v{r.get('version',''):8s} {stars:6s} {dl:6s}  {r.get('description','')[:50]}")


def cmd_install(args):
    agent_id = args.agent_id
    version = None
    if "@" in agent_id:
        agent_id, version = agent_id.split("@", 1)
    c = _get_client(args.server, args.api_key)
    try:
        path = c.install(agent_id=agent_id, version=version, output_dir=args.output_dir or None, verify=args.verify)
        print(f"✅ 安装成功! 路径: {path}")
    except Exception as e:
        print(f"❌ 安装失败: {e}")
        sys.exit(1)


def cmd_list(args):
    c = _get_client()
    agents = c.list_installed()
    if not agents:
        print("没有已安装的 Agent")
        return
    if args.json:
        print(json.dumps(agents, indent=2, ensure_ascii=False))
        return
    print(f"已安装 {len(agents)} 个 Agent:\n")
    for a in agents:
        print(f"  {a.get('id',''):20s} v{a.get('version',''):8s}  {a.get('description','')[:50]}")


def cmd_uninstall(args):
    c = _get_client()
    try:
        c.uninstall(args.agent_id)
        print(f"✅ 已卸载: {args.agent_id}")
    except Exception as e:
        print(f"❌ 卸载失败: {e}")
        sys.exit(1)


def cmd_update(args):
    c = _get_client(args.server)
    if args.all:
        updates = c.check_updates()
    elif args.agent_id:
        updates = c.check_updates(args.agent_id)
    else:
        print("请指定 agent_id 或使用 --all")
        return
    updated = 0
    for aid, info in updates.items():
        if info.get("has_update"):
            print(f"🔄 更新 {aid}: {info['current']} → {info['latest']}")
            try:
                c.install(aid, version=info["latest"])
                updated += 1
            except Exception as e:
                print(f"  ❌ 更新失败: {e}")
        else:
            print(f"✓ {aid}: 已是最新 ({info.get('current','N/A')})")
    print(f"\n更新完成: {updated} 个 Agent 已更新")


def cmd_pack(args):
    from market.package import pack_agent, get_package_size
    try:
        pkg = pack_agent(args.path, args.output or None)
        print(f"✅ 打包成功: {pkg}  ({get_package_size(pkg)} bytes)")
        if args.verify:
            from market.verify import verify_package
            v, e = verify_package(Path(args.path))
            if v:
                print("✅ 包验证通过")
            else:
                for err in e:
                    print(f"  ⚠️  {err}")
    except Exception as e:
        print(f"❌ 打包失败: {e}")
        sys.exit(1)


def cmd_unpack(args):
    from market.package import unpack_agent, extract_metadata
    if args.dry_run:
        try:
            meta = extract_metadata(args.path)
            iden = meta.get("identity", {})
            print(f"包内容预览:\n  名称: {iden.get('name','N/A')}\n  版本: {iden.get('version','N/A')}\n  子Agent: {len(meta.get('subagents',[]))}")
        except Exception as e:
            print(f"❌ 预览失败: {e}")
        return
    try:
        target = unpack_agent(args.path, args.output or "./tmp")
        print(f"✅ 解压成功: {target}")
    except Exception as e:
        print(f"❌ 解压失败: {e}")
        sys.exit(1)


def cmd_cache_status(args):
    from market.cache import cache_size_info, list_cached_agents
    info = cache_size_info()
    agents = list_cached_agents()
    print(f"本地缓存状态:\n  Agent 数量: {info.get('agent_count',0)}\n  总大小: {info.get('total_size_mb',0):.1f} MB")
    if agents:
        for a in agents:
            print(f"  - {a.get('id','')} v{a.get('version','')}")


def cmd_cache_clean(args):
    from market.cache import clean_cache
    cleaned = clean_cache(max_age_days=args.max_age)
    print(f"✅ 已清理 {cleaned} 个过期缓存")


def cmd_cache_help(args):
    print("用法: pilotdeck market cache <子命令>\n   status   查看缓存状态\n   clean    清理过期缓存")


def cmd_key_create(args):
    import httpx
    data = {"owner": args.owner, "role": args.role}
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    try:
        r = httpx.post(f"{args.server}/api/v1/api-keys", json=data, headers=headers, timeout=10)
        r.raise_for_status()
        res = r.json()
        print(f"✅ API Key 创建成功:\n   Key: {res.get('key','')}\n   所有者: {res.get('owner','')}\n   角色: {res.get('role','')}")
    except Exception as e:
        print(f"❌ 创建失败: {e}")
        sys.exit(1)


def cmd_key_list(args):
    import httpx
    headers = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    try:
        r = httpx.get(f"{args.server}/api/v1/api-keys", headers=headers, timeout=10)
        r.raise_for_status()
        keys = r.json()
        if not keys:
            print("没有 API Keys")
            return
        print(f"共 {len(keys)} 个 API Keys:")
        for k in keys:
            print(f"  {k.get('key','')[:30]}...  {k.get('owner','')}  {k.get('role','')}")
    except Exception as e:
        print(f"❌ 查询失败: {e}")
        sys.exit(1)


def cmd_key_revoke(args):
    import httpx
    headers = {}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"
    try:
        r = httpx.delete(f"{args.server}/api/v1/api-keys/{args.key}", headers=headers, timeout=10)
        if r.status_code == 204:
            print(f"✅ API Key 已撤销")
        else:
            r.raise_for_status()
    except Exception as e:
        print(f"❌ 撤销失败: {e}")
        sys.exit(1)


def cmd_key_help(args):
    print("用法: pilotdeck market key <子命令>\n   create         创建 API Key\n   list           列出 API Keys\n   revoke <key>   撤销 API Key")

def cmd_resync(args):
    c = _get_client(args.server, args.api_key)
    try:
        r = c.resync()
        print(f"✅ Skills & MCP 同步完成!")
        print(f"   已处理 Agent: {r.get('agents_processed', 0)} 个")
        print(f"   已提取 Skill: {r.get('skills_extracted', 0)} 个")
        print(f"   已提取 MCP:   {r.get('mcp_servers_extracted', 0)} 个")
    except Exception as e:
        print(f"❌ 同步失败: {e}")
        sys.exit(1)