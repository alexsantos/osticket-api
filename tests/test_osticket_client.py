import pytest
import requests

import osticket_client


def test_build_signature_matches_known_good_vector():
    """
    Golden vector captured from manual validation against a real osTicket
    instance. This is the single most important test in this file - it
    would have caught the file_id-vs-attachment_id bug immediately.
    """
    signature = osticket_client.build_signature(
        host="10.107.0.41",
        root_path="/",
        file_id=129211,
        key="yxor1ahdrhtkf-yttpu5qj2qgm6a6kz8",
        file_hash="aHDRhTkf-yTTPU5QTTxPp0ZM1MNklqxi",
        expires=1788393600,
        secret_salt="sOzFejCth_ZX6NMsb9lXMKpfxf1i2XBP",
    )
    assert signature == "2c12ce4c3e84962be278102dc50bf098ac7cc5d6"


class _FakeResponse:
    def __init__(self, status_code=200, text="", content=b"", headers=None):
        self.status_code = status_code
        self.text = text
        self.content = content
        self.headers = headers or {}


class _FakeSession:
    def __init__(self, get_responses=None, post_responses=None):
        self._get_responses = list(get_responses or [])
        self._post_responses = list(post_responses or [])
        self.get_calls = []
        self.post_calls = []

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if callable(self._get_responses[0]):
            return self._get_responses.pop(0)()
        return self._get_responses.pop(0)

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._post_responses.pop(0)


@pytest.fixture(autouse=True)
def _reset_client_state():
    """Every test starts from a clean, disabled state."""
    osticket_client.init(None, None, None, None)
    yield
    osticket_client.init(None, None, None, None)


def _enable(monkeypatch, fake_session):
    osticket_client._base_url = "http://10.107.0.41"
    osticket_client._secret_salt = "salt"
    osticket_client._staff_username = "apiosticket"
    osticket_client._staff_password = "pw"
    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_session", fake_session)


def test_login_success_parses_csrf_and_posts_credentials(monkeypatch):
    login_page = _FakeResponse(text='<input type="hidden" name="__CSRFToken__" value="abc123" />')
    fake_session = _FakeSession(get_responses=[login_page], post_responses=[_FakeResponse(status_code=302)])
    _enable(monkeypatch, fake_session)

    assert osticket_client._login() is True
    assert fake_session.post_calls[0][1]["data"]["__CSRFToken__"] == "abc123"
    assert fake_session.post_calls[0][1]["data"]["userid"] == "apiosticket"
    assert fake_session.post_calls[0][1]["allow_redirects"] is False


def test_login_failure_returns_false(monkeypatch):
    login_page = _FakeResponse(text='<input type="hidden" name="__CSRFToken__" value="abc123" />')
    fake_session = _FakeSession(get_responses=[login_page], post_responses=[_FakeResponse(status_code=200)])
    _enable(monkeypatch, fake_session)

    assert osticket_client._login() is False


def test_login_missing_csrf_returns_false(monkeypatch):
    fake_session = _FakeSession(get_responses=[_FakeResponse(text="<html>no token here</html>")])
    _enable(monkeypatch, fake_session)

    assert osticket_client._login() is False
    assert fake_session.post_calls == []


def test_ensure_logged_in_only_logs_in_once(monkeypatch):
    call_count = {"n": 0}

    def fake_login():
        call_count["n"] += 1
        return True

    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_login", fake_login)

    assert osticket_client._ensure_logged_in() is True
    assert osticket_client._ensure_logged_in() is True
    assert call_count["n"] == 1


def test_fetch_attachment_content_returns_none_when_disabled():
    assert osticket_client.fetch_attachment_content(
        file_id=1, attachment_id=2, key="k", file_hash="h"
    ) is None


def test_fetch_attachment_content_uses_file_id_not_attachment_id_in_signature(monkeypatch):
    """
    Critical regression guard for the historical bug: the signature must be
    built from file_id, and the file.php query param `id` must be
    attachment_id - the two must never be swapped or conflated.
    """
    captured = {}

    def fake_build_signature(**kwargs):
        captured.update(kwargs)
        return "sig"

    monkeypatch.setattr(osticket_client, "build_signature", fake_build_signature)
    monkeypatch.setattr(osticket_client, "_ensure_logged_in", lambda: True)

    fake_session = _FakeSession(get_responses=[_FakeResponse(status_code=200, content=b"bytes")])
    osticket_client._base_url = "http://10.107.0.41"
    osticket_client._secret_salt = "salt"
    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_session", fake_session)

    result = osticket_client.fetch_attachment_content(
        file_id=111, attachment_id=222, key="K", file_hash="h"
    )

    assert result == b"bytes"
    assert captured["file_id"] == 111
    assert fake_session.get_calls[0][1]["params"]["id"] == 222


def test_fetch_attachment_content_lowercases_key(monkeypatch):
    captured = {}

    def fake_build_signature(**kwargs):
        captured.update(kwargs)
        return "sig"

    monkeypatch.setattr(osticket_client, "build_signature", fake_build_signature)
    monkeypatch.setattr(osticket_client, "_ensure_logged_in", lambda: True)

    fake_session = _FakeSession(get_responses=[_FakeResponse(status_code=200, content=b"bytes")])
    osticket_client._base_url = "http://10.107.0.41"
    osticket_client._secret_salt = "salt"
    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_session", fake_session)

    osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="MiXeDCaSe", file_hash="h")

    assert captured["key"] == "mixedcase"
    assert fake_session.get_calls[0][1]["params"]["key"] == "mixedcase"


