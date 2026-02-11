import base64
import hashlib
import os
from datetime import datetime
from typing import List, Optional
import json
import importlib.metadata
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import (Depends, FastAPI, File, Header, HTTPException, Query,
                     Request, UploadFile)
from fastapi.responses import RedirectResponse
from sqlalchemy import create_engine, text, event

from models import (AttachmentResponse, CloseResponse, DepartmentResponse,
                    HealthResponse, PaginatedTicketResponse, StatusResponse,
                    TicketCreate, TicketCreateResponse, TopicResponse, UserResponse, PaginatedUserResponse, TicketItem)
from utils import make_url, CommaSeparatedInts

engine: Optional[create_engine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages the application's lifespan events.

    On startup, it loads environment variables, establishes a database connection pool,
    and sets up an event listener to ensure all new connections use UTF-8.
    On shutdown, it disposes of the database connection pool.
    """
    # This code runs on startup
    global engine

    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    DB_HOST = os.getenv("DB_HOST")
    DB_NAME = os.getenv("DB_NAME")
    DB_PORT = os.getenv("DB_PORT", "3306")

    if not all([DB_USER, DB_PASSWORD, DB_HOST, DB_NAME]):
        raise ValueError("Database environment variables are not fully set.")

    DB_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}?charset=utf8mb4"
    engine = create_engine(DB_URL, pool_pre_ping=True)

    # This event listener ensures that every connection uses the correct UTF-8 encoding and collation.
    # This is crucial for correctly handling special characters like 'é' in searches.
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
        cursor.close()

    yield
    # This code runs on shutdown
    engine.dispose()


# --- SECURITY (Dependency Injection) ---
async def verify_token(x_api_key: str = Header(...), request: Request = None):
    """
    Verify an API key provided in the `X-API-Key` header.

    This security dependency checks the key against the `ost_api_key` table for:
    - Existence
    - Active status (`isactive` flag)

    Raises an HTTPException with status 401 or 403 if validation fails.
    """
    conn = engine.connect()
    try:
        query = text("SELECT `id`, `apikey`, `isactive` FROM `ost_api_key` WHERE `apikey` = :apikey")
        result = conn.execute(query, {"apikey": x_api_key}).mappings().first()

        if not result:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        if not result["isactive"]:
            raise HTTPException(status_code=403, detail="API Key is not active")

    finally:
        conn.close()

app = FastAPI(
    title="osTicket Ultimate Python API", version="0.5.0-dev", lifespan=lifespan
)


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
    with engine.connect() as conn:
        query = text("SELECT topic_id, topic, ispublic FROM ost_help_topic WHERE isactive = 1 ORDER BY topic ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]


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
        offset: int = Query(0, ge=0),
):
    """
    Retrieve a paginated list of users.

    This endpoint allows you to list all users in the system and provides
    pagination controls. You can also filter the results by email address.

    - **email**: Filter users by a specific email address.
    - **limit**: The maximum number of users to return in a single page.
    - **offset**: The number of users to skip before starting to collect the results.
    """
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
            LIMIT {limit} OFFSET {offset}
        """
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
    """
    Retrieve a single user by their unique ID.

    Provides detailed information for a specific user. Returns a 404 error if the user cannot be found.
    """
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
        status_id: Optional[List[int]] = Depends(CommaSeparatedInts("status_id")),
        topic_id: Optional[List[int]] = Depends(CommaSeparatedInts("topic_id")),
        dept_id: Optional[List[int]] = Depends(CommaSeparatedInts("dept_id")),
        email: Optional[str] = None,
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
):
    """
    Retrieve a paginated list of tickets with powerful filtering capabilities.

    This endpoint allows you to search for tickets based on standard fields like status,
    topic, and department, as well as any custom form fields defined in osTicket.

    - **Standard Filters**: `status_id`, `topic_id`, `dept_id`, and `email`. These can accept
      a single ID or a comma-separated list of IDs for multi-value filtering.
    - **Custom Field Filters**: Any other query parameter is treated as a custom field filter.
      For example, `?order_id=123` will search for tickets where the custom field named
      `order_id` has the value `123`. Custom fields also support multi-value searches
      (e.g., `?EFR=Value1,Value2`).
    - **Pagination**: Use `limit` and `offset` to control the result set size and navigate
      through pages.

    The response includes the list of tickets, pagination details, and any associated custom fields for each ticket.
    """
    conn = engine.connect()
    try:
        where_clauses = []
        params = {}
        if status_id:
            where_clauses.append("t.status_id IN :status_ids")
            params["status_ids"] = tuple(status_id)
        if topic_id:
            where_clauses.append("t.topic_id IN :topic_ids")
            params["topic_ids"] = tuple(topic_id)
        if dept_id:
            where_clauses.append("t.dept_id IN :dept_ids")
            params["dept_ids"] = tuple(dept_id)
        if email:
            where_clauses.append("ue.address = :email")
            params["email"] = email

        # --- Custom Fields Filtering ---
        custom_field_joins = ""
        custom_field_params = {}
        known_params = {'status_id', 'topic_id', 'dept_id', 'email', 'limit', 'offset'}

        # Identify custom field filters from the query parameters
        custom_field_keys = [k for k in request.query_params.keys() if k not in known_params]

        # Dynamically build joins and where clauses for each custom field
        for i, field_name in enumerate(custom_field_keys):
            join_alias_fe = f"fe{i}"
            join_alias_fev = f"fev{i}"
            join_alias_ff = f"ff{i}"
            param_name_field = f"cf_name_{i}"

            custom_field_joins += f"""
                JOIN ost_form_entry {join_alias_fe} ON ({join_alias_fe}.object_id = t.ticket_id AND {join_alias_fe}.object_type = 'T')
                JOIN ost_form_entry_values {join_alias_fev} ON {join_alias_fev}.entry_id = {join_alias_fe}.id
                JOIN ost_form_field {join_alias_ff} ON {join_alias_ff}.id = {join_alias_fev}.field_id
            """

            # Handle multiple values for a single custom field (e.g., ?EFR=Value1,Value2 or ?EFR=Value1&EFR=Value2)
            search_values = request.query_params.getlist(field_name)
            flat_values = [item for sublist in [v.split(',') for v in search_values] for item in sublist if item.strip()]

            # Create a list of LIKE conditions for each value to handle JSON-encoded fields
            like_conditions = []
            for j, value in enumerate(flat_values):
                param_name_val = f"cf_val_{i}_{j}"
                # This condition intelligently handles both plain text and JSON-encoded choice fields.
                # 1. It tries to extract the value from a JSON object (e.g., {"14":"Médis"}) and unescapes it.
                # 2. If the field is not a JSON object, the COALESCE falls back to the raw value.
                # 3. This ensures a clean, direct comparison against the user's search term.
                like_conditions.append(f"COALESCE(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT({join_alias_fev}.value, '$.*'), '$[0]')), {join_alias_fev}.value) LIKE :{param_name_val}")
                custom_field_params[param_name_val] = f"%{value}%"

            # Combine the LIKE conditions with OR
            combined_likes = " OR ".join(like_conditions)

            where_clauses.append(
                f"""(
                    {join_alias_ff}.name = :{param_name_field} AND ({combined_likes})
                )"""
            )
            custom_field_params[param_name_field] = field_name

        params.update(custom_field_params)

        # --- Finalize WHERE clause after all filters are added ---
        where_clause = " AND ".join(where_clauses)
        if where_clause:
            where_clause = "WHERE " + where_clause

        count_sql = f"""
            SELECT COUNT(t.ticket_id)
            FROM ost_ticket t
            JOIN ost_user u ON t.user_id = u.id
            JOIN ost_user_email ue ON u.id = ue.user_id
            {custom_field_joins}
            {where_clause}
        """

        total_records = conn.execute(text(count_sql), params).scalar()

        data_sql = f"""
            SELECT t.ticket_id, t.number, t.created, t.status_id, s.name as status_name, 
                   t.topic_id, ht.topic as topic_name, t.dept_id, d.name as dept_name, 
                   t.user_id, u.name as user_name, ue.address as user_email
            FROM ost_ticket t
            JOIN ost_ticket_status s ON t.status_id = s.id
            JOIN ost_user u ON t.user_id = u.id
            JOIN ost_user_email ue ON u.id = ue.user_id
            LEFT JOIN ost_help_topic ht ON t.topic_id = ht.topic_id
            LEFT JOIN ost_department d ON t.dept_id = d.id
            {custom_field_joins}
            {where_clause}
            ORDER BY t.created DESC, t.ticket_id DESC
            LIMIT {limit} OFFSET {offset}
        """

        results = conn.execute(text(data_sql), params).mappings().all()

        # --- Fetch and Attach Custom Fields ---
        ticket_ids = [r["ticket_id"] for r in results]
        final_items = [dict(r) for r in results]

        if ticket_ids:
            custom_fields_query = text("""
                SELECT
                    fe.object_id as ticket_id,
                    ff.name,
                    fev.value
                FROM
                    ost_form_entry fe
                JOIN
                    ost_form_entry_values fev ON fe.id = fev.entry_id
                JOIN
                    ost_form_field ff ON fev.field_id = ff.id
                WHERE
                    fe.object_id IN :ticket_ids
                    AND fe.object_type = 'T'
            """)
            custom_fields_results = conn.execute(custom_fields_query, {"ticket_ids": tuple(ticket_ids)}).mappings().all()

            # Organize custom fields by ticket_id
            custom_fields_map = {tid: {} for tid in ticket_ids}
            for cf in custom_fields_results:
                # For JSON-encoded fields, try to extract the user-friendly value
                try:
                    parsed_val = json.loads(cf['value'])
                    # If it's a dictionary (like a dropdown choice), extract the value.
                    # Otherwise (if it's a number, string, etc.), use the parsed value directly.
                    if isinstance(parsed_val, dict) and parsed_val:
                        custom_fields_map[cf['ticket_id']][cf['name']] = next(iter(parsed_val.values()))
                    else:
                        custom_fields_map[cf['ticket_id']][cf['name']] = parsed_val
                except (json.JSONDecodeError, StopIteration, TypeError):
                    custom_fields_map[cf['ticket_id']][cf['name']] = cf['value']

            # Attach the custom fields to the corresponding ticket items
            for item in final_items:
                item['custom_fields'] = custom_fields_map.get(item['ticket_id'], {})

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
            "items": final_items
        }
    finally:
        conn.close()


