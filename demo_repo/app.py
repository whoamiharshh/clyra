"""Flask API for user authentication.

Contains a few subtle bugs that are common in legacy code bases.
"""

from flask import Flask, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# NOTE: The Limiter initialization below uses the legacy signature.
# The modern API expects `limiter = Limiter(key_func=get_remote_address, app=app)`.
# Keeping the old style for demonstration of a hidden bug.
app = Flask(__name__)
limiter = Limiter(app, key_func=get_remote_address)

# Imported modules from the same package
from auth import register_user, login_user, verify_token

@app.route('/register', methods=['POST'])
@limiter.limit("100/day")  # The decorator works but the string syntax is outdated for newer Flask‑Limiter versions.
def register():
    """Register a new user.

    Expected JSON payload:
        {"username": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Missing fields"}), 400
    try:
        register_user(username, password)
    except Exception as e:
        # Generic error handling – real code would be more specific.
        return jsonify({"error": str(e)}), 500
    return jsonify({"message": "User registered"}), 201


@app.route('/login', methods=['POST'])
@limiter.limit("200/hour")
def login():
    """Authenticate a user and return a JWT token.

    Expected JSON payload:
        {"username": "...", "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    username = data.get('username')
    password = data.get('password')
    if not username or not password:
        return jsonify({"error": "Missing fields"}), 400
    try:
        token = login_user(username, password)
    except Exception as e:
        return jsonify({"error": str(e)}), 401
    # The token is returned without explicit expiration handling – the JWT library defaults may vary.
    return jsonify({"access_token": token}), 200


@app.route('/protected', methods=['GET'])
@limiter.limit("500/day")
def protected():
    """A simple protected endpoint that requires a valid JWT token.
    """
    auth_header = request.headers.get('Authorization', '')
    token = auth_header.replace('Bearer ', '')
    if not token:
        return jsonify({"error": "Missing token"}), 401
    try:
        payload = verify_token(token)
    except Exception as e:
        return jsonify({"error": str(e)}), 401
    return jsonify({"message": f"Hello, {payload.get('sub')}!"}), 200


# NOTE: There is no dedicated error handler for ``RateLimitExceeded`` exceptions.
# Flask‑Limiter raises a ``429 Too Many Requests`` response internally, but a custom
# handler would allow returning a JSON body instead of the default HTML page.

if __name__ == '__main__':
    # Running with debug=True in development – remember to disable in production.
    app.run(host='0.0.0.0', port=5000, debug=True)
