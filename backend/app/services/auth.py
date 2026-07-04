"""单用户认证服务。

用户和 session 固定存放在 control SQLite，避免业务数据库不可达时无法登录或切换数据库。
"""
from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

from .runtime_config import connect_control_db

SESSION_COOKIE_NAME = "sparkling_session"
SESSION_DAYS = 30
USERNAME_RE = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_hasher = PasswordHasher()


class AuthError(RuntimeError):
    """认证失败。"""


class AuthConflictError(RuntimeError):
    """单用户已存在或用户名冲突。"""


class AuthValidationError(ValueError):
    """输入不符合安全约束。"""


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str
    email: str | None
    created_at: str
    updated_at: str


def validate_username(username: str) -> str:
    value = username.strip()
    if not USERNAME_RE.fullmatch(value):
        raise AuthValidationError("用户名只能包含 3-32 位数字、英文、点、下划线或连字符")
    return value


def validate_password(password: str) -> str:
    if len(password) < 8:
        raise AuthValidationError("密码至少需要 8 位")
    return password


def validate_email(email: str | None) -> str | None:
    if email is None:
        return None
    value = email.strip()
    if not value:
        return None
    if not EMAIL_RE.fullmatch(value):
        raise AuthValidationError("邮箱格式无效")
    return value


def has_user() -> bool:
    with connect_control_db() as conn:
        row = conn.execute("SELECT 1 FROM auth_user WHERE id = 1").fetchone()
    return row is not None


def get_user() -> AuthUser | None:
    with connect_control_db() as conn:
        row = conn.execute(
            "SELECT id, username, email, created_at, updated_at FROM auth_user WHERE id = 1"
        ).fetchone()
    return _row_to_user(row) if row is not None else None


def create_user(username: str, password: str, email: str | None) -> AuthUser:
    username = validate_username(username)
    password = validate_password(password)
    email = validate_email(email)
    now = _now_iso()
    password_hash = _hasher.hash(password)
    with connect_control_db() as conn:
        if conn.execute("SELECT 1 FROM auth_user WHERE id = 1").fetchone() is not None:
            raise AuthConflictError("用户已存在")
        conn.execute(
            """
            INSERT INTO auth_user (id, username, password_hash, email, created_at, updated_at)
            VALUES (1, ?, ?, ?, ?, ?)
            """,
            (username, password_hash, email, now, now),
        )
        conn.commit()
    user = get_user()
    if user is None:
        raise AuthError("用户创建失败")
    return user


def authenticate(username: str, password: str) -> AuthUser:
    with connect_control_db() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, email, created_at, updated_at FROM auth_user WHERE id = 1"
        ).fetchone()
    if row is None or row["username"] != username:
        raise AuthError("用户名或密码错误")
    try:
        ok = _hasher.verify(row["password_hash"], password)
    except (VerifyMismatchError, VerificationError) as exc:
        raise AuthError("用户名或密码错误") from exc
    if not ok:
        raise AuthError("用户名或密码错误")
    if _hasher.check_needs_rehash(row["password_hash"]):
        _update_password_hash(password)
    return _row_to_user(row)


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    token_hash = _hash_token(token)
    now = datetime.utcnow()
    expires = now + timedelta(days=SESSION_DAYS)
    with connect_control_db() as conn:
        conn.execute("DELETE FROM auth_session WHERE expires_at <= ?", (_iso(now),))
        conn.execute(
            """
            INSERT INTO auth_session (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (token_hash, user_id, _iso(now), _iso(expires)),
        )
        conn.commit()
    return token, _iso(expires)


def get_user_by_session(token: str | None) -> AuthUser | None:
    if not token:
        return None
    token_hash = _hash_token(token)
    now = _now_iso()
    with connect_control_db() as conn:
        row = conn.execute(
            """
            SELECT u.id, u.username, u.email, u.created_at, u.updated_at
            FROM auth_session s
            JOIN auth_user u ON u.id = s.user_id
            WHERE s.token_hash = ? AND s.expires_at > ?
            """,
            (token_hash, now),
        ).fetchone()
    return _row_to_user(row) if row is not None else None


def delete_session(token: str | None) -> None:
    if not token:
        return
    with connect_control_db() as conn:
        conn.execute("DELETE FROM auth_session WHERE token_hash = ?", (_hash_token(token),))
        conn.commit()


def update_user(
    *,
    username: str | None = None,
    email: str | None = None,
    password: str | None = None,
) -> AuthUser:
    current = get_user()
    if current is None:
        raise AuthError("用户不存在")
    next_username = validate_username(username) if username is not None else current.username
    next_email = validate_email(email) if email is not None else current.email
    now = _now_iso()
    fields: list[str] = ["username = ?", "email = ?", "updated_at = ?"]
    values: list[str | None] = [next_username, next_email, now]
    if password is not None and password != "":
        validate_password(password)
        fields.append("password_hash = ?")
        values.append(_hasher.hash(password))
    values.append(str(current.id))
    with connect_control_db() as conn:
        conn.execute(
            f"UPDATE auth_user SET {', '.join(fields)} WHERE id = ?",  # noqa: S608
            values,
        )
        conn.commit()
    user = get_user()
    if user is None:
        raise AuthError("用户不存在")
    return user


def _update_password_hash(password: str) -> None:
    with connect_control_db() as conn:
        conn.execute(
            "UPDATE auth_user SET password_hash = ?, updated_at = ? WHERE id = 1",
            (_hasher.hash(password), _now_iso()),
        )
        conn.commit()


def _row_to_user(row) -> AuthUser:  # noqa: ANN001
    return AuthUser(
        id=row["id"],
        username=row["username"],
        email=row["email"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return _iso(datetime.utcnow())


def _iso(value: datetime) -> str:
    return value.isoformat(timespec="seconds")
