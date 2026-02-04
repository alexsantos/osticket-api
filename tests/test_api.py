from fastapi.testclient import TestClient
from sqlalchemy import text, exc
import pytest
import io
from datetime import datetime, timedelta

# The `client` fixture is automatically injected by pytest from conftest.py
# and it ensures the database is clean for every test.


def test_health_check(client: TestClient):
    """
    Tests that the /health endpoint is working and connected to the database.
    """
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_check_db_error(client: TestClient, monkeypatch):
    """
    Tests that the /health endpoint returns a 503 error if the database
    connection fails.
    """
    # --- Setup: Mock the engine's connect method to raise an error ---
    from main import engine

    def mock_connect_error():
        raise exc.OperationalError("Connection failed", {}, "Mocked error")

    monkeypatch.setattr(engine, "connect", mock_connect_error)

    response = client.get("/health")
    assert response.status_code == 503
    json_response = response.json()
    assert json_response["detail"]["status"] == "error"
    assert json_response["detail"]["database"] == "error"
    assert "Mocked error" in json_response["detail"]["details"]


def test_security_no_api_key(client: TestClient):
    """
    Tests that an endpoint protected by `verify_token` returns 422 if the header is missing.
    """
    response = client.get("/topics")
    # FastAPI's default behavior for a missing required header is 422 Unprocessable Entity
    assert response.status_code == 422


def test_security_invalid_api_key(client: TestClient):
    """
    Tests that an endpoint returns 401 Unauthorized for an invalid API key.
    """
    headers = {"X-API-Key": "this-is-a-fake-key"}
    response = client.get("/topics", headers=headers)
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid API Key"}


def test_security_inactive_api_key(client: TestClient):
    """
    Tests that an endpoint returns 403 Forbidden for an inactive API key.
    """
    # --- Setup: Create an inactive API key ---
    from main import engine
    api_key = "my-inactive-key"
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (0, 'testclient', :apikey, NOW(), NOW())"),
                {"apikey": api_key}
            )

    headers = {"X-API-Key": api_key}
    response = client.get("/topics", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "API Key is not active"}


def test_security_ip_not_allowed(client: TestClient):
    """
    Tests that an endpoint returns 403 Forbidden for a non-whitelisted IP address.
    """
    # --- Setup: Create an API key with a specific IP whitelist ---
    from main import engine
    api_key = "my-ip-restricted-key"
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(
                text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, '192.168.1.1', :apikey, NOW(), NOW())"),
                {"apikey": api_key}
            )

    headers = {"X-API-Key": api_key}
    # The TestClient's IP is 'testclient', which does not match '192.168.1.1'
    response = client.get("/topics", headers=headers)
    assert response.status_code == 403
    assert response.json() == {"detail": "IP address not allowed"}


def test_list_help_topics(client: TestClient):
    """
    Tests that the /topics endpoint returns only active help topics.
    """
    # --- Setup: Create help topics and a valid API key ---
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            # Active and public topic
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (1, 1, 0, 'Active Public Topic', NOW(), NOW(), 1)"))
            # Active but not public topic
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (2, 0, 0, 'Active Private Topic', NOW(), NOW(), 1)"))
            # Inactive topic
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (3, 1, 0, 'Inactive Topic', NOW(), NOW(), 0)"))
            
            api_key = "topics-test-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/topics", headers=headers)

    assert response.status_code == 200
    topics = response.json()
    
    # The endpoint should only return active topics
    assert len(topics) == 2
    
    topic_ids = {t["topic_id"] for t in topics}
    assert topic_ids == {1, 2}
    assert 3 not in topic_ids


def test_list_departments(client: TestClient):
    """
    Tests that the /departments endpoint returns all departments.
    """
    # --- Setup: Create departments and a valid API key ---
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Support', '', 1, NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (2, 'Sales', '', 1, NOW(), NOW())"))
            
            api_key = "dept-test-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/departments", headers=headers)

    assert response.status_code == 200
    departments = response.json()
    
    assert len(departments) == 2
    dept_names = {d["name"] for d in departments}
    assert dept_names == {"Support", "Sales"}


def test_list_statuses(client: TestClient):
    """
    Tests that the /statuses endpoint returns all ticket statuses.
    """
    # --- Setup: Create statuses and a valid API key ---
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (2, 'Resolved', 'closed', 3, 0, '{}', NOW(), NOW())"))
            
            api_key = "status-test-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/statuses", headers=headers)

    assert response.status_code == 200
    statuses = response.json()
    
    assert len(statuses) == 2
    status_names = {s["name"] for s in statuses}
    assert status_names == {"Open", "Resolved"}


