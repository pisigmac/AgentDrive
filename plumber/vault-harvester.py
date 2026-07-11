#!/usr/bin/env python3
"""
Vault Harvester — Central Context Scanner for Multi-Project Workspaces

Scans a workspace directory, finds every project with `.vault/`,
harvests context from the project files, and auto-populates the vault.

Usage:
    python vault-harvester.py --workspace ~/projects
    python vault-harvester.py --workspace ~/projects --project neevibe
    python vault-harvester.py --workspace ~/projects --dry-run
    python vault-harvester.py --workspace ~/projects --daemon --interval 3600

Architecture:
    ~/projects/
    ├── neevibe/          ← vault init (has .vault/)
    │   ├── README.md
    │   ├── package.json
    │   ├── src/
    │   └── .vault/
    │       ├── projects/neevibe.md          ← harvested from README
    │       ├── projects/tech-stack.md       ← harvested from package.json
    │       ├── projects/structure.md        ← harvested from src/
    │       ├── projects/todos.md            ← harvested from TODOs
    │       ├── commits/2026-07-11.md        ← harvested from git log
    │       ├── decisions/agents.md          ← harvested from AGENTS.md
    │       └── meetings/                    ← manual or calendar-sync
    ├── agentmaya/        ← vault init
    └── sigmaplex/        ← no .vault/ (ignored)

The harvester is idempotent. Run it daily via cron or as a daemon.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class HarvestResult:
    project: str
    files_harvested: int = 0
    entries_created: int = 0
    entries_updated: int = 0
    errors: list[str] = field(default_factory=list)


class VaultHarvester:
    """Discovers vaults and harvests project context into them."""

    def __init__(self, workspace: Path, dry_run: bool = False):
        self.workspace = Path(workspace).resolve()
        self.dry_run = dry_run
        self.results: list[HarvestResult] = []

    def discover(self) -> list[Path]:
        """Find all directories under workspace that contain .vault/config.yaml."""
        vaults = []
        for entry in sorted(self.workspace.iterdir()):
            if not entry.is_dir() or entry.name.startswith("."):
                continue
            if (entry / ".vault" / "config.yaml").exists():
                vaults.append(entry)
        return vaults

    def harvest(self, project_path: Path) -> HarvestResult:
        """Harvest all context from a single project into its vault."""
        result = HarvestResult(project=project_path.name)
        vault_path = project_path / ".vault"

        # Ensure vault directories exist
        for d in ["projects", "commits", "decisions", "meetings", "sessions", "people"]:
            (project_path / d).mkdir(exist_ok=True)

        # 1. Harvest README → projects/<name>.md
        try:
            self._harvest_readme(project_path, result)
        except Exception as e:
            result.errors.append(f"readme: {e}")

        # 2. Harvest tech stack → projects/tech-stack.md
        try:
            self._harvest_tech_stack(project_path, result)
        except Exception as e:
            result.errors.append(f"tech-stack: {e}")

        # 3. Harvest source structure → projects/structure.md
        try:
            self._harvest_structure(project_path, result)
        except Exception as e:
            result.errors.append(f"structure: {e}")

        # 4. Harvest git commits → commits/YYYY-MM-DD.md
        try:
            self._harvest_git_commits(project_path, result)
        except Exception as e:
            result.errors.append(f"git: {e}")

        # 5. Harvest TODOs/FIXMEs → projects/todos.md
        try:
            self._harvest_todos(project_path, result)
        except Exception as e:
            result.errors.append(f"todos: {e}")

        # 6. Harvest AGENTS.md → decisions/agents.md
        try:
            self._harvest_agents(project_path, result)
        except Exception as e:
            result.errors.append(f"agents: {e}")

        # 7. Harvest project health → projects/health.md
        try:
            self._harvest_health(project_path, result)
        except Exception as e:
            result.errors.append(f"health: {e}")

        return result

    def _write_entry(self, path: Path, content: str, result: HarvestResult) -> None:
        """Write a vault entry, tracking creates vs updates."""
        if self.dry_run:
            action = "UPDATE" if path.exists() else "CREATE"
            print(f"  [{action}] {path.relative_to(self.workspace)}")
            return

        if path.exists():
            old = path.read_text()
            if old != content:
                path.write_text(content)
                result.entries_updated += 1
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            result.entries_created += 1

    def _frontmatter(self, **kwargs) -> str:
        """Generate YAML frontmatter."""
        now = datetime.now(timezone.utc).isoformat()
        defaults = {
            "id": hashlib.sha256(f"{now}:{kwargs.get('title','')}".encode()).hexdigest()[:12],
            "created": now,
            "modified": now,
            "source": "harvester",
            "status": "active",
        }
        defaults.update(kwargs)
        lines = ["---"]
        for k, v in sorted(defaults.items()):
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{k}: {v}")
        lines.append("---")
        return "\n".join(lines) + "\n\n"

    def _harvest_readme(self, project_path: Path, result: HarvestResult) -> None:
        readme = project_path / "README.md"
        if not readme.exists():
            return

        content = readme.read_text()
        result.files_harvested += 1

        # Extract first heading as title
        title = project_path.name
        match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if match:
            title = match.group(1).strip()

        # Extract first paragraph as description
        desc = ""
        paragraphs = re.split(r"\n\n+", content)
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith("#") and not p.startswith("!") and len(p) > 20:
                desc = p[:300]
                break

        entry = self._frontmatter(
            title=title,
            type="project-summary",
            tags=["auto-generated", "readme"],
        )
        entry += f"# {title}\n\n"
        entry += f"**Project:** `{project_path.name}`\n\n"
        entry += f"**Path:** `{project_path.relative_to(self.workspace)}`\n\n"
        if desc:
            entry += f"**Description:** {desc}\n\n"
        entry += "## README\n\n"
        entry += content[:4000]  # first 4K chars
        entry += "\n\n_(truncated — see full README in project root)_\n"

        self._write_entry(project_path / "projects" / f"{project_path.name}.md", entry, result)

    def _harvest_tech_stack(self, project_path: Path, result: HarvestResult) -> None:
        stack = {}

        # Node.js
        pkg = project_path / "package.json"
        if pkg.exists():
            try:
                data = json.loads(pkg.read_text())
                stack["runtime"] = "Node.js"
                stack["framework"] = data.get("dependencies", {})
                stack["dev_dependencies"] = list(data.get("devDependencies", {}).keys())[:10]
                stack["scripts"] = list(data.get("scripts", {}).keys())
            except Exception:
                pass

        # Python
        pyproject = project_path / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text()
            stack["runtime"] = "Python"
            deps = re.findall(r'^dependencies\s*=\s*\[(.*?)\]', text, re.MULTILINE | re.DOTALL)
            if deps:
                stack["dependencies"] = deps[0][:500]

        # Rust
        cargo = project_path / "Cargo.toml"
        if cargo.exists():
            text = cargo.read_text()
            stack["runtime"] = "Rust"
            deps = re.findall(r'^\[dependencies\](.*?)(?=\n\[|\Z)', text, re.MULTILINE | re.DOTALL)
            if deps:
                stack["dependencies"] = deps[0][:500]

        # Go
        gomod = project_path / "go.mod"
        if gomod.exists():
            text = gomod.read_text()
            stack["runtime"] = "Go"
            stack["module"] = text.split("\n")[0] if text else ""

        if not stack:
            return

        result.files_harvested += 1

        entry = self._frontmatter(
            title=f"{project_path.name} — Tech Stack",
            type="tech-stack",
            tags=["auto-generated", "dependencies"],
        )
        entry += f"# Tech Stack: {project_path.name}\n\n"
        for k, v in stack.items():
            if isinstance(v, list):
                entry += f"**{k.replace('_', ' ').title()}:** {', '.join(v)}\n\n"
            else:
                entry += f"**{k.replace('_', ' ').title()}:** {v}\n\n"

        self._write_entry(project_path / "projects" / "tech-stack.md", entry, result)

    def _harvest_structure(self, project_path: Path, result: HarvestResult) -> None:
        src_dirs = ["src", "app", "lib", "core", "vault", "api", "components", "pages"]
        found = None
        for d in src_dirs:
            if (project_path / d).is_dir():
                found = project_path / d
                break

        if not found:
            return

        # Build tree (max depth 3)
        lines = []
        for root, dirs, files in os.walk(found):
            depth = root.replace(str(found), "").count(os.sep)
            if depth > 2:
                del dirs[:]
                continue
            indent = "  " * depth
            rel = Path(root).relative_to(found)
            lines.append(f"{indent}{rel}/")
            for f in sorted(files)[:20]:  # cap files per dir
                if not f.startswith("."):
                    lines.append(f"{indent}  {f}")
            if len(files) > 20:
                lines.append(f"{indent}  ... ({len(files) - 20} more files)")

        result.files_harvested += 1

        entry = self._frontmatter(
            title=f"{project_path.name} — Structure",
            type="structure",
            tags=["auto-generated", "source"],
        )
        entry += f"# Source Structure: {project_path.name}\n\n"
        entry += f"**Root:** `{found.relative_to(project_path)}`\n\n"
        entry += "```\n"
        entry += "\n".join(lines[:200])  # cap total lines
        entry += "\n```\n"

        self._write_entry(project_path / "projects" / "structure.md", entry, result)

    def _harvest_git_commits(self, project_path: Path, result: HarvestResult) -> None:
        git_dir = project_path / ".git"
        if not git_dir.exists():
            return

        # Get commits from last 7 days
        since = (datetime.now(timezone.utc) - __import__("datetime").timedelta(days=7)).strftime("%Y-%m-%d")
        log = subprocess.run(
            ["git", "log", f"--since={since}", "--pretty=%h|%s|%an|%aI", "--no-merges"],
            cwd=project_path, capture_output=True, text=True,
        )
        if log.returncode != 0 or not log.stdout.strip():
            return

        commits = []
        for line in log.stdout.strip().split("\n"):
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append(parts)

        if not commits:
            return

        # Group by date
        by_date: dict[str, list] = {}
        for hash_, msg, author, date in commits:
            day = date[:10]
            by_date.setdefault(day, []).append((hash_, msg, author))

        for day, day_commits in by_date.items():
            entry = self._frontmatter(
                title=f"Commits on {day}",
                type="commit-log",
                tags=["auto-generated", "git"],
                commit_count=len(day_commits),
            )
            entry += f"# Commits on {day}\n\n"
            for hash_, msg, author in day_commits:
                entry += f"- **[{hash_}]** {msg} — *{author}*\n"
            entry += "\n"

            self._write_entry(project_path / "commits" / f"{day}.md", entry, result)
            result.files_harvested += 1

    def _harvest_todos(self, project_path: Path, result: HarvestResult) -> None:
        todos = []
        skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__", ".vault", "dist", "build"}

        for root, dirs, files in os.walk(project_path):
            # Skip hidden and build dirs
            dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
            for f in files:
                if not f.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".md")):
                    continue
                fp = Path(root) / f
                try:
                    text = fp.read_text(errors="ignore")
                    for match in re.finditer(r"(TODO|FIXME|HACK|BUG|XXX)[\s:]*(.*?)$", text, re.MULTILINE | re.IGNORECASE):
                        kind = match.group(1).upper()
                        desc = match.group(2).strip()[:200]
                        rel = fp.relative_to(project_path)
                        todos.append((kind, desc, rel))
                except Exception:
                    pass

        if not todos:
            return

        result.files_harvested += 1

        entry = self._frontmatter(
            title=f"{project_path.name} — Open Items",
            type="todos",
            tags=["auto-generated", "todos"],
            todo_count=len(todos),
        )
        entry += f"# Open Items: {project_path.name}\n\n"
        for kind, desc, rel in todos[:50]:  # cap at 50
            entry += f"- **[{kind}]** {desc} — `{rel}`\n"
        if len(todos) > 50:
            entry += f"\n_... and {len(todos) - 50} more_\n"

        self._write_entry(project_path / "projects" / "todos.md", entry, result)

    def _harvest_agents(self, project_path: Path, result: HarvestResult) -> None:
        agents = project_path / "AGENTS.md"
        if not agents.exists():
            return

        content = agents.read_text()
        result.files_harvested += 1

        entry = self._frontmatter(
            title=f"{project_path.name} — Agent Governance",
            type="decision",
            tags=["auto-generated", "agents"],
        )
        entry += f"# Agent Governance: {project_path.name}\n\n"
        entry += content[:3000]
        entry += "\n\n_(see full AGENTS.md in project root)_\n"

        self._write_entry(project_path / "decisions" / "agents.md", entry, result)

    def _harvest_health(self, project_path: Path, result: HarvestResult) -> None:
        issues = []

        # Check for README
        if not (project_path / "README.md").exists():
            issues.append("No README.md")

        # Check for uncommitted changes
        git_dir = project_path / ".git"
        if git_dir.exists():
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=project_path, capture_output=True, text=True,
            )
            if dirty.stdout.strip():
                lines = dirty.stdout.strip().split("\n")
                issues.append(f"{len(lines)} uncommitted file(s)")

        # Check for tests
        has_tests = any(
            (project_path / d).exists()
            for d in ["tests", "test", "__tests__", "spec"]
        )
        if not has_tests:
            issues.append("No test directory found")

        # Check for license
        if not any((project_path / f).exists() for f in ["LICENSE", "LICENSE.md"]):
            issues.append("No LICENSE file")

        entry = self._frontmatter(
            title=f"{project_path.name} — Health",
            type="health",
            tags=["auto-generated", "health"],
            issue_count=len(issues),
        )
        entry += f"# Health Check: {project_path.name}\n\n"
        if issues:
            entry += "**Issues:**\n\n"
            for issue in issues:
                entry += f"- ⚠️ {issue}\n"
        else:
            entry += "✅ All checks passed.\n"

        self._write_entry(project_path / "projects" / "health.md", entry, result)

    def run(self, project_filter: str | None = None) -> None:
        """Run harvest across all discovered vaults."""
        vaults = self.discover()
        if project_filter:
            vaults = [v for v in vaults if v.name == project_filter]

        print(f"[harvester] Workspace: {self.workspace}")
        print(f"[harvester] Vaults found: {len(vaults)}")
        if not vaults:
            print("[harvester] No vaults found. Run `vault init` in your projects first.")
            return

        for vault_path in vaults:
            print(f"\n[harvester] Harvesting: {vault_path.name}")
            result = self.harvest(vault_path)
            self.results.append(result)
            print(f"  Files scanned: {result.files_harvested}")
            print(f"  Entries created: {result.entries_created}")
            print(f"  Entries updated: {result.entries_updated}")
            if result.errors:
                for e in result.errors:
                    print(f"  ⚠️ {e}")

        # Summary
        total_created = sum(r.entries_created for r in self.results)
        total_updated = sum(r.entries_updated for r in self.results)
        print(f"\n[harvester] Done. Created: {total_created}, Updated: {total_updated}")




def generate_master_overview(workspace_path: Path, output_path: Path = None):
    """Generate a consolidated dashboard across all projects in the workspace."""
    workspace_path = Path(workspace_path).resolve()
    vaults = []

    for entry in sorted(workspace_path.iterdir()):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if (entry / ".vault" / "config.yaml").exists():
            vaults.append(entry)

    now = datetime.now(timezone.utc).isoformat()

    # Aggregate data from each vault
    projects_data = []
    all_todos = []
    all_commits = []
    all_health = []

    for vault in vaults:
        proj = {"name": vault.name, "path": str(vault.relative_to(workspace_path))}

        # Read harvested summary
        summary_file = vault / "projects" / f"{vault.name}.md"
        if summary_file.exists():
            text = summary_file.read_text()
            # Extract description from frontmatter or body
            desc_match = re.search(r"\*\*Description:\*\*\s*(.+)", text)
            proj["description"] = desc_match.group(1).strip() if desc_match else ""
            # Extract status from frontmatter
            status_match = re.search(r"status:\s*(\w+)", text)
            proj["status"] = status_match.group(1) if status_match else "unknown"
        else:
            proj["description"] = ""
            proj["status"] = "unknown"

        # Read tech stack
        tech_file = vault / "projects" / "tech-stack.md"
        proj["tech"] = []
        if tech_file.exists():
            text = tech_file.read_text()
            runtime = re.search(r"\*\*Runtime:\*\*\s*(.+)", text)
            if runtime:
                proj["tech"].append(runtime.group(1).strip())
            deps = re.findall(r"-?\s*([\w\-]+)>=?", text)
            proj["tech"].extend(deps[:5])

        # Read health
        health_file = vault / "projects" / "health.md"
        proj["health"] = "unknown"
        proj["issues"] = []
        if health_file.exists():
            text = health_file.read_text()
            if "All checks passed" in text:
                proj["health"] = "healthy"
            else:
                proj["health"] = "issues"
                issues = re.findall(r"- ⚠️\s*(.+)", text)
                proj["issues"] = issues

        # Read recent commits (last 7 days)
        proj["recent_commits"] = 0
        commits_dir = vault / "commits"
        if commits_dir.exists():
            for cf in commits_dir.glob("*.md"):
                text = cf.read_text()
                commits = re.findall(r"- \*\*\[", text)
                proj["recent_commits"] += len(commits)
                for c in commits:
                    all_commits.append({"project": vault.name, "file": cf.name})

        # Read TODOs
        todos_file = vault / "projects" / "todos.md"
        proj["todo_count"] = 0
        if todos_file.exists():
            text = todos_file.read_text()
            todos = re.findall(r"- \*\*\[(TODO|FIXME|HACK|BUG)\]\*\*\s*(.+?)$", text, re.MULTILINE)
            for kind, desc in todos[:10]:
                all_todos.append({
                    "project": vault.name,
                    "kind": kind,
                    "desc": desc.strip()[:100],
                })

        projects_data.append(proj)

    # Build master document
    md = f"""---
