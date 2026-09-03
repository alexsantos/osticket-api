import base64
import hashlib
import os
from datetime import datetime
from typing import List, Optional
import json
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import (Depends, FastAPI, File, Header, HTTPException, Query,
                     Request, UploadFile)
from fastapi.responses import RedirectResponse
from sqlalchemy import bindparam, create_engine, text, event
from sqlalchemy.engine import Engine, URL

import osticket_client
from models import (AttachmentResponse, CloseResponse, DepartmentResponse, TeamResponse,
                    HealthResponse, MessageCreate, MessageResponse, NoteCreate, NoteResponse, PaginatedTicketResponse, StatusResponse,
                    TicketCreate, TicketCreateResponse, TopicResponse, UserResponse, PaginatedUserResponse, TicketItem, MessagesResponse,
                    StatusUpdateRequest, DepartmentUpdateRequest, TeamUpdateRequest, MessageUpdateRequest,
                    UpdateResponse, AttachmentsResponse)
from utils import build_pagination_urls, CommaSeparatedInts

MAX_UPLOAD_MB: int = 10
MAX_UPLOAD_BYTES: int = MAX_UPLOAD_MB * 1024 * 1024

engine: Optional[Engine] = None
_supports_json_functions: Optional[bool] = None


def _get_engine() -> Engine:
    if engine is None:
        raise RuntimeError("Database engine is not initialized.")
    return engine


def _server_supports_json_functions(version_string: str) -> bool:
    """
    Whether the connected server supports JSON_EXTRACT/JSON_UNQUOTE, used to
    unwrap JSON-encoded custom field values when filtering GET /tickets.

    MariaDB added these functions in 10.2; MySQL in 5.7.8. Older MariaDB
    builds report a "5.5.5-10.11.5-MariaDB..." compatibility-prefixed
    version string, where the real version follows the "5.5.5-" prefix.
    """
    is_mariadb = "MariaDB" in version_string
    version_part = version_string.split("-MariaDB")[0] if is_mariadb else version_string.split("-")[0]
    if is_mariadb and version_part.startswith("5.5.5-"):
        version_part = version_part[len("5.5.5-"):]
    try:
        numeric_version = tuple(int(p) for p in version_part.split(".")[:3])
    except ValueError:
        return True  # Unrecognized format — assume a modern server rather than degrading filters.
    return numeric_version >= ((10, 2) if is_mariadb else (5, 7, 8))


def _json_functions_supported(conn) -> bool:
    """Lazily detects and caches JSON function support for the connected server."""
    global _supports_json_functions
    if _supports_json_functions is None:
        server_version = conn.execute(text("SELECT VERSION()")).scalar_one()
        _supports_json_functions = _server_supports_json_functions(server_version)
    return _supports_json_functions


def _get_status_id(conn, state: str) -> int:
    status_id = conn.execute(
        text("SELECT id FROM ost_ticket_status WHERE state = :state LIMIT 1"),
        {"state": state}
    ).scalar_one_or_none()
    if not status_id:
        raise HTTPException(status_code=500, detail=f"No '{state}' status configured in osTicket.")
    return status_id


