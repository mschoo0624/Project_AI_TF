"""Authentication endpoints for training workflows."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from user.app.database import get_db
from user.app.models.auth_session import AuthSession
from user.app.models.auth_login_failure import AuthLoginFailure
from user.app.models.audit_log import AuditLog
from user.app.models.user import User
from user.app.schemas.auth import (
    AuthTokenRead,
    BootstrapRequest,
    LoginRequest,
    PasswordResetRequest,
    UserCreate,
    UserRead,
    UserUpdate,
)
from user.app.services.auth import (
    ALLOWED_ROLES,
    bearer_scheme,
    get_current_user,
    hash_password,
    issue_session,
    _now,
    require_approver,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["authentication"])
LOGIN_FAILURE_LIMIT = 5
LOGIN_WINDOW = timedelta(minutes=15)


def _token_response(user: User, token: str, expires_at) -> dict[str, object]:
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": {"id": user.id, "username": user.username, "role": user.role},
    }


@router.post("/bootstrap", response_model=AuthTokenRead, status_code=status.HTTP_201_CREATED)
def bootstrap_first_approver(
    payload: BootstrapRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    if request.client is None or request.client.host not in {"127.0.0.1", "::1", "localhost"}:
        raise HTTPException(status_code=403, detail="Initial account setup is only allowed from localhost")
    if db.bind is None or db.bind.dialect.name != "sqlite":
        raise HTTPException(status_code=503, detail="Bootstrap requires the configured SQLite database")
    db.execute(text("BEGIN IMMEDIATE"))
    if db.scalar(select(func.count(User.id))) or 0:
        db.rollback()
        raise HTTPException(status_code=409, detail="Bootstrap is disabled after the first account exists")

    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role="approver",
    )
    db.add(user)
    try:
        db.flush()
        token, expires_at = issue_session(db, user)
        db.add(AuditLog(
            user_id=user.id,
            action="auth.bootstrap",
            table_name="app_user",
            record_id=user.id,
            entity_key=user.username,
            actor_label=user.username,
            after_data=json.dumps({"role": user.role, "is_active": user.is_active}, sort_keys=True),
        ))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from error
    return _token_response(user, token, expires_at)


@router.post("/login", response_model=AuthTokenRead)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, object]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    client_ip = request.client.host if request.client is not None else "unknown"
    normalized_username = payload.username.strip().casefold()
    keys = (
        hashlib.sha256(f"ip:{client_ip}".encode()).hexdigest(),
        hashlib.sha256(f"user:{client_ip}:{normalized_username}".encode()).hexdigest(),
    )
    cutoff = now - LOGIN_WINDOW
    db.execute(delete(AuthLoginFailure).where(AuthLoginFailure.failed_at < cutoff))
    if any(
        (db.scalar(select(func.count(AuthLoginFailure.id)).where(
            AuthLoginFailure.key_hash == key,
            AuthLoginFailure.failed_at >= cutoff,
        )) or 0) >= LOGIN_FAILURE_LIMIT
        for key in keys
    ):
        raise HTTPException(
            status_code=429,
            detail="Too many failed login attempts. Try again later.",
            headers={"Retry-After": str(int(LOGIN_WINDOW.total_seconds()))},
        )

    user = db.scalar(select(User).where(User.username == payload.username.strip()))
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        db.add_all(AuthLoginFailure(key_hash=key, failed_at=now) for key in keys)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")
    if user.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="Account role is not configured")
    if not user.password_hash.startswith("$argon2"):
        user.password_hash = hash_password(payload.password)
    db.execute(delete(AuthLoginFailure).where(AuthLoginFailure.key_hash.in_(keys)))
    token, expires_at = issue_session(db, user)
    db.commit()
    return _token_response(user, token, expires_at)


@router.get("/me", response_model=UserRead)
def who_am_i(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    user: User = Depends(get_current_user),
    credentials=Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> None:
    del user
    session_hash = __import__("hashlib").sha256(
        credentials.credentials.encode("ascii", errors="ignore")
    ).hexdigest()
    session = db.get(AuthSession, session_hash)
    if session is not None and session.revoked_at is None:
        from user.app.services.auth import _now

        session.revoked_at = _now()
        db.commit()


@router.post("/users", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: UserCreate,
    actor: User = Depends(require_approver),
    db: Session = Depends(get_db),
) -> User:
    if payload.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=422, detail="Role must be viewer, scheduler, or approver")
    user = User(
        username=payload.username.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.flush()
        db.add(AuditLog(
            user_id=actor.id,
            action="auth.user.create",
            table_name="app_user",
            record_id=user.id,
            entity_key=user.username,
            actor_label=actor.username,
            after_data=json.dumps({"role": user.role, "is_active": user.is_active}, sort_keys=True),
        ))
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status_code=409, detail="Username already exists") from error
    db.refresh(user)
    return user


def _lock_account_rows(db: Session) -> None:
    if db.bind is not None and db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))


def _revoke_user_sessions(db: Session, user_id: int) -> None:
    db.execute(update(AuthSession).where(
        AuthSession.user_id == user_id,
        AuthSession.revoked_at.is_(None),
    ).values(revoked_at=_now()))


@router.post("/users/{user_id}/password-reset", response_model=UserRead)
def reset_user_password(
    user_id: int,
    payload: PasswordResetRequest,
    actor: User = Depends(require_approver),
    db: Session = Depends(get_db),
) -> User:
    _lock_account_rows(db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.password_hash = hash_password(payload.password)
    _revoke_user_sessions(db, user.id)
    db.add(AuditLog(
        user_id=actor.id,
        action="auth.password_reset",
        table_name="app_user",
        record_id=user.id,
        entity_key=user.username,
        actor_label=actor.username,
        before_data=json.dumps({"password_set": True}, sort_keys=True),
        after_data=json.dumps({"password_reset": True, "sessions_revoked": True}, sort_keys=True),
    ))
    db.commit()
    db.refresh(user)
    return user


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(
    user_id: int,
    payload: UserUpdate,
    actor: User = Depends(require_approver),
    db: Session = Depends(get_db),
) -> User:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(status_code=422, detail="At least one account field must be provided")
    if any(value is None for value in changes.values()):
        raise HTTPException(status_code=422, detail="Account fields cannot be null")
    _lock_account_rows(db)
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    before = {"role": user.role, "is_active": user.is_active}
    next_role = changes.get("role", user.role)
    next_active = changes.get("is_active", user.is_active)
    if user.role == "approver" and user.is_active and (next_role != "approver" or not next_active):
        approver_count = db.scalar(select(func.count(User.id)).where(
            User.role == "approver", User.is_active.is_(True),
        )) or 0
        if approver_count <= 1:
            db.rollback()
            raise HTTPException(status_code=409, detail="The last active approver cannot be demoted or deactivated")
    for field, value in changes.items():
        setattr(user, field, value)
    after = {"role": user.role, "is_active": user.is_active}
    if before != after:
        _revoke_user_sessions(db, user.id)
        db.add(AuditLog(
            user_id=actor.id,
            action="auth.user.update",
            table_name="app_user",
            record_id=user.id,
            entity_key=user.username,
            actor_label=actor.username,
            before_data=json.dumps(before, sort_keys=True),
            after_data=json.dumps(after, sort_keys=True),
        ))
    db.commit()
    db.refresh(user)
    return user