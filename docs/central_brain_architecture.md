# AgentDrive: Central Brain Architecture Reference

## 1. Abstract
The **Central Brain Architecture** is an advanced deployment pattern for AgentDrive. It physically decouples AI memory storage from codebase execution. Rather than cluttering individual software repositories with `.vault/` directories and markdown tracking files, memory is consolidated into a single master repository (the "Central Brain"). AI agents and background daemons operate across distributed codebases but read and write context exclusively from this centralized hub.

## 2. System Components

### 2.1 The Central Brain (Master Repository)
The Central Brain is a dedicated Git repository initialized via `vault init`. 
* **Role**: Acts as the single source of truth for all AI context, architectural decision records (ADRs), meeting notes, and global system configurations.
* **Structure**: Contains the core `.vault/config.yaml`, the `AGENTS.md` global rulebook, and dedicated subdirectories (e.g., `/projects/frontend`, `/projects/backend`) for each linked codebase.

### 2.2 Project Spaces (Linked Codebases)
Project spaces are pure software repositories (e.g., React apps, Python APIs) linked to the Central Brain via `vault link --brain <path>`.
* **Role**: The execution environment where developers and AI agents write functional source code.
* **Structure**: Project spaces contain *no* local `.vault/` data. The only AgentDrive footprint is the presence of Git hooks and a pointer file.

### 2.3 The Breadcrumb Redirect (`AGENTS.md`)
Because local CLI agents (such as `agy` or `kimi`) natively look for an `AGENTS.md` file in the current working directory, linked Project Spaces generate a lightweight "Breadcrumb Redirect."
This file contains no local rules. Instead, it explicitly instructs the parsing AI agent to halt local analysis and traverse the filesystem to the Central Brain's absolute path to absorb project context before executing tasks.

## 3. Data Telemetry & Harvesting

### 3.1 Remote Daemon Execution
When a Project Space is linked, the local Git hooks (`post-commit`, `post-push`) are modified to include the `--brain` routing flag.
When a commit occurs in a Project Space:
1. The local Git hook fires.
2. The `VaultDaemon` spawns and analyzes the local codebase structure, TODOs, and tech stack.
3. Instead of writing outputs locally, the Daemon uses the `--brain` flag to pipe all generated markdown summaries directly into the Central Brain's `projects/` registry.

## 4. The Automated Review Lifecycle (GitHub Actions)
To enforce strict human-in-the-loop governance over AI agents, the Central Brain architecture utilizes a dual-branch standard (`dev` and `main`) synchronized via GitHub Actions.

* **The `dev` Sandbox**: AI agents and the Vault Daemon are strictly forbidden from writing to `main`. All local code execution and all harvested memory updates are committed to the `dev` branch.
* **The Cron Workflow**: A bundled GitHub Action (`agentdrive-auto-pr.yml`) runs nightly at Midnight UTC in both the Project Spaces and the Central Brain.
* **The Promotion**: The workflow automatically detects divergences and generates a Pull Request from `dev` to `main`. 

This guarantees that humans review all AI-generated codebase modifications (in the Project Space PRs) and all automated context updates (in the Central Brain PRs) every morning before they are permanently merged into the stable `main` history.
