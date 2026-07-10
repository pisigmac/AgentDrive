"""Git workflow: dev branch staging, PR to main."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from dataclasses import dataclass

import git
from rich.console import Console

console = Console()


@dataclass
class StageResult:
    branch: str
    file: str
    hash: str
    agent: str
    pr_url: str | None = None


@dataclass
class PRResult:
    pr_id: str
    from_branch: str
    to_branch: str
    title: str
    description: str
    status: str


class VaultGit:
    """Manages git workflow for vault writes."""
    
    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.repo = git.Repo(self.vault_path)
        self.staging = self.vault_path / ".vault" / "staging"
        self.staging.mkdir(parents=True, exist_ok=True)
        self._ensure_branches()
    
    def _ensure_branches(self) -> None:
        """Ensure main and dev branches exist."""
        branches = [b.name for b in self.repo.branches]
        
        if "main" not in branches:
            # Create main from current
            if self.repo.active_branch.name != "main":
                self.repo.create_head("main")
        
        if "dev" not in branches:
            main = self.repo.heads.main
            self.repo.create_head("dev", main)
    
    def checkout(self, branch: str) -> None:
        """Checkout a branch, creating if needed."""
        if branch not in [b.name for b in self.repo.branches]:
            self.repo.create_head(branch)
        self.repo.heads[branch].checkout()
    
    def stage_write(
        self,
        filepath: Path | str,
        content: str,
        agent: str,
        metadata: dict[str, Any] | None = None,
    ) -> StageResult:
        """Write content to staging on dev branch."""
        self.checkout("dev")
        
        rel_path = Path(filepath)
        if rel_path.is_absolute():
            rel_path = rel_path.relative_to(self.vault_path)
        
        # Write to staging
        stage_path = self.staging / rel_path
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        stage_path.write_text(content, encoding="utf-8")
        
        # Generate hash
        file_hash = hashlib.sha256(content.encode()).hexdigest()[:8]
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Build commit message
        meta_str = ""
        if metadata:
            meta_str = " | " + " ".join(f"{k}:{v}" for k, v in metadata.items())
        
        commit_msg = f"[{agent}] {rel_path} | hash:{file_hash} | ts:{timestamp}{meta_str}"
        
        # Git add and commit
        self.repo.index.add([str(stage_path.relative_to(self.vault_path))])
        self.repo.index.commit(commit_msg)
        
        return StageResult(
            branch="dev",
            file=str(rel_path),
            hash=file_hash,
            agent=agent,
        )
    
    def raise_pr(
        self,
        title: str,
        description: str,
        from_branch: str = "dev",
        to_branch: str = "main",
    ) -> PRResult:
        """Create a PR from dev to main."""
        pr_id = f"vault-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        
        # Try to push dev branch
        try:
            origin = self.repo.remote("origin")
            origin.push(refspec=f"{from_branch}:{from_branch}")
        except Exception:
            pass  # No remote configured
        
        return PRResult(
            pr_id=pr_id,
            from_branch=from_branch,
            to_branch=to_branch,
            title=title,
            description=description,
            status="pending_approval",
        )
    
    def promote_staged(self, pr_id: str | None = None) -> list[Path]:
        """Move staged files to live paths and merge to main."""
        self.checkout("dev")
        
        promoted = []
        for staged in self.staging.rglob("*.md"):
            rel = staged.relative_to(self.staging)
            target = self.vault_path / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            
            # Move (not copy) — staging is transient
            shutil_move = __import__("shutil").move
            shutil_move(str(staged), str(target))
            promoted.append(target)
        
        # Clean empty staging dirs
        self._clean_empty_dirs(self.staging)
        
        # Commit promotion
        if promoted:
            self.repo.index.add([str(p.relative_to(self.vault_path)) for p in promoted])
            msg = f"Promote {pr_id} to main" if pr_id else "Promote staged to main"
            self.repo.index.commit(msg)
        
        # Merge to main
        self.checkout("main")
        self.repo.merge_tree("dev")
        self.repo.index.commit(f"Merge dev: {pr_id or 'manual promotion'}")
        
        # Back to dev
        self.checkout("dev")
        
        return promoted
    
    def _clean_empty_dirs(self, path: Path) -> None:
        """Remove empty directories recursively."""
        for dirpath in sorted(path.rglob("*"), reverse=True):
            if dirpath.is_dir() and not any(dirpath.iterdir()):
                dirpath.rmdir()
    
    def diff_staged(self) -> str:
        """Show diff between last main commit and current dev."""
        main_commit = self.repo.heads.main.commit
        dev_commit = self.repo.heads.dev.commit
        
        diff = main_commit.diff(dev_commit)
        output = []
        for d in diff:
            output.append(f"{d.change_type}: {d.a_path}")
        return "\n".join(output) if output else "No staged changes."
    
    def status(self) -> dict[str, Any]:
        """Return git status summary."""
        return {
            "branch": self.repo.active_branch.name,
            "is_dirty": self.repo.is_dirty(),
            "untracked": [str(p) for p in self.repo.untracked_files],
            "modified": [item.a_path for item in self.repo.index.diff(None)],
            "staged_files": [str(p.relative_to(self.vault_path)) for p in self.staging.rglob("*.md")],
            "last_commit": self.repo.head.commit.hexsha[:8],
            "commit_message": self.repo.head.commit.message.strip(),
        }