def test_fetch_attachment_content_returns_none_on_non_200(monkeypatch):
    monkeypatch.setattr(osticket_client, "_ensure_logged_in", lambda: True)
    fake_session = _FakeSession(get_responses=[_FakeResponse(status_code=404, text="Unknown or invalid file")])
    osticket_client._base_url = "http://10.107.0.41"
    osticket_client._secret_salt = "salt"
    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_session", fake_session)

    assert osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h") is None


def test_fetch_attachment_content_returns_none_on_network_error(monkeypatch):
    monkeypatch.setattr(osticket_client, "_ensure_logged_in", lambda: True)

    class _RaisingSession:
        def get(self, *args, **kwargs):
            raise requests.ConnectionError("boom")

    osticket_client._base_url = "http://10.107.0.41"
    osticket_client._secret_salt = "salt"
    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_session", _RaisingSession())

    assert osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h") is None


def test_fetch_attachment_content_returns_none_when_login_fails(monkeypatch):
    monkeypatch.setattr(osticket_client, "_ensure_logged_in", lambda: False)
    osticket_client._enabled = True

    assert osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h") is None


def _enable_download(monkeypatch, fake_session, login_results):
    """Enables the client with a fake session and a scripted sequence of _login() results."""
    osticket_client._base_url = "http://10.107.0.41"
    osticket_client._secret_salt = "salt"
    osticket_client._enabled = True
    monkeypatch.setattr(osticket_client, "_session", fake_session)
    results = list(login_results)
    calls = {"n": 0}

    def fake_login():
        calls["n"] += 1
        return results.pop(0)

    monkeypatch.setattr(osticket_client, "_login", fake_login)
    return calls


def test_fetch_attachment_content_does_not_follow_redirects(monkeypatch):
    fake_session = _FakeSession(get_responses=[_FakeResponse(status_code=200, content=b"bytes")])
    _enable_download(monkeypatch, fake_session, [True])

    osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h")

    assert fake_session.get_calls[0][1]["allow_redirects"] is False


def test_fetch_attachment_content_relogs_in_and_retries_on_expired_session(monkeypatch):
    expired = _FakeResponse(status_code=302, headers={"Location": "/scp/login.php"})
    ok = _FakeResponse(status_code=200, content=b"bytes")
    fake_session = _FakeSession(get_responses=[expired, ok])
    login_calls = _enable_download(monkeypatch, fake_session, [True, True])
    osticket_client._logged_in = True  # stale cached session from an earlier request
    login_calls["n"] = 0

    result = osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h")

    assert result == b"bytes"
    assert login_calls["n"] == 1
    assert len(fake_session.get_calls) == 2
    assert fake_session.get_calls[0][1]["params"] == fake_session.get_calls[1][1]["params"]


def test_fetch_attachment_content_retries_only_once(monkeypatch):
    expired = _FakeResponse(status_code=302, headers={"Location": "login.php"})
    fake_session = _FakeSession(get_responses=[expired, expired])
    _enable_download(monkeypatch, fake_session, [True, True])

    assert osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h") is None
    assert len(fake_session.get_calls) == 2


def test_fetch_attachment_content_returns_none_when_relogin_fails(monkeypatch):
    expired = _FakeResponse(status_code=302, headers={"Location": "/scp/login.php"})
    fake_session = _FakeSession(get_responses=[expired])
    _enable_download(monkeypatch, fake_session, [True, False])

    assert osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h") is None
    assert len(fake_session.get_calls) == 1


def test_fetch_attachment_content_does_not_retry_non_login_redirect(monkeypatch):
    other = _FakeResponse(status_code=302, headers={"Location": "https://elsewhere.example/file"})
    fake_session = _FakeSession(get_responses=[other])
    _enable_download(monkeypatch, fake_session, [True])

    assert osticket_client.fetch_attachment_content(file_id=1, attachment_id=2, key="k", file_hash="h") is None
    assert len(fake_session.get_calls) == 1


def test_summarize_body_extracts_title_and_visible_text_on_one_line():
    page = (
        "<!DOCTYPE html>\n<html>\n<head>\n<meta charset='utf-8'>\n"
        "<title>422 Unprocessable &amp; Rejected</title>\n"
        "<style>body { color: red; }</style>\n<script>var x = 1;</script>\n</head>\n"
        "<body>\n<h1>Request rejected</h1>\n<p>Reason:   invalid\n parameter</p>\n</body>\n</html>"
    )

    summary = osticket_client._summarize_body(page)

    assert "\n" not in summary
    assert "title='422 Unprocessable & Rejected'" in summary
    assert "Request rejected Reason: invalid parameter" in summary
    assert "color: red" not in summary
    assert "var x" not in summary
    assert "DOCTYPE" not in summary


def test_summarize_body_handles_plain_text_and_empty():
    assert osticket_client._summarize_body("Unknown or invalid file") == "text='Unknown or invalid file'"
    assert osticket_client._summarize_body("") == "text=''"
    assert osticket_client._summarize_body(None) == "text=''"


def test_fetch_attachment_content_logs_readable_error_excerpt(monkeypatch, caplog):
    page = "<!DOCTYPE html>\n<html><head><title>Blocked</title></head><body><p>Policy X</p></body></html>"
    fake_session = _FakeSession(get_responses=[
        _FakeResponse(status_code=422, text=page, headers={"Content-Type": "text/html"})
    ])
    _enable_download(monkeypatch, fake_session, [True])

    with caplog.at_level("WARNING", logger="osticket_client"):
        osticket_client.fetch_attachment_content(file_id=136043, attachment_id=161721, key="k", file_hash="h")

    message = caplog.records[-1].getMessage()
    assert "file.php 422" in message
    assert "title='Blocked'" in message
    assert "Policy X" in message
    assert "\n" not in message
