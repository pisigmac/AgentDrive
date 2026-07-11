# Agent Governance & Context

This repository is governed by the AgentDrive framework. All autonomous AI agents (Cursor, Claude, Antigravity, etc.) must adhere to the following rules:

1. **Branch Rule**: All writes go to `dev` branch. Never commit to `main` directly.
2. **Approval Gate**: Every write must be staged in `.vault/staging/` and raised as a PR.
3. **No Raw Secrets**: Never write API keys, tokens, or passwords into any vault file.

---
*Note: Global system memory is tracked securely outside this repository. Read architecture decisions from: `~/.agentdrive/brains/CentralBrain/projects/AgentDrive`*