def test_list_users_pagination(client: TestClient):
    """
    Tests listing users with pagination and filtering.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            # Create 3 users with distinct creation times
            now = datetime.now()
            user_ids = []
            for i in range(3):
                created_time = now - timedelta(seconds=i)
                user_res = conn.execute(text(f"INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'User {3-i}', :created_time, :created_time, 0)"), {"created_time": created_time})
                user_id = user_res.lastrowid
                user_ids.append(user_id)
                email_res = conn.execute(text(f"INSERT INTO ost_user_email (user_id, address) VALUES (:user_id, 'user{3-i}@example.com')"), {"user_id": user_id})
                conn.execute(text("UPDATE ost_user SET default_email_id = :email_id WHERE id = :user_id"), {"email_id": email_res.lastrowid, "user_id": user_id})
            
            api_key = "user-list-test-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    
    # Test first page (limit=2, offset=0)
    response = client.get("/users?limit=2&offset=0", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 2
    assert data["items"][0]["name"] == "User 3" # Ordered by created DESC
    assert data["items"][1]["name"] == "User 2"
    assert data["previous"] is None
    assert "offset=2" in data["next"]

    # Test second page (limit=2, offset=2)
    response = client.get(data["next"], headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert len(data["items"]) == 1
    assert data["items"][0]["name"] == "User 1"
    assert "offset=0" in data["previous"]
    assert data["next"] is None

    # Test filtering by email
    response = client.get("/users?email=user1@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "User 1"


def test_get_user(client: TestClient):
    """
    Tests retrieving a single user by their ID.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            user_res = conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Specific User', NOW(), NOW(), 0)"))
            user_id = user_res.lastrowid
            email_res = conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:user_id, 'specific@example.com')"), {"user_id": user_id})
            conn.execute(text("UPDATE ost_user SET default_email_id = :email_id WHERE id = :user_id"), {"email_id": email_res.lastrowid, "user_id": user_id})

            api_key = "user-get-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get(f"/users/{user_id}", headers=headers)
    
    assert response.status_code == 200
    user_data = response.json()
    assert user_data["id"] == user_id
    assert user_data["name"] == "Specific User"


