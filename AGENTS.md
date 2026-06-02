# AGENTS.md

## Goal

Keep `agent-command-receipt` a small, dependency-free Python CLI that creates and verifies hashed command evidence receipts for coding-agent handoffs.

## Constraints

- Prefer standard-library Python only.
- Do not execute shell commands, inspect shell history, or imply a command ran unless the caller supplied evidence.
- Keep receipt keys stable: `schema_version`, `command`, `status`, `exit_code`, `cwd`, `created_at`, `notes`, and `evidence`.
- Keep examples realistic but sanitized. Never commit secrets, private paths, generated package metadata, or virtualenvs.

## Verification

Run these before committing behavior changes:

```sh
make test
make lint
make build
make smoke
git diff --check
```

Use `repo-flightcheck` before public promotion:

```sh
node /Users/manuelsampedro/Documents/Codex/2026-05-21/repo-flightcheck/bin/repo-flightcheck.js . --check-remote --strict --threshold 80
```
