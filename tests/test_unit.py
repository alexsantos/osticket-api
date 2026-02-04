import pytest
from unittest.mock import Mock
from utils import make_url

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
    next_url = make_url(request=mock_request, limit=50, new_offset=50)
    # The query parameters should be correctly ordered and encoded
    assert next_url == "http://testserver/users?email=test%40example.com&limit=50&offset=50"

    # --- 3. Test generating a 'previous' URL ---
    # Update the mock for the second scenario
    mock_request.query_params = {"email": "test@example.com", "limit": "50", "offset": "100"}
    prev_url = make_url(request=mock_request, limit=50, new_offset=50)
    assert prev_url == "http://testserver/users?email=test%40example.com&limit=50&offset=50"

    # --- 4. Test with no initial query parameters ---
    mock_request.url = "http://testserver/users"
    mock_request.query_params = {"limit": "50", "offset": "0"}
    next_url_no_params = make_url(request=mock_request, limit=50, new_offset=50)
    assert next_url_no_params == "http://testserver/users?limit=50&offset=50"
