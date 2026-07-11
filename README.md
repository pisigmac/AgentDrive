# 🧠 Personal Vault

**Give your AI Agents a Git-Native, Infinite Memory Drive.**

Say goodbye to black-box vector databases and locked-in memory platforms. **Personal Vault** turns your local filesystem into a highly structured, self-updating, markdown-based memory system. Whether you use Claude, Cursor, OpenAI, or a custom script, your agents can seamlessly read, write, and reason over an ever-evolving context that lives right alongside your code.

---

## Quick Start

### One-Command Install

```bash
curl -sSL https://raw.githubusercontent.com/pisigmac/personal-vault/main/setup.sh | bash
```

Or manually:

```bash
# 1. Install the CLI globally
git clone https://github.com/pisigmac/personal-vault.git
cd personal-vault
pip install -e .

# 2. Go to your own project and initialize a vault
cd ~/my-project
vault init
```

### Adopting Existing Projects

You can run `vault init` safely inside projects that already have code and a `.git` repository! Here is what happens:
- It detects your existing `.git` repo and gracefully creates a new `dev` branch for AI agents to write to.
- It safely scaffolds the `.vault/` configuration and templates.
- **Tip:** `vault init` commits these setup files automatically. Ensure your working tree is clean before running it to avoid bundling uncommitted changes into the initialization commit.
- **Auto-Summarization:** The vault won't scan your codebase immediately on init. Instead, a background daemon will automatically wake up and summarize your tech stack, folder structure, open TODOs, and health status **the very next time you make a commit**. 
- To force an immediate summarization without waiting for a commit, simply run:
  ```bash
  vault daemon
  ```

### What You Get

```
vault/
├── AGENTS.md                 # Root governance (all providers read this)
├── projects/                   # Active work
├── people/                     # Contacts (never archived)
├── meetings/                   # Meeting notes
├── decisions/                  # Architecture decisions
├── goals/                      # OKRs and objectives
├── resources/                  # Bookmarks, articles
├── experiments/                # Ephemeral prototypes
├── threads/                    # Conversation histories
├── reviews/                    # Retrospectives
├── templates/                  # Markdown templates
├── .vault/
│   ├── skills/                 # Executable agent skills
│   ├── registry/               # Capability registry
│   ├── staging/                # Pending writes (dev branch)
│   ├── archive/                # Hidden — 120-day+ files
│   ├── index/                  # Search indices
│   └── schemas/                # Validation schemas
└── .github/workflows/
    └── auto-archive.yml        # Weekly maintenance
```

---

## Core Concepts

### 1. Git Branching for Agent Safety

All agent writes go to `dev`. Human approval merges to `main`.

```
User prompt → Agent writes → Staged to dev → PR raised → Human merges → main
```

```bash
vault stage path/to/file.md "# New content" --agent claude
vault promote                    # Merge dev → main
```

### 2. Contextual Directories

Your life is organized into 10+ contextual buckets. Each has its own archive rules, templates, and frontmatter requirements.

| Directory | Purpose | Archive | Never Archive |
|-----------|---------|---------|---------------|
| `projects/` | Active work | 120 days | — |
| `people/` | Contacts | Never | ✓ |
| `decisions/` | ADRs | Never | ✓ |
| `experiments/` | Prototypes | 30 days | — |
| `meetings/` | Notes | 90 days | — |
| `threads/` | Conversations | 120 days | — |

### 3. Archive Engine

Files older than their threshold automatically move to `.vault/archive/YYYY/MM/` with preserved metadata. Tombstones remain in place for traceability.

```bash
vault archive --dry-run          # Preview what would archive
vault archive --threshold 90     # Archive files older than 90 days
vault archive --list             # View archived files
```

### 4. Capability Registry

Self-documenting skills that any provider can discover and execute.

```bash
vault registry --list            # List all skills
vault registry --provider claude # Filter by provider
```

### 5. MCP Server (Any Provider)

Expose your vault to Claude, Cursor, Codex, or any MCP client.

```bash
vault mcp --install              # Install to Claude/Cursor
vault mcp --run                  # Start MCP server
```

**Available MCP Tools:**
- `vault_search` — Semantic + keyword search
- `vault_read` — Read any file
- `vault_write` — Stage write to dev branch
- `vault_archive` — Run archive engine
- `vault_health` — Full health check
- `vault_status` — Git status
- `vault_skills` — List capabilities
- `vault_new` — Create from template
- `vault_related` — Find related files