def test_get_user_not_found(client: TestClient):
    """
    Tests that retrieving a non-existent user returns a 404 error.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            api_key = "user-not-found-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/users/99999", headers=headers)
    
    assert response.status_code == 404
    assert response.json() == {"detail": "User not found"}


def test_list_tickets_pagination(client: TestClient):
    """
    Tests listing tickets with pagination and filtering.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            # Dependencies
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Support', '', 1, NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (2, 'Sales', '', 1, NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (1, 1, 0, 'General', NOW(), NOW(), 1)"))
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (2, 1, 0, 'Inquiries', NOW(), NOW(), 1)")) # New topic for filtering
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (3, 'Closed', 'closed', 3, 0, '{}', NOW(), NOW())"))
            
            # Users
            user_ids = []
            for i in range(1, 6): # Create 5 users
                user_res = conn.execute(text(f"INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Ticket User {i}', NOW(), NOW(), 0)"))
                user_id = user_res.lastrowid
                user_ids.append(user_id)
                email_res = conn.execute(text(f"INSERT INTO ost_user_email (user_id, address) VALUES (:user_id, 'ticketuser{i}@example.com')"), {"user_id": user_id})
                conn.execute(text("UPDATE ost_user SET default_email_id = :email_id WHERE id = :user_id"), {"email_id": email_res.lastrowid, "user_id": user_id})

            # Tickets (ordered by creation time, so user_ids[4] will be ticket 5, etc.)
            now = datetime.now()
            conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('105', :user_id, 1, 1, 1, :created_time, :created_time)"), {"user_id": user_ids[4], "created_time": now - timedelta(seconds=4)})
            conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('104', :user_id, 2, 1, 1, :created_time, :created_time)"), {"user_id": user_ids[3], "created_time": now - timedelta(seconds=3)})
            conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('103', :user_id, 1, 3, 3, :created_time, :created_time)"), {"user_id": user_ids[2], "created_time": now - timedelta(seconds=2)}) # Topic 3
            conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('102', :user_id, 2, 1, 1, :created_time, :created_time)"), {"user_id": user_ids[1], "created_time": now - timedelta(seconds=1)})
            conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('101', :user_id, 1, 2, 3, :created_time, :created_time)"), {"user_id": user_ids[0], "created_time": now}) # Topic 2

            api_key = "ticket-list-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}

    # Test first page (limit=2, offset=0)
    response = client.get("/tickets?limit=2&offset=0", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["number"] == "101" # Now ordered by explicit created time DESC
    assert data["items"][1]["number"] == "102"
    assert data["previous"] is None
    assert "offset=2" in data["next"]

    # Test second page (limit=2, offset=2)
    response = client.get(data["next"], headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 2
    assert data["items"][0]["number"] == "103"
    assert data["items"][1]["number"] == "104"
    assert "offset=0" in data["previous"]
    assert "offset=4" in data["next"]

    # Test last page (limit=2, offset=4)
    response = client.get(data["next"], headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 5
    assert len(data["items"]) == 1
    assert data["items"][0]["number"] == "105"
    assert "offset=2" in data["previous"]
    assert data["next"] is None

    # Test filtering by status
    response = client.get("/tickets?status_id=3", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    assert data["items"][0]["number"] == "101" # Newest closed ticket
    assert data["items"][1]["number"] == "103" # Older closed ticket

    # Test filtering by email
    response = client.get(f"/tickets?email=ticketuser{user_ids[0]}@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["owner_name"] == f"Ticket User {user_ids[0]}"

    # Test filtering by topic_id
    response = client.get("/tickets?topic_id=2", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["number"] == "101"

    # Test filtering by dept_id
    response = client.get("/tickets?dept_id=2", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["items"][0]["number"] == "102"
    assert data["items"][1]["number"] == "104"


def test_create_and_get_ticket(client: TestClient):
    """
    An end-to-end integration test for creating and then retrieving a ticket.
    This verifies database writes and reads.
    """
    # --- Setup: Create all necessary prerequisite data for a ticket ---
    from main import engine
    user_id = None
    api_key = "my-secret-test-key"
    with engine.connect() as conn:
        with conn.begin(): # Start a transaction
            # Create prerequisite records that a ticket depends on
            conn.execute(text(
                "INSERT INTO ost_department (id, name, signature, ispublic, created, updated) "
                "VALUES (1, 'Test Department', 'Test Signature', 1, NOW(), NOW())"
            ))
            conn.execute(text(
                "INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated) "
                "VALUES (1, 1, 1, 'Test Topic', NOW(), NOW())"
            ))
            conn.execute(text(
                "INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) "
                "VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"
            ))
            conn.execute(text(
                "INSERT INTO ost_sequence (name, next, updated) VALUES ('ticket_number', 0, NOW())"
            ))

            # Create the user who will own the ticket
            user_res = conn.execute(
                text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Test User', NOW(), NOW(), 0)")
            )
            user_id = user_res.lastrowid

            email_res = conn.execute(
                text("INSERT INTO ost_user_email (user_id, address) VALUES (:user_id, 'testuser@example.com')"),
                {"user_id": user_id}
            )
            email_id = email_res.lastrowid

            conn.execute(
                text("UPDATE ost_user SET default_email_id = :email_id WHERE id = :user_id"),
                {"email_id": email_id, "user_id": user_id}
            )
            
            # Create an API key and whitelist the test client's IP address
            conn.execute(
                text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"),
                {"apikey": api_key}
            )
        # The transaction is automatically committed here

    headers = {"X-API-Key": api_key}

    # 1. Create a new ticket
    ticket_data = {
        "user_id": user_id,
        "subject": "Test Ticket from Integration Test",
        "message": "This is the body of the test ticket.",
        "topic_id": 1,
        "dept_id": 1
    }
    create_response = client.post("/tickets", headers=headers, json=ticket_data)
    assert create_response.status_code == 200
    response_data = create_response.json()
    assert "ticket_id" in response_data
    assert "number" in response_data
    new_ticket_id = response_data["ticket_id"]

    # 2. Retrieve the ticket we just created
    get_response = client.get(f"/tickets/{new_ticket_id}", headers=headers)
    assert get_response.status_code == 200
    ticket_details = get_response.json()
    assert ticket_details["ticket_id"] == new_ticket_id
    assert ticket_details["owner_name"] == "Test User"
    assert ticket_details["email"] == "testuser@example.com"
    assert ticket_details["number"] == "1"


def test_create_ticket_invalid_user(client: TestClient):
    """
    Tests that creating a ticket with a non-existent user ID fails.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            # Setup all prerequisites except the user
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Test Dept', '', 1, NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated) VALUES (1, 1, 1, 'Test Topic', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_sequence (name, next, updated) VALUES ('ticket_number', 0, NOW())"))
            
            api_key = "invalid-user-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    ticket_data = {
        "user_id": 99999,  # Non-existent user
        "subject": "Test with invalid user",
        "message": "This should fail.",
        "topic_id": 1,
        "dept_id": 1
    }
    
    response = client.post("/tickets", headers=headers, json=ticket_data)
    assert response.status_code == 400
    assert "does not exist" in response.json()["detail"]


def test_get_ticket_not_found(client: TestClient):
    """
    Tests that retrieving a non-existent ticket returns a 404 error.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            api_key = "ticket-not-found-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/tickets/99999", headers=headers)
    
    assert response.status_code == 404
    assert response.json() == {"detail": "Ticket not found"}


def test_add_attachment_to_ticket(client: TestClient):
    """
    Tests that a file can be attached to an existing ticket.
    """
    # --- Setup: Create a ticket to attach a file to ---
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            # Minimal setup for a ticket to exist
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Test Dept', '', 1, NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated) VALUES (1, 1, 1, 'Test Topic', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_sequence (name, next, updated) VALUES ('ticket_number', 0, NOW())"))
            
            user_res = conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Attachment User', NOW(), NOW(), 0)"))
            user_id = user_res.lastrowid
            email_res = conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:user_id, 'attachmentuser@example.com')"), {"user_id": user_id})
            conn.execute(text("UPDATE ost_user SET default_email_id = :email_id WHERE id = :user_id"), {"email_id": email_res.lastrowid, "user_id": user_id})

            ticket_res = conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('1', :user_id, 1, 1, 1, NOW(), NOW())"), {"user_id": user_id})
            ticket_id = ticket_res.lastrowid
            
            thread_res = conn.execute(text("INSERT INTO ost_thread (object_id, object_type, created) VALUES (:ticket_id, 'T', NOW())"), {"ticket_id": ticket_id})
            thread_id = thread_res.lastrowid

            # Create a thread entry to attach the file to
            conn.execute(text("INSERT INTO ost_thread_entry (thread_id, poster, body, created, updated) VALUES (:thread_id, 'Test Poster', 'Initial message', NOW(), NOW())"), {"thread_id": thread_id})

            api_key = "attachment-test-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    
    # Create a dummy file in memory
    file_content = b"This is a test attachment."
    file_wrapper = io.BytesIO(file_content)
    file_wrapper.name = "test_attachment.txt"

    # 2. Attach the file
    response = client.post(
        f"/tickets/{ticket_id}/attach",
        headers=headers,
        files={"file": (file_wrapper.name, file_wrapper, "text/plain")}
    )

    # 3. Assert the response
    assert response.status_code == 200
    response_data = response.json()
    assert "file_id" in response_data
    file_id = response_data["file_id"]

    # 4. Verify the attachment in the database (optional but good practice)
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT COUNT(*) FROM ost_attachment WHERE file_id = :file_id AND object_id IN (SELECT id FROM ost_thread_entry WHERE thread_id = :thread_id)"),
            {"file_id": file_id, "thread_id": thread_id}
        ).scalar()
        assert result == 1


def test_add_attachment_ticket_not_found(client: TestClient):
    """
    Tests that adding an attachment to a non-existent ticket fails.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            api_key = "attachment-fail-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    file_content = b"This is a test attachment."
    file_wrapper = io.BytesIO(file_content)
    file_wrapper.name = "test_attachment.txt"

    response = client.post(
        "/tickets/99999/attach",
        headers=headers,
        files={"file": (file_wrapper.name, file_wrapper, "text/plain")}
    )
    
    assert response.status_code == 500 # Should fail due to integrity error
    assert "Internal Server Error" in response.text


def test_add_attachment_no_file(client: TestClient):
    """
    Tests that the endpoint returns 422 if no file is provided.
    """
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            api_key = "no-file-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.post("/tickets/1/attach", headers=headers)
    
    assert response.status_code == 422


def test_close_ticket(client: TestClient):
    """
    Tests that a ticket can be closed.
    """
    # --- Setup: Create a ticket to close ---
    from main import engine
    with engine.connect() as conn:
        with conn.begin():
            # Minimal setup for a ticket to exist
            conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Test Dept', '', 1, NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated) VALUES (1, 1, 1, 'Test Topic', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (3, 'Closed', 'closed', 3, 0, '{}', NOW(), NOW())"))
            conn.execute(text("INSERT INTO ost_sequence (name, next, updated) VALUES ('ticket_number', 0, NOW())"))
            
            user_res = conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Close User', NOW(), NOW(), 0)"))
            user_id = user_res.lastrowid
            email_res = conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:user_id, 'closeuser@example.com')"), {"user_id": user_id})
            email_id = email_res.lastrowid
            conn.execute(text("UPDATE ost_user SET default_email_id = :email_id WHERE id = :user_id"), {"email_id": email_id, "user_id": user_id})

            ticket_res = conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('1', :user_id, 1, 1, 1, NOW(), NOW())"), {"user_id": user_id})
            ticket_id = ticket_res.lastrowid
            
            api_key = "close-test-key"
            conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    
    # 2. Close the ticket
    response = client.put(f"/tickets/{ticket_id}/close", headers=headers)

    # 3. Assert the response
    assert response.status_code == 200
    assert response.json() == {"status": "closed"}

    # 4. Verify the ticket status in the database
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT status_id FROM ost_ticket WHERE ticket_id = :ticket_id"),
            {"ticket_id": ticket_id}
        ).scalar()
        assert result == 3
