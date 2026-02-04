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
