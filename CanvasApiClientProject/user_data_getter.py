"""
user_data_getter.py - talks to the Canvas LMS API and stores credentials safely.

Requires:  pip install keyring

The Canvas access token and school URL are stored in the OS credential store
(Windows Credential Locker / macOS Keychain / Linux Secret Service). Nothing
secret is ever written to a file in the project folder, so the repo is safe
to publish.
"""
import json
import re
from datetime import datetime
import urllib.error
import urllib.parse
import urllib.request

import keyring
from keyring.errors import KeyringError, PasswordDeleteError

SERVICE = "canvas-client"
TOKEN_ACCOUNT = "api-token"
URL_ACCOUNT = "base-url"

# Fallback if the machine has no keyring backend (e.g. headless Linux).
# Lives in memory only, so the user has to re-enter the key next launch.
_session = {"token": None, "base_url": None}


class CanvasError(Exception):
    """Something went wrong talking to Canvas. The message is safe to show."""


class CanvasAuthError(CanvasError):
    """Canvas rejected the token."""


# ----------------------------------------------------------------------------
# Credential storage
# ----------------------------------------------------------------------------
def normalize_base_url(base_url):
    """'school.instructure.com/' -> 'https://school.instructure.com'. HTTPS only."""
    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        raise CanvasError("Enter your school's Canvas URL.")
    if "://" not in base_url:
        base_url = "https://" + base_url
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise CanvasError("The Canvas URL must start with https://")
    return f"https://{parsed.netloc}"


def get_credentials():
    """Returns (base_url, token), or None if nothing is stored yet."""
    try:
        token = keyring.get_password(SERVICE, TOKEN_ACCOUNT)
        base_url = keyring.get_password(SERVICE, URL_ACCOUNT)
        if token and base_url:
            return base_url, token
    except KeyringError:
        pass
    if _session["token"] and _session["base_url"]:
        return _session["base_url"], _session["token"]
    return None


def has_credentials():
    return get_credentials() is not None


def save_credentials(base_url, token):
    """Returns True if saved to the OS keyring, False if kept in memory only."""
    try:
        keyring.set_password(SERVICE, TOKEN_ACCOUNT, token)
        keyring.set_password(SERVICE, URL_ACCOUNT, base_url)
        _session["token"] = _session["base_url"] = None
        return True
    except KeyringError:
        _session["token"], _session["base_url"] = token, base_url
        return False


def clear_credentials():
    _session["token"] = _session["base_url"] = None
    for account in (TOKEN_ACCOUNT, URL_ACCOUNT):
        try:
            keyring.delete_password(SERVICE, account)
        except (PasswordDeleteError, KeyringError):
            pass


def mask(token):
    return "not set" if not token else f"••••{token[-4:]}"


# ----------------------------------------------------------------------------
# Canvas API
# ----------------------------------------------------------------------------
_NEXT_LINK = re.compile(r'<([^>]+)>\s*;\s*rel="next"')


def _get(base_url, token, path):
    """GET a Canvas endpoint, following pagination. Never includes the token in errors."""
    url = f"{base_url}/api/v1{path}"
    results = []
    while url:
        request = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                data = json.loads(response.read().decode("utf-8"))
                link_header = response.headers.get("Link", "")
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise CanvasAuthError("Canvas rejected that API key. Check that it is "
                                      "correct and hasn't expired.") from None
            raise CanvasError(f"Canvas returned an error (HTTP {e.code}).") from None
        except urllib.error.URLError as e:
            raise CanvasError(f"Could not reach Canvas: {e.reason}") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise CanvasError("Canvas sent a response that couldn't be read. "
                              "Is the URL correct?") from None

        if not isinstance(data, list):
            return data
        results.extend(data)

        match = _NEXT_LINK.search(link_header)
        url = match.group(1) if match else None
        # Never send the token to a host other than the one the user entered.
        if url and not url.startswith(base_url + "/"):
            break
    return results


def validate(base_url, token):
    """Checks the key works. Returns the normalized base URL, raises CanvasError otherwise."""
    base_url = normalize_base_url(base_url)
    if not token.strip():
        raise CanvasError("Enter your API key.")
    _get(base_url, token.strip(), "/users/self")
    return base_url


def _creds_or_raise():
    creds = get_credentials()
    if not creds:
        raise CanvasAuthError("No API key is set up yet.")
    return creds


def fetch_courses():
    """Returns [[course name, grade], ...] for active courses."""
    base_url, token = _creds_or_raise()
    courses = _get(base_url, token,
                   "/courses?enrollment_state=active&include[]=total_scores&per_page=100")
    rows = []
    for course in courses:
        if not isinstance(course, dict) or not course.get("name"):
            continue  # Canvas returns stubs for courses you can't access
        grade = "N/A"
        for enrollment in course.get("enrollments", []):
            if enrollment.get("computed_current_grade"):
                grade = enrollment["computed_current_grade"]
                break
            if enrollment.get("computed_current_score") is not None:
                grade = f"{enrollment['computed_current_score']}%"
                break
        rows.append([course["name"], grade])
    return rows


# ----------------------------------------------------------------------------
# Date helpers (shared by the to-do list and the calendar so they always agree)
# ----------------------------------------------------------------------------
def format_due(due_at):
    """Canvas UTC timestamp -> 'M/D/YYYY' in the user's local timezone.
    Anything that isn't an ISO timestamp (already formatted, blank, 'No due date')
    is returned unchanged."""
    try:
        due = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return due_at
    if due.tzinfo:
        due = due.astimezone()  # convert to the computer's local timezone
    return f"{due.month}/{due.day}/{due.year}"


def parse_due(text):
    """Text from the to-do list -> datetime.date, or None if it isn't a date.
    Accepts M/D/YYYY (what users see and type) and legacy ISO timestamps."""
    text = (text or "").strip()
    try:
        return datetime.strptime(text, "%m/%d/%Y").date()
    except ValueError:
        pass
    try:
        due = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if due.tzinfo:
            due = due.astimezone()
        return due.date()
    except ValueError:
        return None


def fetch_todo():
    """Returns [[assignment name, due date as M/D/YYYY local], ...] from the Canvas to-do list."""
    base_url, token = _creds_or_raise()
    items = _get(base_url, token, "/users/self/todo?per_page=100")
    rows = []
    for item in items:
        assignment = item.get("assignment") if isinstance(item, dict) else None
        if not assignment:
            continue
        due_at = assignment.get("due_at")
        rows.append([assignment.get("name", "Untitled"),
                     format_due(due_at) if due_at else "No due date"])
    return rows