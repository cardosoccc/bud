---
title: "feat: Multi-user support via --user flag and BUD_USER env var"
type: feat
status: completed
date: 2026-03-28
origin: docs/brainstorms/2026-03-28-multi-user-support-requirements.md
---

# feat: Multi-user support

## Overview

Enable multiple people to use bud on the same OS user by isolating each user's data under `~/.bud/users/<name>/`. User selection via `--user` CLI flag (highest priority), `BUD_USER` env var (fallback), or `default` (final fallback). Designed primarily for agentic multi-tenant deployments where AI agents manage finances for different people on a shared server.

## Problem Statement / Motivation

bud is designed for agentic workflows where remote AI agents manage finances on behalf of different people. Currently all data lives in a single `~/.bud/` directory — one database, one config, one set of credentials. This blocks the primary use case of a single server running bud for multiple people via agents (see origin: `docs/brainstorms/2026-03-28-multi-user-support-requirements.md`).

## Proposed Solution

### Directory Structure

```
~/.bud/
└── users/
    ├── default/
    │   ├── bud.db
    │   ├── config.json
    │   ├── credentials.json
    │   └── sync_meta.json
    ├── alice/
    │   ├── bud.db
    │   ├── config.json
    │   ├── credentials.json
    │   └── sync_meta.json
    └── bob/
        └── ...
```

### User Selection Precedence

1. `--user <name>` CLI flag (must appear before subcommand: `bud --user alice t list`)
2. `BUD_USER` env var
3. Falls back to `"default"`

### Path Resolution Architecture

Replace module-level constants in `config_store.py` with a **mutable module-level `_active_user`** variable and **functions** that resolve paths dynamically:

```python
# bud/commands/config_store.py

_BUD_ROOT = Path.home() / ".bud"
_active_user: str = "default"

def set_active_user(name: str) -> None:
    global _active_user
    _validate_username(name)
    _active_user = name

def get_config_dir() -> Path:
    return _BUD_ROOT / "users" / _active_user

def get_db_path() -> Path:
    return get_config_dir() / "bud.db"

def get_db_url() -> str:
    return f"sqlite+aiosqlite:///{get_db_path()}"

def get_config_file() -> Path:
    return get_config_dir() / "config.json"
```

The Click group callback calls `set_active_user()` before any subcommand runs:

```python
# bud/cli.py

@click.group()
@click.option("--user", "-u", envvar="BUD_USER", default="default",
              help="User profile name (default: 'default')")
def cli(user):
    """bud - budget management cli."""
    set_active_user(user)
```

Click's `envvar` parameter handles the `BUD_USER` fallback natively — no custom code needed.

## Technical Considerations

### Architecture Impacts

**Module-level constants → functions (breaking change to internal API)**

Every file that imports `CONFIG_DIR`, `DB_PATH`, `DB_URL`, `CONFIG_FILE` from `config_store.py` must switch to calling the corresponding function. Current importers:

| File | Currently imports | Changes to |
|---|---|---|
| `bud/commands/db.py` | `get_db_url()` | No change (already a function call) |
| `bud/commands/db_commands.py` | `DB_PATH`, `set_config_value` | `get_db_path()` |
| `bud/commands/sync.py` | `CONFIG_DIR`, `DB_PATH`, `get_config_value` | `get_config_dir()`, `get_db_path()` |
| `bud/credentials.py` | `CONFIG_DIR` | `get_config_dir()` |
| `bud/cli.py` | `set_config_value` | No change + add `set_active_user` |

Additionally, `sync.py` derives `SYNC_META_FILE = CONFIG_DIR / "sync_meta.json"` at module level — this must become a function call too.

Similarly, `credentials.py` derives `CREDENTIALS_FILE` at module level — same treatment.

**database.py module-level engine must be removed**

`bud/database.py` (line 23) creates `engine = _make_engine()` at import time, bound to hardcoded `~/.bud/bud.db`. This fires as a side effect whenever any model is imported (all models import `Base` from `database.py`). Since CLI commands actually use `bud/commands/db.py`'s `get_engine()` for sessions, the module-level engine in `database.py` is dead code. Remove `engine`, `AsyncSessionLocal`, `get_db()`, and `create_tables()` from `database.py`, keeping only `Base` and model imports.

**Dead code: `bud/config.py`**

