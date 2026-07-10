"""MCP Server for Personal Vault — Any provider can access."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from vault.core.config import VaultConfig, find_vault_root
from vault.core.git_workflow import VaultGit
from vault.core.archive import ArchiveEngine
from vault.core.search import VaultSearch
from vault.core.health import VaultHealth
from vault.core.registry import CapabilityRegistry


class VaultMCPServer:
    """MCP server exposing vault operations to any LLM client."""
    
    def __init__(self, vault_path: str | None = None):
        if vault_path:
            self.vault_path = Path(vault_path)
        else:
            env_path = os.environ.get("VAULT_PATH")
            if env_path:
                self.vault_path = Path(env_path)
            else:
                self.vault_path = find_vault_root()
        
        self.config = VaultConfig.load(self.vault_path / ".vault" / "config.yaml")
    
    def run(self) -> None:
        """Run MCP server over stdio (default for Claude/Cursor)."""
        try:
            from mcp.server import Server
            from mcp.types import Tool, TextContent
            
            self.server = Server("personal-vault")
            self._register_tools()
            self.server.run()
        except ImportError:
            print("ERROR: MCP dependencies not installed.", file=os.sys.stderr)
            print("Install with: pip install personal-vault[mcp]", file=os.sys.stderr)
            raise
    
    def _register_tools(self) -> None:
        """Register all vault tools with MCP server."""
        from mcp.types import Tool, TextContent
        
        @self.server.list_tools()
        async def list_tools():
            return [
                Tool(
                    name="vault_search",
                    description="Search vault by keyword query across all directories. Returns ranked results with snippets.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "directories": {"type": "array", "items": {"type": "string"}, "description": "Limit to specific directories (projects, people, etc.)"},
                            "limit": {"type": "integer", "default": 10, "description": "Max results to return"},
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="vault_read",
                    description="Read a specific vault file by path. Returns full content with frontmatter.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path from vault root (e.g., projects/neevibe.md)"}
                        },
                        "required": ["path"]
                    }
                ),
                Tool(
                    name="vault_write",
                    description="Write content to vault. Staged to dev branch, requires human approval to merge to main.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path from vault root"},
                            "content": {"type": "string", "description": "Full markdown content with frontmatter"},
                            "agent": {"type": "string", "default": "mcp", "description": "Agent identifier for audit trail"}
                        },
                        "required": ["path", "content"]
                    }
                ),
                Tool(
                    name="vault_archive",
                    description="Run archive engine on stale files. Moves files older than threshold to hidden .vault/archive.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "threshold_days": {"type": "integer", "default": 120, "description": "Days before archiving"}
                        }
                    }
                ),
                Tool(
                    name="vault_health",
                    description="Run full vault health check. Returns errors, warnings, and suggestions.",
                    inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="vault_status",
                    description="Get vault git status: branch, staged files, last commit.",
                    inputSchema={"type": "object", "properties": {}}
                ),
                Tool(
                    name="vault_skills",
                    description="List available skills in the registry. Filter by provider.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "provider": {"type": "string", "description": "Filter by provider (claude, codex, cursor, openai)"}
                        }
                    }
                ),
                Tool(
                    name="vault_new",
                    description="Create a new vault entry from template. Staged to dev branch.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["project", "person", "meeting", "decision", "goal", "experiment"], "description": "Entry type"},
                            "name": {"type": "string", "description": "Entry name/title"},
                            "content": {"type": "string", "description": "Optional custom content (uses template if omitted)"}
                        },
                        "required": ["type", "name"]
                    }
                ),
                Tool(
                    name="vault_related",
                    description="Find files related to a given path by tags and wiki links.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "Relative path to find related content for"}
                        },
                        "required": ["path"]
                    }
                ),
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict):
            if name == "vault_search":
                return await self._handle_search(arguments)
            elif name == "vault_read":
                return await self._handle_read(arguments)
            elif name == "vault_write":
                return await self._handle_write(arguments)
            elif name == "vault_archive":
                return await self._handle_archive(arguments)
            elif name == "vault_health":
                return await self._handle_health()
            elif name == "vault_status":
                return await self._handle_status()
            elif name == "vault_skills":
                return await self._handle_skills(arguments)
            elif name == "vault_new":
                return await self._handle_new(arguments)
            elif name == "vault_related":
                return await self._handle_related(arguments)
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
    
    async def _handle_search(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        searcher = VaultSearch(self.vault_path)
        results = searcher.search(
            args["query"],
            directories=args.get("directories"),
            limit=args.get("limit", 10)
        )
        output = {
            "query": args["query"],
            "results": [
                {
                    "path": r.path,
                    "score": round(r.score, 2),
                    "snippet": r.snippet,
                    "metadata": r.metadata
                }
                for r in results
            ]
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    async def _handle_read(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        filepath = self.vault_path / args["path"]
        if not filepath.exists():
            return [TextContent(type="text", text=f"File not found: {args['path']}")]
        content = filepath.read_text(encoding="utf-8")
        return [TextContent(type="text", text=content)]
    
    async def _handle_write(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        git = VaultGit(self.vault_path)
        path = Path(args["path"])
        content = args["content"]
        agent = args.get("agent", "mcp")
        
        result = git.stage_write(path, content, agent)
        pr = git.raise_pr(
            title=f"[{agent}] Update {path.name}",
            description=f"Staged by {agent} via MCP"
        )
        
        output = {
            "staged": {
                "branch": result.branch,
                "file": result.file,
                "hash": result.hash,
            },
            "pr": {
                "pr_id": pr.pr_id,
                "from": pr.from_branch,
                "to": pr.to_branch,
                "status": pr.status,
            },
            "note": "This write is staged on the 'dev' branch. A human must merge the PR to promote to 'main'."
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    async def _handle_archive(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        engine = ArchiveEngine(self.vault_path)
        report = engine.run(args.get("threshold_days", 120))
        return [TextContent(type="text", text=json.dumps(report, indent=2))]
    
    async def _handle_health(self) -> list[Any]:
        from mcp.types import TextContent
        health = VaultHealth(self.vault_path)
        report = health.check()
        return [TextContent(type="text", text=json.dumps(report, indent=2))]
    
    async def _handle_status(self) -> list[Any]:
        from mcp.types import TextContent
        git = VaultGit(self.vault_path)
        status = git.status()
        return [TextContent(type="text", text=json.dumps(status, indent=2))]
    
    async def _handle_skills(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        registry = CapabilityRegistry(self.vault_path)
        skills = registry.discover(provider=args.get("provider"))
        output = {
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "version": s.version,
                    "providers": s.providers,
                    "schedule": s.schedule,
                }
                for s in skills
            ]
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    async def _handle_new(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        import uuid as uuid_mod
        from datetime import datetime, timezone
        
        entry_type = args["type"]
        name = args["name"]
        content = args.get("content")
        
        if not content:
            # Use template
            template_path = self.vault_path / "templates" / f"{entry_type}.md"
            if template_path.exists():
                template = template_path.read_text()
                now = datetime.now(timezone.utc)
                content = template.replace("{{uuid}}", str(uuid_mod.uuid4()))
                content = content.replace("{{iso_timestamp}}", now.isoformat())
                content = content.replace("{{date}}", now.strftime("%Y-%m-%d"))
                content = content.replace("{{agent}}", "mcp")
                content = content.replace("{{title}}", name)
                content = content.replace("{{name}}", name)
            else:
                content = f"# {name}\n\nCreated via MCP.\n"
        
        dir_map = {
            "project": "projects",
            "person": "people",
            "meeting": "meetings",
            "decision": "decisions",
            "goal": "goals",
            "experiment": "experiments",
        }
        
        target_dir = self.vault_path / dir_map[entry_type]
        target_dir.mkdir(exist_ok=True)
        safe_name = name.lower().replace(" ", "-").replace("/", "-")
        target_file = target_dir / f"{safe_name}.md"
        
        git = VaultGit(self.vault_path)
        result = git.stage_write(target_file, content, agent="mcp")
        
        output = {
            "created": str(target_file.relative_to(self.vault_path)),
            "staged_to": "dev",
            "hash": result.hash,
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
    
    async def _handle_related(self, args: dict) -> list[Any]:
        from mcp.types import TextContent
        searcher = VaultSearch(self.vault_path)
        results = searcher.find_related(args["path"])
        output = {
            "path": args["path"],
            "related": [
                {
                    "path": r.path,
                    "score": round(r.score, 2),
                    "snippet": r.snippet,
                }
                for r in results
            ]
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2))]
