from fastapi.testclient import TestClient
from sqlalchemy import text, exc
import io
from datetime import datetime, timedelta

from sqlalchemy.engine.base import Engine, Connection


# The `client` and `db_conn` fixtures are automatically injected by pytest from conftest.py.


def test_health_check(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_check_db_error(client: TestClient, monkeypatch):
    from main import engine
    def mock_connect_error():
        raise exc.OperationalError("Connection failed", {}, "Mocked error")
    monkeypatch.setattr(engine, "connect", mock_connect_error)
    response = client.get("/health")
    assert response.status_code == 503
    assert "Mocked error" in response.json()["detail"]["details"]


def test_security_no_api_key(client: TestClient):
    response = client.get("/topics")
    assert response.status_code == 422


def test_security_invalid_api_key(client: TestClient):
    headers = {"X-API-Key": "this-is-a-fake-key"}
    response = client.get("/topics", headers=headers)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid API Key"


def test_security_inactive_api_key(client: TestClient, db_conn):
    with db_conn.begin():
        api_key = "my-inactive-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (0, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})
    
    headers = {"X-API-Key": api_key}
    response = client.get("/topics", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "API Key is not active"


def test_security_ip_not_allowed(client: TestClient, db_conn):
    with db_conn.begin():
        api_key = "my-ip-restricted-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, '192.168.1.1', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/topics", headers=headers)
    assert response.status_code == 403
    assert response.json()["detail"] == "IP address not allowed"


def test_list_help_topics(client: TestClient, db_conn):
    with db_conn.begin():
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (1, 1, 0, 'Active Public Topic', NOW(), NOW(), 1)"))
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (2, 0, 0, 'Active Private Topic', NOW(), NOW(), 1)"))
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (3, 1, 0, 'Inactive Topic', NOW(), NOW(), 0)"))
        api_key = "topics-test-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/topics", headers=headers)
    assert response.status_code == 200
    topics = response.json()
    assert len(topics) == 2
    assert {t["topic_id"] for t in topics} == {1, 2}


def test_list_departments(client: TestClient, db_conn):
    with db_conn.begin():
        db_conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Support', '', 1, NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (2, 'Sales', '', 1, NOW(), NOW())"))
        api_key = "dept-test-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/departments", headers=headers)
    assert response.status_code == 200
    departments = response.json()
    assert len(departments) == 2
    assert {d["name"] for d in departments} == {"Support", "Sales"}


def test_list_statuses(client: TestClient, db_conn):
    with db_conn.begin():
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (2, 'Resolved', 'closed', 3, 0, '{}', NOW(), NOW())"))
        api_key = "status-test-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/statuses", headers=headers)
    assert response.status_code == 200
    statuses = response.json()
    assert len(statuses) == 2
    assert {s["name"] for s in statuses} == {"Open", "Resolved"}


def test_list_users_scenarios(client: TestClient, db_conn):
    with db_conn.begin():
        api_key = "user-scenarios-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})
    headers = {"X-API-Key": api_key}

    response = client.get("/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []

    with db_conn.begin():
        now = datetime.now()
        for i in range(3):
            created_time = now - timedelta(seconds=i)
            user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, :name, :ct, :ct, 0)"), {"name": f"User {3-i}", "ct": created_time})
            user_id = user_res.lastrowid
            email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, :email)"), {"uid": user_id, "email": f"user{3-i}@example.com"})
            db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})

    response = client.get("/users?email=user2@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["name"] == "User 2"

    response = client.get("/users?email=nonexistent@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_pagination_links(client: TestClient, db_conn):
    with db_conn.begin():
        now = datetime.now()
        for i in range(3):
            created_time = now - timedelta(seconds=i)
            user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, :name, :ct, :ct, 0)"), {"name": f"User {3-i}", "ct": created_time})
            user_id = user_res.lastrowid
            email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, :email)"), {"uid": user_id, "email": f"user{3-i}@example.com"})
            db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})
        api_key = "pagination-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})
    
    headers = {"X-API-Key": api_key}

    # First page
    response = client.get("/users?limit=1&offset=0", headers=headers)
    data = response.json()
    assert data["previous"] is None
    assert data["next"] is not None

    # Middle page
    response = client.get("/users?limit=1&offset=1", headers=headers)
    data = response.json()
    assert data["previous"] is not None
    assert data["next"] is not None

    # Last page
    response = client.get("/users?limit=1&offset=2", headers=headers)
    data = response.json()
    assert data["previous"] is not None
    assert data["next"] is None


def test_get_user(client: TestClient, db_conn):
    with db_conn.begin():
        user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Specific User', NOW(), NOW(), 0)"))
        user_id = user_res.lastrowid
        email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, 'specific@example.com')"), {"uid": user_id})
        db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})
        api_key = "user-get-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get(f"/users/{user_id}", headers=headers)
    
    assert response.status_code == 200
    assert response.json()["id"] == user_id


def test_get_user_not_found(client: TestClient, db_conn):
    with db_conn.begin():
        api_key = "user-not-found-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/users/99999", headers=headers)
    assert response.status_code == 404


