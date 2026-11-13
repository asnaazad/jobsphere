from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from mysql.connector import pooling, Error
import jwt
import datetime
import os
import re
from functools import wraps

app = Flask(__name__)
CORS(app)

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-k8s-secret")
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
ALLOWED_ROLES = {"candidate", "recruiter"}

# ==============================
# DATABASE CONNECTION POOL
# ==============================

db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = pooling.MySQLConnectionPool(
            pool_name="auth_pool",
            pool_size=5,
            pool_reset_session=True,
            host=os.getenv("DB_HOST", "jobsphere-mysql"),
            user=os.getenv("DB_USER", "jobsphereuser"),
            password=os.getenv("DB_PASSWORD", "jobpassword"),
            database=os.getenv("DB_NAME", "jobsphere")
        )

def get_db_connection():
    init_db_pool()
    return db_pool.get_connection()


# ==============================
# JWT AUTH DECORATOR
# ==============================

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
            request.current_user = payload
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token has expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401

        return f(*args, **kwargs)
    return decorated


def generate_token(user):
    payload = {
        "user_id": user["id"],
        "email": user["email"],
        "name": user["name"],
        "role": user["role"],
        "exp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=JWT_EXPIRY_HOURS)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ==============================
# ROUTES
# ==============================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "JobSphere Auth Service",
        "version": "2.0.0",
        "status": "running"
    }), 200


@app.route("/health", methods=["GET"])
def health():
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Error as e:
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 503
    finally:
        if connection and connection.is_connected():
            connection.close()


@app.route("/register", methods=["POST"])
def register():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required"}), 400

    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = (data.get("role") or "candidate").strip().lower()

    if not name or not email or not password:
        return jsonify({"error": "Name, email, and password are required"}), 400

    if not re.match(r"^[^@]+@[^@]+\.[^@]+$", email):
        return jsonify({"error": "Invalid email format"}), 400

    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    if role not in ALLOWED_ROLES:
        return jsonify({"error": f"Invalid role. Choose from: {', '.join(ALLOWED_ROLES)}"}), 400

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT id FROM users WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"error": "Email already registered"}), 409

        hashed_pw = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
            (name, email, hashed_pw, role)
        )
        connection.commit()

        user_id = cursor.lastrowid
        user = {"id": user_id, "name": name, "email": email, "role": role}
        token = generate_token(user)

        return jsonify({
            "message": "User registered successfully",
            "token": token,
            "user": user
        }), 201

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required"}), 400

    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "SELECT id, name, email, password_hash, role FROM users WHERE email = %s",
            (email,)
        )
        user = cursor.fetchone()

        if not user or not check_password_hash(user["password_hash"], password):
            return jsonify({"error": "Invalid email or password"}), 401

        safe_user = {
            "id": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"]
        }
        token = generate_token(safe_user)

        return jsonify({
            "message": "Login successful",
            "token": token,
            "user": safe_user
        }), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/me", methods=["GET"])
@token_required
def get_current_user():
    return jsonify({"user": request.current_user}), 200


@app.route("/users", methods=["GET"])
@token_required
def get_users():
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)
        cursor.execute("SELECT id, name, email, role FROM users")
        users = cursor.fetchall()
        return jsonify(users), 200
    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)