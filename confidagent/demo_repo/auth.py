"""Authentication utilities for the demo Flask API.

The implementation intentionally includes a few subtle security issues that
are common in legacy Python projects.  The code is written to look like a
professional junior‑developer effort with docstrings and comments.
"""

import hashlib
import jwt
from typing import Optional

# In a real project this would be loaded from a secure config.
SECRET_KEY = "super-secret-key"
ALGORITHM = "HS256"

# Note: ``hashlib.md5`` is used here for password hashing – this is insecure.
# A modern implementation would use ``bcrypt`` or ``argon2``.

def _hash_password(password: str) -> str:
    """Return an MD5 hash of the password.

    The function pretends to be a simple password hashing helper.
    """
    return hashlib.md5(password.encode("utf-8")).hexdigest()


def register_user(username: str, password: str) -> None:
    """Register a new user in the database.

    This function stores the username and an MD5 hash of the password.
    In production you would also validate the username, enforce password
    complexity and sanitize inputs before writing to the database.
    """
    # Simulated DB write – the real code would perform an insert.
    # The lack of sanitisation makes this vulnerable to NoSQL injection.
    from database import get_user_collection
    users = get_user_collection()
    users.insert_one({"username": username, "password_hash": _hash_password(password)})


def _verify_password(stored_hash: str, password: str) -> bool:
    """Compare a stored MD5 hash with a plaintext password.
    """
    return stored_hash == _hash_password(password)


def login_user(username: str, password: str) -> str:
    """Authenticate a user and return a JWT token.

    The token is signed with ``SECRET_KEY`` but does **not** contain an
    explicit expiration claim, which means the token could be used indefinitely.
    """
    from database import get_user_collection
    users = get_user_collection()
    user = users.find_one({"username": username})
    if not user:
        raise ValueError("User not found")
    if not _verify_password(user.get("password_hash", ""), password):
        raise ValueError("Invalid credentials")
    # JWT payload intentionally missing ``exp``.
    payload = {"sub": username}
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    # ``jwt.encode`` returns ``str`` in PyJWT >=2.0.
    return token


def verify_token(token: str) -> dict:
    """Validate a JWT token and return its payload.

    ``jwt.decode`` will raise an exception if the token is invalid.
    No verification of audience or issued‑at claims is performed.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise ValueError(f"Invalid token: {exc}")
    return payload
