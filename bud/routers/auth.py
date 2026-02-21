from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from bud.database import get_db
from bud.schemas.auth import Token, LoginRequest, GoogleCallbackRequest
from bud.schemas.user import UserCreate, UserRead
from bud.services import users as user_service
from bud.auth import verify_password, create_access_token, get_google_auth_url, exchange_google_code

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(data: UserCreate, db: AsyncSession = Depends(get_db)):
    existing = await user_service.get_user_by_email(db, data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = await user_service.create_user(db, data)
    return user


@router.post("/login", response_model=Token)
async def login(data: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await user_service.get_user_by_email(db, data.email)
    if not user or not user.hashed_password:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(user.id)
    return Token(access_token=token)


@router.get("/google")
async def google_login():
    url = get_google_auth_url()
    return RedirectResponse(url=url)


@router.get("/google/callback", response_model=Token)
async def google_callback(code: str, db: AsyncSession = Depends(get_db)):
    try:
        google_info = await exchange_google_code(code)
    except Exception:
        raise HTTPException(status_code=400, detail="Failed to exchange Google code")
    user = await user_service.create_or_update_google_user(db, google_info)
    token = create_access_token(user.id)
    return Token(access_token=token)
