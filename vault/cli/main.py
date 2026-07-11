"""AgentDrive CLI — Filesystem-as-Memory for AI Agents."""

from __future__ import annotations

import sys
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vault.core.config import VaultConfig, find_vault_root, VaultNotFoundError
from vault.core.git_workflow import VaultGit
from vault.core.archive import ArchiveEngine
from vault.core.registry import CapabilityRegistry
from vault.core.scheduler import SkillScheduler
from vault.core.search import VaultSearch
from vault.core.health import VaultHealth
from vault.core.daemon import VaultDaemon, install_hooks

console = Console()


def get_vault_path() -> Path:
    """Find vault root or fail gracefully."""
    try:
        return find_vault_root()
    except VaultNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        console.print(
            "\n[dim]Run 'vault init' to create a new vault, or cd into an existing one.[/dim]"
        )
        sys.exit(1)


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """AgentDrive — Filesystem-as-Memory for AI Agents."""
    pass


# ─── INIT ───
@cli.command()
@click.argument("path", default=".", type=click.Path(exists=False))
@click.option("--name", default="agentdrive", help="Vault name")
@click.option("--force", is_flag=True, help="Overwrite existing vault")
def init(path: str, name: str, force: bool) -> None:
    """Initialize a new vault in the given directory."""
    vault_path = Path(path).resolve()
    vault_path.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]Initializing vault at {vault_path}[/bold green]")

    # Git setup
    import subprocess

    git_dir = vault_path / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=vault_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "vault@localhost"], cwd=vault_path)
        subprocess.run(["git", "config", "user.name", "AgentDrive"], cwd=vault_path)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "chore: initial repository creation"], cwd=vault_path, capture_output=True)

    # Create or switch to dev branch
    result = subprocess.run(["git", "checkout", "-b", "dev"], cwd=vault_path, capture_output=True)
    if result.returncode != 0:
        subprocess.run(["git", "checkout", "dev"], cwd=vault_path, capture_output=True)

    # Create structure
    (vault_path / ".vault").mkdir(exist_ok=True)
    (vault_path / ".vault/skills").mkdir(exist_ok=True)
    (vault_path / ".vault/registry").mkdir(exist_ok=True)
    (vault_path / ".vault/staging").mkdir(exist_ok=True)
    (vault_path / ".vault/archive").mkdir(exist_ok=True)
    (vault_path / ".vault/index").mkdir(exist_ok=True)
    (vault_path / ".vault/schemas").mkdir(exist_ok=True)
    (vault_path / "templates").mkdir(exist_ok=True)

    # Write config
    config = VaultConfig.default(vault_path)
    config.save(vault_path / ".vault" / "config.yaml")

    # Write AGENTS.md
    _write_agents_md(vault_path)

    # Write templates
    _write_templates(vault_path)

    # Write registry
    _write_registry(vault_path)

    # Write GitHub Workflow
    _write_github_workflow(vault_path)

    # Write cron
    _write_cron(vault_path)

    # Gitignore
    gitignore_path = vault_path / ".gitignore"
    vault_ignores = "\n# AgentDrive\n.vault/staging/\n.vault/index/\n.vault/archive/*.tmp\n.session\n"
    if gitignore_path.exists():
        content = gitignore_path.read_text()
        if ".vault/staging/" not in content:
            with open(gitignore_path, "a") as f:
                f.write(vault_ignores)
    else:
        standard_ignores = "node_modules/\nvenv/\n.venv/\n__pycache__/\n.env\n.DS_Store\nThumbs.db\n"
        gitignore_path.write_text(standard_ignores + vault_ignores)

    # Initial commit
    subprocess.run(["git", "add", "-A"], cwd=vault_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "[vault] Initial setup"], cwd=vault_path, capture_output=True
    )
    subprocess.run(["git", "checkout", "main"], cwd=vault_path, capture_output=True)
    subprocess.run(
        ["git", "merge", "dev", "--no-ff", "-m", "Bootstrap from dev"],
        cwd=vault_path,
        capture_output=True,
    )

    # Install git hooks for event-driven harvesting
    install_hooks(vault_path, python_executable=sys.executable)

    console.print("[green]✓[/green] Vault initialized")
    console.print(f"[dim]  Path: {vault_path}[/dim]")
    console.print("[dim]  Branches: main (stable) / dev (agent writes)[/dim]")
    console.print("[dim]  Hooks: post-commit + post-push (auto-harvesting)[/dim]")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  vault status     # Check vault health")
    console.print("  vault config     # Edit directory configuration")
    console.print("  vault mcp        # Install MCP server for Claude/Cursor")
    console.print("  vault daemon     # Manually trigger context harvest")


