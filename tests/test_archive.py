"""Tests for archive engine."""

import pytest
from pathlib import Path
import tempfile
from datetime import datetime, timezone, timedelta

from vault.core.config import VaultConfig
from vault.core.archive import ArchiveEngine


class TestArchiveEngine:
    def setup_vault(self, tmp_path: Path) -> Path:
        """Create vault with old and new files."""
        (tmp_path / ".vault").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "people").mkdir()
        
        # Old file (should archive)
        old_file = tmp_path / "projects" / "old-project.md"
        old_file.write_text("---\nid: test\n---\n\n# Old")
        old_time = datetime.now(timezone.utc) - timedelta(days=200)
        import os
        os.utime(old_file, (old_time.timestamp(), old_time.timestamp()))
        
        # New file (should not archive)
        new_file = tmp_path / "projects" / "new-project.md"
        new_file.write_text("---\nid: test2\n---\n\n# New")
        
        # Person file (should not archive, archive_after_days=0)
        person_file = tmp_path / "people" / "alice.md"
        person_file.write_text("---\nid: test3\n---\n\n# Alice")
        old_time2 = datetime.now(timezone.utc) - timedelta(days=200)
        os.utime(person_file, (old_time2.timestamp(), old_time2.timestamp()))
        
        config = VaultConfig.default(tmp_path)
        config.save(tmp_path / ".vault" / "config.yaml")
        
        return tmp_path
    
    def test_scan_finds_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            engine = ArchiveEngine(path)
            stale = engine.scan(threshold_days=120)
            
            assert len(stale) == 1
            assert stale[0].name == "old-project.md"
    
    def test_archive_moves_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            engine = ArchiveEngine(path)
            old_file = path / "projects" / "old-project.md"
            
            dest = engine.archive(old_file)
            
            assert not old_file.exists()
            assert dest.exists()
            assert ".vault/archive" in str(dest)
            
            # Check tombstone
            tombstone = path / "projects" / "old-project.archived"
            assert tombstone.exists()
