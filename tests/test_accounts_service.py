"""Unit tests for the accounts service layer."""
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from bud.models.account import AccountType
from bud.schemas.account import AccountCreate, AccountUpdate
from bud.schemas.project import ProjectCreate
from bud.services import accounts as account_service
from bud.services import projects as project_service


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _create_project(db: AsyncSession, name: str = "TestProject") -> object:
    return await project_service.create_project(db, ProjectCreate(name=name))


async def _create_account(
    db: AsyncSession,
    project_id: uuid.UUID,
    name: str = "Checking",
    account_type: AccountType = AccountType.debit,
    initial_balance: float = 0.0,
) -> object:
    return await account_service.create_account(
        db,
        AccountCreate(
            name=name,
            type=account_type,
            project_id=project_id,
            initial_balance=initial_balance,
        ),
    )


# ---------------------------------------------------------------------------
# list_accounts
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_accounts_empty(db_session: AsyncSession):
    project = await _create_project(db_session)
    result = await account_service.list_accounts(db_session, project.id)
    assert result == []


@pytest.mark.asyncio
async def test_list_accounts_returns_all_for_project(db_session: AsyncSession):
    project = await _create_project(db_session)
    await _create_account(db_session, project.id, "Checking")
    await _create_account(db_session, project.id, "Savings")

    result = await account_service.list_accounts(db_session, project.id)

    assert len(result) == 2
    assert {a.name for a in result} == {"Checking", "Savings"}


@pytest.mark.asyncio
async def test_list_accounts_only_returns_accounts_for_given_project(db_session: AsyncSession):
    proj1 = await _create_project(db_session, "Proj1")
    proj2 = await _create_project(db_session, "Proj2")
    await _create_account(db_session, proj1.id, "Account1")
    await _create_account(db_session, proj2.id, "Account2")

    result = await account_service.list_accounts(db_session, proj1.id)

    assert len(result) == 1
    assert result[0].name == "Account1"


@pytest.mark.asyncio
async def test_list_accounts_without_project_id_returns_all(db_session: AsyncSession):
    proj1 = await _create_project(db_session, "P1")
    proj2 = await _create_project(db_session, "P2")
    await _create_account(db_session, proj1.id, "Acc1")
    await _create_account(db_session, proj2.id, "Acc2")

    result = await account_service.list_accounts(db_session)

    assert len(result) == 2


# ---------------------------------------------------------------------------
# get_account_by_name
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_account_by_name_found(db_session: AsyncSession):
    project = await _create_project(db_session)
    created = await _create_account(db_session, project.id, "MyAccount")

    found = await account_service.get_account_by_name(db_session, "MyAccount", project.id)

    assert found is not None
    assert found.id == created.id
    assert found.name == "MyAccount"


