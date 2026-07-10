"""Configuration management for Personal Vault."""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field, asdict


@dataclass
class DirectoryConfig:
    """Configuration for a single contextual directory."""
    name: str
    description: str
    path: str
    vault_path: str
    archive_after_days: int = 120
    required_frontmatter: list[str] = field(default_factory=list)
    required_sections: list[str] = field(default_factory=list)
    templates: list[str] = field(default_factory=list)


@dataclass
class VaultConfig:
    """Root vault configuration."""
    version: str = "1.0"
    auto_archive_days: int = 120
    archive_hidden: bool = True
    directories: list[DirectoryConfig] = field(default_factory=list)
    git_remote: str = ""
    providers: list[str] = field(default_factory=lambda: ["codex", "claude", "cursor", "openai"])
    
    @classmethod
    def load(cls, path: Path | str) -> VaultConfig:
        """Load config from YAML file."""
        path = Path(path)
        if not path.exists():
            return cls.default(path.parent)
        
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        
        dirs = []
        for d in data.get("directories", []):
            dirs.append(DirectoryConfig(**d))
        
        return cls(
            version=data.get("version", "1.0"),
            auto_archive_days=data.get("auto_archive_days", 120),
            archive_hidden=data.get("archive_hidden", True),
            directories=dirs,
            git_remote=data.get("git_remote", ""),
            providers=data.get("providers", ["codex", "claude", "cursor", "openai"]),
        )
    
    @classmethod
    def default(cls, vault_path: Path) -> VaultConfig:
        """Generate default config for a new vault."""
        defaults = [
            ("projects", "Active work, long-lived context", 120),
            ("goals", "OKRs and objectives", 365),
            ("people", "Contacts and collaborators", 0),  # Never archive
            ("meetings", "Meeting notes and action items", 90),
            ("decisions", "Architecture decisions and ADRs", 0),
            ("resources", "Bookmarks, articles, references", 180),
            ("experiments", "Ephemeral prototypes", 30),
            ("threads", "Conversation histories", 120),
            ("reviews", "Retrospectives and weekly reviews", 365),
        ]
        
        directories = []
        for name, desc, days in defaults:
            directories.append(DirectoryConfig(
                name=name,
                description=desc,
                path=str(vault_path / name),
                vault_path=str(vault_path / name),
                archive_after_days=days,
                required_frontmatter=["id", "created", "modified", "tags", "status", "source"],
                templates=[f"vault/templates/{name}.md"],
            ))
        
        return cls(directories=directories)
    
    def save(self, path: Path | str) -> None:
        """Save config to YAML file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        
        data = asdict(self)
        # Convert dataclasses to dicts
        data["directories"] = [asdict(d) for d in self.directories]
        
        with open(path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def get_directory(self, name: str) -> DirectoryConfig | None:
        """Get directory config by name."""
        for d in self.directories:
            if d.name == name:
                return d
        return None
    
    def list_archiveable(self) -> list[DirectoryConfig]:
        """Return directories that have archive_after_days > 0."""
        return [d for d in self.directories if d.archive_after_days > 0]


def find_vault_root(start: Path | str | None = None) -> Path:
    """Find vault root by walking up looking for .vault/config.yaml."""
    if start is None:
        start = Path.cwd()
    else:
        start = Path(start)
    
    current = start.resolve()
    while current != current.parent:
        if (current / ".vault" / "config.yaml").exists():
            return current
        if (current / "AGENTS.md").exists() and (current / ".vault").exists():
            return current
        current = current.parent
    
    # Fallback: check if current dir looks like a vault
    if (start / ".vault").exists() or (start / "AGENTS.md").exists():
        return start.resolve()
    
    raise VaultNotFoundError(f"No vault found in {start} or ancestors. Run 'vault init'.")


class VaultNotFoundError(Exception):
    """Raised when a vault root cannot be found."""
    pass
