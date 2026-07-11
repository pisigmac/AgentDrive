"""Archive engine: move stale files to hidden .vault/archive."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field

import yaml
from rich.console import Console

from .config import VaultConfig

console = Console()


@dataclass
class ArchiveEntry:
    original: str
    archived_to: str
    age_days: int
    reason: str
    archived_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ArchiveEngine:
    """Moves files older than threshold to .vault/archive with preserved structure."""

    PROTECTED = {".git", ".vault", "templates", ".github"}

    def __init__(self, vault_path: Path, config: VaultConfig | None = None):
        self.vault_path = Path(vault_path)
        self.config = config or VaultConfig.load(self.vault_path / ".vault" / "config.yaml")
        self.archive_path = self.vault_path / ".vault" / "archive"
        self.archive_path.mkdir(parents=True, exist_ok=True)

    def scan(self, threshold_days: int | None = None) -> list[Path]:
        """Find stale files across configured directories."""
        threshold = timedelta(days=threshold_days or self.config.auto_archive_days)
        stale = []

        for dir_config in self.config.list_archiveable():
            dir_path = Path(dir_config.vault_path)
            if not dir_path.exists():
                continue

            for file in dir_path.rglob("*.md"):
                if file.name.startswith("."):
                    continue

                mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
                age = datetime.now(timezone.utc) - mtime

                if age > threshold:
                    stale.append(file)

        return stale

    def archive(self, file: Path, reason: str | None = None) -> Path:
        """Move file to .vault/archive/YYYY/MM/ with metadata."""
        mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
        rel_path = file.relative_to(self.vault_path)

        # Archive destination: .vault/archive/2026/07/projects/old-file.md
        dest = self.archive_path / f"{mtime.year}" / f"{mtime.month:02d}" / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Read original content
        content = file.read_text(encoding="utf-8")

        # Add archive metadata header
        age_days = (datetime.now(timezone.utc) - mtime).days
        header = f"""---
archived: {datetime.now(timezone.utc).isoformat()}
original_path: {rel_path}
original_modified: {mtime.isoformat()}
age_days: {age_days}
archive_reason: {reason or f"age > {self.config.auto_archive_days} days"}
---

"""

        dest.write_text(header + content, encoding="utf-8")

        # Remove from live vault
        file.unlink()

        # Write tombstone for traceability
        tombstone = file.parent / f"{file.stem}.archived"
        tombstone.write_text(
            f"Archived to: {dest.relative_to(self.vault_path)}\n"
            f"Date: {datetime.now(timezone.utc).isoformat()}\n"
        )

        return dest

    def run(self, threshold_days: int | None = None) -> dict[str, Any]:
        """Full archive pass. Returns report."""
        stale = self.scan(threshold_days)
        archived = []

        for file in stale:
            mtime = datetime.fromtimestamp(file.stat().st_mtime, tz=timezone.utc)
            age_days = (datetime.now(timezone.utc) - mtime).days

            dest = self.archive(file)
            archived.append(
                ArchiveEntry(
                    original=str(file.relative_to(self.vault_path)),
                    archived_to=str(dest.relative_to(self.vault_path)),
                    age_days=age_days,
                    reason=f"age > {threshold_days or self.config.auto_archive_days} days",
                )
            )

        # Clean empty directories
        self._clean_empty_dirs()

        # Write report
        report = {
            "run_date": datetime.now(timezone.utc).isoformat(),
            "threshold_days": threshold_days or self.config.auto_archive_days,
            "scanned": len(stale),
            "archived": len(archived),
            "entries": [self._entry_to_dict(e) for e in archived],
        }

        report_path = self.vault_path / ".vault" / "index" / "archive-report.yaml"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w") as f:
            yaml.dump(report, f, default_flow_style=False, sort_keys=False)

        return report

    def _entry_to_dict(self, entry: ArchiveEntry) -> dict[str, Any]:
        return {
            "original": entry.original,
            "archived_to": entry.archived_to,
            "age_days": entry.age_days,
            "reason": entry.reason,
            "archived_at": entry.archived_at,
        }

    def _clean_empty_dirs(self) -> None:
        """Remove empty directories in vault (except protected)."""
        for dirpath in sorted(self.vault_path.rglob("*"), reverse=True):
            if not dirpath.is_dir():
                continue
            if dirpath.name in self.PROTECTED or ".vault" in str(dirpath):
                continue
            if not any(dirpath.iterdir()):
                try:
                    dirpath.rmdir()
                except OSError:
                    pass

    def restore(self, archive_path: Path) -> Path:
        """Restore a file from archive to live vault."""
        content = archive_path.read_text(encoding="utf-8")

        # Parse frontmatter to find original path
        original_path = None
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 2:
                meta = yaml.safe_load(parts[1])
                original_path = meta.get("original_path")

        if not original_path:
            raise ValueError(f"Cannot determine original path for {archive_path}")

        target = self.vault_path / original_path
        target.parent.mkdir(parents=True, exist_ok=True)

        # Strip archive header and write
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                target.write_text(parts[2].lstrip(), encoding="utf-8")
        else:
            target.write_text(content, encoding="utf-8")

        # Remove tombstone if exists
        tombstone = target.parent / f"{target.stem}.archived"
        if tombstone.exists():
            tombstone.unlink()

        return target

    def list_archived(self) -> list[dict[str, Any]]:
        """List all archived files with metadata."""
        archived = []
        for file in self.archive_path.rglob("*.md"):
            content = file.read_text(encoding="utf-8")
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 2:
                    meta = yaml.safe_load(parts[1])
                    archived.append(
                        {
                            "path": str(file.relative_to(self.vault_path)),
                            "original_path": meta.get("original_path"),
                            "archived": meta.get("archived"),
                            "reason": meta.get("archive_reason"),
                        }
                    )
        return archived
