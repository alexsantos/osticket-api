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
    def __init__(self, status_code=200, text="", content=b""):
        self.status_code = status_code
        self.text = text
        self.content = content


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
