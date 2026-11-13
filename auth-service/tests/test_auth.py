import pytest
from unittest.mock import MagicMock, patch
from werkzeug.security import generate_password_hash
import sys
import os

# Add parent directory so pytest can import app.py cleanly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_home_endpoint(client):
    """Verify the root endpoint returns service metadata."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.get_json()
    assert data["service"] == "JobSphere Auth Service"
    assert data["status"] == "running"


@patch("app.get_db_connection")
def test_health_check_success(mock_db, client):
    """Verify /health returns 200 when database connection succeeds."""
    mock_conn = MagicMock()
    mock_conn.is_connected.return_value = True
    mock_db.return_value = mock_conn

    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"


def test_register_missing_fields(client):
    """Verify /register rejects incomplete payloads with 400."""
    response = client.post("/register", json={"email": "test@example.com"})
    assert response.status_code == 400
    assert "required" in response.get_json()["error"].lower()


def test_register_short_password(client):
    """Verify /register enforces minimum 6-character password rule."""
    response = client.post("/register", json={
        "name": "Asna Azad",
        "email": "asna@example.com",
        "password": "123",
        "role": "candidate"
    })
    assert response.status_code == 400
    assert "6 characters" in response.get_json()["error"]


@patch("app.get_db_connection")
def test_register_success(mock_db, client):
    """Verify /register creates a user and returns a valid JWT token."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.is_connected.return_value = True

    # Simulate email not yet existing in DB
    mock_cursor.fetchone.return_value = None
    mock_cursor.lastrowid = 101
    mock_db.return_value = mock_conn

    response = client.post("/register", json={
        "name": "Asna Azad",
        "email": "asna@example.com",
        "password": "securepassword",
        "role": "recruiter"
    })

    assert response.status_code == 201
    data = response.get_json()
    assert "token" in data
    assert data["user"]["id"] == 101
    assert data["user"]["role"] == "recruiter"


@patch("app.get_db_connection")
def test_login_invalid_password(mock_db, client):
    """Verify /login returns 401 when password hash does not match."""
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.is_connected.return_value = True

    mock_cursor.fetchone.return_value = {
        "id": 1,
        "name": "Asna Azad",
        "email": "asna@example.com",
        "password_hash": generate_password_hash("correctpassword"),
        "role": "candidate"
    }
    mock_db.return_value = mock_conn

    response = client.post("/login", json={
        "email": "asna@example.com",
        "password": "wrongpassword"
    })

    assert response.status_code == 401
    assert "invalid" in response.get_json()["error"].lower()


def test_protected_me_route_without_token(client):
    """Verify /me rejects unauthenticated requests with 401."""
    response = client.get("/me")
    assert response.status_code == 401