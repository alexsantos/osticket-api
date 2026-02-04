import base64
import hashlib
import os
import random
import string
from datetime import datetime
from typing import List, Optional
from urllib.parse import urlencode
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import (Depends, FastAPI, File, Header, HTTPException, Query,
                     Request, UploadFile)
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, text

from models import (AttachmentResponse, CloseResponse, DepartmentResponse,
                    HealthResponse, PaginatedTicketResponse, StatusResponse,
                    TicketCreate, TicketCreateResponse, TopicResponse, UserResponse, PaginatedUserResponse, TicketItem)
from utils import make_url

engine: Optional[create_engine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # This code runs on startup
    global engine

    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_NAME = os.getenv("DB_NAME")
    DB_PORT = os.getenv("DB_PORT", "3306")

    if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
        raise ValueError("Database environment variables are not fully set.")

    DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(DB_URL, pool_pre_ping=True)
    yield
    # This code runs on shutdown
    engine.dispose()


# --- SECURITY (Dependency Injection) ---
async def verify_token(x_api_key: str = Header(...), request: Request = None):
    """
    Verify the API key against the osTicket database.
    This function checks if the API key is valid, active, and matches the client's IP address.
    """
    conn = engine.connect()
    try:
        query = text("SELECT `id`, `apikey`, `isactive`, `ipaddr` FROM `ost_api_key` WHERE `apikey` = :apikey")
        result = conn.execute(query, {"apikey": x_api_key}).mappings().first()

        if not result:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        if not result["isactive"]:
            raise HTTPException(status_code=403, detail="API Key is not active")

        if result["ipaddr"] and result["ipaddr"] != request.client.host:
            raise HTTPException(status_code=403, detail="IP address not allowed")

    finally:
        conn.close()


app = FastAPI(title="osTicket Ultimate Python API", version="0.0.1", lifespan=lifespan)


# --- HEALTH CHECK ---
@app.get("/health", tags=["Health Check"], response_model=HealthResponse)
def health_check():
    """Checks the health of the API and its database connection."""
    try:
        conn = engine.connect()
        conn.execute(text("SELECT 1"))
        conn.close()
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"status": "error", "database": "error", "details": str(e)})


# --- AUXILIARY LISTING ENDPOINTS ---

