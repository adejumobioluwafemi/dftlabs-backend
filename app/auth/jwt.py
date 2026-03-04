import logging
from datetime import datetime, timedelta, UTC
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger(__name__)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/admin/login")


def create_access_token(
    data: dict[str, Any],
    expires_delta: timedelta | None = None,
) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(UTC) + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    token = jwt.encode(
        payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )
    logger.debug("Access token created for sub=%s", data.get("sub"))
    return token


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        logger.warning("Token decode failed: %s", exc)
        return None


async def require_admin(
    token: Annotated[str, Depends(oauth2_scheme)],
) -> dict[str, Any]:
    payload = decode_token(token)
    if not payload or payload.get("role") != "admin":
        logger.warning("Unauthorized admin access attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


# Reusable type alias — use in every router that needs admin auth
AdminDep = Annotated[dict[str, Any], Depends(require_admin)]