@cli.command()
@click.option("--brain", required=True, help="Path to the central AgentDrive Brain repository")
@click.option("--path", default=".", help="Project path to link")
def link(brain: str, path: str) -> None:
    """Link a project to a Central Brain without creating local vault folders."""
    import subprocess
    from pathlib import Path

    project_path = Path(path).resolve()
    brain_path = Path(brain).resolve()

    if not (brain_path / ".vault" / "config.yaml").exists():
        console.print(
            f"[red]Error:[/red] The specified brain path ({brain_path}) does not look like a valid AgentDrive Brain."
        )
        sys.exit(1)

    console.print(
        f"[bold green]Linking project at {project_path} to Brain at {brain_path}[/bold green]"
    )

    git_dir = project_path / ".git"
    if not git_dir.exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=project_path, capture_output=True)
        subprocess.run(["git", "config", "user.email", "vault@localhost"], cwd=project_path)
        subprocess.run(["git", "config", "user.name", "AgentDrive"], cwd=project_path)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "chore: initial repository creation"], cwd=project_path, capture_output=True)

    # Create or switch to dev branch
    result = subprocess.run(["git", "checkout", "-b", "dev"], cwd=project_path, capture_output=True)
    if result.returncode != 0:
        subprocess.run(["git", "checkout", "dev"], cwd=project_path, capture_output=True)

    # Generate global agentdrive registry
    global_dir = Path.home() / ".agentdrive"
    global_dir.mkdir(parents=True, exist_ok=True)
    global_config_path = global_dir / "config.json"
    
    import json
    global_config = {"links": {}}
    if global_config_path.exists():
        try:
            global_config = json.loads(global_config_path.read_text())
        except Exception:
            pass
            
    if "links" not in global_config:
        global_config["links"] = {}
        
    global_config["links"][str(project_path)] = str(brain_path)
    global_config_path.write_text(json.dumps(global_config, indent=2))
    
    # Create symlink for AI tools
    brains_dir = global_dir / "brains"
    brains_dir.mkdir(parents=True, exist_ok=True)
    symlink_path = brains_dir / brain_path.name
    if symlink_path.exists() or symlink_path.is_symlink():
        symlink_path.unlink()
    symlink_path.symlink_to(brain_path)

    # Append generic instruction to AGENTS.md
    agents_md = project_path / "AGENTS.md"
    generic_text = f"\n\n---\n*Note: Global system memory is tracked securely outside this repository. Read architecture decisions from: `~/.agentdrive/brains/{brain_path.name}/projects/{project_path.name}`*\n"
    
    if agents_md.exists():
        content = agents_md.read_text()
        if "Global system memory is tracked securely" not in content:
            agents_md.write_text(content.rstrip() + generic_text)
    else:
        agents_md.write_text(f"# Agent Governance & Context{generic_text}")

    # Write GitHub Workflow
    _write_github_workflow(project_path)

    # Install linked git hooks (no need to pass brain path, daemon will resolve it via config)
    from vault.core.daemon import install_hooks
    install_hooks(project_path, python_executable=sys.executable)

    # Update Brain config
    from vault.core.config import VaultConfig, DirectoryConfig
    brain_config = VaultConfig.load(brain_path / ".vault" / "config.yaml")
    brain_config.directories.append(DirectoryConfig(**{
        "name": project_path.name,
        "description": f"Linked project: {project_path.name}",
        "path": str(project_path),
        "vault_path": str(brain_path / "projects" / project_path.name)
    }))
    brain_config.save(brain_path / ".vault" / "config.yaml")

    console.print("[green]✓[/green] Project successfully linked to Central Brain via ~/.agentdrive registry!")
    console.print("[dim]  Local AGENTS.md updated safely.[/dim]")
    console.print("[dim]  Git hooks installed. Commits will route to the Brain automatically.[/dim]")


