"""Demo authentication module."""

import os
import bcrypt
from typing import Tuple

# Number of bcrypt rounds can be configured via environment; default is 12.
BCRYPT_ROUNDS = int(os.getenv("BCRYPT_ROUNDS", "12"))


def hash_password(password: str) -> bytes:
    """
    Hash a plaintext password using bcrypt.
    Returns the full bcrypt hash (including salt) as bytes.
    """
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    return bcrypt.hashpw(password_bytes, salt)


def verify_password(password: str, hashed: bytes) -> bool:
    """
    Verify a plaintext password against a stored bcrypt hash.
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed)


def register_user(db, username: str, password: str) -> Tuple[bool, str]:
    """
    Create a new user with a securely hashed password.
    Returns (success, message).
    """
    if db.get_user_by_username(username):
        return False, "Username already exists."

    password_hash = hash_password(password)
    db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, password_hash),
    )
    return True, "User registered successfully."


def authenticate_user(db, username: str, password: str) -> bool:
    """
    Authenticate a user by verifying the supplied password.
    Returns True on success, False otherwise.
    """
    user = db.get_user_by_username(username)
    if not user:
        return False

    _, _, stored_hash = user
    return verify_password(password, stored_hash)