@app.get("/topics", dependencies=[Depends(verify_token)], tags=["Listings"], response_model=List[TopicResponse])
def list_help_topics():
    """Lists active Help Topics (e.g., General Support, Sales)."""
    conn = engine.connect()
    try:
        query = text("SELECT topic_id, topic, ispublic FROM ost_help_topic WHERE isactive = 1 ORDER BY topic ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]
    finally:
        conn.close()


@app.get("/departments", dependencies=[Depends(verify_token)], tags=["Listings"],
         response_model=List[DepartmentResponse])
def list_departments():
    """Lists available Departments (e.g., Support, Finance)."""
    conn = engine.connect()
    try:
        query = text("SELECT id, name FROM ost_department ORDER BY name ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]
    finally:
        conn.close()


@app.get("/statuses", dependencies=[Depends(verify_token)], tags=["Listings"], response_model=List[StatusResponse])
def list_statuses():
    """Lists ticket Statuses (e.g., Open, Closed, Resolved)."""
    conn = engine.connect()
    try:
        query = text("SELECT id, name, state FROM ost_ticket_status ORDER BY sort ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]
    finally:
        conn.close()


# --- USERS ---

@app.get("/users", response_model=PaginatedUserResponse, dependencies=[Depends(verify_token)], tags=["Users"])
def list_users(
        request: Request,
        email: Optional[str] = None,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0)
):
    conn = engine.connect()
    try:
        where_clauses = []
        params = {}
        if email:
            where_clauses.append("ue.address = :email")
            params["email"] = email

        where_clause = " AND ".join(where_clauses)
        if where_clause:
            where_clause = "WHERE " + where_clause

        count_sql = f"""
            SELECT COUNT(u.id)
            FROM ost_user u
            JOIN ost_user_email ue ON u.id = ue.user_id
            {where_clause}
        """
        total_records = conn.execute(text(count_sql), params).scalar()

        data_sql = f"""
            SELECT u.id, u.name, ue.address as email, u.created, u.updated
            FROM ost_user u
            JOIN ost_user_email ue ON u.id = ue.user_id
            {where_clause}
            ORDER BY u.created DESC, u.id DESC
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = limit
        params["offset"] = offset
        results = conn.execute(text(data_sql), params).mappings().all()

        next_url = None
        if offset + limit < total_records:
            next_url = make_url(request, limit, offset + limit)

        prev_url = None
        if offset > 0:
            new_prev_offset = max(0, offset - limit)
            prev_url = make_url(request, limit, new_prev_offset)

        return {
            "total": total_records,
            "limit": limit,
            "offset": offset,
            "next": next_url,
            "previous": prev_url,
            "items": [dict(r) for r in results]
        }
    finally:
        conn.close()


@app.get("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_token)], tags=["Users"])
def get_user(user_id: int):
    conn = engine.connect()
    try:
        query = """
                SELECT u.id, u.name, ue.address as email, u.created, u.updated
                FROM ost_user u
                         JOIN ost_user_email ue ON u.id = ue.user_id
                WHERE u.id = :user_id \
                """
        result = conn.execute(text(query), {"user_id": user_id}).mappings().first()
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(result)
    finally:
        conn.close()


# --- TICKETS ---

@app.get("/tickets", response_model=PaginatedTicketResponse, dependencies=[Depends(verify_token)],
         tags=["Tickets"])
def list_tickets(
        request: Request,
        status_id: Optional[int] = None,
        topic_id: Optional[int] = None,
        dept_id: Optional[int] = None,
        email: Optional[str] = None,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0)
):
    conn = engine.connect()
    try:
        where_clauses = []
        params = {}
        if status_id:
            where_clauses.append("t.status_id = :status_id")
            params["status_id"] = status_id
        if topic_id:
            where_clauses.append("t.topic_id = :topic_id")
            params["topic_id"] = topic_id
        if dept_id:
            where_clauses.append("t.dept_id = :dept_id")
            params["dept_id"] = dept_id
        if email:
            where_clauses.append("ue.address = :email")
            params["email"] = email

        where_clause = " AND ".join(where_clauses)
        if where_clause:
            where_clause = "WHERE " + where_clause

        count_sql = f"""
            SELECT COUNT(t.ticket_id)
            FROM ost_ticket t
            JOIN ost_user u ON t.user_id = u.id
            JOIN ost_user_email ue ON u.id = ue.user_id
            {where_clause}
        """
        total_records = conn.execute(text(count_sql), params).scalar()

        data_sql = f"""
            SELECT t.ticket_id, t.number, t.created, s.name as status_name, 
                   ht.topic as topic_name, d.name as dept_name, u.name as owner_name, ue.address as email
            FROM ost_ticket t
            JOIN ost_ticket_status s ON t.status_id = s.id
            JOIN ost_user u ON t.user_id = u.id
            JOIN ost_user_email ue ON u.id = ue.user_id
            LEFT JOIN ost_help_topic ht ON t.topic_id = ht.topic_id
            LEFT JOIN ost_department d ON t.dept_id = d.id
            {where_clause}
            ORDER BY t.created DESC, t.ticket_id DESC
            LIMIT :limit OFFSET :offset
        """
        params["limit"] = limit
        params["offset"] = offset
        results = conn.execute(text(data_sql), params).mappings().all()

        next_url = None
        if offset + limit < total_records:
            next_url = make_url(request, limit, offset + limit)

        prev_url = None
        if offset > 0:
            new_prev_offset = max(0, offset - limit)
            prev_url = make_url(request, limit, new_prev_offset)

        return {
            "total": total_records,
            "limit": limit,
            "offset": offset,
            "next": next_url,
            "previous": prev_url,
            "items": [dict(r) for r in results]
        }
    finally:
        conn.close()


@app.get("/tickets/{ticket_id}", response_model=TicketItem, dependencies=[Depends(verify_token)], tags=["Tickets"])
def get_ticket(ticket_id: int):
    conn = engine.connect()
    try:
        query = """
                SELECT t.ticket_id,
                       t.number,
                       t.created,
                       s.name     as status_name,
                       ht.topic   as topic_name,
                       d.name     as dept_name,
                       u.name     as owner_name,
                       ue.address as email
                FROM ost_ticket t
                         JOIN ost_ticket_status s ON t.status_id = s.id
                         JOIN ost_user u ON t.user_id = u.id
                         JOIN ost_user_email ue ON u.id = ue.user_id
                         LEFT JOIN ost_help_topic ht ON t.topic_id = ht.topic_id
                         LEFT JOIN ost_department d ON t.dept_id = d.id
                WHERE t.ticket_id = :ticket_id \
                """
        result = conn.execute(text(query), {"ticket_id": ticket_id}).mappings().first()
        if not result:
            raise HTTPException(status_code=404, detail="Ticket not found")
        return dict(result)
    finally:
        conn.close()


@app.post("/tickets", dependencies=[Depends(verify_token)], tags=["Tickets"], response_model=TicketCreateResponse)
def create_ticket(ticket: TicketCreate):
    """Creates ticket, thread and subject."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        # --- Validate user_id ---
        user_exists = conn.execute(text("SELECT id FROM ost_user WHERE id = :user_id"),
                                   {"user_id": ticket.user_id}).first()
        if not user_exists:
            raise HTTPException(status_code=400, detail=f"User with id {ticket.user_id} does not exist.")

        # Atomically get the next ticket number
        conn.execute(text("UPDATE ost_sequence SET next = LAST_INSERT_ID(next + 1) WHERE name = 'ticket_number'"))
        t_num_res = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()
        t_num = str(t_num_res)

        insert_topic_id = ticket.topic_id if ticket.topic_id is not None else 1
        insert_dept_id = ticket.dept_id if ticket.dept_id is not None else 1

        res = conn.execute(text("""
                                INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated)
                                VALUES (:n, :user_id, :dept_id, :topic, 1, NOW(), NOW())
                                """), {"n": t_num, "user_id": ticket.user_id, "dept_id": insert_dept_id,
                                       "topic": insert_topic_id})
        tid = res.lastrowid

        conn.execute(text("INSERT INTO ost_thread (object_id, object_type, created) VALUES (:id, 'T', NOW())"),
                     {"id": tid})
        thid = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

        conn.execute(text("""
                          INSERT INTO ost_thread_entry (thread_id, type, body, poster, created, updated)
                          VALUES (:thid, 'M', :body, :p, NOW(), NOW())
                          """), {"thid": thid, "body": ticket.message, "p": "API"})

        trans.commit()
        return {"ticket_id": tid, "number": t_num}
    except HTTPException as e:
        trans.rollback()
        raise e  # Re-raise the HTTPException
    except Exception as e:
        trans.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@app.post("/tickets/{ticket_id}/attach", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=AttachmentResponse)
async def add_attachment(ticket_id: int, file: UploadFile = File(...)):
    """Chunk logic for attachments in osTicket."""
    conn = engine.connect()
    trans = conn.begin()
    try:
        data = await file.read()
        f_hash = base64.b64encode(hashlib.sha1(data).digest()).decode()

        fid = conn.execute(text("""
                                INSERT INTO ost_file (ft, type, size, name, `key`, signature, created)
                                VALUES ('T', :t, :s, :n, :k, :sig, NOW())
                                """), {"t": file.content_type, "s": len(data), "n": file.filename, "k": f_hash[:32],
                                       "sig": f_hash}).lastrowid

        conn.execute(text("INSERT INTO ost_file_chunk (file_id, chunk_id, filedata) VALUES (:fid, 0, :d)"),
                     {"fid": fid, "d": data})

        eid = conn.execute(text(
            "SELECT id FROM ost_thread_entry WHERE thread_id = (SELECT id FROM ost_thread WHERE object_id=:tid AND object_type='T') ORDER BY id DESC LIMIT 1"),
            {"tid": ticket_id}).scalar()
        conn.execute(text("INSERT INTO ost_attachment (object_id, type, file_id) VALUES (:eid, 'H', :fid)"),
                     {"eid": eid, "fid": fid})

        trans.commit()
        return {"file_id": fid}
    except Exception as e:
        trans.rollback()
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {e}")
    finally:
        conn.close()


@app.put("/tickets/{ticket_id}/close", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=CloseResponse)
def close_ticket(ticket_id: int):
    """Closes the ticket (Status ID 3)."""
    conn = engine.connect()
    try:
        conn.execute(text("UPDATE ost_ticket SET status_id = 3, closed = NOW(), updated = NOW() WHERE ticket_id = :id"),
                     {"id": ticket_id})
        conn.commit()
        return {"status": "closed"}
    finally:
        conn.close()


@app.get("/", include_in_schema=False)
async def redirect_to_docs():  # pragma: no cover
    return RedirectResponse(url="/redoc")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    # Load .env file for direct script execution
    load_dotenv()
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