id: master-overview-{datetime.now().strftime('%Y-%m-%d')}
created: {now}
source: harvester
type: master-overview
project_count: {len(vaults)}
---

# Master Workspace Overview

**Generated:** {now}  
**Workspace:** `{workspace_path}`  
**Active Projects:** {len(vaults)}

## Project Dashboard

| Project | Status | Runtime | Health | Commits (7d) | Open Items |
|---------|--------|---------|--------|--------------|------------|
"""

    for p in projects_data:
        health_icon = "🟢" if p["health"] == "healthy" else "🟡" if p["health"] == "issues" else "⚪"
        tech_str = p["tech"][0] if p["tech"] else "—"
        md += f"| **{p['name']}** | {p['status']} | {tech_str} | {health_icon} {p['health']} | {p['recent_commits']} | {p['todo_count']} |\n"

    md += "\n## Project Details\n\n"

    for p in projects_data:
        md += f"""### {p['name']}

- **Path:** `{p['path']}`
- **Status:** {p['status']}
- **Health:** {p['health']}
"""
        if p["description"]:
            md += f"- **Description:** {p['description'][:120]}\n"
        if p["tech"]:
            md += f"- **Stack:** {', '.join(p['tech'][:5])}\n"
        if p["issues"]:
            md += "- **Issues:**\n"
            for issue in p["issues"]:
                md += f"  - ⚠️ {issue}\n"
        if p["recent_commits"] > 0:
            md += f"- **Recent activity:** {p['recent_commits']} commits in last 7 days\n"
        if p["todo_count"] > 0:
            md += f"- **Open items:** {p['todo_count']} TODOs/FIXMEs\n"
        md += "\n"

    # Cross-project tech stack comparison
    all_tech = {}
    for p in projects_data:
        for t in p["tech"]:
            all_tech.setdefault(t, []).append(p["name"])

    if all_tech:
        md += "## Cross-Project Tech Stack\n\n"
        md += "| Technology | Used In | Projects |\n"
        md += "|------------|---------|----------|\n"
        for tech, projs in sorted(all_tech.items(), key=lambda x: -len(x[1])):
            md += f"| {tech} | {len(projs)} | {', '.join(projs[:3])}{'...' if len(projs) > 3 else ''} |\n"
        md += "\n"

    # Recent activity across all projects
    if all_commits:
        md += "## Recent Activity (7 Days)\n\n"
        recent_by_project = {}
        for c in all_commits:
            recent_by_project.setdefault(c["project"], 0)
            recent_by_project[c["project"]] += 1
        for proj, count in sorted(recent_by_project.items(), key=lambda x: -x[1]):
            md += f"- **{proj}:** {count} commits\n"
        md += "\n"

    # Cross-project TODOs
    if all_todos:
        md += "## Cross-Project Open Items\n\n"
        for todo in all_todos[:20]:  # cap at 20
            md += f"- **[{todo['kind']}]** {todo['desc']} — *{todo['project']}*\n"
        if len(all_todos) > 20:
            md += f"\n_... and {len(all_todos) - 20} more_\n"
        md += "\n"

    # Health summary
    healthy = sum(1 for p in projects_data if p["health"] == "healthy")
    issues = sum(1 for p in projects_data if p["health"] == "issues")
    md += f"""## Health Summary

