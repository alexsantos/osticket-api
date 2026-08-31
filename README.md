![Tests](https://github.com/alexsantos/osticket-api/actions/workflows/tests.yml/badge.svg)
![Coverage](https://codecov.io/gh/alexsantos/osticket-api/branch/main/graph/badge.svg)
# osTicket Ultimate Python API

This project provides a Python-based API for interacting with osTicket, a popular open-source ticketing system. It allows you to create, search, and manage tickets through a simple RESTful interface.

## Disclaimer

This project is not an official API for osTicket, nor does it have any official relationship with the developers of osTicket. It is an independent project that has been tested and confirmed to work with the latest version of osTicket.

## Purpose

The main goal of this project is to offer a modern, flexible, and easy-to-use API for osTicket. It's built with FastAPI, providing high performance and automatic interactive documentation. This API can be used to integrate osTicket with other systems, automate ticket creation, or build custom interfaces.

## Configuration

To run this application, you need to configure the following environment variables.

### Database Variables

- `DB_USER`: The username for the osTicket database.
- `DB_PASSWORD`: The password for the osTicket database.
- `DB_HOST`: The hostname or IP address of the osTicket database server.
- `DB_NAME`: The name of the osTicket database.
- `DB_PORT`: The port of the osTicket database server. Defaults to `3306`.

### Port

- `PORT`: The port on which the application will run. Defaults to `8080`.

### Upload Limit

- `MAX_UPLOAD_MB`: Maximum file size (in megabytes) accepted by the attachment endpoint. Defaults to `10`.

### Root Path

- `ROOT_PATH`: Sub-path the API is mounted under behind a reverse proxy (e.g. `/osticket-dop`). Leave empty when serving from the domain root. The proxy must strip this prefix before forwarding requests to the container; this variable only makes generated URLs (docs, redirects) resolve correctly. Defaults to `` (empty).

## API Keys

This API uses the API keys configured within your osTicket installation. To create and manage API keys, log in to your osTicket admin panel and navigate to `Admin Panel > Manage > API Keys`.

When creating an API key, you can also specify a whitelisted IP address for added security. This API will enforce that whitelist.

## Build Instructions

This project is designed to be run in a Docker container.

### Prerequisites

Docker installed and running.

### Building the Image

1.  **Clone the repository.**
2.  **Navigate to the project directory.**
3.  **Build the Docker image:**

    ```bash
    docker build -t osticket-api .
    ```

### Using a Pre-Built Image

Every published GitHub release is also built and pushed to the GitHub Container Registry:

```bash
docker pull ghcr.io/alexsantos/osticket-api:latest
# or a specific version
docker pull ghcr.io/alexsantos/osticket-api:0.7.0
```

### Running the Container

You can run the container by passing the environment variables directly on the command line.

```bash
docker run -d -p 8080:8080 \
  -e DB_USER="your_db_user" \
  -e DB_PASSWORD="your_db_password" \
  -e DB_HOST="your_db_host" \
  -e DB_NAME="your_db_name" \
  -e DB_PORT="3306" \
  -e PORT="8080" \
  -e MAX_UPLOAD_MB="10" \
  -e ROOT_PATH="/osticket-dop" \
  --name osticket-api-container \
  osticket-api
```

The API will be accessible at `http://localhost:8080`.

## Testing

This project includes a test suite that uses a separate test database.

### Test Database

The test database is managed with Docker Compose. The configuration is in the `docker-compose.test.yml` file:

```yaml
services:
  test-db:
    image: mariadb:10
    container_name: osticket-test-db
    environment:
      # These are the credentials your test suite will use
      MYSQL_ROOT_PASSWORD: testpassword
      MYSQL_DATABASE: osticket_test
      MYSQL_USER: testuser
      MYSQL_PASSWORD: testpassword
    ports:
      # Map the container's port 3306 to the host's port 3307 to avoid conflicts
      # with any local MySQL instance you might be running.
      - "3307:3306"
    volumes:
      # This is the magic part: it mounts your schema file into the directory
      # where MySQL looks for initialization scripts on startup.
      - ./tests/schema/install-mysql.sql:/docker-entrypoint-initdb.d/init.sql
    # MariaDB 10 typically uses 'mysql_native_password' by default, so this command might not be strictly necessary,
    # but keeping it ensures compatibility if the client expects it.
    command: --default-authentication-plugin=mysql_native_password
```

### Running the Tests

1.  **Start the test database:**

    ```bash
    docker-compose -f docker-compose.test.yml up -d
    ```

2.  **Run the tests:**

    ```bash
    pytest
    ```

3.  **Stop the test database:**

    ```bash
    docker-compose -f docker-compose.test.yml down
    ```

## API Endpoints

All endpoints require an `X-API-Key` header with a valid API key created in osTicket.

### Listings

-   **GET /topics**
    -   **Description:** Lists all active help topics.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/topics" -H "X-API-Key: your_osTicket_api_key"
        ```

-   **GET /departments**
    -   **Description:** Lists all available departments.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/departments" -H "X-API-Key: your_osTicket_api_key"
        ```

-   **GET /teams**
    -   **Description:** Lists all available teams.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/teams" -H "X-API-Key: your_osTicket_api_key"
        ```

-   **GET /statuses**
    -   **Description:** Lists all ticket statuses.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/statuses" -H "X-API-Key: your_osTicket_api_key"
        ```

### Users

-   **GET /users**
    -   **Description:** Lists all users with pagination.
    -   **Query Parameters:**
        -   `email` (optional): Filter by email address.
        -   `limit` (optional, default: 50): The maximum number of users to return.
        -   `offset` (optional, default: 0): The starting point for pagination.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/users?email=user@example.com&limit=10" -H "X-API-Key: your_osTicket_api_key"
        ```

-   **GET /users/{user_id}**
    -   **Description:** Retrieves a single user by their ID.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/users/123" -H "X-API-Key: your_osTicket_api_key"
        ```

### Tickets

-   **GET /tickets**
    -   **Description:** Lists all tickets with pagination.
    -   **Standard Query Parameters:**
        -   `status_id`, `topic_id`, `dept_id` (optional): Filter by one or more IDs. You can provide a single ID, a comma-separated list (`?status_id=1,3`), or repeat the parameter (`?status_id=1&status_id=3`).
        -   `email` (optional): Filter by the ticket owner's email address.
        -   `updated_after`, `updated_before` (optional): Filter by the last update timestamp in `YYYY-MM-DDTHH:MM:SS` format.
        -   `limit` (optional, default: 50): The maximum number of tickets to return.
        -   `offset` (optional, default: 0): The starting point for pagination.
    -   **Custom Field Filtering:**
        -   This endpoint supports searching by any custom field created in osTicket's "Dynamic Forms".
        -   To filter by a custom field, use the field's `name` (the variable name set in the form builder) as a query parameter.
        -   Custom field filters also support single or multiple values (comma-separated or repeated).
    -   **Response Data:**
        -   The response for each ticket includes a `custom_fields` object containing the parsed data from any associated custom forms.
    -   **Examples:**
        -   **Basic Search:**
            ```bash
            curl -X GET "http://localhost:8080/tickets?status_id=1&dept_id=22" -H "X-API-Key: your_osTicket_api_key"
            ```
        -   **Date Range Search:**
            ```bash
            curl -X GET "http://localhost:8080/tickets?updated_after=2023-10-27T00:00:00&updated_before=2023-10-28T00:00:00" -H "X-API-Key: your_osTicket_api_key"
            ```
        -   **Custom Field Search:**
            ```bash
            curl -X GET "http://localhost:8080/tickets?order_id=XYZ-123" -H "X-API-Key: your_osTicket_api_key"
            ```
        -   **Multi-Value Custom Field Search (with special characters):**
            ```bash
            curl -X GET "http://localhost:8080/tickets?EFR=Médis,Multicare" -H "X-API-Key: your_osTicket_api_key"
            ```

-   **GET /tickets/{ticket_id}**
    -   **Description:** Retrieves a single ticket by its ID, including all associated custom field data, its original `subject`/`message` (from the ticket thread's first entry), and `closed` timestamp (`null` if still open). Note: `GET /tickets` (list) also includes `subject`/`message`/`custom_fields`, but not `closed` - fetch the individual ticket for that.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/123" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `404` if the ticket does not exist.

-   **GET /tickets/{ticket_id}/messages**
    -   **Description:** Retrieves the messages for a single ticket by its ID.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/123/messages" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `404` if the ticket does not exist or has no messages.

-   **GET /tickets/{ticket_id}/attachments**
    -   **Description:** Retrieves the attachments for a single ticket by its ID, including file metadata, base64-encoded content, and the message entry they belong to.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/123/attachments" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `404` if the ticket does not exist or has no attachments.

### Messages

-   **GET /messages**
    -   **Description:** Retrieves the messages for a comma-separated list of ticket IDs.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/messages?ticket_ids=123,456" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `422` if `ticket_ids` is missing.
        -   `404` if the tickets do not exist or no messages found.

-   **GET /tickets/messages** *(deprecated - use `GET /messages` instead)*
    -   **Description:** Same as `GET /messages`, kept for backward compatibility.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/messages?ticket_ids=123,456" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `422` if `ticket_ids` is missing.
        -   `404` if the tickets do not exist or no messages found.

### Attachments

-   **GET /attachments**
    -   **Description:** Retrieves the attachments for a comma-separated list of ticket IDs, including file metadata, base64-encoded content, and the message entry they belong to.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/attachments?ticket_ids=123,456" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `422` if `ticket_ids` is missing.
        -   `404` if the tickets do not exist or no attachments found.

-   **GET /tickets/attachments** *(deprecated - use `GET /attachments` instead)*
    -   **Description:** Same as `GET /attachments`, kept for backward compatibility.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/attachments?ticket_ids=123,456" -H "X-API-Key: your_osTicket_api_key"
        ```
    -   **Errors:**
        -   `422` if `ticket_ids` is missing.
        -   `404` if the tickets do not exist or no attachments found.

-   **POST /tickets**
    -   **Description:** Creates a new ticket.
    -   **Request Body:**
        ```json
        {
          "user_id": 123,
          "subject": "Test Ticket",
          "message": "This is a test ticket.",
          "topic_id": 1,
          "dept_id": 1
        }
        ```
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "user_id": 123,
          "subject": "Test Ticket",
          "message": "This is a test ticket.",
          "topic_id": 1,
          "dept_id": 1
        }'
        ```

-   **POST /tickets/{ticket_id}/messages/{entry_id}/attachments**
    -   **Description:** Attaches a file to an existing message of an existing ticket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to attach the file to.
        -   `entry_id`: The ID of the entry to attach the file to.
    -   **Form Data:**
        -   `file`: The file to attach. Maximum size is controlled by `MAX_UPLOAD_MB` (default 10 MB). Files exceeding the limit return `413`.
    -   **Errors:**
        -   `404` if the ticket or message do not exist.
        -   `413` if the file exceeds the configured size limit.
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets/123/messages/456/attachments" \
        -H "X-API-Key: your_osTicket_api_key" \
        -F "file=@/path/to/your/file.txt"
        ```

-   **POST /tickets/{ticket_id}/messages/{entry_id}/attach** *(deprecated - use `POST .../messages/{entry_id}/attachments` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **POST /tickets/{ticket_id}/notes**
    -   **Description:** Adds an internal (staff-only) note to a ticket's thread. Notes are never visible to the ticket's owner and generate no outbound email — useful for integrations to leave an audit trail.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to add the note to.
    -   **Request Body:**
        -   `body` (required): The note's content.
        -   `title` (optional): A short title for the note.
        -   `poster` (optional, default: `"API"`): The display name attributed as the note's author.
    -   **Errors:**
        -   `404` if the ticket does not exist.
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets/123/notes" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "body": "Forwarded to Ops as ticket #456.",
          "poster": "Ticket-Sync"
        }'
        ```

-   **POST /tickets/{ticket_id}/note** *(deprecated - use `POST /tickets/{ticket_id}/notes` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **POST /tickets/{ticket_id}/messages**
    -   **Description:** Adds a public message or reply to a ticket's thread and returns the created thread and entry IDs.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to reply to.
    -   **Request Body:**
        -   `type` (optional, default: `"M"`): The message type.
        -   `body` (required): The message content.
        -   `title` (optional): A short subject for the message.
        -   `poster` (optional, default: `"API"`): The display name attributed as the message's author.
    -   **Response:**
        ```json
        {
          "thread_id": 12,
          "entry_id": 34
        }
        ```
    -   **Errors:**
        -   `404` if the ticket does not exist or has no thread.
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets/123/messages" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "title": "Status update",
          "body": "The requested update is ready."
        }'
        ```

-   **POST /tickets/{ticket_id}/message** *(deprecated - use `POST /tickets/{ticket_id}/messages` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **PATCH /tickets/{ticket_id}/status**
    -   **Description:** Updates a ticket's status.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to update.
    -   **Errors:**
        -   `404` if the ticket does not exist.
    -   **Example:**
        ```bash
        curl -X PATCH "http://localhost:8080/tickets/123/status" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "status_id": 1
        }'
        ```

-   **PUT /tickets/{ticket_id}/status** *(deprecated - use `PATCH /tickets/{ticket_id}/status` instead)*
    -   **Description:** Same as above, kept for backward compatibility. `PATCH` is the semantically correct verb for a partial update; `PUT` implies replacing the entire resource.

-   **PATCH /tickets/{ticket_id}/department**
    -   **Description:** Updates a ticket's department.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to update.
    -   **Errors:**
        -   `404` if the ticket does not exist.
    -   **Example:**
        ```bash
        curl -X PATCH "http://localhost:8080/tickets/123/department" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "dept_id": 1
        }'
        ```

-   **PUT /tickets/{ticket_id}/department** *(deprecated - use `PATCH /tickets/{ticket_id}/department` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **PATCH /tickets/{ticket_id}/team**
    -   **Description:** Updates a ticket's team.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to update.
    -   **Errors:**
        -   `404` if the ticket does not exist.
    -   **Example:**
        ```bash
        curl -X PATCH "http://localhost:8080/tickets/123/team" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "team_id": 1
        }'
        ```

-   **PUT /tickets/{ticket_id}/team** *(deprecated - use `PATCH /tickets/{ticket_id}/team` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **PATCH /tickets/{ticket_id}/messages/{entry_id}**
    -   **Description:** Updates a specific message entry on a ticket's thread.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to update.
        -   `entry_id`: The ID of the message entry to update.
    -   **Errors:**
        -   `400` if neither `title` nor `body` is provided.
        -   `404` if the ticket or message entry does not exist.
    -   **Example:**
        ```bash
        curl -X PATCH "http://localhost:8080/tickets/123/messages/456" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "title": "Test Message",
          "body": "This is a test message."
        }'
        ```

-   **PUT /tickets/{ticket_id}/messages/{entry_id}** *(deprecated - use `PATCH /tickets/{ticket_id}/messages/{entry_id}` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **PUT /tickets/{ticket_id}/message** *(deprecated - use `PATCH /tickets/{ticket_id}/messages/{entry_id}` instead)*
    -   **Description:** Updates the latest message entry on a ticket thread, instead of a specifically addressed one. Kept for backward compatibility.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to update.
    -   **Errors:**
        -   `404` if the ticket does not exist.
    -   **Example:**
        ```bash
        curl -X PUT "http://localhost:8080/tickets/123/message" \
        -H "X-API-Key: your_osTicket_api_key" \
        -d '{
          "title": "Test Message",
          "body": "This is a test message."
        }'
        ```

-   **PATCH /tickets/{ticket_id}/attachments/{file_id}**
    -   **Description:** Replaces the contents of an existing attachment on a ticket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to update.
        -   `file_id`: The ID of the attachment to update.
    -   **Form Data:**
        -   `file`: The file to attach. Maximum size is controlled by `MAX_UPLOAD_MB` (default 10 MB). Files exceeding the limit return `413`.
    -   **Errors:**
        -   `404` if the attachment does not exist.
        -   `413` if the file exceeds the configured size limit.
    -   **Example:**
        ```bash
        curl -X PATCH "http://localhost:8080/tickets/123/attachments/1" \
        -H "X-API-Key: your_osTicket_api_key" \
        -F "file=@/path/to/your/file.txt"
        ```

-   **PUT /tickets/{ticket_id}/attachments/{file_id}** *(deprecated - use `PATCH /tickets/{ticket_id}/attachments/{file_id}` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **PUT /tickets/{ticket_id}/attachment/{file_id}** *(deprecated - use `PATCH /tickets/{ticket_id}/attachments/{file_id}` instead)*
    -   **Description:** Same as above, kept for backward compatibility.

-   **PUT /tickets/{ticket_id}/closed**
    -   **Description:** Closes a ticket by setting its status to the configured "closed" state in osTicket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to close.
    -   **Errors:**
        -   `404` if the ticket does not exist.
    -   **Example:**
        ```bash
        curl -X PUT "http://localhost:8080/tickets/123/closed" -H "X-API-Key: your_osTicket_api_key"
        ```

-   **PUT /tickets/{ticket_id}/close** *(deprecated - use `PUT /tickets/{ticket_id}/closed` instead)*
    -   **Description:** Same as above, kept for backward compatibility. `close` is a verb baked into the URL; `closed` names the resulting state instead, the same pattern used e.g. by GitHub's `starred` endpoint.