def _parse_custom_field_value(raw_value):
    """
    Parses a custom field's raw stored value, unwrapping JSON-encoded choice
    fields (e.g. dropdowns stored as {"14": "Value"}) to their user-friendly value.
    """
    try:
        parsed_val = json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return raw_value
    if isinstance(parsed_val, dict) and parsed_val:
        return next(iter(parsed_val.values()))
    return parsed_val


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Manages the application's lifespan events.

    On startup, it loads environment variables, establishes a database connection pool,
    and sets up an event listener to ensure all new connections use UTF-8.
    On shutdown, it disposes of the database connection pool.
    """
    # This code runs on startup
    global engine, MAX_UPLOAD_MB, MAX_UPLOAD_BYTES

    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "10"))
    MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

    db_user = os.getenv("DB_USER")
    db_password = os.getenv("DB_PASSWORD")
    db_host = os.getenv("DB_HOST")
    db_name = os.getenv("DB_NAME")
    db_port = os.getenv("DB_PORT", "3306")

    if not all([db_user, db_password, db_host, db_name]):
        raise ValueError("Database environment variables are not fully set.")

    db_url = URL.create(
        drivername="mysql+mysqldb",
        username=db_user,
        password=db_password,
        host=db_host,
        port=int(db_port),
        database=db_name,
        query={"charset": "utf8mb4"},
    )
    engine = create_engine(db_url, pool_pre_ping=True)

    # This event listener ensures that every connection uses the correct UTF-8 encoding and collation.
    # This is crucial for correctly handling special characters like 'é' in searches.
    @event.listens_for(engine, "connect")
    def connect(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET NAMES 'utf8mb4' COLLATE 'utf8mb4_unicode_ci'")
        cursor.close()

    osticket_client.init(
        base_url=os.getenv("OSTICKET_BASE_URL"),
        secret_salt=os.getenv("OSTICKET_SECRET_SALT"),
        staff_username=os.getenv("OSTICKET_STAFF_USERNAME"),
        staff_password=os.getenv("OSTICKET_STAFF_PASSWORD"),
    )

    yield
    # This code runs on shutdown
    engine.dispose()


# --- SECURITY (Dependency Injection) ---
async def verify_token(x_api_key: str = Header(...)):
    """
    Verify an API key provided in the `X-API-Key` header.

    This security dependency checks the key against the `ost_api_key` table for:
    - Existence
    - Active status (`isactive` flag)

    Raises an HTTPException with status 401 or 403 if validation fails.
    """
    with _get_engine().connect() as conn:
        query = text("SELECT `id`, `apikey`, `isactive` FROM `ost_api_key` WHERE `apikey` = :apikey")
        result = conn.execute(query, {"apikey": x_api_key}).mappings().first()

        if not result:
            raise HTTPException(status_code=401, detail="Invalid API Key")

        if not result["isactive"]:
            raise HTTPException(status_code=403, detail="API Key is not active")

app = FastAPI(
    title="osTicket Ultimate Python API", version="0.10.9", lifespan=lifespan
)


# --- HEALTH CHECK ---
@app.get("/health", tags=["Health Check"], response_model=HealthResponse)
def health_check():
    """Checks the health of the API and its database connection."""
    try:
        with _get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        raise HTTPException(status_code=503, detail={"status": "error", "database": "error", "details": str(e)}) from e


# --- AUXILIARY LISTING ENDPOINTS ---

@app.get("/topics", dependencies=[Depends(verify_token)], tags=["Listings"], response_model=List[TopicResponse])
def list_help_topics():
    """Lists active Help Topics (e.g., General Support, Sales)."""
    with _get_engine().connect() as conn:
        query = text("SELECT topic_id, topic, ispublic FROM ost_help_topic WHERE isactive = 1 ORDER BY topic ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]


@app.get("/departments", dependencies=[Depends(verify_token)], tags=["Listings"],
         response_model=List[DepartmentResponse])
def list_departments():
    """Lists available Departments (e.g., Support, Finance)."""
    with _get_engine().connect() as conn:
        query = text("SELECT id, name FROM ost_department ORDER BY name ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]


@app.get("/teams", dependencies=[Depends(verify_token)], tags=["Listings"],
         response_model=List[TeamResponse])
def list_teams():
    """Lists available Teams."""
    with _get_engine().connect() as conn:
        query = text("SELECT team_id, name FROM ost_team ORDER BY name ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]


@app.get("/statuses", dependencies=[Depends(verify_token)], tags=["Listings"], response_model=List[StatusResponse])
def list_statuses():
    """Lists ticket Statuses (e.g., Open, Closed, Resolved)."""
    with _get_engine().connect() as conn:
        query = text("SELECT id, name, state FROM ost_ticket_status ORDER BY sort ASC")
        results = conn.execute(query).mappings().all()
        return [dict(row) for row in results]


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
    with _get_engine().connect() as conn:
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
        total_records = conn.execute(text(count_sql), params).scalar_one()

        params["limit"] = limit
        params["offset"] = offset
        data_sql = f"""
            SELECT u.id, u.name, ue.address as email, u.created, u.updated
            FROM ost_user u
            JOIN ost_user_email ue ON u.id = ue.user_id
            {where_clause}
            ORDER BY u.created DESC, u.id DESC
            LIMIT :limit OFFSET :offset
        """
        results = conn.execute(text(data_sql), params).mappings().all()

        next_url, prev_url = build_pagination_urls(request, limit, offset, total_records)

        return {
            "total": total_records,
            "limit": limit,
            "offset": offset,
            "next": next_url,
            "previous": prev_url,
            "items": [dict(r) for r in results]
        }


@app.get("/users/{user_id}", response_model=UserResponse, dependencies=[Depends(verify_token)], tags=["Users"])
def get_user(user_id: int):
    """
    Retrieve a single user by their unique ID.

    Provides detailed information for a specific user. Returns a 404 error if the user cannot be found.
    """
    with _get_engine().connect() as conn:
        query = """
                SELECT u.id, u.name, ue.address as email, u.created, u.updated
                FROM ost_user u
                         JOIN ost_user_email ue ON u.id = ue.user_id
                WHERE u.id = :user_id
                """
        result = conn.execute(text(query), {"user_id": user_id}).mappings().first()
        if not result:
            raise HTTPException(status_code=404, detail="User not found")
        return dict(result)


# --- TICKETS ---

@app.get("/tickets", response_model=PaginatedTicketResponse, dependencies=[Depends(verify_token)],
         tags=["Tickets"])
def list_tickets(
        request: Request,
        status_id: Optional[List[int]] = Depends(CommaSeparatedInts("status_id")),
        topic_id: Optional[List[int]] = Depends(CommaSeparatedInts("topic_id")),
        dept_id: Optional[List[int]] = Depends(CommaSeparatedInts("dept_id")),
        email: Optional[str] = None,
        updated_after: Optional[datetime] = Query(None, description="Filter tickets updated after this date (YYYY-MM-DDTHH:MM:SS)."),
        updated_before: Optional[datetime] = Query(None, description="Filter tickets updated before this date (YYYY-MM-DDTHH:MM:SS)."),
        limit: int = Query(50, ge=1, le=500),
        offset: int = Query(0, ge=0),
):
    """
    Retrieve a paginated list of tickets with powerful filtering capabilities.

    This endpoint allows you to search for tickets based on standard fields like status,
    topic, and department, as well as any custom form fields defined in osTicket.

    - **Standard Filters**: `status_id`, `topic_id`, `dept_id`, and `email`. These can accept
      a single ID or a comma-separated list of IDs for multi-value filtering. `updated_after` and `updated_before`
      can be used to filter by the last update timestamp.
    - **Custom Field Filters**: Any other query parameter is treated as a custom field filter.
      For example, `?order_id=123` will search for tickets where the custom field named
      `order_id` has the value `123`. Custom fields also support multi-value searches
      (e.g., `?EFR=Value1,Value2`).
    - **Pagination**: Use `limit` and `offset` to control the result set size and navigate
      through pages.

    The response includes the list of tickets, pagination details, and any associated custom fields for each ticket.
    """
    with _get_engine().connect() as conn:
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
        if updated_after:
            where_clauses.append("t.updated >= :updated_after")
            params["updated_after"] = updated_after
        if updated_before:
            where_clauses.append("t.updated <= :updated_before")
            params["updated_before"] = updated_before

        # --- Custom Fields Filtering ---
        custom_field_joins = ""
        custom_field_params = {}
        known_params = {'status_id', 'topic_id', 'dept_id', 'email', 'updated_after', 'updated_before', 'limit', 'offset'}

        # Identify custom field filters from the query parameters
        custom_field_keys = [k for k in request.query_params.keys() if k not in known_params]
        supports_json = _json_functions_supported(conn) if custom_field_keys else True

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
                if supports_json:
                    # This condition intelligently handles both plain text and JSON-encoded choice fields.
                    # 1. It tries to extract the value from a JSON object (e.g., {"14":"Médis"}) and unescapes it.
                    # 2. If the field is not a JSON object, the COALESCE falls back to the raw value.
                    # 3. This ensures a clean, direct comparison against the user's search term.
                    like_conditions.append(f"COALESCE(JSON_UNQUOTE(JSON_EXTRACT(JSON_EXTRACT({join_alias_fev}.value, '$.*'), '$[0]')), {join_alias_fev}.value) LIKE :{param_name_val}")
                else:
                    # Older servers (MariaDB < 10.2, MySQL < 5.7.8) lack JSON_EXTRACT/JSON_UNQUOTE.
                    # Fall back to matching the raw stored value directly.
                    like_conditions.append(f"{join_alias_fev}.value LIKE :{param_name_val}")
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

        total_records = conn.execute(text(count_sql), params).scalar_one()

        data_sql = f"""
            SELECT t.ticket_id,
                   t.number, 
                   t.created, 
                   t.status_id, 
                   s.name as status_name, 
                   t.topic_id, 
                   ht.topic as topic_name, 
                   t.dept_id, 
                   d.name as dept_name, 
                   t.updated,
                   t.user_id, 
                   u.name as user_name, 
                   ue.address as user_email, 
                   t.team_id, 
                   team.name as team_name,
                   te.title   as subject,
                   te.body    as message
            FROM ost_ticket t
            JOIN ost_ticket_status s ON t.status_id = s.id
            JOIN ost_user u ON t.user_id = u.id
            JOIN ost_user_email ue ON u.id = ue.user_id
            LEFT JOIN ost_help_topic ht ON t.topic_id = ht.topic_id
            LEFT JOIN ost_department d ON t.dept_id = d.id
            LEFT JOIN ost_team team ON t.team_id = team.team_id
            LEFT JOIN ost_thread th ON th.object_id = t.ticket_id AND th.object_type = 'T'
            LEFT JOIN ost_thread_entry te ON te.id = (
                             SELECT MIN(id) FROM ost_thread_entry WHERE thread_id = th.id
                         )
            {custom_field_joins}
            {where_clause}
            ORDER BY t.created DESC, t.ticket_id DESC
            LIMIT :limit OFFSET :offset
        """

        params["limit"] = limit
        params["offset"] = offset
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
                custom_fields_map[cf['ticket_id']][cf['name']] = _parse_custom_field_value(cf['value'])

            # Attach the custom fields to the corresponding ticket items
            for item in final_items:
                item['custom_fields'] = custom_fields_map.get(item['ticket_id'], {})

        next_url, prev_url = build_pagination_urls(request, limit, offset, total_records)

        return {
            "total": total_records,
            "limit": limit,
            "offset": offset,
            "next": next_url,
            "previous": prev_url,
            "items": final_items
        }


def _query_ticket_messages(conn, ticket_ids: List[int]):
    query = text("""
            SELECT t.ticket_id,
                   te.thread_id,
                   te.id as entry_id,
                   te.staff_id,
                   te.user_id,
                   te.type,
                   te.poster,
                   te.editor,
                   te.editor_type,
                   te.source,
                   te.format,
                   te.title   as subject,
                   te.body    as message,
                   te.created,
                   te.updated
            FROM ost_ticket t
                     JOIN ost_thread th ON th.object_id = t.ticket_id AND th.object_type = 'T'
                     JOIN ost_thread_entry te ON thread_id = th.id
            WHERE t.ticket_id IN :ticket_ids
            ORDER BY t.ticket_id ASC, te.id ASC
            """).bindparams(bindparam("ticket_ids", expanding=True))
    return conn.execute(query, {"ticket_ids": ticket_ids}).mappings().all()


@app.get("/messages", dependencies=[Depends(verify_token)], tags=["Messages"],
         response_model=List[MessagesResponse])
def list_messages(ticket_ids: List[int] = Depends(CommaSeparatedInts("ticket_ids"))):
    """
    Retrieve the messages for a list of tickets by their unique IDs.
    Returns a 404 error if no matching tickets or messages are found.
    """
    if not ticket_ids:
        raise HTTPException(status_code=422, detail="Query parameter 'ticket_ids' is required")

    with _get_engine().connect() as conn:
        results = _query_ticket_messages(conn, ticket_ids)

        if not results:
            raise HTTPException(status_code=404, detail="Ticket or Messages not found")

        return [dict(row) for row in results]


@app.get("/tickets/messages", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=List[MessagesResponse], deprecated=True)
def list_ticket_messages(ticket_ids: List[int] = Depends(CommaSeparatedInts("ticket_ids"))):
    """
    Deprecated: use `GET /messages?ticket_ids=...` instead.

    Retrieve the messages for a list of tickets by their unique IDs.
    Returns a 404 error if no matching tickets or messages are found.
    """
    return list_messages(ticket_ids)


@app.get("/tickets/{ticket_id}/messages", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=List[MessagesResponse])
def get_ticket_messages(ticket_id: int):
    """
    Retrieve the messages for a single ticket by its unique ID.
    Returns a 404 error if the ticket cannot be found or has no messages.
    """
    with _get_engine().connect() as conn:
        results = _query_ticket_messages(conn, [ticket_id])

        if not results:
            raise HTTPException(status_code=404, detail="Ticket or Messages not found")

        return [dict(row) for row in results]


def _query_ticket_attachments(conn, ticket_ids: List[int]):
    query = text("""
            SELECT t.ticket_id,
                   a.id AS attachment_id,
                   a.file_id,
                   th.id AS thread_id,
                   te.id AS entry_id,
                   f.name,
                   f.type,
                   f.size,
                   a.inline,
                   f.created,
                   f.`key`       AS file_key,
                   f.signature   AS file_hash,
                   fc.chunk_id,
                   fc.filedata
            FROM ost_ticket t
                     JOIN ost_thread th ON th.object_id = t.ticket_id AND th.object_type = 'T'
                     JOIN ost_thread_entry te ON te.thread_id = th.id
                     JOIN ost_attachment a ON a.object_id = te.id AND a.type = 'H'
                     JOIN ost_file f ON f.id = a.file_id
                     LEFT JOIN ost_file_chunk fc ON fc.file_id = f.id
            WHERE t.ticket_id IN :ticket_ids
            ORDER BY f.created ASC, a.id ASC, fc.chunk_id ASC
            """).bindparams(bindparam("ticket_ids", expanding=True))
    results = conn.execute(query, {"ticket_ids": ticket_ids}).mappings().all()

    attachments = {}
    chunks = {}
    fallback_meta = {}
    for row in results:
        attachment_id = row["attachment_id"]
        if attachment_id not in attachments:
            attachment = dict(row)
            attachment.pop("chunk_id", None)
            attachment.pop("filedata", None)
            file_key = attachment.pop("file_key", None)
            file_hash = attachment.pop("file_hash", None)
            attachments[attachment_id] = attachment
            chunks[attachment_id] = []
            fallback_meta[attachment_id] = (file_key, file_hash)
        if row["filedata"] is not None:
            chunks[attachment_id].append(row["filedata"])

    response = []
    for attachment_id, attachment in attachments.items():
        if chunks[attachment_id]:
            content_bytes = b"".join(chunks[attachment_id])
        else:
            # No rows in ost_file_chunk means the file's bytes live in a non-database
            # storage backend (see ost_file.bk) - fetch them from osTicket's own
            # web frontend instead. Returns None (-> content stays null) if the
            # fallback isn't configured, or the fetch itself fails.
            file_key, file_hash = fallback_meta[attachment_id]
            content_bytes = osticket_client.fetch_attachment_content(
                file_id=attachment["file_id"],  # a.file_id == ost_file.id via the join
                attachment_id=attachment_id,
                key=file_key,
                file_hash=file_hash,
            )
        attachment["content"] = base64.b64encode(content_bytes).decode("ascii") if content_bytes else None
        response.append(attachment)
    return response


@app.get("/attachments", dependencies=[Depends(verify_token)], tags=["Attachments"],
         response_model=List[AttachmentsResponse])
def list_attachments(ticket_ids: List[int] = Depends(CommaSeparatedInts("ticket_ids"))):
    """
    Retrieve the attachments for a list of tickets by their unique ID.
    Returns a 404 error if no matching tickets or attachments are found.
    """
    if not ticket_ids:
        raise HTTPException(status_code=422, detail="Query parameter 'ticket_ids' is required")

    with _get_engine().connect() as conn:
        response = _query_ticket_attachments(conn, ticket_ids)

        if not response:
            raise HTTPException(status_code=404, detail="Ticket or Attachments not found")

        return response


@app.get("/tickets/attachments", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=List[AttachmentsResponse], deprecated=True)
def list_ticket_attachments(ticket_ids: List[int] = Depends(CommaSeparatedInts("ticket_ids"))):
    """
    Deprecated: use `GET /attachments?ticket_ids=...` instead.

    Retrieve the attachments for a list of tickets by their unique ID.
    Returns a 404 error if no matching tickets or attachments are found.
    """
    return list_attachments(ticket_ids)


@app.get("/tickets/{ticket_id}/attachments", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=List[AttachmentsResponse])
def get_ticket_attachments(ticket_id: int):
    """
    Retrieve the attachments for a single ticket by its unique ID.
    Returns a 404 error if the ticket cannot be found or has no attachments.
    """
    with _get_engine().connect() as conn:
        response = _query_ticket_attachments(conn, [ticket_id])

        if not response:
            raise HTTPException(status_code=404, detail="Ticket or Attachments not found")

        return response


@app.get("/tickets/{ticket_id}", response_model=TicketItem, dependencies=[Depends(verify_token)], tags=["Tickets"])
def get_ticket(ticket_id: int):
    """
    Retrieve a single ticket by its unique ID.

    Provides detailed information for a specific ticket, including its status, topic,
    department, team, owner, and all associated custom field data. Returns a 404 error if the ticket cannot be found.
    """
    with _get_engine().connect() as conn:
        query = """
                SELECT t.ticket_id,
                       t.number,
                       t.created,
                       t.status_id,
                       s.name     as status_name,
                       t.topic_id,
                       ht.topic   as topic_name,
                       t.updated,
                       t.dept_id,
                       d.name     as dept_name,
                       t.user_id,
                       u.name     as user_name,
                       ue.address as user_email,
                       t.team_id,
                       team.name as team_name,
                       t.closed,
                       te.title   as subject,
                       te.body    as message
                FROM ost_ticket t
                         JOIN ost_ticket_status s ON t.status_id = s.id
                         JOIN ost_user u ON t.user_id = u.id
                         JOIN ost_user_email ue ON u.id = ue.user_id
                         LEFT JOIN ost_help_topic ht ON t.topic_id = ht.topic_id
                         LEFT JOIN ost_department d ON t.dept_id = d.id
                         LEFT JOIN ost_thread th ON th.object_id = t.ticket_id AND th.object_type = 'T'
                         LEFT JOIN ost_thread_entry te ON te.id = (
                             SELECT MIN(id) FROM ost_thread_entry WHERE thread_id = th.id
                         )
                         LEFT JOIN ost_team team ON t.team_id = team.team_id
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
            custom_fields_map[cf['name']] = _parse_custom_field_value(cf['value'])

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
    try:
        with _get_engine().begin() as conn:
            # --- Validate user_id ---
            user_exists = conn.execute(text("SELECT id FROM ost_user WHERE id = :user_id"),
                                       {"user_id": ticket.user_id}).first()
            if not user_exists:
                raise HTTPException(status_code=400, detail=f"User with id {ticket.user_id} does not exist.")

            open_status_id = _get_status_id(conn, "open")

            t_num = _generate_ticket_number(conn)

            insert_topic_id = ticket.topic_id if ticket.topic_id is not None else 1
            insert_dept_id = ticket.dept_id if ticket.dept_id is not None else 1

            res = conn.execute(text("""
                                    INSERT INTO ost_ticket (number, user_id, dept_id, topic_id, status_id, created, updated)
                                    VALUES (:n, :user_id, :dept_id, :topic, :status_id, NOW(), NOW())
                                    """), {"n": t_num, "user_id": ticket.user_id, "dept_id": insert_dept_id,
                                           "topic": insert_topic_id, "status_id": open_status_id})
            tid = res.lastrowid

            thread_res = conn.execute(text("INSERT INTO ost_thread (object_id, object_type, created) VALUES (:id, 'T', NOW())"),
                         {"id": tid})
            thid = thread_res.lastrowid

            conn.execute(text("""
                              INSERT INTO ost_thread_entry (thread_id, type, title, body, poster, created, updated)
                              VALUES (:thid, 'M', :title, :body, :p, NOW(), NOW())
                              """), {"thid": thid, "title": ticket.subject, "body": ticket.message, "p": "API"})

            return {"ticket_id": tid, "number": t_num}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred while creating the ticket.") from e


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
    # Lock by id then update by id to avoid a name-lookup round-trip
    conn.execute(text("SELECT id FROM ost_sequence WHERE id = :id FOR UPDATE"), {"id": sequence_id})
    conn.execute(text("UPDATE ost_sequence SET next = LAST_INSERT_ID(next + 1) WHERE id = :id"), {"id": sequence_id})
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


