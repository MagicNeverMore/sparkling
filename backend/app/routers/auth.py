"""认证路由。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from ..logger import get_logger
from ..services import auth as auth_service
from ..services.auth import AuthUser

router = APIRouter()
logger = get_logger(__name__)


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
        logger.warning("认证拦截：未登录访问受保护接口 path=%s", request.url.path)
        raise HTTPException(status_code=401, detail="Unauthorized")
    return user


def user_to_out(user: AuthUser) -> UserOut:
    return UserOut(username=user.username, email=user.email)


@router.get("/status", response_model=AuthStatusOut)
def status(request: Request) -> AuthStatusOut:
    user = getattr(request.state, "user", None)
    logger.debug("认证状态查询 authenticated=%s", user is not None)
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
    logger.info("注册完成并已登录 username=%s", user.username)
    return user_to_out(user)


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, request: Request, response: Response) -> UserOut:
    try:
        user = auth_service.authenticate(body.username, body.password)
    except auth_service.AuthError as exc:
        raise HTTPException(status_code=401, detail="用户名或密码错误") from exc
    token, expires_at = auth_service.create_session(user.id)
    _set_session_cookie(response, request, token, expires_at)
    logger.info("登录完成 username=%s", user.username)
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
    logger.info("用户已退出登录")


@router.get("/me", response_model=UserOut)
def me(user: AuthUser = Depends(require_current_user)) -> UserOut:
    logger.debug("读取当前用户 username=%s", user.username)
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
    logger.info("当前用户资料已更新 username=%s", user.username)
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
