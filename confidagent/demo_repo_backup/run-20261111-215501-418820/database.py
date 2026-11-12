"""MongoDB connection utilities for the demo application.

This module intentionally contains a few outdated patterns that are
commonly found in older code bases.
"""

from pymongo import MongoClient

# NOTE: The connection string uses the legacy format without ``server_api``.
# Modern PyMongo recommends specifying ``ServerAPI('1')`` for stable API.
# Also, no timeout is set and there is no error handling.

client = MongoClient("mongodb://localhost:27017/")

def get_user_collection():
    """Return the ``users`` collection from the ``demo`` database.

    In a robust implementation you would handle connection errors and
    optionally configure a timeout.
    """
    db = client["demo"]
    return db["users"]
