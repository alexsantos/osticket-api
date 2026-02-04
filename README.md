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

## API Keys

This API uses the API keys configured within your osTicket installation. To create and manage API keys, log in to your osTicket admin panel and navigate to `Admin Panel > Manage > API Keys`.

When creating an API key, you can also specify a whitelisted IP address for added security. This API will enforce that whitelist.

## Build Instructions

This project is designed to be run in a Docker container.

### Prerequisites

- Docker installed and running.

### Building the Image

1.  **Clone the repository.**
2.  **Navigate to the project directory.**
3.  **Build the Docker image:**

    ```bash
    docker build -t osticket-api .
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
    -   **Query Parameters:**
        -   `status_id` (optional): Filter by status ID.
        -   `topic_id` (optional): Filter by topic ID.
        -   `dept_id` (optional): Filter by department ID.
        -   `email` (optional): Filter by the ticket owner's email address.
        -   `limit` (optional, default: 50): The maximum number of tickets to return.
        -   `offset` (optional, default: 0): The starting point for pagination.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets?email=user@example.com&limit=10" -H "X-API-Key: your_osTicket_api_key"
        ```

-   **GET /tickets/{ticket_id}**
    -   **Description:** Retrieves a single ticket by its ID.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/123" -H "X-API-Key: your_osTicket_api_key"
        ```

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

-   **POST /tickets/{ticket_id}/attach**
    -   **Description:** Attaches a file to an existing ticket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to attach the file to.
    -   **Form Data:**
        -   `file`: The file to attach.
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets/123/attach" \
        -H "X-API-Key: your_osTicket_api_key" \
        -F "file=@/path/to/your/file.txt"
        ```

-   **PUT /tickets/{ticket_id}/close**
    -   **Description:** Closes a ticket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to close.
    -   **Example:**
        ```bash
        curl -X PUT "http://localhost:8080/tickets/123/close" -H "X-API-Key: your_osTicket_api_key"
        ```
