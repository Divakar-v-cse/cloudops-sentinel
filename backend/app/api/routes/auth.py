from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, DbSession, client_ip, require_admin
from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.core.utils import utcnow
from app.models import User
from app.schemas.domain import (
    LoginRequest,
    PasswordChange,
    Token,
    UserCreate,
    UserOut,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/auth", tags=["authentication"])


def _authenticate(db: Session, email: str, password: str, request: Request | None = None) -> Token:
    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if user is None or not verify_password(password, user.hashed_password):
        record_audit(
            db,
            actor=email,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else None,
            detail={"reason": "invalid credentials"},
            ip_address=client_ip(request) if request else None,
        )
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is disabled")

    user.last_login_at = utcnow()
    db.commit()
    token = create_access_token(subject=user.email, role=user.role)
    record_audit(
        db,
        actor=user.email,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        ip_address=client_ip(request) if request else None,
    )
    return Token(
        access_token=token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserOut.model_validate(user),
    )


@router.post("/login", response_model=Token, summary="Authenticate with email and password")
def login(payload: LoginRequest, db: DbSession, request: Request) -> Token:
    return _authenticate(db, payload.email, payload.password, request)


@router.post("/token", response_model=Token, summary="OAuth2 password flow (for API docs)")
def token(
    db: DbSession,
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    return _authenticate(db, form.username, form.password, request)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/change-password", response_model=UserOut)
def change_password(payload: PasswordChange, user: CurrentUser, db: DbSession) -> UserOut:
    if not verify_password(payload.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if payload.current_password == payload.new_password:
        raise HTTPException(status_code=400, detail="New password must differ from the current password")
    user.hashed_password = hash_password(payload.new_password)
    user.must_change_password = False
    db.commit()
    db.refresh(user)
    record_audit(
        db, actor=user.email, action="auth.password_changed", entity_type="user", entity_id=user.id
    )
    return UserOut.model_validate(user)


@router.get("/users", response_model=list[UserOut])
def list_users(db: DbSession, user: CurrentUser) -> list[UserOut]:
    if user.role not in {"admin", "engineer"}:
        raise HTTPException(status_code=403, detail="Requires engineer or admin role")
    return [UserOut.model_validate(item) for item in db.query(User).order_by(User.id).all()]


@router.post("/users", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate, db: DbSession, admin: Annotated[User, Depends(require_admin)]
) -> UserOut:
    from app.models import Role

    if db.query(User).filter(User.email == payload.email.lower()).first():
        raise HTTPException(status_code=409, detail="A user with that email already exists")
    role = db.query(Role).filter(Role.name == payload.role).first()
    if role is None:
        raise HTTPException(status_code=422, detail=f"Unknown role '{payload.role}'")
    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role_id=role.id,
        must_change_password=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    record_audit(
        db,
        actor=admin.email,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        detail={"role": payload.role, "email": payload.email},
    )
    return UserOut.model_validate(user)


@router.patch("/users/{user_id}/status", response_model=UserOut)
def toggle_user(user_id: int, active: bool, db: DbSession, admin: Annotated[User, Depends(require_admin)]) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.id == admin.id and not active:
        raise HTTPException(status_code=400, detail="You cannot deactivate your own account")
    target.is_active = active
    db.commit()
    db.refresh(target)
    record_audit(
        db,
        actor=admin.email,
        action="user.activated" if active else "user.deactivated",
        entity_type="user",
        entity_id=target.id,
    )
    return UserOut.model_validate(target)
