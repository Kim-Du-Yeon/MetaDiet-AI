"""
core/auth.py

Supabase Auth JWT 검증. 클라이언트가 보낸 user_id를 신뢰하지 않고
Authorization 헤더의 Supabase JWT를 직접 검증해서 user_id를 도출한다.

주의: JWT의 `sub` 클레임은 Supabase auth.uid()이며, 이는 users.auth_id 값이다.
     앱 전반의 user_id 파라미터는 users.id(내부 PK, meal_logs 등이 참조)이므로
     auth_id -> users.id 매핑을 거쳐야 기존 쿼리(.eq("user_id", ...))가 그대로 동작한다.
     이 매핑이 없으면 로그인은 성공해도 모든 데이터 조회가 빈 결과를 반환한다.
"""
import time
import logging
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt as jose_jwt, JWTError
from app.core.config import get_settings
from app.db.supabase_client import get_supabase

# tokenUrl은 Swagger UI 표시용일 뿐 실제 로그인은 Supabase Auth가 처리한다.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)

_UNAUTHORIZED = lambda detail: HTTPException(
    status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"}
)

_jwks_client = None


@dataclass(frozen=True)
class AuthContext:
    auth_id: str
    session_id: str


def _get_jwks_client() -> PyJWKClient:
    """Supabase Auth(GoTrue) JWKS 캐싱 클라이언트. ES256/RS256 신규 키 체계 검증용.

    경로는 Supabase 표준인 auth/v1 하위(`{SUPABASE_URL}/.well-known/jwks.json`가
    아니라 `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`) — 프로젝트 도메인 루트가
    아닌 GoTrue 서비스 네임스페이스에 노출된다.
    """
    global _jwks_client
    if _jwks_client is None:
        url = f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json"
        _jwks_client = PyJWKClient(url)
    return _jwks_client


def _decode_verified_token(token: str) -> dict:
    if not token:
        raise _UNAUTHORIZED("인증 토큰이 없습니다.")
    try:
        signing_key = _get_jwks_client().get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
        )
    except Exception:
        try:
            payload = jose_jwt.decode(
                token,
                get_settings().supabase_jwt_secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        except JWTError:
            raise _UNAUTHORIZED("유효하지 않거나 만료된 토큰입니다.")
    return payload


def get_current_auth_id(token: str = Depends(oauth2_scheme)) -> str:
    """Authorization: Bearer <supabase_jwt> 검증 후 auth.uid()(sub)를 반환."""
    payload = _decode_verified_token(token)

    auth_id = payload.get("sub")
    if not auth_id:
        raise _UNAUTHORIZED("토큰에 sub 클레임이 없습니다.")
    return auth_id


def validate_recent_auth_payload(
    payload: dict, *, now: float | None = None, max_age_seconds: int = 300
) -> AuthContext:
    """Require a live session claim and a recent password authentication event.

    Token ``iat`` is deliberately ignored: automatic token refresh produces a
    fresh iat without proving that the user entered their password again.
    """
    auth_id = payload.get("sub")
    session_id = payload.get("session_id")
    current_time = time.time() if now is None else now
    password_times = []
    for method in payload.get("amr") or []:
        if method.get("method") != "password":
            continue
        try:
            password_times.append(float(method["timestamp"]))
        except (KeyError, TypeError, ValueError):
            continue
    latest_password_auth = max(password_times, default=None)
    age = None if latest_password_auth is None else current_time - latest_password_auth
    if (
        not auth_id
        or not session_id
        or age is None
        or age > max_age_seconds
        or age < -60
    ):
        raise _UNAUTHORIZED({
            "code": "recent_authentication_required",
            "message": "계정 삭제 전에 비밀번호를 다시 확인해주세요.",
        })
    return AuthContext(auth_id=str(auth_id), session_id=str(session_id))


def get_recent_auth_context(token: str = Depends(oauth2_scheme)) -> AuthContext:
    return validate_recent_auth_payload(_decode_verified_token(token))


def get_active_auth_id(token: str = Depends(oauth2_scheme)) -> str:
    """Verify the Auth user still exists before creating application state.

    Signature validation alone is insufficient after account deletion because
    an already-issued Supabase access token remains valid until its expiry.
    """
    payload = _decode_verified_token(token)
    auth_id = payload.get("sub")
    if not auth_id:
        raise _UNAUTHORIZED("토큰에 sub 클레임이 없습니다.")
    try:
        response = get_supabase().auth.get_user(token)
        active_id = str(response.user.id)
    except Exception:
        raise _UNAUTHORIZED({
            "code": "auth_session_inactive",
            "message": "인증 계정이 존재하지 않거나 세션이 유효하지 않습니다.",
        }) from None
    if active_id != str(auth_id):
        raise _UNAUTHORIZED({
            "code": "auth_session_inactive",
            "message": "인증 계정과 세션 정보가 일치하지 않습니다.",
        })
    return str(auth_id)


def get_current_user(auth_id: str = Depends(get_current_auth_id)) -> str:
    """auth_id -> users.id 매핑. 프로필(users row)이 있어야 하는 일반 엔드포인트용."""
    started = time.perf_counter()
    try:
        rows = (
            get_supabase().table("users").select("id")
            .eq("auth_id", auth_id).limit(1).execute().data
        )
    finally:
        logging.getLogger(__name__).warning('chat_preparation stage=auth_profile elapsed_ms=%.3f',
            (time.perf_counter() - started) * 1000)
    if not rows:
        raise _UNAUTHORIZED("프로필이 없는 사용자입니다. 먼저 회원가입을 완료하세요.")
    return rows[0]["id"]


def get_current_admin(token: str = Depends(oauth2_scheme)) -> str:
    """Require a verified JWT whose top-level email is in the server allowlist."""
    payload = _decode_verified_token(token)
    auth_id = payload.get("sub")
    email = str(payload.get("email") or "").strip().lower()
    allowed = {
        item.strip().lower()
        for item in get_settings().admin_emails.split(",")
        if item.strip()
    }
    if not auth_id:
        raise _UNAUTHORIZED("토큰에 sub 클레임이 없습니다.")
    if not email or email not in allowed:
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다.")
    return str(auth_id)