def _write_github_workflow(vault_path: Path) -> None:
    """Install the daily auto-PR GitHub workflow."""
    workflows_dir = vault_path / ".github" / "workflows"
    workflows_dir.mkdir(parents=True, exist_ok=True)

    # We copy the template from vault/templates/github/auto-pr.yml if available, otherwise write it directly
    from vault import __file__ as vault_init

    template_path = Path(vault_init).parent / "templates" / "github" / "auto-pr.yml"

    if template_path.exists():
        workflow_content = template_path.read_text()
    else:
        # Fallback raw content in case it isn't packaged properly
        workflow_content = """name: "AgentDrive: Daily Auto-PR (dev -> main)"
on:
  schedule:
    - cron: '0 0 * * *'
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  create-pr:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: dev
          fetch-depth: 0
      - id: check_diff
        run: |
          git fetch origin main
          if git diff --quiet origin/main..dev; then
            echo "has_changes=false" >> $GITHUB_OUTPUT
          else
            echo "has_changes=true" >> $GITHUB_OUTPUT
          fi
      - if: steps.check_diff.outputs.has_changes == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          PR_DATE=$(date +'%Y-%m-%d')
          gh pr create --base main --head dev --title "🤖 Auto-PR: Agent/Memory Updates ($PR_DATE)" --body "This automated PR promotes the latest AI Agent code execution and/or Vault memory summaries from the dev sandbox into the main stable branch."
"""

    workflow_file = workflows_dir / "agentdrive-auto-pr.yml"
    if not workflow_file.exists():
        workflow_file.write_text(workflow_content)
        
        # Automatically stage it so the user doesn't forget
        import subprocess
        subprocess.run(["git", "add", ".github/workflows/agentdrive-auto-pr.yml"], cwd=vault_path, capture_output=True)


def _write_agents_md(vault_path: Path) -> None:
    """Write root AGENTS.md."""
    content = """# AgentDrive — Agent Governance

## Scope
This AGENTS.md governs ALL AI providers (Claude, Codex, Cursor, OpenAI, etc.)
accessing this vault via MCP or direct filesystem.

## Rules
1. **Branch Rule**: All writes go to `dev` branch. Never commit to `main` directly.
2. **Approval Gate**: Every write must be staged in `.vault/staging/` and raised as a PR.
3. **Schema Rule**: Every markdown file MUST include frontmatter per its directory config.
4. **Archive Rule**: Files older than threshold are moved to `.vault/archive/`. Do not delete.
5. **Source Tag**: Every file must include `source: <provider>` in frontmatter.
6. **No Raw Secrets**: Never write API keys, tokens, or passwords into any vault file.
7. **Cross-Reference**: Link related entries with `[[WikiLinks]]` or `related:` frontmatter.
8. **Confidence Tag**: Mark speculative content with `confidence: low`.

## Directory Quick Reference
| Directory | Purpose | Archive | Template |
|-----------|---------|---------|----------|
| projects/ | Active work | 120d | templates/project.md |
| people/ | Contacts | Never | templates/person.md |
| goals/ | OKRs | 365d | templates/goal.md |
| meetings/ | Meeting notes | 90d | templates/meeting.md |
| decisions/ | ADRs | Never | templates/decision.md |
| resources/ | Bookmarks | 180d | templates/resource.md |
| experiments/ | Prototypes | 30d | templates/experiment.md |
| threads/ | Conversations | 120d | templates/thread.md |
| reviews/ | Retrospectives | 365d | templates/review.md |
"""
    (vault_path / "AGENTS.md").write_text(content)


