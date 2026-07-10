"""Tests for health checker."""

import pytest
from pathlib import Path
import tempfile

from vault.core.config import VaultConfig
from vault.core.health import VaultHealth


class TestVaultHealth:
    def test_healthy_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / ".vault").mkdir()
            (path / "projects").mkdir()
            
            # Good file with frontmatter
            (path / "projects" / "good.md").write_text(
                "---\nid: 1\ncreated: 2026-01-01\nmodified: 2026-01-01\ntags: []\nstatus: active\nsource: test\n---\n\n# Good"
            )
            
            config = VaultConfig.default(path)
            config.save(path / ".vault" / "config.yaml")
            
            health = VaultHealth(path)
            report = health.check()
            
            assert report["errors"] == 0
    
    def test_missing_frontmatter(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / ".vault").mkdir()
            (path / "projects").mkdir()
            
            # Bad file without frontmatter
            (path / "projects" / "bad.md").write_text("# Bad")
            
            config = VaultConfig.default(path)
            config.save(path / ".vault" / "config.yaml")
            
            health = VaultHealth(path)
            report = health.check()
            
            assert report["warnings"] > 0
