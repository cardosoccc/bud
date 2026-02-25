# bud

A personal budget management CLI built for humans and agents alike. `bud` helps you track expenses, plan monthly budgets, and forecast your financial future — all from the terminal.

It is designed to fit naturally into **agentic workflows**: a remote AI agent (e.g. connected to WhatsApp or Telegram) can use `bud` as a tool to query and update your finances on your behalf, while you keep full control of your data locally.

---

## The Problem It Solves

Most budgeting apps live in the cloud and require trusting a third party with your financial data. `bud` takes the opposite approach:

- Your data lives in a local SQLite file (`~/.bud/bud.db`) — you own it entirely
- You interact via CLI, which makes it scriptable and automation-friendly
- Cloud sync (AWS S3 or GCP) is opt-in and on your terms
- Transactions are simple, account-relative records — no hidden complexity
- It works as both a personal tool and as a backend for an AI agent that manages finances on your behalf through any messaging channel

---

## Installation

**Requirements:** Python 3.13+, [uv](https://github.com/astral-sh/uv)

```bash
git clone <repo>
cd bud
make setup          # creates venv and installs dependencies
```

Initialize the database before first use:

```bash
bud db init
```

---

## Quick Start

```bash
# 1. Initialize the database
bud db init

# 2. Create a project
bud project create --name "Personal"

# 3. Set it as the default (so you don't have to pass --project every time)
bud project set-default <project-id>

# 4. Set the active month
bud set-month 2025-02

# 5. Create accounts
bud account create --name "Bank" --type debit
bud account create --name "Credit Card" --type credit

# 6. Record transactions
bud transaction create --value -50 --description "Groceries" --account Bank
bud transaction create --value 3000 --description "Salary" --account Bank

# 7. View this month's transactions
bud txns

# 8. Create a budget and add a forecast
bud budget create --month 2025-02
bud forecast create --budget 2025-02 --description "Groceries" --value -200 --category food

# 9. Generate a report
bud report show 2025-02
```

---

## Core Concepts

### Projects

A project is the top-level container for your financial data. You can have multiple projects (e.g. personal, business, a shared household budget). Every operation is scoped to a project. One project can be set as the default so you never need to pass `--project` explicitly.

### Accounts

Accounts represent where money lives. There are two types:

| Type | Description | Example |
|------|-------------|---------|
| `debit` | Assets you own | Bank account, cash, wallet |
| `credit` | Liabilities | Credit card, loan |

Accounts can be shared across multiple projects.

### Transactions

A transaction records a money movement relative to a single account. The sign of the value determines the direction:

- **Positive value**: money coming into the account (income, deposits, payments received)
- **Negative value**: money leaving the account (expenses, withdrawals, payments made)

For example:
- `--value -50 --account Bank` → $50 expense from your bank account
- `--value 3000 --account Bank` → $3000 income into your bank account
- `--value -100 --account "Credit Card"` → $100 charged to your credit card

Transfers between accounts are handled by creating two separate transactions — one per account — with opposite signs.

Transactions have:
- A **value** (positive = in, negative = out)
- A **date** (defaults to today)
- An **account** they belong to
- An optional **category** and **tags**

### Budgets

A budget covers a calendar month (`YYYY-MM`). Each budget belongs to a project and contains a set of **forecasts** — your financial plan for that month.

### Forecasts

Forecasts are the planned line items in a budget: expected income, expected expenses, recurring bills, etc. They can be:
- **One-time**: applies only to the budget they belong to
- **Recurrent**: automatically applies across multiple months, with optional start/end boundaries

Use positive values for expected income and negative values for expected expenses.

### Categories

Categories are global labels (not project-specific) that link forecasts to actual transactions. If a forecast has category "food" and a transaction also has category "food", the report will show how much you actually spent versus what you planned.

### Reports

A report compares forecasts against actual transactions for a given budget month. For months in the future, `bud` calculates a **projected net balance** by summing forecast values from the current month forward through the target month.

---

## All Commands

### Global Options and Shorthands

Every command that operates on a project accepts `--project <uuid-or-name>`. If you have a default project set, this option can be omitted.

Every command that operates on accounts, categories, or budgets accepts either the UUID or the human-readable name/month as the identifier.

**Command group aliases** — shorter versions of the group names:

| Full name | Alias |
|-----------|-------|
| `transaction` | `txn` |
| `budget` | `bud` |
| `category` | `cat` |
| `forecast` | `for` |
| `project` | `prj` |
| `account` | `acc` |
| `report` | `rep` |
| `set-month` | `mon` |
| `config` | `cfg` |

**List shortcuts** — single commands that directly list a resource:

| Command | Equivalent |
|---------|------------|
| `bud txns [--month] [--project]` | `bud transaction list` |
| `bud buds [--project]` | `bud budget list` |
| `bud cats` | `bud category list` |
| `bud fors --budget <id> [--project]` | `bud forecast list` |
| `bud prjs` | `bud project list` |
| `bud accs [--project]` | `bud account list` |

---

### `project` — Manage Projects

```
bud project list
```
List all projects. Shows ID, name, and which one is the default.

```
bud project create --name <name>
```
Create a new project with the given name.

```
bud project edit <project-id> --name <new-name>
```
Rename a project. The `<project-id>` can be the UUID or the current name.

```
bud project delete <project-id>
```
Delete a project. Prompts for confirmation. This cascades to all budgets and transactions belonging to the project.

```
bud project set-default <project-id>
```
Mark a project as the default. The default project is used automatically when `--project` is not provided.

---

### `account` — Manage Accounts

```
bud account list [--project <id>]
```
List all accounts for the given project.

```
bud account create --name <name> --type <type> [--project <id>] [--initial-balance <float>]
```
Create a new account. Type must be `credit` or `debit`. The `--initial-balance` option sets a starting balance (default: 0).

```
bud account edit <account-id> [--name <name>] [--type <type>] [--project <id>]
```
Edit an account's name or type.

```
bud account delete <account-id> [--project <id>]
```
Delete an account. Fails if transactions reference it (you must delete or reassign transactions first).

---

### `transaction` — Manage Transactions

```
bud transaction list [--month <YYYY-MM>] [--project <id>]
```
List all transactions for the given month. Defaults to the active month if set. Shows: truncated ID, date, description, value, account.

```
bud transaction show <transaction-id>
```
Show full details of a transaction: ID, date, description, value, account, category, and tags.

```
bud transaction create \
  --value <float> \
  --description <text> \
  --account <account> \
  [--date <YYYY-MM-DD>] \
  [--project <id>] \
  [--category <name-or-id>] \
  [--tags <tag1,tag2>]
```
Create a transaction. `--account` is required. Use a positive `--value` for money coming in (income, deposits) and a negative `--value` for money going out (expenses, payments). The date defaults to today.

If a `--category` name is given that doesn't exist yet, `bud` will ask if you want to create it on the spot.

```
bud transaction edit <transaction-id> \
  [--value <float>] \
  [--description <text>] \
  [--date <YYYY-MM-DD>] \
  [--category <name-or-id>] \
  [--tags <tag1,tag2>]
```
Edit a transaction. Only the fields you provide are updated.

```
bud transaction delete <transaction-id>
```
Delete a transaction. Prompts for confirmation.

---

### `budget` — Manage Budgets

```
bud budget list [--project <id>]
```
List all budgets for the project, ordered by month.

```
bud budget create --month <YYYY-MM> [--project <id>]
```
Create a monthly budget. The start and end dates are computed automatically from the month string using the correct number of days for that month.

```
bud budget edit <budget-id> [--month <YYYY-MM>] [--project <id>]
```
Change the month of a budget. The start/end dates are recalculated. `<budget-id>` can be the UUID or the `YYYY-MM` string.

```
bud budget delete <budget-id>
```
Delete a budget. Prompts for confirmation. Cascades to all forecasts.

---

### `forecast` — Manage Forecasts

```
bud forecast list --budget <id> [--project <id>]
```
List all forecasts for a given budget.

```
bud forecast create \
  --budget <id> \
  --description <text> \
  --value <float> \
  [--category <name-or-id>] \
  [--tags <tag1,tag2>] \
  [--min <float>] \
  [--max <float>] \
  [--recurrent] \
  [--project <id>]
```
Create a forecast line item. Options:
- `--value`: the expected amount (positive = income, negative = expense)
- `--min` / `--max`: optional range for variable expenses
- `--recurrent`: marks this forecast as recurring across months
- `--category`: links this forecast to a category for actual-vs-forecast comparison

```
bud forecast edit <forecast-id> \
  [--description <text>] \
  [--value <float>] \
  [--category <name-or-id>] \
  [--tags <tag1,tag2>] \
  [--min <float>] \
  [--max <float>]
```
Edit a forecast. Only provided fields are updated.

```
bud forecast delete <forecast-id>
```
Delete a forecast. Prompts for confirmation.

---

### `category` — Manage Categories

Categories are global (shared across all projects).

```
bud category list
```
List all categories.

```
bud category create --name <name>
```
Create a category.

```
bud category edit <category-id> --name <new-name>
```
Rename a category.

```
bud category delete <category-id>
```
Delete a category. Transactions and forecasts that reference it will have their category set to `NULL` (not deleted).

---

### `report` — Budget Reports

```
bud report show [<budget-id>] [--project <id>]
```
Generate a report for a budget. `<budget-id>` can be a UUID or a `YYYY-MM` month string. If omitted, defaults to the current active month.

The report shows:
- **Account balances** — net change for each account in the period (sum of transaction values)
- **Totals** — total earnings (sum of positive transaction values), total expenses (sum of absolute negative values), net balance
- **Forecast vs. Actuals** — for each forecast line item, shows the planned value, actual spend (from transactions with a matching category), and the difference
- **Projected net balance** — for future months only: the cumulative sum of forecast values from the current month through the target month, accounting for recurrence bounds

---

### `db` — Database Management

```
bud db init
```
Create the `~/.bud/` directory and initialize all database tables. Safe to run multiple times (no-op if already initialized).

```
bud db destroy
```
Delete the database file (`~/.bud/bud.db`). Prompts for confirmation. This is irreversible.

```
bud db reset
```
Destroy and re-initialize the database. Prompts for confirmation. All data is lost.

```
bud db push [--force]
```
Upload the local database to the configured cloud storage bucket. `bud` tracks a version number in `~/.bud/sync_meta.json`. If the remote has a newer version, the push is blocked unless `--force` is passed.

```
bud db pull [--force]
```
Download the database from cloud storage. If the local version is newer, the pull is blocked unless `--force` is passed. A backup of the local database is created at `~/.bud/bud.db.bak` before overwriting.

---

### Configuration Commands

```
bud set-month <YYYY-MM>
bud mon <YYYY-MM>
```
Set the active month. This is used as the default for commands that require a month (e.g. `transaction list`, `report show`) so you don't have to type it every time.

```
bud set-config <key> <value>
```
Set an arbitrary configuration value. Used primarily for cloud storage:
```bash
bud set-config bucket s3://my-bucket/bud
bud set-config bucket gs://my-bucket/bud
```

```
bud config --show
bud cfg --show
```
Print the current configuration.

```
bud configure-aws
```
Interactively store AWS credentials (`access_key_id` and `secret_access_key`) in `~/.bud/credentials.json` (mode 0600).

```
bud configure-gcp
```
Store the path to a GCP service account key file in `~/.bud/credentials.json`.

---

## Cloud Sync

`bud` can sync your database to AWS S3 or Google Cloud Storage so you can use it across multiple machines.

### Setup

**AWS S3:**
```bash
bud configure-aws          # store credentials
bud set-config bucket s3://my-bucket/bud
```

**Google Cloud Storage:**
```bash
bud configure-gcp          # store path to service account JSON key
bud set-config bucket gs://my-bucket/bud
```

### Sync Workflow

```bash
# On machine A: make changes, then push
bud db push

# On machine B: get latest
bud db pull
```

Version conflicts are detected automatically. If the remote is ahead of your local copy, `pull` will refuse to overwrite until you `push` first (or use `--force`). This prevents accidental data loss when using `bud` on multiple devices.

---

## Architecture

### Directory Layout

```
bud/
├── bud/
│   ├── cli.py                    # Entry point: Click group + all command wiring
│   ├── database.py               # SQLAlchemy async engine setup
│   ├── config.py                 # Pydantic settings
│   ├── credentials.py            # Cloud credential storage
│   │
│   ├── commands/                 # CLI layer: input parsing, output formatting
│   │   ├── projects.py
│   │   ├── accounts.py
│   │   ├── transactions.py
│   │   ├── budgets.py
│   │   ├── forecasts.py
│   │   ├── categories.py
│   │   ├── reports.py
│   │   ├── db.py                 # Session factory + run_async() helper
│   │   ├── db_commands.py        # db init / destroy / reset
│   │   ├── sync.py               # db push / pull
│   │   ├── credentials.py        # configure-aws / configure-gcp
│   │   ├── config_store.py       # Config file read/write (~/.bud/config.json)
│   │   └── utils.py              # ID resolution (UUID or name → UUID)
│   │
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── project.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   ├── forecast.py
│   │   └── category.py
│   │
│   ├── schemas/                  # Pydantic input/output schemas
│   │   ├── project.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   ├── forecast.py
│   │   ├── category.py
│   │   └── report.py
│   │
│   └── services/                 # Business logic (no CLI concerns)
│       ├── projects.py
│       ├── accounts.py
│       ├── transactions.py
│       ├── budgets.py
│       ├── forecasts.py
│       ├── categories.py
│       ├── reports.py
│       └── storage.py            # AWS S3 / GCP storage providers
│
├── tests/
├── pyproject.toml
└── Makefile
```

### Layered Design

```
┌─────────────────────────────────────────┐
│            CLI (commands/)              │  ← Click decorators, tabulate output
├─────────────────────────────────────────┤
│           Services (services/)          │  ← Business logic, validation
├─────────────────────────────────────────┤
│            Models (models/)             │  ← SQLAlchemy ORM, schema definitions
├─────────────────────────────────────────┤
│         SQLite via aiosqlite            │  ← ~/.bud/bud.db
└─────────────────────────────────────────┘
```

Each layer has a single responsibility:
- **Commands** handle user input and output only — they parse CLI arguments, resolve human-readable names to UUIDs, call service functions, and format results with `tabulate`
- **Services** implement business logic — computing month boundaries, generating reports — with no knowledge of CLI or output formatting
- **Models** define the database schema via SQLAlchemy ORM
- **Schemas** (Pydantic) validate data at the CLI→service boundary

### Async Database Access

All database operations are `async` using SQLAlchemy's async interface with `aiosqlite` as the SQLite driver. The CLI is synchronous (Click does not support async natively), so each command wraps its async work in a `run_async()` helper:

```python
def run_async(coro):
    return asyncio.run(coro)
```

A context manager provides a scoped database session:

```python
async with get_session() as db:
    result = await service.do_something(db, ...)
```

SQLite foreign key enforcement is enabled at the connection level via `PRAGMA foreign_keys = ON`.

### Transaction Model

Each transaction belongs to a single account and carries a signed value:

- **Positive value**: money flowing into the account (income, deposits)
- **Negative value**: money flowing out of the account (expenses, payments)

This makes balance calculations straightforward: the balance for any account over a period is the sum of its transaction values. There are no hidden counterpart records or special "external" accounts.

Transfers between two accounts (e.g. paying off a credit card with your bank account) are recorded as two separate transactions — a negative entry on the source account and a positive entry on the destination account. This keeps each transaction simple and self-contained.

### ID Resolution

Every command that accepts a resource identifier (project, account, budget, category) will accept either:
- A full UUID string
- A human-readable name (or `YYYY-MM` for budgets)

Resolution logic in `commands/utils.py`:
1. If the input is a valid UUID format → use it directly
2. Otherwise → query the database by name, scoped to the relevant project where applicable
3. Return the UUID or `None` if not found (CLI will print an error)

This means you can write `bud transaction create --account "Bank"` instead of copying UUIDs from list output.

### Cloud Storage Versioning

The sync system tracks a monotonically increasing version number in `~/.bud/sync_meta.json`:

```json
{"version": 5, "pushed_at": 1700000000.0}
```

On `push`: local version is compared to the remote version. If remote is newer, push is blocked (data on another machine would be overwritten). On success, version is incremented.

On `pull`: remote version is compared to local. If local is newer, pull is blocked (local changes would be lost). A `.db.bak` file is created before overwriting.

The `--force` flag bypasses the version check in either direction.

### Configuration Files

`bud` stores all persistent state in `~/.bud/`:

| File | Contents |
|------|----------|
| `bud.db` | SQLite database |
| `config.json` | User settings (`active_month`, `default_project_id`, `bucket`) |
| `credentials.json` | Cloud credentials (mode 0600) |
| `sync_meta.json` | Sync version tracking |
| `bud.db.bak` | Automatic backup created before each pull |

---

## Database Schema

```
projects
  id (UUID PK), name (unique), is_default, created_at

project_accounts                  ← many-to-many junction
  project_id (FK → projects), account_id (FK → accounts)

accounts
  id (UUID PK), name, type (credit|debit), initial_balance, current_balance

transactions
  id (UUID PK), value, description, date, tags (JSON array),
  account_id (FK → accounts RESTRICT),
  category_id (FK → categories SET NULL),
  project_id (FK → projects CASCADE),
  created_at

budgets
  id (UUID PK), name (YYYY-MM), start_date, end_date,
  project_id (FK → projects CASCADE), created_at
  UNIQUE (name, project_id)

forecasts
  id (UUID PK), description, value, min_value, max_value, tags (JSON),
  is_recurrent, recurrent_start, recurrent_end,
  budget_id (FK → budgets CASCADE),
  category_id (FK → categories SET NULL), created_at

categories
  id (UUID PK), name (unique), created_at
```

**Cascade rules:**
- Deleting a project cascades to its budgets and transactions
- Deleting a budget cascades to its forecasts
- Deleting a category sets `category_id` to `NULL` on transactions and forecasts (does not delete them)
- Deleting an account is blocked (`RESTRICT`) if any transaction references it

---

## Development

```bash
make setup     # Create venv and install all dependencies (via uv)
make test      # Run test suite with pytest
make lint      # Run ruff linter and format check
make clean     # Remove venv, caches, build artifacts
make build     # Build Docker image
make up        # Start Docker Compose services
make down      # Stop Docker Compose services
```

Tests live in `tests/` and use `pytest` with `pytest-asyncio` for async test support.

---

## Technology Stack

| Component | Library |
|-----------|---------|
| CLI framework | [Click](https://click.palletsprojects.com/) 8.x |
| ORM | [SQLAlchemy](https://www.sqlalchemy.org/) 2.0 async |
| SQLite driver | [aiosqlite](https://github.com/omnilib/aiosqlite) |
| Data validation | [Pydantic](https://docs.pydantic.dev/) / pydantic-settings |
| Table formatting | [tabulate](https://github.com/astanin/python-tabulate) |
| AWS S3 sync | [boto3](https://boto3.amazonaws.com/v1/documentation/api/latest/index.html) |
| GCP sync | [google-cloud-storage](https://cloud.google.com/python/docs/reference/storage/latest) |
| Password hashing | [bcrypt](https://pypi.org/project/bcrypt/) |
| Package manager | [uv](https://github.com/astral-sh/uv) |
| Python version | 3.13+ |
