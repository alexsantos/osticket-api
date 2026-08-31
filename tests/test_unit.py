from datetime import datetime

import pytest
from unittest.mock import Mock
from starlette.datastructures import URL, Headers
from utils import make_url
from main import _server_supports_json_functions
from models import MessagesResponse


def _mock_request(url: str, query_params: dict, headers: dict = None) -> Mock:
    mock_request = Mock()
    mock_request.url = URL(url)
    mock_request.query_params = query_params
    mock_request.headers = Headers(headers or {})
    return mock_request


def test_make_url():
    """
    Unit tests for the make_url utility function.
    """
    # --- 1. Test generating a 'next' URL ---
    mock_request = _mock_request(
        "http://testserver/users?email=test@example.com",
        {"email": "test@example.com", "limit": "50", "offset": "0"},
    )
    next_url = make_url(request=mock_request, limit=50, offset=50)
    # The query parameters should be correctly ordered and encoded
    assert next_url == "http://testserver/users?email=test%40example.com&limit=50&offset=50"

    # --- 2. Test generating a 'previous' URL ---
    mock_request = _mock_request(
        "http://testserver/users?email=test@example.com",
        {"email": "test@example.com", "limit": "50", "offset": "100"},
    )
    prev_url = make_url(request=mock_request, limit=50, offset=50)
    assert prev_url == "http://testserver/users?email=test%40example.com&limit=50&offset=50"

    # --- 3. Test with no initial query parameters ---
    mock_request = _mock_request(
        "http://testserver/users",
        {"limit": "50", "offset": "0"},
    )
    next_url_no_params = make_url(request=mock_request, limit=50, offset=50)
    assert next_url_no_params == "http://testserver/users?limit=50&offset=50"


def test_make_url_prefers_forwarded_headers():
    """
    Behind a gateway (e.g. Cloud Run fronted by an API facade), the ASGI
    scope only sees the internal host. X-Forwarded-Proto/X-Forwarded-Host
    should be used to rebuild the URL the client actually called, when present.
    """
    mock_request = _mock_request(
        "http://osticket-dgp-api-ext-a-648469268857.europe-west4.run.app/tickets",
        {"limit": "50", "offset": "0"},
        headers={
            "x-forwarded-proto": "https",
            "x-forwarded-host": "integration-facade.apis.uat.jmslab.pt",
        },
    )
    next_url = make_url(request=mock_request, limit=50, offset=50)
    assert next_url == "https://integration-facade.apis.uat.jmslab.pt/tickets?limit=50&offset=50"


def test_make_url_falls_back_without_forwarded_headers():
    """No X-Forwarded-* headers -> behavior is unchanged from before."""
    mock_request = _mock_request(
        "http://osticket-dgp-api-ext-a-648469268857.europe-west4.run.app/tickets",
        {"limit": "50", "offset": "0"},
    )
    next_url = make_url(request=mock_request, limit=50, offset=50)
    assert next_url == "http://osticket-dgp-api-ext-a-648469268857.europe-west4.run.app/tickets?limit=50&offset=50"


@pytest.mark.parametrize("version_string, expected", [
    # Real-world report: old MariaDB, no JSON functions.
    ("5.5.68-MariaDB", False),
    # Real-world report: MariaDB's "5.5.5-" compatibility-prefixed string,
    # where the real version (10.11.5) does support JSON functions.
    ("5.5.5-10.11.5-MariaDB", True),
    # MariaDB right at the 10.2 boundary.
    ("10.2.0-MariaDB", True),
    ("10.1.48-MariaDB", False),
    # Debian/Ubuntu package builds append extra suffixes after "-MariaDB".
    ("10.6.12-MariaDB-0ubuntu0.22.04.1", True),
    # Plain MySQL, with and without a "-log" style suffix.
    ("8.0.34", True),
    ("5.7.8-log", True),
    ("5.6.51-log", False),
    # Unrecognized format: assume a modern server rather than degrading filters.
    ("not-a-version", True),
])
def test_server_supports_json_functions(version_string, expected):
    """
    Unit tests for the version-string parsing that decides whether the
    connected server supports JSON_EXTRACT/JSON_UNQUOTE (MariaDB >= 10.2,
    MySQL >= 5.7.8), including MariaDB's quirky compatibility-prefixed
    "5.5.5-10.11.5-MariaDB" version string format.
    """
    assert _server_supports_json_functions(version_string) is expected


def test_messages_response_tolerates_null_updated():
    """
    Some osTicket installations have ost_thread_entry rows with a NULL
    `updated` column (e.g. legacy rows predating a schema change), even
    though `created` is always populated. The response model must not
    reject those rows.
    """
    row = MessagesResponse(
        ticket_id=1,
        thread_id=1,
        entry_id=1,
        type="M",
        poster="API",
        created=datetime(2026, 1, 1),
        updated=None,
    )
    assert row.updated is None
