import hashlib
import hmac
import logging
import re
import threading
import time
from typing import Optional
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

_ROOT_PATH = "/"  # osTicket is root-installed in every known deployment; not derivable from config.
_LOGIN_TIMEOUT = 10
_DOWNLOAD_TIMEOUT = 30
_URL_EXPIRY_SECONDS = 3600

_CSRF_RE = re.compile(r'name=["\']__CSRFToken__["\']\s+value=["\']([^"\']*)["\']')

_base_url: Optional[str] = None
_secret_salt: Optional[str] = None
_staff_username: Optional[str] = None
_staff_password: Optional[str] = None
_enabled: bool = False

_session: Optional[requests.Session] = None
_session_lock = threading.Lock()
_logged_in: bool = False


def init(base_url, secret_salt, staff_username, staff_password) -> None:
    """
    Called once from main.py's lifespan() with the 4 OSTICKET_* env vars.

    Feature is enabled only if all 4 are set; otherwise fetch_attachment_content()
    always returns None immediately (current `content: null` behavior is preserved).
    """
    global _base_url, _secret_salt, _staff_username, _staff_password, _enabled, _session, _logged_in
    _base_url = base_url.rstrip("/") if base_url else None
    _secret_salt, _staff_username, _staff_password = secret_salt, staff_username, staff_password
    _enabled = all([_base_url, _secret_salt, _staff_username, _staff_password])
    _session = requests.Session() if _enabled else None
    _logged_in = False


def build_signature(host: str, root_path: str, file_id: int, key: str,
                     file_hash: str, expires: int, secret_salt: str) -> str:
    """
    Pure function - no I/O, unit-testable directly against a known-good vector.

    CRITICAL: `file_id` MUST be ost_file.id (the FILE's own id), never
    ost_attachment.id. Getting this wrong produces a 404 "Unknown or invalid
    file" that is indistinguishable from a genuine auth/signature/lookup
    failure. The `id=` query param sent to file.php is ost_attachment.id - a
    DIFFERENT value - do not let the two get conflated by reusing one "id"
    variable for both. (See CLAUDE.md.)
    """
    message = f"Host={host}\nPath={root_path}\nId={file_id}\nKey={key}\nHash={file_hash}\nExpires={expires}"
    return hmac.new(secret_salt.encode("utf-8"), message.encode("utf-8"), hashlib.sha1).hexdigest()


def _host_from_base_url() -> str:
    # Host is derived solely from _base_url (single source of truth) so the
    # connection Host header and the signed Host= field can never diverge.
    # NEVER set an explicit Host header anywhere in this module - osTicket
    # validates against $_SERVER['HTTP_HOST'], which must equal whatever the
    # HTTP client naturally sends for _base_url.
    return urlsplit(_base_url).netloc


def _login() -> bool:
    """Must be called while holding _session_lock."""
    try:
        get_resp = _session.get(f"{_base_url}/scp/login.php", timeout=_LOGIN_TIMEOUT)
        match = _CSRF_RE.search(get_resp.text)
        if not match:
            logger.warning("osTicket fallback: no CSRF token found on login page.")
            return False
        post_resp = _session.post(
            f"{_base_url}/scp/login.php",
            data={"userid": _staff_username, "passwd": _staff_password,
                  "__CSRFToken__": match.group(1)},
            timeout=_LOGIN_TIMEOUT,
            allow_redirects=False,  # 302 == success; must not be silently followed
        )
        if post_resp.status_code == 302:
            return True
        logger.warning("osTicket fallback: login failed (status=%s).", post_resp.status_code)
        return False
    except requests.RequestException:
        logger.exception("osTicket fallback: login request failed.")
        return False


def _ensure_logged_in() -> bool:
    global _logged_in
    if _logged_in:
        return True
    with _session_lock:  # double-checked locking: guards only the login handshake
        if not _logged_in:
            _logged_in = _login()
        return _logged_in


def fetch_attachment_content(file_id: int, attachment_id: int, key: str, file_hash: str) -> Optional[bytes]:
    """
    Returns raw bytes on success, or None on any failure/misconfiguration -
    never raises. Called by main.py only when a file has zero ost_file_chunk rows.
    """
    if not _enabled:
        return None
    try:
        if not _ensure_logged_in():
            return None
        lowered_key = key.lower()  # osTicket's signer lowercases the key; must match on both sides
        expires = int(time.time()) + _URL_EXPIRY_SECONDS
        signature = build_signature(
            host=_host_from_base_url(), root_path=_ROOT_PATH,
            file_id=file_id,  # ost_file.id - see build_signature docstring
            key=lowered_key, file_hash=file_hash, expires=expires, secret_salt=_secret_salt,
        )
        resp = _session.get(
            f"{_base_url}/file.php",
            params={"key": lowered_key, "id": attachment_id, "expires": expires, "signature": signature},
            timeout=_DOWNLOAD_TIMEOUT,
        )
        if resp.status_code == 200:
            return resp.content
        logger.warning("osTicket fallback: file.php %s for attachment_id=%s file_id=%s: %.200s",
                        resp.status_code, attachment_id, file_id, resp.text)
        return None
    except requests.RequestException:
        logger.exception("osTicket fallback: file.php request failed for attachment_id=%s.", attachment_id)
        return None
