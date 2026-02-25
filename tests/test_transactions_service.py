"""Unit tests for the transactions service layer."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bud.models.account import AccountType
from bud.schemas.account import AccountCreate
from bud.schemas.category import CategoryCreate
from bud.schemas.project import ProjectCreate
from bud.schemas.transaction import TransactionCreate, TransactionUpdate
from bud.services import accounts as account_service
from bud.services import categories as category_service
from bud.services import projects as project_service
from bud.services import transactions as transaction_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project(db: AsyncSession, name: str = "TestProject") -> object:
    return await project_service.create_project(db, ProjectCreate(name=name))


async def _create_account(
    db: AsyncSession,
    project_id: uuid.UUID,
    name: str = "Checking",
) -> object:
    return await account_service.create_account(
        db,
        AccountCreate(
            name=name,
            type=AccountType.debit,
            project_id=project_id,
            initial_balance=0.0,
        ),
    )


async def _create_category(db: AsyncSession, name: str = "Food") -> object:
    return await category_service.create_category(db, CategoryCreate(name=name))


async def _create_transaction(
    db: AsyncSession,
    project_id: uuid.UUID,
    account_id: uuid.UUID,
    value: Decimal = Decimal("-50.00"),
    description: str = "Groceries",
    txn_date: date = date(2025, 1, 15),
    category_id: uuid.UUID = None,
    tags: list = None,
) -> object:
    return await transaction_service.create_transaction(
        db,
        TransactionCreate(
            value=value,
            description=description,
            date=txn_date,
            account_id=account_id,
            project_id=project_id,
            category_id=category_id,
            tags=tags or [],
        ),
    )


# ---------------------------------------------------------------------------
# list_transactions
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_transactions_empty(db_session: AsyncSession):
    project = await _create_project(db_session)
    result = await transaction_service.list_transactions(db_session, project.id)
    assert result == []


@pytest.mark.asyncio
async def test_list_transactions_returns_all_for_project(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(db_session, project.id, account.id, description="Tx1")
    await _create_transaction(db_session, project.id, account.id, description="Tx2")

    result = await transaction_service.list_transactions(db_session, project.id)

    assert len(result) == 2
    assert {t.description for t in result} == {"Tx1", "Tx2"}


@pytest.mark.asyncio
async def test_list_transactions_only_returns_for_project(db_session: AsyncSession):
    proj1 = await _create_project(db_session, "P1")
    proj2 = await _create_project(db_session, "P2")
    acc1 = await _create_account(db_session, proj1.id, "Acc1")
    acc2 = await _create_account(db_session, proj2.id, "Acc2")
    await _create_transaction(db_session, proj1.id, acc1.id, description="P1 Tx")
    await _create_transaction(db_session, proj2.id, acc2.id, description="P2 Tx")

    result = await transaction_service.list_transactions(db_session, proj1.id)

    assert len(result) == 1
    assert result[0].description == "P1 Tx"


@pytest.mark.asyncio
async def test_list_transactions_filters_by_month(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(
        db_session, project.id, account.id,
        description="Jan Tx", txn_date=date(2025, 1, 15),
    )
    await _create_transaction(
        db_session, project.id, account.id,
        description="Feb Tx", txn_date=date(2025, 2, 10),
    )

    result = await transaction_service.list_transactions(db_session, project.id, month="2025-01")

    assert len(result) == 1
    assert result[0].description == "Jan Tx"


@pytest.mark.asyncio
async def test_list_transactions_month_includes_first_day(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(
        db_session, project.id, account.id,
        description="First Day", txn_date=date(2025, 3, 1),
    )

    result = await transaction_service.list_transactions(db_session, project.id, month="2025-03")

    assert len(result) == 1
    assert result[0].description == "First Day"


@pytest.mark.asyncio
async def test_list_transactions_month_excludes_next_month_first_day(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(
        db_session, project.id, account.id,
        description="In Month", txn_date=date(2025, 3, 31),
    )
    await _create_transaction(
        db_session, project.id, account.id,
        description="Next Month", txn_date=date(2025, 4, 1),
    )

    result = await transaction_service.list_transactions(db_session, project.id, month="2025-03")

    assert len(result) == 1
    assert result[0].description == "In Month"


@pytest.mark.asyncio
async def test_list_transactions_december_year_boundary(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(
        db_session, project.id, account.id,
        description="Dec Tx", txn_date=date(2025, 12, 15),
    )
    await _create_transaction(
        db_session, project.id, account.id,
        description="Jan Tx", txn_date=date(2026, 1, 1),
    )

    result = await transaction_service.list_transactions(db_session, project.id, month="2025-12")

    assert len(result) == 1
    assert result[0].description == "Dec Tx"


@pytest.mark.asyncio
async def test_list_transactions_no_month_returns_all(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(db_session, project.id, account.id, description="Tx1", txn_date=date(2025, 1, 1))
    await _create_transaction(db_session, project.id, account.id, description="Tx2", txn_date=date(2025, 6, 15))
    await _create_transaction(db_session, project.id, account.id, description="Tx3", txn_date=date(2025, 12, 31))

    result = await transaction_service.list_transactions(db_session, project.id)

    assert len(result) == 3


@pytest.mark.asyncio
async def test_list_transactions_ordered_by_date_desc(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    await _create_transaction(db_session, project.id, account.id, description="Early", txn_date=date(2025, 1, 5))
    await _create_transaction(db_session, project.id, account.id, description="Late", txn_date=date(2025, 1, 20))
    await _create_transaction(db_session, project.id, account.id, description="Middle", txn_date=date(2025, 1, 12))

    result = await transaction_service.list_transactions(db_session, project.id, month="2025-01")

    assert result[0].description == "Late"
    assert result[1].description == "Middle"
    assert result[2].description == "Early"


@pytest.mark.asyncio
async def test_list_transactions_eager_loads_account(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id, "MyBank")
    await _create_transaction(db_session, project.id, account.id)

    result = await transaction_service.list_transactions(db_session, project.id)

    assert result[0].account.name == "MyBank"


# ---------------------------------------------------------------------------
# get_transaction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_transaction_found(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    created = await _create_transaction(db_session, project.id, account.id, description="Lookup")

    result = await transaction_service.get_transaction(db_session, created.id)

    assert result is not None
    assert result.id == created.id
    assert result.description == "Lookup"


@pytest.mark.asyncio
async def test_get_transaction_not_found(db_session: AsyncSession):
    result = await transaction_service.get_transaction(db_session, uuid.uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_get_transaction_eager_loads_account(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id, "EagerBank")
    created = await _create_transaction(db_session, project.id, account.id)

    result = await transaction_service.get_transaction(db_session, created.id)

    assert result.account.name == "EagerBank"


# ---------------------------------------------------------------------------
# create_transaction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_transaction_returns_uuid(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)

    assert t.id is not None
    assert isinstance(t.id, uuid.UUID)


@pytest.mark.asyncio
async def test_create_transaction_stores_value(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, value=Decimal("-99.99"))

    assert t.value == Decimal("-99.99")


@pytest.mark.asyncio
async def test_create_transaction_stores_description(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, description="My Description")

    assert t.description == "My Description"


@pytest.mark.asyncio
async def test_create_transaction_stores_date(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, txn_date=date(2025, 3, 22))

    assert t.date == date(2025, 3, 22)


@pytest.mark.asyncio
async def test_create_transaction_default_tags_empty(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)

    assert t.tags == []


@pytest.mark.asyncio
async def test_create_transaction_stores_tags(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, tags=["food", "weekly"])

    assert t.tags == ["food", "weekly"]


@pytest.mark.asyncio
async def test_create_transaction_without_category(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)

    assert t.category_id is None


@pytest.mark.asyncio
async def test_create_transaction_with_category(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    category = await _create_category(db_session, "Groceries")
    t = await _create_transaction(db_session, project.id, account.id, category_id=category.id)

    assert t.category_id == category.id


@pytest.mark.asyncio
async def test_create_transaction_positive_value(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, value=Decimal("1000.00"))

    assert t.value == Decimal("1000.00")


@pytest.mark.asyncio
async def test_create_transaction_persisted(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    created = await _create_transaction(db_session, project.id, account.id, description="Persisted")

    fetched = await transaction_service.get_transaction(db_session, created.id)

    assert fetched is not None
    assert fetched.description == "Persisted"


@pytest.mark.asyncio
async def test_create_transaction_unique_ids(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t1 = await _create_transaction(db_session, project.id, account.id, description="Tx1")
    t2 = await _create_transaction(db_session, project.id, account.id, description="Tx2")

    assert t1.id != t2.id


# ---------------------------------------------------------------------------
# update_transaction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_transaction_value(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, value=Decimal("-50.00"))

    updated = await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(value=Decimal("-75.00"))
    )

    assert updated is not None
    assert updated.value == Decimal("-75.00")


@pytest.mark.asyncio
async def test_update_transaction_description(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, description="Old")

    updated = await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(description="New")
    )

    assert updated.description == "New"


@pytest.mark.asyncio
async def test_update_transaction_date(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, txn_date=date(2025, 1, 1))

    updated = await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(date=date(2025, 6, 15))
    )

    assert updated.date == date(2025, 6, 15)


@pytest.mark.asyncio
async def test_update_transaction_tags(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, tags=["old"])

    updated = await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(tags=["new", "updated"])
    )

    assert updated.tags == ["new", "updated"]


@pytest.mark.asyncio
async def test_update_transaction_category(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)
    category = await _create_category(db_session, "Transport")

    updated = await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(category_id=category.id)
    )

    assert updated.category_id == category.id


@pytest.mark.asyncio
async def test_update_transaction_partial_keeps_other_fields(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(
        db_session, project.id, account.id,
        value=Decimal("-50.00"),
        description="Original",
        txn_date=date(2025, 1, 15),
    )

    updated = await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(description="Changed")
    )

    assert updated.description == "Changed"
    assert updated.value == Decimal("-50.00")
    assert updated.date == date(2025, 1, 15)


@pytest.mark.asyncio
async def test_update_transaction_not_found(db_session: AsyncSession):
    result = await transaction_service.update_transaction(
        db_session, uuid.uuid4(), TransactionUpdate(description="Ghost")
    )
    assert result is None


@pytest.mark.asyncio
async def test_update_transaction_persists(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, description="Before")

    await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(description="After")
    )

    fetched = await transaction_service.get_transaction(db_session, t.id)
    assert fetched.description == "After"


# ---------------------------------------------------------------------------
# delete_transaction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_transaction_returns_true(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)

    result = await transaction_service.delete_transaction(db_session, t.id)

    assert result is True


@pytest.mark.asyncio
async def test_delete_transaction_removes_from_db(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)

    await transaction_service.delete_transaction(db_session, t.id)

    fetched = await transaction_service.get_transaction(db_session, t.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_transaction_not_found(db_session: AsyncSession):
    result = await transaction_service.delete_transaction(db_session, uuid.uuid4())
    assert result is False


@pytest.mark.asyncio
async def test_delete_transaction_does_not_remove_others(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t1 = await _create_transaction(db_session, project.id, account.id, description="Keep")
    t2 = await _create_transaction(db_session, project.id, account.id, description="Remove")

    await transaction_service.delete_transaction(db_session, t2.id)

    remaining = await transaction_service.list_transactions(db_session, project.id)
    ids = [t.id for t in remaining]
    assert t1.id in ids
    assert t2.id not in ids


@pytest.mark.asyncio
async def test_delete_transaction_not_in_list_after_deletion(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id)

    await transaction_service.delete_transaction(db_session, t.id)

    remaining = await transaction_service.list_transactions(db_session, project.id)
    assert all(r.id != t.id for r in remaining)


# ---------------------------------------------------------------------------
# account balance updates
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_transaction_decreases_balance_for_expense(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    assert Decimal(str(account.initial_balance)) == Decimal("0")

    await _create_transaction(db_session, project.id, account.id, value=Decimal("-50.00"))

    refreshed = await account_service.get_account(db_session, account.id)
    assert Decimal(str(refreshed.current_balance)) == Decimal("-50.00")


@pytest.mark.asyncio
async def test_create_transaction_increases_balance_for_income(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)

    await _create_transaction(db_session, project.id, account.id, value=Decimal("1000.00"))

    refreshed = await account_service.get_account(db_session, account.id)
    assert Decimal(str(refreshed.current_balance)) == Decimal("1000.00")


@pytest.mark.asyncio
async def test_create_multiple_transactions_accumulate_balance(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)

    await _create_transaction(db_session, project.id, account.id, value=Decimal("500.00"))
    await _create_transaction(db_session, project.id, account.id, value=Decimal("-120.00"))

    refreshed = await account_service.get_account(db_session, account.id)
    assert Decimal(str(refreshed.current_balance)) == Decimal("380.00")


@pytest.mark.asyncio
async def test_delete_transaction_restores_balance(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, value=Decimal("-50.00"))

    await transaction_service.delete_transaction(db_session, t.id)

    refreshed = await account_service.get_account(db_session, account.id)
    assert Decimal(str(refreshed.current_balance)) == Decimal("0.00")


@pytest.mark.asyncio
async def test_update_transaction_value_adjusts_balance(db_session: AsyncSession):
    project = await _create_project(db_session)
    account = await _create_account(db_session, project.id)
    t = await _create_transaction(db_session, project.id, account.id, value=Decimal("-50.00"))

    await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(value=Decimal("-75.00"))
    )

    refreshed = await account_service.get_account(db_session, account.id)
    assert Decimal(str(refreshed.current_balance)) == Decimal("-75.00")


@pytest.mark.asyncio
async def test_update_transaction_account_moves_balance(db_session: AsyncSession):
    project = await _create_project(db_session)
    account_a = await _create_account(db_session, project.id, name="AccountA")
    account_b = await _create_account(db_session, project.id, name="AccountB")
    t = await _create_transaction(db_session, project.id, account_a.id, value=Decimal("-100.00"))

    await transaction_service.update_transaction(
        db_session, t.id, TransactionUpdate(account_id=account_b.id)
    )

    refreshed_a = await account_service.get_account(db_session, account_a.id)
    refreshed_b = await account_service.get_account(db_session, account_b.id)
    assert Decimal(str(refreshed_a.current_balance)) == Decimal("0.00")
    assert Decimal(str(refreshed_b.current_balance)) == Decimal("-100.00")
