#!/usr/bin/env bash
# AgentDrive Setup Script
# One-command install: curl -sSL https://raw.githubusercontent.com/you/agentdrive/main/setup.sh | bash
# Or: wget -qO- https://raw.githubusercontent.com/you/agentdrive/main/setup.sh | bash

set -euo pipefail

VAULT_VERSION="1.0.0"
REPO_URL="https://github.com/pisigmac/AgentDrive.git"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║           AgentDrive Setup v${VAULT_VERSION}               ║"
echo "║     Filesystem-as-Memory for AI Agents (Any Provider)      ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ─── Detect Environment ───
OS=$(uname -s)
ARCH=$(uname -m)
HAS_GIT=false
HAS_PYTHON=false
HAS_UV=false
HAS_PIP=false

command -v git &>/dev/null && HAS_GIT=true
command -v python3 &>/dev/null && HAS_PYTHON=true
command -v uv &>/dev/null && HAS_UV=true
command -v pip3 &>/dev/null && HAS_PIP=true

echo "[1/7] Detecting environment..."
echo "    OS: ${OS} | Arch: ${ARCH}"
echo "    Git: $HAS_GIT | Python: $HAS_PYTHON | uv: $HAS_UV | pip: $HAS_PIP"
echo ""

if [[ "$HAS_GIT" == false ]]; then
    echo "ERROR: Git is required. Install it first:"
    echo "  macOS: brew install git"
    echo "  Ubuntu: sudo apt-get install git"
    exit 1
fi

if [[ "$HAS_PYTHON" == false ]]; then
    echo "ERROR: Python 3.10+ is required."
    exit 1
fi

# ─── Get Vault Path ───
echo "[2/7] Where should your vault live?"
DEFAULT_VAULT="$HOME/agentdrive"
read -rp "  Path [${DEFAULT_VAULT}]: " VAULT_PATH
VAULT_PATH=${VAULT_PATH:-$DEFAULT_VAULT}
VAULT_PATH=$(eval echo "$VAULT_PATH")
VAULT_PATH=$(cd "$(dirname "$VAULT_PATH")" && pwd)/$(basename "$VAULT_PATH")

if [[ -d "$VAULT_PATH/.git" ]]; then
    echo ""
    echo "WARNING: $VAULT_PATH is already a git repo."
    read -rp "  Continue and adopt it? [y/N]: " ADOPT
    if [[ ! "$ADOPT" =~ ^[Yy]$ ]]; then
        echo "Aborted."
        exit 0
    fi
    ADOPTING=true
else
    ADOPTING=false
fi

mkdir -p "$VAULT_PATH"
cd "$VAULT_PATH"

# ─── Git Init ───
echo ""
echo "[3/7] Initializing git repository..."
if [[ "$ADOPTING" == false ]]; then
    git init -b main
    git config user.email "vault@localhost"
    git config user.name "AgentDrive"
fi

# Create dev branch if not exists
if ! git branch --list dev | grep -q dev; then
    git checkout -b dev
    git checkout -b main
    git checkout dev
fi

# ─── Install Python Package ───
echo ""
echo "[4/7] Installing vault CLI..."

# Clone into a temporary directory, install, and clean up!
INSTALL_DIR=$(mktemp -d)
echo "    Cloning AgentDrive repository into temporary folder..."
git clone -q "$REPO_URL" "$INSTALL_DIR"

if [[ "$HAS_UV" == true ]]; then
    echo "    Using uv (fast) for installation"
    uv pip install "$INSTALL_DIR" --system
elif [[ "$HAS_PIP" == true ]]; then
    echo "    Using pip for installation"
    pip3 install "$INSTALL_DIR"
else
    echo "ERROR: Could not find pip or uv to install the package."
    exit 1
fi

echo "    Cleaning up temporary files..."
rm -rf "$INSTALL_DIR"

# ─── Interactive Directory Setup ───
echo ""
echo "[5/7] Configuring contextual directories..."
echo ""
echo "    AgentDrive organizes your life into contextual buckets."
echo "    You can map your EXISTING directories, or use our defaults."
echo ""

# Config file path
CONFIG_DIR="$VAULT_PATH/.vault"
mkdir -p "$CONFIG_DIR"

