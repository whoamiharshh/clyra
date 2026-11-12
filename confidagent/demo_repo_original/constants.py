"""HTTP status codes and standard API error messages."""

HTTP_STATUS_OK = 200
HTTP_STATUS_CREATED = 201
HTTP_STATUS_BAD_REQUEST = 400
HTTP_STATUS_NOT_FOUND = 404
HTTP_STATUS_TOO_MANY_REQUESTS = 429
HTTP_STATUS_SERVER_ERROR = 500

ERROR_MSG_INVALID_INPUT = "Supplied request payload is malformed or invalid."
ERROR_MSG_ITEM_NOT_FOUND = "The requested resource could not be located."
ERROR_MSG_RATE_LIMIT = "Rate limit quota exceeded. Please retry later."
ERROR_MSG_INTERNAL = "An unexpected server error occurred during processing."


def get_status_description(code: int) -> str:
    """Return a brief descriptive string for standard status codes."""
    descriptions = {
        200: "Success",
        201: "Created",
        400: "Bad Request",
        404: "Not Found",
        429: "Too Many Requests",
        500: "Internal Error",
    }
    return descriptions.get(code, "Unknown Status")
