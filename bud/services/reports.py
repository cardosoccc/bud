import uuid
from datetime import date
from decimal import Decimal
from typing import List

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from bud.models.budget import Budget
from bud.models.forecast import Forecast
from bud.models.transaction import Transaction
from bud.models.account import Account, AccountType
from bud.models.project import project_accounts
from bud.schemas.report import ReportRead, AccountBalance, ForecastActual


async def generate_report(db: AsyncSession, budget_id: uuid.UUID) -> ReportRead:
    budget_result = await db.execute(select(Budget).where(Budget.id == budget_id))
    budget = budget_result.scalar_one_or_none()
    if not budget:
        raise ValueError("Budget not found")

    today = date.today()
    is_projected = budget.end_date > today

    # Get all accounts for the project
    accts_result = await db.execute(
        select(Account)
        .join(project_accounts, Account.id == project_accounts.c.account_id)
        .where(
            project_accounts.c.project_id == budget.project_id,
            Account.type != AccountType.nil,
        )
    )
    accounts = list(accts_result.scalars().all())

    # Get all primary transactions in the budget period
    txns_result = await db.execute(
        select(Transaction).where(
            and_(
                Transaction.project_id == budget.project_id,
                Transaction.is_counterpart == False,  # noqa: E712
                Transaction.date >= budget.start_date,
                Transaction.date <= budget.end_date,
            )
        )
    )
    transactions = list(txns_result.scalars().all())

    # Calculate account balances
    account_balances = []
    total_balance = Decimal("0")
    total_earnings = Decimal("0")
    total_expenses = Decimal("0")

    for account in accounts:
        inflows = sum(
            t.value for t in transactions if t.destination_account_id == account.id
        )
        outflows = sum(
            t.value for t in transactions if t.source_account_id == account.id
        )
        balance = Decimal(str(inflows)) - Decimal(str(outflows))
        account_balances.append(
            AccountBalance(
                account_id=account.id,
                account_name=account.name,
                balance=balance,
            )
        )
        total_balance += balance

    # Get nil accounts (external flows)
    nil_accts_result = await db.execute(
        select(Account)
        .join(project_accounts, Account.id == project_accounts.c.account_id)
        .where(
            project_accounts.c.project_id == budget.project_id,
            Account.type == AccountType.nil,
        )
    )
    nil_accounts = {a.id for a in nil_accts_result.scalars().all()}

    for t in transactions:
        val = Decimal(str(t.value))
        if t.source_account_id in nil_accounts and t.destination_account_id not in nil_accounts:
            # Money coming in from external: earnings
            total_earnings += val
        elif t.destination_account_id in nil_accounts and t.source_account_id not in nil_accounts:
            # Money going out to external: expenses
            total_expenses += val

    # Get forecasts and compute actuals
    forecasts_result = await db.execute(
        select(Forecast).where(Forecast.budget_id == budget_id)
    )
    forecasts = list(forecasts_result.scalars().all())

    forecast_actuals = []
    for forecast in forecasts:
        if forecast.category_id:
            actual = sum(
                Decimal(str(t.value))
                for t in transactions
                if t.category_id == forecast.category_id
            )
        else:
            actual = Decimal("0")

        forecast_val = Decimal(str(forecast.value))
        forecast_actuals.append(
            ForecastActual(
                forecast_id=forecast.id,
                description=forecast.description,
                forecast_value=forecast_val,
                actual_value=actual,
                difference=actual - forecast_val,
                category_id=forecast.category_id,
            )
        )

    # For future budgets, calculate projected net balance by summing
    # net forecast values for all budgets from the earliest future month
    # up to and including this budget month
    projected_net_balance = None
    if is_projected:
        projected_net_balance = await _calculate_projected_net_balance(
            db, budget, today
        )

    return ReportRead(
        budget_id=budget.id,
        budget_name=budget.name,
        start_date=budget.start_date,
        end_date=budget.end_date,
        account_balances=account_balances,
        total_balance=total_balance,
        total_earnings=total_earnings,
        total_expenses=total_expenses,
        forecasts=forecast_actuals,
        is_projected=is_projected,
        projected_net_balance=projected_net_balance,
    )


async def _calculate_projected_net_balance(
    db: AsyncSession, target_budget: Budget, today: date
) -> Decimal:
    """Calculate the cumulative projected net balance from current month through
    the target budget month by summing net forecast values across all intermediate
    monthly budgets."""

    # Get all budgets for the project ordered by name (YYYY-MM)
    all_budgets_result = await db.execute(
        select(Budget)
        .where(Budget.project_id == target_budget.project_id)
        .order_by(Budget.name)
    )
    all_budgets: List[Budget] = list(all_budgets_result.scalars().all())

    # Include budgets from the first future/current month up to target
    cumulative = Decimal("0")
    for b in all_budgets:
        if b.start_date > today or (b.start_date <= today <= b.end_date):
            if b.name > target_budget.name:
                break

            # Get forecasts for this budget
            forecasts_result = await db.execute(
                select(Forecast).where(Forecast.budget_id == b.id)
            )
            budget_forecasts = list(forecasts_result.scalars().all())

            # Net forecast: positive = earnings, negative = expenses
            # Use the sum of forecast values as the net projected change
            for f in budget_forecasts:
                # Check if this recurrent forecast applies to this month
                if f.is_recurrent:
                    applies = True
                    if f.recurrent_start and b.start_date < f.recurrent_start:
                        applies = False
                    if f.recurrent_end and b.end_date > f.recurrent_end:
                        applies = False
                    if applies:
                        cumulative += Decimal(str(f.value))
                else:
                    cumulative += Decimal(str(f.value))

    return cumulative