def test_list_tickets_pagination(client: TestClient, db_conn):
    with db_conn.begin():
        db_conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Support', '', 1, NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (2, 'Sales', '', 1, NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (1, 1, 0, 'General', NOW(), NOW(), 1)"))
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated, isactive) VALUES (2, 1, 0, 'Inquiries', NOW(), NOW(), 1)"))
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (3, 'Closed', 'closed', 3, 0, '{}', NOW(), NOW())"))
        
        user_ids = []
        for i in range(5):
            user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, :name, NOW(), NOW(), 0)"), {"name": f"Ticket User {i+1}"})
            user_id = user_res.lastrowid
            user_ids.append(user_id)
            email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, :email)"), {"uid": user_id, "email": f"ticketuser{i+1}@example.com"})
            db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})

        now = datetime.now()
        db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('101', :uid, 1, 2, 3, :ct, :ct)"), {"uid": user_ids[0], "ct": now})
        db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('102', :uid, 2, 1, 1, :ct, :ct)"), {"uid": user_ids[1], "ct": now - timedelta(seconds=1)})
        db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('103', :uid, 1, 1, 3, :ct, :ct)"), {"uid": user_ids[2], "ct": now - timedelta(seconds=2)})
        db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('104', :uid, 2, 1, 1, :ct, :ct)"), {"uid": user_ids[3], "ct": now - timedelta(seconds=3)})
        db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated) VALUES ('105', :uid, 1, 1, 1, :ct, :ct)"), {"uid": user_ids[4], "ct": now - timedelta(seconds=4)})

        api_key = "ticket-list-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}

    response = client.get("/tickets?status_id=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert {item["number"] for item in data["items"]} == {"102", "104", "105"}

    response = client.get("/tickets?topic_id=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 4
    assert {item["number"] for item in data["items"]} == {"102", "103", "104", "105"}

    response = client.get("/tickets?dept_id=1", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert {item["number"] for item in data["items"]} == {"101", "103", "105"}

    response = client.get("/tickets?email=ticketuser2@example.com", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["items"][0]["number"] == "102"

    # First page
    response = client.get("/tickets?limit=1&offset=0", headers=headers)
    data = response.json()
    assert data["previous"] is None
    assert data["next"] is not None

    # Middle page
    response = client.get("/tickets?limit=1&offset=1", headers=headers)
    data = response.json()
    assert data["previous"] is not None
    assert data["next"] is not None

    # Last page
    response = client.get("/tickets?limit=1&offset=4", headers=headers)
    data = response.json()
    assert data["previous"] is not None
    assert data["next"] is None


def test_create_and_get_ticket(client: TestClient, db_conn):
    with db_conn.begin():
        db_conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Test Department', 'Test Signature', 1, NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated) VALUES (1, 1, 1, 'Test Topic', NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_sequence (id, name, next, updated) VALUES (1, 'ticket_number', 0, NOW())"))
        db_conn.execute(text("INSERT INTO ost_config (`key`, `value`, namespace, updated) VALUES ('ticket_sequence_id', '1', 'core', NOW())"))
        db_conn.execute(text("INSERT INTO ost_config (`key`, `value`, namespace, updated) VALUES ('ticket_number_format', 'GCE-######', 'core', NOW())"))
        
        user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Test User', NOW(), NOW(), 0)"))
        user_id = user_res.lastrowid
        email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, 'testuser@example.com')"), {"uid": user_id})
        db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})
        
        api_key = "my-secret-test-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    ticket_data = {"user_id": user_id, "subject": "Test", "message": "Test"}
    
    create_response = client.post("/tickets", headers=headers, json=ticket_data)
    assert create_response.status_code == 200
    new_ticket_id = create_response.json()["ticket_id"]

    get_response = client.get(f"/tickets/{new_ticket_id}", headers=headers)
    assert get_response.status_code == 200
    assert get_response.json()["number"] == "GCE-000001"


def test_create_ticket_with_seq_format(client: TestClient, db_conn):
    with db_conn.begin():
        db_conn.execute(text("INSERT INTO ost_department (id, name, signature, ispublic, created, updated) VALUES (1, 'Test Department', 'Test Signature', 1, NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_help_topic (topic_id, ispublic, noautoresp, topic, created, updated) VALUES (1, 1, 1, 'Test Topic', NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (1, 'Open', 'open', 3, 0, '{}', NOW(), NOW())"))
        db_conn.execute(text("INSERT INTO ost_sequence (id, name, next, updated) VALUES (1, 'ticket_number', 0, NOW())"))
        db_conn.execute(text("INSERT INTO ost_config (`key`, `value`, namespace, updated) VALUES ('ticket_sequence_id', '1', 'core', NOW())"))
        db_conn.execute(text("INSERT INTO ost_config (`key`, `value`, namespace, updated) VALUES ('ticket_number_format', 'TICKET-%SEQ', 'core', NOW())"))
        
        user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Test User', NOW(), NOW(), 0)"))
        user_id = user_res.lastrowid
        email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, 'testuser@example.com')"), {"uid": user_id})
        db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})
        
        api_key = "my-secret-test-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    ticket_data = {"user_id": user_id, "subject": "Test", "message": "Test"}
    
    create_response = client.post("/tickets", headers=headers, json=ticket_data)
    assert create_response.status_code == 200
    assert create_response.json()["number"] == "TICKET-1"


