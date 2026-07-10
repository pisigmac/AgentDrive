"""Tests for search engine."""

import pytest
from pathlib import Path
import tempfile

from vault.core.config import VaultConfig
from vault.core.search import VaultSearch


class TestVaultSearch:
    def setup_vault(self, tmp_path: Path) -> Path:
        (tmp_path / ".vault").mkdir()
        (tmp_path / "projects").mkdir()
        (tmp_path / "people").mkdir()
        
        (tmp_path / "projects" / "neevibe.md").write_text(
            "---\nid: 1\ntags: [frontend, design]\n---\n\n# NeeVibe\n\nA design system project."
        )
        (tmp_path / "projects" / "agentmaya.md").write_text(
            "---\nid: 2\ntags: [ai, agents]\n---\n\n# AgentMaya\n\nAI agent platform."
        )
        (tmp_path / "people" / "alice.md").write_text(
            "---\nid: 3\ntags: [collaborator]\n---\n\n# Alice Chen\n\nWorks on AI."
        )
        
        config = VaultConfig.default(tmp_path)
        config.save(tmp_path / ".vault" / "config.yaml")
        
        return tmp_path
    
    def test_keyword_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            searcher = VaultSearch(path)
            results = searcher.search("design", limit=5)
            
            assert len(results) > 0
            assert any("neevibe" in r.path for r in results)
    
    def test_tag_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            searcher = VaultSearch(path)
            results = searcher.search("agents", limit=5)
            
            assert any("agentmaya" in r.path for r in results)
    
    def test_no_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            searcher = VaultSearch(path)
            results = searcher.search("nonexistent-query-12345")
            
            assert len(results) == 0
