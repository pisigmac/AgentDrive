"""Vault health monitoring."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field

from rich.console import Console

from .config import VaultConfig, find_vault_root

console = Console()


@dataclass
class HealthIssue:
    severity: str  # error, warning, info
    category: str
    message: str
    file: str | None = None
    suggestion: str = ""


class VaultHealth:
    """Monitor vault health and detect issues."""
    
    def __init__(self, vault_path: Path | None = None):
        self.vault_path = Path(vault_path) if vault_path else find_vault_root()
        self.config = VaultConfig.load(self.vault_path / ".vault" / "config.yaml")
        self.issues: list[HealthIssue] = []
    
    def check(self) -> dict[str, Any]:
        """Run full health check."""
        self.issues = []
        
        self._check_git_health()
        self._check_frontmatter()
        self._check_orphans()
        self._check_duplicates()
        self._check_stale_entries()
        self._check_broken_links()
        self._check_archive_integrity()
        
        report = {
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "vault_path": str(self.vault_path),
            "total_issues": len(self.issues),
            "errors": len([i for i in self.issues if i.severity == "error"]),
            "warnings": len([i for i in self.issues if i.severity == "warning"]),
            "infos": len([i for i in self.issues if i.severity == "info"]),
            "issues": [
                {
                    "severity": i.severity,
                    "category": i.category,
                    "message": i.message,
                    "file": i.file,
                    "suggestion": i.suggestion,
                }
                for i in self.issues
            ],
        }
        
        # Save report
        report_path = self.vault_path / ".vault" / "index" / "health-report.yaml"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            yaml.dump(report, f, default_flow_style=False, sort_keys=False)
        
        return report
    
    def _check_git_health(self) -> None:
        """Check git repository status."""
        git_dir = self.vault_path / ".git"
        if not git_dir.exists():
            self.issues.append(HealthIssue(
                severity="error",
                category="git",
                message="No git repository found",
                suggestion="Run 'git init' in your vault directory",
            ))
            return
        
        # Check for main/dev branches
        try:
            import git
            repo = git.Repo(self.vault_path)
            branches = [b.name for b in repo.branches]
            
            if "main" not in branches:
                self.issues.append(HealthIssue(
                    severity="error",
                    category="git",
                    message="No 'main' branch found",
                    suggestion="Run 'git checkout -b main'",
                ))
            
            if "dev" not in branches:
                self.issues.append(HealthIssue(
                    severity="warning",
                    category="git",
                    message="No 'dev' branch found",
                    suggestion="Run 'git checkout -b dev' for agent writes",
                ))
            
            if repo.is_dirty():
                self.issues.append(HealthIssue(
                    severity="warning",
                    category="git",
                    message="Working directory has uncommitted changes",
                    suggestion="Commit or stash changes before agent writes",
                ))
                
        except Exception as e:
            self.issues.append(HealthIssue(
                severity="error",
                category="git",
                message=f"Git check failed: {e}",
            ))
    
    def _check_frontmatter(self) -> None:
        """Check all markdown files have required frontmatter."""
        for dir_config in self.config.directories:
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue
            
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                content = file.read_text(encoding="utf-8")
                
                # Check for frontmatter
                if not content.startswith("---"):
                    self.issues.append(HealthIssue(
                        severity="warning",
                        category="frontmatter",
                        message=f"Missing frontmatter",
                        file=str(file.relative_to(self.vault_path)),
                        suggestion="Add YAML frontmatter between --- delimiters",
                    ))
                    continue
                
                # Parse frontmatter
                try:
                    parts = content.split("---", 2)
                    if len(parts) >= 2:
                        meta = yaml.safe_load(parts[1]) or {}
                        
                        for field in dir_config.required_frontmatter:
                            if field not in meta:
                                self.issues.append(HealthIssue(
                                    severity="warning",
                                    category="frontmatter",
                                    message=f"Missing required field: {field}",
                                    file=str(file.relative_to(self.vault_path)),
                                    suggestion=f"Add '{field}: value' to frontmatter",
                                ))
                except Exception as e:
                    self.issues.append(HealthIssue(
                        severity="error",
                        category="frontmatter",
                        message=f"Invalid frontmatter: {e}",
                        file=str(file.relative_to(self.vault_path)),
                    ))
    
    def _check_orphans(self) -> None:
        """Find files not linked from any other file."""
        all_files = set()
        all_links = set()
        
        for dir_config in self.config.directories:
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue
            
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                rel = str(file.relative_to(self.vault_path))
                all_files.add(rel)
                
                content = file.read_text(encoding="utf-8")
                # Find wiki links [[...]]
                import re
                links = re.findall(r"\[\[(.*?)\]\]", content)
                for link in links:
                    all_links.add(link)
        
        # Check for unlinked files (excluding people, which are referenced by name)
        for file in all_files:
            if "people/" in file:
                continue
            
            # Check if file is referenced anywhere
            stem = Path(file).stem
            referenced = any(
                stem in link or link in stem
                for link in all_links
            )
            
            if not referenced:
                self.issues.append(HealthIssue(
                    severity="info",
                    category="orphan",
                    message=f"File not linked from any other file",
                    file=file,
                    suggestion="Add a [[wiki link]] from a related file",
                ))
    
    def _check_duplicates(self) -> None:
        """Find potential duplicate entries."""
        names: dict[str, list[str]] = {}
        
        for dir_config in self.config.directories:
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue
            
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                stem = file.stem.lower()
                rel = str(file.relative_to(self.vault_path))
                
                if stem in names:
                    names[stem].append(rel)
                else:
                    names[stem] = [rel]
        
        for stem, files in names.items():
            if len(files) > 1:
                self.issues.append(HealthIssue(
                    severity="warning",
                    category="duplicate",
                    message=f"Potential duplicate: {len(files)} files with similar name",
                    file=files[0],
                    suggestion=f"Consider merging: {', '.join(files)}",
                ))
    
    def _check_stale_entries(self) -> None:
        """Find entries that should have been archived."""
        for dir_config in self.config.directories:
            if dir_config.archive_after_days <= 0:
                continue
            
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue
            
            threshold = timedelta(days=dir_config.archive_after_days)
            
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
                age = datetime.now(timezone.utc) - mtime
                
                if age > threshold * 1.5:  # 50% over threshold
                    self.issues.append(HealthIssue(
                        severity="warning",
                        category="stale",
                        message=f"File is {age.days} days old (threshold: {dir_config.archive_after_days})",
                        file=str(file.relative_to(self.vault_path)),
                        suggestion=f"Run 'vault archive --threshold {dir_config.archive_after_days}'",
                    ))
    
    def _check_broken_links(self) -> None:
        """Find wiki links that point to non-existent files."""
        import re
        
        all_files = set()
        for dir_config in self.config.directories:
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue
            for file in dir_path.rglob("*.md"):
                all_files.add(file.stem)
        
        for dir_config in self.config.directories:
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue
            
            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue
                
                content = file.read_text(encoding="utf-8")
                links = re.findall(r"\[\[(.*?)\]\]", content)
                
                for link in links:
                    # Strip display text if present: [[file|display]]
                    target = link.split("|")[0].strip()
                    if target not in all_files:
                        self.issues.append(HealthIssue(
                            severity="warning",
                            category="broken_link",
                            message=f"Broken wiki link: [[{target}]]",
                            file=str(file.relative_to(self.vault_path)),
                            suggestion=f"Create {target}.md or fix the link",
                        ))
    
    def _check_archive_integrity(self) -> None:
        """Verify archive structure is intact."""
        archive_path = self.vault_path / ".vault" / "archive"
        if not archive_path.exists():
            return
        
        for file in archive_path.rglob("*.md"):
            content = file.read_text(encoding="utf-8")
            if not content.startswith("---"):
                self.issues.append(HealthIssue(
                    severity="error",
                    category="archive",
                    message="Archive file missing metadata header",
                    file=str(file.relative_to(self.vault_path)),
                    suggestion="Archive may be corrupted",
                ))