---

## CLI Commands

```bash
# Initialize
vault init                       # Create new vault in current directory
vault init ~/my-vault --name my-vault # Custom path and name

# Status & Health
vault status                     # Git + health overview
vault health --report            # Full diagnostic report

# Search
vault search "kubernetes"        # Keyword search
vault search "design" --semantic # Semantic rerank
vault search "agents" -d projects -d people  # Limit directories

# Archive
vault archive                    # Archive stale files
vault archive --dry-run          # Preview only
vault archive --list             # List archived

# Registry
vault registry --list            # All skills
vault registry --provider codex   # Filtered

# Cron (Scheduled Tasks)
vault cron --enable              # Start scheduler
vault cron --disable             # Stop scheduler
vault cron --status              # Show jobs
vault cron --edit                # Edit cron.yaml

# MCP
vault mcp --install              # Auto-configure Claude/Cursor
vault mcp --run                  # Start stdio server


# Create Entries
vault new project "NeeVibe"     # From template
vault new person "Alice Chen"   # From template
vault new meeting "Sprint Review"

# Index
vault index                      # Build search index
```

---

## Configuration

Edit `.vault/config.yaml`:

```yaml
version: "1.0"
auto_archive_days: 120
archive_hidden: true

directories:
  - name: "projects"
    description: "Active work"
    path: "/home/user/vault/projects"
    vault_path: "/home/user/vault/projects"
    archive_after_days: 120
    required_frontmatter: [id, created, modified, tags, status, source]
    templates: ["vault/templates/project.md"]
  
  - name: "people"
    description: "Contacts"
    path: "/home/user/vault/people"
    vault_path: "/home/user/vault/people"
    archive_after_days: 0  # Never archive
```

---

## AGENTS.md Governance

Every vault has a root `AGENTS.md` that ALL providers must read before acting. It defines:

1. **Branch Rule** — All writes to `dev`, never `main`
2. **Approval Gate** — Stage to `.vault/staging/`, raise PR
3. **Schema Rule** — Every file needs frontmatter
4. **Archive Rule** — Old files move to `.vault/archive/`
5. **Source Tag** — Mark who wrote each file
6. **No Secrets** — Never store tokens in vault files
7. **Cross-Reference** — Use `[[WikiLinks]]` between entries

Nested directories can have their own `AGENTS.md` that supplements (not overrides) root rules.

---

## GitHub Actions

Auto-archive and health checks run weekly via GitHub Actions:

```yaml
# .github/workflows/auto-archive.yml
- Runs every Sunday at 2am UTC
- Archives stale files
- Runs health check
- Raises PR to main for human approval
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     MCP CLIENTS                             │
│  Claude    Cursor    Codex    OpenAI    Any LLM             │
│     │         │        │         │          │                │
└─────┼─────────┼────────┼─────────┼──────────┼──────────────┘
      │         │        │         │          │
      └─────────┴────────┴─────────┴──────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │   MCP Server        │
              │   (vault.mcp)       │
              └─────────────────────┘
                          │
              ┌─────────┼───────────┼───────────┐
              ▼           ▼           ▼           ▼
        ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐
        │ Search  │  │ Archive │  │  Git    │  │ Daemon  │
        │ Engine  │  │ Engine  │  │ Workflow│  │ (Hooks &│
        │(.index) │  │(.archive│  │(dev/main│  │ Harvest)│
        └─────────┘  │ 120d)   │  │   PR)   │  └─────────┘
                   └─────────┘  └─────────┘
                          │
                          ▼
              ┌─────────────────────┐
              │      VAULT FS       │
              │                     │
              │  projects/          │
              │  people/            │
              │  decisions/         │
              │  meetings/          │
              │  resources/         │
              │  goals/             │
              │  reviews/           │
              │  experiments/       │
              │  threads/           │
              │                     │
              │  .vault/skills/     │
              │  .vault/registry/   │
              │  .vault/staging/    │
              │  .vault/archive/    │
              │  .vault/index/      │
              └─────────────────────┘
```

---

## Development

```bash
# Clone
git clone https://github.com/pisigmac/personal-vault.git
cd personal-vault

# Install
pip install -e ".[dev]"

# Test
pytest tests/ -v

# Lint
ruff check vault/
black vault/
```

---

## License

MIT
