from flask import Flask, request, jsonify
from flask_cors import CORS
from mysql.connector import pooling, Error
import jwt
import os
from functools import wraps

app = Flask(__name__)
CORS(app)

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-k8s-secret")
ALLOWED_JOB_TYPES = {"Full-Time", "Part-Time", "Internship", "Contract", "Remote"}

# ==============================
# DATABASE CONNECTION POOL
# ==============================

db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = pooling.MySQLConnectionPool(
            pool_name="job_pool",
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
# JWT & RBAC DECORATORS
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


def role_required(*allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user_role = getattr(request, "current_user", {}).get("role")
            if user_role not in allowed_roles:
                return jsonify({"error": f"Access forbidden: requires role {', '.join(allowed_roles)}"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


# ==============================
# ROUTES
# ==============================

@app.route("/", methods=["GET"])
def home():
    return jsonify({
        "service": "JobSphere Job Service",
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


@app.route("/jobs", methods=["GET"])
def get_jobs():
    search = (request.args.get("search") or "").strip()
    job_type = (request.args.get("type") or "").strip()
    location = (request.args.get("location") or "").strip()

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = "SELECT * FROM jobs WHERE 1=1"
        params = []

        if search:
            query += " AND (title LIKE %s OR company LIKE %s)"
            like_term = f"%{search}%"
            params.extend([like_term, like_term])

        if job_type:
            query += " AND type = %s"
            params.append(job_type)

        if location:
            query += " AND location LIKE %s"
            params.append(f"%{location}%")

        query += " ORDER BY id DESC"

        cursor.execute(query, tuple(params))
        jobs = cursor.fetchall()
        return jsonify(jobs), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/jobs/<int:job_id>", methods=["GET"])
def get_job(job_id):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        job = cursor.fetchone()

        if not job:
            return jsonify({"error": "Job not found"}), 404

        return jsonify(job), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/jobs", methods=["POST"])
@token_required
@role_required("recruiter")
def create_job():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required"}), 400

    title = (data.get("title") or "").strip()
    company = (data.get("company") or "").strip()
    location = (data.get("location") or "Remote").strip()
    job_type = (data.get("type") or "Full-Time").strip()

    if not title or not company:
        return jsonify({"error": "Title and company are required"}), 400

    if job_type not in ALLOWED_JOB_TYPES:
        return jsonify({
            "error": f"Invalid job type. Allowed values: {', '.join(sorted(ALLOWED_JOB_TYPES))}"
        }), 400

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute(
            "INSERT INTO jobs (title, company, location, type) VALUES (%s, %s, %s, %s)",
            (title, company, location, job_type)
        )
        connection.commit()

        job_id = cursor.lastrowid
        cursor.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        new_job = cursor.fetchone()

        return jsonify({
            "message": "Job created successfully",
            "job": new_job
        }), 201

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/jobs/<int:job_id>", methods=["DELETE"])
@token_required
@role_required("recruiter")
def delete_job(job_id):
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT id FROM jobs WHERE id = %s", (job_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Job not found"}), 404

        cursor.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
        connection.commit()

        return jsonify({
            "message": "Job deleted successfully",
            "job_id": job_id
        }), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)