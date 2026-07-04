"""认证路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..services import auth as auth_service
from ..services.auth import AuthUser

router = APIRouter()


class UserOut(BaseModel):
    username: str
    email: str | None = None


class AuthStatusOut(BaseModel):
    initialized: bool
    authenticated: bool
    user: UserOut | None = None


class RegisterIn(BaseModel):
    username: str
    password: str
    email: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class UserUpdateIn(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str | None = None


def require_current_user(request: Request) -> AuthUser:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def user_to_out(user: AuthUser) -> UserOut:
    return UserOut(username=user.username, email=user.email)


@router.get("/status", response_model=AuthStatusOut)
def status(request: Request) -> AuthStatusOut:
    user = getattr(request.state, "user", None)
    return AuthStatusOut(
        initialized=auth_service.has_user(),
        authenticated=user is not None,
        user=user_to_out(user) if user is not None else None,
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response) -> UserOut:
    try:
        user = auth_service.create_user(body.username, body.password, body.email)
    except auth_service.AuthConflictError as exc:
        raise HTTPException(status_code=409, detail="用户已存在") from exc
    except auth_service.AuthValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    token, expires_at = auth_service.create_session(user.id)
    _set_session_cookie(response, request, token, expires_at)
    return user_to_out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response) -> UserOut:
    try:
        user = auth_service.authenticate(body.username, body.password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail="用户名或密码错误") from exc
    token, expires_at = auth_service.create_session(user.id)
    _set_session_cookie(response, request, token, expires_at)
    return user_to_out(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    auth_service.delete_session(request.cookies.get(auth_service.SESSION_COOKIE_NAME))
    response.delete_cookie(
        auth_service.SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
    )


@router.get("/me", response_model=UserOut)
def me(user: AuthUser = Depends(require_current_user)) -> UserOut:
    return user_to_out(user)


@router.put("/me", response_model=UserOut)
def update_me(body: UserUpdateIn, _user: AuthUser = Depends(require_current_user)) -> UserOut:
    try:
        user = auth_service.update_user(
            username=body.username,
            email=body.email,
            password=body.password,
        )
    except auth_service.AuthValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return user_to_out(user)


def _set_session_cookie(response: Response, request: Request, token: str, expires_at: str) -> None:
    response.set_cookie(
        auth_service.SESSION_COOKIE_NAME,
        token,
        max_age=auth_service.SESSION_DAYS * 24 * 60 * 60,
        expires=expires_at,
        path="/",
        httponly=True,
        samesite="lax",
        secure=_is_secure_request(request),
    )


def _is_secure_request(request: Request) -> bool:
    forwarded = request.headers.get("x-forwarded-proto", "")
    return request.url.scheme == "https" or forwarded.split(",")[0].strip() == "https"
