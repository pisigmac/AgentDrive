"""Agent capability registry. Self-documenting skills."""

from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any
from dataclasses import dataclass, field


@dataclass
class SkillInput:
    name: str
    type: str
    required: bool = True
    default: Any = None


@dataclass
class SkillOutput:
    type: str
    path_template: str | None = None
    schema: str | None = None


@dataclass
class SkillPermission:
    read: list[str] = field(default_factory=list)
    write: list[str] = field(default_factory=list)


@dataclass
class SkillSandbox:
    network: bool = False
    filesystem: str = "restricted"
    timeout: str = "30s"


@dataclass
class Skill:
    id: str
    name: str
    description: str
    version: str
    inputs: list[SkillInput]
    outputs: list[SkillOutput]
    permissions: SkillPermission
    providers: list[str]
    sandbox: SkillSandbox
    schedule: str | None = None


class CapabilityRegistry:
    """Self-documenting skill registry."""
    
    def __init__(self, vault_path: Path):
        self.vault_path = Path(vault_path)
        self.registry_file = self.vault_path / ".vault" / "registry" / "skills.yaml"
        self.skills = self._load()
    
    def _load(self) -> list[Skill]:
        if not self.registry_file.exists():
            return []
        
        with open(self.registry_file) as f:
            data = yaml.safe_load(f) or {}
        
        skills = []
        for s in data.get("skills", []):
            skills.append(self._parse_skill(s))
        return skills
    
    def _parse_skill(self, data: dict) -> Skill:
        inputs = [SkillInput(**i) for i in data.get("inputs", [])]
        outputs = [SkillOutput(**o) for o in data.get("outputs", [])]
        perms = SkillPermission(**data.get("permissions", {}))
        sandbox = SkillSandbox(**data.get("sandbox", {}))
        
        return Skill(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            version=data.get("version", "1.0.0"),
            inputs=inputs,
            outputs=outputs,
            permissions=perms,
            providers=data.get("providers", ["all"]),
            sandbox=sandbox,
            schedule=data.get("schedule"),
        )
    
    def discover(self, provider: str | None = None, permission: str | None = None) -> list[Skill]:
        """Filter skills by provider and permission."""
        results = self.skills
        if provider:
            results = [
                s for s in results
                if "all" in s.providers or provider in s.providers
            ]
        if permission:
            results = [
                s for s in results
                if permission in s.permissions.read or permission in s.permissions.write
            ]
        return results
    
    def get(self, skill_id: str) -> Skill | None:
        return next((s for s in self.skills if s.id == skill_id), None)
    
    def validate(self, skill_id: str, agent: str) -> tuple[bool, str]:
        """Check if agent can execute skill."""
        skill = self.get(skill_id)
        if not skill:
            return False, f"Skill '{skill_id}' not found in registry"
        
        if "all" not in skill.providers and agent not in skill.providers:
            return False, f"Skill '{skill_id}' not enabled for provider '{agent}'"
        
        return True, "OK"
    
    def add(self, skill: Skill) -> None:
        """Add a new skill to registry."""
        if self.get(skill.id):
            raise ValueError(f"Skill '{skill.id}' already exists")
        self.skills.append(skill)
        self._save()
    
    def _save(self) -> None:
        data = {
            "version": "1.0",
            "skills": [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "version": s.version,
                    "inputs": [{"name": i.name, "type": i.type, "required": i.required, "default": i.default} for i in s.inputs],
                    "outputs": [{"type": o.type, "path_template": o.path_template, "schema": o.schema} for o in s.outputs],
                    "permissions": {"read": s.permissions.read, "write": s.permissions.write},
                    "providers": s.providers,
                    "sandbox": {"network": s.sandbox.network, "filesystem": s.sandbox.filesystem, "timeout": s.sandbox.timeout},
                    "schedule": s.schedule,
                }
                for s in self.skills
            ]
        }
        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def list_scheduled(self) -> list[Skill]:
        """Return skills with cron schedules."""
        return [s for s in self.skills if s.schedule]
