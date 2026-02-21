import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register(client: AsyncClient):
    resp = await client.post("/auth/register", json={
        "email": "test@example.com",
        "name": "Test User",
        "password": "secret123",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "test@example.com"
    assert "id" in data


@pytest.mark.asyncio
async def test_login(client: AsyncClient):
    await client.post("/auth/register", json={
        "email": "user@example.com",
        "name": "User",
        "password": "password",
    })
    resp = await client.post("/auth/login", json={
        "email": "user@example.com",
        "password": "password",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_login_invalid(client: AsyncClient):
    resp = await client.post("/auth/login", json={
        "email": "nobody@example.com",
        "password": "wrong",
    })
    assert resp.status_code == 401