def _write_templates(vault_path: Path) -> None:
    """Write default templates."""
    templates_dir = vault_path / "templates"

    templates = {
        "project.md": """---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
people: []
related_projects: []
---

# {{title}}

**Status:** active | stalled | completed | archived  
**Priority:** P0 | P1 | P2 | P3  
**Last Active:** {{date}}  

## Description

## GOAL.md
Long-running objectives

## RESULT.md
Completed work and verification

## Decisions
- [[decision-slug]]

## Meetings
- [[meeting-slug]]

## Notes
""",
        "person.md": """---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
last_contact: {{date}}
relationship: collaborator
---

# {{name}}

**Role:**  
**Company:**  
**Relationship:** collaborator | client | friend | mentor  

## Context
How I know them, projects we've worked on

## Communication Style
Formal / casual / technical / business

## Notes
- Thread references: [[thread-slug]]
- Projects: [[project-slug]]

## Last Contact
{{date}}
""",
        "meeting.md": """---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
attendees: []
projects: []
---

# Meeting: {{title}}

**Date:** {{date}}  
**Attendees:**  
**Project:**  

## Agenda

## Notes

## Action Items
- [ ] 

## Decisions
- 
""",
    }

    for name, content in templates.items():
        (templates_dir / name).write_text(content)


def _write_registry(vault_path: Path) -> None:
    """Write default skill registry."""
    import yaml

    registry = {
        "version": "1.0",
        "skills": [
            {
                "id": "new-person",
                "name": "Create Person Note",
                "description": "Generate a structured person file from context",
                "version": "1.0.0",
                "inputs": [
                    {"name": "name", "type": "string", "required": True},
                    {"name": "role", "type": "string", "required": False},
                ],
                "outputs": [
                    {"type": "file", "path_template": "people/{slug}.md", "schema": "person"}
                ],
                "permissions": {"read": ["templates/person.md"], "write": ["people/"]},
                "providers": ["all"],
                "sandbox": {"network": False, "filesystem": "restricted", "timeout": "30s"},
            },
            {
                "id": "archive-stale",
                "name": "Archive Stale Content",
                "description": "Move files older than threshold to .vault/archive",
                "version": "1.0.0",
                "inputs": [{"name": "threshold_days", "type": "integer", "default": 120}],
                "outputs": [{"type": "report", "path": ".vault/index/archive-report.yaml"}],
                "permissions": {
                    "read": ["projects/", "people/", "threads/", "experiments/", "meetings/"],
                    "write": [".vault/archive/", ".vault/index/"],
                },
                "schedule": "0 2 * * 0",
                "providers": ["all"],
            },
        ],
    }

    registry_path = vault_path / ".vault" / "registry" / "skills.yaml"
    with open(registry_path, "w") as f:
        yaml.dump(registry, f, default_flow_style=False, sort_keys=False)


def _write_cron(vault_path: Path) -> None:
    """Write default cron config."""
    import yaml

    cron = {
        "version": "1.0",
        "jobs": [
            {
                "skill": "archive-stale",
                "schedule": "0 2 * * 0",
                "description": "Archive files older than 120 days",
                "enabled": True,
            },
            {
                "skill": "health-check",
                "schedule": "0 9 * * 1",
                "description": "Weekly vault health report",
                "enabled": True,
            },
        ],
    }

    with open(vault_path / ".vault" / "cron.yaml", "w") as f:
        yaml.dump(cron, f, default_flow_style=False, sort_keys=False)


