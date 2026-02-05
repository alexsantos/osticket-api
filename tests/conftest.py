import os
import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from fastapi.testclient import TestClient

# Load .env.test at the very beginning of the session
load_dotenv(dotenv_path=".env.test")

@pytest.fixture(scope="session")
def db_engine():
    """
    Creates a single, session-scoped database engine for all tests.
    """
    db_url = f"mysql+pymysql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    engine = create_engine(db_url)
    yield engine
    engine.dispose()

@pytest.fixture(scope="function")
def db_conn(db_engine):
    """
    Provides a database connection for a test function and handles cleanup.
    The test function is responsible for its own transaction management.
    """
    connection = db_engine.connect()
    yield connection  # The test runs here, using this connection

    # --- Teardown: Clean the database after each test is complete ---
    # This runs after the test function has finished
    transaction = connection.begin()
    try:
        tables = connection.execute(text("SHOW TABLES;")).fetchall()
        table_names = [table[0] for table in tables]
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 0;"))
        for table_name in table_names:
            connection.execute(text(f"TRUNCATE TABLE `{table_name}`;"))
        connection.execute(text("SET FOREIGN_KEY_CHECKS = 1;"))
        transaction.commit()
    except Exception:
        transaction.rollback()
        raise
    finally:
        connection.close()

@pytest.fixture(scope="function")
def client(db_engine, monkeypatch):
    """
    Provides a TestClient that is configured to use the same database engine
    as the test fixtures. This is the key to solving test isolation issues.
    """
    from main import app
    import main as main_module

    # Monkeypatch the engine used by the app to be the same as the test engine
    monkeypatch.setattr(main_module, "engine", db_engine)

    with TestClient(app) as c:
        yield c
