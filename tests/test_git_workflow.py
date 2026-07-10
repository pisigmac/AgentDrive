"""Tests for git workflow."""

import pytest
from pathlib import Path
import tempfile
import git

from vault.core.git_workflow import VaultGit


class TestVaultGit:
    def setup_vault(self, tmp_path: Path) -> Path:
        """Create a minimal vault with git repo."""
        repo = git.Repo.init(tmp_path)
        repo.config_writer().set_value("user", "email", "test@example.com").release()
        repo.config_writer().set_value("user", "name", "Test").release()
        
        # Create initial commit on main
        (tmp_path / "AGENTS.md").write_text("# Test")
        repo.index.add(["AGENTS.md"])
        repo.index.commit("Initial")
        
        # Create dev branch
        repo.create_head("dev")
        
        return tmp_path
    
    def test_ensure_branches(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            vg = VaultGit(path)
            branches = [b.name for b in vg.repo.branches]
            assert "main" in branches
            assert "dev" in branches
    
    def test_stage_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            vg = VaultGit(path)
            result = vg.stage_write("projects/test.md", "# Test", "test-agent")
            
            assert result.branch == "dev"
            assert result.file == "projects/test.md"
            assert result.agent == "test-agent"
            assert len(result.hash) == 8
    
    def test_promote_staged(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            self.setup_vault(path)
            
            vg = VaultGit(path)
            vg.stage_write("projects/test.md", "# Test", "test-agent")
            
            promoted = vg.promote_staged("test-pr")
            assert len(promoted) == 1
            assert promoted[0].name == "test.md"
            
            # Check main branch has the file
            vg.checkout("main")
            assert (path / "projects" / "test.md").exists()