@app.post("/tickets/{ticket_id}/messages/{entry_id}/attachments", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=AttachmentResponse)
async def add_attachment(ticket_id: int, entry_id: int, file: UploadFile = File(...)):
    """
    Attach a file to an entry in a ticket's thread.

    This endpoint uploads a file, creates the necessary records in `ost_file` and
    `ost_file_chunk`, and links the file as an attachment to the specified message in the ticket's thread.
    """
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_MB} MB.")

    f_hash = base64.b64encode(hashlib.sha256(data).digest()).decode()

    try:
        with _get_engine().begin() as conn:
            count_id = conn.execute(text("""
                                         SELECT count(*)
                                         FROM ost_thread th
                                            JOIN ost_thread_entry te ON th.id = te.thread_id
                                         WHERE th.object_id = :ticket_id
                                            AND th.object_type = 'T'
                                            AND te.id = :entry_id
                                        """), {"ticket_id": ticket_id, "entry_id": entry_id})
            if count_id.scalar() == 0:
                raise HTTPException(status_code=404, detail="Ticket or message not found.")

            fid = conn.execute(text("""
                                    INSERT INTO ost_file (ft, type, size, name, `key`, signature, created)
                                    VALUES ('T', :t, :s, :n, :k, :sig, NOW())
                                    """), {"t": file.content_type, "s": len(data), "n": file.filename,
                                           "k": f_hash[:32], "sig": f_hash}).lastrowid

            conn.execute(text("INSERT INTO ost_file_chunk (file_id, chunk_id, filedata) VALUES (:fid, 0, :d)"),
                         {"fid": fid, "d": data})

            conn.execute(text("INSERT INTO ost_attachment (object_id, type, file_id) VALUES (:eid, 'H', :fid)"),
                         {"eid": entry_id, "fid": fid})

            return {"file_id": fid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred while processing the attachment.") from e


@app.post("/tickets/{ticket_id}/messages/{entry_id}/attach", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=AttachmentResponse, deprecated=True)
async def add_attachment_deprecated(ticket_id: int, entry_id: int, file: UploadFile = File(...)):
    """Deprecated: use `POST /tickets/{ticket_id}/messages/{entry_id}/attachments` instead."""
    return await add_attachment(ticket_id, entry_id, file)


@app.post("/tickets/{ticket_id}/notes", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=NoteResponse)
def add_note(ticket_id: int, note: NoteCreate):
    """
    Add an internal note to a ticket's thread.

    Notes are staff-only: unlike a message/response, they are never visible
    to the ticket's owner and generate no outbound email. Useful for
    integrations to leave an audit trail (e.g. "Forwarded to Ops as #123")
    without notifying the requester. Returns 404 if the ticket does not exist.
    """
    try:
        with _get_engine().begin() as conn:
            thread_id = conn.execute(
                text("SELECT id FROM ost_thread WHERE object_id = :tid AND object_type = 'T'"),
                {"tid": ticket_id}).scalar()
            if thread_id is None:
                raise HTTPException(status_code=404, detail="Ticket not found.")

            res = conn.execute(text("""
                                    INSERT INTO ost_thread_entry (thread_id, type, title, body, poster, source, created, updated)
                                    VALUES (:thid, 'N', :title, :body, :poster, 'API', NOW(), NOW())
                                    """), {"thid": thread_id, "title": note.title or "", "body": note.body,
                                           "poster": note.poster or "API"})

            return {"entry_id": res.lastrowid}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred while adding the note.") from e


@app.post("/tickets/{ticket_id}/note", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=NoteResponse, deprecated=True)
def add_note_deprecated(ticket_id: int, note: NoteCreate):
    """Deprecated: use `POST /tickets/{ticket_id}/notes` instead."""
    return add_note(ticket_id, note)


@app.post("/tickets/{ticket_id}/messages", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=MessageResponse)
def add_message(ticket_id: int, message: MessageCreate):
    """Add a public message or reply to a ticket's thread."""
    try:
        with _get_engine().begin() as conn:
            thread_id = conn.execute(
                text("""
                    SELECT th.id
                    FROM ost_ticket t
                    JOIN ost_thread th ON th.object_id = t.ticket_id AND th.object_type = 'T'
                    WHERE t.ticket_id = :ticket_id
                    ORDER BY th.id
                    LIMIT 1
                """),
                {"ticket_id": ticket_id}).scalar_one_or_none()
            if thread_id is None:
                raise HTTPException(status_code=404, detail="Ticket not found or has no thread.")

            entry_id = conn.execute(text("""
                INSERT INTO ost_thread_entry (thread_id, type, title, body, poster, source, created, updated)
                VALUES (:thread_id, :type, :title, :body, :poster, 'API', NOW(), NOW())
                """), {
                    "thread_id": thread_id,
                    "type": message.type or "M",
                    "title": message.title or "",
                    "body": message.body,
                    "poster": message.poster or "API",
                }).lastrowid

            conn.execute(text("""
                UPDATE ost_thread
                SET lastmessage = NOW(), lastresponse = NOW()
                WHERE id = :thread_id
                """), {"thread_id": thread_id})
            conn.execute(
                text("UPDATE ost_ticket SET updated = NOW() WHERE ticket_id = :ticket_id"),
                {"ticket_id": ticket_id})

            return {"thread_id": thread_id, "entry_id": entry_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred while adding the message.") from e


@app.post("/tickets/{ticket_id}/message", dependencies=[Depends(verify_token)], tags=["Tickets"],
          response_model=MessageResponse, deprecated=True)
def add_message_deprecated(ticket_id: int, message: MessageCreate):
    """Deprecated: use `POST /tickets/{ticket_id}/messages` instead."""
    return add_message(ticket_id, message)


@app.patch("/tickets/{ticket_id}/status", dependencies=[Depends(verify_token)], tags=["Tickets"],
           response_model=UpdateResponse)
def update_ticket_status(ticket_id: int, payload: StatusUpdateRequest):
    """Update a ticket's status."""
    with _get_engine().begin() as conn:
        result = conn.execute(
            text("UPDATE ost_ticket SET status_id = :status_id, updated = NOW() WHERE ticket_id = :id"),
            {"status_id": payload.status_id, "id": ticket_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return {"status": "updated"}


@app.put("/tickets/{ticket_id}/status", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
def update_ticket_status_put_deprecated(ticket_id: int, payload: StatusUpdateRequest):
    """Deprecated: use `PATCH /tickets/{ticket_id}/status` instead."""
    return update_ticket_status(ticket_id, payload)


@app.patch("/tickets/{ticket_id}/department", dependencies=[Depends(verify_token)], tags=["Tickets"],
           response_model=UpdateResponse)
def update_ticket_department(ticket_id: int, payload: DepartmentUpdateRequest):
    """Update the department assigned to a ticket."""
    with _get_engine().begin() as conn:
        result = conn.execute(
            text("UPDATE ost_ticket SET dept_id = :dept_id, updated = NOW() WHERE ticket_id = :id"),
            {"dept_id": payload.dept_id, "id": ticket_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return {"status": "updated"}


@app.put("/tickets/{ticket_id}/department", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
def update_ticket_department_put_deprecated(ticket_id: int, payload: DepartmentUpdateRequest):
    """Deprecated: use `PATCH /tickets/{ticket_id}/department` instead."""
    return update_ticket_department(ticket_id, payload)


@app.patch("/tickets/{ticket_id}/team", dependencies=[Depends(verify_token)], tags=["Tickets"],
           response_model=UpdateResponse)
def update_ticket_team(ticket_id: int, payload: TeamUpdateRequest):
    """Update the team assigned to a ticket."""
    with _get_engine().begin() as conn:
        result = conn.execute(
            text("UPDATE ost_ticket SET team_id = :team_id, updated = NOW() WHERE ticket_id = :id"),
            {"team_id": payload.team_id, "id": ticket_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return {"status": "updated"}


@app.put("/tickets/{ticket_id}/team", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
def update_ticket_team_put_deprecated(ticket_id: int, payload: TeamUpdateRequest):
    """Deprecated: use `PATCH /tickets/{ticket_id}/team` instead."""
    return update_ticket_team(ticket_id, payload)


def _apply_message_entry_update(conn, ticket_id: int, entry_id: int, payload: MessageUpdateRequest):
    updates = ["updated = NOW()"]
    params = {"entry_id": entry_id}
    if payload.title is not None:
        updates.append("title = :title")
        params["title"] = payload.title
    if payload.body is not None:
        updates.append("body = :body")
        params["body"] = payload.body

    conn.execute(
        text(f"UPDATE ost_thread_entry SET {', '.join(updates)} WHERE id = :entry_id"),
        params
    )
    conn.execute(
        text("UPDATE ost_ticket SET updated = NOW() WHERE ticket_id = :ticket_id"),
        {"ticket_id": ticket_id}
    )


@app.patch("/tickets/{ticket_id}/messages/{entry_id}", dependencies=[Depends(verify_token)], tags=["Tickets"],
           response_model=UpdateResponse)
def update_ticket_message_entry(ticket_id: int, entry_id: int, payload: MessageUpdateRequest):
    """Update a specific message entry on a ticket's thread."""
    if payload.title is None and payload.body is None:
        raise HTTPException(status_code=400, detail="At least one of title or body must be provided.")

    with _get_engine().begin() as conn:
        exists = conn.execute(
            text("""
                SELECT 1
                FROM ost_thread_entry te
                JOIN ost_thread th ON te.thread_id = th.id
                WHERE th.object_id = :ticket_id AND th.object_type = 'T' AND te.id = :entry_id
            """),
            {"ticket_id": ticket_id, "entry_id": entry_id}
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="Ticket or message not found.")

        _apply_message_entry_update(conn, ticket_id, entry_id, payload)
        return {"status": "updated"}


@app.put("/tickets/{ticket_id}/messages/{entry_id}", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
def update_ticket_message_entry_put_deprecated(ticket_id: int, entry_id: int, payload: MessageUpdateRequest):
    """Deprecated: use `PATCH /tickets/{ticket_id}/messages/{entry_id}` instead."""
    return update_ticket_message_entry(ticket_id, entry_id, payload)


@app.put("/tickets/{ticket_id}/message", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
def update_ticket_message(ticket_id: int, payload: MessageUpdateRequest):
    """
    Deprecated: use `PATCH /tickets/{ticket_id}/messages/{entry_id}` instead.

    Update the latest message entry on a ticket thread.
    """
    if payload.title is None and payload.body is None:
        raise HTTPException(status_code=400, detail="At least one of title or body must be provided.")

    with _get_engine().begin() as conn:
        entry = conn.execute(
            text("""
                SELECT te.id
                FROM ost_thread_entry te
                JOIN ost_thread th ON te.thread_id = th.id
                WHERE th.object_id = :ticket_id AND th.object_type = 'T'
                ORDER BY te.id DESC
                LIMIT 1
            """),
            {"ticket_id": ticket_id}
        ).scalar_one_or_none()
        if entry is None:
            raise HTTPException(status_code=404, detail="Ticket not found or has no thread entries.")

        _apply_message_entry_update(conn, ticket_id, entry, payload)
        return {"status": "updated"}


@app.patch("/tickets/{ticket_id}/attachments/{file_id}", dependencies=[Depends(verify_token)], tags=["Tickets"],
           response_model=UpdateResponse)
async def update_ticket_attachment(ticket_id: int, file_id: int, file: UploadFile = File(...)):
    """Replace the contents of an existing attachment on a ticket."""
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_MB} MB.")

    f_hash = base64.b64encode(hashlib.sha256(data).digest()).decode()

    try:
        with _get_engine().begin() as conn:
            attachment = conn.execute(
                text("""
                    SELECT a.object_id
                    FROM ost_attachment a
                    JOIN ost_thread_entry te ON te.id = a.object_id
                    JOIN ost_thread th ON th.id = te.thread_id
                    WHERE a.file_id = :file_id AND a.type = 'H' AND th.object_id = :ticket_id AND th.object_type = 'T'
                """),
                {"file_id": file_id, "ticket_id": ticket_id}
            ).scalar_one_or_none()
            if attachment is None:
                raise HTTPException(status_code=404, detail="Attachment not found for this ticket.")

            conn.execute(
                text("""
                    UPDATE ost_file
                    SET ft = :ft, type = :file_type, size = :size, name = :name, `key` = :key, signature = :sig
                    WHERE id = :file_id
                """),
                {
                    "ft": "T",
                    "file_type": file.content_type,
                    "size": len(data),
                    "name": file.filename,
                    "key": f_hash[:32],
                    "sig": f_hash,
                    "file_id": file_id,
                }
            )
            conn.execute(
                text("DELETE FROM ost_file_chunk WHERE file_id = :file_id AND chunk_id = 0"),
                {"file_id": file_id}
            )
            conn.execute(
                text("INSERT INTO ost_file_chunk (file_id, chunk_id, filedata) VALUES (:file_id, 0, :data)"),
                {"file_id": file_id, "data": data}
            )
            conn.execute(
                text("UPDATE ost_ticket SET updated = NOW() WHERE ticket_id = :ticket_id"),
                {"ticket_id": ticket_id}
            )
            return {"status": "updated"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="An internal error occurred while updating the attachment.") from e


@app.put("/tickets/{ticket_id}/attachments/{file_id}", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
async def update_ticket_attachment_put_deprecated(ticket_id: int, file_id: int, file: UploadFile = File(...)):
    """Deprecated: use `PATCH /tickets/{ticket_id}/attachments/{file_id}` instead."""
    return await update_ticket_attachment(ticket_id, file_id, file)


@app.put("/tickets/{ticket_id}/attachment/{file_id}", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=UpdateResponse, deprecated=True)
async def update_ticket_attachment_deprecated(ticket_id: int, file_id: int, file: UploadFile = File(...)):
    """Deprecated: use `PATCH /tickets/{ticket_id}/attachments/{file_id}` instead."""
    return await update_ticket_attachment(ticket_id, file_id, file)


@app.put("/tickets/{ticket_id}/closed", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=CloseResponse)
def close_ticket(ticket_id: int):
    """
    Close a ticket.

    This is a convenience endpoint that sets the ticket's status to 'closed' (typically status_id 3)
    and updates its `closed` and `updated` timestamps.
    """
    with _get_engine().begin() as conn:
        closed_status_id = _get_status_id(conn, "closed")

        result = conn.execute(
            text("UPDATE ost_ticket SET status_id = :status_id, closed = NOW(), updated = NOW() WHERE ticket_id = :id"),
            {"status_id": closed_status_id, "id": ticket_id}
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Ticket not found.")

        return {"status": "closed"}


@app.put("/tickets/{ticket_id}/close", dependencies=[Depends(verify_token)], tags=["Tickets"],
         response_model=CloseResponse, deprecated=True)
def close_ticket_deprecated(ticket_id: int):
    """Deprecated: use `PUT /tickets/{ticket_id}/closed` instead."""
    return close_ticket(ticket_id)


@app.get("/", include_in_schema=False)
async def redirect_to_docs(request: Request):  # pragma: no cover
    return RedirectResponse(url=f"{request.scope.get('root_path', '')}/redoc")


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    # Load .env file for direct script execution
    load_dotenv()
    port = int(os.environ.get("PORT", 8080))
    root_path = os.environ.get("ROOT_PATH", "")
    uvicorn.run(app, host="0.0.0.0", port=port, root_path=root_path)
