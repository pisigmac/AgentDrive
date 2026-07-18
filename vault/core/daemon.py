"""Event-driven vault context harvester.

Triggered by git hooks (post-commit, post-push). No cron, no polling.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


class VaultDaemon:
    """Harvests project context into vault on git events."""

    def __init__(self, project_path: Path, brain_path: Path | None = None):
        self.project = Path(project_path).resolve()
        self.brain_path = Path(brain_path).resolve() if brain_path else None

        if self.brain_path:
            self.vault = self.brain_path / ".vault"
            self.output_dir = self.brain_path / "projects" / self.project.name
        else:
            self.vault = self.project / ".vault"
            self.output_dir = self.project / "projects"

        self.state_file = self.vault / ".daemon-state.json"
        self.state = self._load_state()
        self.ignore_patterns = self._load_ignore_patterns()

    def _load_ignore_patterns(self) -> list[str]:
        ignore_file = self.project / ".agentignore"
        patterns = []
        if ignore_file.exists():
            for line in ignore_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    patterns.append(line)
        return patterns

    def _is_ignored(self, path: Path) -> bool:
        import fnmatch

        try:
            rel_str = str(path.relative_to(self.project))
        except ValueError:
            return False

        name = path.name

        for pat in self.ignore_patterns:
            if fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(name, pat):
                return True
            if pat.endswith("/") and fnmatch.fnmatch(name + "/", pat):
                return True
        return False

    def _load_state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"last_harvest": None, "last_master": None, "last_commit_hash": None}

    def _save_state(self) -> None:
        self.state_file.write_text(json.dumps(self.state, indent=2))

    def run(self, trigger: str) -> None:
        """Main entry point called by git hooks."""
        start = datetime.now(timezone.utc)

        # Ensure vault directories exist
        for d in ("projects", "commits", "decisions", "meetings", "sessions"):
            target = self.brain_path / d if self.brain_path else self.project / d
            target.mkdir(parents=True, exist_ok=True)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        entries = 0

        # Always harvest commits on commit/push triggers
        if trigger in ("commit", "push"):
            entries += self._harvest_git_commits()

        # Full harvest on push or manual
        if trigger in ("push", "manual"):
            entries += self._harvest_readme()
            entries += self._harvest_tech_stack()
            entries += self._harvest_structure()
            entries += self._harvest_todos()
            entries += self._harvest_health()

        self.state["last_harvest"] = start.isoformat()
        self.state["last_trigger"] = trigger
        self._save_state()

        if entries > 0 and self.brain_path:
            # Clean Git env vars to prevent hook bleed into CentralBrain subprocesses
            clean_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}

            # Commit files into the Brain dev branch
            subprocess.run(
                ["git", "add", "."], cwd=self.brain_path, capture_output=True, env=clean_env
            )
            subprocess.run(
                [
                    "git",
                    "commit",
                    "-m",
                    f"🤖 Auto-harvest: {self.project.name} ({entries} updates)",
                ],
                cwd=self.brain_path,
                capture_output=True,
                env=clean_env,
            )

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()
        print(f"[vault-daemon] {self.project.name}: {entries} entries, {elapsed:.2f}s ({trigger})")

        self._maybe_rebuild_master()

    def _maybe_rebuild_master(self) -> None:
        """Rebuild master overview if stale (>1 hour)."""
        workspace = self.project.parent
        master_state = workspace / ".vault-daemon-master.state"

        brain_projects = self.project / "projects"
        if brain_projects.exists() and brain_projects.is_dir():
            master_output = self.project / "master-overview.md"
        else:
            master_output = workspace / "master-overview.md"

        last_build = None
        if master_state.exists():
            try:
                last_build = datetime.fromisoformat(master_state.read_text().strip())
            except ValueError:
                pass

        now = datetime.now(timezone.utc)
        if last_build and (now - last_build) < timedelta(hours=1):
            return

        vaults = []

        # 1. If this is a Central Brain, collect all linked projects
        brain_projects = self.project / "projects"
        if brain_projects.exists() and brain_projects.is_dir():
            for entry in sorted(brain_projects.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    vaults.append(entry)
        else:
            # 2. Standalone scan: look for local .vault folders
            for entry in sorted(workspace.iterdir()):
                if entry.is_dir() and not entry.name.startswith("."):
                    if (entry / ".vault" / "config.yaml").exists():
                        vaults.append(entry)

        if not vaults:
            return

        self._generate_master_overview(vaults, master_output)
        master_state.write_text(now.isoformat())
        print(f"[vault-daemon] Master overview: {master_output}")

    # ─── HARVESTERS ───

    def _harvest_readme(self) -> int:
        readme = self.project / "README.md"
        if not readme.exists():
            return 0

        content = readme.read_text()
        title = self.project.name
        m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        if m:
            title = m.group(1).strip()

        desc = ""
        for p in re.split(r"\n\n+", content):
            p = p.strip()
            if p and not p.startswith("#") and not p.startswith("!") and len(p) > 20:
                desc = p[:300]
                break

        readme_lines = content.split("\n")
        if len(readme_lines) > 500:
            truncated_content = "\n".join(readme_lines[:500])
            truncation_notice = "\n\n_(truncated — see full README in project root)_\n"
        else:
            truncated_content = content
            truncation_notice = "\n"

        body = (
            f"# {title}\n\n"
            f"**Project:** `{self.project.name}`\n\n"
            f"**Path:** `{self.project.name}`\n\n"
            f"**Description:** {desc}\n\n"
            f"## README\n\n"
            f"{truncated_content}{truncation_notice}"
        )

        dest = self.output_dir / "README.md"
        return (
            1
            if self._write_if_changed(
                dest,
                self._frontmatter(f"{self.project.name} — Overview", "overview", ["readme"], body),
            )
            else 0
        )

    def _harvest_tech_stack(self) -> int:
        stack: dict[str, Any] = {}
        for manifest, runtime in (
            (self.project / "package.json", "Node.js"),
            (self.project / "pyproject.toml", "Python"),
            (self.project / "Cargo.toml", "Rust"),
            (self.project / "go.mod", "Go"),
            (self.project / "requirements.txt", "Python"),
        ):
            if manifest.exists():
                stack["runtime"] = runtime
                text = manifest.read_text()
                if manifest.name == "package.json":
                    try:
                        data = json.loads(text)
                        deps = list(data.get("dependencies", {}).keys())[:10]
                        stack["dependencies"] = deps
                    except Exception:
                        pass
                elif manifest.name == "pyproject.toml":
                    deps = re.findall(
                        r"^dependencies\s*=\s*\[(.*?)\]", text, re.MULTILINE | re.DOTALL
                    )
                    if deps:
                        stack["dependencies"] = deps[0][:500]
                break

        if not stack:
            # Fallback: Guess runtime by counting file extensions in root or src
            counts = {}
            for root, dirs, files in os.walk(self.project):
                dirs[:] = [
                    d
                    for d in dirs
                    if d
                    not in {
                        ".git",
                        "node_modules",
                        ".venv",
                        "venv",
                        "__pycache__",
                        ".vault",
                        "dist",
                        "build",
                    }
                    and not d.startswith(".")
                ]
                for f in files:
                    ext = Path(f).suffix
                    if ext in (".py", ".js", ".ts", ".go", ".rs", ".java"):
                        counts[ext] = counts.get(ext, 0) + 1
            if not counts:
                return 0

            dominant_ext = max(counts, key=counts.get)
            ext_map = {
                ".py": "Python",
                ".js": "JavaScript",
                ".ts": "TypeScript",
                ".go": "Go",
                ".rs": "Rust",
                ".java": "Java",
            }
            stack["runtime"] = ext_map.get(dominant_ext, "Unknown")

        body = f"# Tech Stack: {self.project.name}\n\n"
        for k, v in stack.items():
            if isinstance(v, list):
                body += f"**{k.title()}:** {', '.join(v)}\n\n"
            else:
                body += f"**{k.title()}:** {v}\n\n"

        dest = self.output_dir / "tech-stack.md"
        return (
            1
            if self._write_if_changed(
                dest,
                self._frontmatter(
                    f"{self.project.name} — Tech Stack", "tech-stack", ["dependencies"], body
                ),
            )
            else 0
        )

    def _harvest_structure(self) -> int:
        src_dirs = ("src", "app", "lib", "core", "components", "pages", "api", "vault")
        found = None
        for d in src_dirs:
            if (self.project / d).is_dir():
                found = self.project / d
                break

        if not found:
            found = self.project

        skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".vault", "dist", "build"}
        lines = []
        for root, dirs, files in os.walk(found):
            dirs[:] = [
                d
                for d in dirs
                if d not in skip and not self._is_ignored(Path(root) / d) and not d.startswith(".")
            ]
            depth = root.replace(str(found), "").count(os.sep)
            if depth > 2:
                del dirs[:]
                continue
            rel = Path(root).relative_to(found)
            indent = "  " * depth
            lines.append(f"{indent}{rel}/")

            valid_files = [
                f
                for f in sorted(files)
                if not f.startswith(".") and not self._is_ignored(Path(root) / f)
            ]
            for f in valid_files[:20]:
                lines.append(f"{indent}  {f}")
            if len(valid_files) > 20:
                lines.append(f"{indent}  ... ({len(valid_files) - 20} more)")

        body = (
            f"# Source Structure: {self.project.name}\n\n"
            f"**Root:** `{found.relative_to(self.project)}`\n\n"
            "```\n" + "\n".join(lines[:200]) + "\n```\n"
        )

        dest = self.output_dir / "structure.md"
        return (
            1
            if self._write_if_changed(
                dest,
                self._frontmatter(
                    f"{self.project.name} — Structure", "structure", ["source"], body
                ),
            )
            else 0
        )

    def _harvest_git_commits(self) -> int:
        git_dir = self.project / ".git"
        if not git_dir.exists():
            return 0

        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=self.project,
            capture_output=True,
            text=True,
        )
        if head.returncode != 0:
            return 0

        current_hash = head.stdout.strip()
        last_hash = self.state.get("last_commit_hash")

        if last_hash == current_hash:
            return 0

        log = subprocess.run(
            ["git", "log", "-1", "--pretty=%h|%s|%an|%aI"],
            cwd=self.project,
            capture_output=True,
            text=True,
        )
        if log.returncode != 0 or not log.stdout.strip():
            return 0

        parts = log.stdout.strip().split("|")
        if len(parts) != 4:
            return 0

        hash_, msg, author, date = parts
        day = date[:10]

        target_root = self.brain_path if self.brain_path else self.project
        dest = target_root / "commits" / f"{day}.md"

        if dest.exists():
            existing = dest.read_text()
            if hash_ in existing:
                return 0
            body = existing.rstrip() + f"\n- **[{hash_}]** {msg} — *{author}*\n"
            dest.write_text(body)
        else:
            body = f"# Commits on {day}\n\n" f"- **[{hash_}]** {msg} — *{author}*\n"
            dest.write_text(self._frontmatter(f"Commits on {day}", "commit-log", ["git"], body))

        self.state["last_commit_hash"] = current_hash
        return 1

    def _harvest_todos(self) -> int:
        skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".vault", "dist", "build"}
        todos = []

        for root, dirs, files in os.walk(self.project):
            dirs[:] = [
                d
                for d in dirs
                if d not in skip and not d.startswith(".") and not self._is_ignored(Path(root) / d)
            ]
            for f in files:
                if self._is_ignored(Path(root) / f):
                    continue
                if not f.endswith(
                    (".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go", ".java", ".md")
                ):
                    continue
                fp = Path(root) / f
                try:
                    text = fp.read_text(errors="ignore")
                    for match in re.finditer(
                        r"(TODO|FIXME|HACK|BUG|XXX)[\s:]*(.*?)$",
                        text,
                        re.MULTILINE | re.IGNORECASE,
                    ):
                        kind = match.group(1).upper()
                        desc = match.group(2).strip()[:200]
                        rel = fp.relative_to(self.project)
                        todos.append((kind, desc, rel))
                except Exception:
                    pass

        if not todos:
            return 0

        body = f"# Open Items: {self.project.name}\n\n"
        for kind, desc, rel in todos[:50]:
            body += f"- **[{kind}]** {desc} — `{rel}`\n"
        if len(todos) > 50:
            body += f"\n_... and {len(todos) - 50} more_\n"

        dest = self.output_dir / "todos.md"
        return (
            1
            if self._write_if_changed(
                dest,
                self._frontmatter(f"{self.project.name} — Open Items", "todos", ["todos"], body),
            )
            else 0
        )

    def _harvest_health(self) -> int:
        issues = []

        if not (self.project / "README.md").exists():
            issues.append("No README.md")

        git_dir = self.project / ".git"
        if git_dir.exists():
            dirty = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project,
                capture_output=True,
                text=True,
            )
            if dirty.stdout.strip():
                issues.append(f"{len(dirty.stdout.strip().split(chr(10)))} uncommitted file(s)")

        has_tests = any((self.project / d).exists() for d in ("tests", "test", "__tests__", "spec"))
        if not has_tests:
            issues.append("No test directory found")

        if not any((self.project / f).exists() for f in ("LICENSE", "LICENSE.md")):
            issues.append("No LICENSE file")

        body = f"# Health Check: {self.project.name}\n\n"
        if issues:
            body += "**Issues:**\n\n"
            for issue in issues:
                body += f"- ⚠️ {issue}\n"
        else:
            body += "✅ All checks passed.\n"

        dest = self.output_dir / "health.md"
        return (
            1
            if self._write_if_changed(
                dest, self._frontmatter(f"{self.project.name} — Health", "health", ["health"], body)
            )
            else 0
        )

    def _generate_master_overview(self, vaults: list[Path], output_path: Path) -> None:
        now = datetime.now(timezone.utc).isoformat()

        projects_data = []
        for vault in vaults:
            p: dict[str, Any] = {"name": vault.name}

            # If vault is a CentralBrain project folder (e.g. CentralBrain/projects/AgentOS), files are direct.
            # If vault is a standalone repo (e.g. dummy/), files are in .vault/projects/
            if (vault / "tech-stack.md").exists() or (vault / f"{vault.name}.md").exists():
                data_dir = vault
                commits_dir = vault.parent.parent / "commits"  # CentralBrain/commits
            else:
                data_dir = vault / ".vault" / "projects"
                commits_dir = vault / ".vault" / "commits"

            summary = data_dir / f"{vault.name}.md"
            if summary.exists():
                text = summary.read_text()
                m = re.search(r"\*\*Description:\*\*\s*(.+)", text)
                p["description"] = m.group(1).strip() if m else ""
                m = re.search(r"status:\s*(\w+)", text)
                p["status"] = m.group(1) if m else "unknown"
            else:
                p["description"] = ""
                p["status"] = "unknown"

            tech = data_dir / "tech-stack.md"
            p["tech"] = []
            if tech.exists():
                text = tech.read_text()
                m = re.search(r"\*\*Runtime:\*\*\s*(.+)", text)
                if m:
                    p["tech"].append(m.group(1).strip())

            health = data_dir / "health.md"
            p["health"] = "unknown"
            p["issues"] = []
            if health.exists():
                text = health.read_text()
                if "All checks passed" in text:
                    p["health"] = "healthy"
                else:
                    p["health"] = "issues"
                    p["issues"] = re.findall(r"- ⚠️\s*(.+)", text)

            p["recent_commits"] = 0
            if commits_dir.exists():
                for cf in commits_dir.glob("*.md"):
                    text = cf.read_text()
                    p["recent_commits"] += len(re.findall(r"- \*\*\[", text))

            todos = data_dir / "todos.md"
            p["todo_count"] = 0
            if todos.exists():
                text = todos.read_text()
                p["todo_count"] = len(re.findall(r"- \*\*\[", text))

            projects_data.append(p)

        md = (
            f"---\n"
            f"id: master-overview-{datetime.now().strftime('%Y-%m-%d')}\n"
            f"created: {now}\n"
            f"source: daemon\n"
            f"type: master-overview\n"
            f"project_count: {len(vaults)}\n"
            f"---\n\n"
            f"# Master Workspace Overview\n\n"
            f"**Generated:** {now}  \n"
            f"**Projects:** {len(vaults)}\n\n"
            f"## Dashboard\n\n"
            f"| Project | Status | Stack | Health | Commits | TODOs |\n"
            f"|---------|--------|-------|--------|---------|-------|\n"
        )

        for p in projects_data:
            icon = "🟢" if p["health"] == "healthy" else "🟡" if p["health"] == "issues" else "⚪"
            tech = p["tech"][0] if p["tech"] else "—"
            md += f"| **{p['name']}** | {p['status']} | {tech} | {icon} | {p['recent_commits']} | {p['todo_count']} |\n"

        md += "\n## Details\n\n"
        for p in projects_data:
            md += f"### {p['name']}\n\n"
            if p["description"]:
                md += f"{p['description'][:120]}\n\n"
            if p["issues"]:
                md += "**Issues:**\n"
                for i in p["issues"]:
                    md += f"- ⚠️ {i}\n"
                md += "\n"

        all_tech: dict[str, list[str]] = {}
        for p in projects_data:
            for t in p["tech"]:
                all_tech.setdefault(t, []).append(p["name"])

        if all_tech:
            md += "\n## Shared Tech\n\n"
            for tech, projs in sorted(all_tech.items(), key=lambda x: -len(x[1])):
                md += f"- **{tech}:** {', '.join(projs)}\n"

        md += (
            "\n## AI Quick Reference\n\n"
            "```\n"
            "vault read projects/<name>.md\n"
            "vault read projects/tech-stack.md\n"
            "vault read projects/todos.md\n"
            "vault read commits/YYYY-MM-DD.md\n"
            "```\n"
        )

        output_path.write_text(md)

    # ─── HELPERS ───

    def _frontmatter(self, title: str, type_: str, tags: list[str], body: str) -> str:
        now = datetime.now(timezone.utc).isoformat()
        fm = {
            "id": hashlib.sha256(f"{now}:{title}".encode()).hexdigest()[:12],
            "created": now,
            "modified": now,
            "source": "daemon",
            "status": "active",
            "type": type_,
            "tags": tags,
        }
        lines = ["---"]
        for k, v in sorted(fm.items()):
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{k}: {v}")
        lines.append("---")
        lines.append("")
        lines.append(body)
        return "\n".join(lines)

    def _write_if_changed(self, path: Path, content: str) -> bool:
        if path.exists() and path.read_text() == content:
            return False
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return True


def install_hooks(
    project_path: Path, python_executable: str | None = None, brain_path: str | None = None
) -> None:
    """Install post-commit and post-push hooks into a project's .git/hooks/."""
    project_path = Path(project_path).resolve()
    git_dir = project_path / ".git"
    if not git_dir.exists():
        print(f"[warn] No .git repo in {project_path}. Skipping hooks.")
        return

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    python = python_executable or sys.executable
    # Use python -m vault.cli.main daemon so it works even if 'vault' isn't in PATH
    brain_arg = f' --brain "{brain_path}"' if brain_path else ""
    cmd = f'{python} -m vault.cli.main daemon --project "{project_path}"{brain_arg} --trigger'

    # post-commit: fast — only harvest the new commit
    post_commit = hooks_dir / "post-commit"
    post_commit.write_text(f"#!/bin/bash\n" f"# Auto-installed by vault init\n" f"{cmd} commit\n")
    post_commit.chmod(0o755)

    # pre-push: full harvest (git has no post-push hook)
    pre_push = hooks_dir / "pre-push"
    pre_push.write_text(f"#!/bin/bash\n" f"# Auto-installed by vault init\n" f"{cmd} push\n")
    pre_push.chmod(0o755)

    print(f"[vault] Git hooks installed: {hooks_dir}")
