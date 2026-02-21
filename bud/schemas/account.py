import uuid
from typing import Optional

from pydantic import BaseModel

from bud.models.account import AccountType


class AccountCreate(BaseModel):
    name: str
    type: AccountType = AccountType.debit
    project_id: uuid.UUID


class AccountRead(BaseModel):
    id: uuid.UUID
    name: str
    type: AccountType

    model_config = {"from_attributes": True}


class AccountUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[AccountType] = None
