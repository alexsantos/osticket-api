import pytest
from unittest.mock import Mock
from utils import make_url
from main import _server_supports_json_functions

def test_make_url():
    """
    Unit tests for the make_url utility function.
    """
    # --- 1. Mock the FastAPI Request object ---
    # We only need the 'url' and 'query_params' attributes for this test.
    mock_request = Mock()
    mock_request.url = "http://testserver/users?email=test@example.com"
    mock_request.query_params = {"email": "test@example.com", "limit": "50", "offset": "0"}

    # --- 2. Test generating a 'next' URL ---
    next_url = make_url(request=mock_request, limit=50, offset=50)
    # The query parameters should be correctly ordered and encoded
    assert next_url == "http://testserver/users?email=test%40example.com&limit=50&offset=50"

    # --- 3. Test generating a 'previous' URL ---
    # Update the mock for the second scenario
    mock_request.query_params = {"email": "test@example.com", "limit": "50", "offset": "100"}
    prev_url = make_url(request=mock_request, limit=50, offset=50)
    assert prev_url == "http://testserver/users?email=test%40example.com&limit=50&offset=50"

    # --- 4. Test with no initial query parameters ---
    mock_request.url = "http://testserver/users"
    mock_request.query_params = {"limit": "50", "offset": "0"}
    next_url_no_params = make_url(request=mock_request, limit=50, offset=50)
    assert next_url_no_params == "http://testserver/users?limit=50&offset=50"


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
