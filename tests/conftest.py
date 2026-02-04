import os
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient

# --- 1. Load Test Environment ---
# This ensures that the .env.test file is loaded for all tests
# before any other code (like main.py) is imported.
@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """
    A session-scoped fixture to load the .env.test file once for the entire
    test session. `autouse=True` means it will be automatically used without
    needing to be requested in test functions.
    """
    load_dotenv(dotenv_path=".env.test")


# --- 2. Database Cleaning Fixture ---
@pytest.fixture(scope="function")
def clean_db():
    """
    A function-scoped fixture to ensure the database is clean before each test.
    It connects to the test database, disables foreign key checks, truncates
    all tables, and then re-enables foreign key checks.
    """
    # Get DB connection details from the now-loaded test environment
    db_url = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    engine = create_engine(db_url)

    with engine.connect() as conn:
        with conn.begin(): # Start a transaction
            # Get all table names
            tables = conn.execute(text("SHOW TABLES;")).fetchall()
            table_names = [table[0] for table in tables]

            # Temporarily disable foreign key checks to allow truncation
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
            
            # Truncate all tables
            for table_name in table_names:
                conn.execute(text(f"TRUNCATE TABLE `{table_name}`;"))
            
            # Re-enable foreign key checks
            conn.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
    
    yield # This is where the test runs

    # You could add cleanup code here if needed, but truncation handles it.


# --- 3. API Client Fixture ---
@pytest.fixture(scope="function")
def client(clean_db):
    """
    A function-scoped fixture that provides a TestClient instance for each test.
    It depends on `clean_db` to ensure the database is pristine before the
    client is created and the test runs.
    """
    from main import app # Import the app inside the fixture
    with TestClient(app) as c:
        yield c