@pytest.mark.asyncio
async def test_get_account_by_name_not_found(db_session: AsyncSession):
    project = await _create_project(db_session)

    result = await account_service.get_account_by_name(db_session, "Nonexistent", project.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_account_by_name_wrong_project(db_session: AsyncSession):
    proj1 = await _create_project(db_session, "P1")
    proj2 = await _create_project(db_session, "P2")
    await _create_account(db_session, proj1.id, "SharedName")

    result = await account_service.get_account_by_name(db_session, "SharedName", proj2.id)

    assert result is None


@pytest.mark.asyncio
async def test_get_account_by_name_case_sensitive(db_session: AsyncSession):
    project = await _create_project(db_session)
    await _create_account(db_session, project.id, "CaseSensitive")

    result = await account_service.get_account_by_name(db_session, "casesensitive", project.id)

    assert result is None


# ---------------------------------------------------------------------------
# get_account
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_account_found(db_session: AsyncSession):
    project = await _create_project(db_session)
    created = await _create_account(db_session, project.id, "Lookup")

    found = await account_service.get_account(db_session, created.id)

    assert found is not None
    assert found.id == created.id
    assert found.name == "Lookup"


@pytest.mark.asyncio
async def test_get_account_not_found(db_session: AsyncSession):
    result = await account_service.get_account(db_session, uuid.uuid4())
    assert result is None


# ---------------------------------------------------------------------------
# create_account
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_account_returns_uuid(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id)

    assert a.id is not None
    assert isinstance(a.id, uuid.UUID)


@pytest.mark.asyncio
async def test_create_account_stores_name(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, "StoredName")

    assert a.name == "StoredName"


@pytest.mark.asyncio
async def test_create_account_default_type_is_debit(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id)

    assert a.type == AccountType.debit


@pytest.mark.asyncio
async def test_create_account_credit_type(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, account_type=AccountType.credit)

    assert a.type == AccountType.credit


@pytest.mark.asyncio
async def test_create_account_sets_initial_balance(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, initial_balance=500.0)

    assert float(a.initial_balance) == 500.0


@pytest.mark.asyncio
async def test_create_account_initial_balance_equals_current_balance(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, initial_balance=250.0)

    assert float(a.initial_balance) == float(a.current_balance)


@pytest.mark.asyncio
async def test_create_account_default_balance_is_zero(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id)

    assert float(a.initial_balance) == 0.0
    assert float(a.current_balance) == 0.0


@pytest.mark.asyncio
async def test_create_account_persisted(db_session: AsyncSession):
    project = await _create_project(db_session)
    created = await _create_account(db_session, project.id, "Persisted")

    fetched = await account_service.get_account(db_session, created.id)

    assert fetched is not None
    assert fetched.name == "Persisted"


@pytest.mark.asyncio
async def test_create_account_unique_ids(db_session: AsyncSession):
    project = await _create_project(db_session)
    a1 = await _create_account(db_session, project.id, "Acc1")
    a2 = await _create_account(db_session, project.id, "Acc2")

    assert a1.id != a2.id


@pytest.mark.asyncio
async def test_create_account_duplicate_name_raises(db_session: AsyncSession):
    project = await _create_project(db_session)
    await _create_account(db_session, project.id, "Duplicate")

    with pytest.raises(ValueError, match="already exists"):
        await _create_account(db_session, project.id, "Duplicate")


@pytest.mark.asyncio
async def test_create_account_duplicate_name_allowed_in_different_project(db_session: AsyncSession):
    proj1 = await _create_project(db_session, "P1")
    proj2 = await _create_project(db_session, "P2")

    a1 = await _create_account(db_session, proj1.id, "SharedName")
    a2 = await _create_account(db_session, proj2.id, "SharedName")

    assert a1.id != a2.id


@pytest.mark.asyncio
async def test_create_account_project_not_found_raises(db_session: AsyncSession):
    with pytest.raises(ValueError, match="Project not found"):
        await account_service.create_account(
            db_session,
            AccountCreate(name="Orphan", project_id=uuid.uuid4()),
        )


# ---------------------------------------------------------------------------
# update_account
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_update_account_name(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, "OldName")

    updated = await account_service.update_account(db_session, a.id, AccountUpdate(name="NewName"))

    assert updated is not None
    assert updated.id == a.id
    assert updated.name == "NewName"


@pytest.mark.asyncio
async def test_update_account_type(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, account_type=AccountType.debit)

    updated = await account_service.update_account(db_session, a.id, AccountUpdate(type=AccountType.credit))

    assert updated.type == AccountType.credit


@pytest.mark.asyncio
async def test_update_account_persists(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, "Before")

    await account_service.update_account(db_session, a.id, AccountUpdate(name="After"))

    fetched = await account_service.get_account(db_session, a.id)
    assert fetched.name == "After"


@pytest.mark.asyncio
async def test_update_account_empty_payload_keeps_values(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, "Unchanged", AccountType.credit)

    updated = await account_service.update_account(db_session, a.id, AccountUpdate())

    assert updated is not None
    assert updated.name == "Unchanged"
    assert updated.type == AccountType.credit


@pytest.mark.asyncio
async def test_update_account_not_found(db_session: AsyncSession):
    result = await account_service.update_account(db_session, uuid.uuid4(), AccountUpdate(name="X"))
    assert result is None


# ---------------------------------------------------------------------------
# delete_account
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delete_account_returns_true(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, "ToDelete")

    result = await account_service.delete_account(db_session, a.id)

    assert result is True


@pytest.mark.asyncio
async def test_delete_account_removes_from_db(db_session: AsyncSession):
    project = await _create_project(db_session)
    a = await _create_account(db_session, project.id, "Gone")

    await account_service.delete_account(db_session, a.id)

    fetched = await account_service.get_account(db_session, a.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_account_not_in_list_after_deletion(db_session: AsyncSession):
    project = await _create_project(db_session)
    a1 = await _create_account(db_session, project.id, "Keep")
    a2 = await _create_account(db_session, project.id, "Remove")

    await account_service.delete_account(db_session, a2.id)

    remaining = await account_service.list_accounts(db_session, project.id)
    ids = [a.id for a in remaining]

    assert a1.id in ids
    assert a2.id not in ids


@pytest.mark.asyncio
async def test_delete_account_not_found(db_session: AsyncSession):
    result = await account_service.delete_account(db_session, uuid.uuid4())
    assert result is False
