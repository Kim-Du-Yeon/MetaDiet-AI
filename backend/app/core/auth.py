"""
core/auth.py

Supabase Auth JWT 검증. 클라이언트가 보낸 user_id를 신뢰하지 않고
Authorization 헤더의 Supabase JWT를 직접 검증해서 user_id를 도출한다.

주의: JWT의 `sub` 클레임은 Supabase auth.uid()이며, 이는 users.auth_id 값이다.
     앱 전반의 user_id 파라미터는 users.id(내부 PK, meal_logs 등이 참조)이므로
     auth_id -> users.id 매핑을 거쳐야 기존 쿼리(.eq("user_id", ...))가 그대로 동작한다.
     이 매핑이 없으면 로그인은 성공해도 모든 데이터 조회가 빈 결과를 반환한다.
"""
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


def get_current_auth_id(token: str = Depends(oauth2_scheme)) -> str:
    """Authorization: Bearer <supabase_jwt> 검증 후 auth.uid()(sub)를 반환.

    users row 존재를 요구하지 않는다 — /users/setup처럼 아직 프로필이
    없는 신규 가입자도 호출해야 하는 엔드포인트는 이 의존성을 쓴다.

    Supabase 신규 프로젝트는 비대칭 키(ES256/RS256, JWKS)로 서명하고, 레거시
    프로젝트는 공유 시크릿(HS256)으로 서명한다 — JWKS 검증을 우선 시도하고,
    실패(키 없음/네트워크 오류/레거시 토큰)하면 기존 HS256 경로로 폴백한다.
    """
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

    auth_id = payload.get("sub")
    if not auth_id:
        raise _UNAUTHORIZED("토큰에 sub 클레임이 없습니다.")
    return auth_id


def get_current_user(auth_id: str = Depends(get_current_auth_id)) -> str:
    """auth_id -> users.id 매핑. 프로필(users row)이 있어야 하는 일반 엔드포인트용."""
    rows = (
        get_supabase().table("users").select("id")
        .eq("auth_id", auth_id).limit(1).execute().data
    )
    if not rows:
        raise _UNAUTHORIZED("프로필이 없는 사용자입니다. 먼저 회원가입을 완료하세요.")
    return rows[0]["id"]
