"""Tests for vault configuration."""

import pytest
from pathlib import Path
import tempfile

from vault.core.config import VaultConfig, DirectoryConfig, find_vault_root, VaultNotFoundError


class TestVaultConfig:
    def test_default_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            config = VaultConfig.default(path)
            
            assert config.version == "1.0"
            assert len(config.directories) == 9
            assert config.get_directory("projects") is not None
            assert config.get_directory("people") is not None
    
    def test_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            config = VaultConfig.default(path)
            config.save(path / "config.yaml")
            
            loaded = VaultConfig.load(path / "config.yaml")
            assert loaded.version == config.version
            assert len(loaded.directories) == len(config.directories)
    
    def test_archiveable_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            config = VaultConfig.default(path)
            archiveable = config.list_archiveable()
            
            # people and decisions should not be archiveable (0 days)
            assert len(archiveable) == 7
            assert config.get_directory("people") not in archiveable
    
    def test_get_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            config = VaultConfig.default(path)
            
            assert config.get_directory("projects") is not None
            assert config.get_directory("nonexistent") is None


class TestFindVaultRoot:
    def test_finds_vault_with_agents_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / "AGENTS.md").write_text("# Test")
            (path / ".vault").mkdir()
            
            found = find_vault_root(path)
            assert found == path.resolve()
    
    def test_finds_vault_with_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / ".vault").mkdir()
            (path / ".vault" / "config.yaml").write_text("version: '1.0'\n")
            
            found = find_vault_root(path)
            assert found == path.resolve()
    
    def test_raises_when_no_vault(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(VaultNotFoundError):
                find_vault_root(tmp)
