from contextlib import asynccontextmanager

from fastapi import FastAPI

from bud.database import create_tables
from bud.routers import auth, users, projects, accounts, categories, transactions, budgets, forecasts, reports


@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()
    yield


app = FastAPI(title="bud", description="Budget management API", version="0.1.0", lifespan=lifespan)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(projects.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(transactions.router)
app.include_router(budgets.router)
app.include_router(forecasts.router)
app.include_router(reports.router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "bud"}
