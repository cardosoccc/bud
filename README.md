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
bud p c --name "Personal"

# 3. Set it as the default (so you don't have to pass --project every time)
bud p s Personal

# 4. Set the active month
bud g s month 2025-03

# 5. Create accounts
bud a c --name "Bank" --type debit
bud a c --name "Credit Card" --type credit

# 6. Record transactions
bud t c -v -50 -d "Groceries" -a Bank
bud t c -v 3000 -d "Salary" -a Bank

# 7. View this month's transactions
bud tt

# 8. Create a budget and add a forecast
bud b c 2025-03
bud f c -v -200 -d "Groceries" -c food

# 9. Create a recurrent forecast (monthly rent)
bud f c -v -1500 -d "Rent" -c housing -r

# 10. Create an installment-based forecast (washer in 10x)
bud f c -v -300 -d "Washer" -c appliances -i 10

# 11. Create a transaction from a forecast (uses forecast #1 from bud ff)
bud t c -f 1 -a Bank

# 12. View the budget status
bud s
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
- `-v -50 -a Bank` → $50 expense from your bank account
- `-v 3000 -a Bank` → $3000 income into your bank account
- `-v -100 -a "Credit Card"` → $100 charged to your credit card

Transfers between accounts are handled by creating two separate transactions — one per account — with opposite signs.

Transactions have:
- A **value** (positive = in, negative = out)
- A **date** (defaults to today)
- An **account** they belong to
- An optional **category** and **tags**

### Budgets

A budget covers a calendar month (`YYYY-MM`). Each budget belongs to a project and contains a set of **forecasts** — your financial plan for that month.

When a budget is created, any applicable recurrences are automatically populated as forecasts in the new budget.

### Forecasts

Forecasts are the planned line items in a budget: expected income, expected expenses, recurring bills, etc. Use positive values for expected income and negative values for expected expenses.

At least one of `--description`, `--category`, or `--tags` must be provided. Forecasts match transactions using all provided criteria (AND logic).

### Recurrences

A recurrence is a dedicated record that tracks a repeating forecast across months. When you create a forecast with `--recurrent` or `--installments`, a recurrence record is created and linked to the forecast. There are two types:

**Open-ended recurrences** (`--recurrent`, optionally with `--recurrence-end`):
- The forecast repeats every month starting from the budget it was created in.
- If `--recurrence-end YYYY-MM` is provided, the forecast stops repeating after that month.
- When created, forecasts are immediately placed in all existing budgets within the range.
- When a new budget is created in the future, applicable open-ended recurrences are automatically populated.

**Installment-based recurrences** (`--installments N`):
- The total amount is divided into N monthly installments, each with the same value.
- All N installments are created immediately, auto-creating budgets as needed.
- Each forecast stores its installment number; the display shows a suffix like `(1/10)`.
- Use `--current-installment M` to start from installment M instead of 1 (e.g. when entering a purchase already partially paid). Only installments M through N are created.

**How recurrences are stored:**
- A `recurrences` table holds metadata: start month, optional end month, optional installment count, the base description, and template values (value, category, tags) used when creating forecasts in new budgets.
- Each forecast linked to a recurrence has a `recurrence_id` foreign key and an optional `installment` number.
- The installment suffix (e.g. `(3/10)`) is assembled dynamically at display time — it is not stored in the forecast's description field.

**Managing recurrences directly:**
- Use `bud r l` to list recurrences active in the current month, or `bud r l --all` to see every recurrence in the project.
- Use `bud r e <counter> --all -d "New Name" --propagate` to edit a recurrence and propagate changes to all linked forecasts.
- Use `bud r d <counter> --all --cascade -y` to delete a recurrence and all its linked forecasts.

**Editing recurrent forecasts:**
- A non-recurrent forecast can be turned into an open-ended recurrence via `--recurrent` (and optionally `--recurrence-end`) on the edit command. Turning into an installment-based recurrence via edit is not supported.
- Editing the description of a recurrent forecast also updates the recurrence's base description.
- A forecast that is already recurrent cannot be turned into a recurrence again.

### Categories

Categories are global labels (not project-specific) that link forecasts to actual transactions. If a forecast has category "food" and a transaction also has category "food", the status report will show how much you actually spent versus what you planned.

When you specify a category name that doesn't exist yet, `bud` will prompt to create it on the spot (works in transaction create/edit, forecast create/edit, and recurrence edit).

### Status Report

The status report (formerly "report") compares forecasts against actual transactions for a given budget month. For months in the future, `bud` calculates a **projected net balance** by summing forecast values from the current month forward through the target month.

Installment-based forecasts display their installment number and total in the report (e.g. `Washer (5/10)`).

---

## All Commands

### Aliases and Shortcuts

`bud` uses single-letter aliases for fast terminal usage. Every alias is visible in `--help` output.

**Command group aliases:**

| Full name | Alias |
|-----------|-------|
| `transaction` | `t` |
| `budget` | `b` |
| `category` | `c` |
| `forecast` | `f` |
| `project` | `p` |
| `recurrence` | `r` |
| `account` | `a` |
| `status` | `s` |
| `config` | `g` |