Contains a third duplicate `database_url` definition in a Pydantic `Settings` class that is not imported anywhere. Delete this file.

**Hardcoded `".bud"` mkdir calls**

- `bud/commands/db.py` line 31: `Path.home().joinpath(".bud").mkdir(...)` → use `get_config_dir().mkdir(...)`
- `bud/database.py` line 37: same pattern inside `create_tables()` — removed along with the dead code above

### Username Validation

Validate usernames with `^[a-zA-Z0-9_-]+$` and max 64 characters. This prevents:
- Path traversal (`--user ../../etc`)
- Filesystem issues (spaces, special chars)
- Unreasonably long directory names

Raise `click.BadParameter` on invalid usernames.

### Implicit User Creation

On first use, `get_session()` in `db.py` already calls `mkdir(parents=True, exist_ok=True)` and creates tables if missing. This naturally handles implicit user creation — no additional code needed beyond pointing paths at the right directory. Full `db init` behavior (including default project creation) should run on first access, matching the current first-run experience (see origin: deferred question on auto-init strategy).

### Migration Strategy

For existing users with data in `~/.bud/` root:

```python
def _maybe_migrate_legacy_data():
    """Move legacy ~/.bud/ root files to ~/.bud/users/default/."""
    legacy_db = _BUD_ROOT / "bud.db"
    target_dir = _BUD_ROOT / "users" / "default"

    if not legacy_db.exists() or target_dir.exists():
        return  # nothing to migrate, or already migrated

    target_dir.mkdir(parents=True, exist_ok=True)
    for filename in ("bud.db", "config.json", "credentials.json", "sync_meta.json"):
        src = _BUD_ROOT / filename
        if src.exists():
            shutil.copy2(src, target_dir / filename)

    # Verify copy succeeded before removing originals
    if (target_dir / "bud.db").exists():
        for filename in ("bud.db", "config.json", "credentials.json", "sync_meta.json"):
            src = _BUD_ROOT / filename
            if src.exists():
                src.unlink()
```

Called from `set_active_user("default")` — only triggers when user is "default" and legacy files exist. Copy-then-verify-then-delete for safety. If interrupted mid-copy, next run detects `target_dir.exists()` and skips (partial state is safe because the original files remain).

### Cloud Sync

Per-user sync works naturally: each user's `config.json` has their own `bucket` URL and `credentials.json` has their own cloud credentials. The remote key (`bud.db`) is the same for all users, but since each user configures their own bucket, there's no collision. Document that users sharing a bucket URL will overwrite each other (see origin: R4 decision).

### Concurrent Access

Two agents targeting **different** users: no contention (separate SQLite files). Two agents targeting the **same** user: existing SQLite locking behavior applies. This is an existing limitation, not introduced by this feature.

## System-Wide Impact

- **Interaction graph**: `cli()` group callback → `set_active_user()` → sets `_active_user` in `config_store` → all subsequent `get_config_dir()`/`get_db_path()`/`get_db_url()` calls resolve to user-specific paths → `get_session()` opens user-specific DB → command executes in isolation
- **Error propagation**: Invalid username raises `click.BadParameter` at CLI parse time, before any DB or file operations
- **State lifecycle risks**: Migration copy-then-delete is the only risky state transition. Mitigated by checking target existence before starting and verifying copy before deleting source.
- **API surface parity**: All CLI commands automatically get multi-user support through the path resolution change. No command-specific changes needed.

## Acceptance Criteria

- [ ] `bud --user alice t c -v -50 -d "groceries"` creates `~/.bud/users/alice/bud.db` and stores the transaction there
- [ ] `bud --user bob t list` shows only bob's transactions (separate DB)
- [ ] `BUD_USER=alice bud t list` works identically to `bud --user alice t list`
- [ ] `--user` flag takes precedence over `BUD_USER` env var
- [ ] Running `bud t list` with no flag/env defaults to `~/.bud/users/default/`
- [ ] Existing `~/.bud/bud.db` is auto-migrated to `~/.bud/users/default/bud.db` on first run
- [ ] `bud --user "../../../tmp/evil"` fails with a validation error
- [ ] `bud db push --user alice` uses alice's bucket config and credentials
- [ ] `bud config set bucket s3://alice-bucket --user alice` writes to alice's config.json
- [ ] Dead code removed: `bud/config.py` deleted, `database.py` module-level engine removed

