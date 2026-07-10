"""Tests for capability registry."""

import pytest
from pathlib import Path
import tempfile

from vault.core.registry import CapabilityRegistry, Skill, SkillInput, SkillOutput, SkillPermission, SkillSandbox


class TestCapabilityRegistry:
    def test_load_registry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / ".vault" / "registry").mkdir(parents=True)
            
            import yaml
            data = {
                "version": "1.0",
                "skills": [
                    {
                        "id": "test-skill",
                        "name": "Test Skill",
                        "description": "A test",
                        "version": "1.0.0",
                        "inputs": [],
                        "outputs": [],
                        "permissions": {"read": [], "write": []},
                        "providers": ["all"],
                        "sandbox": {"network": False, "filesystem": "restricted", "timeout": "30s"},
                    }
                ]
            }
            with open(path / ".vault" / "registry" / "skills.yaml", "w") as f:
                yaml.dump(data, f)
            
            reg = CapabilityRegistry(path)
            assert len(reg.skills) == 1
            assert reg.get("test-skill") is not None
    
    def test_validate_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / ".vault" / "registry").mkdir(parents=True)
            
            import yaml
            data = {
                "version": "1.0",
                "skills": [
                    {
                        "id": "claude-only",
                        "name": "Claude Only",
                        "description": "Only for Claude",
                        "version": "1.0.0",
                        "inputs": [],
                        "outputs": [],
                        "permissions": {"read": [], "write": []},
                        "providers": ["claude"],
                        "sandbox": {"network": False, "filesystem": "restricted", "timeout": "30s"},
                    }
                ]
            }
            with open(path / ".vault" / "registry" / "skills.yaml", "w") as f:
                yaml.dump(data, f)
            
            reg = CapabilityRegistry(path)
            
            ok, msg = reg.validate("claude-only", "claude")
            assert ok is True
            
            ok, msg = reg.validate("claude-only", "codex")
            assert ok is False
            assert "not enabled" in msg