def test_create_ticket_invalid_user(client: TestClient, db_conn):
    with db_conn.begin():
        api_key = "invalid-user-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    ticket_data = {"user_id": 99999, "subject": "Test", "message": "This should fail."}
    
    response = client.post("/tickets", headers=headers, json=ticket_data)
    assert response.status_code == 400


def test_create_ticket_internal_error(client: TestClient, db_conn, monkeypatch):
    with db_conn.begin():
        user_res = db_conn.execute(text(
            "INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Error User', NOW(), NOW(), 0)"))
        user_id = user_res.lastrowid
        email_res = db_conn.execute(
            text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, 'error@example.com')"), {"uid": user_id})
        db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"),
                        {"eid": email_res.lastrowid, "uid": user_id})

        api_key = "internal-error-key"
        db_conn.execute(text(
            "INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"),
                        {"apikey": api_key})

    original_execute = Connection.execute

    def mock_execute_error(self, statement, *args, **kwargs):
        sql_str = str(statement)

        # noinspection SqlDialectInspection,SqlNoDataSourceInspection
        if "INSERT INTO " + "ost_ticket" in sql_str:
            raise Exception("Simulated internal server error")

        return original_execute(self, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", mock_execute_error)

    headers = {"X-API-Key": api_key}
    ticket_data = {"user_id": user_id, "subject": "Test", "message": "Test"}

    response = client.post("/tickets", headers=headers, json=ticket_data)
    assert response.status_code == 500
    assert "Simulated internal server error" in response.json()["detail"]


def test_get_ticket_not_found(client: TestClient, db_conn):
    with db_conn.begin():
        api_key = "ticket-not-found-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.get("/tickets/99999", headers=headers)
    assert response.status_code == 404


def test_add_attachment_to_ticket(client: TestClient, db_conn):
    with db_conn.begin():
        user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Attachment User', NOW(), NOW(), 0)"))
        user_id = user_res.lastrowid
        email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, 'attachment@example.com')"), {"uid": user_id})
        db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})
        
        ticket_res = db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, status_id, created, updated) VALUES ('1', :uid, 1, NOW(), NOW())"), {"uid": user_id})
        ticket_id = ticket_res.lastrowid
        
        thread_res = db_conn.execute(text("INSERT INTO ost_thread (object_id, object_type, created) VALUES (:tid, 'T', NOW())"), {"tid": ticket_id})
        thread_id = thread_res.lastrowid
        
        db_conn.execute(text("INSERT INTO ost_thread_entry (thread_id, poster, body, created, updated) VALUES (:thid, 'Poster', 'Body', NOW(), NOW())"), {"thid": thread_id})
        
        api_key = "attachment-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    response = client.post(f"/tickets/{ticket_id}/attach", headers=headers, files={"file": ("test.txt", io.BytesIO(b"test"), "text/plain")})
    assert response.status_code == 200
    response = client.post(f"/tickets/0/attach", headers=headers, files={"file": ("test.txt", io.BytesIO(b"test"), "text/plain")})
    assert response.status_code == 500


def test_close_ticket(client: TestClient, db_conn):
    with db_conn.begin():
        user_res = db_conn.execute(text("INSERT INTO ost_user (org_id, name, created, updated, default_email_id) VALUES (0, 'Close User', NOW(), NOW(), 0)"))
        user_id = user_res.lastrowid
        email_res = db_conn.execute(text("INSERT INTO ost_user_email (user_id, address) VALUES (:uid, 'close@example.com')"), {"uid": user_id})
        db_conn.execute(text("UPDATE ost_user SET default_email_id = :eid WHERE id = :uid"), {"eid": email_res.lastrowid, "uid": user_id})
        
        ticket_res = db_conn.execute(text("INSERT INTO ost_ticket (number, user_id, status_id, created, updated) VALUES ('1', :uid, 1, NOW(), NOW())"), {"uid": user_id})
        ticket_id = ticket_res.lastrowid
        
        db_conn.execute(text("INSERT INTO ost_ticket_status (id, name, state, mode, flags, properties, created, updated) VALUES (3, 'Closed', 'closed', 3, 0, '{}', NOW(), NOW())"))
        
        api_key = "close-key"
        db_conn.execute(text("INSERT INTO ost_api_key (isactive, ipaddr, apikey, created, updated) VALUES (1, 'testclient', :apikey, NOW(), NOW())"), {"apikey": api_key})

    headers = {"X-API-Key": api_key}
    
    response = client.put(f"/tickets/{ticket_id}/close", headers=headers)
    assert response.status_code == 200
    
    with db_conn.begin():
        result = db_conn.execute(text("SELECT status_id FROM ost_ticket WHERE ticket_id = :tid"), {"tid": ticket_id}).scalar()
        assert result == 3