**Subcommand aliases** — within each group, CRUD subcommands have single-letter aliases:

| Full name | Alias |
|-----------|-------|
| `create` | `c` |
| `edit` | `e` |
| `delete` | `d` |
| `list` | `l` |
| `show` | `s` |

Additionally, `project set-default` has alias `s` and `config set` has alias `s`.

**List shortcuts** — double-letter commands that directly list a resource:

| Command | Equivalent |
|---------|------------|
| `bud tt [MONTH]` | `bud t l` |
| `bud aa` | `bud a l` |
| `bud bb` | `bud b l` |
| `bud cc` | `bud c l` |
| `bud ff [BUDGET]` | `bud f l` |
| `bud pp` | `bud p l` |
| `bud rr [MONTH]` | `bud r l` |
| `bud gg` | `bud g l` |

**Option aliases** — most options have single-letter shortcuts (`-v` for `--value`, `-d` for `--description`, `-p` for `--project`, `-c` for `--category`, `-t` for `--tags` or `--date`, `-a` for `--account`, `-s` for `--show-id`, `-f` for `--forecast`, etc.). Run any command with `--help` to see available shortcuts.

### Global Options

Every command that operates on a project accepts `--project`/`-p` with a UUID or name. If you have a default project set, this option can be omitted.

Every command that operates on accounts, categories, or budgets accepts either the UUID or the human-readable name/month as the identifier.

---

### `project` (alias `p`) — Manage Projects

```
bud p l                           # list all projects
bud p c -n <name>                 # create a new project
bud p e <counter> -n <new-name>   # rename a project (by list #)
bud p d <id-or-name>              # delete a project (cascades to budgets, transactions, recurrences)
bud p s <id-or-name>              # set as default project
```

---

### `account` (alias `a`) — Manage Accounts

```
bud a l                                                # list accounts
bud a c -n <name> -t <credit|debit> [-i <balance>]     # create account
bud a e <id-or-name> [-n <name>] [-t <type>]           # edit account
bud a d <id-or-name>                                   # delete account (blocked if transactions exist)
```

---

### `transaction` (alias `t`) — Manage Transactions

```
bud t l [MONTH]                   # list transactions (MONTH = YYYY-MM, defaults to active month)
bud t s <transaction-id>          # show full transaction details
bud t c -v <amount> -d <desc> -a <account> [-t <date>] [-c <category>] [--tags <tag1,tag2>]
bud t c -f <forecast#> -a <account> [-t <date>] [-v <amount>] [-d <desc>] [-c <category>] [--tags <tag1,tag2>]
bud t e <counter> [MONTH] [-v <amount>] [-d <desc>] [-t <date>] [-c <category>] [--tags <tag1,tag2>]
bud t d <id-or-counter> [MONTH] [-y]
```

The `MONTH` argument is positional (e.g. `bud t l 2025-03`). When using a list counter for edit/delete, the month scopes which list the counter refers to.

Key option for `create`:
- `-f` / `--forecast` — create a transaction from an existing forecast. The forecast is identified by its positional counter (`#` column from `bud ff`) in the budget of the month corresponding to the transaction date. Value, description, category, and tags are pre-filled from the forecast but can be overridden with explicit options. When using `-f`, only `--account` is required.

---

### `budget` (alias `b`) — Manage Budgets

```
bud b l                           # list all budgets
bud b c <YYYY-MM>                 # create a budget (auto-populates recurrences)
bud b e <counter> [-m <YYYY-MM>]  # edit a budget's month
bud b d <id-or-month-or-counter> [-y]  # delete a budget (cascades to forecasts)
```

---

### `forecast` (alias `f`) — Manage Forecasts

```
bud f l [BUDGET]                  # list forecasts (BUDGET = UUID or YYYY-MM, defaults to current month)
bud f c [BUDGET] -v <amount> [-d <desc>] [-c <category>] [-t <tags>] [-r] [-e <end>] [-i <N>]
bud f e <counter> [BUDGET] [-d <desc>] [-v <amount>] [-c <category>] [-t <tags>] [-r] [-e <end>]
bud f d <id-or-counter> [BUDGET] [-y]
```

The `BUDGET` argument is positional. If omitted, defaults to the current month's budget. On create, the budget is auto-created if it doesn't exist.

Key options for `create`:
- `-r` / `--recurrent` — marks as open-ended recurrence
- `-e` / `--recurrence-end YYYY-MM` — last month for the recurrence (implies `-r`)
- `-i` / `--installments N` — creates N monthly installments
- `--current-installment M` — start from installment M (requires `-i`)

---

### `recurrence` (alias `r`) — Manage Recurrences

```
bud r l [MONTH]                   # list recurrences active in MONTH (defaults to current month)
bud r l -a                        # list ALL recurrences in the project
bud r e <counter> [-a] [-d <desc>] [-v <amount>] [-c <category>] [-t <tags>] [--propagate]
bud r d <id-or-counter> [-a] [-c] [-y]
```