# ─── STATUS ───
@cli.command()
def status() -> None:
    """Show vault health and git status."""
    vault_path = get_vault_path()

    # Git status
    git = VaultGit(vault_path)
    gs = git.status()

    table = Table(title="Vault Status", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Vault Path", str(vault_path))
    table.add_row("Branch", gs["branch"])
    table.add_row("Dirty", "Yes" if gs["is_dirty"] else "No")
    table.add_row("Last Commit", gs["last_commit"])
    table.add_row("Staged Files", str(len(gs["staged_files"])))

    console.print(table)

    # Health check
    health = VaultHealth(vault_path)
    report = health.check()

    if report["errors"] > 0:
        console.print(f"\n[red]⚠ {report['errors']} errors found[/red]")
    if report["warnings"] > 0:
        console.print(f"[yellow]⚠ {report['warnings']} warnings[/yellow]")
    if report["errors"] == 0 and report["warnings"] == 0:
        console.print("\n[green]✓ Vault is healthy[/green]")


# ─── CONFIG ───
@cli.command()
@click.option("--edit", "-e", is_flag=True, help="Open config in editor")
@click.option("--show", "-s", is_flag=True, help="Show current config")
def config(edit: bool, show: bool) -> None:
    """View or edit vault configuration."""
    vault_path = get_vault_path()
    config_path = vault_path / ".vault" / "config.yaml"

    if show or not edit:
        cfg = VaultConfig.load(config_path)

        table = Table(title="Vault Configuration")
        table.add_column("Directory", style="cyan")
        table.add_column("Path", style="green")
        table.add_column("Archive (days)", style="yellow")
        table.add_column("Templates", style="blue")

        for d in cfg.directories:
            table.add_row(
                d.name,
                d.vault_path,
                str(d.archive_after_days) if d.archive_after_days > 0 else "Never",
                ", ".join(d.templates) if d.templates else "None",
            )

        console.print(table)

    if edit:
        editor = os.environ.get("EDITOR", "vim")
        import subprocess

        subprocess.run([editor, str(config_path)])


# ─── ARCHIVE ───
@cli.command()
@click.option("--threshold", "-t", type=int, default=None, help="Days before archiving")
@click.option("--dry-run", is_flag=True, help="Show what would be archived without doing it")
@click.option("--list", "list_archived", is_flag=True, help="List archived files")
def archive(threshold: int | None, dry_run: bool, list_archived: bool) -> None:
    """Archive stale vault content."""
    vault_path = get_vault_path()

    if list_archived:
        engine = ArchiveEngine(vault_path)
        archived = engine.list_archived()

        if not archived:
            console.print("[dim]No archived files.[/dim]")
            return

        table = Table(title="Archived Files")
        table.add_column("Original", style="cyan")
        table.add_column("Archived", style="green")
        table.add_column("Date", style="yellow")

        for item in archived:
            table.add_row(item["original_path"], item["path"], item["archived"])

        console.print(table)
        return

    engine = ArchiveEngine(vault_path)
    stale = engine.scan(threshold)

    if not stale:
        console.print("[green]✓ No stale files found[/green]")
        return

    console.print(f"[yellow]Found {len(stale)} stale files[/yellow]")

    for file in stale:
        rel = file.relative_to(vault_path)
        console.print(f"  [dim]{rel}[/dim]")

    if dry_run:
        console.print("\n[dim]--dry-run: no changes made[/dim]")
        return

    if click.confirm("Archive these files?"):
        report = engine.run(threshold)
        console.print(f"[green]✓ Archived {report['archived']} files[/green]")
        console.print(
            f"[dim]  Report: {vault_path / '.vault' / 'index' / 'archive-report.yaml'}[/dim]"
        )


# ─── SEARCH ───
@cli.command()
@click.argument("query")
@click.option("--dir", "-d", multiple=True, help="Limit to specific directories")
@click.option("--limit", "-l", type=int, default=10, help="Max results")
@click.option("--semantic", "-s", is_flag=True, help="Use semantic search")
def search(query: str, dir: tuple[str, ...], limit: int, semantic: bool) -> None:
    """Search vault content."""
    vault_path = get_vault_path()
    searcher = VaultSearch(vault_path)

    results = searcher.search(
        query, directories=list(dir) if dir else None, limit=limit, semantic=semantic
    )

    if not results:
        console.print(f"[dim]No results for: {query}[/dim]")
        return

    table = Table(title=f'Search: "{query}"')
    table.add_column("Score", style="yellow", justify="right")
    table.add_column("File", style="cyan")
    table.add_column("Snippet", style="green")

    for r in results:
        table.add_row(f"{r.score:.1f}", r.path, r.snippet[:80])

    console.print(table)


# ─── HEALTH ───
@cli.command()
@click.option("--report", is_flag=True, help="Show full report")
def health(report: bool) -> None:
    """Run vault health check."""
    vault_path = get_vault_path()
    checker = VaultHealth(vault_path)
    result = checker.check()

    if result["errors"] == 0 and result["warnings"] == 0:
        console.print("[green]✓ Vault is healthy[/green]")
    else:
        console.print(
            f"[red]{result['errors']} errors[/red], [yellow]{result['warnings']} warnings[/yellow], {result['infos']} infos"
        )

    if report:
        for issue in result["issues"]:
            color = {"error": "red", "warning": "yellow", "info": "blue"}.get(
                issue["severity"], "white"
            )
            console.print(f"\n[{color}]{issue['severity'].upper()}[{color}] {issue['category']}")
            console.print(f"  {issue['message']}")
            if issue.get("file"):
                console.print(f"  [dim]File: {issue['file']}[/dim]")
            if issue.get("suggestion"):
                console.print(f"  [dim]Suggestion: {issue['suggestion']}[/dim]")


# ─── REGISTRY ───
@cli.command()
@click.option("--list", "list_skills", is_flag=True, help="List all skills")
@click.option("--provider", help="Filter by provider")
def registry(list_skills: bool, provider: str | None) -> None:
    """Manage agent capability registry."""
    vault_path = get_vault_path()
    reg = CapabilityRegistry(vault_path)

    if list_skills or provider is not None or provider is None:  # basically always run
        skills = reg.discover(provider=provider)

        if not skills:
            console.print("[dim]No skills found.[/dim]")
            return

        table = Table(title="Agent Skills")
        table.add_column("ID", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Version", style="yellow")
        table.add_column("Providers", style="blue")
        table.add_column("Schedule", style="magenta")

        for s in skills:
            table.add_row(s.id, s.name, s.version, ", ".join(s.providers), s.schedule or "-")

        console.print(table)


# ─── CRON ───
@cli.command()
@click.option("--enable", is_flag=True, help="Start background scheduler")
@click.option("--disable", is_flag=True, help="Stop background scheduler")
@click.option("--status", "show_status", is_flag=True, help="Show scheduler status")
@click.option("--edit", is_flag=True, help="Edit cron configuration")
@click.option("--run", "run_now", help="Run a specific skill immediately")
def cron(enable: bool, disable: bool, show_status: bool, edit: bool, run_now: str | None) -> None:
    """Manage scheduled vault tasks."""
    vault_path = get_vault_path()
    scheduler = SkillScheduler(vault_path)

    if enable:
        scheduler.load()
        scheduler.start()
        console.print("[green]✓ Scheduler started[/green]")
        console.print("[dim]  Press Ctrl+C to stop[/dim]")
        try:
            while True:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            scheduler.stop()

    elif disable:
        scheduler.stop()

    elif show_status:
        status = scheduler.status()
        console.print(f"Running: {status['running']}")
        console.print(f"Jobs: {status['jobs_scheduled']}")
        if status["next_run"]:
            console.print(f"Next run: {status['next_run']}")

    elif edit:
        editor = os.environ.get("EDITOR", "vim")
        import subprocess

        subprocess.run([editor, str(vault_path / ".vault" / "cron.yaml")])

    elif run_now:
        scheduler.load()
        scheduler.run_once(run_now)

    else:
        # Show cron config
        import yaml

        cron_file = vault_path / ".vault" / "cron.yaml"
        if cron_file.exists():
            with open(cron_file) as f:
                config = yaml.safe_load(f) or {}

            table = Table(title="Scheduled Jobs")
            table.add_column("Skill", style="cyan")
            table.add_column("Schedule", style="green")
            table.add_column("Description", style="yellow")
            table.add_column("Enabled", style="blue")

            for job in config.get("jobs", []):
                table.add_row(
                    job["skill"],
                    job["schedule"],
                    job.get("description", ""),
                    "Yes" if job.get("enabled", True) else "No",
                )

            console.print(table)


# ─── MCP ───
@cli.command()
@click.option("--install", is_flag=True, help="Install MCP server config for Claude/Cursor")
@click.option("--run", "run_server", is_flag=True, help="Run MCP server (stdio)")
@click.option("--port", type=int, default=8765, help="Port for SSE transport")
def mcp(install: bool, run_server: bool, port: int) -> None:
    """Manage MCP server integration."""
    vault_path = get_vault_path()

    if install:
        config = _get_mcp_config(vault_path)

        console.print("[bold]MCP Configuration[/bold]")
        console.print("Add this to your MCP client config:\n")
        console.print(Panel(config, title="mcpServers", border_style="green"))

        # Try to auto-install for common locations
        claude_config = (
            Path.home() / "Library" / "Application Support" / "Claude" / "mcp_config.json"
        )
        if claude_config.exists():
            console.print(f"\n[dim]Found Claude config at {claude_config}[/dim]")
            if click.confirm("Install to Claude?"):
                import json

                with open(claude_config) as f:
                    existing = json.load(f)
                existing.setdefault("mcpServers", {})
                existing["mcpServers"]["agentdrive"] = {
                    "command": "vault",
                    "args": ["mcp", "--run"],
                    "env": {"VAULT_PATH": str(vault_path)},
                }
                with open(claude_config, "w") as f:
                    json.dump(existing, f, indent=2)
                console.print("[green]✓ Installed to Claude[/green]")

    elif run_server:
        try:
            from vault.mcp.server import VaultMCPServer

            server = VaultMCPServer(str(vault_path))
            console.print("[green]Starting MCP server...[/green]")
            server.run()
        except ImportError:
            console.print("[red]MCP dependencies not installed.[/red]")
            console.print("[dim]Install with: pip install agentdrive[mcp][/dim]")


def _get_mcp_config(vault_path: Path) -> str:
    """Generate MCP config JSON."""
    import json

    config = {
        "mcpServers": {
            "agentdrive": {
                "command": "vault",
                "args": ["mcp", "--run"],
                "env": {"VAULT_PATH": str(vault_path)},
            }
        }
    }
    return json.dumps(config, indent=2)


# ─── STAGE ───
@cli.command()
@click.argument("filepath")
@click.argument("content")
@click.option("--agent", default="cli", help="Agent identifier")
def stage(filepath: str, content: str, agent: str) -> None:
    """Stage a file write to dev branch."""
    vault_path = get_vault_path()
    git = VaultGit(vault_path)

    result = git.stage_write(filepath, content, agent)
    console.print("[green]✓ Staged to dev[/green]")
    console.print(f"[dim]  File: {result.file}[/dim]")
    console.print(f"[dim]  Hash: {result.hash}[/dim]")

    # Raise PR
    pr = git.raise_pr(
        title=f"[{agent}] Update {Path(filepath).name}",
        description=f"Staged by {agent} via CLI",
    )
    console.print(f"[dim]  PR: {pr.pr_id}[/dim]")


# ─── PROMOTE ───
@cli.command()
@click.argument("pr_id", required=False)
def promote(pr_id: str | None) -> None:
    """Promote staged files from dev to main."""
    vault_path = get_vault_path()
    git = VaultGit(vault_path)

    # Show diff first
    diff = git.diff_staged()
    if diff:
        console.print("[bold]Staged changes:[/bold]")
        console.print(diff)

    if click.confirm("Promote to main?"):
        promoted = git.promote_staged(pr_id)
        console.print(f"[green]✓ Promoted {len(promoted)} files to main[/green]")


# ─── NEW ───
@cli.command()
@click.argument(
    "type", type=click.Choice(["project", "person", "meeting", "decision", "goal", "experiment"])
)
@click.argument("name")
@click.option("--agent", default="cli", help="Agent identifier")
def new(type: str, name: str, agent: str) -> None:
    """Create a new vault entry from template."""
    vault_path = get_vault_path()

    # Load template
    template_path = vault_path / "templates" / f"{type}.md"
    if not template_path.exists():
        console.print(f"[red]Template not found: {template_path}[/red]")
        return

    template = template_path.read_text()

    # Replace placeholders
    now = datetime.now(timezone.utc)
    content = template.replace("{{uuid}}", str(uuid.uuid4()))
    content = content.replace("{{iso_timestamp}}", now.isoformat())
    content = content.replace("{{date}}", now.strftime("%Y-%m-%d"))
    content = content.replace("{{agent}}", agent)
    content = content.replace("{{title}}", name)
    content = content.replace("{{name}}", name)

    # Determine target directory
    dir_map = {
        "project": "projects",
        "person": "people",
        "meeting": "meetings",
        "decision": "decisions",
        "goal": "goals",
        "experiment": "experiments",
    }

    target_dir = vault_path / dir_map[type]
    target_dir.mkdir(exist_ok=True)

    # Sanitize filename
    safe_name = name.lower().replace(" ", "-").replace("/", "-")
    target_file = target_dir / f"{safe_name}.md"

    # Stage to dev
    git = VaultGit(vault_path)
    result = git.stage_write(target_file, content, agent)

    console.print(f"[green]✓ Created {type}[/green]")
    console.print(f"[dim]  File: {target_file.relative_to(vault_path)}[/dim]")
    console.print(f"[dim]  Hash: {result.hash}[/dim]")
    console.print("[dim]  Staged to dev branch[/dim]")


# ─── INDEX ───
@cli.command()
def index() -> None:
    """Build search index for all vault content."""
    vault_path = get_vault_path()
    searcher = VaultSearch(vault_path)
    result = searcher.build_index()
    console.print(f"[green]✓ Indexed {len(result['entries'])} entries[/green]")


# ─── DAEMON ───
@cli.command()
@click.option("--project", "-p", default=".", help="Project path to harvest")
@click.option(
    "--trigger",
    type=click.Choice(["commit", "push", "manual"]),
    default="manual",
    help="Trigger type",
)
@click.option(
    "--brain",
    type=str,
    default=None,
    help="Path to Central Brain repository",
)
def daemon(project: str, trigger: str, brain: str | None) -> None:
    """Trigger event-driven context harvest (used by git hooks)."""
    project_path = Path(project).resolve()
    brain_path = Path(brain).resolve() if brain else None

    if not brain_path:
        global_config_path = Path.home() / ".agentdrive" / "config.json"
        if global_config_path.exists():
            import json
            try:
                global_config = json.loads(global_config_path.read_text())
                links = global_config.get("links", {})
                if str(project_path) in links:
                    brain_path = Path(links[str(project_path)]).resolve()
            except Exception:
                pass

    if not brain_path and not (project_path / ".vault" / "config.yaml").exists():
        console.print(f"[red]No vault found at {project_path}[/red]")
        console.print("[dim]Run 'vault init' first.[/dim]")
        sys.exit(1)

    vd = VaultDaemon(project_path, brain_path=brain_path)
    vd.run(trigger)


if __name__ == "__main__":
    cli()