## Implementation Phases

### Phase 1: Path Resolution Refactor

Make all paths dynamic without changing directory structure yet.

1. **`bud/commands/config_store.py`**: Replace `CONFIG_DIR`, `CONFIG_FILE`, `DB_PATH`, `DB_URL` constants with `get_config_dir()`, `get_config_file()`, `get_db_path()`, `get_db_url()` functions. Add `_active_user` module state and `set_active_user()`. Add `_validate_username()`.
2. **`bud/commands/db.py`**: Replace hardcoded `Path.home().joinpath(".bud")` with `get_config_dir()`.
3. **`bud/commands/db_commands.py`**: Replace `DB_PATH` references with `get_db_path()` calls.
4. **`bud/commands/sync.py`**: Replace `CONFIG_DIR`, `DB_PATH` imports with function calls. Convert `SYNC_META_FILE` from constant to function.
5. **`bud/credentials.py`**: Replace `CONFIG_DIR` import with `get_config_dir()` call. Convert `CREDENTIALS_FILE` from constant to function.
6. **`bud/database.py`**: Remove `DB_PATH`, `DB_URL`, `engine`, `AsyncSessionLocal`, `get_db()`, `create_tables()`. Keep only `Base` and `_make_engine`.
7. **Delete `bud/config.py`** (dead code).

**Files to modify:**
- `bud/commands/config_store.py`
- `bud/commands/db.py`
- `bud/commands/db_commands.py`
- `bud/commands/sync.py`
- `bud/credentials.py`
- `bud/database.py`
- `bud/config.py` (delete)

### Phase 2: CLI Integration

1. **`bud/cli.py`**: Add `--user` / `-u` option with `envvar="BUD_USER"` and `default="default"` to the `@click.group()`. Call `set_active_user(user)` in the group function body.

**Files to modify:**
- `bud/cli.py`

### Phase 3: User Directory Structure

1. **`bud/commands/config_store.py`**: Update `get_config_dir()` to return `~/.bud/users/<name>/` path.
2. **`bud/commands/config_store.py`**: Add `_maybe_migrate_legacy_data()` called from `set_active_user()` when user is `"default"`.

**Files to modify:**
- `bud/commands/config_store.py`

### Phase 4: Test Updates

1. Update all test fixtures that patch `DB_PATH`, `CONFIG_DIR`, `DB_URL` to patch the new functions instead.
2. Add tests for:
   - `set_active_user()` + path resolution
   - Username validation (valid names, path traversal, empty, too long)
   - Legacy migration (happy path, already migrated, partial state)
   - `--user` flag and `BUD_USER` env var precedence
   - Two users with isolated data

**Files to modify:**
- `tests/test_db_commands.py`
- `tests/test_sync.py`
- `tests/test_credentials.py`
- `tests/test_projects_command.py`
- New: `tests/test_multi_user.py`

## Dependencies & Risks

- **Risk**: Tests have ~30 patches against `DB_PATH` as a constant. Switching to function-based paths requires updating every patch target. Mitigated by doing Phase 1 and Phase 4 together.
- **Risk**: The `--user` flag must appear before the subcommand (`bud --user alice t list`). Agents constructing commands must know this. Mitigated by recommending `BUD_USER` env var for agents (no ordering constraint).
- **Assumption**: `shutil.copy2` is sufficient for atomic-enough migration on all target platforms (Linux servers for the agentic use case).

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-03-28-multi-user-support-requirements.md](docs/brainstorms/2026-03-28-multi-user-support-requirements.md) — Key decisions carried forward: subdirectories over separate home dirs, implicit user creation, "default" user fallback, per-user sync.

### Internal References

- Path definitions: `bud/commands/config_store.py:8-11`
- Duplicate paths: `bud/database.py:7-8`
- Dead code: `bud/config.py:6`
- Hardcoded mkdir: `bud/commands/db.py:31`
- CLI entry point: `bud/cli.py`
- Session factory: `bud/commands/db.py:get_session()`
- Sync paths: `bud/commands/sync.py:CONFIG_DIR,DB_PATH`
- Credentials: `bud/credentials.py:CONFIG_DIR`
- DB init: `bud/commands/db_commands.py:init`
