import pytest
import os
from fastapi.testclient import TestClient

def test_missing_db_env_vars(monkeypatch):
    """
    Tests that the application raises a ValueError on startup if database
    environment variables are not fully set.
    """
    # Use monkeypatch to temporarily delete a required environment variable
    # We only need to remove one to trigger the error.
    monkeypatch.delenv("DB_USER", raising=False)

    # We expect a ValueError to be raised when the TestClient tries to
    # start the app, which runs the lifespan manager.
    with pytest.raises(ValueError) as excinfo:
        # Import the app object
        from main import app
        # Instantiating the TestClient will run the startup event (lifespan)
        with TestClient(app):
            pass  # We don't need to do anything, just start the app
    
    # Assert that the error message is what we expect
    assert "Database environment variables are not fully set." in str(excinfo.value)


def test_db_password_with_special_characters(monkeypatch):
    """
    Tests that a DB_PASSWORD containing URL-reserved characters (e.g. '#', '@',
    ':', '/', '%') is preserved intact in the connection URL, instead of being
    truncated or misparsed as happens when such a URL is built via raw string
    interpolation (e.g. '#' starts a URL fragment, silently dropping the rest).
    """
    special_password = "p@ss#word/with:special%chars"
    monkeypatch.setenv("DB_USER", "testuser")
    monkeypatch.setenv("DB_PASSWORD", special_password)
    monkeypatch.setenv("DB_HOST", "127.0.0.1")
    monkeypatch.setenv("DB_NAME", "testdb")
    monkeypatch.setenv("DB_PORT", "3306")

    import main as main_module
    from main import app

    with TestClient(app):
        assert main_module.engine.url.password == special_password


def test_non_ascii_password_authenticates(monkeypatch):
    """
    End-to-end regression test: a DB_PASSWORD containing a non-ASCII
    character (e.g. '£') must actually authenticate against MySQL/MariaDB.

    PyMySQL hardcodes the auth handshake password to Latin-1, which mismatches
    non-ASCII passwords set via UTF-8-based tools (e.g. DBeaver's JDBC driver),
    causing a 1045 Access Denied even with the exact correct password. This is
    why the driver was switched to mysqlclient, which performs the real MySQL
    client handshake and negotiates UTF-8-based collations like DBeaver does.
    """
    from sqlalchemy import create_engine, text

    special_password = "Str0ng£Pass!"
    username = "special_char_user"

    admin_engine = create_engine("mysql+mysqldb://root:testpassword@127.0.0.1:3306/osticket_test")
    with admin_engine.begin() as conn:
        conn.execute(text(f"DROP USER IF EXISTS '{username}'@'%'"))
        conn.execute(text(f"CREATE USER '{username}'@'%' IDENTIFIED BY :password"), {"password": special_password})
        conn.execute(text(f"GRANT SELECT ON osticket_test.* TO '{username}'@'%'"))

    try:
        monkeypatch.setenv("DB_USER", username)
        monkeypatch.setenv("DB_PASSWORD", special_password)
        monkeypatch.setenv("DB_HOST", "127.0.0.1")
        monkeypatch.setenv("DB_NAME", "osticket_test")
        monkeypatch.setenv("DB_PORT", "3306")

        from main import app

        with TestClient(app) as c:
            response = c.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok", "database": "ok"}
    finally:
        with admin_engine.begin() as conn:
            conn.execute(text(f"DROP USER IF EXISTS '{username}'@'%'"))
        admin_engine.dispose()