Key options:
- `-a` / `--all` — in list: show all recurrences regardless of month. In edit/delete: resolve counter from the full list.
- `--propagate` — on edit: also update description/value/category/tags on all linked forecasts.
- `-c` / `--cascade` — on delete: delete all linked forecasts (default: orphan them by setting `recurrence_id` to NULL).

---

### `status` (alias `s`) — Budget Status Report

```
bud s [BUDGET] [-p <project>]
```

Generate a status report for a budget. `BUDGET` can be a UUID or a `YYYY-MM` month string. If omitted, defaults to the current month's budget.

The report shows:
- **Account balances** — net change for each account in the period, plus calculated and current balances, with an expected balance row that includes the forecast remaining
- **Forecast vs. Actuals** — for each forecast line item, shows the planned value, actual spend (from transactions with a matching category), and the difference. Installment-based forecasts display their installment suffix (e.g. `Washer (5/10)`).
- **Projected net balance** — for future months: the cumulative sum of forecast values from the current month through the target month, shown as Previous + Total = Accumulated rows

---

### `category` (alias `c`) — Manage Categories

Categories are global (shared across all projects).

```
bud c l                           # list all categories
bud c c -n <name>                 # create a category
bud c e <id-or-name> -n <new-name>  # rename a category
bud c d <id-or-name>              # delete (sets category_id to NULL on referencing records)
```

---

### `db` — Database Management

```
bud db init                       # create ~/.bud/ and initialize tables
bud db migrate                    # run pending migrations
bud db destroy                    # delete the database file (irreversible)
bud db reset                      # destroy + re-initialize
bud db push [--force]             # upload database to cloud storage
bud db pull [--force]             # download database from cloud storage
```

---

### `config` (alias `g`) — Configuration

```
bud g s <key> <value>             # set a config value
bud g l                           # list current config
bud g aws                         # store AWS credentials
bud g gcp                         # store GCP service account path
```

Common config keys:
```bash
bud g s month 2025-03                   # set the active month
bud g s bucket s3://my-bucket/bud       # set cloud sync bucket
bud g s bucket gs://my-bucket/bud
```

---

## Cloud Sync

`bud` can sync your database to AWS S3 or Google Cloud Storage so you can use it across multiple machines.

### Setup

**AWS S3:**
```bash
bud g aws                                # store credentials
bud g s bucket s3://my-bucket/bud
```

**Google Cloud Storage:**
```bash
bud g gcp                                # store path to service account JSON key
bud g s bucket gs://my-bucket/bud
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
│   │   ├── recurrences.py
│   │   ├── categories.py
│   │   ├── reports.py            # status report display
│   │   ├── db.py                 # Session factory + run_async() helper
│   │   ├── db_commands.py        # db init / destroy / reset / migrate
│   │   ├── sync.py               # db push / pull
│   │   ├── credentials.py        # config aws / config gcp
│   │   ├── config_store.py       # Config file read/write (~/.bud/config.json)
│   │   └── utils.py              # ID resolution (UUID or name → UUID)
│   │
│   ├── models/                   # SQLAlchemy ORM models
│   │   ├── project.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   ├── forecast.py
│   │   ├── recurrence.py
│   │   └── category.py
│   │
│   ├── schemas/                  # Pydantic input/output schemas
│   │   ├── project.py
│   │   ├── account.py
│   │   ├── transaction.py
│   │   ├── budget.py
│   │   ├── forecast.py
│   │   ├── recurrence.py
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
│       ├── recurrences.py
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

This means you can write `bud t c -a "Bank"` instead of copying UUIDs from list output.

### Counter-Based Selection

Most edit and delete commands accept a **list counter** (the `#` column from list output) instead of a UUID. The counter is 1-indexed and refers to the item's position in the most recent list. For transactions and forecasts, the counter is scoped to a month/budget. For recurrences, use `--all` to resolve the counter from the full project list.

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
| `config.json` | User settings (`month`, `default_project_id`, `bucket`) |
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

recurrences
  id (UUID PK), start (YYYY-MM), end (YYYY-MM, nullable),
  installments (int, nullable), base_description (nullable),
  value, tags (JSON),
  category_id (FK → categories SET NULL),
  project_id (FK → projects CASCADE), created_at

forecasts
  id (UUID PK), description, value, tags (JSON),
  installment (int, nullable),
  budget_id (FK → budgets CASCADE),
  category_id (FK → categories SET NULL),
  recurrence_id (FK → recurrences SET NULL),
  created_at

categories
  id (UUID PK), name (unique), created_at
```

**Cascade rules:**
- Deleting a project cascades to its budgets, transactions, and recurrences
- Deleting a budget cascades to its forecasts
- Deleting a category sets `category_id` to `NULL` on transactions and forecasts (does not delete them)
- Deleting a recurrence sets `recurrence_id` to `NULL` on its forecasts (does not delete them) — unless `--cascade` is used, which deletes them
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
