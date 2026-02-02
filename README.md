# osTicket Ultimate Python API

This project provides a Python-based API for interacting with osTicket, a popular open-source ticketing system. It allows you to create, search, and manage tickets through a simple RESTful interface.

## Purpose

The main goal of this project is to offer a modern, flexible, and easy-to-use API for osTicket. It's built with FastAPI, providing high performance and automatic interactive documentation. This API can be used to integrate osTicket with other systems, automate ticket creation, or build custom interfaces.

## Configuration

To run this application, you need to configure the following environment variables. You can create a `.env` file in the root of the project to store these values. An example file `.env.example` is provided.

### API Keys

- `API_KEYS`: A comma-separated list of API keys that are authorized to use the API.
  - Example: `API_KEYS="key1,key2,another-secret-key"`

### Database Variables

- `DB_USER`: The username for the osTicket database.
- `DB_PASSWORD`: The password for the osTicket database.
- `DB_HOST`: The hostname or IP address of the osTicket database server.
- `DB_NAME`: The name of the osTicket database.

### Port

- `PORT`: The port on which the application will run. Defaults to `8080`.

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

1.  **Create a `.env` file** with the necessary environment variables (as described in the Configuration section).
2.  **Run the Docker container:**

    ```bash
    docker run -d -p 8080:8080 --env-file .env --name osticket-api-container osticket-api
    ```

The API will be accessible at `http://localhost:8080`.

## API Endpoints

All endpoints require an `X-API-Key` header with a valid API key.

### Listings

-   **GET /topics**
    -   **Description:** Lists all active help topics.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/topics" -H "X-API-Key: your_api_key"
        ```

-   **GET /departments**
    -   **Description:** Lists all available departments.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/departments" -H "X-API-Key: your_api_key"
        ```

-   **GET /statuses**
    -   **Description:** Lists all ticket statuses.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/statuses" -H "X-API-Key: your_api_key"
        ```

### Search

-   **GET /tickets/search**
    -   **Description:** Searches for tickets based on various criteria.
    -   **Query Parameters:**
        -   `status_id` (optional): Filter by status ID.
        -   `topic_id` (optional): Filter by topic ID.
        -   `dept_id` (optional): Filter by department ID.
        -   `email` (optional): Filter by the ticket owner's email address.
        -   `limit` (optional, default: 50): The maximum number of tickets to return.
        -   `offset` (optional, default: 0): The starting point for pagination.
    -   **Example:**
        ```bash
        curl -X GET "http://localhost:8080/tickets/search?email=user@example.com&limit=10" -H "X-API-Key: your_api_key"
        ```

### Core

-   **POST /tickets**
    -   **Description:** Creates a new ticket.
    -   **Request Body:**
        ```json
        {
          "name": "John Doe",
          "email": "john.doe@example.com",
          "subject": "Test Ticket",
          "message": "This is a test ticket.",
          "topic_id": 1
        }
        ```
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets" \
        -H "Content-Type: application/json" \
        -H "X-API-Key: your_api_key" \
        -d '{
          "name": "John Doe",
          "email": "john.doe@example.com",
          "subject": "Test Ticket",
          "message": "This is a test ticket.",
          "topic_id": 1
        }'
        ```

### Attachments

-   **POST /tickets/{ticket_id}/attach**
    -   **Description:** Attaches a file to an existing ticket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to attach the file to.
    -   **Form Data:**
        -   `file`: The file to attach.
    -   **Example:**
        ```bash
        curl -X POST "http://localhost:8080/tickets/123/attach" \
        -H "X-API-Key: your_api_key" \
        -F "file=@/path/to/your/file.txt"
        ```

### Status

-   **PUT /tickets/{ticket_id}/close**
    -   **Description:** Closes a ticket.
    -   **Path Parameter:**
        -   `ticket_id`: The ID of the ticket to close.
    -   **Example:**
        ```bash
        curl -X PUT "http://localhost:8080/tickets/123/close" -H "X-API-Key: your_api_key"
        ```