@app.get("/tickets/{ticket_id}", response_model=TicketItem, dependencies=[Depends(verify_token)], tags=["Tickets"])
def get_ticket(ticket_id: int):
    """
    Retrieve a single ticket by its unique ID.

    Provides detailed information for a specific ticket, including its status, topic,
    department, owner, and all associated custom field data. Returns a 404 error if the ticket cannot be found.
    """
    with engine.connect() as conn:
        query = """
                SELECT t.ticket_id,
                       t.number,
                       t.created,
                       t.status_id,
                       s.name     as status_name,
                       t.topic_id,
                       ht.topic   as topic_name,
                       t.dept_id,
                       d.name     as dept_name,
                       t.user_id,
                       u.name     as user_name,
                       ue.address as user_email
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

        final_item = dict(result)

        # --- Fetch and Attach Custom Fields for the single ticket ---
        custom_fields_query = text("""
            SELECT
                ff.name,
                fev.value
            FROM
                ost_form_entry fe
            JOIN
                ost_form_entry_values fev ON fe.id = fev.entry_id
            JOIN
                ost_form_field ff ON fev.field_id = ff.id
            WHERE
                fe.object_id = :ticket_id
                AND fe.object_type = 'T'
        """)
        custom_fields_results = conn.execute(custom_fields_query, {"ticket_id": ticket_id}).mappings().all()

        custom_fields_map = {}
        for cf in custom_fields_results:
            try:
                parsed_val = json.loads(cf['value'])
                if isinstance(parsed_val, dict) and parsed_val:
                    custom_fields_map[cf['name']] = next(iter(parsed_val.values()))
                else:
                    custom_fields_map[cf['name']] = parsed_val
            except (json.JSONDecodeError, StopIteration, TypeError):
                custom_fields_map[cf['name']] = cf['value']

        final_item['custom_fields'] = custom_fields_map
        return final_item


@app.post("/tickets", dependencies=[Depends(verify_token)], tags=["Tickets"], response_model=TicketCreateResponse)
def create_ticket(ticket: TicketCreate):
    """
    Create a new ticket in the system.

    This endpoint creates a new ticket, its initial thread entry, and assigns it a ticket number
    based on the sequence and format configured in the osTicket admin panel.
    It requires a valid `user_id` and will raise an error if the user does not exist.
    """
    with engine.connect() as conn:
        with conn.begin() as trans:
            try:
                # --- Validate user_id ---
                user_exists = conn.execute(text("SELECT id FROM ost_user WHERE id = :user_id"),
                                           {"user_id": ticket.user_id}).first()
                if not user_exists:
                    raise HTTPException(status_code=400, detail=f"User with id {ticket.user_id} does not exist.")

                t_num = _generate_ticket_number(conn)

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

                return {"ticket_id": tid, "number": t_num}
            except HTTPException as e:
                trans.rollback()
                raise e
            except Exception as e:
                trans.rollback()
                raise HTTPException(status_code=500, detail=str(e))


def _generate_ticket_number(conn) -> str:
    """
    Generates the next ticket number based on osTicket's sequence and format settings.
    """
    # --- Get osTicket Numbering Configuration ---
    config_query = text(
        "SELECT `key`, `value` FROM `ost_config` WHERE `key` IN ('ticket_sequence_id', 'ticket_number_format')")
    config_res = conn.execute(config_query).mappings().all()
    config = {row['key']: row['value'] for row in config_res}

    sequence_id = config.get('ticket_sequence_id', 1)
    number_format = config.get('ticket_number_format', '%SEQ')

    # --- Get the Next Value from the Sequence ---
    seq_name_query = text("SELECT `name` FROM `ost_sequence` WHERE `id` = :id")
    seq_name = conn.execute(seq_name_query, {"id": sequence_id}).scalar_one_or_none() or 'ticket_number'

    conn.execute(text(f"UPDATE ost_sequence SET next = LAST_INSERT_ID(next + 1) WHERE name = :seq_name"),
                 {"seq_name": seq_name})
    next_seq = conn.execute(text("SELECT LAST_INSERT_ID()")).scalar()

    # --- Format the Number Based on the Mask ---
    now = datetime.now()
    mask = number_format

    replacements = {
        '%y': now.strftime('%y'),
        '%Y': now.strftime('%Y'),
        '%m': now.strftime('%m'),
        '%d': now.strftime('%d'),
    }
    for key, value in replacements.items():
        mask = mask.replace(key, value)

    if '#' in mask:
        num_hashes = mask.count('#')
        mask = mask.replace('#' * num_hashes, str(next_seq).zfill(num_hashes))

    if '%SEQ' in mask:
        mask = mask.replace('%SEQ', str(next_seq))

    return mask


@app.post("/tickets/{ticket_id}/attach", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=AttachmentResponse)
async def add_attachment(ticket_id: int, file: UploadFile = File(...)):
    """
    Attach a file to the latest entry in a ticket's thread.

    This endpoint uploads a file, creates the necessary records in `ost_file` and
    `ost_file_chunk`, and links the file as an attachment to the most recent message or note in the ticket's thread.
    """
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
        raise HTTPException(status_code=500, detail="An internal error occurred while processing the attachment.")
    finally:
        conn.close()


@app.put("/tickets/{ticket_id}/close", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=CloseResponse)
def close_ticket(ticket_id: int):
    """
    Close a ticket.

    This is a convenience endpoint that sets the ticket's status to 'closed' (typically status_id 3)
    and updates its `closed` and `updated` timestamps.
    """
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