# Default directory mapping
mapfile -t DEFAULT_DIRS << 'EOF'
projects|Active work, long-lived context|projects
goals|OKRs and objectives|goals
people|Contacts and collaborators|people
meetings|Meeting notes and action items|meetings
decisions|Architecture decisions and ADRs|decisions
resources|Bookmarks, articles, references|resources
experiments|Ephemeral prototypes (< 30 days)|experiments
threads|Conversation histories|threads
reviews|Retrospectives and weekly reviews|reviews
EOF

echo "    Scanning for existing directories to adopt..."

# Auto-detect common directories
DETECTED=()
for dir in Documents Notes Work Personal Projects Ideas; do
    if [[ -d "$HOME/$dir" ]]; then
        DETECTED+=("$HOME/$dir")
    fi
done

if [[ ${#DETECTED[@]} -gt 0 ]]; then
    echo "    Found these directories:"
    for d in "${DETECTED[@]}"; do
        echo "      • $(basename "$d") → $d"
    done
    echo ""
fi

# Build config
CONFIG_FILE="$CONFIG_DIR/directories.yaml"
cat > "$CONFIG_FILE" << 'HEADER'
# AgentDrive Directory Configuration
# Each entry maps a contextual bucket to a filesystem path
# You can add, remove, or reorder these anytime.

version: "1.0"
auto_archive_days: 120
archive_hidden: true

directories:
HEADER

for entry in "${DEFAULT_DIRS[@]}"; do
    IFS='|' read -r NAME DESC DEFAULT <<< "$entry"
    
    # Check if user has existing dir
    EXISTING=""
    for d in "${DETECTED[@]}"; do
        if [[ "$(basename "$d")" == "$NAME" || "$(basename "$d")" == "${DEFAULT}" ]]; then
            EXISTING="$d"
            break
        fi
    done
    
    echo ""
    echo "  📁 $NAME — $DESC"
    if [[ -n "$EXISTING" ]]; then
        read -rp "    Adopt existing '$EXISTING'? [Y/n]: " ADOPT_DIR
        ADOPT_DIR=${ADOPT_DIR:-Y}
        if [[ "$ADOPT_DIR" =~ ^[Yy]$ ]]; then
            ACTUAL_PATH="$EXISTING"
            # Create symlink in vault
            ln -sf "$EXISTING" "$VAULT_PATH/$NAME" 2>/dev/null || cp -r "$EXISTING" "$VAULT_PATH/$NAME"
            echo "      ✓ Adopted $EXISTING"
        else
            mkdir -p "$VAULT_PATH/$NAME"
            ACTUAL_PATH="$VAULT_PATH/$NAME"
            echo "      ✓ Created new"
        fi
    else
        read -rp "    Create '$NAME'? [Y/n/custom path]: " CREATE
        CREATE=${CREATE:-Y}
        if [[ "$CREATE" =~ ^[Yy]$ ]]; then
            mkdir -p "$VAULT_PATH/$NAME"
            ACTUAL_PATH="$VAULT_PATH/$NAME"
            echo "      ✓ Created $VAULT_PATH/$NAME"
        elif [[ "$CREATE" != "N" && "$CREATE" != "n" ]]; then
            # Custom path
            mkdir -p "$CREATE"
            ACTUAL_PATH="$CREATE"
            ln -sf "$CREATE" "$VAULT_PATH/$NAME" 2>/dev/null || true
            echo "      ✓ Linked $CREATE"
        else
            ACTUAL_PATH="disabled"
            echo "      ✗ Skipped"
        fi
    fi
    
    if [[ "$ACTUAL_PATH" != "disabled" ]]; then
        cat >> "$CONFIG_FILE" << EOF
  - name: "$NAME"
    description: "$DESC"
    path: "$ACTUAL_PATH"
    vault_path: "$VAULT_PATH/$NAME"
    archive_after_days: 120
    required_frontmatter:
      - id
      - created
      - modified
      - tags
      - status
      - source
    required_sections: []
    templates:
      - "vault/templates/${NAME}.md"
EOF
    fi
done

# ─── Hidden Infrastructure ───
echo ""
echo "[6/7] Creating hidden infrastructure..."

mkdir -p "$VAULT_PATH/.vault/skills"
mkdir -p "$VAULT_PATH/.vault/registry"
mkdir -p "$VAULT_PATH/.vault/staging"
mkdir -p "$VAULT_PATH/.vault/archive"
mkdir -p "$VAULT_PATH/.vault/index"
mkdir -p "$VAULT_PATH/.vault/schemas"
mkdir -p "$VAULT_PATH/templates"
mkdir -p "$VAULT_PATH/.github/workflows"

# Gitignore for hidden dirs
cat > "$VAULT_PATH/.gitignore" << 'EOF'
# Vault infrastructure (hidden)
.vault/staging/
.vault/index/
.vault/archive/*.tmp

# But keep archive structure and schemas
!.vault/archive/
!.vault/schemas/
!.vault/registry/
!.vault/skills/

# OS files
.DS_Store
Thumbs.db
EOF

# ─── AGENTS.md ───
echo "    Writing AGENTS.md governance..."

cat > "$VAULT_PATH/AGENTS.md" << 'EOF'
# AgentDrive — Agent Governance

## Scope
This AGENTS.md governs ALL AI providers (Claude, Codex, Cursor, OpenAI, etc.) 
accessing this vault via MCP or direct filesystem.

## Rules

1. **Branch Rule**: All writes go to `dev` branch. Never commit to `main` directly.
2. **Approval Gate**: Every write must be staged in `.vault/staging/` and raised as a PR.
3. **Schema Rule**: Every markdown file MUST include frontmatter per its directory config.
4. **Archive Rule**: Files older than threshold are moved to `.vault/archive/`. Do not delete.
5. **Source Tag**: Every file must include `source: <provider>` in frontmatter.
6. **No Raw Secrets**: Never write API keys, tokens, or passwords into any vault file.
7. **Cross-Reference**: Link related entries with `[[WikiLinks]]` or `related:` frontmatter.
8. **Confidence Tag**: Mark speculative content with `confidence: low`.

## Directory Quick Reference

| Directory | Purpose | Archive | Template |
|-----------|---------|---------|----------|
| projects/ | Active work | 120d | templates/project.md |
| people/ | Contacts | Never | templates/person.md |
| goals/ | OKRs | 365d | templates/goal.md |
| meetings/ | Meeting notes | 90d | templates/meeting.md |
| decisions/ | ADRs | Never | templates/decision.md |
| resources/ | Bookmarks | 180d | templates/resource.md |
| experiments/ | Prototypes | 30d | templates/experiment.md |
| threads/ | Conversations | 120d | templates/thread.md |
| reviews/ | Retrospectives | 365d | templates/review.md |

## Skill Execution
- Before running any skill, read `.vault/registry/skills.yaml`.
- Check provider permissions: not all skills work with all providers.
- All skill output goes to `.vault/staging/` first.

## Human Override
When in doubt, ask. When confident, stage. Never force-push to main.
EOF

# Nested AGENTS.md for projects/
cat > "$VAULT_PATH/projects/AGENTS.md" << 'EOF'
# projects/ — Agent Rules

## Inherits
All rules from root AGENTS.md apply.

## Specific Rules
1. Every project MUST have a `GOAL.md` section or file.
2. Project status cycle: active → stalled → completed → archived.
3. Link all related people in frontmatter: `people: [alice-chen, bob-smith]`
4. Update `modified` timestamp on every edit.
EOF

# Nested AGENTS.md for people/
cat > "$VAULT_PATH/people/AGENTS.md" << 'EOF'
# people/ — Agent Rules

## Inherits
All rules from root AGENTS.md apply.

## Specific Rules
1. People files NEVER archive. Relationships are permanent context.
2. Update `last_contact` field after every interaction.
3. Include `communication_style` section.
4. Tag with `relationship: [collaborator, client, friend, mentor]`
EOF

# ─── Templates ───
echo "    Writing markdown templates..."

cat > "$VAULT_PATH/templates/project.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
people: []
related_projects: []
---

# {{title}}

**Status:** active | stalled | completed | archived  
**Priority:** P0 | P1 | P2 | P3  
**Last Active:** {{date}}  

## Description

## GOAL.md
Long-running objectives

## RESULT.md
Completed work and verification

## Decisions
- [[decision-slug]]

## Meetings
- [[meeting-slug]]

## Notes
EOF

cat > "$VAULT_PATH/templates/person.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
last_contact: {{date}}
relationship: collaborator
---

# {{name}}

**Role:**  
**Company:**  
**Relationship:** collaborator | client | friend | mentor  

## Context
How I know them, projects we've worked on

## Communication Style
Formal / casual / technical / business

## Notes
- Thread references: [[thread-slug]]
- Projects: [[project-slug]]

## Last Contact
{{date}}
EOF

cat > "$VAULT_PATH/templates/meeting.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
attendees: []
projects: []
---

# Meeting: {{title}}

**Date:** {{date}}  
**Attendees:**  
**Project:**  

## Agenda

## Notes

## Action Items
- [ ] 

## Decisions
- 
EOF

cat > "$VAULT_PATH/templates/decision.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
projects: []
---

# Decision: {{title}}

**Status:** proposed | accepted | rejected | superseded  
**Date:** {{date}}  
**Context:**  

## Problem

## Options Considered

## Decision

## Consequences

## Related
- [[project-slug]]
EOF

cat > "$VAULT_PATH/templates/resource.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
url: ""
author: ""
---

# {{title}}

**URL:**  
**Author:**  
**Type:** article | video | book | tool | paper  

## Summary

## Key Takeaways

## Related
- [[project-slug]]
EOF

cat > "$VAULT_PATH/templates/goal.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
quarter: ""
---

# Goal: {{title}}

**Quarter:**  
**Status:** active | paused | completed  
**Priority:** P0 | P1 | P2  

## Objective

## Key Results
- [ ] KR1: 
- [ ] KR2: 
- [ ] KR3: 

## Projects Supporting This Goal
- [[project-slug]]

## Progress
EOF

cat > "$VAULT_PATH/templates/experiment.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: low
project: ""
---

# Experiment: {{title}}

**Hypothesis:**  
**Project:**  
**Expected Duration:**  

## Method

## Results

## Conclusion
- [ ] Success — promote to project
- [ ] Failure — document and archive
- [ ] Inconclusive — extend or pivot

## Related
- [[project-slug]]
EOF

cat > "$VAULT_PATH/templates/thread.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
participants: []
projects: []
---

# Thread: {{title}}

**Date:** {{date}}  
**Participants:**  
**Agent:**  

## Summary

## Key Decisions

## Action Items
- [ ] 

## Full Log
EOF

cat > "$VAULT_PATH/templates/review.md" << 'EOF'
---
id: {{uuid}}
created: {{iso_timestamp}}
modified: {{iso_timestamp}}
tags: []
status: active
source: {{agent}}
confidence: high
period: ""
---

# Review: {{title}}

**Period:**  
**Type:** weekly | monthly | quarterly  

## What Went Well

## What Didn't

## Learnings

## Next Period Focus

## Projects Reviewed
- [[project-slug]]
EOF

# ─── Registry ───
cat > "$VAULT_PATH/.vault/registry/skills.yaml" << 'EOF'
version: "1.0"
skills:
  - id: new-person
    name: Create Person Note
    description: Generate a structured person file from context
    version: 1.0.0
    inputs:
      - name: name
        type: string
        required: true
      - name: role
        type: string
        required: false
      - name: company
        type: string
        required: false
    outputs:
      - type: file
        path_template: "people/{slug}.md"
        schema: person
    permissions:
      read: [templates/person.md]
      write: [people/]
    providers: [codex, claude, cursor, openai, all]
    sandbox:
      network: false
      filesystem: restricted
      timeout: 30s

  - id: new-project
    name: Create Project Note
    description: Bootstrap a new project directory
    version: 1.0.0
    inputs:
      - name: title
        type: string
        required: true
      - name: priority
        type: string
        default: P2
    outputs:
      - type: file
        path_template: "projects/{slug}.md"
        schema: project
    permissions:
      read: [templates/project.md]
      write: [projects/]
    providers: [all]

  - id: archive-stale
    name: Archive Stale Content
    description: Move files older than threshold to .vault/archive
    version: 1.0.0
    inputs:
      - name: threshold_days
        type: integer
        default: 120
    outputs:
      - type: report
        path: .vault/index/archive-report.yaml
    permissions:
      read: [projects/, people/, threads/, experiments/, meetings/, decisions/, resources/, reviews/, goals/]
      write: [.vault/archive/, .vault/index/]
    schedule: "0 2 * * 0"
    providers: [all]

  - id: health-check
    name: Vault Health Check
    description: Scan for stale entries, orphans, duplicates
    version: 1.0.0
    inputs: []
    outputs:
      - type: report
        path: .vault/index/health-report.yaml
    permissions:
      read: [all]
      write: [.vault/index/]
    schedule: "0 9 * * 1"
    providers: [all]

  - id: stale-project-reminder
    name: Stale Project Reminder
    description: Find projects inactive > 30 days
    version: 1.0.0
    inputs: []
    outputs:
      - type: report
        path: .vault/index/stale-projects.yaml
    permissions:
      read: [projects/]
      write: [.vault/index/]
    schedule: "0 9 * * *"
    providers: [all]

  - id: vault-search
    name: Semantic Vault Search
    description: Search across all vault content
    version: 1.0.0
    inputs:
      - name: query
        type: string
        required: true
      - name: directories
        type: array
        default: []
    outputs:
      - type: results
    permissions:
      read: [all]
    providers: [all]
EOF

# ─── Cron Config ───
cat > "$VAULT_PATH/.vault/cron.yaml" << 'EOF'
version: "1.0"
jobs:
  - skill: archive-stale
    schedule: "0 2 * * 0"
    description: "Archive files older than 120 days"
    enabled: true

  - skill: health-check
    schedule: "0 9 * * 1"
    description: "Weekly vault health report"
    enabled: true

  - skill: stale-project-reminder
    schedule: "0 9 * * *"
    description: "Daily reminder for projects inactive > 30 days"
    enabled: true
EOF

# ─── GitHub Actions ───
cat > "$VAULT_PATH/.github/workflows/auto-archive.yml" << 'EOF'
name: Vault Auto-Archive

on:
  schedule:
    - cron: '0 2 * * 0'  # Sundays at 2am UTC
  workflow_dispatch:

jobs:
  archive:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: dev
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install vault
        run: pip install agentdrive
      
      - name: Run archive
        run: vault archive --threshold 120
      
      - name: Run health check
        run: vault health --report
      
      - name: Commit and raise PR
        run: |
          git config user.name "Vault Bot"
          git config user.email "vault-bot@localhost"
          git add -A
          git commit -m "[bot] Weekly archive + health check" || true
          
          # Push to dev
          git push origin dev
          
          # Create PR to main using GitHub CLI
          gh pr create \
            --title "[bot] Weekly vault maintenance" \
            --body "Auto-generated archive and health report." \
            --base main \
            --head dev \
            --label "automated" \
            || true
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
EOF

# ─── Initial Commit ───
echo ""
echo "[7/7] Creating initial commit..."

git add -A
git commit -m "[vault] Initial setup v${VAULT_VERSION}" || true

git checkout main
git merge dev --no-ff -m "[vault] Bootstrap from dev" || true

# ─── Summary ───
echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║                    SETUP COMPLETE                            ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Vault path: $VAULT_PATH"
echo "  Branch:    main (stable) / dev (agent writes)"
echo ""
echo "  Directories configured:"
for d in "$VAULT_PATH"/*/; do
    name=$(basename "$d")
    if [[ ! "$name" =~ ^\.|^templates$ ]]; then
        echo "    ✓ $name"
    fi
done
echo ""
echo "  Next steps:"
echo "    1. vault status          # Check vault health"
echo "    2. vault config          # Edit directory config"
echo "    3. vault mcp --install   # Install MCP server for Claude/Cursor"
echo "    4. vault cron --enable   # Start background scheduler"
echo ""
echo "  Or manually:"
echo "    cd $VAULT_PATH"
echo "    git checkout dev         # Switch to dev branch"
echo "    # Let your AI agent work, then raise PR to main"
echo ""