- 🟢 Healthy: {healthy}/{len(vaults)}
- 🟡 Issues: {issues}/{len(vaults)}
- ⚪ Unknown: {len(vaults) - healthy - issues}/{len(vaults)}

"""

    # AI action prompts
    md += """## AI Context Quick Reference

```
# Read project context
vault read projects/<project-name>.md

# Read tech stack
vault read projects/tech-stack.md

# Read open items
vault read projects/todos.md

# Read recent commits
vault read commits/YYYY-MM-DD.md

# Read health check
vault read projects/health.md
```

## Suggested Actions

"""

    # Suggest actions based on data
    suggestions = []
    for p in projects_data:
        if p["health"] == "issues":
            suggestions.append(f"- Review health issues in **{p['name']}**")
        if p["todo_count"] > 10:
            suggestions.append(f"- Triage TODOs in **{p['name']}** ({p['todo_count']} open items)")
        if p["recent_commits"] == 0:
            suggestions.append(f"- **{p['name']}** has no recent activity — check status")

    if not suggestions:
        suggestions.append("- All projects healthy. Review cross-project tech stack for consolidation opportunities.")

    md += "\n".join(suggestions) + "\n"

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md)
        print(f"[ok] Master overview written: {output_path}")

    return md

def main():
    parser = argparse.ArgumentParser(description="Vault Harvester — Auto-populate vaults from project files")
    parser.add_argument("--workspace", "-w", required=True, help="Workspace directory containing projects")
    parser.add_argument("--project", "-p", help="Harvest only this project name")
    parser.add_argument("--dry-run", "-n", action="store_true", help="Preview changes without writing")
    parser.add_argument("--daemon", "-d", action="store_true", help="Run as daemon, harvesting every --interval seconds")
    parser.add_argument("--interval", "-i", type=int, default=3600, help="Daemon interval in seconds (default: 3600)")
    parser.add_argument("--master-overview", "-m", action="store_true", help="Generate workspace-level master overview across all projects")
    parser.add_argument("--master-output", help="Output path for master overview (default: workspace/master-overview.md)")

    args = parser.parse_args()

    if args.master_overview:
        output = args.master_output or str(Path(args.workspace) / "master-overview.md")
        generate_master_overview(Path(args.workspace), Path(output))
        return

    harvester = VaultHarvester(Path(args.workspace), dry_run=args.dry_run)

    if args.daemon:
        print(f"[harvester] Daemon mode. Interval: {args.interval}s. Press Ctrl+C to stop.")
        while True:
            harvester.run(project_filter=args.project)
            print(f"[harvester] Sleeping {args.interval}s...")
            time.sleep(args.interval)
    else:
        harvester.run(project_filter=args.project)


if __name__ == "__main__":
    main()
