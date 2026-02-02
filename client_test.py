import requests

# Settings
BASE_URL = "http://localhost:8000"
API_KEY = "YOUR_MASTER_KEY_HERE"  # Must be the same as defined on the server
HEADERS = {"X-API-Key": API_KEY}


def test_osticket_api():
    print("--- Starting osTicket API Tests ---")

    # 1. Create a Ticket
    # ticket_data = {
    #     "name": "John Smith",
    #     "email": "john@example.com",
    #     "subject": "System Access Error",
    #     "message": "I can't log in since this morning. Error 403 appears.",
    #     "topic_id": 1
    # }
    #
    # response = requests.post(f"{BASE_URL}/tickets", json=ticket_data, headers=HEADERS)
    # if response.status_code == 200:
    #     ticket = response.json()
    #     ticket_id = ticket["ticket_id"]
    #     ticket_num = ticket["number"]
    #     print(f"[OK] Ticket created! ID: {ticket_id} | Number: {ticket_num}")
    # else:
    #     print(f"[ERROR] Failed to create ticket: {response.text}")
    #     return

    # 2. Attach a file to the created ticket
    # Let's create a temporary log file for testing
    # with open("error_log.txt", "w") as f:
    #     f.write("DEBUG: Authentication failure in the security module.")
    #
    # with open("error_log.txt", "rb") as f:
    #     files = {"file": ("error_log.txt", f, "text/plain")}
    #     response = requests.post(f"{BASE_URL}/tickets/{ticket_id}/attach", files=files, headers=HEADERS)
    #
    # if response.status_code == 200:
    #     print(f"[OK] Attachment sent successfully! File ID: {response.json()['file_id']}")
    # else:
    #     print(f"[ERROR] Failed to send attachment: {response.text}")

    # 3. Search for the ticket by email
    response = requests.get(f"{BASE_URL}/tickets/search", params={"email": "efr-communications-prod@cuf.pt"}, headers=HEADERS)
    if response.status_code == 200:
        found_tickets = response.json()
        print(f"[OK] Tickets found for this email: {len(found_tickets)}")

    # 4. Close the ticket
    # response = requests.put(f"{BASE_URL}/tickets/{ticket_id}/close", headers=HEADERS)
    # if response.status_code == 200:
    #     print(f"[OK] Ticket {ticket_num} was closed successfully.")
    # else:
    #     print(f"[ERROR] Failed to close ticket.")


if __name__ == "__main__":
    try:
        test_osticket_api()
    except requests.exceptions.ConnectionError:
        print("[ERROR] The FastAPI server is not running. Run 'uvicorn main:app --reload' first.")