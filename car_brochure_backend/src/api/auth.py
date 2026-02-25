import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def _get_admin_credentials() -> tuple[str, str]:
    """
    Resolve admin credentials from environment.

    Required:
    - ADMIN_USERNAME
    - ADMIN_PASSWORD
    """
    username = os.getenv("ADMIN_USERNAME")
    password = os.getenv("ADMIN_PASSWORD")
    if not username or not password:
        raise RuntimeError(
            "Admin credentials missing. Set ADMIN_USERNAME and ADMIN_PASSWORD in the environment."
        )
    return username, password


# PUBLIC_INTERFACE
def require_admin(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """FastAPI dependency enforcing HTTP Basic auth for admin endpoints."""
    expected_user, expected_pass = _get_admin_credentials()

    user_ok = secrets.compare_digest(credentials.username, expected_user)
    pass_ok = secrets.compare_digest(credentials.password, expected_pass)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username
