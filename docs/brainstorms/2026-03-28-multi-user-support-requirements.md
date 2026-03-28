---
date: 2026-03-28
topic: multi-user-support
---

# Multi-User Support

## Problem Frame

bud is designed for agentic workflows where remote AI agents (WhatsApp, Telegram bots) manage finances on behalf of different people. Currently, all data lives in a single `~/.bud/` directory with one database, one config, and one set of credentials. This means only one person's financial data can exist per OS user, which blocks the primary use case of a single server running bud for multiple people via agents.

## Requirements

- R1. Each bud user gets a fully isolated data directory under `~/.bud/users/<name>/` containing their own `bud.db`, `config.json`, `credentials.json`, and `sync_meta.json`.
- R2. The active user is selected via `--user <name>` CLI flag (highest priority) or `BUD_USER` environment variable (fallback). When neither is provided, the user defaults to `default`.
- R3. Users are created implicitly: the first command targeting a non-existent user auto-creates their directory and initializes a fresh database (equivalent to `bud db init`).
- R4. Cloud sync (push/pull) operates per-user. Each user has their own bucket URL, credentials, and sync metadata in their own directory.
- R5. Existing single-user data in `~/.bud/` (root-level `bud.db`, `config.json`, `credentials.json`) must be migrated to `~/.bud/users/default/` so current users experience no data loss.

## Success Criteria

- An agent can run `bud --user alice t c -v -50 -d "groceries"` and `bud --user bob t c -v -100 -d "rent"` on the same machine, with each command operating on completely separate databases.
- Existing users who upgrade see their data seamlessly available under the `default` user with no manual migration steps.
- No user can accidentally read or modify another user's data through normal bud commands.

## Scope Boundaries

- No authentication or access control between users (OS-level trust assumed).
- No shared accounts or cross-user data access.
- No `bud user` management commands (list, create, delete) in this iteration.
- No changes to the project/account model within a single user's database.

## Key Decisions

- **Subdirectories over separate home dirs**: Keeps everything under `~/.bud/` for discoverability and simpler management. Avoids requiring external path configuration.
- **Implicit user creation over explicit**: Reduces friction for agentic callers. An agent doesn't need a setup step before first use.
- **`default` user over raw `~/.bud/`**: Uniform directory structure (always `~/.bud/users/<name>/`) simplifies the code. One code path, not two.

## Dependencies / Assumptions

- `config_store.py` is the single source of truth for `CONFIG_DIR`, `DB_PATH`, and `DB_URL`. All other modules import from it. Centralizing the path resolution there should propagate everywhere.
- `database.py` also defines `DB_PATH` and `DB_URL` independently — this duplication must be resolved during planning.

## Outstanding Questions

### Deferred to Planning

- [Affects R2][Technical] How should `--user` be threaded through Click's context? Global option on the top-level group vs. callback that sets paths before any command runs.
- [Affects R3][Technical] Should auto-init run full `db init` (with default project creation) or a minimal schema-only init?
- [Affects R5][Technical] What's the best migration strategy — auto-migrate on first run, or a one-time `bud db migrate-user` command?
- [Affects R1][Needs research] Verify all code paths that reference `CONFIG_DIR`, `DB_PATH`, or `DB_URL` to ensure none bypass `config_store.py`.

## Next Steps

-> `/ce:plan` for structured implementation planning
