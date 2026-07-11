# AgentDrive: Central Brain & Automated PR Lifecycle
**Implementation Plan**

This document outlines the step-by-step technical implementation to transition AgentDrive into a multi-repo, "Central Brain" architecture with daily automated PR reviews.

## Objective
1. Allow users to designate a central "Brain Space" repository.
2. Allow users to link "Project Spaces" to the Brain without polluting the projects with `.vault/` folders.
3. Automatically route all Daemon harvesting from linked projects directly into the Central Brain's `dev` branch.
4. Establish a strict `dev` → `main` auto-PR lifecycle across both Brain and Project repositories via GitHub Actions.

---

## Phase 1: The `vault link` Command
**File to modify:** `vault/cli/main.py`
- Add a new CLI command: `vault link --brain <path_to_brain>`
- **Logic:**
  1. Validate the `path_to_brain` contains a valid `.vault/config.yaml`.
  2. Ensure the local project is a Git repository.
  3. Automatically create `dev` and `main` branches in the local project (if they don't exist).
  4. Register the local project's path into the Brain's `.vault/config.yaml` programmatically.
  5. Install modified Git hooks (`post-commit`, `post-push`) into the local project that pass the `--brain` flag to the daemon.

## Phase 2: Daemon Routing Updates
**File to modify:** `vault/core/daemon.py`
- Modify the `VaultDaemon` initialization to accept an optional `brain_path`.
- **Logic:**
  1. If `brain_path` is provided, the daemon will scan the local project (the `README`, `todos`, `tech-stack`, etc.) but will **write** the markdown output to `brain_path/projects/<project_name>/`.
  2. Ensure that any commits made by the daemon in the background are strictly committed to the `dev` branch of the Brain space.

## Phase 3: The Daily Auto-PR Workflows
**Files to create:** `vault/templates/github-pr-action.yml` & updates to `setup.sh` / `main.py`
- Create a reusable GitHub Action template that triggers daily at midnight via a `cron` schedule.
- **Workflow Logic:**
  1. Check out the repository.
  2. Check for differences between `dev` and `main`.
  3. Use `gh pr create` to open an automated Pull Request from `dev` to `main`.
- **Deployment:**
  - When `vault init` is run (Brain creation), inject `auto-pr.yml` into `.github/workflows/`.
  - When `vault link` is run (Project linking), inject `auto-pr.yml` into the local project's `.github/workflows/`.

## Phase 4: `AGENTS.md` Revisions
**File to modify:** `setup.sh` (or `vault/cli/main.py` string templates)
- Update the default `AGENTS.md` instructions.
- Add strict explicit rules that AI agents must ALWAYS commit to `dev`.
- Explain the nightly PR workflow so that AI agents understand they are writing to a staging environment that a human will review the next morning.

---

## Execution Checklist
- [ ] Implement `vault link` CLI command.
- [ ] Refactor `VaultDaemon` to support `--brain` routing.
- [ ] Create `auto-pr.yml` GitHub Action template.
- [ ] Update `vault link` and `vault init` to distribute the YAML workflows.
- [ ] Update `AGENTS.md` governance rules.
- [ ] Validate locally with dummy repos.
- [ ] Delete this plan.
