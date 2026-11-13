from flask import Flask, request, jsonify
from flask_cors import CORS
from mysql.connector import pooling, Error
import jwt
import os
from functools import wraps

app = Flask(__name__)
CORS(app)

JWT_SECRET = os.getenv("JWT_SECRET", "change-this-in-k8s-secret")
ALLOWED_STATUSES = {
    "Applied",
    "Under Review",
    "Shortlisted",
    "Interview Scheduled",
    "Rejected",
    "Hired"
}

# ==============================
# DATABASE CONNECTION POOL
# ==============================

db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = pooling.MySQLConnectionPool(
            pool_name="application_pool",
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
        "service": "JobSphere Application Service",
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


@app.route("/applications", methods=["GET"])
@token_required
def get_applications():
    user = request.current_user
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        base_query = """
            SELECT
                applications.id,
                applications.job_id,
                applications.candidate_id,
                applications.status,
                jobs.title AS job_title,
                jobs.company,
                jobs.location,
                users.name AS candidate_name,
                users.email AS candidate_email
            FROM applications
            JOIN jobs ON applications.job_id = jobs.id
            JOIN users ON applications.candidate_id = users.id
        """

        if user.get("role") == "candidate":
            query = base_query + " WHERE applications.candidate_id = %s ORDER BY applications.id DESC"
            cursor.execute(query, (user["user_id"],))
        else:
            query = base_query + " ORDER BY applications.id DESC"
            cursor.execute(query)

        applications = cursor.fetchall()
        return jsonify(applications), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/applications/<int:application_id>", methods=["GET"])
@token_required
def get_application(application_id):
    user = request.current_user
    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        query = """
            SELECT
                applications.id,
                applications.job_id,
                applications.candidate_id,
                applications.status,
                jobs.title AS job_title,
                jobs.company,
                jobs.location,
                users.name AS candidate_name,
                users.email AS candidate_email
            FROM applications
            JOIN jobs ON applications.job_id = jobs.id
            JOIN users ON applications.candidate_id = users.id
            WHERE applications.id = %s
        """
        cursor.execute(query, (application_id,))
        application = cursor.fetchone()

        if not application:
            return jsonify({"error": "Application not found"}), 404

        if user.get("role") == "candidate" and application["candidate_id"] != user["user_id"]:
            return jsonify({"error": "Access forbidden"}), 403

        return jsonify(application), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/applications", methods=["POST"])
@token_required
@role_required("candidate")
def create_application():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required"}), 400

    job_id = data.get("job_id")
    candidate_id = request.current_user["user_id"]

    if not job_id:
        return jsonify({"error": "job_id is required"}), 400

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT id, title FROM jobs WHERE id = %s", (job_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Job not found"}), 404

        cursor.execute(
            "SELECT id FROM applications WHERE job_id = %s AND candidate_id = %s",
            (job_id, candidate_id)
        )
        if cursor.fetchone():
            return jsonify({"error": "You have already applied for this job"}), 409

        cursor.execute(
            "INSERT INTO applications (job_id, candidate_id, status) VALUES (%s, %s, %s)",
            (job_id, candidate_id, "Applied")
        )
        connection.commit()

        return jsonify({
            "message": "Application submitted successfully",
            "application_id": cursor.lastrowid,
            "status": "Applied"
        }), 201

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


@app.route("/applications/<int:application_id>", methods=["PUT"])
@token_required
@role_required("recruiter")
def update_application(application_id):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "JSON request body is required"}), 400

    status = (data.get("status") or "").strip()
    if status not in ALLOWED_STATUSES:
        return jsonify({
            "error": f"Invalid status. Allowed values: {', '.join(sorted(ALLOWED_STATUSES))}"
        }), 400

    connection = None
    try:
        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        cursor.execute("SELECT id FROM applications WHERE id = %s", (application_id,))
        if not cursor.fetchone():
            return jsonify({"error": "Application not found"}), 404

        cursor.execute(
            "UPDATE applications SET status = %s WHERE id = %s",
            (status, application_id)
        )
        connection.commit()

        return jsonify({
            "message": "Application status updated successfully",
            "application_id": application_id,
            "status": status
        }), 200

    except Error as e:
        return jsonify({"error": "Database error", "details": str(e)}), 500
    finally:
        if connection and connection.is_connected():
            cursor.close()
            connection.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)