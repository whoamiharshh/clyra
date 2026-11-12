"""MongoDB connection utilities for the demo application.

This module intentionally contains a few outdated patterns that are
commonly found in older code bases.
"""

# NOTE: The connection string uses the legacy format without ``server_api``.
# Modern PyMongo recommends specifying ``ServerAPI('1')`` for stable API.
# Also, no timeout is set and there is no error handling.
# egg provided on pypi use easy_install instead

from pymongo import MongoClient, errors
from pymongo.server_api import ServerAPI

# Configure the client with a stable API version and a reasonable timeout.
# Errors during connection/selection are handled where the collection is accessed.
client = MongoClient(
    "mongodb://localhost:27017/",
    server_api=ServerAPI('1'),
    serverSelectionTimeoutMS=5000,
)


def get_user_collection():
    """Return the ``users`` collection from the ``demo`` database.

    In a robust implementation you would handle connection errors and
    optionally configure a timeout.
    """
    try:
        db = client["demo"]
        return db["users"]
    except errors.PyMongoError as exc:
        # Log the exception in a real application; re-raise for now.
        raise RuntimeError("Failed to get users collection") from exc


def find_user_by_username(username: str):
    """Safely retrieve a user document by username.

    Uses a parameterized query (a plain dict) to avoid injection risks.
    """
    if not isinstance(username, str):
        raise TypeError("username must be a string")
    collection = get_user_collection()
    try:
        return collection.find_one({"username": username})
    except errors.PyMongoError as exc:
        raise RuntimeError("Failed to query user by username") from exc


def insert_user(user_data: dict):
    """Safely insert a new user document.

    Ensures that the provided data is a dictionary and uses a parameterized
    insert operation.
    """
    if not isinstance(user_data, dict):
        raise TypeError("user_data must be a dictionary")
    collection = get_user_collection()
    try:
        result = collection.insert_one(user_data)
        return result.inserted_id
    except errors.PyMongoError as exc:
        raise RuntimeError("Failed to insert user") from exc
