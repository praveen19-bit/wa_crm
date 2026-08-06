"""Authentication endpoints: register, login, me, update password."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from ..database import get_db
from ..models.user import User
from ..schemas.auth import (
    LoginRequest,
    PasswordUpdate,
    RegisterRequest,
    Token,
    UserOut,
)
from .deps import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        name=user.name,
        avatar_url=user.avatar_url,
        created_at=user.created_at,
    )


def _issue_token(user: User) -> Token:
    token, expires_at = create_access_token(user.id)
    return Token(access_token=token, expires_at=expires_at, user=_user_out(user))


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> Token:
    existing = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(
        email=payload.email.lower(),
        name=payload.name.strip(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=Token)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> Token:
    user = await db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        )
    return _issue_token(user)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return _user_out(user)


@router.put("/me", response_model=UserOut)
async def update_me(
    name: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOut:
    if name is not None:
        user.name = name.strip()
    await db.commit()
    await db.refresh(user)
    return _user_out(user)


@router.put("/me/password", response_model=dict)
async def change_password(
    payload: PasswordUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    await db.commit()
    return {"ok": True, "detail": "Password updated"}
